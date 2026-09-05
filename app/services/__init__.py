"""Application 서비스 5종 — 작업 14.5.

    Assumption    전제 집합 관리 (FR-601 계열을 앱 계층에서 노출)
    Scenario      시나리오 저장·불러오기 (14.4 / FR-902)
    CaseGrid      케이스 그리드 정의 (FR-802)
    Run           실행 이력·비동기 실행 (14.8)
    SupportSolver 지원 조합 도출 (FR-609)

각 서비스는 ``core.contracts`` 추상에 의존한다 — ``core.engine``·``core.cba`` 를
**직접 import 하지 않는다** (계층 규칙). 계산이 필요하면 계약 스텁으로 대체한다
(§16.1 W-6).
"""
from __future__ import annotations

from datetime import datetime

from app.services.model_composer import ModelCompositionService
from app.services.scenario_store import (
    InMemoryScenarioStore,
    ScenarioRecord,
    ScenarioStore,
)
from app.services.scenario_store_file import (
    JsonFileScenarioStore,
    build_scenario_store,
    resolve_scenario_store_dir,
)


class AssumptionService:
    """전제 집합 관리 — ``AssumptionProvider`` (core.contracts) 를 앱에 노출."""

    def __init__(self) -> None:
        # 계약 스텁 — 실제 AssumptionProvider 주입은 통합 시점
        self._sets: dict[str, object] = {}

    def register_set(self, name: str, provider: object) -> None:
        self._sets[name] = provider

    def get_set(self, name: str) -> object | None:
        return self._sets.get(name)


class ScenarioService:
    """시나리오 저장·불러오기 — ``ScenarioStore`` 위의 비즈니스 로직 (FR-902)."""

    def __init__(self, store: ScenarioStore) -> None:
        self._store = store

    def create(self, record: ScenarioRecord) -> ScenarioRecord:
        return self._store.save(record)

    def update(self, record: ScenarioRecord) -> ScenarioRecord:
        return self._store.save(record)

    def get(self, scenario_id: int) -> ScenarioRecord | None:
        return self._store.load(scenario_id)

    def list_for_owner(self, owner_id: int) -> list[ScenarioRecord]:
        return self._store.list_active(owner_id)

    def list_versions(self, scenario_id: int) -> list[ScenarioRecord]:
        return self._store.list_versions(scenario_id)

    def restore_version(self, scenario_id: int, version: int) -> ScenarioRecord:
        return self._store.restore_version(scenario_id, version)

    def delete(self, scenario_id: int) -> None:
        self._store.soft_delete(scenario_id)

    def restore(self, scenario_id: int) -> ScenarioRecord:
        return self._store.restore(scenario_id)

    def purge_expired(self, now: datetime | None = None) -> int:
        return self._store.purge_expired(now)


class CaseGridService:
    """케이스 그리드 정의 — FR-802. 변수 조합의 메타데이터만 다룬다."""

    def __init__(self) -> None:
        self._grids: dict[int, dict[str, object]] = {}
        self._next_id = 1

    def define(self, variables_json: str, coupled_sets_json: str = "") -> int:
        grid_id = self._next_id
        self._next_id += 1
        self._grids[grid_id] = {
            "variables_json": variables_json,
            "coupled_sets_json": coupled_sets_json,
        }
        return grid_id

    def get(self, grid_id: int) -> dict[str, object] | None:
        return self._grids.get(grid_id)


class RunService:
    """실행 이력·비동기 실행 — 14.8 ``AsyncRunExecutor`` 와 짝."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, object]] = {}

    def register(self, run_id: str, manifest: object) -> None:
        self._runs[run_id] = {"manifest": manifest, "status": "queued"}

    def status(self, run_id: str) -> str:
        rec = self._runs.get(run_id)
        return str(rec["status"]) if rec else "unknown"

    def mark_done(self, run_id: str) -> None:
        if run_id in self._runs:
            self._runs[run_id]["status"] = "done"


class SupportSolverService:
    """지원 조합 도출 — FR-609. 무지원 NPV 에서 목표 회수기간까지의 격차."""

    def gap_to_target(
        self, npv_no_support_won: int, target_npv_won: int
    ) -> int:
        """목표 NPV 대비 부족분 — 음수면 이미 충족."""
        return target_npv_won - npv_no_support_won


# **왜 `__all__` 을 두는가.** mypy strict 의 `no_implicit_reexport` 는 암묵
# 재수출을 거부한다 — 여기 적히지 않은 이름을 `app.services` 에서 import 하는
# 코드는 형 검사에서 「없는 이름」이 된다(`core/casegrid/e2e_runner.py::__all__`
# 주석이 같은 사유를 적는다). 새 이름을 여기 싣지 않으면 **호출은 되는데
# 검사만 빨간불**이 되고, 그 어긋남은 실행으로는 드러나지 않는다.
__all__ = (
    "AssumptionService",
    "CaseGridService",
    "InMemoryScenarioStore",
    "JsonFileScenarioStore",
    "ModelCompositionService",
    "RunService",
    "ScenarioRecord",
    "ScenarioService",
    "ScenarioStore",
    "SupportSolverService",
    "build_scenario_store",
    "resolve_scenario_store_dir",
)
