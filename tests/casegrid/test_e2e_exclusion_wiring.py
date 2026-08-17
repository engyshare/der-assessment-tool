"""실행 경로가 **배타 규칙을 지나는가** — FR-402-AC2.A · DV-12 · §14 DoD 6.

거부 기계(`assert_no_exclusions`)와 선언적 규칙표는 R16 이 만들었고, 그것을
붙드는 테스트도 촘촘하다. **그런데 그 테스트가 전부 그 함수를 직접 부른다.**
R26 재검증에서 `assert_no_exclusions` 를 부르는 **배포 코드가 0곳**임이 드러났다
— 실행은 `core/casegrid/e2e_runner.py` 를 지나는데, 거기서는 편익을 조립해 CBA
까지 가면서 배타 검사를 한 번도 부르지 않았다.

즉 DoD 6 의 *「배타 규칙 위반 조합은 **실행이 거부**됨」* 이 **실행 경로에서는
성립하지 않았고**, 그 사실을 어느 테스트도 볼 수 없었다. 함수 층만 검사하면
배선이 되돌아가도 전건 초록불이기 때문이다.

이 파일이 붙드는 것은 함수가 아니라 **배선**이다.

    정상 조합은 그대로 돈다                     ← 거부가 정당한 실행을 막지 않는다
    유형 A 조합은 거부된다                      ← 차단 100% (FR-402-AC2.A)
    ★ 거부는 **CBA 에 닿기 전에** 일어난다      ← 위반 조합의 NPV 가 만들어지지 않는다

셋째가 요점이다. 「예외가 났다」만 보면 **이미 다 계산한 뒤에 던지는 구현**도
통과하고, 그러면 위반 조합의 NPV 가 한 번은 만들어진다 — `DV-10` 에서 러너
호출 0회를 단언한 것과 같은 이유다.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from core.casegrid import e2e_runner
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.casegrid.variants import run_order
from core.contracts.validation import ValidationError
from core.valuestream import SelfConsumption

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **배선**이다.
#: 실물 대장으로 도는 것은 `tests/acceptance2/test_17_2_dod2.py` 가 이미 한다.
LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    # 설계 변수(용량)는 이 파일의 관심이 아니지만 **러너가 요구한다** —
    # 기본값을 두지 않는 것이 규칙이라 기본 탐색점을 그대로 받아 온다.
    **design_levels(),
}

#: 분석기간 **탐침값** — 이 파일이 보는 것은 배타 규칙 배선이고 분석기간이
#: 아니다. 대장값과 같을 필요가 없으므로 일부러 다른 수를 쓴다(사본을 만들면
#: 대장이 바뀔 때 여기가 따라오지 않아도 아무 일이 없다).
_PROBE_HORIZON = 18

#: `SurplusSale` 과 유형 A 인 편익 — `docs/exclusion-rules.yaml` 첫 행이다
#: (*「같은 1 kWh 를 자가소비 절감과 잉여판매로 동시 계상할 수 없다」*).
#: 규칙표가 정본이므로 여기서 유형을 다시 적지 않는다.
def _self_consumption() -> SelfConsumption:
    return SelfConsumption(
        baseline_annual_bill_won=1_200_000.0,
        new_annual_bill_won=900_000.0,
    )


@pytest.mark.req("FR-402-AC2.A")
def test_normal_case_still_runs_end_to_end() -> None:
    """양성 — 배타 쌍이 아닌 기본 조합은 그대로 NPV 를 낸다.

    거부만 검사하면 **무엇이든 거부하는** 구현도 통과한다. FR-402-AC1 은
    정당한 동시 계상을 막지 말라고 명시로 요구하므로 이쪽을 함께 둔다.
    """
    outcome = run_single_case_e2e({}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON)

    assert "npv" in outcome.metrics
    assert "payback_years" in outcome.metrics


@pytest.mark.req("FR-402-AC2.A")
@pytest.mark.req("NFR-303-M1")
def test_type_a_combination_is_refused_by_the_execution_path() -> None:
    """음성 — 유형 A 조합을 실행 진입점에 넣으면 거부된다 (DV-12).

    오라클: `docs/exclusion-rules.yaml` 첫 행. `SelfConsumption` ↔ `SurplusSale`
    은 같은 1 kWh 를 두 번 계상하므로 차단 대상이다. 내장 편익에 `SurplusSale`
    이 있으므로 자가소비를 더하면 그 쌍이 성립한다.
    """
    with pytest.raises(ValidationError) as caught:
        run_single_case_e2e(
            {},
            level_map=LEVEL_MAP,
            horizon_years=_PROBE_HORIZON,
            extra_value_streams=[_self_consumption()],
        )

    parts = caught.value.as_dict()
    assert parts["rule"] == "DV-12"
    assert parts["field"] == "valuestream.enabled"
    reason = parts["reason"] or ""
    assert "SelfConsumption" in reason and "SurplusSale" in reason, (
        f"어느 쌍이 걸렸는지 사유에 없다: {reason!r}"
    )
    assert (parts["action"] or "").strip()


@pytest.mark.req("FR-402-AC2.A")
def test_the_refusal_happens_before_the_cba_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★ **거부가 CBA 앞에 있다** — 위반 조합의 NPV 가 만들어지면 안 된다.

    「예외가 났다」만 보면 **다 계산한 뒤에 던지는 구현**도 통과한다. 그러면
    위반 조합의 수치가 한 번은 존재하게 되고, 그것이 로그·캐시·리포트 어디로든
    새어 나갈 수 있다. `DV-10` 이 러너 호출 0회를 단언한 것과 같은 이유다.

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
    # 케이스 지표 한 번 + **등록된 변형마다 한 번** (R32 — FR-607-AC1 배선)
    assert len(calls) == 1 + len(run_order()), (
        "계수기가 정상 경로에서 세지 않는다 — 단언이 무의미해진다"
    )

    calls.clear()
    with pytest.raises(ValidationError):
        run_single_case_e2e(
            {},
            level_map=LEVEL_MAP,
            horizon_years=_PROBE_HORIZON,
            extra_value_streams=[_self_consumption()],
        )

    assert calls == [], "위반 조합인데 CBA 가 돌았습니다 — 거부가 계산 뒤에 있습니다"
