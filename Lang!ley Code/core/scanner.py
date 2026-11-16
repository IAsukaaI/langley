import time
import ctypes
from ctypes import wintypes
import threading
import psutil


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080

IGNORE_WINDOW_TITLES = {
    "default ime",
    "msctfime ui",
    "gdi+ window",
    "mediacontextnotificationwindow",
    "program manager",
    "windows input experience",
    "settings",
}


class ProcessWindowScanner:
    def __init__(self, ttl=1.2):
        self.ttl = ttl
        self.lock = threading.Lock()
        self.last_ts = 0.0
        self.procs = []
        self.proc_by_pid = {}
        self.windows = []
        self.windows_by_pid = {}
        self.visible_pids = set()

    def has_visible_window(self, pid):
        return pid in self.visible_pids

    def get_snapshot(self, force=False):
        with self.lock:
            now = time.time()
            if not force and self.procs and (now - self.last_ts) < self.ttl:
                return self.procs, self.proc_by_pid, self.windows, self.windows_by_pid

            procs = []
            proc_by_pid = {}
            try:
                for p in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                    try:
                        info = p.info
                        pid = info.get("pid")
                        raw_name = info.get("name") or ""
                        name_low = raw_name.lower()
                        if not pid or not name_low:
                            continue
                        exe = info.get("exe") or ""
                        exe_low = exe.lower()
                        cmd_list = info.get("cmdline") or []
                        cmd_str = " ".join(cmd_list) if isinstance(cmd_list, (list, tuple)) else str(cmd_list or "")
                        entry = {
                            "pid": pid,
                            "name": name_low,
                            "raw_name": raw_name,
                            "exe": exe,
                            "exe_lower": exe_low,
                            "cmdline": cmd_str,
                            "cmdline_lower": cmd_str.lower(),
                            "has_visible_window": False,
                        }
                        procs.append(entry)
                        proc_by_pid[pid] = entry
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                        continue
            except Exception:
                pass

            windows = []
            windows_by_pid = {}
            visible_pids = set()
            try:
                user32 = ctypes.windll.user32
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

                def enum_cb(hwnd, _):
                    try:
                        if not user32.IsWindowVisible(hwnd):
                            return True
                        iconic = bool(user32.IsIconic(hwnd))
                        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                        if ex_style & WS_EX_TOOLWINDOW:
                            return True

                        rect = _RECT()
                        w_width, w_height = 0, 0
                        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                            w_width = rect.right - rect.left
                            w_height = rect.bottom - rect.top
                        if not iconic and (w_width < 80 or w_height < 60):
                            return True

                        length = user32.GetWindowTextLengthW(hwnd)
                        if length < 2:
                            return True
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.strip()
                        if not title or title.lower() in IGNORE_WINDOW_TITLES:
                            return True

                        pid_val = ctypes.c_ulong()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
                        wpid = int(pid_val.value)
                        p_entry = proc_by_pid.get(wpid)
                        pname = p_entry["name"] if p_entry else ""

                        is_active_window = not iconic and w_width >= 80 and w_height >= 60
                        w_item = {
                            "hwnd": hwnd,
                            "pid": wpid,
                            "pname": pname,
                            "title": title,
                            "title_lower": title.lower(),
                            "visible": is_active_window,
                            "iconic": iconic,
                            "width": w_width,
                            "height": w_height,
                        }
                        if is_active_window:
                            windows.append(w_item)
                            windows_by_pid.setdefault(wpid, []).append(title)
                            visible_pids.add(wpid)
                            if p_entry is not None:
                                p_entry["has_visible_window"] = True
                        elif pname == "spotify.exe":
                            windows.append(w_item)
                    except Exception:
                        pass
                    return True

                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            except Exception:
                pass

            self.procs = procs
            self.proc_by_pid = proc_by_pid
            self.windows = windows
            self.windows_by_pid = windows_by_pid
            self.visible_pids = visible_pids
            self.last_ts = now
            return self.procs, self.proc_by_pid, self.windows, self.windows_by_pid
