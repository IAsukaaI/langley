import json
import re
import time
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from core.config_manager import APP_VERSION, GACHA_SUB_GAME_DEFS


PLATFORM_META = {
    "epic": {
        "title": "Epic Games",
        "login_url": "https://www.epicgames.com/account/personal",
        "hint": "Sign in to Epic Games via Browser OAuth or launch Epic Games Launcher to auto-sync your Display Name, library & friends.",
        "placeholder": "Epic Games Display Name",
    },
    "steam": {
        "title": "Steam",
        "login_url": "https://steamcommunity.com/login/home/",
        "hint": "Sign in through Steam OpenID 2.0 or paste your Steam profile URL / SteamID64.",
        "placeholder": "https://steamcommunity.com/id/yourname or 7656119...",
    },
    "gacha": {
        "title": "HoYoPlay & Gacha Games",
        "login_url": "https://www.hoyolab.com/accountCenter",
        "hint": "Sign in to your official Gacha account portal in your browser — Lang!ley automatically syncs your UID, Level, Server Region & Character.",
        "placeholder": "",
    },
    "battlenet": {
        "title": "Blizzard Battle.net",
        "login_url": "https://account.battle.net/overview",
        "hint": "Sign in to Battle.net in your browser or desktop app to auto-sync your BattleTag & friends, or confirm your BattleTag below.",
        "placeholder": "BattleTag (e.g. Player#1234)",
    },
    "riot": {
        "title": "Riot Games",
        "login_url": "https://account.riotgames.com/",
        "hint": "Sign in to Riot Games (or open Riot Client) to auto-detect your Riot ID & friends list, or confirm your Riot ID below.",
        "placeholder": "Riot ID (e.g. Player#EUW)",
    },
    "roblox": {
        "title": "Roblox",
        "login_url": "https://www.roblox.com/home",
        "hint": "Sign in to Roblox in your browser or app to auto-sync your @username, display name & friends, or paste your Roblox profile URL / username below.",
        "placeholder": "Roblox Username (e.g. iAsukaai) or Profile URL",
    },
    "xbox": {
        "title": "Xbox Live / PC Game Pass",
        "login_url": "https://www.xbox.com/play/user",
        "hint": "Sign in to Xbox Live in your browser or Xbox App to auto-detect your Gamertag & friends, or confirm your Gamertag below.",
        "placeholder": "Xbox Live Gamertag",
    },
    "ea": {
        "title": "EA App",
        "login_url": "https://myaccount.ea.com/cp-ui/aboutme/index",
        "hint": "Sign in to your EA Account or launch EA App to auto-detect your EA ID & friends, or confirm your EA ID below.",
        "placeholder": "EA ID / Persona Name",
    },
    "ubisoft": {
        "title": "Ubisoft Connect",
        "login_url": "https://account.ubisoft.com/",
        "hint": "Sign in to Ubisoft Connect in your browser or launcher to auto-detect your username & friends, or confirm below.",
        "placeholder": "Ubisoft Connect Username",
    },
    "gog": {
        "title": "GOG Galaxy",
        "login_url": "https://www.gog.com/account",
        "hint": "Sign in to GOG.com or GOG Galaxy to auto-detect your username & friends, or paste your GOG username / profile URL below.",
        "placeholder": "GOG Username",
    },
    "minecraft": {
        "title": "Minecraft",
        "login_url": "https://www.minecraft.net/en-us/msaprofile",
        "hint": "Sign in to your Microsoft / Minecraft account or launch Lunar, Badlion, Feather, LabyMod, or Prism to auto-detect your username.",
        "placeholder": "Minecraft Username (e.g. Notch)",
    },
}

for _g in GACHA_SUB_GAME_DEFS:
    PLATFORM_META[f"gacha_{_g['key']}"] = {
        "title": f"{_g['name']} ({_g['publisher']})",
        "login_url": _g["login_url"],
        "hint": f"Hybrid Login & Auto-Sync for {_g['name']} — sign in via the official portal, 1-click auto-sync from local game logs & Registry, or paste your UID / Profile below.",
        "placeholder": f"{_g['name']} UID (e.g. 712345678) or Profile URL",
        "is_gacha": True,
        "game_key": _g["key"],
    }


def _render_html_page(title, subtitle, body_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Lang!ley Account Bridge</title>
<style>
  body {{
    margin: 0; padding: 0;
    background: #454138;
    color: #F0EAD8;
    font-family: 'Segoe UI', system-ui, sans-serif;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh;
  }}
  .card {{
    background: #5D584B;
    border: 2px solid #DCD6C4;
    box-shadow: 0 12px 32px rgba(0,0,0,0.45);
    width: 480px; max-width: 92vw;
    padding: 26px 28px;
  }}
  .hdr {{
    font-size: 18px; font-weight: 700; color: #E6D0A3;
    margin-bottom: 6px;
  }}
  .sub {{
    font-size: 13px; color: #C2B9A7;
    margin-bottom: 18px; line-height: 1.45;
  }}
  .status-box {{
    background: #454138;
    border: 1px solid #C8D6B9;
    padding: 12px 14px;
    margin-bottom: 16px;
    font-size: 13px; font-weight: 600; color: #C8D6B9;
  }}
  .btn {{
    display: inline-block;
    background: #454138;
    color: #C8D6B9;
    border: 1px solid #DCD6C4;
    padding: 9px 16px;
    font-size: 13px; font-weight: 700;
    text-decoration: none;
    cursor: pointer;
    width: 100%;
    box-sizing: border-box;
    text-align: center;
    margin-bottom: 10px;
  }}
  .btn:hover {{
    background: #B2AB99; color: #454138;
  }}
  .inp {{
    width: 100%; box-sizing: border-box;
    background: #454138; color: #F0EAD8;
    border: 1px solid #C2B9A7;
    padding: 8px 10px; font-size: 13px;
    margin-bottom: 8px;
  }}
  .row {{
    display: flex; gap: 8px;
  }}
  .muted {{
    font-size: 11px; color: #C2B9A7; margin-top: 12px; text-align: center;
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="hdr">{title}</div>
    <div class="sub">{subtitle}</div>
    {body_html}
    <div class="muted">Lang!ley v{APP_VERSION} • Local Loopback Account Bridge (127.0.0.1)</div>
  </div>
</body>
</html>"""


class _AuthRequestHandler(BaseHTTPRequestHandler):
    auth_server = None

    def log_message(self, format, *args):
        return

    def _send_html(self, html, status=200):
        raw = html.encode("utf-8", errors="ignore")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_json(self, data, status=200):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        srv = self.auth_server
        if not srv:
            self._send_html("Server not ready", 500)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/auth/steam/start":
            callback_url = f"http://127.0.0.1:{srv.port}/auth/steam/callback"
            realm = f"http://127.0.0.1:{srv.port}"
            params = {
                "openid.ns": "http://specs.openid.net/auth/2.0",
                "openid.mode": "checkid_setup",
                "openid.return_to": callback_url,
                "openid.realm": realm,
                "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
                "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
            }
            steam_openid_url = "https://steamcommunity.com/openid/login?" + urllib.parse.urlencode(params)
            self.send_response(302)
            self.send_header("Location", steam_openid_url)
            self.end_headers()
            return

        if path == "/auth/steam/callback":
            claimed = (qs.get("openid.claimed_id") or qs.get("openid.identity") or [""])[0]
            m = re.search(r"(\d{17})", claimed)
            if m:
                sid64 = m.group(1)
                srv.complete_platform_link("steam", sid64)
                uname = srv.state.steam_user_name or sid64
                body = f"""
                <div class="status-box">✓ Account Linked! You can close this tab<br>Connected as: <b>{uname}</b> (SteamID64: {sid64})</div>
                <p style="font-size:13px;color:#F0EAD8;">Your Steam profile, installed games, and friends list are now synced with Lang!ley. You can safely close this browser tab.</p>
                """
                self._send_html(_render_html_page("✓ Account Linked! You can close this tab", "Official Steam OpenID 2.0 Sign-In Complete", body))
                return

        m_status = re.match(r"^/auth/([a-z0-9_]+)/status$", path)
        if m_status:
            plat = m_status.group(1)
            summary = srv.state.platform_account_summary(plat)
            pending = bool(srv.state.auth_pending.get(plat, False))
            self._send_json({"platform": plat, "linked": bool(summary), "summary": summary, "pending": pending})
            return

        m_portal = re.match(r"^/auth/([a-z0-9_]+)/portal$", path)
        if m_portal:
            plat = m_portal.group(1)
            meta = PLATFORM_META.get(plat)
            if not meta:
                self._send_html("Unknown platform", 404)
                return
            is_gacha_plat = plat == "gacha" or plat.startswith("gacha_") or meta.get("is_gacha")
            if is_gacha_plat:
                form_block = f"""
                <div style="font-size:12px;color:#C2B9A7;margin:10px 0 6px 0;">
                  2. Click below for instant 1-click Auto-Sync from your local game logs &amp; Windows Registry:
                </div>
                <a class="btn" href="/auth/{plat}/callback?auto=1" style="margin-top:4px;">
                  ↻ Complete Automatic {meta['title']} Sync
                </a>
                <form method="GET" action="/auth/{plat}/callback" style="margin-top:10px;">
                  <div style="font-size:12px;color:#C2B9A7;margin-bottom:6px;">
                    3. Optional Fallback — Paste your UID (or UID, Level, Region, Character) to fetch via Enka / Mihomo / HoYoLAB:
                  </div>
                  <input class="inp" type="text" name="value" placeholder="{meta.get('placeholder') or 'UID (e.g. 712345678) or Profile URL'}" required>
                  <button type="submit" class="btn" style="margin-top:4px;">✓ Link UID &amp; Fetch Telemetry</button>
                </form>
                """
            else:
                form_block = f"""
                <form method="GET" action="/auth/{plat}/callback" style="margin-top:12px;">
                  <div style="font-size:12px;color:#C2B9A7;margin-bottom:6px;">
                    2. Lang!ley automatically watches your local launcher &amp; session. Or confirm your ID / Profile URL directly below:
                  </div>
                  <input class="inp" type="text" name="value" placeholder="{meta['placeholder']}" required>
                  <button type="submit" class="btn" style="margin-top:4px;">✓ Link &amp; Sync {meta['title']} Now</button>
                </form>
                """
            body = f"""
            <div id="live-status" class="status-box" style="color:#E6D0A3;border-color:#E6D0A3;">
              ⏳ Waiting for {meta['title']} automatic sign-in &amp; telemetry sync...
            </div>
            <a class="btn" href="{meta['login_url']}" target="_blank" rel="noopener">
              1. Open Official {meta['title']} Portal ↗
            </a>
            {form_block}
            <script>
              setInterval(async () => {{
                try {{
                  const r = await fetch('/auth/{plat}/status');
                  const d = await r.json();
                  if (d.linked && !d.pending) {{
                    const box = document.getElementById('live-status');
                    box.style.color = '#C8D6B9';
                    box.style.borderColor = '#C8D6B9';
                    box.innerHTML = '✓ Account Linked! You can close this tab<br>Connected as: <b>' + d.summary + '</b>';
                  }}
                }} catch (e) {{}}
              }}, 1500);
            </script>
            """
            self._send_html(_render_html_page(f"Link {meta['title']}", meta["hint"], body))
            return

        m_cb = re.match(r"^/auth/([a-z0-9_]+)/callback$", path)
        if m_cb:
            plat = m_cb.group(1)
            val = (qs.get("value") or qs.get("uid") or [""])[0].strip()
            lvl = (qs.get("level") or [""])[0].strip()
            reg = (qs.get("region") or [""])[0].strip()
            char = (qs.get("character") or [""])[0].strip()
            ok = srv.complete_platform_link(plat, val, level=lvl, region=reg, character=char)
            summary = srv.state.platform_account_summary(plat) or val or "Auto-Synced"
            title = PLATFORM_META.get(plat, {}).get("title", plat.title())
            if ok:
                body = f"""
                <div class="status-box">✓ Account Linked! You can close this tab<br>Connected to {title} as: <b>{summary}</b></div>
                <p style="font-size:13px;color:#F0EAD8;">Your account, telemetry, and friend list have been synced to Lang!ley. You can now close this browser tab.</p>
                """
                self._send_html(_render_html_page("✓ Account Linked! You can close this tab", f"{title} — Browser Account Sync Complete", body))
            else:
                hint_err = (
                    f"No local game logs or Registry UID found yet for {title}. Launch the game once or paste your UID in the fallback box on the bridge page (or in the Lang!ley ACCOUNTS tab)."
                    if not val
                    else f"Could not verify '{val}'. Please check your UID / account and try again."
                )
                body = f"""
                <div class="status-box" style="color:#D6A79A;border-color:#D6A79A;">{hint_err}</div>
                <a class="btn" href="/auth/{plat}/portal">← Back to {title} Login Bridge</a>
                """
                self._send_html(_render_html_page(f"{title} Sync Notice", "Use Local Auto-Sync or Paste UID Fallback", body))
            return

        self._send_html("Lang!ley Local Auth Bridge Active", 200)


class BrowserAuthServer:
    def __init__(self, state, engine):
        self.state = state
        self.engine = engine
        self.port = 0
        self.httpd = None
        self.poll_Nonce = {}

    def start(self):
        _AuthRequestHandler.auth_server = self
        if self.httpd and self.port:
            return self.port
        for candidate_port in (47831, 47832, 0):
            try:
                self.httpd = HTTPServer(("127.0.0.1", candidate_port), _AuthRequestHandler)
                self.port = self.httpd.server_port
                threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
                break
            except Exception:
                self.httpd = None
        return self.port

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass

    def start_browser_login(self, platform):
        plat = (platform or "").strip().lower()
        if not self.httpd:
            self.start()

        if plat == "epic":
            self.state.auth_pending["epic"] = True
            self.engine.on_ui()

            def _on_epic_done():
                self.state.auth_pending["epic"] = False
                self.engine.on_ui()
                self.engine.sync_rpc(force=True)

            self.engine.epic.login(done_cb=_on_epic_done)
            return

        self.state.auth_pending[plat] = True
        self.engine.on_ui()

        nonce = time.time()
        self.poll_Nonce[plat] = nonce

        if plat == "steam":
            url = f"http://127.0.0.1:{self.port}/auth/steam/start"
            webbrowser.open(url)
        elif plat in PLATFORM_META:
            portal_url = f"http://127.0.0.1:{self.port}/auth/{plat}/portal"
            webbrowser.open(portal_url)
            # Also open the official login page so the user can sign in immediately
            official_url = PLATFORM_META[plat].get("login_url")
            if official_url:
                threading.Timer(0.4, lambda: webbrowser.open(official_url)).start()

        threading.Thread(target=self._auth_poll_worker, args=(plat, nonce), daemon=True).start()

    def complete_platform_link(self, plat, value="", level="", region="", character=""):
        plat = (plat or "").strip().lower()
        ok = False
        if plat == "epic":
            ok = self.engine.epic.link_account(value) if value else self.engine.epic.detect_local_account()
        elif plat == "steam":
            ok = self.engine.steam.link_manual_steam(value) if value else self.engine.steam.detect_local_steam_user()
        elif plat.startswith("gacha_"):
            gkey = plat.split("gacha_", 1)[1]
            if value or level or region or character:
                ok = self.engine.gacha.save_profile(
                    uid=value, level=level, region=region, character=character, game_key=gkey
                )
            else:
                ok = self.engine.gacha.detect_game_account(gkey, from_browser_callback=True)
        elif plat == "gacha":
            if value or level or region or character:
                ok = self.engine.gacha.save_profile(uid=value, level=level, region=region, character=character)
            else:
                ok = self.engine.gacha.detect_local_account()
        elif plat == "battlenet":
            ok = self.engine.battlenet.link_account(value) if value else self.engine.battlenet.detect_local_account()
        elif plat == "riot":
            ok = self.engine.riot.link_account(value) if value else self.engine.riot.detect_local_account()
        elif plat == "roblox":
            ok = self.engine.roblox.link_username(value) if value else self.engine.roblox.detect_local_account()
        elif plat == "xbox":
            ok = self.engine.xbox.link_gamertag(value) if value else bool(self.engine.xbox.detect_local_gamertag() or self.state.xbox_gamertag)
        elif plat == "ea":
            ok = self.engine.ea.link_account(value) if value else self.engine.ea.detect_local_account()
        elif plat == "ubisoft":
            ok = self.engine.ubisoft.link_account(value) if value else self.engine.ubisoft.detect_local_account()
        elif plat == "gog":
            ok = self.engine.gog.link_account(value) if value else self.engine.gog.detect_local_account()
        elif plat == "minecraft":
            ok = self.engine.minecraft.link_account(value) if value else self.engine.minecraft.detect_local_account()

        if ok:
            self.state.auth_pending[plat] = False
            self.engine.on_ui()
            self.engine.sync_rpc(force=True)
        return ok

    def link_platform_value(self, plat, value="", level="", region="", character=""):
        return self.complete_platform_link(plat, value=value, level=level, region=region, character=character)

    def _try_detect_from_browser_windows(self, plat):
        try:
            _, _, windows, _ = self.engine.scanner.get_snapshot(force=True)
            for w in windows:
                title = (w.get("title") or "").strip()
                t_low = title.lower()
                if not title:
                    continue
                if plat == "battlenet":
                    m = re.search(r"\b([A-Za-z0-9_]{2,16}#\d{3,6})\b", title)
                    if m:
                        return self.engine.battlenet.link_account(m.group(1))
                elif plat == "riot":
                    m = re.search(r"\b([A-Za-z0-9_ ]{2,16}#[A-Za-z0-9]{2,6})\b", title)
                    if m and ("riot" in t_low or "valorant" in t_low or "league" in t_low):
                        return self.engine.riot.link_account(m.group(1).strip())
                elif plat == "gacha" or plat.startswith("gacha_"):
                    gkey = plat.split("gacha_", 1)[1] if plat.startswith("gacha_") else "genshin"
                    m_uid = re.search(r"\b([1-9]\d{8,9})\b", title)
                    if m_uid and (
                        "hoyolab" in t_low
                        or "genshin" in t_low
                        or "star rail" in t_low
                        or "zenless" in t_low
                        or "wuthering" in t_low
                        or "enka" in t_low
                    ):
                        return self.engine.gacha.save_profile(uid=m_uid.group(1), game_key=gkey)
                elif plat == "roblox":
                    if "roblox" in t_low and "profile" in t_low:
                        m_r = re.match(r"^([A-Za-z0-9_]{3,20})'s Profile", title)
                        if m_r:
                            return self.engine.roblox.link_username(m_r.group(1))
        except Exception:
            pass
        return False

    def _auth_poll_worker(self, plat, nonce):
        deadline = time.time() + 60.0
        while time.time() < deadline and not self.engine.stop_evt.is_set():
            if self.poll_Nonce.get(plat) != nonce or not self.state.auth_pending.get(plat):
                return

            detected = False
            try:
                if plat == "steam":
                    if self.engine.steam.detect_local_steam_user() or self.state.steam_user_name:
                        self.engine.steam.fetch_public_profile()
                        self.engine.steam.fetch_steam_friends()
                        detected = bool(self.state.steam_user_name or self.state.steam_id64)
                elif plat.startswith("gacha_"):
                    gkey = plat.split("gacha_", 1)[1]
                    detected = (
                        self.engine.gacha.detect_game_account(gkey, from_browser_callback=False)
                        or self._try_detect_from_browser_windows(plat)
                    )
                elif plat == "gacha":
                    detected = self.engine.gacha.detect_local_account() or self._try_detect_from_browser_windows("gacha")
                elif plat == "battlenet":
                    detected = self.engine.battlenet.detect_local_account() or self._try_detect_from_browser_windows("battlenet")
                elif plat == "riot":
                    detected = self.engine.riot.detect_local_account() or self._try_detect_from_browser_windows("riot")
                elif plat == "roblox":
                    detected = self.engine.roblox.detect_local_account() or self._try_detect_from_browser_windows("roblox")
                elif plat == "xbox":
                    self.engine.xbox.detect_local_gamertag()
                    self.engine.xbox.fetch_friends()
                    detected = bool(self.state.xbox_gamertag)
                elif plat == "ea":
                    detected = self.engine.ea.detect_local_account()
                elif plat == "ubisoft":
                    detected = self.engine.ubisoft.detect_local_account()
                elif plat == "gog":
                    detected = self.engine.gog.detect_local_account()
                elif plat == "minecraft":
                    detected = self.engine.minecraft.detect_local_account()
            except Exception:
                detected = False

            if detected:
                self.state.auth_pending[plat] = False
                self.engine.on_ui()
                self.engine.sync_rpc(force=True)
                return

            time.sleep(1.5)

        if self.poll_Nonce.get(plat) == nonce and self.state.auth_pending.get(plat):
            self.state.auth_pending[plat] = False
            self.engine.on_ui()
