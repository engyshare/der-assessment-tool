"""`salvage_row()` 단위 검사 — 잔존가치 행 빌더 (R43-B · `FR-104-AC5`).

## 왜 이 파일이 있는가

빌더를 세우는 것만으로는 **아무것도 붙들리지 않는다.** 종전에는 잔존가치 행만
빌더 없이 `core/casegrid/lifecycle.py` 가 `CashFlowRow(...)` 로 직접 지었고,
그래서 교체 행이 지는 두 규약(분석 종료 초과 · 수명 0 거부)을 **잔존가치만
지지 않았다.** 규약을 함수로 옮겨도 그 규약을 재는 검사가 없으면 다음 사람이
조용히 되돌릴 수 있다.

## 오라클을 검사가 계산하지 않는다

기대값은 **밖에서 고정한 수**다 — 이 파일은 `-salvage` 를 다시 계산해 견주지
않는다. 자원 제원도 대장에서 오지 않는다(오면 대장이 바뀔 때마다 이 파일이
낡는다); 관계를 드러내려고 고른 탐침값이다.

## 이 파일이 붙들지 못하는 것

`lifecycle_rows()` 가 이 빌더를 **부르는가**는 재지 않는다 — 그것은
`tests/casegrid/test_lifecycle_wiring.py` 의 ⓑ·ⓔ 몫이고, 그쪽은 표시층
(`OneOffLine`)과 프로포마층의 금액이 같은지를 두 산출물로 견준다.
"""
from __future__ import annotations

import pytest

from core.cba.proforma import salvage_row
from core.contracts.validation import ValidationError

#: 탐침값 — 대장에서 오지 않는다. 아래 기대값은 이 셋에서 **손으로** 고정했다.
_TAG = "PVSalvage"
_LABEL = "PV 잔존가치 (20년차)"
_HORIZON = 20


@pytest.mark.req("FR-104-AC5")
def test_salvage_enters_the_cost_row_as_a_negative_amount() -> None:
    """정상 한 건 — 명목 1,200,000원을 넘기면 20년차에 **−1,200,000원**이 실린다.

    오라클: 순위 4 (정의 항등식). 호출자는 **양수 명목액**을 넘기고 부호를
    뒤집는 것은 빌더가 한다 — 이 검사는 그 뒤집기가 **한 번만** 일어난다는
    것을 고정한다. 두 번 뒤집히면 여기서 `+1,200,000` 이 되고, 그때 잔존가치는
    비용이 되어 결론을 잔존가치의 두 배만큼 나쁘게 만든다(예외는 나지 않는다).
    """
    rows = salvage_row(
        _TAG,
        label=_LABEL,
        salvage_year=_HORIZON,
        salvage_won=1_200_000,
        asset_lifetime_years=25,
        analysis_end_year=_HORIZON,
    )

    assert len(rows) == 1
    assert rows[0].tag == _TAG
    assert rows[0].label == _LABEL
    assert list(rows[0].amounts) == [_HORIZON]
    assert int(rows[0].amounts[_HORIZON]) == -1_200_000


@pytest.mark.req("FR-104-AC5")
def test_a_zero_salvage_still_gets_a_row() -> None:
    """0원이어도 행을 싣는다 — 교체 행과 **갈리는** 자리다.

    오라클: 순위 4. 잔존가치의 연차는 언제나 분석 종료연도이므로 「0원을 몇
    년차에 적을 것인가」가 열리지 않는다. 행을 빼면 「남은 게 없어서 0」과
    「행이 없어서 0」이 프로포마에서 똑같이 보인다.
    """
    rows = salvage_row(
        _TAG,
        label=_LABEL,
        salvage_year=_HORIZON,
        salvage_won=0,
        asset_lifetime_years=_HORIZON,
        analysis_end_year=_HORIZON,
    )

    assert len(rows) == 1
    assert int(rows[0].amounts[_HORIZON]) == 0


@pytest.mark.req("FR-701-AC4")
def test_salvage_after_analysis_end_is_not_accounted() -> None:
    """분석 종료 이후의 잔존가치는 행을 만들지 않는다 — `replacement_row` 와 같은 규약.

    오라클: 순위 4 (정의 항등식). analysis_end_year=20 인데 계상 연차가 25 면
    행 자체가 없다. 만들면 **분석기간을 늘리지 않고 늘린 효과**가 생기고,
    그 효과는 결론을 한 방향으로만 좋게 만든다.
    """
    rows = salvage_row(
        _TAG,
        label=_LABEL,
        salvage_year=25,
        salvage_won=1_200_000,
        asset_lifetime_years=30,
        analysis_end_year=_HORIZON,
    )

    assert rows == []


def test_salvage_row_rejects_non_positive_asset_lifetime() -> None:
    """자산 수명이 0 이하면 거부 — 잔존 수명 비례가 정의되지 않는다.

    §7.3 대장에 이 값의 양수 여부를 다루는 전용 규칙이 없어 ``rule`` 은 비운다
    (`replacement_row`·`salvage_value` 와 같은 판단).
    """
    with pytest.raises(ValidationError) as caught:
        salvage_row(
            _TAG,
            label=_LABEL,
            salvage_year=_HORIZON,
            salvage_won=1_200_000,
            asset_lifetime_years=0,
            analysis_end_year=_HORIZON,
        )

    parts = caught.value.as_dict()
    assert parts["field"] == "proforma.asset_lifetime_years"
    assert "0" in (parts["reason"] or "")
    assert (parts["action"] or "").strip()
    assert parts["rule"] is None


def test_a_pre_negated_salvage_is_refused() -> None:
    """★ 이미 뒤집힌 값을 넘기면 거부한다 — **두 번 뒤집으면 다시 양수**다.

    통과시키면 잔존가치가 **비용**으로 실린다. `net_operating_flows()` 가
    *「부호를 뒤집을 자리는 경계 하나여야 한다」* 로 만난 것과 같은 형태이고,
    값이 아니라 **방향**이 틀리므로 검토자 눈에 띄지 않는다.
    """
    with pytest.raises(ValidationError) as caught:
        salvage_row(
            _TAG,
            label=_LABEL,
            salvage_year=_HORIZON,
            salvage_won=-1_200_000,
            asset_lifetime_years=25,
            analysis_end_year=_HORIZON,
        )

    assert caught.value.field == "proforma.salvage_won"
