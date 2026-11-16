import os
import time
import psutil
from core.config_manager import CFG, CUSTOM_FALLBACK_LOGO, MEDAL_PROCS


class CustomAppsClient:
    def __init__(self, state, xbox_helper, on_ui, on_push):
        self.state = state
        self.xbox_helper = xbox_helper
        self.on_ui = on_ui
        self.on_push = on_push
        self.reload()

    def reload(self):
        self.state.custom_apps_list = CFG.get_custom_apps()
        return self.state.custom_apps_list

    def add_app(self, exe_path, display_name="", status_text="", icon_url=""):
        exe_path = str(exe_path or "").strip().strip('"')
        if not exe_path or not exe_path.lower().endswith(".exe"):
            return False
        exe_name = os.path.basename(exe_path).lower()
        if not exe_name:
            return False
        disp = str(display_name or "").strip()
        if not disp:
            disp = os.path.splitext(os.path.basename(exe_path))[0].replace("_", " ").replace("-", " ").title()
        st_txt = str(status_text or "").strip() or "Active on Desktop"
        ico = str(icon_url or "").strip()

        apps = CFG.get_custom_apps()
        updated = False
        for item in apps:
            if (item.get("exe_name") or "").lower() == exe_name:
                item["name"] = disp
                item["exe_path"] = os.path.normpath(exe_path)
                item["status_text"] = st_txt
                item["icon_url"] = ico
                updated = True
                break
        if not updated:
            apps.append(
                {
                    "name": disp,
                    "exe_name": exe_name,
                    "exe_path": os.path.normpath(exe_path),
                    "status_text": st_txt,
                    "icon_url": ico,
                }
            )
        CFG.set_custom_apps(apps)
        self.state.custom_apps_list = apps
        self.on_ui()
        self.on_push()
        return True

    def remove_app(self, exe_name):
        target = str(exe_name or "").strip().lower()
        apps = [a for a in CFG.get_custom_apps() if (a.get("exe_name") or "").lower() != target and (a.get("name") or "").lower() != target]
        CFG.set_custom_apps(apps)
        self.state.custom_apps_list = apps
        self.on_ui()
        self.on_push()
        return True

    def poll(self, snapshot=None):
        apps = self.state.custom_apps_list
        if not self.state.custom_apps_enabled or not apps:
            if self.state.custom_app_running:
                self.state.custom_app_running = False
                self.state.custom_app_name = ""
                self.state.custom_app_state = ""
                self.state.custom_app_icon = CUSTOM_FALLBACK_LOGO
                return True
            return False

        if snapshot is not None:
            procs, _, windows, _ = snapshot
        else:
            procs, windows = [], []
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    exe = p.info.get("exe") or ""
                    procs.append(
                        {
                            "pid": p.info.get("pid"),
                            "name": (p.info.get("name") or "").lower(),
                            "exe": exe,
                            "exe_lower": exe.lower(),
                            "has_visible_window": True,
                        }
                    )
                except Exception:
                    pass

        by_exe = {(a.get("exe_name") or "").lower(): a for a in apps if a.get("exe_name")}
        matched_app = None
        matched_pid = None

        for p in procs:
            pname = p["name"]
            if not pname or pname in MEDAL_PROCS:
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue
            if pname in by_exe:
                matched_app = by_exe[pname]
                matched_pid = p.get("pid")
                break

        if not matched_app:
            if self.state.custom_app_running:
                self.state.custom_app_running = False
                self.state.custom_app_name = ""
                self.state.custom_app_state = ""
                self.state.custom_app_icon = CUSTOM_FALLBACK_LOGO
                return True
            return False

        detected_name = matched_app.get("name") or matched_app.get("exe_name") or "Custom App"
        detected_state = matched_app.get("status_text") or "Active Session"
        custom_icon = (matched_app.get("icon_url") or "").strip()
        if custom_icon:
            detected_icon = custom_icon
        else:
            detected_icon = self.xbox_helper.resolve_cover_icon(detected_name, fallback=CUSTOM_FALLBACK_LOGO)

        if matched_pid and windows and detected_state == "Active Session":
            for w in windows:
                if w.get("pid") == matched_pid and w.get("title"):
                    wt = w["title"].strip()
                    if 2 <= len(wt) <= 44 and wt.lower() != detected_name.lower():
                        detected_state = wt
                    break

        changed = (
            not self.state.custom_app_running
            or self.state.custom_app_name != detected_name
            or self.state.custom_app_state != detected_state
            or self.state.custom_app_icon != detected_icon
        )
        if not self.state.custom_app_running or self.state.custom_app_name != detected_name:
            self.state.custom_app_start_ts = int(time.time())
        self.state.custom_app_running = True
        self.state.custom_app_name = detected_name
        self.state.custom_app_state = detected_state
        self.state.custom_app_icon = detected_icon
        return changed
