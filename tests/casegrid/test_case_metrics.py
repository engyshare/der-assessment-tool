"""지표 조립이 옮겨 온 자리 — `core/casegrid/case_metrics.py` / R57/WP-9.

R57/WP-9 가 `core/casegrid/e2e_runner.py`(코드 **496/500** · 여유 4줄)에서
`metrics_for`·`initial_outlay` 를 `core/casegrid/case_metrics.py` 로 옮겼다.
다음 라운드의 배선이 들어갈 자리를 내기 위해서였다.

## 이 파일이 재는 것 둘 — **옮긴 코드를 다시 적지 않는다**

    ① ★ `initial_outlay` 는 **부호를 뒤집는다**       빈 행은 0원이다
    ② ★★ `metrics_for` 의 **키가 셋이고 입력이 달라도 같다**

**①이 조용히 틀릴 수 있는 자리다.** 행의 금액은 유출이라 음수인데
(`{1: -자부담}`) `npv()` 의 첫 인자는 *「t=0 에 나가는 비용(양수)」* 이다.
부호를 안 뒤집으면 초기투자가 음수가 되어 **NPV 가 초기지출만큼 커진다** —
예외는 나지 않고 수만 틀린다. ⚠ **빈 행 갈래를 함께 둔다**: 그것은 「지출이
없는 사업」이 아니라 `FR-611-AC4` 의 「해당 설비를 제외한 케이스」다.

**②는 표시 층까지 가서야 드러나는 것을 여기서 잡는다.** 키가 갈리면
`build_variant_table()` 이 「변형마다 지표가 다릅니다」로 **거부**하고
(`core/report/variant_report.py::_shared_metric_names`), 사람은 그 증상에서
여기까지 되짚어야 한다. 케이스 지표와 변형 지표가 **같은 함수**를 쓰는 것이
그 거부를 막는 장치이므로, 서로 다른 입력에 대해 키가 같은지를 잰다.

⚠ **금액 오라클을 두지 않는다.** 이 조립이 옳은 수를 내는가는 골든 3건
(`tests/golden/test_regression_scenarios.py`)이 `npv_won` **정확 일치**로
잰다. 여기서 또 두면 같은 수의 출처가 둘이 된다.

⚠ **`req` 마커를 달지 않았다.** 이 둘은 옮겨 온 조립의 기계적 성질을 재는
것이지 조항의 인수 조건을 끝까지 재지 않는다 — `FR-611-AC4` 의 병기 케이스
「산출」은 `tests/incentive/test_incentive.py` 가 재고, `FR-607-AC1` 의 변형
축은 `tests/casegrid/test_variant_production_wiring.py` 가 잰다. 본문이 재지
않는 조항에 마커를 달면 추적표가 실물보다 후해진다.
"""

from __future__ import annotations

from decimal import Decimal

from core.casegrid.case_metrics import initial_outlay, metrics_for
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money

#: 운영 현금흐름 탐침값. **골든의 사본이 아니다** — 이 파일은 금액을 재지
#: 않으므로 대장과 같을 필요가 없고, 같게 두면 대장이 바뀔 때 여기가 따라오지
#: 않아도 아무 일이 없다(탐침값 규약).
_OPERATING = [
    CashFlowRow(label="편익", amounts={1: Decimal(3_000_000), 2: Decimal(3_000_000)}),
]


# ── ① ★ 부호를 뒤집는다 · 빈 행은 0원 ──────────────────────────────────

def test_initial_outlay_flips_the_sign_of_the_outflow_rows() -> None:
    """★ **유출(음수) 행이 t=0 비용(양수)이 된다** — 안 뒤집으면 수만 틀린다.

    `npv()` 의 첫 인자는 *「t=0 에 나가는 비용(양수)」* 이고 지원 현금흐름
    행은 유출이라 음수다(`{1: -자부담}`). 부호가 살아 있으면 초기투자가
    음수가 되어 NPV 가 그만큼 **커지고**, 예외는 나지 않는다.

    ⚠ **행 여럿·연도 여럿을 함께 둔다** — 첫 행의 1년차만 읽는 구현도
    한 행짜리 사례에서는 초록불이 된다.
    """
    rows = [
        CashFlowRow(label="자부담", amounts={1: Decimal(-5_000_000)}),
        CashFlowRow(label="추가 자부담", amounts={1: Decimal(-1_000_000), 2: Decimal(-250_000)}),
    ]

    assert initial_outlay(rows) == Money(6_250_000)


def test_initial_outlay_of_no_rows_is_zero_won() -> None:
    """★ **빈 행은 0원이다** — `FR-611-AC4` 의 「해당 설비를 제외한 케이스」.

    지원 예정(미확정)분이 무산됐을 때의 병기 케이스이며, 그 경우 설비가
    없으므로 CAPEX 행도 없다. 여기서 예외를 내거나 `None` 을 내놓으면 그
    케이스가 **실행 자체를 못 한다** — 0원이어야 한다.
    """
    assert initial_outlay([]) == Money(0)


# ── ② ★★ 키가 셋이고 입력이 달라도 같다 ────────────────────────────────

#: 케이스 지표와 변형 지표가 함께 갖는 이름. 하나라도 갈리면
#: `build_variant_table()` 이 표시 층에서 거부한다.
_METRIC_KEYS = frozenset({"npv", "payback_years", "initial_outlay_won"})


def test_metrics_for_yields_the_same_three_keys_for_any_input() -> None:
    """★★ **키가 셋이고, 초기투자가 달라도 그대로다.**

    `initial_outlay_won` 이 빠지면 리포트는 *「무지원과 입력 지원안의 NPV 가
    이만큼 다르다」* 까지만 말하고 **「얼마를 덜 냈기에 그런가」** 를 말할 수
    없다(R33 · `MC-1` 이 재는 것이 정확히 그 「왜」다).

    ⚠ **입력 둘을 둔다** — 케이스 지표(총사업비)와 변형 지표(그 변형의 실제
    초기 지출)가 **같은 함수**를 쓰는 것이 키가 갈리지 않게 하는 장치다.
    한쪽만 재면 입력에 따라 키를 달리 내놓는 구현도 초록불이 된다.

    ⚠ **금액은 재지 않는다** — 골든 3건이 그 수를 갖는다.
    """
    case_metrics = metrics_for(Money(20_000_000), _OPERATING, 0.045)
    variant_metrics = metrics_for(initial_outlay([]), _OPERATING, 0.045)

    assert frozenset(case_metrics) == _METRIC_KEYS
    assert frozenset(variant_metrics) == _METRIC_KEYS
