import io
import os
import tempfile
import threading
import webbrowser
import winreg
import requests
import pystray
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk

from core.config_manager import (
    APP_TITLE,
    APP_VERSION,
    REG_NAME,
    GSI_PORT,
    WEB_URL,
    HTTP_HEADERS,
    ROBLOX_FALLBACK_LOGO,
    GACHA_SUB_GAME_DEFS,
    CFG,
    Reg,
    get_app_icon,
    make_roblox_fallback_thumb,
    make_game_fallback_thumb,
)
from core.state import SessionState
from core.engine import Engine
from ui.modals import (
    ToolTip,
    LicenseModal,
    UpdatePromptModal,
    PatchNotesModal,
    AddCustomAppModal,
)


class LangleyApp(tk.Tk):
    PAL = {
        "outer_bg": "#B2AB99",
        "panel_bg": "#6E695A",
        "card_bg": "#5D584B",
        "card_alt": "#534E42",
        "border_dark": "#454138",
        "border_light": "#DCD6C4",
        "text_primary": "#F0EAD8",
        "text_muted": "#C2B9A7",
        "status_ok": "#C8D6B9",
        "status_warn": "#E6D0A3",
        "status_err": "#D6A79A",
    }

    PRIORITY_ORDER = [
        "auto",
        "fortnite",
        "minecraft",
        "gacha",
        "riot",
        "ea",
        "ubisoft",
        "gog",
        "battlenet",
        "steam",
        "roblox",
        "xbox",
        "custom_apps",
    ]

    def _safe_after(self, cb):
        try:
            self.after(0, cb)
        except Exception:
            pass

    def __init__(self, minimized=False):
        super().__init__()
        self.state = SessionState()
        self.engine = Engine(
            self.state,
            on_ui=lambda: self._safe_after(self.refresh_ui),
            on_update_found=lambda: self._safe_after(self._notify_update_available),
        )
        self.tray = None
        self.update_modal = None
        self.license_modal = None
        self.patch_notes_modal = None
        self.add_custom_modal = None
        self.current_tab = "dashboard"
        self.gamehub_subtab = "library"
        self.gamehub_lib_filter = "all"
        self.friends_platform = "epic"
        self.friends_filter_online = False
        self.thumb_cache = {}
        self.current_thumb_url = ""
        self._tk_preview_thumb = None
        self._ico_path = None
        self._ico_16 = None
        self._ico_32 = None
        self._ico_64 = None

        self.title(APP_TITLE)
        self.geometry("500x616")
        self.resizable(False, False)
        self.configure(bg=self.PAL["outer_bg"])

        self.pil_icon = get_app_icon()
        self._setup_icons()
        self._draw_bg()
        self._build_widgets()
        self._init_tray()

        # Bind mousewheel globally once on the root window (never unbind on <Leave>)
        self.bind_all("<MouseWheel>", self._on_mousewheel)

        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.engine.start()
        self.after(60, self._reapply_titlebar_icon)
        self.after(1000, self._tick)
        if minimized:
            self.withdraw()

    def _tip(self, widget, text):
        ToolTip(widget, text, self.PAL)
        return widget

    def _setup_icons(self):
        try:
            ico_16_pil = self.pil_icon.resize((16, 16), Image.LANCZOS)
            ico_24_pil = self.pil_icon.resize((24, 24), Image.LANCZOS)
            ico_32_pil = self.pil_icon.resize((32, 32), Image.LANCZOS)
            ico_48_pil = self.pil_icon.resize((48, 48), Image.LANCZOS)
            ico_64_pil = self.pil_icon.resize((64, 64), Image.LANCZOS)

            self._ico_16 = ImageTk.PhotoImage(ico_16_pil)
            self._ico_32 = ImageTk.PhotoImage(ico_32_pil)
            self._ico_64 = ImageTk.PhotoImage(ico_64_pil)

            self._ico_path = os.path.join(
                tempfile.gettempdir(), "langley_window_icon_v105.ico"
            )
            ico_64_pil.save(
                self._ico_path,
                format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)],
                append_images=[ico_48_pil, ico_32_pil, ico_24_pil, ico_16_pil],
            )
            self.iconbitmap(self._ico_path)
            self.wm_iconphoto(True, self._ico_64, self._ico_32, self._ico_16)
        except Exception:
            pass

        try:
            buf_hdr = io.BytesIO()
            self.pil_icon.resize((22, 22), Image.LANCZOS).save(buf_hdr, format="PNG")
            self._tk_ico_hdr = tk.PhotoImage(data=buf_hdr.getvalue())
        except Exception:
            self._tk_ico_hdr = None

        try:
            fallback_thumb = self.pil_icon.resize((52, 52), Image.LANCZOS)
            self._tk_default_thumb = ImageTk.PhotoImage(fallback_thumb)
        except Exception:
            self._tk_default_thumb = None

    def _reapply_titlebar_icon(self):
        try:
            if self._ico_path and os.path.exists(self._ico_path):
                self.iconbitmap(self._ico_path)
            if self._ico_64 and self._ico_32 and self._ico_16:
                self.wm_iconphoto(True, self._ico_64, self._ico_32, self._ico_16)
        except Exception:
            pass

    def _request_thumbnail(self, url):
        plat = self.state.active_platform()
        headline = self.state.rpc_headline or ""
        cache_key = f"{url}::{plat}::{headline[:24]}"
        if not url or cache_key == self.current_thumb_url:
            return
        self.current_thumb_url = cache_key
        if cache_key in self.thumb_cache:
            self._tk_preview_thumb = self.thumb_cache[cache_key]
            if hasattr(self, "lbl_rpc_thumb"):
                self.lbl_rpc_thumb.config(image=self._tk_preview_thumb)
            return
        threading.Thread(
            target=self._fetch_thumb_worker,
            args=(url, cache_key, plat, headline),
            daemon=True,
        ).start()

    def _fetch_thumb_worker(self, url, cache_key, plat, headline):
        pil_border = None
        clean_title = (headline or "").replace(" with Lang!ley", "").strip()
        try:
            if url and url.startswith("http") and not (url == ROBLOX_FALLBACK_LOGO and "wikimedia" in url):
                r = requests.get(url, headers=HTTP_HEADERS, timeout=4.5)
                if r.status_code == 200 and r.content:
                    im = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    w, h = im.size
                    if w != h:
                        side = min(w, h)
                        im = im.crop(
                            (
                                (w - side) // 2,
                                (h - side) // 2,
                                (w - side) // 2 + side,
                                (h - side) // 2 + side,
                            )
                        )
                    im = im.resize((52, 52), Image.LANCZOS)
                    pil_border = Image.new("RGBA", (56, 56), "#454138")
                    pil_border.paste(im, (2, 2), im)
        except Exception:
            pil_border = None

        if pil_border is None:
            is_roblox = (
                url == ROBLOX_FALLBACK_LOGO
                or "roblox" in (url or "").lower()
                or plat == "roblox"
            )
            try:
                if is_roblox:
                    pil_border = make_roblox_fallback_thumb(52, clean_title)
                else:
                    pil_border = make_game_fallback_thumb(plat, clean_title, 52)
            except Exception:
                pil_border = None

        if pil_border is not None:
            self.after(0, lambda: self._apply_thumb(cache_key, pil_border))

    def _apply_thumb(self, cache_key, pil_img):
        try:
            tk_img = ImageTk.PhotoImage(pil_img)
            if len(self.thumb_cache) > 64:
                self.thumb_cache.clear()
            self.thumb_cache[cache_key] = tk_img
            if self.current_thumb_url == cache_key and hasattr(self, "lbl_rpc_thumb"):
                self._tk_preview_thumb = tk_img
                self.lbl_rpc_thumb.config(image=self._tk_preview_thumb)
        except Exception:
            pass

    @staticmethod
    def _fmt_sec(sec):
        sec = max(0, int(sec))
        m, s = divmod(sec, 60)
        return f"{m:02d}:{s:02d}"

    def _gacha_dash_text(self, l_name, lt):
        s = self.state
        acc = (s.gacha_account_name or "").strip()
        lvl_s = s.gacha_level_str()
        meta = " • ".join(x for x in (acc[:12] if acc else "", lvl_s) if x)
        if not meta:
            g_sum = s.gacha_summary_str()
            meta = g_sum[:16] if g_sum else ""
        head = f"{l_name[:12]} • {meta}" if meta else l_name[:22]
        return f"{head[:34]}  •  ⏱ {lt}"

    def _update_media_progress(self):
        if not hasattr(self, "lbl_time_cur") or not hasattr(self, "prog_canvas"):
            return
        s, p = self.state, self.PAL
        cur = self.engine.media.current_pos()
        s.media_pos = cur
        dur = max(0, int(getattr(s, "media_duration", 0) or 0))
        self.lbl_time_cur.config(text=self._fmt_sec(cur))
        if hasattr(self, "lbl_time_end"):
            self.lbl_time_end.config(text=self._fmt_sec(dur) if dur > 0 else "Live")
        self.prog_canvas.delete("all")
        w = max(10, self.prog_canvas.winfo_width())
        if s.media_title:
            denom = float(dur) if dur > 0 else 210.0
            ratio = min(1.0, (cur / denom) if dur > 0 else ((cur % 210) / 210.0))
            fill_w = max(2, int(w * ratio)) if cur > 0 else 0
            bar_col = p["status_ok"] if s.media_playing else p["status_warn"]
            if fill_w > 0:
                self.prog_canvas.create_rectangle(
                    0, 0, fill_w, 8, fill=bar_col, outline=""
                )

    def _tick(self):
        plat = self.state.active_platform()
        if self.state.running and self.state.fortnite_enabled:
            t = self.state.timer_str("fortnite")
            st = "In Match" if self.state.in_match else "In Lobby"
            col = self.PAL["status_ok"] if self.state.in_match else self.PAL["status_warn"]
            self.lbl_state.config(text=f"{st}  •  ⏱ {t}", fg=col)
        elif self.state.epic_game_running and self.state.fortnite_enabled:
            t = self.state.timer_str("fortnite")
            ename = self.state.epic_game_name or "Epic Game"
            self.lbl_state.config(
                text=f"{ename[:22]}  •  ⏱ {t}", fg=self.PAL["status_ok"]
            )
        if self.state.steam_running and self.state.steam_enabled:
            st_t = self.state.timer_str("steam")
            self.lbl_steam_dash.config(
                text=f"{self.state.steam_game_name[:22]}  •  ⏱ {st_t}",
                fg=self.PAL["status_ok"],
            )
            if hasattr(self, "lbl_steam_tab_status"):
                self.lbl_steam_tab_status.config(
                    text=f"● RUNNING: {self.state.steam_game_name[:24]} ({st_t})",
                    fg=self.PAL["status_ok"],
                )
        if self.state.roblox_running and self.state.roblox_enabled:
            rb_t = self.state.timer_str("roblox")
            rname = self.state.roblox_game_name or "Roblox"
            self.lbl_roblox_dash.config(
                text=f"{rname[:22]}  •  ⏱ {rb_t}", fg=self.PAL["status_ok"]
            )
        if self.state.xbox_running and self.state.xbox_enabled:
            xb_t = self.state.timer_str("xbox")
            xname = self.state.xbox_game_name or "Xbox Game"
            self.lbl_xbox_dash.config(
                text=f"{xname[:22]}  •  ⏱ {xb_t}", fg=self.PAL["status_ok"]
            )

        for l_key, l_en, l_run, l_name in (
            ("gacha", self.state.gacha_enabled, self.state.gacha_running, self.state.gacha_game_name),
            ("riot", self.state.riot_enabled, self.state.riot_running, self.state.riot_game_name),
            ("ea", self.state.ea_enabled, self.state.ea_running, self.state.ea_game_name),
            ("ubisoft", self.state.ubisoft_enabled, self.state.ubisoft_running, self.state.ubisoft_game_name),
            ("gog", self.state.gog_enabled, self.state.gog_running, self.state.gog_game_name),
            ("battlenet", self.state.battlenet_enabled, self.state.battlenet_running, self.state.battlenet_game_name),
            ("custom_apps", self.state.custom_apps_enabled, self.state.custom_app_running, self.state.custom_app_name),
        ):
            if l_en and l_run:
                lt = self.state.timer_str(l_key)
                if l_key == "gacha":
                    self.lbl_launchers_dash.config(
                        text=self._gacha_dash_text(l_name, lt), fg=self.PAL["status_ok"]
                    )
                else:
                    self.lbl_launchers_dash.config(
                        text=f"{l_name[:22]}  •  ⏱ {lt}", fg=self.PAL["status_ok"]
                    )
                break

        if self.state.minecraft_enabled and self.state.minecraft_running:
            mc_t = self.state.timer_str("minecraft")
            cname = self.state.minecraft_client_name or "Minecraft"
            ver = f" {self.state.minecraft_version}" if self.state.minecraft_version else ""
            self.lbl_mc_dash.config(
                text=f"{(cname + ver)[:22]}  •  ⏱ {mc_t}", fg=self.PAL["status_ok"]
            )

        if plat not in ("paused", "idle"):
            self.lbl_rpc_timer.config(text=f"⏱ {self.state.timer_str(plat)} elapsed")
        else:
            self.lbl_rpc_timer.config(text="● Standby Mode")
        self._update_media_progress()
        self.after(1000, self._tick)

    def _show_license_modal(self):
        if self.license_modal and self.license_modal.winfo_exists():
            self.license_modal.lift()
            return
        self.license_modal = LicenseModal(self, self.PAL)

    def _show_patch_notes_modal(self):
        if self.patch_notes_modal and self.patch_notes_modal.winfo_exists():
            self.patch_notes_modal.lift()
            return
        self.patch_notes_modal = PatchNotesModal(self, self.PAL)

    def _show_add_custom_modal(self):
        if self.add_custom_modal and self.add_custom_modal.winfo_exists():
            self.add_custom_modal.lift()
            return
        self.add_custom_modal = AddCustomAppModal(
            self, self.PAL, on_save=self._save_custom_app_callback
        )

    def _save_custom_app_callback(self, exe_path, name, status_text, icon_url):
        self.engine.custom_apps.add_app(exe_path, name, status_text, icon_url)
        self._render_custom_apps_settings_list()
        if self.current_tab == "gamehub":
            self._render_steam_games()
        self.refresh_ui()

    def _notify_update_available(self):
        self.refresh_ui()
        if self.tray and not self.winfo_viewable():
            try:
                self.tray.notify(
                    "A new update is available! Click to choose whether to install.",
                    f"{APP_TITLE} Update Available",
                )
            except Exception:
                pass
        self._show_update_modal()

    def _show_update_modal(self):
        if not self.state.update_available:
            return
        self._show()
        if self.update_modal and self.update_modal.winfo_exists():
            self.update_modal.lift()
            return
        self.update_modal = UpdatePromptModal(
            self, self.PAL, self.state, self.engine.updater, self.shutdown
        )

    def _init_tray(self):
        img = self.pil_icon.resize((64, 64), Image.LANCZOS)
        menu = pystray.Menu(
            pystray.MenuItem(
                f"Open {APP_TITLE}", lambda *_: self.after(0, self._show), default=True
            ),
            pystray.MenuItem(
                "Play / Pause Media", lambda *_: self.engine.media.play_pause()
            ),
            pystray.MenuItem("Next Track", lambda *_: self.engine.media.next_track()),
            pystray.MenuItem(
                "Re-Assert RPC Priority (Medal Guard)",
                lambda *_: threading.Thread(
                    target=self.engine.force_reassert_rpc, daemon=True
                ).start(),
            ),
            pystray.MenuItem(
                "Check for Updates",
                lambda *_: threading.Thread(
                    target=lambda: self.engine.updater.check_now(manual=True),
                    daemon=True,
                ).start(),
            ),
            pystray.MenuItem(
                "Refresh Stats Now",
                lambda *_: threading.Thread(
                    target=self.engine.rescan, daemon=True
                ).start(),
            ),
            pystray.MenuItem("Visit asukaa.de", lambda *_: webbrowser.open(WEB_URL)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Completely", self.shutdown),
        )
        self.tray = pystray.Icon(REG_NAME, img, APP_TITLE, menu)

        def _safe_tray_run():
            try:
                self.tray.run()
            except Exception:
                pass

        threading.Thread(target=_safe_tray_run, daemon=True).start()

    def _show(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self._reapply_titlebar_icon()

    def shutdown(self, *_):
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True

        def _bg_stop():
            try:
                if self.tray:
                    self.tray.stop()
            except Exception:
                pass
            try:
                self.engine.stop()
            except Exception:
                pass

        threading.Thread(target=_bg_stop, daemon=True).start()

        def _begin_ui_close():
            try:
                self.withdraw()
            except Exception:
                pass
            self.after(300, self._finalize_destroy)

        try:
            self.after(0, _begin_ui_close)
        except Exception:
            self._finalize_destroy()

    def _finalize_destroy(self):
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def _draw_bg(self):
        p = self.PAL
        self.cv = tk.Canvas(
            self, width=500, height=616, bg=p["outer_bg"], highlightthickness=0
        )
        self.cv.pack(fill="both", expand=True)
        self.cv.create_rectangle(
            20, 20, 480, 596, fill=p["panel_bg"], outline=p["border_light"], width=2
        )
        self.cv.create_rectangle(
            14, 14, 486, 602, outline=p["border_dark"], width=2
        )
        for x1, y1, x2, y2 in [
            (6, 6, 14, 14),
            (486, 6, 494, 14),
            (6, 602, 14, 610),
            (486, 602, 494, 610),
        ]:
            self.cv.create_rectangle(
                x1, y1, x2, y2, fill=p["border_dark"], outline=""
            )
        for r, c in [(160, "#757061"), (116, "#7E7869"), (72, "#878172")]:
            self.cv.create_oval(
                250 - r, 308 - r, 250 + r, 308 + r, fill=c, outline=""
            )

    def _build_widgets(self):
        p = self.PAL
        hdr = tk.Frame(self.cv, bg=p["border_dark"], padx=10, pady=7)
        self.cv.create_window(250, 46, window=hdr, width=432, height=36)
        if self._tk_ico_hdr:
            tk.Label(hdr, image=self._tk_ico_hdr, bg=p["border_dark"]).pack(
                side="left", padx=(0, 7)
            )
        tk.Label(
            hdr,
            text="Lang!ley - Play Everything. Show Everything.",
            font=("Segoe UI", 9, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
        ).pack(side="left")
        lnk = tk.Label(
            hdr,
            text="asukaa.de ↗",
            font=("Segoe UI", 8, "underline"),
            fg=p["text_muted"],
            bg=p["border_dark"],
            cursor="hand2",
        )
        lnk.pack(side="right")
        lnk.bind("<Button-1>", lambda _: webbrowser.open(WEB_URL))
        self.btn_hdr_update = tk.Button(
            hdr,
            text="⚡ Update",
            command=self._show_update_modal,
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=0,
        )

        # Clean top status bar: shows only Discord connection + full username on left, Medal Guard on right
        sbox = tk.Frame(
            self.cv,
            bg=p["card_bg"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=10,
            pady=4,
        )
        self.cv.create_window(250, 86, window=sbox, width=432, height=30)
        self.lbl_discord = tk.Label(
            sbox,
            text="● Discord: Connecting...",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
            anchor="w",
        )
        self.lbl_discord.pack(side="left", fill="x", expand=True)
        self._tip(
            self.lbl_discord,
            "Shows your live desktop Discord Rich Presence connection and linked Discord username.",
        )

        self.lbl_medal_pill = tk.Label(
            sbox,
            text="● Priority Guard: Armed",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["card_bg"],
            anchor="e",
        )
        self.lbl_medal_pill.pack(side="right")
        self._tip(
            self.lbl_medal_pill,
            "Universal Discord Priority Guard — keeps Lang!ley at #1 priority on Discord above all games, Medal.tv, and overlays.",
        )

        tbar = tk.Frame(self.cv, bg=p["panel_bg"])
        self.cv.create_window(250, 120, window=tbar, width=432, height=28)
        self.tab_btns = {}
        tab_defs = [
            (
                "dashboard",
                "DASHBOARD",
                "Live Discord Rich Presence preview and real-time activity overview.",
            ),
            (
                "gamehub",
                "GAME HUB",
                "Browse & launch installed Steam, Xbox Game Pass, HoYoPlay/Gacha, PC Launchers, and Custom .exe games.",
            ),
            (
                "friends",
                "FRIENDS",
                "View friends and online status across Epic, Steam, Roblox, Xbox Live, Discord, and PC Launchers.",
            ),
            (
                "media",
                "MEDIA",
                "Control Spotify, YouTube Music, or browser audio and show your current song on Discord.",
            ),
            (
                "accounts",
                "ACCOUNTS",
                "Link your Epic Games, Steam, Roblox, and Xbox Live accounts in one place.",
            ),
            (
                "settings",
                "SETTINGS",
                "Customize app preferences, platform priority, Medal.tv guard, game toggles, and custom .exe apps.",
            ),
        ]
        for key, label, tip_txt in tab_defs:
            b = tk.Button(
                tbar,
                text=label,
                command=lambda k=key: self._switch_tab(k),
                font=("Segoe UI", 7, "bold"),
                relief="flat",
                cursor="hand2",
            )
            b.pack(side="left", expand=True, fill="both", padx=1)
            self._tip(b, tip_txt)
            self.tab_btns[key] = b

        self.view_container = tk.Frame(self.cv, bg=p["panel_bg"])
        self.cv.create_window(
            250, 338, window=self.view_container, width=432, height=392
        )
        self._init_toggle_vars()
        self._build_dashboard_tab()
        self._build_gamehub_tab()
        self._build_friends_tab()
        self._build_media_tab()
        self._build_accounts_tab()
        self._build_settings_tab()

        bbar = tk.Frame(self.cv, bg=p["panel_bg"])
        self.cv.create_window(250, 562, window=bbar, width=432, height=34)
        self.btn_pause = tk.Button(
            bbar,
            text="Pause RPC",
            command=self._pause_action,
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
        )
        self.btn_pause.pack(side="left", expand=True, fill="both", padx=(0, 2))
        self._tip(
            self.btn_pause,
            "Temporarily hides your game activity from Discord until you click Resume.",
        )

        btn_ref = tk.Button(
            bbar,
            text="↻ Refresh",
            command=lambda: threading.Thread(
                target=self.engine.rescan, daemon=True
            ).start(),
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
        )
        btn_ref.pack(side="left", expand=True, fill="both", padx=2)
        self._tip(
            btn_ref,
            "Rescans running games, installed libraries, and online friend lists immediately.",
        )

        btn_tray = tk.Button(
            bbar,
            text="Hide to Tray",
            command=self.withdraw,
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
        )
        btn_tray.pack(side="left", expand=True, fill="both", padx=2)
        self._tip(
            btn_tray,
            "Hides this window into the Windows system tray while keeping Lang!ley running.",
        )

        btn_patch = tk.Button(
            bbar,
            text="Patch Notes",
            command=self._show_patch_notes_modal,
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["status_warn"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
        )
        btn_patch.pack(side="left", expand=True, fill="both", padx=2)
        self._tip(
            btn_patch,
            f"View release history and patch notes (v1.0.0 through v{APP_VERSION}).",
        )

        btn_lic = tk.Button(
            bbar,
            text="License",
            command=self._show_license_modal,
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
        )
        btn_lic.pack(side="left", expand=True, fill="both", padx=2)
        self._tip(btn_lic, "View software license and copyright information.")

        btn_quit = tk.Button(
            bbar,
            text="Quit",
            command=self.shutdown,
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["status_err"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
        )
        btn_quit.pack(side="right", fill="y", ipadx=8, padx=(2, 0))
        self._tip(
            btn_quit,
            "Completely closes Lang!ley and clears your Discord Rich Presence.",
        )
        self._switch_tab("dashboard")

    def _init_toggle_vars(self):
        self.v_auto = tk.BooleanVar(value=Reg.has_autostart())
        self.v_mini = tk.BooleanVar(value=bool(Reg.get("StartMinimized", 1)))
        self.v_medal_prio = tk.BooleanVar(value=self.state.medal_priority_enabled)
        self.v_media_rpc = tk.BooleanVar(value=self.state.show_media_rpc)

        self.v_fortnite_en = tk.BooleanVar(value=self.state.fortnite_enabled)
        self.v_steam_en = tk.BooleanVar(value=self.state.steam_enabled)
        self.v_roblox_en = tk.BooleanVar(value=self.state.roblox_enabled)
        self.v_xbox_en = tk.BooleanVar(value=self.state.xbox_enabled)
        self.v_gacha_en = tk.BooleanVar(value=self.state.gacha_enabled)
        self.v_custom_en = tk.BooleanVar(value=self.state.custom_apps_enabled)

        self.v_riot_en = tk.BooleanVar(value=self.state.riot_enabled)
        self.v_ea_en = tk.BooleanVar(value=self.state.ea_enabled)
        self.v_ubisoft_en = tk.BooleanVar(value=self.state.ubisoft_enabled)
        self.v_gog_en = tk.BooleanVar(value=self.state.gog_enabled)
        self.v_battlenet_en = tk.BooleanVar(value=self.state.battlenet_enabled)

        self.v_mc_en = tk.BooleanVar(value=self.state.minecraft_enabled)
        self.v_mc_lunar = tk.BooleanVar(value=self.state.mc_lunar_enabled)
        self.v_mc_badlion = tk.BooleanVar(value=self.state.mc_badlion_enabled)
        self.v_mc_feather = tk.BooleanVar(value=self.state.mc_feather_enabled)
        self.v_mc_labymod = tk.BooleanVar(value=self.state.mc_labymod_enabled)
        self.v_mc_prism = tk.BooleanVar(value=self.state.mc_prism_vanilla_enabled)

        self.v_gacha_sub = {
            g["key"]: tk.BooleanVar(
                value=bool(self.state.gacha_sub_enabled.get(g["key"], True))
            )
            for g in GACHA_SUB_GAME_DEFS
        }

    def _build_dashboard_tab(self):
        p = self.PAL
        self.tab_dashboard = tk.Frame(self.view_container, bg=p["panel_bg"])

        rpc_card = tk.Frame(
            self.tab_dashboard,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=10,
            pady=6,
        )
        rpc_card.pack(side="top", fill="x", pady=(0, 4))
        top_bar = tk.Frame(rpc_card, bg=p["border_dark"])
        top_bar.pack(fill="x", pady=(0, 3))
        tk.Label(
            top_bar,
            text="LIVE DISCORD RICH PRESENCE PREVIEW",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_warn"],
            bg=p["border_dark"],
        ).pack(side="left")
        self.btn_priority = tk.Button(
            top_bar,
            text="Priority: AUTO",
            command=self._cycle_priority,
            font=("Segoe UI", 7, "bold"),
            bg=p["card_bg"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=0,
        )
        self.btn_priority.pack(side="right")
        self._tip(
            self.btn_priority,
            "Click to cycle which platform takes priority on Discord if two games are open at once (or configure in SETTINGS).",
        )

        body_row = tk.Frame(rpc_card, bg=p["border_dark"])
        body_row.pack(fill="x")
        self.lbl_rpc_thumb = tk.Label(
            body_row,
            image=self._tk_default_thumb,
            bg=p["card_bg"],
            width=56,
            height=56,
        )
        self.lbl_rpc_thumb.pack(side="left", padx=(0, 10))
        txt_col = tk.Frame(body_row, bg=p["border_dark"])
        txt_col.pack(side="left", fill="both", expand=True)
        self.lbl_rpc_headline = tk.Label(
            txt_col,
            text="Waiting for Game...",
            font=("Segoe UI", 9, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_rpc_headline.pack(fill="x")
        self.lbl_rpc_details = tk.Label(
            txt_col,
            text="Launch Any Game or Launcher",
            font=("Segoe UI", 8),
            fg=p["status_ok"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_rpc_details.pack(fill="x")
        self.lbl_rpc_state = tk.Label(
            txt_col,
            text="Idle in Background",
            font=("Segoe UI", 8),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_rpc_state.pack(fill="x")
        self.lbl_rpc_timer = tk.Label(
            txt_col,
            text="● Standby Mode",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_warn"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_rpc_timer.pack(fill="x")

        cfg_bar = tk.Frame(
            self.tab_dashboard,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=10,
            pady=4,
        )
        cfg_bar.pack(side="bottom", fill="x", pady=(4, 0))
        btn_open_set = tk.Button(
            cfg_bar,
            text="⚙ Open Settings →",
            command=lambda: self._switch_tab("settings"),
            font=("Segoe UI", 7, "bold"),
            bg=p["card_bg"],
            fg=p["status_warn"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            padx=7,
            pady=1,
        )
        btn_open_set.pack(side="right", padx=(6, 0))
        self._tip(
            btn_open_set,
            "Open the SETTINGS tab to customize game status toggles, custom .exe apps, startup behavior, and Medal.tv priority.",
        )
        self.lbl_dash_cfg_summary = tk.Label(
            cfg_bar,
            text="12/12 RPCs On  •  Priority: AUTO  •  Medal Guard: ON",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_dash_cfg_summary.pack(side="left", fill="x", expand=True)

        card = tk.Frame(
            self.tab_dashboard,
            bg=p["card_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=12,
            pady=5,
        )
        card.pack(side="top", fill="both", expand=True)
        hdr_row = tk.Frame(card, bg=p["card_bg"])
        hdr_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        tk.Label(
            hdr_row,
            text="REAL-TIME MULTI-PLATFORM TELEMETRY",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        tk.Label(
            hdr_row,
            text="Auto-detects active games",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["card_bg"],
        ).pack(side="right")

        self.lbl_state = self._row(card, "Epic Games / Fortnite", "Offline", 1)
        self.lbl_mode = self._row(card, "Playlist & Party", "Solo (1/4)", 2)
        self.lbl_skin = self._row(
            card,
            "Outfit & Season Level",
            f"{self.state.skin_name} • Lv.{self.state.season_level}",
            3,
        )
        self.lbl_steam_dash = self._row(
            card, "Steam Status", "Ready (Waiting for Steam Game)", 4
        )
        self.lbl_roblox_dash = self._row(
            card, "Roblox Status", "Ready (Waiting for Roblox)", 5
        )
        self.lbl_xbox_dash = self._row(
            card, "Xbox / Game Pass", "Ready (Waiting for Xbox Game)", 6
        )
        self.lbl_launchers_dash = self._row(
            card, "Launchers / Gacha / Custom", "Ready (All Networks Enabled)", 7
        )
        self.lbl_mc_dash = self._row(
            card, "Minecraft Clients", "Ready (5 Clients Enabled)", 8
        )
        self.lbl_medal_dash = self._row(
            card, "Discord Priority Guard", "Armed (Above All Games & Medal)", 9
        )
        self.lbl_dash_music = self._row(card, "Active Media", "No Media Playing", 10)

    def _build_gamehub_tab(self):
        p = self.PAL
        self.tab_gamehub = tk.Frame(
            self.view_container,
            bg=p["card_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=10,
            pady=8,
        )

        sub_bar = tk.Frame(self.tab_gamehub, bg=p["card_bg"])
        sub_bar.pack(fill="x", pady=(0, 6))
        self.gh_sub_btns = {}
        for skey, slabel, stip in [
            (
                "library",
                "📚 INSTALLED GAME LIBRARIES",
                "Browse & launch installed Steam, Xbox Game Pass, HoYoPlay/Gacha, PC Launchers, and Custom .exe games.",
            ),
            (
                "settings",
                "⚙ CONFIGURE RPC & CUSTOM APPS →",
                "Open the SETTINGS tab to toggle game networks or manage custom .exe applications.",
            ),
        ]:
            b = tk.Button(
                sub_bar,
                text=slabel,
                command=lambda k=skey: self._switch_gamehub_subtab(k),
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                cursor="hand2",
                pady=3,
            )
            b.pack(side="left", expand=True, fill="x", padx=2)
            self._tip(b, stip)
            self.gh_sub_btns[skey] = b

        self.gh_body = tk.Frame(self.tab_gamehub, bg=p["card_bg"])
        self.gh_body.pack(fill="both", expand=True)

        self.gh_lib_frame = tk.Frame(self.gh_body, bg=p["card_bg"])
        self.gh_cfg_frame = tk.Frame(self.gh_body, bg=p["card_bg"])

        info_box = tk.Frame(
            self.gh_lib_frame,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=9,
            pady=6,
        )
        info_box.pack(fill="x", pady=(0, 6))
        top_st = tk.Frame(info_box, bg=p["border_dark"])
        top_st.pack(fill="x")
        self.lbl_steam_profile = tk.Label(
            top_st,
            text="Steam Profile: Detecting...",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_steam_profile.pack(side="left")
        self.lbl_steam_tab_status = tk.Label(
            top_st,
            text="● STEAM STANDBY",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_warn"],
            bg=p["border_dark"],
        )
        self.lbl_steam_tab_status.pack(side="right")

        self.lbl_steam_active_detail = tk.Label(
            info_box,
            text="Active Game: None — Launch any game below or from your desktop",
            font=("Segoe UI", 8),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_steam_active_detail.pack(fill="x", pady=(2, 1))
        self.lbl_steam_gsi_status = tk.Label(
            info_box,
            text=f"Live Match Stats (CS2 / Dota 2): Auto-Applied on Startup (127.0.0.1:{GSI_PORT})",
            font=("Segoe UI", 7),
            fg=p["status_ok"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_steam_gsi_status.pack(fill="x")

        act_bar = tk.Frame(self.gh_lib_frame, bg=p["card_bg"])
        act_bar.pack(fill="x", pady=(0, 6))
        self.btn_install_gsi = tk.Button(
            act_bar,
            text="✓ Live Stats Auto",
            command=self._install_gsi_action,
            font=("Segoe UI", 8, "bold"),
            bg=p["border_dark"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=4,
        )
        self.btn_install_gsi.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._tip(
            self.btn_install_gsi,
            "CS2 & Dota 2 Live Stats GSI configs are applied automatically on startup, scan, and launch. Click to re-verify.",
        )

        btn_add_ext = tk.Button(
            act_bar,
            text="➕ Add External .exe",
            command=self._show_add_custom_modal,
            font=("Segoe UI", 8, "bold"),
            bg=p["border_dark"],
            fg=p["status_warn"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=4,
        )
        btn_add_ext.grid(row=0, column=1, sticky="ew", padx=2)
        self._tip(
            btn_add_ext,
            "Add any custom external .exe game or application to display on Discord Rich Presence.",
        )

        self.btn_stop_running_steam = tk.Button(
            act_bar,
            text="✕ Close",
            command=lambda: threading.Thread(
                target=self.engine.steam.close_game, daemon=True
            ).start(),
            font=("Segoe UI", 8, "bold"),
            bg=p["border_dark"],
            fg=p["status_err"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=4,
        )
        self.btn_stop_running_steam.grid(row=0, column=2, sticky="ew", padx=2)
        self._tip(
            self.btn_stop_running_steam,
            "Safely closes the currently running Steam game.",
        )

        btn_rescan_lib = tk.Button(
            act_bar,
            text="↻ Rescan",
            command=self._rescan_steam_library,
            font=("Segoe UI", 8, "bold"),
            bg=p["border_dark"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=4,
        )
        btn_rescan_lib.grid(row=0, column=3, sticky="ew", padx=(2, 0))
        self._tip(
            btn_rescan_lib,
            "Rescans your PC drives for installed Steam, Xbox, HoYoPlay/Gacha, Riot, EA, Ubisoft, GOG, and Battle.net games.",
        )

        act_bar.grid_columnconfigure(0, weight=3)
        act_bar.grid_columnconfigure(1, weight=4)
        act_bar.grid_columnconfigure(2, weight=2)
        act_bar.grid_columnconfigure(3, weight=2)

        flt_bar = tk.Frame(self.gh_lib_frame, bg=p["card_bg"])
        flt_bar.pack(fill="x", pady=(0, 4))
        self.lbl_steam_lib_count = tk.Label(
            flt_bar,
            text="GAMES:",
            font=("Segoe UI", 7, "bold"),
            fg=p["text_muted"],
            bg=p["card_bg"],
        )
        self.lbl_steam_lib_count.pack(side="left")

        self.gh_flt_btns = {}
        for fkey, flbl in [
            ("custom", "Custom"),
            ("gacha", "Gacha"),
            ("launchers", "Launchers"),
            ("xbox", "Xbox"),
            ("steam", "Steam"),
            ("epic", "Epic"),
            ("all", "All"),
        ]:
            fb = tk.Button(
                flt_bar,
                text=flbl,
                command=lambda k=fkey: self._set_gamehub_filter(k),
                font=("Segoe UI", 7, "bold"),
                relief="flat",
                cursor="hand2",
                padx=4,
                pady=0,
            )
            fb.pack(side="right", padx=1)
            self.gh_flt_btns[fkey] = fb

        lib_wrap = tk.Frame(self.gh_lib_frame, bg=p["border_dark"])
        lib_wrap.pack(fill="both", expand=True)
        self.steam_canvas = tk.Canvas(
            lib_wrap, bg=p["border_dark"], highlightthickness=0
        )
        sb = tk.Scrollbar(
            lib_wrap, orient="vertical", command=self.steam_canvas.yview
        )
        self.steam_inner = tk.Frame(self.steam_canvas, bg=p["border_dark"])
        self.steam_canvas.create_window(
            (0, 0), window=self.steam_inner, anchor="nw", width=388
        )
        self.steam_canvas.configure(yscrollcommand=sb.set)
        self.steam_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._set_gamehub_filter("all")
        self._switch_gamehub_subtab("library")

    def _switch_gamehub_subtab(self, skey):
        if skey == "settings":
            self._switch_tab("settings")
            return
        self.gamehub_subtab = "library"
        p = self.PAL
        for k, b in self.gh_sub_btns.items():
            b.config(
                bg=p["border_dark"] if k == "library" else p["panel_bg"],
                fg=p["status_ok"] if k == "library" else p["text_muted"],
            )
        self.gh_cfg_frame.pack_forget()
        self.gh_lib_frame.pack(fill="both", expand=True)
        self._render_steam_games()

    def _set_gamehub_filter(self, fkey):
        self.gamehub_lib_filter = fkey
        p = self.PAL
        for k, b in self.gh_flt_btns.items():
            b.config(
                bg=p["border_dark"] if k == fkey else p["panel_bg"],
                fg=p["status_ok"] if k == fkey else p["text_muted"],
            )
        self._render_steam_games()

    def _open_or_launch_dir(self, path):
        if not path or not os.path.exists(path):
            return
        try:
            os.startfile(path)
        except Exception:
            pass

    def _build_friends_tab(self):
        p = self.PAL
        self.tab_friends = tk.Frame(
            self.view_container,
            bg=p["card_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=10,
            pady=8,
        )

        plat_row1 = tk.Frame(self.tab_friends, bg=p["card_bg"])
        plat_row1.pack(fill="x", pady=(0, 2))
        plat_row2 = tk.Frame(self.tab_friends, bg=p["card_bg"])
        plat_row2.pack(fill="x", pady=(0, 5))
        self.friend_plat_btns = {}
        row1_defs = [
            ("epic", "EPIC", "Fortnite & Epic Games friends and live party squad."),
            ("steam", "STEAM", "Steam friends and what game they are currently playing."),
            ("roblox", "ROBLOX", "Roblox friends and online status."),
            (
                "xbox",
                "XBOX LIVE",
                "Xbox Live friends and party status (PC Game Pass games are in GAME HUB).",
            ),
            (
                "discord",
                "DISCORD",
                "Your connected Discord account, live RPC broadcast, and squad friends.",
            ),
        ]
        row2_defs = [
            (
                "riot",
                "RIOT GAMES",
                "VALORANT & League of Legends friends (auto-synced when Riot Client is open).",
            ),
            ("ea", "EA APP", "EA App / Origin friends and tracked EA IDs."),
            ("ubisoft", "UBISOFT", "Ubisoft Connect friends and tracked profiles."),
            ("gog", "GOG GALAXY", "GOG Galaxy friends from local database & tracked list."),
            ("battlenet", "BATTLE.NET", "Blizzard Battle.net friends and pinned BattleTags."),
        ]
        for key, title, tip_t in row1_defs:
            b = tk.Button(
                plat_row1,
                text=title,
                command=lambda k=key: self._switch_friends_platform(k),
                font=("Segoe UI", 7, "bold"),
                relief="flat",
                cursor="hand2",
                pady=2,
            )
            b.pack(side="left", expand=True, fill="x", padx=1)
            self._tip(b, tip_t)
            self.friend_plat_btns[key] = b
        for key, title, tip_t in row2_defs:
            b = tk.Button(
                plat_row2,
                text=title,
                command=lambda k=key: self._switch_friends_platform(k),
                font=("Segoe UI", 7, "bold"),
                relief="flat",
                cursor="hand2",
                pady=2,
            )
            b.pack(side="left", expand=True, fill="x", padx=1)
            self._tip(b, tip_t)
            self.friend_plat_btns[key] = b

        top = tk.Frame(self.tab_friends, bg=p["card_bg"])
        top.pack(fill="x", pady=(0, 4))
        self.lbl_friends_hdr = tk.Label(
            top,
            text="FRIENDS LIST",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_muted"],
            bg=p["card_bg"],
        )
        self.lbl_friends_hdr.pack(side="left")
        self.btn_filter_friends = tk.Button(
            top,
            text="Filter: All",
            command=self._toggle_friends_filter,
            font=("Segoe UI", 7, "bold"),
            bg=p["border_dark"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=7,
            pady=1,
        )
        self.btn_filter_friends.pack(side="right")
        self._tip(
            self.btn_filter_friends,
            "Switch between showing all friends or only friends who are currently online / in-game.",
        )

        legend = tk.Frame(self.tab_friends, bg=p["border_dark"], padx=8, pady=3)
        legend.pack(fill="x", pady=(0, 4))
        tk.Label(
            legend,
            text="★ Lang!ley Squad / In-Game",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        ).pack(side="left")
        tk.Label(
            legend,
            text="● Online / Active",
            font=("Segoe UI", 7),
            fg=p["status_warn"],
            bg=p["border_dark"],
        ).pack(side="right")

        list_wrap = tk.Frame(self.tab_friends, bg=p["border_dark"])
        list_wrap.pack(fill="both", expand=True)
        self.friends_canvas = tk.Canvas(
            list_wrap, bg=p["border_dark"], highlightthickness=0
        )
        sb = tk.Scrollbar(
            list_wrap, orient="vertical", command=self.friends_canvas.yview
        )
        self.friends_inner = tk.Frame(self.friends_canvas, bg=p["border_dark"])
        self.friends_window_id = self.friends_canvas.create_window(
            (0, 0), window=self.friends_inner, anchor="nw", width=388
        )
        self.friends_canvas.configure(yscrollcommand=sb.set)
        self.friends_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.friend_add_bar = tk.Frame(self.tab_friends, bg=p["card_bg"], pady=4)
        self.lbl_friend_add_hint = tk.Label(
            self.friend_add_bar,
            text="Add Friend:",
            font=("Segoe UI", 7, "bold"),
            fg=p["text_muted"],
            bg=p["card_bg"],
        )
        self.lbl_friend_add_hint.pack(side="left", padx=(0, 4))
        self.ent_add_friend = tk.Entry(
            self.friend_add_bar,
            font=("Segoe UI", 8),
            bg=p["border_dark"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_add_friend.pack(
            side="left", fill="x", expand=True, ipady=2, padx=(0, 4)
        )
        self.ent_add_friend.bind("<Return>", lambda _: self._add_friend_action())
        btn_add_f = tk.Button(
            self.friend_add_bar,
            text="+ Add Friend",
            command=self._add_friend_action,
            font=("Segoe UI", 7, "bold"),
            bg=p["border_dark"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=2,
        )
        btn_add_f.pack(side="right")
        self._tip(
            btn_add_f,
            "Pin a friend's Gamertag, Riot ID (Name#TAG), or username to your friends list for this platform.",
        )

        self._switch_friends_platform("epic")

    def _add_friend_action(self):
        val = self.ent_add_friend.get().strip()
        if not val:
            return
        plat = self.friends_platform
        if plat == "epic":
            self.engine.epic.add_tracked_friend(val)
        elif plat == "xbox":
            self.engine.xbox.add_tracked_friend(val)
        elif plat == "discord":
            self.engine.rpc.add_tracked_friend(val, self.state)
        elif plat == "riot":
            self.engine.riot.add_tracked_friend(val)
        elif plat == "ea":
            self.engine.ea.add_tracked_friend(val)
        elif plat == "ubisoft":
            self.engine.ubisoft.add_tracked_friend(val)
        elif plat == "gog":
            self.engine.gog.add_tracked_friend(val)
        elif plat == "battlenet":
            self.engine.battlenet.add_tracked_friend(val)
        self.ent_add_friend.delete(0, "end")
        self._render_friends_list()

    def _remove_friend_action(self, plat, name):
        if plat == "epic":
            self.engine.epic.remove_tracked_friend(name)
        elif plat == "xbox":
            self.engine.xbox.remove_tracked_friend(name)
        elif plat == "discord":
            self.engine.rpc.remove_tracked_friend(name, self.state)
        elif plat == "riot":
            self.engine.riot.remove_tracked_friend(name)
        elif plat == "ea":
            self.engine.ea.remove_tracked_friend(name)
        elif plat == "ubisoft":
            self.engine.ubisoft.remove_tracked_friend(name)
        elif plat == "gog":
            self.engine.gog.remove_tracked_friend(name)
        elif plat == "battlenet":
            self.engine.battlenet.remove_tracked_friend(name)
        self._render_friends_list()

    def _switch_friends_platform(self, plat_key):
        self.friends_platform = plat_key
        p = self.PAL
        for k, b in self.friend_plat_btns.items():
            b.config(
                bg=p["border_dark"] if k == plat_key else p["panel_bg"],
                fg=p["status_ok"] if k == plat_key else p["text_muted"],
            )

        hints = {
            "epic": "Add Epic Display Name:",
            "xbox": "Add Xbox Gamertag:",
            "discord": "Add Discord Username:",
            "riot": "Add Riot ID (Name#TAG):",
            "ea": "Add EA ID:",
            "ubisoft": "Add Ubisoft Username:",
            "gog": "Add GOG Username:",
            "battlenet": "Add BattleTag (Name#1234):",
        }
        if plat_key in hints:
            self.lbl_friend_add_hint.config(text=hints[plat_key])
            self.friend_add_bar.pack(fill="x", pady=(4, 0))
        else:
            self.friend_add_bar.pack_forget()
        self._render_friends_list()

    def _on_mousewheel(self, event):
        if self.patch_notes_modal and self.patch_notes_modal.winfo_exists():
            self.patch_notes_modal.on_mousewheel(event)
            return
        units = int(-1 * (event.delta / 120))
        if self.current_tab == "friends" and hasattr(self, "friends_canvas"):
            self.friends_canvas.yview_scroll(units, "units")
        elif (
            self.current_tab == "gamehub"
            and self.gamehub_subtab == "library"
            and hasattr(self, "steam_canvas")
        ):
            self.steam_canvas.yview_scroll(units, "units")
        elif self.current_tab == "settings" and hasattr(self, "settings_canvas"):
            self.settings_canvas.yview_scroll(units, "units")
        elif self.current_tab == "accounts" and hasattr(self, "accounts_canvas"):
            self.accounts_canvas.yview_scroll(units, "units")

    def _build_media_tab(self):
        p = self.PAL
        self.tab_media = tk.Frame(
            self.view_container,
            bg=p["card_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=14,
            pady=10,
        )
        top = tk.Frame(self.tab_media, bg=p["card_bg"])
        top.pack(fill="x", pady=(0, 6))
        tk.Label(
            top,
            text="WINDOWS MEDIA & SPOTIFY CONTROLLER",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        self.lbl_media_badge = tk.Label(
            top,
            text="● IDLE",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_muted"],
            bg=p["card_bg"],
        )
        self.lbl_media_badge.pack(side="right")

        tk.Label(
            self.tab_media,
            text="Automatically detects music playing on Spotify, YouTube Music, Apple Music, or your browser.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(fill="x", pady=(0, 6))

        now_box = tk.Frame(
            self.tab_media,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        now_box.pack(fill="x", pady=(0, 10))
        self.lbl_media_app = tk.Label(
            now_box,
            text="SOURCE: NO MEDIA DETECTED",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_media_app.pack(fill="x")
        self.lbl_media_title = tk.Label(
            now_box,
            text="Play a song on Spotify, YT Music or Amazon Music",
            font=("Segoe UI", 10, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_media_title.pack(fill="x", pady=(4, 2))
        self.lbl_media_artist = tk.Label(
            now_box,
            text="—",
            font=("Segoe UI", 9),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
        )
        self.lbl_media_artist.pack(fill="x")

        prog_wrap = tk.Frame(now_box, bg=p["border_dark"])
        prog_wrap.pack(fill="x", pady=(8, 0))
        self.lbl_time_cur = tk.Label(
            prog_wrap,
            text="00:00",
            font=("Segoe UI", 8),
            fg=p["text_muted"],
            bg=p["border_dark"],
        )
        self.lbl_time_cur.pack(side="left")
        self.prog_canvas = tk.Canvas(
            prog_wrap, height=8, bg=p["card_bg"], highlightthickness=0
        )
        self.prog_canvas.pack(side="left", fill="x", expand=True, padx=8)
        self.lbl_time_end = tk.Label(
            prog_wrap,
            text="Live",
            font=("Segoe UI", 8),
            fg=p["text_muted"],
            bg=p["border_dark"],
        )
        self.lbl_time_end.pack(side="right")

        ctrl = tk.Frame(self.tab_media, bg=p["card_bg"])
        ctrl.pack(fill="x", pady=(2, 10))
        for txt, cmd, tip_m in [
            (
                "⏮ Previous",
                self.engine.media.prev_track,
                "Skip back to the previous track.",
            ),
            (
                "⏯ Play / Pause",
                self.engine.media.play_pause,
                "Play or pause your current music player.",
            ),
            (
                "⏭ Next Track",
                self.engine.media.next_track,
                "Skip ahead to the next track.",
            ),
        ]:
            b = tk.Button(
                ctrl,
                text=txt,
                command=cmd,
                font=("Segoe UI", 8, "bold"),
                bg=p["border_dark"],
                fg=p["text_primary"],
                activebackground=p["outer_bg"],
                activeforeground=p["border_dark"],
                relief="flat",
                cursor="hand2",
                pady=6,
            )
            b.pack(side="left", expand=True, fill="x", padx=3)
            self._tip(b, tip_m)

        opt = tk.Frame(self.tab_media, bg=p["panel_bg"], padx=10, pady=8)
        opt.pack(fill="x")
        cb_med = tk.Checkbutton(
            opt,
            text="Show currently playing song inside my Discord game status",
            variable=self.v_media_rpc,
            command=self._toggle_media_rpc,
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["panel_bg"],
            selectcolor=p["border_dark"],
            activebackground=p["panel_bg"],
            activeforeground=p["text_primary"],
            cursor="hand2",
        )
        cb_med.pack(anchor="w")
        self._tip(
            cb_med,
            "Adds a '🎵 Artist - Song' note to your Discord Rich Presence while you play any game.",
        )
        tk.Label(
            opt,
            text="Friends on Discord will see both the game you're playing and the song you're listening to.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["panel_bg"],
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

    def _build_accounts_tab(self):
        p = self.PAL
        self.tab_accounts = tk.Frame(
            self.view_container,
            bg=p["card_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=10,
            pady=8,
        )
        hdr = tk.Frame(self.tab_accounts, bg=p["card_bg"])
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(
            hdr,
            text="ACCOUNT LINKING & BROWSER CONNECTIONS",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(side="left")
        tk.Label(
            hdr,
            text="10 Launchers + 11 Gacha Games",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["card_bg"],
        ).pack(side="right")

        acc_scroll_wrap = tk.Frame(self.tab_accounts, bg=p["border_dark"])
        acc_scroll_wrap.pack(fill="both", expand=True)
        self.accounts_canvas = tk.Canvas(
            acc_scroll_wrap, bg=p["card_bg"], highlightthickness=0
        )
        acc_sb = tk.Scrollbar(
            acc_scroll_wrap, orient="vertical", command=self.accounts_canvas.yview
        )
        self.accounts_inner = tk.Frame(
            self.accounts_canvas, bg=p["card_bg"], padx=2, pady=2
        )
        self.accounts_canvas.create_window(
            (0, 0), window=self.accounts_inner, anchor="nw", width=390
        )
        self.accounts_canvas.configure(yscrollcommand=acc_sb.set)
        self.accounts_canvas.pack(side="left", fill="both", expand=True)
        acc_sb.pack(side="right", fill="y")

        self.lbl_acc_status = {}
        self.btn_acc_browser = {}
        self.ent_acc_input = {}

        def _make_section_banner(title_txt, subtitle_txt):
            sec_f = tk.Frame(self.accounts_inner, bg=p["card_bg"])
            sec_f.pack(fill="x", pady=(2, 3))
            tk.Label(
                sec_f,
                text=title_txt,
                font=("Segoe UI", 8, "bold"),
                fg=p["status_warn"],
                bg=p["card_bg"],
                anchor="w",
            ).pack(side="left")
            tk.Label(
                sec_f,
                text=subtitle_txt,
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=p["card_bg"],
                anchor="e",
            ).pack(side="right")

        def _make_card_shell(plat_key, title_txt, desc_txt, browser_btn_txt="🌐 Login via Browser"):
            box = tk.Frame(
                self.accounts_inner,
                bg=p["border_dark"],
                highlightbackground=p["border_light"],
                highlightthickness=1,
                padx=10,
                pady=6,
            )
            box.pack(fill="x", pady=(0, 6))
            row1 = tk.Frame(box, bg=p["border_dark"])
            row1.pack(fill="x")
            tk.Label(
                row1,
                text=title_txt,
                font=("Segoe UI", 8, "bold"),
                fg=p["status_warn"],
                bg=p["border_dark"],
            ).pack(side="left")
            lbl_st = tk.Label(
                row1,
                text="Not Linked",
                font=("Segoe UI", 7, "bold"),
                fg=p["text_muted"],
                bg=p["border_dark"],
            )
            lbl_st.pack(side="right")
            self.lbl_acc_status[plat_key] = lbl_st

            tk.Label(
                box,
                text=desc_txt,
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=p["border_dark"],
                anchor="w",
                justify="left",
                wraplength=365,
            ).pack(fill="x", pady=(1, 3))

            btn_row = tk.Frame(box, bg=p["border_dark"])
            btn_row.pack(fill="x", pady=(1, 2))
            btn_br = tk.Button(
                btn_row,
                text=browser_btn_txt,
                command=lambda k=plat_key: self._browser_login_action(k),
                font=("Segoe UI", 8, "bold"),
                bg=p["card_bg"],
                fg=p["status_ok"],
                activebackground=p["outer_bg"],
                relief="flat",
                cursor="hand2",
                padx=8,
                pady=2,
            )
            btn_br.pack(side="left", fill="x", expand=True, padx=(0, 4))
            self.btn_acc_browser[plat_key] = btn_br
            self._tip(
                btn_br,
                "Opens your browser to sign in and automatically links your profile, level & friends.",
            )

            btn_auto = tk.Button(
                btn_row,
                text="↻ Auto-Detect",
                command=lambda k=plat_key: self._auto_detect_account_action(k),
                font=("Segoe UI", 7, "bold"),
                bg=p["card_bg"],
                fg=p["text_primary"],
                activebackground=p["outer_bg"],
                relief="flat",
                cursor="hand2",
                padx=7,
                pady=2,
            )
            btn_auto.pack(side="left", padx=(0, 4))
            self._tip(
                btn_auto,
                "Scans local launcher configs, logs & registry on this PC to detect your signed-in account.",
            )

            btn_un = tk.Button(
                btn_row,
                text="Unlink",
                command=lambda k=plat_key: self._unlink_account_action(k),
                font=("Segoe UI", 7, "bold"),
                bg=p["card_bg"],
                fg=p["status_err"],
                activebackground=p["outer_bg"],
                relief="flat",
                cursor="hand2",
                padx=7,
                pady=2,
            )
            btn_un.pack(side="right")
            self._tip(btn_un, "Unlink and clear saved account credentials for this platform.")
            return box

        def _add_fallback_input(box, plat_key, label_txt, initial_val=""):
            inp_row = tk.Frame(box, bg=p["border_dark"])
            inp_row.pack(fill="x", pady=(2, 0))
            tk.Label(
                inp_row,
                text=label_txt,
                font=("Segoe UI", 7, "bold"),
                fg=p["text_muted"],
                bg=p["border_dark"],
            ).pack(side="left", padx=(0, 4))
            ent = tk.Entry(
                inp_row,
                font=("Segoe UI", 8),
                bg=p["card_bg"],
                fg=p["text_primary"],
                insertbackground=p["text_primary"],
                relief="flat",
            )
            ent.pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 4))
            if initial_val:
                ent.insert(0, str(initial_val))
            self.ent_acc_input[plat_key] = ent
            btn_sv = tk.Button(
                inp_row,
                text="Save / Link",
                command=lambda k=plat_key: self._manual_link_account_action(k),
                font=("Segoe UI", 7, "bold"),
                bg=p["card_bg"],
                fg=p["status_ok"],
                activebackground=p["outer_bg"],
                relief="flat",
                cursor="hand2",
                padx=8,
                pady=1,
            )
            btn_sv.pack(side="right")
            return ent

        # =====================================================================
        # CATEGORY 1: LAUNCHER & PLATFORM ACCOUNTS (ALL 10 SUPPORTED LAUNCHERS)
        # =====================================================================
        _make_section_banner(
            "LAUNCHER & PLATFORM ACCOUNTS",
            "Browser Login + Local Auto-Detect",
        )

        # 1. EPIC GAMES
        epic_box = _make_card_shell(
            "epic",
            "1. EPIC GAMES",
            "Official Epic OAuth Browser Login & Local Launcher Sync — unlocks all Epic Games Store titles, live Fortnite telemetry & Epic friends.",
            "🌐 Login via Browser (Epic OAuth)",
        )
        self.lbl_acc_epic_status = self.lbl_acc_status["epic"]
        self.btn_acc_epic = self.btn_acc_browser["epic"]
        self.ent_epic_user = _add_fallback_input(
            epic_box, "epic", "Epic Name:", self.state.epic_name
        )

        # 2. STEAM
        steam_box = _make_card_shell(
            "steam",
            "2. STEAM",
            "Official Steam OpenID 2.0 browser sign-in — automatically fetches your SteamID64, persona & friends.",
            "🌐 Login via Browser (Steam OpenID)",
        )
        self.lbl_acc_steam_status = self.lbl_acc_status["steam"]
        self.ent_steam_id = _add_fallback_input(
            steam_box, "steam", "SteamID / URL:", self.state.steam_id64
        )

        # 3. RIOT GAMES
        riot_box = _make_card_shell(
            "riot",
            "3. RIOT GAMES",
            "Sign in via Browser or auto-detect your Riot ID (Name#TAG) from Riot Client / League.",
            "🌐 Login via Browser",
        )
        _add_fallback_input(riot_box, "riot", "Riot ID:", self.state.riot_id)

        # 4. BLIZZARD BATTLE.NET
        bnet_box = _make_card_shell(
            "battlenet",
            "4. BLIZZARD BATTLE.NET",
            "Sign in via Browser or auto-detect your BattleTag (Name#1234) & Battle.net friends.",
            "🌐 Login via Browser",
        )
        _add_fallback_input(
            bnet_box, "battlenet", "BattleTag:", self.state.battlenet_battletag
        )

        # 5. EA APP
        ea_box = _make_card_shell(
            "ea",
            "5. EA APP",
            "Sign in via Browser or auto-detect your EA ID from local EA App / Origin session data.",
            "🌐 Login via Browser",
        )
        _add_fallback_input(ea_box, "ea", "EA ID:", self.state.ea_account_name)

        # 6. UBISOFT CONNECT
        ubi_box = _make_card_shell(
            "ubisoft",
            "6. UBISOFT CONNECT",
            "Sign in via Browser or auto-detect your Ubisoft Connect username from local session files.",
            "🌐 Login via Browser",
        )
        _add_fallback_input(
            ubi_box, "ubisoft", "Ubisoft ID:", self.state.ubisoft_username
        )

        # 7. GOG GALAXY
        gog_box = _make_card_shell(
            "gog",
            "7. GOG GALAXY",
            "Sign in via Browser or auto-detect your GOG Galaxy username from galaxy-2.0.db / Registry.",
            "🌐 Login via Browser",
        )
        _add_fallback_input(gog_box, "gog", "GOG User:", self.state.gog_username)

        # 8. XBOX LIVE / PC GAME PASS
        xbox_box = _make_card_shell(
            "xbox",
            "8. XBOX LIVE / PC GAME PASS",
            "Browser login or local Xbox Identity scan — displays your Gamertag on PC Game Pass titles.",
            "🌐 Login via Browser",
        )
        self.lbl_acc_xbox_status = self.lbl_acc_status["xbox"]
        self.ent_xbox_user = _add_fallback_input(
            xbox_box, "xbox", "Gamertag:", self.state.xbox_gamertag
        )

        # 9. ROBLOX
        roblox_box = _make_card_shell(
            "roblox",
            "9. ROBLOX",
            "Browser login or local Roblox app scan — links your @username, UserID & live friend activity.",
            "🌐 Login via Browser",
        )
        self.lbl_acc_roblox_status = self.lbl_acc_status["roblox"]
        self.ent_roblox_user = _add_fallback_input(
            roblox_box, "roblox", "User / URL:", self.state.roblox_user_name
        )

        # 10. MINECRAFT
        mc_acc_box = _make_card_shell(
            "minecraft",
            "10. MINECRAFT",
            "Browser login or local Lunar / Badlion / Feather / Prism / Official Launcher profile scan.",
            "🌐 Login via Browser",
        )
        self.lbl_acc_mc_status = self.lbl_acc_status["minecraft"]
        self.ent_mc_user = _add_fallback_input(
            mc_acc_box, "minecraft", "MC IGN:", self.state.minecraft_username
        )

        # =====================================================================
        # CATEGORY 2: GACHA GAMES ACCOUNTS (HYBRID BROWSER, AUTO-SYNC & UID FALLBACK)
        # =====================================================================
        tk.Frame(self.accounts_inner, bg=p["border_light"], height=1).pack(
            fill="x", pady=(4, 4)
        )
        _make_section_banner(
            "GACHA GAMES ACCOUNTS (AUTO-SYNC)",
            "Hybrid Browser • Local Logs • UID Fallback",
        )

        gacha_intro = tk.Frame(
            self.accounts_inner,
            bg=p["card_alt"],
            highlightbackground=p["border_dark"],
            highlightthickness=1,
            padx=8,
            pady=4,
        )
        gacha_intro.pack(fill="x", pady=(0, 6))
        tk.Label(
            gacha_intro,
            text="Seamless Hybrid System: Click 🌐 Login to open the official portal, click ↻ Auto-Sync Logs & Registry for instant local detection, or paste your UID / Profile below to fetch your Level (AR/TL/IK/UL), Server Region & Character via Enka.Network / Mihomo.",
            font=("Segoe UI", 7),
            fg=p["text_primary"],
            bg=p["card_alt"],
            anchor="w",
            justify="left",
            wraplength=365,
        ).pack(fill="x")

        for g_idx, gdef in enumerate(GACHA_SUB_GAME_DEFS, start=1):
            gkey = gdef["key"]
            plat_key = f"gacha_{gkey}"
            gname = gdef["name"]
            gpub = gdef["publisher"]
            glvl_pfx = gdef["level_prefix"]
            gprof = self.state.gacha_profiles.get(gkey) or {}
            g_init_val = gprof.get("uid") or gprof.get("account_name") or ""

            gbox = tk.Frame(
                self.accounts_inner,
                bg=p["border_dark"],
                highlightbackground=p["border_light"],
                highlightthickness=1,
                padx=9,
                pady=5,
            )
            gbox.pack(fill="x", pady=(0, 5))

            top_r = tk.Frame(gbox, bg=p["border_dark"])
            top_r.pack(fill="x")
            tk.Label(
                top_r,
                text=f"{g_idx}. {gname}",
                font=("Segoe UI", 8, "bold"),
                fg=p["status_warn"],
                bg=p["border_dark"],
            ).pack(side="left")

            lbl_gst = tk.Label(
                top_r,
                text="Not Linked",
                font=("Segoe UI", 7, "bold"),
                fg=p["text_muted"],
                bg=p["border_dark"],
            )
            lbl_gst.pack(side="right")
            self.lbl_acc_status[plat_key] = lbl_gst

            tk.Label(
                gbox,
                text=f"{gpub} • Hybrid Portal Login, Local Log/Registry Sync & UID Lookup ({glvl_pfx})",
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=p["border_dark"],
                anchor="w",
            ).pack(fill="x", pady=(1, 3))

            bot_r = tk.Frame(gbox, bg=p["border_dark"])
            bot_r.pack(fill="x", pady=(1, 2))

            btn_gbr = tk.Button(
                bot_r,
                text="🌐 Login",
                command=lambda k=plat_key: self._browser_login_action(k),
                font=("Segoe UI", 8, "bold"),
                bg=p["card_bg"],
                fg=p["status_ok"],
                activebackground=p["outer_bg"],
                relief="flat",
                cursor="hand2",
                padx=8,
                pady=2,
            )
            btn_gbr.pack(side="left", fill="x", expand=True, padx=(0, 4))
            self.btn_acc_browser[plat_key] = btn_gbr
            self._tip(
                btn_gbr,
                f"Open official {gpub} portal in your browser and auto-sync {gname} UID, {glvl_pfx}, Region & Character.",
            )

            btn_gauto = tk.Button(
                bot_r,
                text="↻ Auto-Sync Logs & Registry",
                command=lambda k=plat_key: self._auto_detect_account_action(k),
                font=("Segoe UI", 7, "bold"),
                bg=p["card_bg"],
                fg=p["text_primary"],
                activebackground=p["outer_bg"],
                relief="flat",
                cursor="hand2",
                padx=7,
                pady=2,
            )
            btn_gauto.pack(side="left", padx=(0, 4))
            self._tip(
                btn_gauto,
                f"Instantly scan local {gname} logs, Windows Registry & Enka/Mihomo showcase APIs.",
            )

            btn_gun = tk.Button(
                bot_r,
                text="Unlink",
                command=lambda k=plat_key: self._unlink_account_action(k),
                font=("Segoe UI", 7, "bold"),
                bg=p["card_bg"],
                fg=p["status_err"],
                activebackground=p["outer_bg"],
                relief="flat",
                cursor="hand2",
                padx=7,
                pady=2,
            )
            btn_gun.pack(side="right")
            self._tip(
                btn_gun,
                f"Unlink and clear saved telemetry for {gname}.",
            )

            _add_fallback_input(
                gbox,
                plat_key,
                "UID / Profile:",
                g_init_val,
            )

        self.lbl_acc_gacha_status = self.lbl_acc_status.get("gacha_genshin")

        self.accounts_inner.update_idletasks()
        self.accounts_canvas.config(scrollregion=self.accounts_canvas.bbox("all"))

    def _build_settings_tab(self):
        p = self.PAL
        self.tab_settings = tk.Frame(
            self.view_container,
            bg=p["card_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=10,
            pady=8,
        )

        hdr = tk.Frame(self.tab_settings, bg=p["card_bg"])
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(
            hdr,
            text="SETTINGS & RPC CONFIGURATION",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(side="left")

        btn_dis_all = tk.Button(
            hdr,
            text="○ All Off",
            command=lambda: self._set_all_rpcs(False),
            font=("Segoe UI", 7, "bold"),
            bg=p["border_dark"],
            fg=p["text_muted"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=1,
        )
        btn_dis_all.pack(side="right", padx=(2, 0))
        self._tip(btn_dis_all, "Turns off all 12 game Rich Presence networks at once.")

        btn_en_all = tk.Button(
            hdr,
            text="✓ Enable All RPCs",
            command=lambda: self._set_all_rpcs(True),
            font=("Segoe UI", 7, "bold"),
            bg=p["border_dark"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=1,
        )
        btn_en_all.pack(side="right", padx=2)
        self._tip(
            btn_en_all,
            "Turns on all 12 game Rich Presence networks and all 5 Minecraft clients.",
        )

        scroll_wrap = tk.Frame(self.tab_settings, bg=p["border_dark"])
        scroll_wrap.pack(fill="both", expand=True)
        self.settings_canvas = tk.Canvas(
            scroll_wrap, bg=p["card_bg"], highlightthickness=0
        )
        sb = tk.Scrollbar(
            scroll_wrap, orient="vertical", command=self.settings_canvas.yview
        )
        self.settings_inner = tk.Frame(
            self.settings_canvas, bg=p["card_bg"], padx=2, pady=2
        )
        self.settings_canvas.create_window(
            (0, 0), window=self.settings_inner, anchor="nw", width=390
        )
        self.settings_canvas.configure(yscrollcommand=sb.set)
        self.settings_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 1. APP BEHAVIOR
        sec1_hdr = tk.Frame(self.settings_inner, bg=p["card_bg"])
        sec1_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            sec1_hdr,
            text="1. APP BEHAVIOR & STARTUP PREFERENCES",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        tk.Label(
            sec1_hdr,
            text="Synced to settings.json",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["card_bg"],
        ).pack(side="right")

        app_card = tk.Frame(
            self.settings_inner,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=9,
            pady=6,
        )
        app_card.pack(fill="x", pady=(0, 8))

        r_auto = tk.Frame(app_card, bg=p["border_dark"])
        r_auto.pack(fill="x")
        cb_auto = tk.Checkbutton(
            r_auto,
            text="Autostart Lang!ley with Windows",
            variable=self.v_auto,
            command=self._save_cfg,
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
            selectcolor=p["card_bg"],
            activebackground=p["border_dark"],
            activeforeground=p["status_ok"],
            cursor="hand2",
        )
        cb_auto.pack(side="left")
        self._tip(
            cb_auto, "Starts Lang!ley automatically whenever you sign in to Windows."
        )
        self.lbl_set_auto_status = tk.Label(
            r_auto,
            text="● On",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        )
        self.lbl_set_auto_status.pack(side="right")
        tk.Label(
            app_card,
            text="Launches Lang!ley automatically when you turn on your PC so your Discord game status is always ready.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
            justify="left",
            wraplength=362,
        ).pack(fill="x", pady=(0, 5))

        r_mini = tk.Frame(app_card, bg=p["border_dark"])
        r_mini.pack(fill="x")
        cb_mini = tk.Checkbutton(
            r_mini,
            text="Start Minimized to System Tray",
            variable=self.v_mini,
            command=self._save_cfg,
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
            selectcolor=p["card_bg"],
            activebackground=p["border_dark"],
            activeforeground=p["status_ok"],
            cursor="hand2",
        )
        cb_mini.pack(side="left")
        self._tip(
            cb_mini,
            "When Windows starts Lang!ley, keep it tucked quietly inside the system tray near your clock.",
        )
        self.lbl_set_mini_status = tk.Label(
            r_mini,
            text="● On",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        )
        self.lbl_set_mini_status.pack(side="right")
        tk.Label(
            app_card,
            text="Starts quietly in the Windows taskbar corner without popping up a window on startup.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
            justify="left",
            wraplength=362,
        ).pack(fill="x", pady=(0, 5))

        r_med = tk.Frame(app_card, bg=p["border_dark"])
        r_med.pack(fill="x")
        cb_med_set = tk.Checkbutton(
            r_med,
            text="Show Currently Playing Music in Discord Status",
            variable=self.v_media_rpc,
            command=self._toggle_media_rpc,
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
            selectcolor=p["card_bg"],
            activebackground=p["border_dark"],
            activeforeground=p["status_ok"],
            cursor="hand2",
        )
        cb_med_set.pack(side="left")
        self._tip(
            cb_med_set,
            "Adds your active Spotify, YouTube Music, or browser song to your game status on Discord.",
        )
        self.lbl_set_media_status = tk.Label(
            r_med,
            text="● On",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        )
        self.lbl_set_media_status.pack(side="right")
        tk.Label(
            app_card,
            text="Friends on Discord will see both the game you are playing and the song you are listening to.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
            justify="left",
            wraplength=362,
        ).pack(fill="x")

        # 2. PLATFORM PRIORITY & UNIVERSAL DISCORD GUARD
        sec2_hdr = tk.Frame(self.settings_inner, bg=p["card_bg"])
        sec2_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            sec2_hdr,
            text="2. PLATFORM PRIORITY & UNIVERSAL DISCORD GUARD",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        tk.Label(
            sec2_hdr,
            text="#1 Priority over all apps",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["card_bg"],
        ).pack(side="right")

        prio_card = tk.Frame(
            self.settings_inner,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=9,
            pady=6,
        )
        prio_card.pack(fill="x", pady=(0, 8))

        pr_top = tk.Frame(prio_card, bg=p["border_dark"])
        pr_top.pack(fill="x", pady=(0, 3))
        tk.Label(
            pr_top,
            text="Platform Priority Mode:",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
        ).pack(side="left")
        self.lbl_set_prio_mode = tk.Label(
            pr_top,
            text="● AUTO (Smart Detection)",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        )
        self.lbl_set_prio_mode.pack(side="right")

        pr_row1 = tk.Frame(prio_card, bg=p["border_dark"])
        pr_row1.pack(fill="x", pady=(0, 2))
        pr_row2 = tk.Frame(prio_card, bg=p["border_dark"])
        pr_row2.pack(fill="x", pady=(0, 3))
        self.prio_mode_btns = {}
        prio_r1_defs = [
            ("auto", "AUTO", "Automatically display whichever enabled game is active."),
            ("fortnite", "FN", "Prefer Fortnite when multiple games are open."),
            ("minecraft", "MC", "Prefer Minecraft when multiple games are open."),
            ("gacha", "GACHA", "Prefer HoYoPlay & Gacha games when multiple games are open."),
            ("riot", "RIOT", "Prefer Riot Games (VALORANT / LoL) when multiple games are open."),
            ("battlenet", "B.NET", "Prefer Blizzard Battle.net games when multiple games are open."),
            ("steam", "STEAM", "Prefer Steam games when multiple games are open."),
        ]
        prio_r2_defs = [
            ("ea", "EA", "Prefer EA App games when multiple games are open."),
            ("ubisoft", "UBI", "Prefer Ubisoft Connect games when multiple games are open."),
            ("gog", "GOG", "Prefer GOG Galaxy games when multiple games are open."),
            ("roblox", "RBLX", "Prefer Roblox when multiple games are open."),
            ("xbox", "XBOX", "Prefer Xbox / PC Game Pass when multiple games are open."),
            ("custom_apps", "CUSTOM", "Prefer custom external .exe apps when multiple games are open."),
        ]
        for pkey, plbl, ptip in prio_r1_defs:
            pb = tk.Button(
                pr_row1,
                text=plbl,
                command=lambda k=pkey: self._set_priority_mode(k),
                font=("Segoe UI", 7, "bold"),
                relief="flat",
                cursor="hand2",
                pady=1,
            )
            pb.pack(side="left", expand=True, fill="x", padx=1)
            self._tip(pb, ptip)
            self.prio_mode_btns[pkey] = pb
        for pkey, plbl, ptip in prio_r2_defs:
            pb = tk.Button(
                pr_row2,
                text=plbl,
                command=lambda k=pkey: self._set_priority_mode(k),
                font=("Segoe UI", 7, "bold"),
                relief="flat",
                cursor="hand2",
                pady=1,
            )
            pb.pack(side="left", expand=True, fill="x", padx=1)
            self._tip(pb, ptip)
            self.prio_mode_btns[pkey] = pb

        tk.Label(
            prio_card,
            text="Chooses which game appears on Discord if two games are open at once. Leave on AUTO for smart detection.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
            justify="left",
            wraplength=362,
        ).pack(fill="x", pady=(0, 6))

        md_top = tk.Frame(prio_card, bg=p["border_dark"])
        md_top.pack(fill="x")
        cb_md_strict = tk.Checkbutton(
            md_top,
            text="Universal Priority Guard (Above All Games & Medal)",
            variable=self.v_medal_prio,
            command=self._toggle_medal_priority,
            font=("Segoe UI", 8, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
            selectcolor=p["card_bg"],
            activebackground=p["border_dark"],
            cursor="hand2",
        )
        cb_md_strict.pack(side="left")
        self._tip(
            cb_md_strict,
            "Forces Discord to prioritize Lang!ley over everything: native game statuses, built-in client RPCs, Medal.tv, Overwolf, GeForce Overlay, and Xbox Game Bar.",
        )

        btn_reassert = tk.Button(
            md_top,
            text="⚡ Re-Assert",
            command=lambda: threading.Thread(
                target=self.engine.force_reassert_rpc, daemon=True
            ).start(),
            font=("Segoe UI", 7, "bold"),
            bg=p["card_bg"],
            fg=p["status_warn"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=1,
        )
        btn_reassert.pack(side="right")
        self._tip(
            btn_reassert, "Immediately forces Lang!ley to the #1 activity slot on Discord."
        )

        self.lbl_medal_detail = tk.Label(
            prio_card,
            text="Locks Lang!ley at #1 priority on Discord above native game statuses, Medal.tv, Overwolf, GeForce & Game Bar.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
            justify="left",
            wraplength=362,
        )
        self.lbl_medal_detail.pack(fill="x", pady=(1, 0))

        # 3. RICH PRESENCE NETWORK TOGGLES (compact titles & compact status badges so nothing clips)
        sec3_hdr = tk.Frame(self.settings_inner, bg=p["card_bg"])
        sec3_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            sec3_hdr,
            text="3. RICH PRESENCE NETWORK TOGGLES",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        self.lbl_set_rpc_count = tk.Label(
            sec3_hdr,
            text="12 / 12 Enabled",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["card_bg"],
        )
        self.lbl_set_rpc_count.pack(side="right")

        rpc_card = tk.Frame(
            self.settings_inner,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=9,
            pady=6,
        )
        rpc_card.pack(fill="x", pady=(0, 8))

        self.lbl_set_plat_status = {}
        self.lbl_launcher_rows = {}
        rpc_platforms = [
            (
                "fortnite",
                "Epic Games & Fortnite (All Store Titles + Live BR)",
                self.v_fortnite_en,
                self._toggle_fortnite_rpc,
                "Detects all Epic Games Store games (Rocket League, Fall Guys, Alan Wake 2, GTA V, etc.) plus live Fortnite match, mode, outfit icon, Season Level & party size.",
            ),
            (
                "minecraft",
                "Minecraft (All Clients & Editions)",
                self.v_mc_en,
                self._toggle_mc_rpc,
                "Shows your active Minecraft client, game version, and Singleplayer/Multiplayer status when the game window is open.",
            ),
            (
                "gacha",
                "HoYoPlay & Gacha (Genshin • HSR • ZZZ • WuWa)",
                self.v_gacha_en,
                self._toggle_gacha_rpc,
                "Detects Genshin Impact, Honkai: Star Rail, Zenless Zone Zero, Honkai Impact 3rd, Wuthering Waves, NIKKE, Reverse: 1999, PGR, Solo Leveling, Infinity Nikki & Endfield.",
            ),
            (
                "riot",
                "Riot Games (VALORANT & League of Legends)",
                self.v_riot_en,
                self._toggle_launcher_rpc,
                "Shows live VALORANT and League of Legends match, queue, or lobby activity (ignores idle Riot Client tray).",
            ),
            (
                "ea",
                "EA App (Apex • EA FC • Battlefield • Sims)",
                self.v_ea_en,
                self._toggle_launcher_rpc,
                "Shows when you are playing Apex Legends, EA Sports FC, Battlefield, The Sims 4, or other EA App titles.",
            ),
            (
                "ubisoft",
                "Ubisoft Connect (R6 Siege • XDefiant • AC)",
                self.v_ubisoft_en,
                self._toggle_launcher_rpc,
                "Shows when you are playing Rainbow Six Siege, XDefiant, Assassin's Creed, or other Ubisoft Connect games.",
            ),
            (
                "gog",
                "GOG Galaxy (Cyberpunk • Witcher • DRM-Free)",
                self.v_gog_en,
                self._toggle_launcher_rpc,
                "Detects and displays any DRM-free game installed through your GOG Galaxy library.",
            ),
            (
                "battlenet",
                "Battle.net (CoD • WoW • Overwatch 2 • Diablo)",
                self.v_battlenet_en,
                self._toggle_launcher_rpc,
                "Shows when you are playing Call of Duty, World of Warcraft, Overwatch 2, Diablo IV, Hearthstone, or StarCraft II.",
            ),
            (
                "steam",
                "Steam (All Games + CS2 & Dota 2 Live Stats)",
                self.v_steam_en,
                self._toggle_steam_rpc,
                "Shows your running Steam game cover art, genre, Steam profile, and live CS2 / Dota 2 score & K/D/A.",
            ),
            (
                "roblox",
                "Roblox (Live Experience Title & Thumbnail)",
                self.v_roblox_en,
                self._toggle_roblox_rpc,
                "Detects the exact Roblox experience you joined and shows its official icon, creator, and 'View on Roblox' button.",
            ),
            (
                "xbox",
                "Xbox / PC Game Pass (Store & Xbox App)",
                self.v_xbox_en,
                self._toggle_xbox_rpc,
                "Shows PC Game Pass and Microsoft Store games along with your linked Xbox Live Gamertag on Discord.",
            ),
            (
                "custom_apps",
                "Custom External Apps (.exe Games & Tools)",
                self.v_custom_en,
                self._toggle_custom_rpc,
                "Displays any custom external .exe applications or games you have added in Section 6 or Game Hub.",
            ),
        ]

        for idx, (pkey, ptitle, pvar, pcmd, pdesc) in enumerate(rpc_platforms):
            row_top = tk.Frame(rpc_card, bg=p["border_dark"])
            row_top.pack(fill="x", pady=(2 if idx > 0 else 0, 0))
            cb_p = tk.Checkbutton(
                row_top,
                text=ptitle,
                variable=pvar,
                command=pcmd,
                font=("Segoe UI", 8, "bold"),
                fg=p["text_primary"],
                bg=p["border_dark"],
                selectcolor=p["card_bg"],
                activebackground=p["border_dark"],
                activeforeground=p["status_ok"],
                cursor="hand2",
            )
            cb_p.pack(side="left")
            self._tip(cb_p, pdesc)
            st_lbl = tk.Label(
                row_top,
                text="● Ready",
                font=("Segoe UI", 7, "bold"),
                fg=p["status_ok"],
                bg=p["border_dark"],
            )
            st_lbl.pack(side="right")
            self.lbl_set_plat_status[pkey] = st_lbl
            if pkey in ("riot", "ea", "ubisoft", "gog", "battlenet"):
                self.lbl_launcher_rows[pkey] = st_lbl

            tk.Label(
                rpc_card,
                text=pdesc,
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=p["border_dark"],
                anchor="w",
                justify="left",
                wraplength=362,
            ).pack(fill="x", pady=(0, 4 if idx < len(rpc_platforms) - 1 else 0))

        # 4. MINECRAFT CLIENT SUB-TOGGLES
        sec4_hdr = tk.Frame(self.settings_inner, bg=p["card_bg"])
        sec4_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            sec4_hdr,
            text="4. MINECRAFT CLIENT SUB-TOGGLES",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        tk.Label(
            sec4_hdr,
            text="Active game window only",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["card_bg"],
        ).pack(side="right")

        mc_box = tk.Frame(
            self.settings_inner,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=9,
            pady=6,
        )
        mc_box.pack(fill="x", pady=(0, 8))
        self.lbl_mc_rows = {}
        mc_defs = [
            (
                "lunar",
                "Lunar Client (PvP / FPS Boost)",
                self.v_mc_lunar,
                "Detects Lunar Client JVM with an active game window and shows your Minecraft version and mode.",
            ),
            (
                "badlion",
                "Badlion Client (BLC)",
                self.v_mc_badlion,
                "Detects Badlion Client with an active game window and shows your Minecraft version and mode.",
            ),
            (
                "feather",
                "Feather Client (Modded / Fabric)",
                self.v_mc_feather,
                "Detects Feather Client with an active game window and shows your Minecraft version and mode.",
            ),
            (
                "labymod",
                "LabyMod 4 (Custom Client)",
                self.v_mc_labymod,
                "Detects LabyMod 4 with an active game window and shows your Minecraft version and mode.",
            ),
            (
                "prism_vanilla",
                "Prism / Vanilla Java & Bedrock",
                self.v_mc_prism,
                "Detects Prism Launcher, MultiMC, Vanilla Java, Fabric/Forge, and Windows Bedrock when in-game.",
            ),
        ]
        for r_idx, (mkey, mtitle, mvar, mtip) in enumerate(mc_defs):
            mrow = tk.Frame(mc_box, bg=p["border_dark"])
            mrow.pack(fill="x", pady=(2 if r_idx > 0 else 0, 0))
            cb = tk.Checkbutton(
                mrow,
                text=mtitle,
                variable=mvar,
                command=self._toggle_mc_rpc,
                font=("Segoe UI", 8, "bold"),
                fg=p["text_primary"],
                bg=p["border_dark"],
                selectcolor=p["card_bg"],
                activebackground=p["border_dark"],
                activeforeground=p["status_ok"],
                cursor="hand2",
            )
            cb.pack(side="left")
            self._tip(cb, mtip)
            mst_lbl = tk.Label(
                mrow,
                text="● Ready",
                font=("Segoe UI", 7, "bold"),
                fg=p["status_ok"],
                bg=p["border_dark"],
                anchor="e",
            )
            mst_lbl.pack(side="right")
            self.lbl_mc_rows[mkey] = mst_lbl
            tk.Label(
                mc_box,
                text=mtip,
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=p["border_dark"],
                anchor="w",
                justify="left",
                wraplength=362,
            ).pack(fill="x", pady=(0, 3 if r_idx < len(mc_defs) - 1 else 0))

        # 5. GACHA GAMES & HOYOPLAY SUB-TOGGLES
        sec5_gacha_hdr = tk.Frame(self.settings_inner, bg=p["card_bg"])
        sec5_gacha_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            sec5_gacha_hdr,
            text="5. GACHA GAMES & HOYOPLAY SUB-TOGGLES",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        self.lbl_set_gacha_count = tk.Label(
            sec5_gacha_hdr,
            text="11 / 11 Enabled",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_ok"],
            bg=p["card_bg"],
        )
        self.lbl_set_gacha_count.pack(side="right")

        gacha_sub_box = tk.Frame(
            self.settings_inner,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=9,
            pady=6,
        )
        gacha_sub_box.pack(fill="x", pady=(0, 8))

        gacha_master_row = tk.Frame(gacha_sub_box, bg=p["card_alt"], padx=6, pady=3)
        gacha_master_row.pack(fill="x", pady=(0, 4))
        cb_gm = tk.Checkbutton(
            gacha_master_row,
            text="Master Switch: HoYoPlay & Gacha Games RPC",
            variable=self.v_gacha_en,
            command=self._toggle_gacha_rpc,
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_alt"],
            selectcolor=p["card_bg"],
            activebackground=p["card_alt"],
            activeforeground=p["status_ok"],
            cursor="hand2",
        )
        cb_gm.pack(side="left")
        self._tip(
            cb_gm,
            "Master toggle for all 11 supported HoYoPlay & Gacha games.",
        )
        self.lbl_gacha_master_badge = tk.Label(
            gacha_master_row,
            text="● Ready",
            font=("Segoe UI", 7, "bold"),
            fg=p["status_warn"],
            bg=p["card_alt"],
            anchor="e",
        )
        self.lbl_gacha_master_badge.pack(side="right")

        self.lbl_gacha_rows = {}
        for g_idx, gdef in enumerate(GACHA_SUB_GAME_DEFS):
            gkey = gdef["key"]
            gname = gdef["name"]
            gpub = gdef["publisher"]
            gtip = gdef["tip"]
            gvar = self.v_gacha_sub[gkey]

            grow = tk.Frame(gacha_sub_box, bg=p["border_dark"])
            grow.pack(fill="x", pady=(2 if g_idx > 0 else 0, 0))
            cb_g = tk.Checkbutton(
                grow,
                text=f"{g_idx + 1}. {gname} ({gpub})",
                variable=gvar,
                command=self._toggle_gacha_rpc,
                font=("Segoe UI", 8, "bold"),
                fg=p["text_primary"],
                bg=p["border_dark"],
                selectcolor=p["card_bg"],
                activebackground=p["border_dark"],
                activeforeground=p["status_ok"],
                cursor="hand2",
            )
            cb_g.pack(side="left")
            self._tip(cb_g, gtip)
            gst_lbl = tk.Label(
                grow,
                text="● Ready",
                font=("Segoe UI", 7, "bold"),
                fg=p["status_warn"],
                bg=p["border_dark"],
                anchor="e",
            )
            gst_lbl.pack(side="right")
            self.lbl_gacha_rows[gkey] = gst_lbl
            tk.Label(
                gacha_sub_box,
                text=gtip,
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=p["border_dark"],
                anchor="w",
                justify="left",
                wraplength=362,
            ).pack(
                fill="x",
                pady=(0, 3 if g_idx < len(GACHA_SUB_GAME_DEFS) - 1 else 0),
            )

        # 6. CUSTOM EXTERNAL APPLICATIONS (.EXE)
        sec5_hdr = tk.Frame(self.settings_inner, bg=p["card_bg"])
        sec5_hdr.pack(fill="x", pady=(0, 2))
        tk.Label(
            sec5_hdr,
            text="6. CUSTOM EXTERNAL APPLICATIONS (.EXE)",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
        ).pack(side="left")
        tk.Button(
            sec5_hdr,
            text="➕ Add via Dialog",
            command=self._show_add_custom_modal,
            font=("Segoe UI", 7, "bold"),
            bg=p["border_dark"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=0,
        ).pack(side="right")

        custom_box = tk.Frame(
            self.settings_inner,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=9,
            pady=6,
        )
        custom_box.pack(fill="x", pady=(0, 6))

        tk.Label(
            custom_box,
            text="Add any standalone .exe game or application to show on Discord Rich Presence when running:",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["border_dark"],
            anchor="w",
            justify="left",
            wraplength=362,
        ).pack(fill="x", pady=(0, 4))

        c_row1 = tk.Frame(custom_box, bg=p["border_dark"])
        c_row1.pack(fill="x", pady=(0, 3))
        self.ent_custom_exe = tk.Entry(
            c_row1,
            font=("Segoe UI", 8),
            bg=p["card_bg"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_custom_exe.pack(
            side="left", fill="x", expand=True, ipady=2, padx=(0, 4)
        )
        tk.Button(
            c_row1,
            text="📂 Browse .exe",
            command=self._browse_custom_exe_inline,
            font=("Segoe UI", 7, "bold"),
            bg=p["card_bg"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=7,
            pady=2,
        ).pack(side="right")

        c_row2 = tk.Frame(custom_box, bg=p["border_dark"])
        c_row2.pack(fill="x", pady=(0, 3))
        tk.Label(
            c_row2,
            text="Name:",
            font=("Segoe UI", 7, "bold"),
            fg=p["text_muted"],
            bg=p["border_dark"],
        ).pack(side="left", padx=(0, 3))
        self.ent_custom_name = tk.Entry(
            c_row2,
            font=("Segoe UI", 8),
            bg=p["card_bg"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
            width=16,
        )
        self.ent_custom_name.pack(side="left", ipady=2, padx=(0, 6))
        tk.Label(
            c_row2,
            text="Status:",
            font=("Segoe UI", 7, "bold"),
            fg=p["text_muted"],
            bg=p["border_dark"],
        ).pack(side="left", padx=(0, 3))
        self.ent_custom_state = tk.Entry(
            c_row2,
            font=("Segoe UI", 8),
            bg=p["card_bg"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_custom_state.insert(0, "In Game")
        self.ent_custom_state.pack(side="left", fill="x", expand=True, ipady=2)

        c_row3 = tk.Frame(custom_box, bg=p["border_dark"])
        c_row3.pack(fill="x", pady=(0, 4))
        tk.Label(
            c_row3,
            text="Icon URL (Optional):",
            font=("Segoe UI", 7, "bold"),
            fg=p["text_muted"],
            bg=p["border_dark"],
        ).pack(side="left", padx=(0, 4))
        self.ent_custom_icon = tk.Entry(
            c_row3,
            font=("Segoe UI", 8),
            bg=p["card_bg"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_custom_icon.pack(
            side="left", fill="x", expand=True, ipady=2, padx=(0, 4)
        )
        tk.Button(
            c_row3,
            text="+ Save App",
            command=self._add_custom_exe_inline,
            font=("Segoe UI", 7, "bold"),
            bg=p["card_bg"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=2,
        ).pack(side="right")

        self.custom_apps_list_frame = tk.Frame(custom_box, bg=p["border_dark"])
        self.custom_apps_list_frame.pack(fill="x")
        self._render_custom_apps_settings_list()

        self.settings_inner.update_idletasks()
        self.settings_canvas.config(scrollregion=self.settings_canvas.bbox("all"))

    def _browse_custom_exe_inline(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Application or Game Executable (.exe)",
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")],
        )
        if path:
            self.ent_custom_exe.delete(0, "end")
            self.ent_custom_exe.insert(0, path)
            if not self.ent_custom_name.get().strip():
                stem = os.path.splitext(os.path.basename(path))[0]
                clean = stem.replace("-Win64-Shipping", "").replace("_", " ").strip()
                self.ent_custom_name.insert(0, clean)

    def _add_custom_exe_inline(self):
        exe_path = self.ent_custom_exe.get().strip()
        if not exe_path:
            self._browse_custom_exe_inline()
            exe_path = self.ent_custom_exe.get().strip()
            if not exe_path:
                return
        name = self.ent_custom_name.get().strip()
        st = self.ent_custom_state.get().strip() or "In Game"
        icon = self.ent_custom_icon.get().strip()
        self.engine.custom_apps.add_app(exe_path, name, st, icon)
        self.ent_custom_exe.delete(0, "end")
        self.ent_custom_name.delete(0, "end")
        self.ent_custom_icon.delete(0, "end")
        self._render_custom_apps_settings_list()
        if self.current_tab == "gamehub":
            self._render_steam_games()
        self.refresh_ui()

    def _remove_custom_exe_action(self, exe_key):
        self.engine.custom_apps.remove_app(exe_key)
        self._render_custom_apps_settings_list()
        if self.current_tab == "gamehub":
            self._render_steam_games()
        self.refresh_ui()

    def _render_custom_apps_settings_list(self):
        if not hasattr(self, "custom_apps_list_frame"):
            return
        p = self.PAL
        for child in self.custom_apps_list_frame.winfo_children():
            child.destroy()

        apps = CFG.get_custom_apps()
        if not apps:
            tk.Label(
                self.custom_apps_list_frame,
                text="No custom external .exe apps added yet.",
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=p["border_dark"],
                anchor="w",
            ).pack(fill="x", pady=(2, 0))
        else:
            for item in apps:
                row = tk.Frame(
                    self.custom_apps_list_frame, bg=p["card_bg"], padx=6, pady=3
                )
                row.pack(fill="x", pady=1)
                nm = item.get("name") or item.get("exe_name") or "Custom App"
                ex = item.get("exe_name") or os.path.basename(item.get("exe_path", ""))
                tk.Label(
                    row,
                    text=f"• {nm[:22]} ({ex[:18]})",
                    font=("Segoe UI", 7, "bold"),
                    fg=p["text_primary"],
                    bg=p["card_bg"],
                    anchor="w",
                ).pack(side="left")
                tk.Button(
                    row,
                    text="✕",
                    command=lambda k=ex: self._remove_custom_exe_action(k),
                    font=("Segoe UI", 7, "bold"),
                    bg=p["card_bg"],
                    fg=p["status_err"],
                    activebackground=p["border_dark"],
                    relief="flat",
                    cursor="hand2",
                    padx=4,
                    pady=0,
                ).pack(side="right")

        if hasattr(self, "settings_inner") and hasattr(self, "settings_canvas"):
            self.settings_inner.update_idletasks()
            self.settings_canvas.config(scrollregion=self.settings_canvas.bbox("all"))

    def _browser_login_action(self, plat):
        if plat == "epic":
            self._epic_action()
            return
        lbl = self.lbl_acc_status.get(plat) if hasattr(self, "lbl_acc_status") else None
        if lbl:
            lbl.config(text="⏳ Waiting for Browser Login...", fg=self.PAL["status_warn"])
        self.engine.auth.start_browser_login(plat)

    def _auto_detect_account_action(self, plat):
        lbl = self.lbl_acc_status.get(plat) if hasattr(self, "lbl_acc_status") else None
        if lbl:
            lbl.config(text="⏳ Scanning Local PC...", fg=self.PAL["status_warn"])

        def _work():
            if plat == "epic":
                self.engine.epic.load()
            elif plat == "steam":
                self.engine.steam.reset_steam_account()
            elif plat == "gacha":
                self.engine.gacha.reset_profile()
            elif plat.startswith("gacha_"):
                gkey = plat.replace("gacha_", "", 1)
                self.engine.gacha.detect_game_account(gkey, from_browser_callback=False)
            elif plat == "battlenet":
                self.engine.battlenet.detect_local_account()
            elif plat == "riot":
                self.engine.riot.detect_local_account()
            elif plat == "roblox":
                self.engine.roblox.detect_local_account()
            elif plat == "xbox":
                self.engine.xbox.reset_gamertag()
            elif plat == "ea":
                self.engine.ea.detect_local_account()
            elif plat == "ubisoft":
                self.engine.ubisoft.detect_local_account()
            elif plat == "gog":
                self.engine.gog.detect_local_account()
            elif plat == "minecraft":
                self.engine.minecraft.detect_local_account()
            self.engine.sync_rpc(force=True)

        threading.Thread(target=_work, daemon=True).start()

    def _unlink_account_action(self, plat):
        self.state.auth_pending[plat] = False
        if plat == "epic":
            self.engine.epic.unlink()
        elif plat == "steam":
            self.engine.steam.unlink_steam()
        elif plat == "gacha":
            self.engine.gacha.unlink()
        elif plat.startswith("gacha_"):
            gkey = plat.replace("gacha_", "", 1)
            self.engine.gacha.unlink_game(gkey)
        elif plat == "battlenet":
            self.engine.battlenet.unlink()
        elif plat == "riot":
            self.engine.riot.unlink()
        elif plat == "roblox":
            self.engine.roblox.unlink()
        elif plat == "xbox":
            self.engine.xbox.unlink()
        elif plat == "ea":
            self.engine.ea.unlink()
        elif plat == "ubisoft":
            self.engine.ubisoft.unlink()
        elif plat == "gog":
            self.engine.gog.unlink()
        elif plat == "minecraft":
            self.engine.minecraft.unlink()

        ent = self.ent_acc_input.get(plat) if hasattr(self, "ent_acc_input") else None
        if ent:
            ent.delete(0, "end")
        self.refresh_ui()
        threading.Thread(
            target=lambda: self.engine.sync_rpc(force=True), daemon=True
        ).start()

    def _manual_link_account_action(self, plat):
        ent = self.ent_acc_input.get(plat) if hasattr(self, "ent_acc_input") else None
        val = ent.get().strip() if ent else ""
        if not val:
            if plat == "gacha" or plat.startswith("gacha_"):
                self._auto_detect_account_action(plat)
            return
        lbl = self.lbl_acc_status.get(plat) if hasattr(self, "lbl_acc_status") else None
        if lbl:
            lbl.config(text="⏳ Linking & Syncing...", fg=self.PAL["status_warn"])

        def _work():
            self.engine.auth.link_platform_value(plat, val)
            self.engine.sync_rpc(force=True)

        threading.Thread(target=_work, daemon=True).start()

    def _link_steam_manual_action(self):
        self._manual_link_account_action("steam")

    def _reset_steam_action(self):
        self._auto_detect_account_action("steam")

    def _link_roblox_action(self):
        self._manual_link_account_action("roblox")

    def _link_xbox_action(self):
        self._manual_link_account_action("xbox")

    def _reset_xbox_action(self):
        self._auto_detect_account_action("xbox")

    def _save_gacha_profile_action(self):
        self._auto_detect_account_action("gacha")

    def _reset_gacha_profile_action(self):
        self._auto_detect_account_action("gacha")

    def _switch_tab(self, tab_key):
        if tab_key in ("steam", "launchers"):
            tab_key = "gamehub"
        self.current_tab = tab_key
        p = self.PAL
        for k, b in self.tab_btns.items():
            b.config(
                bg=p["border_dark"] if k == tab_key else p["card_bg"],
                fg=p["status_ok"] if k == tab_key else p["text_muted"],
            )
        for frame in (
            self.tab_dashboard,
            self.tab_gamehub,
            self.tab_friends,
            self.tab_media,
            self.tab_accounts,
            self.tab_settings,
        ):
            frame.pack_forget()
        if tab_key == "dashboard":
            self.tab_dashboard.pack(fill="both", expand=True)
        elif tab_key == "gamehub":
            self.tab_gamehub.pack(fill="both", expand=True)
            if self.gamehub_subtab == "library":
                self._render_steam_games()
        elif tab_key == "friends":
            self.tab_friends.pack(fill="both", expand=True)
            self._render_friends_list()
        elif tab_key == "media":
            self.tab_media.pack(fill="both", expand=True)
        elif tab_key == "accounts":
            self.tab_accounts.pack(fill="both", expand=True)
            if hasattr(self, "accounts_inner") and hasattr(self, "accounts_canvas"):
                self.accounts_inner.update_idletasks()
                self.accounts_canvas.config(scrollregion=self.accounts_canvas.bbox("all"))
        elif tab_key == "settings":
            self.tab_settings.pack(fill="both", expand=True)
            self._render_custom_apps_settings_list()
            self.settings_inner.update_idletasks()
            self.settings_canvas.config(scrollregion=self.settings_canvas.bbox("all"))

    def _set_priority_mode(self, mode_key):
        nxt = mode_key if mode_key in self.PRIORITY_ORDER else "auto"
        self.state.platform_priority = nxt
        Reg.set("PlatformPriority", nxt)
        self.refresh_ui()
        threading.Thread(
            target=lambda: self.engine.sync_rpc(force=True), daemon=True
        ).start()

    def _cycle_priority(self):
        cur = (
            self.state.platform_priority
            if self.state.platform_priority in self.PRIORITY_ORDER
            else "auto"
        )
        nxt = self.PRIORITY_ORDER[
            (self.PRIORITY_ORDER.index(cur) + 1) % len(self.PRIORITY_ORDER)
        ]
        self._set_priority_mode(nxt)

    def _set_all_rpcs(self, enabled):
        flag = bool(enabled)
        for v in (
            self.v_fortnite_en,
            self.v_mc_en,
            self.v_gacha_en,
            self.v_riot_en,
            self.v_ea_en,
            self.v_ubisoft_en,
            self.v_gog_en,
            self.v_battlenet_en,
            self.v_steam_en,
            self.v_roblox_en,
            self.v_xbox_en,
            self.v_custom_en,
            self.v_mc_lunar,
            self.v_mc_badlion,
            self.v_mc_feather,
            self.v_mc_labymod,
            self.v_mc_prism,
        ):
            v.set(flag)
        if hasattr(self, "v_gacha_sub"):
            for gv in self.v_gacha_sub.values():
                gv.set(flag)

        self.state.fortnite_enabled = flag
        self.state.minecraft_enabled = flag
        self.state.gacha_enabled = flag
        self.state.riot_enabled = flag
        self.state.ea_enabled = flag
        self.state.ubisoft_enabled = flag
        self.state.gog_enabled = flag
        self.state.battlenet_enabled = flag
        self.state.steam_enabled = flag
        self.state.roblox_enabled = flag
        self.state.xbox_enabled = flag
        self.state.custom_apps_enabled = flag
        self.state.mc_lunar_enabled = flag
        self.state.mc_badlion_enabled = flag
        self.state.mc_feather_enabled = flag
        self.state.mc_labymod_enabled = flag
        self.state.mc_prism_vanilla_enabled = flag
        for gdef in GACHA_SUB_GAME_DEFS:
            self.state.gacha_sub_enabled[gdef["key"]] = flag

        ival = int(flag)
        for reg_k in (
            "FortniteEnabled",
            "MinecraftEnabled",
            "GachaEnabled",
            "RiotEnabled",
            "EAEnabled",
            "UbisoftEnabled",
            "GOGEnabled",
            "BattleNetEnabled",
            "SteamEnabled",
            "RobloxEnabled",
            "XboxEnabled",
            "CustomAppsEnabled",
            "MCLunarEnabled",
            "MCBadlionEnabled",
            "MCFeatherEnabled",
            "MCLabyModEnabled",
            "MCPrismVanillaEnabled",
        ):
            Reg.set(reg_k, ival, winreg.REG_DWORD)
        for gdef in GACHA_SUB_GAME_DEFS:
            Reg.set(gdef["reg_toggle"], ival, winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(target=self.engine.rescan, daemon=True).start()

    def _toggle_fortnite_rpc(self):
        val = bool(self.v_fortnite_en.get())
        self.state.fortnite_enabled = val
        Reg.set("FortniteEnabled", int(val), winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(
            target=lambda: self.engine.sync_rpc(force=True), daemon=True
        ).start()

    def _toggle_gacha_rpc(self):
        val = bool(self.v_gacha_en.get())
        self.state.gacha_enabled = val
        Reg.set("GachaEnabled", int(val), winreg.REG_DWORD)
        if hasattr(self, "v_gacha_sub"):
            for gdef in GACHA_SUB_GAME_DEFS:
                gkey = gdef["key"]
                gflag = bool(self.v_gacha_sub[gkey].get())
                self.state.gacha_sub_enabled[gkey] = gflag
                Reg.set(gdef["reg_toggle"], int(gflag), winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(target=self.engine.rescan, daemon=True).start()

    def _toggle_custom_rpc(self):
        val = bool(self.v_custom_en.get())
        self.state.custom_apps_enabled = val
        Reg.set("CustomAppsEnabled", int(val), winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(target=self.engine.rescan, daemon=True).start()

    def _toggle_steam_rpc(self):
        val = bool(self.v_steam_en.get())
        self.state.steam_enabled = val
        Reg.set("SteamEnabled", int(val), winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(
            target=lambda: self.engine.sync_rpc(force=True), daemon=True
        ).start()

    def _toggle_roblox_rpc(self):
        val = bool(self.v_roblox_en.get())
        self.state.roblox_enabled = val
        Reg.set("RobloxEnabled", int(val), winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(
            target=lambda: self.engine.sync_rpc(force=True), daemon=True
        ).start()

    def _toggle_xbox_rpc(self):
        val = bool(self.v_xbox_en.get())
        self.state.xbox_enabled = val
        Reg.set("XboxEnabled", int(val), winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(
            target=lambda: self.engine.sync_rpc(force=True), daemon=True
        ).start()

    def _toggle_launcher_rpc(self):
        self.state.riot_enabled = bool(self.v_riot_en.get())
        self.state.ea_enabled = bool(self.v_ea_en.get())
        self.state.ubisoft_enabled = bool(self.v_ubisoft_en.get())
        self.state.gog_enabled = bool(self.v_gog_en.get())
        self.state.battlenet_enabled = bool(self.v_battlenet_en.get())
        Reg.set("RiotEnabled", int(self.state.riot_enabled), winreg.REG_DWORD)
        Reg.set("EAEnabled", int(self.state.ea_enabled), winreg.REG_DWORD)
        Reg.set("UbisoftEnabled", int(self.state.ubisoft_enabled), winreg.REG_DWORD)
        Reg.set("GOGEnabled", int(self.state.gog_enabled), winreg.REG_DWORD)
        Reg.set(
            "BattleNetEnabled", int(self.state.battlenet_enabled), winreg.REG_DWORD
        )
        self.refresh_ui()
        threading.Thread(target=self.engine.rescan, daemon=True).start()

    def _toggle_mc_rpc(self):
        self.state.minecraft_enabled = bool(self.v_mc_en.get())
        self.state.mc_lunar_enabled = bool(self.v_mc_lunar.get())
        self.state.mc_badlion_enabled = bool(self.v_mc_badlion.get())
        self.state.mc_feather_enabled = bool(self.v_mc_feather.get())
        self.state.mc_labymod_enabled = bool(self.v_mc_labymod.get())
        self.state.mc_prism_vanilla_enabled = bool(self.v_mc_prism.get())
        Reg.set(
            "MinecraftEnabled", int(self.state.minecraft_enabled), winreg.REG_DWORD
        )
        Reg.set("MCLunarEnabled", int(self.state.mc_lunar_enabled), winreg.REG_DWORD)
        Reg.set(
            "MCBadlionEnabled", int(self.state.mc_badlion_enabled), winreg.REG_DWORD
        )
        Reg.set(
            "MCFeatherEnabled", int(self.state.mc_feather_enabled), winreg.REG_DWORD
        )
        Reg.set(
            "MCLabyModEnabled", int(self.state.mc_labymod_enabled), winreg.REG_DWORD
        )
        Reg.set(
            "MCPrismVanillaEnabled",
            int(self.state.mc_prism_vanilla_enabled),
            winreg.REG_DWORD,
        )
        self.refresh_ui()
        threading.Thread(target=self.engine.rescan, daemon=True).start()

    def _toggle_medal_priority(self):
        val = bool(self.v_medal_prio.get())
        self.state.medal_priority_enabled = val
        Reg.set("MedalPriorityRPC", int(val), winreg.REG_DWORD)
        self.refresh_ui()
        if val:
            threading.Thread(
                target=self.engine.force_reassert_rpc, daemon=True
            ).start()
        else:
            threading.Thread(
                target=lambda: self.engine.sync_rpc(force=True), daemon=True
            ).start()

    def _install_gsi_action(self):
        targets = self.engine.steam.install_gsi_configs()
        if targets:
            self.btn_install_gsi.config(
                text=f"✓ Auto: {', '.join(targets)}", fg=self.PAL["status_ok"]
            )
        else:
            self.btn_install_gsi.config(
                text="No CS2/Dota Found", fg=self.PAL["status_warn"]
            )
        self.refresh_ui()

    def _rescan_steam_library(self):
        def _worker():
            self.engine.epic.scan_installed_games()
            self.engine.steam.scan_installed_games()
            self.engine.steam.detect_local_steam_user()
            self.engine.xbox.scan_installed_xbox_games()
            self.engine.gacha.scan_installed_games()
            self.engine.riot.scan_installed_games()
            self.engine.ea.scan_installed_games()
            self.engine.ubisoft.scan_installed_games()
            self.engine.gog.scan_installed_games()
            self.engine.battlenet.scan_installed_games()
            self.after(0, lambda: (self._render_steam_games(), self.refresh_ui()))

        threading.Thread(target=_worker, daemon=True).start()

    def _render_steam_games(self):
        p = self.PAL
        for child in self.steam_inner.winfo_children():
            child.destroy()

        flt = getattr(self, "gamehub_lib_filter", "all")
        entries = []

        if flt in ("all", "epic"):
            for g in self.state.epic_installed_games:
                is_fn = g["name"].lower() == "fortnite"
                is_run = (
                    (self.state.running if is_fn else (self.state.epic_game_running and self.state.epic_game_name == g["name"]))
                )
                entries.append(
                    {
                        "kind": "epic",
                        "name": g["name"],
                        "badge": "Epic Games",
                        "running": is_run,
                        "dir": g.get("install_dir") or "",
                        "epic_entry": g,
                    }
                )

        if flt in ("all", "custom"):
            for app in CFG.get_custom_apps():
                nm = app.get("name") or app.get("exe_name") or "Custom App"
                epath = app.get("exe_path") or ""
                ename = app.get("exe_name") or os.path.basename(epath)
                is_run = (
                    self.state.custom_app_running
                    and self.state.custom_app_name == nm
                )
                entries.append(
                    {
                        "kind": "custom",
                        "name": nm,
                        "badge": "Custom .exe",
                        "running": is_run,
                        "dir": epath if os.path.exists(epath) else "",
                        "exe_key": ename,
                    }
                )

        if flt in ("all", "gacha"):
            for g in self.state.gacha_installed_games:
                is_run = (
                    self.state.gacha_running
                    and self.state.gacha_game_name == g["name"]
                )
                entries.append(
                    {
                        "kind": "gacha",
                        "name": g["name"],
                        "badge": "HoYoPlay / Gacha",
                        "running": is_run,
                        "dir": g.get("install_dir") or "",
                    }
                )

        if flt in ("all", "steam"):
            for g in self.state.steam_installed_games:
                aid = g["appid"]
                is_run = self.state.steam_running and self.state.steam_appid == aid
                entries.append(
                    {
                        "kind": "steam",
                        "name": g["name"],
                        "badge": f"Steam • {aid}",
                        "running": is_run,
                        "appid": aid,
                        "dir": g.get("install_dir") or "",
                    }
                )

        if flt in ("all", "xbox"):
            for g in self.state.xbox_installed_games:
                is_run = (
                    self.state.xbox_running and self.state.xbox_game_name == g["name"]
                )
                entries.append(
                    {
                        "kind": "xbox",
                        "name": g["name"],
                        "badge": "Xbox / Game Pass",
                        "running": is_run,
                        "dir": g.get("install_dir") or "",
                    }
                )

        if flt in ("all", "launchers"):
            for plat_lbl, run_flag, run_name, glist in [
                (
                    "Riot Games",
                    self.state.riot_running,
                    self.state.riot_game_name,
                    self.state.riot_installed_games,
                ),
                (
                    "EA App",
                    self.state.ea_running,
                    self.state.ea_game_name,
                    self.state.ea_installed_games,
                ),
                (
                    "Ubisoft",
                    self.state.ubisoft_running,
                    self.state.ubisoft_game_name,
                    self.state.ubisoft_installed_games,
                ),
                (
                    "GOG Galaxy",
                    self.state.gog_running,
                    self.state.gog_game_name,
                    self.state.gog_installed_games,
                ),
                (
                    "Battle.net",
                    self.state.battlenet_running,
                    self.state.battlenet_game_name,
                    self.state.battlenet_installed_games,
                ),
            ]:
                for g in glist:
                    is_run = run_flag and run_name == g["name"]
                    entries.append(
                        {
                            "kind": "launcher",
                            "name": g["name"],
                            "badge": plat_lbl,
                            "running": is_run,
                            "dir": g.get("install_dir") or "",
                        }
                    )

        self.lbl_steam_lib_count.config(text=f"GAMES ({len(entries)}):")
        if not entries:
            tk.Label(
                self.steam_inner,
                text="No games found for the selected filter.\nClick '↻ Rescan' or '➕ Add External .exe' above.",
                font=("Segoe UI", 8),
                fg=p["text_muted"],
                bg=p["border_dark"],
                justify="center",
                pady=30,
            ).pack(fill="x")
            self.steam_inner.update_idletasks()
            self.steam_canvas.config(scrollregion=self.steam_canvas.bbox("all"))
            return

        for item in entries:
            is_running = item["running"]
            row_bg = p["card_bg"] if is_running else "#4F4B40"
            row = tk.Frame(self.steam_inner, bg=row_bg, padx=8, pady=5)
            row.pack(fill="x", pady=1, padx=2)
            title_fg = p["status_ok"] if is_running else p["text_primary"]
            prefix = "▶ " if is_running else "• "
            tk.Label(
                row,
                text=f"{prefix}{item['name'][:25]}",
                font=("Segoe UI", 8, "bold"),
                fg=title_fg,
                bg=row_bg,
                anchor="w",
            ).pack(side="left")

            if item["kind"] == "steam":
                aid = item["appid"]
                if is_running:
                    tk.Button(
                        row,
                        text="✕ Close",
                        command=lambda a=aid: threading.Thread(
                            target=lambda: self.engine.steam.close_game(a), daemon=True
                        ).start(),
                        font=("Segoe UI", 7, "bold"),
                        bg=p["border_dark"],
                        fg=p["status_err"],
                        activebackground=p["outer_bg"],
                        relief="flat",
                        cursor="hand2",
                        padx=6,
                        pady=0,
                    ).pack(side="right")
                else:
                    tk.Button(
                        row,
                        text="▶ Launch",
                        command=lambda a=aid: threading.Thread(
                            target=lambda: self.engine.steam.launch_game(a), daemon=True
                        ).start(),
                        font=("Segoe UI", 7, "bold"),
                        bg=p["border_dark"],
                        fg=p["status_ok"],
                        activebackground=p["outer_bg"],
                        relief="flat",
                        cursor="hand2",
                        padx=6,
                        pady=0,
                    ).pack(side="right")
            elif item["kind"] == "epic":
                e_ent = item.get("epic_entry") or item.get("dir", "")
                if is_running:
                    tk.Label(
                        row,
                        text="★ RUNNING",
                        font=("Segoe UI", 7, "bold"),
                        fg=p["status_ok"],
                        bg=row_bg,
                    ).pack(side="right")
                else:
                    tk.Button(
                        row,
                        text="▶ Launch",
                        command=lambda ge=e_ent: threading.Thread(
                            target=lambda: self.engine.epic.launch_game(ge),
                            daemon=True,
                        ).start(),
                        font=("Segoe UI", 7, "bold"),
                        bg=p["border_dark"],
                        fg=p["status_ok"],
                        activebackground=p["outer_bg"],
                        relief="flat",
                        cursor="hand2",
                        padx=6,
                        pady=0,
                    ).pack(side="right")
            elif item["kind"] == "custom":
                ekey = item.get("exe_key", "")
                gdir = item.get("dir", "")
                tk.Button(
                    row,
                    text="✕",
                    command=lambda k=ekey: self._remove_custom_exe_action(k),
                    font=("Segoe UI", 7, "bold"),
                    bg=p["border_dark"],
                    fg=p["status_err"],
                    activebackground=p["outer_bg"],
                    relief="flat",
                    cursor="hand2",
                    padx=4,
                    pady=0,
                ).pack(side="right", padx=(3, 0))
                if is_running:
                    tk.Label(
                        row,
                        text="★ RUNNING",
                        font=("Segoe UI", 7, "bold"),
                        fg=p["status_ok"],
                        bg=row_bg,
                    ).pack(side="right")
                elif gdir:
                    tk.Button(
                        row,
                        text="▶ Launch",
                        command=lambda d=gdir: self._open_or_launch_dir(d),
                        font=("Segoe UI", 7, "bold"),
                        bg=p["border_dark"],
                        fg=p["status_ok"],
                        activebackground=p["outer_bg"],
                        relief="flat",
                        cursor="hand2",
                        padx=6,
                        pady=0,
                    ).pack(side="right")
            else:
                gdir = item["dir"]
                if is_running:
                    tk.Label(
                        row,
                        text="★ RUNNING",
                        font=("Segoe UI", 7, "bold"),
                        fg=p["status_ok"],
                        bg=row_bg,
                    ).pack(side="right")
                elif gdir:
                    tk.Button(
                        row,
                        text="📂 Folder",
                        command=lambda d=gdir: self._open_or_launch_dir(d),
                        font=("Segoe UI", 7, "bold"),
                        bg=p["border_dark"],
                        fg=p["text_primary"],
                        activebackground=p["outer_bg"],
                        relief="flat",
                        cursor="hand2",
                        padx=6,
                        pady=0,
                    ).pack(side="right")
            tk.Label(
                row,
                text=item["badge"],
                font=("Segoe UI", 7),
                fg=p["text_muted"],
                bg=row_bg,
            ).pack(side="right", padx=(0, 8))

        self.steam_inner.update_idletasks()
        self.steam_canvas.config(scrollregion=self.steam_canvas.bbox("all"))

    def _toggle_friends_filter(self):
        self.friends_filter_online = not self.friends_filter_online
        self.btn_filter_friends.config(
            text="Filter: Online" if self.friends_filter_online else "Filter: All"
        )
        self._render_friends_list()

    def _toggle_media_rpc(self):
        val = bool(self.v_media_rpc.get())
        self.state.show_media_rpc = val
        Reg.set("ShowMediaRPC", int(val), winreg.REG_DWORD)
        self.refresh_ui()
        threading.Thread(
            target=lambda: self.engine.sync_rpc(force=True), daemon=True
        ).start()

    def _render_generic_friends_rows(self, friends, plat_key, empty_msg):
        p = self.PAL
        filtered = (
            [f for f in friends if f.get("online") or f.get("in_game")]
            if self.friends_filter_online
            else friends
        )
        if not filtered:
            tk.Label(
                self.friends_inner,
                text=empty_msg,
                font=("Segoe UI", 8),
                fg=p["text_muted"],
                bg=p["border_dark"],
                justify="center",
                pady=28,
            ).pack(fill="x")
            return

        for f in filtered:
            is_ig = bool(f.get("in_game"))
            is_on = bool(f.get("online")) or is_ig
            row_bg = p["card_bg"] if is_on else "#4F4B40"
            row = tk.Frame(self.friends_inner, bg=row_bg, padx=8, pady=5)
            row.pack(fill="x", pady=1, padx=2)
            if is_ig:
                name_fg, badge_txt, badge_fg = (
                    p["status_ok"],
                    f"★ {f.get('status', 'In-Game')[:26]}",
                    p["status_ok"],
                )
            elif is_on:
                name_fg, badge_txt, badge_fg = (
                    p["text_primary"],
                    f"● {f.get('status', 'Online')[:26]}",
                    p["status_warn"],
                )
            else:
                name_fg, badge_txt, badge_fg = (
                    p["text_muted"],
                    f"○ {f.get('status', 'Offline')[:26]}",
                    p["text_muted"],
                )

            tk.Label(
                row,
                text=f["name"][:24],
                font=("Segoe UI", 8, "bold"),
                fg=name_fg,
                bg=row_bg,
                anchor="w",
            ).pack(side="left")
            if plat_key in (
                "xbox",
                "discord",
                "riot",
                "ea",
                "ubisoft",
                "gog",
                "battlenet",
            ):
                tk.Button(
                    row,
                    text="✕",
                    command=lambda pk=plat_key, fn=f["name"]: self._remove_friend_action(
                        pk, fn
                    ),
                    font=("Segoe UI", 7, "bold"),
                    bg=row_bg,
                    fg=p["text_muted"],
                    activebackground=p["border_dark"],
                    activeforeground=p["status_err"],
                    relief="flat",
                    cursor="hand2",
                    padx=3,
                    pady=0,
                ).pack(side="right", padx=(4, 0))
            tk.Label(
                row,
                text=badge_txt,
                font=("Segoe UI", 8),
                fg=badge_fg,
                bg=row_bg,
                anchor="e",
            ).pack(side="right")

    def _render_friends_list(self):
        p = self.PAL
        for child in self.friends_inner.winfo_children():
            child.destroy()

        plat = self.friends_platform

        if plat == "epic":
            if not self.state.epic_ok and not self.state.friends_list:
                tk.Label(
                    self.friends_inner,
                    text="Link your Epic Games account in the ACCOUNTS tab (or add an Epic friend below)\nto view your Epic Games & Fortnite Friendlist and Lang!ley Squad members.",
                    font=("Segoe UI", 8),
                    fg=p["text_muted"],
                    bg=p["border_dark"],
                    justify="center",
                    pady=35,
                ).pack(fill="x")
                self.lbl_friends_hdr.config(text="EPIC FRIENDS (NOT LINKED)")
            else:
                friends = self.state.friends_list
                if self.friends_filter_online:
                    friends = [f for f in friends if f["in_party"] or f["online"]]
                in_party_cnt = sum(
                    1 for f in self.state.friends_list if f["in_party"]
                )
                online_cnt = sum(
                    1
                    for f in self.state.friends_list
                    if f["in_party"] or f["online"]
                )
                self.lbl_friends_hdr.config(
                    text=f"EPIC  •  PARTY: {in_party_cnt}  •  ONLINE: {online_cnt}  •  TOTAL: {len(self.state.friends_list)}"
                )
                if not friends:
                    tk.Label(
                        self.friends_inner,
                        text="No Epic friends match the current filter.",
                        font=("Segoe UI", 8),
                        fg=p["text_muted"],
                        bg=p["border_dark"],
                        pady=30,
                    ).pack(fill="x")
                else:
                    for f in friends:
                        row_bg = (
                            p["card_bg"]
                            if (f["in_party"] or f["online"])
                            else "#4F4B40"
                        )
                        row = tk.Frame(
                            self.friends_inner, bg=row_bg, padx=8, pady=5
                        )
                        row.pack(fill="x", pady=1, padx=2)
                        if f["in_party"] and f["is_langley"]:
                            name_fg, badge_txt, badge_fg = (
                                p["status_ok"],
                                "★ LANG!LEY SQUAD",
                                p["status_ok"],
                            )
                        elif f["in_party"]:
                            name_fg, badge_txt, badge_fg = (
                                p["status_warn"],
                                "● IN PARTY",
                                p["status_warn"],
                            )
                        elif f["online"]:
                            name_fg, badge_txt, badge_fg = (
                                p["text_primary"],
                                f"● {f['status']}",
                                p["status_ok"],
                            )
                        else:
                            name_fg, badge_txt, badge_fg = (
                                p["text_muted"],
                                f"○ {f['status']}",
                                p["text_muted"],
                            )
                        tk.Label(
                            row,
                            text=f["name"][:26],
                            font=("Segoe UI", 8, "bold"),
                            fg=name_fg,
                            bg=row_bg,
                            anchor="w",
                        ).pack(side="left")
                        if f.get("tracked"):
                            tk.Button(
                                row,
                                text="✕",
                                command=lambda fn=f["name"]: self._remove_friend_action(
                                    "epic", fn
                                ),
                                font=("Segoe UI", 7, "bold"),
                                bg=row_bg,
                                fg=p["text_muted"],
                                activebackground=p["border_dark"],
                                activeforeground=p["status_err"],
                                relief="flat",
                                cursor="hand2",
                                padx=3,
                                pady=0,
                            ).pack(side="right", padx=(4, 0))
                        tk.Label(
                            row,
                            text=badge_txt,
                            font=(
                                "Segoe UI",
                                8,
                                "bold" if f["in_party"] else "normal",
                            ),
                            fg=badge_fg,
                            bg=row_bg,
                            anchor="e",
                        ).pack(side="right")

        elif plat == "steam":
            sfriends = self.state.steam_friends
            online_cnt = sum(
                1 for f in sfriends if f.get("online") or f.get("in_game")
            )
            self.lbl_friends_hdr.config(
                text=f"STEAM  •  ONLINE / IN-GAME: {online_cnt}  •  TOTAL: {len(sfriends)}"
            )
            self._render_generic_friends_rows(
                sfriends,
                "steam",
                "No Steam friends found (or current filter hides offline friends).\nCheck the ACCOUNTS tab to verify your Steam connection.",
            )

        elif plat == "roblox":
            rfriends = self.state.roblox_friends
            online_cnt = sum(1 for f in rfriends if f.get("online"))
            self.lbl_friends_hdr.config(
                text=f"ROBLOX  •  ONLINE: {online_cnt}  •  TOTAL: {len(rfriends)}"
            )
            if not self.state.roblox_user_id:
                tk.Label(
                    self.friends_inner,
                    text="Link your Roblox Username in the ACCOUNTS tab\nto view your Roblox Friends and online status.",
                    font=("Segoe UI", 8),
                    fg=p["text_muted"],
                    bg=p["border_dark"],
                    justify="center",
                    pady=35,
                ).pack(fill="x")
            else:
                self._render_generic_friends_rows(
                    rfriends,
                    "roblox",
                    "No Roblox friends match the current filter.",
                )

        elif plat == "xbox":
            gt = self.state.xbox_gamertag or "Auto-Detecting"
            xfriends = self.state.xbox_friends
            online_cnt = sum(
                1 for f in xfriends if f.get("online") or f.get("in_game")
            )
            self.lbl_friends_hdr.config(
                text=f"XBOX LIVE ({gt})  •  ACTIVE: {online_cnt}  •  FRIENDS: {len(xfriends)}"
            )
            self._render_generic_friends_rows(
                xfriends,
                "xbox",
                f"Xbox Live Gamertag: {gt}\n\nNo Xbox Live friends cached yet. Add a friend's Gamertag below\nor join an Xbox party to see live Xbox friend statuses here.",
            )

        elif plat == "discord":
            d_user = (
                self.state.discord_display_name
                or self.state.discord_username
                or ("Connected" if self.state.discord_ok else "Not Connected")
            )
            u_tag = (
                f"@{self.state.discord_username}"
                if self.state.discord_username
                else d_user
            )
            dfriends = self.state.discord_friends
            self.lbl_friends_hdr.config(
                text=f"DISCORD ({u_tag})  •  ACTIVE PEERS & FRIENDS: {len(dfriends)}"
            )

            me_row = tk.Frame(
                self.friends_inner, bg=p["card_bg"], padx=8, pady=5
            )
            me_row.pack(fill="x", pady=(2, 3), padx=2)
            st_col = p["status_ok"] if self.state.discord_ok else p["status_warn"]
            tk.Label(
                me_row,
                text=f"★ You ({d_user[:18]})",
                font=("Segoe UI", 8, "bold"),
                fg=st_col,
                bg=p["card_bg"],
                anchor="w",
            ).pack(side="left")
            tk.Label(
                me_row,
                text=f"Broadcasting: {self.state.rpc_headline[:24]}",
                font=("Segoe UI", 7, "bold"),
                fg=p["text_primary"],
                bg=p["card_bg"],
                anchor="e",
            ).pack(side="right")

            self._render_generic_friends_rows(
                dfriends,
                "discord",
                "Connected to local Discord RPC.\nActive Lang!ley Squad members and pinned Discord friends appear here.\nUse the box below to pin Discord friends.",
            )

        elif plat == "riot":
            rf = self.state.riot_friends
            on_cnt = sum(1 for f in rf if f.get("online") or f.get("in_game"))
            self.lbl_friends_hdr.config(
                text=f"RIOT GAMES  •  ONLINE / IN-MATCH: {on_cnt}  •  TOTAL: {len(rf)}"
            )
            self._render_generic_friends_rows(
                rf,
                "riot",
                "No Riot friends detected yet.\nOpen Riot Client, VALORANT, or League of Legends to auto-sync your\nRiot friends list via local Riot Client API, or add a Riot ID (Name#TAG) below.",
            )

        elif plat == "ea":
            ef = self.state.ea_friends
            self.lbl_friends_hdr.config(
                text=f"EA APP  •  FRIENDS & TRACKED EA IDS: {len(ef)}"
            )
            self._render_generic_friends_rows(
                ef,
                "ea",
                "No local EA App friends cached yet.\nLaunch EA App or add a friend's EA ID below to track them here.",
            )

        elif plat == "ubisoft":
            uf = self.state.ubisoft_friends
            self.lbl_friends_hdr.config(
                text=f"UBISOFT CONNECT  •  FRIENDS & PROFILES: {len(uf)}"
            )
            self._render_generic_friends_rows(
                uf,
                "ubisoft",
                "No local Ubisoft Connect friends cached yet.\nLaunch Ubisoft Connect or add a friend's Ubisoft username below.",
            )

        elif plat == "gog":
            gf = self.state.gog_friends
            self.lbl_friends_hdr.config(
                text=f"GOG GALAXY  •  FRIENDS & PROFILES: {len(gf)}"
            )
            self._render_generic_friends_rows(
                gf,
                "gog",
                "No local GOG Galaxy friends found yet.\nLaunch GOG Galaxy or add a friend's GOG username below.",
            )

        elif plat == "battlenet":
            bf = self.state.battlenet_friends
            on_cnt = sum(1 for f in bf if f.get("online") or f.get("in_game"))
            self.lbl_friends_hdr.config(
                text=f"BATTLE.NET  •  ACTIVE: {on_cnt}  •  FRIENDS & BATTLETAGS: {len(bf)}"
            )
            self._render_generic_friends_rows(
                bf,
                "battlenet",
                "No local Battle.net friends or BattleTags found yet.\nLaunch Battle.net or add a friend's BattleTag (Name#1234) below.",
            )

        self.friends_inner.update_idletasks()
        self.friends_canvas.config(scrollregion=self.friends_canvas.bbox("all"))

    def _row(self, parent, title, val, r):
        p = self.PAL
        tk.Label(
            parent,
            text=title,
            font=("Segoe UI", 8),
            fg=p["text_muted"],
            bg=p["card_bg"],
            anchor="w",
        ).grid(row=r, column=0, sticky="w", pady=0)
        lbl = tk.Label(
            parent,
            text=val,
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["card_bg"],
            anchor="e",
        )
        lbl.grid(row=r, column=1, sticky="e", pady=0)
        parent.grid_columnconfigure(1, weight=1)
        return lbl

    def _epic_action(self):
        self.state.auth_pending["epic"] = True
        self.lbl_acc_epic_status.config(
            text="⏳ Waiting for Browser Login...",
            fg=self.PAL["status_warn"],
        )
        self.btn_acc_epic.config(
            text="🌐 Opening Browser... Complete Login",
            fg=self.PAL["status_warn"],
        )

        def _done():
            self.state.auth_pending["epic"] = False
            self.engine.sync_rpc(force=True)

        self.engine.epic.login(done_cb=_done)

    def _save_cfg(self):
        Reg.update_startup(self.v_auto.get(), self.v_mini.get())
        self.refresh_ui()

    def _pause_action(self):
        self.state.active = not self.state.active
        if self.state.active:
            self.btn_pause.config(text="Pause RPC")
            threading.Thread(
                target=lambda: self.engine.sync_rpc(force=True), daemon=True
            ).start()
        else:
            self.btn_pause.config(text="Resume RPC")
            threading.Thread(target=self.engine.clear_rpc, daemon=True).start()
        self.refresh_ui()

    def refresh_ui(self):
        p, s = self.PAL, self.state
        if s.update_available:
            self.btn_hdr_update.config(text="⚡ Update")
            self.btn_hdr_update.pack(side="right", padx=(0, 8))
        else:
            self.btn_hdr_update.pack_forget()

        prio_key = (
            s.platform_priority
            if s.platform_priority in self.PRIORITY_ORDER
            else "auto"
        )
        self.btn_priority.config(text=f"Priority: {prio_key.upper()}")
        self.lbl_rpc_headline.config(text=s.rpc_headline[:48])
        self.lbl_rpc_details.config(text=s.rpc_details[:56])
        self.lbl_rpc_state.config(text=s.rpc_state[:56])
        self._request_thumbnail(s.rpc_image_url)

        if hasattr(self, "lbl_set_auto_status"):
            auto_on = bool(self.v_auto.get())
            self.lbl_set_auto_status.config(
                text="● On" if auto_on else "○ Off",
                fg=p["status_ok"] if auto_on else p["text_muted"],
            )
        if hasattr(self, "lbl_set_mini_status"):
            mini_on = bool(self.v_mini.get())
            self.lbl_set_mini_status.config(
                text="● On" if mini_on else "○ Off",
                fg=p["status_ok"] if mini_on else p["text_muted"],
            )
        if hasattr(self, "lbl_set_media_status"):
            med_on = bool(s.show_media_rpc)
            self.lbl_set_media_status.config(
                text="● On" if med_on else "○ Off",
                fg=p["status_ok"] if med_on else p["text_muted"],
            )
        if hasattr(self, "lbl_set_prio_mode"):
            if prio_key == "auto":
                self.lbl_set_prio_mode.config(
                    text="● AUTO (Smart Detection)", fg=p["status_ok"]
                )
            else:
                self.lbl_set_prio_mode.config(
                    text=f"★ OVERRIDE ({prio_key.upper()})", fg=p["status_warn"]
                )
        if hasattr(self, "prio_mode_btns"):
            for pk, pb in self.prio_mode_btns.items():
                pb.config(
                    bg=p["card_bg"] if pk == prio_key else p["panel_bg"],
                    fg=p["status_ok"] if pk == prio_key else p["text_muted"],
                )

        if hasattr(self, "lbl_acc_status"):
            for plat_k in (
                "epic",
                "steam",
                "riot",
                "battlenet",
                "ea",
                "ubisoft",
                "gog",
                "xbox",
                "roblox",
                "minecraft",
            ):
                lbl_st = self.lbl_acc_status.get(plat_k)
                if not lbl_st:
                    continue
                if s.auth_pending.get(plat_k):
                    lbl_st.config(
                        text="⏳ Waiting for Browser Login...", fg=p["status_warn"]
                    )
                else:
                    summary = s.platform_account_summary(plat_k)
                    if summary:
                        lbl_st.config(
                            text=f"✓ Linked: {summary[:28]}", fg=p["status_ok"]
                        )
                    else:
                        lbl_st.config(text="Not Linked", fg=p["text_muted"])

            for gdef in GACHA_SUB_GAME_DEFS:
                gkey = gdef["key"]
                plat_k = f"gacha_{gkey}"
                lbl_gst = self.lbl_acc_status.get(plat_k)
                if not lbl_gst:
                    continue
                if s.auth_pending.get(plat_k) or s.auth_pending.get("gacha"):
                    lbl_gst.config(
                        text="⏳ Waiting for Browser Login...", fg=p["status_warn"]
                    )
                else:
                    gsummary = s.gacha_game_summary(gkey)
                    if gsummary:
                        lbl_gst.config(
                            text=f"✓ Linked: {gsummary[:34]}", fg=p["status_ok"]
                        )
                    else:
                        prof = s.gacha_profiles.get(gkey, {})
                        installed_names = {
                            g.get("name", "").lower()
                            for g in (s.gacha_installed_games or [])
                        }
                        is_inst = gdef["name"].lower() in installed_names
                        if prof.get("unlinked") or not is_inst:
                            lbl_gst.config(text="Not Linked", fg=p["text_muted"])
                        else:
                            lbl_gst.config(
                                text="● Auto-Detect Ready", fg=p["status_warn"]
                            )

        if hasattr(self, "btn_acc_epic"):
            if s.auth_pending.get("epic"):
                self.btn_acc_epic.config(
                    text="🌐 Opening Browser... Complete Login", fg=p["status_warn"]
                )
            elif s.epic_ok:
                self.btn_acc_epic.config(
                    text=f"🌐 Re-Link Epic ({s.epic_name[:18]})", fg=p["status_ok"]
                )
            else:
                self.btn_acc_epic.config(
                    text="🌐 Login via Browser (Epic OAuth)", fg=p["status_ok"]
                )

        if hasattr(self, "ent_acc_input"):
            val_map = {
                "epic": self.state.epic_name,
                "steam": s.steam_id64,
                "battlenet": s.battlenet_battletag,
                "riot": s.riot_id,
                "roblox": s.roblox_user_name,
                "xbox": s.xbox_gamertag,
                "ea": s.ea_account_name,
                "ubisoft": s.ubisoft_username,
                "gog": s.gog_username,
                "minecraft": s.minecraft_username,
            }
            for gdef in GACHA_SUB_GAME_DEFS:
                gk = gdef["key"]
                gprof = s.gacha_profiles.get(gk) or {}
                val_map[f"gacha_{gk}"] = gprof.get("uid") or gprof.get("account_name") or ""
            try:
                focused = self.focus_get()
            except Exception:
                focused = None
            for pk, cur_val in val_map.items():
                ent = self.ent_acc_input.get(pk)
                if ent and focused != ent and cur_val and not ent.get().strip():
                    ent.insert(0, str(cur_val))

        # Clean top status bar: full Discord username without truncation on left, Universal Priority Guard on right
        if not s.active:
            self.lbl_discord.config(text="● Discord: Paused", fg=p["status_warn"])
        elif s.discord_ok:
            uname = s.discord_username or s.discord_display_name
            u_str = f" — @{uname}" if uname else ""
            self.lbl_discord.config(
                text=f"● Discord: Connected{u_str}", fg=p["status_ok"]
            )
        else:
            self.lbl_discord.config(
                text="● Discord: Disconnected", fg=p["status_err"]
            )

        plat_now = s.active_platform()
        is_game_active = plat_now not in ("paused", "idle")
        if hasattr(self, "lbl_medal_pill"):
            if not s.medal_priority_enabled:
                self.lbl_medal_pill.config(
                    text="○ Priority Guard: Off", fg=p["text_muted"]
                )
            elif s.medal_running or is_game_active:
                self.lbl_medal_pill.config(
                    text="★ Priority Guard: Active", fg=p["status_ok"]
                )
            else:
                self.lbl_medal_pill.config(
                    text="● Priority Guard: Armed", fg=p["status_warn"]
                )

        # Compact status badges in Settings (no installed counts or clipping)
        fn_set_lbl = (
            self.lbl_set_plat_status.get("fortnite")
            if hasattr(self, "lbl_set_plat_status")
            else None
        )
        if not s.fortnite_enabled:
            self.lbl_state.config(text="Disabled", fg=p["text_muted"])
            if fn_set_lbl:
                fn_set_lbl.config(text="○ Off", fg=p["text_muted"])
        elif s.running:
            t = s.timer_str("fortnite")
            self.lbl_state.config(
                text=f"{'In Match' if s.in_match else 'In Lobby'}  •  ⏱ {t}",
                fg=p["status_ok"] if s.in_match else p["status_warn"],
            )
            if fn_set_lbl:
                fn_set_lbl.config(text="★ Active", fg=p["status_ok"])
        elif s.epic_game_running:
            t = s.timer_str("fortnite")
            ename = s.epic_game_name or "Epic Game"
            self.lbl_state.config(
                text=f"{ename[:22]}  •  ⏱ {t}",
                fg=p["status_ok"],
            )
            if fn_set_lbl:
                fn_set_lbl.config(text="★ Active", fg=p["status_ok"])
        else:
            self.lbl_state.config(text="Ready (Epic & Fortnite)", fg=p["text_muted"])
            if fn_set_lbl:
                fn_set_lbl.config(text="● Ready", fg=p["status_warn"])

        if s.peers:
            self.lbl_mode.config(
                text=f"{s.mode} • ★ {', '.join(s.peers[:2])}", fg=p["status_ok"]
            )
        else:
            tag = (
                "Solo"
                if s.party_size <= 1
                else f"Party ({s.party_size}/{s.party_max})"
            )
            self.lbl_mode.config(text=f"{s.mode} • {tag}", fg=p["text_primary"])
        self.lbl_skin.config(text=f"{s.skin_name[:24]} • Lv.{s.season_level}")

        st_set_lbl = (
            self.lbl_set_plat_status.get("steam")
            if hasattr(self, "lbl_set_plat_status")
            else None
        )
        if s.steam_running and s.steam_enabled:
            st_t = s.timer_str("steam")
            self.lbl_steam_dash.config(
                text=f"{s.steam_game_name[:22]} • ⏱ {st_t}", fg=p["status_ok"]
            )
            self.lbl_steam_tab_status.config(
                text=f"● RUNNING: {s.steam_game_name[:22]}", fg=p["status_ok"]
            )
            gsi_extra = (
                f" • {s.steam_gsi_text}"
                if s.steam_gsi_text
                else f" • {s.steam_genre}"
            )
            self.lbl_steam_active_detail.config(
                text=f"Active Game: {s.steam_game_name} (AppID {s.steam_appid}){gsi_extra}",
                fg=p["status_ok"],
            )
            if st_set_lbl:
                st_set_lbl.config(text="★ Active", fg=p["status_ok"])
        else:
            self.lbl_steam_dash.config(
                text="Ready (Waiting for Steam Game)"
                if s.steam_enabled
                else "Disabled",
                fg=p["text_muted"],
            )
            self.lbl_steam_tab_status.config(
                text="● STEAM STANDBY", fg=p["status_warn"]
            )
            self.lbl_steam_active_detail.config(
                text="Active Game: None — Launch any game below or from your desktop",
                fg=p["text_muted"],
            )
        if hasattr(self, "lbl_steam_gsi_status"):
            cfg_games = list(getattr(s, "steam_gsi_configured_games", []) or [])
            if cfg_games:
                self.lbl_steam_gsi_status.config(
                    text=f"Live Match Stats: Auto-Applied ✓ ({', '.join(cfg_games)}) • Port {GSI_PORT}",
                    fg=p["status_ok"],
                )
            else:
                self.lbl_steam_gsi_status.config(
                    text=f"Live Match Stats (CS2 / Dota 2): Auto-Apply Ready • Port {GSI_PORT}",
                    fg=p["text_muted"],
                )
        if hasattr(self, "btn_install_gsi"):
            cfg_games = list(getattr(s, "steam_gsi_configured_games", []) or [])
            if cfg_games:
                self.btn_install_gsi.config(
                    text=f"✓ Auto: {', '.join(cfg_games)}", fg=p["status_ok"]
                )
            if st_set_lbl:
                st_set_lbl.config(
                    text="● Ready" if s.steam_enabled else "○ Off",
                    fg=p["status_warn"] if s.steam_enabled else p["text_muted"],
                )

        if s.steam_user_name:
            self.lbl_steam_profile.config(
                text=f"Steam Account: {s.steam_user_name}  •  SteamID64: {s.steam_id64 or 'Local'}",
                fg=p["status_ok"],
            )
        else:
            self.lbl_steam_profile.config(
                text="Steam Account: Ready (Local Registry Mode)",
                fg=p["text_primary"],
            )

        rb_set_lbl = (
            self.lbl_set_plat_status.get("roblox")
            if hasattr(self, "lbl_set_plat_status")
            else None
        )
        if s.roblox_running and s.roblox_enabled:
            rb_t = s.timer_str("roblox")
            rname = s.roblox_game_name or "Roblox"
            self.lbl_roblox_dash.config(
                text=f"{rname[:22]} • ⏱ {rb_t}", fg=p["status_ok"]
            )
            if rb_set_lbl:
                rb_set_lbl.config(text="★ Active", fg=p["status_ok"])
        else:
            self.lbl_roblox_dash.config(
                text="Ready (Waiting for Roblox)"
                if s.roblox_enabled
                else "Disabled",
                fg=p["text_muted"],
            )
            if rb_set_lbl:
                rb_set_lbl.config(
                    text="● Ready" if s.roblox_enabled else "○ Off",
                    fg=p["status_warn"] if s.roblox_enabled else p["text_muted"],
                )

        xb_set_lbl = (
            self.lbl_set_plat_status.get("xbox")
            if hasattr(self, "lbl_set_plat_status")
            else None
        )
        if s.xbox_running and s.xbox_enabled:
            xb_t = s.timer_str("xbox")
            xname = s.xbox_game_name or "Xbox Game"
            self.lbl_xbox_dash.config(
                text=f"{xname[:22]} • ⏱ {xb_t}", fg=p["status_ok"]
            )
            if xb_set_lbl:
                xb_set_lbl.config(text="★ Active", fg=p["status_ok"])
        else:
            self.lbl_xbox_dash.config(
                text="Ready (Waiting for Xbox Game)"
                if s.xbox_enabled
                else "Disabled",
                fg=p["text_muted"],
            )
            if xb_set_lbl:
                xb_set_lbl.config(
                    text="● Ready" if s.xbox_enabled else "○ Off",
                    fg=p["status_warn"] if s.xbox_enabled else p["text_muted"],
                )

        gacha_set_lbl = (
            self.lbl_set_plat_status.get("gacha")
            if hasattr(self, "lbl_set_plat_status")
            else None
        )
        enabled_gacha_sub_cnt = sum(
            1
            for gdef in GACHA_SUB_GAME_DEFS
            if s.gacha_enabled and s.gacha_sub_enabled.get(gdef["key"], True)
        )
        if gacha_set_lbl:
            if not s.gacha_enabled or enabled_gacha_sub_cnt == 0:
                gacha_set_lbl.config(text="○ Off", fg=p["text_muted"])
            elif s.gacha_running:
                gacha_set_lbl.config(text="★ Active", fg=p["status_ok"])
            else:
                gacha_set_lbl.config(text="● Ready", fg=p["status_warn"])

        if hasattr(self, "lbl_gacha_master_badge"):
            if not s.gacha_enabled:
                self.lbl_gacha_master_badge.config(text="○ Off", fg=p["text_muted"])
            elif s.gacha_running:
                self.lbl_gacha_master_badge.config(text="★ Active", fg=p["status_ok"])
            else:
                self.lbl_gacha_master_badge.config(text="● Ready", fg=p["status_warn"])

        if hasattr(self, "lbl_set_gacha_count"):
            self.lbl_set_gacha_count.config(
                text=f"{enabled_gacha_sub_cnt} / {len(GACHA_SUB_GAME_DEFS)} Enabled",
                fg=p["status_ok"] if enabled_gacha_sub_cnt > 0 else p["status_err"],
            )

        if hasattr(self, "lbl_gacha_rows"):
            for gdef in GACHA_SUB_GAME_DEFS:
                gkey = gdef["key"]
                grow_lbl = self.lbl_gacha_rows.get(gkey)
                if not grow_lbl:
                    continue
                gflag = bool(s.gacha_sub_enabled.get(gkey, True))
                if not s.gacha_enabled or not gflag:
                    grow_lbl.config(text="○ Off", fg=p["text_muted"])
                elif s.gacha_running and s.gacha_game_key == gkey:
                    grow_lbl.config(text="★ Active", fg=p["status_ok"])
                else:
                    grow_lbl.config(text="● Ready", fg=p["status_warn"])

        custom_set_lbl = (
            self.lbl_set_plat_status.get("custom_apps")
            if hasattr(self, "lbl_set_plat_status")
            else None
        )
        if custom_set_lbl:
            if not s.custom_apps_enabled:
                custom_set_lbl.config(text="○ Off", fg=p["text_muted"])
            elif s.custom_app_running:
                custom_set_lbl.config(text="★ Active", fg=p["status_ok"])
            else:
                custom_set_lbl.config(text="● Ready", fg=p["status_warn"])

        active_launcher_txt = ""
        launcher_meta = [
            ("gacha", "Gacha", s.gacha_enabled, s.gacha_running, s.gacha_game_name),
            ("riot", "Riot", s.riot_enabled, s.riot_running, s.riot_game_name),
            ("ea", "EA", s.ea_enabled, s.ea_running, s.ea_game_name),
            ("ubisoft", "Ubi", s.ubisoft_enabled, s.ubisoft_running, s.ubisoft_game_name),
            ("gog", "GOG", s.gog_enabled, s.gog_running, s.gog_game_name),
            ("battlenet", "B.net", s.battlenet_enabled, s.battlenet_running, s.battlenet_game_name),
            ("custom_apps", "Custom", s.custom_apps_enabled, s.custom_app_running, s.custom_app_name),
        ]
        enabled_launchers_cnt = sum(1 for _, _, en, _, _ in launcher_meta if en)
        for lkey, lshort, lenabled, lrunning, lgname in launcher_meta:
            row_lbl = self.lbl_launcher_rows.get(lkey)
            if not lenabled:
                if row_lbl:
                    row_lbl.config(text="○ Off", fg=p["text_muted"])
            elif lrunning:
                lt = s.timer_str(lkey)
                if not active_launcher_txt:
                    if lkey == "gacha":
                        active_launcher_txt = self._gacha_dash_text(lgname, lt)
                    else:
                        active_launcher_txt = f"{lshort}: {lgname[:18]} • ⏱ {lt}"
                if row_lbl:
                    row_lbl.config(text="★ Active", fg=p["status_ok"])
            else:
                if row_lbl:
                    row_lbl.config(text="● Ready", fg=p["status_warn"])

        if active_launcher_txt:
            self.lbl_launchers_dash.config(
                text=active_launcher_txt, fg=p["status_ok"]
            )
        elif enabled_launchers_cnt > 0:
            self.lbl_launchers_dash.config(
                text=f"Ready ({enabled_launchers_cnt}/7 Networks Enabled)",
                fg=p["text_muted"],
            )
        else:
            self.lbl_launchers_dash.config(
                text="All Disabled", fg=p["text_muted"]
            )

        mc_client_flags = [
            ("lunar", s.mc_lunar_enabled),
            ("badlion", s.mc_badlion_enabled),
            ("feather", s.mc_feather_enabled),
            ("labymod", s.mc_labymod_enabled),
            ("prism_vanilla", s.mc_prism_vanilla_enabled),
        ]
        enabled_mc_cnt = sum(
            1 for _, flag in mc_client_flags if flag and s.minecraft_enabled
        )
        for mkey, mflag in mc_client_flags:
            mrow_lbl = self.lbl_mc_rows.get(mkey)
            if not mrow_lbl:
                continue
            if not s.minecraft_enabled or not mflag:
                mrow_lbl.config(text="○ Off", fg=p["text_muted"])
            elif s.minecraft_running and s.minecraft_client_key == mkey:
                mrow_lbl.config(text="★ Active", fg=p["status_ok"])
            else:
                mrow_lbl.config(text="● Ready", fg=p["status_warn"])

        mc_set_lbl = (
            self.lbl_set_plat_status.get("minecraft")
            if hasattr(self, "lbl_set_plat_status")
            else None
        )
        if s.minecraft_enabled and s.minecraft_running:
            mc_t = s.timer_str("minecraft")
            cname = s.minecraft_client_name or "Minecraft"
            ver_s = f" {s.minecraft_version}" if s.minecraft_version else ""
            self.lbl_mc_dash.config(
                text=f"{(cname + ver_s)[:22]} • ⏱ {mc_t}", fg=p["status_ok"]
            )
            if mc_set_lbl:
                mc_set_lbl.config(text="★ Active", fg=p["status_ok"])
        elif s.minecraft_enabled and enabled_mc_cnt > 0:
            self.lbl_mc_dash.config(
                text=f"Ready ({enabled_mc_cnt}/5 MC Clients Enabled)",
                fg=p["text_muted"],
            )
            if mc_set_lbl:
                mc_set_lbl.config(text="● Ready", fg=p["status_warn"])
        else:
            self.lbl_mc_dash.config(text="Disabled", fg=p["text_muted"])
            if mc_set_lbl:
                mc_set_lbl.config(text="○ Off", fg=p["text_muted"])

        enabled_total_cnt = sum(
            1
            for flag in (
                s.fortnite_enabled,
                s.minecraft_enabled,
                s.gacha_enabled,
                s.riot_enabled,
                s.ea_enabled,
                s.ubisoft_enabled,
                s.gog_enabled,
                s.battlenet_enabled,
                s.steam_enabled,
                s.roblox_enabled,
                s.xbox_enabled,
                s.custom_apps_enabled,
            )
            if flag
        )
        if hasattr(self, "lbl_set_rpc_count"):
            self.lbl_set_rpc_count.config(
                text=f"{enabled_total_cnt} / 12 Enabled",
                fg=p["status_ok"] if enabled_total_cnt > 0 else p["status_err"],
            )
        if hasattr(self, "lbl_dash_cfg_summary"):
            guard_tag = "ON" if s.medal_priority_enabled else "OFF"
            self.lbl_dash_cfg_summary.config(
                text=f"{enabled_total_cnt}/12 RPCs On  •  Priority: {prio_key.upper()}  •  Priority Guard: {guard_tag}",
                fg=p["status_ok"] if enabled_total_cnt > 0 else p["status_warn"],
            )

        if not s.medal_priority_enabled:
            self.lbl_medal_dash.config(
                text="Disabled (Standard RPC Mode)", fg=p["text_muted"]
            )
            self.lbl_medal_detail.config(
                text="Priority Guard is off — other games or overlays may share your Discord status.",
                fg=p["text_muted"],
            )
        elif s.medal_running or is_game_active:
            if s.medal_running:
                enc_tag = (
                    "Clip Recorder Active"
                    if s.medal_encoder_active
                    else "Overlay Detected"
                )
            else:
                enc_tag = "Top Slot Locked"
            self.lbl_medal_dash.config(
                text=f"★ Locked #1 ({s.medal_reassertions} Locks)",
                fg=p["status_ok"],
            )
            self.lbl_medal_detail.config(
                text=f"Universal Priority Active ({enc_tag}) • Lang!ley is locked above all games & Medal ({s.medal_reassertions} locks)",
                fg=p["status_ok"],
            )
        else:
            self.lbl_medal_dash.config(
                text="✓ Armed (Above All Games & Medal)", fg=p["status_warn"]
            )
            self.lbl_medal_detail.config(
                text="Locks Lang!ley at #1 priority on Discord above native game statuses, Medal.tv, Overwolf, GeForce & Game Bar.",
                fg=p["text_muted"],
            )

        if s.media_title:
            m_str = s.media_str()
            state_ico = "▶" if s.media_playing else "⏸"
            self.lbl_dash_music.config(
                text=f"{state_ico} {m_str[:28]}{'...' if len(m_str) > 28 else ''}",
                fg=p["status_ok"] if s.media_playing else p["status_warn"],
            )
            self.lbl_media_app.config(text=f"SOURCE: {s.media_app.upper()}")
            self.lbl_media_title.config(text=s.media_title[:40])
            self.lbl_media_artist.config(
                text=s.media_artist[:44] if s.media_artist else "Unknown Artist"
            )
            self.lbl_media_badge.config(
                text="● PLAYING" if s.media_playing else "● PAUSED",
                fg=p["status_ok"] if s.media_playing else p["status_warn"],
            )
        else:
            self.lbl_dash_music.config(
                text="No Media Playing", fg=p["text_muted"]
            )
            self.lbl_media_app.config(text="SOURCE: NO MEDIA DETECTED")
            self.lbl_media_title.config(
                text="Play a song on Spotify, YT Music or Amazon Music"
            )
            self.lbl_media_artist.config(text="—")
            self.lbl_media_badge.config(text="● IDLE", fg=p["text_muted"])

        self._update_media_progress()

        if self.current_tab == "gamehub" and self.gamehub_subtab == "library":
            self._render_steam_games()
        elif self.current_tab == "friends":
            self._render_friends_list()
