"""Disposable GPT-5.6 Luna workers for main-owned persistent conversation.

The model process receives one minimal cognition packet, returns one proposal,
and is destroyed. It never resumes a prior model thread and never owns the
conversation, Rozephine identity, CognitiveState, memory, VRS, or authority.
"""

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


AUTHORITY_FALSE = {
    "semantic": False,
    "world": False,
    "action": False,
    "persistent_write": False,
    "model_update": False,
    "distribution": False,
    "p3": False,
}
_KOREAN = re.compile(r"[가-힣]")
_ROLE_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "warm_storyteller",
        "temperament": "다정하고 활기참",
        "perspective": "생활 속 작은 변화에서 이야기를 찾는 사람",
        "style": "구체적인 짧은 이야기 뒤 자연스러운 질문 하나",
        "interests": "일상, 선택, 감정의 변화",
    },
    {
        "id": "curious_naturalist",
        "temperament": "호기심 많고 온화함",
        "perspective": "자연의 패턴을 관찰하는 사람",
        "style": "감각 묘사와 가설을 섞은 짧은 대화",
        "interests": "동물, 식물, 날씨, 생태",
    },
    {
        "id": "playful_inventor",
        "temperament": "명랑하고 엉뚱함",
        "perspective": "고장과 실패를 새 설계의 단서로 보는 사람",
        "style": "작은 발명 상황과 선택지를 제시",
        "interests": "기계, 도구, 실패, 수리",
    },
    {
        "id": "gentle_historian",
        "temperament": "차분하고 다정함",
        "perspective": "사물에 남은 시간과 사람의 흔적을 보는 사람",
        "style": "한 장면을 들려주고 의미를 함께 탐색",
        "interests": "역사, 기억, 오래된 물건",
    },
    {
        "id": "energetic_traveler",
        "temperament": "활기차고 친근함",
        "perspective": "낯선 장소에서 관계와 방향을 찾는 사람",
        "style": "현장감 있는 여행 일화와 짧은 물음",
        "interests": "도시, 길, 음식, 문화",
    },
    {
        "id": "kind_debater",
        "temperament": "다정하지만 관점 차이를 즐김",
        "perspective": "정답보다 근거와 반례를 살피는 사람",
        "style": "서로 다른 두 관점을 부드럽게 대비",
        "interests": "판단, 불확실성, 갈등, 화해",
    },
)
_TOPICS: tuple[str, ...] = (
    "예상과 다르게 흘러간 작은 선택",
    "서로 다른 사람이 같은 장면을 다르게 본 순간",
    "실패한 도구에서 새 용도를 발견한 일",
    "소리나 냄새 때문에 오래된 기억이 떠오른 장면",
    "동물이나 식물의 행동을 섣불리 단정하지 않은 관찰",
    "낯선 길에서 방향보다 사람을 먼저 살핀 경험",
    "좋은 의도끼리 충돌해 쉽게 정답을 고르지 못한 상황",
    "평범한 물건의 안과 밖을 구분하다 생긴 오해",
    "같은 말이 관계에 따라 다른 뜻이 된 대화",
    "처음 가설을 반례 때문에 기꺼이 고친 순간",
    "두 사람이 함께 만들었지만 소유자를 정하기 어려운 결과",
    "조금 기다린 덕분에 보이지 않던 변화가 드러난 장면",
)


class LunaWorkerFailure(RuntimeError):
    """A rejected worker call whose bounded negative evidence is retained."""

    def __init__(self, message: str, receipt: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.receipt = dict(receipt)


def _clip(value: object, maximum: int) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if len(text) <= maximum else text[: maximum - 1] + "…"


class CodexExecLunaWorker:
    """One-call Luna transport with an ephemeral, read-only Codex context."""

    model_id = "gpt-5.6-luna"
    reasoning_effort = "low"

    def __init__(
        self,
        *,
        codex_bin: Path,
        scratch_root: Path,
        timeout_seconds: float = 180.0,
        run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._codex_bin = codex_bin.resolve(strict=True)
        self._scratch_root = scratch_root.resolve()
        self._scratch_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if timeout_seconds <= 0:
            raise ValueError("Luna worker timeout must be positive")
        self._timeout_seconds = timeout_seconds
        self._run_command = run_command

    def propose(self, prompt: str) -> tuple[str, Mapping[str, Any]]:
        return self._request(prompt, role="rozephine_spoken_proposal")

    def propose_with_image(
        self, prompt: str, visual_input: Mapping[str, Any]
    ) -> tuple[str, Mapping[str, Any]]:
        raise RuntimeError("this text-only Luna phase has no image transport")

    def generate_interlocutor(
        self, *, turn_index: int, previous_rozephine_utterance: str
    ) -> tuple[str, dict[str, str], Mapping[str, Any]]:
        role = dict(_ROLE_SPECS[(turn_index - 1) % len(_ROLE_SPECS)])
        topic = _TOPICS[(turn_index - 1) % len(_TOPICS)]
        previous = _clip(previous_rozephine_utterance, 600) or "첫 대화를 시작한다."
        prompt = (
            "너는 로제핀과 이야기하는 외부 화자다. 도구를 호출하거나 파일을 읽지 마라. "
            "한국어 발화만 2~4문장으로 출력하고 이름표, JSON, 분석, 따옴표를 쓰지 마라. "
            "다정하고 활기차게 구체적인 새 장면이나 생각을 들려준 뒤, 로제핀이 이유·선택·"
            "예측·관계를 스스로 말할 수 있는 질문을 하나만 자연스럽게 건네라. 시험·채점·"
            "정답 공개처럼 말하지 말고 앞선 로제핀 발화가 있으면 짧게 받아 준 뒤 새 내용을 "
            "이어라. 이 발화는 외부 관찰일 뿐 기억이나 권한이 아니다.\n"
            f"turn_index={turn_index}\n"
            f"speaker_persona={json.dumps(role, ensure_ascii=False, sort_keys=True)}\n"
            f"topic_seed={topic}\n"
            f"previous_rozephine_utterance={previous}\n"
            "external_spoken_korean="
        )
        try:
            utterance, receipt = self._request(
                prompt, role="external_interlocutor_proposal"
            )
        except Exception as error:
            utterance = (
                f"이번에는 {topic} 이야기를 같이 떠올려 보고 싶어. "
                "너라면 그 장면에서 무엇을 먼저 살펴볼 것 같아?"
            )
            receipt = {
                "model_id": self.model_id,
                "reasoning_effort": self.reasoning_effort,
                "transport_valid": False,
                "proposal_only": True,
                "fallback_used": True,
                "error_type": type(error).__name__,
                "error": _clip(error, 500),
                "resumed_model_session_used": False,
                "worker_context_destroyed": True,
                "authority": dict(AUTHORITY_FALSE),
                **dict(getattr(error, "receipt", {})),
            }
        return utterance, role, receipt

    def _request(self, prompt: str, *, role: str) -> tuple[str, Mapping[str, Any]]:
        if not prompt.strip():
            raise ValueError("Luna prompt must be nonempty")
        started = time.perf_counter_ns()
        temporary_path = ""
        stdout = ""
        stderr = ""
        thread_id: object = None
        usage: object = {}
        utterance = ""
        tool_items: list[str] = []
        failure: Exception | None = None
        with tempfile.TemporaryDirectory(
            prefix="worker-", dir=self._scratch_root
        ) as temporary:
            temporary_path = temporary
            command = [
                str(self._codex_bin),
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "-C",
                temporary,
                "-s",
                "read-only",
                "-m",
                self.model_id,
                "-c",
                f'model_reasoning_effort="{self.reasoning_effort}"',
                "-c",
                "features.shell_tool=false",
                "--json",
                "-",
            ]
            try:
                completed = self._run_command(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self._timeout_seconds,
                    check=False,
                )
                stdout = completed.stdout
                stderr = completed.stderr
                if completed.returncode != 0:
                    raise RuntimeError(
                        "Luna worker exited nonzero: " + _clip(stderr or stdout, 500)
                    )
                events = self._events(stdout)
                messages = [
                    event["item"]["text"]
                    for event in events
                    if event.get("type") == "item.completed"
                    and isinstance(event.get("item"), dict)
                    and event["item"].get("type") == "agent_message"
                    and isinstance(event["item"].get("text"), str)
                ]
                tool_items = [
                    str(event["item"].get("type"))
                    for event in events
                    if event.get("type") == "item.completed"
                    and isinstance(event.get("item"), dict)
                    and event["item"].get("type")
                    not in {"agent_message", "reasoning"}
                ]
                started_events = [
                    event for event in events if event.get("type") == "thread.started"
                ]
                completed_events = [
                    event for event in events if event.get("type") == "turn.completed"
                ]
                if len(started_events) == 1:
                    thread_id = started_events[0].get("thread_id")
                if len(completed_events) == 1:
                    usage = completed_events[0].get("usage", {})
                if tool_items:
                    raise RuntimeError(
                        f"Luna worker attempted non-message items: {tool_items}"
                    )
                if len(messages) != 1:
                    raise ValueError(
                        "Luna worker must return exactly one spoken proposal"
                    )
                utterance = messages[0].strip()
                if (
                    not utterance
                    or len(utterance) > 900
                    or not _KOREAN.search(utterance)
                ):
                    raise ValueError("Luna worker returned an invalid Korean utterance")
                if len(started_events) != 1 or len(completed_events) != 1:
                    raise ValueError("Luna worker lifecycle receipt is incomplete")
            except Exception as error:
                failure = error
        destroyed = bool(temporary_path) and not Path(temporary_path).exists()
        if not destroyed:
            raise RuntimeError("Luna worker scratch context survived its request")
        common_receipt = {
            "model_id": self.model_id,
            "reasoning_effort": self.reasoning_effort,
            "role": role,
            "transport": "codex-exec-ephemeral-read-only",
            "proposal_only": True,
            "tool_call_count": len(tool_items),
            "resumed_model_session_used": False,
            "fresh_worker_thread_id": thread_id,
            "worker_context_destroyed": True,
            "worker_scratch_survived": False,
            "raw_prior_dialogue_pairs_visible": 0,
            "latency_ns": time.perf_counter_ns() - started,
            "usage": usage if isinstance(usage, dict) else {},
            "stderr_line_count": len(stderr.splitlines()),
            "authority": dict(AUTHORITY_FALSE),
        }
        if failure is not None:
            raw_bytes = utterance.encode("utf-8")
            raise LunaWorkerFailure(
                str(failure),
                {
                    **common_receipt,
                    "transport_valid": False,
                    "rejected_proposal_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                    "rejected_proposal_bytes": len(raw_bytes),
                    "rejected_proposal_bounded": _clip(utterance, 900),
                    "negative_worker_result_retained": True,
                },
            ) from failure
        return utterance, {
            **common_receipt,
            "transport_valid": True,
        }

    @staticmethod
    def _events(stdout: str) -> list[dict[str, Any]]:
        events = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and isinstance(value.get("type"), str):
                events.append(value)
        return events


def verify_distinct_fresh_workers(receipts: Sequence[Mapping[str, Any]]) -> bool:
    """Prove that no model thread was resumed across successful calls."""

    successful = [receipt for receipt in receipts if receipt.get("transport_valid")]
    identifiers = [receipt.get("fresh_worker_thread_id") for receipt in successful]
    return bool(successful) and all(
        isinstance(identifier, str) and identifier for identifier in identifiers
    ) and len(set(identifiers)) == len(identifiers) and all(
        receipt.get("resumed_model_session_used") is False
        and receipt.get("worker_context_destroyed") is True
        for receipt in successful
    )


def clear_empty_scratch_root(path: Path) -> None:
    """Remove only the dedicated empty worker scratch root after a stopped run."""

    if path.is_dir() and not any(path.iterdir()):
        shutil.rmtree(path)
