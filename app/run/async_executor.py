"""비동기 실행 — 작업 14.8.

조회 API 가 금방 돌아도 «실행» (디스패치 8760시간 + CBA)은 수 초~수십 초 걸린다.
즉시 ``작업 ID`` 를 반환하고 폴링으로 상태를 본다 — 클라이언트가 동기 대기하지
않는다.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class RunTask:
    """비동기 실행 1건 — ID·상태·결과."""

    id: str
    status: str = "queued"  # queued | running | done | failed
    result: object | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AsyncRunExecutor:
    """비동기 실행 큐 — ``submit()`` 즉시 ID 반환, ``poll()`` 로 상태 조회.

    **여기서 실제 디스패치를 돌리지 않는다** — ``core.engine`` 을 import 하지
    않는다 (계층 규칙). ``task_fn`` 을 생성자에서 받아 실행만 한다. 통합 시점에
    실제 엔진 호출을 주입한다 (§16.1 W-6).
    """

    def __init__(self) -> None:
        self._tasks: dict[str, RunTask] = {}

    def submit(
        self, task_fn: Callable[[str], object], manifest: object | None = None
    ) -> str:
        """실행을 큐에 넣고 ID 를 즉시 반환한다.

        ``task_fn`` 은 run_id 를 받아 결과를 반환하는 callable 이다. 동기적으로
        즉시 실행한다(단순 구현) — 실제 비동기는 통합 시점에 ``asyncio.create_task``
        또는 백그라운드 워커로 교체한다. **인터페이스(``submit`` → ID, ``poll`` →
        상태)는 그대로다.**
        """
        run_id = uuid.uuid4().hex[:12]
        task = RunTask(id=run_id, status="running")
        self._tasks[run_id] = task
        try:
            task.result = task_fn(run_id)
            task.status = "done"
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
        return run_id

    def poll(self, run_id: str) -> RunTask | None:
        """상태 폴링 — ``done``/``failed`` 가 아니면 클라이언트가 다시 폴링한다."""
        return self._tasks.get(run_id)
