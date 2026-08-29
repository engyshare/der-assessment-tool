"""**적정 용량 검토** — 본문 4.4 · 붙임 10.

## 왜 이 절이 생겼는가 (2026-08-15 · 검토 지적)

지적 원문: *「ESS, heatpump, p2h 등은 **적정 용량 검토가 선행**되어야 함」*.
옳다. 그리고 확인해 보니 리포트는 그 물음을 **묻지도 답하지도 못하는 상태**
였다 — 용량이 `e2e_runner` 의 모듈 상수였고 어느 케이스 축에도 없었다. 27
케이스를 다 돌려도 3kW·10kWh 한 값이며, 민감도 표에도 오르지 않는다. 즉
*「이 구성이 맞는가」* 는 리포트 밖에 있었다.

## 무엇을 재는가 — **답을 고르지 않고 형태를 잰다**

이 모듈은 최적 용량을 *고르지* 않는다. 용량을 탐색 구간에서 움직여 결론 축이
어떤 **형태**를 그리는지만 잰다:

    단조 증가 → 최선은 구간 상한. 즉 «키울수록 좋다» 이며 **상한을 정하는
                것이 모델 밖에 있다**
    단조 감소 → 최선은 구간 하한. 즉 «작을수록 좋다»
    내부 최대 → 그 점이 적정 용량이다

★ **단조면 적정 용량이 정해지지 않는다.** 그것은 계산이 실패한 것이 아니라
*「용량을 제한하는 것이 이 모델에 없다」* 는 측정 결과다 — 부하 상한도, 지붕
가용면적도, 접속 용량도, 산 전력의 값도 들어 있지 않기 때문이다. 그 사실을
싣는 것이 이 절이 하는 일이고, 그래서 **지적이 말한 「선행」이 어느 순서인지**
가 리포트에서 드러난다.

⚠ **계산되지 않는 점을 버리지 않는다.** 용량을 키우면 정격출력·SOC 같은 자원
제약에 걸려 파이프라인이 거부하는 구간이 생긴다. 그 점을 조용히 빼면 표가
매끈해지고 **제약이 사라진 것처럼 보인다** — 제약이야말로 적정 용량을 정하는
것이므로, 걸린 자리를 값으로 싣는다.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from core.casegrid.ledger_levels import DesignVariable, design_variables
from core.contracts.validation import ValidationError

#: 탐색 구간을 몇 점으로 볼 것인가. 홀수로 두어 기준값이 가운데에 오게 한다.
SAMPLES = 5

SHAPE_INCREASING = "단조 증가 — 구간 상한에서 최선"
SHAPE_DECREASING = "단조 감소 — 구간 하한에서 최선"
SHAPE_INTERIOR = "내부 최적점 있음"
SHAPE_UNDECIDED = "판정 불가 — 계산된 점 2개 미만"

#: 결론 축이 이 폭 안에서 같으면 **움직이지 않은 것**으로 본다 (원).
_FLAT_WON = 1.0

#: 계산되지 않은 점의 **두 갈래** 라벨 (문의사항 나-9).
#:
#: ## ★★ 한 문면으로 둘을 인쇄하면 어느 쪽이든 거짓말이 된다
#:
#: 종전 이 칸은 갈래 없이 **「계산 불가」** 였고 비고 칸에 예외 메시지가
#: 그대로 실렸다 — *「e2e-ess: 방전 계획 6 kW 가 정격출력 5 kW 를 넘습니다」*.
#: 검토자에게 그것은 **프로그램 결함**으로 보인다. 실제로는 표 위 설명대로
#: 자원이 그 조합을 **거부한 것**이며 계산이 실패한 것이 아니다.
#:
#: ⚠ **그렇다고 문면만 바꾸면 반대 방향으로 거짓말이 된다.** 진짜 계산 실패가
#: 났을 때도 「설계 제약」이라 인쇄하면 결함이 정상으로 보인다. 그래서
#: **가르는 근거를 코드가 갖는다** — `ValidationError`(NFR-303 · 필드·사유·조치
#: 셋을 반드시 갖는 **입력 검증** 실패)인가 아닌가다. 자원의 정격출력·SOC·계통
#: 한도 거부와 배타 규칙 거부가 전부 그 형이고, 그 밖의 예외는 결함이다.
#: 짧은 이름. 긴 라벨과 본문 줄이 **둘 다 이것에서 자란다** — 두 곳에 적으면
#: 한쪽만 고쳐지고, 그때 표와 그 아래 줄이 서로 다른 것을 말하는 것처럼 읽힌다.
DESIGN_CONSTRAINT = "설계 제약"
BLOCKED_BY_DESIGN = f"{DESIGN_CONSTRAINT}으로 검토 제외"
BLOCKED_BY_FAILURE = "계산 실패"


@dataclass(frozen=True)
class CapacityPoint:
    """탐색 구간의 한 점."""

    value: float
    #: 결론 축(NPV, 원). 자원 제약에 걸리면 `None`.
    conclusion: float | None
    #: 걸린 제약의 문면. 계산된 점이면 `None`.
    blocked_by: str | None
    #: 걸린 것이 **설계 제약**인가 (`ValidationError`). 계산이 진짜로 실패했으면
    #: `False`. 계산된 점에서는 뜻이 없다 — 위 두 라벨 참조.
    #:
    #: ⚠ **기본값을 두지 않았다.** 두면 새 진입점이 갈래를 정하지 않고도
    #: 지나가고, 그때 인쇄되는 것은 **둘 중 한쪽으로 조용히 기운 문면**이다.
    by_design: bool
    #: 거부한 **입력 필드 경로** (`ValidationError.field`, 예 `ess.power_kw`).
    #: 설계 제약일 때만 있다 — *「이 용량을 쓰려면 무엇을 함께 바꿔야 하는가」*
    #: 가 이 칸에서 나온다. 메시지를 되파싱해 짓지 않는 이유는
    #: `ValidationError.as_dict` 독스트링에 있다.
    blocked_field: str | None


@dataclass(frozen=True)
class CapacityFinding:
    """설계 변수 하나의 용량 검토 결과 — 4.4 의 한 행."""

    variable: str
    label: str
    unit: str
    used_value: float
    points: tuple[CapacityPoint, ...]
    shape: str
    #: 구간 평균 한계 기여 (원/단위). 계산된 점이 둘 미만이면 `None`.
    marginal_won_per_unit: float | None
    #: 계산된 점 중 결론 축이 가장 큰 용량.
    best_value: float | None
    #: 처음 걸린 자원 제약. 없으면 `None`.
    binding_constraint: str | None

    @property
    def bounded(self) -> bool:
        """**적정 용량이 이 모델 안에서 정해지는가.**

        내부 최적점이 있거나 제약에 걸려야 «정해진다». 단조인 채로 구간 끝까지
        가면 그 끝은 *우리가 고른 탐색 구간*이지 사업의 적정값이 아니다.
        """
        return self.shape == SHAPE_INTERIOR or self.binding_constraint is not None


def _sample_values(variable: DesignVariable) -> tuple[float, ...]:
    span = variable.high - variable.low
    step = span / (SAMPLES - 1)
    return tuple(variable.low + step * index for index in range(SAMPLES))


def _solved(points: tuple[CapacityPoint, ...]) -> list[tuple[float, float]]:
    """계산된 점만 `(용량, 결론 축)` 으로. **제약에 걸린 점은 형태 판정에서만
    빠지고 표에는 남는다** — 표에서 빼면 제약이 사라진 것처럼 보인다."""
    return [
        (point.value, point.conclusion)
        for point in points
        if point.conclusion is not None
    ]


def _shape_of(points: tuple[CapacityPoint, ...]) -> str:
    solved = _solved(points)
    if len(solved) < 2:
        return SHAPE_UNDECIDED
    values = [conclusion for _value, conclusion in solved]
    best = max(range(len(values)), key=lambda index: values[index])
    if 0 < best < len(values) - 1:
        # 양옆보다 확실히 높아야 «내부 최적» 이다 — 평평한 구간을 최적으로
        # 읽으면 아무 데나 최적점이 생긴다.
        higher_than_left = values[best] - values[best - 1] > _FLAT_WON
        higher_than_right = values[best] - values[best + 1] > _FLAT_WON
        if higher_than_left and higher_than_right:
            return SHAPE_INTERIOR
    return SHAPE_INCREASING if best == len(values) - 1 else SHAPE_DECREASING


def _marginal(points: tuple[CapacityPoint, ...]) -> float | None:
    solved = _solved(points)
    if len(solved) < 2:
        return None
    span = solved[-1][0] - solved[0][0]
    if not span:
        return None
    return (solved[-1][1] - solved[0][1]) / span


def build_capacity_review(
    probe: Callable[[str, float], float],
    *,
    used: dict[str, float],
) -> tuple[CapacityFinding, ...]:
    """설계 변수마다 탐색 구간을 훑는다.

    `probe` 는 *「그 변수를 이 값으로 두었을 때의 결론 축」* 이다 —
    `core/report/case_report.py::_Sweeper.conclusion_at` 이 그것이며, 1변수
    스윕과 **같은 기계**를 쓴다. 갈라 두면 용량 쪽만 변형(`as_planned`)을 읽지
    않는 어긋남이 생기고, 그때 두 절이 서로 다른 사업을 그린다.

    `used` 는 이 실행이 실제로 쓴 용량이다. 탐색 구간의 `base` 를 그대로 쓰지
    않는 이유는, 러너가 다른 값을 받았을 때 **표만 기준 구성을 가리키는** 것을
    막기 위해서다.
    """
    findings: list[CapacityFinding] = []
    for variable in design_variables():
        points: list[CapacityPoint] = []
        blocked: str | None = None
        for value in _sample_values(variable):
            field: str | None = None
            by_design = False
            try:
                conclusion: float | None = probe(variable.name, value)
                reason: str | None = None
            # ★ **갈래를 예외의 종류로 가른다 (R43-H · 문의사항 나-9).**
            # `ValidationError` 는 자원·배타 규칙이 **입력을 거부한 것**이고
            # (NFR-303 — 필드·사유·조치 셋을 반드시 갖는다), 그 밖의 예외는
            # 결함이다. `except Exception` 하나로 받던 동안 붙임 10 은 둘을
            # 같은 문면(「계산 불가」)으로 인쇄했다.
            except ValidationError as error:
                conclusion, reason = None, _first_clause(str(error))
                by_design, field = True, error.field
                blocked = blocked or reason
            except Exception as error:
                conclusion, reason = None, _first_clause(str(error))
                # ⚠ **`blocked` 에 넣지 않는다.** 그 값이 `binding_constraint`
                # 이고 그것이 `bounded`(적정 용량이 모델 안에서 정해지는가)를
                # 정한다 — **결함은 설계의 상한을 말해 주지 않는다.** 넣으면
                # 예외가 나는 구간이 「제약에 걸렸다」로 세어져 4.4 가
                # *「적정값이 정해진다」* 를 낸다.
            points.append(
                CapacityPoint(
                    value=value,
                    conclusion=conclusion,
                    blocked_by=reason,
                    by_design=by_design,
                    blocked_field=field,
                )
            )
        frozen = tuple(points)
        solved = _solved(frozen)
        findings.append(
            CapacityFinding(
                variable=variable.name,
                label=variable.label,
                unit=variable.unit,
                used_value=used.get(variable.name, variable.base),
                points=frozen,
                shape=_shape_of(frozen),
                marginal_won_per_unit=_marginal(frozen),
                best_value=(
                    max(solved, key=lambda pair: pair[1])[0] if solved else None
                ),
                binding_constraint=blocked,
            )
        )
    return tuple(findings)


def _blocked_label(point: CapacityPoint) -> str:
    """계산되지 않은 점의 **결론 축 칸** — 두 갈래 중 하나."""
    return BLOCKED_BY_DESIGN if point.by_design else BLOCKED_BY_FAILURE


def _blocked_note(point: CapacityPoint) -> str:
    """그 점의 **비고 칸** — *무엇 때문에* 검토에서 빠졌는가.

    설계 제약이면 **거부한 입력 필드**를 가리킨다. 그것이 곧
    *「이 용량을 쓰려면 무엇을 함께 바꿔야 하는가」* 이며, 그 물음이 붙임 10 을
    읽는 이유다(4.4 는 「이 용량이 맞는가」를 묻는다).

    ⚠ **방향을 말하지 않는다** — 「키워야 한다」로 적으면 상한에 걸린 경우에는
    거짓이 된다. `ValidationError` 는 어느 쪽으로 어긋났는지를 `reason` 에
    적으며 그 원문은 주로 내려가 있다.
    ⚠ **조치를 지시하지 않는다** (양식 0절) — 「…하십시오」는 개발자에게 하는
    말이고, 그것을 표에 실으면 보고서가 조치 문서가 된다.
    """
    if not point.by_design:
        return f"자원 제약이 아니다 — {BLOCKED_BY_FAILURE}이며 결함으로 다룬다"
    field = f"`{point.blocked_field}`" if point.blocked_field else "같은 자원의 제원"
    return f"{field} 를 함께 바꾸지 않으면 이 용량은 성립하지 않는다"


def _first_clause(message: str) -> str:
    """제약 문면에서 **무엇에 걸렸는지**까지만 남긴다.

    자원이 던지는 메시지는 「어느 항목이 · 왜 · 어떻게 고치는가」 셋을 담는다
    (`NFR-303-M1`). 셋째는 개발자에게 하는 말이라 표에 실으면 리포트가 조치를
    지시하는 문장이 된다 (양식 0절).
    """
    head = message.split(". ", maxsplit=1)[0]
    return head.split(" — ", maxsplit=1)[-1].strip()


# ── 렌더링 ────────────────────────────────────────────────────────────

#: 적정 용량이 **모델 안에서 정해지지 않는다**는 사실의 라벨.
UNBOUNDED_NOTE = (
    "최선이 탐색 구간의 끝에 있다 — 그 끝은 이 검토가 고른 값이지 "
    "사업의 적정값이 아니다"
)


def _won(value: float) -> str:
    return f"{value:,.0f}원"


def capacity_section(findings: tuple[CapacityFinding, ...]) -> list[str]:
    """본문 **4.4 적정 용량 검토** — 형태와 한계 기여만. 점별 값은 붙임 10."""
    lines = ["### 4.4 적정 용량 검토", ""]
    if not findings:
        return [*lines, "- 설계 변수 — 없음", ""]
    lines += [
        "| 설계 변수 | 사용값 | 탐색 구간 | 한계 기여 | 결론 축의 형태 | 구간 내 최선 |",
        "|---|---|---|---|---|---|",
    ]
    for finding in findings:
        values = [point.value for point in finding.points]
        marginal = (
            f"{_won(finding.marginal_won_per_unit)}/{finding.unit}"
            if finding.marginal_won_per_unit is not None
            else "—"
        )
        best = (
            f"{finding.best_value:g} {finding.unit}"
            if finding.best_value is not None
            else "—"
        )
        lines.append(
            f"| {finding.label} (`{finding.variable}`) | "
            f"{finding.used_value:g} {finding.unit} | "
            f"{min(values):g}~{max(values):g} {finding.unit} | {marginal} | "
            f"{finding.shape} | {best} |"
        )
    lines.append("")
    lines += [
        f"- 산출 — 1변수 스윕 {SAMPLES}점 · 나머지 인자는 기준값 고정 "
        "(점별 결론 축은 붙임 10 · 용어는 붙임 9)",
    ]
    unbounded = [f.label for f in findings if not f.bounded]
    if unbounded:
        lines.append(
            "- 이 모델 안에서 적정값이 정해지지 않은 설계 변수 — "
            f"{' · '.join(unbounded)}. {UNBOUNDED_NOTE}"
        )
    lines.append("")
    return lines


def capacity_appendix(findings: tuple[CapacityFinding, ...]) -> list[str]:
    """붙임 10 — 점별 결론 축과 **걸린 제약**."""
    lines = [
        "## 붙임 10. 적정 용량 검토 상세",
        "",
        "- 산출 — 설계 변수 하나만 움직이고 나머지는 기준값 고정",
        "- 결론 축 — 순현재가치 (원)",
        # ★ **두 갈래를 미리 밝힌다 (R43-H).** 종전 이 줄은 계산되지 않은 점을
        # 전부 「자원 제약에 걸린 것」이라 단정했는데, 표는 그것을
        # 「계산 불가」로 인쇄했다 — **설명과 표가 서로 다른 말을 했고** 검토자가
        # 읽는 것은 표다(문의사항 나-9 가 그 표를 인용했다).
        f"- 계산되지 않은 점은 두 갈래로 갈라 싣는다 — **{BLOCKED_BY_DESIGN}**"
        f"(자원·배타 규칙이 그 조합을 거부한 것) · **{BLOCKED_BY_FAILURE}**"
        "(결함). 거부 원문은 표 아래 주",
        "- 「한계 기여」 — 계산된 양 끝점 사이의 결론 축 변화 ÷ 용량 변화",
        "",
    ]
    if not findings:
        return [*lines, "- 설계 변수 — 없음", ""]
    for finding in findings:
        lines += [
            f"### {finding.label} — `{finding.variable}`",
            "",
            f"| 용량 ({finding.unit}) | 결론 축 | 회수 | 비고 |",
            "|---|---|---|---|",
        ]
        # ★ **원문 메시지를 지우지 않고 주로 내린다 (R43-H).** 원문이 근거다 —
        # 「설계 제약」이라는 우리 판정이 맞는지 검토자가 되짚을 수 있어야 한다.
        notes: list[str] = []
        for point in finding.points:
            if point.conclusion is None:
                # ⚠ 주의 이름도 갈래를 따른다 — 결함의 예외 메시지를
                # 「거부 원문」이라 부르면 그것마저 정상 거부로 읽힌다.
                kind = "거부 원문" if point.by_design else "예외 원문"
                notes.append(f"주{len(notes) + 1}) {kind} — {point.blocked_by}")
                lines.append(
                    f"| {point.value:g} | {_blocked_label(point)} | — | "
                    f"{_blocked_note(point)} (주{len(notes)}) |"
                )
                continue
            recovered = "회수" if point.conclusion >= 0 else "미회수"
            marker = " (사용값)" if point.value == finding.used_value else ""
            lines.append(
                f"| {point.value:g}{marker} | {_won(point.conclusion)} | "
                f"{recovered} | — |"
            )
        lines.append("")
        lines += [f"- {note}" for note in notes]
        if finding.binding_constraint:
            # ⚠ **원문을 여기 한 번 더 적지 않는다 (R43-H).** 위 주가 그것을
            # 들고 있고, 같은 문장을 두 줄에 인쇄하면 검토자는 서로 다른 두
            # 제약으로 읽는다. 이 줄이 답하는 것은 *「어느 제원이 용량을
            # 제한했는가」* 이며 그것은 필드다.
            fields = sorted(
                {
                    point.blocked_field
                    for point in finding.points
                    if point.conclusion is None
                    and point.by_design
                    and point.blocked_field
                }
            )
            listed = " · ".join(f"`{name}`" for name in fields) if fields else "—"
            lines.append(
                f"- 용량을 제한한 {DESIGN_CONSTRAINT} — 거부 필드 {listed} "
                "(거부 원문은 위 주)"
            )
        lines.append(f"- 형태 — {finding.shape}")
        lines.append(
            "- 이 모델 안에서 적정값이 정해지는가 — "
            + ("예" if finding.bounded else "아니오")
        )
        lines.append("")
    return lines


def capacity_summary(findings: tuple[CapacityFinding, ...]) -> str:
    """요약 1절의 **적정 용량** 칸.

    ⚠ **여기서 새 수를 만들지 않는다** — 4.4 가 낸 형태를 그대로 가리킨다.
    심의위원이 요약만 읽고도 *「이 구성이 검토된 것인가」* 를 알아야 하므로
    한 줄을 쓴다: 지금 용량보다 나은 용량이 구간 안에 있으면 그 사실이 결론
    자체보다 먼저 걸리는 물음이다.
    """
    if not findings:
        return "설계 변수 없음"
    better = [
        f"{finding.label} {finding.best_value:g}{finding.unit}"
        for finding in findings
        if finding.best_value is not None
        and finding.best_value != finding.used_value
    ]
    if not better:
        return f"검토 {len(findings)}건 — 사용값이 탐색 구간 내 최선 (4.4)"
    unbounded = sum(1 for finding in findings if not finding.bounded)
    tail = f" · 구간 안에서 적정값 미정 {unbounded}건" if unbounded else ""
    return f"검토 {len(findings)}건 — 구간 내 최선은 {' · '.join(better)}{tail} (4.4)"
