import os
import re
import json
import time
import psutil
from core.config_manager import Reg, MEDAL_PROCS, MINECRAFT_FALLBACK_LOGO, lookup_known_game_icon

LAUNCHER_ONLY_PROCS = {
    "lunar client.exe",
    "lunarclient.exe",
    "badlion client.exe",
    "badlionclient.exe",
    "feather.exe",
    "feather client.exe",
    "feather-launcher.exe",
    "labymodlauncher.exe",
    "labymod.exe",
    "prismlauncher.exe",
    "minecraftlauncher.exe",
    "javaw_launcher.exe",
}


class MinecraftClient:
    re_mc_ver = re.compile(r"\b(1\.\d{1,2}(?:\.\d{1,2})?|2\d\.\d+(?:\.\d+)?)\b")
    re_mc_user = re.compile(r"(?:--username|-username)\s+([A-Za-z0-9_]{3,16})\b", re.I)

    def __init__(self, state, on_ui, on_push):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push

    def link_account(self, raw_val):
        val = (raw_val or "").strip()
        if not val:
            return False
        if "namemc.com/profile/" in val.lower():
            val = val.rstrip("/").split("/")[-1].split(".")[0]
        val = val.lstrip("@").strip()
        if not val:
            return False
        self.state.minecraft_username = val
        Reg.set("MinecraftUsername", val)
        self.on_ui()
        self.on_push()
        return True

    def unlink(self):
        self.state.minecraft_username = ""
        Reg.remove("MinecraftUsername")
        self.on_ui()
        self.on_push()
        return True

    def detect_local_account(self):
        appdata = os.environ.get("APPDATA", "")
        user_prof = os.path.expanduser("~")
        candidates_paths = [
            os.path.join(appdata, ".minecraft", "launcher_accounts_microsoft_store.json"),
            os.path.join(appdata, ".minecraft", "launcher_accounts.json"),
            os.path.join(user_prof, ".lunarclient", "settings", "game", "accounts.json"),
            os.path.join(appdata, "PrismLauncher", "accounts.json"),
            os.path.join(appdata, "MultiMC", "accounts.json"),
            os.path.join(appdata, ".feather", "accounts.json"),
            os.path.join(appdata, "Badlion Client", "accounts.json"),
        ]
        for path in candidates_paths:
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                accounts = data.get("accounts")
                if isinstance(accounts, dict):
                    for _, acc in accounts.items():
                        if not isinstance(acc, dict):
                            continue
                        prof = acc.get("minecraftProfile") or acc.get("profile") or {}
                        name = str(prof.get("name") or acc.get("username") or "").strip()
                        if name and len(name) >= 3:
                            return self.link_account(name)
                elif isinstance(accounts, list):
                    for acc in accounts:
                        if not isinstance(acc, dict):
                            continue
                        prof = acc.get("profile") or acc.get("minecraftProfile") or {}
                        name = str(prof.get("name") or acc.get("username") or "").strip()
                        if name and len(name) >= 3:
                            return self.link_account(name)
            except Exception:
                pass

        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                pname = (p.info.get("name") or "").lower()
                if pname in ("javaw.exe", "java.exe"):
                    cmd = " ".join(p.info.get("cmdline") or [])
                    m = self.re_mc_user.search(cmd)
                    if m:
                        return self.link_account(m.group(1))
            except Exception:
                pass

        if self.state.xbox_gamertag:
            return self.link_account(self.state.xbox_gamertag)
        return False

    def is_client_enabled(self, key):
        if not self.state.minecraft_enabled:
            return False
        if key == "lunar":
            return self.state.mc_lunar_enabled
        if key == "badlion":
            return self.state.mc_badlion_enabled
        if key == "feather":
            return self.state.mc_feather_enabled
        if key == "labymod":
            return self.state.mc_labymod_enabled
        if key == "prism_vanilla":
            return self.state.mc_prism_vanilla_enabled
        return False

    @classmethod
    def _extract_version(cls, text):
        if not text:
            return ""
        m = cls.re_mc_ver.search(text)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_activity_from_title(title):
        low = (title or "").lower()
        if "multiplayer" in low:
            if "3rd-party" in low or "server" in low:
                return "Multiplayer Server"
            return "Playing Multiplayer"
        if "singleplayer" in low:
            return "Singleplayer World"
        if "realms" in low:
            return "Minecraft Realms"
        if "lan" in low:
            return "LAN World"
        return "In Game / Menus"

    def poll(self, snapshot=None):
        if not self.state.minecraft_enabled:
            if self.state.minecraft_running:
                self._clear_state()
                return True
            return False

        if snapshot is not None:
            procs, _, windows, windows_by_pid = snapshot
        else:
            procs, windows, windows_by_pid = [], [], {}
            for p in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    cmd = " ".join(p.info.get("cmdline") or [])
                    exe = p.info.get("exe") or ""
                    procs.append(
                        {
                            "pid": p.info.get("pid"),
                            "name": (p.info.get("name") or "").lower(),
                            "exe": exe,
                            "exe_lower": exe.lower(),
                            "cmdline": cmd,
                            "cmdline_lower": cmd.lower(),
                            "has_visible_window": True,
                        }
                    )
                except Exception:
                    pass

        candidates = []

        for p in procs:
            pname = p["name"]
            if pname in MEDAL_PROCS or pname in LAUNCHER_ONLY_PROCS:
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue

            exe_low = p["exe_lower"]
            cmd_low = p["cmdline_lower"]
            pid_titles = windows_by_pid.get(p["pid"]) or []
            joined_titles = " | ".join(pid_titles)
            joined_titles_low = joined_titles.lower()

            if pname in ("javaw.exe", "java.exe"):
                is_mc_jvm = any(
                    tok in cmd_low or tok in exe_low or tok in joined_titles_low
                    for tok in (
                        "minecraft",
                        ".lunarclient",
                        "lunarclient",
                        "ichor",
                        "badlion",
                        "blclient",
                        "feather",
                        "labymod",
                        "prismlauncher",
                        "multimc",
                        "net.fabricmc",
                        "cpw.mods",
                        "optifine",
                    )
                )
                if not is_mc_jvm:
                    continue

                if "lunar" in cmd_low or ".lunarclient" in exe_low or "ichor" in cmd_low or "lunar client" in joined_titles_low:
                    ckey, cname = "lunar", "Lunar Client"
                elif "badlion" in cmd_low or "blclient" in cmd_low or "badlion" in exe_low or "badlion" in joined_titles_low:
                    ckey, cname = "badlion", "Badlion Client"
                elif "feather" in cmd_low or ".feather" in exe_low or "feather" in joined_titles_low:
                    ckey, cname = "feather", "Feather Client"
                elif "labymod" in cmd_low or "net.labymod" in cmd_low or "labymod" in joined_titles_low:
                    ckey, cname = "labymod", "LabyMod"
                else:
                    ckey = "prism_vanilla"
                    if "prismlauncher" in cmd_low or "prismlauncher" in exe_low:
                        cname = "Prism Launcher (Minecraft)"
                    elif "fabric" in cmd_low:
                        cname = "Minecraft Java (Fabric)"
                    elif "forge" in cmd_low or "neoforge" in cmd_low:
                        cname = "Minecraft Java (Forge)"
                    else:
                        cname = "Minecraft: Java Edition"

                if self.is_client_enabled(ckey):
                    m_u = self.re_mc_user.search(p["cmdline"])
                    if m_u and not self.state.minecraft_username:
                        self.state.minecraft_username = m_u.group(1)
                        Reg.set("MinecraftUsername", self.state.minecraft_username)
                    ver = self._extract_version(joined_titles) or self._extract_version(p["cmdline"])
                    act = self._extract_activity_from_title(joined_titles) if joined_titles else "In Game"
                    candidates.append((0, ckey, cname, ver, act))

            elif pname == "minecraft.windows.exe":
                if self.is_client_enabled("prism_vanilla"):
                    ver = self._extract_version(joined_titles)
                    act = self._extract_activity_from_title(joined_titles) if joined_titles else "In Game"
                    candidates.append((1, "prism_vanilla", "Minecraft (Bedrock)", ver, act))

        for w in windows:
            wpname = w.get("pname") or ""
            if wpname not in ("javaw.exe", "java.exe", "minecraft.windows.exe"):
                continue
            t = w["title"]
            t_low = w["title_lower"]
            if "lunar client" in t_low and self.is_client_enabled("lunar"):
                candidates.append((1, "lunar", "Lunar Client", self._extract_version(t), self._extract_activity_from_title(t)))
            elif "badlion" in t_low and ("client" in t_low or "minecraft" in t_low) and self.is_client_enabled("badlion"):
                candidates.append((1, "badlion", "Badlion Client", self._extract_version(t), self._extract_activity_from_title(t)))
            elif "feather client" in t_low and self.is_client_enabled("feather"):
                candidates.append((1, "feather", "Feather Client", self._extract_version(t), self._extract_activity_from_title(t)))
            elif "labymod" in t_low and self.is_client_enabled("labymod"):
                candidates.append((1, "labymod", "LabyMod", self._extract_version(t), self._extract_activity_from_title(t)))
            elif (t_low.startswith("minecraft ") or t_low.startswith("minecraft* ")) and self.is_client_enabled("prism_vanilla"):
                candidates.append((1, "prism_vanilla", "Minecraft: Java Edition", self._extract_version(t), self._extract_activity_from_title(t)))

        if not candidates:
            if self.state.minecraft_running:
                self._clear_state()
                return True
            return False

        candidates.sort(key=lambda x: x[0])
        _, best_key, best_name, best_ver, best_act = candidates[0]

        changed = (
            not self.state.minecraft_running
            or self.state.minecraft_client_key != best_key
            or self.state.minecraft_client_name != best_name
            or self.state.minecraft_version != best_ver
            or self.state.minecraft_activity != best_act
        )
        if not self.state.minecraft_running or self.state.minecraft_client_key != best_key:
            self.state.minecraft_start_ts = int(time.time())
        self.state.minecraft_running = True
        self.state.minecraft_client_key = best_key
        self.state.minecraft_client_name = best_name
        self.state.minecraft_version = best_ver
        self.state.minecraft_activity = best_act
        self.state.minecraft_icon = lookup_known_game_icon(best_name, fallback=MINECRAFT_FALLBACK_LOGO)
        return changed

    def _clear_state(self):
        self.state.minecraft_running = False
        self.state.minecraft_client_key = ""
        self.state.minecraft_client_name = ""
        self.state.minecraft_version = ""
        self.state.minecraft_activity = ""
        self.state.minecraft_icon = MINECRAFT_FALLBACK_LOGO
