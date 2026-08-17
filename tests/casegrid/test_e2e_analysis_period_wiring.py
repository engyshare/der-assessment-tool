"""실행 경로가 **분석기간 상한을 지나는가** — DV-5 · NFR-303.

거부 기계(`core/cba/proforma.py::check_analysis_period`)는 R24 가 만들었고
그것을 붙드는 테스트도 촘촘하다. **그런데 그 테스트가 전부 그 함수를 직접
부른다.** R24 인수가 스스로 적어 두었듯 `check_analysis_period` 를 부르는
**배포 코드가 0곳**이었다 — 사용자가 200년을 넣어도 그 함수를 지나지 않으면
아무도 막지 않는다.

`tests/casegrid/test_e2e_exclusion_wiring.py` 가 `DV-12` 에서 고친 것과 **같은
자리·같은 형태**다. 이 파일이 붙드는 것도 함수가 아니라 **배선**이다.

    기본 호출은 그대로 돈다                     ← 거부가 정당한 실행을 막지 않는다
    경계(정확히 2배)는 통과한다                 ← `≤` 이지 `<` 가 아니다
    상한을 넘기면 진입점이 거부한다             ← DV-5 가 실행 경로에 있다
    ★ 거부는 **CBA 에 닿기 전에** 일어난다      ← 위반 케이스의 NPV 가 없다
    ★ `horizon_years` 는 **계산에도 쓰인다**    ← 재는 것과 쓰는 것이 갈리지 않는다

뒤 둘이 요점이다.

셋째만 두면 **다 계산한 뒤에 던지는 구현**도 통과하고, 그러면 위반 케이스의
수치가 한 번은 존재하게 된다(`DV-10` 이 러너 호출 0회를 단언한 것과 같은 이유).

넷째가 없으면 **검사가 아무도 쓰지 않는 수를 지키게 된다.** `horizon_years` 를
받아서 검사에만 넘기고 프로포마는 상수를 계속 쓰면, 이 파일의 나머지 셋은
전부 초록불인 채 **분석기간을 재는 것과 분석기간으로 계산하는 것이 갈린다.**
값은 맞고 뜻이 틀린 상태이며 아무 예외도 나지 않는다.
"""

from __future__ import annotations

import inspect
from types import MappingProxyType

import pytest

from core.casegrid import e2e_runner
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.casegrid.variants import run_order
from core.contracts.validation import ValidationError

#: 배선을 보는 데 쓰는 **탐침값**이다 — 기본값도 대장값도 아니다.
#: 일부러 대장의 20 과 다른 수를 쓴다: 같은 수를 쓰면 이 파일이 대장의 사본을
#: 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도 아무 일이 없다.
#: **분석기간을 누가 갖는가**는 `tests/assumption/test_analysis_period.py` 가 본다.
_PROBE_HORIZON = 18

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **배선**이다.
#: 실물 대장으로 도는 것은 `tests/acceptance2/test_17_2_dod2.py` 가 이미 한다.
LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    # 계통 전력 구매 한계단가 — 러너가 요구한다(기본값을 두지 않는 것이 규칙).
    # **대장의 120 과 다른 수를 일부러 쓴다** — 같은 수를 쓰면 이 파일이 대장의
    # 사본을 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도 아무 일이
    # 없다 — 이 파일 머리의 「탐침값」 규약 그대로다.
    "grid_purchase_price": MappingProxyType({"base": 100.0}),
    # 설계 변수(용량)는 이 파일의 관심이 아니지만 **러너가 요구한다** —
    # 기본값을 두지 않는 것이 규칙이라 기본 탐색점을 그대로 받아 온다.
    **design_levels(),
}

#: 러너가 세우는 자원의 수명(년) — `PV.lifetime` 25 · `ESS.lifetime` 17.
#: **여기에 손으로 적지 않고 실물에서 읽는다** — 자원 기본 수명이 바뀌면 이
#: 파일의 경계값이 조용히 틀려지고, 그때 거부 케이스가 통과 케이스가 된다.
def _ceiling_years() -> int:
    """이 케이스의 분석기간 상한 = 최장 자원 수명 × 2 (DV-5)."""
    from core.der.ess import ESS
    from core.der.pv import PV

    lifetimes = [
        PV(
            name="probe",
            capacity_kw=3.0,
            capacity_factor=0.15,
            unit_capex_won_per_kw=1,
            fixed_om_won_per_year=0,
            escalation_rate=0.02,
            self_consumption_ratio=0.0,
        ).lifetime,
        ESS(
            name="probe",
            capacity_kwh=10.0,
            power_kw=5.0,
            rte_pct=90.0,
            soc_min_pct=10.0,
            soc_max_pct=90.0,
            cycle_life=6_000,
            calendar_life=20,
            eol_soh_pct=80.0,
            cycles_per_year=365.0,
            capex_unit_won_per_kwh=1,
            fixed_om_won_per_year=0,
        ).lifetime,
    ]
    return max(lifetimes) * 2


@pytest.mark.req("NFR-303-M1")
def test_a_plain_horizon_still_runs_end_to_end() -> None:
    """양성 — 평범한 분석기간은 그대로 NPV 를 낸다.

    거부만 검사하면 **무엇이든 거부하는** 구현도 통과한다. 그리고 이 배선이
    기존 케이스그리드 실행을 막지 않는다는 것 자체가 확인 대상이다.
    """
    outcome = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON
    )

    assert "npv" in outcome.metrics
    assert "payback_years" in outcome.metrics


@pytest.mark.req("NFR-303-M1")
def test_exactly_double_the_longest_lifetime_is_accepted_through_the_entry_point() -> None:
    """경계 — 정확히 2배는 진입점에서도 통과한다 (`≤` 이지 `<` 가 아니다).

    오라클: 최장 자원 수명 × 2. 함수 층 경계는 `tests/cba/test_proforma.py` 가
    이미 보지만, **배선이 `<` 로 들어가면 그 테스트는 초록불인 채** 실행 경로만
    한 해씩 좁아진다. 통과 케이스를 함께 두지 않으면 그것이 드러나지 않는다.
    """
    ceiling = _ceiling_years()

    try:
        outcome = run_single_case_e2e(
            {}, level_map=LEVEL_MAP, horizon_years=ceiling
        )
    except ValidationError as exc:
        pytest.fail(f"경계값(정확히 2배) {ceiling}년이 거부됐다: {exc.as_dict()}")

    assert "npv" in outcome.metrics


@pytest.mark.req("NFR-303-M1")
def test_over_the_ceiling_is_refused_by_the_execution_path() -> None:
    """음성 — 상한을 1년 넘긴 분석기간을 진입점에 넣으면 거부된다 (DV-5).

    오라클: §7.3 `DV-5` *「분석기간 ≤ 최장 자원 수명 × 2」*. 최장 수명은
    `PV.lifetime` 이고 상한은 그 2배다.

    **3요소(필드·사유·조치)를 함께 본다** — `NFR-303` 이 요구하는 것이고,
    사유에 실제 수치가 없으면 사용자는 무엇을 얼마로 낮춰야 하는지 모른다.
    """
    over = _ceiling_years() + 1

    with pytest.raises(ValidationError) as caught:
        run_single_case_e2e({}, level_map=LEVEL_MAP, horizon_years=over)

    parts = caught.value.as_dict()
    assert parts["rule"] == "DV-5"
    assert parts["field"] == "cba.analysis_years"
    reason = parts["reason"] or ""
    assert str(over) in reason, f"거부된 분석기간이 사유에 없다: {reason!r}"
    assert (parts["action"] or "").strip()


@pytest.mark.req("NFR-303-M1")
def test_the_refusal_happens_before_the_cba_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★ **거부가 CBA 앞에 있다** — 상한을 넘긴 케이스의 NPV 가 있으면 안 된다.

    「예외가 났다」만 보면 **다 계산한 뒤에 던지는 구현**도 통과한다. 그러면
    위반 케이스의 수치가 한 번은 존재하게 되고, 그것이 로그·캐시·리포트 어디로든
    새어 나갈 수 있다.

    `e2e_runner` 는 `npv` 를 자기 이름공간으로 가져오므로 그 이름을 갈아 끼워
    **호출 여부**를 센다.
    """
    calls: list[object] = []

    def _recording_npv(*args: object, **kwargs: object) -> float:
        calls.append(args)
        return 0.0

    monkeypatch.setattr(e2e_runner, "npv", _recording_npv)

    # 먼저 정상 조합으로 이 계수기가 실제로 센다는 것을 보인다 — 세지 않는
    # 계수기로 「0회」를 단언하면 그 단언은 아무것도 붙들지 않는다
    run_single_case_e2e({}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON)
    # 케이스 지표 한 번 + **등록된 변형마다 한 번** (R32 — FR-607-AC1 배선).
    # 상수 1 로 두면 변형이 하나 늘 때 이 단언이 빨간불이 되고, 그것은 결함이
    # 아니라 확장점이 쓰인 것이다 — 세는 근거를 목록에서 가져온다.
    assert len(calls) == 1 + len(run_order()), (
        "계수기가 정상 경로에서 세지 않는다 — 단언이 무의미해진다"
    )

    calls.clear()
    with pytest.raises(ValidationError):
        run_single_case_e2e(
            {}, level_map=LEVEL_MAP, horizon_years=_ceiling_years() + 1
        )

    assert calls == [], "상한을 넘겼는데 CBA 가 돌았습니다 — 거부가 계산 뒤에 있습니다"


@pytest.mark.req("NFR-303-M1")
def test_the_horizon_argument_also_drives_the_cashflow_not_just_the_check() -> None:
    """★★ **재는 것과 쓰는 것이 같아야 한다** — 인자가 계산에도 들어간다.

    `horizon_years` 를 검사에만 넘기고 프로포마가 모듈 상수를 계속 쓰면, 이
    파일의 다른 넷은 **전부 초록불**이다. 그런데 그 상태는 *「분석기간을 재는
    값」*과 *「분석기간으로 계산하는 값」*이 갈린 것이고, 아무 예외도 나지
    않으므로 어디서도 드러나지 않는다 — 값은 맞고 뜻이 틀린 형태다.

    분석기간이 짧아지면 편익 연도 수가 줄어 NPV 가 달라진다. **방향이 아니라
    「달라진다」를 본다** — 부호는 단가·할인율에 달려 있고 이 파일은 금액을
    붙드는 자리가 아니다(그것은 `tests/cba/` 의 몫이다).
    """
    full = run_single_case_e2e({}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON)
    half = run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON // 2
    )

    assert full.metrics["npv"] != half.metrics["npv"], (
        "분석기간을 절반으로 줄였는데 NPV 가 같습니다 — "
        "`horizon_years` 가 검사에만 쓰이고 계산은 상수를 보고 있습니다"
    )


@pytest.mark.req("NFR-303-M1")
def test_the_runner_declares_no_default_horizon() -> None:
    """★★ **러너가 분석기간의 기본값을 갖지 않는다 (R31).**

    종전에는 `HORIZON_YEARS = 20` 모듈 상수가 기본값이었다. 그런데 §7.1 O-1 은
    분석기간의 소유자를 `AssumptionSet` 으로 못 박고 `infra/orm/scenario.py` 가
    그것을 금지 필드로 열거한다 — **소유자는 정해져 있었고 값만 다른 층에
    있었다.**

    기본값이 되살아나면 대장을 고쳐도 이 구획이 옛 값을 쓴다. 그 어긋남은
    **NPV 를 바꾸면서 아무 예외도 내지 않으므로** 어느 검사도 잡지 못한다 —
    위 넷은 전부 초록불인 채다. 그래서 시그니처를 직접 붙든다
    (`test_leap_year_policy` 가 `steps_per_year` 에 쓴 것과 같은 형태).
    """
    parameter = inspect.signature(run_single_case_e2e).parameters["horizon_years"]

    assert parameter.default is inspect.Parameter.empty, (
        f"`horizon_years` 에 기본값 {parameter.default!r} 이 생겼습니다. "
        "분석기간의 소유자는 `AssumptionSet` 입니다(§7.1 O-1) — 호출측이 "
        "`provider.analysis_years()` 로 읽어 넘기십시오"
    )
