"""저장이 **프로세스를 넘어 사는가** — `FR-902-AC1`~`AC3`.

## 이 파일이 재는 구멍

`InMemoryScenarioStore` 는 인터페이스와 비즈니스 규칙(소프트 삭제·버전 이력·
30일 보관)을 고정했고 그 일을 다 했다. 못 하던 것은 **저장**이다 — 프로세스가
죽으면 사라지므로 사용자 문면 *「시나리오를 수정, 저장할 수 있어야 함」*·
*「기본 설정도 쉽게 변경, 저장, 로드할 수 있어야 함」* 이 성립하지 않는다.

## ★ 그래서 **같은 인스턴스에서 읽지 않는다**

같은 store 객체에 넣고 그 객체에서 꺼내면 인메모리 저장과 **구별되지 않는다** —
그 검사는 파일이 한 바이트도 안 써져도 초록불이다. 여기서는 매번 **새 인스턴스를
지어** 읽는다. 그것이 이 축의 요점이다.

## 저장 자리는 코드에 박지 않는다

시험은 `tmp_path` 를 준다(생성자 인자). 배포는 환경변수 또는 홈 밑 점 디렉터리를
쓴다 — 저장소 안(`fixtures/`·`docs/`)에는 쓰지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services import ScenarioRecord, ScenarioService, ScenarioStore
from app.services.scenario_store import SOFT_DELETE_RETENTION_DAYS
from app.services.scenario_store_file import (
    JsonFileScenarioStore,
    build_scenario_store,
    default_scenario_store_dir,
)


def _store(tmp_path: Path) -> JsonFileScenarioStore:
    """**새 인스턴스**를 짓는다 — 앞선 인스턴스의 기억을 물려받지 않는다."""
    return JsonFileScenarioStore(tmp_path)


# ── ⑦ 왕복 — 새 인스턴스가 같은 레코드를 준다 ──────────────────────────


@pytest.mark.req("FR-902-AC1")
def test_a_saved_scenario_survives_into_a_brand_new_store_instance(
    tmp_path: Path,
) -> None:
    """★ `save` 한 것을 **다른 객체**가 `load` 로 되찾는다.

    메타데이터 4종(이름·설명·태그·최종수정일시)이 함께 살아 와야 `FR-902-AC1`
    이 성립한다 — 이름만 남으면 목록 화면이 설명과 태그를 잃는다.
    """
    saved = _store(tmp_path).save(
        ScenarioRecord(
            id=0,
            name="제주 VPP",
            description="저장 왕복 검사",
            tags=("vpp", "jeju"),
            definition_json='{"baseline_arrangement": "자가용 유지"}',
            owner_id=101,
        )
    )
    assert saved.id != 0

    reopened = _store(tmp_path).load(saved.id)

    assert reopened is not None, "새 인스턴스가 저장된 시나리오를 못 찾았다"
    assert reopened.name == "제주 VPP"
    assert reopened.description == "저장 왕복 검사"
    assert reopened.tags == ("vpp", "jeju")
    assert reopened.definition_json == '{"baseline_arrangement": "자가용 유지"}'
    assert reopened.owner_id == 101
    assert reopened.version == 1
    assert isinstance(reopened.updated_at, datetime)
    assert reopened.updated_at.tzinfo is not None, (
        "시각이 tz 를 잃었다 — 되살린 시각을 비교하면 조용히 어긋난다"
    )


@pytest.mark.req("FR-902-AC1")
def test_ids_do_not_collide_across_instances(tmp_path: Path) -> None:
    """⚠ 다음 인스턴스가 **1번부터 다시 매기지 않는다.**

    다시 매기면 두 번째 저장이 첫 번째를 덮어쓰고, 그 손실은 예외 없이
    조용하다 — 목록에는 한 건만 남고 사라진 쪽을 가리키는 것이 없다.
    """
    first = _store(tmp_path).save(ScenarioRecord(id=0, name="첫째", owner_id=1))
    second = _store(tmp_path).save(ScenarioRecord(id=0, name="둘째", owner_id=1))

    assert first.id != second.id

    both = _store(tmp_path).list_active(1)
    assert sorted(r.name for r in both) == ["둘째", "첫째"]


# ── ⑧ 버전 이력이 인스턴스를 넘어 산다 ─────────────────────────────────


@pytest.mark.req("FR-902-AC2")
def test_version_history_and_restore_survive_a_new_instance(tmp_path: Path) -> None:
    """★ 버전 이력과 복원이 **다시 연 뒤에도** 성립한다 (`FR-902-AC2`).

    이력만 살고 복원이 안 되면 「이전 버전이 있다」는 목록에만 참이다.
    """
    created = _store(tmp_path).save(
        ScenarioRecord(id=0, name="초기 시나리오", description="버전 1", owner_id=10)
    )
    updated = _store(tmp_path).save(
        ScenarioRecord(
            id=created.id, name="수정된 시나리오", description="버전 2", owner_id=10
        )
    )
    assert updated.version == 2

    versions = _store(tmp_path).list_versions(created.id)
    assert [v.version for v in versions] == [1, 2]

    restored = _store(tmp_path).restore_version(created.id, version=1)
    assert restored.version == 3
    assert restored.name == "초기 시나리오"

    current = _store(tmp_path).load(created.id)
    assert current is not None and current.name == "초기 시나리오"
    assert [v.version for v in _store(tmp_path).list_versions(created.id)] == [1, 2, 3]


# ── ⑨ 소프트 삭제·복원·30일 보관이 인스턴스를 넘어 산다 ─────────────────


@pytest.mark.req("FR-902-AC3")
def test_soft_delete_and_restore_survive_a_new_instance(tmp_path: Path) -> None:
    """소프트 삭제가 **다시 연 뒤에도** 삭제이고, 복원이 되살린다.

    삭제가 안 살아남으면 다시 열었을 때 지운 것이 되돌아온다 — 그 상태는
    「복원했다」와 화면에서 구별되지 않는다.
    """
    saved = _store(tmp_path).save(ScenarioRecord(id=0, name="삭제 검사", owner_id=20))

    _store(tmp_path).soft_delete(saved.id)

    after_delete = _store(tmp_path).load(saved.id)
    assert after_delete is not None, "행이 통째로 사라졌다 — 소프트 삭제가 아니다"
    assert after_delete.is_deleted is True
    assert _store(tmp_path).list_active(20) == []

    _store(tmp_path).restore(saved.id)

    after_restore = _store(tmp_path).load(saved.id)
    assert after_restore is not None and after_restore.is_deleted is False
    assert [r.id for r in _store(tmp_path).list_active(20)] == [saved.id]


@pytest.mark.req("FR-902-AC3")
def test_the_thirty_day_retention_window_survives_a_new_instance(
    tmp_path: Path,
) -> None:
    """★ **30일 보관**이 다시 연 뒤에도 지켜진다 (`FR-902-AC3`).

    ⚠ 되돌려 받은 레코드의 `deleted_at` 을 손으로 고쳐 과거를 만들지 않는다 —
    파일 저장소에서 그 편집은 디스크에 닿지 않아 **아무것도 재지 못한다.**
    대신 `purge_expired(now=...)` 에 미래를 준다. 보관 창의 정의는 저장소가
    갖고(`SOFT_DELETE_RETENTION_DAYS`) 여기서 다시 적지 않는다.
    """
    kept = _store(tmp_path).save(ScenarioRecord(id=0, name="살아 있는 것", owner_id=30))
    doomed = _store(tmp_path).save(ScenarioRecord(id=0, name="지울 것", owner_id=30))
    _store(tmp_path).soft_delete(doomed.id)

    now = datetime.now(UTC)
    assert _store(tmp_path).purge_expired(now=now) == 0, "보관 창 안인데 지워졌다"
    assert _store(tmp_path).load(doomed.id) is not None

    expired_at = now + timedelta(days=SOFT_DELETE_RETENTION_DAYS + 1)
    assert _store(tmp_path).purge_expired(now=expired_at) == 1

    assert _store(tmp_path).load(doomed.id) is None, "보관 창이 지났는데 남아 있다"
    assert _store(tmp_path).load(kept.id) is not None, "삭제하지 않은 것이 지워졌다"
    assert _store(tmp_path).list_versions(doomed.id) == []


# ── ⑩ 남의 것을 주지 않는다 ────────────────────────────────────────────


@pytest.mark.req("FR-902-AC1")
def test_the_active_list_does_not_hand_over_someone_elses_scenarios(
    tmp_path: Path,
) -> None:
    """`list_active(owner_id)` 가 **자기 것만** 준다.

    저장이 프로세스를 넘어 살면 한 파일에 여러 사용자의 시나리오가 함께 쌓인다 —
    인메모리일 때는 프로세스마다 비어 있어 이 어긋남이 드러날 자리가 없었다.
    """
    store = _store(tmp_path)
    mine = store.save(ScenarioRecord(id=0, name="내 것", owner_id=1))
    store.save(ScenarioRecord(id=0, name="남의 것", owner_id=2))

    listed = _store(tmp_path).list_active(1)

    assert [r.id for r in listed] == [mine.id]


# ── 저장 자리 — 코드에 박지 않는다 ─────────────────────────────────────


def test_the_service_runs_on_the_file_store_unchanged(tmp_path: Path) -> None:
    """★ `ScenarioService` 가 **고치지 않고** 파일 저장소 위에서 돈다.

    프로토콜을 고쳤으면 여기서 드러난다 — 같은 인터페이스여야
    `InMemoryScenarioStore` 를 쓰는 기존 시험이 그대로 산다.
    """
    store: ScenarioStore = _store(tmp_path)
    service = ScenarioService(store)

    saved = service.create(ScenarioRecord(id=0, name="서비스 경유", owner_id=7))

    assert ScenarioService(_store(tmp_path)).get(saved.id) is not None


def test_the_store_choice_is_a_pure_function_of_the_configured_place(
    tmp_path: Path,
) -> None:
    """★ 「어디에 저장하는가」를 **인자로 받는다** — 부작용 없이 잰다.

    `app/deps.py::resolve_db_url` 이 같은 판단을 적어 두었다: 모듈 수준에서
    `os.environ` 을 직접 읽으면 검사가 「소스에 그 이름이 있는가」밖에 볼 수
    없고, **환경변수를 읽고 그 값을 버리도록 고쳐도 통과한다.**

    ⚠ 자리를 정하지 않은 경우(`None`)에 인메모리로 되돌리는 것은 그 파일의
    `DEFAULT_DB_URL` 과 같은 규약이다 — 기존 시험이 그것을 전제한다.
    """
    assert isinstance(build_scenario_store(tmp_path), JsonFileScenarioStore)
    assert not isinstance(build_scenario_store(None), JsonFileScenarioStore)


def test_the_default_place_is_under_the_home_directory_and_not_in_the_repo() -> None:
    """⛔ 기본 저장 자리는 **저장소 안이 아니다.**

    저장소 안(`fixtures/`·`docs/`)에 쓰면 사용자의 저장이 골든 픽스처·대장과
    같은 나무에 섞이고, `git status` 가 그것을 변경으로 센다.
    """
    default = default_scenario_store_dir()

    assert default.is_absolute()
    assert Path.home() in default.parents
    assert Path(__file__).resolve().parents[2] not in default.parents
