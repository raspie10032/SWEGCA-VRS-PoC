from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tinylm_slicer.mosaic_luna_persistent_conversation import (
    CodexExecLunaWorker,
    verify_distinct_fresh_workers,
)


def _completed(thread_id: str, text: str) -> subprocess.CompletedProcess[str]:
    events = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": text},
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 20,
            },
        },
    ]
    return subprocess.CompletedProcess(
        args=[], returncode=0, stdout="\n".join(json.dumps(row) for row in events), stderr=""
    )


def test_luna_worker_is_ephemeral_read_only_and_destroys_context(tmp_path: Path) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return _completed("thread-fresh-1", "그 장면에서 무엇이 가장 먼저 눈에 들어왔어?")

    codex = tmp_path / "codex"
    codex.write_text("fake", encoding="utf-8")
    worker = CodexExecLunaWorker(
        codex_bin=codex,
        scratch_root=tmp_path / "scratch",
        run_command=fake_run,
    )

    utterance, receipt = worker.propose("현재 발화와 main cognition packet")

    assert "무엇" in utterance
    command, kwargs = calls[0]
    assert "--ephemeral" in command
    assert [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-s"] == ["read-only"]
    assert [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-m"] == ["gpt-5.6-luna"]
    assert 'model_reasoning_effort="low"' in command
    assert kwargs["input"] == "현재 발화와 main cognition packet"
    assert receipt["resumed_model_session_used"] is False
    assert receipt["worker_context_destroyed"] is True
    assert receipt["raw_prior_dialogue_pairs_visible"] == 0
    assert list((tmp_path / "scratch").iterdir()) == []


def test_non_message_tool_item_is_rejected(tmp_path: Path) -> None:
    def fake_run(_command, **_kwargs):
        result = _completed("thread-fresh-2", "안녕")
        result.stdout = result.stdout.replace(
            '{"type": "turn.completed"',
            '{"type":"item.completed","item":{"type":"command_execution"}}\n'
            '{"type": "turn.completed"',
        )
        return result

    codex = tmp_path / "codex"
    codex.write_text("fake", encoding="utf-8")
    worker = CodexExecLunaWorker(
        codex_bin=codex,
        scratch_root=tmp_path / "scratch",
        run_command=fake_run,
    )

    try:
        worker.propose("도구 없는 발화")
    except RuntimeError as error:
        assert "non-message" in str(error)
        assert error.receipt["worker_context_destroyed"] is True
        assert error.receipt["tool_call_count"] == 1
        assert error.receipt["negative_worker_result_retained"] is True
    else:
        raise AssertionError("tool attempt must be rejected")


def test_distinct_worker_receipts_never_resume() -> None:
    receipts = [
        {
            "transport_valid": True,
            "fresh_worker_thread_id": "thread-a",
            "resumed_model_session_used": False,
            "worker_context_destroyed": True,
        },
        {
            "transport_valid": True,
            "fresh_worker_thread_id": "thread-b",
            "resumed_model_session_used": False,
            "worker_context_destroyed": True,
        },
    ]
    assert verify_distinct_fresh_workers(receipts)
    receipts[1]["fresh_worker_thread_id"] = "thread-a"
    assert not verify_distinct_fresh_workers(receipts)
