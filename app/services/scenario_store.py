"""시나리오·전제 저장/불러오기 — 작업 14.4 / FR-902-AC1~AC3.

    AC1: 이름·설명·태그·최종수정일시 부여
    AC2: 버전 이력 → 이전 버전 복원 가능
    AC3: 삭제는 소프트 삭제(30일 보관)

**소프트 삭제가 «30일 보관» 인 것은 복원 창이다.** 30일이 지나면 행이 진짜
삭제된다 — «삭제됨» 플래그만 두고 영구 보관하면 «삭제» 가 의미 없다.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

SOFT_DELETE_RETENTION_DAYS = 30  # FR-902-AC3


@dataclass
class ScenarioRecord:
    """시나리오 1건 — FR-902-AC1 메타데이터."""

    id: int
    name: str
    description: str = ""
    tags: tuple[str, ...] = ()
    definition_json: str = ""
    owner_id: int = 0
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None  # 소프트 삭제 — None 이면 활성

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, at: datetime | None = None) -> None:
        """소프트 삭제 — ``deleted_at`` 만 찍는다 (FR-902-AC3). 행은 남는다."""
        if self.deleted_at is not None:
            return
        self.deleted_at = at or datetime.now(UTC)
        self.updated_at = self.deleted_at

    def restore(self) -> None:
        """소프트 삭제 복원 — ``deleted_at`` 을 None 으로."""
        self.deleted_at = None
        self.updated_at = datetime.now(UTC)


class ScenarioStore(Protocol):
    """시나리오 저장소 프로토콜 — in-memory 와 DB 구현이 같은 인터페이스."""

    def save(self, record: ScenarioRecord) -> ScenarioRecord: ...
    def load(self, scenario_id: int) -> ScenarioRecord | None: ...
    def list_active(self, owner_id: int) -> list[ScenarioRecord]: ...
    def list_versions(self, scenario_id: int) -> list[ScenarioRecord]: ...
    def restore_version(
        self, scenario_id: int, version: int
    ) -> ScenarioRecord: ...
    def soft_delete(self, scenario_id: int) -> None: ...
    def restore(self, scenario_id: int) -> ScenarioRecord: ...
    def purge_expired(self, now: datetime | None = None) -> int: ...


class InMemoryScenarioStore:
    """테스트·로컬 개발용 in-memory 저장소.

    DB 구현(infra.orm.Scenario)은 운영 배포 시 추가한다 — 여기서는 인터페이스와
    비즈니스 규칙(소프트 삭제·버전 이력·30일 보관)을 고정한다.
    """

    def __init__(self) -> None:
        self._records: dict[int, ScenarioRecord] = {}
        self._history: dict[int, list[ScenarioRecord]] = {}
        self._next_id = 1

    def save(self, record: ScenarioRecord) -> ScenarioRecord:
        now = datetime.now(UTC)
        if record.id == 0:
            record.id = self._next_id
            self._next_id += 1
            record.version = 1
            record.created_at = now
            record.updated_at = now
            snapshot = dataclasses.replace(record)
            self._records[record.id] = snapshot
            self._history[record.id] = [snapshot]
            return snapshot

        existing = self._records.get(record.id)
        if existing is None:
            raise KeyError(f"시나리오 {record.id} 가 없습니다")

        new_version = existing.version + 1
        updated = dataclasses.replace(
            record,
            id=existing.id,
            owner_id=existing.owner_id,
            version=new_version,
            created_at=existing.created_at,
            updated_at=now,
            deleted_at=existing.deleted_at,
        )
        self._records[record.id] = updated
        if record.id not in self._history:
            self._history[record.id] = []
        self._history[record.id].append(updated)
        return updated

    def load(self, scenario_id: int) -> ScenarioRecord | None:
        return self._records.get(scenario_id)

    def list_active(self, owner_id: int) -> list[ScenarioRecord]:
        return [
            r
            for r in self._records.values()
            if r.owner_id == owner_id and not r.is_deleted
        ]

    def list_versions(self, scenario_id: int) -> list[ScenarioRecord]:
        """버전 이력 — 저장된 버전 전체 목록."""
        return list(self._history.get(scenario_id, []))

    def restore_version(self, scenario_id: int, version: int) -> ScenarioRecord:
        """이전 버전 복원 (FR-902-AC2). 복원도 새 버전으로 이력에 기록된다."""
        history = self._history.get(scenario_id, [])
        target = next((v for v in history if v.version == version), None)
        if target is None:
            raise KeyError(f"시나리오 {scenario_id} 의 버전 {version} 이 없습니다")

        current = self._records.get(scenario_id)
        if current is None:
            raise KeyError(f"시나리오 {scenario_id} 가 없습니다")

        now = datetime.now(UTC)
        restored = dataclasses.replace(
            target,
            version=current.version + 1,
            updated_at=now,
            deleted_at=None,
        )
        self._records[scenario_id] = restored
        self._history[scenario_id].append(restored)
        return restored

    def soft_delete(self, scenario_id: int) -> None:
        rec = self._records.get(scenario_id)
        if rec is None:
            raise KeyError(f"시나리오 {scenario_id} 가 없습니다")
        rec.soft_delete()

    def restore(self, scenario_id: int) -> ScenarioRecord:
        """소프트 삭제 복원 (FR-902-AC3)."""
        rec = self._records.get(scenario_id)
        if rec is None:
            raise KeyError(f"시나리오 {scenario_id} 가 없습니다")
        rec.restore()
        return rec

    def purge_expired(self, now: datetime | None = None) -> int:
        """``SOFT_DELETE_RETENTION_DAYS`` 지난 소프트삭제 행을 진짜 삭제한다.

        반환: 삭제된 행 수. **30일 보관** 이 FR-902-AC3 — 영구 보관하면 «삭제» 가
        의미 없고, 30일 미만이면 복원 창이 닫힌다.
        """
        cutoff = (now or datetime.now(UTC)) - timedelta(
            days=SOFT_DELETE_RETENTION_DAYS
        )
        expired = [
            rid
            for rid, r in self._records.items()
            if r.deleted_at is not None and r.deleted_at < cutoff
        ]
        for rid in expired:
            del self._records[rid]
            self._history.pop(rid, None)
        return len(expired)
