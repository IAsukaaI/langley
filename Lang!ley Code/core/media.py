import base64
import datetime
import json
import re
import subprocess
import time
import ctypes
import threading
import psutil

_PS_SMTC_SCRIPT = r"""
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($WinRtTask, $ResultType) {
    $netTask = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
while (($cmd = [Console]::In.ReadLine()) -ne $null) {
    if ($cmd -eq 'exit') { break }
    try {
        $s = $mgr.GetCurrentSession()
        if ($s) {
            $info = $s.GetPlaybackInfo()
            $tl = $s.GetTimelineProperties()
            $mp = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
            $out = @{
                ok = $true
                app = [string]$s.SourceAppUserModelId
                playing = ([string]$info.PlaybackStatus -eq 'Playing')
                title = [string]$mp.Title
                artist = [string]$mp.Artist
                pos = [double]$tl.Position.TotalSeconds
                end = [double]$tl.EndTime.TotalSeconds
                upd = $tl.LastUpdatedTime.UtcDateTime.ToString('o')
            }
            [Console]::Out.WriteLine(($out | ConvertTo-Json -Compress))
        } else {
            [Console]::Out.WriteLine('{"ok":false}')
        }
    } catch {
        [Console]::Out.WriteLine('{"ok":false}')
    }
    [Console]::Out.Flush()
}
"""


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
        self._smtc_proc = None
        self._smtc_lock = threading.Lock()
        self._anchor_pos = 0.0
        self._anchor_dur = 0.0
        self._anchor_mono = 0.0
        self._anchor_playing = False
        self._last_smtc_ts = 0.0
        self._cached_smtc = None
        self._track_sig = None

    def start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        self.stop_evt.set()
        self._stop_smtc_proc()

    def _stop_smtc_proc(self):
        with self._smtc_lock:
            p = self._smtc_proc
            self._smtc_proc = None
        if p:
            try:
                if p.stdin:
                    p.stdin.write("exit\n")
                    p.stdin.flush()
            except Exception:
                pass
            try:
                p.terminate()
            except Exception:
                pass

    def _ensure_smtc_proc(self):
        if self._smtc_proc is not None and self._smtc_proc.poll() is None:
            return self._smtc_proc
        try:
            enc = base64.b64encode(_PS_SMTC_SCRIPT.encode("utf-16le")).decode("ascii")
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            self._smtc_proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", enc],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="ignore",
                startupinfo=si,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
            return self._smtc_proc
        except Exception:
            self._smtc_proc = None
            return None

    def _query_smtc(self, force=False):
        now = time.monotonic()
        if not force and self._cached_smtc is not None and (now - self._last_smtc_ts) < 0.9:
            return self._cached_smtc
        with self._smtc_lock:
            if self.stop_evt.is_set():
                return None
            p = self._ensure_smtc_proc()
            if not p or not p.stdin or not p.stdout:
                return None
            try:
                p.stdin.write("poll\n")
                p.stdin.flush()
                line = p.stdout.readline()
                if not line:
                    raise OSError("SMTC EOF")
                data = json.loads(line.strip())
                self._last_smtc_ts = time.monotonic()
                if isinstance(data, dict) and data.get("ok"):
                    self._cached_smtc = data
                    return data
                self._cached_smtc = None
                return None
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
                self._smtc_proc = None
                self._cached_smtc = None
                return None

    @staticmethod
    def _clean_smtc_app(raw_app):
        a = str(raw_app or "").strip()
        al = a.lower()
        if "spotify" in al:
            return "Spotify"
        if "chrome" in al or "msedge" in al or "firefox" in al or "brave" in al or "opera" in al:
            return "Browser Media"
        if "apple" in al or "itunes" in al:
            return "Apple Music"
        if "amazon" in al:
            return "Amazon Music"
        if "tidal" in al:
            return "TIDAL"
        if "vlc" in al:
            return "VLC"
        return a.replace(".exe", "").split("!")[-1].strip()[:24] or "Media Player"

    def current_pos(self):
        if self._anchor_playing and self._anchor_mono > 0:
            elapsed = max(0.0, time.monotonic() - self._anchor_mono)
            val = self._anchor_pos + elapsed
            if self._anchor_dur > 0:
                val = min(self._anchor_dur, val)
            return int(val)
        return max(0, int(self._anchor_pos))

    def _worker(self):
        while not self.stop_evt.is_set():
            self.poll_now(force_smtc=True)
            sleep_sec = 1.0 if self.state.media_playing else 2.0
            self.stop_evt.wait(sleep_sec)

    def poll_now(self, snapshot=None, force_smtc=False):
        smtc = self._query_smtc(force=force_smtc)
        app_name, artist, title, playing = "No Media Detected", "", "", False
        duration_sec = 0
        exact_pos = None

        if smtc and str(smtc.get("title") or "").strip():
            app_name = self._clean_smtc_app(smtc.get("app"))
            title = str(smtc.get("title") or "").strip()
            artist = str(smtc.get("artist") or "").strip()
            playing = bool(smtc.get("playing"))
            duration_sec = max(0, int(round(float(smtc.get("end") or 0.0))))
            base_pos = max(0.0, float(smtc.get("pos") or 0.0))
            upd_str = str(smtc.get("upd") or "").strip()
            if playing and upd_str:
                try:
                    upd_dt = datetime.datetime.fromisoformat(upd_str.replace("Z", "+00:00"))
                    now_dt = datetime.datetime.now(datetime.timezone.utc)
                    delta = max(0.0, (now_dt - upd_dt).total_seconds())
                    # Only extrapolate if delta looks plausible for the track (guard against stale player clocks)
                    if delta <= max(3600.0, float(duration_sec or 3600) + 60.0):
                        base_pos += delta
                except Exception:
                    pass
            if duration_sec > 0:
                base_pos = min(float(duration_sec), base_pos)
            exact_pos = base_pos
            self.last_artist, self.last_title = artist, title
        else:
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

        now_mono = time.monotonic()
        track_sig = (app_name, artist.lower(), title.lower())
        track_changed = track_sig != self._track_sig
        self._track_sig = track_sig

        if not title:
            self._anchor_pos = 0.0
            self._anchor_dur = 0.0
            self._anchor_mono = 0.0
            self._anchor_playing = False
        elif exact_pos is not None:
            self._anchor_pos = exact_pos
            self._anchor_dur = float(duration_sec)
            self._anchor_mono = now_mono
            self._anchor_playing = playing
        else:
            if track_changed:
                self._anchor_pos = 0.0
                self._anchor_dur = 0.0
                self._anchor_mono = now_mono
            else:
                if self._anchor_playing and self._anchor_mono > 0:
                    self._anchor_pos += max(0.0, now_mono - self._anchor_mono)
                self._anchor_mono = now_mono
            self._anchor_playing = playing

        cur_pos = self.current_pos()
        changed = (
            self.state.media_app != app_name
            or self.state.media_artist != artist
            or self.state.media_title != title
            or self.state.media_playing != playing
            or self.state.media_duration != duration_sec
        )

        self.state.media_app = app_name
        self.state.media_artist = artist
        self.state.media_title = title
        self.state.media_playing = playing
        self.state.media_duration = duration_sec
        self.state.media_pos = cur_pos

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
        self._anchor_pos = 0.0
        self._anchor_mono = time.monotonic()
        self.state.media_pos = 0
        threading.Thread(target=self._delayed_poll, daemon=True).start()

    def prev_track(self):
        self._tap(self.VK_PREV)
        self._anchor_pos = 0.0
        self._anchor_mono = time.monotonic()
        self.state.media_pos = 0
        threading.Thread(target=self._delayed_poll, daemon=True).start()

    def _delayed_poll(self):
        time.sleep(0.35)
        if self.scanner:
            self.scanner.get_snapshot(force=True)
        self.poll_now(force_smtc=True)
