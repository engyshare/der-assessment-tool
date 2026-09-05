"""시나리오 저장을 **프로세스 밖으로** 내보낸다 — `FR-902-AC1`~`AC3` · R63/P3.

## 왜 이 파일이 생겼는가

`InMemoryScenarioStore` 는 인터페이스와 비즈니스 규칙(소프트 삭제 · 버전 이력 ·
30일 보관)을 고정했고 그 일을 다 했다. 못 하던 것은 **저장**이다 — 프로세스가
죽으면 사라지므로 사용자 문면(*「시나리오를 수정, 저장할 수 있어야 함」* ·
*「기본 설정도 쉽게 변경, 저장, 로드할 수 있어야 함」* — `docs/decisions-2026
-09-05-R63.md` §1)이 성립하지 않는다.

## ⚠ DB 를 세우지 않는다

`infra/orm/scenario.py` 에 테이블(`scenarios`·`scenario_overrides`)이 있으나
alembic 마이그레이션과 세션 배선을 이 라운드에 세우는 것은 범위가 아니다.
사용자가 요구한 것은 **화면이 저장·로드를 하는 것**이고, 그것은 파일 하나로
선다. 그 테이블로 옮길 때 이 구현은 **같은 프로토콜**을 구현한 다른 클래스로
갈아 끼우면 되고, 호출부는 아무것도 고치지 않는다 — `ScenarioStore` 를 고치지
않은 이유가 그것이다.

## ★ 프로토콜을 고치지 않는다

`ScenarioStore` 는 `InMemoryScenarioStore` 와 **같은 인터페이스**여야 한다.
고치면 인메모리 저장소를 쓰는 기존 검사가 함께 깨지고, 그때 무엇이 회귀이고
무엇이 새 규약인지 가릴 수 없다.

## 저장 자리를 코드에 박지 않는다

    생성자 인자        시험이 `tmp_path` 를 준다
    환경변수           배포가 자리를 정한다 (`SCENARIO_STORE_ENV`)
    아무것도 없으면    사용자 홈 밑 점 디렉터리

⛔ **저장소 안(`fixtures/`·`docs/`)에 쓰지 않는다.** 쓰면 사용자의 저장이 골든
픽스처·대장과 같은 나무에 섞이고 `git status` 가 그것을 변경으로 센다.

## 매 호출마다 파일을 다시 읽는다

객체 안에 상태를 캐시해 두면 **같은 인스턴스에서 읽는 검사만 초록불**이 되고,
그것은 인메모리 저장과 구별되지 않는다. 게다가 한 파일을 여러 프로세스(웹
워커)가 볼 수 있으므로 캐시는 조용히 낡는다.
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.scenario_store import (
    SOFT_DELETE_RETENTION_DAYS,
    InMemoryScenarioStore,
    ScenarioRecord,
    ScenarioStore,
)

#: 저장 자리를 정하는 환경변수. `app/deps.py::DB_URL_ENV` 와 같은 규약이다 —
#: 이름을 여기 한 곳이 갖는다.
SCENARIO_STORE_ENV = "DER_SCENARIO_STORE"

#: 자리를 정하지 않았을 때 쓰는 홈 밑 점 디렉터리. **경로 전체를 리터럴로
#: 박지 않는다** — 조각을 상수로 두고 `Path.home()` 위에서 짓는다.
HOME_STORE_DIRNAME = ".der-evaluator"
HOME_STORE_SUBDIR = "scenarios"

#: 한 디렉터리 안의 저장 파일 이름.
STORE_FILENAME = "scenarios.json"

_RECORDS = "records"
_HISTORY = "history"
_NEXT_ID = "next_id"


def default_scenario_store_dir() -> Path:
    """자리를 정하지 않았을 때의 저장 자리 — **사용자 홈 밑**이다."""
    return Path.home() / HOME_STORE_DIRNAME / HOME_STORE_SUBDIR


def resolve_scenario_store_dir() -> Path | None:
    """배포가 정한 저장 자리. **정하지 않았으면 `None`** 이다.

    **함수로 빼 둔 이유**는 `app/deps.py::resolve_db_url` 이 적어 두었다 —
    모듈 수준에서 `os.environ` 을 직접 읽으면 검사가 「소스에 그 이름이
    있는가」밖에 볼 수 없고, **환경변수를 읽고 그 값을 버리도록 고쳐도
    통과한다.**

    빈 문자열은 「설정하지 않음」으로 본다 — 빈 경로를 그대로 넘기면 저장이
    현재 작업 디렉터리(저장소 뿌리일 수 있다)로 떨어진다.
    """
    configured = os.environ.get(SCENARIO_STORE_ENV)
    return Path(configured) if configured else None


def build_scenario_store(directory: Path | None) -> ScenarioStore:
    """자리가 있으면 파일 저장소, 없으면 인메모리.

    ⚠ **인자를 받는 순수 함수다** — 환경변수를 여기서 읽으면 위 함수의
    독스트링이 적은 함정을 그대로 다시 밟는다.

    ⚠ **자리를 정하지 않았을 때 인메모리로 되돌리는 것**은
    `app/deps.py::DEFAULT_DB_URL`(`"sqlite://"`)과 같은 규약이다 — 그 자리
    주석이 *「기존 테스트가 이것을 전제한다」* 로 사유를 적는다. 정하지 않은
    배포가 사용자 홈에 파일을 만들기 시작하면, 검사가 서로의 저장을 물려받아
    **실행 순서에 따라 결과가 달라진다.**
    """
    if directory is None:
        return InMemoryScenarioStore()
    return JsonFileScenarioStore(directory)


def _encode(record: ScenarioRecord) -> dict[str, Any]:
    """레코드 하나를 JSON 이 담을 수 있는 모양으로."""
    return {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "tags": list(record.tags),
        "definition_json": record.definition_json,
        "owner_id": record.owner_id,
        "version": record.version,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "deleted_at": None if record.deleted_at is None else record.deleted_at.isoformat(),
    }


def _decode(raw: dict[str, Any]) -> ScenarioRecord:
    """JSON 한 벌을 레코드로.

    ⚠ **태그를 튜플로 되돌린다.** `ScenarioRecord.tags` 가 튜플인 것은 밖에서
    고칠 수 없게 하려는 것이고(`NFR-205`), 목록으로 되살리면 저장을 한 번
    거친 레코드만 가변이 된다 — 그 차이는 예외 없이 조용하다.

    ⚠ **시각의 tz 를 잃지 않는다.** 잃으면 `purge_expired` 의 비교가
    `TypeError` 로 죽거나(둘 중 하나만 naive), 더 나쁘게는 다른 시각대의 값과
    조용히 견주어진다.
    """
    deleted_at = raw.get("deleted_at")
    return ScenarioRecord(
        id=int(raw["id"]),
        name=str(raw["name"]),
        description=str(raw.get("description", "")),
        tags=tuple(raw.get("tags", ())),
        definition_json=str(raw.get("definition_json", "")),
        owner_id=int(raw.get("owner_id", 0)),
        version=int(raw.get("version", 1)),
        created_at=datetime.fromisoformat(raw["created_at"]),
        updated_at=datetime.fromisoformat(raw["updated_at"]),
        deleted_at=None if deleted_at is None else datetime.fromisoformat(deleted_at),
    )


class JsonFileScenarioStore:
    """`ScenarioStore` 의 **파일 구현** — 저장이 프로세스를 넘어 산다.

    `InMemoryScenarioStore` 와 **같은 규칙**을 지킨다: 새 저장은 버전 1 로
    이력에 서고, 수정은 버전을 올려 이력에 쌓이며, 삭제는 소프트 삭제이고
    `SOFT_DELETE_RETENTION_DAYS` 가 지나야 행이 진짜 사라진다. 규칙을 여기서
    다시 정하지 않는다 — 두 구현이 다른 규칙을 가지면 저장 자리를 바꾸는 것이
    동작을 바꾸는 것이 된다.
    """

    def __init__(self, directory: Path | str | None = None) -> None:
        self._path = Path(directory or default_scenario_store_dir()) / STORE_FILENAME

    # ── 파일 입출력 ────────────────────────────────────────────────────

    def _read(self) -> dict[str, Any]:
        """저장 파일 한 벌. **없으면 빈 상태**이지 오류가 아니다."""
        if not self._path.exists():
            return {_NEXT_ID: 1, _RECORDS: {}, _HISTORY: {}}
        loaded = json.loads(self._path.read_text(encoding="utf-8"))
        return {
            _NEXT_ID: int(loaded.get(_NEXT_ID, 1)),
            _RECORDS: dict(loaded.get(_RECORDS, {})),
            _HISTORY: dict(loaded.get(_HISTORY, {})),
        }

    def _write(self, state: dict[str, Any]) -> None:
        """**옆에 쓰고 갈아 끼운다.**

        같은 파일에 곧바로 쓰면 도중에 죽었을 때 반쯤 쓰인 JSON 이 남고, 그때
        저장소는 「비었다」가 아니라 **읽을 수 없다** 가 된다 — 사용자가 저장한
        것 전부를 한 번에 잃는 형태다.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        staging = self._path.with_suffix(self._path.suffix + ".tmp")
        staging.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        staging.replace(self._path)

    # ── ScenarioStore 프로토콜 ─────────────────────────────────────────

    def save(self, record: ScenarioRecord) -> ScenarioRecord:
        """새 시나리오는 버전 1 로, 기존 시나리오는 **버전을 올려** 저장한다."""
        state = self._read()
        now = datetime.now(UTC)

        if record.id == 0:
            new_id = int(state[_NEXT_ID])
            state[_NEXT_ID] = new_id + 1
            fresh = dataclasses.replace(
                record, id=new_id, version=1, created_at=now, updated_at=now
            )
            state[_RECORDS][str(new_id)] = _encode(fresh)
            state[_HISTORY][str(new_id)] = [_encode(fresh)]
            self._write(state)
            return fresh

        stored = state[_RECORDS].get(str(record.id))
        if stored is None:
            raise KeyError(f"시나리오 {record.id} 가 없습니다")
        existing = _decode(stored)

        # ⚠ 소유자·생성시각·삭제표시는 **기존 것을 이긴다.** 수정 요청이
        # 소유자를 바꿀 수 있으면 남의 시나리오를 가져올 수 있고, 그 이동은
        # 목록에서 「없어졌다」로만 보인다 (인메모리 구현과 같은 판단이다).
        updated = dataclasses.replace(
            record,
            id=existing.id,
            owner_id=existing.owner_id,
            version=existing.version + 1,
            created_at=existing.created_at,
            updated_at=now,
            deleted_at=existing.deleted_at,
        )
        state[_RECORDS][str(record.id)] = _encode(updated)
        state[_HISTORY].setdefault(str(record.id), []).append(_encode(updated))
        self._write(state)
        return updated

    def load(self, scenario_id: int) -> ScenarioRecord | None:
        stored = self._read()[_RECORDS].get(str(scenario_id))
        return None if stored is None else _decode(stored)

    def list_active(self, owner_id: int) -> list[ScenarioRecord]:
        """**자기 것만** 준다. 한 파일에 여러 사용자의 시나리오가 함께 쌓인다."""
        records = (_decode(raw) for raw in self._read()[_RECORDS].values())
        return [r for r in records if r.owner_id == owner_id and not r.is_deleted]

    def list_versions(self, scenario_id: int) -> list[ScenarioRecord]:
        """버전 이력 — 저장된 버전 전체 목록 (`FR-902-AC2`)."""
        return [_decode(raw) for raw in self._read()[_HISTORY].get(str(scenario_id), [])]

    def restore_version(self, scenario_id: int, version: int) -> ScenarioRecord:
        """이전 버전 복원 (`FR-902-AC2`). 복원도 **새 버전으로** 이력에 남는다."""
        state = self._read()
        history = state[_HISTORY].get(str(scenario_id), [])
        target = next(
            (_decode(raw) for raw in history if int(raw["version"]) == version), None
        )
        if target is None:
            raise KeyError(f"시나리오 {scenario_id} 의 버전 {version} 이 없습니다")

        stored = state[_RECORDS].get(str(scenario_id))
        if stored is None:
            raise KeyError(f"시나리오 {scenario_id} 가 없습니다")

        restored = dataclasses.replace(
            target,
            version=_decode(stored).version + 1,
            updated_at=datetime.now(UTC),
            deleted_at=None,
        )
        state[_RECORDS][str(scenario_id)] = _encode(restored)
        state[_HISTORY].setdefault(str(scenario_id), []).append(_encode(restored))
        self._write(state)
        return restored

    def soft_delete(self, scenario_id: int) -> None:
        """소프트 삭제 — `deleted_at` 만 찍는다 (`FR-902-AC3`). 행은 남는다."""
        state = self._read()
        stored = state[_RECORDS].get(str(scenario_id))
        if stored is None:
            raise KeyError(f"시나리오 {scenario_id} 가 없습니다")
        record = _decode(stored)
        record.soft_delete()
        state[_RECORDS][str(scenario_id)] = _encode(record)
        self._write(state)

    def restore(self, scenario_id: int) -> ScenarioRecord:
        """소프트 삭제 복원 (`FR-902-AC3`)."""
        state = self._read()
        stored = state[_RECORDS].get(str(scenario_id))
        if stored is None:
            raise KeyError(f"시나리오 {scenario_id} 가 없습니다")
        record = _decode(stored)
        record.restore()
        state[_RECORDS][str(scenario_id)] = _encode(record)
        self._write(state)
        return record

    def purge_expired(self, now: datetime | None = None) -> int:
        """보관 기간이 지난 소프트삭제 행을 **진짜** 지운다 (`FR-902-AC3`).

        보관 기간의 정의는 `scenario_store.SOFT_DELETE_RETENTION_DAYS` 하나가
        갖는다 — 여기서 다시 적으면 두 저장소의 창이 갈릴 수 있고, 그 어긋남은
        「복원이 안 된다」로만 나타난다.
        """
        state = self._read()
        cutoff = (now or datetime.now(UTC)) - timedelta(days=SOFT_DELETE_RETENTION_DAYS)
        expired = [
            key
            for key, raw in state[_RECORDS].items()
            if raw.get("deleted_at") is not None
            and datetime.fromisoformat(raw["deleted_at"]) < cutoff
        ]
        for key in expired:
            del state[_RECORDS][key]
            state[_HISTORY].pop(key, None)
        if expired:
            self._write(state)
        return len(expired)
