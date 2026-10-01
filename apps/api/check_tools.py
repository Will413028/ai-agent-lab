"""Behavioral guard mutations; use only an idle development checkout."""

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = str(ROOT / ".venv/bin/python")
TEST = str(ROOT / "apps/api/tests/test_tools.py")


def check(*extra, expect_failure=False):
    result = subprocess.run(
        [PYTHON, "-m", "pytest", "-c", str(ROOT / "apps/api/pyproject.toml"), TEST, *extra],
        cwd=ROOT,
        timeout=180,
    )
    if expect_failure:
        if result.returncode != 1:
            raise RuntimeError("Mutation must produce an assertion failure")
    elif result.returncode:
        raise RuntimeError("Tools check failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    check()
    mutations = [
        ("artifacts.py", "if (", "if False and (", "rejects_traversal_and_secret_names"),
        (
            "network.py",
            "return parsed.is_global and not parsed.is_multicast",
            "return True",
            "private_and_translation_addresses_blocked",
        ),
    ]
    for name, original, broken, test in mutations:
        path = ROOT / "apps/api/agent_lab_api" / name
        content = path.read_text()
        if original not in content:
            raise RuntimeError("Mutation anchor changed; update this check")
        try:
            path.write_text(content.replace(original, broken, 1))
            check("-k", test, expect_failure=True)
            print(f"PASS: {name} guard mutation rejected")
        finally:
            path.write_text(content)
    check()
    if args.browser:
        env = {**os.environ, "AGENT_LAB_TOOLS": "fixture", "AGENT_LAB_E2E_PERSISTENCE": "0"}
        subprocess.run(
            [
                "pnpm",
                "--dir",
                str(ROOT / "apps/web"),
                "exec",
                "playwright",
                "test",
                "tools.spec.ts",
            ],
            env=env,
            cwd=ROOT,
            timeout=600,
            check=True,
        )


if __name__ == "__main__":
    main()
