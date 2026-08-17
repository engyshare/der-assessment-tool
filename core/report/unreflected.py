"""**이 평가가 하지 않은 것** — 검토 「1차 의견」 6 의 절충안 (R33).

## 의견과 그에 대한 판정

의견 원문은 *「미반영 사항은 붙임으로 별도 기재」* 였다. **절반만 받았다.**

붙임으로 **내리기만** 하면 본문의 순현재가치가 확정 수치로 읽힌다. 남은 미반영
항목은 방향이 서로 다르다 — 교체비를 넣으면 결과가 나빠지고 잔존가치를 넣으면
좋아진다. NSPM 이 *「정량화하지 못한 영향을 결과와 함께 제시하라」* 고 요구하는
자리가 그것이다(양식 1절 A③).

**절충안 — 이 파일이 구현하는 것.**

    요약 · 3.4   항목명과 **방향만** (표)     ← 결과와 함께 읽힌다
    붙임 8       크기 · 사유 · 해소 조건     ← 본문을 늘리지 않는다

## ★ 목록을 문장으로 박아 두지 않는다

*「ESS 는 교체비가 빠져 있다」* 를 문장으로 적으면 수명 25년 ESS 를 쓰는 날
리포트가 **틀린 경고를 계속 인쇄한다.** 그래서 항목을 **그때그때 재어** 만든다 —
수명과 분석기간을 견주고, 편익 갈래를 세고, 운전 결과의 계통 수전을 본다.

재지 못하는 것(방법의 한계)은 `measured=False` 로 표시한다. 표시하지 않으면
「매 실행 재확인되는 사실」과 「저자가 적어 둔 문장」이 같은 무게로 읽힌다.

## ★★ 칸에 담는 것은 **사실**이며 해설이 아니다 (양식 0절)

`reason`·`resolves_when` 은 서술이 아니라 **좌표**다 — *「어느 함수가 있고 어느
경로가 부르지 않는가」*, *「어느 대장 항목·어느 절차가 오면 닫히는가」*. 짧은
명사구로 적고, 그것을 어떻게 읽어야 하는지는 적지 않는다.

⚠ **방향을 지어내지 않는다.** 배선되지 않은 인자(`unread_by_pipeline`)는
반영했을 때 결론이 어느 쪽으로 움직이는지 잴 수 없다. 재지 못한 것은
`방향 미측정` 으로 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.casegrid.models import CaseBasis
from core.report.case_report import CaseReport
from core.report.dispatch_notes import DispatchHour

#: 반영하면 결론이 **좋아지는** 항목.
DIRECTION_FAVORABLE = "반영 시 결과 개선"
#: 반영하면 결론이 **나빠지는** 항목.
DIRECTION_ADVERSE = "반영 시 결과 악화"
#: 방향을 재지 못한 항목. **「영향 없음」이 아니다.**
DIRECTION_UNKNOWN = "방향 미측정"

#: 매 실행 재어 판정한 항목인가를 나타내는 라벨.
JUDGED_MEASURED = "매 실행 측정"
JUDGED_METHOD = "방법의 한계"

#: 자가소비 편익의 태그 (`core/valuestream/self_consumption.py`).
_SELF_CONSUMPTION_TAG = "SelfConsumption"

#: 계통 전력 구매 **비용 항목**의 태그 (`core/casegrid/e2e_runner.py`).
#: 문자열 하나를 두 파일이 나누어 갖는다 — 러너가 태그를 바꾸면 이 판정이
#: 조용히 「비용 행 없음」으로 돌아서므로 계약 테스트가 둘을 함께 붙든다.
_GRID_PURCHASE_TAG = "GridPurchase"

#: 한 해를 스텝으로 다 덮었는지 가르는 수.
_STEPS_PER_YEAR = 8_760

#: 스텝별 출력이 이 폭 안에서 같으면 **평탄**으로 본다 (kWh). 부동소수 오차만
#: 흡수한다 — 넓히면 「완만한 곡선」까지 평탄으로 세어 진짜 곡선을 가린다.
_FLAT_TOLERANCE_KWH = 1e-9


@dataclass(frozen=True)
class UnreflectedItem:
    """미반영 항목 한 건 — 붙임 8 의 한 행.

    다섯 칸이 각각 다른 물음에 답한다: 무엇이(label) · 결론을 어느 쪽으로
    (direction) · 얼마나(magnitude) · 어디가 비었는가(reason) · 무엇이 오면
    닫히는가(resolves_when). **크기를 모르면 「미정량」이라 적는다** — 빈칸으로
    두면 「작다」로 읽힌다.
    """

    label: str
    direction: str
    magnitude: str
    reason: str
    resolves_when: str
    #: 이 실행에서 **재어** 판정했는가. `False` 면 값과 무관한 방법의 한계다.
    measured: bool

    @property
    def judged(self) -> str:
        return JUDGED_MEASURED if self.measured else JUDGED_METHOD


@dataclass(frozen=True)
class _AssumedQuantities:
    """형상을 가정한 운전에서 **잰** 수량 (대표일, kWh)."""

    self_consumption: float
    grid_import: float
    grid_export: float


def _assumed_quantities(
    hours: tuple[DispatchHour, ...],
) -> _AssumedQuantities | None:
    """가정 운전에서 자가소비·수전·송전을 잰다.

    **자가소비 = 스텝마다 min(발전, 부하)** 다. 발전 자원은 전 스텝이 0 이상,
    부하 자원은 전 스텝이 0 이하인 것으로 가른다 — 이름으로 가르면 자원이
    늘 때마다 여기를 고쳐야 하고, 고치지 않으면 조용히 0 이 된다. 충·방전을
    함께 하는 자원(ESS)은 어느 쪽도 아니므로 빠진다.
    """
    if not hours:
        return None
    names = tuple(hours[0].per_resource)
    generation = [
        name
        for name in names
        if all(hour.per_resource.get(name, 0.0) >= 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) > 0.0 for hour in hours)
    ]
    load = [
        name
        for name in names
        if all(hour.per_resource.get(name, 0.0) <= 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) < 0.0 for hour in hours)
    ]
    if not load:
        return None
    matched = sum(
        min(
            sum(hour.per_resource.get(name, 0.0) for name in generation),
            -sum(hour.per_resource.get(name, 0.0) for name in load),
        )
        for hour in hours
    )
    return _AssumedQuantities(
        self_consumption=matched,
        grid_import=sum(hour.grid_import for hour in hours),
        grid_export=sum(hour.grid_export for hour in hours),
    )

def _replacement_items(basis: CaseBasis) -> list[UnreflectedItem]:
    """수명과 분석기간을 견주어 **교체비·잔존가치**를 판정한다.

    둘은 조건이 다르다 — 교체비는 *수명이 분석기간보다 짧을 때*, 잔존가치는
    *길 때* 생긴다. 한 항목으로 뭉치면 PV(25년)와 ESS(17년)가 함께 있는 지금
    구성에서 둘 중 하나가 사라진다.
    """
    items: list[UnreflectedItem] = []
    horizon = basis.horizon_years
    short = [r for r in basis.resources if r.lifetime_years < horizon]
    outliving = [r for r in basis.resources if r.lifetime_years > horizon]

    if short:
        listed = " · ".join(f"{r.kind} {r.lifetime_years}년" for r in short)
        items.append(
            UnreflectedItem(
                label="교체비",
                direction=DIRECTION_ADVERSE,
                magnitude=(
                    f"미정량 · 분석기간 {horizon}년 내 수명 종료 자원 "
                    f"{len(short)}건 ({listed}) · 각 1회 교체"
                ),
                reason=(
                    # ⚠ 종전 문면은 「비용 행은 고정 운영비뿐」이었다. R34 에
                    # 전력 구매 행이 생겨 **거짓이 됐다.** 비용 행의 구성을
                    # 세어 적으면 다음에 또 낡으므로, 없는 것만 적는다.
                    "`ESS.replacement_schedule()` 존재 · 실행 경로 "
                    "(`e2e_runner`) 호출 없음 · 비용 행에 교체 항목 없음"
                ),
                resolves_when="`FR-104-AC2` (교체비 계상) 실행 경로 배선",
                measured=True,
            )
        )
    if outliving:
        listed = " · ".join(f"{r.kind} {r.lifetime_years}년" for r in outliving)
        items.append(
            UnreflectedItem(
                label="잔존가치",
                direction=DIRECTION_FAVORABLE,
                magnitude=(
                    f"미정량 · 분석기간 {horizon}년 초과 수명 자원 "
                    f"{len(outliving)}건 ({listed})"
                ),
                reason=(
                    "`core/cba/salvage.py::salvage_value()` 존재 · 실행 경로 "
                    "호출 없음"
                ),
                resolves_when="`FR-104-AC4` (잔존가치) 실행 경로 배선",
                measured=True,
            )
        )
    return items


def _unit(value_unit: str) -> str:
    head = value_unit.split("(", maxsplit=1)[0].strip()
    return f" {head}" if head else ""


def _unread_items(report: CaseReport) -> list[UnreflectedItem]:
    """**계산에 들어가지 않은 인자** — 영향폭이 정확히 0원인 것.

    ⚠ 방향을 적지 않는다. 배선되지 않았으므로 반영했을 때의 이동을 잴 수 없다.
    """
    return [
        UnreflectedItem(
            label=f"{entry.variable} (대장 `{entry.ledger_key}`)",
            direction=DIRECTION_UNKNOWN,
            magnitude=(
                f"사용값 {entry.used_value:,.4g}{_unit(entry.value_unit)} · "
                f"검토 범위 {entry.low:,.4g}~{entry.high:,.4g} · "
                "결론 변동폭 0원"
            ),
            reason="케이스 그리드 탐색 축 · 파이프라인이 읽는 자리 없음",
            resolves_when="이 값을 쓰는 계산의 실행 경로 배선 (요금 엔진 등)",
            measured=True,
        )
        for entry in report.unread_variables
    ]


def _self_consumption_item(
    basis: CaseBasis, assumed: _AssumedQuantities | None
) -> list[UnreflectedItem]:
    """자가소비를 세었는가 — **편익 갈래에 그 태그가 있는가**로 판정한다.

    모듈 상수(`PV_SELF_CONSUMPTION_RATIO`)를 읽지 않는 이유는 그것이 러너의
    내부이기 때문이다. 결과로 드러난 사실(편익 갈래)로 판정하면 자가소비를
    켜는 경로가 어디에 생기든 이 판정이 따라간다.
    """
    if any(line.tag == _SELF_CONSUMPTION_TAG for line in basis.benefits):
        return []
    sized = "미정량 · 편익 갈래에 `SelfConsumption` 없음 (전량 판매)"
    if assumed is not None:
        # ★ **금액을 잰다 (R34).** 구매 단가가 배선되기 전에는 이 칸이 「금액
        # 미정량 (소매 단가 없음)」이었다. 자가소비 절감은 *사지 않아서 아낀
        # 돈*이므로 **같은 한계단가**를 쓴다 — 이 항목이 구매 비용의 반대편
        # 추이며, 크기를 적지 않으면 붙임 8 이 불리한 항목만 정량으로 싣는다
        # (NSPM 대칭성. 양식 4절이 금지하는 형태다).
        annual_kwh = assumed.self_consumption * 365
        price = basis.grid_purchase_price_won_per_kwh
        sized = (
            "편익 갈래에 `SelfConsumption` 없음 (전량 판매) · **형상 가정 시** "
            f"자가소비 {assumed.self_consumption:,.2f}kWh/일 "
            f"(연간화 {annual_kwh:,.0f}kWh) · "
            f"단가 {price:,.0f}원/kWh 적용 시 연 {annual_kwh * price:,.0f}원 · "
            "붙임 7"
        )
    return [
        UnreflectedItem(
            label="자가소비 편익",
            # ⚠ **개선으로 적지 않는다.** 자가소비는 잉여판매와 배타(유형 A)라
            # 켜는 순간 판매 수익이 그만큼 사라진다 — 순 방향은 구매 단가와
            # 판매 단가의 차이, 그리고 부하 형상이 정한다. 지금 두 단가가
            # 우연히 같아 지금 구성에서는 상쇄에 가깝다(대장 항목
            # `tariff.hv_single_contract.energy_only` 부기).
            direction=DIRECTION_UNKNOWN,
            magnitude=sized,
            reason=(
                "파이프라인 운전에 가구 부하 없음 (전량 판매) · "
                "잉여판매와 배타이므로 순 방향은 두 단가의 차이가 정한다"
            ),
            resolves_when=(
                "가구 부하 `Q-3` 확보 (§16.3 개인정보 절차 선행) "
                "(배타 규칙 유형 A — 잉여판매와 동시 계상 불가)"
            ),
            measured=True,
        )
    ]


def _purchase_item(
    basis: CaseBasis,
    hours: tuple[DispatchHour, ...],
    assumed: _AssumedQuantities | None,
) -> list[UnreflectedItem]:
    """**계통에서 산 전력의 비용**이 프로포마에 있는가 — 비용 항목으로 판정한다.

    ## ★★ 시간대별 표를 내고서야 드러난 것 (R33 · 의견 3)

    검토 의견은 *「계통에서 전력을 구매한다면 구매 비용이 얼마인지」* 를
    물었고, 종전 판정은 *「가구 부하가 없으므로 구매 자체가 없다」* 였다.
    **틀렸다.** 붙임 7 을 실제로 내 보니 ESS 가 심야 여섯 스텝에서 충전하고
    그 전력이 **계통에서 들어온다** — 부하가 없어도 구매는 일어난다.

    ## ✔ R34 에 배선됐다 — **그래서 이 판정은 남는다**

    비용 행이 생겼으므로 이 항목은 지금 구성에서 빈 목록을 돌려준다. 그런데
    **판정 자체를 지우지 않았다**: 비용 행을 만드는 것은 러너의 세 줄이고,
    그것이 조건부가 되거나 다른 진입점이 생기면 **수전이 있는데 값이 없는**
    상태가 다시 만들어진다. 그때 조용히 좋아진 순현재가치를 붙드는 것이 이
    함수다 — 이 저장소가 반복해서 만난 *「지웠더니 되돌아왔다」* 를 막는다.

    ⚠ 조건을 「수전이 0인가」로 두었다가 이 결함을 놓칠 뻔했다. 판정은
    **수전이 있는데 비용 행이 없는가**여야 한다 — 그래서 세 갈래로 적는다.
    ⚠ 러너의 상수·인자를 읽지 않고 **결과로 드러난 사실**(비용 항목의 태그)로
    판정한다. 구매를 계상하는 경로가 어디에 생기든 이 판정이 따라가게 하려는
    것이며, `_self_consumption_item` 이 편익 갈래로 판정하는 것과 같은 형태다.
    """
    if not hours:
        return []
    if any(line.tag == _GRID_PURCHASE_TAG for line in basis.costs):
        return []
    daily = sum(hour.grid_import for hour in hours)
    if not daily:
        return [
            UnreflectedItem(
                label="계통 전력 구매 비용",
                direction=DIRECTION_UNKNOWN,
                magnitude="해당 없음 · 대표일 계통 수전 합계 0kWh",
                reason="파이프라인에 가구 부하 시계열 없음",
                resolves_when="가구 부하 `Q-3` 확보 (§16.3 개인정보 절차 선행)",
                measured=True,
            )
        ]
    return [
        UnreflectedItem(
            label="계통 전력 구매 비용",
            direction=DIRECTION_ADVERSE,
            # ★ **금액을 잰다 (R34).** 종전 문면은 *「금액 미정량 (구매 단가
            # 없음)」* 이었고, 한계단가가 대장에 선 뒤로 **거짓이 됐다** —
            # 단가는 `basis` 가 들고 있다. 그 문면을 남겨 두면 검토자는 이미
            # 확보된 값을 다시 확보하라는 뜻으로 읽고, 빠진 것이 **행 하나**
            # 라는 사실이 가려진다.
            magnitude=(
                f"수량 측정 · 대표일 계통 수전 {daily:,.2f}kWh "
                f"(연간화 {daily * 365:,.0f}kWh) · 단가 "
                f"{basis.grid_purchase_price_won_per_kwh:,.0f}원/kWh 적용 시 연 "
                f"{daily * 365 * basis.grid_purchase_price_won_per_kwh:,.0f}원"
                + (
                    " · **형상 가정 시** "
                    f"{assumed.grid_import:,.2f}kWh/일 "
                    f"(연간화 {assumed.grid_import * 365:,.0f}kWh · 붙임 7)"
                    if assumed is not None
                    else ""
                )
            ),
            reason=(
                "프로포마 비용 항목에 전력 구매 없음 · 단가는 대장에 있다 "
                "(`tariff.hv_single_contract.energy_only`)"
            ),
            resolves_when=(
                "구매 비용 행 배선 (`e2e_runner` → `energy_purchase_row`) — "
                "단가 확보는 끝났다 (`Q-6`)"
            ),
            measured=True,
        )
    ]


def _flat_generation_item(
    basis: CaseBasis, hours: tuple[DispatchHour, ...]
) -> list[UnreflectedItem]:
    """**일중 발전 곡선이 평탄한가** — 스텝별 출력을 재어 판정한다.

    ## ★ 붙임 7 을 눈으로 읽고서야 드러났다 (2026-08-15)

    표에 **00~01시 태양광 0.45kWh** 가 실려 있었다. 야간 발전이다. 러너가 PV 에
    이용률 하나만 주어 하루 발전량을 **24스텝에 균등 배분**한 결과이며, 실물의
    일사 곡선이 아니다. 드러내지 않으면 검토자는 표를 보고 **야간 태양광 발전을
    사실로 읽는다.**

    ⚠ **방향을 적지 않는다.** 발전을 주간으로 옮기면 계통 송전(편익)이 늘고
    계통 수전(비용)이 준다. **R34 에 구매 비용이 배선되어 둘 다 값을 갖게 됐고,
    그래서 방향은 이제 「배선 여부」가 아니라 두 단가의 차이가 정한다** — 지금
    판매 120원/kWh 와 구매 120원/kWh 가 우연히 같아 부호가 형상에 달려 있다.
    실제 일사 곡선을 넣어 보지 않고는 잴 수 없으므로 미측정으로 남긴다
    (지어내면 「곡선을 넣으면 좋아진다」가 되고 그것이 검토 결론이 된다).

    ⚠ **「PV 가 평탄하다」를 문장으로 박지 않는다.** 일사 시계열을 바인딩하는
    날 그 문장은 틀린 채로 계속 인쇄된다. 그래서 *「스텝별 출력이 전부 같은
    발전 자원이 있는가」* 를 매 실행 재어 판정한다 — 곡선이 들어오면 이 행이
    스스로 사라진다.
    """
    if len(hours) <= 1:
        return []
    kinds = {resource.name: resource.kind for resource in basis.resources}
    flat: list[tuple[str, float]] = []
    for name in sorted(hours[0].per_resource):
        series = [hour.per_resource.get(name, 0.0) for hour in hours]
        if any(value < 0.0 for value in series):
            continue  # 받아들이는 스텝이 있는 자원(충·방전·부하)은 대상이 아니다
        if max(series) <= 0.0:
            continue  # 이 대표 구간에 발전이 없다
        if max(series) - min(series) > _FLAT_TOLERANCE_KWH:
            continue  # 곡선이 있다
        flat.append((name, series[0]))
    if not flat:
        return []

    flat_names = {name for name, _ in flat}
    covered = sum(
        sum(hour.per_resource.get(name, 0.0) for name in flat_names)
        for hour in hours
        if hour.grid_import > 0.0
    )
    listed = " · ".join(
        # RUF001: 「×」는 검토자가 읽는 문면이다 (`e2e_runner` 와 같은 판단).
        f"{kinds.get(name, name)} {value:,.2f}kWh/스텝 × {len(hours)}스텝"  # noqa: RUF001
        for name, value in flat
    )
    return [
        UnreflectedItem(
            label="일중 발전 프로파일 (평탄)",
            direction=DIRECTION_UNKNOWN,
            magnitude=(
                f"수량 측정 · 스텝별 출력이 전부 같은 발전 자원 {len(flat)}건 "
                f"({listed}) · 계통 수전 스텝에 실린 발전량 "
                f"{covered:,.2f}kWh/일 (연간화 {covered * 365:,.0f}kWh) · "
                # ★ **금액을 잰다 (R34).** 이 수는 「야간 발전이라는 인공물이
                # 결론에 얼마를 보태고 있는가」다 — 수전 스텝에 실린 발전량은
                # 그만큼의 구매를 면하게 해 주므로 **한계단가를 곱하면 그
                # 인공물의 값**이 나온다. 4.4 가 태양광 용량을 「키울수록
                # 좋다」로 내는 근거의 크기가 여기 있다.
                f"구매 단가 {basis.grid_purchase_price_won_per_kwh:,.0f}원/kWh "
                f"기준 연 {covered * 365 * basis.grid_purchase_price_won_per_kwh:,.0f}"
                "원어치 구매를 면하고 있다"
            ),
            reason=(
                "발전 입력이 이용률(`capacity_factor`) 단일값 · 일사 시계열 "
                "(`PV.generation_profile_kwh`) 미바인딩 · 대표일 전 스텝 동일 출력"
            ),
            resolves_when=(
                "일사 시계열 확보 + `PV(generation_profile_kwh=…)` 바인딩 "
                "(입력 통로 기존 · `PV._resolve_generation`)"
            ),
            measured=True,
        )
    ]


def _season_item(hours: tuple[DispatchHour, ...]) -> list[UnreflectedItem]:
    """대표 구간을 되풀이했는가 — 스텝 수로 판정한다."""
    if len(hours) >= _STEPS_PER_YEAR:
        return []
    return [
        UnreflectedItem(
            label="계절·요일 변동",
            direction=DIRECTION_UNKNOWN,
            magnitude=(
                f"미정량 · 모의 {len(hours)}스텝 되풀이 "
                f"(연간 {_STEPS_PER_YEAR:,}스텝)"
            ),
            reason="대표일 1일 모의 · 연간 일사량·부하 시계열 없음",
            resolves_when="연간 시계열(일사량·부하) 입력 배선",
            measured=True,
        )
    ]


#: 방법 자체의 한계 — **값과 무관하게 성립**하므로 재지 않는다.
_METHOD_LIMITS: tuple[UnreflectedItem, ...] = (
    UnreflectedItem(
        label="확률적 불확실성 (몬테카를로)",
        direction=DIRECTION_UNKNOWN,
        magnitude="미산출 · 3수준 스윕(low·base·high) · 확률분포·신뢰구간 없음",
        reason="인자별 분포 부재 (전제 신뢰도 `가정`)",
        resolves_when="핵심 인자 신뢰도 `추정`·`확정` 상향 + 분포 자료 확보",
        measured=False,
    ),
)


def build_unreflected(report: CaseReport) -> tuple[UnreflectedItem, ...]:
    """이 실행의 미반영 항목 전건. **잰 것을 앞에** 둔다.

    순서가 판단을 담는다 — 매 실행 재확인되는 사실이 위, 방법의 한계가
    아래다.
    """
    basis = report.basis
    assumed = _assumed_quantities(report.assumed_hours)
    return (
        *_replacement_items(basis),
        *_unread_items(report),
        *_self_consumption_item(basis, assumed),
        *_purchase_item(basis, report.dispatch_hours, assumed),
        *_flat_generation_item(basis, report.dispatch_hours),
        *_season_item(report.dispatch_hours),
        *_METHOD_LIMITS,
    )


def unreflected_rows(items: tuple[UnreflectedItem, ...]) -> list[str]:
    """본문 3.4 의 표 — **항목명과 방향만** (절충안의 앞 절반).

    ⚠ **크기·사유를 여기 싣지 않는다.** 싣기 시작하면 본문이 붙임이 되고,
    양식이 본문을 4~5쪽으로 묶어 둔 이유가 사라진다.
    """
    if not items:
        return ["| 없음 | — | — |"]
    return [
        f"| {item.label} | {item.direction} | {item.judged} |" for item in items
    ]


def unreflected_direction_tally(items: tuple[UnreflectedItem, ...]) -> str:
    """요약 1절의 미반영 칸 — 건수와 방향별 내역.

    방향이 **갈린다는 사실**이 요약에 필요한 정보다. 건수만 적으면 검토자는
    그것을 한 방향의 여유로 읽는다.
    """
    if not items:
        return "없음"
    favorable = sum(1 for i in items if i.direction == DIRECTION_FAVORABLE)
    adverse = sum(1 for i in items if i.direction == DIRECTION_ADVERSE)
    unknown = sum(1 for i in items if i.direction == DIRECTION_UNKNOWN)
    return (
        f"{len(items)}건 — 개선 {favorable} · 악화 {adverse} · "
        f"방향 미측정 {unknown} (붙임 8)"
    )


def unreflected_section(items: tuple[UnreflectedItem, ...]) -> list[str]:
    """붙임 8 — 미반영 항목 **전문**. 절충안의 뒤 절반."""
    lines = [
        "## 붙임 8. 미반영 항목",
        "",
        "본문 3.4 가 항목명과 방향만 실은 항목의 전건이다.",
        "",
    ]
    if not items:
        lines += ["- 미반영으로 판정된 항목 — 없음", ""]
        return lines
    lines += [
        "| 항목 | 방향 | 크기 | 비어 있는 자리 | 해소 조건 | 판정 |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {item.label} | {item.direction} | {item.magnitude} | "
        f"{item.reason} | {item.resolves_when} | {item.judged} |"
        for item in items
    ]
    lines += [
        "",
        f"- `{JUDGED_MEASURED}` — 이 실행에서 수명·편익 갈래·운전 결과를 재어 "
        "판정한 항목. 구성이 바뀌면 행이 바뀐다",
        f"- `{JUDGED_METHOD}` — 값과 무관하게 성립하는 방법의 한계",
        f"- `{DIRECTION_UNKNOWN}` — 반영 시 결론의 이동 방향을 계산하지 못한 "
        "항목. 영향이 없다는 뜻이 아니다",
        "",
    ]
    return lines
