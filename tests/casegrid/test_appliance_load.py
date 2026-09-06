"""**가구의 추가 전력사용기기 부하가 총량에 더해진다** — 사용자 요구 2 (R64/WP-2).

사용자 문면: *「가구의 전기 부하 설정을 변경할 수 있어야 함 (EV, heatpump,
AI 가전)」*. 종전에는 바꿀 방법이 없었다 — 러너
(`core/casegrid/e2e_runner.py::run_single_case_e2e`)가
`extra_appliance_load_kwh` 인자를 **갖고만 있었고 배포 경로에서 아무도 넘기지
않았다**(착수 실측: `grep -rn "extra_appliance_load_kwh="` 가 시험 밖에서 0건).

## ★★★ 이 파일이 실제로 붙드는 것 — **안 준 실행이 종전과 같은가**

이 축에서 가장 위험한 것은 「부하를 얹는 것」이 아니라 **기기를 적지 않은
실행이 조용히 달라지는 것**이다. 배포 경로(골든 시나리오 셋)는 두 필드를
갖지 않으므로, 기본 갈래가 한 원이라도 움직이면 그것은 이 라운드가 결론축을
흔든 것이고 회귀 기준값 여섯이 전부 거짓이 된다.

⇒ 그래서 첫 검사가 **인자를 안 준 실행과 미지정으로 준 실행이 같은 수를
낸다**이고, 그 위에서만 증분을 잰다. 파이프라인 전체의 동일성은
`tests/golden/test_regression_scenarios.py::
test_golden_scenarios_match_current_regression_snapshot` 이 `npv_won` 으로
잰다.

## ★★★ 둘째로 붙드는 것 — **합성 순서**

    단지 총부하 = ( 가구 한 호의 연간 사용량 + 히트펌프 + 전기차 ) × 가구 수

**곱한 뒤에 더하면** 추가 기기가 단지에 딱 한 대 있는 사업이 되고, 그 실행은
「모든 가구에 히트펌프를 놓았다」와 산출물에서 구별되지 않는다. 근거는 대장의
`load.household.annual` 이 **kWh/호·년**(한 호당)이라는 사실이다.

## ⚠ 값을 리터럴로 박지 않는다

기대 총부하는 대장 수준표(`build_level_map`)에서 읽어 만든다. 박으면 대장
판이 오르는 날 이 검사가 조용히 낡는다.

## ⚠ `req()` 마커를 달지 않았다 — **조항을 대조하고 내린 판정이다**

spec(`rslt/spec-분산특구-경제성평가.md`)에 「히트펌프 부하」·「전기차 충전
부하」를 요구하는 수용기준이 없다. 가까워 보이는 ID 를 짐작해 붙이면
`docs/traceability.md` 에 *「이 조항이 검증됐다」* 는 거짓 인용이 실린다 —
`tests/casegrid/test_household_count.py` 머리말이 같은 자리에서 같은 판정을
적었다. 조항 신설은 spec 개정이므로 사람 몫이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.casegrid.appliance_load import (
    APPLIANCE_LOAD_UNSPECIFIED,
    EV_LOAD_FIELD,
    EV_LOAD_LEDGER_KEY,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_FIELD,
    HEATPUMP_LOAD_LEDGER_KEY,
    HEATPUMP_LOAD_TITLE,
    NO_APPLIANCE_LOADS,
    ApplianceLoads,
    resolve_appliance_load,
    resolve_appliance_loads,
)
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import load_daily_shapes
from core.contracts.validation import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_LOAD = "e2e-load"

#: 단지 총부하가 커져도 **태양광 잉여가 남는** 규모. 사유는
#: `tests/casegrid/test_household_count.py::_COUNT` 가 갖는다.
_COUNT = 2

#: 시험용 기기 부하. **참고자료의 값(2,675·2,412)을 쓰지 않는다** — 그 수를
#: 검사에 박으면 「이 저장소가 그 값으로 돈다」로 읽히고, 대장은 그 값을 갖지
#: 않는다(`track: blocked`). 검사가 재는 것은 **크기가 아니라 합성 순서**다.
_HEATPUMP = 900.0
_EV = 600.0


def _levels() -> dict[str, dict[str, float]]:
    return build_level_map(_ASSUMPTIONS)


def _daily_load_kwh(outcome: object) -> float:
    """대표일 하루의 가구 소비(kWh) — **부호를 뒤집어** 양수로 낸다."""
    return -sum(outcome.dispatch.per_resource[_LOAD].electric)  # type: ignore[attr-defined]


def _run(levels: dict[str, dict[str, float]], **extra: object):
    return run_single_case_e2e(
        {},
        level_map=levels,
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=levels["household_load_annual_kwh"]["base"],
        **extra,  # type: ignore[arg-type]
    )


def test_not_giving_an_appliance_is_the_same_run_as_giving_zero_total() -> None:
    """★★★ **미지정이 기본이고, 그때 수가 한 원도 움직이지 않는다.**

    인자를 아예 넘기지 않은 실행과 미지정 `ApplianceLoads` 의 합계(0.0)를
    넘긴 실행이 **원소 하나까지** 같아야 한다. 여기가 어긋나면 골든 회귀
    여섯이 전부 거짓이 되고, 그 어긋남은 「기기 부하 축을 열었다」가 아니라
    **결론축을 말없이 옮겼다**는 뜻이다.
    """
    levels = _levels()
    without = _run(levels)
    explicit_zero = _run(
        levels, extra_appliance_load_kwh=NO_APPLIANCE_LOADS.total_kwh
    )
    assert without.variants == explicit_zero.variants, (
        "기기를 안 준 실행과 미지정 합계를 준 실행의 지표가 다르다 — "
        "기본 갈래가 움직였다"
    )
    assert _daily_load_kwh(without) == _daily_load_kwh(explicit_zero)


def test_an_appliance_adds_exactly_its_annual_consumption_to_one_household() -> None:
    """★★★ 한 호의 연간 소비가 **정확히 그 기기의 소비량만큼** 는다.

    이 단언이 없으면 아래 순서 검사는 *「인자를 나르기만 하고 계산에 안 쓴다」*
    로도 통과한다 — 이 저장소가 반복해 만난 「표시만 하는 구현」이다.

    ⚠ 대표일 하루로 재고 365배 한 것이 연간이므로, 기댓값도 365로 나눈다.
    리터럴을 박지 않고 **미지정 실행의 값 + 증분**으로 짓는다.
    """
    levels = _levels()
    days = 365
    plain = _daily_load_kwh(_run(levels))
    loaded = _daily_load_kwh(
        _run(levels, extra_appliance_load_kwh=_HEATPUMP + _EV)
    )
    assert loaded == pytest.approx(plain + (_HEATPUMP + _EV) / days, rel=1e-9), (
        f"기기 부하 {_HEATPUMP + _EV}kWh/년을 얹었는데 대표일 소비가 "
        f"{plain}kWh → {loaded}kWh 로만 늘었다"
    )


def test_the_appliance_is_per_household_so_it_is_added_before_scaling() -> None:
    """★★★ **합성 순서** — `(연간 + 히트펌프 + 전기차) × 가구 수` 다 (판정 ④).

    ⚠⚠ 곱한 뒤에 더하면 **추가 기기가 단지에 딱 한 대 있는 사업**이 되고, 그
    실행은 「모든 가구에 히트펌프를 놓았다」와 산출물에서 구별되지 않는다.

    ⚠ 기대값을 리터럴로 적지 않는다 — **한 호에 얹은 실행**의 대표일 소비를
    재고 거기에 `_COUNT` 를 곱한 것이 기대값이다. 대장 판이 올라도 산다.

    ## 이 시험이 `tests/casegrid/test_household_count.py` 의 것과 다른 점

    그 파일의 `test_the_extra_appliance_is_per_household_so_it_is_added_
    before_scaling` 은 **러너 인자**로 순서를 잰다. 여기서는 그 인자에 실제로
    **두 기기의 합계**가 오는 지금 배선에서 같은 순서가 서는지를 재고, 아래
    `test_the_two_appliances_add_up_before_they_reach_the_runner` 가 그 합계가
    합쳐지는 자리를 잰다.
    """
    levels = _levels()
    extra = _HEATPUMP + _EV
    per_household = _daily_load_kwh(_run(levels, extra_appliance_load_kwh=extra))
    site = _daily_load_kwh(
        _run(levels, extra_appliance_load_kwh=extra, household_count=_COUNT)
    )
    assert site == pytest.approx(per_household * _COUNT, rel=1e-12), (
        f"{_COUNT}호 단지의 대표일 소비가 {site}kWh 다 — 기기를 얹은 한 호의 "
        f"{per_household}kWh 의 {_COUNT}배가 아니다. 곱한 뒤에 더했다면 "
        "추가 기기가 단지에 딱 한 대 있는 사업이다"
    )


def test_the_two_appliances_add_up_before_they_reach_the_runner() -> None:
    """★★ 러너가 받는 것은 **합계 하나**다 — 갈래는 산출물에서만 갈린다.

    인자를 기기별로 쪼개면 러너가 기기 목록을 알게 되고, 셋째 기기가 오는 날
    러너 시그니처가 늘어난다.
    """
    loads = ApplianceLoads(heatpump_kwh=_HEATPUMP, ev_kwh=_EV)
    assert loads.total_kwh == pytest.approx(_HEATPUMP + _EV)
    assert loads.any_specified is True


def test_unspecified_and_zero_are_the_same_number_but_different_statements() -> None:
    """★★★ **「0이라고 적었다」와 「적지 않았다」를 가른다** (판정 ⑦).

    더해지는 값은 둘 다 0 이지만 앞의 것은 *「이 단지의 가구에는 히트펌프가
    없다」*이고 뒤의 것은 *「있는지 아직 모른다」*다. 산출물이 그 둘을 다르게
    인쇄해야 검토자가 「반영했다」와 「반영하지 않았다」를 가릴 수 있다.
    """
    said_none = resolve_appliance_loads({HEATPUMP_LOAD_FIELD: 0})
    said_nothing = resolve_appliance_loads({})
    assert said_none.heatpump_kwh == 0.0
    assert said_nothing.heatpump_kwh is None
    assert said_none.total_kwh == said_nothing.total_kwh == 0.0
    assert said_none.any_specified is True
    assert said_nothing.any_specified is False


def test_the_scenario_fields_are_the_only_channel() -> None:
    """★★ 통로는 **두 필드 하나씩**이다 — 다른 이름은 읽히지 않는다.

    통로가 둘이면 어느 것이 이겼는지 산출물에서 알 수 없다
    (`core/casegrid/household_scale.py::HOUSEHOLD_COUNT_FIELD` 와 같은 규약).
    """
    loads = resolve_appliance_loads(
        {HEATPUMP_LOAD_FIELD: 1_000, EV_LOAD_FIELD: "2000", "heatpump_kwh": 9_999}
    )
    assert loads.heatpump_kwh == 1_000.0
    assert loads.ev_kwh == 2_000.0
    assert loads.total_kwh == 3_000.0


@pytest.mark.parametrize(
    "bad", [-1, -0.5, True, "abc", "-3", float("nan"), float("inf"), [], {}]
)
def test_a_load_that_is_not_a_non_negative_number_is_refused(bad: object) -> None:
    """★★ **0 이상의 수만 기기 부하다** — 그 밖은 3요소로 거부한다 (`NFR-303`).

    ⚠ `True` 가 목록에 있는 이유: 파이썬에서 `bool` 은 `int` 의 하위형이라
    막지 않으면 *「히트펌프 = 참」* 이 **1kWh** 로 조용히 통과한다.

    ⚠ `nan`·`inf` 가 목록에 있는 이유: 총량에 더해지면 리포트의 **모든 수가
    조용히 `nan`** 이 되고, 그 산출물은 빈칸이 아니라 「계산된 것처럼 보이는
    글자」로 나온다.

    ⚠ 음수가 거부인 이유: 「부하가 마이너스」는 발전이며, 그것을 부하 칸으로
    적으면 아무 설비도 편익도 없는 발전이 선다.
    """
    with pytest.raises(ValidationError, match=HEATPUMP_LOAD_TITLE):
        resolve_appliance_load(
            bad, ledger_key=HEATPUMP_LOAD_LEDGER_KEY, title=HEATPUMP_LOAD_TITLE
        )


@pytest.mark.parametrize("blank", ["", " ", None])
def test_a_blank_is_not_a_refusal_but_a_statement_that_nothing_was_written(
    blank: object,
) -> None:
    """★ 화면의 **빈 칸**은 거부가 아니라 「적지 않았다」다.

    폼이 GET 질의로 보낼 수 있는 모양은 빈 칸과 수 문면 둘뿐이며, 그 변환을
    라우터가 아니라 **판정하는 자리 하나**가 한다.
    """
    assert (
        resolve_appliance_load(
            blank, ledger_key=EV_LOAD_LEDGER_KEY, title=EV_LOAD_TITLE
        )
        is None
    )


def test_a_number_string_is_read_as_a_load() -> None:
    """★ 화면이 GET 질의로 보내는 것은 **문면**이다 — `"2412"` 가 2,412kWh 다."""
    assert (
        resolve_appliance_load(
            "2412", ledger_key=EV_LOAD_LEDGER_KEY, title=EV_LOAD_TITLE
        )
        == 2_412.0
    )
    assert (
        resolve_appliance_load(
            "2412.5", ledger_key=EV_LOAD_LEDGER_KEY, title=EV_LOAD_TITLE
        )
        == 2_412.5
    )


def test_the_refusal_names_the_ledger_slot_and_says_it_is_not_ours_to_fill() -> None:
    """★ 거부 3요소가 **어느 대장 자리**인지와 **왜 기본값이 없는지**를 적는다."""
    with pytest.raises(ValidationError) as caught:
        resolve_appliance_load(
            -1, ledger_key=EV_LOAD_LEDGER_KEY, title=EV_LOAD_TITLE
        )
    error = caught.value
    assert error.field == EV_LOAD_LEDGER_KEY
    assert "사업 계획이 정하는 사실" in error.reason
    assert error.action


def test_the_unspecified_wording_is_not_a_blank() -> None:
    """★★ 「미지정」은 **글자**다 — 빈 문자열이면 산출물이 빈칸을 인쇄한다."""
    assert APPLIANCE_LOAD_UNSPECIFIED.strip()
    assert "미지정" in APPLIANCE_LOAD_UNSPECIFIED


def test_the_ledger_has_no_ai_appliance_row() -> None:
    """★★★ **「AI 가전」을 부하 항목으로 세우지 않았다** (사용자 판정 2026-09-06).

    사용자 문면: *「기존 가전에 AI 기능이 포함된다고 보면 어떠한가? 냉장고,
    세탁기 등 DR 자원으로 활용 가능한 전자기기에 대해서 **기능이 추가되는
    것**임」*.

    ⇒ AI 가전은 전기를 더 쓰는 새 기기가 아니라 이미 있는 가전에 붙는
    기능이다. `load.ai_appliance.*` 를 세워 총량에 더하면 냉장고·세탁기의
    소비가 `load.household.annual`(일반가전 포함)과 **두 번 세어진다.**

    ⚠ 이 검사는 「지금 없다」가 아니라 **「세우면 안 된다」**를 재는 래칫이다 —
    다음 사람이 요구 문면(「EV, heatpump, AI 가전」)만 읽고 항목을 세우면
    여기서 걸리고, 그때 이 독스트링이 사유를 준다. 값어치가 kWh 가 아니라
    **그 kWh 를 언제 쓸지 옮기는 데** 있으므로 자리는 부하 형상 축이다.
    """
    ledger = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    keys = [str(item.get("key", "")) for item in ledger["assumptions"]]
    offenders = [key for key in keys if "ai_appliance" in key or "ai.appliance" in key]
    assert offenders == [], (
        f"대장에 AI 가전 부하 항목이 섰다: {offenders} — 그것을 총량에 더하면 "
        "그 가전의 소비가 `load.household.annual` 과 두 번 세어진다"
    )
    assert HEATPUMP_LOAD_LEDGER_KEY in keys
    assert EV_LOAD_LEDGER_KEY in keys


def test_the_two_ledger_rows_hold_a_value_with_its_notes_and_source() -> None:
    """★★★ **두 항목은 이제 값을 갖는다 — 그리고 그 값이 «어디서 왔는지»도 갖는다.**

    ## ⚠⚠ 이 검사는 R65 에 **재는 대상이 뒤집혔다.** 옛 사실을 지우지 않는다

    R64/WP-2 에 이 자리는 `test_the_two_ledger_rows_hold_no_value` 였고
    *「두 항목은 `blocked` · `value: null` 이다」* 를 쟀다. 그 판단은 **틀리지
    않았다** — 근거는 사용자 문면 *「해당 자료도 참값은 아님. 가정한 값임을
    유의해줘」* 였고, 참고 엑셀의 수를 그냥 올리면 **우리가 고른 구성으로 우리가
    돌린 계산**이 되기 때문이었다(§13.0.2 자기충족).

    **R65 요구가 그 전제를 바꿨다** — *「히트펌프, 전기차 충전 연간 소비전력량 …
    조사하거나, 앞서 예시로 제시한 엑셀 파일 상의 수치를 사용(**조사 권장**)」*
    (2026-09-07). 값을 세우라고 **사실을 정하는 쪽이 지시했다.** 그래서 두 항목이
    `track: assume` · `value` 있음으로 섰다(R65/WP-2).

    ## 그러면 자기충족은 무엇이 막는가 — **부기다. 그것을 이 검사가 잰다**

    값이 선 뒤의 방어선은 *「값이 없다」*가 아니라 *「이 값이 무엇이고 어디서
    왔는지가 함께 실린다」*이다. 그래서 이 검사는 **값 · 민감도 · 단위 ·
    유도 · 출처 · 이용조건 · 신뢰도 · 공개등급**을 함께 요구한다 — 하나라도
    비면 산출물이 그 수를 **근거 없이** 인쇄하게 된다.

    ⚠ **수를 여기 리터럴로 적지 않는다.** 2,675·2,784 를 박으면 대장이 갱신되는
    날 이 검사가 조용히 낡는다(모듈 머리말 ⚠ 절과 같은 판단). 재는 것은
    *「값이 있는가 · 부기가 붙었는가 · 민감도의 `base` 가 그 값인가」*다.

    ⚠ `value_unit` 만은 옛 검사에서 **그대로 가져왔다** — 「호당」이 아니면
    곱셈 순서가 뜻을 잃는다는 사실은 값이 서도 바뀌지 않는다.
    """
    ledger = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    rows = {
        str(item.get("key", "")): item
        for item in ledger["assumptions"]
        if str(item.get("key", "")) in (HEATPUMP_LOAD_LEDGER_KEY, EV_LOAD_LEDGER_KEY)
    }
    assert set(rows) == {HEATPUMP_LOAD_LEDGER_KEY, EV_LOAD_LEDGER_KEY}
    for key, row in rows.items():
        assert row["track"] != "blocked", (
            f"{key} 가 다시 blocked 로 돌아갔다 — R65 요구가 값을 세우라고 했다"
        )
        assert isinstance(row["value"], (int, float)), (
            f"{key} 에 값이 없다 — R65 요구 *「엑셀 파일 상의 수치를 사용」* 이 "
            "이 칸을 채우라고 했다"
        )
        sensitivity = row["sensitivity"]
        assert isinstance(sensitivity, dict), (
            f"{key} 에 민감도 3수준이 없다 — 값이 가정·추정이므로 "
            "「얼마나 틀릴 수 있는가」가 함께 실려야 한다"
        )
        assert sensitivity["base"] == row["value"], (
            f"{key} 의 민감도 base 가 값과 다르다 — 두 수가 갈리면 "
            "스윕이 본문과 다른 기준점을 잰다"
        )
        assert sensitivity["low"] <= row["value"] <= sensitivity["high"], (
            f"{key} 의 값이 민감도 띠 밖에 있다"
        )
        assert row["value_unit"] == "kWh/호·년", (
            f"{key} 의 단위가 「호당」이 아니다 — 곱셈 순서가 뜻을 잃는다"
        )
        # ★ 값이 선 뒤의 방어선은 **부기**다 (독스트링 둘째 절).
        for field in (
            "derivation_method", "source", "usage_terms", "confidence", "disclosure"
        ):
            assert str(row.get(field) or "").strip(), (
                f"{key} 에 `{field}` 가 비어 있다 — 값만 있고 근거가 없으면 "
                "산출물이 그 수를 근거 없이 인쇄한다"
            )
