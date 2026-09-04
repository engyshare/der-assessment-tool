"""**스윕이 본 실행과 같은 계측 선언으로 돈다** — `_Sweeper` 의 ⓒ 배선.

(`FR-705-AC2` · `DV-15` · R60/WP-3)

## 이 파일이 붙드는 것 — 주석에 적은 사유를 **시험으로 세운다**

`core/report/case_influences.py::_Sweeper` 는 5.1 영향도·결합 스윕·용량 검토가
쓰는 탐침이며, 축을 하나씩 옮겨 `run_single_case_e2e` 를 **다시 돌린다.**
R60/WP-2 가 기준선 갈래를 그 생성자의 **필수 인자**로 세운 이유는 *「안 넘기면
본문 4절과 5.1 이 서로 다른 기준선 위에 선다」* 였다.

★★★ **ⓒ(자가용 집합자원화)에서는 그 어긋남이 「다른 기준선」이 아니라 「아예
안 돈다」다.** ⓒ 의 성립 전제(소유·운영권 인계 · 구분 계측)는 명시적 입력이고
선언이 없으면 `get_baseline_branch` 가 `DV-15` 로 거부하므로, 선언을 스윕에
넘기지 않으면 **본문 4절만 서고 5.1·용량 검토가 통째로 거부된다** — 리포트가
조립되지 않는다. 그것이 `_Sweeper.__init__` 과 `case_report.py` 의 주석이 적은
사유이고, 이 파일이 그 사유를 잰다.

    P1  선언이 러너까지 **그 객체 그대로** 닿는다        ← 스파이(빠르다)
    P2  ⓒ + 선언이면 스윕이 **값을 낸다**                ← 실물 한 번
    P3  ⓒ + 선언 없음이면 스윕이 **`DV-15` 로 거부**한다 ← 실물 한 번

★ **P1 과 P2·P3 를 함께 두는 이유.** 스파이만으로는 *「인자가 흘러갔다」* 까지만
재고 그 인자가 실제로 거부를 풀거나 값을 바꾸는지는 모른다. 반대로 실물만
두면 *「어느 인자 때문에 됐는가」* 를 못 가른다.

## ⚠ 가장 좁은 입력으로 잰다

`conclusion_at_many({})` 는 축을 하나도 옮기지 않으므로 러너를 **한 번만**
돌린다(`_Sweeper` 의 메모가 그 한 번을 기억한다). 케이스 그리드를 돌리지 않고
`build_level_map` 이 낸 대장 기준수준만 쓴다 — 지시문 2절의 *「30초를 넘기면
멈춰라」* 를 지키는 자리다(실측은 아래 result 파일이 갖는다).

⚠ **`tests/report/test_case_influences.py` 에 얹지 않았다.** 그 파일의 머리말이
자기 대상을 *「R54/WP-2 가 갈라낸 영향도 스윕이 본 실행과 같은 사업을
그리는가」* 로 적고 스파이 하나로 그것을 잰다. ⓒ 는 **거부가 걸린 갈래**이므로
실물 실행 둘이 필요하고, 그것을 그 파일에 넣으면 빠른 스파이 파일에 초 단위
검사가 섞인다.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import load_daily_shapes
from core.cba.baseline import BaselineArrangement, PoolMeteringDeclaration
from core.contracts.validation import ValidationError
from core.report import case_influences
from core.report.case_influences import CONCLUSION_METRIC, PLAN_VARIANT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 둘 다 선언한 계측 전제 — ⓒ 가 서는 유일한 조건이다.
_DECLARED = PoolMeteringDeclaration(
    ownership_or_operation_transferred=True, metering_separated=True
)


def _sweeper(
    arrangement: BaselineArrangement,
    *,
    pool_metering: PoolMeteringDeclaration | None,
) -> case_influences._Sweeper:
    """대장 기준수준만 쓰는 **가장 좁은** 탐침.

    ⚠ 값을 손으로 짓지 않는다 — `build_level_map` 이 낸 것을 그대로 쓴다.
    베끼면 대장이 바뀔 때 이 검사가 다른 사업을 재게 된다.
    """
    return case_influences._Sweeper(
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=20,
        scheme=None,
        daily_shapes=load_daily_shapes(),
        rec_price_won_per_unit=0.0,
        rec_weight_pv=1.0,
        distributed_sub_items=None,
        baseline_arrangement=arrangement,
        pool_metering=pool_metering,
    )


@pytest.mark.req("FR-705-AC2")
def test_the_sweeper_hands_the_pool_metering_declaration_to_the_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**P1** — 생성자가 받은 계측 선언이 러너까지 **그 객체 그대로** 닿는다.

    ★ **「헷갈릴 여지 없는」 선언을 준다** — 한쪽만 참인 선언을 넘긴다. 둘 다
    참인 기본형을 넘기면 러너가 인자를 흘려버리고 스스로 지어낸 선언을 써도
    같은 모양이 되어 이 단언이 아무것도 붙들지 못한다(같은 판단을 이 폴더의
    `test_case_influences.py` 가 `distributed_sub_items`·`baseline_arrangement`
    에서 이미 했다).

    ⚠ 러너를 스파이로 갈아 끼우므로 **거부는 여기서 재지 않는다** — 아래 P3 이
    실물로 잰다.
    """
    recorded: dict[str, object] = {}

    def fake_runner(*args: object, **kwargs: object) -> object:
        recorded.update(kwargs)
        return SimpleNamespace(variants={PLAN_VARIANT: {CONCLUSION_METRIC: 1.0}})

    monkeypatch.setattr(case_influences, "run_single_case_e2e", fake_runner)

    lopsided = PoolMeteringDeclaration(metering_separated=True)
    sweeper = case_influences._Sweeper(
        level_map={
            "household_load_annual_kwh": {"low": 1.0, "base": 2.0, "high": 3.0}
        },
        horizon_years=10,
        scheme=None,
        daily_shapes=load_daily_shapes(),
        rec_price_won_per_unit=70.0,
        rec_weight_pv=1.0,
        distributed_sub_items=None,
        baseline_arrangement=BaselineArrangement.POOL,
        pool_metering=lopsided,
    )
    sweeper.conclusion_at_many({"household_load_annual_kwh": 5.0})

    assert recorded, "스파이가 호출을 녹음하지 못했다 — 이 검사가 아무것도 보지 못했다"
    assert recorded["pool_metering"] is lopsided, (
        f"생성자는 {lopsided!r} 를 받았는데 러너에는 "
        f"{recorded.get('pool_metering')!r} 이 닿았다 — 스윕이 본 실행과 다른 "
        "계측 전제 위에 선다(ⓒ 에서는 그 어긋남이 곧 `DV-15` 거부다)"
    )


@pytest.mark.req("FR-705-AC2")
def test_the_pool_sweep_runs_with_the_declaration_and_is_refused_without_it() -> None:
    """**P2·P3** ★ — 선언이 있으면 ⓒ 스윕이 **값을 내고**, 없으면 **거부**된다.

    ★★ **P3 가 이 배선의 존재 이유다.** 선언을 `_Sweeper` 에 넘기지 않으면
    ⓒ 를 고른 실행에서 5.1 영향도·결합 스윕·용량 검토가 **전건** 이 예외로
    죽는다 — 본문 4절만 선 리포트가 된다. 그러므로 이 거부는 「막는 것」이
    아니라 **그 인자가 실제로 필요하다는 증거**다.

    ⚠ **크기를 못 박지 않는다.** ⓒ 의 결론축 실측(−14,636,061원)은
    `tests/report/test_pool_branch_calculated.py` 가 진입점을 지나서 재고,
    여기서 다시 박으면 같은 수를 두 곳이 갖는다. 여기서 재는 것은
    *「도는가 / 거부되는가」* 다.

    ⚠ ⓑ 와 견주어 **수가 실제로 갈리는지**도 본다 — 「무슨 수든 낸다」만
    보면 선언을 받고도 포기 항을 안 세우는 구현이 통과한다.
    """
    with_declaration = _sweeper(
        BaselineArrangement.POOL, pool_metering=_DECLARED
    ).conclusion_at_many({})
    maintain = _sweeper(
        BaselineArrangement.MAINTAIN, pool_metering=None
    ).conclusion_at_many({})

    assert isinstance(with_declaration, float)
    assert with_declaration < maintain, (
        f"ⓒ 스윕이 낸 결론({with_declaration:,.0f}원)이 ⓑ"
        f"({maintain:,.0f}원)보다 나쁘지 않다 — 선언을 받고도 포기 항이 "
        "스윕의 프로포마에 실리지 않았다"
    )

    with pytest.raises(ValidationError) as caught:
        _sweeper(BaselineArrangement.POOL, pool_metering=None).conclusion_at_many({})
    assert caught.value.rule == "DV-15", (
        f"규칙 ID 가 다르다: {caught.value.rule!r} — 선언 없는 ⓒ 스윕은 "
        "`DV-15` 로 거부되어야 한다(그것이 이 인자가 필요한 이유다)"
    )
