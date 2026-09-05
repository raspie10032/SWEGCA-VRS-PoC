#!/usr/bin/env python3
"""Run the preregistered Phase 5 E2B-to-135.5M/Luna swap diagnostic."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from tinylm_slicer.mosaic_luna_persistent_conversation import (
    verify_distinct_fresh_workers,
)
from tools.run_rozephine_swegca_vrs_paper_phase3_re_evidence import (
    AUTHORITY_FALSE,
    _c4_main_result,
    _json,
    _load_main_state,
    _memory_trace,
    _paper_receipt,
    _resident_main,
    _run_luna,
    _run_small,
    _sha256,
    _socket_request,
    _state_bits,
    _write_json,
    _write_jsonl,
)
from tools.run_rozephine_swegca_vrs_paper_phase3_re_evidence import (
    _validate_config as _validate_phase3_config,
)
from tools.validate_rozephine_swegca_vrs_paper_phase1_receipt_contract import (
    validate_receipt,
)

SCHEMA = "rozephine-swegca-vrs-paper-phase5-specialist-swap-run-v1"
CONFIG_SCHEMA = "rozephine-swegca-vrs-paper-phase5-specialist-swap-v1"
MODEL_KEYS = ("S", "L")


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _resolve(value: object) -> Path:
    path = Path(str(value))
    return (path if path.is_absolute() else ROOT / path).resolve(strict=True)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"JSONL objects required: {path}")
    return rows


def _validate_config(config_path: Path, config: Mapping[str, Any]) -> None:
    if (
        config.get("schema_version") != CONFIG_SCHEMA
        or config.get("phase") != 5
        or config.get("status") != "preregistered_before_phase5_model_outputs"
        or config.get("growth_claimed") is not False
    ):
        raise ValueError("Phase 5 preregistration changed")
    if tuple(config.get("post_swap_model_keys", ())) != MODEL_KEYS:
        raise ValueError("Phase 5 swap model order changed")
    tasks = config.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 3:
        raise ValueError("Phase 5 requires three frozen development tasks")
    if any(
        task.get("split") != "development"
        or task.get("is_final_confirmation") is not False
        or task.get("pre_swap_main_verdict") != "refute"
        for task in tasks
    ):
        raise ValueError("Phase 5 task boundary changed")
    references = [
        (config["runner"]["path"], config["runner"]["sha256"]),
        (config["test"]["path"], config["test"]["sha256"]),
        (config["parent"]["phase0_contract"], config["parent"]["phase0_contract_sha256"]),
        (config["parent"]["phase1_receipt_contract"], config["parent"]["phase1_receipt_contract_sha256"]),
        (config["parent"]["phase3_config"], config["parent"]["phase3_config_sha256"]),
        (config["parent"]["phase4_config"], config["parent"]["phase4_config_sha256"]),
        (config["parent"]["phase4_report"], config["parent"]["phase4_report_sha256"]),
        (config["parent"]["source_plan"], config["parent"]["source_plan_sha256"]),
        (config["source_run"]["frozen_inputs"], config["source_run"]["frozen_inputs_sha256"]),
        (config["source_run"]["resident_projection"], config["source_run"]["resident_projection_sha256"]),
        (config["source_run"]["pre_swap_receipts"], config["source_run"]["pre_swap_receipts_sha256"]),
        (config["source_run"]["phase4_report"], config["source_run"]["phase4_report_sha256"]),
    ]
    for model in config["models"].values():
        for path_key, hash_key in (
            ("runner", "runner_sha256"),
            ("manifest", "manifest_sha256"),
            ("source_freeze", "source_freeze_sha256"),
            ("worker_module", "worker_module_sha256"),
        ):
            if path_key in model:
                references.append((model[path_key], model[hash_key]))
    for raw_path, expected in references:
        if _sha256(_resolve(raw_path)) != expected:
            raise ValueError(f"frozen Phase 5 artifact changed: {raw_path}")
    boundary = config["specialist_swap_boundary"]
    if (
        boundary.get("pre_swap_specialist") != "M"
        or boundary.get("post_swap_specialists") != ["S", "L"]
        or boundary.get("same_sealed_request_bytes") is not True
        or boundary.get("same_main_owned_snapshot") is not True
        or boundary.get("main_identity_or_state_transferred") is not False
        or boundary.get("raw_prior_model_context_visible") is not False
    ):
        raise ValueError("Phase 5 specialist-swap boundary changed")
    resources = config["resource_boundary"]
    if (
        resources.get("E2B_calls") != 0
        or resources.get("new_135_5M_loads") != 1
        or resources.get("Luna_calls") != 3
        or resources.get("heldout_reads") != 0
        or resources.get("resident_restarts") != 0
    ):
        raise ValueError("Phase 5 resource boundary changed")
    if config_path.read_bytes().startswith(b"\xef\xbb\xbf"):
        raise ValueError("Phase 5 config must be UTF-8 without BOM")


def _capacity(output: Path, maximum_runtime_bytes: int) -> dict[str, Any]:
    home = shutil.disk_usage(output.parent)
    e_drive = shutil.disk_usage(Path("/run/media/raspie/NVMe 4.0 1TB"))
    return {
        "home_total_bytes": home.total,
        "home_available_bytes": home.free,
        "maximum_runtime_bytes": maximum_runtime_bytes,
        "home_twenty_percent_floor_preserved": home.free - maximum_runtime_bytes >= home.total * 0.2,
        "E_drive_total_bytes": e_drive.total,
        "E_drive_available_bytes": e_drive.free,
        "E_drive_writes": 0,
        "E_drive_twenty_percent_floor_preserved": e_drive.free >= e_drive.total * 0.2,
    }


def _correct_luna_accounting(results: Mapping[str, dict[str, Any]]) -> None:
    for result in results.values():
        usage = result.get("transport", {}).get("usage", {})
        if not isinstance(usage, dict):
            result["token_count"] = None
            continue
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            result["token_count"] = input_tokens + output_tokens
            result["transport"]["corrected_usage"] = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_plus_output_tokens": input_tokens + output_tokens,
                "cached_input_tokens_component": usage.get("cached_input_tokens"),
                "reasoning_output_tokens_component": usage.get("reasoning_output_tokens"),
                "components_not_double_counted": True,
            }
        else:
            result["token_count"] = None


def run(config_path: Path, output: Path) -> dict[str, Any]:
    config_path = config_path.resolve(strict=True)
    config = _json(config_path)
    _validate_config(config_path, config)
    phase3_path = _resolve(config["parent"]["phase3_config"])
    phase3 = _json(phase3_path)
    _validate_phase3_config(phase3_path, phase3)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    capacity = _capacity(output, int(config["resource_boundary"]["maximum_runtime_bytes"]))
    if not capacity["home_twenty_percent_floor_preserved"]:
        raise OSError("Phase 5 runtime would violate the home 20% floor")
    if not capacity["E_drive_twenty_percent_floor_preserved"]:
        raise OSError("E: is below its hard 20% free-space floor")
    output.mkdir(mode=0o700, parents=True)
    started_at = _now()
    _write_json(
        output / "attempt.json",
        {
            "schema_version": SCHEMA,
            "status": "frozen_before_phase5_model_outputs",
            "started_at": started_at,
            "config": str(config_path),
            "config_sha256": _sha256(config_path),
            "capacity": capacity,
            "growth_claimed": False,
            "heldout_accessed": False,
            "persistent_mutation_allowed": False,
            "authority": dict(AUTHORITY_FALSE),
        },
    )
    all_rows = _jsonl(_resolve(config["source_run"]["frozen_inputs"]))
    row_map = {str(row["id"]): row for row in all_rows}
    task_ids = [str(task["task_id"]) for task in config["tasks"]]
    rows = [row_map[f"C4:{task_id}"] for task_id in task_ids]
    for task, row in zip(config["tasks"], rows, strict=True):
        if (
            row["serialized_input_sha256"] != task["input_sha256"]
            or row["serialized_input_utf8_bytes"] != task["input_bytes"]
        ):
            raise ValueError("Phase 5 task prompt bytes changed")
    inputs = output / "sealed_inputs.jsonl"
    _write_jsonl(inputs, rows)
    pre_receipts = _jsonl(_resolve(config["source_run"]["pre_swap_receipts"]))
    pre_map = {str(receipt["run"]["task_id"]): receipt for receipt in pre_receipts}
    if set(pre_map) != set(task_ids):
        raise ValueError("Phase 5 pre-swap E2B receipts changed")
    receipt_contract = _json(_resolve(config["parent"]["phase1_receipt_contract"]))
    pre_errors = {
        task_id: errors
        for task_id, receipt in pre_map.items()
        if (errors := validate_receipt(receipt, receipt_contract))
    }
    if pre_errors:
        raise ValueError(f"pre-swap E2B receipts failed validation: {pre_errors}")
    resident = _json(_resolve(config["source_run"]["resident_projection"]))
    socket_path = Path(phase3["full_current"]["resident_socket"])
    resident_before = _resident_main(_socket_request(socket_path, {"command": "status"}))
    if resident_before != resident["main"]:
        raise ValueError("resident pair changed before Phase 5")
    main_state = _load_main_state({**phase3, "models": {**phase3["models"], "S": config["models"]["S"]}})
    main_state_before = _state_bits(main_state)
    _write_jsonl(output / "pre_swap_E2B_receipts.jsonl", pre_receipts)
    _write_json(
        output / "pre_model_freeze.json",
        {
            "status": "phase5_inputs_expectations_and_swap_boundary_frozen",
            "config_sha256": _sha256(config_path),
            "sealed_inputs_sha256": _sha256(inputs),
            "task_input_sha256": {task_id: row_map[f"C4:{task_id}"]["serialized_input_sha256"] for task_id in task_ids},
            "pre_swap_receipt_ids": {task_id: pre_map[task_id]["run"]["receipt_id"] for task_id in task_ids},
            "post_swap_model_order": list(MODEL_KEYS),
            "model_outputs_observed": False,
        },
    )
    merged = {
        **phase3,
        "attempt_started_at": started_at,
        "models": {**phase3["models"], **config["models"]},
    }
    prompts = {str(row["id"]): str(row["serialized_input"]) for row in rows}
    results = {
        "S": _run_small(merged, rows, inputs, output),
        "L": _run_luna(merged, rows, prompts, output),
    }
    _correct_luna_accounting(results["L"])
    _write_json(output / "model_L_outputs.json", results["L"])
    task_map = {str(task["task_id"]): task for task in phase3["tasks"]}
    receipts: list[dict[str, Any]] = []
    errors: dict[str, list[str]] = {}
    cells: dict[str, Any] = {}
    for model_key in MODEL_KEYS:
        for task_id in task_ids:
            row = row_map[f"C4:{task_id}"]
            task = task_map[task_id]
            result = results[model_key][str(row["id"])]
            trace = _memory_trace(task, "C4", resident["main"]["pair_snapshot_id"])
            main_result = _c4_main_result(main_state, model_key, str(row["id"]), str(row["serialized_input"]), result, task)
            receipt = _paper_receipt(
                config=merged,
                model_key=model_key,
                condition="C4",
                task=task,
                row=row,
                result=result,
                resident=resident,
                trace=trace,
                main_result=main_result,
            )
            receipt["run"]["receipt_id"] = f"phase5-M-to-{model_key}-C4-{task_id}"
            receipt["run"]["phase"] = 5
            receipt["accounting"]["distinct_source_episodes"] = 0
            receipt["accounting"]["addressed_existing_source_episodes"] = 1
            receipt["accounting"]["repetitions"] = 1
            pre = pre_map[task_id]
            post_verdict = receipt["judgment"]["detached_condition_verdict"]
            receipt["specialist_swap"] = {
                "pre_swap_specialist_id": pre["specialist"]["specialist_id"],
                "post_swap_specialist_id": receipt["specialist"]["specialist_id"],
                "pre_swap_input_sha256": pre["run"]["input_sha256"],
                "post_swap_input_sha256": receipt["run"]["input_sha256"],
                "identical_sealed_request_bytes": pre["run"]["input_sha256"] == receipt["run"]["input_sha256"],
                "same_main_pair_snapshot": pre["main_before"]["pair_snapshot_id"] == receipt["main_before"]["pair_snapshot_id"],
                "pre_swap_main_verdict": pre["judgment"]["detached_condition_verdict"],
                "post_swap_main_verdict": post_verdict,
                "exact_verdict_retained": pre["judgment"]["detached_condition_verdict"] == post_verdict,
                "safe_refute_or_abstain": post_verdict == "refute" or receipt["judgment"]["abstained"],
                "raw_prior_model_context_visible": False,
                "main_identity_or_state_transferred": False,
                "continuity_owner": "Rozephine main-owned external Experience/VRS snapshot",
            }
            validation = validate_receipt(receipt, receipt_contract)
            key = f"{model_key}:{task_id}"
            if validation:
                errors[key] = validation
            receipts.append(receipt)
            cells[key] = {
                "transport_success": bool(receipt["specialist"]["transport"].get("success")),
                "strict_parse": receipt["judgment"]["worker_decision"] is not None,
                "pre_swap_verdict": receipt["specialist_swap"]["pre_swap_main_verdict"],
                "post_swap_verdict": post_verdict,
                "exact_verdict_retained": receipt["specialist_swap"]["exact_verdict_retained"],
                "safe_refute_or_abstain": receipt["specialist_swap"]["safe_refute_or_abstain"],
                "historical_support_reused": receipt["judgment"]["historical_support_reused"],
                "same_request_bytes": receipt["specialist_swap"]["identical_sealed_request_bytes"],
                "same_main_pair": receipt["specialist_swap"]["same_main_pair_snapshot"],
            }
    _write_jsonl(output / "post_swap_receipts.jsonl", receipts)
    luna_transports = [
        receipt["specialist"]["transport"]
        for receipt in receipts
        if receipt["specialist_swap"]["post_swap_specialist_id"] == config["models"]["L"]["specialist_id"]
    ]
    fresh_luna_workers = verify_distinct_fresh_workers(luna_transports)
    main_state_after = _state_bits(main_state)
    resident_after = _resident_main(_socket_request(socket_path, {"command": "status"}))
    safe_count = sum(cell["safe_refute_or_abstain"] for cell in cells.values())
    retained_count = sum(cell["exact_verdict_retained"] for cell in cells.values())
    s_cells = [cells[f"S:{task_id}"] for task_id in task_ids]
    l_cells = [cells[f"L:{task_id}"] for task_id in task_ids]
    passed = (
        not errors
        and len(receipts) == 6
        and all(cell["transport_success"] for cell in cells.values())
        and all(cell["same_request_bytes"] and cell["same_main_pair"] for cell in cells.values())
        and all(not cell["historical_support_reused"] for cell in cells.values())
        and safe_count == 6
        and all(cell["post_swap_verdict"] == "refute" for cell in l_cells)
        and all(cell["post_swap_verdict"] in {"refute", "insufficient", "conflict"} for cell in s_cells)
        and fresh_luna_workers
        and main_state_before == main_state_after
        and resident_before == resident_after
        and all(not any(receipt["authority"].values()) for receipt in receipts)
    )
    report = {
        "schema_version": SCHEMA,
        "status": "phase5_specialist_swap_execution_complete" if passed else "phase5_specialist_swap_contract_failed",
        "completed_at": _now(),
        "passed": passed,
        "phase_complete": passed,
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "pre_swap_specialist": config["pre_swap_specialist"],
        "post_swap_specialists": [config["models"][key]["specialist_id"] for key in MODEL_KEYS],
        "cell_count": len(receipts),
        "cell_summary": cells,
        "safe_refute_or_abstain_count": safe_count,
        "exact_verdict_retention_count": retained_count,
        "strict_parse_count": sum(cell["strict_parse"] for cell in cells.values()),
        "fresh_distinct_luna_workers": fresh_luna_workers,
        "receipt_validation_errors": errors,
        "resident_pair_unchanged": resident_before == resident_after,
        "detached_main_state_bit_exact": main_state_before == main_state_after,
        "new_distinct_source_episode_count": 0,
        "addressed_existing_source_episode_count": 6,
        "actual_outcome_count": 0,
        "generated_row_count": 6,
        "repetition_count": 6,
        "experience_assimilation_count": 0,
        "vrs_reconvergence_count": 0,
        "growth_claimed": False,
        "heldout_accessed": False,
        "authority": dict(AUTHORITY_FALSE),
        "capacity": capacity,
        "Rozephine의 판단": (
            "동일 main-owned Experience/VRS lineage는 E2B가 135.5M 또는 Luna로 교체된 뒤에도 "
            "주소와 provenance를 유지했다. Worker capability가 부족하면 main은 과거 support를 "
            "재사용하지 않고 abstain하며, worker 출력은 persistent authority가 아니다."
        ),
        "Codex의 판단": (
            "Phase 5는 same-corpus E2B-to-S/L swap diagnostic이다. 정확 verdict retention과 "
            "safe boundary를 분리하며, source-diverse growth나 final confirmation을 주장하지 않는다."
        ),
        "Codex 작업 실수 및 교정": list(config["codex_errors_before_model_outputs"]),
    }
    _write_json(output / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/rozephine_swegca_vrs_paper_phase5_specialist_swap_v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.config, args.output)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
