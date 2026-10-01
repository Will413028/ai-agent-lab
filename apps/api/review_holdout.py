"""Record explicit human rubric verdicts without editing the immutable live attempt."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "docs/plans/2026-10-01-rebuild/holdout.json"


def adjudicate(attempt, verdicts, corpus, *, evidence_dir):
    if attempt["corpus_sha256"] != hashlib.sha256(corpus).hexdigest():
        raise ValueError("corpus_changed")
    cases = json.loads(corpus)["cases"]
    expected = {case["id"] for case in cases}
    rows = attempt["cases"]
    if {row["case"] for row in rows} != expected or len(rows) != len(expected):
        raise ValueError("incomplete_attempt")
    required = {row["case"] for row in rows if row["status"] == "needs_review"}
    if set(verdicts) != required:
        raise ValueError("review_each_pending_case_only")
    results = []
    evidence_keys = {
        "chat": ("allowed_answers",),
        "report": ("allowed_report",),
        "rag": ("allowed_answers", "source", "retrieval_snapshots"),
        "tools": ("allowed_run_events", "artifact_file", "artifact_sha256"),
    }
    kinds = {case["id"]: case["kind"] for case in cases}
    for row in rows:
        status = row["status"]
        reason = None
        if "artifact_file" in row:
            name = row["artifact_file"]
            if Path(name).name != name or name.startswith("."):
                raise ValueError("invalid_artifact_path")
            artifact = evidence_dir / name
            if artifact.is_symlink() or not artifact.is_file():
                raise ValueError("missing_artifact")
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != row["artifact_sha256"]:
                raise ValueError("artifact_changed")
        if status == "needs_review":
            if any(not row.get(key) for key in evidence_keys.get(kinds[row["case"]], ())):
                raise ValueError("missing_review_evidence")
            review = verdicts[row["case"]]
            if review.get("status") not in ("passed", "failed") or not isinstance(
                review.get("reason"), str
            ):
                raise ValueError("invalid_verdict")
            reason = review["reason"].strip()
            if not reason:
                raise ValueError("reason_required")
            status = review["status"]
        elif status not in ("passed", "failed", "not_run"):
            raise ValueError("invalid_attempt_status")
        results.append({"case": row["case"], "status": status, "human_reason": reason})
    return {
        "attempt_id": attempt["attempt_id"],
        "corpus_sha256": attempt["corpus_sha256"],
        "cases": results,
        "conclusion": "passed" if all(r["status"] == "passed" for r in results) else "incomplete",
        "scope": "N04 functional smoke；不代表品質或可靠率",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args()
    if not args.reviewer.strip():
        parser.error("reviewer 不可空白")
    artifacts = (ROOT / "artifacts").resolve()
    path = args.attempt.resolve()
    if args.attempt.is_symlink() or not path.is_relative_to(artifacts):
        parser.error("attempt 必須是 artifacts 內原始 attempt.json")
    attempt_bytes = path.read_bytes()
    result = adjudicate(
        json.loads(attempt_bytes),
        json.loads(args.review.read_text()),
        CORPUS.read_bytes(),
        evidence_dir=path.parent,
    )
    result.update(
        reviewed_at=datetime.now(UTC).isoformat(),
        reviewer=args.reviewer.strip(),
        attempt_sha256=hashlib.sha256(attempt_bytes).hexdigest(),
    )
    output = path.parent / ("review-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".json")
    with output.open("x") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(result["conclusion"])
    return 0 if result["conclusion"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
