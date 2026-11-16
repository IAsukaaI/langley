import os
import re
import glob
import json
import time
import winreg
import webbrowser
import threading
import psutil
import requests
from core.config_manager import (
    CFG,
    Reg,
    HTTP_HEADERS,
    FALLBACK_LOGO,
    EPIC_IGNORE_PROCS,
    OAUTH_URL,
    PARTY_URL,
    MCP_URL,
    FRIENDS_URL,
    PRESENCE_URL,
    SWITCH_BASIC,
    ANDROID_BASIC,
)
from core.rpc import _parse_str_list

DEFAULT_MODES = {
    "nobuildbr_habanero": "Ranked Zero Build",
    "nobuildbr_solo": "Zero Build • Solo",
    "nobuildbr_duo": "Zero Build • Duos",
    "nobuildbr_trio": "Zero Build • Trios",
    "nobuildbr_squad": "Zero Build • Squads",
    "defaultsolo": "Battle Royale • Solo",
    "defaultduo": "Battle Royale • Duos",
    "defaulttrio": "Battle Royale • Trios",
    "defaultsquad": "Battle Royale • Squads",
    "habanero": "Ranked Battle Royale",
    "punchberry": "Fortnite Reload",
    "lightbunny": "Reload Zero Build",
    "figment": "Fortnite OG",
    "ballistic": "Ballistic",
    "playgroundv2": "Creative",
    "creative": "Creative",
    "respawn": "Team Rumble",
    "delmar": "Rocket Racing",
    "sparks": "Fortnite Festival",
    "juno": "LEGO Fortnite",
}

MODES = CFG.games_db.get("fortnite_modes") or DEFAULT_MODES
SKIP_MODES = {"sprout", "none", "null", "front", "default", "prelobby"}

FN_EXES = {
    "fortniteclient-win64-shipping.exe",
    "fortniteclient-win64-shipping_eac.exe",
    "fortniteclient-win64-shipping_be.exe",
    "fortniteclient-win64-shipping_eac_eos.exe",
    "fortnite.exe",
    "fortnitelauncher.exe",
}


def is_fn_proc(proc_entry):
    pname = (proc_entry.get("name") or "").lower()
    exe_low = (proc_entry.get("exe_lower") or "").lower()
    if pname.startswith("fortniteclient-") or pname in FN_EXES:
        return True
    if pname == "gamelaunchhelper.exe" and "\\fortnite" in exe_low:
        return True
    return False


def get_log_path():
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
    user_prof = os.path.expanduser("~")
    candidates = [
        os.path.join(local, "FortniteGame", "Saved", "Logs", "FortniteGame.log"),
        os.path.join(user_prof, "Saved Games", "FortniteGame", "Saved", "Logs", "FortniteGame.log"),
    ]
    for pattern in (
        os.path.join(local, "Packages", "*", "LocalCache", "Local", "FortniteGame", "Saved", "Logs", "FortniteGame.log"),
        os.path.join(local, "Packages", "*", "LocalState", "FortniteGame", "Saved", "Logs", "FortniteGame.log"),
        os.path.join(local, "Packages", "*", "AC", "Temp", "FortniteGame", "Saved", "Logs", "FortniteGame.log"),
    ):
        candidates.extend(glob.glob(pattern))
    existing = [p for p in candidates if os.path.exists(p)]
    return max(existing, key=os.path.getmtime) if existing else candidates[0]


def enable_log_flags():
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
    dirs = [os.path.join(local, "FortniteGame", "Saved", "Config")]
    dirs.extend(glob.glob(os.path.join(local, "Packages", "*", "LocalCache", "Local", "FortniteGame", "Saved", "Config")))
    dirs.extend(glob.glob(os.path.join(local, "Packages", "*", "LocalState", "FortniteGame", "Saved", "Config")))
    flags = [
        "LogParty=Verbose",
        "LogOnlinePresence=Verbose",
        "LogRichPresence=Verbose",
        "LogFort=Log",
        "LogAthena=Log",
        "LogMCP=Log",
    ]
    for d in dirs:
        for sub in ("WindowsClient", "WinGDK", "WinGDKClient"):
            target = os.path.join(d, sub)
            if not (os.path.exists(target) or os.path.exists(d)):
                continue
            ini = os.path.join(target, "Engine.ini")
            try:
                os.makedirs(target, exist_ok=True)
                txt = open(ini, "r", encoding="utf-8", errors="ignore").read() if os.path.exists(ini) else ""
                if "[Core.Log]" not in txt:
                    with open(ini, "a", encoding="utf-8") as f:
                        f.write("\n[Core.Log]\n" + "\n".join(flags) + "\n")
                else:
                    missing = [line for line in flags if line not in txt]
                    if missing:
                        txt = txt.replace("[Core.Log]", "[Core.Log]\n" + "\n".join(missing), 1)
                        with open(ini, "w", encoding="utf-8") as f:
                            f.write(txt)
            except OSError:
                pass


def parse_mode(raw):
    if not raw:
        return None
    s = raw.lower().replace("playlist_", "").strip()
    if not s or s in SKIP_MODES or "sprout" in s:
        return None
    for k, label in MODES.items():
        if k in s:
            if "solo" in s and "Solo" not in label:
                return f"{label} • Solo"
            if "duo" in s and "Duos" not in label:
                return f"{label} • Duos"
            if "trio" in s and "Trios" not in label:
                return f"{label} • Trios"
            if "squad" in s and "Squads" not in label:
                return f"{label} • Squads"
            return label
    out = s.replace("_", " ").title()
    return out if out else None


class Cosmetics:
    BASE = "https://fortnite-api.com/v2/cosmetics/br"
    LOCAL_OVERRIDES = {
        "teto": ("Kasane Teto", FALLBACK_LOGO),
        "kasaneteto": ("Kasane Teto", FALLBACK_LOGO),
        "miku": ("Hatsune Miku", FALLBACK_LOGO),
    }

    def __init__(self):
        self.cache = dict(self.LOCAL_OVERRIDES)

    @staticmethod
    def clean_id(raw):
        s = raw.replace("\\", "").replace('"', "").replace("'", "").strip()
        return s.split(":")[-1].split("/")[-1].split(".")[0].strip().lower()

    def get_id(self, cid):
        cid = self.clean_id(cid)
        if not cid or len(cid) < 4:
            return None
        if cid in self.cache:
            return self.cache[cid]
        for key, val in self.LOCAL_OVERRIDES.items():
            if key in cid:
                self.cache[cid] = val
                return val

        fb = f"https://fortnite-api.com/images/cosmetics/br/{cid}/icon.png"
        try:
            r = requests.get(f"{self.BASE}/{cid}", params={"language": "en"}, headers=HTTP_HEADERS, timeout=3.5)
            if r.status_code == 200:
                d = r.json().get("data") or {}
                name = d.get("name") or "Fortnite Outfit"
                imgs = d.get("images") or {}
                icon = imgs.get("icon") or imgs.get("smallIcon") or imgs.get("featured") or fb
                self.cache[cid] = (name, icon)
                return name, icon
        except requests.RequestException:
            pass

        clean_name = cid
        for prefix in ["cid_", "character_", "athenacharacter_"]:
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):]
        parts = clean_name.split("_")
        if parts:
            candidate = parts[-1]
            if candidate.lower() in ("m", "f", "male", "female", "def", "default") and len(parts) > 1:
                candidate = parts[-2]
            parsed_name = candidate.replace("_", " ").title()
            if len(parsed_name) >= 2:
                res = (parsed_name, fb)
                self.cache[cid] = res
                return res

        res = ("Kasane Teto" if "teto" in cid else "Fortnite Outfit", fb)
        self.cache[cid] = res
        return res

    def get_name(self, name):
        k = name.strip().lower()
        if k in self.cache:
            return self.cache[k]
        for key, val in self.LOCAL_OVERRIDES.items():
            if key in k:
                return val
        try:
            r = requests.get(f"{self.BASE}/search", params={"name": name.strip(), "language": "en"}, headers=HTTP_HEADERS, timeout=3.5)
            if r.status_code == 200:
                d = r.json().get("data") or {}
                n = d.get("name") or name
                imgs = d.get("images") or {}
                icon = imgs.get("icon") or imgs.get("smallIcon") or ""
                if icon:
                    self.cache[k] = (n, icon)
                    return n, icon
        except requests.RequestException:
            pass
        res = (name.strip().title(), FALLBACK_LOGO)
        self.cache[k] = res
        return res


class EpicClient:
    TAG_1 = "urn:epic:member:langley_s"
    TAG_2 = "Default:LangleyUser_s"

    DEFAULT_KNOWN_PROCS = {
        "rocketleague.exe": ("Rocket League", "In Soccar Match / Arena", 252950),
        "fallguys_client_game.exe": ("Fall Guys", "In Blunderdome Show", 1097150),
        "fallguys_client.exe": ("Fall Guys", "In Blunderdome Show", 1097150),
        "alanwake2.exe": ("Alan Wake 2", "In Bright Falls / The Dark Place", 0),
        "gtav.exe": ("Grand Theft Auto V", "In Los Santos / GTA Online", 271590),
        "playgtav.exe": ("Grand Theft Auto V", "In Los Santos / GTA Online", 271590),
        "deadbydaylight-egs-shipping.exe": ("Dead by Daylight", "In Trial • The Fog", 381210),
        "deadbydaylight-win64-shipping.exe": ("Dead by Daylight", "In Trial • The Fog", 381210),
        "rdr2.exe": ("Red Dead Redemption 2", "In Story / Red Dead Online", 1174180),
        "borderlands3.exe": ("Borderlands 3", "In Vault Hunter Session", 397540),
        "wonderlands.exe": ("Tiny Tina's Wonderlands", "In Bunkers & Badasses", 1286680),
        "subnautica.exe": ("Subnautica", "In 4546B Ocean Survival", 264710),
        "subnauticazero.exe": ("Subnautica: Below Zero", "In Planet 4546B", 848450),
        "factorygame-win64-shipping.exe": ("Satisfactory", "Building Factory", 526870),
        "satisfactory.exe": ("Satisfactory", "Building Factory", 526870),
        "sifu-win64-shipping.exe": ("Sifu", "In Martial Arts Combat", 2138710),
        "chivalry2-win64-shipping.exe": ("Chivalry 2", "In Medieval Battlefield", 1824220),
        "remnant2-win64-shipping.exe": ("Remnant II", "In Co-Op Campaign", 1282100),
        "payday3client-win64-shipping.exe": ("PAYDAY 3", "In Heist", 1272080),
        "dyinglightgame_x64_rwdi.exe": ("Dying Light 2 Stay Human", "In Villedor", 534380),
        "control_dx12.exe": ("Control", "In The Oldest House", 870780),
        "control_dx11.exe": ("Control", "In The Oldest House", 870780),
        "control.exe": ("Control", "In The Oldest House", 870780),
        "hitman3.exe": ("HITMAN World of Assassination", "In Contract Mission", 1659040),
        "kingdom hearts hd 1.5+2.5 remix.exe": ("KINGDOM HEARTS", "In Story Adventure", 2552430),
        "kingdom hearts iii.exe": ("KINGDOM HEARTS", "In Story Adventure", 2552430),
        "snowrunner.exe": ("SnowRunner", "In Off-Road Expedition", 1465360),
        "arkascended.exe": ("ARK: Survival", "In Dino Survival", 2399830),
        "shootergame.exe": ("ARK: Survival", "In Dino Survival", 2399830),
        "civilizationvi.exe": ("Sid Meier's Civilization VI", "In Turn-Based Campaign", 289070),
        "civilizationvi_dx12.exe": ("Sid Meier's Civilization VI", "In Turn-Based Campaign", 289070),
        "witchfire-win64-shipping.exe": ("Witchfire", "In Dark Fantasy Raid", 3156770),
        "witchfire.exe": ("Witchfire", "In Dark Fantasy Raid", 3156770),
    }

    re_char = re.compile(r"AthenaCharacter:(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)", re.I)
    re_path = re.compile(r"/Cosmetics/Characters/[^\"\'\s\\]*?(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)", re.I)
    re_cid = re.compile(r"\b(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)\b", re.I)

    def __init__(self, state, cosmetics, on_ui, on_push, xbox_helper=None):
        self.state = state
        self.cosmetics = cosmetics
        self.xbox_helper = xbox_helper
        self.on_ui = on_ui
        self.on_push = on_push
        self.http = requests.Session()
        self.token = None
        self.account_id = None
        self.expires = 0.0
        self.busy = False
        self.scanned_once = False
        self.loadouts = {}
        self.mate_cids = set()
        self.own_party_cid = None
        self.sent_party_id = None
        self.name_cache = {}
        self.raw_friends_cache = []
        db_procs = CFG.games_db.get("epic_known_procs") or {}
        self.KNOWN_PROCS = (
            {k.lower(): tuple(v) for k, v in db_procs.items()}
            if db_procs
            else dict(self.DEFAULT_KNOWN_PROCS)
        )

    def _resolve_icon(self, game_name, steam_aid=0):
        if self.xbox_helper:
            return self.xbox_helper.resolve_cover_icon(
                game_name, fallback=FALLBACK_LOGO, appid=steam_aid
            )
        icons_map = CFG.games_db.get("game_icons") or {}
        k = (game_name or "").strip().lower()
        if k in icons_map:
            return icons_map[k]
        if steam_aid and int(steam_aid) > 0:
            return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{int(steam_aid)}/header.jpg"
        return FALLBACK_LOGO

    def scan_installed_games(self):
        self.scanned_once = True
        games = []
        seen = set()

        def add_game(title, install_dir, exe_path="", app_name=""):
            title = re.sub(r"\s+", " ", str(title or "")).strip()
            install_dir = str(install_dir or "").strip().replace("/", "\\")
            if not title or not install_dir or not os.path.exists(install_dir):
                return
            low_t = title.lower()
            if (
                low_t.startswith("ue_")
                or low_t.startswith("unreal engine")
                or low_t in ("epic games launcher", "epic online services", "directx", "launcher")
            ):
                return
            k = os.path.normcase(os.path.normpath(install_dir)).rstrip("\\")
            if k in seen:
                return
            seen.add(k)
            exe_name = os.path.basename(str(exe_path or "")).lower()
            launch_uri = (
                f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true"
                if app_name
                else ""
            )
            games.append(
                {
                    "name": title,
                    "install_dir": os.path.normpath(install_dir),
                    "norm_dir": k,
                    "exe_name": exe_name,
                    "app_name": str(app_name or ""),
                    "launch_uri": launch_uri,
                }
            )

        prog_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        manifest_dirs = [
            os.path.join(prog_data, "Epic", "EpicGamesLauncher", "Data", "Manifests"),
        ]
        reg_appdata = Reg.get_any(
            "AppDataPath", "", path=r"SOFTWARE\Epic Games\EpicGamesLauncher"
        ) or Reg.get_any(
            "AppDataPath", "", path=r"SOFTWARE\WOW6432Node\Epic Games\EpicGamesLauncher"
        )
        if reg_appdata:
            m_cand = os.path.join(str(reg_appdata), "Manifests")
            if m_cand not in manifest_dirs:
                manifest_dirs.append(m_cand)

        for mdir in manifest_dirs:
            if not os.path.exists(mdir):
                continue
            for item_file in glob.glob(os.path.join(mdir, "*.item")):
                try:
                    data = json.load(
                        open(item_file, "r", encoding="utf-8", errors="ignore")
                    )
                    if data.get("bIsIncompleteInstall"):
                        continue
                    cats = [str(c).lower() for c in (data.get("AppCategories") or [])]
                    if "plugins" in cats or "plugins/engine" in cats or "engines" in cats:
                        if "games" not in cats and "applications" not in cats:
                            continue
                    dname = data.get("DisplayName") or data.get("AppName") or ""
                    iloc = data.get("InstallLocation") or ""
                    lexe = data.get("LaunchExecutable") or ""
                    aname = data.get("AppName") or ""
                    if dname and iloc:
                        add_game(dname, iloc, lexe, aname)
                except Exception:
                    pass

        dat_path = os.path.join(
            prog_data, "Epic", "UnrealEngineLauncher", "LauncherInstalled.dat"
        )
        if os.path.exists(dat_path):
            try:
                dat = json.load(open(dat_path, "r", encoding="utf-8", errors="ignore"))
                for entry in dat.get("InstallationList") or []:
                    iloc = entry.get("InstallLocation") or ""
                    aname = entry.get("AppName") or ""
                    if iloc and os.path.exists(iloc):
                        folder_title = os.path.basename(iloc.rstrip("\\/"))
                        if not folder_title.lower().startswith("ue_"):
                            add_game(folder_title, iloc, "", aname)
            except Exception:
                pass

        for drive in ("C:", "D:", "E:", "F:"):
            for rel in (
                "Program Files\\Epic Games",
                "Program Files (x86)\\Epic Games",
                "Epic Games",
            ):
                base = os.path.join(drive + "\\", rel)
                if not os.path.exists(base):
                    continue
                try:
                    for sub in os.listdir(base):
                        full = os.path.join(base, sub)
                        if os.path.isdir(full) and not sub.lower().startswith("ue_"):
                            title = "Rocket League" if sub.lower() == "rocketleague" else sub
                            add_game(title, full)
                except OSError:
                    pass

        games.sort(key=lambda x: x["name"].lower())
        self.state.epic_installed_games = games
        return games

    def launch_game(self, game_entry):
        if isinstance(game_entry, dict):
            uri = game_entry.get("launch_uri") or ""
            idir = game_entry.get("install_dir") or ""
            if uri:
                try:
                    os.startfile(uri)
                    return True
                except Exception:
                    pass
            if idir and os.path.exists(idir):
                try:
                    os.startfile(idir)
                    return True
                except Exception:
                    pass
        elif isinstance(game_entry, str) and os.path.exists(game_entry):
            try:
                os.startfile(game_entry)
                return True
            except Exception:
                pass
        return False

    def poll(self, snapshot=None):
        if not self.scanned_once:
            self.scan_installed_games()

        if not self.state.fortnite_enabled or self.state.running:
            if self.state.epic_game_running:
                self.state.epic_game_running = False
                self.state.epic_game_name = ""
                self.state.epic_game_state = ""
                self.state.epic_game_icon = FALLBACK_LOGO
                return True
            return False

        if snapshot is not None:
            procs, wins = snapshot[0], snapshot[2]
        else:
            procs, wins = [], []
            for p in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    exe = p.info.get("exe") or ""
                    cmd = " ".join(p.info.get("cmdline") or [])
                    procs.append(
                        {
                            "pid": p.info["pid"],
                            "name": (p.info.get("name") or "").lower(),
                            "exe": exe,
                            "exe_lower": exe.lower(),
                            "cmdline_lower": cmd.lower(),
                            "has_visible_window": True,
                        }
                    )
                except Exception:
                    pass

        detected_name = ""
        detected_state = ""
        detected_icon = FALLBACK_LOGO
        matched_pid = None

        for p in procs:
            pname = p.get("name") or ""
            exe_low = p.get("exe_lower") or ""
            cmd_low = p.get("cmdline_lower") or ""
            if not pname or pname in EPIC_IGNORE_PROCS or is_fn_proc(p):
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue

            is_epic_launch = (
                "\\epic games\\" in exe_low
                or "-epicapp=" in cmd_low
                or "-epicenv=" in cmd_low
                or "-epicuserid=" in cmd_low
                or "-epicportal" in cmd_low
            )

            # 1. Check installed Epic Games manifests
            for g in self.state.epic_installed_games:
                if g["name"].lower() == "fortnite":
                    continue
                ndir = g.get("norm_dir") or ""
                gexe = g.get("exe_name") or ""
                if (ndir and len(ndir) > 5 and exe_low.startswith(ndir)) or (
                    gexe and pname == gexe and is_epic_launch
                ):
                    detected_name = g["name"]
                    detected_state = "Active on Epic Games Store"
                    if pname in self.KNOWN_PROCS:
                        _, kstate, kaid = self.KNOWN_PROCS[pname]
                        detected_state = kstate
                        detected_icon = self._resolve_icon(detected_name, kaid)
                    else:
                        detected_icon = self._resolve_icon(detected_name)
                    matched_pid = p.get("pid")
                    break
            if detected_name:
                break

            # 2. Check known Epic Games Store executables
            if pname in self.KNOWN_PROCS:
                if ("steamapps" in exe_low or "windowsapps" in exe_low) and not is_epic_launch:
                    continue
                gname, gstate, steam_aid = self.KNOWN_PROCS[pname]
                detected_name = gname
                detected_state = gstate
                detected_icon = self._resolve_icon(detected_name, steam_aid)
                matched_pid = p.get("pid")
                break

            # 3. Check any game inside an Epic Games folder or launched with -epicapp=
            if is_epic_launch and exe_low:
                if "\\epic games\\" in exe_low:
                    parts = (p.get("exe") or "").split("\\")
                    for idx, part in enumerate(parts):
                        if part.lower() == "epic games" and idx + 1 < len(parts):
                            folder_name = parts[idx + 1]
                            if folder_name.lower() not in ("launcher", "directxredist", "fortnite") and not folder_name.lower().startswith("ue_"):
                                detected_name = (
                                    "Rocket League"
                                    if folder_name.lower() == "rocketleague"
                                    else folder_name
                                )
                                detected_state = "Active on Epic Games Store"
                                detected_icon = self._resolve_icon(detected_name)
                                matched_pid = p.get("pid")
                            break
                if detected_name:
                    break

        if not detected_name:
            if self.state.epic_game_running:
                self.state.epic_game_running = False
                self.state.epic_game_name = ""
                self.state.epic_game_state = ""
                self.state.epic_game_icon = FALLBACK_LOGO
                return True
            return False

        if matched_pid and wins:
            for w in wins:
                if w.get("pid") == matched_pid:
                    wtitle = (w.get("title") or "").strip()
                    if (
                        wtitle
                        and len(wtitle) > 2
                        and wtitle.lower() != detected_name.lower()
                        and "unreal" not in wtitle.lower()
                    ):
                        clean_t = wtitle.replace(detected_name, "").strip(" -–—•|:")
                        if 2 <= len(clean_t) <= 38:
                            detected_state = f"{clean_t} • Epic Games"
                    break

        changed = (
            not self.state.epic_game_running
            or self.state.epic_game_name != detected_name
            or self.state.epic_game_state != detected_state
        )
        if not self.state.epic_game_running or self.state.epic_game_name != detected_name:
            self.state.epic_game_start_ts = int(time.time())
        self.state.epic_game_running = True
        self.state.epic_game_name = detected_name
        self.state.epic_game_state = detected_state
        self.state.epic_game_icon = detected_icon
        return changed

    def unlink(self):
        Reg.remove("EpicAuthData")
        Reg.remove("EpicName")
        self.token = None
        self.account_id = None
        self.expires = 0.0
        self.state.epic_ok = False
        self.state.epic_name = ""
        self.state.party_size = 1
        self.state.party_max = 4
        self.state.peers = []
        self.state.party_members_info.clear()
        self.state.friends_list.clear()
        self.loadouts.clear()
        self.mate_cids.clear()
        self.own_party_cid = None
        self.sent_party_id = None
        self.on_ui()
        self.on_push()

    def link_account(self, name_or_id):
        val = str(name_or_id or "").strip()
        if not val or "EpicAccountId" in val:
            return False
        self.state.epic_name = val
        self.state.epic_ok = True
        Reg.set("EpicName", val)
        self.rebuild_friends_view()
        self.on_ui()
        self.on_push()
        return True

    def detect_local_account(self):
        if self.restore():
            self.fetch_party()
            self.fetch_profile()
            self.fetch_friends()
            return True

        local_app = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        egl_log_dir = os.path.join(local_app, "EpicGamesLauncher", "Saved", "Logs")
        candidate_logs = []
        if os.path.exists(egl_log_dir):
            candidate_logs.extend(
                sorted(
                    glob.glob(os.path.join(egl_log_dir, "EpicGamesLauncher*.log")),
                    key=os.path.getmtime,
                    reverse=True,
                )[:3]
            )
        fn_log = get_log_path()
        if fn_log and os.path.exists(fn_log):
            candidate_logs.append(fn_log)

        re_name = re.compile(
            r'(?:-epicusername=|DisplayName=|UserName=|Logged in user\s+|"displayName"\s*:\s*)"?([A-Za-z0-9_.\-\u00C0-\u024F ]{2,28})"?',
            re.I,
        )
        re_aid = re.compile(
            r'(?:-epicuserid=|AccountId=|LocalUserId=|"accountId"\s*:\s*")([0-9a-fA-F]{32})',
            re.I,
        )

        detected_name = ""
        detected_aid = ""
        for lpath in candidate_logs:
            try:
                sz = os.path.getsize(lpath)
                with open(lpath, "r", encoding="utf-8", errors="ignore") as f:
                    if sz > 1_500_000:
                        f.seek(sz - 1_500_000)
                    txt = f.read()
                if not detected_aid:
                    m_a = re_aid.search(txt)
                    if m_a:
                        detected_aid = m_a.group(1).lower()
                for m_n in re_name.finditer(txt):
                    cand = m_n.group(1).strip()
                    if (
                        2 <= len(cand) <= 28
                        and "EpicAccountId" not in cand
                        and "=" not in cand
                        and cand.lower() not in ("none", "null", "default", "unknown", "user", "player")
                    ):
                        detected_name = cand
                        break
                if detected_name:
                    break
            except OSError:
                pass

        if not detected_aid:
            reg_aid = Reg.get_any(
                "AccountId", "", path=r"Software\Epic Games\UnrealEngine\Identifiers"
            )
            if reg_aid and len(str(reg_aid).strip()) == 32:
                detected_aid = str(reg_aid).strip().lower()

        if detected_aid and not self.state.account_id:
            self.state.account_id = detected_aid
            self.account_id = detected_aid

        if detected_name:
            return self.link_account(detected_name)
        if self.state.epic_name:
            self.state.epic_ok = True
            self.rebuild_friends_view()
            self.on_ui()
            return True
        return False

    def load(self):
        return self.detect_local_account()

    def add_tracked_friend(self, epic_name):
        ename = str(epic_name or "").strip()
        if not ename:
            return False
        tracked = _parse_str_list(Reg.get("EpicTrackedFriends", ""))
        if ename.lower() not in [x.lower() for x in tracked]:
            tracked.append(ename)
            Reg.set("EpicTrackedFriends", json.dumps(tracked))
        self.rebuild_friends_view()
        return True

    def remove_tracked_friend(self, epic_name):
        ename = str(epic_name or "").strip().lower()
        tracked = [
            x
            for x in _parse_str_list(Reg.get("EpicTrackedFriends", ""))
            if x.lower() != ename
        ]
        Reg.set("EpicTrackedFriends", json.dumps(tracked))
        self.rebuild_friends_view()
        return True

    def restore(self):
        raw = Reg.get("EpicAuthData")
        if not raw:
            return False
        try:
            saved = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return False

        if saved.get("display_name"):
            self.state.epic_name = saved["display_name"]
            Reg.set("EpicName", self.state.epic_name)

        if saved.get("device_id") and saved.get("account_id") and saved.get("secret"):
            try:
                r = self.http.post(
                    f"{OAUTH_URL}/account/api/oauth/token",
                    headers={"Authorization": f"basic {ANDROID_BASIC}", "Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "grant_type": "device_auth",
                        "account_id": saved["account_id"],
                        "device_id": saved["device_id"],
                        "secret": saved["secret"],
                        "token_type": "eg1",
                    },
                    timeout=5,
                )
                if r.status_code == 200:
                    saved["client_basic"] = ANDROID_BASIC
                    self._apply_auth(r.json(), saved)
                    return True
            except requests.RequestException:
                pass

        if saved.get("refresh_token"):
            basic = saved.get("client_basic", ANDROID_BASIC)
            try:
                r = self.http.post(
                    f"{OAUTH_URL}/account/api/oauth/token",
                    headers={"Authorization": f"basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
                    data={"grant_type": "refresh_token", "refresh_token": saved["refresh_token"], "token_type": "eg1"},
                    timeout=5,
                )
                if r.status_code == 200:
                    data = r.json()
                    if basic != ANDROID_BASIC:
                        adata, dev = self._to_android(data["access_token"])
                        if adata:
                            if dev:
                                saved.update(dev)
                            saved["client_basic"] = ANDROID_BASIC
                            self._apply_auth(adata, saved)
                            return True
                    self._apply_auth(data, saved)
                    return True
            except requests.RequestException:
                pass

        self.state.epic_ok = False
        self.on_ui()
        return False

    def _apply_auth(self, data, saved=None):
        self.token = data["access_token"]
        self.account_id = data["account_id"]
        self.state.account_id = self.account_id
        self.expires = time.time() + int(data.get("expires_in", 3600)) - 120
        self.state.epic_name = data.get("displayName") or (saved or {}).get("display_name") or self.state.epic_name
        self.state.epic_ok = True
        if self.state.epic_name:
            Reg.set("EpicName", self.state.epic_name)
        out = dict(saved or {})
        out["account_id"] = self.account_id
        out["display_name"] = self.state.epic_name
        if "refresh_token" in data:
            out["refresh_token"] = data["refresh_token"]
        Reg.set("EpicAuthData", json.dumps(out))
        self.on_ui()

    def login(self, done_cb=None):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._login_thread, args=(done_cb,), daemon=True).start()

    def _login_thread(self, done_cb=None):
        try:
            r = self.http.post(
                f"{OAUTH_URL}/account/api/oauth/token",
                headers={"Authorization": f"basic {SWITCH_BASIC}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials"},
                timeout=6,
            )
            if r.status_code != 200:
                return
            ctok = r.json()["access_token"]
            dr = self.http.post(
                f"{OAUTH_URL}/account/api/oauth/deviceAuthorization",
                headers={"Authorization": f"bearer {ctok}", "Content-Type": "application/x-www-form-urlencoded"},
                timeout=6,
            )
            if dr.status_code != 200:
                return
            d = dr.json()
            code = d["device_code"]
            webbrowser.open(d.get("verification_uri_complete") or d.get("verification_uri"))

            for _ in range(60):
                time.sleep(2.5)
                pr = self.http.post(
                    f"{OAUTH_URL}/account/api/oauth/token",
                    headers={"Authorization": f"basic {SWITCH_BASIC}", "Content-Type": "application/x-www-form-urlencoded"},
                    data={"grant_type": "device_code", "device_code": code, "token_type": "eg1"},
                    timeout=6,
                )
                if pr.status_code == 200:
                    sw = pr.json()
                    saved = {"client_basic": ANDROID_BASIC, "display_name": sw.get("displayName", "")}
                    adata, dev = self._to_android(sw["access_token"])
                    if dev:
                        saved.update(dev)
                    self._apply_auth(adata or sw, saved)
                    self.fetch_party()
                    self.fetch_profile()
                    self.fetch_friends()
                    if done_cb:
                        done_cb()
                    break
        except Exception:
            pass
        finally:
            self.busy = False

    def _to_android(self, sw_token):
        try:
            ex = self.http.get(f"{OAUTH_URL}/account/api/oauth/exchange", headers={"Authorization": f"bearer {sw_token}"}, timeout=6)
            if ex.status_code != 200:
                return None, None
            code = ex.json()["code"]
            ar = self.http.post(
                f"{OAUTH_URL}/account/api/oauth/token",
                headers={"Authorization": f"basic {ANDROID_BASIC}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "exchange_code", "exchange_code": code, "token_type": "eg1"},
                timeout=6,
            )
            if ar.status_code != 200:
                return None, None
            adata = ar.json()
            acc, tok = adata["account_id"], adata["access_token"]
            dev = None
            dr = self.http.post(f"{OAUTH_URL}/account/api/public/account/{acc}/deviceAuth", headers={"Authorization": f"bearer {tok}"}, timeout=6)
            if dr.status_code == 200:
                dd = dr.json()
                dev = {
                    "device_id": dd.get("deviceId"),
                    "account_id": dd.get("accountId", acc),
                    "secret": dd.get("secret"),
                    "client_basic": ANDROID_BASIC,
                }
            return adata, dev
        except Exception:
            return None, None

    def update_skin(self, raw_cid, immediate=False):
        cid = Cosmetics.clean_id(raw_cid)
        if not cid:
            return False
        if cid == self.state.skin_id and self.state.skin_icon and "wikimedia" not in self.state.skin_icon:
            return False
        res = self.cosmetics.get_id(cid)
        if res:
            self.state.skin_id = cid
            self.state.skin_name, self.state.skin_icon = res
            Reg.set("SkinId", cid)
            Reg.set("SkinName", self.state.skin_name)
            Reg.set("SkinIcon", self.state.skin_icon)
            self.on_ui()
            if immediate:
                self.on_push()
            return True
        return False

    def fetch_profile(self):
        if not self.token or not self.account_id:
            return False
        try:
            url = f"{MCP_URL}/fortnite/api/game/v2/profile/{self.account_id}/client/QueryProfile?profileId=athena&rvn=-1"
            r = self.http.post(url, headers={"Authorization": f"bearer {self.token}", "Content-Type": "application/json"}, json={}, timeout=4.5)
            if r.status_code != 200:
                return False
            changes = r.json().get("profileChanges") or []
            if not changes:
                return False
            prof = changes[0].get("profile") or {}
            attrs = (prof.get("stats") or {}).get("attributes") or {}
            lvl = attrs.get("book_level") or attrs.get("level")
            if lvl and int(lvl) >= 1:
                v = int(lvl)
                if v != self.state.season_level:
                    self.state.season_level = v
                    Reg.set("SeasonLevel", v, winreg.REG_DWORD)
                    return True
        except Exception:
            pass
        return False

    def _resolve_names(self, account_ids):
        missing = [aid for aid in account_ids if aid and aid not in self.name_cache]
        for i in range(0, len(missing), 50):
            batch = missing[i : i + 50]
            try:
                params = [("accountId", aid) for aid in batch]
                r = self.http.get(
                    f"{OAUTH_URL}/account/api/public/account",
                    headers={"Authorization": f"bearer {self.token}"},
                    params=params,
                    timeout=4.0,
                )
                if r.status_code == 200:
                    for item in r.json():
                        aid = item.get("id")
                        dn = item.get("displayName") or item.get("externalAuths", {}).get("psn", {}).get("externalDisplayName")
                        if aid and dn:
                            self.name_cache[aid] = dn
            except Exception:
                pass

    def fetch_friends(self):
        if not self.state.epic_ok or not self.token or not self.account_id:
            return False
        try:
            r = self.http.get(f"{FRIENDS_URL}/friends/api/v1/{self.account_id}/summary", headers={"Authorization": f"bearer {self.token}"}, timeout=4.0)
            if r.status_code != 200:
                return False
            data = r.json() or {}
            friends_raw = data.get("friends") or []
            self.raw_friends_cache = friends_raw
            last_online_map = {}
            try:
                pr = self.http.get(
                    f"{PRESENCE_URL}/presence/api/v1/_/{self.account_id}/last-online",
                    headers={"Authorization": f"bearer {self.token}"},
                    timeout=3.5,
                )
                if pr.status_code == 200:
                    last_online_map = pr.json() or {}
            except Exception:
                pass
            aids = [f.get("accountId") for f in friends_raw if f.get("accountId")]
            for p_aid in self.state.party_members_info:
                if p_aid not in aids:
                    aids.append(p_aid)
            self._resolve_names(aids)
            self.rebuild_friends_view(last_online_map)
            return True
        except Exception:
            return False

    def rebuild_friends_view(self, last_online_map=None):
        if last_online_map is None:
            last_online_map = {}
        now = time.time()
        combined = {}
        for p_aid, pinfo in list(self.state.party_members_info.items()):
            if p_aid == self.account_id:
                continue
            name = pinfo.get("name") or self.name_cache.get(p_aid) or "Party Member"
            is_lang = bool(pinfo.get("is_langley"))
            combined[p_aid] = {
                "account_id": p_aid,
                "name": name,
                "in_party": True,
                "is_langley": is_lang,
                "online": True,
                "status": "★ Lang!ley Squad (In Party)" if is_lang else "In Your Party",
                "favorite": True,
            }
        for f in self.raw_friends_cache:
            aid = f.get("accountId")
            if not aid or aid == self.account_id:
                continue
            base_name = self.name_cache.get(aid) or f.get("displayName") or aid[:8]
            alias = (f.get("alias") or "").strip()
            disp = f"{base_name} ({alias})" if alias and alias.lower() != base_name.lower() else base_name
            fav = bool(f.get("favorite"))
            if aid in combined:
                combined[aid]["name"] = disp
                combined[aid]["favorite"] = fav
                continue
            log_pres = self.state.log_online_friends.get(aid)
            is_online, status_txt = False, "Offline"
            if log_pres and (now - log_pres.get("ts", 0) < 900):
                is_online = True
                status_txt = log_pres.get("status") or "Online in Fortnite"
            else:
                lo_list = last_online_map.get(aid)
                if isinstance(lo_list, list) and lo_list:
                    lo_str = lo_list[0].get("last_online", "")
                    if lo_str:
                        status_txt = f"Last seen: {lo_str[:10]}"
            combined[aid] = {
                "account_id": aid,
                "name": disp,
                "in_party": False,
                "is_langley": False,
                "online": is_online,
                "status": status_txt,
                "favorite": fav,
            }

        existing_names = {v["name"].lower() for v in combined.values()}
        for item in _parse_str_list(Reg.get("EpicTrackedFriends", "")):
            clean = str(item or "").strip()
            if not clean or clean.lower() in existing_names:
                continue
            existing_names.add(clean.lower())
            is_act = bool(self.state.running or self.state.epic_game_running)
            combined[f"tracked_{clean.lower()}"] = {
                "account_id": f"tracked_{clean.lower()}",
                "name": clean,
                "in_party": False,
                "is_langley": False,
                "online": is_act,
                "status": "Epic Friend (Active)" if is_act else "Epic Friend (Pinned)",
                "favorite": True,
                "tracked": True,
            }

        def sort_key(item):
            rank = (
                0
                if (item["in_party"] and item["is_langley"])
                else (1 if item["in_party"] else (2 if item["online"] else (3 if item["favorite"] else 4)))
            )
            return (rank, item["name"].lower())

        self.state.friends_list = sorted(combined.values(), key=sort_key)
        self.on_ui()

    def _patch_tag(self, pid, rev):
        if not pid or not self.token or not self.account_id:
            return
        url = f"{PARTY_URL}/party/api/v1/Fortnite/parties/{pid}/members/{self.account_id}/meta"
        body = {"delete": [], "revision": int(rev or 0), "update": {self.TAG_1: "true", self.TAG_2: "true"}}
        try:
            r = self.http.patch(
                url,
                headers={"Authorization": f"bearer {self.token}", "Content-Type": "application/json"},
                json=body,
                timeout=2.5,
            )
            if r.status_code in (200, 204):
                self.sent_party_id = pid
            elif r.status_code == 409:
                mv = r.json().get("messageVars") or []
                if len(mv) >= 2 and str(mv[1]).isdigit():
                    body["revision"] = int(mv[1])
                    r2 = self.http.patch(
                        url,
                        headers={"Authorization": f"bearer {self.token}", "Content-Type": "application/json"},
                        json=body,
                        timeout=2.5,
                    )
                    if r2.status_code in (200, 204):
                        self.sent_party_id = pid
        except Exception:
            pass

    @classmethod
    def _is_langley(cls, meta):
        if not meta:
            return False
        if meta.get(cls.TAG_1) == "true" or meta.get(cls.TAG_2) == "true":
            return True
        raw = json.dumps(meta).lower()
        return "langley_s" in raw or "langleyuser" in raw

    def _extract_cid(self, blob):
        m = self.re_char.search(blob) or self.re_path.search(blob) or self.re_cid.search(blob)
        return m.group(1) if m else None

    def fetch_party(self):
        if not self.state.epic_ok or not self.token or not self.account_id:
            return False
        if time.time() >= self.expires and not self.restore():
            return False
        try:
            r = self.http.get(
                f"{PARTY_URL}/party/api/v1/Fortnite/user/{self.account_id}",
                headers={"Authorization": f"bearer {self.token}"},
                timeout=2.5,
            )
            if r.status_code in (401, 403):
                self.restore()
                return False
            if r.status_code != 200:
                return False

            parties = r.json().get("current") or []
            if not parties:
                self.mate_cids.clear()
                if self.state.party_size != 1 or self.state.peers or self.state.party_members_info:
                    self.state.party_size = 1
                    self.state.peers = []
                    self.state.party_members_info.clear()
                    self.rebuild_friends_view()
                    return True
                return False

            p = parties[0]
            pid, pcfg, pmeta, members = p.get("id"), p.get("config") or {}, p.get("meta") or {}, p.get("members") or []
            changed = False
            sz = max(1, len(members))
            msz = int(pcfg.get("max_size") or 4)
            if msz > 16:
                msz = 4
            if sz != self.state.party_size or msz != self.state.party_max:
                self.state.party_size, self.state.party_max = sz, max(sz, msz)
                changed = True

            for k in ("Default:SelectedIsland_j", "Default:PlaylistData_j", "Default:PartyMatchmakingInfo_j"):
                v = pmeta.get(k)
                if v:
                    m = re.search(r"(playlist_[A-Za-z0-9_]+)", str(v), re.I)
                    if m:
                        mode = parse_mode(m.group(1))
                        if mode and mode != self.state.mode:
                            self.state.mode = mode
                            changed = True
                            break

            me, peers, new_party_map, new_mate_cids = None, [], {}, set()
            loadout_keys = (
                "Default:MpLoadout_j",
                "Default:AthenaCosmeticLoadout_j",
                "Default:FrontendCosmeticLoadout_j",
                "Default:LoadoutMeta_j",
            )

            for mem in members:
                aid = mem.get("account_id")
                mm = mem.get("meta") or {}
                mname = str(mm.get("urn:epic:member:dn_s") or mem.get("display_name") or self.name_cache.get(aid) or "Teammate")
                if aid and mname and mname != "Teammate":
                    self.name_cache[aid] = mname
                if aid == self.account_id:
                    me = mem
                else:
                    is_l = self._is_langley(mm)
                    if aid:
                        new_party_map[aid] = {"name": mname, "is_langley": is_l}
                    if is_l:
                        peers.append(mname)
                    for lk in loadout_keys:
                        mc = self._extract_cid(str(mm.get(lk) or ""))
                        if mc:
                            new_mate_cids.add(Cosmetics.clean_id(mc))

            self.mate_cids = new_mate_cids
            if new_party_map != self.state.party_members_info:
                self.state.party_members_info = new_party_map
                self.rebuild_friends_view()
                changed = True
            if peers != self.state.peers:
                self.state.peers = peers
                changed = True
            if not me:
                return changed

            mmeta = me.get("meta") or {}
            if pid and (self.sent_party_id != pid or not self._is_langley(mmeta)):
                threading.Thread(target=self._patch_tag, args=(pid, me.get("revision", 0)), daemon=True).start()

            dn = mmeta.get("urn:epic:member:dn_s")
            if dn and str(dn) != self.state.epic_name and "EpicAccountId" not in str(dn):
                self.state.epic_name = str(dn)
                Reg.set("EpicName", self.state.epic_name)
                changed = True

            changed_cid, first_cid = None, None
            for k in loadout_keys:
                blob = str(mmeta.get(k) or "")
                raw_c = self._extract_cid(blob) if blob else None
                c = Cosmetics.clean_id(raw_c) if raw_c else None
                if not c:
                    continue
                if first_cid is None:
                    first_cid = c
                prev_c = self.loadouts.get(k)
                self.loadouts[k] = c
                if prev_c is not None and prev_c != c:
                    changed_cid = c
                    break

            target_cid = changed_cid or (first_cid if not self.own_party_cid else None)
            if target_cid:
                self.own_party_cid = target_cid
                if self.update_skin(target_cid, immediate=True):
                    changed = True

            lvls = []
            for k in ("Default:BattlePassInfo_j", "Default:AthenaBannerInfo_j"):
                bp = mmeta.get(k)
                if bp:
                    for m in re.finditer(r'(?:passLevel|seasonLevel)\\?"\s*:\s*(\d+)', str(bp)):
                        val = int(m.group(1))
                        if 1 <= val <= 2000:
                            lvls.append(val)
            if lvls:
                best = max(lvls)
                if (best > 1 or self.state.season_level == 1) and best != self.state.season_level:
                    self.state.season_level = best
                    Reg.set("SeasonLevel", best, winreg.REG_DWORD)
                    changed = True

            loc = str(mmeta.get("Default:Location_s") or "")
            packed = str(mmeta.get("Default:PackedState_j") or "").replace(" ", "")
            fstats = str(mmeta.get("Default:FortGameplayStats_j") or "")
            pstate = str(pmeta.get("Default:PartyState_s") or "")
            ingame = (
                "InGame" in loc
                or '"location":"InGame"' in packed
                or "PostMatchmaking" in pstate
                or '"bInMatch":true' in fstats.replace(" ", "")
            )
            inlobby = ("Lobby" in loc and "PreLobby" not in loc) or '"location":"Lobby"' in packed

            if ingame and not self.state.in_match:
                self.state.in_match = True
                changed = True
            elif inlobby and not ingame and self.state.in_match:
                self.state.in_match = False
                changed = True

            mpl = re.search(r"(Playlist_[A-Za-z0-9_]+)", fstats, re.I)
            if mpl:
                mode = parse_mode(mpl.group(1))
                if mode and mode != self.state.mode:
                    self.state.mode = mode
                    changed = True
            return changed
        except Exception:
            return False
