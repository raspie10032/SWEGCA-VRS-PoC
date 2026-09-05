#!/usr/bin/env python3
"""Validate the paper Phase 1 receipt contract and future receipt instances."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/rozephine_swegca_vrs_paper_phase1_receipt_contract_v1.json"
CONTRACT_SCHEMA = "rozephine-swegca-vrs-paper-phase1-receipt-contract-v1"
RECEIPT_SCHEMA = "rozephine-swegca-vrs-paper-experiment-receipt-v1"
MEMORY_ORDER = ["Déjà vu", "Recall", "Replay", "Re-evidence"]
OUTCOME_CLASSES = {"success", "failure", "negative", "uncertain", "conflicting", "pending"}
AUTHORITY_FIELDS = ("semantic", "world", "action", "persistent_write", "model_update", "distribution", "p3")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _required_fields(errors: list[str], section: str, value: dict[str, Any], required: list[str]) -> None:
    missing = [key for key in required if key not in value]
    if missing:
        errors.append(f"{section} missing fields: {missing}")


def validate_contract(config_path: Path = DEFAULT_CONFIG, *, check_environment: bool = True) -> list[str]:
    errors: list[str] = []
    config_path = config_path.resolve()
    root = ROOT if config_path == DEFAULT_CONFIG.resolve() else config_path.parents[1]
    try:
        config = _read_json(config_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cannot read contract: {exc}"]

    raw = config_path.read_bytes()
    _require(errors, not raw.startswith(b"\xef\xbb\xbf"), "contract must be UTF-8 without BOM")
    _require(errors, config.get("schema_version") == CONTRACT_SCHEMA, "contract schema changed")
    _require(errors, config.get("phase") == 1, "contract phase must be 1")
    _require(errors, config.get("status") == "preregistered_for_static_validation", "contract must remain preregistered")

    parent = config.get("parent", {})
    source = root / str(parent.get("local_source_plan", ""))
    _require(errors, source.is_file(), "local source plan missing")
    if source.is_file():
        _require(errors, _sha256(source) == parent.get("local_source_plan_sha256"), "local source plan hash mismatch")
    _require(errors, parent.get("google_drive_reads_allowed") is False, "Phase 1 must not reread the Drive plan")

    registry = config.get("evidence_registry", {})
    _require(errors, set(registry) == {"fixed_135_5m", "gemma_4_e2b", "gpt_5_6_luna"}, "model evidence registry changed")
    for name, row in registry.items():
        _require(errors, "replaceable stateless" in str(row.get("role", "")), f"{name} role must be replaceable and stateless")
        _require(errors, row.get("phase1_execution_allowed") is False, f"{name} execution must be disabled in Phase 1")

    fixed = registry.get("fixed_135_5m", {})
    e2b = registry.get("gemma_4_e2b", {})
    luna = registry.get("gpt_5_6_luna", {})
    _require(errors, fixed.get("current_path_exists") is False, "135.5M missing-path evidence changed")
    _require(errors, fixed.get("current_content_hash_verified") is False, "135.5M cannot claim a current content hash")
    _require(errors, fixed.get("current_execution_availability_established") is False, "135.5M availability cannot be inferred")
    _require(errors, e2b.get("may_temporarily_replace_fixed_135_5m") is True, "E2B substitution boundary missing")
    _require(errors, e2b.get("current_content_hash_recomputed") is False, "E2B Phase 1 must not claim a new full hash")
    _require(errors, "historical_sealed" in str(e2b.get("evidence_tier", "")), "E2B current and historical evidence must remain separated")
    _require(errors, luna.get("model_id") == "gpt-5.6-luna" and luna.get("reasoning_effort") == "low", "Luna identity changed")
    _require(errors, luna.get("current_provider_call_made") is False, "Luna provider must remain uncalled")
    _require(errors, luna.get("current_execution_availability_established") is False, "Luna availability must remain unprobed")

    reference_files = [
        (fixed.get("identity_config_path"), fixed.get("identity_config_sha256")),
        (e2b.get("source_freeze_path"), e2b.get("source_freeze_sha256")),
        (e2b.get("runtime_stack_path"), e2b.get("runtime_stack_sha256")),
        (luna.get("source_freeze_path"), luna.get("source_freeze_sha256")),
    ]
    full = config.get("full_current_reference", {})
    reference_files.append((full.get("source_config_path"), full.get("source_config_sha256")))
    for raw_path, expected in reference_files:
        path = root / str(raw_path or "")
        _require(errors, path.is_file(), f"reference file missing: {raw_path}")
        if path.is_file():
            _require(errors, _sha256(path) == expected, f"reference hash mismatch: {raw_path}")

    if check_environment:
        checkpoint = root / str(fixed.get("expected_checkpoint_path", ""))
        _require(errors, not checkpoint.exists(), "135.5M path availability changed; refresh contract before continuing")
        model = root / str(e2b.get("model_path", ""))
        _require(errors, model.is_file(), "E2B model path missing")
        if model.is_file():
            stat = model.stat()
            expected_stat = e2b.get("current_stat", {})
            for key, actual in (("bytes", stat.st_size), ("mtime_ns", stat.st_mtime_ns), ("inode", stat.st_ino), ("device", stat.st_dev)):
                _require(errors, expected_stat.get(key) == actual, f"E2B current stat changed: {key}")

    _require(errors, config.get("receipt_schema_version") == RECEIPT_SCHEMA, "receipt schema changed")
    required_sections = config.get("required_sections", [])
    rules = config.get("receipt_rules", {})
    _require(errors, set(required_sections) == set(rules), "receipt sections and rules differ")
    _require(errors, rules.get("memory_activation", {}).get("ordered_stages") == MEMORY_ORDER, "memory order changed")
    retrieval_classes = set(rules.get("retrieval", {}).get("required_active_outcome_classes", []))
    _require(errors, retrieval_classes == OUTCOME_CLASSES, "active outcome classes incomplete")
    _require(errors, rules.get("retrieval", {}).get("evaluator_allowlist_used") is False, "evaluator allowlists must be forbidden")
    _require(errors, rules.get("specialist", {}).get("output_is_proposal_only") is True, "specialist output must be proposal only")
    _require(errors, rules.get("resources", {}).get("hot_path_io_allowed") is False, "hot-path I/O must be forbidden")
    _require(errors, rules.get("heldout", {}).get("ordinary_prior_experience_hidden") is False, "held-out cannot hide ordinary cognition")
    profiles = config.get("condition_profiles", {})
    _require(errors, set(profiles) == {"C0", "C1", "C2", "C3", "C4"}, "condition receipt profiles changed")
    expected_stages = {
        "C0": [],
        "C1": [],
        "C2": [],
        "C3": MEMORY_ORDER[:3],
        "C4": MEMORY_ORDER,
    }
    for condition_id, stages in expected_stages.items():
        profile = profiles.get(condition_id, {})
        _require(errors, profile.get("retrieval_executed") is (condition_id != "C0"), f"{condition_id} retrieval execution boundary changed")
        _require(errors, profile.get("memory_activation_stages") == stages, f"{condition_id} memory activation boundary changed")
        expected_classes = set() if condition_id == "C0" else OUTCOME_CLASSES
        _require(errors, set(profile.get("active_outcome_classes", [])) == expected_classes, f"{condition_id} active outcome classes changed")

    boundary = config.get("phase1_boundary", {})
    for key in ("model_calls", "gpu_calls", "new_experience_count", "actual_outcome_count", "resident_queries", "resident_mutations", "google_drive_source_plan_reads"):
        _require(errors, boundary.get(key) == 0, f"Phase 1 boundary {key} must be zero")
    for key in ("experience_assimilation_allowed", "vrs_reconvergence_allowed", "heldout_access_allowed", "full_corpus_enumeration_or_rehash", "growth_claimed"):
        _require(errors, boundary.get(key) is False, f"Phase 1 boundary {key} must be false")

    authority = config.get("authority", {})
    _require(errors, authority.get("identity_owner") == "Rozephine main only", "main identity owner changed")
    _require(errors, authority.get("persistent_cognition_owner") == "Rozephine main only", "main cognition owner changed")
    _require(errors, authority.get("specialists_are_proposal_only") is True, "specialists must remain proposal only")
    for field in AUTHORITY_FIELDS:
        _require(errors, authority.get(field) is False, f"Phase 1 authority {field} must be false")
    return errors


def validate_receipt(receipt: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _require(errors, receipt.get("schema_version") == RECEIPT_SCHEMA, "receipt schema mismatch")
    rules = contract["receipt_rules"]
    for section in contract["required_sections"]:
        value = receipt.get(section)
        if not isinstance(value, dict):
            errors.append(f"missing receipt section: {section}")
            continue
        _required_fields(errors, section, value, rules[section]["required_fields"])
    if errors:
        return errors

    run = receipt["run"]
    main = receipt["main_before"]
    retrieval = receipt["retrieval"]
    activation = receipt["memory_activation"]
    specialist = receipt["specialist"]
    judgment = receipt["judgment"]
    outcome = receipt["outcome"]
    successor = receipt["successor"]
    accounting = receipt["accounting"]
    resources = receipt["resources"]
    authority = receipt["authority"]
    heldout = receipt["heldout"]
    condition_id = run["condition_id"]
    profile = contract.get("condition_profiles", {}).get(condition_id)
    _require(errors, isinstance(profile, dict), "unknown condition receipt profile")
    if not isinstance(profile, dict):
        return errors

    _require(errors, main["identity_owner"] == "Rozephine main only", "receipt transfers identity away from main")
    _require(errors, main["persistent_cognition_owner"] == "Rozephine main only", "receipt transfers persistent cognition away from main")
    _require(errors, main["full_current_addressable"] is True, "receipt lacks full-current addressability")
    _require(errors, main["lookup_requires_io"] is False, "receipt permits hot lookup I/O")
    _require(errors, retrieval["snapshot_id"] == main["pair_snapshot_id"], "retrieval snapshot differs from main snapshot")
    retrieval_expected = profile["retrieval_executed"]
    _require(errors, retrieval["executed"] is retrieval_expected, "retrieval execution differs from condition")
    _require(errors, retrieval["runtime_selected"] is retrieval_expected, "runtime retrieval selection differs from condition")
    _require(errors, retrieval["evaluator_allowlist_used"] is False, "evaluator allowlist used")
    _require(errors, set(retrieval["active_outcome_classes"]) == set(profile["active_outcome_classes"]), "receipt outcome classes differ from condition")
    _require(errors, set(retrieval["selected_addresses"]).issubset(set(retrieval["candidate_addresses"])), "selected address not in candidates")
    _require(errors, set(retrieval["rejected_addresses"]).issubset(set(retrieval["candidate_addresses"])), "rejected address not in candidates")
    if not retrieval_expected:
        for field in ("candidate_addresses", "selected_addresses", "rejected_addresses", "provenance_revisions", "rationales", "rejection_evidence"):
            _require(errors, not retrieval[field], f"C0 retrieval payload must be empty: {field}")
    expected_stages = profile["memory_activation_stages"]
    _require(errors, activation["executed"] is bool(expected_stages), "memory activation execution differs from condition")
    _require(errors, activation["ordered_stages"] == expected_stages, "memory activation order invalid")
    _require(errors, activation["snapshot_id"] == main["pair_snapshot_id"], "memory stages use a different snapshot")
    _require(errors, len(activation["stage_receipts"]) == len(expected_stages), "memory stage receipt count differs from condition")
    _require(errors, all(stage.get("snapshot_id") == main["pair_snapshot_id"] for stage in activation["stage_receipts"]), "memory stage snapshot mismatch")

    _require(errors, specialist["replaceable"] is True and specialist["stateless"] is True, "specialist is not replaceable and stateless")
    _require(errors, specialist["input_sha256"] == run["input_sha256"], "specialist input digest differs from run input")
    _require(errors, specialist["output_is_proposal_only"] is True, "specialist output claims authority")
    _require(errors, specialist["persistent_state_owned"] is False, "specialist owns persistent state")
    _require(errors, specialist["main_mutable_reference_received"] is False, "specialist received mutable main state")
    _require(errors, specialist["context_destroyed_after_request"] is True, "specialist context not destroyed")
    _require(errors, specialist["cache_destroyed_after_request"] is True, "specialist cache not destroyed")

    _require(errors, judgment["main_arbitrated"] is True, "main did not arbitrate")
    _require(errors, judgment["falsification_first"] is True, "arbitration is not falsification-first")
    _require(errors, not judgment["conflict_detected"] or judgment["abstained"], "unresolved conflict did not abstain")
    _require(errors, outcome["outcome_class"] in rules["outcome"]["allowed_classes"], "outcome class invalid")
    if outcome["assimilated"]:
        _require(errors, outcome["actual_outcome_observed"] is True, "assimilation lacks an actual outcome")
        _require(errors, successor["published"] is True, "assimilated outcome lacks a successor")
        _require(errors, successor["atomic_copy_on_write"] is True and successor["compare_and_swap"] is True, "successor is not atomic COW/CAS")
        _require(errors, successor["pair_snapshot_id"] != main["pair_snapshot_id"], "published successor did not replace the pair snapshot")
    else:
        _require(errors, successor["published"] is False, "successor published without assimilation")

    _require(errors, accounting["distinct_source_episodes"] >= 0 and accounting["actual_outcomes"] >= 0, "episode accounting cannot be negative")
    _require(errors, resources["elapsed_ns"] >= 0 and resources["cpu_time_ns"] >= 0, "resource clocks cannot be negative")
    _require(errors, resources["hot_path_disk_json_sqlite_network_or_hash_io"] is False, "receipt reports forbidden hot-path I/O")
    for field in AUTHORITY_FIELDS:
        _require(errors, authority[field] is False, f"receipt grants {field} authority")
    _require(errors, heldout["accessed_during_development"] is False, "held-out accessed during development")
    _require(errors, heldout["used_for_code_threshold_weight_or_curriculum_selection"] is False, "held-out used for selection")
    _require(errors, heldout["ordinary_prior_experience_hidden"] is False, "held-out hid ordinary cognition")

    if run["growth_claimed"]:
        _require(errors, run["synthetic_fixture"] is False, "synthetic fixture cannot claim growth")
        _require(errors, accounting["distinct_source_episodes"] > 0, "growth lacks a distinct source episode")
        _require(errors, accounting["actual_outcomes"] > 0, "growth lacks an actual outcome")
        _require(errors, outcome["actual_outcome_observed"] is True and outcome["assimilated"] is True, "growth lacks outcome assimilation")
        _require(errors, successor["published"] is True, "growth lacks an atomic successor")
        proof = receipt.get("longitudinal_proof", {})
        _require(errors, proof.get("later_source_diverse_change_proven") is True, "growth lacks later source-diverse change")
        _require(errors, proof.get("retention_proven") is True, "growth lacks retention")
        _require(errors, proof.get("correction_or_abstention_proven") is True, "growth lacks correction or abstention")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--skip-environment-check", action="store_true")
    args = parser.parse_args()
    errors = validate_contract(args.config, check_environment=not args.skip_environment_check)
    if not errors and args.receipt:
        errors.extend(validate_receipt(_read_json(args.receipt), _read_json(args.config)))
    result = {
        "status": "FAIL" if errors else "PASS",
        "phase": 1,
        "contract_schema": CONTRACT_SCHEMA,
        "receipt_schema": RECEIPT_SCHEMA,
        "errors": errors,
        "growth_claimed": False,
        "model_calls": 0,
        "gpu_calls": 0,
        "resident_queries": 0,
        "drive_source_plan_reads": 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
