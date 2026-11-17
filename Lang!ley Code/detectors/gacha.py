import os
import re
import glob
import time
import urllib.parse
import winreg
import threading
import psutil
import requests
from core.config_manager import (
    CFG,
    Reg,
    GACHA_SUB_GAME_DEFS,
    HTTP_HEADERS,
    GACHA_FALLBACK_LOGO,
    GACHA_IGNORE_PROCS,
    lookup_known_game_icon,
)

DEFAULT_GACHA_GAMES = [
    {
        "key": "genshin",
        "name": "Genshin Impact",
        "publisher": "HoYoverse",
        "level_prefix": "AR",
        "exes": ["genshinimpact.exe", "yuanshen.exe"],
        "path_tokens": ["genshin impact", "genshinimpact"],
        "state": "Exploring Teyvat",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/15/9e/b1/159eb1a7-fc58-2b43-b330-c5e619a77e2d/AppIcon-0-0-1x_U007epad-0-1-85-220.png/512x512bb.jpg",
    },
    {
        "key": "hsr",
        "name": "Honkai: Star Rail",
        "publisher": "HoYoverse",
        "level_prefix": "TL",
        "exes": ["starrail.exe"],
        "path_tokens": ["star rail", "starrail"],
        "state": "Trailblazing Across the Cosmos",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/b9/19/0a/b9190ac1-9dfc-6d88-5ac4-96dd4e6d6ff4/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
    {
        "key": "zzz",
        "name": "Zenless Zone Zero",
        "publisher": "HoYoverse",
        "level_prefix": "IK Lv.",
        "exes": ["zenlesszonezero.exe"],
        "path_tokens": ["zenlesszonezero", "zenless zone zero"],
        "state": "In New Eridu / Hollow Commission",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/c8/ee/27/c8ee2769-fe15-e1ea-aeb7-2247a535767a/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
    {
        "key": "hi3",
        "name": "Honkai Impact 3rd",
        "publisher": "HoYoverse",
        "level_prefix": "Captain Lv.",
        "exes": ["bh3.exe"],
        "path_tokens": ["honkai impact 3rd", "bh3"],
        "state": "On the Hyperion / Abyss Stage",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/20/4b/e7/204be75d-5108-d55b-eac2-3dac080e7f3e/AppIcon-1x_U007emarketing-0-10-0-85-220-0.png/512x512bb.jpg",
    },
    {
        "key": "wuwa",
        "name": "Wuthering Waves",
        "publisher": "Kuro Games",
        "level_prefix": "UL",
        "exes": ["wuthering waves.exe", "client-win64-shipping.exe"],
        "require_path_for_generic_exe": ["wuthering"],
        "path_tokens": ["wuthering waves", "wutheringwaves"],
        "state": "Exploring Solaris-3",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/3f/77/be/3f77be9b-5344-9483-efda-1c5932732b3a/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
    {
        "key": "nikke",
        "name": "Goddess of Victory: NIKKE",
        "publisher": "SHIFT UP",
        "level_prefix": "Commander Lv.",
        "exes": ["nikke.exe"],
        "path_tokens": ["nikke", "goddess of victory"],
        "state": "In Outpost / Surface Operation",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/f3/76/62/f376627d-7f96-b269-c635-34ddb704ec48/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
    {
        "key": "reverse1999",
        "name": "Reverse: 1999",
        "publisher": "Bluepoch",
        "level_prefix": "Timekeeper Lv.",
        "exes": ["reverse1999.exe"],
        "path_tokens": ["reverse1999", "reverse 1999"],
        "state": "In Timekeeper Suitcase / Story",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/30/30/2d/30302df1-5214-ba75-81a0-b9f4255f84ec/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
    {
        "key": "pgr",
        "name": "Punishing: Gray Raven",
        "publisher": "Kuro Games",
        "level_prefix": "Commandant Lv.",
        "exes": ["pgr.exe"],
        "path_tokens": ["punishing gray raven", "pgr_pc"],
        "state": "In Babylonia / Combat Sortie",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/f2/db/86/f2db8629-a697-d3a8-345c-16e1cc9c6f89/AppIcon-1x_U007emarketing-0-8-0-85-220-0.png/512x512bb.jpg",
    },
    {
        "key": "sololeveling",
        "name": "Solo Leveling:ARISE",
        "publisher": "Netmarble",
        "level_prefix": "Hunter Lv.",
        "exes": ["solo_leveling_arise.exe", "sololevelingarise.exe"],
        "path_tokens": ["solo_leveling_arise", "solo leveling"],
        "state": "In Dungeon Gate / Hunter Raid",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/75/28/93/752893bc-afc9-7797-8b45-160f9fd4f25c/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
    {
        "key": "infinitynikki",
        "name": "Infinity Nikki",
        "publisher": "Infold Games",
        "level_prefix": "Mira Lv.",
        "exes": ["infinitynikki.exe", "x6game-win64-shipping.exe"],
        "require_path_for_generic_exe": ["infinitynikki", "infinity nikki"],
        "path_tokens": ["infinity nikki", "infinitynikki"],
        "state": "Exploring Miraland",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/9f/db/73/9fdb7374-823a-a5e8-a9fd-2bd7cee2dd34/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
    {
        "key": "endfield",
        "name": "Arknights: Endfield",
        "publisher": "GRYPHLINE",
        "level_prefix": "Endministrator Lv.",
        "exes": ["endfield.exe", "arknightsendfield.exe"],
        "path_tokens": ["arknights endfield", "endfield"],
        "state": "Exploring Talos-II",
        "icon": "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/5e/a4/53/5ea453a8-f819-f42e-aae4-28f21b8c7166/AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/512x512bb.jpg",
    },
]

GENERIC_SHIPPING_EXES = {"client-win64-shipping.exe", "x6game-win64-shipping.exe"}

# Internal codename -> Clean Character Name map across Genshin, HSR, ZZZ, WuWa, HI3, etc.
CHARACTER_CODENAME_MAP = {
    "shougun": "Raiden Shogun",
    "raidenshogun": "Raiden Shogun",
    "furina": "Furina",
    "neuvillette": "Neuvillette",
    "arlecchino": "Arlecchino",
    "mavuika": "Mavuika",
    "citlali": "Citlali",
    "xilonen": "Xilonen",
    "chasca": "Chasca",
    "kinich": "Kinich",
    "mualani": "Mualani",
    "kachina": "Kachina",
    "ororon": "Ororon",
    "kazuha": "Kaedehara Kazuha",
    "ayaka": "Kamisato Ayaka",
    "ayato": "Kamisato Ayato",
    "hutao": "Hu Tao",
    "zhongli": "Zhongli",
    "nahida": "Nahida",
    "venti": "Venti",
    "yelan": "Yelan",
    "xingqiu": "Xingqiu",
    "bennett": "Bennett",
    "xiangling": "Xiangling",
    "navia": "Navia",
    "clorinde": "Clorinde",
    "wriothesley": "Wriothesley",
    "lyney": "Lyney",
    "lynette": "Lynette",
    "freminet": "Freminet",
    "xianyun": "Xianyun",
    "liuyun": "Xianyun",
    "chiori": "Chiori",
    "sigewinne": "Sigewinne",
    "emilie": "Emilie",
    "alhaitham": "Alhaitham",
    "wanderer": "Wanderer",
    "scaramouche": "Wanderer",
    "nilou": "Nilou",
    "cyno": "Cyno",
    "tighnari": "Tighnari",
    "yae": "Yae Miko",
    "kokomi": "Sangonomiya Kokomi",
    "yoimiya": "Yoimiya",
    "itto": "Arataki Itto",
    "shenhe": "Shenhe",
    "ganyu": "Ganyu",
    "xiao": "Xiao",
    "keqing": "Keqing",
    "tartaglia": "Tartaglia",
    "childe": "Tartaglia",
    "eula": "Eula",
    "klee": "Klee",
    "jean": "Jean",
    "diluc": "Diluc",
    "mona": "Mona",
    "playerboy": "Aether (Traveler)",
    "playergirl": "Lumine (Traveler)",
    "acheron": "Acheron",
    "firefly": "Firefly",
    "sam": "Firefly",
    "feixiao": "Feixiao",
    "sunday": "Sunday",
    "fugue": "Fugue",
    "theherta": "The Herta",
    "aglaea": "Aglaea",
    "castorice": "Castorice",
    "tribbie": "Tribbie",
    "mydei": "Mydei",
    "robin": "Robin",
    "aventurine": "Aventurine",
    "blackswan": "Black Swan",
    "sparkle": "Sparkle",
    "ruanmei": "Ruan Mei",
    "kafka": "Kafka",
    "silverwolf": "Silver Wolf",
    "blade": "Blade",
    "jingliu": "Jingliu",
    "danhengil": "Dan Heng • Imbibitor Lunae",
    "danheng": "Dan Heng",
    "march7th": "March 7th",
    "stelle": "Stelle (Trailblazer)",
    "caelus": "Caelus (Trailblazer)",
    "seele": "Seele",
    "bronya": "Bronya",
    "jingyuan": "Jing Yuan",
    "fuxuan": "Fu Xuan",
    "huohuo": "Huohuo",
    "topaz": "Topaz & Numby",
    "dr_ratio": "Dr. Ratio",
    "lingsha": "Lingsha",
    "rappa": "Rappa",
    "yunli": "Yunli",
    "jiaiaoqiu": "Jiaoqiu",
    "miyabi": "Hoshimi Miyabi",
    "astrayao": "Astra Yao",
    "evelyn": "Evelyn",
    "harumasa": "Asaba Harumasa",
    "yanagi": "Tsukishiro Yanagi",
    "lighter": "Lighter",
    "burnice": "Burnice",
    "caesar": "Caesar King",
    "janedoe": "Jane Doe",
    "qingyi": "Qingyi",
    "zhuyuan": "Zhu Yuan",
    "ellen": "Ellen Joe",
    "lycaon": "Von Lycaon",
    "grace": "Grace Howard",
    "rina": "Alexandrina",
    "koleda": "Koleda Belobog",
    "nekomata": "Nekomiya Mana",
    "soldier11": "Soldier 11",
    "anby": "Anby Demara",
    "nicole": "Nicole Demara",
    "billy": "Billy Kid",
    "belle": "Belle (Proxy)",
    "wise": "Wise (Proxy)",
    "jinhsi": "Jinhsi",
    "changli": "Changli",
    "shorekeeper": "The Shorekeeper",
    "camellya": "Camellya",
    "carlotta": "Carlotta",
    "roccia": "Roccia",
    "phoebe": "Phoebe",
    "brant": "Brant",
    "zani": "Zani",
    "jiyan": "Jiyan",
    "yinlin": "Yinlin",
    "zhezhi": "Zhezhi",
    "xiangliyao": "Xiangli Yao",
    "verina": "Verina",
    "encore": "Encore",
    "calcharo": "Calcharo",
    "sanhua": "Sanhua",
    "rover": "Rover",
    "kiana": "Kiana Kaslana",
    "mei": "Raiden Mei",
    "elysia": "Elysia",
    "senaladina": "Senadina",
    "vita": "Vita",
    "songque": "Songque",
    "thelema": "Thelema",
    "lantern": "Lantern",
}

GENSHIN_ENKA_AVATAR_MAP = {
    10000002: "Kamisato Ayaka",
    10000003: "Jean",
    10000005: "Aether (Traveler)",
    10000007: "Lumine (Traveler)",
    10000016: "Diluc",
    10000021: "Amber",
    10000022: "Venti",
    10000023: "Xiangling",
    10000025: "Xingqiu",
    10000026: "Xiao",
    10000029: "Klee",
    10000030: "Zhongli",
    10000032: "Bennett",
    10000033: "Tartaglia",
    10000037: "Ganyu",
    10000038: "Albedo",
    10000041: "Mona",
    10000042: "Keqing",
    10000046: "Hu Tao",
    10000047: "Kaedehara Kazuha",
    10000049: "Yoimiya",
    10000051: "Eula",
    10000052: "Raiden Shogun",
    10000054: "Sangonomiya Kokomi",
    10000057: "Arataki Itto",
    10000058: "Yae Miko",
    10000060: "Yelan",
    10000063: "Shenhe",
    10000066: "Kamisato Ayato",
    10000069: "Tighnari",
    10000070: "Nilou",
    10000071: "Cyno",
    10000073: "Nahida",
    10000075: "Wanderer",
    10000078: "Alhaitham",
    10000084: "Lyney",
    10000085: "Freminet",
    10000086: "Wriothesley",
    10000087: "Neuvillette",
    10000088: "Charlotte",
    10000089: "Furina",
    10000090: "Chevreuse",
    10000091: "Navia",
    10000093: "Xianyun",
    10000094: "Chiori",
    10000095: "Sigewinne",
    10000096: "Arlecchino",
    10000098: "Clorinde",
    10000099: "Emilie",
    10000100: "Kachina",
    10000101: "Kinich",
    10000102: "Mualani",
    10000103: "Xilonen",
    10000104: "Chasca",
    10000105: "Ororon",
    10000106: "Mavuika",
    10000107: "Citlali",
}


def normalize_region_name(raw, game_key=""):
    rc = str(raw or "").strip().lower()
    if not rc:
        return ""
    if rc in ("eu", "eur", "europe", "euro", "os_euro", "prod_official_eur", "prod_gf_eu", "combologin_eu", "europe (eu)"):
        return "Europe (EU)"
    if rc in ("na", "us", "usa", "america", "americas", "os_usa", "prod_official_usa", "prod_gf_us", "combologin_us", "combologin_na", "america (na)"):
        return "America (NA)"
    if rc in ("sea", "os_sea", "prod_sea"):
        return "SEA"
    if rc in ("asia", "jp", "kr", "os_asia", "prod_official_asia", "prod_gf_jp", "prod_gf_sg", "combologin_asia", "combologin_jp"):
        return "Asia"
    if rc in ("tw", "hk", "mo", "cht", "hmt", "tw/hk/mo", "os_cht", "prod_official_cht", "combologin_tw", "combologin_cht"):
        return "TW/HK/MO"
    if rc in ("cn", "prod_gf_cn", "cn_gf01", "cn_qd01", "combologin_cn"):
        return "CN (Celestia)" if game_key in ("genshin", "hsr") else "CN"
    if "eur" in rc or rc.endswith("_eu"):
        return "Europe (EU)"
    if "usa" in rc or rc.endswith("_us") or rc.endswith("_na"):
        return "America (NA)"
    if "sea" in rc:
        return "SEA"
    if "asia" in rc or rc.endswith("_jp"):
        return "Asia"
    if "cht" in rc or "hmt" in rc or rc.endswith("_tw"):
        return "TW/HK/MO"
    if rc.startswith("cn_") or rc.endswith("_cn"):
        return "CN"
    return str(raw).strip()


def infer_region_from_uid(uid_str, game_key=""):
    s = str(uid_str or "").strip()
    gk = str(game_key or "").strip().lower()
    if not s or not s.isdigit():
        return ""

    if gk == "zzz":
        if len(s) >= 10:
            if s.startswith("10"):
                return "America (NA)"
            if s.startswith("13"):
                return "Asia"
            if s.startswith("15"):
                return "Europe (EU)"
            if s.startswith("17"):
                return "TW/HK/MO"
            return ""
        if len(s) == 8:
            return "CN"
        return ""

    if gk == "wuwa":
        if len(s) == 9:
            first = s[0]
            if first == "5":
                return "America (NA)"
            if first == "6":
                return "Europe (EU)"
            if first == "7":
                return "Asia"
            if first == "8":
                return "TW/HK/MO"
            if first == "9":
                return "SEA"
            if first in ("1", "2", "3"):
                return "CN"
        return ""

    if gk == "hi3":
        if len(s) == 9:
            if s.startswith("10"):
                return "America (NA)"
            if s.startswith("20"):
                return "Europe (EU)"
        return ""

    if gk and gk not in ("genshin", "hsr"):
        return ""

    if len(s) < 9:
        return ""
    if s.startswith("18"):
        return "Asia"
    first = s[0]
    if first == "6":
        return "America (NA)"
    if first == "7":
        return "Europe (EU)"
    if first == "8":
        return "Asia"
    if first == "9":
        return "TW/HK/MO"
    if len(s) == 9:
        if first in ("1", "2", "3"):
            return "CN (Celestia)"
        if first == "5":
            return "CN (Irminsul)"
    return ""


class GachaClient:
    re_uid = re.compile(
        r'\b(?:game_uid|role_?id|RoleId|player_?id|PlayerId|LastUid|uid)["\'\s:=]+([1-9]\d{7,10})(?![a-fA-F0-9])',
        re.I,
    )
    re_uid_fallback = re.compile(
        r'\b(?:userId|user_id)["\'\s:=]+([1-9]\d{7,10})(?![a-fA-F0-9])',
        re.I,
    )
    re_region_code = re.compile(
        r"(?:\b(os_euro|os_usa|os_asia|os_cht|os_sea|prod_official_eur|prod_official_usa|prod_official_asia|prod_official_cht|prod_gf_eu|prod_gf_us|prod_gf_jp|prod_gf_sg|prod_gf_cn|cn_gf01|cn_qd01|comboLogin_eu|comboLogin_us|comboLogin_na|comboLogin_asia|comboLogin_jp|comboLogin_tw|comboLogin_cht|comboLogin_cn)\b|\b(?:region|server|ServerArea|ServerName|area)[\s:=,\"']+(Europe|America|Asia|SEA|Global|TW/HK/MO|EU|EUR|NA|USA|US|JP|TW|HK|MO|CHT|HMT|CN)\b)",
        re.I,
    )
    re_level = re.compile(
        r'(?:player_?level|adventure_?rank|AdventureRank|world_level_player|trailblaze_?level|TrailblazeLevel|union_?level|inter_?knot_?level|InterKnotLevel|captain_?level|PlayerLevel|UnionLevel|account_?level|AccountLevel|commander_?level|CommanderLevel|HunterLevel|hunter_?level|TimekeeperLevel|timekeeper_?level|mira_?level)["\'\s:=]+(\d{1,3})\b',
        re.I,
    )
    re_url_level = re.compile(
        r"(?:sdk\.hoyoverse\.com|hoyoverse\.com|hoyolab\.com)[^\s\"']*?[?&]level=(\d{1,3})\b",
        re.I,
    )
    re_name = re.compile(
        r'"(?:nickname|playerName|player_name|roleName|role_name|commanderName|hunterName|timekeeperName)"\s*:\s*"([^"\r\n\\]{2,28})"',
        re.I,
    )
    re_url_name = re.compile(
        r"(?:sdk\.hoyoverse\.com|hoyoverse\.com|hoyolab\.com)[^\s\"']*?[?&](?:nickname|role_?name)=([^&\s\"']+)",
        re.I,
    )
    re_avatar = re.compile(
        r"\b(?:Avatar_(?:Girl|Boy|Lady|Male|Loli)_(?:Sword|Pole|Claymore|Bow|Catalyst)_([A-Za-z0-9]+)|(?:Character|Avatar|Role|Resonator|Agent)_([A-Za-z]{3,18}))\b"
    )
    infer_region_from_uid = staticmethod(infer_region_from_uid)

    def __init__(self, state, on_ui, on_push):
        self.state = state
        self.on_ui = on_ui
        self.on_push = on_push
        self.scanned_once = False
        self.games_defs = CFG.games_db.get("gacha_games") or list(DEFAULT_GACHA_GAMES)
        self.http = requests.Session()
        self.http.headers.update(HTTP_HEADERS)
        self.uid_api_cache = {}
        self.last_log_parse_ts = 0.0

    def _sync_active_from_game_profile(self, game_key):
        prof = self.state.gacha_profiles.get(game_key) or {}
        if prof.get("unlinked"):
            self.state.gacha_uid = ""
            self.state.gacha_account_name = ""
            self.state.gacha_level = ""
            self.state.gacha_region = ""
            self.state.gacha_character = ""
            return
        self.state.gacha_uid = str(prof.get("uid") or "")
        self.state.gacha_account_name = str(prof.get("account_name") or "")
        self.state.gacha_level = str(prof.get("level") or "")
        self.state.gacha_region = str(prof.get("region") or "")
        self.state.gacha_character = str(prof.get("character") or "")

    def _save_game_profile(
        self,
        game_key,
        uid="",
        account_name="",
        level="",
        region="",
        character="",
        unlinked=False,
    ):
        if not game_key:
            game_key = self.state.gacha_game_key or "genshin"
        prof = self.state.gacha_profiles.setdefault(
            game_key,
            {
                "uid": "",
                "account_name": "",
                "level": "",
                "region": "",
                "character": "",
                "unlinked": False,
            },
        )
        prof["unlinked"] = bool(unlinked)
        if unlinked:
            prof["uid"] = ""
            prof["account_name"] = ""
            prof["level"] = ""
            prof["region"] = ""
            prof["character"] = ""
        else:
            if uid:
                prof["uid"] = str(uid).strip()
            if account_name:
                prof["account_name"] = str(account_name).strip()
            if level:
                prof["level"] = str(level).strip()
            uid_reg = infer_region_from_uid(prof.get("uid", ""), game_key) if prof.get("uid") else ""
            if region:
                prof["region"] = normalize_region_name(region, game_key) or str(region).strip()
            elif uid_reg:
                cur_reg = str(prof.get("region") or "").strip()
                if not cur_reg or (cur_reg in ("CN (Celestia)", "CN (Irminsul)") and uid_reg != cur_reg):
                    prof["region"] = uid_reg
            elif prof.get("region") in ("CN (Celestia)", "CN (Irminsul)") and game_key not in ("genshin", "hsr"):
                prof["region"] = ""
            if character:
                prof["character"] = str(character).strip()

        Reg.set("GachaProfiles", self.state.gacha_profiles)
        if not unlinked and (
            not self.state.gacha_game_key or self.state.gacha_game_key == game_key
        ):
            self._sync_active_from_game_profile(game_key)
            Reg.set("GachaUID", self.state.gacha_uid)
            Reg.set("GachaAccountName", self.state.gacha_account_name)
            Reg.set("GachaLevel", self.state.gacha_level)
            Reg.set("GachaRegion", self.state.gacha_region)
            Reg.set("GachaCharacter", self.state.gacha_character)

    def save_profile(
        self,
        uid="",
        level="",
        region="",
        character="",
        account_name="",
        game_key="",
    ):
        target_key = (game_key or self.state.gacha_game_key or "genshin").strip().lower()
        raw_input = str(uid or "").strip()
        raw_uid = ""

        # Allow composite input such as "712345678, 60, EU, Furina" or "712345678"
        if any(sep in raw_input for sep in (",", "|", "•")) and "http" not in raw_input.lower():
            tokens = [t.strip() for t in re.split(r"[,|•]+", raw_input) if t.strip()]
            for tok in tokens:
                m_u = re.search(r"\b([1-9]\d{7,9})\b", tok)
                if m_u and not raw_uid:
                    raw_uid = m_u.group(1)
                    continue
                m_lv = re.match(r"^(?:lv\.?|ar|tl|ik|ul)?\s*(\d{1,2})$", tok, re.I)
                if m_lv and not level:
                    level = m_lv.group(1)
                    continue
                if tok.upper() in ("EU", "EUROPE", "NA", "AMERICA", "ASIA", "TW", "HK", "MO", "TW/HK/MO", "CN", "GLOBAL") and not region:
                    region = tok
                    continue
                if not character and len(tok) >= 2 and not tok.isdigit():
                    character = tok
        elif "hoyolab.com" in raw_input.lower():
            m_hl = re.search(r"[?&]id=(\d{5,12})", raw_input)
            if m_hl:
                hl_id = m_hl.group(1)
                try:
                    r = self.http.get(
                        f"https://bbs-api-os.hoyolab.com/community/painter/wapi/user/full?uid={hl_id}",
                        timeout=3.5,
                    )
                    if r.status_code == 200:
                        uinfo = ((r.json() or {}).get("data") or {}).get("user_info") or {}
                        nick = str(uinfo.get("nickname") or "").strip()
                        if nick and not account_name:
                            account_name = nick
                except Exception:
                    pass
                if not account_name:
                    account_name = f"HoYoLAB #{hl_id}"
                raw_uid = hl_id
        else:
            m_digits = re.search(r"\b([1-9]\d{7,10})\b", raw_input)
            if m_digits:
                raw_uid = m_digits.group(1)
            elif raw_input and not account_name:
                account_name = raw_input

        inferred_reg = normalize_region_name(region, target_key) if region else (
            infer_region_from_uid(raw_uid, target_key) if raw_uid else ""
        )
        self._save_game_profile(
            target_key,
            uid=raw_uid,
            account_name=account_name,
            level=level,
            region=inferred_reg,
            character=character,
            unlinked=False,
        )
        # Also scan local logs & registry for this game to enrich level/character
        self._detect_telemetry_for_game(target_key, "")

        prof = self.state.gacha_profiles.get(target_key) or {}
        self.state.gacha_uid = prof.get("uid") or raw_uid or self.state.gacha_uid
        if prof.get("account_name") or account_name:
            self.state.gacha_account_name = str(prof.get("account_name") or account_name).strip()
        if prof.get("level") or level:
            self.state.gacha_level = str(prof.get("level") or level).strip()
        if prof.get("region") or inferred_reg:
            self.state.gacha_region = str(prof.get("region") or inferred_reg).strip()
        if prof.get("character") or character:
            self.state.gacha_character = str(prof.get("character") or character).strip()
        Reg.set("GachaUID", self.state.gacha_uid)
        Reg.set("GachaAccountName", self.state.gacha_account_name)
        Reg.set("GachaLevel", self.state.gacha_level)
        Reg.set("GachaRegion", self.state.gacha_region)
        Reg.set("GachaCharacter", self.state.gacha_character)

        if raw_uid and target_key in ("genshin", "hsr", "zzz"):
            threading.Thread(
                target=self._fetch_public_uid_showcase,
                args=(target_key, raw_uid),
                daemon=True,
            ).start()
        self.on_ui()
        self.on_push()
        return bool(raw_uid or account_name or prof.get("uid") or prof.get("account_name"))

    def detect_game_account(self, game_key, from_browser_callback=False):
        gkey = (game_key or "genshin").strip().lower()
        prof = self.state.gacha_profiles.setdefault(
            gkey,
            {
                "uid": "",
                "account_name": "",
                "level": "",
                "region": "",
                "character": "",
                "unlinked": False,
            },
        )
        prof["unlinked"] = False
        self._detect_telemetry_for_game(gkey, "")
        prof = self.state.gacha_profiles.get(gkey) or {}
        has_data = bool(prof.get("uid") or prof.get("account_name"))
        self.on_ui()
        self.on_push()
        return has_data

    def detect_local_account(self, game_key=""):
        if game_key:
            return self.detect_game_account(game_key, from_browser_callback=False)
        self.state.gacha_manual_override = False
        Reg.set("GachaManualOverride", 0, winreg.REG_DWORD)
        any_found = False
        for g in GACHA_SUB_GAME_DEFS:
            gk = g["key"]
            if self.detect_game_account(gk, from_browser_callback=False):
                any_found = True
        self.on_ui()
        self.on_push()
        return any_found

    def reset_profile(self, game_key=""):
        return self.detect_local_account(game_key=game_key)

    def unlink_game(self, game_key):
        gkey = (game_key or "").strip().lower()
        if not gkey:
            return self.unlink()
        self._save_game_profile(gkey, unlinked=True)
        if self.state.gacha_game_key == gkey:
            self.state.gacha_uid = ""
            self.state.gacha_account_name = ""
            self.state.gacha_level = ""
            self.state.gacha_region = ""
            self.state.gacha_character = ""
        self.on_ui()
        self.on_push()
        return True

    def unlink(self):
        self.state.gacha_manual_override = True
        self.state.gacha_uid = ""
        self.state.gacha_account_name = ""
        self.state.gacha_level = ""
        self.state.gacha_region = ""
        self.state.gacha_character = ""
        for g in GACHA_SUB_GAME_DEFS:
            self._save_game_profile(g["key"], unlinked=True)
        Reg.set("GachaManualOverride", 1, winreg.REG_DWORD)
        Reg.remove("GachaUID")
        Reg.remove("GachaAccountName")
        Reg.remove("GachaLevel")
        Reg.remove("GachaRegion")
        Reg.remove("GachaCharacter")
        self.on_ui()
        self.on_push()
        return True

    def _detect_uid_from_registry(self, game_key):
        reg_paths = {
            "genshin": [r"Software\miHoYo\Genshin Impact", r"Software\Cognosphere\Genshin Impact"],
            "hsr": [r"Software\Cognosphere\Star Rail", r"Software\miHoYo\Star Rail"],
            "zzz": [r"Software\Cognosphere\ZenlessZoneZero", r"Software\miHoYo\ZenlessZoneZero"],
            "hi3": [r"Software\miHoYo\Honkai Impact 3rd", r"Software\Cognosphere\Honkai Impact 3rd"],
            "wuwa": [r"Software\Kuro Games\Wuthering Waves"],
            "nikke": [r"Software\LevelInfinite\NIKKE", r"Software\SHIFT UP\NIKKE"],
            "reverse1999": [r"Software\Bluepoch\Reverse: 1999"],
            "pgr": [r"Software\Kuro Games\Punishing Gray Raven"],
            "sololeveling": [r"Software\Netmarble\Solo_Leveling_ARISE"],
            "infinitynikki": [r"Software\InfoldGames\Infinity Nikki"],
            "endfield": [r"Software\GRYPHLINE\Arknights Endfield"],
        }.get(game_key, [])

        for rpath in reg_paths:
            vals = Reg.read_key_dict(winreg.HKEY_CURRENT_USER, 0, rpath)
            for k, v in vals.items():
                k_low = k.lower()
                if "lastuserid" in k_low or "uid" in k_low or "userid" in k_low:
                    s_val = str(v or "").strip()
                    if s_val.isdigit() and 7 <= len(s_val) <= 11 and s_val[0] != "0":
                        return s_val
                if isinstance(v, (bytes, bytearray)):
                    try:
                        decoded = v.decode("utf-8", errors="ignore").rstrip("\x00")
                        m_u = self.re_uid.search(decoded)
                        if m_u:
                            return m_u.group(1)
                    except Exception:
                        pass
        return ""

    def _candidate_log_paths(self, game_key, exe_path=""):
        user_prof = os.path.expanduser("~")
        locallow = os.path.join(user_prof, "AppData", "LocalLow")
        local = os.environ.get("LOCALAPPDATA", os.path.join(user_prof, "AppData", "Local"))
        paths = []
        if game_key == "genshin":
            paths.extend(
                [
                    os.path.join(locallow, "miHoYo", "Genshin Impact", "Player.log"),
                    os.path.join(locallow, "miHoYo", "Genshin Impact", "output_log.txt"),
                    os.path.join(locallow, "Cognosphere", "Genshin Impact", "Player.log"),
                    os.path.join(locallow, "Cognosphere", "Genshin Impact", "output_log.txt"),
                    os.path.join(locallow, "miHoYo", "原神", "output_log.txt"),
                ]
            )
        elif game_key == "hsr":
            paths.extend(
                [
                    os.path.join(locallow, "Cognosphere", "Star Rail", "Player.log"),
                    os.path.join(locallow, "Cognosphere", "Star Rail", "Player-prev.log"),
                    os.path.join(locallow, "miHoYo", "Star Rail", "Player.log"),
                ]
            )
        elif game_key == "zzz":
            paths.extend(
                [
                    os.path.join(locallow, "miHoYo", "ZenlessZoneZero", "Player.log"),
                    os.path.join(locallow, "miHoYo", "ZenlessZoneZero", "Player-prev.log"),
                    os.path.join(locallow, "miHoYo", "ZenlessZoneZero", "output_log.txt"),
                    os.path.join(locallow, "Cognosphere", "ZenlessZoneZero", "Player.log"),
                    os.path.join(locallow, "Cognosphere", "ZenlessZoneZero", "Player-prev.log"),
                ]
            )
        elif game_key == "hi3":
            paths.extend(
                [
                    os.path.join(locallow, "miHoYo", "Honkai Impact 3rd", "Player.log"),
                    os.path.join(locallow, "miHoYo", "Honkai Impact 3rd", "output_log.txt"),
                    os.path.join(locallow, "Cognosphere", "Honkai Impact 3rd", "Player.log"),
                ]
            )
        elif game_key == "wuwa":
            if exe_path:
                client_dir = os.path.dirname(os.path.dirname(os.path.dirname(exe_path)))
                paths.append(os.path.join(client_dir, "Saved", "Logs", "Client.log"))
            paths.append(os.path.join(local, "Wuthering Waves", "Saved", "Logs", "Client.log"))
        elif game_key == "nikke":
            paths.extend(
                [
                    os.path.join(locallow, "Unity", "com_proximabeta_NIKKE", "output_log.txt"),
                    os.path.join(locallow, "com_proximabeta", "NIKKE", "Player.log"),
                    os.path.join(locallow, "SHIFT UP", "NIKKE", "Player.log"),
                ]
            )
        elif game_key == "reverse1999":
            paths.extend(
                [
                    os.path.join(locallow, "Bluepoch", "Reverse1999", "Player.log"),
                    os.path.join(locallow, "Bluepoch", "Reverse 1999", "Player.log"),
                ]
            )
        elif game_key == "pgr":
            paths.extend(
                [
                    os.path.join(locallow, "Kuro Game", "Punishing Gray Raven", "Player.log"),
                    os.path.join(locallow, "Kuro Games", "Punishing Gray Raven", "Player.log"),
                ]
            )
        elif game_key == "sololeveling":
            paths.extend(
                [
                    os.path.join(locallow, "Netmarble", "Solo_Leveling_ARISE", "Player.log"),
                    os.path.join(locallow, "Netmarble", "SoloLevelingARISE", "Player.log"),
                ]
            )
        elif game_key == "infinitynikki":
            if exe_path:
                x6_dir = os.path.dirname(os.path.dirname(os.path.dirname(exe_path)))
                paths.append(os.path.join(x6_dir, "Saved", "Logs", "X6Game.log"))
            paths.append(os.path.join(local, "X6Game", "Saved", "Logs", "X6Game.log"))
        elif game_key == "endfield":
            paths.extend(
                [
                    os.path.join(locallow, "GRYPHLINE", "Endfield", "Player.log"),
                    os.path.join(locallow, "Hypergryph", "Endfield", "Player.log"),
                ]
            )
        return [p for p in paths if p and os.path.exists(p)]

    @staticmethod
    def _clean_player_name(raw):
        cand = urllib.parse.unquote_plus(str(raw or "")).strip()
        if not cand or len(cand) < 2 or len(cand) > 28:
            return ""
        low = cand.lower()
        if low in ("null", "none", "undefined", "unknown", "default", "player", "guest", "test", "admin", "traveler", "trailblazer", "proxy", "rover"):
            return ""
        if "@" in cand or "://" in cand or "=" in cand:
            return ""
        if len(cand) >= 16 and re.fullmatch(r"[0-9a-fA-F]+", cand):
            return ""
        return cand

    def _parse_log_content(self, chunk, game_key=""):
        res = {"uid": "", "account_name": "", "region": "", "level": 0, "character": ""}
        if not chunk:
            return res

        for m_u in self.re_uid.finditer(chunk):
            res["uid"] = m_u.group(1)
        if not res["uid"] and game_key not in ("genshin", "hsr", "zzz", "hi3"):
            for m_u in self.re_uid_fallback.finditer(chunk):
                res["uid"] = m_u.group(1)

        for m_n in self.re_name.finditer(chunk):
            clean_n = self._clean_player_name(m_n.group(1))
            if clean_n:
                res["account_name"] = clean_n
        for m_un in self.re_url_name.finditer(chunk):
            clean_n = self._clean_player_name(m_un.group(1))
            if clean_n:
                res["account_name"] = clean_n

        for m_r in self.re_region_code.finditer(chunk):
            raw_r = m_r.group(1) or m_r.group(2) or ""
            norm_r = normalize_region_name(raw_r, game_key)
            if norm_r and norm_r.lower() != "global":
                res["region"] = norm_r

        if not res["region"] and res["uid"]:
            res["region"] = infer_region_from_uid(res["uid"], game_key)

        for m_l in self.re_level.finditer(chunk):
            lv = int(m_l.group(1))
            if 1 <= lv <= 999:
                res["level"] = lv

        for m_ul in self.re_url_level.finditer(chunk):
            lv = int(m_ul.group(1))
            if 1 <= lv <= 999:
                res["level"] = lv

        for m_c in self.re_avatar.finditer(chunk):
            raw_c = (m_c.group(1) or m_c.group(2) or "").strip()
            c_low = raw_c.lower()
            if c_low in ("base", "npc", "monster", "prop", "weapon", "camera", "common", "default", "dummy", "effect"):
                continue
            if c_low in CHARACTER_CODENAME_MAP:
                res["character"] = CHARACTER_CODENAME_MAP[c_low]
            elif len(raw_c) >= 3:
                res["character"] = raw_c.capitalize()
        return res

    def _detect_telemetry_for_game(self, game_key, exe_path=""):
        prof = self.state.gacha_profiles.get(game_key) or {}
        if prof.get("unlinked"):
            return

        found_uid = ""
        found_acc = ""
        found_region = ""
        found_level = ""
        found_char = ""

        reg_uid = self._detect_uid_from_registry(game_key)
        if reg_uid:
            found_uid = reg_uid

        for lpath in self._candidate_log_paths(game_key, exe_path):
            try:
                sz = os.path.getsize(lpath)
                with open(lpath, "r", encoding="utf-8", errors="ignore") as f:
                    if sz > 600_000:
                        f.seek(sz - 600_000)
                        f.readline()
                    chunk = f.read()

                parsed = self._parse_log_content(chunk, game_key=game_key)
                if parsed["uid"] and not found_uid:
                    found_uid = parsed["uid"]
                if parsed.get("account_name"):
                    found_acc = parsed["account_name"]
                if parsed["region"]:
                    found_region = parsed["region"]
                if parsed["level"]:
                    found_level = str(parsed["level"])
                if parsed["character"]:
                    found_char = parsed["character"]
            except Exception:
                pass

        effective_uid = found_uid or prof.get("uid") or ""
        if not found_region and effective_uid:
            found_region = infer_region_from_uid(effective_uid, game_key)

        # Only save telemetry if a valid UID (or existing linked UID/account) exists for this specific game
        has_valid_identity = bool(found_uid or found_acc or prof.get("uid") or prof.get("account_name"))
        if has_valid_identity and (found_uid or found_acc or found_region or found_level or found_char):
            self._save_game_profile(
                game_key,
                uid=found_uid,
                account_name=found_acc,
                level=found_level,
                region=found_region,
                character=found_char,
                unlinked=False,
            )

        uid_to_query = (self.state.gacha_profiles.get(game_key) or {}).get("uid") or found_uid
        if uid_to_query and game_key in ("genshin", "hsr", "zzz"):
            threading.Thread(
                target=self._fetch_public_uid_showcase,
                args=(game_key, uid_to_query),
                daemon=True,
            ).start()

    def _fetch_public_uid_showcase(self, game_key, uid):
        uid = str(uid or "").strip()
        if not uid.isdigit() or len(uid) < 8:
            return
        cache_key = f"{game_key}:{uid}"
        now = time.time()
        prof_cur = self.state.gacha_profiles.get(game_key) or {}
        cache_ttl = 300 if (prof_cur.get("level") and prof_cur.get("account_name")) else 45
        if cache_key in self.uid_api_cache and (now - self.uid_api_cache[cache_key][0]) < cache_ttl:
            return
        self.uid_api_cache[cache_key] = (now, True)

        try:
            if game_key == "hsr":
                r = self.http.get(f"https://api.mihomo.me/sr_info_parsed/{uid}?lang=en", timeout=3.5)
                if r.status_code == 200:
                    data = r.json() or {}
                    player = data.get("player") or {}
                    nick = str(player.get("nickname") or "").strip()
                    lvl = str(player.get("level") or "").strip()
                    chars = data.get("characters") or []
                    cname = str(chars[0].get("name") or "").strip() if (chars and isinstance(chars[0], dict)) else ""
                    self._save_game_profile(
                        "hsr",
                        uid=uid,
                        account_name=nick,
                        level=lvl,
                        region=infer_region_from_uid(uid, "hsr"),
                        character=cname,
                        unlinked=False,
                    )
                    self.on_ui()
                    self.on_push()
                    return

            if game_key == "zzz":
                r = self.http.get(f"https://enka.network/api/zzz/uid/{uid}", timeout=4.0)
                if r.status_code == 200:
                    data = r.json() or {}
                    pinfo = data.get("PlayerInfo") or {}
                    soc = pinfo.get("SocialDetail") or {}
                    pdet = soc.get("ProfileDetail") or {}
                    nick = str(pdet.get("Nickname") or soc.get("Nickname") or "").strip()
                    lvl = str(pdet.get("Level") or soc.get("Level") or "").strip()
                    api_reg = normalize_region_name(data.get("region"), "zzz") or infer_region_from_uid(uid, "zzz")
                    self._save_game_profile(
                        "zzz",
                        uid=uid,
                        account_name=nick,
                        level=lvl,
                        region=api_reg,
                        unlinked=False,
                    )
                    self.on_ui()
                    self.on_push()
                return

            if game_key != "genshin":
                return

            r = self.http.get(f"https://enka.network/api/uid/{uid}?info", timeout=3.5)
            if r.status_code == 200:
                data = r.json() or {}
                pinfo = data.get("playerInfo") or {}
                nick = str(pinfo.get("nickname") or "").strip()
                lvl = str(pinfo.get("level") or "").strip()
                avatars = pinfo.get("showAvatarInfoList") or []
                cname = ""
                if avatars and isinstance(avatars[0], dict):
                    aid = int(avatars[0].get("avatarId") or 0)
                    cname = GENSHIN_ENKA_AVATAR_MAP.get(aid, "")
                self._save_game_profile(
                    game_key,
                    uid=uid,
                    account_name=nick,
                    level=lvl,
                    region=infer_region_from_uid(uid, game_key),
                    character=cname,
                    unlinked=False,
                )
                self.on_ui()
                self.on_push()
        except Exception:
            pass

    def scan_installed_games(self):
        self.scanned_once = True
        games = []
        seen = set()

        def add_game(title, install_dir, publisher="HoYoPlay / Gacha"):
            title = (title or "").strip()
            install_dir = (install_dir or "").strip()
            if not title or not install_dir or not os.path.exists(install_dir):
                return
            k = title.lower()
            if k in seen:
                return
            seen.add(k)
            games.append(
                {
                    "name": title,
                    "publisher": publisher,
                    "install_dir": os.path.normpath(install_dir),
                    "norm_dir": os.path.normcase(os.path.normpath(install_dir)),
                }
            )

        for reg_path in (
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ):
            for root, flag, sub_path, _ in Reg.list_subkeys(reg_path):
                vals = Reg.read_key_dict(root, flag, sub_path)
                dname = str(vals.get("DisplayName") or "").strip()
                iloc = str(vals.get("InstallLocation") or "").strip()
                if not dname or not iloc:
                    continue
                d_low = dname.lower()
                for gdef in self.games_defs:
                    if gdef["name"].lower() in d_low or any(tok in d_low for tok in gdef.get("path_tokens", [])):
                        add_game(gdef["name"], iloc, gdef.get("publisher", "HoYoPlay / Gacha"))
                        break

        for drive in ("C:", "D:", "E:", "F:"):
            for rel in (
                "Program Files\\HoYoPlay\\games",
                "HoYoPlay\\games",
                "Games\\HoYoPlay\\games",
                "Program Files\\Genshin Impact",
                "Genshin Impact",
                "Program Files\\Star Rail",
                "Star Rail",
                "Program Files\\ZenlessZoneZero",
                "ZenlessZoneZero",
                "Program Files\\Honkai Impact 3rd",
                "Wuthering Waves",
                "Program Files\\Wuthering Waves",
                "NIKKE",
                "Reverse1999",
                "Punishing Gray Raven",
                "Netmarble\\Solo_Leveling_ARISE",
                "Infinity Nikki",
                "Program Files\\Infinity Nikki",
                "Arknights Endfield",
            ):
                base = os.path.join(drive + "\\", rel)
                if not os.path.exists(base):
                    continue
                base_low = base.lower()
                matched_direct = False
                for gdef in self.games_defs:
                    if any(tok in base_low for tok in gdef.get("path_tokens", [])):
                        add_game(gdef["name"], base, gdef.get("publisher", "HoYoPlay / Gacha"))
                        matched_direct = True
                        break
                if not matched_direct:
                    try:
                        for sub in os.listdir(base):
                            full = os.path.join(base, sub)
                            if not os.path.isdir(full):
                                continue
                            s_low = sub.lower()
                            for gdef in self.games_defs:
                                if any(tok in s_low for tok in gdef.get("path_tokens", [])):
                                    add_game(gdef["name"], full, gdef.get("publisher", "HoYoPlay / Gacha"))
                                    break
                    except OSError:
                        pass

        games.sort(key=lambda x: x["name"].lower())
        self.state.gacha_installed_games = games
        return games

    def poll(self, snapshot=None):
        if not self.scanned_once:
            self.scan_installed_games()

        if not self.state.gacha_enabled:
            if self.state.gacha_running:
                self.state.gacha_running = False
                self.state.gacha_game_key = ""
                self.state.gacha_game_name = ""
                self.state.gacha_game_state = ""
                return True
            return False

        if snapshot is not None:
            procs, _, _, _ = snapshot
        else:
            procs = []
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

        detected_key = ""
        detected_name = ""
        detected_state = ""
        detected_prefix = "Lv."
        detected_icon = GACHA_FALLBACK_LOGO
        detected_exe = ""
        detected_pid = 0

        for p in procs:
            pname = p["name"]
            exe_low = p["exe_lower"]
            if not pname or pname in GACHA_IGNORE_PROCS:
                continue
            if snapshot is not None and not p.get("has_visible_window", False):
                continue

            for gdef in self.games_defs:
                gkey_candidate = gdef.get("key") or "gacha"
                if not self.state.is_gacha_game_enabled(gkey_candidate):
                    continue
                exes = [e.lower() for e in gdef.get("exes", [])]
                if pname not in exes:
                    continue
                if pname in GENERIC_SHIPPING_EXES:
                    req_tokens = [t.lower() for t in gdef.get("require_path_for_generic_exe", [])]
                    if req_tokens and not any(tok in exe_low for tok in req_tokens):
                        continue
                detected_key = gkey_candidate
                detected_name = gdef["name"]
                detected_state = gdef.get("state") or "Active Session"
                detected_prefix = gdef.get("level_prefix") or "Lv."
                detected_icon = (
                    lookup_known_game_icon(detected_name)
                    or gdef.get("icon")
                    or GACHA_FALLBACK_LOGO
                )
                detected_exe = p.get("exe") or exe_low
                detected_pid = int(p.get("pid") or 0)
                break
            if detected_name:
                break

        if not detected_name:
            if self.state.gacha_running:
                self.state.gacha_running = False
                self.state.gacha_game_key = ""
                self.state.gacha_game_name = ""
                self.state.gacha_game_state = ""
                self.state.gacha_game_icon = GACHA_FALLBACK_LOGO
                return True
            return False

        now = time.time()
        is_new_session = (
            not self.state.gacha_running or self.state.gacha_game_name != detected_name
        )
        prev_summary = self.state.gacha_summary_str()
        prev_level = str(self.state.gacha_level or "")
        prev_acc = str(self.state.gacha_account_name or "")
        self.state.gacha_game_key = detected_key
        self.state.gacha_level_prefix = detected_prefix
        if detected_pid > 0:
            self.state.active_game_pid = detected_pid

        if is_new_session or (now - self.last_log_parse_ts >= 15.0):
            self.last_log_parse_ts = now
            self._detect_telemetry_for_game(detected_key, detected_exe)
        self._sync_active_from_game_profile(detected_key)

        changed = (
            is_new_session
            or self.state.gacha_game_state != detected_state
            or self.state.gacha_game_icon != detected_icon
            or str(self.state.gacha_level or "") != prev_level
            or str(self.state.gacha_account_name or "") != prev_acc
            or self.state.gacha_summary_str() != prev_summary
        )
        if is_new_session:
            self.state.gacha_start_ts = int(now)
        self.state.gacha_running = True
        self.state.gacha_game_name = detected_name
        self.state.gacha_game_state = detected_state
        self.state.gacha_game_icon = detected_icon
        return changed
