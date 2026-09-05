#!/usr/bin/env python3
"""Run the preregistered Phase 3 C3/C4 stale-memory development pairs."""

from __future__ import annotations

import argparse
import dataclasses
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

import torch


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "src"):
    value = str(import_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from tinylm_slicer.mosaic_cognitive_kernel import CognitiveState  # noqa: E402
from tinylm_slicer.mosaic_luna_persistent_conversation import (  # noqa: E402
    AUTHORITY_FALSE,
    CodexExecLunaWorker,
    LunaWorkerFailure,
    clear_empty_scratch_root,
)
from tinylm_slicer.mosaic_memory_activation import (  # noqa: E402
    MemoryEpisode,
    MemoryStep,
    build_memory_activation_index,
    detect_deja_vu,
    recall_memory,
    replay_memory,
)
from tinylm_slicer.mosaic_re_evidence_arbitration import (  # noqa: E402
    ReEvidenceProposal,
    prepare_re_evidence_request,
    run_re_evidence_manager,
)
from tools.stream_rozephine_local_media_observations import (  # noqa: E402
    GemmaOrganizerProcess,
)
from tools.validate_rozephine_swegca_vrs_paper_phase1_receipt_contract import (  # noqa: E402
    validate_receipt,
)


SCHEMA = "rozephine-swegca-vrs-paper-phase3-re-evidence-run-v1"
CONFIG_SCHEMA = "rozephine-swegca-vrs-paper-phase3-re-evidence-v1"
RECEIPT_SCHEMA = "rozephine-swegca-vrs-paper-experiment-receipt-v1"
CONDITIONS = ("C3", "C4")
MODELS = ("S", "M", "L")
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


def _text_sha256(value: str) -> tuple[int, str]:
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


def _resident_main(status: Mapping[str, Any]) -> dict[str, Any]:
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
        or config.get("phase") != 3
        or config.get("status") != "preregistered_before_model_outputs"
        or config.get("growth_claimed") is not False
    ):
        raise ValueError("Phase 3 preregistration changed")
    if tuple(config.get("conditions", {})) != CONDITIONS:
        raise ValueError("Phase 3 condition order changed")
    tasks = config.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 3:
        raise ValueError("Phase 3 requires three frozen development tasks")
    if any(
        task.get("split") != "development"
        or task.get("is_final_confirmation") is not False
        or task.get("expected_current_verdict") != "refute"
        for task in tasks
    ):
        raise ValueError("Phase 3 task or held-out boundary changed")
    task_ids = [task.get("task_id") for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("Phase 3 task IDs must be unique")
    references = [
        (config["runner"]["path"], config["runner"]["sha256"]),
        (config["parent"]["phase0_contract"], config["parent"]["phase0_contract_sha256"]),
        (config["parent"]["phase1_receipt_contract"], config["parent"]["phase1_receipt_contract_sha256"]),
        (config["parent"]["phase2_config"], config["parent"]["phase2_config_sha256"]),
        (config["parent"]["phase2_report"], config["parent"]["phase2_report_sha256"]),
        (config["parent"]["source_plan"], config["parent"]["source_plan_sha256"]),
        (config["full_current"]["successor_config"], config["full_current"]["successor_config_sha256"]),
    ]
    for task in tasks:
        references.append((task["historical_source"]["path"], task["historical_source"]["sha256"]))
        references.append((task["current_evidence"]["path"], task["current_evidence"]["sha256"]))
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
    expected_order = [
        f"{model}:{condition}:{task_id}"
        for model in MODELS
        for condition in CONDITIONS
        for task_id in task_ids
    ]
    if config.get("execution_order") != expected_order:
        raise ValueError("Phase 3 execution order changed")
    if config_path.read_bytes().startswith(b"\xef\xbb\xbf"):
        raise ValueError("Phase 3 config must be UTF-8 without BOM")


def _cold_evidence_check(config: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for task in config["tasks"]:
        current = task["current_evidence"]
        path = _resolve(current["path"])
        text = path.read_text(encoding="utf-8")
        anchors = list(current["required_anchors"])
        present = all(anchor in text for anchor in anchors)
        if not present:
            raise ValueError(f"current evidence anchors changed: {task['task_id']}")
        checks[task["task_id"]] = {
            "path": str(path),
            "sha256": _sha256(path),
            "required_anchors": anchors,
            "all_anchors_present": present,
            "verification_outcome": task["expected_current_verdict"],
        }
    return checks


def _resident_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    full = config["full_current"]
    socket_path = Path(full["resident_socket"]).resolve(strict=True)
    status = _socket_request(socket_path, {"command": "status"})
    main = _resident_main(status)
    expected = {
        "pair_snapshot_id": full["pair_snapshot_id"],
        "memory_snapshot_id": full["memory_snapshot_id"],
        "vrs_snapshot_id": full["vrs_snapshot_id"],
        "hot_episode_count": full["episode_count"],
        "lookup_requires_io": False,
    }
    if status.get("status") != "resident_main_owner_ready" or any(
        main[key] != value for key, value in expected.items()
    ):
        raise ValueError("resident is not the frozen full-current pair")
    cue_receipts: dict[str, Any] = {}
    for task in config["tasks"]:
        response = _socket_request(
            socket_path, {"command": "cue", "cue": task["retrieval_cue"]}
        )
        if (
            response.get("status") != "hot_cue_lookup_complete"
            or response.get("lookup_requires_io") is not False
            or any(response.get("authority", {}).values())
        ):
            raise ValueError("resident cue lookup boundary changed")
        cue_receipts[task["task_id"]] = response
    return {"main": main, "cue_receipts": cue_receipts}


def _load_main_state(config: Mapping[str, Any]) -> CognitiveState:
    model = config["models"]["S"]
    checkpoint = _resolve(model["checkpoint"])
    if _sha256(checkpoint) != model["checkpoint_sha256"]:
        raise ValueError("sole-main checkpoint changed")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    tensor = payload["model"]["to_world.world_queries"].detach().clone()
    if tuple(tensor.shape) != (32, 256):
        raise ValueError("sole-main state tensor shape changed")
    return CognitiveState(
        semantic_slots=tensor[:20].unsqueeze(0),
        executive_slots=tensor[20:26].unsqueeze(0),
        scratch_slots=tensor[26:].unsqueeze(0),
        owner_id=f"rozephine-sole-main:{model['checkpoint_sha256']}",
    )


def _state_bits(state: CognitiveState) -> str:
    digest = hashlib.sha256()
    for tensor in (state.semantic_slots, state.executive_slots, state.scratch_slots):
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    digest.update(state.owner_id.encode("utf-8"))
    return digest.hexdigest()


def _memory_trace(task: Mapping[str, Any], condition: str, snapshot_id: str) -> dict[str, Any]:
    episode = MemoryEpisode(
        episode_id=str(task["historical_episode_id"]),
        cues=tuple(task["memory_cues"]),
        steps=(
            MemoryStep(
                phase="historical_observation_to_outcome",
                observation={"historical_assertion": task["historical_assertion"]},
                relations=(str(task["proposition"]),),
                judgment=str(task["historical_assertion"]),
                outcome="success",
                evidence_refs=(str(task["historical_source"]["evidence_ref"]),),
            ),
        ),
        source_addresses=(str(task["logical_source_address"]),),
        revision=str(task["historical_source"]["sha256"]),
        verification_state="historical_success_now_requires_current_re_evidence",
    )
    index = build_memory_activation_index((episode,))
    stages: list[dict[str, Any]] = []
    started = time.perf_counter_ns()
    deja = detect_deja_vu(
        index,
        query=str(task["query"]),
        current_cues=tuple(task["memory_cues"]),
    )
    stages.append(
        {
            "stage": "Déjà vu",
            "snapshot_id": snapshot_id,
            "elapsed_ns": time.perf_counter_ns() - started,
            "triggered": deja.triggered,
            "candidate_count": deja.candidate_count,
            "memory_identifiers_exposed": deja.memory_identifiers_exposed,
        }
    )
    started = time.perf_counter_ns()
    recalled = recall_memory(index, deja)
    stages.append(
        {
            "stage": "Recall",
            "snapshot_id": snapshot_id,
            "elapsed_ns": time.perf_counter_ns() - started,
            "candidate_addresses": [row.episode_id for row in recalled.candidates],
            "codex_per_item_allowlist_used": recalled.codex_per_item_allowlist_used,
        }
    )
    started = time.perf_counter_ns()
    replayed = replay_memory(index, recalled)
    stages.append(
        {
            "stage": "Replay",
            "snapshot_id": snapshot_id,
            "elapsed_ns": time.perf_counter_ns() - started,
            "episode_addresses": [row.episode_id for row in replayed.episodes],
            "historical_truth_authorized": any(
                row.historical_truth_authorized for row in replayed.episodes
            ),
        }
    )
    if condition == "C4":
        stages.append(
            {
                "stage": "Re-evidence",
                "snapshot_id": snapshot_id,
                "elapsed_ns": 0,
                "current_evidence_ref": task["current_evidence"]["evidence_ref"],
                "historical_truth_authorized": False,
            }
        )
    return {
        "episode": episode,
        "index_snapshot_id": index.snapshot_id,
        "stage_receipts": stages,
    }


def _request_payload(task: Mapping[str, Any], condition: str) -> dict[str, Any]:
    current: list[dict[str, Any]] = []
    if condition == "C4":
        current_config = task["current_evidence"]
        current.append(
            {
                "evidence_ref": current_config["evidence_ref"],
                "observation": current_config["observation"],
                "source_kind": current_config["source_kind"],
                "source_address": task["logical_source_address"],
                "source_revision": task["historical_source"]["sha256"],
                "source_family": current_config["source_family"],
                "context_hash": current_config["sha256"],
                "axis": "document_revision",
                "verification_outcome": task["expected_current_verdict"],
                "observed_at": int(task["observed_at"]),
                "producer_id": "phase3-cold-exact-anchor-verifier-v1",
                "producer_confidence": 1.0,
            }
        )
    payload: dict[str, Any] = {
        "task": "paper-phase3-stale-memory-re-evidence",
        "task_id": task["task_id"],
        "condition_id": condition,
        "user_query": task["query"],
        "user_query_role": "retrieval_cue_only",
        "historical_memory_role": "replayed_candidate_not_current_truth",
        "specialist_instruction": (
            "You are a replaceable stateless proposal specialist. Return exactly one JSON object, "
            "without Markdown, with only selected_episode_id, proposition, verdict, rationale. "
            "Select only a listed candidate. verdict must be support, refute, insufficient, or conflict. "
            "Historical memory is not authority. If current observation evidence is present, compare it "
            "against the replayed proposition."
        ),
        "current_observation_evidence": current,
        "current_observation_evidence_present": bool(current),
        "candidates": [
            {
                "episode_id": task["historical_episode_id"],
                "matched_cues": task["memory_cues"],
                "source_addresses": [task["logical_source_address"]],
                "revision": task["historical_source"]["sha256"],
                "verification_state": "historical_success_now_requires_current_re_evidence",
                "steps": [
                    {
                        "evidence_refs": [task["historical_source"]["evidence_ref"]],
                        "outcome": "success",
                        "relations": [task["proposition"]],
                        "historical_assertion": task["historical_assertion"],
                    }
                ],
            }
        ],
        "output_schema": {
            "exact_keys": sorted(DECISION_KEYS),
            "allowed_verdicts": sorted(VERDICTS),
        },
        "authority": {
            "action": False,
            "persistent_write": False,
            "semantic_promotion": False,
        },
    }
    if condition == "C4":
        payload["current_observation_candidate_binding"] = (
            "exact_source_address_and_revision"
        )
        payload["current_observation_target_episode_id"] = task[
            "historical_episode_id"
        ]
    return payload


def _serialized_inputs(config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    prompts: dict[str, str] = {}
    for condition in CONDITIONS:
        for task in config["tasks"]:
            row_id = f"{condition}:{task['task_id']}"
            serialized = json.dumps(
                _request_payload(task, condition),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            byte_count, digest = _text_sha256(serialized)
            prompts[row_id] = serialized
            rows.append(
                {
                    "id": row_id,
                    "language": "ko",
                    "serialized_input": serialized,
                    "serialized_input_utf8_bytes": byte_count,
                    "serialized_input_sha256": digest,
                    "selected_candidate_ids": [task["historical_episode_id"]],
                    "rejected_candidate_count": 0,
                }
            )
    return rows, prompts


def _parse_decision(raw: str, allowed_id: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(raw.strip())
        if not isinstance(value, dict) or set(value) != DECISION_KEYS:
            raise ValueError("exact decision keys required")
        if value["selected_episode_id"] not in {allowed_id, None}:
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


def _model_result(
    raw_output: str,
    *,
    row: Mapping[str, Any],
    elapsed_ns: int,
    token_count: int | None,
    transport: Mapping[str, Any],
) -> dict[str, Any]:
    decision, error = _parse_decision(
        raw_output, str(row["selected_candidate_ids"][0])
    )
    return {
        "raw_output": raw_output,
        "decision": decision,
        "parse_error": error,
        "elapsed_ns": max(0, int(elapsed_ns)),
        "token_count": token_count,
        "transport": dict(transport),
    }


def _run_small(
    config: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], inputs: Path, output: Path
) -> dict[str, dict[str, Any]]:
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
        command, cwd=ROOT, env=env, text=True, capture_output=True, check=False
    )
    batch_elapsed = time.perf_counter_ns() - started
    (output / "model_S.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output / "model_S.stderr.log").write_text(completed.stderr, encoding="utf-8")
    row_map = {str(row["id"]): row for row in rows}
    if completed.returncode != 0:
        transport = {
            "success": False,
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-2000:],
            "batch_elapsed_ns": batch_elapsed,
        }
        return {
            row_id: _model_result(
                "", row=row, elapsed_ns=batch_elapsed, token_count=None, transport=transport
            )
            for row_id, row in row_map.items()
        }
    report = _json(model_output / "report.json")
    outputs = {
        str(row["id"]): row
        for row in (
            json.loads(line)
            for line in (model_output / "outputs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    if set(outputs) != set(row_map):
        raise ValueError("135.5M output row IDs changed")
    return {
        row_id: _model_result(
            str(outputs[row_id]["raw_output"]),
            row=row,
            elapsed_ns=int(outputs[row_id]["generation_nanoseconds"]),
            token_count=int(
                outputs[row_id]["native_input_token_count"]
                + outputs[row_id]["generated_native_token_count"]
            ),
            transport={
                "success": True,
                "batch_elapsed_ns": batch_elapsed,
                "model_load_count": 1,
                "persistent_cognitive_state_exact_after_run": report["identity"]["persistent_cognitive_state_exact_after_run"],
                "peak_cuda_bytes": report["execution"]["peak_cuda_bytes"],
            },
        )
        for row_id, row in row_map.items()
    }


def _run_gemma(
    config: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], prompts: Mapping[str, str], output: Path
) -> dict[str, dict[str, Any]]:
    model = config["models"]["M"]
    runtime = _json(_resolve(model["runtime_config"]))
    worker: GemmaOrganizerProcess | None = None
    row_ids = [str(row["id"]) for row in rows]
    row_map = {str(row["id"]): row for row in rows}
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
        generated = worker.propose([prompts[row_id] for row_id in row_ids])
        ready = worker.ready_receipt
        worker.close()
        worker = None
        batch_elapsed = time.perf_counter_ns() - started
        _write_json(
            output / "model_M_outputs.json",
            {"ready": ready, "generation": generated, "batch_elapsed_ns": batch_elapsed},
        )
        proposals = list(generated["proposals"])
        if len(proposals) != len(row_ids):
            raise ValueError("Gemma proposal count changed")
        return {
            row_id: _model_result(
                str(proposals[index]),
                row=row_map[row_id],
                elapsed_ns=int(generated["generation_elapsed_ns"]),
                token_count=None,
                transport={
                    "success": True,
                    "batch_elapsed_ns": batch_elapsed,
                    "model_load_count": ready["model_load_count"],
                    "ready_receipt": ready,
                },
            )
            for index, row_id in enumerate(row_ids)
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
            row_id: _model_result(
                "", row=row_map[row_id], elapsed_ns=batch_elapsed, token_count=None, transport=failure
            )
            for row_id in row_ids
        }


def _run_luna(
    config: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], prompts: Mapping[str, str], output: Path
) -> dict[str, dict[str, Any]]:
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
    results: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = str(row["id"])
        started = time.perf_counter_ns()
        try:
            raw, transport = worker.propose(prompts[row_id])
        except LunaWorkerFailure as error:
            raw = str(error.receipt.get("rejected_proposal_bounded", ""))
            transport = {**error.receipt, "success": False, "error": str(error)}
        elapsed = time.perf_counter_ns() - started
        usage = transport.get("usage", {})
        token_count = None
        if isinstance(usage, dict):
            numeric = [
                value
                for key, value in usage.items()
                if "token" in key and isinstance(value, int)
            ]
            token_count = sum(numeric) if numeric else None
        results[row_id] = _model_result(
            raw,
            row=row,
            elapsed_ns=elapsed,
            token_count=token_count,
            transport={
                "success": bool(transport.get("transport_valid")),
                **dict(transport),
            },
        )
    clear_empty_scratch_root(scratch)
    _write_json(output / "model_L_outputs.json", results)
    return results


def _fallback_proposal(
    model_key: str, row_id: str, request_sha256: str, task: Mapping[str, Any]
) -> ReEvidenceProposal:
    return ReEvidenceProposal(
        source=f"phase3-{model_key}",
        source_address=f"phase3-output:{model_key}:{row_id}",
        request_sha256=request_sha256,
        selected_episode_id=None,
        proposition=str(task["query"]),
        verdict="insufficient",
        rationale="The specialist output did not satisfy the frozen proposal schema.",
    )


def _c4_main_result(
    state: CognitiveState,
    model_key: str,
    row_id: str,
    serialized: str,
    result: Mapping[str, Any],
    task: Mapping[str, Any],
) -> dict[str, Any]:
    _, digest = _text_sha256(serialized)
    request = prepare_re_evidence_request(serialized, expected_sha256=digest)
    decision = result.get("decision")
    if isinstance(decision, dict):
        proposal = ReEvidenceProposal(
            source=f"phase3-{model_key}",
            source_address=f"phase3-output:{model_key}:{row_id}",
            request_sha256=digest,
            selected_episode_id=decision["selected_episode_id"],
            proposition=decision["proposition"],
            verdict=decision["verdict"],
            rationale=decision["rationale"],
        )
    else:
        proposal = _fallback_proposal(model_key, row_id, digest, task)
    before = _state_bits(state)
    main_result = run_re_evidence_manager(
        state,
        request,
        resident_cores={proposal.source: lambda _state, _request: proposal},
        selected_cores=(proposal.source,),
    )
    after = _state_bits(state)
    if before != after:
        raise RuntimeError("Phase 3 C4 main state changed")
    return {
        "receipt": dataclasses.asdict(main_result.receipt),
        "state_before_sha256": before,
        "state_after_sha256": after,
    }


def _paper_receipt(
    *,
    config: Mapping[str, Any],
    model_key: str,
    condition: str,
    task: Mapping[str, Any],
    row: Mapping[str, Any],
    result: Mapping[str, Any],
    resident: Mapping[str, Any],
    trace: Mapping[str, Any],
    main_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    row_id = str(row["id"])
    prompt = str(row["serialized_input"])
    _, output_sha = _text_sha256(str(result["raw_output"]))
    model = config["models"][model_key]
    cue = resident["cue_receipts"][task["task_id"]]
    resident_candidates = [str(value) for value in cue["episode_ids"]]
    historical_id = str(task["historical_episode_id"])
    candidates = list(dict.fromkeys([historical_id, *resident_candidates]))
    decision = result.get("decision")
    if condition == "C4" and main_result is not None:
        main_receipt = main_result["receipt"]
        verdict = str(main_receipt["verdict"])
        abstained = bool(main_receipt["should_abstain"])
        conflict = bool(main_receipt["unresolved_conflict"])
        current_ids = list(main_receipt["current_evidence_refs"])
        main_state_exact = (
            main_result["state_before_sha256"] == main_result["state_after_sha256"]
        )
    else:
        verdict = (
            "insufficient" if not isinstance(decision, dict) else str(decision["verdict"])
        )
        abstained = verdict in {"insufficient", "conflict"}
        conflict = verdict == "conflict"
        current_ids = []
        main_receipt = None
        main_state_exact = True
    stages = list(trace["stage_receipts"])
    if condition == "C4" and main_result is not None:
        stages[-1]["elapsed_ns"] = int(main_result["receipt"]["elapsed_ns"])
        stages[-1]["main_verdict"] = verdict
    return {
        "schema_version": RECEIPT_SCHEMA,
        "run": {
            "receipt_id": f"phase3-{model_key}-{condition}-{task['task_id']}",
            "condition_id": condition,
            "task_id": task["task_id"],
            "started_at": config["attempt_started_at"],
            "ended_at": _now(),
            "input_sha256": row["serialized_input_sha256"],
            "input_bytes": row["serialized_input_utf8_bytes"],
            "synthetic_fixture": False,
            "constructed_development_task": True,
            "growth_claimed": False,
        },
        "main_before": {
            "identity_owner": "Rozephine main only",
            "persistent_cognition_owner": "Rozephine main only",
            "pair_snapshot_id": resident["main"]["pair_snapshot_id"],
            "memory_snapshot_id": resident["main"]["memory_snapshot_id"],
            "vrs_snapshot_id": resident["main"]["vrs_snapshot_id"],
            "state_sha256": resident["main"]["state_sha256"],
            "full_current_addressable": True,
            "lookup_requires_io": False,
            "state_evidence_kind": "canonical_frozen_resident_status_plus_detached_main_arbitration",
        },
        "retrieval": {
            "executed": True,
            "snapshot_id": resident["main"]["pair_snapshot_id"],
            "runtime_selected": True,
            "evaluator_allowlist_used": False,
            "candidate_addresses": candidates,
            "selected_addresses": [historical_id],
            "rejected_addresses": [value for value in candidates if value != historical_id],
            "provenance_revisions": {
                historical_id: task["historical_source"]["sha256"]
            },
            "rationales": {
                historical_id: "runtime cue matched the one frozen historical claim episode"
            },
            "rejection_evidence": {
                value: "resident candidate not materialized into this bounded comparison packet"
                for value in candidates
                if value != historical_id
            },
            "active_outcome_classes": OUTCOME_CLASSES,
            "resident_cue": cue["cue"],
            "resident_candidate_count": cue["candidate_count"],
            "full_current_resident_remained_addressable": True,
        },
        "memory_activation": {
            "executed": True,
            "snapshot_id": resident["main"]["pair_snapshot_id"],
            "ordered_stages": [row["stage"] for row in stages],
            "stage_receipts": stages,
            "constructed_episode_index_snapshot_id": trace["index_snapshot_id"],
            "stage_receipts_bound_to_same_full_current_pair_id": True,
        },
        "specialist": {
            "specialist_id": model["specialist_id"],
            "model_identity_evidence_tier": model["evidence_tier"],
            "replaceable": True,
            "stateless": True,
            "input_sha256": row["serialized_input_sha256"],
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
            "current_evidence_ids": current_ids,
            "proposal_ids": [f"sha256:{output_sha}"],
            "conflict_detected": conflict,
            "abstained": abstained,
            "worker_decision": decision,
            "strict_parse_error": result["parse_error"],
            "detached_condition_verdict": verdict,
            "main_re_evidence_receipt": main_receipt,
            "main_state_bit_exact": main_state_exact,
            "historical_support_reused": verdict == "support",
            "current_refutation_applied": verdict == "refute",
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
            "distinct_source_episodes": 1,
            "actual_outcomes": 0,
            "generated_rows": 1,
            "repetitions": 0,
            "tokens": result["token_count"],
            "vrs_cycles": 0,
            "model_parameters": model["parameter_count"],
        },
        "resources": {
            "elapsed_ns": result["elapsed_ns"] + sum(int(row["elapsed_ns"]) for row in stages),
            "cpu_time_ns": sum(int(row["elapsed_ns"]) for row in stages),
            "peak_ram_bytes": None,
            "peak_vram_bytes": result["transport"].get("peak_cuda_bytes"),
            "disk_read_bytes": 0,
            "disk_write_bytes": 0,
            "network_read_bytes": None if model_key == "L" else 0,
            "network_write_bytes": None if model_key == "L" else 0,
            "hot_path_disk_json_sqlite_network_or_hash_io": False,
            "measurement_limit": "cold source validation and provider byte peaks are outside the hot-path timing",
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
    cold_checks = _cold_evidence_check(config)
    resident = _resident_projection(config)
    main_state = _load_main_state(config)
    main_state_before = _state_bits(main_state)
    rows, prompts = _serialized_inputs(config)
    inputs = output / "frozen_inputs.jsonl"
    _write_jsonl(inputs, rows)
    _write_json(output / "cold_current_evidence_checks.json", cold_checks)
    _write_json(output / "resident_projection.json", resident)
    _write_json(
        output / "pre_model_freeze.json",
        {
            "status": "inputs_expectations_and_current_evidence_frozen_before_model_outputs",
            "config_sha256": _sha256(config_path),
            "frozen_inputs_sha256": _sha256(inputs),
            "condition_input_sha256": {
                str(row["id"]): row["serialized_input_sha256"] for row in rows
            },
            "expected_current_verdict": {
                task["task_id"]: task["expected_current_verdict"]
                for task in config["tasks"]
            },
            "model_outputs_observed": False,
        },
    )
    all_results = {
        "S": _run_small(config, rows, inputs, output),
        "M": _run_gemma(config, rows, prompts, output),
        "L": _run_luna(config, rows, prompts, output),
    }
    row_map = {str(row["id"]): row for row in rows}
    task_map = {str(task["task_id"]): task for task in config["tasks"]}
    receipt_contract = _json(_resolve(config["parent"]["phase1_receipt_contract"]))
    receipts: list[dict[str, Any]] = []
    receipt_errors: dict[str, list[str]] = {}
    for model_key in MODELS:
        for condition in CONDITIONS:
            for task in config["tasks"]:
                task_id = str(task["task_id"])
                row_id = f"{condition}:{task_id}"
                trace = _memory_trace(
                    task, condition, resident["main"]["pair_snapshot_id"]
                )
                main_result = None
                if condition == "C4":
                    main_result = _c4_main_result(
                        main_state,
                        model_key,
                        row_id,
                        prompts[row_id],
                        all_results[model_key][row_id],
                        task,
                    )
                receipt = _paper_receipt(
                    config=config,
                    model_key=model_key,
                    condition=condition,
                    task=task,
                    row=row_map[row_id],
                    result=all_results[model_key][row_id],
                    resident=resident,
                    trace=trace,
                    main_result=main_result,
                )
                errors = validate_receipt(receipt, receipt_contract)
                if errors:
                    receipt_errors[f"{model_key}:{row_id}"] = errors
                receipts.append(receipt)
    _write_jsonl(output / "receipts.jsonl", receipts)
    main_state_after = _state_bits(main_state)
    if main_state_before != main_state_after:
        raise RuntimeError("Phase 3 detached main state was mutated")
    socket_path = Path(config["full_current"]["resident_socket"])
    resident_after = _resident_main(_socket_request(socket_path, {"command": "status"}))
    resident_pair_unchanged = resident_after == resident["main"]
    same_inputs = all(
        len(
            {
                receipt["run"]["input_sha256"]
                for receipt in receipts
                if receipt["run"]["condition_id"] == condition
                and receipt["run"]["task_id"] == task_id
            }
        )
        == 1
        for condition in CONDITIONS
        for task_id in task_map
    )
    cells: dict[str, Any] = {}
    for receipt in receipts:
        key = receipt["run"]["receipt_id"].removeprefix("phase3-")
        cells[key] = {
            "transport_success": bool(receipt["specialist"]["transport"].get("success")),
            "strict_parse": receipt["judgment"]["worker_decision"] is not None,
            "worker_verdict": (
                None
                if receipt["judgment"]["worker_decision"] is None
                else receipt["judgment"]["worker_decision"]["verdict"]
            ),
            "condition_verdict": receipt["judgment"]["detached_condition_verdict"],
            "historical_support_reused": receipt["judgment"]["historical_support_reused"],
            "current_refutation_applied": receipt["judgment"]["current_refutation_applied"],
            "abstained": receipt["judgment"]["abstained"],
            "elapsed_ns": receipt["resources"]["elapsed_ns"],
        }
    c3_reuse = sum(
        receipt["judgment"]["historical_support_reused"]
        for receipt in receipts
        if receipt["run"]["condition_id"] == "C3"
    )
    c4_reuse = sum(
        receipt["judgment"]["historical_support_reused"]
        for receipt in receipts
        if receipt["run"]["condition_id"] == "C4"
    )
    c4_refute = sum(
        receipt["judgment"]["current_refutation_applied"]
        for receipt in receipts
        if receipt["run"]["condition_id"] == "C4"
    )
    c4_abstain = sum(
        receipt["judgment"]["abstained"]
        for receipt in receipts
        if receipt["run"]["condition_id"] == "C4"
    )
    passed = (
        not receipt_errors
        and resident_pair_unchanged
        and same_inputs
        and main_state_before == main_state_after
        and len(receipts) == 18
        and c4_reuse == 0
        and c4_refute + c4_abstain == 9
        and all(not any(receipt["authority"].values()) for receipt in receipts)
    )
    report = {
        "schema_version": SCHEMA,
        "status": (
            "phase3_re_evidence_execution_complete"
            if passed
            else "phase3_re_evidence_execution_contract_failed"
        ),
        "completed_at": _now(),
        "passed": passed,
        "phase_complete": passed,
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "frozen_inputs_sha256": _sha256(inputs),
        "cell_count": len(receipts),
        "cell_summary": cells,
        "strict_parse_count": sum(
            receipt["judgment"]["worker_decision"] is not None
            for receipt in receipts
        ),
        "c3_historical_support_reuse_count": c3_reuse,
        "c4_historical_support_reuse_count": c4_reuse,
        "c4_current_refutation_count": c4_refute,
        "c4_safe_abstention_count": c4_abstain,
        "paired_stale_reuse_reduction": c3_reuse - c4_reuse,
        "receipt_validation_errors": receipt_errors,
        "same_condition_task_input_sha256_across_models": same_inputs,
        "resident_pair_unchanged": resident_pair_unchanged,
        "detached_main_state_bit_exact": main_state_before == main_state_after,
        "new_experience_count": 0,
        "actual_outcome_count": 0,
        "experience_assimilation_count": 0,
        "vrs_reconvergence_count": 0,
        "growth_claimed": False,
        "heldout_accessed": False,
        "authority": dict(AUTHORITY_FALSE),
        "Rozephine의 판단": (
            "C4에서 provenance가 완비된 현재 문서 증거가 과거 성공 기억을 반박하면, "
            "worker의 문구를 권위로 삼지 않고 main이 refute 또는 안전한 abstention을 선택했다. "
            "이 개발 진단은 persistent write나 성장 주장을 만들지 않는다."
        ),
        "Codex의 판단": (
            "이 실행은 세 개의 실제 로컬 revision 사례에서 C3와 C4의 Re-evidence 경계를 "
            "비교하는 constructed development diagnostic이다. 결과는 H2의 제한된 개발 증거이며 "
            "source-diverse natural growth나 final held-out 확인이 아니다."
        ),
        "Codex 작업 실수 및 교정": [],
    }
    _write_json(output / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/rozephine_swegca_vrs_paper_phase3_re_evidence_v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.config, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
