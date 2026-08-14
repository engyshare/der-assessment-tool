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

from types import MappingProxyType

import pytest

from core.casegrid import e2e_runner
from core.casegrid.e2e_runner import HORIZON_YEARS, run_single_case_e2e
from core.contracts.validation import ValidationError

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **배선**이다.
#: 실물 대장으로 도는 것은 `tests/acceptance2/test_17_2_dod2.py` 가 이미 한다.
LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
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
def test_default_horizon_still_runs_end_to_end() -> None:
    """양성 — 기본 분석기간(종전 상수)은 그대로 NPV 를 낸다.

    거부만 검사하면 **무엇이든 거부하는** 구현도 통과한다. 그리고 이 배선이
    기존 케이스그리드 실행을 막지 않는다는 것 자체가 확인 대상이다.
    """
    metrics = run_single_case_e2e({}, level_map=LEVEL_MAP)

    assert "npv" in metrics
    assert "payback_years" in metrics


@pytest.mark.req("NFR-303-M1")
def test_exactly_double_the_longest_lifetime_is_accepted_through_the_entry_point() -> None:
    """경계 — 정확히 2배는 진입점에서도 통과한다 (`≤` 이지 `<` 가 아니다).

    오라클: 최장 자원 수명 × 2. 함수 층 경계는 `tests/cba/test_proforma.py` 가
    이미 보지만, **배선이 `<` 로 들어가면 그 테스트는 초록불인 채** 실행 경로만
    한 해씩 좁아진다. 통과 케이스를 함께 두지 않으면 그것이 드러나지 않는다.
    """
    ceiling = _ceiling_years()

    try:
        metrics = run_single_case_e2e(
            {}, level_map=LEVEL_MAP, horizon_years=ceiling
        )
    except ValidationError as exc:
        pytest.fail(f"경계값(정확히 2배) {ceiling}년이 거부됐다: {exc.as_dict()}")

    assert "npv" in metrics


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
    run_single_case_e2e({}, level_map=LEVEL_MAP)
    assert len(calls) == 1, "계수기가 정상 경로에서 세지 않는다 — 단언이 무의미해진다"

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
    full = run_single_case_e2e({}, level_map=LEVEL_MAP, horizon_years=HORIZON_YEARS)
    half = run_single_case_e2e({}, level_map=LEVEL_MAP, horizon_years=HORIZON_YEARS // 2)

    assert full["npv"] != half["npv"], (
        "분석기간을 절반으로 줄였는데 NPV 가 같습니다 — "
        "`horizon_years` 가 검사에만 쓰이고 계산은 상수를 보고 있습니다"
    )
