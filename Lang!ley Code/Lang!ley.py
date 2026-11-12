import io
import os
import re
import sys
import glob
import json
import time
import struct
import ctypes
import winreg
import tempfile
import subprocess
import webbrowser
import threading
import tkinter as tk
import psutil
import requests
from PIL import Image, ImageDraw
import pystray

CLIENT_ID = "1570074042340212776"
APP_TITLE = "Lang!ley"
APP_VERSION = "1.0.1"
REG_NAME = "LangleyFortniteRPC"
REG_PATH = r"Software\LangleyFortniteRPC"
RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

WEB_URL = "https://asukaa.de"
LANGLEY_URL = "https://asukaa.de/langley"
UPDATE_JSON_URL = "https://asukaa.de/langley/version.json"
DEFAULT_SETUP_URL = "https://asukaa.de/langley/Langley_Setup.exe"
FALLBACK_LOGO = "https://upload.wikimedia.org/wikipedia/commons/7/7c/Fortnite_F_lettermark_logo.png"

OAUTH_URL = "https://account-public-service-prod.ol.epicgames.com"
PARTY_URL = "https://party-service-prod.ol.epicgames.com"
MCP_URL = "https://fngw-mcp-gc-livefn.ol.epicgames.com"
FRIENDS_URL = "https://friends-public-service-prod.ol.epicgames.com"
PRESENCE_URL = "https://presence-public-service-prod.ol.epicgames.com"

SWITCH_BASIC = "OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3"
ANDROID_BASIC = "M2Y2OWU1NmM3NjQ5NDkyYzhjYzI5ZjFhZjA4YThhMTI6YjUxZWU5Y2IxMjIzNGY1MGE2OWVmYTY3ZWY1MzgxMmU="

MODES = {
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

SKIP_MODES = {"sprout", "none", "null", "front", "default", "prelobby"}


def set_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("asukaa.langley.rpc")
    except Exception:
        pass


def find_icon():
    names = ["Asukaa.de.png", "asukaa.de.png", "Asukaa.png", "icon.png", "icon.ico"]
    dirs = [getattr(sys, "_MEIPASS", ""), os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()]
    for d in dirs:
        if not d:
            continue
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


def fallback_icon(size=128):
    img = Image.new("RGBA", (size, size), "#B2AB99")
    d = ImageDraw.Draw(img)

    m1, m2, cs = int(size * 0.06), int(size * 0.11), int(size * 0.05)
    d.rectangle([m2, m2, size - m2, size - m2], fill="#6E695A", outline="#DCD6C4", width=max(1, size // 48))
    d.rectangle([m1, m1, size - m1, size - m1], outline="#454138", width=max(1, size // 42))

    for x1, y1, x2, y2 in [
        (m1 - cs, m1 - cs, m1, m1),
        (size - m1, m1 - cs, size - m1 + cs, m1),
        (m1 - cs, size - m1, m1, size - m1 + cs),
        (size - m1, size - m1, size - m1 + cs, size - m1 + cs),
    ]:
        d.rectangle([x1, y1, x2, y2], fill="#454138")

    cx, cy = size // 2, size // 2
    for r_fac, col in [(0.34, "#7C7667"), (0.26, "#898373"), (0.18, "#96907F")]:
        r = int(size * r_fac)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    petals = [
        [(cx, cy), (cx - int(size * 0.24), cy - int(size * 0.26)), (cx - int(size * 0.04), cy - int(size * 0.18))],
        [(cx, cy), (cx + int(size * 0.22), cy - int(size * 0.16)), (cx + int(size * 0.08), cy - int(size * 0.02))],
        [(cx, cy), (cx + int(size * 0.28), cy + int(size * 0.15)), (cx + int(size * 0.05), cy + int(size * 0.14))],
        [(cx, cy), (cx - int(size * 0.05), cy + int(size * 0.34)), (cx + int(size * 0.08), cy + int(size * 0.18))],
        [(cx, cy), (cx - int(size * 0.30), cy + int(size * 0.02)), (cx - int(size * 0.12), cy + int(size * 0.12))],
    ]
    for poly in petals:
        d.polygon(poly, fill="#E5DFCE", outline="#C2B9A7")

    cr = max(2, size // 22)
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill="#454138")
    return img


def get_app_icon():
    path = find_icon()
    if path:
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            pass
    return fallback_icon(128)


def ver_tuple(v_str):
    nums = [int(x) for x in re.findall(r"\d+", str(v_str or "0"))]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def kill_old_procs():
    my_pid = os.getpid()
    script = os.path.basename(sys.argv[0]).lower()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == my_pid:
                continue
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            pname = (p.info.get("name") or "").lower()
            if (script in cmd and "python" in pname) or "lang!ley" in pname or "langley" in pname:
                p.terminate()
        except Exception:
            pass


def get_log_path():
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
    candidates = [os.path.join(local, "FortniteGame", "Saved", "Logs", "FortniteGame.log")]
    candidates.extend(
        glob.glob(
            os.path.join(local, "Packages", "*", "LocalCache", "Local", "FortniteGame", "Saved", "Logs", "FortniteGame.log")
        )
    )
    existing = [p for p in candidates if os.path.exists(p)]
    return max(existing, key=os.path.getmtime) if existing else candidates[0]


def enable_log_flags():
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
    dirs = [os.path.join(local, "FortniteGame", "Saved", "Config")]
    dirs.extend(glob.glob(os.path.join(local, "Packages", "*", "LocalCache", "Local", "FortniteGame", "Saved", "Config")))
    flags = [
        "LogParty=Verbose",
        "LogOnlinePresence=Verbose",
        "LogRichPresence=Verbose",
        "LogFort=Log",
        "LogAthena=Log",
        "LogMCP=Log",
    ]

    for d in dirs:
        for sub in ("WindowsClient", "WinGDK"):
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


class Reg:
    @staticmethod
    def get(name, default=None):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as k:
                val, _ = winreg.QueryValueEx(k, name)
                return val
        except OSError:
            return default

    @staticmethod
    def set(name, val, rtype=winreg.REG_SZ):
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as k:
                winreg.SetValueEx(k, name, 0, rtype, val)
        except OSError:
            pass

    @staticmethod
    def remove(name):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            pass

    @staticmethod
    def has_autostart():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH, 0, winreg.KEY_READ) as k:
                winreg.QueryValueEx(k, REG_NAME)
                return True
        except OSError:
            return False

    @staticmethod
    def update_startup(enabled, minimized):
        Reg.set("StartMinimized", int(minimized), winreg.REG_DWORD)
        arg = " --minimized" if minimized else ""
        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}"{arg}'
        else:
            pyw = sys.executable.replace("python.exe", "pythonw.exe")
            cmd = f'"{pyw}" "{os.path.abspath(sys.argv[0])}"{arg}'
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH, 0, winreg.KEY_SET_VALUE) as k:
                if enabled:
                    winreg.SetValueEx(k, REG_NAME, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(k, REG_NAME)
                    except OSError:
                        pass
        except OSError:
            pass


class SessionState:
    def __init__(self):
        self.skin_id = Reg.get("SkinId", "")
        self.skin_name = Reg.get("SkinName", "Charlotte-Sensei")
        self.skin_icon = Reg.get("SkinIcon", FALLBACK_LOGO)
        if "kafka" in self.skin_name.lower():
            self.skin_id = ""
            self.skin_name = "Charlotte-Sensei"
            self.skin_icon = FALLBACK_LOGO

        self.season_level = max(1, int(Reg.get("SeasonLevel", 1)))
        self.party_size = 1
        self.party_max = 4
        self.peers = []
        self.party_members_info = {}
        self.friends_list = []
        self.log_online_friends = {}

        self.mode = "Battle Royale"
        self.in_match = False
        self.running = False
        self.discord_ok = False
        self.epic_ok = False
        self.epic_name = Reg.get("EpicName", "")
        if "EpicAccountId" in self.epic_name or "=" in self.epic_name:
            self.epic_name = ""
            Reg.remove("EpicName")
        self.account_id = ""
        self.active = True
        self.start_ts = int(time.time())

        self.media_title = ""
        self.media_artist = ""
        self.media_app = "No Media Detected"
        self.media_playing = False
        self.media_pos = 0
        self.show_media_rpc = bool(Reg.get("ShowMediaRPC", 1))

        self.update_available = False
        self.update_version = ""
        self.update_url = DEFAULT_SETUP_URL
        self.update_changelog = ""

    def timer_str(self):
        diff = max(0, int(time.time()) - self.start_ts)
        h, rem = divmod(diff, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def media_str(self):
        if not self.media_title:
            return ""
        return f"{self.media_artist} - {self.media_title}" if self.media_artist else self.media_title


class AutoUpdater:
    def __init__(self, state, on_update_found):
        self.state = state
        self.on_update_found = on_update_found
        self.stop_evt = threading.Event()
        self.notified_version = None
        self.downloading = False

    def start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        self.stop_evt.set()

    def _worker(self):
        time.sleep(2.5)
        while not self.stop_evt.is_set():
            self.check_now(manual=False)
            for _ in range(1800):
                if self.stop_evt.is_set():
                    break
                time.sleep(1.0)

    def check_now(self, manual=False):
        try:
            r = requests.get(f"{UPDATE_JSON_URL}?t={int(time.time())}", timeout=5.0)
            if r.status_code != 200:
                return False
            data = r.json() or {}
            rem_ver = str(data.get("version") or "").strip()
            if not rem_ver:
                return False

            if ver_tuple(rem_ver) > ver_tuple(APP_VERSION):
                self.state.update_available = True
                self.state.update_version = rem_ver
                self.state.update_url = str(data.get("download_url") or data.get("url") or DEFAULT_SETUP_URL).strip()
                self.state.update_changelog = str(
                    data.get("changelog") or data.get("notes") or "• Bugfixes, stability improvements & new features."
                ).strip()

                if manual or self.notified_version != rem_ver:
                    self.notified_version = rem_ver
                    self.on_update_found()
                return True
        except Exception:
            pass
        return False

    def download_and_install(self, on_progress, on_error, on_shutdown):
        if self.downloading:
            return
        self.downloading = True
        threading.Thread(
            target=self._download_thread,
            args=(on_progress, on_error, on_shutdown),
            daemon=True,
        ).start()

    def _download_thread(self, on_progress, on_error, on_shutdown):
        try:
            url = self.state.update_url or DEFAULT_SETUP_URL
            setup_path = os.path.join(tempfile.gettempdir(), f"Langley_Setup_{self.state.update_version}.exe")

            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                downloaded = 0
                with open(setup_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int((downloaded / total) * 100)
                            on_progress(min(99, pct), f"Downloading Update... {pct}%")
                        else:
                            mb = downloaded / (1024 * 1024)
                            on_progress(50, f"Downloading Update... {mb:.1f} MB")

            on_progress(100, "Download complete! Launching installer...")
            time.sleep(0.5)

            subprocess.Popen([setup_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"])
            time.sleep(0.3)
            on_shutdown()
        except Exception as e:
            self.downloading = False
            on_error(str(e))


class MediaController:
    VK_NEXT = 0xB0
    VK_PREV = 0xB1
    VK_PLAY_PAUSE = 0xB3

    def __init__(self, state, on_ui, on_push):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push
        self.stop_evt = threading.Event()
        self.last_title = ""
        self.last_artist = ""

    def start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        self.stop_evt.set()

    def _worker(self):
        while not self.stop_evt.is_set():
            self.poll_now()
            time.sleep(1.0)

    def poll_now(self):
        user32 = ctypes.windll.user32
        spotify_title = None
        spotify_running = False
        other_media = None

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_cb(hwnd, _):
            nonlocal spotify_title, spotify_running, other_media
            length = user32.GetWindowTextLengthW(hwnd)
            if length < 2:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            t = buf.value.strip()
            if not t:
                return True

            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                pname = psutil.Process(pid.value).name().lower()
            except Exception:
                return True

            if pname == "spotify.exe":
                spotify_running = True
                if t not in ("Default IME", "MSCTFIME UI", "GDI+ Window", "MediaContextNotificationWindow"):
                    if " - " in t and not t.lower().startswith("spotify"):
                        spotify_title = t

            elif pname in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"):
                if " - youtube music" in t.lower():
                    clean = re.sub(r"\s*-\s*YouTube Music.*$", "", t, flags=re.I).strip()
                    clean = re.sub(r"\s*-\s*(Google Chrome|Microsoft Edge|Brave|Firefox|Opera).*$", "", clean, flags=re.I).strip()
                    other_media = ("YouTube Music", clean)
                elif " - youtube" in t.lower() and not other_media:
                    clean = re.sub(r"\s*-\s*YouTube.*$", "", t, flags=re.I).strip()
                    clean = re.sub(r"\s*-\s*(Google Chrome|Microsoft Edge|Brave|Firefox|Opera).*$", "", clean, flags=re.I).strip()
                    other_media = ("YouTube", clean)
                elif "on soundcloud" in t.lower() and not other_media:
                    clean = re.sub(r"\s*on SoundCloud.*$", "", t, flags=re.I).strip()
                    other_media = ("SoundCloud", clean)

            elif pname in ("amazon music.exe", "amazonmusic.exe") and not other_media:
                if t not in ("Amazon Music", "Default IME"):
                    other_media = ("Amazon Music", t)

            elif pname in ("applemusic.exe", "itunes.exe") and not other_media:
                if " - " in t:
                    other_media = ("Apple Music", t)

            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        app_name = "No Media Detected"
        artist = ""
        title = ""
        playing = False

        if spotify_title:
            app_name = "Spotify"
            playing = True
            parts = spotify_title.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
            self.last_artist, self.last_title = artist, title
        elif spotify_running and self.last_title:
            app_name = "Spotify"
            playing = False
            artist, title = self.last_artist, self.last_title
        elif other_media:
            app_name, raw_txt = other_media
            playing = True
            if " - " in raw_txt:
                p = raw_txt.split(" - ", 1)
                artist, title = p[0].strip(), p[1].strip()
            else:
                artist, title = "", raw_txt
            self.last_artist, self.last_title = artist, title

        changed = (
            self.state.media_app != app_name
            or self.state.media_artist != artist
            or self.state.media_title != title
            or self.state.media_playing != playing
        )

        if playing:
            self.state.media_pos += 1
        elif not title:
            self.state.media_pos = 0

        self.state.media_app = app_name
        self.state.media_artist = artist
        self.state.media_title = title
        self.state.media_playing = playing

        if changed:
            self.on_ui()
            if self.state.show_media_rpc:
                self.on_push()

    def _tap(self, vk):
        try:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        except Exception:
            pass

    def play_pause(self):
        self._tap(self.VK_PLAY_PAUSE)
        threading.Thread(target=self._delayed_poll, daemon=True).start()

    def next_track(self):
        self._tap(self.VK_NEXT)
        self.state.media_pos = 0
        threading.Thread(target=self._delayed_poll, daemon=True).start()

    def prev_track(self):
        self._tap(self.VK_PREV)
        self.state.media_pos = 0
        threading.Thread(target=self._delayed_poll, daemon=True).start()

    def _delayed_poll(self):
        time.sleep(0.3)
        self.poll_now()


class DiscordRPC:
    def __init__(self, cid):
        self.cid = str(cid)
        self.pipe = None
        self.lock = threading.Lock()
        self.connected = False

    def connect(self):
        with self.lock:
            self._close()
            for i in range(10):
                p = rf"\\?\pipe\discord-ipc-{i}"
                if not os.path.exists(p):
                    continue
                try:
                    self.pipe = open(p, "r+b", buffering=0)
                    self._send(0, {"v": 1, "client_id": self.cid})
                    self.connected = True
                    return True
                except OSError:
                    self._close()
            return False

    def _send(self, op, data):
        if not self.pipe:
            raise OSError()
        raw = json.dumps(data).encode("utf-8")
        self.pipe.write(struct.pack("<II", op, len(raw)) + raw)
        self.pipe.flush()
        hdr = self.pipe.read(8)
        if not hdr or len(hdr) < 8:
            raise OSError()
        _, size = struct.unpack("<II", hdr)
        if size > 0:
            self.pipe.read(size)

    def update(self, activity):
        with self.lock:
            if not self.connected:
                return False
            msg = {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": activity},
                "nonce": str(time.time()),
            }
            try:
                self._send(1, msg)
                return True
            except OSError:
                self._close()
                return False

    def clear(self):
        return self.update(None)

    def _close(self):
        self.connected = False
        if self.pipe:
            try:
                self.pipe.close()
            except Exception:
                pass
            self.pipe = None

    def close(self):
        with self.lock:
            if self.connected and self.pipe:
                try:
                    self._send(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": None}, "nonce": "0"})
                except Exception:
                    pass
            self._close()


class Cosmetics:
    BASE = "https://fortnite-api.com/v2/cosmetics/br"

    def __init__(self):
        self.cache = {}

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
        fb = f"https://fortnite-api.com/images/cosmetics/br/{cid}/icon.png"
        try:
            r = requests.get(f"{self.BASE}/{cid}", params={"language": "en"}, timeout=3.5)
            if r.status_code == 200:
                d = r.json().get("data") or {}
                name = d.get("name") or "Fortnite Outfit"
                imgs = d.get("images") or {}
                icon = imgs.get("icon") or imgs.get("smallIcon") or imgs.get("featured") or fb
                self.cache[cid] = (name, icon)
                return name, icon
        except requests.RequestException:
            pass
        return None

    def get_name(self, name):
        k = name.strip().lower()
        if k in self.cache:
            return self.cache[k]
        try:
            r = requests.get(f"{self.BASE}/search", params={"name": name.strip(), "language": "en"}, timeout=3.5)
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
        return None


class EpicClient:
    TAG_1 = "urn:epic:member:langley_s"
    TAG_2 = "Default:LangleyUser_s"

    re_char = re.compile(r"AthenaCharacter:(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)", re.I)
    re_path = re.compile(r"/Cosmetics/Characters/[^\"\'\s\\]*?(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)", re.I)
    re_cid = re.compile(r"\b(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)\b", re.I)

    def __init__(self, state, cosmetics, on_ui, on_push):
        self.state = state
        self.cosmetics = cosmetics
        self.on_ui = on_ui
        self.on_push = on_push
        self.http = requests.Session()
        self.token = None
        self.account_id = None
        self.expires = 0.0
        self.busy = False
        self.loadouts = {}
        self.mate_cids = set()
        self.own_party_cid = None
        self.sent_party_id = None
        self.name_cache = {}
        self.raw_friends_cache = []

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

    def restore(self):
        raw = Reg.get("EpicAuthData")
        if not raw:
            return False
        try:
            saved = json.loads(raw)
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
            ex = self.http.get(
                f"{OAUTH_URL}/account/api/oauth/exchange",
                headers={"Authorization": f"bearer {sw_token}"},
                timeout=6,
            )
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
            acc = adata["account_id"]
            tok = adata["access_token"]

            dev = None
            dr = self.http.post(
                f"{OAUTH_URL}/account/api/public/account/{acc}/deviceAuth",
                headers={"Authorization": f"bearer {tok}"},
                timeout=6,
            )
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
            r = self.http.post(
                url,
                headers={"Authorization": f"bearer {self.token}", "Content-Type": "application/json"},
                json={},
                timeout=4.5,
            )
            if r.status_code != 200:
                return False

            changes = r.json().get("profileChanges") or []
            if not changes:
                return False

            prof = changes[0].get("profile") or {}
            attrs = (prof.get("stats") or {}).get("attributes") or {}
            changed = False

            lvl = attrs.get("book_level") or attrs.get("level")
            if lvl and int(lvl) >= 1:
                v = int(lvl)
                if v != self.state.season_level:
                    self.state.season_level = v
                    Reg.set("SeasonLevel", v, winreg.REG_DWORD)
                    changed = True

            return changed
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
            r = self.http.get(
                f"{FRIENDS_URL}/friends/api/v1/{self.account_id}/summary",
                headers={"Authorization": f"bearer {self.token}"},
                timeout=4.0,
            )
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
            is_online = False
            status_txt = "Offline"

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

        def sort_key(item):
            if item["in_party"] and item["is_langley"]:
                rank = 0
            elif item["in_party"]:
                rank = 1
            elif item["online"]:
                rank = 2
            elif item["favorite"]:
                rank = 3
            else:
                rank = 4
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
            pid = p.get("id")
            pcfg = p.get("config") or {}
            pmeta = p.get("meta") or {}
            members = p.get("members") or []
            changed = False

            sz = max(1, len(members))
            msz = int(pcfg.get("max_size") or 4)
            if msz > 16:
                msz = 4
            if sz != self.state.party_size or msz != self.state.party_max:
                self.state.party_size = sz
                self.state.party_max = max(sz, msz)
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

            me = None
            peers = []
            new_party_map = {}
            new_mate_cids = set()

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

            changed_cid = None
            first_cid = None
            for k in loadout_keys:
                blob = str(mmeta.get(k) or "")
                if not blob:
                    continue
                raw_c = self._extract_cid(blob)
                if not raw_c:
                    continue
                c = Cosmetics.clean_id(raw_c)
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


class Engine:
    re_acc = re.compile(r"(?:-epicuserid=|AccountId=|LocalUserId=)([0-9a-fA-F]{32})", re.I)
    re_any_hex = re.compile(r"\b([0-9a-fA-F]{32})\b")
    re_usr = re.compile(r'(?:-epicusername=|DisplayName=|UserName=)"?([^"\r\n\t]+?)"?(?:\s+-|\s*$|\s*\[|\s*\()', re.I)
    re_skin = re.compile(
        r"(?:characterPrimaryAssetId|characterDef|AthenaCharacter:|LoadoutSchema_Character|PutModularCosmeticLoadout).*?"
        r"(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)",
        re.I,
    )
    re_mode = re.compile(
        r'(?:PlaylistName(?:_s)?|CurrentPlaylist|SelectedPlaylist|mnemonic")[\\"\':=\s]+(playlist_[A-Za-z0-9_]+)',
        re.I,
    )
    re_lvl = re.compile(r'(?:passLevel|seasonLevel|season_level|book_level)(?:\\"|["\'\s:=])+?(\d{1,4})\b', re.I)
    re_pres = re.compile(r"([0-9a-fA-F]{32}).*?(?:StatusStr|Status|Presence)[^A-Za-z0-9]+([^,\r\n\]\}]{2,40})", re.I)

    def __init__(self, state, on_ui, on_update_found):
        self.state = state
        self.on_ui = on_ui
        self.cosmetics = Cosmetics()
        self.rpc = DiscordRPC(CLIENT_ID)
        self.epic = EpicClient(state, self.cosmetics, on_ui, lambda: self.sync_rpc(force=True))
        self.media = MediaController(state, on_ui, lambda: self.sync_rpc(force=True))
        self.updater = AutoUpdater(state, on_update_found)
        self.stop_evt = threading.Event()
        self.last_sync = 0.0
        self.last_snap = None
        self.cleared = True
        self.in_frontend = True
        self.pending_skin_id = None

    def start(self):
        enable_log_flags()
        if not self.state.skin_id or "wikimedia" in self.state.skin_icon:
            threading.Thread(target=self._init_skin, daemon=True).start()
        self.media.start()
        self.updater.start()
        threading.Thread(target=self._epic_worker, daemon=True).start()
        threading.Thread(target=self._log_worker, daemon=True).start()

    def _init_skin(self):
        if self.state.skin_id:
            res = self.cosmetics.get_id(self.state.skin_id)
            if res:
                self.state.skin_name, self.state.skin_icon = res
                self.on_ui()
                return
        res = self.cosmetics.get_name(self.state.skin_name) or self.cosmetics.get_name("Charlotte")
        if res:
            self.state.skin_name, self.state.skin_icon = res
            self.on_ui()

    def stop(self):
        self.stop_evt.set()
        self.updater.stop()
        self.media.stop()
        self.rpc.close()

    @staticmethod
    def is_fn_running():
        try:
            for p in psutil.process_iter(["name"]):
                n = (p.info.get("name") or "").lower()
                if n.startswith("fortniteclient-") or n == "fortnite.exe":
                    return True
        except Exception:
            pass
        return False

    def _snap(self):
        return (
            self.state.in_match,
            self.state.mode,
            self.state.skin_name,
            self.state.skin_icon,
            self.state.epic_name,
            self.state.party_size,
            self.state.party_max,
            tuple(self.state.peers),
            self.state.season_level,
            self.state.show_media_rpc,
            self.state.media_str() if (self.state.show_media_rpc and self.state.media_playing) else "",
        )

    def clear_rpc(self):
        if not self.rpc.connected or self.cleared:
            return
        if self.rpc.clear():
            self.cleared = True
            self.last_snap = None
        else:
            self.state.discord_ok = False
            self.on_ui()

    def sync_rpc(self, force=False):
        if not self.state.active or not self.state.running:
            self.clear_rpc()
            return
        if not self.rpc.connected:
            return

        now = time.time()
        snap = self._snap()
        if not force:
            if snap == self.last_snap and not self.cleared:
                return
            if now - self.last_sync < 0.8:
                return

        loc_txt = "In Match" if self.state.in_match else "In Lobby"
        if self.state.peers:
            p_names = ", ".join(self.state.peers[:2])
            details = f"{loc_txt} • {self.state.mode} (w/ {p_names} on Lang!ley)"
        else:
            details = f"{loc_txt} • {self.state.mode}"

        ptag = "Solo" if self.state.party_size <= 1 else f"Party ({self.state.party_size}/{self.state.party_max})"
        if self.state.peers:
            ptag = f"Lang!ley Squad ({len(self.state.peers) + 1})"

        if self.state.epic_name:
            state_txt = f"{self.state.epic_name} • Season Level {self.state.season_level} • {ptag}"
        else:
            state_txt = f"Season Level {self.state.season_level} • {ptag}"

        small_txt = "Lang!ley by asukaa.de"
        if self.state.show_media_rpc and self.state.media_playing and self.state.media_title:
            song = self.state.media_str()
            if len(song) > 42:
                song = song[:39] + "..."
            state_txt = f"{state_txt} • 🎵 {song}"
            small_txt = f"🎵 {self.state.media_app}: {song}"

        payload = {
            "name": "Fortnite with Lang!ley",
            "details": details,
            "state": state_txt[:128],
            "timestamps": {"start": self.state.start_ts},
            "assets": {
                "large_image": self.state.skin_icon or FALLBACK_LOGO,
                "large_text": self.state.skin_name if len(self.state.skin_name) >= 2 else "Fortnite Outfit",
                "small_image": "asukaa_logo",
                "small_text": small_txt[:128],
            },
            "buttons": [
                {"label": "Visit Website", "url": WEB_URL},
                {"label": "Get Lang!ley", "url": LANGLEY_URL},
            ],
        }

        if self.rpc.update(payload):
            self.last_sync = now
            self.last_snap = snap
            self.cleared = False
            self.state.discord_ok = True
        else:
            self.state.discord_ok = False
            self.on_ui()

    def _is_mate_line(self, line):
        if "LogParty" in line or "LogOnline" in line or "Presence" in line or "Remote" in line:
            return True
        for hid in self.re_any_hex.findall(line):
            h = hid.lower()
            if h in self.state.party_members_info:
                return True
            if self.state.account_id and h != self.state.account_id and ("AccountId" in line or "UserId" in line or "MCP" in line):
                return True
        return False

    def _read_line(self, line, live=False):
        changed = False

        if not self.state.account_id:
            m = self.re_acc.search(line)
            if m:
                self.state.account_id = m.group(1).lower()

        if not self.state.epic_name and ("-epicusername=" in line or "DisplayName=" in line):
            m = self.re_usr.search(line)
            if m:
                n = m.group(1).strip()
                if 2 <= len(n) <= 32 and "EpicAccountId" not in n and "=" not in n:
                    self.state.epic_name = n
                    Reg.set("EpicName", n)
                    changed = True

        if "Presence" in line or "LogOnlinePresence" in line:
            mpres = self.re_pres.search(line)
            if mpres:
                f_aid = mpres.group(1).lower()
                f_st = mpres.group(2).strip(" \"':=")
                if f_aid != self.state.account_id and len(f_st) >= 2:
                    self.state.log_online_friends[f_aid] = {"status": f_st[:36], "ts": time.time()}

        if (
            ("LogNet: Browse:" in line and ("Frontend" in line or "FortniteEntry" in line))
            or ("LoadMap:" in line and ("Frontend" in line or "FortniteEntry" in line))
            or "Returning to Frontend" in line
            or "ReturningToFrontEnd" in line
            or "current=LeavingMap" in line
            or "to LeavingMap" in line
            or "WaitingPostMatch" in line
        ):
            self.in_frontend = True
            if self.state.in_match:
                self.state.in_match = False
                changed = True
                if live and self.state.epic_ok:
                    threading.Thread(target=self.rescan, daemon=True).start()

        elif (
            ("LogNet: Browse:" in line and "Frontend" not in line and "FortniteEntry" not in line)
            or (
                "LoadMap:" in line
                and "Frontend" not in line
                and "FortniteEntry" not in line
                and ("Athena" in line or "Apollo" in line or "Asteria" in line or "Helios" in line)
            )
            or "EAthenaGamePhase::Warmup" in line
            or "EAthenaGamePhase::Aircraft" in line
        ):
            self.in_frontend = False
            if not self.state.in_match:
                self.state.in_match = True
                changed = True

        if self.in_frontend and not self.state.in_match and not self._is_mate_line(line):
            m = self.re_skin.search(line)
            if m:
                cid = Cosmetics.clean_id(m.group(1))
                is_locker_equip = "LoadoutSchema_Character" in line or "characterPrimaryAssetId" in line
                if cid and (is_locker_equip or cid not in self.epic.mate_cids):
                    if live:
                        if self.epic.update_skin(cid, immediate=True):
                            changed = True
                    else:
                        self.pending_skin_id = cid

        if not self._is_mate_line(line):
            if not self.state.account_id or self.state.account_id in line.lower():
                m = self.re_lvl.search(line)
                if m:
                    v = int(m.group(1))
                    if 1 < v <= 2000 and v != self.state.season_level:
                        self.state.season_level = v
                        Reg.set("SeasonLevel", v, winreg.REG_DWORD)
                        changed = True

        mp = self.re_mode.search(line)
        if mp:
            mode = parse_mode(mp.group(1))
            if mode and mode != self.state.mode:
                self.state.mode = mode
                changed = True

        return changed

    def rescan(self):
        if self.state.epic_ok:
            self.epic.fetch_party()
            self.epic.fetch_profile()
            self.epic.fetch_friends()
        self.media.poll_now()
        self.on_ui()
        self.sync_rpc(force=True)

    def _epic_worker(self):
        self.epic.restore()
        if self.state.epic_ok:
            self.epic.fetch_party()
            self.epic.fetch_profile()
            self.epic.fetch_friends()
            self.on_ui()
            self.sync_rpc(force=True)

        last_prof = time.time()
        last_friends = time.time()
        while not self.stop_evt.is_set():
            if self.state.epic_ok:
                if self.state.running:
                    if self.epic.fetch_party():
                        self.on_ui()
                        self.sync_rpc(force=True)
                now = time.time()
                if now - last_prof >= 25.0 and self.state.running:
                    last_prof = now
                    if self.epic.fetch_profile():
                        self.on_ui()
                        self.sync_rpc(force=False)
                if now - last_friends >= 20.0:
                    last_friends = now
                    self.epic.fetch_friends()
                time.sleep(1.2)
            else:
                time.sleep(2.0)

    def _log_worker(self):
        while not self.stop_evt.is_set():
            if not self.rpc.connected:
                if self.rpc.connect():
                    self.state.discord_ok = True
                    self.on_ui()
                    if self.state.running:
                        self.sync_rpc(force=True)
                else:
                    self.state.discord_ok = False
                    self.on_ui()

            if not self.is_fn_running():
                if self.state.running:
                    self.state.running = False
                    self.state.in_match = False
                    self.in_frontend = True
                    self.clear_rpc()
                    self.on_ui()
                time.sleep(1.5)
                continue

            if not self.state.running:
                enable_log_flags()
                self.state.running = True
                self.state.in_match = False
                self.in_frontend = True
                self.state.start_ts = int(time.time())
                self.on_ui()

            lpath = get_log_path()
            if not os.path.exists(lpath):
                self.sync_rpc(force=True)
                time.sleep(1.5)
                continue

            try:
                self.in_frontend = True
                self.pending_skin_id = None
                with open(lpath, "r", encoding="utf-8", errors="ignore") as f:
                    try:
                        sz = os.path.getsize(lpath)
                        if sz > 2_000_000:
                            f.seek(sz - 2_000_000)
                            f.readline()
                    except OSError:
                        pass

                    for line in f:
                        self._read_line(line, live=False)

                    if self.pending_skin_id:
                        self.epic.update_skin(self.pending_skin_id, immediate=False)

                    if self.state.epic_ok:
                        self.epic.fetch_party()

                    self.on_ui()
                    self.sync_rpc(force=True)

                    while not self.stop_evt.is_set() and self.is_fn_running():
                        if not self.rpc.connected:
                            break
                        try:
                            if os.path.getsize(lpath) < f.tell():
                                break
                        except OSError:
                            break

                        line = f.readline()
                        if not line:
                            self.sync_rpc(force=False)
                            time.sleep(0.1)
                            continue

                        if self._read_line(line, live=True):
                            self.on_ui()
                            self.sync_rpc(force=True)
            except OSError:
                time.sleep(1.5)


class UpdatePromptModal(tk.Toplevel):
    def __init__(self, parent, pal, state, updater, on_shutdown):
        super().__init__(parent)
        self.parent = parent
        self.pal = pal
        self.state = state
        self.updater = updater
        self.on_shutdown = on_shutdown

        self.title("Lang!ley // Update Available")
        self.resizable(False, False)
        self.configure(bg=pal["outer_bg"])
        self.transient(parent)
        self.grab_set()

        self._build()
        self._fit_window()

    def _fit_window(self):
        self.update_idletasks()
        req_h = self.wrap.winfo_reqheight() + 24
        w = 430
        self.parent.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - req_h) // 2
        self.geometry(f"{w}x{req_h}+{max(0, x)}+{max(0, y)}")

    def _build(self):
        p = self.pal
        self.wrap = tk.Frame(
            self, bg=p["panel_bg"], highlightbackground=p["border_dark"], highlightthickness=2, padx=16, pady=14
        )
        self.wrap.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = tk.Frame(self.wrap, bg=p["border_dark"], padx=10, pady=6)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(
            hdr,
            text=f"⚡ UPDATE AVAILABLE  //  v{APP_VERSION}  ➔  v{self.state.update_version}",
            font=("Segoe UI", 9, "bold"),
            fg=p["status_ok"],
            bg=p["border_dark"],
        ).pack(side="left")

        msg = (
            f"A new version of Lang!ley (v{self.state.update_version}) is ready.\n"
            "Would you like to download and install the update now?"
        )
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
            self.wrap, bg=p["card_bg"], highlightbackground=p["border_light"], highlightthickness=1, padx=12, pady=8
        )
        notes_box.pack(fill="x", pady=(0, 12))
        tk.Label(
            notes_box, text="WHAT'S NEW / CHANGELOG:", font=("Segoe UI", 8, "bold"), fg=p["status_warn"], bg=p["card_bg"], anchor="w"
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
            self.prog_frame, text="Preparing download...", font=("Segoe UI", 8, "bold"), fg=p["status_ok"], bg=p["panel_bg"], anchor="w"
        )
        self.lbl_prog.pack(fill="x", pady=(0, 4))
        self.prog_cv = tk.Canvas(self.prog_frame, height=10, bg=p["border_dark"], highlightthickness=0)
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
            on_progress=lambda pct, txt: self.after(0, lambda: self._update_prog(pct, txt)),
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
        self.prog_cv.create_rectangle(0, 0, fill_w, 10, fill=self.pal["status_ok"], outline="")

    def _on_err(self, err):
        if not self.winfo_exists():
            return
        self.lbl_prog.config(text=f"Update failed: {err[:45]}", fg=self.pal["status_err"])
        self.btn_install.config(state="normal", text="Retry Update")
        self.btn_later.config(state="normal")


class EpicPromptModal(tk.Toplevel):
    def __init__(self, parent, pal, on_link):
        super().__init__(parent)
        self.parent = parent
        self.pal = pal
        self.on_link = on_link
        self.open_more = False

        self.title("Lang!ley // Epic Games Connection")
        self.resizable(False, False)
        self.configure(bg=pal["outer_bg"])
        self.transient(parent)
        self.grab_set()

        self._build()
        self._fit_window(center=True)

    def _fit_window(self, center=False):
        self.update_idletasks()
        req_h = self.wrap.winfo_reqheight() + 24
        w = 440
        if center:
            self.parent.update_idletasks()
            x = self.parent.winfo_rootx() + (self.parent.winfo_width() - w) // 2
            y = self.parent.winfo_rooty() + (self.parent.winfo_height() - req_h) // 2
            self.geometry(f"{w}x{req_h}+{max(0, x)}+{max(0, y)}")
        else:
            self.geometry(f"{w}x{req_h}")

    def _build(self):
        p = self.pal
        self.wrap = tk.Frame(
            self, bg=p["panel_bg"], highlightbackground=p["border_dark"], highlightthickness=2, padx=16, pady=14
        )
        self.wrap.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = tk.Frame(self.wrap, bg=p["border_dark"], padx=10, pady=6)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(
            hdr, text="⚠ EPIC GAMES ACCOUNT NOT LINKED", font=("Segoe UI", 9, "bold"), fg=p["status_warn"], bg=p["border_dark"]
        ).pack(side="left")

        msg = (
            "Your Epic Games account is currently not linked to Lang!ley.\n\n"
            "Linking your account is optional, but strongly recommended to unlock "
            "the full scope of the app (Epic Username in Discord RPC, Friendlist, "
            "Lang!ley Squad Detection, Season Level, and 100% accurate Outfit syncing)."
        )
        tk.Label(
            self.wrap,
            text=msg,
            font=("Segoe UI", 9),
            fg=p["text_primary"],
            bg=p["panel_bg"],
            justify="left",
            anchor="nw",
            wraplength=380,
        ).pack(fill="x", pady=(0, 12))

        self.more_frame = tk.Frame(
            self.wrap, bg=p["card_bg"], highlightbackground=p["border_light"], highlightthickness=1, padx=12, pady=10
        )
        info = (
            "SECURITY & PRIVACY INFORMATION:\n\n"
            "• 100% Local Storage on Your PC:\n"
            "  Your authentication token is stored exclusively on your own computer "
            "inside your personal Windows Registry (HKEY_CURRENT_USER).\n\n"
            "• Zero External Servers:\n"
            "  Lang!ley has no backend server and never collects or shares your data. "
            "All requests go directly between your PC and official Epic Games servers.\n\n"
            "• Official Browser Login:\n"
            "  You sign in directly on the official Epic Games website in your browser. "
            "Lang!ley never sees your password or 2FA codes.\n\n"
            "• Instant Unlink:\n"
            "  You can unlink your account at any time with a single click."
        )
        tk.Label(
            self.more_frame,
            text=info,
            font=("Segoe UI", 8),
            fg=p["text_primary"],
            bg=p["card_bg"],
            justify="left",
            anchor="nw",
            wraplength=355,
        ).pack(fill="x", anchor="nw")

        self.bar = tk.Frame(self.wrap, bg=p["panel_bg"])
        self.bar.pack(fill="x", side="bottom", pady=(4, 0))

        tk.Button(
            self.bar, text="Link Epic", command=self._do_link, font=("Segoe UI", 9, "bold"),
            bg=p["border_dark"], fg=p["status_ok"], activebackground=p["outer_bg"],
            activeforeground=p["border_dark"], relief="flat", cursor="hand2", pady=5
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_more = tk.Button(
            self.bar, text="Read More", command=self._toggle, font=("Segoe UI", 9, "bold"),
            bg=p["card_bg"], fg=p["text_primary"], activebackground=p["outer_bg"],
            activeforeground=p["border_dark"], relief="flat", cursor="hand2", pady=5
        )
        self.btn_more.pack(side="left", expand=True, fill="x", padx=4)

        tk.Button(
            self.bar, text="Cancel", command=self.destroy, font=("Segoe UI", 9, "bold"),
            bg=p["card_bg"], fg=p["text_muted"], activebackground=p["outer_bg"],
            activeforeground=p["border_dark"], relief="flat", cursor="hand2", pady=5
        ).pack(side="right", expand=True, fill="x", padx=(4, 0))

    def _do_link(self):
        self.destroy()
        self.on_link()

    def _toggle(self):
        if not self.open_more:
            self.more_frame.pack(fill="x", pady=(0, 12), before=self.bar)
            self.btn_more.config(text="Hide Info")
            self.open_more = True
        else:
            self.more_frame.pack_forget()
            self.btn_more.config(text="Read More")
            self.open_more = False
        self._fit_window(center=False)


class LangleyApp(tk.Tk):
    PAL = {
        "outer_bg": "#B2AB99",
        "panel_bg": "#6E695A",
        "card_bg": "#5D584B",
        "border_dark": "#454138",
        "border_light": "#DCD6C4",
        "text_primary": "#F0EAD8",
        "text_muted": "#C2B9A7",
        "status_ok": "#C8D6B9",
        "status_warn": "#E6D0A3",
        "status_err": "#D6A79A",
    }

    def __init__(self, minimized=False):
        super().__init__()
        self.state = SessionState()
        self.engine = Engine(
            self.state,
            on_ui=lambda: self.after(0, self.refresh_ui),
            on_update_found=lambda: self.after(0, self._notify_update_available),
        )
        self.tray = None
        self.update_modal = None
        self.current_tab = "dashboard"
        self.friends_filter_online = False

        self.title(APP_TITLE)
        self.geometry("460x548")
        self.resizable(False, False)
        self.configure(bg=self.PAL["outer_bg"])

        self.pil_icon = get_app_icon()
        self._setup_icons()

        self._draw_bg()
        self._build_widgets()
        self._init_tray()

        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.engine.start()
        self.after(1000, self._tick)

        if minimized:
            self.withdraw()
        else:
            self.after(400, self._warn_unlinked)

    def _setup_icons(self):
        try:
            buf_big = io.BytesIO()
            self.pil_icon.resize((64, 64), Image.LANCZOS).save(buf_big, format="PNG")
            self._tk_ico_big = tk.PhotoImage(data=buf_big.getvalue())
            self.iconphoto(True, self._tk_ico_big)
        except Exception:
            pass

        try:
            buf_hdr = io.BytesIO()
            self.pil_icon.resize((22, 22), Image.LANCZOS).save(buf_hdr, format="PNG")
            self._tk_ico_hdr = tk.PhotoImage(data=buf_hdr.getvalue())
        except Exception:
            self._tk_ico_hdr = None

        try:
            ico_path = os.path.join(tempfile.gettempdir(), "langley_window_icon.ico")
            self.pil_icon.resize((64, 64), Image.LANCZOS).save(
                ico_path, format="ICO", sizes=[(16, 16), (32, 32), (64, 64)]
            )
            self.iconbitmap(default=ico_path)
        except Exception:
            pass

    @staticmethod
    def _fmt_sec(sec):
        sec = max(0, int(sec))
        m, s = divmod(sec, 60)
        return f"{m:02d}:{s:02d}"

    def _tick(self):
        if self.state.running:
            t = self.state.timer_str()
            st = "In Match" if self.state.in_match else "In Lobby"
            col = self.PAL["status_ok"] if self.state.in_match else self.PAL["status_warn"]
            self.lbl_state.config(text=f"{st}  •  ⏱ {t}", fg=col)
        self.after(1000, self._tick)

    def _warn_unlinked(self):
        if not Reg.get("EpicAuthData") and not self.state.epic_ok:
            EpicPromptModal(self, self.PAL, self._epic_action)

    def _notify_update_available(self):
        self.refresh_ui()
        if self.tray and not self.winfo_viewable():
            try:
                self.tray.notify(
                    f"Version {self.state.update_version} is available! Click to choose whether to install.",
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
            pystray.MenuItem(f"Open {APP_TITLE}", lambda *_: self.after(0, self._show), default=True),
            pystray.MenuItem("Play / Pause Media", lambda *_: self.engine.media.play_pause()),
            pystray.MenuItem("Next Track", lambda *_: self.engine.media.next_track()),
            pystray.MenuItem("Check for Updates", lambda *_: threading.Thread(target=lambda: self.engine.updater.check_now(manual=True), daemon=True).start()),
            pystray.MenuItem("Refresh Stats Now", lambda *_: threading.Thread(target=self.engine.rescan, daemon=True).start()),
            pystray.MenuItem("Visit asukaa.de", lambda *_: webbrowser.open(WEB_URL)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Completely", self.shutdown),
        )
        self.tray = pystray.Icon(REG_NAME, img, APP_TITLE, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _show(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def shutdown(self, *_):
        if self.tray:
            self.tray.stop()
        self.engine.stop()
        self.after(0, self.destroy)

    def _draw_bg(self):
        p = self.PAL
        self.cv = tk.Canvas(self, width=460, height=548, bg=p["outer_bg"], highlightthickness=0)
        self.cv.pack(fill="both", expand=True)

        self.cv.create_rectangle(22, 22, 438, 526, fill=p["panel_bg"], outline=p["border_light"], width=2)
        self.cv.create_rectangle(16, 16, 444, 532, outline=p["border_dark"], width=2)

        for x1, y1, x2, y2 in [(8, 8, 16, 16), (444, 8, 452, 16), (8, 532, 16, 540), (444, 532, 452, 540)]:
            self.cv.create_rectangle(x1, y1, x2, y2, fill=p["border_dark"], outline="")

        for r, c in [(145, "#757061"), (105, "#7E7869"), (65, "#878172")]:
            self.cv.create_oval(230 - r, 274 - r, 230 + r, 274 + r, fill=c, outline="")

    def _build_widgets(self):
        p = self.PAL

        hdr = tk.Frame(self.cv, bg=p["border_dark"], padx=10, pady=7)
        self.cv.create_window(230, 50, window=hdr, width=386, height=38)

        if self._tk_ico_hdr:
            tk.Label(hdr, image=self._tk_ico_hdr, bg=p["border_dark"]).pack(side="left", padx=(0, 7))

        tk.Label(
            hdr,
            text="Lang!ley | Fortnite Stats Discord RPC",
            font=("Segoe UI", 9, "bold"),
            fg=p["text_primary"],
            bg=p["border_dark"],
        ).pack(side="left")

        lnk = tk.Label(hdr, text="asukaa.de ↗", font=("Segoe UI", 8, "underline"), fg=p["text_muted"], bg=p["border_dark"], cursor="hand2")
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

        sbox = tk.Frame(self.cv, bg=p["card_bg"], highlightbackground=p["border_light"], highlightthickness=1, padx=12, pady=5)
        self.cv.create_window(230, 92, window=sbox, width=386, height=32)

        self.lbl_discord = tk.Label(sbox, text="● Discord: Connecting...", font=("Segoe UI", 9, "bold"), fg=p["status_warn"], bg=p["card_bg"])
        self.lbl_discord.pack(side="left")

        self.lbl_game = tk.Label(sbox, text="● Fortnite: Offline", font=("Segoe UI", 9, "bold"), fg=p["text_muted"], bg=p["card_bg"])
        self.lbl_game.pack(side="right")

        tbar = tk.Frame(self.cv, bg=p["panel_bg"])
        self.cv.create_window(230, 128, window=tbar, width=386, height=28)

        self.tab_btns = {}
        for key, label in [
            ("dashboard", "DASHBOARD"),
            ("friends", "FRIENDS & SQUAD"),
            ("media", "MEDIA / SPOTIFY"),
        ]:
            b = tk.Button(
                tbar,
                text=label,
                command=lambda k=key: self._switch_tab(k),
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                cursor="hand2",
            )
            b.pack(side="left", expand=True, fill="both", padx=2)
            self.tab_btns[key] = b

        self.view_container = tk.Frame(self.cv, bg=p["panel_bg"])
        self.cv.create_window(230, 298, window=self.view_container, width=386, height=296)

        self._build_dashboard_tab()
        self._build_friends_tab()
        self._build_media_tab()

        bbar = tk.Frame(self.cv, bg=p["panel_bg"])
        self.cv.create_window(230, 488, window=bbar, width=386, height=34)

        self.btn_epic = tk.Button(
            bbar, text="Link Epic", command=self._epic_action, font=("Segoe UI", 8, "bold"),
            bg=p["border_dark"], fg=p["status_warn"], activebackground=p["outer_bg"],
            activeforeground=p["border_dark"], relief="flat", cursor="hand2"
        )
        self.btn_epic.pack(side="left", expand=True, fill="both", padx=(0, 3))

        self.btn_pause = tk.Button(
            bbar, text="Pause RPC", command=self._pause_action, font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"], fg=p["text_primary"], activebackground=p["outer_bg"],
            activeforeground=p["border_dark"], relief="flat", cursor="hand2"
        )
        self.btn_pause.pack(side="left", expand=True, fill="both", padx=3)

        tk.Button(
            bbar, text="Refresh", command=lambda: threading.Thread(target=self.engine.rescan, daemon=True).start(),
            font=("Segoe UI", 8, "bold"), bg=p["card_bg"], fg=p["text_primary"],
            activebackground=p["outer_bg"], activeforeground=p["border_dark"], relief="flat", cursor="hand2"
        ).pack(side="left", expand=True, fill="both", padx=3)

        tk.Button(
            bbar, text="To Tray", command=self.withdraw, font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"], fg=p["text_primary"], activebackground=p["outer_bg"],
            activeforeground=p["border_dark"], relief="flat", cursor="hand2"
        ).pack(side="left", expand=True, fill="both", padx=3)

        tk.Button(
            bbar, text="Quit", command=self.shutdown, font=("Segoe UI", 8, "bold"),
            bg=p["card_bg"], fg=p["status_err"], activebackground=p["outer_bg"],
            activeforeground=p["border_dark"], relief="flat", cursor="hand2"
        ).pack(side="right", fill="y", ipadx=8, padx=(3, 0))

        self._switch_tab("dashboard")

    def _build_dashboard_tab(self):
        p = self.PAL
        self.tab_dashboard = tk.Frame(self.view_container, bg=p["panel_bg"])

        card = tk.Frame(self.tab_dashboard, bg=p["card_bg"], highlightbackground=p["border_dark"], highlightthickness=2, padx=16, pady=10)
        card.pack(fill="both", expand=True, pady=(0, 8))

        tk.Label(card, text="PLAYING FORTNITE WITH LANG!LEY", font=("Segoe UI", 8, "bold"), fg=p["text_muted"], bg=p["card_bg"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.lbl_epic = self._row(card, "Epic Account", "Not Linked", 1)
        self.lbl_state = self._row(card, "State & Session Timer", "Waiting for Fortnite...", 2)
        self.lbl_mode = self._row(card, "Game Mode", "—", 3)
        self.lbl_party = self._row(card, "Party & Lang!ley Squad", "Solo (1/4)", 4)
        self.lbl_skin = self._row(card, "Current Outfit (PNG)", self.state.skin_name, 5)
        self.lbl_level = self._row(card, "Season Level", f"Season Level {self.state.season_level}", 6)
        self.lbl_dash_music = self._row(card, "Active Media", "No Media Playing", 7)

        cfg = tk.Frame(self.tab_dashboard, bg=p["card_bg"], highlightbackground=p["border_dark"], highlightthickness=1, padx=12, pady=5)
        cfg.pack(fill="x")

        self.v_auto = tk.BooleanVar(value=Reg.has_autostart())
        self.v_mini = tk.BooleanVar(value=bool(Reg.get("StartMinimized", 1)))

        tk.Checkbutton(
            cfg, text="Run automatically on Windows Startup", variable=self.v_auto, command=self._save_cfg,
            font=("Segoe UI", 8), fg=p["text_primary"], bg=p["card_bg"], selectcolor=p["border_dark"],
            activebackground=p["card_bg"], activeforeground=p["text_primary"], cursor="hand2"
        ).grid(row=0, column=0, sticky="w")

        tk.Checkbutton(
            cfg, text="Always start Minimized in System Tray (Background)", variable=self.v_mini, command=self._save_cfg,
            font=("Segoe UI", 8), fg=p["text_muted"], bg=p["card_bg"], selectcolor=p["border_dark"],
            activebackground=p["card_bg"], activeforeground=p["text_primary"], cursor="hand2"
        ).grid(row=1, column=0, sticky="w")

    def _build_friends_tab(self):
        p = self.PAL
        self.tab_friends = tk.Frame(self.view_container, bg=p["card_bg"], highlightbackground=p["border_dark"], highlightthickness=2, padx=12, pady=10)

        top = tk.Frame(self.tab_friends, bg=p["card_bg"])
        top.pack(fill="x", pady=(0, 6))

        self.lbl_friends_hdr = tk.Label(
            top, text="FORTNITE FRIENDS & PARTY", font=("Segoe UI", 8, "bold"), fg=p["text_muted"], bg=p["card_bg"]
        )
        self.lbl_friends_hdr.pack(side="left")

        self.btn_filter_friends = tk.Button(
            top, text="Filter: All", command=self._toggle_friends_filter,
            font=("Segoe UI", 8, "bold"), bg=p["border_dark"], fg=p["text_primary"],
            activebackground=p["outer_bg"], relief="flat", cursor="hand2", padx=8, pady=1
        )
        self.btn_filter_friends.pack(side="right")

        legend = tk.Frame(self.tab_friends, bg=p["border_dark"], padx=8, pady=4)
        legend.pack(fill="x", pady=(0, 6))
        tk.Label(legend, text="★ Lang!ley Squad (In Party)", font=("Segoe UI", 8, "bold"), fg=p["status_ok"], bg=p["border_dark"]).pack(side="left")
        tk.Label(legend, text="● In Party / Online", font=("Segoe UI", 8), fg=p["status_warn"], bg=p["border_dark"]).pack(side="right")

        list_wrap = tk.Frame(self.tab_friends, bg=p["border_dark"])
        list_wrap.pack(fill="both", expand=True)

        self.friends_canvas = tk.Canvas(list_wrap, bg=p["border_dark"], highlightthickness=0)
        sb = tk.Scrollbar(list_wrap, orient="vertical", command=self.friends_canvas.yview)
        self.friends_inner = tk.Frame(self.friends_canvas, bg=p["border_dark"])

        self.friends_window_id = self.friends_canvas.create_window((0, 0), window=self.friends_inner, anchor="nw", width=338)
        self.friends_canvas.configure(yscrollcommand=sb.set)

        self.friends_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tab_friends.bind("<Enter>", lambda _: self.bind_all("<MouseWheel>", self._on_mousewheel))
        self.tab_friends.bind("<Leave>", lambda _: self.unbind_all("<MouseWheel>"))

    def _on_mousewheel(self, event):
        if self.current_tab == "friends" and hasattr(self, "friends_canvas"):
            self.friends_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_media_tab(self):
        p = self.PAL
        self.tab_media = tk.Frame(self.view_container, bg=p["card_bg"], highlightbackground=p["border_dark"], highlightthickness=2, padx=16, pady=12)

        top = tk.Frame(self.tab_media, bg=p["card_bg"])
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="WINDOWS MEDIA & SPOTIFY CONTROLLER", font=("Segoe UI", 8, "bold"), fg=p["text_muted"], bg=p["card_bg"]).pack(side="left")
        self.lbl_media_badge = tk.Label(top, text="● IDLE", font=("Segoe UI", 8, "bold"), fg=p["text_muted"], bg=p["card_bg"])
        self.lbl_media_badge.pack(side="right")

        now_box = tk.Frame(self.tab_media, bg=p["border_dark"], highlightbackground=p["border_light"], highlightthickness=1, padx=14, pady=12)
        now_box.pack(fill="x", pady=(0, 10))

        self.lbl_media_app = tk.Label(now_box, text="SOURCE: NO MEDIA DETECTED", font=("Segoe UI", 8, "bold"), fg=p["status_warn"], bg=p["border_dark"], anchor="w")
        self.lbl_media_app.pack(fill="x")

        self.lbl_media_title = tk.Label(now_box, text="Play a song on Spotify, YT Music or Amazon Music", font=("Segoe UI", 10, "bold"), fg=p["text_primary"], bg=p["border_dark"], anchor="w")
        self.lbl_media_title.pack(fill="x", pady=(4, 2))

        self.lbl_media_artist = tk.Label(now_box, text="—", font=("Segoe UI", 9), fg=p["text_muted"], bg=p["border_dark"], anchor="w")
        self.lbl_media_artist.pack(fill="x")

        prog_wrap = tk.Frame(now_box, bg=p["border_dark"])
        prog_wrap.pack(fill="x", pady=(8, 0))

        self.lbl_time_cur = tk.Label(prog_wrap, text="00:00", font=("Segoe UI", 8), fg=p["text_muted"], bg=p["border_dark"])
        self.lbl_time_cur.pack(side="left")

        self.prog_canvas = tk.Canvas(prog_wrap, height=8, bg=p["card_bg"], highlightthickness=0)
        self.prog_canvas.pack(side="left", fill="x", expand=True, padx=8)

        self.lbl_time_end = tk.Label(prog_wrap, text="Live", font=("Segoe UI", 8), fg=p["text_muted"], bg=p["border_dark"])
        self.lbl_time_end.pack(side="right")

        ctrl = tk.Frame(self.tab_media, bg=p["card_bg"])
        ctrl.pack(fill="x", pady=(2, 12))

        for txt, cmd in [
            ("⏮ Prev", self.engine.media.prev_track),
            ("⏯ Play / Pause", self.engine.media.play_pause),
            ("⏭ Next", self.engine.media.next_track),
        ]:
            tk.Button(
                ctrl, text=txt, command=cmd, font=("Segoe UI", 8, "bold"),
                bg=p["border_dark"], fg=p["text_primary"], activebackground=p["outer_bg"],
                activeforeground=p["border_dark"], relief="flat", cursor="hand2", pady=6
            ).pack(side="left", expand=True, fill="x", padx=3)

        opt = tk.Frame(self.tab_media, bg=p["panel_bg"], padx=10, pady=8)
        opt.pack(fill="x")

        self.v_media_rpc = tk.BooleanVar(value=self.state.show_media_rpc)
        tk.Checkbutton(
            opt,
            text="Display currently playing Song in Discord RPC status",
            variable=self.v_media_rpc,
            command=self._toggle_media_rpc,
            font=("Segoe UI", 8, "bold"),
            fg=p["text_primary"],
            bg=p["panel_bg"],
            selectcolor=p["border_dark"],
            activebackground=p["panel_bg"],
            activeforeground=p["text_primary"],
            cursor="hand2",
        ).pack(anchor="w")

        tk.Label(
            opt,
            text="Supports Spotify, YouTube Music, Amazon Music, Apple Music & Browser Players.",
            font=("Segoe UI", 7),
            fg=p["text_muted"],
            bg=p["panel_bg"],
        ).pack(anchor="w", pady=(2, 0))

    def _switch_tab(self, tab_key):
        self.current_tab = tab_key
        p = self.PAL
        for k, b in self.tab_btns.items():
            if k == tab_key:
                b.config(bg=p["border_dark"], fg=p["status_ok"])
            else:
                b.config(bg=p["card_bg"], fg=p["text_muted"])

        for frame in (self.tab_dashboard, self.tab_friends, self.tab_media):
            frame.pack_forget()

        if tab_key == "dashboard":
            self.tab_dashboard.pack(fill="both", expand=True)
        elif tab_key == "friends":
            self.tab_friends.pack(fill="both", expand=True)
            self._render_friends_list()
        elif tab_key == "media":
            self.tab_media.pack(fill="both", expand=True)

    def _toggle_friends_filter(self):
        self.friends_filter_online = not self.friends_filter_online
        self.btn_filter_friends.config(text="Filter: Online/Party" if self.friends_filter_online else "Filter: All")
        self._render_friends_list()

    def _toggle_media_rpc(self):
        val = bool(self.v_media_rpc.get())
        self.state.show_media_rpc = val
        Reg.set("ShowMediaRPC", int(val), winreg.REG_DWORD)
        threading.Thread(target=lambda: self.engine.sync_rpc(force=True), daemon=True).start()

    def _render_friends_list(self):
        p = self.PAL
        for child in self.friends_inner.winfo_children():
            child.destroy()

        if not self.state.epic_ok:
            tk.Label(
                self.friends_inner,
                text="Link your Epic Games account to view your Fortnite Friendlist\nand highlight Lang!ley Squad members in your party.",
                font=("Segoe UI", 8),
                fg=p["text_muted"],
                bg=p["border_dark"],
                justify="center",
                pady=35,
            ).pack(fill="x")
            self.lbl_friends_hdr.config(text="FORTNITE FRIENDS (NOT LINKED)")
            self.friends_inner.update_idletasks()
            self.friends_canvas.config(scrollregion=self.friends_canvas.bbox("all"))
            return

        friends = self.state.friends_list
        if self.friends_filter_online:
            friends = [f for f in friends if f["in_party"] or f["online"]]

        in_party_cnt = sum(1 for f in self.state.friends_list if f["in_party"])
        online_cnt = sum(1 for f in self.state.friends_list if f["in_party"] or f["online"])
        total_cnt = len(self.state.friends_list)
        self.lbl_friends_hdr.config(text=f"PARTY: {in_party_cnt}  •  ONLINE: {online_cnt}  •  TOTAL: {total_cnt}")

        if not friends:
            tk.Label(
                self.friends_inner,
                text="No friends match the current filter.",
                font=("Segoe UI", 8),
                fg=p["text_muted"],
                bg=p["border_dark"],
                pady=30,
            ).pack(fill="x")
            self.friends_inner.update_idletasks()
            self.friends_canvas.config(scrollregion=self.friends_canvas.bbox("all"))
            return

        for f in friends:
            row_bg = p["card_bg"] if (f["in_party"] or f["online"]) else "#4F4B40"
            row = tk.Frame(self.friends_inner, bg=row_bg, padx=8, pady=5)
            row.pack(fill="x", pady=1, padx=2)

            if f["in_party"] and f["is_langley"]:
                name_fg = p["status_ok"]
                badge_txt = "★ LANG!LEY SQUAD"
                badge_fg = p["status_ok"]
            elif f["in_party"]:
                name_fg = p["status_warn"]
                badge_txt = "● IN PARTY"
                badge_fg = p["status_warn"]
            elif f["online"]:
                name_fg = p["text_primary"]
                badge_txt = f"● {f['status']}"
                badge_fg = p["status_ok"]
            else:
                name_fg = p["text_muted"]
                badge_txt = f"○ {f['status']}"
                badge_fg = p["text_muted"]

            tk.Label(row, text=f["name"][:24], font=("Segoe UI", 8, "bold"), fg=name_fg, bg=row_bg, anchor="w").pack(side="left")
            tk.Label(row, text=badge_txt, font=("Segoe UI", 8, "bold" if f["in_party"] else "normal"), fg=badge_fg, bg=row_bg, anchor="e").pack(side="right")

        self.friends_inner.update_idletasks()
        self.friends_canvas.config(scrollregion=self.friends_canvas.bbox("all"))

    def _row(self, parent, title, val, r):
        p = self.PAL
        tk.Label(parent, text=title, font=("Segoe UI", 9), fg=p["text_muted"], bg=p["card_bg"], anchor="w").grid(row=r, column=0, sticky="w", pady=2)
        lbl = tk.Label(parent, text=val, font=("Segoe UI", 9, "bold"), fg=p["text_primary"], bg=p["card_bg"], anchor="e")
        lbl.grid(row=r, column=1, sticky="e", pady=2)
        parent.grid_columnconfigure(1, weight=1)
        return lbl

    def _epic_action(self):
        if self.state.epic_ok:
            self.engine.epic.unlink()
            self.refresh_ui()
            threading.Thread(target=lambda: self.engine.sync_rpc(force=True), daemon=True).start()
        else:
            self.btn_epic.config(text="Linking...", fg=self.PAL["status_warn"])
            self.engine.epic.login(done_cb=lambda: self.engine.sync_rpc(force=True))

    def _save_cfg(self):
        Reg.update_startup(self.v_auto.get(), self.v_mini.get())

    def _pause_action(self):
        self.state.active = not self.state.active
        if self.state.active:
            self.btn_pause.config(text="Pause RPC")
            threading.Thread(target=lambda: self.engine.sync_rpc(force=True), daemon=True).start()
        else:
            self.btn_pause.config(text="Resume RPC")
            threading.Thread(target=self.engine.clear_rpc, daemon=True).start()
        self.refresh_ui()

    def refresh_ui(self):
        p = self.PAL
        s = self.state

        if s.update_available:
            self.btn_hdr_update.config(text="⚡ Update")
            self.btn_hdr_update.pack(side="right", padx=(0, 8))
        else:
            self.btn_hdr_update.pack_forget()

        if s.epic_ok:
            name = s.epic_name or "Linked Account"
            self.lbl_epic.config(text=f"{name} (Linked)", fg=p["status_ok"])
            self.btn_epic.config(text="Unlink Epic", fg=p["status_err"])
        else:
            if s.epic_name:
                self.lbl_epic.config(text=f"{s.epic_name} (Unlinked)", fg=p["status_warn"])
            else:
                self.lbl_epic.config(text="Not Linked", fg=p["text_muted"])
            self.btn_epic.config(text="Link Epic", fg=p["status_warn"])

        if not s.active:
            self.lbl_discord.config(text="● Discord: Paused", fg=p["status_warn"])
        elif s.discord_ok:
            self.lbl_discord.config(text="● Discord: Connected", fg=p["status_ok"])
        else:
            self.lbl_discord.config(text="● Discord: Disconnected", fg=p["status_err"])

        if s.running:
            self.lbl_game.config(text="● Fortnite: Running (RPC Active)", fg=p["status_ok"])
            t = s.timer_str()
            if s.in_match:
                self.lbl_state.config(text=f"In Match  •  ⏱ {t}", fg=p["status_ok"])
            else:
                self.lbl_state.config(text=f"In Lobby  •  ⏱ {t}", fg=p["status_warn"])
            self.lbl_mode.config(text=s.mode)
        else:
            self.lbl_game.config(text="● Fortnite: Offline (RPC Hidden)", fg=p["text_muted"])
            self.lbl_state.config(text="Offline (Waiting for Fortnite)", fg=p["text_muted"])
            self.lbl_mode.config(text="—")

        if s.peers:
            names = ", ".join(s.peers[:2])
            self.lbl_party.config(text=f"Party ({s.party_size}/{s.party_max}) • ★ {names}", fg=p["status_ok"])
        else:
            tag = "Solo" if s.party_size <= 1 else "Party"
            self.lbl_party.config(text=f"{tag} ({s.party_size}/{s.party_max})", fg=p["text_primary"])

        self.lbl_skin.config(text=s.skin_name)
        self.lbl_level.config(text=f"Season Level {s.season_level}")

        if s.media_title:
            m_str = s.media_str()
            state_ico = "▶" if s.media_playing else "⏸"
            self.lbl_dash_music.config(
                text=f"{state_ico} {m_str[:26]}{'...' if len(m_str) > 26 else ''}",
                fg=p["status_ok"] if s.media_playing else p["status_warn"],
            )
            self.lbl_media_app.config(text=f"SOURCE: {s.media_app.upper()}")
            self.lbl_media_title.config(text=s.media_title[:38])
            self.lbl_media_artist.config(text=s.media_artist[:42] if s.media_artist else "Unknown Artist")
            self.lbl_media_badge.config(
                text="● PLAYING" if s.media_playing else "● PAUSED",
                fg=p["status_ok"] if s.media_playing else p["status_warn"],
            )
        else:
            self.lbl_dash_music.config(text="No Media Playing", fg=p["text_muted"])
            self.lbl_media_app.config(text="SOURCE: NO MEDIA DETECTED")
            self.lbl_media_title.config(text="Play a song on Spotify, YT Music or Amazon Music")
            self.lbl_media_artist.config(text="—")
            self.lbl_media_badge.config(text="● IDLE", fg=p["text_muted"])

        self.lbl_time_cur.config(text=self._fmt_sec(s.media_pos))
        self.prog_canvas.delete("all")
        w = max(10, self.prog_canvas.winfo_width())
        if s.media_playing:
            fill_w = int(w * min(1.0, (s.media_pos % 210) / 210.0))
            self.prog_canvas.create_rectangle(0, 0, fill_w, 8, fill=p["status_ok"], outline="")


if __name__ == "__main__":
    set_app_id()
    kill_old_procs()
    start_hidden = ("--minimized" in sys.argv) and bool(Reg.get("StartMinimized", 1))
    app = LangleyApp(minimized=start_hidden)
    app.mainloop()