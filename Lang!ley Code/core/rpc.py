import os
import json
import time
import struct
import threading
from core.config_manager import Reg, MEDAL_PROCS

COMPETING_OVERLAY_PROCS = MEDAL_PROCS | {
    "overwolf.exe",
    "overwolfbrowser.exe",
    "nvidia overlay.exe",
    "nvidia share.exe",
    "steelseriesgg.exe",
    "steelseriesengine.exe",
    "razercortex.exe",
    "gamebar.exe",
    "xboxgamebar.exe",
    "premid.exe",
    "rpc-bridge.exe",
}


def _parse_str_list(raw):
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass
    return []


class DiscordRPC:
    def __init__(self, cid, state=None):
        self.cid = str(cid)
        self.state = state
        self.pipe = None
        self.pipe_index = -1
        self.lock = threading.Lock()
        self.connected = False
        self.last_activity = None
        self.nonce_seq = 0
        self.last_pulse_ts = 0.0

    def connect(self):
        with self.lock:
            self._close()
            for i in range(10):
                p = rf"\\?\pipe\discord-ipc-{i}"
                if not os.path.exists(p):
                    continue
                try:
                    self.pipe = open(p, "r+b", buffering=0)
                    self._send(0, {"v": 1, "client_id": self.cid})
                    self.pipe_index = i
                    self.connected = True
                    self.sync_social(self.state)
                    return True
                except OSError:
                    self._close()
            return False

    def _capture_ipc_user(self, user_obj):
        if not isinstance(user_obj, dict):
            return
        uid = str(user_obj.get("id") or "").strip()
        uname = str(user_obj.get("username") or "").strip()
        gname = str(user_obj.get("global_name") or uname).strip()
        if self.state is not None:
            if uid:
                self.state.discord_user_id = uid
                Reg.set("DiscordUserId", uid)
            if uname:
                self.state.discord_username = uname
                Reg.set("DiscordUsername", uname)
            if gname:
                self.state.discord_display_name = gname
                Reg.set("DiscordDisplayName", gname)

    def _send(self, op, data):
        if not self.pipe:
            raise OSError("Discord IPC pipe not open")
        raw = json.dumps(data).encode("utf-8")
        self.pipe.write(struct.pack("<II", op, len(raw)) + raw)
        self.pipe.flush()
        hdr = self.pipe.read(8)
        if not hdr or len(hdr) < 8:
            raise OSError("Discord IPC short header")
        resp_op, size = struct.unpack("<II", hdr)
        body = b""
        if size > 0:
            body = self.pipe.read(size)
        if resp_op == 2:
            raise OSError("Discord IPC closed by remote")
        if body:
            try:
                parsed = json.loads(body.decode("utf-8", errors="ignore"))
                if isinstance(parsed, dict):
                    if parsed.get("evt") == "ERROR":
                        raise OSError(f"Discord IPC error: {parsed.get('data')}")
                    d_block = parsed.get("data")
                    if isinstance(d_block, dict) and isinstance(d_block.get("user"), dict):
                        self._capture_ipc_user(d_block["user"])
            except ValueError:
                pass

    def sync_social(self, state=None):
        st = state or self.state
        if st is None:
            return False
        appdata = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
        if not st.discord_username:
            for client_dir in ("discord", "discordptb", "discordcanary"):
                scope_path = os.path.join(appdata, client_dir, "sentry", "scope_v3.json")
                if os.path.exists(scope_path):
                    try:
                        with open(scope_path, "r", encoding="utf-8", errors="ignore") as f:
                            raw = json.load(f)
                        u = (raw.get("scope") or {}).get("user") or raw.get("user") or {}
                        if isinstance(u, dict) and (u.get("username") or u.get("id")):
                            self._capture_ipc_user(u)
                            break
                    except Exception:
                        pass

        friends = []
        seen = set()

        def add_entry(name, status, online=True, badge="●"):
            clean = (name or "").strip()
            if not clean:
                return
            k = clean.lower()
            if k in seen:
                return
            seen.add(k)
            friends.append({"name": clean, "status": status, "online": online, "badge": badge})

        for peer in st.peers:
            add_entry(peer, "★ In Your Lang!ley Squad / Active Party", online=True, badge="★")

        for ef in st.friends_list:
            if ef.get("in_party") or ef.get("is_langley"):
                add_entry(ef["name"], f"★ {ef.get('status') or 'In Party'} (Epic / Discord)", online=True, badge="★")
        for rf in st.riot_friends:
            if rf.get("online"):
                add_entry(rf["name"], f"● {rf.get('status') or 'Online on Riot'}", online=True, badge="●")
        for sf in st.steam_friends[:8]:
            if sf.get("in_game"):
                add_entry(sf["name"], f"★ {sf.get('status') or 'In-Game on Steam'}", online=True, badge="★")

        tracked_list = _parse_str_list(Reg.get("DiscordTrackedFriends", ""))
        for fname in tracked_list:
            add_entry(fname, "Discord Friend (Pinned)", online=self.connected, badge="●" if self.connected else "○")

        st.discord_friends = friends
        return True

    def add_tracked_friend(self, username, state=None):
        st = state or self.state
        uname = str(username or "").strip()
        if not uname:
            return False
        tracked = _parse_str_list(Reg.get("DiscordTrackedFriends", ""))
        if uname.lower() not in [x.lower() for x in tracked]:
            tracked.append(uname)
            Reg.set("DiscordTrackedFriends", json.dumps(tracked))
        self.sync_social(st)
        return True

    def remove_tracked_friend(self, username, state=None):
        st = state or self.state
        uname = str(username or "").strip().lower()
        tracked = [x for x in _parse_str_list(Reg.get("DiscordTrackedFriends", "")) if x.lower() != uname]
        Reg.set("DiscordTrackedFriends", json.dumps(tracked))
        self.sync_social(st)
        return True

    def _next_nonce(self):
        self.nonce_seq += 1
        return f"langley-prio-{int(time.time() * 1000)}-{self.nonce_seq}"

    def _target_pid(self):
        return os.getpid()

    def update(self, activity, promote=False):
        with self.lock:
            if not self.connected:
                return False
            if isinstance(activity, dict):
                enriched = dict(activity)
                enriched.setdefault("type", 0)
                enriched.setdefault("instance", True)
                self.last_activity = enriched
            else:
                enriched = None
                self.last_activity = None

            pid = self._target_pid()
            try:
                if promote and enriched is not None:
                    now = time.time()
                    if now - self.last_pulse_ts >= 3.0:
                        self.last_pulse_ts = now
                        self._send(
                            1,
                            {
                                "cmd": "SET_ACTIVITY",
                                "args": {"pid": pid, "activity": None},
                                "nonce": self._next_nonce(),
                            },
                        )
                msg = {
                    "cmd": "SET_ACTIVITY",
                    "args": {"pid": pid, "activity": enriched},
                    "nonce": self._next_nonce(),
                }
                self._send(1, msg)
                return True
            except OSError:
                self._close()
                return False

    def reassert_priority(self, promote=False):
        with self.lock:
            if not self.connected or not self.last_activity:
                return False
            pid = self._target_pid()
            try:
                now = time.time()
                if promote and (now - self.last_pulse_ts >= 4.0):
                    self.last_pulse_ts = now
                    self._send(
                        1,
                        {
                            "cmd": "SET_ACTIVITY",
                            "args": {"pid": pid, "activity": None},
                            "nonce": self._next_nonce(),
                        },
                    )
                msg = {
                    "cmd": "SET_ACTIVITY",
                    "args": {"pid": pid, "activity": self.last_activity},
                    "nonce": self._next_nonce(),
                }
                self._send(1, msg)
                return True
            except OSError:
                self._close()
                return False

    def clear(self):
        return self.update(None)

    def _close(self):
        self.connected = False
        self.pipe_index = -1
        if self.pipe:
            try:
                self.pipe.close()
            except Exception:
                pass
            self.pipe = None

    def close(self):
        with self.lock:
            if self.connected and self.pipe:
                try:
                    self._send(
                        1,
                        {
                            "cmd": "SET_ACTIVITY",
                            "args": {"pid": os.getpid(), "activity": None},
                            "nonce": "0",
                        },
                    )
                except Exception:
                    pass
            self._close()


class MedalRPCGuard:
    """Universal Discord Priority Guard:
    Ensures Lang!ley's Rich Presence stays at #1 on Discord above all native
    registered game detections, built-in game RPCs, Medal.tv, Overwolf, NVIDIA Overlay,
    Xbox Game Bar, and any other background software.
    """

    REASSERT_INTERVAL_ACTIVE = 2.0
    PROMOTE_PULSE_INTERVAL = 14.0

    def __init__(self, state, rpc):
        self.state = state
        self.rpc = rpc
        self.last_reassert_ts = 0.0
        self.last_promote_ts = 0.0
        self.prev_competing_running = False
        self.prev_encoder_active = False
        self.prev_pids_count = 0

    def poll(self, snapshot):
        procs, _, windows, _ = snapshot
        competing_run = False
        encoder_run = False
        for p in procs:
            pname = p["name"]
            if pname in COMPETING_OVERLAY_PROCS:
                competing_run = True
                if pname == "medalencoder.exe":
                    encoder_run = True
            elif "\\medal\\" in p["exe_lower"] or "\\overwolf\\" in p["exe_lower"]:
                competing_run = True
                if "encoder" in pname:
                    encoder_run = True

        if not competing_run:
            for w in windows:
                if w["pname"] in COMPETING_OVERLAY_PROCS or w["title_lower"].startswith("medal"):
                    competing_run = True
                    break

        cur_pids_cnt = len(procs)
        new_proc_spawned = abs(cur_pids_cnt - self.prev_pids_count) >= 2
        self.prev_pids_count = cur_pids_cnt

        changed = (competing_run != self.state.medal_running) or (
            encoder_run != self.state.medal_encoder_active
        )
        transitioned_on = (
            (competing_run and not self.prev_competing_running)
            or (encoder_run and not self.prev_encoder_active)
            or new_proc_spawned
        )
        self.prev_competing_running = competing_run
        self.prev_encoder_active = encoder_run
        self.state.medal_running = competing_run
        self.state.medal_encoder_active = encoder_run
        return changed, transitioned_on

    def enforce_priority(self, active_platform, immediate=False):
        if not self.state.active or active_platform in ("paused", "idle"):
            return False
        if not self.state.medal_priority_enabled:
            return False
        now = time.time()
        if immediate or (now - self.last_reassert_ts >= self.REASSERT_INTERVAL_ACTIVE):
            should_promote = immediate or (
                now - self.last_promote_ts >= self.PROMOTE_PULSE_INTERVAL
            )
            if self.rpc.reassert_priority(promote=should_promote):
                self.last_reassert_ts = now
                if should_promote:
                    self.last_promote_ts = now
                self.state.medal_reassertions += 1
                return True
        return False
