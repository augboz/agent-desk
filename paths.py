"""Where Agent Desk keeps its own files: %APPDATA%\\AgentDesk (settings and the
error log). Nothing is written into the app's folder or into ~/.claude."""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "AgentDesk")
CONFIG = os.path.join(DATA_DIR, "config.json")
LOG = os.path.join(DATA_DIR, "agent_desk.log")


def ensure_data_dir():
    """Create the folder, and bring over settings from older versions (kept next to the app)."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        old = os.path.join(HERE, "config.json")
        if os.path.isfile(old) and not os.path.exists(CONFIG):
            shutil.copy2(old, CONFIG)
    except OSError:
        pass
