"""실행 경로가 **변형별 지표를 낳는가** — `FR-607-AC1` / R32.

R31 이 담을 자리(`CaseResult.variants`)와 표시 층(`build_variant_table`)을
만들었다. **그 필드를 채우는 배포 코드는 0곳이었다** — `grep -rn "variants=" core/
app/` 가 한 건도 내지 않았고 채우는 것은 테스트뿐이었다. 즉 소비자는 있고
생산자가 없었으며, 실제 실행 결과로 표를 부르면 「변형별 결과가 없습니다」로
거부됐다. **기계는 옳게 거부하는데 아무도 그것을 부르지 않는 상태.**

R26 이 형태 하나로 모은 결함이고(`DV-12`·`DV-5`·`FR-205`) 이것이 **넷째**다.

다섯 층을 따로 붙든다:

    ① 진입점이 변형을 낸다            등록된 변형 **전부**가 결과에 있다
    ② ★ 값이 서로 다르다              지원 조건이 있으면 무지원 ≠ 지원안
    ③ ★ 규약이 같다                   기준선 NPV = 케이스 지표 NPV
    ④ ★ 병렬 경로에서도 살아 있다     피클을 지나며 변형이 사라지지 않는다
    ⑤ ★ 확장점이 숫자에 닿는다        변형을 하나 더하면 그 값이 실제로 다르다

②를 따로 두는 이유가 요점이다. ①만 두면 **두 변형에 같은 지표를 두 번 담는
구현**이 초록불이다 — 표에는 행이 둘 있고 「자동 포함」도 지켜진 것처럼 보인다.
그런데 무지원과 지원안은 자부담이 다르므로 NPV 가 같을 수 없다.

⑤ 는 R23 이 `Perspective.SOCIETY` 에서 쓴 형태다 — **확장점을 신설했으면 그
경로로 두 번째 인스턴스를 넣어 보인다.** 여기서는 이미 있는 확장점(변형 파일
하나)이 **숫자까지** 닿는지를 본다. 닿지 않으면 확장점 문서가 *「필요한 것은
파일 하나이며 파이프라인은 바뀌지 않는다」* 고 약속한 것이 지켜지지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import Executor, ThreadPoolExecutor
from types import MappingProxyType
from typing import Any, ClassVar

import pytest

from core.casegrid import incentive_cases
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.execution import run_cases
from core.casegrid.ledger_levels import design_levels
from core.casegrid.models import Case
from core.casegrid.variants import run_order
from core.contracts.casevariant import CaseVariant
from core.contracts.validation import ValidationError
from core.incentive.schemas import IncentiveScheme
from core.report.variant_report import build_variant_table

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **배선**이다.
LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    # 계통 전력 구매 한계단가 — 러너가 요구한다(기본값을 두지 않는 것이 규칙).
    # **대장의 120 과 다른 수를 일부러 쓴다** — 같은 수를 쓰면 이 파일이 대장의
    # 사본을 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도 아무 일이
    # 없다 — 이 파일 머리의 「탐침값」 규약 그대로다.
    "grid_purchase_price": MappingProxyType({"base": 100.0}),
    # 잉여 판매단가 — 러너가 요구한다(R35 에 대장으로 올렸다). **대장의 110 과
    # 다른 수를 일부러 쓴다** — 위 구매 단가와 같은 이유이며, 두 단가가 서로
    # 다른 수인 것도 일부러다(같게 두면 R35 가 없앤 「우연히 같다」가 검사
    # 안에서 되살아난다).
    "surplus_sale_price": MappingProxyType({"base": 90.0}),
    # 설계 변수(용량)는 이 파일의 관심이 아니지만 **러너가 요구한다** —
    # 기본값을 두지 않는 것이 규칙이라 기본 탐색점을 그대로 받아 온다.
    **design_levels(),
}

#: 분석기간 탐침값 — 소유자는 `AssumptionSet` 이고 이 파일의 관심이 아니다.
_PROBE_HORIZON = 18

#: 보조율 탐침값. 대장값이 아니다 — **0 이 아니라는 것만이** 이 파일의 관심이다.
_PROBE_SUBSIDY_RATE = 0.3


def _scheme(**kwargs: Any) -> IncentiveScheme:
    """검사용 지원 조건 — 지정하지 않은 칸은 「효과 없음」으로 둔다."""
    defaults: dict[str, Any] = {
        "subsidy_rate": _PROBE_SUBSIDY_RATE,
        "subsidy_fixed": None,
        "subsidy_limit": None,
        "loan_rate": 0.0,
        "loan_interest": 0.0,
        "loan_grace_years": 0,
        "loan_repayment_years": 0,
        "loan_repayment_type": "원리금균등",
        "tax_credit_rate": 0.0,
        "sponsor": "국비",
        "funding_program": None,
        "is_prefunded": False,
        "prefunded_status": None,
    }
    defaults.update(kwargs)
    return IncentiveScheme(**defaults)


def _run(**kwargs: Any) -> Any:
    return run_single_case_e2e(
        {}, level_map=LEVEL_MAP, horizon_years=_PROBE_HORIZON, **kwargs
    )


@pytest.mark.req("FR-607-AC1")
def test_the_entry_point_produces_every_registered_variant() -> None:
    """① 진입점이 **등록된 변형 전부**의 지표를 낸다.

    「모든 실행에서 자동 포함」이므로 스킴을 주지 않은 평범한 실행도 변형을
    낸다 — 지원 조건이 없는 사업에도 무지원 기준선은 있다.
    """
    outcome = _run()

    assert set(outcome.variants) == {v.tag for v in run_order()}, (
        "실행이 등록된 변형 전부를 산출하지 않았습니다 — 「모든 실행에서 자동 "
        "포함」이 실행 경로에서 성립하지 않습니다"
    )


@pytest.mark.req("FR-607-AC1")
def test_the_variants_do_not_carry_the_same_numbers_twice() -> None:
    """② ★★ 무지원과 지원안의 **NPV 가 다르다**.

    ①만 두면 **같은 지표를 두 번 담는 구현**이 통과한다. 그 표는 행이 둘이고
    「자동 포함」도 지켜진 것처럼 보이는데, 실제로는 지원의 효과가 0으로
    보고되고 **그것이 이 저장소의 목적 자체**(지원 수준 산출)를 무의미하게
    만든다.

    보조율 30%면 사업자 자부담이 줄어 NPV 가 **커진다** — 방향까지 본다.
    「다르다」만 보면 부호를 뒤집어 자부담을 늘리는 구현도 통과한다.
    """
    outcome = _run(scheme=_scheme())

    baseline = outcome.variants["unsupported"]["npv"]
    planned = outcome.variants["as_planned"]["npv"]

    assert planned > baseline, (
        f"보조율 {_PROBE_SUBSIDY_RATE:.0%} 인데 지원안 NPV({planned})가 무지원"
        f"({baseline})보다 크지 않습니다 — 지원이 계산에 들어가지 않았거나 "
        "부호가 뒤집혔습니다"
    )


@pytest.mark.req("FR-607-AC1")
def test_no_support_means_the_two_variants_agree() -> None:
    """②의 뒤쪽 — 지원 조건이 없으면 두 변형이 **같아야** 한다.

    이것을 두지 않으면 「두 값이 언제나 다르게 나오는」 구현(예: 변형마다 다른
    상수를 섞는 것)이 위 테스트를 통과한다. 지원이 0인 사업에서 무지원과
    입력 지원안은 **같은 사업**이다.
    """
    outcome = _run()

    assert (
        outcome.variants["unsupported"]["npv"] == outcome.variants["as_planned"]["npv"]
    ), "지원이 0인데 두 변형의 NPV 가 다릅니다 — 변형이 지원 외의 것을 바꿉니다"


@pytest.mark.req("FR-607-AC1")
def test_the_baseline_variant_and_the_case_metric_use_one_convention() -> None:
    """③ ★★ 기준선 NPV = 케이스 지표 NPV — **할인 규약이 갈리지 않았다.**

    지원 현금흐름 행은 `{1: -자부담}` 이라 **1년차**에 있고, 케이스 지표는
    총사업비를 **`t=0`** 에 두고 뺀다. 변형 쪽을 운영 행에 그대로 섞으면 같은
    이름(`npv`)의 두 수가 **한 해 차이로 할인**되어, 비교 표에서 「지원이 없는
    변형이 케이스보다 유리」한 것으로 조용히 어긋난다.

    무지원 기준선은 지원이 0이므로 자부담이 총사업비와 같다 — 그러므로 규약이
    같다면 두 수가 **일치해야** 하고, 이 일치가 규약 어긋남을 재는 저울이다.
    """
    outcome = _run()

    assert outcome.variants["unsupported"]["npv"] == outcome.metrics["npv"], (
        "무지원 기준선의 NPV 가 케이스 지표와 다릅니다 — 초기투자를 `t=0` 에 "
        "두는 규약이 한쪽에서만 지켜지고 있습니다"
    )


@pytest.mark.req("FR-607-AC1")
def test_the_case_grid_carries_the_variants_into_the_result() -> None:
    """`run_cases()` 가 변형을 `CaseResult` 로 나른다 — 표가 실제로 선다.

    함수 층만 보면 진입점이 변형을 «돌려주는» 것까지만 알 수 있다. 그 값을
    케이스 그리드가 버리면 표시 층은 여전히 빈 결과를 받고, 그 상태에서 위
    네 테스트는 전부 초록불이다.
    """
    results = run_cases(
        [Case(index=0, values={})],
        lambda case: _run(scheme=_scheme()),
    )

    table = build_variant_table(results[0])

    assert table.baseline_row.tag == "unsupported"
    assert table.baseline_row.baseline is True
    # ★ **목록을 못 박는다.** 지표가 변형마다 갈리면 `build_variant_table` 이
    # 거부하므로 그 어긋남은 여기까지 오지 않는다. 이 단언이 지키는 것은 다른
    # 것이다 — **지표가 조용히 사라지는 것**. R33 이 `initial_outlay_won` 을
    # 더했고(리포트가 「얼마를 덜 냈기에 그런가」를 말하려면 필요하다) 그때
    # 이 줄이 빨간불로 그 사실을 알렸다. 지우면 다음 사람이 지표를 지워도
    # 아무 일도 일어나지 않는다.
    assert table.metric_names == ("initial_outlay_won", "npv", "payback_years")


@pytest.mark.req("FR-607-AC1", "FR-805-AC1")
def test_the_variants_survive_the_parallel_path() -> None:
    """④ ★ 병렬 경로에서도 변형이 살아 있다 — 결과가 **피클을 지난다.**

    `CaseResult.__getstate__` 가 `variants` 를 빠뜨리면 **직렬에서는 보이고
    병렬에서만 사라진다.** R31 이 그 위험을 독스트링에 적어 두었으나 그때는
    변형을 낳는 코드가 없어 실행 경로로 확인할 수 없었다.

    `ProcessPoolExecutor` 대신 스레드를 쓰면 피클을 지나지 않아 이 검사가
    아무것도 붙들지 못한다. 그래서 **결과를 직접 피클로 왕복**시켜 그 층을
    따로 붙든다(프로세스 풀은 람다를 절일 수 없어 이 파일에서 쓸 수 없다).
    """
    import pickle

    def _factory(max_workers: int | None) -> Executor:
        return ThreadPoolExecutor(max_workers=max_workers or 1)

    results = run_cases(
        [Case(index=0, values={})],
        lambda case: _run(scheme=_scheme()),
        parallel=True,
        executor_factory=_factory,
    )

    restored = pickle.loads(pickle.dumps(results[0]))

    assert dict(restored.variants) == dict(results[0].variants), (
        "피클 왕복에서 변형이 달라졌습니다 — 병렬 실행에서만 변형이 사라지고 "
        "케이스 수가 적은 검사에서는 드러나지 않습니다"
    )
    assert build_variant_table(restored).rows[0].baseline is True


class _MinimumSupportProbe(CaseVariant):
    """⑤ 를 위한 **세 번째 변형** — 등록 파일을 놓는 대신 목록에 끼워 넣는다.

    `FR-608`(최소 지원 수준 역산)이 올 자리가 이런 모양이다: 보조율을 자기
    값으로 덮어쓰는 변형. **실물 파일을 놓지 않는 이유**는 그러면 저장소의
    모든 실행이 이 탐침 변형을 산출하게 되기 때문이다.
    """

    tag: ClassVar[str] = "minimum_support_probe"
    label: ClassVar[str] = "최소 지원 탐침"
    order: ClassVar[int] = 50
    clauses: ClassVar[tuple[str, ...]] = ("FR-607-AC1",)

    def overrides(self, base: Mapping[str, Any]) -> dict[str, Any]:
        return {"subsidy_rate": _PROBE_SUBSIDY_RATE / 2}


@pytest.mark.req("FR-607-AC1", "FR-801-AC1")
def test_a_third_variant_changes_its_own_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⑤ ★★★ 변형을 하나 더하면 **그 변형의 값이 실제로 달라진다.**

    이것이 R32 가 찾은 것이다. `CaseVariant.overrides()` 는 추상 메서드라 변형
    전부가 구현하고 계약 테스트가 반환값을 붙들고 있었는데, **그것을 읽는 배포
    코드가 한 줄도 없었다.** 순회는 `baseline` 깃발 하나만 보고 「무지원」과
    「입력 스킴 그대로」로 갈랐다.

    변형이 둘일 때는 두 기계의 답이 같다. **셋째에서 갈린다** — 보조율 15% 를
    덮어쓰는 변형이 입력 지원안(30%)과 **똑같은 NPV** 를 내면서 아무 예외도
    내지 않는다. 표에는 행이 셋 있고 값이 둘만 다르니 사람은 그것을 「지원안이
    최소 지원과 같다」는 결과로 읽는다.
    """
    monkeypatch.setattr(
        incentive_cases,
        "run_order",
        lambda: (*run_order(), _MinimumSupportProbe),
    )

    outcome = _run(scheme=_scheme())

    probe = outcome.variants["minimum_support_probe"]["npv"]
    baseline = outcome.variants["unsupported"]["npv"]
    planned = outcome.variants["as_planned"]["npv"]

    assert baseline < probe < planned, (
        f"보조율 15% 변형의 NPV({probe})가 무지원({baseline})과 30% 지원안"
        f"({planned}) 사이에 있지 않습니다 — `overrides()` 가 계산에 닿지 "
        "않고 있으며, 새 변형 파일은 값이 아니라 이름만 늘립니다"
    )


class _TypoVariant(CaseVariant):
    """오타를 낸 변형 — `subsidy_rate` 를 `subsidy_ratio` 로 적었다."""

    tag: ClassVar[str] = "typo_probe"
    label: ClassVar[str] = "오타 탐침"
    order: ClassVar[int] = 60

    def overrides(self, base: Mapping[str, Any]) -> dict[str, Any]:
        return {"subsidy_ratio": 0.1}


@pytest.mark.req("FR-607-AC1", "NFR-303-M1")
def test_an_unknown_override_key_is_refused_not_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 모르는 덮어쓰기 키는 **거부**된다 — 조용히 무시하지 않는다.

    무시하면 그 변형은 입력 지원안과 **같은 수**를 내면서 표에 별개 행으로
    남는다. 「효과 없는 지원안」으로 읽히는데 실제로는 오타 하나다 — 이
    저장소가 반복해 만난 「검사가 아무것도 붙들지 않는」 형태의 입력측 판이다.
    """
    monkeypatch.setattr(
        incentive_cases, "run_order", lambda: (*run_order(), _TypoVariant)
    )

    with pytest.raises(ValidationError) as caught:
        _run(scheme=_scheme())

    parts = caught.value.as_dict()
    assert "subsidy_ratio" in (parts["reason"] or "")
    assert (parts["action"] or "").strip()
