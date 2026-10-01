"""Validate feature dispositions and source coverage without live APIs or secrets."""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = "6d4608c58b442d470fffc7a5e0b2aedb0e9478c8"
DECISIONS = {"D1", "D2", "D3", "D4", "D5", "D6a", "D6b"}
ACTIONS = {"replace-without-reading", "omit", "replace", "rewrite"}


def phase_ids(spec: str) -> set[str]:
    result = set()
    for part in spec.split("、"):
        part = part.strip()
        if re.fullmatch(r"S[0-7][AB]?", part):
            result.add(part)
            continue
        match = re.fullmatch(r"S([0-7])[–-]S([0-7])", part)
        if not match or int(match[1]) > int(match[2]):
            raise ValueError(f"Invalid phase specification: {spec}")
        result.update(f"S{i}" for i in range(int(match[1]), int(match[2]) + 1))
    return result


def rows(text: str, pattern: str) -> dict[str, list[str]]:
    found = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and re.fullmatch(pattern, cells[0]):
            if cells[0] in found:
                raise ValueError(f"Duplicate row: {cells[0]}")
            found[cells[0]] = cells
    return found


def validate(root: Path, source: Path | None = None) -> None:
    inventory = (root / "inventory.md").read_text()
    plan = (root.parent / "2026-10-01-rebuild.md").read_text()
    requirements = rows(inventory, r"R\d{2}")
    defects = rows(inventory, r"B\d{2}")
    decisions = rows(plan, r"D(?:[1-5]|6[ab])")
    nfr = rows(inventory, r"N\d{2}")
    sections = dict(re.findall(r"^- \[[ x]\] \*\*(S\d[AB]?)\.[^\n]*\n(.*?)(?=^- \[[ x]\] \*\*|\n## |\Z)", plan, re.M | re.S))
    if set(requirements) != {f"R{i:02}" for i in range(1, 14)}:
        raise ValueError("Requirement rows missing or unexpected")
    if set(defects) != {f"B{i:02}" for i in range(1, 7)}:
        raise ValueError("Defect dispositions missing or unexpected")
    if set(decisions) != DECISIONS:
        raise ValueError("Decision rows missing or unexpected")
    for key, cells in requirements.items():
        if len(cells) != 4 or not all(cells):
            raise ValueError(f"Missing feature disposition or phase: {key}")
        if not phase_ids(cells[3]) <= sections.keys():
            raise ValueError(f"Feature refers to nonexistent phase: {key}")
    for key, cells in defects.items():
        if len(cells) != 3 or not all(cells):
            raise ValueError(f"Missing defect disposition: {key}")
    for key, cells in decisions.items():
        if len(cells) != 5 or not all(cells):
            raise ValueError(f"Missing decision conclusion or dependency: {key}")
        if not phase_ids(cells[4]) <= sections.keys():
            raise ValueError(f"Decision refers to nonexistent phase: {key}")
    if set(nfr) != {"N01", "N02", "N03", "N04"}:
        raise ValueError("Nonfunctional mapping rows missing or unexpected")
    for key, cells in nfr.items():
        if len(cells) != 3 or not all(cells):
            raise ValueError(f"Nonfunctional requirement not mapped: {key}")
        for phase in phase_ids(cells[1]):
            if phase not in sections or key not in sections[phase]:
                raise ValueError(f"Nonfunctional requirement absent from phase acceptance: {key}/{phase}")
    ledger = json.loads((root / "source-ledger.json").read_text())
    if ledger["revision"] != PIN or ledger["contents_read"] is not False:
        raise ValueError("Invalid metadata-only source snapshot")
    paths = []
    for item in ledger["files"]:
        if not all(item.get(k) for k in ("path", "action", "phase", "reason")):
            raise ValueError("Source disposition is incomplete")
        if item["phase"] not in sections:
            raise ValueError("Unknown source destination phase")
        if item["action"] not in ACTIONS:
            raise ValueError("Unknown source disposition action")
        paths.append(item["path"])
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("Empty or duplicate source paths")
    if source:
        head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"]).decode().strip()
        actual = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).decode().split("\0")[:-1]
        if head != PIN or set(paths) != set(actual):
            raise ValueError("Source ledger does not cover the pinned checkout")


def self_test() -> None:
    """Mutation copies stay under this attachment and never alter real files."""
    validate(HERE)
    cases = ("requirement", "phase", "defect", "decision", "source", "duplicate",
             "illegal-phase", "negated-phase", "unknown-label", "reverse-range", "unknown-action", "nfr", "source-phase")
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="check-mutation-", dir=HERE) as temp:
            parent = Path(temp)
            root = parent / "attachments"
            root.mkdir()
            plan = (HERE.parent / "2026-10-01-rebuild.md").read_text()
            inventory = (HERE / "inventory.md").read_text()
            ledger = json.loads((HERE / "source-ledger.json").read_text())
            if case == "requirement":
                inventory = re.sub(r"^\| R01 .*\n", "", inventory, flags=re.M)
            elif case == "phase":
                inventory = re.sub(r"^(\| R01 .*\|) S2 \|$", r"\1  |", inventory, flags=re.M)
            elif case == "defect":
                inventory = re.sub(r"^\| B01 .*\n", "", inventory, flags=re.M)
            elif case == "decision":
                plan = re.sub(r"^\| D2 .*\n", "", plan, flags=re.M)
            elif case == "source":
                ledger["files"][0]["reason"] = ""
            elif case == "duplicate":
                ledger["files"].append(ledger["files"][0])
            elif case in {"illegal-phase", "negated-phase", "unknown-label", "reverse-range"}:
                invalid = {"illegal-phase": "S10", "negated-phase": "not S2",
                           "unknown-label": "S1-unknown", "reverse-range": "S3–S1"}[case]
                inventory = re.sub(r"^(\| R01 .*\|) S2 \|$", lambda m: m[1] + f" {invalid} |", inventory, flags=re.M)
            elif case == "unknown-action":
                ledger["files"][0]["action"] = "invented-action"
            elif case == "nfr":
                inventory = re.sub(r"^\| N02 .*\n", "", inventory, flags=re.M)
            elif case == "source-phase":
                ledger["files"][0]["phase"] = "S0"
            (parent / "2026-10-01-rebuild.md").write_text(plan)
            (root / "inventory.md").write_text(inventory)
            (root / "source-ledger.json").write_text(json.dumps(ledger))
            try:
                validate(root)
            except ValueError:
                continue
            raise ValueError(f"Mutation escaped validation: {case}")
    print(f"Passed baseline and {len(cases)} negative mutations.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    validate(HERE, args.source.resolve() if args.source else None)
    if args.self_test:
        self_test()
    print("Plan mappings and source dispositions passed.")


if __name__ == "__main__":
    main()
