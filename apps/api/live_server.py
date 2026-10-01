import os
from pathlib import Path

import uvicorn

from agent_lab_api.personal_config import load_personal_config

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    try:
        load_personal_config(ROOT / ".env")
    except RuntimeError:
        print("Live server 未啟動：個人設定尚未就緒。")
        raise SystemExit(3) from None
    os.environ.update(
        AGENT_LAB_PROVIDER="cloudflare",
        AGENT_LAB_TOOLS="live",
        AGENT_LAB_IMAGES="live",
        AGENT_LAB_PERSISTENCE="1",
    )
    uvicorn.run("agent_lab_api.main:app", host="127.0.0.1", port=18761)
