"""비에너지 공통설비 구현 — 구획 WP-1f / spec FR-106 · §13.2.3 `RC-CA-*`.

CEMS·HEMS·공용 계량통신 설비는 **발전하지도 소비하지도 않는다.** 그래서
`DER` 이 아니라 `core.contracts.asset.CommonAsset` 을 구현하며, 이 파일에는
`dispatch()` 도 매체 플래그도 없다 (FR-106-AC1). 대신 비용 쪽에서 두 가지가
`DER` 과 다르다.

    1) **SW/HW 분리 계상** (AC3) — 감가상각 내용연수와 교체 주기가 다르다.
       SW는 재개발, HW는 교체이므로 교체비 비율도 잔존가치도 따로 간다.
    2) **안분** (AC5) — 공통비용을 가구에 나눠 실어야 한다. 나눗셈이므로
       원 단위 반올림에서 반드시 잔차가 생기고, 방치하면 "가구별 합계 ≠
       단지 총계"가 되어 리포트 신뢰를 잃는다 (NFR-103).

**안분 잔차 규약 (이 파일의 핵심).**
    각 가구 몫을 `to_won()` 으로 반올림한 뒤, 원액과의 차이를 **최종 가구**
    (`RESIDUAL_HOLDER_INDEX = -1`)에 전부 가산한다. 어느 가구가 잔차를
    받는지 정해 두지 않으면 실행마다·정렬 순서마다 결과가 달라져 재현성이
    깨진다. 최종 가구를 택한 이유는 규약이 **한 줄로 검증 가능**하기
    때문이다 — "마지막을 제외한 전 가구는 `round(총액/n)`" 이 성립하는지만
    보면 되고, 잔차를 여러 가구에 흩뿌리는 방식(최대잔여법 등)처럼 배분
    순서를 다시 규약으로 정할 필요가 없다. 잔차 크기는 항상 `가구 수/2`원
    미만이므로 특정 가구가 유의미하게 손해 보지도 않는다.

    비용 계상 대상이 될 수 없을 만큼 작은 총액(가구 수 제곱 수준 이하)에서는
    최종 가구 몫이 음수가 될 수 있다. 그 경우에도 **합계 보존은 유지**되며,
    이는 규약이 지키기로 한 유일한 불변식이다(§13.2.3 `RC-CA-A1`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar, Final

from core.contracts.asset import AllocationResult, AllocationRule, CommonAsset
from core.contracts.units import ZERO, Money, Year, to_won, won_sum

#: 안분 잔차를 받는 가구의 인덱스. **-1(최종 가구)로 고정한다** — 상수로 두는
#: 이유는 테스트와 리포트 설명이 같은 값을 참조하게 하기 위해서다.
RESIDUAL_HOLDER_INDEX: Final[int] = -1

#: 가구 프로포마 행 구분 (FR-106-AC6). 안분 공통비용은 가구 자체 설비 비용과
#: **다른 행**으로 나가야 한다 — 합치면 가구 부담액의 근거를 되짚을 수 없다.
OWN_COST_ROW: Final[str] = "가구 자체 설비"
COMMON_COST_ROW: Final[str] = "안분 공통비용"

MoneyLike = Money | Decimal | int


# ── 입력 검증 헬퍼 ───────────────────────────────────────────────────

def _non_negative_money(label: str, value: MoneyLike) -> Money:
    """금액을 원 단위로 정규화한다. 음수 비용은 거부한다.

    허용하면 편익을 비용 항목에 음수로 밀어 넣는 우회로가 생기고, 그 순간
    비용측 합계가 실제 지출과 달라진다 (도메인 원칙 1-2 기준선 분리).
    """
    amount = to_won(value)
    if amount < 0:
        raise ValueError(f"{label} 은 음수일 수 없습니다: {amount}")
    return amount


def _fraction(label: str, value: float, *, upper: float = 1.0) -> Decimal:
    """비율을 소수(0~1)로 검사한다 (§7.5 — 코드 내부는 소수로 정규화).

    2%를 `2.0` 으로 넣으면 20년 뒤 결과가 그럴듯하면서 완전히 틀린다.
    """
    if not 0.0 <= value < upper:
        raise ValueError(
            f"{label} 는 0~{upper} 소수입니다: {value}. 2%는 0.02 입니다 (§7.5 비율)"
        )
    return Decimal(str(value))


def _ratio(label: str, value: float) -> Decimal:
    """교체비 비율. 1.0(=취득가 전액)을 넘을 수 있으므로 상한을 두지 않는다."""
    if value < 0.0:
        raise ValueError(f"{label} 는 0 이상입니다: {value}")
    return Decimal(str(value))


def _checked_year(year: int) -> int:
    """분석 연도는 1-base다. 0-base 인덱스가 새어 들면 잔존가치가 한 해 밀린다."""
    return int(Year(year))


# ── 표준 공통설비 구현 ───────────────────────────────────────────────

class StandardCommonAsset(CommonAsset):
    """정액 SW/HW 비용 + 물가연동 운영비를 갖는 공통설비 표준 구현.

    기본 제공 유형 3종(FR-106-AC2)이 공유하는 계산은 전부 여기 있다. 유형별
    차이는 `tag` · `display_name` · `scope` 뿐이다 — 계산이 같은데 클래스를
    나눈 이유는 리포트와 케이스 그리드에서 **유형을 지칭할 수 있어야** 하기
    때문이다 (FR-103 인스턴스 구분과 같은 취지).

    **기본값을 주지 않는다** (FR-106-AC7 "기본값 없음"). 비용·수명·물가를
    잊으면 인스턴스화가 실패한다. 기본값이 있으면 잊힌 비용이 0원으로
    계상되고, 회수기간이 짧게 나오는데 화면상으로는 정상으로 보인다.
    """

    tag: ClassVar[str]
    #: 리포트 표시명. `tag` 는 레지스트리 키이므로 ASCII 로 두고 한국어는 여기 둔다
    display_name: ClassVar[str]
    #: 설비가 놓이는 층위 — "단지" 또는 "가구" (FR-106-AC2의 괄호 설명)
    scope: ClassVar[str]

    def __init__(
        self,
        *,
        name: str,
        capex_sw: MoneyLike,
        capex_hw: MoneyLike,
        fixed_om_annual: MoneyLike,
        lifetime_sw: int,
        lifetime_hw: int,
        escalation_rate: float,
        sw_redevelopment_ratio: float = 1.0,
        hw_replacement_ratio: float = 1.0,
        vat_rate: float = 0.0,
        allocation: AllocationRule = AllocationRule.EQUAL_PER_HOUSEHOLD,
    ) -> None:
        super().__init__(
            name=name,
            lifetime_sw=lifetime_sw,
            lifetime_hw=lifetime_hw,
            allocation=allocation,
            escalation_rate=escalation_rate,
        )
        self.capex_sw = _non_negative_money("capex_sw", capex_sw)
        self.capex_hw = _non_negative_money("capex_hw", capex_hw)
        self.fixed_om_annual = _non_negative_money("fixed_om_annual", fixed_om_annual)
        self._sw_ratio = _ratio("sw_redevelopment_ratio", sw_redevelopment_ratio)
        self._hw_ratio = _ratio("hw_replacement_ratio", hw_replacement_ratio)
        self._vat = _fraction("vat_rate", vat_rate)

    # ── CAPEX (FR-106-AC3) ──────────────────────────────────────────
    # 초기 투자는 1년차에만 발생한다. 2년차 이후에도 돌려주면 20년 분석에서 CAPEX가
    # 20배로 계상되는데, 총액만 보면 규모가 커 보일 뿐이라 눈에 잘 띄지 않는다.
    # 교체는 `replacement_schedule()` 이 따로 담는다.

    def capex_software(self, *, year: int) -> Money:
        """소프트웨어 개발비 (원)."""
        return self.capex_sw if _checked_year(year) == 1 else ZERO

    def capex_hardware(self, *, year: int) -> Money:
        """하드웨어 구축비 (원)."""
        return self.capex_hw if _checked_year(year) == 1 else ZERO

    def capex_vat(self, *, year: int) -> Money:
        """부가가치세 (원). **`capex()` 에 섞지 않는다** (§13.2.2 C-1).

        합쳐 두면 매입세액 환급 가정이 바뀔 때 어느 금액을 빼야 할지 알 수 없다.
        """
        return to_won(Decimal(self.capex(year=year)) * self._vat)

    # ── 운영비 (FR-106-AC4) ─────────────────────────────────────────

    def fixed_om(self, *, year: int) -> Money:
        """연간 운영비 (원/년) — 라이선스·클라우드·유지보수·관제 인건비.

        `A × (1+i)^(연차-1)`. 1년차가 기준연도 명목가다. 물가를 적용하지
        않으면 20년 누계가 A×20에 그쳐, i=2%에서 21.5%가 사라진다
        (§13.2.2 C-2: A=100,000·i=0.02·n=20 → 2,429,737원).
        """
        return to_won(
            Decimal(self.fixed_om_annual)
            * Decimal(str(self.escalation_factor(year=_checked_year(year))))
        )

    # ── 교체·잔존가치 (FR-106-AC3) ──────────────────────────────────

    @property
    def sw_replacement_cost(self) -> Money:
        """SW 재개발비. 전면 신규개발보다 싼 경우가 많아 비율로 조정한다."""
        return to_won(Decimal(self.capex_sw) * self._sw_ratio)

    @property
    def hw_replacement_cost(self) -> Money:
        """HW 교체비."""
        return to_won(Decimal(self.capex_hw) * self._hw_ratio)

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """{교체 연도: 교체비}. SW 재개발과 HW 교체를 **각각** 반영한다.

        수명 도달 **다음 연도 초**에 계상한다 (§13.2.2 C-4 — 인버터 12년이면
        13년차). 같은 해에 SW·HW가 겹치면 **합산**한다. 덮어쓰면 한쪽 교체비가
        통째로 사라지는데, 그 해 현금흐름만 보면 정상처럼 보인다.
        """
        if horizon < 1:
            raise ValueError(f"분석기간은 1년 이상입니다: {horizon}")

        schedule: dict[int, Money] = {}
        for lifetime, unit_cost in (
            (self.lifetime_sw, self.sw_replacement_cost),
            (self.lifetime_hw, self.hw_replacement_cost),
        ):
            if unit_cost == 0:
                # 0원 교체 항목을 남기면 "교체가 필요 없다"와 구분되지 않는다.
                continue
            year = lifetime + 1
            while year <= horizon:
                schedule[year] = won_sum([schedule.get(year, ZERO), unit_cost])
                year += lifetime
        return dict(sorted(schedule.items()))

    def _salvage(self, *, initial: Money, replacement: Money, lifetime: int, year: int) -> Money:
        """`취득가 × 잔존수명 / 총수명` (§13.2.2 C-5).

        **현재 설치돼 있는 개체의 취득가**를 쓴다. 교체된 개체는 재개발·교체비로
        취득한 것이므로 초기 CAPEX를 쓰면 잔존가치가 실제와 어긋난다.

        할인은 하지 않는다 — 할인율은 재무 계층의 파라미터이고, 자원이 할인까지
        하면 CBA에서 같은 금액이 두 번 할인된다.
        """
        y = _checked_year(year)
        installed_at = 1 + lifetime * ((y - 1) // lifetime)
        used = y - installed_at + 1
        remaining = max(lifetime - used, 0)
        acquisition = initial if installed_at == 1 else replacement
        return to_won(Decimal(acquisition) * remaining / lifetime)

    def salvage_software(self, *, year: int) -> Money:
        return self._salvage(
            initial=self.capex_sw,
            replacement=self.sw_replacement_cost,
            lifetime=self.lifetime_sw,
            year=year,
        )

    def salvage_hardware(self, *, year: int) -> Money:
        return self._salvage(
            initial=self.capex_hw,
            replacement=self.hw_replacement_cost,
            lifetime=self.lifetime_hw,
            year=year,
        )

    # `salvage_value()` 는 **덮어쓰지 않는다.** 계약이 `SW + HW` 로 확정했다
    # (v1.1 개정 ②) — 합계 규칙이 설비마다 달라지면 AC3 분리 계상의 의미가
    # 사라진다. v1.0 계약은 합계만 요구하고 분리를 요구하지 않았으므로
    # 이 파일이 `salvage_software`·`salvage_hardware` 를 스스로 만들었다.


class CEMS(StandardCommonAsset):
    """단지 통합 제어·모니터링 시스템 (FR-106-AC2).

    원 요구사항의 *"개별 주택 자원(HEMS 등)의 통합 모니터링 및 단지 제어"* 가
    이 클래스다. 10~20가구 실증에서 개발·구축비와 연간 운영비가 무시할 수 없다.
    """

    tag: ClassVar[str] = "CEMS"
    display_name: ClassVar[str] = "CEMS"
    scope: ClassVar[str] = "단지"


class HEMS(StandardCommonAsset):
    """가구 단위 에너지관리 시스템 (FR-106-AC2)."""

    tag: ClassVar[str] = "HEMS"
    display_name: ClassVar[str] = "HEMS"
    scope: ClassVar[str] = "가구"


class MeteringComm(StandardCommonAsset):
    """공용 계량·통신 설비 (FR-106-AC2).

    `tag` 는 레지스트리 키이자 파일·케이스 ID에 쓰이므로 ASCII 로 둔다.
    한국어 표시명은 `display_name` 이 갖는다.
    """

    tag: ClassVar[str] = "MeteringComm"
    display_name: ClassVar[str] = "공용 계량·통신 설비"
    scope: ClassVar[str] = "단지"


#: 기본 제공 유형 3종 (FR-106-AC2). NFR-106 케이스 순회가 이 순서를 그대로 쓴다.
COMMON_ASSET_TYPES: Final[tuple[type[StandardCommonAsset], ...]] = (CEMS, HEMS, MeteringComm)


# ── 안분 (FR-106-AC5) ────────────────────────────────────────────────
#
# `AllocationResult` 는 **계약이 소유한다** (`core.contracts.asset`, v1.1 개정 ③).
# 안분 결과는 프로포마(WP-7)와 리포트(WP-10)가 읽는 **구획 경계 자료구조**이므로
# §16.2 「데이터 스키마」에 해당한다. v1.0 에서는 이 파일이 형(型)까지 소유해서,
# 형을 고치려면 WP-7·WP-10 이 남의 구획 파일을 건드려야 했다.
#
# **배분 알고리즘은 이 파일이 소유한다** — 가중치 계산과 잔차 규약은 구현이며
# 계약이 아니다. 계약은 「합계가 보존된다」만 요구하고, 어느 가구가 잔차를
# 받는지는 여기서 정한다.


def _capacity_weights(capacities: Sequence[float] | None, households: int) -> list[Decimal]:
    """설비용량 비례 안분의 가중치.

    용량을 받지 못했는데 균등으로 조용히 되돌아가면, 리포트에는 "용량 비례"라고
    적히고 실제로는 균등 배분된 값이 나간다. 그래서 오류로 중단한다.
    """
    if capacities is None:
        raise ValueError(
            "설비용량 비례 안분에는 가구별 용량이 필요합니다 (capacities). "
            "지정하지 않으면 규칙 표기와 실제 배분이 어긋납니다"
        )
    if len(capacities) != households:
        raise ValueError(
            f"가구별 용량 개수가 가구 수와 다릅니다: {len(capacities)}개, 기대 {households}개"
        )
    weights = []
    for i, c in enumerate(capacities):
        if c < 0:
            raise ValueError(f"{i + 1}번째 가구의 설비용량이 음수입니다: {c}")
        weights.append(Decimal(str(c)))
    if sum(weights) <= 0:
        raise ValueError(
            "설비용량 합계가 0입니다. 용량 비례 안분은 0으로 나누게 되므로 "
            "다른 안분 규칙을 지정하십시오"
        )
    return weights


def _split_with_residual(total: Money, weights: Sequence[Decimal]) -> tuple[Money, ...]:
    """가중치대로 나누고 **반올림 잔차를 최종 가구에 가산**한다.

    모듈 docstring의 잔차 규약을 수행하는 곳이다. 각 몫은 `to_won()` 한 곳에서만
    반올림되며(NFR-103 경계 정의), 잔차는 원액에서 반올림된 몫의 합을 뺀 값이므로
    **결과 합계는 정의상 원액과 정확히 같다.**
    """
    weight_total = sum(weights, Decimal(0))
    amount = Decimal(total)
    shares = [to_won(amount * w / weight_total) for w in weights]
    residual = amount - sum(shares, Decimal(0))
    shares[RESIDUAL_HOLDER_INDEX] = Money(Decimal(shares[RESIDUAL_HOLDER_INDEX]) + residual)
    return tuple(shares)


def allocate(
    total: MoneyLike,
    *,
    rule: AllocationRule,
    households: int,
    capacities: Sequence[float] | None = None,
) -> AllocationResult:
    """공통비용을 가구에 안분한다 (FR-106-AC5).

    §13.2.3 `RC-CA-A1`: 20,000,000원 / 15가구 → 가구당 1,333,333원이고 단순
    합계는 19,999,995원으로 원액과 5원 어긋난다. 잔차 5원은 규약대로 최종
    가구에 가산되어 합계가 정확히 20,000,000원이 된다.
    """
    amount = to_won(total)
    if households < 1:
        raise ValueError(f"가구 수는 1 이상입니다: {households}")

    if rule is AllocationRule.NO_ALLOCATION:
        # 가구 행은 0원으로 **남긴다**. 행을 지우면 "안분하지 않기로 했다"와
        # "공통설비가 없다"가 리포트에서 구분되지 않는다.
        return AllocationResult(
            rule=rule,
            source_total=amount,
            per_household=tuple([ZERO] * households),
            unallocated=amount,
        )

    if rule is AllocationRule.EQUAL_PER_HOUSEHOLD:
        weights = [Decimal(1)] * households
    elif rule is AllocationRule.BY_CAPACITY:
        weights = _capacity_weights(capacities, households)
    else:  # pragma: no cover - StrEnum 확장 시의 방어
        raise ValueError(f"알 수 없는 안분 규칙입니다: {rule!r}")

    return AllocationResult(
        rule=rule,
        source_total=amount,
        per_household=_split_with_residual(amount, weights),
        unallocated=ZERO,
    )


def annual_cost(asset: CommonAsset, *, year: int, horizon: int) -> Money:
    """해당 연차에 발생하는 공통설비 비용 (원) — CAPEX + 고정 O&M + 교체비.

    잔존가치는 넣지 않는다 — 분석 종료 시점의 **회수 항목**이므로 비용 흐름에
    음수로 섞으면 연차별 비용 행이 실제 지출과 달라진다.
    """
    schedule = asset.replacement_schedule(horizon=horizon)
    return won_sum([
        asset.capex(year=year),
        asset.fixed_om(year=year),
        schedule.get(year, ZERO),
    ])


def allocate_assets(
    assets: Sequence[CommonAsset],
    *,
    year: int,
    horizon: int,
    households: int,
    capacities: Sequence[float] | None = None,
) -> dict[str, AllocationResult]:
    """공통설비별 연차 비용을 각자의 안분 규칙으로 배분한다.

    **공통설비가 없으면 빈 dict를 돌려주고 안분 로직을 부르지 않는다**
    (FR-106-AC7 — 단독주택 모델). 부재를 "총액 0원 안분"으로 처리하면 가구
    수가 0인 모델에서 0으로 나누기가 나거나, 있지도 않은 0원 행이 리포트에
    남는다.
    """
    results: dict[str, AllocationResult] = {}
    for asset in assets:
        if asset.name in results:
            raise ValueError(
                f"공통설비 이름이 중복됩니다: {asset.name!r}. 이름이 겹치면 한쪽 "
                "안분 결과가 조용히 덮여 비용이 사라집니다 (FR-103)"
            )
        results[asset.name] = allocate(
            annual_cost(asset, year=year, horizon=horizon),
            rule=asset.allocation,
            households=households,
            capacities=capacities,
        )
    return results


# ── 가구 프로포마 (FR-106-AC6) ───────────────────────────────────────

@dataclass(frozen=True)
class ProformaRow:
    """가구 프로포마의 비용 한 행."""

    label: str
    category: str
    amount: Money
    #: 공통비용 행에만 붙는다. 규칙 없는 부담액은 해석할 수 없다 (AC5)
    rule: AllocationRule | None = None


def household_proforma_rows(
    *,
    own_costs: Mapping[str, MoneyLike],
    allocations: Mapping[str, AllocationResult],
    household_index: int,
) -> list[ProformaRow]:
    """한 가구의 비용 행 목록. 안분 공통비용을 **별도 행**으로 낸다 (AC6).

    자체 설비 비용에 합산해 버리면 가구 부담액이 왜 그 값인지 되짚을 수 없고,
    안분 규칙을 바꿨을 때 무엇이 달라졌는지도 보이지 않는다.
    """
    rows = [
        ProformaRow(label=label, category=OWN_COST_ROW, amount=to_won(amount))
        for label, amount in own_costs.items()
    ]
    for name, result in allocations.items():
        if not 0 <= household_index < result.households:
            raise IndexError(
                f"가구 번호 {household_index} 가 범위를 벗어났습니다 "
                f"(0~{result.households - 1}, 대상 {name!r})"
            )
        rows.append(
            ProformaRow(
                label=f"{name} 공통비용 안분",
                category=COMMON_COST_ROW,
                amount=result.per_household[household_index],
                rule=result.rule,
            )
        )
    return rows
