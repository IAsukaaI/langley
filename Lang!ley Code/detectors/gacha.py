import os
import re
import glob
import time
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
        "icon": "https://fastcdn.hoyoverse.com/static-resource-v2/2024/04/12/b7002217a91f18d87e22d0b419b04f29_7455586655940982297.png",
    },
    {
        "key": "hsr",
        "name": "Honkai: Star Rail",
        "publisher": "HoYoverse",
        "level_prefix": "TL",
        "exes": ["starrail.exe"],
        "path_tokens": ["star rail", "starrail"],
        "state": "Trailblazing Across the Cosmos",
        "icon": "https://fastcdn.hoyoverse.com/static-resource-v2/2024/04/12/74330de127c739f65c592029621a098f_3734580422352353708.png",
    },
    {
        "key": "zzz",
        "name": "Zenless Zone Zero",
        "publisher": "HoYoverse",
        "level_prefix": "IK Lv.",
        "exes": ["zenlesszonezero.exe"],
        "path_tokens": ["zenlesszonezero", "zenless zone zero"],
        "state": "In New Eridu / Hollow Commission",
        "icon": "https://fastcdn.hoyoverse.com/static-resource-v2/2024/07/02/cad8f1e6aa90e3ce1ce15e6d95eb18a1_4389824919339970805.png",
    },
    {
        "key": "hi3",
        "name": "Honkai Impact 3rd",
        "publisher": "HoYoverse",
        "level_prefix": "Captain Lv.",
        "exes": ["bh3.exe"],
        "path_tokens": ["honkai impact 3rd", "bh3"],
        "state": "On the Hyperion / Abyss Stage",
        "icon": "https://fastcdn.hoyoverse.com/static-resource-v2/2024/02/29/3d7657b9a8fb1d4c3e8bf2bc2f64f141_6359632807177131637.png",
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
        "icon": "https://cdn.cloudflare.steamstatic.com/steam/apps/3513350/header.jpg",
    },
    {
        "key": "nikke",
        "name": "Goddess of Victory: NIKKE",
        "publisher": "SHIFT UP",
        "level_prefix": "Commander Lv.",
        "exes": ["nikke.exe"],
        "path_tokens": ["nikke", "goddess of victory"],
        "state": "In Outpost / Surface Operation",
        "icon": "https://cdn.cloudflare.steamstatic.com/steam/apps/2161500/header.jpg",
    },
    {
        "key": "reverse1999",
        "name": "Reverse: 1999",
        "publisher": "Bluepoch",
        "level_prefix": "Timekeeper Lv.",
        "exes": ["reverse1999.exe"],
        "path_tokens": ["reverse1999", "reverse 1999"],
        "state": "In Timekeeper Suitcase / Story",
        "icon": "https://cdn.cloudflare.steamstatic.com/steam/apps/3092660/header.jpg",
    },
    {
        "key": "pgr",
        "name": "Punishing: Gray Raven",
        "publisher": "Kuro Games",
        "level_prefix": "Commandant Lv.",
        "exes": ["pgr.exe"],
        "path_tokens": ["punishing gray raven", "pgr_pc"],
        "state": "In Babylonia / Combat Sortie",
        "icon": "https://cdn.cloudflare.steamstatic.com/steam/apps/2161500/header.jpg",
    },
    {
        "key": "sololeveling",
        "name": "Solo Leveling:ARISE",
        "publisher": "Netmarble",
        "level_prefix": "Hunter Lv.",
        "exes": ["solo_leveling_arise.exe", "sololevelingarise.exe"],
        "path_tokens": ["solo_leveling_arise", "solo leveling"],
        "state": "In Dungeon Gate / Hunter Raid",
        "icon": "https://cdn.cloudflare.steamstatic.com/steam/apps/2373990/header.jpg",
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
        "icon": "https://cdn.cloudflare.steamstatic.com/steam/apps/3164330/header.jpg",
    },
    {
        "key": "endfield",
        "name": "Arknights: Endfield",
        "publisher": "GRYPHLINE",
        "level_prefix": "Endministrator Lv.",
        "exes": ["endfield.exe", "arknightsendfield.exe"],
        "path_tokens": ["arknights endfield", "endfield"],
        "state": "Exploring Talos-II",
        "icon": "https://fastcdn.hoyoverse.com/static-resource-v2/2024/07/02/cad8f1e6aa90e3ce1ce15e6d95eb18a1_4389824919339970805.png",
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


def infer_region_from_uid(uid_str):
    s = str(uid_str or "").strip()
    if not s or not s.isdigit() or len(s) < 9:
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
    if first in ("1", "2", "3"):
        return "CN (Celestia)"
    if first == "5":
        return "CN (Irminsul)"
    return ""


class GachaClient:
    re_uid = re.compile(
        r'(?:uid|userId|account_id|player_id|open_id|roleId|RoleId)["\'\s:=]+([1-9]\d{8,9})\b',
        re.I,
    )
    re_region_code = re.compile(
        r"\b(os_euro|os_usa|os_asia|os_cht|prod_official_eur|prod_official_usa|prod_official_asia|prod_official_cht|prod_gf_cn|cn_gf01|cn_qd01)\b",
        re.I,
    )
    re_level = re.compile(
        r'(?:player_level|adventure_rank|AdventureRank|world_level_player|trailblaze_level|TrailblazeLevel|union_level|inter_knot_level|InterKnotLevel|PlayerLevel|UnionLevel|account_level|AccountLevel|commander_level|CommanderLevel|HunterLevel|TimekeeperLevel)["\'\s:=]+(\d{1,2})\b',
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
            return
        if prof.get("uid"):
            self.state.gacha_uid = str(prof["uid"])
        if prof.get("account_name"):
            self.state.gacha_account_name = str(prof["account_name"])
        if prof.get("level"):
            self.state.gacha_level = str(prof["level"])
        if prof.get("region"):
            self.state.gacha_region = str(prof["region"])
        if prof.get("character"):
            self.state.gacha_character = str(prof["character"])

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
            if region:
                prof["region"] = str(region).strip()
            elif prof.get("uid") and not prof.get("region"):
                prof["region"] = infer_region_from_uid(prof["uid"])
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

        inferred_reg = str(region or "").strip() or (
            infer_region_from_uid(raw_uid) if raw_uid else ""
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
                    os.path.join(locallow, "miHoYo", "Genshin Impact", "output_log.txt"),
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
                    os.path.join(locallow, "Cognosphere", "ZenlessZoneZero", "Player.log"),
                ]
            )
        elif game_key == "hi3":
            paths.extend(
                [
                    os.path.join(locallow, "miHoYo", "Honkai Impact 3rd", "output_log.txt"),
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

    def _parse_log_content(self, chunk):
        res = {"uid": "", "region": "", "level": 0, "character": ""}
        if not chunk:
            return res

        m_u = self.re_uid.search(chunk)
        if m_u:
            res["uid"] = m_u.group(1)
            res["region"] = infer_region_from_uid(res["uid"])

        m_r = self.re_region_code.search(chunk)
        if m_r:
            rc = m_r.group(1).lower()
            if "eur" in rc:
                res["region"] = "Europe (EU)"
            elif "usa" in rc:
                res["region"] = "America (NA)"
            elif "asia" in rc:
                res["region"] = "Asia"
            elif "cht" in rc:
                res["region"] = "TW/HK/MO"
            elif "cn" in rc:
                res["region"] = "CN"

        for m_l in self.re_level.finditer(chunk):
            lv = int(m_l.group(1))
            if 1 <= lv <= 90:
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
        found_region = ""
        found_level = ""
        found_char = ""

        reg_uid = self._detect_uid_from_registry(game_key)
        if reg_uid:
            found_uid = reg_uid
            found_region = infer_region_from_uid(reg_uid)

        for lpath in self._candidate_log_paths(game_key, exe_path):
            try:
                sz = os.path.getsize(lpath)
                with open(lpath, "r", encoding="utf-8", errors="ignore") as f:
                    if sz > 600_000:
                        f.seek(sz - 600_000)
                        f.readline()
                    chunk = f.read()

                parsed = self._parse_log_content(chunk)
                if not found_uid and parsed["uid"]:
                    found_uid = parsed["uid"]
                if not found_region and parsed["region"]:
                    found_region = parsed["region"]
                if parsed["level"]:
                    found_level = str(parsed["level"])
                if parsed["character"]:
                    found_char = parsed["character"]
            except Exception:
                pass

        # Only save telemetry if a valid UID (or existing linked UID/account) exists for this specific game
        has_valid_identity = bool(found_uid or prof.get("uid") or prof.get("account_name"))
        if has_valid_identity and (found_uid or found_region or found_level or found_char):
            self._save_game_profile(
                game_key,
                uid=found_uid,
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
        if not uid.isdigit() or len(uid) < 9:
            return
        cache_key = f"{game_key}:{uid}"
        now = time.time()
        if cache_key in self.uid_api_cache and (now - self.uid_api_cache[cache_key][0]) < 300:
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
                        region=infer_region_from_uid(uid),
                        character=cname,
                        unlinked=False,
                    )
                    self.on_ui()
                    self.on_push()
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
                    region=infer_region_from_uid(uid),
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
        self.state.gacha_game_key = detected_key
        self.state.gacha_level_prefix = detected_prefix
        if detected_pid > 0:
            self.state.active_game_pid = detected_pid

        if is_new_session or (now - self.last_log_parse_ts >= 15.0):
            self.last_log_parse_ts = now
            self._detect_telemetry_for_game(detected_key, detected_exe)
        self._sync_active_from_game_profile(detected_key)

        prev_summary = self.state.gacha_summary_str()
        changed = (
            is_new_session
            or self.state.gacha_game_state != detected_state
            or self.state.gacha_game_icon != detected_icon
        )
        if is_new_session:
            self.state.gacha_start_ts = int(now)
        self.state.gacha_running = True
        self.state.gacha_game_name = detected_name
        self.state.gacha_game_state = detected_state
        self.state.gacha_game_icon = detected_icon
        if self.state.gacha_summary_str() != prev_summary:
            changed = True
        return changed
