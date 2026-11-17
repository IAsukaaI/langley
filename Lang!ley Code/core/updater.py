import os
import time
import tempfile
import subprocess
import threading
import requests
from core.config_manager import APP_VERSION, CFG, UPDATE_JSON_URL, DEFAULT_SETUP_URL, HTTP_HEADERS, ver_tuple


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
            r = requests.get(f"{UPDATE_JSON_URL}?t={int(time.time())}", headers=HTTP_HEADERS, timeout=5.0)
            if r.status_code != 200:
                return False
            data = r.json() or {}
            rem_ver = str(data.get("version") or "").strip()
            if not rem_ver:
                return False
            pn_ver = str((CFG.get_patch_notes() or {}).get("current_version") or APP_VERSION).strip()
            local_ver_t = max(ver_tuple(APP_VERSION), ver_tuple(pn_ver))
            if ver_tuple(rem_ver) > local_ver_t:
                self.state.update_available = True
                self.state.update_version = rem_ver
                self.state.update_url = str(data.get("download_url") or data.get("url") or DEFAULT_SETUP_URL).strip()
                self.state.update_changelog = str(data.get("changelog") or data.get("notes") or "• Bugfixes, stability improvements & new features.").strip()
                if manual or self.notified_version != rem_ver:
                    self.notified_version = rem_ver
                    self.on_update_found()
                return True
            self.state.update_available = False
            self.state.update_version = ""
        except Exception:
            pass
        return False

    def download_and_install(self, on_progress, on_error, on_shutdown):
        if self.downloading:
            return
        self.downloading = True
        threading.Thread(target=self._download_thread, args=(on_progress, on_error, on_shutdown), daemon=True).start()

    def _download_thread(self, on_progress, on_error, on_shutdown):
        try:
            url = self.state.update_url or DEFAULT_SETUP_URL
            setup_path = os.path.join(tempfile.gettempdir(), f"Langley_Setup_{self.state.update_version}.exe")
            with requests.get(url, headers=HTTP_HEADERS, stream=True, timeout=15) as r:
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
