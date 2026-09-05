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

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services import ScenarioRecord, ScenarioService, ScenarioStore
from app.services.scenario_store import SOFT_DELETE_RETENTION_DAYS
from app.services.scenario_store_file import (
    _HISTORY,
    _NEXT_ID,
    _RECORDS,
    SCENARIO_STORE_ENV,
    STORE_FILENAME,
    JsonFileScenarioStore,
    build_scenario_store,
    default_scenario_store_dir,
    resolve_scenario_store_dir,
)
from core.contracts.validation import ValidationError


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


# ── R1 의 결함 재현 — 「모르면 멈춘다」가 저장 계층에서도 성립하는가 ──────
#
# 아래 열넷은 `result_R1.md` §0 의 **D-1 · D-2 · D-11 · D-12** 를 그대로 옮긴
# 것이다. 넷 다 **예외 없이 조용히** 사용자의 저장을 잃거나(D-1 ⓑ · D-2 ·
# D-12) 저장을 엉뚱한 자리에 떨어뜨렸다(D-11). 이 저장소의 규약은
# `core/model/parameters.py::ParameterCatalogueError` 와
# `core/assumption/provider.py` 의 `price_basis` 거부가 정한 **「모르면
# 멈춘다」** 이고, 이 자리들만 그것을 어기고 **메웠다.**


def _record_payload(scenario_id: int, name: str, owner_id: int = 7) -> dict[str, object]:
    """파일 안의 레코드 한 벌 — `_encode` 가 내는 키와 같은 모양.

    ⚠ 저장소의 `save` 로 짓지 않는다. `_write` 는 언제나 세 키를 다 쓰므로
    「`next_id` 가 없는 파일」·「최상위가 목록인 파일」 같은 갈래를 저장소로는
    만들 수 없다 — 그 갈래가 바로 R1 이 잰 것이다.
    """
    stamp = datetime.now(UTC).isoformat()
    return {
        "id": scenario_id,
        "name": name,
        "description": "",
        "tags": [],
        "definition_json": "",
        "owner_id": owner_id,
        "version": 1,
        "created_at": stamp,
        "updated_at": stamp,
        "deleted_at": None,
    }


def _write_store_file(tmp_path: Path, payload: object) -> Path:
    """저장 파일을 **손으로** 짓는다 — 다른 판이 쓴 것·손편집·백업 되돌리기."""
    path = tmp_path / STORE_FILENAME
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.req("FR-902-AC1")
def test_a_store_file_without_next_id_is_refused_instead_of_reissuing_id_one(
    tmp_path: Path,
) -> None:
    """★★★ `next_id` 를 **모르면 멈춘다** — 메우면 남의 시나리오를 통째로 덮는다.

    `result_R1.md` D-2 의 재현이다. `records` 는 있고 `next_id` 가 **없는**
    파일에 새 시나리오를 저장하면 `int(loaded.get(next_id, 1))` 이 id 1 을
    다시 발급해 기존 레코드와 그 **버전 이력 전체**를 덮었다. 예외는 어디에서도
    나지 않았다 — 실측 `list_active(7) = [(1, '사업B')]` ·
    `list_versions(1) = [(1, '사업B')]`.

    ⛔ 조용히 `max(id)+1` 로 고쳐 쓰지 않는다 — 그러면 파일이 왜 어긋났는지
    아무도 모르고, 다음 사람은 그 파일을 정상으로 읽는다.
    """
    _write_store_file(
        tmp_path,
        {
            _RECORDS: {"1": _record_payload(1, "사업A")},
            _HISTORY: {"1": [_record_payload(1, "사업A")]},
        },
    )

    with pytest.raises(ValidationError) as caught:
        _store(tmp_path).save(ScenarioRecord(id=0, name="사업B", owner_id=7))

    assert caught.value.field and caught.value.reason and caught.value.action, (
        "NFR-303 3요소가 비어 있다 — 운영자가 무엇을 고쳐야 하는지 모른다"
    )
    assert _NEXT_ID in caught.value.reason

    with pytest.raises(ValidationError):
        _store(tmp_path).load(1)


@pytest.mark.req("FR-902-AC1")
def test_a_next_id_that_would_reissue_a_live_id_is_refused(tmp_path: Path) -> None:
    """★ `next_id` 가 파일 안 최대 id **이하**면 거부한다 — 「있는데 어긋났다」.

    `result_R1.md` D-2 의 둘째 갈래다. 손편집·백업 되돌리기·D-1 ⓑ 로
    `next_id` 보다 큰 id 가 파일에 남으면 몇 번 저장한 뒤 그 레코드를 덮는다
    (실측 `새 id = 5  사업E 살아있나: 새`). `next_id` 가 있다는 것과 그것이
    다음 id 라는 것은 다르다.
    """
    _write_store_file(
        tmp_path,
        {
            _NEXT_ID: 3,
            _RECORDS: {"5": _record_payload(5, "사업E")},
            _HISTORY: {"5": [_record_payload(5, "사업E")]},
        },
    )

    with pytest.raises(ValidationError) as caught:
        _store(tmp_path).list_active(7)

    assert "5" in caught.value.reason, "어느 id 와 부딪히는지를 말하지 않는다"


@pytest.mark.req("FR-902-AC1")
@pytest.mark.parametrize("payload", [[], "문자열", None, 3])
def test_a_store_file_that_is_not_a_mapping_is_refused_with_the_three_parts(
    tmp_path: Path, payload: object
) -> None:
    """저장 파일의 최상위 형이 틀리면 **맨 예외가 아니라 거부**다 (`NFR-303`).

    `result_R1.md` D-12 의 재현이다 — 실측
    `top-level list -> AttributeError: 'list' object has no attribute 'get'` ·
    `null -> AttributeError: 'NoneType' object has no attribute 'get'`.
    멈추기는 했으나 3요소가 없어 운영자가 무엇을 고쳐야 하는지 모른다.
    """
    _write_store_file(tmp_path, payload)

    with pytest.raises(ValidationError) as caught:
        _store(tmp_path).load(1)

    assert caught.value.field and caught.value.reason and caught.value.action


@pytest.mark.req("FR-902-AC1")
def test_an_explicitly_empty_records_list_is_a_valid_state(tmp_path: Path) -> None:
    """`records: []` 는 **정말 다 지운 뒤**일 수 있다 — 빈 상태로 받는다.

    ⚠ `records` 키가 **없는** 것과 갈라야 한다(아래 시험). 키가 없으면
    「모른다」이고, 빈 목록은 「없다」이다 — `result_R1.md` D-12 가 그 둘을
    한 갈래로 묶어 조용히 잃던 자리다.
    """
    _write_store_file(tmp_path, {_NEXT_ID: 4, _RECORDS: [], _HISTORY: {}})

    assert _store(tmp_path).list_active(7) == []

    saved = _store(tmp_path).save(ScenarioRecord(id=0, name="다시 시작", owner_id=7))

    assert saved.id == 4, "빈 상태인데 id 를 1 부터 다시 매겼다"


@pytest.mark.req("FR-902-AC1")
@pytest.mark.parametrize("missing", [_RECORDS, _HISTORY])
def test_a_store_file_missing_a_section_is_refused(tmp_path: Path, missing: str) -> None:
    """세 칸 중 하나가 **없으면** 멈춘다 — 없는 것과 빈 것은 다르다.

    `_write` 는 언제나 셋을 함께 쓰므로, 하나가 없는 파일은 **이 저장소가
    쓴 것이 아니다.** 그것을 빈 값으로 메우면 `list_versions` 가 조용히 빈
    목록을 주고 `restore_version` 이 뒤늦게 `KeyError` 로 죽는다 —
    `result_R1.md` §1 ⓐ5 가 `history` 결손에서 실제로 잰 형태다.
    """
    payload: dict[str, object] = {_NEXT_ID: 9, _RECORDS: {}, _HISTORY: {}}
    del payload[missing]
    _write_store_file(tmp_path, payload)

    with pytest.raises(ValidationError) as caught:
        _store(tmp_path).load(1)

    assert missing in caught.value.reason


@pytest.mark.req("FR-902-AC1")
def test_a_truncated_store_file_names_the_file_the_operator_must_fix(
    tmp_path: Path,
) -> None:
    """잘린 JSON 은 **그대로 멈추되** 무엇을 고쳐야 하는지 말한다.

    `result_R1.md` §1 ⓐ5 — 빈 파일·잘린 JSON 은 이미 `JSONDecodeError` 로
    멈춘다(규약대로). 바뀌는 것은 문면뿐이다: 어느 파일인지 말하지 않으면
    운영자는 여러 배포 중 어느 자리를 열어야 하는지 모른다.
    """
    (tmp_path / STORE_FILENAME).write_text('{"records": {', encoding="utf-8")

    with pytest.raises(ValidationError) as caught:
        _store(tmp_path).load(1)

    assert STORE_FILENAME in caught.value.reason


@pytest.mark.req("FR-902-AC1")
def test_two_writes_do_not_share_one_staging_name(tmp_path: Path) -> None:
    """★ 옆에 쓰는 자리의 이름이 **호출마다 다르다** (`result_R1.md` D-1 ⓐ).

    이름이 `scenarios.json.tmp` 로 고정이면 두 쓰기가 부딪혀
    `PermissionError` 가 `save()` 밖으로 나가고 `POST /scenarios` 가 500 이
    된다 — 실측 `A: 성공=26 PermissionError=4` · `B: 성공=26
    PermissionError=4`.

    ⚠ **같은 디렉터리**여야 한다. `os.replace` 가 원자적인 것은 같은
    파일시스템 안에서이고, 다른 자리에 쓰면 교체가 복사가 되어 `_write` 의
    독스트링이 막으려던 「반쯤 쓰인 파일」이 되돌아온다.
    """
    store = _store(tmp_path)

    first_fd, first = store._open_staging()
    second_fd, second = store._open_staging()
    os.close(first_fd)
    os.close(second_fd)

    try:
        assert first != second, "스테이징 이름이 고정이다 — 두 쓰기가 부딪힌다"
        assert first.parent == tmp_path and second.parent == tmp_path
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


@pytest.mark.req("FR-902-AC1")
def test_a_staging_file_held_open_by_someone_else_does_not_break_a_save(
    tmp_path: Path,
) -> None:
    """★ 남이 잡고 있는 옛 이름의 스테이징 파일이 저장을 막지 않는다.

    윈도 실측에서 고정 이름이면 `staging.replace()` 가
    `PermissionError [WinError 32]` 로 죽었고 그것이 `save()` 밖으로 나갔다.
    ⚠ POSIX 에서는 열린 파일도 `os.replace` 가 성공하므로 이 시험은 그
    자리에서 약하다 — 이름이 갈리는지는 위 시험이 따로 재고, 여기서는
    **끝까지 도는 것**을 잰다.
    """
    _store(tmp_path).save(ScenarioRecord(id=0, name="첫째", owner_id=1))

    with (tmp_path / f"{STORE_FILENAME}.tmp").open("w", encoding="utf-8") as holder:
        holder.write("{}")
        holder.flush()
        second = _store(tmp_path).save(ScenarioRecord(id=0, name="둘째", owner_id=1))

    assert second.id != 0
    assert sorted(r.name for r in _store(tmp_path).list_active(1)) == ["둘째", "첫째"]


@pytest.mark.req("FR-902-AC1")
def test_a_save_that_would_lose_a_concurrent_write_reads_again_instead(
    tmp_path: Path,
) -> None:
    """★★ 읽고-쓰기 **사이에 파일이 바뀌면 다시 읽는다** — 잃지 않는다.

    `result_R1.md` D-1 ⓑ 의 재현이다. 두 프로세스가 각각 30번 저장했을 때
    **「성공했다」를 돌려받은 30건이 파일에 없었다.** 예외는 아무 데서도 나지
    않았으므로 사용자는 목록에서 없어진 것을 나중에 안다 — 그것이 이 결함의
    본질이고, 「성공」을 돌려주고 잃는 것만은 하지 않는다.

    ⚠ **프로세스를 띄우지 않는다**(느린 시험을 만들지 않는다). 두 store
    인스턴스로 `_read`→`_write` 사이를 짓고 그 사이를 이 시험이 연다.
    """
    reader = _store(tmp_path)
    other = _store(tmp_path)
    attempts: list[int] = []

    def mutate(state: dict[str, object]) -> int:
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            other.save(ScenarioRecord(id=0, name="사이에 낀 저장", owner_id=1))
        state[_NEXT_ID] = int(state[_NEXT_ID]) + 10
        return int(state[_NEXT_ID])

    reader._update(mutate)

    assert attempts == [1, 2], "파일이 바뀐 것을 못 보고 그대로 덮었다"
    assert [r.name for r in _store(tmp_path).list_active(1)] == ["사이에 낀 저장"], (
        "성공을 돌려받은 저장이 사라졌다"
    )


@pytest.mark.req("FR-902-AC1")
def test_a_second_collision_refuses_rather_than_reporting_a_success(
    tmp_path: Path,
) -> None:
    """★ 다시 읽고도 또 바뀌었으면 **거부한다** — 잠금을 새로 발명하지 않는다.

    ⚠ 이것이 이 라운드의 경계다: 파일 잠금은 플랫폼마다 다르고 범위가 아니다.
    여기까지가 「잃지 않게」이며, 거부는 **남의 저장을 지우지 않는다** —
    끼어든 둘이 그대로 남아 있는 것을 함께 잰다.
    """
    reader = _store(tmp_path)
    other = _store(tmp_path)

    def mutate(state: dict[str, object]) -> None:
        other.save(ScenarioRecord(id=0, name="계속 끼어든다", owner_id=1))
        state[_NEXT_ID] = int(state[_NEXT_ID]) + 10

    with pytest.raises(ValidationError) as caught:
        reader._update(mutate)

    assert caught.value.field and caught.value.action
    assert len(_store(tmp_path).list_active(1)) == 2, "거부가 남의 저장을 지웠다"


@pytest.mark.req("FR-902-AC1")
@pytest.mark.parametrize("configured", [".", "fixtures", "docs/..", "a/b"])
def test_a_relative_store_place_is_refused(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    """★ 상대경로는 저장을 **현재 작업 디렉터리**에 떨어뜨린다 — 거부한다.

    `result_R1.md` D-11 의 재현이다: `DER_SCENARIO_STORE='.'` → 쓸 파일이
    `scenarios.json`(저장소 뿌리) · `'fixtures'` → `fixtures/scenarios.json`.
    `resolve_scenario_store_dir` 의 독스트링이 *「빈 경로를 그대로 넘기면
    저장이 현재 작업 디렉터리(저장소 뿌리일 수 있다)로 떨어진다」* 로 막으려던
    결과를 `"."` 이 **정확히** 낸다. 모듈 머리말의 ⛔ *「저장소
    안(`fixtures/`·`docs/`)에 쓰지 않는다」* 를 강제하는 것이 없었다.
    """
    monkeypatch.setenv(SCENARIO_STORE_ENV, configured)

    with pytest.raises(ValidationError) as caught:
        resolve_scenario_store_dir()

    assert SCENARIO_STORE_ENV in caught.value.reason
    assert caught.value.action


@pytest.mark.req("FR-902-AC1")
@pytest.mark.parametrize("configured", ["", "   ", "\t "])
def test_a_blank_store_place_means_not_configured(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    """공백만 있는 값은 **「설정하지 않음」**이다 — 이름이 공백인 자리를 짓지 않는다.

    실측(`result_R1.md` D-11): `DER_SCENARIO_STORE='   '` 이
    `WindowsPath('   ')` 를 지나 그 밑에 `scenarios.json` 을 썼다. 빈값
    방어가 `""` 하나만 잡았기 때문이다.
    """
    monkeypatch.setenv(SCENARIO_STORE_ENV, configured)

    assert resolve_scenario_store_dir() is None


@pytest.mark.req("FR-902-AC1")
def test_an_absolute_store_place_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """양성 — 절대경로는 그대로 받는다. 거부만 재면 전부 막는 구현도 만점이다."""
    monkeypatch.setenv(SCENARIO_STORE_ENV, f"  {tmp_path}  ")

    assert resolve_scenario_store_dir() == tmp_path
