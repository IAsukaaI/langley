import os
import re
import sys
import json
import ctypes
import winreg
import threading
import psutil
from PIL import Image, ImageDraw

CLIENT_ID = "1570074042340212776"
APP_TITLE = "Lang!ley"
APP_VERSION = "1.0.7"
REG_NAME = "LangleyFortniteRPC"
REG_PATH = r"Software\LangleyFortniteRPC"
RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STEAM_REG_PATH = r"Software\Valve\Steam"
STEAM_ACTIVE_PATH = r"Software\Valve\Steam\ActiveProcess"
XBOX_REG_PATH = r"Software\Microsoft\XboxLive"
GSI_PORT = 58741

WEB_URL = "https://asukaa.de"
LANGLEY_URL = "https://asukaa.de/langley"
UPDATE_JSON_URL = "https://asukaa.de/langley/version.json"
DEFAULT_SETUP_URL = "https://asukaa.de/langley/Langley_Setup.exe"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    ),
    "Accept": "application/json, image/avif, image/webp, image/apng, image/png, image/*, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

OAUTH_URL = "https://account-public-service-prod.ol.epicgames.com"
PARTY_URL = "https://party-service-prod.ol.epicgames.com"
MCP_URL = "https://fngw-mcp-gc-livefn.ol.epicgames.com"
FRIENDS_URL = "https://friends-public-service-prod.ol.epicgames.com"
PRESENCE_URL = "https://presence-public-service-prod.ol.epicgames.com"

SWITCH_BASIC = "OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3"
ANDROID_BASIC = "M2Y2OWU1NmM3NjQ5NDkyYzhjYzI5ZjFhZjA4YThhMTI6YjUxZWU5Y2IxMjIzNGY1MGE2OWVmYTY3ZWY1MzgxMmU="

LICENSE_TEXT = (
    "================================================================================\n"
    "                                  L I C E N S E\n"
    "================================================================================\n\n"
    "Copyright (C) 2026 Lang!ley | Asukaa | asukaa.de - All Rights Reserved.\n\n"
    "Unauthorized copying, modification, distribution, reverse engineering, or use \n"
    "of this software and its source code, via any medium, is strictly prohibited \n"
    "without prior written permission from the author.\n\n\n"
    "--------------------------------------------------------------------------------\n"
    "                   DISCLAIMER OF WARRANTY AND LIABILITY\n"
    "--------------------------------------------------------------------------------\n\n"
    "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR \n"
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, \n"
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. \n\n"
    "IN NO EVENT SHALL THE AUTHOR OR COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, \n"
    "DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, \n"
    "ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER \n"
    "DEALINGS IN THE SOFTWARE. \n\n"
    "USE AT YOUR OWN RISK."
)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_static_config_dir():
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cand = os.path.join(meipass, "config")
        if os.path.exists(cand):
            return cand
    return os.path.join(get_base_dir(), "config")


def get_user_data_dir():
    appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    return os.path.join(appdata, "Lang!ley")


BASE_DIR = get_base_dir()
CONFIG_DIR = get_static_config_dir()
USER_DATA_DIR = get_user_data_dir()

GACHA_SUB_GAME_DEFS = [
    {
        "key": "genshin",
        "name": "Genshin Impact",
        "publisher": "HoYoverse",
        "level_prefix": "AR",
        "reg_toggle": "GachaGenshinEnabled",
        "json_toggle": "gacha_genshin",
        "login_url": "https://act.hoyolab.com/app/community-game-records-sea/index.html#/ys",
        "tip": "Detects Genshin Impact and syncs your UID, Adventure Rank (AR), Server Region & Equipped Character.",
    },
    {
        "key": "hsr",
        "name": "Honkai: Star Rail",
        "publisher": "HoYoverse",
        "level_prefix": "TL",
        "reg_toggle": "GachaHSREnabled",
        "json_toggle": "gacha_hsr",
        "login_url": "https://act.hoyolab.com/app/community-game-records-sea/index.html#/hsr",
        "tip": "Detects Honkai: Star Rail and syncs your UID, Trailblaze Level (TL), Server Region & Equipped Character.",
    },
    {
        "key": "zzz",
        "name": "Zenless Zone Zero",
        "publisher": "HoYoverse",
        "level_prefix": "IK Lv.",
        "reg_toggle": "GachaZZZEnabled",
        "json_toggle": "gacha_zzz",
        "login_url": "https://act.hoyolab.com/app/zzz-game-record/index.html",
        "tip": "Detects Zenless Zone Zero and syncs your UID, Inter-Knot Level (IK Lv.), Server Region & Agent.",
    },
    {
        "key": "hi3",
        "name": "Honkai Impact 3rd",
        "publisher": "HoYoverse",
        "level_prefix": "Captain Lv.",
        "reg_toggle": "GachaHI3Enabled",
        "json_toggle": "gacha_hi3",
        "login_url": "https://act.hoyolab.com/app/community-game-records-sea/index.html#/bh3",
        "tip": "Detects Honkai Impact 3rd and syncs your UID, Captain Level, Server Region & Valkyrie.",
    },
    {
        "key": "wuwa",
        "name": "Wuthering Waves",
        "publisher": "Kuro Games",
        "level_prefix": "UL",
        "reg_toggle": "GachaWuWaEnabled",
        "json_toggle": "gacha_wuwa",
        "login_url": "https://wutheringwaves.kurogames.com/en/",
        "tip": "Detects Wuthering Waves and syncs your UID, Union Level (UL), Server Region & Resonator.",
    },
    {
        "key": "nikke",
        "name": "Goddess of Victory: NIKKE",
        "publisher": "SHIFT UP",
        "level_prefix": "Commander Lv.",
        "reg_toggle": "GachaNikkeEnabled",
        "json_toggle": "gacha_nikke",
        "login_url": "https://www.blablalink.com/",
        "tip": "Detects Goddess of Victory: NIKKE and syncs your Commander Level, Server Region & Outpost status.",
    },
    {
        "key": "reverse1999",
        "name": "Reverse: 1999",
        "publisher": "Bluepoch",
        "level_prefix": "Timekeeper Lv.",
        "reg_toggle": "GachaReverse1999Enabled",
        "json_toggle": "gacha_reverse1999",
        "login_url": "https://re1999.bluepoch.com/en/home/",
        "tip": "Detects Reverse: 1999 and syncs your Timekeeper Level, Server Region & Arcanist.",
    },
    {
        "key": "pgr",
        "name": "Punishing: Gray Raven",
        "publisher": "Kuro Games",
        "level_prefix": "Commandant Lv.",
        "reg_toggle": "GachaPGREnabled",
        "json_toggle": "gacha_pgr",
        "login_url": "https://pgr.kurogame.net/",
        "tip": "Detects Punishing: Gray Raven and syncs your Commandant Level, Server Region & Construct.",
    },
    {
        "key": "sololeveling",
        "name": "Solo Leveling:ARISE",
        "publisher": "Netmarble",
        "level_prefix": "Hunter Lv.",
        "reg_toggle": "GachaSoloLevelingEnabled",
        "json_toggle": "gacha_sololeveling",
        "login_url": "https://sololeveling.netmarble.com/en",
        "tip": "Detects Solo Leveling:ARISE and syncs your Hunter Level, Server Region & Hunter status.",
    },
    {
        "key": "infinitynikki",
        "name": "Infinity Nikki",
        "publisher": "Infold Games",
        "level_prefix": "Mira Lv.",
        "reg_toggle": "GachaInfinityNikkiEnabled",
        "json_toggle": "gacha_infinitynikki",
        "login_url": "https://infinitynikki.infoldgames.com/en/home",
        "tip": "Detects Infinity Nikki and syncs your Mira Level, Server Region & Miraland Stylist status.",
    },
    {
        "key": "endfield",
        "name": "Arknights: Endfield",
        "publisher": "GRYPHLINE",
        "level_prefix": "Endministrator Lv.",
        "reg_toggle": "GachaEndfieldEnabled",
        "json_toggle": "gacha_endfield",
        "login_url": "https://endfield.gryphline.com/en-us",
        "tip": "Detects Arknights: Endfield and syncs your Endministrator Level, Server Region & Operator.",
    },
]


DEFAULT_SETTINGS = {
    "version": APP_VERSION,
    "autostart": False,
    "start_minimized": True,
    "platform_priority": "auto",
    "medal_priority_rpc": True,
    "show_media_rpc": True,
    "toggles": {
        "fortnite": True,
        "minecraft": True,
        "gacha": True,
        "riot": True,
        "ea": True,
        "ubisoft": True,
        "gog": True,
        "battlenet": True,
        "steam": True,
        "roblox": True,
        "xbox": True,
        "custom_apps": True,
        "mc_lunar": True,
        "mc_badlion": True,
        "mc_feather": True,
        "mc_labymod": True,
        "mc_prism_vanilla": True,
        "gacha_genshin": True,
        "gacha_hsr": True,
        "gacha_zzz": True,
        "gacha_hi3": True,
        "gacha_wuwa": True,
        "gacha_nikke": True,
        "gacha_reverse1999": True,
        "gacha_pgr": True,
        "gacha_sololeveling": True,
        "gacha_infinitynikki": True,
        "gacha_endfield": True,
    },
    "accounts": {
        "skin_id": "",
        "skin_name": "Charlotte-Sensei",
        "skin_icon": "https://fortnite-api.com/images/cosmetics/br/cid_028_athena_commando_f/icon.png",
        "season_level": 1,
        "epic_name": "",
        "steam_persona": "",
        "steam_id64": "",
        "steam_manual_override": False,
        "roblox_user_id": "",
        "roblox_user_name": "",
        "roblox_display_name": "",
        "xbox_gamertag": "",
        "xbox_manual_override": False,
        "discord_user_id": "",
        "discord_username": "",
        "discord_display_name": "",
        "gacha_uid": "",
        "gacha_account_name": "",
        "gacha_level": "",
        "gacha_region": "",
        "gacha_character": "",
        "gacha_manual_override": False,
        "gacha_profiles": {},
        "battlenet_battletag": "",
        "riot_id": "",
        "ea_account_name": "",
        "ubisoft_username": "",
        "gog_username": "",
        "minecraft_username": "",
    },
    "tracked_friends": {
        "epic": [],
        "discord": [],
        "xbox": [],
        "riot": [],
        "ea": [],
        "ubisoft": [],
        "gog": [],
        "battlenet": [],
    },
}

DEFAULT_CUSTOM_APPS = {"apps": []}

DEFAULT_PATCH_NOTES = {
    "current_version": APP_VERSION,
    "releases": [
        {
            "version": "1.0.7",
            "date": "2026-11-17",
            "title": "Discord RPC Reliability, Gacha Levels & Region Fixes, CS2/Fortnite Priority",
            "highlights": [
                "Fixed Discord IPC reconnect backoff, non-blocking named-pipe timeouts, and instant non-freezing Quit/Shutdown.",
                "Fixed Gacha game icons, accurate game-specific Server Region detection, and live Gacha Level display (AR, TL, IK Lv., UL, etc.) while playing.",
                "Fixed Roblox Home icon loading, auto-update false prompts / legacy autostart sync, and RPC priority lock over native Fortnite and Steam CS2.",
            ],
        },
        {
            "version": "1.0.6",
            "date": "2026-11-16",
            "title": "Major and Minor Bug Fixes",
            "highlights": [
                "Fixed Major and Small Bugs.",
            ],
        },
        {
            "version": "1.0.5",
            "date": "2026-11-15",
            "title": "Modular Architecture, HoYoPlay & Gacha Support, Custom Apps & Polish",
            "highlights": [
                "Refactored codebase into a modular multi-file architecture with external JSON configs.",
                "Added HoYoPlay & PC Gacha Games detector (Genshin Impact, Honkai: Star Rail, Zenless Zone Zero, Honkai Impact 3rd, Wuthering Waves, NIKKE, Reverse: 1999, PGR, Solo Leveling:ARISE, Infinity Nikki, Arknights: Endfield).",
                "Added Custom External Applications (.exe) support in Game Hub and Settings.",
                "Fixed Xbox PC / Microsoft Store Fortnite conflict so XboxClient never hijacks Fortnite.",
                "Enforced strict visible-window checks so background launchers and tray apps never trigger RPC.",
                "Fixed global mousewheel scrolling, top-left window icon, top status bar layout, Settings compact badges, and Roblox fallback thumbnail.",
            ],
        },
        {
            "version": "1.0.4",
            "date": "2026-11-10",
            "title": "Battle.net, Minecraft Clients, Medal.tv Priority Guard & Settings Tab",
            "highlights": [
                "Added Blizzard Battle.net detector for Call of Duty, WoW, Overwatch 2, Diablo IV, Hearthstone, and StarCraft II.",
                "Added Minecraft multi-client detection for Lunar, Badlion, Feather, LabyMod, and Prism / Vanilla.",
                "Introduced Medal.tv RPC Priority Guard and centralized Settings tab.",
            ],
        },
        {
            "version": "1.0.3",
            "date": "2026-10-28",
            "title": "PC Game Launchers & Unified Game Hub Library",
            "highlights": [
                "Added native detectors for Riot Games, EA App, Ubisoft Connect, and GOG Galaxy.",
                "Built the unified Game Hub tab to browse and launch installed games.",
            ],
        },
        {
            "version": "1.0.2",
            "date": "2026-10-14",
            "title": "Xbox PC Game Pass, Roblox Resolver & Multi-Platform Friends",
            "highlights": [
                "Added Xbox / PC Game Pass detector and Gamertag linking.",
                "Added live Roblox place resolver with experience title, creator, and thumbnail.",
            ],
        },
        {
            "version": "1.0.1",
            "date": "2026-09-30",
            "title": "Steam Integration, CS2 / Dota 2 Live Stats & Media Controller",
            "highlights": [
                "Added Steam active game detection and CS2 / Dota 2 GSI server.",
                "Added Windows Media & Spotify controller.",
            ],
        },
        {
            "version": "1.0.0",
            "date": "2026-09-15",
            "title": "Initial Release — Fortnite & Epic Games Rich Presence",
            "highlights": [
                "Real-time Fortnite log parser, Epic Party API telemetry, and custom desktop UI.",
            ],
        },
    ],
}


class ConfigManager:
    def __init__(self, config_dir=CONFIG_DIR, user_data_dir=USER_DATA_DIR):
        self.config_dir = config_dir
        self.user_data_dir = user_data_dir
        self.lock = threading.RLock()
        for d in (self.user_data_dir, self.config_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                pass
        self.settings_path = os.path.join(self.user_data_dir, "settings.json")
        self.custom_apps_path = os.path.join(self.user_data_dir, "custom_apps.json")
        self.games_db_path = os.path.join(self.config_dir, "games_db.json")
        self.patch_notes_path = os.path.join(self.config_dir, "patch_notes.json")

        self.settings = self._load_or_init(self.settings_path, DEFAULT_SETTINGS, write_if_missing=True)
        self._merge_defaults(self.settings, DEFAULT_SETTINGS)
        self.custom_apps = self._load_or_init(self.custom_apps_path, DEFAULT_CUSTOM_APPS, write_if_missing=True)
        self.games_db = self._load_or_init(self.games_db_path, {}, write_if_missing=False)
        self.patch_notes = self._load_or_init(self.patch_notes_path, DEFAULT_PATCH_NOTES, write_if_missing=False)

    def _load_or_init(self, path, default_obj, write_if_missing=True):
        with self.lock:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
            copy_obj = json.loads(json.dumps(default_obj))
            if default_obj and write_if_missing:
                self._write_json(path, copy_obj)
            return copy_obj

    def _merge_defaults(self, target, defaults):
        changed = False
        for k, v in defaults.items():
            if k not in target:
                target[k] = json.loads(json.dumps(v))
                changed = True
            elif isinstance(v, dict) and isinstance(target.get(k), dict):
                for sk, sv in v.items():
                    if sk not in target[k]:
                        target[k][sk] = json.loads(json.dumps(sv))
                        changed = True
        if target.get("version") != APP_VERSION:
            target["version"] = APP_VERSION
            changed = True
        if changed:
            self.save_settings()

    def _write_json(self, path, data):
        with self.lock:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, path)
            except Exception:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

    def save_settings(self):
        self._write_json(self.settings_path, self.settings)

    def save_custom_apps(self):
        self._write_json(self.custom_apps_path, self.custom_apps)

    def get_custom_apps(self):
        with self.lock:
            apps = self.custom_apps.get("apps")
            return list(apps) if isinstance(apps, list) else []

    def set_custom_apps(self, apps_list):
        with self.lock:
            self.custom_apps["apps"] = list(apps_list)
            self.save_custom_apps()

    def get_patch_notes(self):
        with self.lock:
            self.patch_notes = self._load_or_init(self.patch_notes_path, DEFAULT_PATCH_NOTES, write_if_missing=False)
            return self.patch_notes


CFG = ConfigManager()
_pn_ver = str((CFG.patch_notes or {}).get("current_version") or "").strip()
if _pn_ver and tuple(int(x) for x in re.findall(r"\d+", _pn_ver)[:3]) > tuple(int(x) for x in re.findall(r"\d+", APP_VERSION)[:3]):
    APP_VERSION = _pn_ver

_LOGOS = CFG.games_db.get("logos") or {}
FALLBACK_LOGO = _LOGOS.get("fortnite", "https://upload.wikimedia.org/wikipedia/commons/7/7c/Fortnite_F_lettermark_logo.png")
STEAM_FALLBACK_LOGO = _LOGOS.get("steam", "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/512px-Steam_icon_logo.svg.png")
ROBLOX_FALLBACK_LOGO = _LOGOS.get("roblox", "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7e/Roblox_Logo_2022.jpg/512px-Roblox_Logo_2022.jpg")
XBOX_FALLBACK_LOGO = _LOGOS.get("xbox", "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/Xbox_one_logo.svg/512px-Xbox_one_logo.svg.png")
RIOT_FALLBACK_LOGO = _LOGOS.get("riot", "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/LoL_icon.svg/512px-LoL_icon.svg.png")
VALORANT_LOGO = _LOGOS.get("valorant", "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fc/Valorant_logo_-_pink_color_version.svg/512px-Valorant_logo_-_pink_color_version.svg.png")
LOL_LOGO = _LOGOS.get("lol", "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/LoL_icon.svg/512px-LoL_icon.svg.png")
EA_FALLBACK_LOGO = _LOGOS.get("ea", "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0d/Electronic-Arts-Logo.svg/512px-Electronic-Arts-Logo.svg.png")
UBISOFT_FALLBACK_LOGO = _LOGOS.get("ubisoft", "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Ubisoft_logo.svg/512px-Ubisoft_logo.svg.png")
GOG_FALLBACK_LOGO = _LOGOS.get("gog", "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/GOG.com_logo.svg/512px-GOG.com_logo.svg.png")
BATTLENET_FALLBACK_LOGO = _LOGOS.get("battlenet", "https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/Blizzard_Entertainment_Logo_2015.svg/512px-Blizzard_Entertainment_Logo_2015.svg.png")
MINECRAFT_FALLBACK_LOGO = _LOGOS.get("minecraft", "https://upload.wikimedia.org/wikipedia/commons/thumb/1/10/Minecraft_2024_block_icon.png/512px-Minecraft_2024_block_icon.png")
GACHA_FALLBACK_LOGO = _LOGOS.get("gacha", "https://fastcdn.hoyoverse.com/static-resource-v2/2024/04/12/b7002217a91f18d87e22d0b419b04f29_7455586655940982297.png")
CUSTOM_FALLBACK_LOGO = _LOGOS.get("custom", STEAM_FALLBACK_LOGO)
GAME_ICONS_MAP = {k.lower(): v for k, v in (CFG.games_db.get("game_icons") or {}).items()}


def lookup_known_game_icon(title, fallback=""):
    t_low = re.sub(r"\s+", " ", str(title or "")).strip().lower()
    if not t_low:
        return fallback
    if t_low in GAME_ICONS_MAP:
        return GAME_ICONS_MAP[t_low]
    for k, url in GAME_ICONS_MAP.items():
        if len(k) >= 4 and (k in t_low or t_low in k):
            return url
    return fallback

STEAM_IGNORE_APPIDS = set(CFG.games_db.get("steam_ignore_appids") or [0, 228980, 250820, 1070560, 1391110, 1493710, 1628350, 1887720, 2180100])
MEDAL_PROCS = {x.lower() for x in (CFG.games_db.get("medal_procs") or ["medal.exe", "medalencoder.exe", "medalservice.exe", "medaloverlay.exe"])}
XBOX_IGNORE_PROCS = {
    x.lower()
    for x in (
        CFG.games_db.get("xbox_ignore_procs")
        or [
            "gamingservices.exe",
            "gamingservicesnet.exe",
            "xboxpcapp.exe",
            "xboxpcappft.exe",
            "xboxgamebarwidgets.exe",
            "gamebar.exe",
            "gamebarftserver.exe",
            "gameinputsvc.exe",
            "gamelaunchhelper.exe",
            "fortniteclient-win64-shipping.exe",
            "fortniteclient-win64-shipping_eac.exe",
            "fortniteclient-win64-shipping_be.exe",
            "fortniteclient-win64-shipping_eac_eos.exe",
            "fortnite.exe",
            "fortnitelauncher.exe",
            "easyanticheat.exe",
            "easyanticheat_eos.exe",
            "crashreportclient.exe",
        ]
    )
} | MEDAL_PROCS
EA_IGNORE_PROCS = {x.lower() for x in (CFG.games_db.get("ea_ignore_procs") or [])} | MEDAL_PROCS
UBISOFT_IGNORE_PROCS = {x.lower() for x in (CFG.games_db.get("ubisoft_ignore_procs") or [])} | MEDAL_PROCS
GOG_IGNORE_PROCS = {x.lower() for x in (CFG.games_db.get("gog_ignore_procs") or [])} | MEDAL_PROCS
BATTLENET_IGNORE_PROCS = {x.lower() for x in (CFG.games_db.get("battlenet_ignore_procs") or [])} | MEDAL_PROCS
GACHA_IGNORE_PROCS = {x.lower() for x in (CFG.games_db.get("gacha_ignore_procs") or ["hyp.exe", "hyphelper.exe", "launcher.exe"])} | MEDAL_PROCS
EPIC_IGNORE_PROCS = {
    x.lower()
    for x in (
        CFG.games_db.get("epic_ignore_procs")
        or [
            "epicgameslauncher.exe",
            "epicwebhelper.exe",
            "epiconlineservicesuserhelper.exe",
            "epiconlineservices.exe",
            "eosoverlayrenderer-win64-shipping.exe",
            "eosoverlayrenderer-win32-shipping.exe",
            "unrealcefsubprocess.exe",
            "crashreportclient.exe",
            "easyanticheat.exe",
            "easyanticheat_eos.exe",
            "fortnitelauncher.exe",
        ]
    )
} | MEDAL_PROCS


_JSON_KEY_MAP = {
    "StartMinimized": ("root", "start_minimized", bool),
    "PlatformPriority": ("root", "platform_priority", str),
    "MedalPriorityRPC": ("root", "medal_priority_rpc", bool),
    "ShowMediaRPC": ("root", "show_media_rpc", bool),
    "FortniteEnabled": ("toggles", "fortnite", bool),
    "MinecraftEnabled": ("toggles", "minecraft", bool),
    "GachaEnabled": ("toggles", "gacha", bool),
    "RiotEnabled": ("toggles", "riot", bool),
    "EAEnabled": ("toggles", "ea", bool),
    "UbisoftEnabled": ("toggles", "ubisoft", bool),
    "GOGEnabled": ("toggles", "gog", bool),
    "BattleNetEnabled": ("toggles", "battlenet", bool),
    "SteamEnabled": ("toggles", "steam", bool),
    "RobloxEnabled": ("toggles", "roblox", bool),
    "XboxEnabled": ("toggles", "xbox", bool),
    "CustomAppsEnabled": ("toggles", "custom_apps", bool),
    "MCLunarEnabled": ("toggles", "mc_lunar", bool),
    "MCBadlionEnabled": ("toggles", "mc_badlion", bool),
    "MCFeatherEnabled": ("toggles", "mc_feather", bool),
    "MCLabyModEnabled": ("toggles", "mc_labymod", bool),
    "MCPrismVanillaEnabled": ("toggles", "mc_prism_vanilla", bool),
    "GachaGenshinEnabled": ("toggles", "gacha_genshin", bool),
    "GachaHSREnabled": ("toggles", "gacha_hsr", bool),
    "GachaZZZEnabled": ("toggles", "gacha_zzz", bool),
    "GachaHI3Enabled": ("toggles", "gacha_hi3", bool),
    "GachaWuWaEnabled": ("toggles", "gacha_wuwa", bool),
    "GachaNikkeEnabled": ("toggles", "gacha_nikke", bool),
    "GachaReverse1999Enabled": ("toggles", "gacha_reverse1999", bool),
    "GachaPGREnabled": ("toggles", "gacha_pgr", bool),
    "GachaSoloLevelingEnabled": ("toggles", "gacha_sololeveling", bool),
    "GachaInfinityNikkiEnabled": ("toggles", "gacha_infinitynikki", bool),
    "GachaEndfieldEnabled": ("toggles", "gacha_endfield", bool),
    "SkinId": ("accounts", "skin_id", str),
    "SkinName": ("accounts", "skin_name", str),
    "SkinIcon": ("accounts", "skin_icon", str),
    "SeasonLevel": ("accounts", "season_level", int),
    "EpicName": ("accounts", "epic_name", str),
    "SteamPersona": ("accounts", "steam_persona", str),
    "SteamID64": ("accounts", "steam_id64", str),
    "SteamManualOverride": ("accounts", "steam_manual_override", bool),
    "RobloxUserId": ("accounts", "roblox_user_id", str),
    "RobloxUserName": ("accounts", "roblox_user_name", str),
    "RobloxDisplayName": ("accounts", "roblox_display_name", str),
    "XboxGamertag": ("accounts", "xbox_gamertag", str),
    "XboxManualOverride": ("accounts", "xbox_manual_override", bool),
    "DiscordUserId": ("accounts", "discord_user_id", str),
    "DiscordUsername": ("accounts", "discord_username", str),
    "DiscordDisplayName": ("accounts", "discord_display_name", str),
    "GachaUID": ("accounts", "gacha_uid", str),
    "GachaAccountName": ("accounts", "gacha_account_name", str),
    "GachaLevel": ("accounts", "gacha_level", str),
    "GachaRegion": ("accounts", "gacha_region", str),
    "GachaCharacter": ("accounts", "gacha_character", str),
    "GachaManualOverride": ("accounts", "gacha_manual_override", bool),
    "GachaProfiles": ("accounts", "gacha_profiles", dict),
    "BattleNetBattleTag": ("accounts", "battlenet_battletag", str),
    "RiotID": ("accounts", "riot_id", str),
    "EAAccountName": ("accounts", "ea_account_name", str),
    "UbisoftUsername": ("accounts", "ubisoft_username", str),
    "GOGUsername": ("accounts", "gog_username", str),
    "MinecraftUsername": ("accounts", "minecraft_username", str),
    "EpicTrackedFriends": ("tracked_friends", "epic", list),
    "DiscordTrackedFriends": ("tracked_friends", "discord", list),
    "XboxTrackedFriends": ("tracked_friends", "xbox", list),
    "RiotTrackedFriends": ("tracked_friends", "riot", list),
    "EATrackedFriends": ("tracked_friends", "ea", list),
    "UbisoftTrackedFriends": ("tracked_friends", "ubisoft", list),
    "GOGTrackedFriends": ("tracked_friends", "gog", list),
    "BattleNetTrackedFriends": ("tracked_friends", "battlenet", list),
}


class Reg:
    @staticmethod
    def _reg_read_raw(name, default=None, path=REG_PATH):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as k:
                val, _ = winreg.QueryValueEx(k, name)
                return val
        except OSError:
            return default

    @staticmethod
    def get(name, default=None, path=REG_PATH):
        if path == REG_PATH and name in _JSON_KEY_MAP:
            section, key, vtype = _JSON_KEY_MAP[name]
            with CFG.lock:
                container = CFG.settings if section == "root" else CFG.settings.setdefault(section, {})
                val = container.get(key)
                reg_val = Reg._reg_read_raw(name, None, path=REG_PATH)
                if reg_val is not None and (val is None or val == "" or val == [] or val == {}):
                    if vtype is list and isinstance(reg_val, str):
                        try:
                            val = json.loads(reg_val)
                        except Exception:
                            val = []
                    elif vtype is dict and isinstance(reg_val, str):
                        try:
                            val = json.loads(reg_val)
                        except Exception:
                            val = {}
                    elif vtype is bool:
                        val = bool(reg_val)
                    elif vtype is int:
                        try:
                            val = int(reg_val)
                        except Exception:
                            val = default
                    else:
                        val = str(reg_val)
                    container[key] = val
                    CFG.save_settings()
                if val is not None:
                    if vtype in (list, dict):
                        return json.dumps(val) if isinstance(default, str) else val
                    return val
        return Reg._reg_read_raw(name, default, path=path)

    @staticmethod
    def get_any(name, default=None, path=REG_PATH, roots=(winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)):
        for root in roots:
            for flag in (
                winreg.KEY_READ,
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0),
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            ):
                try:
                    with winreg.OpenKey(root, path, 0, flag) as k:
                        val, _ = winreg.QueryValueEx(k, name)
                        return val
                except OSError:
                    continue
        return default

    @staticmethod
    def list_subkeys(path, roots=(winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)):
        out = []
        seen = set()
        for root in roots:
            for flag in (
                winreg.KEY_READ,
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0),
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            ):
                try:
                    with winreg.OpenKey(root, path, 0, flag) as k:
                        idx = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(k, idx)
                                idx += 1
                                key_id = (root, sub.lower())
                                if key_id not in seen:
                                    seen.add(key_id)
                                    out.append((root, flag, f"{path}\\{sub}", sub))
                            except OSError:
                                break
                except OSError:
                    continue
        return out

    @staticmethod
    def read_key_dict(root, flag, path):
        res = {}
        try:
            with winreg.OpenKey(root, path, 0, flag) as k:
                idx = 0
                while True:
                    try:
                        vname, vval, _ = winreg.EnumValue(k, idx)
                        res[vname] = vval
                        idx += 1
                    except OSError:
                        break
        except OSError:
            pass
        return res

    @staticmethod
    def set(name, val, rtype=winreg.REG_SZ):
        if name in _JSON_KEY_MAP:
            section, key, vtype = _JSON_KEY_MAP[name]
            with CFG.lock:
                container = CFG.settings if section == "root" else CFG.settings.setdefault(section, {})
                if vtype is list and isinstance(val, str):
                    try:
                        container[key] = json.loads(val)
                    except Exception:
                        container[key] = []
                elif vtype is dict and isinstance(val, str):
                    try:
                        container[key] = json.loads(val)
                    except Exception:
                        container[key] = {}
                elif vtype is bool:
                    container[key] = bool(val)
                elif vtype is int:
                    try:
                        container[key] = int(val)
                    except Exception:
                        container[key] = 1
                else:
                    container[key] = val
                CFG.save_settings()
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as k:
                reg_store_val = json.dumps(val) if isinstance(val, (dict, list)) else val
                winreg.SetValueEx(k, name, 0, rtype, reg_store_val)
        except OSError:
            pass

    @staticmethod
    def remove(name):
        if name in _JSON_KEY_MAP:
            section, key, vtype = _JSON_KEY_MAP[name]
            with CFG.lock:
                container = CFG.settings if section == "root" else CFG.settings.setdefault(section, {})
                container[key] = (
                    []
                    if vtype is list
                    else ({} if vtype is dict else (False if vtype is bool else (0 if vtype is int else "")))
                )
                CFG.save_settings()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            pass

    @staticmethod
    def _build_autostart_cmd(minimized):
        arg = " --minimized" if minimized else ""
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"{arg}'
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        main_script = os.path.join(BASE_DIR, "Lang!ley.py")
        if not os.path.exists(main_script):
            main_script = os.path.abspath(sys.argv[0])
        return f'"{pyw}" "{main_script}"{arg}'

    @staticmethod
    def sync_autostart_target():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH, 0, winreg.KEY_READ) as k:
                cur_val, _ = winreg.QueryValueEx(k, REG_NAME)
        except OSError:
            return False
        cur_str = str(cur_val or "").strip()
        cur_low = cur_str.lower()
        minimized = bool(CFG.settings.get("start_minimized", True))
        desired = Reg._build_autostart_cmd(minimized)
        should_update = False
        if getattr(sys, "frozen", False):
            if cur_low != desired.lower():
                should_update = True
        else:
            if "lang!ley code" in cur_low:
                should_update = True
            else:
                exe_part = cur_str
                if exe_part.startswith('"') and '"' in exe_part[1:]:
                    first_target = exe_part[1:exe_part.index('"', 1)]
                else:
                    first_target = exe_part.split(" ")[0]
                if not os.path.exists(first_target):
                    should_update = True
        if should_update:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, REG_NAME, 0, winreg.REG_SZ, desired)
                return True
            except OSError:
                pass
        return False

    @staticmethod
    def has_autostart():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_PATH, 0, winreg.KEY_READ) as k:
                winreg.QueryValueEx(k, REG_NAME)
                with CFG.lock:
                    if not CFG.settings.get("autostart"):
                        CFG.settings["autostart"] = True
                        CFG.save_settings()
                Reg.sync_autostart_target()
                return True
        except OSError:
            return bool(CFG.settings.get("autostart", False))

    @staticmethod
    def update_startup(enabled, minimized):
        with CFG.lock:
            CFG.settings["autostart"] = bool(enabled)
            CFG.settings["start_minimized"] = bool(minimized)
            CFG.save_settings()
        Reg.set("StartMinimized", int(minimized), winreg.REG_DWORD)
        cmd = Reg._build_autostart_cmd(minimized)
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


def set_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("asukaa.langley.rpc")
    except Exception:
        pass


def find_icon():
    names = ["Asukaa.de.png", "asukaa.de.png", "Asukaa.png", "icon.png", "icon.ico"]
    dirs = [getattr(sys, "_MEIPASS", ""), BASE_DIR, os.path.dirname(os.path.abspath(sys.argv[0])), os.getcwd()]
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


def make_roblox_fallback_thumb(size=52, title=""):
    img = Image.new("RGBA", (size, size), "#1B1D1F")
    d = ImageDraw.Draw(img)
    d.rectangle([2, 2, size - 3, size - 3], outline="#E2231A", width=2)

    outer = [
        (int(size * 0.24), int(size * 0.12)),
        (int(size * 0.88), int(size * 0.24)),
        (int(size * 0.76), int(size * 0.88)),
        (int(size * 0.12), int(size * 0.76)),
    ]
    inner = [
        (int(size * 0.42), int(size * 0.39)),
        (int(size * 0.61), int(size * 0.42)),
        (int(size * 0.58), int(size * 0.61)),
        (int(size * 0.39), int(size * 0.58)),
    ]
    d.polygon(outer, fill="#32363B", outline="#DCD6C4")
    d.polygon(inner, fill="#1B1D1F")

    clean_t = str(title or "").replace(" with Lang!ley", "").strip()
    skip_words = {"roblox", "experience", "in", "app", "home", "the", "of", "and"}
    words = [
        w
        for w in re.split(r"[^A-Za-z0-9]+", clean_t)
        if w and w.lower() not in skip_words and not w.isdigit()
    ]
    if len(words) >= 3:
        initials = (words[0][0] + words[1][0] + words[2][0]).upper()
    elif len(words) == 2:
        initials = (words[0][0] + words[1][0]).upper()
    elif len(words) == 1 and len(words[0]) >= 2:
        initials = words[0][:3].upper()
    else:
        initials = "RBX"

    cx, cy = size // 2, size // 2
    pill_w = max(22, len(initials) * 7 + 8)
    pill_h = 15
    d.rectangle(
        [
            cx - pill_w // 2,
            cy - pill_h // 2,
            cx + pill_w // 2,
            cy + pill_h // 2,
        ],
        fill="#232527",
        outline="#E2231A",
        width=1,
    )
    tw = len(initials) * 6
    d.text((cx - tw // 2, cy - 5), initials, fill="#F0EAD8")

    border = Image.new("RGBA", (size + 4, size + 4), "#454138")
    border.paste(img, (2, 2), img)
    return border


def make_game_fallback_thumb(platform="idle", title="", size=52):
    plat_low = str(platform or "").lower()
    if plat_low == "roblox":
        return make_roblox_fallback_thumb(size=size, title=title)

    palette = {
        "fortnite": ("#1B2838", "#4FC3F7", "FN"),
        "minecraft": ("#2E4623", "#8BC34A", "MC"),
        "gacha": ("#28243D", "#E6D0A3", "★"),
        "riot": ("#361920", "#FF4655", "RG"),
        "ea": ("#1D2939", "#60A5FA", "EA"),
        "ubisoft": ("#1F2438", "#93C5FD", "UBI"),
        "gog": ("#2D1F38", "#D8B4FE", "GOG"),
        "battlenet": ("#172B42", "#38BDF8", "BNET"),
        "steam": ("#171A21", "#66C0F4", "STM"),
        "xbox": ("#103A10", "#4ADE80", "XBOX"),
        "custom_apps": ("#3A362E", "#F0EAD8", "APP"),
    }
    bg_col, acc_col, default_tag = palette.get(
        plat_low, ("#454138", "#E6D0A3", "GAME")
    )
    img = Image.new("RGBA", (size, size), bg_col)
    d = ImageDraw.Draw(img)
    d.rectangle([2, 2, size - 3, size - 3], outline=acc_col, width=2)

    words = [w for w in re.split(r"[^A-Za-z0-9]+", str(title or "").strip()) if w]
    if len(words) >= 2:
        tag = (words[0][0] + words[1][0]).upper()
    elif len(words) == 1 and len(words[0]) >= 2:
        tag = words[0][:3].upper()
    else:
        tag = default_tag

    cx, cy = size // 2, size // 2
    r = int(size * 0.30)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#232527", outline=acc_col, width=1)
    tw = len(tag) * 6
    d.text((cx - tw // 2, cy - 5), tag, fill="#F0EAD8")

    border = Image.new("RGBA", (size + 4, size + 4), "#454138")
    border.paste(img, (2, 2), img)
    return border


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
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums[:4])


def kill_old_procs():
    my_pid = os.getpid()
    script = os.path.basename(sys.argv[0]).lower()
    skip_tokens = ("installer", "setup", "unins", ".tmp", "_iu")
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == my_pid:
                continue
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            pname = (p.info.get("name") or "").lower()
            if any(tok in pname or tok in cmd for tok in skip_tokens):
                continue
            if (script in cmd and "python" in pname) or pname in ("lang!ley.exe", "langley.exe"):
                p.terminate()
        except Exception:
            pass
