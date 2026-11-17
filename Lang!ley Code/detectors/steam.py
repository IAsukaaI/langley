import os
import re
import glob
import json
import time
import winreg
import subprocess
import webbrowser
import threading
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
import psutil
import requests
from core.config_manager import (
    Reg,
    HTTP_HEADERS,
    STEAM_REG_PATH,
    STEAM_ACTIVE_PATH,
    GSI_PORT,
    STEAM_FALLBACK_LOGO,
    STEAM_IGNORE_APPIDS,
)


class SteamGSIHandler(BaseHTTPRequestHandler):
    steam_client = None

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0 and self.steam_client:
                raw = self.rfile.read(length).decode("utf-8", errors="ignore")
                self.steam_client.handle_gsi_payload(json.loads(raw))
            self.send_response(200)
            self.end_headers()
        except Exception:
            try:
                self.send_response(200)
                self.end_headers()
            except Exception:
                pass

    def log_message(self, format, *args):
        return


class SteamClient:
    def __init__(self, state, on_ui, on_push):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push
        self.http = requests.Session()
        self.http.headers.update(HTTP_HEADERS)
        self.store_cache = {}
        self.local_manifest_cache = {}
        self.last_gsi_ts = 0.0
        self.gsi_server = None
        self.steam_path = self._find_steam_path()

    def _find_steam_path(self):
        p = Reg.get("SteamPath", "", path=STEAM_REG_PATH)
        if p and os.path.exists(p):
            return os.path.normpath(p)
        for cand in [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", os.path.expandvars(r"%ProgramFiles(x86)%\Steam")]:
            if os.path.exists(cand):
                return cand
        return ""

    def start_gsi_server(self):
        SteamGSIHandler.steam_client = self
        try:
            self.gsi_server = HTTPServer(("127.0.0.1", GSI_PORT), SteamGSIHandler)
            threading.Thread(target=self.gsi_server.serve_forever, daemon=True).start()
        except Exception:
            self.gsi_server = None

    def stop_gsi_server(self):
        if self.gsi_server:
            try:
                self.gsi_server.shutdown()
            except Exception:
                pass

    def launch_game(self, appid):
        appid = int(appid)
        if not self.steam_path:
            self.steam_path = self._find_steam_path()
        steam_exe = os.path.join(self.steam_path, "steam.exe") if self.steam_path else ""
        try:
            if steam_exe and os.path.exists(steam_exe):
                subprocess.Popen([steam_exe, "-applaunch", str(appid)])
                return True
        except Exception:
            pass
        try:
            os.startfile(f"steam://rungameid/{appid}")
            return True
        except Exception:
            try:
                webbrowser.open(f"steam://rungameid/{appid}")
                return True
            except Exception:
                return False

    def close_game(self, appid=None):
        target_id = int(appid or self.state.steam_appid or 0)
        install_dir = ""
        for g in self.state.steam_installed_games:
            if int(g["appid"]) == target_id:
                install_dir = g.get("install_dir") or ""
                break

        killed_any = False
        norm_dir = os.path.normcase(os.path.normpath(install_dir)) if install_dir else ""
        ignore_procs = {"steam.exe", "steamwebhelper.exe", "steamservice.exe", "gameoverlayui.exe", "steamerrorreporter.exe"}

        for p in psutil.process_iter(["pid", "name", "exe", "cwd"]):
            try:
                pname = (p.info.get("name") or "").lower()
                if pname in ignore_procs or "langley" in pname or "python" in pname:
                    continue
                exe = os.path.normcase(os.path.normpath(p.info.get("exe") or ""))
                cwd = os.path.normcase(os.path.normpath(p.info.get("cwd") or ""))
                if norm_dir and len(norm_dir) > 5 and (exe.startswith(norm_dir) or cwd.startswith(norm_dir)):
                    p.terminate()
                    killed_any = True
            except Exception:
                pass

        if not killed_any:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if (p.info.get("name") or "").lower() == "steam.exe":
                        for child in p.children(recursive=True):
                            if child.name().lower() not in ignore_procs:
                                child.terminate()
                                killed_any = True
                except Exception:
                    pass

        if killed_any:
            self.state.steam_running = False
            self.state.steam_appid = 0
            self.state.steam_game_name = ""
            self.state.steam_gsi_text = ""
            self.on_ui()
            self.on_push()
        return killed_any

    def link_manual_steam(self, raw_input):
        val = str(raw_input or "").strip().rstrip("/")
        if not val:
            return False
        if "steamcommunity.com/openid/id/" in val:
            val = val.split("steamcommunity.com/openid/id/")[-1].split("/")[0].split("?")[0]
        elif "steamcommunity.com/profiles/" in val:
            val = val.split("steamcommunity.com/profiles/")[-1].split("/")[0].split("?")[0]
        elif "steamcommunity.com/id/" in val:
            val = val.split("steamcommunity.com/id/")[-1].split("/")[0].split("?")[0]

        sid64 = val if (val.isdigit() and len(val) == 17 and val.startswith("7656")) else ""
        sname = ""
        try:
            url = f"https://steamcommunity.com/profiles/{val}/?xml=1" if val.isdigit() else f"https://steamcommunity.com/id/{val}/?xml=1"
            r = self.http.get(url, timeout=4.5)
            if r.status_code == 200 and "<steamID64>" in r.text:
                root = ET.fromstring(r.text)
                sid64 = (root.findtext("steamID64") or sid64).strip()
                sname = (root.findtext("steamID") or "").strip()
        except Exception:
            pass

        if sid64:
            if not sname:
                # Check local loginusers.vdf for persona name if profile XML is private
                if self.steam_path:
                    vdf = os.path.join(self.steam_path, "config", "loginusers.vdf")
                    if os.path.exists(vdf):
                        try:
                            txt = open(vdf, "r", encoding="utf-8", errors="ignore").read()
                            m_b = re.search(rf'"{re.escape(sid64)}"\s*\{{([^\}}]+)\}}', txt)
                            if m_b:
                                m_p = re.search(r'"PersonaName"\s+"([^"]+)"', m_b.group(1))
                                if m_p:
                                    sname = m_p.group(1).strip()
                        except OSError:
                            pass
            self.state.steam_id64 = sid64
            self.state.steam_user_name = sname or self.state.steam_user_name or f"Steam ({sid64[-6:]})"
            self.state.steam_manual_override = True
            Reg.set("SteamID64", self.state.steam_id64)
            Reg.set("SteamPersona", self.state.steam_user_name)
            Reg.set("SteamManualOverride", 1, winreg.REG_DWORD)
            self.fetch_steam_friends()
            self.on_ui()
            self.on_push()
            return True
        return False

    def unlink_steam(self):
        Reg.set("SteamManualOverride", 1, winreg.REG_DWORD)
        Reg.remove("SteamID64")
        Reg.remove("SteamPersona")
        self.state.steam_manual_override = True
        self.state.steam_id64 = ""
        self.state.steam_user_name = ""
        self.state.steam_friends = []
        self.on_ui()
        self.on_push()

    def reset_steam_account(self):
        Reg.set("SteamManualOverride", 0, winreg.REG_DWORD)
        Reg.remove("SteamID64")
        Reg.remove("SteamPersona")
        self.state.steam_manual_override = False
        self.state.steam_id64 = ""
        self.state.steam_user_name = ""
        self.detect_local_steam_user()
        self.fetch_steam_friends()
        self.on_ui()
        self.on_push()

    def handle_gsi_payload(self, data):
        if not isinstance(data, dict):
            return
        now = time.time()
        self.last_gsi_ts = now
        self.state.steam_gsi_active = True
        provider = data.get("provider") or {}
        appid = int(provider.get("appid") or 0)
        summary = ""
        if appid == 730 or ("map" in data and "round" in data):
            appid = appid or 730
            mp, pl = data.get("map") or {}, data.get("player") or {}
            m_name = mp.get("name", "")
            m_mode = mp.get("mode", "Competitive").title()
            ct_score = (mp.get("team_ct") or {}).get("score", 0)
            t_score = (mp.get("team_t") or {}).get("score", 0)
            stats = pl.get("match_stats") or {}
            k, a, d = stats.get("kills", 0), stats.get("assists", 0), stats.get("deaths", 0)
            summary = f"{m_name} ({m_mode}) • {ct_score}:{t_score} • {k}K/{a}A/{d}D" if m_name else "In Lobby / Main Menu"
        elif appid == 570 or ("hero" in data and "player" in data):
            appid = appid or 570
            mp, pl, hero = data.get("map") or {}, data.get("player") or {}, data.get("hero") or {}
            h_name = str(hero.get("name") or "").replace("npc_dota_hero_", "").replace("_", " ").title()
            h_lvl = hero.get("level", 1)
            k, d, a = pl.get("kills", 0), pl.get("deaths", 0), pl.get("assists", 0)
            if h_name:
                summary = f"{h_name} (Lv.{h_lvl}) • {k}/{d}/{a} KDA"
            elif mp.get("game_state"):
                summary = str(mp.get("game_state")).split("_")[-1].title()

        meta_changed = False
        if appid in (730, 570) and (not self.state.steam_running or self.state.steam_appid != appid):
            gname, gicon, ggenre = self.resolve_game_metadata(appid)
            self.state.steam_running = True
            self.state.steam_appid = appid
            self.state.steam_game_name = gname
            self.state.steam_game_icon = gicon
            self.state.steam_genre = ggenre
            self.state.steam_start_ts = int(now)
            meta_changed = True

        if (summary and summary != self.state.steam_gsi_text) or meta_changed:
            if summary:
                self.state.steam_gsi_text = summary
            self.on_ui()
            self.on_push()

    def get_library_folders(self):
        if not self.steam_path:
            self.steam_path = self._find_steam_path()
        if not self.steam_path:
            return []
        folders = [self.steam_path]
        vdf = os.path.join(self.steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            try:
                txt = open(vdf, "r", encoding="utf-8", errors="ignore").read()
                for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
                    p = m.group(1).replace("\\\\", "\\")
                    if os.path.exists(p) and p not in folders:
                        folders.append(p)
            except OSError:
                pass
        return folders

    def scan_installed_games(self):
        games, seen = [], {}
        self.gsi_candidate_dirs = {730: [], 570: []}
        for lib in self.get_library_folders():
            sapps = os.path.join(lib, "steamapps")
            if not os.path.exists(sapps):
                continue
            for acf in glob.glob(os.path.join(sapps, "appmanifest_*.acf")):
                try:
                    txt = open(acf, "r", encoding="utf-8", errors="ignore").read()
                    m_id = re.search(r'"appid"\s+"(\d+)"', txt)
                    m_name = re.search(r'"name"\s+"([^"]+)"', txt)
                    m_dir = re.search(r'"installdir"\s+"([^"]+)"', txt)
                    if not m_id or not m_name:
                        continue
                    aid, name = int(m_id.group(1)), m_name.group(1).strip()
                    if aid in STEAM_IGNORE_APPIDS or "redistributable" in name.lower() or "proton" in name.lower():
                        continue
                    install_dir = os.path.join(sapps, "common", m_dir.group(1)) if m_dir else ""
                    if aid in self.gsi_candidate_dirs and install_dir and install_dir not in self.gsi_candidate_dirs[aid]:
                        self.gsi_candidate_dirs[aid].append(install_dir)
                    self.local_manifest_cache[aid] = name
                    if aid in seen:
                        # Prefer an existing install directory over an empty staging entry
                        idx = seen[aid]
                        if install_dir and os.path.exists(install_dir) and not os.path.exists(games[idx].get("install_dir") or ""):
                            games[idx]["install_dir"] = install_dir
                        continue
                    seen[aid] = len(games)
                    games.append({"appid": aid, "name": name, "install_dir": install_dir})
                except OSError:
                    pass
            # Also probe standard CS2 / Dota 2 directories in each library even if manifest is partial
            for fallback_aid, folder in ((730, "Counter-Strike Global Offensive"), (570, "dota 2 beta")):
                cdir = os.path.join(sapps, "common", folder)
                if os.path.exists(cdir) and cdir not in self.gsi_candidate_dirs[fallback_aid]:
                    self.gsi_candidate_dirs[fallback_aid].append(cdir)
        games.sort(key=lambda x: x["name"].lower())
        self.state.steam_installed_games = games
        self.install_gsi_configs(_from_scan=True)
        return games

    def detect_local_steam_user(self):
        if self.state.steam_manual_override and self.state.steam_id64:
            return False
        if not self.steam_path:
            self.steam_path = self._find_steam_path()
        if not self.steam_path:
            return False

        changed = False
        active_u32 = Reg.get("ActiveUser", 0, path=STEAM_ACTIVE_PATH)
        if active_u32 and int(active_u32) > 0:
            calc_id64 = str(int(active_u32) + 76561197960265728)
            if calc_id64 != self.state.steam_id64:
                self.state.steam_id64 = calc_id64
                Reg.set("SteamID64", calc_id64)
                changed = True

        vdf = os.path.join(self.steam_path, "config", "loginusers.vdf")
        if os.path.exists(vdf):
            try:
                txt = open(vdf, "r", encoding="utf-8", errors="ignore").read()
                blocks = re.findall(r'"(7656\d{13})"\s*\{([^\}]+)\}', txt)
                chosen_id, chosen_name = None, None
                for sid, body in blocks:
                    m_p = re.search(r'"PersonaName"\s+"([^"]+)"', body)
                    m_r = re.search(r'"MostRecent"\s+"1"', body)
                    pname = m_p.group(1) if m_p else ""
                    if m_r or not chosen_id:
                        chosen_id, chosen_name = sid, pname
                    if self.state.steam_id64 == sid and pname:
                        chosen_id, chosen_name = sid, pname
                        break
                if chosen_id and not self.state.steam_id64:
                    self.state.steam_id64 = chosen_id
                    Reg.set("SteamID64", chosen_id)
                    changed = True
                if chosen_name and chosen_name != self.state.steam_user_name:
                    self.state.steam_user_name = chosen_name
                    Reg.set("SteamPersona", chosen_name)
                    changed = True
            except OSError:
                pass
        return changed

    def fetch_steam_friends(self):
        friends_map = {}
        if self.steam_path:
            vdfs = glob.glob(os.path.join(self.steam_path, "userdata", "*", "config", "localconfig.vdf"))
            if vdfs:
                latest_vdf = max(vdfs, key=os.path.getmtime)
                try:
                    txt = open(latest_vdf, "r", encoding="utf-8", errors="ignore").read()
                    for m in re.finditer(r'"(\d{6,10})"\s*\{\s*"name"\s+"([^"]+)"', txt):
                        acc_id, fname = int(m.group(1)), m.group(2).strip()
                        if fname and acc_id > 1000:
                            sid64 = str(acc_id + 76561197960265728)
                            if sid64 != self.state.steam_id64:
                                friends_map[sid64] = {
                                    "id": sid64,
                                    "name": fname,
                                    "online": False,
                                    "in_game": False,
                                    "status": "Steam Friend",
                                }
                except Exception:
                    pass

        sid = self.state.steam_id64
        if sid:
            try:
                r = self.http.get(f"https://steamcommunity.com/profiles/{sid}/friends/?xml=1", timeout=4.0)
                if r.status_code == 200 and "<friends>" in r.text:
                    root = ET.fromstring(r.text)
                    xml_ids = [el.text.strip() for el in root.findall(".//friend") if el.text]
                    for xid in xml_ids[:24]:
                        if xid not in friends_map:
                            friends_map[xid] = {
                                "id": xid,
                                "name": f"Steam User ({xid[-4:]})",
                                "online": False,
                                "in_game": False,
                                "status": "Offline",
                            }
            except Exception:
                pass

        for fid in list(friends_map.keys())[:18]:
            try:
                pr = self.http.get(f"https://steamcommunity.com/profiles/{fid}/?xml=1", timeout=2.2)
                if pr.status_code == 200 and "<steamID>" in pr.text:
                    proot = ET.fromstring(pr.text)
                    pname = (proot.findtext("steamID") or "").strip()
                    ostate = (proot.findtext("onlineState") or "").strip().lower()
                    smsg = re.sub(r"<[^>]+>", " ", proot.findtext("stateMessage") or "").strip()
                    if pname:
                        friends_map[fid]["name"] = pname
                    if ostate == "in-game":
                        friends_map[fid]["online"] = True
                        friends_map[fid]["in_game"] = True
                        friends_map[fid]["status"] = smsg or "In-Game on Steam"
                    elif ostate == "online":
                        friends_map[fid]["online"] = True
                        friends_map[fid]["status"] = "Online on Steam"
                    else:
                        friends_map[fid]["status"] = smsg if smsg else "Offline"
            except Exception:
                pass

        self.state.steam_friends = sorted(
            friends_map.values(),
            key=lambda x: (0 if x.get("in_game") else (1 if x.get("online") else 2), x["name"].lower()),
        )
        self.on_ui()
        return True

    def fetch_public_profile(self):
        sid = self.state.steam_id64
        if not sid:
            return False
        try:
            r = self.http.get(f"https://steamcommunity.com/profiles/{sid}/?xml=1", timeout=4.0)
            if r.status_code != 200:
                return False
            root = ET.fromstring(r.text)
            steam_id_el = root.find("steamID")
            state_msg_el = root.find("stateMessage")
            changed = False
            if steam_id_el is not None and steam_id_el.text:
                pname = steam_id_el.text.strip()
                if pname and pname != self.state.steam_user_name:
                    self.state.steam_user_name = pname
                    Reg.set("SteamPersona", pname)
                    changed = True
            if state_msg_el is not None and state_msg_el.text:
                smsg = re.sub(r"<[^>]+>", " ", state_msg_el.text).strip()
                if "In-Game" in smsg and not self.state.steam_gsi_text:
                    self.state.steam_rich_text = smsg
            return changed
        except Exception:
            return False

    def resolve_game_metadata(self, appid):
        appid = int(appid)
        if appid in self.store_cache:
            return self.store_cache[appid]
        fallback_name = self.local_manifest_cache.get(appid) or f"Steam Game ({appid})"
        cdn_header = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
        genre_label = "Steam Game"
        try:
            r = self.http.get("https://store.steampowered.com/api/appdetails", params={"appids": appid, "l": "english"}, timeout=4.0)
            if r.status_code == 200:
                payload = (r.json() or {}).get(str(appid)) or {}
                if payload.get("success") and isinstance(payload.get("data"), dict):
                    d = payload["data"]
                    fallback_name = d.get("name") or fallback_name
                    hdr = str(d.get("header_image") or "").split("?")[0]
                    if hdr.startswith("http"):
                        cdn_header = hdr
                    genres = d.get("genres") or []
                    if genres and isinstance(genres[0], dict):
                        genre_label = genres[0].get("description") or genre_label
        except Exception:
            pass
        meta = (fallback_name, cdn_header, genre_label)
        self.store_cache[appid] = meta
        return meta

    def poll_running_game(self):
        self.detect_local_steam_user()
        if time.time() - self.last_gsi_ts > 120.0 and self.state.steam_gsi_active:
            self.state.steam_gsi_active = False
            self.state.steam_gsi_text = ""

        raw_appid = Reg.get("RunningAppID", 0, path=STEAM_REG_PATH)
        appid = int(raw_appid or 0)
        if appid in STEAM_IGNORE_APPIDS:
            appid = 0

        if appid <= 0 and self.state.steam_running and self.state.steam_appid in (730, 570):
            target_exe = "cs2.exe" if self.state.steam_appid == 730 else "dota2.exe"
            try:
                if any((p.info.get("name") or "").lower() == target_exe for p in psutil.process_iter(["name"])):
                    appid = self.state.steam_appid
            except Exception:
                pass
            if appid <= 0 and self.state.steam_gsi_active and (time.time() - self.last_gsi_ts < 20.0):
                appid = self.state.steam_appid

        if appid <= 0:
            if self.state.steam_running:
                self.state.steam_running = False
                self.state.steam_appid = 0
                self.state.steam_game_name = ""
                self.state.steam_gsi_text = ""
                self.state.steam_gsi_active = False
                return True
            return False

        changed = False
        if not self.state.steam_running or self.state.steam_appid != appid:
            if not self.local_manifest_cache:
                self.scan_installed_games()
            if appid in (730, 570):
                self.install_gsi_configs(_from_scan=True)
            gname, gicon, ggenre = self.resolve_game_metadata(appid)
            self.state.steam_running = True
            self.state.steam_appid = appid
            self.state.steam_game_name = gname
            self.state.steam_game_icon = gicon
            self.state.steam_genre = ggenre
            self.state.steam_start_ts = int(time.time())
            self.state.steam_gsi_text = ""
            changed = True
        return changed

    @staticmethod
    def _write_cfg_if_needed(cfg_file, cfg_content):
        if os.path.exists(cfg_file):
            try:
                if open(cfg_file, "r", encoding="utf-8", errors="ignore").read() == cfg_content:
                    return True
            except OSError:
                pass
        with open(cfg_file, "w", encoding="utf-8") as f:
            f.write(cfg_content)
        return True

    def install_gsi_configs(self, _from_scan=False):
        if not _from_scan and (not self.state.steam_installed_games or not hasattr(self, "gsi_candidate_dirs")):
            self.scan_installed_games()
            return list(self.state.steam_gsi_configured_games)
        cfg_content = f'''"Langley Discord RPC Integration"
{{
    "uri" "http://127.0.0.1:{GSI_PORT}"
    "timeout" "15.0"
    "buffer"  "0.1"
    "throttle" "0.5"
    "heartbeat" "5.0"
    "data"
    {{
        "provider"            "1"
        "map"                 "1"
        "round"               "1"
        "player_id"           "1"
        "player_state"        "1"
        "player_match_stats"  "1"
        "hero"                "1"
    }}
}}
'''
        installed_targets = []
        cand_dirs_730 = list(getattr(self, "gsi_candidate_dirs", {}).get(730, []))
        cand_dirs_570 = list(getattr(self, "gsi_candidate_dirs", {}).get(570, []))
        for g in self.state.steam_installed_games:
            if g["appid"] == 730 and g.get("install_dir") and g["install_dir"] not in cand_dirs_730:
                cand_dirs_730.append(g["install_dir"])
            elif g["appid"] == 570 and g.get("install_dir") and g["install_dir"] not in cand_dirs_570:
                cand_dirs_570.append(g["install_dir"])

        for idir in cand_dirs_730:
            if not idir or not os.path.exists(idir):
                continue
            for sub in [os.path.join(idir, "game", "csgo", "cfg"), os.path.join(idir, "csgo", "cfg")]:
                if os.path.exists(os.path.dirname(sub)):
                    try:
                        os.makedirs(sub, exist_ok=True)
                        self._write_cfg_if_needed(os.path.join(sub, "gamestate_integration_langley.cfg"), cfg_content)
                        if "Counter-Strike 2" not in installed_targets:
                            installed_targets.append("Counter-Strike 2")
                        break
                    except OSError:
                        pass

        for idir in cand_dirs_570:
            if not idir or not os.path.exists(idir):
                continue
            for sub in [
                os.path.join(idir, "game", "dota", "cfg", "gamestate_integration"),
                os.path.join(idir, "dota", "cfg", "gamestate_integration"),
            ]:
                if os.path.exists(os.path.dirname(os.path.dirname(sub))):
                    try:
                        os.makedirs(sub, exist_ok=True)
                        self._write_cfg_if_needed(os.path.join(sub, "gamestate_integration_langley.cfg"), cfg_content)
                        if "Dota 2" not in installed_targets:
                            installed_targets.append("Dota 2")
                        break
                    except OSError:
                        pass
        self.state.steam_gsi_configured_games = installed_targets
        return installed_targets
