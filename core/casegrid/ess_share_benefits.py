"""몫 → **편익** 공장 — 몫이 든 표찰을 그 몫의 편익에 싣는다 (★분할 마지막 조각).

## 무엇이 끊겨 있었는가 — **몫이 표찰을 들고만 있고 아무도 읽지 않았다**

R56/WP-4 가 배타 판정에 물리량 축을 세웠고(`ValueStream.quantity_id`),
R57/WP-1 이 몫 선언(`core/casegrid/ess_share.py::ESSShare`)에 그 표찰을
지웠으며, R57/WP-2 가 구상 편익 다섯에 표찰 받는 자리를 냈다. 그런데 **셋을
잇는 코드가 저장소에 0곳**이었다 — `ESSSharePlan.share.quantity_id` 를 읽어
편익에 싣는 자리가 없으면 그 축은 스텁과 단위시험 안에서만 선다.

이 모듈이 그 한 자리다. `core/casegrid/grid_support.py` 가 *「세운 자원에서
읽어 편익을 짓는」* 모양을 이미 세워 두었고 **그 모양을 그대로 따른다** —
새 설계가 아니다.

## 왜 `core/casegrid/` 인가 — 거부한 자리 둘

- **`core/der/ess.py` 에 넣지 않는다.** 자원이 스스로 편익을 조립하면
  `ess_share.py` 머리말이 거부한 갈래(*「자원이 임의 배분을 하면 결과가 두
  벌이 된다」*)로 되돌아가고, 그 파일은 `NFR-206` 코드 줄 상한에 붙어 있다.
- **`core/casegrid/ess_share.py` 에 넣지 않는다.** 그 파일은 스스로 범위를
  *「몫을 수로 만드는 자리」* 로 적었고, 편익 조립은 **단가를 알아야 하는**
  다른 관심사다.

계층은 넘지 않는다 — `.importlinter` 에서 `core.casegrid` 는 `core.der` 와
`core.valuestream` 을 둘 다 import 할 수 있고 `grid_support.py` 가 이미 그렇게
서 있다.

## 표가 둘인데 중복이 아니다 — **방향이 반대다**

    ① 운전 방법 → 편익 태그     `ESS.value_streams()` 가 **정본**이다
    ② 편익 태그 → 편익 인스턴스  이 모듈이 갖는다 (`_BENEFIT_BY_TAG`)

①을 여기 옮겨 적으면 **같은 표 두 벌**이 되고 편익이 한 종 늘 때 한쪽만
자란다 — `ESS.value_streams()` 가 독스트링에 *「`if` 갈래 대신 표로 둔다」*
고 적은 그 표다. 그래서 이 공장은 표를 베끼지 않고
`plan.resource.value_streams()` 를 **불러서** 그 몫의 태그를 얻는다.

## 태그가 정확히 하나여야 한다 — 아니면 거부한다

몫은 역할이 **하나**다(`ESSShare` 에 `mode_weights` 가 없는 것이 그 뜻이다).
0개면 그 몫이 **조용히 편익 없이** 서고, 2개 이상이면 몫 하나가 두 역할을 져
정격출력이 몫마다 옳게 걸리지 않는다.

## 모르는 태그도 거부한다 — 빈 값으로 떨어뜨리지 않는다

떨어뜨리면 편익이 한 종 느는 날 그 몫이 **조용히 편익 0개**가 되고,
「몫을 갈랐는데 아무 편익도 안 난다」가 아무 예외 없이 지나간다.

## 수량은 자원에서 · 단가는 인자로

몫 자원은 `power_kw` 와 `annual_*_kwh` 가 이미 몫 비율로 갈려 있으므로
(`core/casegrid/ess_share.py::split_ess`) **그대로 읽으면 편익이 저절로 몫
크기가 된다.** 단가는 자원에 없다 — 대장에서 러너가 읽어 넘긴다
(`core/casegrid/grid_support.py::_nwas` 가 같은 모양이다).

## ⚠ 이 모듈은 배포 경로가 쓰지 않는다

`core/casegrid/e2e_runner.py` 는 이 모듈을 import 하지 않는다 — 배선은 다음
자리의 몫이고 **그때가 결론축을 한 번 흔드는 자리**다.
`tests/casegrid/test_ess_share_benefits.py` 의 ⑥ 이 그것을 소스에서 기계로
못 박는다(`tests/casegrid/test_ess_share.py` 의 ⑤ 와 같은 꼴이다).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, NoReturn

from core.casegrid.ess_share import ESSSharePlan
from core.contracts.validation import ValidationError
from core.contracts.valuestream import ValueStream
from core.valuestream import CapacityPayment, NWAs, PeakShaving, TouArbitrage


@dataclass(frozen=True)
class ShareBenefitContext:
    """**몫 자원 밖에서 오는 값**만 담는다 — 단가 다섯과 사업장 부하·연차.

    수량은 몫 자원에서 읽는다(모듈 머리말 「수량은 자원에서」). 여기 있는 것은
    자원에 **없는** 값뿐이다:

    - **단가 다섯** — 대장이 정한다. 자원에서 읽으려 하면 없다.
    - **`site_load_kw`** — `ESS.reducible_peak_kw(site_load_kw=)` 가 요구하는
      시각별 사업장 부하이며 **배터리 밖의 값**이다. 러너가
      `core/casegrid/e2e_runner.py::_site_load_kw` 로 만든다. `None` 이면 피크
      저감 가능 출력이 0 이다 — 그 규약은 `reducible_peak_kw` 가 갖는다.
    - **`year`** — 열화가 걸린 해. 수량 조회에 그대로 넘긴다.

    ⚠ **기본값을 두지 않는다(단가 다섯).** 0 을 기본값으로 두면 단가를 빠뜨린
    호출이 **0원짜리 편익**을 조용히 내고, 그 0원은 「제도가 없어서 0원」
    (`docs/assumptions.yaml` · `track: default0`)과 구별되지 않는다.
    """

    peak_price_won_per_kwh: float
    offpeak_price_won_per_kwh: float
    demand_charge_won_per_kw_month: float
    nwas_price_won_per_kwh: float
    cp_price_won_per_kw_month: float
    site_load_kw: Sequence[float] | None = None
    year: int = 1


def _reject(field: str, reason: str, action: str) -> NoReturn:
    """몫의 편익 조립을 거부한다 — **원인과 조치를 함께 적는다** (`NFR-303`).

    `core/casegrid/ess_share.py::_reject` 와 같은 모양이며 `rule` 을 비우는
    이유도 같다 — `§7.3` 대장에 몫의 편익 조립을 다루는 규칙이 아직 없고,
    없는 ID 를 달면 추적표가 그 규칙을 검증된 것으로 센다.
    """
    raise ValidationError(field=field, reason=reason, action=action)


def _tou_arbitrage(plan: ESSSharePlan, ctx: ShareBenefitContext) -> ValueStream:
    """`TouArbitrage` — 수량 둘을 **몫 자원에서** 읽는다.

    `annual_discharge_kwh`·`annual_charge_kwh` 는 갈린 용량에서 나오므로 몫
    크기가 그대로 실린다. 단가 둘은 자원에 없어 `ctx` 가 나른다.
    """
    return TouArbitrage(
        discharge_kwh=plan.resource.annual_discharge_kwh(year=ctx.year),
        charge_kwh=plan.resource.annual_charge_kwh(year=ctx.year),
        peak_price_won_per_kwh=ctx.peak_price_won_per_kwh,
        offpeak_price_won_per_kwh=ctx.offpeak_price_won_per_kwh,
        enabled=True,
        quantity_id=plan.share.quantity_id,
    )


def _peak_shaving(plan: ESSSharePlan, ctx: ShareBenefitContext) -> ValueStream:
    """`PeakShaving` — 12개월 치를 **같은 값으로** 편다.

    ⚠ **월별 변동을 여기서 지어내지 않는다.** `core/casegrid/e2e_runner.py` 가
    이미 `[peak_reduction_kw] * MONTHS_PER_YEAR` 로 같은 값을 펴며, 월별
    최대부하를 모형화하지 않는다는 한계는 `ESS.reducible_peak_kw` 독스트링이
    갖는다. 여기서 다른 규약을 세우면 배선하는 날 두 벌이 된다.

    개월 수는 **편익이 선언한 것**(`PeakShaving.MONTHS`)을 쓴다 — 12 를 여기
    적으면 그 상수가 바뀌는 날 생성자가 길이로 거부한다.
    """
    reducible_kw = plan.resource.reducible_peak_kw(
        year=ctx.year, site_load_kw=ctx.site_load_kw
    )
    return PeakShaving(
        monthly_peak_reduction_kw=[reducible_kw] * PeakShaving.MONTHS,
        demand_charge_won_per_kw_month=ctx.demand_charge_won_per_kw_month,
        enabled=True,
        quantity_id=plan.share.quantity_id,
    )


def _nwas(plan: ESSSharePlan, ctx: ShareBenefitContext) -> ValueStream:
    """`NWAs` — 생성자가 **수량을 받지 않는다**.

    ⚠ 이 편익만은 몫 크기가 생성자로 들어가지 않는다. 계통 방전량을
    `annual_value()` 가 **디스패치 결과에서** 읽기 때문이다
    (`core/valuestream/nwa.py::NWAs._grid_discharge_kwh`). 그래서 몫 크기는
    **그 몫 자원을 디스패치한 결과**가 나른다 — 여기서 비율을 곱하면
    같은 몫이 두 번 걸린다.
    """
    return NWAs(
        contribution_price_won_per_kwh=ctx.nwas_price_won_per_kwh,
        enabled=True,
        quantity_id=plan.share.quantity_id,
    )


def _cp(plan: ESSSharePlan, ctx: ShareBenefitContext) -> ValueStream:
    """`CapacityPayment` — 등록 용량은 **몫의 정격출력**이다.

    `core/casegrid/grid_support.py::_cp` 는 물리 자원의 `ess.power_kw` 를
    넘겼다. 여기서는 갈린 자원의 것을 넘기므로 **몫을 절반으로 가르면 등록
    용량도 절반**이 된다 — 그것이 *「몫이 선언이 아니라 수다」* 의 자리다.
    """
    return CapacityPayment(
        registered_capacity_kw=plan.resource.power_kw,
        capacity_price_won_per_kw_month=ctx.cp_price_won_per_kw_month,
        enabled=True,
        quantity_id=plan.share.quantity_id,
    )


def _refuse_self_consumption(plan: ESSSharePlan, ctx: ShareBenefitContext) -> NoReturn:
    """★ **자가소비 몫은 이 통로로 편익이 되지 않는다** — 사유 둘.

    ① **인자가 몫 자원에서 나오지 않는다.** `SelfConsumption` 은
       `baseline_annual_bill_won`·`new_annual_bill_won` — **요금 차액**을
       받는다. 그것은 요금 대장과 부하가 정하지 배터리 몫이 정하지 않는다.
       이 공장의 규약(*「수량은 몫 자원에서 읽는다」*)이 성립하지 않는 유일한
       태그다.
    ② ★★★ **그 절감은 이미 결론축에 있다.** `status.md` 「다음에 집을 것」의
       ★관점공백 행이 실측으로 적는다 — *「자가소비 1,985kWh/년은 「안 사서」
       이미 비용을 줄이는 방식으로 계상돼 있다(`GridPurchase`). 편익
       `SelfConsumption` 을 더하면 **같은 화폐 흐름을 두 번 센다** —
       `FR-402-AC1` 이 중복을 정확히 그렇게 정의한다」*. 같은 행이 남은 물음도
       적는다 — *「먼저 정할 것은 금액이 아니라 귀속이다」*.

    ⚠ **조용히 빈 편익을 내지 않는다.** 거부해야 그 몫을 세운 사람이 *「이
    역할은 이 통로로 편익이 되지 않는다」* 를 그 자리에서 안다.

    ⚠⚠ **이것은 가정이며 오케스트레이터가 명시로 정한 것이다**(R57/WP-4 4절
    ⑦). 이 갈래를 다시 여는 조건은 `.orch/R57/result_4.md` 5절이 갖는다.
    """
    _reject(
        "ess_share_benefits.SelfConsumption",
        f"몫 「{plan.share.name}」은 자가소비를 역할로 골랐는데 이 공장은 그 "
        "편익을 짓지 않습니다 — ① 인자(요금 차액)가 몫 자원에서 나오지 않고 "
        "② 그 절감은 이미 결론축에 계상돼 있어 더하면 이중 계상입니다",
        "이 몫의 자가소비 절감은 「안 사서」 이미 `GridPurchase` 를 줄이는 "
        "방식으로 결론축에 들어 있습니다(`status.md` 「다음에 집을 것」 "
        "★관점공백 행의 실측). 편익으로 더하면 `FR-402-AC1` 이 정의한 "
        "중복이므로, 먼저 정할 것은 금액이 아니라 **귀속**입니다 — 그 판정 "
        "뒤에 이 갈래를 여십시오. 지금은 이 몫에 다른 역할을 주거나 몫을 "
        "가르지 마십시오",
    )


#: **편익 태그 → 편익 인스턴스** (모듈 머리말의 표 ②). `ESS.value_streams()`
#: 의 표와 **방향이 반대**이므로 중복이 아니다.
#:
#: **다섯 전건을 다룬다.** 넷은 짓고 하나(`SelfConsumption`)는 **거부**한다 —
#: 거부도 「다뤘다」이며, 빠뜨리면 아래 `benefit_for_tag` 가 「모르는 태그」로
#: 읽어 사유를 잃는다.
#:
#: **`MappingProxyType` 인 이유 (`NFR-205`).** 평범한 `dict` 는 모듈 수준
#: 가변 상태이며, 케이스 그리드 병렬 실행에서 한 번의 변형이 다른 케이스의
#: 결과를 조용히 바꾼다 —
#: `core/casegrid/grid_support.py::GRID_DIRECTED_MODES` 가 `frozenset` 인 것과
#: 같은 근거다.
_BENEFIT_BY_TAG: Final[
    Mapping[str, Callable[[ESSSharePlan, ShareBenefitContext], ValueStream]]
] = MappingProxyType({
    "SelfConsumption": _refuse_self_consumption,
    "TouArbitrage": _tou_arbitrage,
    "PeakShaving": _peak_shaving,
    "NWAs": _nwas,
    "CP": _cp,
})


def benefit_for_tag(
    tag: str, plan: ESSSharePlan, ctx: ShareBenefitContext
) -> ValueStream:
    """태그 하나를 편익 하나로 — **모르는 태그는 거부한다**.

    ⚠ **빈 값으로 떨어뜨리지 않는다.** 떨어뜨리면 편익이 한 종 느는 날 그 몫이
    조용히 편익 0개가 되고, 「몫을 갈랐는데 아무 편익도 안 난다」가 아무 예외
    없이 지나간다 — 이 저장소가 반복해 경계해 온 「검사하지 않으면서 초록불」의
    그 형태다.

    ⚠ 태그가 몇 개인지는 여기서 보지 않는다 — 그것은 `build_share_benefits`
    의 일이다. 이 함수를 따로 둔 이유는 **모르는 태그의 거부**가 몫 자원을
    거치지 않고도 재어져야 하기 때문이다(`ESS.value_streams()` 는 정의상
    아는 태그만 낸다).
    """
    builder = _BENEFIT_BY_TAG.get(tag)
    if builder is None:
        _reject(
            "ess_share_benefits.tag",
            f"모르는 편익 태그입니다: {tag!r} (아는 것: "
            f"{', '.join(sorted(_BENEFIT_BY_TAG))})",
            "이 공장의 태그 표(`_BENEFIT_BY_TAG`)에 그 태그의 생성 규칙을 "
            "더하십시오 — 수량을 몫 자원의 어느 값에서 읽고 단가를 어디서 "
            "받을지가 그 규칙입니다. 빈 값으로 떨어뜨리면 그 몫이 조용히 "
            "편익 없이 섭니다",
        )
    return builder(plan, ctx)


def build_share_benefits(
    plan: ESSSharePlan, ctx: ShareBenefitContext
) -> ValueStream:
    """★★★ **몫 하나 → 편익 하나.** 표찰은 `plan.share.quantity_id` 를 그대로 싣는다.

    **이 함수가 이 모듈의 존재 이유다.** 표찰을 유추하지 않고 · 이름에서 만들지
    않고 · 편익 클래스에 상수로 박지 않는다 — 셋 다 R57/WP-2 가 거부한 갈래이며,
    박으면 몫 둘이 같은 편익 종을 쓸 때 같은 표찰을 달아 R57/WP-1 이 세운 거부
    (같은 `quantity_id`)를 우회한다. 표찰의 임자는 **몫**이다.

    태그는 `plan.resource.value_streams()` 에서 온다 — 표를 베끼지 않는다
    (모듈 머리말 「표가 둘인데 중복이 아니다」).

    ⚠ **정확히 하나여야 한다.** 0개면 그 몫이 조용히 편익 없이 서고, 2개
    이상이면 몫 하나가 두 역할을 져 정격출력이 몫마다 옳게 걸리지 않는다.
    `split_ess` 는 `mode_weights` 를 주지 않으므로 그 함수가 세운 몫은 늘
    단일 모드이며, 여기 걸리는 것은 **역할이 없는 모드**(예: 백업 예비 확보)
    이거나 이 함수에 직접 넘긴 혼합 모드 자원이다.
    """
    tags = plan.resource.value_streams()
    if len(tags) != 1:
        _reject(
            "ess_share_benefits.value_streams",
            f"몫 「{plan.share.name}」의 편익 태그가 하나가 아닙니다: "
            f"{len(tags)}개 {tags}",
            "몫 하나에 역할 하나를 주십시오 — 0개면 그 몫이 편익 없이 서고, "
            "2개 이상이면 몫 하나가 두 역할을 져 정격출력이 몫마다 옳게 "
            "걸리지 않습니다. 역할이 둘이라면 그것은 몫 둘입니다",
        )
    return benefit_for_tag(tags[0], plan, ctx)
