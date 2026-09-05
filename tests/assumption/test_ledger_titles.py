"""분석 설정 대장 항목의 **한국어 라벨** — 착수 목록 54 · 47ⓐ.

## 왜 이 파일이 있나

사용자 문면은 *「"옥상 태양광 · azimuth_deg" 와 같이 coding 상의 변수명을 병기하지
않음」*(`docs/decisions-2026-09-05-R63.md` §1 「용어」)이다. R63 이 **자원 파라미터
85건**에 라벨 원천(`core/model/parameters.py::LABEL_BY_NAME`·`resolve_label`)을
세워 그 꼴을 0건으로 만들었으나, **대장 항목은 화면에 키(`capex.pv.rooftop` 꼴)로
서 있었다** — 브라우저 실측이 설정 화면 본문에서 그 꼴 159건을 셌다
(`.orch/R63/result_V2.md` §0).

★ **조항 위반은 아니다**(「병기」가 아니라 키만 보인다). 사람이 읽는 화면에
데이터 식별자가 서 있는 것이 사용자 요구의 정신에 어긋날 뿐이다.

## ★★ 라벨 원천은 **대장 자신**이다 — `core/` 에 사전을 만들지 않는다

`ParameterSpec.label` 은 `LABEL_BY_NAME` 이라는 코드 사전에서 온다. 자원
파라미터의 이름이 **코드에만** 있기 때문이다. 대장은 다르다 — 항목의 정본이
`docs/assumptions.yaml` 이고 그 파일이 이미 `title:` 을 갖는다. `core/` 에
`LABEL_BY_KEY` 를 만들면 **같은 사실이 두 곳에 살고** 대장이 늘 때 낡는다.

⇒ 자료형(`AssumptionItem.title`)은 라벨을 **나르기만** 하고 짓지 않는다.

## ⚠⚠ 오케스트레이터 판정의 전제 하나가 실물과 달랐다

`WP-NEXT.md` §A-2 는 *「대장 39항목에는 라벨이 없다」* 로 적고 *「없는 항목에
채우는 일이다」* 라고 지시했다. **실측은 그 반대다** — 이 검사가 처음 돌 때
`title` 이 없는 항목은 **0 건**이었다(전 41 항목 · `blocked` 둘 포함).
어긋나 있던 것은 대장이 아니라 **자료형과 화면**이었다: `load_from_yaml` 이
`title` 을 읽지 않고 버렸고, 그래서 화면이 그릴 것이 키밖에 없었다.

★ 그래도 이 검사를 「이미 초록이니 필요 없다」로 두지 않는다. 라벨이 **없어도
아무 일도 일어나지 않는** 것이 그 상태를 만든 원인이고, 세지 않으면 다음 항목이
조용히 라벨 없이 등재된다 — `core/model/parameters.py` 머리말이 *「라벨이 없는
것은 멈추는 자리가 아니라 **세는 자리**다」* 로 같은 판단을 적었다.

## ⚠ `@pytest.mark.req(...)` — **달지 않았다**

사용자 요구(*「변수명을 병기하지 않음」*)를 받는 수용기준이 spec 에 없다. 없는
조항을 지어 붙이면 `docs/traceability.md` 가 거짓 인용을 싣는다 —
`tests/app/test_screen_words.py` 머리말이 같은 자리에서 같은 판정을 적었다.

## ★ 47ⓐ(가구 수·유형)도 여기서 선다 — **자리만. 값은 비어 있다**

지시문 §A-3 4항이 요구한 가구 수·유형의 대장 자리를 `track: blocked` 로 세웠다.
⚠⚠ **값을 지어내지 않는다** — 실증단지 가구 수를 우리가 정하면 그 수로 돌린
계산을 우리가 검증하게 된다(§13.0.2 자기충족). 자리가 서면 다음 라운드가 채운다.

⚠ **`q_ref` 를 달지 않았다.** spec §15.1 Q 표에 이 물음의 행이 없고, 없는 Q
번호를 적으면 같은 검사기의 Q 목록 양방향 대조가 「유령 Q」로 잡는다. Q 행을
세우는 것은 spec 개정이므로 사람 몫이다.

★ 그래서 **`scripts/check_assumptions.py` 의 인쇄문 한 줄을 함께 고쳤다** —
「유예 중인 판정」 표가 `i["q_ref"]` 로 읽어 `KeyError` 로 죽었다. R31 이 스무
줄 위 「영향도」 표에서 같은 결함을 고쳤으나 이 표는 같이 고쳐지지 않았다.

"""
from __future__ import annotations

from pathlib import Path

import yaml

from core.assumption.item import AssumptionItem
from core.assumption.provider import AssumptionSet

#: 대장 정본.
_ASSUMPTIONS = Path(__file__).resolve().parents[2] / "docs" / "assumptions.yaml"

#: 47ⓐ 가 세우는 **자리 둘** — 값은 비어 있어야 한다.
_HOUSEHOLD_KEYS = ("load.household.count", "load.household.type_mix")


def _raw_items() -> list[dict]:
    """대장 파일이 든 항목 **전건** — `blocked` 를 포함한다."""
    data = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8")) or {}
    items = data.get("assumptions")
    assert isinstance(items, list) and items, f"{_ASSUMPTIONS} 에서 항목을 못 읽었다"
    return items


def _label_of(item: dict) -> str:
    return str(item.get("title") or "").strip()


def test_the_ledger_declares_a_label_for_every_item() -> None:
    """★★ **라벨이 없는 대장 항목이 0 건이다** — 「하나 이상 있다」로 두지 않는다.

    ⚠ **`blocked` 항목도 센다.** 화면이 그리지 않는다는 이유로 빼면, 그 항목이
    자료를 얻어 `assume` 으로 올라가는 날 **라벨 없이** 화면에 서고 그때는 아무
    검사도 빨간불을 내지 않는다. 라벨은 값과 달리 실측을 기다릴 필요가 없다.
    """
    missing = [str(item.get("key")) for item in _raw_items() if not _label_of(item)]

    assert not missing, (
        f"라벨(`title`)이 없는 대장 항목 {len(missing)}건: {missing} — "
        "docs/assumptions.yaml 의 해당 항목에 한국어 이름을 적으십시오"
    )


def test_the_dataclass_carries_the_label_to_the_boundary() -> None:
    """★★ **자료형이 라벨을 나른다** — 대장에만 있으면 화면이 못 읽는다.

    이것이 실제로 어긋나 있던 자리다: 대장은 41 항목 전건에 `title` 을 갖고
    있었는데 `AssumptionSet.load_from_yaml` 이 그것을 **읽지 않고 버렸다.**
    그래서 화면에 그릴 것이 키밖에 없었고, 「대장에 라벨이 없다」로 오독됐다.

    ⚠ **「하나가 실린다」로 두지 않는다** — 로더가 한 항목만 채우는 경로는
    없지만, 전건을 세면 다음에 로더가 갈릴 때도 이 검사가 그대로 선다.
    """
    # ★★ **자료형을 직접 세운다 — 로더를 지나지 않고 잰다.** 로더만 통해
    # 재면 「필드가 있다」와 「로더가 채운다」가 한 검사에 섞이고, 둘 중 어느
    # 쪽이 깨졌는지 실패 문면이 말해 주지 못한다.
    # ⚠ **기본값이 있어야 한다** — `title` 을 안 주는 기존 호출자가 저장소
    # 안에 있고(대장을 지나지 않고 항목을 세우는 자리), 필수로 만들면 그쪽이
    # 깨진다. 라벨 부재는 계산 오류가 아니라 표시 결함이다.
    #: 부기 7종은 이 검사의 관심이 아니므로 최소로 채운다 — 잰 것은 `title` 뿐이다.
    _BOOKKEEPING = {
        "value_unit": "원",
        "base_year": "2026",
        "applicable_scope": "라벨 검사용 표본",
        "derivation_method": "이 검사가 세우는 표본이며 계산에 쓰이지 않는다",
        "source": None,
        "verified_at": None,
        "confidence": "가정",
    }
    assert AssumptionItem(key="probe.label", value=1.0, **_BOOKKEEPING).title == "", (
        "`AssumptionItem.title` 의 기본값이 빈 문자열이 아니다 — 라벨을 안 주는 "
        "기존 호출자가 깨지거나 없는 이름이 지어진다"
    )
    assert (
        AssumptionItem(
            key="probe.label", value=1.0, title="시험용 이름", **_BOOKKEEPING
        ).title
        == "시험용 이름"
    ), "자료형이 준 라벨을 그대로 나르지 않는다"

    loaded = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS)).items()
    assert loaded, "대장에서 항목을 하나도 싣지 못했다"

    blank = sorted(key for key, item in loaded.items() if not item.title.strip())

    assert not blank, (
        f"자료형이 라벨을 못 실은 항목 {len(blank)}건: {blank} — "
        "core/assumption/provider.py 의 `load_from_yaml` 이 `title` 을 읽는지 보십시오"
    )


def test_the_label_is_not_the_key_or_the_unit_wearing_a_hat() -> None:
    """★ **라벨에 키도 단위도 새지 않는다.**

    두 가지를 함께 잰다. **키**가 새면 화면이 「라벨을 그린다」면서 결국 변수명을
    인쇄하고, **단위**가 새면 같은 사실이 `value_unit` 과 라벨 두 곳에 살아
    한쪽만 고쳐진다(단위를 「원/kW」에서 「천원/kW」로 옮기는 날 라벨이 따라오지
    않고, 그때 화면은 값의 100배·1000배를 태연히 인쇄한다 — R63 적대적 검수
    `D-8` 이 자원 파라미터에서 밟은 형태다).

    ⚠ 단위 문면 전체가 아니라 **단위 꼴 토큰**(`원/kW`·`%/년` 처럼 `/` 나 `%` 를
    든 첫 마디)까지 본다. 전체 문면만 보면 라벨 끝에 붙인 「(원/kW)」 가
    빠져나간다 — 단위 문면은 대개 뒤에 긴 단서가 붙어 있기 때문이다.
    """
    offenders: list[str] = []
    for item in _raw_items():
        key = str(item.get("key"))
        label = _label_of(item)
        unit = str(item.get("value_unit") or "").strip()

        if key and key in label:
            offenders.append(f"{key}: 라벨에 키가 들어 있다 — {label!r}")
        if "." in label:
            offenders.append(f"{key}: 라벨에 점이 있다(키 꼴이다) — {label!r}")
        if unit and unit in label:
            offenders.append(f"{key}: 라벨에 단위 문면이 들어 있다 — {label!r}")
        head = unit.split()[0] if unit else ""
        if head and ("/" in head or "%" in head) and head in label:
            offenders.append(f"{key}: 라벨에 단위 꼴 {head!r} 이 있다 — {label!r}")

    assert not offenders, "라벨이 키·단위를 새고 있다:\n" + "\n".join(
        f"  · {line}" for line in offenders
    )


def test_every_ledger_group_has_a_label_and_none_is_stale() -> None:
    """★ **묶음 머리의 한국어 이름도 대장이 갖는다** — 화면이 손으로 적지 않는다.

    설정 화면은 대장 키의 **첫 마디**로 항목을 묶는다(`capex`·`capacity_factor`
    …). 그 조각은 온전한 키가 아니라서 위 라벨 검사가 못 보는데, 사람이 읽는
    `<legend>` 에 서면 화면은 여전히 변수명을 인쇄한다.

    ⚠ **`core/` 나 템플릿에 사전을 만들지 않았다.** 대장이 항목 이름의 정본이면
    묶음 이름도 같은 자리여야 한다 — 두 곳에 두면 항목이 새 무리를 만드는 날
    한쪽만 고쳐지고, 그때 화면은 한 묶음만 조용히 영문 조각으로 돌아간다.

    ★ **양방향으로 잰다.** 빠진 것(새 무리가 이름 없이 생김)과 낡은 것(무리가
    사라졌는데 이름이 남음) 둘 다 빨간불이다 — 낡은 이름은 「고쳤다」와
    「검사가 못 본다」를 구별하지 못하게 만든다.
    """
    data = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8")) or {}
    declared = data.get("group_titles") or {}
    assert isinstance(declared, dict) and declared, (
        "대장 최상위에 `group_titles:` 가 없다 — 설정 화면의 묶음 머리가 "
        "키 조각을 그대로 인쇄하게 된다"
    )

    heads = {str(item.get("key")).split(".")[0] for item in _raw_items()}

    missing = sorted(heads - set(declared))
    assert not missing, (
        f"묶음 {missing} 의 한국어 이름이 대장에 없다 — "
        "docs/assumptions.yaml 의 `group_titles:` 에 적으십시오"
    )

    stale = sorted(set(declared) - heads)
    assert not stale, (
        f"`group_titles:` 의 {stale} 가 대장에 없는 묶음이다 — 낡은 줄을 "
        "지우십시오. 낡은 이름은 「고쳤다」와 「검사가 못 본다」를 구별하지 못하게 한다"
    )

    blank = sorted(head for head, title in declared.items() if not str(title).strip())
    assert not blank, f"묶음 {blank} 의 이름이 비어 있다"


def test_the_household_count_and_type_stand_in_the_ledger_without_a_made_up_value() -> None:
    """★ **47ⓐ — 가구 수·유형이 대장에 자리를 갖는다. 값은 비어 있다.**

    검증 모드 1단계가 *「가구 수와 가구 유형을 적는 자리가 이 저장소에 **자료형
    수준으로** 없다」* 로 칸을 비워 두었다(`app/services/verify_steps.py` 의
    갭 사유 · 브라우저 실측 `.orch/R63/result_V2.md` §3). 이 라운드가 하는 것은
    **자리를 세우는 것**이고, 값을 채우는 것이 아니다.

    ⚠⚠ **값을 지어내지 않는다.** 실증단지 가구 수를 우리가 정하면 그 수로 돌린
    계산을 우리가 검증하게 된다 — `track: blocked` 가 막는 그 형태다
    (`docs/assumptions.yaml` 머리말 · `scripts/check_assumptions.py` 검사 4).
    ⇒ `provider` 가 건너뛰고 화면은 「없다」를 그대로 유지한다.

    ★ **자리가 서면 다음 라운드가 그 칸을 채운다** — 그것이 이 항목의 값이다.
    """
    items = {str(item.get("key")): item for item in _raw_items()}

    absent = [key for key in _HOUSEHOLD_KEYS if key not in items]
    assert not absent, (
        f"가구 수·유형 자리가 대장에 없다: {absent} — 검증 모드 1단계가 "
        "「자료형 수준으로 없다」로 비워 둔 칸이다(착수 목록 47ⓐ)"
    )

    for key in _HOUSEHOLD_KEYS:
        item = items[key]
        assert item.get("track") == "blocked", (
            f"{key} 의 갈래가 `blocked` 가 아니다 — 실측이 없는데 값을 갖는다"
        )
        assert item.get("value") is None, (
            f"{key} 에 값이 채워져 있다 — 지어낸 가구 수로 우리 계산을 검증하게 된다"
        )
        assert _label_of(item), f"{key} 에 한국어 라벨이 없다"

    loaded = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS)).items()
    leaked = [key for key in _HOUSEHOLD_KEYS if key in loaded]
    assert not leaked, (
        f"{leaked} 가 provider 를 지나 실행 경로에 실렸다 — `blocked` 는 "
        "건너뛰어야 하고, 실리면 화면이 「없다」 대신 빈 값을 그린다"
    )
