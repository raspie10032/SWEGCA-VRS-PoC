"""Offline, outcome-independent analysis of minimized historical specialist rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

MODELS = (
    "rozephine-fixed-135.5m",
    "google-gemma-4-E2B-it-qat-mobile-ct",
    "gpt-5.6-luna",
)
VERDICTS = {"support", "refute", "insufficient", "conflict"}


def compare(rows, before, after):
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        groups[row.get("task")][row.get("condition")].append(row)
    units = []
    counts = Counter()
    for task, cells in sorted(groups.items(), key=lambda item: str(item[0])):
        errors = []
        left, right = cells[before], cells[after]
        if not task or len(left) != 1 or len(right) != 1:
            errors.append("missing_or_duplicate_pair")
        a, b = (left[0] if left else {}), (right[0] if right else {})
        if any(r.get("verdict") not in VERDICTS for r in (a, b)):
            errors.append("missing_or_invalid_verdict")
        if any(r.get("transport_valid") is not True for r in (a, b)):
            errors.append("invalid_transport")
        if not a.get("pair_sha256") or a.get("pair_sha256") != b.get("pair_sha256"):
            errors.append("different_or_missing_main_pair")
        unit = {
            "task": task,
            "before": a.get("verdict"),
            "after": b.get("verdict"),
            "issues": errors,
        }
        units.append(unit)
        if errors:
            counts["invalid"] += 1
            continue
        counts["changed" if a["verdict"] != b["verdict"] else "unchanged"] += 1
        counts[f"{a['verdict']}->{b['verdict']}"] += 1
        counts["pairs_with_parse_failure"] += int(
            any(r.get("strict_parse") is not True for r in (a, b))
        )
    return {
        "changed": counts["changed"],
        "unchanged": counts["unchanged"],
        "invalid": counts["invalid"],
        "pairs_with_parse_failure": counts["pairs_with_parse_failure"],
        "units": units,
    }


def analyze(snapshot):
    if snapshot.get("schema_version") != "historical-specialist-comparisons-v1":
        raise ValueError("unexpected evidence schema")
    rows = snapshot["rows"]
    if any(r.get("model") not in MODELS for r in rows):
        raise ValueError("unknown specialist")
    result = {}
    for model in MODELS:
        selected = [r for r in rows if r["model"] == model]
        baseline = [r for r in selected if r["phase"] == "2"]
        result[model] = {
            "C0_C1": [
                {
                    "condition": r["condition"],
                    "verdict": r["verdict"],
                    "strict_parse": r["strict_parse"],
                }
                for r in sorted(baseline, key=lambda r: r["condition"])
            ],
            "C3_to_C4": compare([r for r in selected if r["phase"] == "3"], "C3", "C4"),
            "swap": [
                {
                    "task": r["task"],
                    "verdict": r["verdict"],
                    "strict_parse": r["strict_parse"],
                }
                for r in selected
                if r["phase"] == "5"
            ],
        }
    return {
        "models": result,
        "new_model_calls": 0,
        "new_experience": 0,
        "scope": "saved development diagnostics; C3/C4 varies re-evidence, not VRS on/off; no population or growth claim",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "snapshot",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("specialist_comparisons.json"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(json.loads(args.snapshot.read_text(encoding="utf-8"))),
            indent=2,
            sort_keys=True,
        )
    )
