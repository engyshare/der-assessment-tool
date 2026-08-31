"""**적자는 어디서 오는가** — 결손을 항목별로 갈라 크기 순으로 (R49 · 판정 §3 ⓐ).

## 무엇이 어긋나 있었나

5.1 은 *「단독 전환 인자 — 없음」* 이라 적고, 그 옆에 거리(결손 12,956,180원)와
전환 지원율을 싣는다. 셋 다 참이지만 **셋 다 「얼마나 모자란가」까지만** 말한다.
사용자 판정이 그 자리를 정확히 짚었다 — *「단순하게 답이 없음으로 기재하는
것보다 **주요한 적자 요인이 무엇이고, 이것이 얼마나 영향을 미치는지**에 대한
내용이 기술되야 함」*.

이 절이 답하는 것은 **「그 결손이 어느 항에서 왔는가」** 하나다. *「무엇을
고치면 얼마가 줄어드나」* 는 **5.1 의 몫**이며, 두 절은 서로를 가리킨다
(`SENSITIVITY_SECTION`).

## ★★★ 오라클 — **합계가 결론 축과 정확히 같아야 한다**

합이 맞지 않는 분해는 *「어디서 오는가」* 에 답하는 **척만 하는 표**다. 그래서
`build_shortfall()` 은 맞지 않으면 **표를 만들지 않고 터뜨린다.** 그 규약이
이 파일의 설계를 전부 정한다:

- **엔진이 만든 행을 그대로 쓴다** (`CaseOutcome.cashflows`). 1년차 편익·운영비를
  20년 등액으로 놓고 되지으면 물가 상승이 빠져 **469,314원이 어긋난다**
  (실측은 `CashflowSplit` 독스트링).
- **할인 후 현재가치로 가른다.** `npv` 가 할인값이므로 명목으로 가르면 합계가
  맞지 않는다. 현가는 `core.cba.metrics.npv()` 를 **초기투자 0 으로** 불러
  얻는다 — 할인 규칙을 여기서 다시 쓰면 그것이 사본이 되고, 사본은 러너가
  할인 규약을 바꿔도 옛 규칙으로 그럴듯하게 계속 인쇄한다.
- **초기투자는 할인하지 않는다** — `t=0` 에 나가는 비용이다. 같은 규약을
  `CaseReport.break_even_subsidy_rate` 독스트링이 이미 적어 두었고
  (*「지원 1원은 결론 축을 정확히 1원 올린다」*), 그 환산이 성립하는 근거가
  바로 이것이다.

## ⚠ 더하는 항과 **속항**을 가른다

`운영 단계` 는 *편익 − 운영비* 이므로 **편익 누적을 이미 품고 있다.** 넷을 다
더하면 편익이 두 번 세어져 합계가 거짓이 된다. 그래서 더해지는 것은
`ShortfallItem` 셋뿐이고, `ShortfallPart` 는 그 셋을 **가르기만** 한다
(`Shortfall.total_won` 이 속항을 세지 않는 이유다).

## ⚠⚠ 수를 문장으로 박지 않는다 — **실린 항목에서 짓는다**

*「최대 원인은 계통 구매다」* 를 문자열로 두면 구성이 바뀌어도 **틀린 채로 계속
인쇄된다** — 실제로 무보조와 보조 80% 는 **1위 항이 다르다**(초기투자 ↔ 운영
단계). 그래서 문장은 표에 실린 항에서 `max()` 로 골라 짓는다.
`core/report/unreflected.py` 가 같은 규약을 적어 두었다 — *「목록을 문장으로 박아
두지 않는다 … 그때그때 재어 만든다」*.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.casegrid.models import CashflowSplit
from core.cba.metrics import npv
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO
from core.report._format import NO_VALUE, _won
from core.report.case_report import CONCLUSION_METRIC, CaseReport

#: 더해지는 항의 **키** — 문면이 아니라 이것으로 항을 찾는다. 라벨로 찾으면
#: 제목을 다듬는 순간 문장이 항을 잃고, 잃은 자리는 예외가 아니라 **빈 문장**
#: 으로 나타난다.
ITEM_INITIAL = "초기투자"
ITEM_OPERATING = "운영"
ITEM_LIFECYCLE = "교체잔존"

#: 이 절의 **번호와 이름** — 한 자리에서만 적는다.
#:
#: 5.1 의 「없음」 칸과 「지원만으로는 안 된다」 문면이 이 절을 가리키므로
#: (판정 §3 ⓒ · §2), 번호를 자리마다 적으면 절을 옮길 때 한 곳만 고쳐지고
#: 나머지는 **없는 절을 가리킨다.** 이름은 판정 문면 그대로다.
SECTION_NUMBER = "5.3"
SECTION_TITLE = "적자는 어디서 오는가"

#: **짝이 되는 절의 번호** — 5.1. 둘은 같은 결손을 서로 다른 축으로 가른다:
#:
#:     5.3   결손이 **어디서** 오는가          (항목별 분해)
#:     5.1   **무엇을 고치면** 얼마가 줄어드나  (인자별 줄임)
#:
#: ★ 그래서 **서로를 가리켜야 한다** (판정 §3 ⓑ · R49/WP-4). 갈라져 있으면
#: 심의회가 *「초기투자가 76% 다」* 와 *「설비단가를 끝까지 밀면 96만원 준다」*
#: 를 이어 읽지 못하고, 두 표가 각각 다른 사업을 말하는 것처럼 읽힌다.
#:
#: ⚠ **번호를 5.1 쪽에도 적지 않는다.** 위 `SECTION_NUMBER` 와 같은 이유로
#: 여기서 한 번만 짓고 `narrative.py` 가 자기 표제에도 이 상수를 쓴다 — 두
#: 자리에 적으면 절을 옮길 때 한쪽이 **없는 절을 가리킨다.**
SENSITIVITY_SECTION = "5.1"

#: 합계가 결론 축과 어긋나도 되는 폭 — **원 미만**이다. 행 금액은 전부 정수
#: 원이고 `metrics.npv()` 도 원 단위로 반올림해 더하므로(`units.won_sum`),
#: 1원이라도 어긋나면 그것은 반올림이 아니라 **분해가 틀린 것**이다.
EXACT_WON = 0.5


@dataclass(frozen=True)
class ShortfallPart:
    """**속항** — 위 항을 가르기만 한다. 다시 더하지 않는다."""

    label: str
    amount_won: float


@dataclass(frozen=True)
class ShortfallItem:
    """**더해지는 항** — 이 셋의 합이 결론 축(`npv`)이다."""

    key: str
    label: str
    amount_won: float
    #: 이 항을 가르는 속항. 합은 `amount_won` 과 같지만 **표에서 다시 더하지
    #: 않는다**(위 모듈 독스트링).
    parts: tuple[ShortfallPart, ...] = ()


@dataclass(frozen=True)
class Shortfall:
    """한 실행의 결손 분해 — 항은 **절대값 내림차순**이다.

    순서가 이 자료형의 산출물 중 하나다. 판정 §3 ⓑ 가 *「ⓐ 의 분해에서 큰
    항목부터 고른다」* 로 다음 축을 고르므로, **순위가 다음 검토의 입력**이다.
    """

    items: tuple[ShortfallItem, ...]
    #: 엔진이 낸 결론 축. 아래 `total_won` 과 같아야 한다.
    npv_won: float
    horizon_years: int

    @property
    def total_won(self) -> float:
        """더해지는 항만 더한다 — 속항은 세지 않는다."""
        return sum(item.amount_won for item in self.items)


def _present_value(rows: Sequence[CashFlowRow], discount_rate: float) -> float:
    """행 묶음의 현재가치 — **엔진의 할인 함수를 그대로 부른다.**

    초기투자 자리에 `ZERO` 를 넣으면 `npv()` 는 운영 현금흐름의 현가만 낸다.
    할인 계수를 여기서 다시 쓰지 않는 이유는 이 파일 머리말에 있다.
    """
    return float(npv(ZERO, list(rows), discount_rate=discount_rate))


def _rows_as_parts(
    rows: Sequence[CashFlowRow], discount_rate: float, *, sign: float
) -> tuple[ShortfallPart, ...]:
    """행 하나를 속항 하나로 — 이름은 **행이 스스로 단 것**을 쓴다.

    ⚠ `row.tag` 를 보고 이름표를 다시 붙이지 않는다. 태그로 되짚으면 태그를
    다듬는 순간 그 항이 어느 이름에도 들지 못한다(`CashflowSplit` 독스트링).
    `sign` 은 **비용 행의 부호를 뒤집는 자리**이며, 러너 쪽에서 그 일을 하는
    자리(`operating_lines.net_operating_flows()`)와 같은 규약이다.
    """
    parts = [
        ShortfallPart(
            label=row.label, amount_won=sign * _present_value([row], discount_rate)
        )
        for row in rows
    ]
    return tuple(sorted(parts, key=lambda part: -abs(part.amount_won)))


def build_shortfall(report: CaseReport) -> Shortfall:
    """결손을 셋으로 가른다 — **합계는 `npv` 와 정확히 같다.**

    ⚠ 초기투자는 **이 시나리오가 실제로 낸 돈**(`initial_outlay_won`, 지원
    반영 후)이다. 총사업비(무지원 기준선)를 쓰면 지원받은 시나리오에서 합계가
    지원액만큼 어긋나고, 그 어긋남은 아래 확인에서 잡힌다.

    맞지 않으면 **표를 만들지 않고 터뜨린다.** 합이 안 맞는 분해는 *「어디서
    오는가」* 에 답하는 척만 하는 표이며, 그것을 인쇄하는 것이 「없음」 한 줄보다
    나쁘다 — 검토자가 확인할 수 없는 수가 늘기 때문이다.
    """
    split: CashflowSplit = report.cashflows
    rate = report.basis.discount_rate
    horizon = report.basis.horizon_years
    outlay = float(report.metrics["initial_outlay_won"])

    benefit_pv = _present_value(split.benefit, rate)
    operating_cost_pv = _present_value(split.operating_cost, rate)
    lifecycle_pv = _present_value(split.lifecycle, rate)

    items = (
        ShortfallItem(
            key=ITEM_INITIAL,
            label="초기투자 (t=0 · 지원 반영 후)",
            amount_won=-outlay,
        ),
        ShortfallItem(
            key=ITEM_OPERATING,
            label=f"운영 단계 {horizon}년 누적 (편익에서 운영비를 뺀 값)",
            amount_won=benefit_pv - operating_cost_pv,
            # ★ 편익 누적이 **여기 속항으로** 선다 — 판정 §3 ⓐ 의 ④ 다.
            # 더해지는 항으로 올리면 편익이 두 번 세어진다(모듈 독스트링).
            parts=(
                ShortfallPart(
                    label=f"편익 {horizon}년 누적", amount_won=benefit_pv
                ),
                *_rows_as_parts(split.operating_cost, rate, sign=-1.0),
            ),
        ),
        ShortfallItem(
            key=ITEM_LIFECYCLE,
            label="교체·잔존 순액",
            amount_won=-lifecycle_pv,
            parts=_rows_as_parts(split.lifecycle, rate, sign=-1.0),
        ),
    )
    shortfall = Shortfall(
        items=tuple(sorted(items, key=lambda item: -abs(item.amount_won))),
        npv_won=float(report.metrics[CONCLUSION_METRIC]),
        horizon_years=horizon,
    )
    drift = shortfall.total_won - shortfall.npv_won
    if abs(drift) > EXACT_WON:
        raise ValueError(
            "적자 분해의 합이 결론 축과 다릅니다 — "
            f"분해 합계 {shortfall.total_won:,.0f}원 · 결론 축 "
            f"{shortfall.npv_won:,.0f}원 · 어긋남 {drift:,.0f}원. "
            "합이 맞지 않는 분해는 「적자가 어디서 오는가」에 답하지 못하므로 "
            "인쇄하지 않습니다. 엔진이 낸 현금흐름 행 밖에서 항을 만들었거나 "
            "행 하나가 어느 묶음에도 들지 않았는지 확인하십시오"
        )
    return shortfall


def _worst(items: Sequence[ShortfallItem]) -> ShortfallItem | None:
    """결손을 **키우는** 항 중 가장 큰 것. 없으면 `None`(전부 유입이다)."""
    adverse = [item for item in items if item.amount_won < 0.0]
    return min(adverse, key=lambda item: item.amount_won) if adverse else None


def _worst_part(parts: Sequence[ShortfallPart]) -> ShortfallPart | None:
    """속항 중 결손을 가장 크게 키우는 것."""
    adverse = [part for part in parts if part.amount_won < 0.0]
    return min(adverse, key=lambda part: part.amount_won) if adverse else None


def _find(items: Sequence[ShortfallItem], key: str) -> ShortfallItem | None:
    return next((item for item in items if item.key == key), None)


def _lead_line(shortfall: Shortfall) -> str:
    """1위 항 문장 — **표에서 골라 짓는다.**

    ⚠ `items[0]` 을 쓰지 않는다. 순서는 `build_shortfall()` 이 정한 성질이고
    이 문장이 말하는 것은 *「어느 항이 가장 큰가」* 다 — 둘을 한 자리에서 묶으면
    정렬을 손대는 순간 문장이 조용히 다른 항을 가리킨다.
    """
    worst = _worst(shortfall.items)
    if worst is None:
        return "- 결손을 키우는 항이 없다 — 세 항이 모두 유입이다"
    share = abs(worst.amount_won) / abs(shortfall.npv_won) if shortfall.npv_won else 0.0
    return (
        f"- 가장 큰 항 — **{worst.label}** {_won(worst.amount_won)} "
        f"(결손 {_won(abs(shortfall.npv_won))}의 {share:.0%}) · "
        # ★ **되짚는 통로다** (R49/WP-4). 이 절은 *어디서 오는가* 까지만 답하고,
        # *무엇을 고치면 얼마가 줄어드나* 는 5.1 의 표가 인자별로 진다.
        f"이 항들을 무엇으로 얼마나 줄일 수 있는지는 {SENSITIVITY_SECTION}"
    )


def _operating_line(shortfall: Shortfall) -> str:
    """운영 단계 문장 — **부호가 판정을 대신한다.**

    이 사업이 *「투자금을 못 갚는」* 정도인지 *「운영 단계부터 매년 더 까먹는」*
    구조인지를 가르는 것은 운영 단계 항의 **부호 하나**다. 그 사실을 문장으로
    박지 않고 부호에서 읽는 이유는 모듈 독스트링에 있다.
    """
    item = _find(shortfall.items, ITEM_OPERATING)
    if item is None:  # pragma: no cover - 항은 언제나 셋이다
        return f"- 운영 단계 — {NO_VALUE}"
    worst = _worst_part(item.parts)
    driver = (
        f" · 그중 가장 큰 지출은 **{worst.label}** {_won(worst.amount_won)}"
        if worst is not None
        else ""
    )
    state = "이미 순지출이다" if item.amount_won < 0.0 else "순유입이다"
    return (
        f"- 운영 단계가 {state} — {shortfall.horizon_years}년 누적 "
        f"{_won(item.amount_won)}{driver}"
    )


def shortfall_section(shortfall: Shortfall) -> list[str]:
    """본문 5.3 — 표 하나와 표에서 지은 두 문장.

    ⚠ **붙임을 새로 만들지 않는다.** 양식 §2 가 본문 부피를 정하므로 표는
    간결하게 세우고, 더 잘게 가른 값은 붙임 4(비용·편익 갈래)가 이미 진다.

    ⚠ **`Shortfall` 만 받는다** — 리포트를 받아 여기서 다시 조립하면 검사가
    「값을 바꾼 표」로 문면을 재 볼 수 없다(`tests/report/test_shortfall.py` 의
    넷째 검사가 그것을 잰다).
    """
    lines = [
        f"### {SECTION_NUMBER} {SECTION_TITLE} — 결손의 항목별 분해",
        "",
        "| 항목 (**굵은 항** 셋만 더한다) | 현재가치 (원) |",
        "|---|---|",
    ]
    for item in shortfall.items:
        lines.append(f"| **{item.label}** | **{_won(item.amount_won)}** |")
        lines += [
            f"| └ {part.label} | {_won(part.amount_won)} |" for part in item.parts
        ]
    lines += [
        f"| **합계 = 결론 축** | **{_won(shortfall.npv_won)}** |",
        "",
        _lead_line(shortfall),
        _operating_line(shortfall),
        "",
    ]
    return lines
