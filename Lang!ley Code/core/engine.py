import os
import re
import time
import winreg
import threading
from core.config_manager import (
    CLIENT_ID,
    WEB_URL,
    LANGLEY_URL,
    Reg,
    FALLBACK_LOGO,
    STEAM_FALLBACK_LOGO,
    ROBLOX_FALLBACK_LOGO,
    XBOX_FALLBACK_LOGO,
    RIOT_FALLBACK_LOGO,
    EA_FALLBACK_LOGO,
    UBISOFT_FALLBACK_LOGO,
    GOG_FALLBACK_LOGO,
    BATTLENET_FALLBACK_LOGO,
    MINECRAFT_FALLBACK_LOGO,
    GACHA_FALLBACK_LOGO,
    CUSTOM_FALLBACK_LOGO,
)
from core.scanner import ProcessWindowScanner
from core.rpc import DiscordRPC, MedalRPCGuard
from core.media import MediaController
from core.updater import AutoUpdater
from core.auth_server import BrowserAuthServer
from detectors import (
    Cosmetics,
    EpicClient,
    get_log_path,
    enable_log_flags,
    parse_mode,
    is_fn_proc,
    SteamClient,
    RobloxClient,
    XboxClient,
    RiotClient,
    EAClient,
    UbisoftClient,
    GOGClient,
    BattleNetClient,
    MinecraftClient,
    GachaClient,
    CustomAppsClient,
)


class Engine:
    re_acc = re.compile(r"(?:-epicuserid=|AccountId=|LocalUserId=)([0-9a-fA-F]{32})", re.I)
    re_any_hex = re.compile(r"\b([0-9a-fA-F]{32})\b")
    re_usr = re.compile(r'(?:-epicusername=|DisplayName=|UserName=)"?([^"\r\n\t]+?)"?(?:\s+-|\s*$|\s*\[|\s*\()', re.I)
    re_skin = re.compile(
        r"(?:characterPrimaryAssetId|characterDef|AthenaCharacter:|LoadoutSchema_Character|PutModularCosmeticLoadout|CID_).*?(CID_[A-Za-z0-9_]+|Character_[A-Za-z0-9_]+)",
        re.I,
    )
    re_mode = re.compile(r'(?:PlaylistName(?:_s)?|CurrentPlaylist|SelectedPlaylist|mnemonic")[\\"\':=\s]+(playlist_[A-Za-z0-9_]+)', re.I)
    re_lvl = re.compile(r'(?:passLevel|seasonLevel|season_level|book_level)(?:\\"|["\'\s:=])+?(\d{1,4})\b', re.I)
    re_pres = re.compile(r"([0-9a-fA-F]{32}).*?(?:StatusStr|Status|Presence)[^A-Za-z0-9]+([^,\r\n\]\}]{2,40})", re.I)

    def __init__(self, state, on_ui, on_update_found):
        self.state = state
        self.on_ui = on_ui
        self.scanner = ProcessWindowScanner(ttl=1.2)
        self.rpc_lock = threading.RLock()
        self.cosmetics = Cosmetics()
        self.rpc = DiscordRPC(CLIENT_ID, state)
        self.medal_guard = MedalRPCGuard(state, self.rpc)
        self.xbox = XboxClient(state, on_ui, lambda: self.sync_rpc(force=True))
        self.epic = EpicClient(state, self.cosmetics, on_ui, lambda: self.sync_rpc(force=True), xbox_helper=self.xbox)
        self.steam = SteamClient(state, on_ui, lambda: self.sync_rpc(force=True))
        self.roblox = RobloxClient(state, on_ui, lambda: self.sync_rpc(force=True))
        self.riot = RiotClient(state, on_ui, lambda: self.sync_rpc(force=True))
        self.ea = EAClient(state, self.xbox, on_ui, lambda: self.sync_rpc(force=True))
        self.ubisoft = UbisoftClient(state, self.xbox, on_ui, lambda: self.sync_rpc(force=True))
        self.gog = GOGClient(state, self.xbox, on_ui, lambda: self.sync_rpc(force=True))
        self.battlenet = BattleNetClient(state, self.xbox, on_ui, lambda: self.sync_rpc(force=True))
        self.gacha = GachaClient(state, on_ui, lambda: self.sync_rpc(force=True))
        self.minecraft = MinecraftClient(state, on_ui, lambda: self.sync_rpc(force=True))
        self.custom_apps = CustomAppsClient(state, self.xbox, on_ui, lambda: self.sync_rpc(force=True))
        self.media = MediaController(state, on_ui, lambda: self.sync_rpc(force=True), scanner=self.scanner)
        self.updater = AutoUpdater(state, on_update_found)
        self.auth = BrowserAuthServer(state, self)
        self.stop_evt = threading.Event()
        self.last_sync = 0.0
        self.last_snap = None
        self.cleared = True
        self.in_frontend = True
        self.pending_skin_id = None
        self.plat_started_ts = 0.0
        self.prev_gsi_text = ""
        self.fn_missed_polls = 0

    def start(self):
        Reg.sync_autostart_target()
        enable_log_flags()
        if not self.state.skin_id or "wikimedia" in self.state.skin_icon:
            threading.Thread(target=self._init_skin, daemon=True).start()
        self.steam.start_gsi_server()
        self.auth.start()
        self.media.start()
        self.updater.start()
        threading.Thread(target=self._epic_worker, daemon=True).start()
        threading.Thread(target=self._steam_worker, daemon=True).start()
        threading.Thread(target=self._platform_worker, daemon=True).start()
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
        self.rpc.request_abort()
        threads = []
        for fn in (self.steam.stop_gsi_server, self.auth.stop, self.rpc.close):
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            threads.append(t)
        self.updater.stop()
        self.media.stop()
        for t in threads:
            t.join(timeout=0.6)

    def is_fn_running(self, snapshot=None):
        try:
            if snapshot is None:
                snapshot = self.scanner.get_snapshot()
            for p in snapshot[0]:
                if is_fn_proc(p):
                    return True
        except Exception:
            pass
        return False

    def _snap(self):
        plat = self.state.active_platform()
        return (
            plat,
            self.state.running,
            self.state.in_match,
            self.state.mode,
            self.state.skin_name,
            self.state.skin_icon,
            self.state.epic_name,
            self.state.epic_game_running,
            self.state.epic_game_name,
            self.state.epic_game_state,
            self.state.epic_game_icon,
            self.state.party_size,
            self.state.party_max,
            tuple(self.state.peers),
            self.state.season_level,
            self.state.steam_appid,
            self.state.steam_game_name,
            self.state.steam_game_icon,
            self.state.steam_user_name,
            self.state.steam_gsi_text,
            self.state.roblox_place_id,
            self.state.roblox_game_name,
            self.state.roblox_game_icon,
            self.state.roblox_display_name,
            self.state.xbox_game_name,
            self.state.xbox_game_icon,
            self.state.xbox_gamertag,
            self.state.riot_game_name,
            self.state.riot_game_state,
            self.state.riot_game_icon,
            self.state.riot_id,
            self.state.ea_game_name,
            self.state.ea_game_state,
            self.state.ea_game_icon,
            self.state.ea_account_name,
            self.state.ubisoft_game_name,
            self.state.ubisoft_game_state,
            self.state.ubisoft_game_icon,
            self.state.ubisoft_username,
            self.state.gog_game_name,
            self.state.gog_game_state,
            self.state.gog_game_icon,
            self.state.gog_username,
            self.state.battlenet_game_name,
            self.state.battlenet_game_state,
            self.state.battlenet_game_icon,
            self.state.battlenet_battletag,
            self.state.gacha_game_name,
            self.state.gacha_game_state,
            self.state.gacha_game_icon,
            self.state.gacha_account_name,
            self.state.gacha_level_prefix,
            self.state.gacha_level,
            self.state.gacha_region,
            self.state.gacha_character,
            self.state.minecraft_client_key,
            self.state.minecraft_client_name,
            self.state.minecraft_version,
            self.state.minecraft_activity,
            self.state.minecraft_username,
            self.state.custom_app_name,
            self.state.custom_app_state,
            self.state.custom_app_icon,
            self.state.show_media_rpc,
            self.state.media_str() if (self.state.show_media_rpc and self.state.media_playing) else "",
        )

    def clear_rpc(self):
        with self.rpc_lock:
            self.state.rpc_headline = "Waiting for Game..." if self.state.active else "Discord RPC Paused"
            self.state.rpc_details = (
                "Launch Any Game or Launcher" if self.state.active else "Click Resume RPC to re-enable"
            )
            self.state.rpc_state = "Idle in Background"
            self.state.rpc_image_url = self.state.skin_icon or FALLBACK_LOGO
            if not self.rpc.connected or self.cleared:
                return
            if self.rpc.clear():
                self.cleared = True
                self.last_snap = None
            else:
                self.state.discord_ok = False
                self.on_ui()

    def force_reassert_rpc(self):
        with self.rpc_lock:
            plat = self.state.active_platform()
            if plat not in ("paused", "idle") and self.rpc.connected:
                if self.rpc.reassert_priority(promote=True):
                    self.state.medal_reassertions += 1
                    self.on_ui()
                    return True
            self.sync_rpc(force=True)
            return False

    def sync_rpc(self, force=False):
        with self.rpc_lock:
            plat = self.state.active_platform()
            if plat in ("paused", "idle"):
                self.clear_rpc()
                self.on_ui()
                return

            now = time.time()
            snap = self._snap()
            prev_plat = self.last_snap[0] if self.last_snap else ""
            if snap == self.last_snap and not self.cleared:
                if not force or (now - self.last_sync < 0.8):
                    in_warmup = (now - self.plat_started_ts) <= 45.0
                    due_warmup = in_warmup and (now - self.medal_guard.last_reassert_ts >= 5.0)
                    if self.rpc.connected:
                        if self.medal_guard.enforce_priority(plat, immediate=due_warmup):
                            self.last_sync = now
                            self.on_ui()
                        elif not self.rpc.connected and self.state.discord_ok:
                            self.state.discord_ok = False
                            self.on_ui()
                    return
            elif not force and now - self.last_sync < 0.8:
                return

            small_txt = "Lang!ley by Asukaa (asukaa.de)"
            if self.state.medal_priority_enabled:
                small_txt = "Lang!ley by Asukaa (asukaa.de)"
            song_suffix = ""
            if self.state.show_media_rpc and self.state.media_playing and self.state.media_title:
                song = self.state.media_str()
                if len(song) > 42:
                    song = song[:39] + "..."
                song_suffix = f" • 🎵 {song}"
                small_txt = f"🎵 {self.state.media_app}: {song}"

            buttons = [{"label": "Visit Developer Website", "url": WEB_URL}, {"label": "Get Lang!ley", "url": LANGLEY_URL}]

            if plat == "fortnite":
                if self.state.running:
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
                        state_txt = f"{self.state.epic_name} • Season Level {self.state.season_level} • {ptag}{song_suffix}"
                    else:
                        state_txt = f"Season Level {self.state.season_level} • {ptag}{song_suffix}"
                    act_name = "Fortnite with Lang!ley"
                    large_img = self.state.skin_icon or FALLBACK_LOGO
                    large_txt = self.state.skin_name if len(self.state.skin_name) >= 2 else "Fortnite Outfit"
                    start_ts = self.state.start_ts
                else:
                    gname = self.state.epic_game_name or "Epic Games Store"
                    act_name = f"{gname} with Lang!ley"
                    details = f"Playing {gname} • {self.state.epic_game_state or 'Active on Epic Games Store'}"
                    state_txt = (
                        f"Epic Games: {self.state.epic_name}{song_suffix}"
                        if self.state.epic_name
                        else f"Active on Epic Games Store{song_suffix}"
                    )
                    large_img = self.state.epic_game_icon or FALLBACK_LOGO
                    large_txt = f"{gname} (Epic Games)"
                    start_ts = self.state.epic_game_start_ts
            elif plat == "minecraft":
                cname = self.state.minecraft_client_name or "Minecraft"
                ver_tag = f" {self.state.minecraft_version}" if self.state.minecraft_version else ""
                act_name = f"{cname} with Lang!ley"
                details = f"Playing {cname}{ver_tag} • {self.state.minecraft_activity or 'In Game'}"
                if self.state.minecraft_username:
                    state_txt = f"Player: {self.state.minecraft_username} • {cname}{song_suffix}"
                else:
                    state_txt = f"Minecraft ({cname}){song_suffix}"
                large_img = self.state.minecraft_icon or MINECRAFT_FALLBACK_LOGO
                large_txt = f"{cname}{ver_tag}"
                start_ts = self.state.minecraft_start_ts
            elif plat == "gacha":
                gname = self.state.gacha_game_name or "HoYoPlay / Gacha Game"
                gstate = self.state.gacha_game_state or "Active Session"
                uid_str = (self.state.gacha_uid or "").strip()
                acc_name = (self.state.gacha_account_name or "").strip()
                lvl_str = self.state.gacha_level_str()
                reg_str = (self.state.gacha_region or "").strip()
                char_name = (self.state.gacha_character or "").strip()
                act_name = f"{gname} with Lang!ley"
                det_parts = [f"Playing {gname}"]
                if lvl_str:
                    det_parts.append(lvl_str)
                det_parts.append(gstate)
                if char_name:
                    det_parts.append(f"Equipped: {char_name}")
                details = " • ".join(det_parts)
                ident = f"Player: {acc_name}" if acc_name else (f"UID {uid_str}" if uid_str else "")
                meta_parts = [x for x in (ident, lvl_str, f"Region: {reg_str}" if reg_str else "") if x]
                base_state = " • ".join(meta_parts) if meta_parts else "HoYoPlay / PC Gacha"
                state_txt = f"{base_state}{song_suffix}"
                large_img = self.state.gacha_game_icon or GACHA_FALLBACK_LOGO
                name_uid = f"{acc_name} (UID {uid_str})" if (acc_name and uid_str and acc_name != uid_str) else ident
                hover_meta = [x for x in (name_uid, lvl_str, reg_str, char_name) if x]
                large_txt = f"{gname} • {' • '.join(hover_meta)}" if hover_meta else gname
                start_ts = self.state.gacha_start_ts
            elif plat == "riot":
                gname = self.state.riot_game_name or "Riot Games"
                act_name = f"{gname} with Lang!ley"
                details = f"Playing {gname} • {self.state.riot_game_state or 'Active'}"
                state_txt = f"Riot: {self.state.riot_id}{song_suffix}" if self.state.riot_id else f"Riot Games{song_suffix}"
                large_img = self.state.riot_game_icon or RIOT_FALLBACK_LOGO
                large_txt = f"{gname} (Riot Games)"
                start_ts = self.state.riot_start_ts
            elif plat == "ea":
                gname = self.state.ea_game_name or "EA App Game"
                act_name = f"{gname} with Lang!ley"
                details = f"Playing {gname} • {self.state.ea_game_state or 'Active on EA App'}"
                state_txt = f"EA: {self.state.ea_account_name}{song_suffix}" if self.state.ea_account_name else f"EA App{song_suffix}"
                large_img = self.state.ea_game_icon or EA_FALLBACK_LOGO
                large_txt = f"{gname} (EA App)"
                start_ts = self.state.ea_start_ts
            elif plat == "ubisoft":
                gname = self.state.ubisoft_game_name or "Ubisoft Game"
                act_name = f"{gname} with Lang!ley"
                details = f"Playing {gname} • {self.state.ubisoft_game_state or 'Active on Ubisoft Connect'}"
                state_txt = f"Ubisoft: {self.state.ubisoft_username}{song_suffix}" if self.state.ubisoft_username else f"Ubisoft Connect{song_suffix}"
                large_img = self.state.ubisoft_game_icon or UBISOFT_FALLBACK_LOGO
                large_txt = f"{gname} (Ubisoft Connect)"
                start_ts = self.state.ubisoft_start_ts
            elif plat == "gog":
                gname = self.state.gog_game_name or "GOG Galaxy Game"
                act_name = f"{gname} with Lang!ley"
                details = f"Playing {gname} • {self.state.gog_game_state or 'Active on GOG Galaxy'}"
                state_txt = f"GOG: {self.state.gog_username}{song_suffix}" if self.state.gog_username else f"GOG Galaxy{song_suffix}"
                large_img = self.state.gog_game_icon or GOG_FALLBACK_LOGO
                large_txt = f"{gname} (GOG Galaxy)"
                start_ts = self.state.gog_start_ts
            elif plat == "battlenet":
                gname = self.state.battlenet_game_name or "Battle.net Game"
                act_name = f"{gname} with Lang!ley"
                details = f"Playing {gname} • {self.state.battlenet_game_state or 'Active on Battle.net'}"
                state_txt = f"Battle.net: {self.state.battlenet_battletag}{song_suffix}" if self.state.battlenet_battletag else f"Blizzard Battle.net{song_suffix}"
                large_img = self.state.battlenet_game_icon or BATTLENET_FALLBACK_LOGO
                large_txt = f"{gname} (Battle.net)"
                start_ts = self.state.battlenet_start_ts
            elif plat == "steam":
                gname = self.state.steam_game_name or f"Steam Game ({self.state.steam_appid})"
                act_name = f"{gname} with Lang!ley"
                details = (
                    f"Playing {gname} • {self.state.steam_gsi_text}"
                    if self.state.steam_gsi_text
                    else f"Playing {gname} on Steam • {self.state.steam_genre}"
                )
                state_txt = f"Steam: {self.state.steam_user_name}{song_suffix}" if self.state.steam_user_name else f"Active on Steam{song_suffix}"
                large_img = self.state.steam_game_icon or STEAM_FALLBACK_LOGO
                large_txt = gname
                start_ts = self.state.steam_start_ts
                store_url = f"https://store.steampowered.com/app/{self.state.steam_appid}"
                buttons = [{"label": "View on Steam", "url": store_url}, {"label": "Get Lang!ley", "url": LANGLEY_URL}]
            elif plat == "roblox":
                rname = self.state.roblox_game_name or "Roblox"
                act_name = f"{rname} with Lang!ley"
                details = f"Playing {rname} • by {self.state.roblox_creator}" if self.state.roblox_creator else f"Playing {rname} on Roblox"
                ruser = self.state.roblox_display_name or self.state.roblox_user_name
                state_txt = f"Roblox: {ruser}{song_suffix}" if ruser else f"Active on Roblox{song_suffix}"
                large_img = self.state.roblox_game_icon or ROBLOX_FALLBACK_LOGO
                large_txt = rname
                start_ts = self.state.roblox_start_ts
                if self.state.roblox_place_id:
                    buttons = [
                        {"label": "View on Roblox", "url": f"https://www.roblox.com/games/{self.state.roblox_place_id}"},
                        {"label": "Get Lang!ley", "url": LANGLEY_URL},
                    ]
            elif plat == "custom_apps":
                cname = self.state.custom_app_name or "Custom Application"
                act_name = f"{cname} with Lang!ley"
                details = f"Playing {cname} • {self.state.custom_app_state or 'Active Session'}"
                state_txt = f"Custom App / Game{song_suffix}"
                large_img = self.state.custom_app_icon or CUSTOM_FALLBACK_LOGO
                large_txt = cname
                start_ts = self.state.custom_app_start_ts
            else:
                xname = self.state.xbox_game_name or "Xbox Game"
                act_name = f"{xname} with Lang!ley"
                details = f"Playing {xname} on Xbox / PC Game Pass"
                state_txt = f"Xbox: {self.state.xbox_gamertag}{song_suffix}" if self.state.xbox_gamertag else f"Active on Xbox{song_suffix}"
                large_img = self.state.xbox_game_icon or XBOX_FALLBACK_LOGO
                large_txt = xname
                start_ts = self.state.xbox_start_ts

            self.state.rpc_headline = act_name
            self.state.rpc_details = details[:128]
            self.state.rpc_state = state_txt[:128]
            self.state.rpc_image_url = large_img

            payload = {
                "type": 0,
                "instance": True,
                "name": act_name[:128],
                "details": details[:128],
                "state": state_txt[:128],
                "timestamps": {"start": start_ts},
                "assets": {
                    "large_image": large_img,
                    "large_text": large_txt[:128],
                    "small_image": "asukaa_logo",
                    "small_text": small_txt[:128],
                },
                "buttons": buttons,
            }

            if self.cleared or plat != prev_plat:
                self.plat_started_ts = now
            self.prev_gsi_text = self.state.steam_gsi_text or ""
            # Use seamless parity-bumped SET_ACTIVITY updates (never periodic activity=None clears)
            # so Fortnite / Xbox / CS2 native RPC cannot override Lang!ley or make it cut out.
            if self.rpc.connected and self.rpc.update(payload, promote=False):
                self.last_sync = now
                self.last_snap = snap
                self.cleared = False
                self.state.discord_ok = True
                self.medal_guard.last_reassert_ts = now
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
                f_aid, f_st = mpres.group(1).lower(), mpres.group(2).strip(" \"':=")
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
            low_line = line.lower()
            is_noise_or_shop = any(
                bad in low_line
                for bad in (
                    "applycosmeticusage",
                    "downloadmanager",
                    "itemshop",
                    "logfortstore",
                    "storefront",
                    "catalog",
                    "hotfix",
                    "failed retrieving item",
                    "logprofilesys",
                    "channel tag",
                    "ignoring primaryassettype",
                    "logassetmanager",
                    "logteampedestal",
                    "skipping preload",
                    "cid_random",
                    "cid_stwhero",
                    "_temp",
                )
            )
            is_local_loadout_line = (
                "[loadoutslot.character]=" in low_line
                or "updatememberrepdatawithmploadout" in low_line
                or "completed queryitems success:true" in low_line
                or "loadoutschema_character" in low_line
                or "putmodularcosmeticloadout" in low_line
                or "characterprimaryassetid" in low_line
            )
            if is_local_loadout_line and not is_noise_or_shop:
                m = self.re_skin.search(line)
                if m:
                    cid = Cosmetics.clean_id(m.group(1))
                    if cid and cid not in self.epic.mate_cids:
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
        snapshot = self.scanner.get_snapshot(force=True)
        self.epic.scan_installed_games()
        self.epic.poll(snapshot)
        if self.state.epic_ok:
            self.epic.fetch_party()
            self.epic.fetch_profile()
            self.epic.fetch_friends()
        self.steam.scan_installed_games()
        self.steam.poll_running_game()
        self.steam.fetch_public_profile()
        self.steam.fetch_steam_friends()
        self.roblox.poll(snapshot)
        self.roblox.fetch_friends()
        self.xbox.scan_installed_xbox_games()
        self.xbox.poll(snapshot)
        self.xbox.fetch_friends()
        self.riot.scan_installed_games()
        self.riot.poll(snapshot)
        self.riot.fetch_friends()
        self.ea.scan_installed_games()
        self.ea.poll(snapshot)
        self.ea.fetch_friends()
        self.ubisoft.scan_installed_games()
        self.ubisoft.poll(snapshot)
        self.ubisoft.fetch_friends()
        self.gog.scan_installed_games()
        self.gog.poll(snapshot)
        self.gog.fetch_friends()
        self.battlenet.scan_installed_games()
        self.battlenet.poll(snapshot)
        self.battlenet.fetch_friends()
        self.gacha.scan_installed_games()
        self.gacha.poll(snapshot)
        self.minecraft.poll(snapshot)
        self.custom_apps.reload()
        self.custom_apps.poll(snapshot)
        self.medal_guard.poll(snapshot)
        self.media.poll_now(snapshot)
        self.rpc.sync_social(self.state)
        self.on_ui()
        self.sync_rpc(force=True)

    def _platform_worker(self):
        self.epic.scan_installed_games()
        self.xbox.detect_local_gamertag()
        self.xbox.scan_installed_xbox_games()
        self.xbox.fetch_friends()
        self.riot.scan_installed_games()
        self.riot.fetch_friends()
        self.ea.scan_installed_games()
        self.ea.fetch_friends()
        self.ubisoft.scan_installed_games()
        self.ubisoft.fetch_friends()
        self.gog.scan_installed_games()
        self.gog.fetch_friends()
        self.battlenet.scan_installed_games()
        self.battlenet.fetch_friends()
        if not self.state.battlenet_battletag:
            self.battlenet.detect_local_account()
        if not self.state.riot_id:
            self.riot.detect_local_account()
        if not self.state.ea_account_name:
            self.ea.detect_local_account()
        if not self.state.ubisoft_username:
            self.ubisoft.detect_local_account()
        if not self.state.gog_username:
            self.gog.detect_local_account()
        if not self.state.minecraft_username:
            self.minecraft.detect_local_account()
        self.gacha.scan_installed_games()
        if not self.state.gacha_manual_override:
            self.gacha.detect_local_account()
        self.rpc.sync_social(self.state)
        if not self.state.roblox_user_id:
            self.roblox.detect_local_account()
        if self.state.roblox_user_id:
            self.roblox.fetch_friends()
        self.on_ui()

        last_social_sync = time.time()
        while not self.stop_evt.is_set():
            snapshot = self.scanner.get_snapshot(force=False)
            medal_changed, medal_transitioned_on = self.medal_guard.poll(snapshot)

            changed = False
            if self.epic.poll(snapshot):
                changed = True
            if self.minecraft.poll(snapshot):
                changed = True
            if self.gacha.poll(snapshot):
                changed = True
            if self.riot.poll(snapshot):
                changed = True
            if self.ea.poll(snapshot):
                changed = True
            if self.ubisoft.poll(snapshot):
                changed = True
            if self.gog.poll(snapshot):
                changed = True
            if self.battlenet.poll(snapshot):
                changed = True
            if self.roblox.poll(snapshot):
                changed = True
            if self.xbox.poll(snapshot):
                changed = True
            if self.custom_apps.poll(snapshot):
                changed = True

            now = time.time()
            if now - last_social_sync >= 35.0:
                last_social_sync = now
                if self.state.roblox_user_id:
                    self.roblox.fetch_friends()
                self.riot.fetch_friends()
                self.xbox.fetch_friends()
                self.battlenet.fetch_friends()
                self.rpc.sync_social(self.state)

            plat = self.state.active_platform()
            is_idle = plat in ("paused", "idle")
            self.scanner.ttl = 1.8 if is_idle else 1.1

            if changed:
                self.on_ui()
                self.sync_rpc(force=True)
            elif medal_transitioned_on and not is_idle:
                self.medal_guard.enforce_priority(plat, immediate=True)
                self.on_ui()
            elif medal_changed:
                self.on_ui()
            elif not is_idle:
                self.sync_rpc(force=False)

            time.sleep(2.6 if is_idle else 1.5)

    def _steam_worker(self):
        self.steam.detect_local_steam_user()
        self.steam.scan_installed_games()
        self.steam.install_gsi_configs()
        self.steam.fetch_public_profile()
        self.steam.fetch_steam_friends()
        self.on_ui()
        last_prof_check = time.time()
        while not self.stop_evt.is_set():
            changed = self.steam.poll_running_game()
            now = time.time()
            if now - last_prof_check >= 45.0:
                last_prof_check = now
                if self.steam.fetch_public_profile():
                    changed = True
                self.steam.fetch_steam_friends()
            if changed:
                self.on_ui()
                self.sync_rpc(force=True)
            elif self.state.steam_running and self.state.active_platform() == "steam":
                self.sync_rpc(force=False)
            time.sleep(1.5 if self.state.steam_running else 2.5)

    def _epic_worker(self):
        if not self.epic.restore():
            self.epic.detect_local_account()
        if self.state.epic_ok:
            self.epic.fetch_party()
            self.epic.fetch_profile()
            self.epic.fetch_friends()
            self.on_ui()
            self.sync_rpc(force=True)
        last_prof, last_friends = time.time(), time.time()
        while not self.stop_evt.is_set():
            if self.state.epic_ok:
                if self.state.running and self.epic.fetch_party():
                    self.on_ui()
                    self.sync_rpc(force=True)
                now = time.time()
                if now - last_prof >= 25.0 and self.state.running:
                    last_prof = now
                    if self.epic.fetch_profile():
                        self.on_ui()
                        self.sync_rpc(force=False)
                if now - last_friends >= 25.0:
                    last_friends = now
                    self.epic.fetch_friends()
                time.sleep(1.4 if self.state.running else 2.8)
            else:
                time.sleep(3.0)

    def _log_worker(self):
        while not self.stop_evt.is_set():
            if not self.rpc.connected:
                if self.rpc.connect():
                    self.state.discord_ok = True
                    self.on_ui()
                    self.sync_rpc(force=True)
                else:
                    self.state.discord_ok = False
                    self.on_ui()

            if not self.is_fn_running():
                if self.state.running:
                    self.fn_missed_polls += 1
                    if self.fn_missed_polls >= 2:
                        self.fn_missed_polls = 0
                        self.state.running = False
                        self.state.in_match = False
                        self.in_frontend = True
                        self.sync_rpc(force=True)
                        self.on_ui()
                time.sleep(2.4)
                continue

            self.fn_missed_polls = 0
            if not self.state.running:
                enable_log_flags()
                self.state.running = True
                self.state.in_match = False
                self.in_frontend = True
                self.state.start_ts = int(time.time())
                self.on_ui()
                self.sync_rpc(force=True)

            lpath = get_log_path()
            if not os.path.exists(lpath):
                self.sync_rpc(force=False)
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
                        if not self.rpc.connected and self.rpc.connect():
                            self.state.discord_ok = True
                            self.on_ui()
                            self.sync_rpc(force=True)
                        try:
                            if os.path.getsize(lpath) < f.tell():
                                break
                        except OSError:
                            break
                        line = f.readline()
                        if not line:
                            self.sync_rpc(force=False)
                            time.sleep(0.15)
                            continue
                        if self._read_line(line, live=True):
                            self.on_ui()
                            self.sync_rpc(force=True)
            except OSError:
                time.sleep(1.5)
