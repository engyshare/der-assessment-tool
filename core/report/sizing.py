"""자립 역산 (경우 「가」 · 100% 에너지 자립) — R55/WP-1.

## 왜 이 모듈이 생겼는가

`docs/적정용량-산출방법-검토.md` §0 표가 이렇게 적어 두었다: *「없다 — 대장에
연간 사용량은 있으나 역산 산식이 없다」*. 대장(`docs/assumptions.yaml` 의
`load.household.annual`)에 가구 연간 사용량은 있었고
`core/der/pv.py::PV.annual_generation_kwh` 에 정방향 산식(용량 × 8,760h ×
이용률, 오라클 1kW × 8760 × 0.15 = 1,314.0)도 있었다 — 다만 그 둘을 잇는
**역함수**가 저장소 어디에도 없었다. 이 모듈이 채우는 것이 그 자리다: 연간 부하를 전량 자가
발전으로 충당하는 데 필요한 최소 PV 용량을, 대장 세 수준(low·base·high)과
참고 부하 각각에 대해 역산한다.

## 이 모듈이 답하지 않는 것

**어느 연간 사용량이 맞는가**(검토서 §7)는 물음으로 남아 있다. 사용자 예시
(월 600kWh · 연 7,200kWh)와 대장 base(연 3,600kWh)가 두 배 가까이 다르고, 이
모듈은 어느 쪽도 고르지 않는다 — 둘 다 역산해 나란히 낸다. **이용률도 고르지
않는다** — 값의 소유자는 전제 대장(`capacity_factor.pv_rooftop`)이고 이 모듈은
그것을 **인자로만** 받는다.

⚠ **R67/WP-N2 까지 그 값은 소스 상수였다**(종전 이름은 `e2e_runner` 의
`PV_CAPACITY_FACTOR`). 역산 **전체가 그 값에 반비례**하는데 사용자가 바꿀
통로가 없었고, 판정 `docs/decisions-2026-09-08-R67b.md` §3-4 가 그것을 지목해
대장으로 옮겼다.

## 탐색 구간을 넓히지 않는다 — **그리고 답을 구간 안으로 깎지도 않는다**

역산 용량이 `core/casegrid/ledger_levels.py::_DESIGN_VARS` 의 `pv_capacity_kw`
탐색 상한을 넘을 수 있다 — 그때 이 모듈은 구간을 넓히지 않고
`within_search_range=False` 를 값으로 싣는다. 구간을 넓히는 것은 결론 축
(`core/report/capacity.py` 의 4.4 적정 용량 검토)이 훑는 폭 자체를 바꾸는
일이며, 넘는 점을 지우지도 않는다(`capacity.py` 머리 독스트링의
*「계산되지 않는 점을 버리지 않는다」* 와 같은 태도).

★★ **그 구간은 «경제성 스윕»의 것이다** (R67/WP-N2 · 판정 §2-2). 사용자
판정이 *「용량 범위 제한이 없어야 하며」* 이므로 이 역산의 답은 구간과
무관하게 그대로 제시되고, 「구간 밖」 표시는 *그 스윕이 이 용량을 훑지
않았다*는 뜻이다. 문면은 `capacity.py::search_range_note` 하나가 갖는다 —
같은 표를 두 문서가 싣기 때문이다.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from core.contracts.units import HOURS_PER_YEAR
from core.contracts.validation import ValidationError

# ⚠ **문면 하나를 두 문서가 쓴다** — 「구간 밖」이 무슨 뜻인가를 검증 보고서
# 2단계와 이 붙임이 같이 적어야 한다(R67/WP-N2 · 판정 §2-2). 정본은 경제성
# 스윕을 소유한 모듈이며, 여기서 다시 적으면 한쪽만 고쳐진다.
from core.report.capacity import search_range_note

#: 사용자 예시의 월 사용량 (판정 §2-1 「가」 · 검토서 §7). **대장 값이 아니다** —
#: 대장(`load.household.annual`)의 base 는 연 3,600kWh 이고 이 예시는 연 7,200kWh 다.
#: 어느 쪽이 맞는지는 답이 오지 않았다(검토서 §7 의 세 가능성).
USER_EXAMPLE_MONTHLY_KWH: Final[float] = 600.0
MONTHS_PER_YEAR: Final[int] = 12

#: 대장이 `sensitivity` 에 반드시 갖는 세 수준. `ledger_levels.LEVEL_NAMES` 와
#: 값이 같다 — 이 모듈이 그 모듈을 import 하지 않는 이유는, 여기서 요구하는
#: 것은 「이 세 이름의 부하가 다 있는가」뿐이고 대장을 직접 읽지 않기
#: 때문이다(`load_levels` 는 호출측이 `build_level_map()` 으로 만들어 건넨다).
_LOAD_LEVEL_NAMES: tuple[str, str, str] = ("low", "base", "high")


def required_pv_capacity_kw(*, annual_load_kwh: float, capacity_factor: float) -> float:
    """연간 부하를 전량 자가 발전으로 충당하는 데 필요한 **최소 설치 용량**(kW).

    `PV.annual_generation_kwh` 의 **역함수**다 — 그 오라클(1kW · 8,760h ·
    이용률 15% → 1,314.0kWh)을 용량에 대해 뒤집는다:
    용량 = 연간 부하 ÷ (8,760h × 이용률). 열화율을 넣지 않는 이유는 오라클
    자신이 1년차(열화 0) 기준이고, 여기서 뒤집는 것은 그 1년차 산식이지
    20년 누계가 아니기 때문이다.
    """
    if not 0.0 < capacity_factor <= 1.0:
        raise ValidationError(
            field="pv.capacity_factor",
            reason=f"이용률은 0보다 크고 1 이하여야 합니다 (받은 값 {capacity_factor})",
            action="이용률을 0 초과 1 이하의 소수로 지정하십시오",
        )
    if annual_load_kwh <= 0.0:
        raise ValidationError(
            field="load.household.annual",
            reason=f"연간 부하는 0보다 커야 합니다 (받은 값 {annual_load_kwh})",
            action="연간 부하(kWh)에 0보다 큰 값을 지정하십시오",
        )
    return annual_load_kwh / (HOURS_PER_YEAR * capacity_factor)


@dataclass(frozen=True)
class SelfSufficiencyPoint:
    """자립 역산 점 하나."""

    #: 이 부하가 어디서 왔는가 — 예 「대장 base」·「사용자 예시(월 600kWh)」.
    source_label: str
    annual_load_kwh: float
    required_capacity_kw: float
    #: 역산 용량이 지금 탐색 구간(`pv_capacity_kw`) 안에 있는가.
    #: **밖이면 구간을 넓히지 않고 「밖이다」를 싣는다** — 구간을 움직이면
    #: 결론축이 움직인다.
    within_search_range: bool


@dataclass(frozen=True)
class SelfSufficiencySizing:
    """자립 역산 결과 한 벌 — 대장 세 수준 + 참고 부하."""

    capacity_factor: float
    #: 이용률의 **출처**. 지금은 대장 항목이 아니라 소스 상수다 — 그 사실을
    #: 값으로 갖는다(검토서 §7 부수발견).
    capacity_factor_source: str
    #: ★ **단지 규모가 곱해진 탐색 구간**이다 (R65/WP-2c) —
    #: `_DESIGN_VARS` 의 `pv_capacity_kw` 는 **한 호분**(1.0~9.0 kW)이고
    #: 20호 실행에서는 20~180 kW 가 된다. ⛔ **띠의 수를 고친 것이 아니라
    #: 곱한 것이다.**
    search_low_kw: float
    search_high_kw: float
    points: tuple[SelfSufficiencyPoint, ...]
    #: 이 역산이 답한 **단지 규모**(호). `None` 이면 「가구 한 호」이고 그때
    #: 배수는 1 이라 이 인자가 생기기 전과 원소 하나까지 같다.
    household_count: int | None = None
    #: 한 호에 얹힌 **추가 전력사용기기** 연간 부하(kWh/호·년). 위 점들의
    #: 연간 사용량에 **이미 더해져 있다** — 왜 더하는지는
    #: `build_self_sufficiency_sizing` 독스트링 ★★ 가 갖는다.
    extra_appliance_load_kwh: float = 0.0


def build_self_sufficiency_sizing(
    *,
    load_levels: Mapping[str, float],
    capacity_factor: float,
    capacity_factor_source: str,
    search_low_kw: float,
    search_high_kw: float,
    reference_loads: Sequence[tuple[str, float]] = (),
    extra_appliance_load_kwh: float = 0.0,
    household_count: int | None = None,
) -> SelfSufficiencySizing:
    """대장 세 수준(low·base·high)과 참고 부하를 **각각** 역산한다.

    `load_levels` 는 `build_level_map(...)["household_load_annual_kwh"]` 를
    그대로 받는 모양이다(`low`·`base`·`high` 셋). 점 순서는 **`low` → `base` →
    `high` → `reference_loads` 순서 그대로**다 — `source_label` 은 그 순서로
    「대장 low」·「대장 base」·「대장 high」이고, 참고 부하는 받은 라벨 그대로다.

    ## ★★ R65/WP-2c — **이 역산이 답하는 사업이 본문과 같아졌다**

    받는 부하도 탐색 구간도 **「한 호」 값**이었다. 그런데 본문 4절은
    `core/casegrid/e2e_runner.py` 가 단지 규모를 곱한 설비(20호면 60 kW)로
    돌고 부하도 `(대장 annual + 기기) × 호수` 다. 그래서 같은 리포트가
    **두 사업을 그렸다** — 본문은 60 kW 를 쓰는데 이 표는 「1~9 kW 구간」과
    한 호 부하로 *「필요 용량은 2.74 kW」* 라 답했다.

    ⇒ 부하와 탐색 구간에 **같은 배수**를 건다. 곱하는 것이지 **띠의 수
    (1.0·9.0)를 고치는 것이 아니다** — 고치면 결론축(4.4 가 훑는 폭)이
    움직인다(머리 독스트링 「탐색 구간을 넓히지 않는다」).

    ★★ **기기 부하를 더하는 자리도 여기다.** 대장 `load.household.annual` 은
    *「추가 전력사용기기가 없는 가구 기준」* 이고 본문은 거기에 히트펌프·전기차를
    **더한 뒤** 곱한다(`core/casegrid/seasonal_dispatch.py::_load_total_kwh`).
    이 역산이 `annual` 만 보면 **본문보다 작은 부하로 답한다** — 그러면 이
    표의 「필요 용량」이 본문이 실제로 감당해야 하는 것보다 작게 나온다.

    ⚠ **참고 부하(사용자 예시)에도 같은 처리를 한다.** 두 부하를 나란히 놓고
    *「어느 쪽이 맞는가」* 를 묻는 것이 이 표의 목적인데(`_mismatch_lines`),
    한쪽만 곱하면 그 물음이 **규모 차이로 덮인다.**

    ⚠ **미지정이면 배수가 1 이고 기기 부하가 0** 이라, 이 두 인자가 생기기
    전과 원소 하나까지 같다.
    """
    missing = [name for name in _LOAD_LEVEL_NAMES if name not in load_levels]
    if missing:
        raise ValidationError(
            field="load.household.annual",
            reason=f"부하 수준에 {', '.join(missing)} 이(가) 없습니다",
            action="load_levels 에 low·base·high 세 수준을 모두 지정하십시오",
        )
    if search_low_kw > search_high_kw:
        raise ValidationError(
            field="pv.capacity_kw",
            reason=(
                f"탐색 구간 하한({search_low_kw})이 상한({search_high_kw})보다 큽니다"
            ),
            action="search_low_kw 를 search_high_kw 이하의 값으로 지정하십시오",
        )

    labeled_loads: list[tuple[str, float]] = [
        (f"대장 {name}", load_levels[name]) for name in _LOAD_LEVEL_NAMES
    ]
    labeled_loads.extend(reference_loads)

    # ★★★ **한 호분 → 단지분** (R65/WP-2c · 위 독스트링 ★★). 부하와 탐색
    # 구간에 **같은 배수**를 건다.
    scale = 1.0 if household_count is None else float(household_count)
    suffix = _scale_suffix(extra_appliance_load_kwh, household_count)
    search_low_kw, search_high_kw = search_low_kw * scale, search_high_kw * scale

    points: list[SelfSufficiencyPoint] = []
    for label, household_load_kwh in labeled_loads:
        annual_load_kwh = (household_load_kwh + extra_appliance_load_kwh) * scale
        required_capacity_kw = required_pv_capacity_kw(
            annual_load_kwh=annual_load_kwh, capacity_factor=capacity_factor
        )
        points.append(
            SelfSufficiencyPoint(
                source_label=f"{label}{suffix}",
                annual_load_kwh=annual_load_kwh,
                required_capacity_kw=required_capacity_kw,
                within_search_range=(
                    search_low_kw <= required_capacity_kw <= search_high_kw
                ),
            )
        )

    return SelfSufficiencySizing(
        capacity_factor=capacity_factor,
        capacity_factor_source=capacity_factor_source,
        search_low_kw=search_low_kw,
        search_high_kw=search_high_kw,
        points=tuple(points),
        household_count=household_count,
        extra_appliance_load_kwh=extra_appliance_load_kwh,
    )


def _scale_suffix(extra_appliance_load_kwh: float, household_count: int | None) -> str:
    """점 이름에 **무엇을 더하고 무엇을 곱했는지**를 적는다.

    ⚠ 라벨을 그대로 두면 「대장 base」가 대장에 적힌 수가 아닌 값을 가리키게
    되고, 그 어긋남은 아무 예외도 내지 않는다.
    """
    parts = []
    if extra_appliance_load_kwh:
        parts.append(" + 기기")
    if household_count is not None:
        parts.append(f" × {household_count}호")  # noqa: RUF001
    return "".join(parts)


def _range_note(sizing: SelfSufficiencySizing, point: SelfSufficiencyPoint) -> str:
    if point.within_search_range:
        return "예"
    if point.required_capacity_kw > sizing.search_high_kw:
        return f"아니오 — 구간 상한 {sizing.search_high_kw:g}kW 초과"
    return f"아니오 — 구간 하한 {sizing.search_low_kw:g}kW 미만"


def _mismatch_lines(sizing: SelfSufficiencySizing) -> list[str]:
    """대장 base 와 참고 부하(있으면 첫째)의 필요 용량을 **원문 값 그대로** 나란히 낸다."""
    base_point = sizing.points[_LOAD_LEVEL_NAMES.index("base")]
    reference_points = sizing.points[len(_LOAD_LEVEL_NAMES):]
    if not reference_points:
        return []
    reference_point = reference_points[0]
    return [
        f"- 어긋남 — 대장 base(연 {base_point.annual_load_kwh:,.0f}kWh)의 필요 용량 "
        f"**{base_point.required_capacity_kw:.2f}kW**와 {reference_point.source_label}"
        f"(연 {reference_point.annual_load_kwh:,.0f}kWh)의 필요 용량 "
        f"**{reference_point.required_capacity_kw:.2f}kW**가 두 배 가까이 다르고, "
        "어느 쪽이 맞는지는 답이 오지 않았다(검토서 §7)",
    ]


def _scale_lines(sizing: SelfSufficiencySizing) -> list[str]:
    """**무엇을 곱했고 무엇을 더했는가** — 한 호 실행에서는 한 줄도 나오지 않는다.

    이 줄이 없으면 표의 수가 대장에 적힌 수와 달라 보이는데 **왜 다른지가
    리포트 안에 없다**(R65/WP-2c).
    """
    if sizing.household_count is None and not sizing.extra_appliance_load_kwh:
        return []
    added = (
        f"한 호에 추가 전력사용기기 **{sizing.extra_appliance_load_kwh:,.0f}kWh/년**을 "
        "더하고 "
        if sizing.extra_appliance_load_kwh
        else ""
    )
    scaled = (
        f"단지 규모 **{sizing.household_count}호**를 곱했다"
        if sizing.household_count is not None
        else "단지 규모는 곱하지 않았다(가구 한 호)"
    )
    return [
        f"- 규모 — {added}{scaled}. 본문 4절이 도는 부하·설비와 **같은 배수**이며"
        "(`core/casegrid/e2e_runner.py`), 탐색 구간도 함께 곱했다 — "
        "구간의 수(한 호분 "
        f"{sizing.search_low_kw / (sizing.household_count or 1):g}~"
        f"{sizing.search_high_kw / (sizing.household_count or 1):g}kW)를 고친 것이 "
        "아니다",
    ]


def self_sufficiency_section(sizing: SelfSufficiencySizing) -> list[str]:
    """**붙임 10** 의 소절 — 경우 「가」(100% 자립) 역산 결과 (R55/WP-2-fix).

    ## 왜 본문 4.4 가 아니라 붙임 10 인가

    처음에는 본문 4.4 안에 실었다(R55/WP-2). 그런데
    `tests/report/test_overview_sections.py::test_body_stays_within_the_form_length_budget`
    가 본문 분량 상한(219줄 — 「4~5쪽·130~170줄」기준에서 이미 다섯 번
    밀려 있었다)을 넘겨 빨간불을 냈고, 그 실패 문면 자체가 *「늘어난 것을
    붙임으로 내릴 것」* 이라 적었다. 상한을 여섯 번째로 미는 대신 이 소절을
    붙임 10 으로 옮겼다 — `capacity_appendix` 가 이미 설계 변수마다
    `### {label}` 소절을 쌓는 자리이므로 같은 층에 나란히 세운다.

    이 표는 **진단이지 답이 아니다** — 대장 세 수준과 참고 부하를 나란히
    역산해 보일 뿐, `_DESIGN_VARS` 탐색 구간도 이용률도 여기서 바꾸지
    않는다(검토서 §1-⑥). 구간 밖 점도 지우지 않는다 — `capacity_section`
    이 지키는 태도(「계산되지 않는 점을 버리지 않는다」)와 같다.

    ⚠ **칸 이름이 그 구간의 소유자를 말한다** (R67/WP-N2). 종전에는 「탐색
    구간 안인가」라고만 적어, 이 역산이 **본문 4.4 의 경제성 스윕과 같은
    구간에 매인 것처럼** 읽혔다 — 사용자 판정은 그 반대다(§2-2).
    """
    lines = [
        "### 경우 「가」 — 100% 에너지 자립에 필요한 용량 (역산)",
        "",
        "| 연간 사용량의 출처 | 연간 사용량 (kWh) | 필요 용량 (kW) "
        "| 4.4 의 경제성 스윕 구간 안인가 |",
        "|---|---|---|---|",
    ]
    for point in sizing.points:
        lines.append(
            f"| {point.source_label} | {point.annual_load_kwh:,.0f} | "
            f"{point.required_capacity_kw:.2f} | {_range_note(sizing, point)} |"
        )
    lines.append("")
    lines += [
        "- 산식 — 필요 용량(kW) = 연간 사용량(kWh) ÷ "
        f"({HOURS_PER_YEAR:,}h × 이용률)",  # noqa: RUF001
        (
            f"- 이용률 {sizing.capacity_factor:.0%} — 출처: {sizing.capacity_factor_source}. "
            "**그 값이 옳다는 근거는 없다** — 이 사업지의 일사량·경사·방위·음영을 "
            "재지 않았고 실적 발전량도 없다(대장 항목의 유도 근거가 그 사실을 "
            "적는다). 이 표의 필요 용량은 그 값에 반비례하므로, 수가 그럴듯해 "
            "보이는 것을 근거로 쓸 수 없다"
        ),
    ]
    lines += _scale_lines(sizing)
    lines += _mismatch_lines(sizing)
    lines.append(f"- {search_range_note(sweep_where='본문 4.4')}")
    lines.append(
        "- 이 표는 진단이다 — 이 용량을 채택한 것이 아니다. 채택하려면 탐색 구간·"
        "기준 구성을 바꿔야 하고 그것은 결론축을 움직인다"
    )
    lines.append("")
    return lines
