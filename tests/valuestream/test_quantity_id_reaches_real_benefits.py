"""물량 표찰이 **실물 편익까지 닿는가** — `FR-402-AC1` · `FR-402-AC2.E` / R57.

## 이 파일이 닫는 것

R56 이 배타 판정에 **물리량 축**을 세웠고(`ValueStream.quantity_id`),
R57/WP-1 이 **몫**(`core/casegrid/ess_share.py::ESSShare`)에 그 표찰을 지웠다.
그런데 그 사이가 끊겨 있었다 — 구상 편익 다섯의 `__init__` 이
`super().__init__(name=…, enabled=…)` 만 부르고 **`quantity_id` 를 위로 넘기지
않았다.** 그래서 몫이 표찰을 들고 있어도 **그 몫의 편익에 실을 자리가 없었고**,
축은 `tests/valuestream/test_exclusion_quantity_axis.py` 의 **스텁**으로만
검증돼 있었다.

스텁이 재는 것은 *「판정이 표찰을 읽는가」* 이고, 이 파일이 재는 것은
*「**실물 편익이 표찰을 실어 나르는가**」* 다. 둘은 다른 것이며, 스텁만 있으면
배선이 끊긴 채로도 초록불이 난다.

## 붙드는 것 넷

    ① 다섯 편익이 받은 표찰을 그대로 들고 있다      배선이 닿았다
    ② 인자를 주지 않으면 다섯 다 `None` 이다        ★ 배포 경로 불변
    ③ 실물 둘(NWAs × PeakShaving = 유형 E)이
       서로 다른 표찰이면 정상 계상된다             ★★ 축이 실물에 섰다
    ④ 같은 표찰이면 거부 · 한쪽만 달아도 거부       ★★ 우회로가 없다

**②가 ①만큼 중요하다.** 기본값이 `None` 이 아니게 되는 순간 배포 경로의
배타 판정이 바뀌고, 그러면 결론축(`npv_won`)이 이 WP 때문에 움직인다. 어느
케이스도 아직 표찰을 주지 않으므로 다섯은 **전부 `None` 이어야** 한다.

**④의 「한쪽만」을 빼지 마라.** ③만 두면 *「한쪽 표찰만으로 규칙이 꺼지는」*
구현도 함께 통과하고, 그것은 배타 기계에 난 우회로다.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from core.contracts.validation import ValidationError
from core.contracts.valuestream import ValueStream
from core.valuestream.capacity_payment import CapacityPayment
from core.valuestream.exclusion_table import assert_no_exclusions, collect_exclusions
from core.valuestream.nwa import NWAs
from core.valuestream.peak_shaving import PeakShaving
from core.valuestream.self_consumption import SelfConsumption
from core.valuestream.tou_arbitrage import TouArbitrage

#: 이 WP 가 배선한 **구상 편익 다섯** — 태그 → 「나머지 인자는 채워 두고
#: `quantity_id` 만 받는」 생성기.
#:
#: 단가·수량은 **이 검사의 관심사가 아니다.** 값이 무엇이든 표찰의 운반 여부는
#: 같으므로, 생성자가 거부하지 않을 최소값만 채운다(음수 거부·12개월 길이 검사).
#: 그래도 다섯을 **실제로 세우는** 것이 요점이다 — 서명만 문자열로 훑으면
#: `super()` 에 넘기지 않은 구현이 그대로 통과한다.
_BENEFITS: dict[str, Callable[..., ValueStream]] = {
    "SelfConsumption": lambda **kw: SelfConsumption(
        baseline_annual_bill_won=1_200_000.0, new_annual_bill_won=900_000.0, **kw
    ),
    "TouArbitrage": lambda **kw: TouArbitrage(
        discharge_kwh=1_000.0,
        charge_kwh=1_100.0,
        peak_price_won_per_kwh=200.0,
        offpeak_price_won_per_kwh=70.0,
        **kw,
    ),
    "PeakShaving": lambda **kw: PeakShaving(
        monthly_peak_reduction_kw=[5.0] * PeakShaving.MONTHS,
        demand_charge_won_per_kw_month=8_320.0,
        **kw,
    ),
    "NWAs": lambda **kw: NWAs(contribution_price_won_per_kwh=60.0, **kw),
    "CP": lambda **kw: CapacityPayment(
        registered_capacity_kw=100.0, capacity_price_won_per_kw_month=7_000.0, **kw
    ),
}


# ── ① 다섯이 받은 표찰을 그대로 들고 있다 ────────────────────────────────

@pytest.mark.req("FR-402-AC1")
@pytest.mark.parametrize("tag", sorted(_BENEFITS))
def test_every_real_benefit_carries_the_quantity_id_it_is_given(tag: str) -> None:
    """**배선이 닿았다** — 생성자가 받은 표찰이 계약의 자리에 들어간다.

    받는 자리는 이미 `ValueStream.__init__` 에 있었다(R56). 없던 것은 구상
    편익이 그것을 **위로 넘기는 한 줄**이며, 넘기지 않아도 `TypeError` 조차
    나지 않았다 — 인자를 아예 받지 않았으므로 호출측이 표찰을 줄 수 없었을
    뿐이다. 그래서 이 단언은 **인스턴스에서 되읽어** 확인한다.
    """
    stream = _BENEFITS[tag](quantity_id="몫A가 방전한 kWh")

    assert stream.quantity_id == "몫A가 방전한 kWh", (
        f"{tag} 이 표찰을 위로 넘기지 않는다 — 몫이 표찰을 들고 있어도 "
        "그 몫의 편익에 실을 자리가 없다"
    )


# ── ② 주지 않으면 다섯 다 None (★ 배포 경로 불변) ────────────────────────

@pytest.mark.req("FR-402-AC1")
@pytest.mark.parametrize("tag", sorted(_BENEFITS))
def test_omitting_the_argument_leaves_the_benefit_unlabelled(tag: str) -> None:
    """★ **기본값은 `None` 이다** — 배포 경로의 판정이 이 WP 로 바뀌지 않는다.

    `None` 은 「없다」가 아니라 **「말하지 않았다」** 이고, 판정은 그것을
    보수적으로 「같을 수 있다」에 센다(`_same_quantity_is_possible`). 즉
    기본값이 `None` 인 한 배타 판정은 종전과 **정확히 같고**, 그래서 결론축
    (`npv_won`)이 움직이지 않는다.

    ⚠ 기본값을 `None` 이외로 두면 그 순간 배포 경로의 거부가 달라진다 —
    어느 케이스도 아직 표찰을 주지 않으므로 그 변화는 **아무 입력 변경 없이**
    일어나고, 골든 회귀가 깨지기 전까지는 보이지 않는다.
    """
    stream = _BENEFITS[tag]()

    assert stream.quantity_id is None, (
        f"{tag} 의 기본 표찰이 None 이 아니다 — 아무도 표찰을 주지 않았는데 "
        "배타 판정이 달라진다"
    )


# ── ③·④ 실물 둘로 세우는 물리량 축 (유형 E) ─────────────────────────────
#
# 오라클은 `docs/exclusion-rules.yaml` 의 `NWAs ↔ PeakShaving` 행 — 유형 `E`
# (*「방전 시점을 계통운영자가 정하면 사용자가 원하는 시각에 방전할 수 없다」*).
# 규칙표가 정본이므로 여기서 유형·근거를 다시 적지 않는다.
#
# ★ **유형 `E` 를 골랐다.** 이 축이 실제로 쓰일 자리가 «한 대의 ESS 를 용량
# 몫으로 갈라 몫마다 다른 역할을 주는 구성»(R52 §3 · R57/WP-1)이고, 그 구성이
# 걸리는 규칙이 바로 `E` 다 — 몫이 갈리면 방전하는 전력이 실제로 다르다.

_LABEL_GRID = "계통 급전 몫이 방전한 kWh"
_LABEL_USER = "사용자 운전 몫이 방전한 kWh"


def _grid_and_user_pair(
    *, grid_quantity: str | None, user_quantity: str | None
) -> list[ValueStream]:
    """유형 `E` 로 걸리는 **실물** 편익 둘 — 표찰만 갈아 끼운다.

    ⚠ `NWAs` 는 기본이 **비활성**이다(`enabled=False`). 배타 판정은 활성 편익만
    보므로(`collect_exclusions`) 켜지 않으면 이 검사 전체가 «걸릴 쌍이 없다» 로
    조용히 통과한다.
    """
    return [
        NWAs(
            contribution_price_won_per_kwh=60.0,
            enabled=True,
            quantity_id=grid_quantity,
        ),
        PeakShaving(
            monthly_peak_reduction_kw=[5.0] * PeakShaving.MONTHS,
            demand_charge_won_per_kw_month=8_320.0,
            enabled=True,
            quantity_id=user_quantity,
        ),
    ]


@pytest.mark.req("FR-402-AC1")
def test_two_real_benefits_with_different_quantities_are_counted_normally() -> None:
    """★★ **축이 실물에 섰다** — 몫이 갈리면 유형 `E` 조합도 정상 계상된다.

    `FR-402-AC1` 문면: *「동시 발생 효과는 중복이 아니다 — 지불 주체가 다르거나
    **물리량이 다르면 정상 계상한다**」*. 그리고 거부 메시지 자신이 *「용량을
    나누어 각 몫에 다른 역할을 맡기는 것은 허용됩니다」* 라고 처방한다
    (`exclusion_table.assert_no_exclusions`). 이 검사가 **그 처방을 실제로
    따를 수 있음**을 붙든다 — 스텁으로는 처방을 따를 수 없었다.

    ⚠ **거부되지 않는 데서 그치지 않고 감지 목록에서도 빠져야 한다.**
    `collect_exclusions` 는 리포트가 「배타제외」로 **표시**하는 근거이기도
    하다 — 정상 계상되는 쌍을 배타제외로 인쇄하면 검토자가 계상되지 않은
    편익을 찾게 된다.
    """
    streams = _grid_and_user_pair(
        grid_quantity=_LABEL_GRID, user_quantity=_LABEL_USER
    )

    assert collect_exclusions(streams) == [], (
        "몫이 갈려 물량이 다른데 실물 편익 쌍이 여전히 배타로 잡힌다 — "
        "FR-402-AC1 위반이며, 표찰이 편익까지 닿지 않았다는 뜻이다"
    )
    assert_no_exclusions(streams)  # 예외가 나면 안 된다


@pytest.mark.req("FR-402-AC2.E")
@pytest.mark.parametrize(
    ("grid_quantity", "user_quantity", "why"),
    [
        (_LABEL_GRID, _LABEL_GRID, "같은 표찰"),
        (_LABEL_GRID, None, "계통 쪽만 선언"),
        (None, _LABEL_USER, "사용자 쪽만 선언"),
    ],
)
def test_same_or_one_sided_labels_on_real_benefits_are_refused(
    grid_quantity: str | None, user_quantity: str | None, why: str
) -> None:
    """★★ **우회로가 없다** — 표찰을 달았다는 사실 자체는 통과 사유가 아니다.

    통과 사유는 **둘 다 선언하고 서로 다르다**는 것이다.

    - **같은 표찰**: 몫을 갈랐다고 적어 놓고 같은 전력을 주장하는 것이므로
      조항이 금지하는 바로 그 조합이다. R57/WP-1 의 `split_ess()` 도 같은
      근거로 몫 둘에 같은 `quantity_id` 를 주는 것을 거부한다
    - **한쪽만**: 다르다는 것을 **증명할 수 없다.** 통과시키면 어느 쌍이든
      한쪽에 이름 하나만 적어 거부를 지울 수 있다 — Q4(*「확인 못 했으면
      보수적으로 배타」*, 도메인 원칙 부록 A)의 반대다

    **양쪽 한쪽씩을 다 돌린다** — 한 방향만 검사하면 `benefit_a` 쪽만 보는
    구현이 통과한다.
    """
    streams = _grid_and_user_pair(
        grid_quantity=grid_quantity, user_quantity=user_quantity
    )

    assert collect_exclusions(streams), f"{why}인데 감지가 사라졌다"
    with pytest.raises(ValidationError) as caught:
        assert_no_exclusions(streams)
    assert caught.value.rule == "DV-12"
