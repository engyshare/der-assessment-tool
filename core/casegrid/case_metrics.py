"""지표 조립 — `core/casegrid/e2e_runner.py` 에서 R57/WP-9 가 옮겼다.

`ess_build.py`(R57/WP-5) · `pv_allocation.py`(R51/WP-5) · `grid_support.py`
(R51/WP-7) 와 **같은 사유로 뗀 것이다.** 그 파일이 `NFR-206` 코드 줄
상한(500)에 닿아 있었다 — 옮기기 직전 실측이 **코드 496/500**, 곧 **여유
4줄**이었다. R57 이 한 라운드에 이 자리를 **두 번** 만났다: WP-5 가 낸 여유
18줄을 WP-6 의 몫 배선이 거의 다 썼다.

⚠ **이 자리를 쓸 사람은 이 라운드에 없다.** 그래도 지금 내는 이유는 다음
라운드가 「자리 내기 → 배선」 사슬을 통째로 지지 않게 하는 것이다.

**행동은 한 원도 바뀌지 않았다.** 두 함수를 독스트링·주석째로 옮기고 이름의
밑줄만 뗐을 뿐이며, 같은 인자로 같은 수가 나온다. 그것을 재는 것은 골든
3건(`tests/golden/test_regression_scenarios.py`)의 `npv_won` **정확
일치**다.

## 왜 공개 이름인가 — 밑줄을 뗐다

`e2e_runner.py` 가 모듈 **밖에서** 부르므로 밑줄로 시작하는 비공개 이름으로
두면 `ruff` 규약과 어긋난다 — 그래서 종전의 밑줄을 뗐다. 옛 이름을 가리키던
문면 넷(`perspectives.py` 셋 · `tests/golden/test_regression_scenarios.py`
하나)은 **지우지 않고 새 자리·새 이름을 가리키게 고쳤다** — 문면을 지워
검사를 통과시키는 것은 이 저장소가 반복해 적은 함정이다.

## ⚠ 함께 오지 않은 것 — 이 이동의 경계

`_resource_lines` · `_with_model_generation` · `_site_load_kw` ·
`_household_load_if_total_given` · `_rec` 는 러너에 그대로 있다. 특히
`_resource_lines` 는 **밖에서 `from core.casegrid.e2e_runner import ...` 로
쓰는 곳이 있다**(`core/casegrid/operating_lines.py` 머리말). 그것까지 함께
옮기면 이 WP 가 「자리 옮김」이 아니게 되고, 골든이 움직였을 때 원인이
여럿이 된다.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from core.cba.metrics import npv, payback_discounted
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money


def metrics_for(
    initial_investment: Money,
    operating: list[CashFlowRow],
    discount_rate: float,
) -> dict[str, float]:
    """지표 사전 하나 — **케이스와 변형이 같은 함수를 쓴다.**

    갈라 두면 한쪽에 지표가 추가될 때 다른 쪽이 따라오지 않고, 그 상태에서
    `build_variant_table()` 은 「변형마다 지표가 다릅니다」로 거부한다 —
    즉 증상이 **표시 층에서** 나타나 원인을 여기까지 되짚어야 한다.

    ★ **초기지출을 함께 싣는다 (R33).** 지표가 둘뿐일 때 리포트는 *「무지원과
    입력 지원안의 NPV 가 이만큼 다르다」* 까지만 말할 수 있고 **「얼마를 덜
    냈기에 그런가」** 를 말할 수 없었다 — 변형별 초기지출이 경계를 넘지
    않았기 때문이다. `MC-1` 이 재는 것이 정확히 그 「왜」이므로 여기서 싣는다.
    지표가 아니라 대입값이지만, 변형마다 **다른** 값이고 변형별로 담을 자리는
    여기뿐이다(`CaseBasis` 는 케이스 하나에 하나다).
    """
    return {
        "npv": float(npv(initial_investment, operating, discount_rate=discount_rate)),
        "payback_years": payback_discounted(
            initial_investment, operating, discount_rate=discount_rate
        ),
        "initial_outlay_won": float(initial_investment),
    }


def initial_outlay(rows: Sequence[CashFlowRow]) -> Money:
    """지원 현금흐름 행을 **`t=0` 초기투자 한 수로** 접는다.

    행의 금액은 유출이므로 음수다(`{1: -자부담}`). `npv()` 의 첫 인자는 *「t=0 에
    나가는 비용(양수)」* 이라 부호를 뒤집는다.

    ⚠ **행이 비어 있으면 0원이다.** 그것은 「지출이 없는 사업」이 아니라
    `FR-611-AC4` 의 **「해당 설비를 제외한 케이스」**다 — 지원 예정(미확정)분이
    무산됐을 때의 병기 케이스이며, 그 경우 설비가 없으므로 CAPEX 행도 없다
    (`build_baseline_capex_cashflows` 가 그렇게 판정한다).
    """
    total = sum(
        (amount for row in rows for amount in row.amounts.values()), Decimal(0)
    )
    return Money(-total)
