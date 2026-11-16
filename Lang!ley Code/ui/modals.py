import os
import tkinter as tk
from tkinter import filedialog
from core.config_manager import APP_VERSION, LICENSE_TEXT, CFG


def apply_window_icon(win, parent):
    try:
        ico_path = getattr(parent, "_ico_path", None)
        if ico_path and os.path.exists(ico_path):
            win.iconbitmap(ico_path)
    except Exception:
        pass
    try:
        photos = [
            p
            for p in (
                getattr(parent, "_ico_64", None),
                getattr(parent, "_ico_32", None),
                getattr(parent, "_ico_16", None),
            )
            if p is not None
        ]
        if photos:
            win.wm_iconphoto(False, *photos)
    except Exception:
        pass


class ToolTip:
    def __init__(self, widget, text, pal):
        self.widget = widget
        self.text = text
        self.pal = pal
        self.tip_win = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, _=None):
        if self.tip_win or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 10
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip_win = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_attributes("-topmost", True)
            p = self.pal
            frame = tk.Frame(
                tw,
                bg=p["border_dark"],
                highlightbackground=p["border_light"],
                highlightthickness=1,
                padx=8,
                pady=5,
            )
            frame.pack()
            tk.Label(
                frame,
                text=self.text,
                font=("Segoe UI", 8),
                fg=p["text_primary"],
                bg=p["border_dark"],
                justify="left",
                wraplength=290,
            ).pack()
            tw.update_idletasks()
            scr_w = tw.winfo_screenwidth()
            req_w = tw.winfo_reqwidth()
            if x + req_w + 12 > scr_w:
                x = max(8, scr_w - req_w - 16)
            tw.wm_geometry(f"+{x}+{y}")
        except Exception:
            self._on_leave()

    def _on_leave(self, _=None):
        if self.tip_win:
            try:
                self.tip_win.destroy()
            except Exception:
                pass
            self.tip_win = None


class LicenseModal(tk.Toplevel):
    def __init__(self, parent, pal):
        super().__init__(parent)
        self.parent, self.pal = parent, pal
        self.title("Lang!ley // License")
        self.resizable(False, False)
        self.configure(bg=pal["outer_bg"])
        self.transient(parent)
        apply_window_icon(self, parent)
        self.grab_set()
        self._build()
        self._fit_window()

    def _fit_window(self):
        self.update_idletasks()
        req_h, w = self.wrap.winfo_reqheight() + 24, 430
        self.parent.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - req_h) // 2
        self.geometry(f"{w}x{req_h}+{max(0, x)}+{max(0, y)}")

    def _build(self):
        p = self.pal
        self.wrap = tk.Frame(
            self,
            bg=p["panel_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=16,
            pady=14,
        )
        self.wrap.pack(fill="both", expand=True, padx=10, pady=10)
        hdr = tk.Frame(self.wrap, bg=p["border_dark"], padx=10, pady=6)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(
            hdr,
            text="LICENSE & DISCLAIMER",
            font=("Segoe UI", 9, "bold"),
            fg=p["status_warn"],
            bg=p["border_dark"],
        ).pack(side="left")
        tk.Label(
            hdr,
            text=f"v{APP_VERSION}",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_muted"],
            bg=p["border_dark"],
        ).pack(side="right")
        box = tk.Frame(
            self.wrap,
            bg=p["card_bg"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        box.pack(fill="x", pady=(0, 12))
        tk.Label(
            box,
            text=LICENSE_TEXT,
            font=("Segoe UI", 8),
            fg=p["text_primary"],
            bg=p["card_bg"],
            justify="left",
            anchor="nw",
            wraplength=350,
        ).pack(fill="x")
        bar = tk.Frame(self.wrap, bg=p["panel_bg"])
        bar.pack(fill="x", side="bottom")
        tk.Button(
            bar,
            text="Close",
            command=self.destroy,
            font=("Segoe UI", 9, "bold"),
            bg=p["border_dark"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=5,
        ).pack(fill="x")


class UpdatePromptModal(tk.Toplevel):
    def __init__(self, parent, pal, state, updater, on_shutdown):
        super().__init__(parent)
        self.parent, self.pal, self.state, self.updater, self.on_shutdown = (
            parent,
            pal,
            state,
            updater,
            on_shutdown,
        )
        self.title("Lang!ley // Update Available")
        self.resizable(False, False)
        self.configure(bg=pal["outer_bg"])
        self.transient(parent)
        apply_window_icon(self, parent)
        self.grab_set()
        self._build()
        self._fit_window()

    def _fit_window(self):
        self.update_idletasks()
        req_h, w = self.wrap.winfo_reqheight() + 24, 430
        self.parent.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - req_h) // 2
        self.geometry(f"{w}x{req_h}+{max(0, x)}+{max(0, y)}")

    def _build(self):
        p = self.pal
        self.wrap = tk.Frame(
            self,
            bg=p["panel_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=16,
            pady=14,
        )
        self.wrap.pack(fill="both", expand=True, padx=10, pady=10)
        hdr = tk.Frame(self.wrap, bg=p["border_dark"], padx=10, pady=6)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(
            hdr,
            text="⚡ UPDATE AVAILABLE",
            font=("Segoe UI", 9, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        ).pack(side="left")
        msg = "A new version of Lang!ley is ready.\nWould you like to download and install the update now?"
        tk.Label(
            self.wrap,
            text=msg,
            font=("Segoe UI", 9),
            fg=p["text_primary"],
            bg=p["panel_bg"],
            justify="left",
            anchor="nw",
            wraplength=370,
        ).pack(fill="x", pady=(0, 10))
        notes_box = tk.Frame(
            self.wrap,
            bg=p["card_bg"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        notes_box.pack(fill="x", pady=(0, 12))
        tk.Label(
            notes_box,
            text="WHAT'S NEW / CHANGELOG:",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_warn"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            notes_box,
            text=self.state.update_changelog,
            font=("Segoe UI", 8),
            fg=p["text_primary"],
            bg=p["card_bg"],
            justify="left",
            anchor="nw",
            wraplength=345,
        ).pack(fill="x")
        self.prog_frame = tk.Frame(self.wrap, bg=p["panel_bg"])
        self.lbl_prog = tk.Label(
            self.prog_frame,
            text="Preparing download...",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_ok"],
            bg=p["panel_bg"],
            anchor="w",
        )
        self.lbl_prog.pack(fill="x", pady=(0, 4))
        self.prog_cv = tk.Canvas(
            self.prog_frame, height=10, bg=p["border_dark"], highlightthickness=0
        )
        self.prog_cv.pack(fill="x", pady=(0, 10))
        self.bar = tk.Frame(self.wrap, bg=p["panel_bg"])
        self.bar.pack(fill="x", side="bottom")
        self.btn_install = tk.Button(
            self.bar,
            text="Install Update Now",
            command=self._start_install,
            font=("Segoe UI", 9, "bold"),
            bg=p["border_dark"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=6,
        )
        self.btn_install.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_later = tk.Button(
            self.bar,
            text="Later (Skip)",
            command=self.destroy,
            font=("Segoe UI", 9, "bold"),
            bg=p["card_bg"],
            fg=p["text_muted"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=6,
        )
        self.btn_later.pack(side="right", expand=True, fill="x", padx=(4, 0))

    def _start_install(self):
        self.btn_install.config(state="disabled", text="Downloading...")
        self.btn_later.config(state="disabled")
        self.prog_frame.pack(fill="x", before=self.bar)
        self._fit_window()
        self.updater.download_and_install(
            on_progress=lambda pct, txt: self.after(
                0, lambda: self._update_prog(pct, txt)
            ),
            on_error=lambda err: self.after(0, lambda: self._on_err(err)),
            on_shutdown=lambda: self.after(0, self.on_shutdown),
        )

    def _update_prog(self, pct, txt):
        if not self.winfo_exists():
            return
        self.lbl_prog.config(text=txt, fg=self.pal["status_ok"])
        self.prog_cv.delete("all")
        w = max(10, self.prog_cv.winfo_width())
        fill_w = int(w * min(1.0, max(0.0, pct / 100.0)))
        self.prog_cv.create_rectangle(
            0, 0, fill_w, 10, fill=self.pal["status_ok"], outline=""
        )

    def _on_err(self, err):
        if not self.winfo_exists():
            return
        self.lbl_prog.config(
            text=f"Update failed: {err[:45]}", fg=self.pal["status_err"]
        )
        self.btn_install.config(state="normal", text="Retry Update")
        self.btn_later.config(state="normal")


class PatchNotesModal(tk.Toplevel):
    def __init__(self, parent, pal):
        super().__init__(parent)
        self.parent = parent
        self.pal = pal
        self.title(f"Lang!ley // Patch Notes (v{APP_VERSION})")
        self.geometry("460x450")
        self.resizable(False, False)
        self.configure(bg=pal["outer_bg"])
        self.transient(parent)
        apply_window_icon(self, parent)
        self.grab_set()
        self._build()
        self._center_window(460, 450)

    def _center_window(self, w, h):
        self.update_idletasks()
        self.parent.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _build(self):
        p = self.pal
        self.wrap = tk.Frame(
            self,
            bg=p["panel_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=14,
            pady=12,
        )
        self.wrap.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = tk.Frame(self.wrap, bg=p["border_dark"], padx=10, pady=6)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(
            hdr,
            text="📋 PATCH NOTES & CHANGELOG",
            font=("Segoe UI", 9, "bold"),
            fg=p["status_warn"],
            bg=p["border_dark"],
        ).pack(side="left")
        tk.Label(
            hdr,
            text=f"Current: v{APP_VERSION}",
            font=("Segoe UI", 8, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        ).pack(side="right")

        list_wrap = tk.Frame(
            self.wrap,
            bg=p["border_dark"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
        )
        list_wrap.pack(fill="both", expand=True, pady=(0, 10))

        self.canvas = tk.Canvas(list_wrap, bg=p["border_dark"], highlightthickness=0)
        sb = tk.Scrollbar(list_wrap, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=p["border_dark"], padx=8, pady=8)
        self.inner.bind(
            "<Configure>",
            lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_win = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw", width=392
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_win, width=e.width),
        )
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        data = CFG.get_patch_notes()
        releases = data.get("releases", []) if isinstance(data, dict) else []
        for idx, rel in enumerate(releases):
            ver = rel.get("version", "1.0.0")
            date_str = rel.get("date", "")
            title = rel.get("title", "")
            highlights = rel.get("highlights", [])
            is_latest = idx == 0

            card = tk.Frame(
                self.inner,
                bg=p["card_bg"],
                highlightbackground=p["status_ok"] if is_latest else p["border_light"],
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            card.pack(fill="x", pady=(0, 6))

            top = tk.Frame(card, bg=p["card_bg"])
            top.pack(fill="x", pady=(0, 3))
            tk.Label(
                top,
                text=f"v{ver}" + (" • LATEST RELEASE" if is_latest else ""),
                font=("Segoe UI", 8, "bold"),
                fg=p["status_ok"] if is_latest else p["status_warn"],
                bg=p["card_bg"],
            ).pack(side="left")
            if date_str:
                tk.Label(
                    top,
                    text=date_str,
                    font=("Segoe UI", 7),
                    fg=p["text_muted"],
                    bg=p["card_bg"],
                ).pack(side="right")

            if title:
                tk.Label(
                    card,
                    text=title,
                    font=("Segoe UI", 8, "bold"),
                    fg=p["text_primary"],
                    bg=p["card_bg"],
                    anchor="w",
                    justify="left",
                    wraplength=360,
                ).pack(fill="x", pady=(0, 4))

            for item in highlights:
                tk.Label(
                    card,
                    text=f"• {item}",
                    font=("Segoe UI", 7),
                    fg=p["text_muted"],
                    bg=p["card_bg"],
                    anchor="w",
                    justify="left",
                    wraplength=360,
                ).pack(fill="x", pady=1)

        bar = tk.Frame(self.wrap, bg=p["panel_bg"])
        bar.pack(fill="x", side="bottom")
        tk.Button(
            bar,
            text="Close",
            command=self.destroy,
            font=("Segoe UI", 9, "bold"),
            bg=p["border_dark"],
            fg=p["text_primary"],
            activebackground=p["outer_bg"],
            activeforeground=p["border_dark"],
            relief="flat",
            cursor="hand2",
            pady=5,
        ).pack(fill="x")
        self.bind("<Escape>", lambda _: self.destroy())

    def on_mousewheel(self, event):
        try:
            if self.canvas.winfo_exists():
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass


class AddCustomAppModal(tk.Toplevel):
    def __init__(self, parent, pal, on_save):
        super().__init__(parent)
        self.parent = parent
        self.pal = pal
        self.on_save = on_save
        self.title("Lang!ley // Add External App / Game (.exe)")
        self.resizable(False, False)
        self.configure(bg=pal["outer_bg"])
        self.transient(parent)
        apply_window_icon(self, parent)
        self.grab_set()
        self._build()
        self._fit_window()

    def _fit_window(self):
        self.update_idletasks()
        req_h, w = self.wrap.winfo_reqheight() + 24, 440
        self.parent.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - req_h) // 2
        self.geometry(f"{w}x{req_h}+{max(0, x)}+{max(0, y)}")

    def _build(self):
        p = self.pal
        self.wrap = tk.Frame(
            self,
            bg=p["panel_bg"],
            highlightbackground=p["border_dark"],
            highlightthickness=2,
            padx=14,
            pady=12,
        )
        self.wrap.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = tk.Frame(self.wrap, bg=p["border_dark"], padx=10, pady=6)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(
            hdr,
            text="➕ ADD EXTERNAL APPLICATION / GAME (.EXE)",
            font=("Segoe UI", 9, "bold"),
            fg=p["status_warn"],
            bg=p["border_dark"],
        ).pack(side="left")

        box = tk.Frame(
            self.wrap,
            bg=p["card_bg"],
            highlightbackground=p["border_light"],
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        box.pack(fill="x", pady=(0, 10))

        tk.Label(
            box,
            text="1. Executable File (.exe):",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(fill="x")
        exe_row = tk.Frame(box, bg=p["card_bg"])
        exe_row.pack(fill="x", pady=(2, 6))
        self.ent_exe = tk.Entry(
            exe_row,
            font=("Segoe UI", 8),
            bg=p["border_dark"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_exe.pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 4))
        tk.Button(
            exe_row,
            text="📂 Browse .exe",
            command=self._browse_exe,
            font=("Segoe UI", 8, "bold"),
            bg=p["border_dark"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=1,
        ).pack(side="right")

        tk.Label(
            box,
            text="2. Display Name on Discord:",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(fill="x")
        self.ent_name = tk.Entry(
            box,
            font=("Segoe UI", 8),
            bg=p["border_dark"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_name.pack(fill="x", ipady=2, pady=(2, 6))

        tk.Label(
            box,
            text="3. Custom Activity / Status Text (Optional):",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(fill="x")
        self.ent_status = tk.Entry(
            box,
            font=("Segoe UI", 8),
            bg=p["border_dark"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_status.insert(0, "Playing Custom Game")
        self.ent_status.pack(fill="x", ipady=2, pady=(2, 6))

        tk.Label(
            box,
            text="4. Custom Icon Image URL (Optional PNG/JPG link):",
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["card_bg"],
            anchor="w",
        ).pack(fill="x")
        self.ent_icon = tk.Entry(
            box,
            font=("Segoe UI", 8),
            bg=p["border_dark"],
            fg=p["text_primary"],
            insertbackground=p["text_primary"],
            relief="flat",
        )
        self.ent_icon.pack(fill="x", ipady=2, pady=(2, 2))

        self.lbl_err = tk.Label(
            self.wrap,
            text="Saved to config/custom_apps.json — detected when running with a visible window.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["panel_bg"],
            anchor="w",
        )
        self.lbl_err.pack(fill="x", pady=(0, 8))

        bar = tk.Frame(self.wrap, bg=p["panel_bg"])
        bar.pack(fill="x", side="bottom")
        tk.Button(
            bar,
            text="✓ Save External App",
            command=self._save,
            font=("Segoe UI", 8, "bold"),
            bg=p["border_dark"],
            fg=p["status_ok"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            pady=5,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(
            bar,
            text="Cancel",
            command=self.destroy,
            font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"],
            fg=p["text_muted"],
            activebackground=p["outer_bg"],
            relief="flat",
            cursor="hand2",
            pady=5,
        ).pack(side="right", expand=True, fill="x", padx=(4, 0))

    def _browse_exe(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Application or Game Executable (.exe)",
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")],
        )
        if path:
            self.ent_exe.delete(0, "end")
            self.ent_exe.insert(0, path)
            if not self.ent_name.get().strip():
                stem = os.path.splitext(os.path.basename(path))[0]
                clean = stem.replace("-Win64-Shipping", "").replace("_", " ").strip()
                self.ent_name.insert(0, clean)

    def _save(self):
        exe_val = self.ent_exe.get().strip()
        name_val = self.ent_name.get().strip()
        status_val = self.ent_status.get().strip() or "Active Session"
        icon_val = self.ent_icon.get().strip()
        if not exe_val:
            self.lbl_err.config(
                text="Please select or enter an .exe file first.",
                fg=self.pal["status_err"],
            )
            return
        if callable(self.on_save):
            self.on_save(exe_val, name_val, status_val, icon_val)
        self.destroy()
