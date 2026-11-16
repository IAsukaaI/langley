# Copyright (C) 2026 Asukaa - All Rights Reserved.
# Lang!ley v1.0.5 — Multi-Platform Gaming Companion & Discord Rich Presence

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config_manager import (
    APP_TITLE,
    APP_VERSION,
    CLIENT_ID,
    CFG,
    Reg,
    set_app_id,
    kill_old_procs,
)
from core.scanner import ProcessWindowScanner
from core.state import SessionState
from core.rpc import DiscordRPC, MedalRPCGuard
from core.media import MediaController
from core.updater import AutoUpdater
from core.engine import Engine
from detectors import (
    Cosmetics,
    EpicClient,
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
from ui.app import LangleyApp
from ui.modals import (
    ToolTip,
    LicenseModal,
    UpdatePromptModal,
    PatchNotesModal,
    AddCustomAppModal,
)


def main():
    set_app_id()
    kill_old_procs()
    start_hidden = ("--minimized" in sys.argv) and bool(Reg.get("StartMinimized", 1))
    app = LangleyApp(minimized=start_hidden)
    app.mainloop()


if __name__ == "__main__":
    main()
