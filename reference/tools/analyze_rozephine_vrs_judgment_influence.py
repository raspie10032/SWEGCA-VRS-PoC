"""Correctness-independent, post-hoc analysis of existing bounded Q receipts.

No runtime calls, media reads, learning, gate replacement or confirmation claims.
Matching receipts are necessary controls, not sufficient proof of causality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

CURRENT = "full_current_current_vrs"
CONTROLS = ("full_current_frozen_vrs", "full_current_no_vrs")
DECISIONS = {"success", "failure", "abstain"}


def analyze(rows):
    """Keep every source and every transition; outcomes never select effects."""
    source_counts = Counter(row.get("source_id") for row in rows)
    units = []
    for row in rows:
        evaluation = row["prediction"]["evaluation"]
        arm_rows = evaluation["arms"]
        arms = {arm["arm"]: arm for arm in arm_rows}
        issues = []
        if len(arms) != len(arm_rows):
            issues.append("duplicate_arm")
        if not row.get("source_id") or source_counts[row.get("source_id")] != 1:
            issues.append("missing_or_duplicate_source")
        if not row.get("source_revision"):
            issues.append("missing_source_revision")
        if not evaluation.get("pair_snapshot_id"):
            issues.append("missing_pair")
        required = (CURRENT, *CONTROLS)
        if any(name not in arms for name in required):
            issues.append("missing_arm")
        elif any(arms[name].get("decision") not in DECISIONS for name in required):
            issues.append("invalid_decision")
        elif any("recalled_episode_ids" not in arms[name] for name in required):
            issues.append("missing_recall")
        elif len({tuple(arms[name]["recalled_episode_ids"]) for name in required}) != 1:
            issues.append("changed_recall")
        units.append(
            {
                "role": row["role"],
                "pair_snapshot_id": evaluation.get("pair_snapshot_id"),
                "decisions": {
                    name: arms.get(name, {}).get("decision") for name in required
                },
                "actual_outcome": row.get("actual_outcome"),
                "control_issues": issues,
            }
        )
    pairs = {unit["pair_snapshot_id"] for unit in units}
    if len(pairs) > 1:
        for unit in units:
            unit["control_issues"].append("mixed_run_snapshots")
    valid = [unit for unit in units if not unit["control_issues"]]
    comparisons, utility = {}, {}
    for control in CONTROLS:
        transitions = Counter()
        improvements = harms = labeled = unknown = 0
        for unit in valid:
            current, other = unit["decisions"][CURRENT], unit["decisions"][control]
            transitions[f"{other}->{current}"] += 1
            actual = unit["actual_outcome"]
            if actual not in {"success", "failure"}:
                unknown += 1
                continue
            labeled += 1
            # Utility convention only: abstention is not an exact correct answer.
            improvements += (current == actual) and (other != actual)
            harms += (current != actual) and (other == actual)
        changed = sum(
            n for edge, n in transitions.items() if len(set(edge.split("->"))) > 1
        )
        comparisons[control] = {
            "control_valid_units": len(valid),
            "changed": changed,
            "unchanged": len(valid) - changed,
            "change_fraction": changed / len(valid) if valid else None,
            "transitions_control_to_current": dict(sorted(transitions.items())),
        }
        utility[control] = {
            "labeled_units": labeled,
            "unknown_outcome_units": unknown,
            "exact_correctness_improved": improvements,
            "exact_correctness_worsened": harms,
            "exact_correctness_unchanged": labeled - improvements - harms,
            "abstention_convention": "not exact-correct; not a calibrated harm measure",
        }
    return {
        "schema_version": "vrs-judgment-influence-descriptive-v1",
        "scope": "bounded memory-branch receipts, not final whole-system judgment",
        "analysis_kind": "post_hoc_development_not_confirmatory",
        "total_selected_units": len(rows),
        "control_invalid_units": len(rows) - len(valid),
        "primary_influence": comparisons,
        "secondary_utility": utility,
        "units": units,
        "causal_identification_established": False,
        "historical_gate_reclassified": False,
        "growth_claimed": False,
        "new_experience_count": 0,
        "confirmation_authorized": False,
        "limitation": "No sham/noise control; no-VRS mechanically blocks promotion. Fractions are descriptive, not population or unique-cause claims.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    result = analyze(json.loads(raw.decode("utf-8"))["raw_units"])
    result["source_report_sha256"] = hashlib.sha256(raw).hexdigest()
    result["analyzer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
