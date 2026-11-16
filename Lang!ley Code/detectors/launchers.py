import os
import re
import ssl
import glob
import json
import time
import base64
import sqlite3
import urllib.request
import psutil
from core.config_manager import (
    CFG,
    Reg,
    RIOT_FALLBACK_LOGO,
    VALORANT_LOGO,
    LOL_LOGO,
    EA_FALLBACK_LOGO,
    UBISOFT_FALLBACK_LOGO,
    GOG_FALLBACK_LOGO,
    BATTLENET_FALLBACK_LOGO,
    MEDAL_PROCS,
    EA_IGNORE_PROCS,
    UBISOFT_IGNORE_PROCS,
    GOG_IGNORE_PROCS,
    BATTLENET_IGNORE_PROCS,
)
from core.rpc import _parse_str_list


class RiotClient:
    UNINSTALL_PATHS = (
        (r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Riot Game valorant.live", "VALORANT"),
        (r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Riot Game league_of_legends.live", "League of Legends"),
        (r"SOFTWARE\WOW6432Node\Riot Games, Inc\League of Legends", "League of Legends"),
    )

    def __init__(self, state, on_ui, on_push):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push
        self.scanned_once = False

    def scan_installed_games(self):
        self.scanned_once = True
        games = []
        seen = set()

        def add_game(name, path):
            k = name.lower()
            if k in seen:
                return
            seen.add(k)
            games.append({"name": name, "install_dir": os.path.normpath(path)})

        prog_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        riot_json = os.path.join(prog_data, "Riot Games", "RiotClientInstalls.json")
        if os.path.exists(riot_json):
            try:
                data = json.load(open(riot_json, "r", encoding="utf-8", errors="ignore"))
                associated = data.get("associated_client") or {}
                for install_dir, _ in associated.items():
                    low = install_dir.lower()
                    if "valorant" in low:
                        add_game("VALORANT", install_dir)
                    elif "league of legends" in low or "league" in low:
                        add_game("League of Legends", install_dir)
            except Exception:
                pass

        meta_dir = os.path.join(prog_data, "Riot Games", "Metadata")
        if os.path.exists(meta_dir):
            try:
                for sub in os.listdir(meta_dir):
                    low = sub.lower()
                    if "valorant" in low:
                        add_game("VALORANT", os.path.join(meta_dir, sub))
                    elif "league_of_legends" in low:
                        add_game("League of Legends", os.path.join(meta_dir, sub))
            except OSError:
                pass

        for reg_path, gname in self.UNINSTALL_PATHS:
            loc = Reg.get_any("InstallLocation", "", path=reg_path) or Reg.get_any("Location", "", path=reg_path)
            if loc and os.path.exists(str(loc)):
                add_game(gname, str(loc))

        for drive in ("C:", "D:", "E:", "F:"):
            base = os.path.join(drive + "\\", "Riot Games")
            if not os.path.exists(base):
                continue
            val_dir = os.path.join(base, "VALORANT")
            if os.path.exists(val_dir):
                add_game("VALORANT", val_dir)
            lol_dir = os.path.join(base, "League of Legends")
            if os.path.exists(lol_dir):
                add_game("League of Legends", lol_dir)

        games.sort(key=lambda x: x["name"].lower())
        self.state.riot_installed_games = games
        return games

    def poll(self, snapshot=None):
        if not self.scanned_once:
            self.scan_installed_games()

        if not self.state.riot_enabled:
            if self.state.riot_running:
                self.state.riot_running = False
                self.state.riot_game_name = ""
                self.state.riot_game_state = ""
                return True
            return False

        if snapshot is not None:
            procs, _, windows, _ = snapshot
        else:
            procs, windows = [], []
            for p in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    cmd = " ".join(p.info.get("cmdline") or [])
                    exe = p.info.get("exe") or ""
                    procs.append(
                        {
                            "name": (p.info.get("name") or "").lower(),
                            "exe_lower": exe.lower(),
                            "cmdline_lower": cmd.lower(),
                            "has_visible_window": True,
                        }
                    )
                except Exception:
                    pass

        detected_name = ""
        detected_state = ""
        detected_icon = RIOT_FALLBACK_LOGO

        has_val_shipping = False
        has_lol_match = False
        has_lol_client = False

        for p in procs:
            pname = p["name"]
            if pname in MEDAL_PROCS or pname in ("riotclientux.exe", "riotclientservices.exe", "riotclientcrashhandler.exe"):
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue
            if pname == "valorant-win64-shipping.exe":
                has_val_shipping = True
            elif pname == "league of legends.exe":
                has_lol_match = True
            elif pname in ("leagueclientux.exe", "leagueclient.exe"):
                has_lol_client = True

        if has_val_shipping:
            detected_name = "VALORANT"
            detected_state = "In Match / Agent Tactical Play"
            detected_icon = VALORANT_LOGO
            for w in windows:
                if "valorant" in w["pname"] and w["title"] and "unreal" not in w["title_lower"]:
                    detected_state = "In Match / Active Session"
                    break
        elif has_lol_match:
            detected_name = "League of Legends"
            detected_state = "In Match (Summoner's Rift / ARAM)"
            detected_icon = LOL_LOGO
        elif has_lol_client:
            detected_name = "League of Legends"
            detected_state = "In Lobby / Champion Select"
            detected_icon = LOL_LOGO

        if not detected_name:
            if self.state.riot_running:
                self.state.riot_running = False
                self.state.riot_game_name = ""
                self.state.riot_game_state = ""
                self.state.riot_game_icon = RIOT_FALLBACK_LOGO
                return True
            return False

        changed = (
            not self.state.riot_running
            or self.state.riot_game_name != detected_name
            or self.state.riot_game_state != detected_state
        )
        if not self.state.riot_running or self.state.riot_game_name != detected_name:
            self.state.riot_start_ts = int(time.time())
        self.state.riot_running = True
        self.state.riot_game_name = detected_name
        self.state.riot_game_state = detected_state
        self.state.riot_game_icon = detected_icon
        return changed

    @staticmethod
    def _riot_local_get(port, password, endpoint):
        url = f"https://127.0.0.1:{port}{endpoint}"
        auth = base64.b64encode(f"riot:{password}".encode("utf-8")).decode("ascii")
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
        with urllib.request.urlopen(req, context=ctx, timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))

    def fetch_friends(self):
        friends = []
        seen = set()

        def add_f(name, status, online=False, in_game=False):
            clean = str(name or "").strip()
            if not clean:
                return
            k = clean.lower()
            if k in seen:
                return
            seen.add(k)
            friends.append({"name": clean, "status": status, "online": online, "in_game": in_game})

        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        lockfiles = [os.path.join(local_app, "Riot Games", "Riot Client", "Config", "lockfile")]
        for g in self.state.riot_installed_games:
            if "league" in g["name"].lower():
                lockfiles.append(os.path.join(g["install_dir"], "lockfile"))

        for lf in lockfiles:
            if not os.path.exists(lf):
                continue
            try:
                content = open(lf, "r", encoding="utf-8", errors="ignore").read().strip()
                parts = content.split(":")
                if len(parts) < 4:
                    continue
                port, pw = parts[2].strip(), parts[3].strip()
                try:
                    f_data = self._riot_local_get(port, pw, "/chat/v4/friends")
                    p_data = {}
                    try:
                        p_raw = self._riot_local_get(port, pw, "/chat/v4/presences")
                        for pr in p_raw.get("presences") or []:
                            if pr.get("puuid"):
                                p_data[pr["puuid"]] = pr
                    except Exception:
                        pass

                    for fr in f_data.get("friends") or []:
                        puuid = fr.get("puuid") or ""
                        gname = (fr.get("game_name") or fr.get("name") or "").strip()
                        gtag = (fr.get("game_tag") or "").strip()
                        disp = f"{gname}#{gtag}" if (gname and gtag) else gname
                        pres = p_data.get(puuid) or {}
                        p_state = str(pres.get("state") or "offline").lower()
                        prod = str(pres.get("product") or "").lower()
                        if p_state in ("online", "dnd", "away", "chat"):
                            if "valorant" in prod:
                                add_f(disp, "Playing VALORANT", online=True, in_game=True)
                            elif "league" in prod:
                                add_f(disp, "Playing League of Legends", online=True, in_game=True)
                            else:
                                add_f(disp, "Online on Riot Client", online=True, in_game=False)
                        else:
                            add_f(disp, "Offline (Riot ID)", online=False, in_game=False)
                except Exception:
                    try:
                        lcu_friends = self._riot_local_get(port, pw, "/lol-chat/v1/friends")
                        if isinstance(lcu_friends, list):
                            for fr in lcu_friends:
                                gname = (fr.get("gameName") or fr.get("name") or "").strip()
                                gtag = (fr.get("gameTag") or "").strip()
                                disp = f"{gname}#{gtag}" if (gname and gtag) else gname
                                avail = str(fr.get("availability") or "offline").lower()
                                is_on = avail not in ("offline", "mobile")
                                is_ig = avail == "dnd" or bool((fr.get("lol") or {}).get("gameStatus"))
                                st_lbl = "In League of Legends" if is_ig else ("Online in LoL Client" if is_on else "Offline")
                                add_f(disp, st_lbl, online=is_on, in_game=is_ig)
                    except Exception:
                        pass
            except Exception:
                pass

        tracked_list = _parse_str_list(Reg.get("RiotTrackedFriends", ""))
        known_lower = {x.lower() for x in tracked_list}
        updated_cache = False
        for f in friends[:30]:
            if f["name"].lower() not in known_lower:
                tracked_list.append(f["name"])
                known_lower.add(f["name"].lower())
                updated_cache = True
        if updated_cache:
            Reg.set("RiotTrackedFriends", json.dumps(tracked_list[:40]))

        for item in tracked_list:
            add_f(str(item), "Riot Friend (Saved)" if not self.state.riot_running else "Offline / Riot ID", online=False, in_game=False)

        friends.sort(key=lambda x: (0 if x.get("in_game") else (1 if x.get("online") else 2), x["name"].lower()))
        self.state.riot_friends = friends
        return friends

    def add_tracked_friend(self, riot_id):
        rid = str(riot_id or "").strip()
        if not rid:
            return False
        tracked = _parse_str_list(Reg.get("RiotTrackedFriends", ""))
        if rid.lower() not in [x.lower() for x in tracked]:
            tracked.append(rid)
            Reg.set("RiotTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def remove_tracked_friend(self, riot_id):
        rid = str(riot_id or "").strip().lower()
        tracked = [x for x in _parse_str_list(Reg.get("RiotTrackedFriends", "")) if x.lower() != rid]
        Reg.set("RiotTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def link_account(self, riot_id):
        rid = str(riot_id or "").strip()
        if not rid:
            return False
        self.state.riot_id = rid
        Reg.set("RiotID", rid)
        self.fetch_friends()
        self.on_ui()
        self.on_push()
        return True

    def unlink(self):
        self.state.riot_id = ""
        Reg.remove("RiotID")
        self.on_ui()
        self.on_push()
        return True

    def detect_local_account(self):
        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        lockfiles = [os.path.join(local_app, "Riot Games", "Riot Client", "Config", "lockfile")]
        for g in self.state.riot_installed_games:
            if "league" in g["name"].lower():
                lockfiles.append(os.path.join(g["install_dir"], "lockfile"))

        for lf in lockfiles:
            if not os.path.exists(lf):
                continue
            try:
                parts = open(lf, "r", encoding="utf-8", errors="ignore").read().strip().split(":")
                if len(parts) < 4:
                    continue
                port, pw = parts[2].strip(), parts[3].strip()
                for ep in ("/chat/v1/session", "/lol-summoner/v1/current-summoner", "/lol-chat/v1/me"):
                    try:
                        me = self._riot_local_get(port, pw, ep)
                        if isinstance(me, dict):
                            gn = (me.get("game_name") or me.get("gameName") or me.get("displayName") or me.get("name") or "").strip()
                            gt = (me.get("game_tag") or me.get("tagLine") or me.get("gameTag") or "").strip()
                            if gn:
                                full_id = f"{gn}#{gt}" if gt else gn
                                return self.link_account(full_id)
                    except Exception:
                        pass
            except Exception:
                pass

        log_dir = os.path.join(local_app, "Riot Games", "Riot Client", "Logs", "Riot Client Logs")
        if os.path.exists(log_dir):
            try:
                logs = sorted(glob.glob(os.path.join(log_dir, "*.log")), key=os.path.getmtime, reverse=True)[:4]
                re_rid = re.compile(r'"(?:game_name|gameName)"\s*:\s*"([^"]{2,24})"\s*,\s*"(?:game_tag|tagLine|gameTag)"\s*:\s*"([^"]{2,8})"', re.I)
                for lpath in logs:
                    txt = open(lpath, "r", encoding="utf-8", errors="ignore").read()
                    m = re_rid.search(txt)
                    if m:
                        return self.link_account(f"{m.group(1)}#{m.group(2)}")
            except Exception:
                pass
        self.fetch_friends()
        return bool(self.state.riot_id)


class EAClient:
    DEFAULT_KNOWN_PROCS = {
        "r5apex.exe": ("Apex Legends", "In Match / Lobby • Battle Royale", 1172470),
        "r5apex_dx12.exe": ("Apex Legends", "In Match / Lobby (DX12) • Battle Royale", 1172470),
        "fc25.exe": ("EA Sports FC 25", "In Match / Ultimate Team", 2669320),
        "fc25_trial.exe": ("EA Sports FC 25", "In Match / Ultimate Team (Trial)", 2669320),
        "fc24.exe": ("EA Sports FC 24", "In Match / Ultimate Team", 2195250),
        "fc24_trial.exe": ("EA Sports FC 24", "In Match / Ultimate Team (Trial)", 2195250),
        "fc26.exe": ("EA Sports FC 26", "In Match / Ultimate Team", 2669320),
        "fifa23.exe": ("EA Sports FIFA 23", "In Match / Ultimate Team", 1811260),
        "bf2042.exe": ("Battlefield 2042", "In Match • All-Out Warfare", 1517290),
        "bfv.exe": ("Battlefield V", "In Multiplayer Match", 1238810),
        "bf1.exe": ("Battlefield 1", "In Multiplayer Match", 1238840),
        "bf4.exe": ("Battlefield 4", "In Multiplayer Match", 1238860),
        "ts4_x64.exe": ("The Sims 4", "In Live / Build Mode", 1222670),
        "ts4.exe": ("The Sims 4", "In Live / Build Mode", 1222670),
        "starwarsjedifallenorder.exe": ("Star Wars Jedi: Fallen Order", "In Campaign", 1172380),
        "starwarsjedisurvivor.exe": ("Star Wars Jedi: Survivor", "In Campaign", 1774580),
        "needforspeedunbound.exe": ("Need for Speed Unbound", "In Lakeshore Online / Career", 1846380),
        "needforspeedheat.exe": ("Need for Speed Heat", "In Palm City", 1222680),
        "it_takes_two.exe": ("It Takes Two", "In Co-Op Adventure", 1426210),
        "madden25.exe": ("Madden NFL 25", "In Match / Franchise", 2582560),
        "madden24.exe": ("Madden NFL 24", "In Match / Franchise", 2140330),
    }

    def __init__(self, state, xbox_helper, on_ui, on_push):
        self.state = state
        self.xbox_helper = xbox_helper
        self.on_ui = on_ui
        self.on_push = on_push
        self.scanned_once = False
        db_procs = CFG.games_db.get("ea_known_procs") or {}
        self.KNOWN_PROCS = {k.lower(): tuple(v) for k, v in db_procs.items()} if db_procs else dict(self.DEFAULT_KNOWN_PROCS)

    @staticmethod
    def _parse_installer_xml(game_dir):
        xml_path = os.path.join(game_dir, "__Installer", "installerdata.xml")
        if os.path.exists(xml_path):
            try:
                txt = open(xml_path, "r", encoding="utf-8", errors="ignore").read()
                m = re.search(r"<gameTitle[^>]*>([^<]+)</gameTitle>", txt, re.I) or re.search(r"<title[^>]*>([^<]+)</title>", txt, re.I)
                if m and m.group(1).strip():
                    return m.group(1).strip()
            except OSError:
                pass
        return os.path.basename(game_dir.rstrip("\\/"))

    def scan_installed_games(self):
        self.scanned_once = True
        games = []
        seen = set()

        def add_game(title, install_dir):
            title = (title or "").strip()
            install_dir = (install_dir or "").strip()
            if not title or not install_dir or not os.path.exists(install_dir):
                return
            k = os.path.normcase(os.path.normpath(install_dir))
            if k in seen or "ea desktop" in title.lower():
                return
            seen.add(k)
            games.append({"name": title, "install_dir": os.path.normpath(install_dir), "norm_dir": k})

        for reg_root in (r"SOFTWARE\EA Games", r"SOFTWARE\Electronic Arts"):
            for root, flag, sub_path, sub_name in Reg.list_subkeys(reg_root):
                vals = Reg.read_key_dict(root, flag, sub_path)
                idir = vals.get("Install Dir") or vals.get("InstallDir") or ""
                dname = vals.get("DisplayName") or sub_name
                if idir:
                    add_game(str(dname), str(idir))

        for drive in ("C:", "D:", "E:", "F:"):
            for rel in ("Program Files\\EA Games", "Program Files (x86)\\Origin Games", "EA Games", "Origin Games"):
                base = os.path.join(drive + "\\", rel)
                if not os.path.exists(base):
                    continue
                try:
                    for sub in os.listdir(base):
                        full = os.path.join(base, sub)
                        if os.path.isdir(full):
                            title = self._parse_installer_xml(full)
                            add_game(title, full)
                except OSError:
                    pass

        games.sort(key=lambda x: x["name"].lower())
        self.state.ea_installed_games = games
        return games

    def poll(self, snapshot=None):
        if not self.scanned_once:
            self.scan_installed_games()

        if not self.state.ea_enabled:
            if self.state.ea_running:
                self.state.ea_running = False
                self.state.ea_game_name = ""
                self.state.ea_game_state = ""
                return True
            return False

        if snapshot is not None:
            procs = snapshot[0]
        else:
            procs = []
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    exe = p.info.get("exe") or ""
                    procs.append({"name": (p.info.get("name") or "").lower(), "exe": exe, "exe_lower": exe.lower(), "has_visible_window": True})
                except Exception:
                    pass

        detected_name = ""
        detected_state = ""
        detected_icon = EA_FALLBACK_LOGO

        for p in procs:
            pname = p["name"]
            if not pname or pname in EA_IGNORE_PROCS:
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue
            if pname in self.KNOWN_PROCS:
                gname, gstate, steam_aid = self.KNOWN_PROCS[pname]
                detected_name = gname
                detected_state = gstate
                detected_icon = self.xbox_helper.resolve_cover_icon(
                    detected_name, fallback=EA_FALLBACK_LOGO, appid=steam_aid
                )
                break

        if not detected_name:
            for p in procs:
                pname = p["name"]
                exe_low = p["exe_lower"]
                if not pname or not exe_low or pname in EA_IGNORE_PROCS:
                    continue
                if snapshot is not None and not p.get("has_visible_window", False):
                    continue
                for g in self.state.ea_installed_games:
                    ndir = g["norm_dir"]
                    if ndir and len(ndir) > 5 and exe_low.startswith(ndir):
                        detected_name = g["name"]
                        detected_state = "Active on EA App"
                        detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=EA_FALLBACK_LOGO)
                        break
                if detected_name:
                    break
                if "\\ea games\\" in exe_low or "\\origin games\\" in exe_low:
                    parts = p["exe"].split("\\")
                    for idx, part in enumerate(parts):
                        if part.lower() in ("ea games", "origin games") and idx + 1 < len(parts):
                            gfolder = "\\".join(parts[: idx + 2])
                            detected_name = self._parse_installer_xml(gfolder)
                            detected_state = "Active on EA App"
                            detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=EA_FALLBACK_LOGO)
                            break
                    if detected_name:
                        break

        if not detected_name:
            if self.state.ea_running:
                self.state.ea_running = False
                self.state.ea_game_name = ""
                self.state.ea_game_state = ""
                self.state.ea_game_icon = EA_FALLBACK_LOGO
                return True
            return False

        changed = (
            not self.state.ea_running
            or self.state.ea_game_name != detected_name
            or self.state.ea_game_state != detected_state
        )
        if not self.state.ea_running or self.state.ea_game_name != detected_name:
            self.state.ea_start_ts = int(time.time())
        self.state.ea_running = True
        self.state.ea_game_name = detected_name
        self.state.ea_game_state = detected_state
        self.state.ea_game_icon = detected_icon
        return changed

    def fetch_friends(self):
        friends = []
        seen = set()

        def add_f(name, status, online=False, in_game=False):
            clean = str(name or "").strip()
            if not clean or len(clean) < 2 or len(clean) > 32:
                return
            k = clean.lower()
            if k in seen or k in ("default", "unknown", "null", "none", "system", "ea", "eadesktop", "origin"):
                return
            seen.add(k)
            friends.append({"name": clean, "status": status, "online": online, "in_game": in_game})

        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        ea_log_dirs = [
            os.path.join(local_app, "ElectronicArts", "EA Desktop", "Logs"),
            os.path.join(local_app, "Origin", "Logs"),
        ]
        re_ea_friend = re.compile(r'"(?:personaName|displayName|friendPersona|eaId)"\s*:\s*"([A-Za-z0-9_\-]{3,24})"', re.I)
        for ldir in ea_log_dirs:
            if not os.path.exists(ldir):
                continue
            try:
                for fn in os.listdir(ldir)[:15]:
                    fpath = os.path.join(ldir, fn)
                    if not os.path.isfile(fpath) or os.path.getsize(fpath) > 1_500_000:
                        continue
                    try:
                        txt = open(fpath, "r", encoding="utf-8", errors="ignore").read()
                        for m in re_ea_friend.finditer(txt):
                            add_f(m.group(1), "EA App Friend (Local Cache)", online=self.state.ea_running)
                    except OSError:
                        pass
            except OSError:
                pass

        for item in _parse_str_list(Reg.get("EATrackedFriends", "")):
            add_f(item, "Active on EA App" if self.state.ea_running else "EA App Friend (Tracked)", online=self.state.ea_running)

        friends.sort(key=lambda x: (0 if x.get("in_game") else (1 if x.get("online") else 2), x["name"].lower()))
        self.state.ea_friends = friends
        return friends

    def add_tracked_friend(self, ea_id):
        eid = str(ea_id or "").strip()
        if not eid:
            return False
        tracked = _parse_str_list(Reg.get("EATrackedFriends", ""))
        if eid.lower() not in [x.lower() for x in tracked]:
            tracked.append(eid)
            Reg.set("EATrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def remove_tracked_friend(self, ea_id):
        eid = str(ea_id or "").strip().lower()
        tracked = [x for x in _parse_str_list(Reg.get("EATrackedFriends", "")) if x.lower() != eid]
        Reg.set("EATrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def link_account(self, ea_id):
        eid = str(ea_id or "").strip()
        if not eid:
            return False
        self.state.ea_account_name = eid
        Reg.set("EAAccountName", eid)
        self.fetch_friends()
        self.on_ui()
        self.on_push()
        return True

    def unlink(self):
        self.state.ea_account_name = ""
        Reg.remove("EAAccountName")
        self.on_ui()
        self.on_push()
        return True

    def detect_local_account(self):
        self.fetch_friends()
        if not self.state.ea_account_name and self.state.ea_friends:
            return self.link_account(self.state.ea_friends[0]["name"])
        return bool(self.state.ea_account_name)


class UbisoftClient:
    DEFAULT_KNOWN_PROCS = {
        "rainbowsix.exe": ("Tom Clancy's Rainbow Six Siege", "In Tactical Match / Operator Lobby", 359550),
        "rainbowsix_vulkan.exe": ("Tom Clancy's Rainbow Six Siege", "In Tactical Match / Lobby (Vulkan)", 359550),
        "rainbowsix_dx11.exe": ("Tom Clancy's Rainbow Six Siege", "In Tactical Match / Lobby (DirectX)", 359550),
        "xdefiant.exe": ("XDefiant", "In Arena Match • Ubisoft Connect", 0),
        "forhonor.exe": ("For Honor", "In Dominion / Duel Match", 304390),
        "thecrewmotorfest.exe": ("The Crew Motorfest", "In Oahu Open World", 2698940),
        "thecrew2.exe": ("The Crew 2", "In Open World Racing", 646910),
        "acmirage.exe": ("Assassin's Creed Mirage", "In Story Session", 3035570),
        "acvalhalla.exe": ("Assassin's Creed Valhalla", "In Story Session", 2208920),
        "acodyssey.exe": ("Assassin's Creed Odyssey", "In Story Session", 812140),
        "acorigins.exe": ("Assassin's Creed Origins", "In Story Session", 582160),
        "farcry6.exe": ("Far Cry 6", "In Campaign / Co-Op", 2369390),
        "farcry5.exe": ("Far Cry 5", "In Campaign / Co-Op", 552520),
        "watchdogslegion.exe": ("Watch Dogs: Legion", "In London Open World", 2239550),
        "ridersrepublic.exe": ("Riders Republic", "In Mass Race / Freeride", 2290180),
    }

    DEFAULT_INSTALL_IDS = {
        "635": "Tom Clancy's Rainbow Six Siege",
        "1843": "Tom Clancy's Rainbow Six Siege",
        "1844": "Tom Clancy's Rainbow Six Siege",
    }

    def __init__(self, state, xbox_helper, on_ui, on_push):
        self.state = state
        self.xbox_helper = xbox_helper
        self.on_ui = on_ui
        self.on_push = on_push
        self.scanned_once = False
        db_procs = CFG.games_db.get("ubisoft_known_procs") or {}
        self.KNOWN_PROCS = {k.lower(): tuple(v) for k, v in db_procs.items()} if db_procs else dict(self.DEFAULT_KNOWN_PROCS)
        self.KNOWN_INSTALL_IDS = CFG.games_db.get("ubisoft_install_ids") or dict(self.DEFAULT_INSTALL_IDS)

    def scan_installed_games(self):
        self.scanned_once = True
        games = []
        seen = set()

        def add_game(title, install_dir):
            title = (title or "").strip()
            install_dir = (install_dir or "").strip().replace("/", "\\")
            if not title or not install_dir or not os.path.exists(install_dir):
                return
            k = os.path.normcase(os.path.normpath(install_dir))
            if k in seen:
                return
            seen.add(k)
            games.append({"name": title, "install_dir": os.path.normpath(install_dir), "norm_dir": k})

        for root, flag, sub_path, sub_name in Reg.list_subkeys(r"SOFTWARE\Ubisoft\Launcher\Installs"):
            vals = Reg.read_key_dict(root, flag, sub_path)
            idir = str(vals.get("InstallDir") or "").strip().rstrip("\\/")
            if idir and os.path.exists(idir):
                gname = self.KNOWN_INSTALL_IDS.get(sub_name) or os.path.basename(idir)
                add_game(gname, idir)

        for drive in ("C:", "D:", "E:", "F:"):
            for rel in (
                "Program Files (x86)\\Ubisoft\\Ubisoft Game Launcher\\games",
                "Program Files\\Ubisoft\\Ubisoft Game Launcher\\games",
                "Ubisoft Games",
            ):
                base = os.path.join(drive + "\\", rel)
                if not os.path.exists(base):
                    continue
                try:
                    for sub in os.listdir(base):
                        full = os.path.join(base, sub)
                        if os.path.isdir(full):
                            add_game(sub, full)
                except OSError:
                    pass

        games.sort(key=lambda x: x["name"].lower())
        self.state.ubisoft_installed_games = games
        return games

    def poll(self, snapshot=None):
        if not self.scanned_once:
            self.scan_installed_games()

        if not self.state.ubisoft_enabled:
            if self.state.ubisoft_running:
                self.state.ubisoft_running = False
                self.state.ubisoft_game_name = ""
                self.state.ubisoft_game_state = ""
                return True
            return False

        if snapshot is not None:
            procs = snapshot[0]
        else:
            procs = []
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    exe = p.info.get("exe") or ""
                    procs.append({"name": (p.info.get("name") or "").lower(), "exe": exe, "exe_lower": exe.lower(), "has_visible_window": True})
                except Exception:
                    pass

        detected_name = ""
        detected_state = ""
        detected_icon = UBISOFT_FALLBACK_LOGO

        for p in procs:
            pname = p["name"]
            if not pname or pname in UBISOFT_IGNORE_PROCS:
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue
            if pname in self.KNOWN_PROCS:
                gname, gstate, steam_aid = self.KNOWN_PROCS[pname]
                detected_name = gname
                detected_state = gstate
                detected_icon = self.xbox_helper.resolve_cover_icon(
                    detected_name, fallback=UBISOFT_FALLBACK_LOGO, appid=steam_aid
                )
                break

        if not detected_name:
            for p in procs:
                pname = p["name"]
                exe_low = p["exe_lower"]
                if not pname or not exe_low or pname in UBISOFT_IGNORE_PROCS:
                    continue
                if snapshot is not None and not p.get("has_visible_window", False):
                    continue
                for g in self.state.ubisoft_installed_games:
                    ndir = g["norm_dir"]
                    if ndir and len(ndir) > 5 and exe_low.startswith(ndir):
                        detected_name = g["name"]
                        detected_state = "Active on Ubisoft Connect"
                        detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=UBISOFT_FALLBACK_LOGO)
                        break
                if detected_name:
                    break
                if "\\ubisoft game launcher\\games\\" in exe_low:
                    parts = p["exe"].split("\\")
                    for idx, part in enumerate(parts):
                        if part.lower() == "games" and idx + 1 < len(parts):
                            detected_name = parts[idx + 1]
                            detected_state = "Active on Ubisoft Connect"
                            detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=UBISOFT_FALLBACK_LOGO)
                            break
                    if detected_name:
                        break

        if not detected_name:
            if self.state.ubisoft_running:
                self.state.ubisoft_running = False
                self.state.ubisoft_game_name = ""
                self.state.ubisoft_game_state = ""
                self.state.ubisoft_game_icon = UBISOFT_FALLBACK_LOGO
                return True
            return False

        changed = (
            not self.state.ubisoft_running
            or self.state.ubisoft_game_name != detected_name
            or self.state.ubisoft_game_state != detected_state
        )
        if not self.state.ubisoft_running or self.state.ubisoft_game_name != detected_name:
            self.state.ubisoft_start_ts = int(time.time())
        self.state.ubisoft_running = True
        self.state.ubisoft_game_name = detected_name
        self.state.ubisoft_game_state = detected_state
        self.state.ubisoft_game_icon = detected_icon
        return changed

    def fetch_friends(self):
        friends = []
        seen = set()

        def add_f(name, status, online=False, in_game=False):
            clean = str(name or "").strip()
            if not clean or len(clean) < 2 or len(clean) > 32:
                return
            k = clean.lower()
            if k in seen or k in ("default", "unknown", "null", "none", "ubisoft", "uplay", "system"):
                return
            seen.add(k)
            friends.append({"name": clean, "status": status, "online": online, "in_game": in_game})

        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        ubi_dir = os.path.join(local_app, "Ubisoft Game Launcher")
        re_ubi_name = re.compile(r'"(?:nameOnPlatform|friendName|username|nickname)"\s*:\s*"([A-Za-z0-9_.\-]{3,24})"', re.I)
        if os.path.exists(ubi_dir):
            for rel in ("users.dat", os.path.join("logs", "launcher_log.txt")):
                fpath = os.path.join(ubi_dir, rel)
                if not os.path.exists(fpath):
                    continue
                try:
                    if os.path.getsize(fpath) > 2_000_000:
                        continue
                    txt = open(fpath, "r", encoding="utf-8", errors="ignore").read()
                    for m in re_ubi_name.finditer(txt):
                        add_f(m.group(1), "Ubisoft Connect Profile / Friend", online=self.state.ubisoft_running)
                except OSError:
                    pass

        for item in _parse_str_list(Reg.get("UbisoftTrackedFriends", "")):
            add_f(item, "Active on Ubisoft Connect" if self.state.ubisoft_running else "Ubisoft Friend (Tracked)", online=self.state.ubisoft_running)

        friends.sort(key=lambda x: (0 if x.get("in_game") else (1 if x.get("online") else 2), x["name"].lower()))
        self.state.ubisoft_friends = friends
        return friends

    def add_tracked_friend(self, ubi_name):
        uname = str(ubi_name or "").strip()
        if not uname:
            return False
        tracked = _parse_str_list(Reg.get("UbisoftTrackedFriends", ""))
        if uname.lower() not in [x.lower() for x in tracked]:
            tracked.append(uname)
            Reg.set("UbisoftTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def remove_tracked_friend(self, ubi_name):
        uname = str(ubi_name or "").strip().lower()
        tracked = [x for x in _parse_str_list(Reg.get("UbisoftTrackedFriends", "")) if x.lower() != uname]
        Reg.set("UbisoftTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def link_account(self, ubi_name):
        uname = str(ubi_name or "").strip()
        if not uname:
            return False
        self.state.ubisoft_username = uname
        Reg.set("UbisoftUsername", uname)
        self.fetch_friends()
        self.on_ui()
        self.on_push()
        return True

    def unlink(self):
        self.state.ubisoft_username = ""
        Reg.remove("UbisoftUsername")
        self.on_ui()
        self.on_push()
        return True

    def detect_local_account(self):
        self.fetch_friends()
        if not self.state.ubisoft_username and self.state.ubisoft_friends:
            return self.link_account(self.state.ubisoft_friends[0]["name"])
        return bool(self.state.ubisoft_username)


class GOGClient:
    def __init__(self, state, xbox_helper, on_ui, on_push):
        self.state = state
        self.xbox_helper = xbox_helper
        self.on_ui = on_ui
        self.on_push = on_push
        self.scanned_once = False

    @staticmethod
    def _parse_gog_info(folder):
        for info_file in glob.glob(os.path.join(folder, "goggame-*.info")):
            try:
                data = json.load(open(info_file, "r", encoding="utf-8", errors="ignore"))
                name = str(data.get("name") or "").strip()
                if name:
                    return name
            except Exception:
                pass
        return os.path.basename(folder.rstrip("\\/"))

    def scan_installed_games(self):
        self.scanned_once = True
        games = []
        seen = set()

        def add_game(title, install_dir, exe_path=""):
            title = (title or "").strip()
            install_dir = (install_dir or "").strip()
            if not title or not install_dir or not os.path.exists(install_dir):
                return
            k = os.path.normcase(os.path.normpath(install_dir))
            if k in seen:
                return
            seen.add(k)
            exe_name = os.path.basename(exe_path).lower() if exe_path else ""
            games.append({"name": title, "install_dir": os.path.normpath(install_dir), "norm_dir": k, "exe_name": exe_name})

        for root, flag, sub_path, sub_name in Reg.list_subkeys(r"SOFTWARE\GOG.com\Games"):
            vals = Reg.read_key_dict(root, flag, sub_path)
            gname = vals.get("gameName") or vals.get("GAMENAME") or sub_name
            gpath = vals.get("path") or vals.get("PATH") or vals.get("workingDir") or ""
            gexe = vals.get("exe") or vals.get("EXE") or ""
            if gpath:
                add_game(str(gname), str(gpath), str(gexe))

        for drive in ("C:", "D:", "E:", "F:"):
            for rel in ("GOG Games", "Program Files (x86)\\GOG Galaxy\\Games", "Program Files\\GOG Galaxy\\Games"):
                base = os.path.join(drive + "\\", rel)
                if not os.path.exists(base):
                    continue
                try:
                    for sub in os.listdir(base):
                        full = os.path.join(base, sub)
                        if os.path.isdir(full):
                            title = self._parse_gog_info(full)
                            add_game(title, full)
                except OSError:
                    pass

        games.sort(key=lambda x: x["name"].lower())
        self.state.gog_installed_games = games
        return games

    def poll(self, snapshot=None):
        if not self.scanned_once:
            self.scan_installed_games()

        if not self.state.gog_enabled:
            if self.state.gog_running:
                self.state.gog_running = False
                self.state.gog_game_name = ""
                self.state.gog_game_state = ""
                return True
            return False

        if snapshot is not None:
            procs = snapshot[0]
        else:
            procs = []
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    exe = p.info.get("exe") or ""
                    procs.append({"name": (p.info.get("name") or "").lower(), "exe": exe, "exe_lower": exe.lower(), "has_visible_window": True})
                except Exception:
                    pass

        detected_name = ""
        detected_state = ""
        detected_icon = GOG_FALLBACK_LOGO

        for p in procs:
            pname = p["name"]
            exe_low = p["exe_lower"]
            if not pname or pname in GOG_IGNORE_PROCS:
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue
            for g in self.state.gog_installed_games:
                ndir = g["norm_dir"]
                if (ndir and len(ndir) > 5 and exe_low.startswith(ndir)) or (
                    g["exe_name"] and pname == g["exe_name"] and exe_low.startswith(ndir)
                ):
                    detected_name = g["name"]
                    detected_state = "Playing on GOG Galaxy (DRM-Free)"
                    detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=GOG_FALLBACK_LOGO)
                    break
            if detected_name:
                break
            if "\\gog games\\" in exe_low or "\\gog galaxy\\games\\" in exe_low:
                parts = p["exe"].split("\\")
                for idx, part in enumerate(parts):
                    if part.lower() in ("gog games", "games") and idx + 1 < len(parts):
                        gfolder = "\\".join(parts[: idx + 2])
                        detected_name = self._parse_gog_info(gfolder)
                        detected_state = "Playing on GOG Galaxy"
                        detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=GOG_FALLBACK_LOGO)
                        break
                if detected_name:
                    break

        if not detected_name:
            if self.state.gog_running:
                self.state.gog_running = False
                self.state.gog_game_name = ""
                self.state.gog_game_state = ""
                self.state.gog_game_icon = GOG_FALLBACK_LOGO
                return True
            return False

        changed = (
            not self.state.gog_running
            or self.state.gog_game_name != detected_name
            or self.state.gog_game_state != detected_state
        )
        if not self.state.gog_running or self.state.gog_game_name != detected_name:
            self.state.gog_start_ts = int(time.time())
        self.state.gog_running = True
        self.state.gog_game_name = detected_name
        self.state.gog_game_state = detected_state
        self.state.gog_game_icon = detected_icon
        return changed

    def fetch_friends(self):
        friends = []
        seen = set()

        def add_f(name, status, online=False, in_game=False):
            clean = str(name or "").strip()
            if not clean or len(clean) < 2 or len(clean) > 32:
                return
            k = clean.lower()
            if k in seen or k in ("default", "unknown", "null", "none", "gog", "galaxy", "system"):
                return
            seen.add(k)
            friends.append({"name": clean, "status": status, "online": online, "in_game": in_game})

        prog_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        db_path = os.path.join(prog_data, "GOG.com", "Galaxy", "storage", "galaxy-2.0.db")
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.0)
                cur = conn.cursor()
                try:
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = {r[0].lower(): r[0] for r in cur.fetchall() if r and r[0]}
                    for tbl_key in ("users", "friends", "userpieces"):
                        if tbl_key in tables:
                            tname = tables[tbl_key]
                            cur.execute(f"SELECT * FROM {tname} LIMIT 40")
                            rows = cur.fetchall()
                            for row in rows:
                                for col in row:
                                    s_col = str(col or "")
                                    if '"username"' in s_col or '"name"' in s_col:
                                        m = re.search(r'"(?:username|name)"\s*:\s*"([^"]{2,28})"', s_col, re.I)
                                        if m:
                                            add_f(m.group(1), "GOG Galaxy Friend (Local DB)", online=self.state.gog_running)
                finally:
                    conn.close()
            except Exception:
                pass

        for item in _parse_str_list(Reg.get("GOGTrackedFriends", "")):
            add_f(item, "Active on GOG Galaxy" if self.state.gog_running else "GOG Galaxy Friend (Tracked)", online=self.state.gog_running)

        friends.sort(key=lambda x: (0 if x.get("in_game") else (1 if x.get("online") else 2), x["name"].lower()))
        self.state.gog_friends = friends
        return friends

    def add_tracked_friend(self, gog_name):
        gname = str(gog_name or "").strip()
        if not gname:
            return False
        tracked = _parse_str_list(Reg.get("GOGTrackedFriends", ""))
        if gname.lower() not in [x.lower() for x in tracked]:
            tracked.append(gname)
            Reg.set("GOGTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def remove_tracked_friend(self, gog_name):
        gname = str(gog_name or "").strip().lower()
        tracked = [x for x in _parse_str_list(Reg.get("GOGTrackedFriends", "")) if x.lower() != gname]
        Reg.set("GOGTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def link_account(self, gog_name):
        gname = str(gog_name or "").strip()
        if not gname:
            return False
        if "gog.com/u/" in gname.lower():
            gname = gname.rstrip("/").split("gog.com/u/")[-1].split("/")[0].split("?")[0]
        self.state.gog_username = gname
        Reg.set("GOGUsername", gname)
        self.fetch_friends()
        self.on_ui()
        self.on_push()
        return True

    def unlink(self):
        self.state.gog_username = ""
        Reg.remove("GOGUsername")
        self.on_ui()
        self.on_push()
        return True

    def detect_local_account(self):
        reg_user = Reg.get_any("username", "", path=r"Software\GOG.com\Galaxy\settings")
        if reg_user and str(reg_user).strip():
            return self.link_account(str(reg_user).strip())
        self.fetch_friends()
        if not self.state.gog_username and self.state.gog_friends:
            return self.link_account(self.state.gog_friends[0]["name"])
        return bool(self.state.gog_username)


class BattleNetClient:
    DEFAULT_KNOWN_EXES = {
        "cod.exe": "Call of Duty",
        "cod24-cod.exe": "Call of Duty: Black Ops 6",
        "cod23-cod.exe": "Call of Duty: Modern Warfare III",
        "cod22-cod.exe": "Call of Duty: Modern Warfare II",
        "blackopscoldwar.exe": "Call of Duty: Black Ops Cold War",
        "modernwarfare.exe": "Call of Duty: Modern Warfare",
        "vanguard.exe": "Call of Duty: Vanguard",
        "wow.exe": "World of Warcraft",
        "wowclassic.exe": "World of Warcraft Classic",
        "wowb.exe": "World of Warcraft (Beta)",
        "wowt.exe": "World of Warcraft (PTR)",
        "overwatch.exe": "Overwatch 2",
        "diablo iv.exe": "Diablo IV",
        "d2r.exe": "Diablo II: Resurrected",
        "diablo iii64.exe": "Diablo III",
        "diablo iii.exe": "Diablo III",
        "hearthstone.exe": "Hearthstone",
        "sc2_x64.exe": "StarCraft II",
        "sc2.exe": "StarCraft II",
        "starcraft.exe": "StarCraft: Remastered",
        "heroesofthestorm_x64.exe": "Heroes of the Storm",
        "heroesofthestorm.exe": "Heroes of the Storm",
        "warcraft iii.exe": "Warcraft III: Reforged",
        "crashbandicoot4.exe": "Crash Bandicoot 4",
        "blizzardarcadecollection.exe": "Blizzard Arcade Collection",
    }

    DEFAULT_PRODUCT_CODES = {
        "fenris": "Diablo IV",
        "pro": "Overwatch 2",
        "wow": "World of Warcraft",
        "wow_classic": "World of Warcraft Classic",
        "wow_classic_era": "World of Warcraft Classic Era",
        "wtcg": "Hearthstone",
        "s2": "StarCraft II",
        "s1": "StarCraft: Remastered",
        "hero": "Heroes of the Storm",
        "w3": "Warcraft III: Reforged",
        "d3": "Diablo III",
        "osi": "Diablo II: Resurrected",
        "auks": "Call of Duty",
        "odin": "Call of Duty: Modern Warfare",
        "zeus": "Call of Duty: Black Ops Cold War",
        "fore": "Call of Duty: Vanguard",
        "wlby": "Crash Bandicoot 4",
    }

    def __init__(self, state, xbox_helper, on_ui, on_push):
        self.state = state
        self.xbox_helper = xbox_helper
        self.on_ui = on_ui
        self.on_push = on_push
        self.scanned_once = False
        self.KNOWN_EXES = CFG.games_db.get("battlenet_known_exes") or dict(self.DEFAULT_KNOWN_EXES)
        self.PRODUCT_CODES = CFG.games_db.get("battlenet_product_codes") or dict(self.DEFAULT_PRODUCT_CODES)

    def _parse_build_info(self, folder):
        for fname in (".build.info", ".flavor.info"):
            fpath = os.path.join(folder, fname)
            if os.path.exists(fpath):
                try:
                    raw = open(fpath, "r", encoding="utf-8", errors="ignore").read().lower()
                    for code, title in self.PRODUCT_CODES.items():
                        if f"|{code}|" in raw or f"\n{code}\n" in raw or f" {code} " in raw:
                            return title
                except Exception:
                    pass
        base = os.path.basename(folder.rstrip("\\/"))
        if base.lower() in ("_retail_", "_classic_", "_classic_era_", "_ptr_", "_beta_"):
            parent = os.path.basename(os.path.dirname(folder.rstrip("\\/")))
            if parent:
                return parent
        return base

    def scan_installed_games(self):
        self.scanned_once = True
        games = []
        seen = set()

        def add_game(name, install_dir):
            if not name or not install_dir or not os.path.exists(install_dir):
                return
            clean_name = re.sub(r"\s+", " ", str(name)).strip()
            low_n = clean_name.lower()
            if not clean_name or low_n in ("battle.net", "blizzard battle.net", "blizzard agent", "agent"):
                return
            k = os.path.normcase(os.path.normpath(install_dir)).rstrip("\\")
            if k in seen:
                return
            seen.add(k)
            games.append({"name": clean_name, "install_dir": os.path.normpath(install_dir), "norm_dir": k})

        for reg_path in (
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ):
            for root, flag, sub_path, _ in Reg.list_subkeys(reg_path):
                vals = Reg.read_key_dict(root, flag, sub_path)
                pub = str(vals.get("Publisher") or "").lower()
                uninst = str(vals.get("UninstallString") or "").lower()
                dname = str(vals.get("DisplayName") or "").strip()
                iloc = str(vals.get("InstallLocation") or "").strip()
                if not dname or not iloc:
                    continue
                if "blizzard" in pub or "battle.net" in uninst or any(t.lower() in dname.lower() for t in self.PRODUCT_CODES.values()):
                    add_game(dname, iloc)

        appdata = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
        bnet_cfg = os.path.join(appdata, "Battle.net", "Battle.net.config")
        candidate_roots = []
        if os.path.exists(bnet_cfg):
            try:
                cfg_data = json.load(open(bnet_cfg, "r", encoding="utf-8", errors="ignore"))
                def_path = ((cfg_data.get("Client") or {}).get("Install") or {}).get("DefaultInstallPath")
                if def_path and os.path.exists(def_path):
                    candidate_roots.append(def_path)
            except Exception:
                pass

        prog_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        prod_db = os.path.join(prog_data, "Battle.net", "Agent", "product.db")
        if os.path.exists(prod_db):
            try:
                raw_bytes = open(prod_db, "rb").read()
                text_dump = raw_bytes.decode("utf-8", errors="ignore")
                for m in re.finditer(r"([A-Za-z]:[\\/][^\x00-\x1f\"<>|?*]{3,120})", text_dump):
                    p_cand = os.path.normpath(m.group(1).strip())
                    if os.path.isdir(p_cand) and os.path.exists(os.path.join(p_cand, ".build.info")):
                        gtitle = self._parse_build_info(p_cand)
                        add_game(gtitle, p_cand)
            except Exception:
                pass

        for drive in ("C:", "D:", "E:", "F:"):
            for rel in ("Program Files (x86)", "Program Files", "Games", "Battle.net", "Blizzard"):
                base = os.path.join(drive + "\\", rel)
                if os.path.exists(base):
                    candidate_roots.append(base)

        known_folders = (
            "Call of Duty",
            "World of Warcraft",
            "Overwatch",
            "Overwatch 2",
            "Diablo IV",
            "Diablo II Resurrected",
            "Diablo III",
            "Hearthstone",
            "StarCraft II",
            "StarCraft",
            "Heroes of the Storm",
            "Warcraft III",
        )
        for root_dir in candidate_roots:
            for kf in known_folders:
                full = os.path.join(root_dir, kf)
                if os.path.isdir(full):
                    title = "Overwatch 2" if kf == "Overwatch" else kf
                    add_game(title, full)
            try:
                for sub in os.listdir(root_dir):
                    full = os.path.join(root_dir, sub)
                    if os.path.isdir(full) and os.path.exists(os.path.join(full, ".build.info")):
                        add_game(self._parse_build_info(full), full)
            except OSError:
                pass

        games.sort(key=lambda x: x["name"].lower())
        self.state.battlenet_installed_games = games
        return games

    def poll(self, snapshot=None):
        if not self.scanned_once:
            self.scan_installed_games()

        if not self.state.battlenet_enabled:
            if self.state.battlenet_running:
                self.state.battlenet_running = False
                self.state.battlenet_game_name = ""
                self.state.battlenet_game_state = ""
                return True
            return False

        if snapshot is not None:
            procs, wins = snapshot[0], snapshot[2]
        else:
            procs, wins = [], []
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    exe = p.info.get("exe") or ""
                    procs.append(
                        {
                            "pid": p.info["pid"],
                            "name": (p.info.get("name") or "").lower(),
                            "exe": exe,
                            "exe_lower": exe.lower(),
                            "has_visible_window": True,
                        }
                    )
                except Exception:
                    pass

        detected_name = ""
        detected_state = ""
        matched_pid = None

        for p in procs:
            pname = p["name"]
            exe_low = p["exe_lower"]
            if not pname or pname in BATTLENET_IGNORE_PROCS:
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue

            if pname in self.KNOWN_EXES:
                if "steamapps" in exe_low or "windowsapps" in exe_low:
                    continue
                detected_name = self.KNOWN_EXES[pname]
                detected_state = "In Game • Battle.net"
                matched_pid = p.get("pid")
                break

            for g in self.state.battlenet_installed_games:
                ndir = g["norm_dir"]
                if ndir and len(ndir) > 5 and exe_low.startswith(ndir):
                    detected_name = g["name"]
                    detected_state = "In Game • Battle.net"
                    matched_pid = p.get("pid")
                    break
            if detected_name:
                break

            if exe_low and ("battle.net" in exe_low or "blizzard" in exe_low):
                exe_dir = os.path.dirname(p["exe"])
                parent_dir = os.path.dirname(exe_dir)
                for cdir in (exe_dir, parent_dir):
                    if cdir and os.path.exists(os.path.join(cdir, ".build.info")):
                        detected_name = self._parse_build_info(cdir)
                        detected_state = "In Game • Battle.net"
                        matched_pid = p.get("pid")
                        break
                if detected_name:
                    break

        if not detected_name:
            if self.state.battlenet_running:
                self.state.battlenet_running = False
                self.state.battlenet_game_name = ""
                self.state.battlenet_game_state = ""
                self.state.battlenet_game_icon = BATTLENET_FALLBACK_LOGO
                return True
            return False

        if matched_pid and wins:
            for w in wins:
                if w.get("pid") == matched_pid:
                    wtitle = (w.get("title") or "").strip()
                    if wtitle and len(wtitle) > 2 and wtitle.lower() != detected_name.lower():
                        clean_t = wtitle.replace(detected_name, "").strip(" -–—•|:")
                        if 2 <= len(clean_t) <= 38:
                            detected_state = f"{clean_t} • Battle.net"
                    break

        detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=BATTLENET_FALLBACK_LOGO)
        changed = (
            not self.state.battlenet_running
            or self.state.battlenet_game_name != detected_name
            or self.state.battlenet_game_state != detected_state
        )
        if not self.state.battlenet_running or self.state.battlenet_game_name != detected_name:
            self.state.battlenet_start_ts = int(time.time())
        self.state.battlenet_running = True
        self.state.battlenet_game_name = detected_name
        self.state.battlenet_game_state = detected_state
        self.state.battlenet_game_icon = detected_icon
        return changed

    def fetch_friends(self):
        friends = []
        seen = set()

        def add_f(name, status, online=False, in_game=False):
            clean = str(name or "").strip()
            if not clean or len(clean) < 2 or len(clean) > 32:
                return
            k = clean.lower()
            if k in seen or k in ("default", "unknown", "null", "none", "blizzard", "battlenet"):
                return
            seen.add(k)
            friends.append({"name": clean, "status": status, "online": online, "in_game": in_game})

        appdata = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
        bnet_cfg = os.path.join(appdata, "Battle.net", "Battle.net.config")
        if os.path.exists(bnet_cfg):
            try:
                raw = open(bnet_cfg, "r", encoding="utf-8", errors="ignore").read()
                for m in re.finditer(r"([A-Za-z0-9_]{2,18}#\d{3,6})", raw):
                    add_f(m.group(1), "Battle.net BattleTag (Local Cache)", online=self.state.battlenet_running)
            except Exception:
                pass

        for item in _parse_str_list(Reg.get("BattleNetTrackedFriends", "")):
            add_f(item, "Active on Battle.net" if self.state.battlenet_running else "Battle.net Friend (Pinned)", online=self.state.battlenet_running)

        friends.sort(key=lambda x: (0 if x.get("in_game") else (1 if x.get("online") else 2), x["name"].lower()))
        self.state.battlenet_friends = friends
        return friends

    def add_tracked_friend(self, btag):
        bname = str(btag or "").strip()
        if not bname:
            return False
        tracked = _parse_str_list(Reg.get("BattleNetTrackedFriends", ""))
        if bname.lower() not in [x.lower() for x in tracked]:
            tracked.append(bname)
            Reg.set("BattleNetTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def remove_tracked_friend(self, btag):
        bname = str(btag or "").strip().lower()
        tracked = [x for x in _parse_str_list(Reg.get("BattleNetTrackedFriends", "")) if x.lower() != bname]
        Reg.set("BattleNetTrackedFriends", json.dumps(tracked))
        self.fetch_friends()
        self.on_ui()
        return True

    def link_account(self, btag):
        bname = str(btag or "").strip()
        if not bname:
            return False
        self.state.battlenet_battletag = bname
        Reg.set("BattleNetBattleTag", bname)
        self.fetch_friends()
        self.on_ui()
        self.on_push()
        return True

    def unlink(self):
        self.state.battlenet_battletag = ""
        Reg.remove("BattleNetBattleTag")
        self.on_ui()
        self.on_push()
        return True

    def detect_local_account(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
        bnet_cfg = os.path.join(appdata, "Battle.net", "Battle.net.config")
        if os.path.exists(bnet_cfg):
            try:
                raw = open(bnet_cfg, "r", encoding="utf-8", errors="ignore").read()
                m_tag = re.search(r"([A-Za-z0-9_]{2,18}#\d{3,6})", raw)
                if m_tag:
                    return self.link_account(m_tag.group(1))
                cfg_json = json.loads(raw)
                saved_acc = ((cfg_json.get("Client") or {}).get("SavedAccountNames") or "").strip()
                if saved_acc:
                    first_acc = saved_acc.split(",")[0].strip()
                    if "@" in first_acc:
                        first_acc = first_acc.split("@")[0]
                    if first_acc:
                        return self.link_account(first_acc)
            except Exception:
                pass
        self.fetch_friends()
        if not self.state.battlenet_battletag and self.state.battlenet_friends:
            return self.link_account(self.state.battlenet_friends[0]["name"])
        return bool(self.state.battlenet_battletag)
