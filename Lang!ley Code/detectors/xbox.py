import os
import re
import json
import time
import urllib.parse
import winreg
import psutil
import requests
from core.config_manager import (
    Reg,
    HTTP_HEADERS,
    XBOX_REG_PATH,
    XBOX_FALLBACK_LOGO,
    XBOX_IGNORE_PROCS,
    lookup_known_game_icon,
)
from core.rpc import _parse_str_list


class XboxClient:
    def __init__(self, state, on_ui, on_push):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push
        self.http = requests.Session()
        self.http.headers.update(HTTP_HEADERS)
        self.icon_cache = {}
        self.dir_meta_cache = {}
        self.scanned_once = False

    def detect_local_gamertag(self):
        if self.state.xbox_manual_override and self.state.xbox_gamertag:
            return False
        gt = Reg.get("Gamertag", "", path=XBOX_REG_PATH)
        if not gt:
            gt = Reg.get("ModernGamertag", "", path=XBOX_REG_PATH)
        if gt and str(gt).strip() and str(gt).strip() != self.state.xbox_gamertag:
            self.state.xbox_gamertag = str(gt).strip()
            Reg.set("XboxGamertag", self.state.xbox_gamertag)
            return True
        return False

    def link_gamertag(self, gamertag):
        gt = str(gamertag or "").strip()
        if not gt:
            return False
        if "xbox.com/" in gt.lower():
            gt = urllib.parse.unquote(gt.rstrip("/").split("/")[-1].split("?")[0]).strip()
        if not gt:
            return False
        self.state.xbox_gamertag = gt
        self.state.xbox_manual_override = True
        Reg.set("XboxGamertag", gt)
        Reg.set("XboxManualOverride", 1, winreg.REG_DWORD)
        self.fetch_friends()
        self.on_ui()
        self.on_push()
        return True

    def reset_gamertag(self):
        Reg.set("XboxManualOverride", 0, winreg.REG_DWORD)
        Reg.remove("XboxGamertag")
        self.state.xbox_manual_override = False
        self.state.xbox_gamertag = ""
        self.detect_local_gamertag()
        self.fetch_friends()
        self.on_ui()
        self.on_push()

    def unlink(self):
        Reg.set("XboxManualOverride", 1, winreg.REG_DWORD)
        Reg.remove("XboxGamertag")
        self.state.xbox_manual_override = True
        self.state.xbox_gamertag = ""
        self.on_ui()
        self.on_push()

    def _parse_game_config(self, folder):
        if folder in self.dir_meta_cache:
            return self.dir_meta_cache[folder]
        title = os.path.basename(folder)
        for cfg_name in ("MicrosoftGame.config", "AppxManifest.xml"):
            p = os.path.join(folder, cfg_name)
            if not os.path.exists(p):
                p = os.path.join(folder, "Content", cfg_name)
            if os.path.exists(p):
                try:
                    txt = open(p, "r", encoding="utf-8", errors="ignore").read()
                    m = re.search(r'DefaultDisplayName="([^"]+)"', txt) or re.search(r"<DisplayName>([^<]+)</DisplayName>", txt)
                    if m and "ms-resource" not in m.group(1).lower():
                        title = m.group(1).strip()
                        break
                except OSError:
                    pass
        self.dir_meta_cache[folder] = title
        return title

    def resolve_cover_icon(self, game_title, fallback=XBOX_FALLBACK_LOGO, appid=0):
        k = (game_title or "").strip().lower()
        cache_key = f"{k}:{appid}"
        if not k and not appid:
            return fallback
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]

        known = lookup_known_game_icon(k)
        if known:
            self.icon_cache[cache_key] = known
            return known

        icon = fallback
        try:
            aid = int(appid or 0)
            tiny_img = ""
            if aid <= 0 and k:
                r = self.http.get(
                    "https://store.steampowered.com/api/storesearch/",
                    params={"term": game_title, "l": "english", "cc": "US"},
                    timeout=3.5,
                )
                if r.status_code == 200:
                    items = (r.json() or {}).get("items") or []
                    if items:
                        aid = int(items[0].get("id") or 0)
                        tiny_img = str(items[0].get("tiny_image") or "").split("?")[0]

            if aid > 0:
                icon = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"
                if tiny_img and "/store_item_assets/" in tiny_img:
                    icon = re.sub(r"/capsule_[^/]+\.jpg$", "/header.jpg", tiny_img)
                else:
                    try:
                        rd = self.http.get(
                            "https://store.steampowered.com/api/appdetails",
                            params={"appids": aid, "l": "english"},
                            timeout=3.0,
                        )
                        if rd.status_code == 200:
                            payload = (rd.json() or {}).get(str(aid)) or {}
                            if payload.get("success") and isinstance(payload.get("data"), dict):
                                hdr = str(payload["data"].get("header_image") or "").split("?")[0]
                                if hdr.startswith("http"):
                                    icon = hdr
                    except Exception:
                        pass
        except Exception:
            pass
        if len(self.icon_cache) > 160:
            self.icon_cache.clear()
        self.icon_cache[cache_key] = icon
        return icon

    def scan_installed_xbox_games(self):
        self.scanned_once = True
        games = []
        seen = set()
        skip_names = {
            "gamesave",
            "minecraft launcher",
            "gamingservices",
            "directx",
            "xbox app",
            "microsoft gameinput",
            "fortnite",
        }
        for drive in ("C:", "D:", "E:", "F:"):
            root = os.path.join(drive + "\\", "XboxGames")
            if not os.path.exists(root):
                continue
            try:
                for sub in os.listdir(root):
                    full = os.path.join(root, sub)
                    if not os.path.isdir(full):
                        continue
                    if "fortnite" in sub.lower():
                        continue
                    title = self._parse_game_config(full)
                    t_low = title.lower().strip()
                    if not t_low or t_low in seen or t_low in skip_names or sub.lower() in skip_names or "fortnite" in t_low:
                        continue
                    seen.add(t_low)
                    games.append({"name": title, "install_dir": full})
            except OSError:
                pass
        games.sort(key=lambda x: x["name"].lower())
        self.state.xbox_installed_games = games
        return games

    def fetch_friends(self):
        friends = []
        seen = set()
        own_gt = (self.state.xbox_gamertag or "").strip().lower()

        def add_f(name, status, online=False, in_game=False):
            clean = str(name or "").strip()
            if not clean or len(clean) < 2 or len(clean) > 32:
                return
            k = clean.lower()
            if k == own_gt or k in seen or k in ("default", "unknown", "null", "none", "system", "xboxlive"):
                return
            seen.add(k)
            friends.append({"name": clean, "status": status, "online": online, "in_game": in_game})

        for peer in self.state.peers:
            add_f(peer, "★ In Your Active Party", online=True, in_game=True)

        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        pkg_roots = [
            os.path.join(local_app, "Packages", "Microsoft.GamingApp_8wekyb3d8bbwe", "LocalState"),
            os.path.join(local_app, "Packages", "Microsoft.GamingApp_8wekyb3d8bbwe", "LocalCache"),
            os.path.join(local_app, "Packages", "Microsoft.XboxGamingOverlay_8wekyb3d8bbwe", "LocalState"),
        ]
        re_gt_json = re.compile(r'"(?:gamertag|modernGamertag|displayName)"\s*:\s*"([A-Za-z0-9 _\-]{3,20})"', re.I)
        for proot in pkg_roots:
            if not os.path.exists(proot):
                continue
            try:
                for dirpath, _, filenames in os.walk(proot):
                    for fn in filenames[:25]:
                        if not fn.lower().endswith((".json", ".txt", ".log", ".dat")):
                            continue
                        fpath = os.path.join(dirpath, fn)
                        try:
                            if os.path.getsize(fpath) > 1_200_000:
                                continue
                            txt = open(fpath, "r", encoding="utf-8", errors="ignore").read()
                            for m in re_gt_json.finditer(txt):
                                cand = m.group(1).strip()
                                if cand and not cand.lower().startswith(("microsoft", "windows", "xbox", "game", "app", "user")):
                                    add_f(cand, "Xbox Live Friend (Local Cache)", online=False)
                        except OSError:
                            pass
            except OSError:
                pass

        for gt_str in _parse_str_list(Reg.get("XboxTrackedFriends", "")):
            is_party = gt_str.lower() in [p.lower() for p in self.state.peers]
            add_f(
                gt_str,
                "★ In Party / Active" if is_party else "Xbox Live Friend (Tracked)",
                online=is_party or self.state.xbox_running,
                in_game=is_party,
            )

        friends.sort(key=lambda x: (0 if x.get("in_game") else (1 if x.get("online") else 2), x["name"].lower()))
        self.state.xbox_friends = friends
        return friends

    def add_tracked_friend(self, gamertag):
        gt = str(gamertag or "").strip()
        if not gt:
            return False
        tracked = _parse_str_list(Reg.get("XboxTrackedFriends", ""))
        if gt.lower() not in [x.lower() for x in tracked]:
            tracked.append(gt)
            Reg.set("XboxTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def remove_tracked_friend(self, gamertag):
        gt = str(gamertag or "").strip().lower()
        tracked = [x for x in _parse_str_list(Reg.get("XboxTrackedFriends", "")) if x.lower() != gt]
        Reg.set("XboxTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def poll(self, snapshot=None):
        self.detect_local_gamertag()
        if not self.scanned_once:
            self.scan_installed_xbox_games()

        if snapshot is not None:
            proc_list = snapshot[0]
        else:
            proc_list = []
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    exe = p.info.get("exe") or ""
                    proc_list.append(
                        {
                            "name": (p.info.get("name") or "").lower(),
                            "exe": exe,
                            "exe_lower": exe.lower(),
                            "has_visible_window": True,
                        }
                    )
                except Exception:
                    pass

        detected_title = None
        for p in proc_list:
            try:
                pname = p.get("name") or ""
                if not pname or pname in XBOX_IGNORE_PROCS or pname.startswith("fortniteclient-"):
                    continue
                if snapshot is not None and not p.get("has_visible_window", False):
                    continue
                exe = p.get("exe") or ""
                if not exe:
                    continue
                low_exe = p.get("exe_lower") or exe.lower()
                if "\\fortnite" in low_exe or "fortnite" in pname:
                    continue
                if "\\xboxgames\\" in low_exe:
                    parts = exe.split("\\")
                    for idx, part in enumerate(parts):
                        if part.lower() == "xboxgames" and idx + 1 < len(parts):
                            if "fortnite" in parts[idx + 1].lower():
                                break
                            gfolder = "\\".join(parts[: idx + 2])
                            cand = self._parse_game_config(gfolder)
                            if cand and "fortnite" not in cand.lower():
                                detected_title = cand
                            break
                    if detected_title:
                        break
                elif "\\windowsapps\\" in low_exe and not any(
                    sys_k in low_exe
                    for sys_k in (
                        "microsoft.windowsterminal",
                        "microsoft.ui",
                        "microsoft.vclibs",
                        "microsoft.net",
                        "microsoft.gamingapp",
                        "microsoft.xbox",
                        "fortnite",
                        "epicgames",
                    )
                ):
                    gfolder = os.path.dirname(exe)
                    if os.path.exists(os.path.join(gfolder, "MicrosoftGame.config")):
                        cand = self._parse_game_config(gfolder)
                        if cand and "fortnite" not in cand.lower():
                            detected_title = cand
                            break
            except Exception:
                pass

        if not detected_title:
            if self.state.xbox_running:
                self.state.xbox_running = False
                self.state.xbox_game_name = ""
                self.state.xbox_game_icon = XBOX_FALLBACK_LOGO
                return True
            return False

        if not self.state.xbox_running or self.state.xbox_game_name != detected_title:
            self.state.xbox_running = True
            self.state.xbox_game_name = detected_title
            self.state.xbox_game_icon = self.resolve_cover_icon(detected_title)
            self.state.xbox_start_ts = int(time.time())
            return True
        return False
