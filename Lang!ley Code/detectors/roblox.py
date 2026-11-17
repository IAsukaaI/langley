import os
import re
import glob
import time
import psutil
import requests
from core.config_manager import Reg, HTTP_HEADERS, ROBLOX_FALLBACK_LOGO


class RobloxClient:
    re_join_place = re.compile(
        r"(?:!Joining game .*? place\s+|Joining game .*? place\s+|placeId[:=]\s*|\"placeId\"\s*:\s*|placeid=)(\d{4,18})",
        re.I,
    )
    re_univ = re.compile(r"(?:universeid[:=]\s*|\"universeId\"\s*:\s*|universeid=)(\d{4,18})", re.I)
    re_userid = re.compile(r"(?:userId[:=]\s*|\"UserId\"\s*:\s*|userid=)(\d{4,18})", re.I)

    ROBLOX_HEADERS = {
        **HTTP_HEADERS,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        ),
        "Accept": "application/json, image/png, image/webp, image/*, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.roblox.com/",
    }

    def __init__(self, state, on_ui, on_push):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push
        self.http = requests.Session()
        self.http.headers.update(self.ROBLOX_HEADERS)
        self.place_cache = {}
        self.last_icon_retry_ts = 0.0

    @staticmethod
    def get_roblox_procs():
        procs = []
        try:
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                n = (p.info.get("name") or "").lower()
                if n in ("robloxplayerbeta.exe", "windows10universal.exe"):
                    procs.append(p)
        except Exception:
            pass
        return procs

    def link_username(self, username):
        uname = str(username or "").strip().lstrip("@")
        if not uname:
            return False
        m_url = re.search(r"roblox\.com/users/(\d+)", uname, re.I)
        if m_url:
            uname = m_url.group(1)
        try:
            if uname.isdigit():
                uid = uname
                ur = self.http.get(f"https://users.roblox.com/v1/users/{uid}", timeout=4.0)
                if ur.status_code == 200:
                    d = ur.json()
                    self.state.roblox_user_id = str(d.get("id") or uid)
                    self.state.roblox_user_name = d.get("name") or uname
                    self.state.roblox_display_name = d.get("displayName") or self.state.roblox_user_name
                else:
                    return False
            else:
                r = self.http.post(
                    "https://users.roblox.com/v1/usernames/users",
                    json={"usernames": [uname], "excludeBannedUsers": False},
                    timeout=4.0,
                )
                if r.status_code != 200:
                    return False
                data = (r.json() or {}).get("data") or []
                if not data:
                    return False
                u = data[0]
                self.state.roblox_user_id = str(u.get("id") or "")
                self.state.roblox_user_name = u.get("name") or uname
                self.state.roblox_display_name = u.get("displayName") or self.state.roblox_user_name

            Reg.set("RobloxUserId", self.state.roblox_user_id)
            Reg.set("RobloxUserName", self.state.roblox_user_name)
            Reg.set("RobloxDisplayName", self.state.roblox_display_name)
            self.fetch_friends()
            self.on_ui()
            self.on_push()
            return True
        except Exception:
            return False

    def detect_local_account(self):
        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        app_storage = os.path.join(local_app, "Roblox", "LocalStorage", "appStorage.json")
        if os.path.exists(app_storage):
            try:
                raw = open(app_storage, "r", encoding="utf-8", errors="ignore").read()
                m_uid = re.search(r'"UserId"\s*:\s*"?([1-9]\d{4,16})"?', raw)
                m_uname = re.search(r'"Username"\s*:\s*"([^"]{2,32})"', raw)
                if m_uid and m_uid.group(1) != "0":
                    if self.link_username(m_uid.group(1)):
                        return True
                if m_uname and m_uname.group(1):
                    if self.link_username(m_uname.group(1)):
                        return True
            except OSError:
                pass

        log_dir = os.path.join(local_app, "Roblox", "logs")
        if os.path.exists(log_dir):
            try:
                files = sorted(glob.glob(os.path.join(log_dir, "*.log")), key=os.path.getmtime, reverse=True)[:5]
                for fpath in files:
                    try:
                        txt = open(fpath, "r", encoding="utf-8", errors="ignore").read()
                        for m in self.re_userid.finditer(txt):
                            uid = m.group(1)
                            if uid and uid != "0" and int(uid) > 1000:
                                if self.link_username(uid):
                                    return True
                    except Exception:
                        pass
            except OSError:
                pass
        return bool(self.state.roblox_user_id)

    def unlink(self):
        Reg.remove("RobloxUserId")
        Reg.remove("RobloxUserName")
        Reg.remove("RobloxDisplayName")
        self.state.roblox_user_id = ""
        self.state.roblox_user_name = ""
        self.state.roblox_display_name = ""
        self.state.roblox_friends = []
        self.on_ui()
        self.on_push()

    def fetch_friends(self):
        uid = self.state.roblox_user_id
        if not uid:
            return False
        try:
            r = self.http.get(f"https://friends.roblox.com/v1/users/{uid}/friends", timeout=4.5)
            if r.status_code != 200:
                return False
            raw = (r.json() or {}).get("data") or []
            out = []
            for f in raw:
                fid = str(f.get("id") or "")
                name = f.get("name") or f.get("displayName") or f"User {fid}"
                dname = f.get("displayName") or name
                disp = f"{dname} (@{name})" if dname.lower() != name.lower() else name
                is_online = bool(f.get("isOnline"))
                out.append({"id": fid, "name": disp, "online": is_online, "status": "Online on Roblox" if is_online else "Offline"})
            out.sort(key=lambda x: (0 if x["online"] else 1, x["name"].lower()))
            self.state.roblox_friends = out
            self.on_ui()
            return True
        except Exception:
            return False

    def resolve_place(self, place_id, universe_id=""):
        place_id = str(place_id or "").strip()
        if not place_id:
            return ("Roblox", "", ROBLOX_FALLBACK_LOGO)
        if place_id in self.place_cache:
            cached = self.place_cache[place_id]
            if cached[2] and cached[2] != ROBLOX_FALLBACK_LOGO and "wikimedia" not in cached[2]:
                return cached

        univ_id = str(universe_id or "").strip()
        if not univ_id:
            try:
                r = self.http.get(
                    f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
                    headers=self.ROBLOX_HEADERS,
                    timeout=3.5,
                )
                if r.status_code == 200:
                    univ_id = str((r.json() or {}).get("universeId") or "")
            except Exception:
                pass

        gname = f"Roblox Experience ({place_id})"
        creator = ""
        icon_url = ""

        if univ_id:
            try:
                gr = self.http.get(
                    "https://games.roblox.com/v1/games",
                    params={"universeIds": univ_id},
                    headers=self.ROBLOX_HEADERS,
                    timeout=4.0,
                )
                if gr.status_code == 200:
                    gdata = (gr.json() or {}).get("data") or []
                    if gdata:
                        gname = gdata[0].get("name") or gname
                        creator = (gdata[0].get("creator") or {}).get("name") or ""
            except Exception:
                pass

            try:
                ir = self.http.get(
                    "https://thumbnails.roblox.com/v1/games/icons",
                    params={
                        "universeIds": univ_id,
                        "returnPolicy": "PlaceHolder",
                        "size": "512x512",
                        "format": "Png",
                        "isCircular": "false",
                    },
                    headers=self.ROBLOX_HEADERS,
                    timeout=4.0,
                )
                if ir.status_code == 200:
                    idata = (ir.json() or {}).get("data") or []
                    if idata and str(idata[0].get("imageUrl") or "").startswith("http"):
                        icon_url = idata[0]["imageUrl"]
            except Exception:
                pass

        if not icon_url:
            try:
                pr = self.http.get(
                    "https://thumbnails.roblox.com/v1/places/gameicons",
                    params={
                        "placeIds": place_id,
                        "returnPolicy": "PlaceHolder",
                        "size": "512x512",
                        "format": "Png",
                        "isCircular": "false",
                    },
                    headers=self.ROBLOX_HEADERS,
                    timeout=4.0,
                )
                if pr.status_code == 200:
                    pdata = (pr.json() or {}).get("data") or []
                    if pdata and str(pdata[0].get("imageUrl") or "").startswith("http"):
                        icon_url = pdata[0]["imageUrl"]
            except Exception:
                pass

        if not icon_url and univ_id:
            try:
                mr = self.http.get(
                    "https://thumbnails.roblox.com/v1/games/multiget/thumbnails",
                    params={
                        "universeIds": univ_id,
                        "countPerUniverse": "1",
                        "defaults": "true",
                        "size": "768x432",
                        "format": "Png",
                        "isCircular": "false",
                    },
                    headers=self.ROBLOX_HEADERS,
                    timeout=4.0,
                )
                if mr.status_code == 200:
                    mdata = (mr.json() or {}).get("data") or []
                    if mdata:
                        thumbs = mdata[0].get("thumbnails") or []
                        if thumbs and str(thumbs[0].get("imageUrl") or "").startswith("http"):
                            icon_url = thumbs[0]["imageUrl"]
            except Exception:
                pass

        if not icon_url:
            icon_url = ROBLOX_FALLBACK_LOGO

        res = (gname, creator, icon_url)
        if icon_url != ROBLOX_FALLBACK_LOGO or not gname.startswith("Roblox Experience"):
            self.place_cache[place_id] = res
        return res

    def poll(self, snapshot=None):
        if snapshot is not None:
            all_procs, _, _, _ = snapshot
            procs = [
                p
                for p in all_procs
                if p["name"] in ("robloxplayerbeta.exe", "windows10universal.exe") and p.get("has_visible_window", False)
            ]
        else:
            procs = []
            for p in self.get_roblox_procs():
                try:
                    cmd = " ".join(p.info.get("cmdline") or [])
                    procs.append({"pid": p.info.get("pid"), "name": (p.info.get("name") or "").lower(), "cmdline": cmd})
                except Exception:
                    pass

        if not procs:
            if self.state.roblox_running:
                self.state.roblox_running = False
                self.state.roblox_place_id = ""
                self.state.roblox_universe_id = ""
                self.state.roblox_game_name = ""
                self.state.roblox_creator = ""
                self.state.roblox_game_icon = ROBLOX_FALLBACK_LOGO
                return True
            return False

        changed = False
        if not self.state.roblox_running:
            self.state.roblox_running = True
            self.state.roblox_start_ts = int(time.time())
            self.state.roblox_game_name = "Roblox"
            self.state.roblox_game_icon = ROBLOX_FALLBACK_LOGO
            changed = True

        cmd_place, cmd_univ = None, None
        for p in procs:
            try:
                cmdline = p.get("cmdline") or ""
                mp = self.re_join_place.search(cmdline)
                if mp:
                    cmd_place = mp.group(1)
                mu = self.re_univ.search(cmdline)
                if mu:
                    cmd_univ = mu.group(1)
            except Exception:
                pass

        local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        log_dir = os.path.join(local, "Roblox", "logs")
        last_place, last_univ = cmd_place, cmd_univ

        if os.path.exists(log_dir):
            all_logs = glob.glob(os.path.join(log_dir, "*.log"))
            if all_logs:
                # Prioritize the newest active *_Player_*.log file so Home sessions do not inherit old places
                player_logs = [p for p in all_logs if "_player_" in os.path.basename(p).lower()]
                target_logs = sorted(player_logs or all_logs, key=os.path.getmtime, reverse=True)[:1]
                for lpath in target_logs:
                    try:
                        with open(lpath, "r", encoding="utf-8", errors="ignore") as f:
                            sz = os.path.getsize(lpath)
                            if sz <= 600_000:
                                content = f.read()
                            else:
                                head = f.read(300_000)
                                f.seek(sz - 300_000)
                                f.readline()
                                tail = f.read()
                                content = head + "\n" + tail

                        if not self.state.roblox_user_id:
                            m_uid = self.re_userid.search(content)
                            if m_uid and m_uid.group(1) != "0":
                                self.link_username(m_uid.group(1))

                        for line in content.splitlines():
                            if "leaveGame" in line or "Disconnecting" in line or "NetworkClient:Remove" in line:
                                if not cmd_place:
                                    last_place, last_univ = "", ""
                            mp = self.re_join_place.search(line)
                            if mp:
                                last_place = mp.group(1)
                            mu = self.re_univ.search(line)
                            if mu:
                                last_univ = mu.group(1)
                    except OSError:
                        pass

        now = time.time()
        need_icon_retry = (
            bool(last_place)
            and last_place == self.state.roblox_place_id
            and (not self.state.roblox_game_icon or self.state.roblox_game_icon == ROBLOX_FALLBACK_LOGO)
            and (now - self.last_icon_retry_ts >= 10.0)
        )
        if (last_place is not None and last_place != self.state.roblox_place_id) or need_icon_retry:
            self.last_icon_retry_ts = now
            self.state.roblox_place_id = last_place
            self.state.roblox_universe_id = last_univ or ""
            if last_place:
                gname, creator, icon = self.resolve_place(last_place, last_univ)
                self.state.roblox_game_name = gname
                self.state.roblox_creator = creator
                self.state.roblox_game_icon = icon
            else:
                self.state.roblox_game_name = "Roblox (In App / Home)"
                self.state.roblox_creator = ""
                self.state.roblox_game_icon = ROBLOX_FALLBACK_LOGO
            changed = True
        return changed
