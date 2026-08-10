"""Wave 0 스모크 검증 — 작업 1.10. **이것이 Wave 0 종료 조건이다.**

계약만 보고 자원 1종(PV)을 구현해 계약 테스트 스위트를 통과시킨다.
DoD: **다른 구획 코드 0줄로 통과.**

왜 `core/der/pv.py` 가 아니라 여기에 쓰는가
-------------------------------------------
진짜 PV는 WP-1의 산출물이고 Wave 1 작업이다(§16.3). Wave 0에서 `core/der/`
에 구현을 넣으면 다음 두 가지가 동시에 일어난다.

    ① WP-1의 소유 경로를 WP-0이 침범한다 (§16.1 W-1 파일 단위 배타 소유)
    ② 참조 구현이 "이미 있는 PV"로 취급되어, WP-1이 그것을 손보는 것으로
       작업을 시작한다 — 계약이 구현을 규정해야 하는데 순서가 뒤집힌다

여기서 검증하려는 것은 **PV가 맞게 계산되는가**가 아니라 **계약이 구현
가능한가**이다. 계약에 모순이 있거나 필요한 정보를 건네지 않으면 여기서
드러난다. 그것이 Wave 0이 답해야 할 유일한 질문이다.

이 파일은 WP-0 소유(`tests/contract/`)이며 배포 코드에 들어가지 않는다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.contracts.der import (
    DER,
    EOL_REPLACE,
    DispatchContext,
    DispatchResult,
)
from core.contracts.units import SECONDS_PER_HOUR, Money, to_won, won_sum
from tests.contract.test_der_contract import DERContractTests


class ReferencePV(DER):
    """계약만 보고 쓴 참조 구현.

    **`core` 안의 다른 구획을 하나도 import하지 않는다** — `core.contracts`
    뿐이다. 그것이 이 스모크가 증명하려는 바다 (FR-101-AC3 · NFR-208-AC1).
    """

    tag = "PV"

    #: FR-105-AC1 — 지원 운전 방법. 참조 구현이라 최소 2종만 둔다. **값을 갖는
    #: 이상 계약이 목록 소속을 검사하므로**, 목록 밖 문자열은 생성자에서 막힌다
    OPERATING_MODES = ("전량 자가소비", "잉여 판매")

    def __init__(
        self,
        *,
        name: str = "옥상PV",
        capacity_kw: float = 3.0,
        unit_capex_won_per_kw: int = 1_600_000,
        capacity_factor: float = 0.15,
        degradation_rate: float = 0.005,
        lifetime: int = 25,
        inverter_lifetime: int = 12,
        operating_mode: str = "잉여 판매",
        escalation_rate: float = 0.02,
        vat_rate: float = 0.1,
        end_of_life_action: str = EOL_REPLACE,
    ) -> None:
        super().__init__(
            name=name,
            dt=SECONDS_PER_HOUR,
            lifetime=lifetime,
            degradation_rate=degradation_rate,
            carries_electric=True,      # PV는 전기만 낸다
            carries_heat=False,
            carries_cool=False,
            consumes_fuel=False,
            operating_mode=operating_mode,
            escalation_rate=escalation_rate,
            end_of_life_action=end_of_life_action,
        )
        self.capacity_kw = capacity_kw
        self.unit_capex = unit_capex_won_per_kw
        self.capacity_factor = capacity_factor
        self.inverter_lifetime = inverter_lifetime
        self.vat_rate = vat_rate

    # ── 금액 — 전부 정수 원 (NFR-103) ───────────────────────────────
    def _gross_capex_won(self) -> float:
        return self.capacity_kw * self.unit_capex

    def capex(self, *, year: int) -> Money:
        # 초기 투자는 1년차에만. 이후 연도에 다시 계상하면 20년 동안
        # 25번 지은 사업이 된다. **부가세는 여기 넣지 않는다** (§13.2.2 C-1).
        return to_won(self._gross_capex_won()) if year == 1 else Money(0)

    def capex_vat(self, *, year: int) -> Money:
        """부가세액 — 본체와 **분리**해 계상한다 (§13.2.2 C-1).

        1년차에만 발생한다. `capex()` 가 0인 해에 세액이 남으면 없는 투자에
        세금이 붙는다.
        """
        if year != 1:
            return Money(0)
        return to_won(self._gross_capex_won() * self.vat_rate)

    def fixed_om(self, *, year: int) -> Money:
        # 설비 보유에 비례 — 발전량과 무관하다. 물가상승률은 계약이 주는
        # 계수 하나로 걸린다 (자원마다 기준연도를 다르게 잡지 않는다)
        base = self.capacity_kw * self.unit_capex * 0.01
        return to_won(base * self.escalation_factor(year=year))

    def variable_om(self, *, year: int) -> Money:
        return Money(0)  # PV는 변동 O&M이 실질적으로 없다

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """**인버터의 독립 수명을 표현한다** (FR-104-AC4).

        본체 25년만 보면 20년 분석에서 12년차 인버터 교체비가 통째로
        빠진다. 그 누락은 회수기간을 짧게 만들고 필요 지원액을 과소
        산정하게 하는데, 결과 화면에는 아무 표시도 남지 않는다.
        """
        # **교체는 수명 도달 *다음* 연도 초에 계상한다** (§13.2.2 C-4).
        #
        # 08-08 초판은 수명 연도(12년차)에 계상했다 — spec과 한 해 어긋났고,
        # WP-1a 가 자원을 구현하며 그 어긋남을 짚었다. 12년차에 넣으면
        # 12년 동안 쓴 설비의 교체비가 그 설비가 아직 살아 있는 해에
        # 잡히고, 20년 분석의 마지막 교체가 분석기간 안으로 잘못 들어올 수
        # 있다. **계약 쪽 참조 구현이 틀리면 자원 6종이 그것을 베낀다.**
        #
        # 같은 이유로 `retire`(FR-104-AC3)도 참조 구현이 먼저 보여야 한다 —
        # **사지 않기로 한 설비는 아무것도 교체하지 않는다.**
        if self.retires_at_end_of_life():
            return {}

        out: dict[int, Money] = {}
        year = self.inverter_lifetime + 1
        while year <= horizon:
            out[year] = to_won(self.capacity_kw * self.unit_capex * 0.15)
            year += self.inverter_lifetime
        return out

    def salvage_value(self, *, year: int) -> Money:
        """잔존 수명 비례 (FR-104-AC5). 분석기간을 넘겨 산 수명만 값이 된다."""
        remaining = self.lifetime - year
        if remaining <= 0:
            return Money(0)
        gross = self.capacity_kw * self.unit_capex
        return to_won(gross * remaining / self.lifetime)

    # ── 편익 (FR-401) ───────────────────────────────────────────────
    def value_streams(self) -> tuple[str, ...]:
        """PV는 자가소비 절감과 잉여 판매를 만든다 — **운전 방법에 따라 다르다.**

        전량 자가소비 모드에서 잉여 판매 편익을 함께 선언하면, 팔지 않은 전력이
        판매 수익으로 계상된다 (FR-402-AC2.A 동일 물리량 이중 판매).
        """
        if self.operating_mode == "전량 자가소비":
            return ("SelfConsumption",)
        return ("SelfConsumption", "SurplusSale")

    # ── 운전 ────────────────────────────────────────────────────────
    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        self.check_context(ctx)   # 해상도 불일치는 계약이 거부한다
        derate = (1.0 - self.degradation_rate) ** (int(ctx.year) - 1)
        # kW → 스텝당 kWh. 스텝 길이를 곱하지 않으면 15분 해상도에서 4배가 된다
        per_step = (self.capacity_kw * self.capacity_factor * derate
                    * ctx.hours_per_step)
        electric = [per_step] * ctx.steps
        # 플래그가 거짓인 매체는 0으로 둔다. 값을 실으면 어느 수지에도
        # 잡히지 않고 사라진다 (FR-101-AC4).
        return DispatchResult(
            electric=electric,
            heat=[0.0] * ctx.steps,
            cool=[0.0] * ctx.steps,
            fuel=[0.0] * ctx.steps,
        )


class TestReferencePVContract(DERContractTests):
    """계약 스위트를 **상속만으로** 통과시킨다.

    `make()` 하나만 채웠다. 자원마다 계약 검사를 손으로 다시 쓰지 않는다는
    것이 이 형태의 요점이며, 손으로 쓰면 반드시 빠진다.
    """

    def make(self) -> DER:
        return ReferencePV()


# ── Wave 0 종료 조건 ─────────────────────────────────────────────────

@pytest.mark.contract
@pytest.mark.req("FR-101-AC3")
def test_reference_impl_imports_only_contracts() -> None:
    """구현이 `core.contracts` 외의 `core` 하위를 참조하지 않는다.

    import-linter가 CI에서 같은 것을 보지만, 여기서 걸리면 **어느 자원이**
    원인인지 즉시 드러난다. 린터는 위반 사실을, 이 테스트는 위반 주체를
    알려 준다.
    """
    import inspect

    source = inspect.getsource(inspect.getmodule(ReferencePV))
    offending = [
        line.strip()
        for line in source.splitlines()
        if line.startswith(("import core", "from core"))
        and not line.startswith(("from core.contracts", "import core.contracts"))
    ]
    assert not offending, (
        f"참조 구현이 계약 밖 core 모듈을 import합니다: {offending}. "
        "Wave 0 DoD는 '다른 구획 코드 0줄로 통과'입니다"
    )


@pytest.mark.contract
@pytest.mark.req("FR-104-AC4")
def test_inverter_replacement_is_not_lost_in_20_year_horizon() -> None:
    """부속설비 독립 수명이 분석기간 안에서 실제로 계상된다.

    본체 수명(25년)만 보면 20년 분석에 교체가 하나도 없다. 인버터 12년을
    따로 보면 12년차에 한 번 있다. **이 차이가 회수기간을 바꾼다.**
    """
    pv = ReferencePV()
    schedule = pv.replacement_schedule(horizon=20)
    assert 13 in schedule, (
        "13년차 인버터 교체가 빠졌습니다. 본체 수명만 보고 있지 않은지 "
        "확인하십시오 (FR-104-AC4)"
    )
    assert 12 not in schedule, (
        "교체를 수명 연도(12년차)에 계상했습니다. §13.2.2 C-4 는 **수명 도달 "
        "다음 연도 초**를 규정합니다 — 12년차에 넣으면 아직 살아 있는 해에 "
        "교체비가 잡힙니다"
    )
    assert 25 not in schedule, "분석기간(20년) 밖의 교체가 들어 있습니다"


@pytest.mark.contract
@pytest.mark.req("NFR-103-M1")
def test_20_year_cashflow_sums_match_to_the_won() -> None:
    """20년 프로포마 합계 = 항목별 합계, **원 단위 완전 일치** (NFR-103-M1).

    참조 구현으로 실제 현금흐름을 만들어 확인한다. 단위 테스트가 아니라
    **계약이 이 항등식을 지킬 수 있는 형태인가**를 보는 것이다 — 금액
    메서드가 float를 돌려주는 계약이었다면 여기서 깨진다.
    """
    pv = ReferencePV()
    horizon = 20
    replacements = pv.replacement_schedule(horizon=horizon)

    # **부가세 행을 포함한다.** C-1 이 분리를 요구한 항목이므로 프로포마에도
    # 별도 행으로 서며, 항등식이 그 행을 빼고 성립하면 검사가 헛돈다.
    items = ("capex", "capex_vat", "fixed_om", "variable_om")

    per_year: list[Money] = []
    for year in range(1, horizon + 1):
        per_year.append(
            won_sum([
                *(getattr(pv, m)(year=year) for m in items),
                replacements.get(year, Money(0)),
            ])
        )

    by_item = won_sum(replacements.values())
    for method in items:
        by_item += won_sum(
            [getattr(pv, method)(year=y) for y in range(1, horizon + 1)]
        )

    assert sum(per_year, Decimal(0)) == by_item, (
        "연도별 합계와 항목별 합계가 어긋납니다 — NFR-103-M1 위반"
    )


@pytest.mark.contract
@pytest.mark.req("FR-101-AC4")
def test_degradation_reduces_output_year_over_year() -> None:
    """열화가 실제로 걸린다 — 연도를 건네는 계약이 쓸모 있음을 확인한다.

    `dispatch(ctx)` 가 연도를 받지 않는 계약이었다면 열화를 표현할 수 없고,
    20년 발전량이 1년차 값으로 고정된다. 그 오류는 편익을 과대 계상한다.
    """
    pv = ReferencePV()
    y1 = pv.dispatch(DispatchContext(steps=24, dt=3600, year=1))
    y20 = pv.dispatch(DispatchContext(steps=24, dt=3600, year=20))
    assert sum(y20.electric) < sum(y1.electric)
