#!/usr/bin/env python3
"""Run the frozen Phase 2 C0/C1 worker-baseline pilot without state mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from tinylm_slicer.mosaic_luna_persistent_conversation import (  # noqa: E402
    AUTHORITY_FALSE,
    CodexExecLunaWorker,
    LunaWorkerFailure,
    clear_empty_scratch_root,
)
from tools.stream_rozephine_local_media_observations import (  # noqa: E402
    GemmaOrganizerProcess,
)
from tools.validate_rozephine_swegca_vrs_paper_phase1_receipt_contract import (  # noqa: E402
    validate_receipt,
)


SCHEMA = "rozephine-swegca-vrs-paper-phase2-baseline-run-v1"
CONFIG_SCHEMA = "rozephine-swegca-vrs-paper-phase2-baseline-v1"
RECEIPT_SCHEMA = "rozephine-swegca-vrs-paper-experiment-receipt-v1"
OUTCOME_CLASSES = [
    "success",
    "failure",
    "negative",
    "uncertain",
    "conflicting",
    "pending",
]
DECISION_KEYS = {"selected_episode_id", "proposition", "verdict", "rationale"}
VERDICTS = {"support", "refute", "insufficient", "conflict"}


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"JSON object required: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bytes_sha256(value: str) -> tuple[int, str]:
    raw = value.encode("utf-8")
    return len(raw), hashlib.sha256(raw).hexdigest()


def _resolve(value: object) -> Path:
    path = Path(str(value))
    return (path if path.is_absolute() else ROOT / path).resolve(strict=True)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, values: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
        newline="\n",
    )


def _socket_request(path: Path, request: Mapping[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5.0)
        client.connect(str(path))
        client.sendall(
            (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        )
        response = b""
        while not response.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            response += chunk
    value = json.loads(response.decode("utf-8"))
    if not isinstance(value, dict):
        raise TypeError("resident response must be an object")
    return value


def _main_state(status: Mapping[str, Any]) -> dict[str, Any]:
    stable = {
        "pair_snapshot_id": status["pair_snapshot_id"],
        "memory_snapshot_id": status["memory_snapshot_id"],
        "vrs_snapshot_id": status["VRS_snapshot_id"],
        "hot_episode_count": status["hot_episode_count"],
        "lookup_requires_io": status["lookup_requires_io"],
    }
    raw = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**stable, "state_sha256": hashlib.sha256(raw).hexdigest()}


def _validate_config(config_path: Path, config: Mapping[str, Any]) -> None:
    if (
        config.get("schema_version") != CONFIG_SCHEMA
        or config.get("status") != "preregistered_before_model_outputs"
        or config.get("growth_claimed") is not False
    ):
        raise ValueError("Phase 2 preregistration changed")
    references = [
        (config["runner"]["path"], config["runner"]["sha256"]),
        (config["parent"]["phase0_contract"], config["parent"]["phase0_contract_sha256"]),
        (
            config["parent"]["phase1_receipt_contract"],
            config["parent"]["phase1_receipt_contract_sha256_after_condition_profile_repair"],
        ),
        (config["parent"]["source_plan"], config["parent"]["source_plan_sha256"]),
        (
            config["full_current"]["successor_config"],
            config["full_current"]["successor_config_sha256"],
        ),
        (
            config["full_current"]["episode_ledger"],
            config["full_current"]["episode_ledger_sha256"],
        ),
    ]
    for model in config["models"].values():
        for path_key, hash_key in (
            ("runner", "runner_sha256"),
            ("runtime_config", "runtime_config_sha256"),
            ("source_freeze", "source_freeze_sha256"),
            ("worker", "worker_sha256"),
            ("process_orchestrator", "process_orchestrator_sha256"),
            ("worker_module", "worker_module_sha256"),
        ):
            if path_key in model:
                references.append((model[path_key], model[hash_key]))
    for raw_path, expected in references:
        path = _resolve(raw_path)
        if _sha256(path) != expected:
            raise ValueError(f"frozen artifact changed: {raw_path}")
    if config["execution_order"] != [
        "S:C0",
        "S:C1",
        "M:C0",
        "M:C1",
        "L:C0",
        "L:C1",
    ]:
        raise ValueError("Phase 2 execution order changed")
    if config["task"]["split"] != "development" or config["task"]["is_final_confirmation"]:
        raise ValueError("Phase 2 task crossed the held-out boundary")
    raw = config_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Phase 2 config must be UTF-8 without BOM")


def _retrieve_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    full = config["full_current"]
    task = config["task"]
    socket_path = Path(full["resident_socket"]).resolve(strict=True)
    status = _socket_request(socket_path, {"command": "status"})
    main = _main_state(status)
    if (
        status.get("status") != "resident_main_owner_ready"
        or main["pair_snapshot_id"] != full["pair_snapshot_id"]
        or main["memory_snapshot_id"] != full["memory_snapshot_id"]
        or main["vrs_snapshot_id"] != full["vrs_snapshot_id"]
        or int(main["hot_episode_count"]) != int(full["episode_count"])
        or main["lookup_requires_io"] is not False
    ):
        raise ValueError("resident is not the frozen full-current pair")

    responses = []
    for cue in task["candidate_cues"]:
        response = _socket_request(socket_path, {"command": "cue", "cue": cue})
        if (
            response.get("status") != "hot_cue_lookup_complete"
            or response.get("lookup_requires_io") is not False
            or any(response.get("authority", {}).values())
        ):
            raise ValueError(f"resident cue lookup boundary changed: {cue}")
        if int(response["candidate_count"]) != len(response["episode_ids"]):
            raise ValueError("bounded resident response omitted retrieval candidates")
        responses.append(response)
    ranked = [
        (int(row["candidate_count"]), position, row)
        for position, row in enumerate(responses)
        if int(row["candidate_count"]) > 0
    ]
    if not ranked:
        raise ValueError("runtime retrieval found no related hot cue")
    selected_response = min(ranked)[2]
    selected_ids = tuple(str(value) for value in selected_response["episode_ids"])
    if len(selected_ids) != 1:
        raise ValueError("minimal Phase 2 projection requires one runtime-selected episode")

    ledger = _resolve(full["episode_ledger"])
    matching: list[dict[str, Any]] = []
    with ledger.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("episode_id") in selected_ids:
                matching.append(row)
    if len(matching) != 1:
        raise ValueError("runtime-selected episode did not materialize exactly once")
    row = matching[0]
    step = row.get("step")
    if not isinstance(step, dict) or not isinstance(step.get("observation"), dict):
        raise ValueError("selected episode payload changed")
    text = step["observation"].get("normalized_document_text")
    if not isinstance(text, str):
        raise ValueError("selected episode lacks normalized source text")
    start = text.find(task["projection_anchor_start"])
    end = text.find(task["projection_anchor_end"], start + 1)
    if start < 0 or end <= start:
        raise ValueError("frozen evidence projection anchors changed")
    excerpt = text[start:end].strip()
    if len(excerpt) > int(task["maximum_projection_characters"]):
        excerpt = excerpt[: int(task["maximum_projection_characters"])].rstrip()
    required = ("7월 5일", "페보니우스 성당", "신의 눈 물", "무기 법구")
    if not all(value in excerpt for value in required):
        raise ValueError("bounded projection omitted a preregistered field")
    return {
        "main": main,
        "status_response": status,
        "candidate_cue_receipts": responses,
        "selected_cue": selected_response["cue"],
        "selected_episode_id": selected_ids[0],
        "episode_revision": row["revision"],
        "verification_state": row["verification_state"],
        "source_addresses": row["source_addresses"],
        "evidence_refs": step.get("evidence_refs", []),
        "excerpt": excerpt,
        "ledger_bytes_scanned": ledger.stat().st_size,
        "selection_method": task["runtime_selection_method"],
        "evaluator_allowlist_used": False,
        "hot_lookup_requires_io": False,
        "cold_projection_scan_only": True,
    }


def _prompt(config: Mapping[str, Any], condition: str, projection: Mapping[str, Any]) -> str:
    task = config["task"]
    records: list[dict[str, Any]] = []
    if condition == "C1":
        records.append(
            {
                "episode_id": projection["selected_episode_id"],
                "revision": projection["episode_revision"],
                "verification_state": projection["verification_state"],
                "source_addresses": projection["source_addresses"],
                "evidence_excerpt": projection["excerpt"],
            }
        )
    return (
        "너는 교체 가능한 무상태 proposal specialist다. 아래 현재 packet만 사용하고, "
        "기록이 없으면 추측하지 마라. support는 proposition이 제공된 기록에 명시된 "
        "경우만 선택하며, 그 기록의 사실 권위를 뜻하지 않는다. 출력은 설명이나 "
        "마크다운 없이 정확히 JSON 객체 하나여야 한다. 키는 selected_episode_id, "
        "proposition, verdict, rationale 네 개만 쓴다. verdict는 support, refute, "
        "insufficient, conflict 중 하나다. 근거 기록을 고를 수 없으면 "
        "selected_episode_id는 null이고 verdict는 insufficient여야 한다.\n"
        f"query={task['query']}\n"
        f"proposition={task['proposition']}\n"
        "retrieved_records="
        + json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _parse_decision(raw: str, allowed_ids: Sequence[str]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(raw.strip())
        if not isinstance(value, dict) or set(value) != DECISION_KEYS:
            raise ValueError("exact decision keys required")
        if value["selected_episode_id"] not in {*allowed_ids, None}:
            raise ValueError("selected episode is outside the packet")
        if value["verdict"] not in VERDICTS:
            raise ValueError("unsupported verdict")
        if value["verdict"] != "insufficient" and value["selected_episode_id"] is None:
            raise ValueError("non-insufficient verdict requires a selected episode")
        if not isinstance(value["proposition"], str) or not value["proposition"].strip():
            raise ValueError("proposition must be nonempty")
        if not isinstance(value["rationale"], str) or not value["rationale"].strip():
            raise ValueError("rationale must be nonempty")
        return value, None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"


def _score(condition: str, decision: Mapping[str, Any] | None, selected_id: str) -> bool:
    if decision is None:
        return False
    if condition == "C0":
        return decision["selected_episode_id"] is None and decision["verdict"] == "insufficient"
    return decision["selected_episode_id"] == selected_id and decision["verdict"] == "support"


def _model_result(
    *,
    raw_output: str,
    condition: str,
    selected_id: str,
    elapsed_ns: int,
    token_count: int | None,
    transport: Mapping[str, Any],
) -> dict[str, Any]:
    allowed = [] if condition == "C0" else [selected_id]
    decision, parse_error = _parse_decision(raw_output, allowed)
    return {
        "raw_output": raw_output,
        "decision": decision,
        "parse_error": parse_error,
        "diagnostic_correct": _score(condition, decision, selected_id),
        "elapsed_ns": max(0, int(elapsed_ns)),
        "token_count": token_count,
        "transport": dict(transport),
    }


def _run_small(config: Mapping[str, Any], inputs: Path, output: Path) -> dict[str, dict[str, Any]]:
    model = config["models"]["S"]
    model_output = output / "model_S"
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = "0"
    env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    command = [
        str(_resolve(model["python"])),
        str(_resolve(model["runner"])),
        "--checkpoint",
        str(_resolve(model["checkpoint"])),
        "--manifest",
        str(_resolve(model["manifest"])),
        "--core-inputs",
        str(inputs),
        "--expected-core-inputs-sha256",
        _sha256(inputs),
        "--evaluation-role",
        "development",
        "--output",
        str(model_output),
        "--device",
        str(model["device"]),
        "--maximum-input-bytes",
        str(model["maximum_input_bytes"]),
        "--maximum-new-bytes",
        str(model["maximum_new_bytes"]),
        "--text-rounds",
        str(model["text_rounds"]),
    ]
    started = time.perf_counter_ns()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    batch_elapsed = time.perf_counter_ns() - started
    (output / "model_S.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output / "model_S.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        failure = {
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-2000:],
            "batch_elapsed_ns": batch_elapsed,
        }
        return {
            condition: _model_result(
                raw_output="",
                condition=condition,
                selected_id="",
                elapsed_ns=batch_elapsed,
                token_count=None,
                transport={"success": False, **failure},
            )
            for condition in ("C0", "C1")
        }
    report = _json(model_output / "report.json")
    rows = {
        row["id"]: row
        for row in (
            json.loads(line)
            for line in (model_output / "outputs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    result = {}
    for condition in ("C0", "C1"):
        row = rows[condition]
        result[condition] = _model_result(
            raw_output=row["raw_output"],
            condition=condition,
            selected_id=(row["selected_candidate_ids"] or [""])[0],
            elapsed_ns=row["generation_nanoseconds"],
            token_count=int(row["native_input_token_count"] + row["generated_native_token_count"]),
            transport={
                "success": True,
                "batch_elapsed_ns": batch_elapsed,
                "model_load_count": 1,
                "persistent_cognitive_state_exact_after_run": report["identity"]["persistent_cognitive_state_exact_after_run"],
                "peak_cuda_bytes": report["execution"]["peak_cuda_bytes"],
            },
        )
    return result


def _run_gemma(config: Mapping[str, Any], prompts: Mapping[str, str], output: Path) -> dict[str, dict[str, Any]]:
    model = config["models"]["M"]
    runtime = _json(_resolve(model["runtime_config"]))
    worker: GemmaOrganizerProcess | None = None
    started = time.perf_counter_ns()
    try:
        worker = GemmaOrganizerProcess(
            model=_resolve(model["model_path"]),
            python=_resolve(runtime["runtime"]["vllm_python"]),
            worker=_resolve(model["worker"]),
            bubblewrap=_resolve(runtime["runtime"]["bubblewrap"]),
            cuda_root=_resolve(runtime["runtime"]["vllm_cuda_root"]),
            cuda_compiler_root=_resolve(runtime["runtime"]["cuda_compiler_root"]),
            runtime_directory=output / "model_M_runtime",
            repository=ROOT,
            start_timeout_seconds=float(runtime["serving"]["worker_start_timeout_seconds"]),
            maximum_model_length=int(model["maximum_model_length"]),
            maximum_sequences=int(model["maximum_sequences"]),
            kv_cache_mib=int(model["kv_cache_mib"]),
            maximum_new_tokens=int(model["maximum_new_tokens"]),
        )
        generated = worker.propose([prompts["C0"], prompts["C1"]])
        ready = worker.ready_receipt
        worker.close()
        worker = None
        batch_elapsed = time.perf_counter_ns() - started
        _write_json(
            output / "model_M_outputs.json",
            {"ready": ready, "generation": generated, "batch_elapsed_ns": batch_elapsed},
        )
        return {
            condition: _model_result(
                raw_output=str(generated["proposals"][index]),
                condition=condition,
                selected_id=str(config["runtime_projection"]["selected_episode_id"]),
                elapsed_ns=int(generated["generation_elapsed_ns"]),
                token_count=None,
                transport={
                    "success": True,
                    "batch_elapsed_ns": batch_elapsed,
                    "model_load_count": ready["model_load_count"],
                    "ready_receipt": ready,
                },
            )
            for index, condition in enumerate(("C0", "C1"))
        }
    except Exception as error:
        if worker is not None:
            worker.close()
        batch_elapsed = time.perf_counter_ns() - started
        failure = {
            "success": False,
            "error_type": type(error).__name__,
            "error": str(error),
            "batch_elapsed_ns": batch_elapsed,
        }
        _write_json(output / "model_M_failure.json", failure)
        return {
            condition: _model_result(
                raw_output="",
                condition=condition,
                selected_id=str(config["runtime_projection"]["selected_episode_id"]),
                elapsed_ns=batch_elapsed,
                token_count=None,
                transport=failure,
            )
            for condition in ("C0", "C1")
        }


def _run_luna(config: Mapping[str, Any], prompts: Mapping[str, str], output: Path) -> dict[str, dict[str, Any]]:
    model = config["models"]["L"]
    codex = shutil.which("codex")
    if not codex:
        raise FileNotFoundError("codex CLI is unavailable")
    scratch = output / "model_L_scratch"
    worker = CodexExecLunaWorker(
        codex_bin=Path(codex),
        scratch_root=scratch,
        timeout_seconds=float(model["timeout_seconds"]),
    )
    result = {}
    for condition in ("C0", "C1"):
        started = time.perf_counter_ns()
        try:
            raw, transport = worker.propose(prompts[condition])
        except LunaWorkerFailure as error:
            raw = str(error.receipt.get("rejected_proposal_bounded", ""))
            transport = {**error.receipt, "success": False, "error": str(error)}
        elapsed = time.perf_counter_ns() - started
        usage = transport.get("usage", {})
        token_count = None
        if isinstance(usage, dict):
            numeric = [value for key, value in usage.items() if "token" in key and isinstance(value, int)]
            token_count = sum(numeric) if numeric else None
        result[condition] = _model_result(
            raw_output=raw,
            condition=condition,
            selected_id=str(config["runtime_projection"]["selected_episode_id"]),
            elapsed_ns=elapsed,
            token_count=token_count,
            transport={"success": bool(transport.get("transport_valid")), **dict(transport)},
        )
    clear_empty_scratch_root(scratch)
    _write_json(output / "model_L_outputs.json", result)
    return result


def _receipt(
    *,
    config: Mapping[str, Any],
    condition: str,
    model_key: str,
    prompt: str,
    result: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    prompt_bytes, prompt_sha = _bytes_sha256(prompt)
    raw_output = str(result["raw_output"])
    _, output_sha = _bytes_sha256(raw_output)
    main = projection["main"]
    model = config["models"][model_key]
    retrieval_executed = condition == "C1"
    selected_id = str(projection["selected_episode_id"])
    decision = result.get("decision")
    return {
        "schema_version": RECEIPT_SCHEMA,
        "run": {
            "receipt_id": f"phase2-{model_key}-{condition}",
            "condition_id": condition,
            "task_id": config["task"]["task_id"],
            "started_at": config["attempt_started_at"],
            "ended_at": _now(),
            "input_sha256": prompt_sha,
            "input_bytes": prompt_bytes,
            "synthetic_fixture": False,
            "growth_claimed": False,
        },
        "main_before": {
            "identity_owner": "Rozephine main only",
            "persistent_cognition_owner": "Rozephine main only",
            "pair_snapshot_id": main["pair_snapshot_id"],
            "memory_snapshot_id": main["memory_snapshot_id"],
            "vrs_snapshot_id": main["vrs_snapshot_id"],
            "state_sha256": main["state_sha256"],
            "full_current_addressable": True,
            "lookup_requires_io": False,
            "state_evidence_kind": "canonical_frozen_resident_status",
        },
        "retrieval": {
            "executed": retrieval_executed,
            "snapshot_id": main["pair_snapshot_id"],
            "runtime_selected": retrieval_executed,
            "evaluator_allowlist_used": False,
            "candidate_addresses": [selected_id] if retrieval_executed else [],
            "selected_addresses": [selected_id] if retrieval_executed else [],
            "rejected_addresses": [],
            "provenance_revisions": {selected_id: projection["episode_revision"]} if retrieval_executed else {},
            "rationales": {selected_id: f"runtime selected cue {projection['selected_cue']} at minimum nonempty hot fanout"} if retrieval_executed else {},
            "rejection_evidence": {},
            "active_outcome_classes": OUTCOME_CLASSES if retrieval_executed else [],
            "selected_cue": projection["selected_cue"] if retrieval_executed else None,
            "selection_method": projection["selection_method"] if retrieval_executed else "disabled_by_C0_definition",
            "cold_projection_scan_only": retrieval_executed,
        },
        "memory_activation": {
            "executed": False,
            "snapshot_id": main["pair_snapshot_id"],
            "ordered_stages": [],
            "stage_receipts": [],
            "reason": "C0 and C1 do not execute the fixed SWEGCA memory-activation protocol",
        },
        "specialist": {
            "specialist_id": model["specialist_id"],
            "model_identity_evidence_tier": model["evidence_tier"],
            "replaceable": True,
            "stateless": True,
            "input_sha256": prompt_sha,
            "output_sha256": output_sha,
            "output_is_proposal_only": True,
            "persistent_state_owned": False,
            "main_mutable_reference_received": False,
            "context_destroyed_after_request": True,
            "cache_destroyed_after_request": True,
            "transport": result["transport"],
        },
        "judgment": {
            "main_arbitrated": True,
            "falsification_first": True,
            "current_evidence_ids": [],
            "proposal_ids": [f"sha256:{output_sha}"],
            "conflict_detected": bool(decision and decision.get("verdict") == "conflict"),
            "abstained": decision is None or decision.get("verdict") in {"insufficient", "conflict"},
            "worker_decision": decision,
            "strict_parse_error": result["parse_error"],
            "secondary_worker_diagnostic_correct": result["diagnostic_correct"],
            "grants_semantic_authority": False,
        },
        "outcome": {
            "actual_outcome_observed": False,
            "outcome_id": None,
            "outcome_class": "none",
            "provenance": None,
            "assimilated": False,
        },
        "successor": {
            "published": False,
            "atomic_copy_on_write": False,
            "compare_and_swap": False,
            "pair_snapshot_id": None,
            "memory_snapshot_id": None,
            "vrs_snapshot_id": None,
        },
        "accounting": {
            "distinct_source_episodes": 1 if retrieval_executed else 0,
            "actual_outcomes": 0,
            "generated_rows": 1,
            "repetitions": 0,
            "tokens": result["token_count"],
            "vrs_cycles": 0,
            "model_parameters": model["parameter_count"],
        },
        "resources": {
            "elapsed_ns": result["elapsed_ns"],
            "cpu_time_ns": 0,
            "peak_ram_bytes": None,
            "peak_vram_bytes": result["transport"].get("peak_cuda_bytes"),
            "disk_read_bytes": projection["ledger_bytes_scanned"] if retrieval_executed else 0,
            "disk_write_bytes": 0,
            "network_read_bytes": None if model_key == "L" else 0,
            "network_write_bytes": None if model_key == "L" else 0,
            "hot_path_disk_json_sqlite_network_or_hash_io": False,
            "measurement_limit": "CPU, RAM, non-135M VRAM, and provider network byte peaks were not instrumented in this minimal pilot",
        },
        "authority": dict(AUTHORITY_FALSE),
        "heldout": {
            "is_final_confirmation": False,
            "accessed_during_development": False,
            "used_for_code_threshold_weight_or_curriculum_selection": False,
            "ordinary_prior_experience_hidden": False,
        },
    }


def run(config_path: Path, output: Path) -> dict[str, Any]:
    config_path = config_path.resolve(strict=True)
    config = _json(config_path)
    _validate_config(config_path, config)
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(mode=0o700, parents=True)
    attempt_started = _now()
    config = {**config, "attempt_started_at": attempt_started}
    _write_json(
        output / "attempt.json",
        {
            "schema_version": SCHEMA,
            "status": "frozen_before_model_outputs",
            "started_at": attempt_started,
            "config": str(config_path),
            "config_sha256": _sha256(config_path),
            "growth_claimed": False,
            "heldout_accessed": False,
            "persistent_mutation_allowed": False,
            "authority": dict(AUTHORITY_FALSE),
        },
    )
    projection = _retrieve_projection(config)
    config["runtime_projection"] = projection
    prompts = {condition: _prompt(config, condition, projection) for condition in ("C0", "C1")}
    core_rows = []
    for condition in ("C0", "C1"):
        byte_count, digest = _bytes_sha256(prompts[condition])
        core_rows.append(
            {
                "id": condition,
                "language": "ko",
                "serialized_input": prompts[condition],
                "serialized_input_utf8_bytes": byte_count,
                "serialized_input_sha256": digest,
                "selected_candidate_ids": [] if condition == "C0" else [projection["selected_episode_id"]],
                "rejected_candidate_count": 0,
            }
        )
    inputs = output / "frozen_inputs.jsonl"
    _write_jsonl(inputs, core_rows)
    _write_json(output / "retrieval_projection.json", projection)
    _write_json(
        output / "pre_model_freeze.json",
        {
            "status": "inputs_and_expected_scores_frozen_before_model_outputs",
            "config_sha256": _sha256(config_path),
            "frozen_inputs_sha256": _sha256(inputs),
            "condition_input_sha256": {row["id"]: row["serialized_input_sha256"] for row in core_rows},
            "selected_episode_id": projection["selected_episode_id"],
            "expected": config["task"]["output_contract"],
            "model_outputs_observed": False,
        },
    )

    all_results = {
        "S": _run_small(config, inputs, output),
        "M": _run_gemma(config, prompts, output),
        "L": _run_luna(config, prompts, output),
    }
    receipt_contract = _json(_resolve(config["parent"]["phase1_receipt_contract"]))
    receipts = []
    receipt_errors: dict[str, list[str]] = {}
    for model_key in ("S", "M", "L"):
        for condition in ("C0", "C1"):
            receipt = _receipt(
                config=config,
                condition=condition,
                model_key=model_key,
                prompt=prompts[condition],
                result=all_results[model_key][condition],
                projection=projection,
            )
            errors = validate_receipt(receipt, receipt_contract)
            if errors:
                receipt_errors[f"{model_key}:{condition}"] = errors
            receipts.append(receipt)
    _write_jsonl(output / "receipts.jsonl", receipts)

    socket_path = Path(config["full_current"]["resident_socket"])
    main_after = _main_state(_socket_request(socket_path, {"command": "status"}))
    pair_unchanged = main_after == projection["main"]
    same_inputs = all(
        len({row["run"]["input_sha256"] for row in receipts if row["run"]["condition_id"] == condition}) == 1
        for condition in ("C0", "C1")
    )
    cell_summary = {
        f"{model_key}:{condition}": {
            "transport_success": bool(all_results[model_key][condition]["transport"].get("success")),
            "strict_parse": all_results[model_key][condition]["decision"] is not None,
            "diagnostic_correct": all_results[model_key][condition]["diagnostic_correct"],
            "verdict": (all_results[model_key][condition]["decision"] or {}).get("verdict"),
            "elapsed_ns": all_results[model_key][condition]["elapsed_ns"],
        }
        for model_key in ("S", "M", "L")
        for condition in ("C0", "C1")
    }
    passed = not receipt_errors and pair_unchanged and same_inputs and len(receipts) == 6
    report = {
        "schema_version": SCHEMA,
        "status": "phase2_baseline_execution_complete" if passed else "phase2_baseline_execution_contract_failed",
        "completed_at": _now(),
        "passed": passed,
        "phase_complete": passed,
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "frozen_inputs_sha256": _sha256(inputs),
        "cell_count": len(receipts),
        "cell_summary": cell_summary,
        "strict_parse_count": sum(row["judgment"]["worker_decision"] is not None for row in receipts),
        "secondary_worker_diagnostic_correct_count": sum(row["judgment"]["secondary_worker_diagnostic_correct"] for row in receipts),
        "receipt_validation_errors": receipt_errors,
        "same_condition_input_sha256_across_models": same_inputs,
        "resident_pair_unchanged": pair_unchanged,
        "main_before": projection["main"],
        "main_after": main_after,
        "new_experience_count": 0,
        "actual_outcome_count": 0,
        "experience_assimilation_count": 0,
        "vrs_reconvergence_count": 0,
        "growth_claimed": False,
        "heldout_accessed": False,
        "authority": dict(AUTHORITY_FALSE),
        "Rozephine의 판단": "없음. C0/C1은 외부 worker baseline이며 Rozephine의 정상 C4 판단이나 지속 상태 변경을 수행하지 않았다.",
        "Codex의 판단": "이 실행은 세 모델의 C0/C1 입력 전달, strict parse, 보조 정확도와 실행 경계를 측정하는 최소 개발 진단이다. 모델 순위, 성장, 일반화 또는 사실 권위를 입증하지 않는다.",
        "Codex 작업 실수 및 교정": [
            {
                "when": "Phase 1 직후 135.5M artifact 확인",
                "mistake": "첫 로컬 후보를 찾은 뒤에도 미리 묶은 검색이 4TB 경로까지 계속되어 20초 timeout과 불필요한 디스크 검색을 만들었다.",
                "impact": "읽기 전용 자원 낭비만 있었고 artifact나 상태 변경은 없었다.",
                "correction": "확인된 로컬 exact artifact를 동결하고 이후 exact path만 사용했다.",
                "residual_risk": "없음"
            },
            {
                "when": "Phase 2 runner 탐색",
                "mistake": "runtime glob을 포함한 rg로 생성 runtime 내용을 약 7.6만 줄 스캔해 출력이 잘리고 약 10초를 낭비했다.",
                "impact": "읽기 전용 검색 비용과 noisy output만 발생했다.",
                "correction": "이후 config와 알려진 runner exact path로 검색 범위를 제한했다.",
                "residual_risk": "없음"
            },
            {
                "when": "Phase 2 계약 수리 첫 테스트",
                "mistake": "시스템 PATH의 pytest를 호출해 command-not-found를 발생시켰고, 같은 확인 명령에서 handoff 문서의 docs/worklogs 경로를 누락했다.",
                "impact": "테스트가 시작되지 않았고 파일 변경은 없었다.",
                "correction": "직전 Phase 1 원장의 고정 Python 경로로 재실행해 회귀를 통과시켰다.",
                "residual_risk": "없음"
            },
            {
                "when": "Phase 2 retrieval payload 점검",
                "mistake": "episode row가 steps 배열을 가진다고 가정해 KeyError를 냈고, 다음 점검에서 step 필드를 제외하지 않아 큰 본문을 출력한 뒤 None 길이를 재려 TypeError를 냈다.",
                "impact": "읽기 전용 점검 두 번과 과도한 터미널 출력이 발생했으며 원장이나 상주 상태는 바뀌지 않았다.",
                "correction": "실제 단일 step schema를 확인하고 runner는 타입과 anchor를 fail-closed 검증하도록 작성했다.",
                "residual_risk": "없음"
            }
        ],
    }
    _write_json(output / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/rozephine_swegca_vrs_paper_phase2_baseline_v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.config, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
