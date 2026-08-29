"""교체비·잔존가치 행 — **일회성 흐름을 만드는 한 자리** (R39-E2 가 갈라냈다).

## 왜 `e2e_runner` 에서 갈라냈나

`NFR-206`(파일 500줄)의 **코드 줄** 상한을 배선이 넘겼다(519줄). 상한을 고치는
것은 spec 개정(§16.5)이고, 근거 주석을 지워 줄이는 것은 조항이 지키려던 것을
정면으로 해치므로 **갈래를 하나 떼는 것**이 남는 길이었다.

**이 함수가 떼기 좋은 이유**: 러너의 다른 부분과 달리 자원 둘과 분석기간만 받고
행·표시줄을 낼 뿐 케이스·대장·디스패치를 보지 않는다. 즉 **경계가 이미 있었다.**

⚠ **러너는 이 함수를 `e2e_runner._lifecycle_rows` 라는 이름으로 계속 부른다** —
검사가 그 이름을 갈아 끼워 「이 행들이 지표에 닿는가」를 재기 때문이다
(`tests/casegrid/test_lifecycle_wiring.py::test_the_one_off_flows_reach_the_npv`).
이름을 옮기면 그 그물이 조용히 아무것도 재지 않게 된다.
"""

from __future__ import annotations

from core.casegrid.models import (
    ONE_OFF_REPLACEMENT,
    ONE_OFF_SALVAGE,
    OneOffLine,
)
from core.cba.proforma import replacement_row, salvage_row
from core.contracts.schemas import CashFlowRow
from core.der.ess import ESS
from core.der.pv import PV

__all__ = ("lifecycle_rows",)


def lifecycle_rows(
    *, pv: PV, ess: ESS, horizon_years: int
) -> tuple[list[CashFlowRow], tuple[OneOffLine, ...]]:
    """**교체비·잔존가치 행** — 다섯 라운드가 미룬 배선 (R39-E · `FR-104-AC2`·`AC5`).

    ## ★★ 부품은 전부 있었고 읽는 쪽이 없었다

    `ESS.replacement_schedule()`·`PV.replacement_schedule()`·`salvage_value()`·
    `core/cba/proforma.py::replacement_row()`·`core/cba/salvage.py` 가 모두
    실재하고 단위 검사도 초록불이었다. 빠진 것은 **실행 경로가 그것을 부르는
    이 함수**였고, 그동안 프로포마의 비용 행은 넷(고정 O&M 둘·전력 구매·정산
    수수료)뿐이었다 — 20년 분석에서 18년차 배터리와 13년차 인버터를 **공짜로
    새로 사는 사업**이었고, 그 대가로 20년차에 남은 설비도 **버리는 사업**이었다.
    아무 예외도 나지 않는다. 「부품은 있는데 읽는 쪽이 없다」의 셋째다.

    ## ⚠ 갈라 넣을 수 없다 — 교체비와 잔존가치는 한 단위다

    교체비만 넣으면 결론이 나빠지고 잔존가치만 넣으면 좋아진다. 양식이
    *「한쪽만 반영한 수를 결론으로 올리지 않는다」*(NSPM 대칭성,
    `docs/report-form-심의보고서.md:252-256`)로 그 중간 상태를 금지한다 — 그래서
    **한 함수가 둘을 함께** 만든다. 갈라 두면 한쪽만 부르는 호출자가 생기고,
    그 실행의 결론은 **한 방향으로 틀린 채 그럴듯하다.**

    ## 잔존가치를 왜 **비용 행에 음수**로 넣는가 (편익 행이 아니다)

    `npv()` 는 어느 쪽이든 같다 — `net_operating_flows()` 가 비용의 부호를 한 번
    뒤집으므로 음수 비용은 그 경계에서 **양수 유입**이 된다(뒤집는 자리는 여전히
    그 하나다). 갈리는 것은 **`bcr()` 의 분자·분모**와 표시 자리이고, 그 둘로
    판정했다:

    - `bcr()` 의 분모는 *「초기투자 + 운영비용 현가」* 다(`metrics.py:88`).
      잔존가치는 **투입 자본의 회수**이므로 초기투자와 **같은 계정**에서
      상쇄되는 것이 맞다 — 분자에 넣으면 *사업이 만들지 않은 편익*이 편익
      현가에 섞이고, 같은 사업이 잔존가치를 편익으로 적으면 B/C 가 유리해진다
      (`fee_row` 독스트링이 반대 부호로 만난 형태와 같다: 비용을 편익 차감으로
      적으면 분모가 작아져 비율이 좋아진다).
    - `benefit_row()` 는 *「증분만(기준선 대비)」* 의 **편익 갈래**를 담는 자리이고
      (`FR-705`), 관점별 계산은 **편익 행을 tag 로 걸러** 만든다
      (`core/cba/perspective.py::compute_perspective_npv`). 자본 회수를 그 채널에
      두면 *「사회 관점에서 잔존가치를 제외하는가」* 라는 판정 대상이 새로 생기는데
      **그 판정은 조항에 없다** — 우리가 정박점을 만들지 않는다.

    ## ⚠ 교체 행은 스케줄이 빌 때 만들지 않는다 (전력 구매 행과 다르다)

    `energy_purchase_row` 는 *「수전이 0이어도 0원 행을 싣는다」* 다 — 「수전이
    없어서 0」과 「행이 없어서 0」이 프로포마에서 똑같이 보이기 때문이다. 교체
    행은 그렇게 할 수 없다: **연차가 없으면 행을 만들 자리가 없다**(0원을 몇
    년차에 적을 것인가). 그래서 그 둘을 가르는 일은 붙임 8 이 진다 — 자원 수명과
    이 목록을 **함께** 보고 판정한다(`core/report/unreflected.py::
    _replacement_items`). 잔존가치는 연차가 언제나 분석 종료연도이므로
    **0원이어도 행을 싣는다**(구성 셋 중 하나만 조건부인 이유가 여기 있다).
    """
    rows: list[CashFlowRow] = []
    lines: list[OneOffLine] = []
    for short, resource in (("PV", pv), ("ESS", ess)):
        schedule = resource.replacement_schedule(horizon=horizon_years)
        for year, cost in sorted(schedule.items()):
            amount = int(cost)
            rows += replacement_row(
                f"{short}Replacement",
                replacement_years=[year],
                unit_cost_won=amount,
                asset_lifetime_years=int(resource.lifetime),
                analysis_end_year=horizon_years,
            )
            lines.append(OneOffLine(
                tag=f"{short}Replacement",
                label=f"{short} 교체비",
                kind=ONE_OFF_REPLACEMENT,
                year=year,
                amount_won=amount,
                resource_name=resource.name,
                # ⚠ **물가 계수를 이 문면에 적지 않는다.** 자원의
                # `escalation_factor(year=)` 를 여기서 적으면 *그 계수가 이 금액에
                # 실렸다* 로 읽히는데, **실렸는지는 자원이 정한다.**
                #
                # R39 시점의 실측은 갈려 있었다 — `PV` 는 곱하고 `ESS` 는 곱하지
                # 않아, 계수를 적었다면 붙임 4 가 ESS 교체비에 대해 **거짓을
                # 인쇄했을** 것이다. **R40 이 `ESS` 쪽을 고쳐 지금은 둘 다
                # 곱한다.** 그렇다고 여기 적지 않는 이유는 바뀌지 않는다: 지금
                # 「둘 다 곱한다」로 적으면 그 문면은 **셋째 자원이 들어오는 날
                # 조용히 거짓이 된다**(자원마다 따로 정하는 값이므로 이 자리에서는
                # 확인할 수 없다). 어긋남을 붙드는 것은 검사 쪽이다 —
                # `tests/casegrid/test_lifecycle_wiring.py` 의 실효 래칫이
                # 「계수를 받고도 안 쓰는 자원」의 목록을 **행동으로** 잰다.
                formula=(
                    f"{year}년차 재취득 · 명목 {amount:,}원 · 단가와 물가 계수는 "
                    f"자원 산식({type(resource).__name__}.replacement_schedule)이 정한다"
                ),
            ))
        # 잔존가치는 **유입**이므로 비용 행에 음수로 담는다(위 독스트링).
        # ⚠ **여기서 뒤집지 않는다** — 명목액을 양수 그대로 넘기고 부호는
        # `salvage_row()` 가 뒤집는다(그쪽 독스트링의 「뒤집는 자리 하나」).
        salvage = int(resource.salvage_value(year=horizon_years))
        rows += salvage_row(
            f"{short}Salvage",
            label=f"{short} 잔존가치 ({horizon_years}년차)",
            salvage_year=horizon_years,
            salvage_won=salvage,
            asset_lifetime_years=int(resource.lifetime),
            analysis_end_year=horizon_years,
        )
        lines.append(OneOffLine(
            tag=f"{short}Salvage",
            label=f"{short} 잔존가치",
            kind=ONE_OFF_SALVAGE,
            year=horizon_years,
            amount_won=-salvage,
            resource_name=resource.name,
            formula=(
                f"분석 종료 {horizon_years}년차 · 수명 {int(resource.lifetime)}년 · "
                f"취득 시점부터 잔존 수명 비례 (`RC-ALL-C5`) · "
                f"교체 취득분 {len(schedule)}건 반영 · 명목 {salvage:,}원 유입"
            ),
        ))
    return rows, tuple(lines)
