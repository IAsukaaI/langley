import re
import time
import ctypes
import threading
import psutil


class MediaController:
    VK_NEXT = 0xB0
    VK_PREV = 0xB1
    VK_PLAY_PAUSE = 0xB3

    def __init__(self, state, on_ui, on_push, scanner=None):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push
        self.scanner = scanner
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
            sleep_sec = 1.2 if self.state.media_playing else 2.4
            time.sleep(sleep_sec)

    def poll_now(self, snapshot=None):
        spotify_title = None
        spotify_running = False
        other_media = None

        if snapshot is None and self.scanner is not None:
            snapshot = self.scanner.get_snapshot()

        if snapshot is not None:
            procs, _, windows, _ = snapshot
            for p in procs:
                if p["name"] == "spotify.exe":
                    spotify_running = True
                    break
            for w in windows:
                pname = w["pname"]
                t = w["title"]
                if not t:
                    continue
                if pname == "spotify.exe":
                    spotify_running = True
                    if " - " in t and not t.lower().startswith("spotify"):
                        spotify_title = t
                elif pname in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"):
                    t_low = w["title_lower"]
                    if " - youtube music" in t_low:
                        clean = re.sub(r"\s*-\s*YouTube Music.*$", "", t, flags=re.I).strip()
                        clean = re.sub(r"\s*-\s*(Google Chrome|Microsoft Edge|Brave|Firefox|Opera).*$", "", clean, flags=re.I).strip()
                        other_media = ("YouTube Music", clean)
                    elif " - youtube" in t_low and not other_media:
                        clean = re.sub(r"\s*-\s*YouTube.*$", "", t, flags=re.I).strip()
                        clean = re.sub(r"\s*-\s*(Google Chrome|Microsoft Edge|Brave|Firefox|Opera).*$", "", clean, flags=re.I).strip()
                        other_media = ("YouTube", clean)
                    elif "on soundcloud" in t_low and not other_media:
                        clean = re.sub(r"\s*on SoundCloud.*$", "", t, flags=re.I).strip()
                        other_media = ("SoundCloud", clean)
                elif pname in ("amazon music.exe", "amazonmusic.exe") and not other_media:
                    if t not in ("Amazon Music", "Default IME"):
                        other_media = ("Amazon Music", t)
                elif pname in ("applemusic.exe", "itunes.exe") and not other_media:
                    if " - " in t:
                        other_media = ("Apple Music", t)
        else:
            user32 = ctypes.windll.user32
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

        app_name, artist, title, playing = "No Media Detected", "", "", False

        if spotify_title:
            app_name, playing = "Spotify", True
            parts = spotify_title.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
            self.last_artist, self.last_title = artist, title
        elif spotify_running and self.last_title:
            app_name, playing = "Spotify", False
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
        if self.scanner:
            self.scanner.get_snapshot(force=True)
        self.poll_now()
