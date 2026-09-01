"""정책 가정 경고가 **자원에서 리포트 재료로 실려 오는가** — `FR-404-AC1` · R48 §7.

## 무엇을 붙드는가

`DER.policy_warnings()` 는 R48 에 계약으로 올라갔지만, 러너가 그 훅을 부르지
않으면 **경고는 자원 안에 갇힌 채 리포트에 한 글자도 나가지 않는다.** 그리고 그
상태는 아무 예외도 내지 않는다 — 리포트는 그냥 조용해진다. 여기가 그 통로다.

## ★ 왜 **가짜 자원**으로 재는가

기준 실행(PV+ESS)에는 경고가 없다. 그러므로 실행을 그냥 돌려 놓고
`policy_warnings == ()` 를 재면 **배선을 지워도 초록불**이다(둘 다 빈 값이므로).
그래서 경고를 내는 자원을 만들어 넣는다.

⚠ **두 자원에 서로 다른 문면을 준다.** 한쪽만 주면 러너가 두 행에 같은 값을
실어도(혹은 첫 자원의 것을 두 번 실어도) 통과한다.

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 문면은 이 파일이 **밖에서** 지어 넣는다. 실행에서
   뽑아 오면 검사가 자기 오라클을 만든다.
② **이 설명이 이 검사에 걸리는가** — 아니다. 소스 문면을 보지 않는다.
③ **이름보다 넓게 주장하는가** — 아니다. *실려 오는가*만 잰다. 인쇄된 모양은
   `tests/report/test_policy_warning_section.py` 가 본다.
④ **수와 그 조건의 짝** — 이 파일은 어느 수치도 보지 않는다. 경고는 문면이므로
   금액을 움직이지 않는다(`DER.policy_warnings()` 독스트링).
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.der.ess import ESS
from core.der.pv import PV

#: 대장을 읽지 않는다 — 이 검사가 보는 것은 금액이 아니라 배선이다.
_LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    "grid_purchase_price": MappingProxyType({"base": 100.0}),
    "surplus_sale_price": MappingProxyType({"base": 90.0}),
    "replacement_real_trend": MappingProxyType({"base": 0.0}),
    # 아래 둘은 러너가 요구하는 축이다. **대장과 다른 수를 일부러 쓴다** —
    # 같은 수를 쓰면 이 파일이 대장의 사본을 하나 갖게 되고, 대장이 바뀔 때
    # 여기가 따라오지 않아도 아무 일이 없다. 이 파일은 두 축을 재지 않는다.
    "pv_inverter_share": MappingProxyType({"base": 0.11}),
    "demand_charge": MappingProxyType({"base": 7_700.0}),
    # 고정 O&M 둘 — 러너가 요구한다(R51/WP-2 에 스윕 축으로 올렸다). **대장의
    # 100,000 과 다른 수를 일부러 쓴다** — 위 단가들과 같은 규약이다.
    "pv_fixed_om": MappingProxyType({"base": 70_000.0}),
    "ess_fixed_om": MappingProxyType({"base": 65_000.0}),
    **design_levels(),
}

#: 가짜 자원이 낼 문면 둘. **서로 다르다**(위 머리말). 실물 문면을 베끼지
#: 않는다 — 베끼면 자원이 문구를 다듬을 때 이 검사가 함께 빨간불이 되고,
#: 이 검사가 재는 것은 문구가 아니라 통로다.
_PV_WARNING = "탐침 — 태양광 쪽 정책 가정 경고 (제도 필요)"
_ESS_WARNING = "탐침 — 저장장치 쪽 정책 가정 경고 (제도 보완 필요)"


def _basis(monkeypatch: pytest.MonkeyPatch, *, warn: bool):
    """실행 한 번. *warn* 이면 두 자원이 서로 다른 경고를 내는 **가짜 자원**이다."""
    if warn:
        monkeypatch.setattr(PV, "policy_warnings", lambda self: [_PV_WARNING])
        monkeypatch.setattr(ESS, "policy_warnings", lambda self: [_ESS_WARNING])
    return run_single_case_e2e({}, level_map=_LEVEL_MAP, horizon_years=20).basis


@pytest.mark.req("FR-404-AC1")
def test_the_runner_carries_each_resources_policy_warnings_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★ 러너가 훅을 불러 **그 자원의 행에** 그대로 싣는다.

    ⚠ **자원별로 따로 잰다.** 「어딘가에 실렸다」로 재면 러너가 모든 행에 같은
    목록을 실어도 통과하고, 그러면 리포트의 *「어느 자원의 경고인가」*(R48 판정
    D2-2)가 거짓이 된다.
    """
    basis = _basis(monkeypatch, warn=True)
    carried = {line.name: line.policy_warnings for line in basis.resources}

    assert carried, "실행이 자원 행을 하나도 세우지 않았다"
    pv_lines = [w for name, w in carried.items() if "pv" in name]
    ess_lines = [w for name, w in carried.items() if "ess" in name]
    assert pv_lines == [(_PV_WARNING,)], (
        f"태양광 행이 자기 경고를 그대로 싣지 않았다 — {pv_lines}"
    )
    assert ess_lines == [(_ESS_WARNING,)], (
        f"저장장치 행이 자기 경고를 그대로 싣지 않았다 — {ess_lines}"
    )


@pytest.mark.req("FR-404-AC1")
def test_the_base_configuration_carries_no_policy_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """기준 구성(PV+ESS)은 **아무 경고도 내지 않는다.**

    이것이 위 검사의 대조군이다 — 러너가 경고를 지어내고 있지 않다는 것을
    함께 재야 위가 *「훅에서 왔다」* 를 말할 수 있다.
    """
    basis = _basis(monkeypatch, warn=False)

    assert basis.resources, "실행이 자원 행을 하나도 세우지 않았다"
    assert all(line.policy_warnings == () for line in basis.resources), (
        "기준 구성에 경고가 실렸다 — 러너가 훅이 아닌 곳에서 문면을 만들고 있다"
    )
