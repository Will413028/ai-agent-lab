import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = str(ROOT / ".venv/bin/python")


def check(*extra, expect_failure=False):
    result = subprocess.run(
        [
            PYTHON,
            "-m",
            "pytest",
            "-c",
            str(ROOT / "apps/api/pyproject.toml"),
            str(ROOT / "apps/api/tests/test_image_mcp.py"),
            *extra,
        ],
        cwd=ROOT,
        timeout=300,
    )
    if expect_failure:
        if result.returncode != 1:
            raise RuntimeError("Schema mutation must fail a behavioral test")
    elif result.returncode:
        raise RuntimeError("MCP checks failed")


def main():
    check()
    path = ROOT / "apps/api/agent_lab_api/image_mcp_server.py"
    original = path.read_text()
    needle = "query: SearchQuery,"
    if original.count(needle) != 1:
        raise RuntimeError("Schema mutation anchor changed")
    try:
        path.write_text(original.replace(needle, "query: int,"))
        check("-k", "real_stdio_discovery", expect_failure=True)
        print("PASS: wrong MCP query schema rejected")
    finally:
        path.write_text(original)
    check("-k", "real_stdio_discovery")
    subprocess.run(
        ["pnpm", "--dir", str(ROOT / "apps/web"), "exec", "playwright", "test", "images.spec.ts"],
        cwd=ROOT,
        env={**os.environ, "AGENT_LAB_IMAGES": "fixture", "AGENT_LAB_E2E_PERSISTENCE": "0"},
        timeout=600,
        check=True,
    )


if __name__ == "__main__":
    main()
