import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = str(ROOT / ".venv/bin/python")
TEST = ROOT / "apps/api/tests/test_agent_runtime.py"


def check(*extra, expect_failure=False):
    result = subprocess.run(
        [PYTHON, "-m", "pytest", "-c", str(ROOT / "apps/api/pyproject.toml"), str(TEST), *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if expect_failure:
        if (
            result.returncode != 1
            or "AssertionError" not in result.stdout
            and "TimeoutError" not in result.stdout
        ):
            raise RuntimeError("Runtime mutation must fail its behavioral regression")
    elif result.returncode:
        print(result.stdout + result.stderr)
        raise RuntimeError("Runtime tests failed")
    else:
        print(result.stdout)
    return result.stdout + result.stderr


def main():
    check()
    path = ROOT / "apps/api/agent_lab_api/agent_runtime.py"
    original = path.read_text()
    for name, needle, replacement, test in [
        ("no-tools", "if not calls:", "if False:", "no_tools_completes"),
        ("cancel", "if cancel.is_set():", "if False:", "cancel_stops_new_calls"),
    ]:
        if needle not in original:
            raise RuntimeError("Runtime mutation anchor changed")
        try:
            path.write_text(original.replace(needle, replacement))
            output = check("-k", test, expect_failure=True)
            (ROOT / "artifacts" / f"s6-{name}-mutation.log").write_text(output)
            print(f"PASS: {name} mutation rejected")
        finally:
            path.write_text(original)
        check("-k", test)


if __name__ == "__main__":
    main()
