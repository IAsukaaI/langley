import time
from core.config_manager import (
    CFG,
    Reg,
    GACHA_SUB_GAME_DEFS,
    DEFAULT_SETUP_URL,
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
        self.fortnite_enabled = bool(Reg.get("FortniteEnabled", 1))
        self.running = False
        self.epic_game_running = False
        self.epic_game_name = ""
        self.epic_game_state = ""
        self.epic_game_icon = FALLBACK_LOGO
        self.epic_game_start_ts = int(time.time())
        self.epic_installed_games = []
        self.discord_ok = False
        self.epic_ok = bool(Reg.get("EpicName", ""))
        self.epic_name = Reg.get("EpicName", "")
        if "EpicAccountId" in self.epic_name or "=" in self.epic_name:
            self.epic_name = ""
            Reg.remove("EpicName")
        self.account_id = ""
        self.active = True
        self.start_ts = int(time.time())

        self.steam_enabled = bool(Reg.get("SteamEnabled", 1))
        self.steam_running = False
        self.steam_appid = 0
        self.steam_game_name = ""
        self.steam_game_icon = STEAM_FALLBACK_LOGO
        self.steam_genre = "Steam Game"
        self.steam_user_name = Reg.get("SteamPersona", "")
        self.steam_id64 = Reg.get("SteamID64", "")
        self.steam_manual_override = bool(Reg.get("SteamManualOverride", 0))
        self.steam_start_ts = int(time.time())
        self.steam_rich_text = ""
        self.steam_gsi_text = ""
        self.steam_gsi_active = False
        self.steam_installed_games = []
        self.steam_friends = []

        self.roblox_enabled = bool(Reg.get("RobloxEnabled", 1))
        self.roblox_running = False
        self.roblox_place_id = ""
        self.roblox_universe_id = ""
        self.roblox_game_name = ""
        self.roblox_creator = ""
        self.roblox_game_icon = ROBLOX_FALLBACK_LOGO
        self.roblox_user_id = Reg.get("RobloxUserId", "")
        self.roblox_user_name = Reg.get("RobloxUserName", "")
        self.roblox_display_name = Reg.get("RobloxDisplayName", "")
        self.roblox_start_ts = int(time.time())
        self.roblox_friends = []

        self.xbox_enabled = bool(Reg.get("XboxEnabled", 1))
        self.xbox_running = False
        self.xbox_game_name = ""
        self.xbox_game_icon = XBOX_FALLBACK_LOGO
        self.xbox_gamertag = Reg.get("XboxGamertag", "")
        self.xbox_manual_override = bool(Reg.get("XboxManualOverride", 0))
        self.xbox_start_ts = int(time.time())
        self.xbox_installed_games = []
        self.xbox_friends = []

        self.riot_enabled = bool(Reg.get("RiotEnabled", 1))
        self.riot_running = False
        self.riot_game_name = ""
        self.riot_game_state = ""
        self.riot_game_icon = RIOT_FALLBACK_LOGO
        self.riot_id = Reg.get("RiotID", "")
        self.riot_start_ts = int(time.time())
        self.riot_installed_games = []
        self.riot_friends = []

        self.ea_enabled = bool(Reg.get("EAEnabled", 1))
        self.ea_running = False
        self.ea_game_name = ""
        self.ea_game_state = ""
        self.ea_game_icon = EA_FALLBACK_LOGO
        self.ea_account_name = Reg.get("EAAccountName", "")
        self.ea_start_ts = int(time.time())
        self.ea_installed_games = []
        self.ea_friends = []

        self.ubisoft_enabled = bool(Reg.get("UbisoftEnabled", 1))
        self.ubisoft_running = False
        self.ubisoft_game_name = ""
        self.ubisoft_game_state = ""
        self.ubisoft_game_icon = UBISOFT_FALLBACK_LOGO
        self.ubisoft_username = Reg.get("UbisoftUsername", "")
        self.ubisoft_start_ts = int(time.time())
        self.ubisoft_installed_games = []
        self.ubisoft_friends = []

        self.gog_enabled = bool(Reg.get("GOGEnabled", 1))
        self.gog_running = False
        self.gog_game_name = ""
        self.gog_game_state = ""
        self.gog_game_icon = GOG_FALLBACK_LOGO
        self.gog_username = Reg.get("GOGUsername", "")
        self.gog_start_ts = int(time.time())
        self.gog_installed_games = []
        self.gog_friends = []

        self.battlenet_enabled = bool(Reg.get("BattleNetEnabled", 1))
        self.battlenet_running = False
        self.battlenet_game_name = ""
        self.battlenet_game_state = ""
        self.battlenet_game_icon = BATTLENET_FALLBACK_LOGO
        self.battlenet_battletag = Reg.get("BattleNetBattleTag", "")
        self.battlenet_start_ts = int(time.time())
        self.battlenet_installed_games = []
        self.battlenet_friends = []

        self.gacha_enabled = bool(Reg.get("GachaEnabled", 1))
        self.gacha_sub_enabled = {
            g["key"]: bool(Reg.get(g["reg_toggle"], 1)) for g in GACHA_SUB_GAME_DEFS
        }
        self.gacha_running = False
        self.gacha_game_key = ""
        self.gacha_game_name = ""
        self.gacha_game_state = ""
        self.gacha_game_icon = GACHA_FALLBACK_LOGO
        self.gacha_level_prefix = "Lv."
        self.gacha_uid = Reg.get("GachaUID", "")
        self.gacha_account_name = Reg.get("GachaAccountName", "")
        self.gacha_level = Reg.get("GachaLevel", "")
        self.gacha_region = Reg.get("GachaRegion", "")
        self.gacha_character = Reg.get("GachaCharacter", "")
        if not self.gacha_uid and (
            self.gacha_level == "11" or self.gacha_account_name.endswith(" Linked")
        ):
            self.gacha_account_name = ""
            self.gacha_level = ""
            self.gacha_region = ""
            self.gacha_character = ""
            Reg.remove("GachaAccountName")
            Reg.remove("GachaLevel")
            Reg.remove("GachaRegion")
            Reg.remove("GachaCharacter")
        self.gacha_manual_override = bool(Reg.get("GachaManualOverride", 0))
        raw_profiles = Reg.get("GachaProfiles", {})
        if not isinstance(raw_profiles, dict):
            raw_profiles = {}
        self.gacha_profiles = {}
        sanitized_profiles = False
        for g in GACHA_SUB_GAME_DEFS:
            gk = g["key"]
            saved = raw_profiles.get(gk) if isinstance(raw_profiles.get(gk), dict) else {}
            s_uid = str(saved.get("uid") or "").strip()
            s_acc = str(saved.get("account_name") or "").strip()
            s_lvl = str(saved.get("level") or "").strip()
            s_reg = str(saved.get("region") or "").strip()
            s_chr = str(saved.get("character") or "").strip()
            # Clean any false-positive level/region without a real UID or real account
            if not s_uid and (not s_acc or s_acc.endswith(" Linked")):
                if s_acc or s_lvl or s_reg or s_chr:
                    sanitized_profiles = True
                s_acc = ""
                s_lvl = ""
                s_reg = ""
                s_chr = ""
            self.gacha_profiles[gk] = {
                "uid": s_uid,
                "account_name": s_acc,
                "level": s_lvl,
                "region": s_reg,
                "character": s_chr,
                "unlinked": bool(saved.get("unlinked", False)),
            }
        if sanitized_profiles:
            Reg.set("GachaProfiles", self.gacha_profiles)
        self.gacha_start_ts = int(time.time())
        self.gacha_installed_games = []

        self.auth_pending = {
            "epic": False,
            "steam": False,
            "gacha": False,
            "battlenet": False,
            "riot": False,
            "roblox": False,
            "xbox": False,
            "ea": False,
            "ubisoft": False,
            "gog": False,
            "minecraft": False,
        }
        for g in GACHA_SUB_GAME_DEFS:
            self.auth_pending[f"gacha_{g['key']}"] = False

        self.custom_apps_enabled = bool(Reg.get("CustomAppsEnabled", 1))
        self.custom_app_running = False
        self.custom_app_name = ""
        self.custom_app_state = ""
        self.custom_app_icon = CUSTOM_FALLBACK_LOGO
        self.custom_app_start_ts = int(time.time())
        self.custom_apps_list = CFG.get_custom_apps()

        self.discord_user_id = Reg.get("DiscordUserId", "")
        self.discord_username = Reg.get("DiscordUsername", "")
        self.discord_display_name = Reg.get("DiscordDisplayName", "")
        self.discord_friends = []

        self.minecraft_enabled = bool(Reg.get("MinecraftEnabled", 1))
        self.mc_lunar_enabled = bool(Reg.get("MCLunarEnabled", 1))
        self.mc_badlion_enabled = bool(Reg.get("MCBadlionEnabled", 1))
        self.mc_feather_enabled = bool(Reg.get("MCFeatherEnabled", 1))
        self.mc_labymod_enabled = bool(Reg.get("MCLabyModEnabled", 1))
        self.mc_prism_vanilla_enabled = bool(Reg.get("MCPrismVanillaEnabled", 1))
        self.minecraft_running = False
        self.minecraft_client_key = ""
        self.minecraft_client_name = ""
        self.minecraft_version = ""
        self.minecraft_activity = ""
        self.minecraft_username = Reg.get("MinecraftUsername", "")
        self.minecraft_icon = MINECRAFT_FALLBACK_LOGO
        self.minecraft_start_ts = int(time.time())

        self.medal_priority_enabled = bool(Reg.get("MedalPriorityRPC", 1))
        self.medal_running = False
        self.medal_encoder_active = False
        self.medal_reassertions = 0
        self.active_game_pid = 0

        self.platform_priority = Reg.get("PlatformPriority", "auto")

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

        self.rpc_headline = "Waiting for Game..."
        self.rpc_details = "Launch Any Game or Launcher"
        self.rpc_state = "Idle in Background"
        self.rpc_image_url = self.skin_icon or FALLBACK_LOGO

    def timer_str(self, platform="fortnite"):
        fn_ts = (
            self.start_ts
            if self.running
            else (self.epic_game_start_ts if self.epic_game_running else self.start_ts)
        )
        ts_map = {
            "fortnite": fn_ts,
            "epic": fn_ts,
            "steam": self.steam_start_ts,
            "roblox": self.roblox_start_ts,
            "xbox": self.xbox_start_ts,
            "riot": self.riot_start_ts,
            "ea": self.ea_start_ts,
            "ubisoft": self.ubisoft_start_ts,
            "gog": self.gog_start_ts,
            "battlenet": self.battlenet_start_ts,
            "gacha": self.gacha_start_ts,
            "minecraft": self.minecraft_start_ts,
            "custom_apps": self.custom_app_start_ts,
        }
        ts = ts_map.get(platform, self.start_ts)
        diff = max(0, int(time.time()) - ts)
        h, rem = divmod(diff, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def active_platform(self):
        if not self.active:
            return "paused"
        prio = self.platform_priority
        checks = {
            "fortnite": self.fortnite_enabled and (self.running or self.epic_game_running),
            "minecraft": self.minecraft_enabled and self.minecraft_running,
            "gacha": self.gacha_enabled and self.gacha_running,
            "riot": self.riot_enabled and self.riot_running,
            "ea": self.ea_enabled and self.ea_running,
            "ubisoft": self.ubisoft_enabled and self.ubisoft_running,
            "gog": self.gog_enabled and self.gog_running,
            "battlenet": self.battlenet_enabled and self.battlenet_running,
            "steam": self.steam_enabled and self.steam_running,
            "roblox": self.roblox_enabled and self.roblox_running,
            "xbox": self.xbox_enabled and self.xbox_running,
            "custom_apps": self.custom_apps_enabled and self.custom_app_running,
        }
        if prio in checks and checks[prio]:
            return prio

        for key in (
            "fortnite",
            "minecraft",
            "gacha",
            "riot",
            "ea",
            "ubisoft",
            "gog",
            "battlenet",
            "steam",
            "roblox",
            "xbox",
            "custom_apps",
        ):
            if checks[key]:
                return key
        return "idle"

    def media_str(self):
        if not self.media_title:
            return ""
        return f"{self.media_artist} - {self.media_title}" if self.media_artist else self.media_title

    def is_gacha_game_enabled(self, game_key):
        if not self.gacha_enabled:
            return False
        return bool(self.gacha_sub_enabled.get(game_key, True))

    def gacha_level_str(self, game_key=None):
        if game_key and game_key in self.gacha_profiles:
            prof = self.gacha_profiles[game_key]
            lvl = str(prof.get("level") or "").strip()
            pref = next(
                (g["level_prefix"] for g in GACHA_SUB_GAME_DEFS if g["key"] == game_key),
                "Lv.",
            )
        else:
            lvl = str(self.gacha_level or "").strip()
            pref = (self.gacha_level_prefix or "Lv.").strip()
        if not lvl:
            return ""
        if any(c.isalpha() for c in lvl):
            return lvl
        return f"{pref} {lvl}"

    def gacha_game_summary(self, game_key):
        prof = self.gacha_profiles.get(game_key) or {}
        if prof.get("unlinked"):
            return ""
        uid = str(prof.get("uid") or "").strip()
        acc = str(prof.get("account_name") or "").strip()
        if not uid and not acc:
            return ""
        parts = []
        if acc and uid and acc != uid:
            parts.append(f"{acc} (UID {uid})")
        elif uid:
            parts.append(f"UID {uid}")
        elif acc:
            parts.append(acc)
        lvl_s = self.gacha_level_str(game_key)
        if lvl_s:
            parts.append(lvl_s)
        reg = str(prof.get("region") or "").strip()
        if reg:
            parts.append(reg)
        char = str(prof.get("character") or "").strip()
        if char:
            parts.append(char)
        return " • ".join(parts)

    def gacha_summary_str(self):
        if self.gacha_game_key and self.gacha_game_key in self.gacha_profiles:
            s_game = self.gacha_game_summary(self.gacha_game_key)
            if s_game:
                return s_game
        parts = []
        if self.gacha_account_name:
            parts.append(self.gacha_account_name)
        lvl_s = self.gacha_level_str()
        if lvl_s:
            parts.append(lvl_s)
        if self.gacha_region:
            parts.append(self.gacha_region)
        if self.gacha_character:
            parts.append(self.gacha_character)
        return " • ".join(parts)

    def platform_account_summary(self, plat):
        if plat and plat.startswith("gacha_"):
            gkey = plat.split("gacha_", 1)[1]
            return self.gacha_game_summary(gkey)
        if plat == "epic":
            return self.epic_name if self.epic_name else ("Linked" if self.epic_ok else "")
        if plat == "steam":
            return self.steam_user_name or (f"ID {self.steam_id64}" if self.steam_id64 else "")
        if plat == "gacha":
            for g in GACHA_SUB_GAME_DEFS:
                gs = self.gacha_game_summary(g["key"])
                if gs:
                    return f"{g['name']}: {gs}"
            return self.gacha_summary_str() or (f"UID {self.gacha_uid}" if self.gacha_uid else "")
        if plat == "battlenet":
            return self.battlenet_battletag
        if plat == "riot":
            return self.riot_id
        if plat == "roblox":
            if self.roblox_display_name and self.roblox_user_name and self.roblox_display_name.lower() != self.roblox_user_name.lower():
                return f"{self.roblox_display_name} (@{self.roblox_user_name})"
            return f"@{self.roblox_user_name}" if self.roblox_user_name else ""
        if plat == "xbox":
            return self.xbox_gamertag
        if plat == "ea":
            return self.ea_account_name
        if plat == "ubisoft":
            return self.ubisoft_username
        if plat == "gog":
            return self.gog_username
        if plat == "minecraft":
            return self.minecraft_username
        return ""
