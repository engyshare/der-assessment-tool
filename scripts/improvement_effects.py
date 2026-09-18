"""**현 상황**과 **개선 방안별 기대효과**를 한 산출물로 낸다 (R71/WP-7).

## 사용자가 요구한 것이 이 둘이다

사용자 판정 2026-09-18(정본 `docs/decisions-2026-09-18-R71.md` §1):

> *「현재 운영 단계에서 수익이 비용보다 작아서 사업성이 나오지 않는 상황이라면
> 추가적인 개선 방안의 적용으로 인한 효과까지 포함하여 분석이 이뤄져야 함. 이
> 경우 현 상황에 대한 분석 결과를 제시하고, 개선 방안을 적용할 때의 기대효과를
> 각각 제시할 수 있어야 함」*

⇒ **§1 이 「지금 왜 안 되는가」, §2 가 「무엇을 바꾸면 얼마나 좋아지는가」다.**

## 방안은 **시나리오 오버레이**로만 표현한다 — 대장을 고치지 않는다

방안 하나 = 기준 시나리오 yaml 에 얹는 오버레이 한 벌이며, 얹는 자리는 넷뿐이다
(`assumption_overrides` · `operation_options` · `design_capacity` ·
`subsidy_rate`). 목록의 정본은 `docs/improvements.yaml` 이고 이 파일은 **그것을
읽어 돌리고 인쇄하는 일만** 한다.

⛔ **`docs/assumptions.yaml` 을 고치지 않는다.** 대장은 「지금 이 사업이 쓰는
값」이고 방안은 「바꾸면」이다 — 같은 파일에 쓰면 기준선이 사라지고 골든 3종이
개선안마다 함께 움직인다(오케 판정 `.orch/R71/WP-7.md` §2①).

## 수는 **전부 다시 잰다** — 어디서도 베끼지 않는다

`.orch/R71/result_5.md` 가 같은 축들을 이미 재 두었으나 그 수를 인쇄하지 않는다.
`build_case_report()` 를 방안마다 한 번씩 돌리고, 현가는 **엔진의 할인 함수**
(`core.cba.metrics.npv` 를 초기투자 0 으로)로 행마다 잰다 — 1년차 값으로 20년을
되짓지 않는다(`core/casegrid/models.py::CashflowSplit` 독스트링이 금한 그것이며,
되짓는 순간 합이 결손과 어긋나 *「답하는 척만 하는 표」* 가 된다).

## ⚠⚠ 이것이 **못 잡는 것**

- **조합.** 방안마다 「기준 + 그 방안 하나」다. §4 의 합계는 **단순 합**이며
  상호작용을 반영하지 않는다 — 함께 적용한 결과가 아니다.
- **실행 가능성.** `precondition`(ⓐ배선·ⓑ구성·ⓒ제도)과 `feasibility`(제도가
  허용하는가)는 **대장이 적은 판정**을 나르는 것이고 이 도구가 판정한 것이 아니다
  (정본은 조사 `.orch/R71/result_9.md` 다). Δ 가 크다고 오늘 되는 것이 아니다 —
  그래서 §2 가 **두 묶음**으로 서고 §4 합계가 `불가`·`미확인` 을 뺀다(R71/WP-10).
- **근거.** `source` 칸이 *「근거 없음 — 크기만 보는 가정」* 인 방안의 Δ 는
  **크기일 뿐이다.** 이 저장소는 *「없는 시장의 수익이 결론의 부호를 만든다」* 를
  반복해 경계해 왔으므로 그 표시를 산출물에 그대로 인쇄한다.
- **화면·계약·회귀.** 이 도구는 리포트 절이 아니다. 골든·사다리·게이트가 그것을
  잰다(오케 판정 §5 ⑦ — *「먼저 도구로 답을 내고, 리포트 절로 승격할지는 사용자가
  그 답을 본 뒤 정한다」*).
- **편익의 갈래별 20년 현가.** 엔진이 만드는 편익 행은 `E2EBenefit` **하나**이고
  갈래별 금액은 1년차로만 있다(`.orch/R71/result_5.md` §1ⓒ). §1 의 편익 표가 그
  자리를 빈칸이 아니라 **글자로** 적는다.

## 갈라 둔 자리 하나 — **방안 대장의 해석은 `improvement_ledger.py` 가 진다**

한 파일에 두니 코드 565줄이 되어 `NFR-206`(500줄)을 넘었고 게이트가 *「파일을
쪼개십시오」* 로 그 조치를 지시했다. 가른 선은 **「대장을 읽는 일」과 「돌려서 재고
인쇄하는 일」** 이며, 저쪽이 서식·거부를 전부 지고 이 파일은 실행·현가·인쇄를 진다.

## 쓰는 법

    export PYTHONUTF8=1
    ./.venv/Scripts/python.exe -m scripts.improvement_effects
    ./.venv/Scripts/python.exe -m scripts.improvement_effects --out <경로>
    ./.venv/Scripts/python.exe -m scripts.improvement_effects --scenario scenario_subsidy_80

⚠ **`-m` 으로 부른다** — 경로로 부르면(`python scripts/improvement_effects.py`)
`sys.path[0]` 이 `scripts/` 가 되어 위 `improvement_ledger` 를 `scripts.` 로 찾지
못한다. `app/run/report_cli.py` 를 `python -m app.run.report_cli` 로 부르는 것과 같은
규약이며, `sys.path` 를 손으로 밀어 넣는 우회(`scripts/negtest_*.py` 가 그렇게 한다)를
쓰지 않는 이유는 그러면 같은 모듈이 **두 이름으로 두 번 적재**되기 때문이다.

기본은 **표준출력**이다. 진행 상황은 `stderr` 로 나간다 — 방안 하나가 6~20초라
그것을 표준출력에 섞으면 산출물이 더러워진다.

⛔ **`DER_REPORT_OUT_DIR` 를 읽지 않는다.** 그 환경변수는 `app/run/report_cli.py`
의 것이고, 이 도구가 같은 자리에 이름을 지어 쓰면 심의·검증 리포트 산출물과
섞인다(오케 판정 §4).

종료 코드: `0` 낸다 · `1` **기준 실행이 골든 기대값과 다르다**(그때 Δ 는 전부 못
쓴다) · `2` 방안 대장·시나리오를 읽지 못한다.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from core.cba.metrics import npv as discounted_sum
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO
from core.contracts.validation import ValidationError
from core.report.case_report import (
    CONCLUSION_METRIC,
    CaseReport,
    build_case_report,
)
from scripts.improvement_ledger import (
    IMPROVEMENTS_PATH,
    REPO_ROOT,
    Effect,
    Improvement,
    choose_without_overlap,
    load_improvements,
)

GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
ASSUMPTIONS_PATH = REPO_ROOT / "docs" / "assumptions.yaml"
DEFAULT_SCENARIO = "scenario_unsubsidized"

def _run(
    scenario_path: Path, overlay: Mapping[str, Any], assumptions_path: Path
) -> CaseReport:
    """기준 시나리오에 오버레이를 얹어 **한 번 돌린다.**

    ⚠ **골든 픽스처를 고치지 않는다** — `tempfile` 안에만 쓴다
    (`tests/report/test_operation_options_wired.py::_report` 와 같은 모양).
    """
    fields: dict[str, Any] = (
        yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    )
    fields.update(overlay)
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / scenario_path.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return build_case_report(path, assumptions_path=assumptions_path)


def _pv(rows: Sequence[CashFlowRow], rate: float) -> int:
    """행 묶음의 현재가치 — **엔진의 할인 함수를 그대로 부른다.**

    초기투자 자리에 `ZERO` 를 넣으면 운영 현금흐름의 현가만 나온다. 할인 계수를
    여기서 다시 쓰면 그것이 사본이 되고, 사본은 러너가 규약을 바꿔도 옛 규칙으로
    그럴듯하게 계속 인쇄한다(`core/report/shortfall.py::_present_value` 와 같은
    판단이며 그 함수는 비공개라 부르지 않는다).
    """
    return int(discounted_sum(ZERO, list(rows), discount_rate=rate))


def _first_year(rows: Sequence[CashFlowRow]) -> int:
    return int(sum(int(row.amounts.get(1, 0)) for row in rows))


def _conclusion(report: CaseReport) -> int:
    return int(report.metrics[CONCLUSION_METRIC])


def _annual_net(report: CaseReport) -> int:
    """1년차 **운영 순수지** — 편익에서 운영비를 뺀 값.

    ⚠ 교체·잔존을 더하지 않는다. 그 행들의 1년차 금액은 전부 0 이라 더해도 값이
    같은데, 더해 적으면 *「1년차 값에 교체·잔존이 들어 있다」* 로 읽힌다.
    """
    split = report.cashflows
    return _first_year(split.benefit) - _first_year(split.operating_cost)


def measure(
    improvement: Improvement,
    *,
    base: CaseReport,
    scenario_path: Path,
    assumptions_path: Path,
) -> Effect:
    """방안 하나를 얹어 재고, **거부되면 그것을 결과로 나른다.**

    ⚠ 거부를 예외로 올리지 않는다 — 거부는 *「지금 그 방안을 표현할 수 없다」*
    는 **발견**이며 산출물 §3 의 내용이다. 값을 바꿔 통과시키지 않는다.
    """
    base_npv = _conclusion(base)
    base_annual = _annual_net(base)
    try:
        report = _run(scenario_path, improvement.apply, assumptions_path)
    except ValueError as exc:
        # ⚠ `ValidationError` 는 `ValueError` 의 하위형이다 — 둘을 함께 적으면
        #   같은 것을 두 번 적는 셈이고, 갈라 적으면 3요소 없는 오류(러너 깊은
        #   곳의 맨 `ValueError`)를 놓친다. `_refusal_text` 가 안에서 가른다.
        return Effect(
            improvement=improvement,
            npv_won=None,
            delta_won=None,
            annual_net_won=None,
            delta_annual_won=None,
            refusal=_refusal_text(exc),
        )
    npv_won = _conclusion(report)
    annual = _annual_net(report)
    return Effect(
        improvement=improvement,
        npv_won=npv_won,
        delta_won=npv_won - base_npv,
        annual_net_won=annual,
        delta_annual_won=annual - base_annual,
    )


def _refusal_text(exc: Exception) -> str:
    """거부 문면 — 3요소가 있으면 **셋을 다** 나른다."""
    if isinstance(exc, ValidationError):
        return f"`{exc.field}` — {exc.reason} ⇒ {exc.action}"
    return f"{type(exc).__name__}: {exc}"


def _won(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


def _head(
    report: CaseReport,
    scenario_path: Path,
    counts: tuple[int, int],
    spent: float,
) -> list[str]:
    """머리말 — *「같은 대장 판에서 나왔는가」* 를 산출물이 스스로 답한다.

    오케 판정 ③이 이 도구를 리포트 «밖»에 두는 대가로 적은 것이 그 물음이며
    (*「같은 대장 판에서 나왔는가를 아무도 안 지킨다」*), 막는 장치가 이 표다.
    """
    return [
        "# 현 상황과 개선 방안별 기대효과",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 기준 시나리오 | {report.scenario_name} (`{scenario_path.name}`) |",
        f"| 분석 설정 대장 | `{ASSUMPTIONS_PATH.relative_to(REPO_ROOT).as_posix()}` "
        f"— {report.assumption_set_name} 판 {report.assumption_set_version} |",
        f"| 기준 실행 매니페스트 | `{report.manifest_hash[:16]}` |",
        f"| 방안 대장 | `{IMPROVEMENTS_PATH.relative_to(REPO_ROOT).as_posix()}` "
        f"— **방안 {counts[0]}건** · 참고(방안이 아닌 것) {counts[1]}건 |",
        f"| 할인율 · 분석기간 | {report.basis.discount_rate:.1%} · "
        f"{report.basis.horizon_years}년 |",
        f"| 실행 시각 | {datetime.now().isoformat(timespec='seconds')} "
        f"(소요 {spent:.0f}초) |",
        "",
        "⚠ **방안은 위 대장 판 위에 얹은 오버레이다.** 대장이 바뀌면 아래 Δ 를 다시 "
        "재야 한다 — 이 표가 그 판을 적는 이유다.",
        "",
        "★★ **크기 순은 실행 순이 아니다 — 근거 축을 함께 보라.** §2 는 Δ 하나로 "
        "세우지 않고 **「근거가 선 것」과 「지금은 못 하는 것」 두 묶음**으로 세우며, "
        "§4 의 합계는 뒤 묶음을 **빼고** 낸다.",
    ]


def _now_section(report: CaseReport) -> list[str]:
    """§1 현 상황 — 검산 줄을 **반드시** 인쇄한다."""
    rate = report.basis.discount_rate
    horizon = report.basis.horizon_years
    split = report.cashflows
    benefit_pv = _pv(split.benefit, rate)
    cost_pv = _pv(split.operating_cost, rate)
    lifecycle_pv = _pv(split.lifecycle, rate)
    outlay = int(report.metrics["initial_outlay_won"])
    npv_won = _conclusion(report)
    drift = benefit_pv - cost_pv - lifecycle_pv - outlay - npv_won
    lines = [
        "## §1 현 상황 — 운영 단계에서 수익과 비용이 각각 얼마인가",
        "",
        f"### 편익 — 1년차는 갈래별 · {horizon}년 현가는 **합계 하나뿐이다**",
        "",
        f"| 편익 갈래 | 1년차 (원) | {horizon}년 현가 (원) |",
        "|---|---:|---:|",
    ]
    for line in report.basis.benefits:
        lines.append(f"| {line.label} | {line.annual_won:,} | (갈래별 현가 없음) |")
    lines += [
        f"| **합계** | **{_first_year(split.benefit):,}** | **{benefit_pv:,}** |",
        "",
        "⚠ **빈칸이 아니라 글자로 적는다.** 엔진이 만드는 편익 행은 `E2EBenefit` "
        "**하나**이고 갈래별 20년 시계열은 합쳐진 뒤라 현가를 낼 자리가 없다 "
        "(`.orch/R71/result_5.md` §1ⓒ). 갈래별 현가가 필요하면 그 자리를 먼저 열어야 "
        "한다 — 이 도구가 되짓지 않는 이유다.",
        "",
        "### 운영비 — 항목별로 두 기준 모두",
        "",
        f"| 운영비 행 | 1년차 (원) | {horizon}년 현가 (원) |",
        "|---|---:|---:|",
    ]
    for row in split.operating_cost:
        lines.append(
            f"| {row.label} | {int(row.amounts.get(1, 0)):,} | {_pv([row], rate):,} |"
        )
    lines += [
        f"| **합계** | **{_first_year(split.operating_cost):,}** | **{cost_pv:,}** |",
        "",
        "### 교체·잔존 — 1년차가 0 인 것이 정상이다 (13·18·20년차에 발생한다)",
        "",
        f"| 행 | {horizon}년 현가 (원) |",
        "|---|---:|",
    ]
    for row in split.lifecycle:
        lines.append(f"| {row.label} | {_pv([row], rate):,} |")
    lines += [
        f"| **순액 합계** | **{lifecycle_pv:,}** |",
        "",
        "### ★ 그 둘의 차 — 운영 단계 순수지",
        "",
        "| 기준 | 편익 | 운영비 | 차(순수지) |",
        "|---|---:|---:|---:|",
        f"| 1년차 | {_first_year(split.benefit):,} | "
        f"{_first_year(split.operating_cost):,} | **{_annual_net(report):,}** |",
        f"| {horizon}년 현가 | {benefit_pv:,} | {cost_pv:,} | "
        f"**{benefit_pv - cost_pv:,}** |",
        "",
        "### ★★ 검산 — 이 표가 결론축과 맞는가",
        "",
        "```",
        f"편익현가 {benefit_pv:,} - 운영비현가 {cost_pv:,} "
        f"- 교체·잔존현가 {lifecycle_pv:,} - 초기투자 {outlay:,}",
        f"  = {benefit_pv - cost_pv - lifecycle_pv - outlay:,}",
        f"  npv = {npv_won:,}",
        f"  어긋남 = {drift:,}원",
        "```",
        "",
    ]
    lines.append(
        "⚠ **어긋남이 0원이 아니면 이 표는 「어디서 오는가」에 답하지 못한다.**"
        if drift
        else "★ **어긋남 0원** — 이 표의 합이 결론축과 원 단위로 같다."
    )
    return lines


#: §2 표의 머리. **`근거 축` 칸이 Δ 옆에 선다** — 크기와 근거를 함께 읽게 하는 것이
#: 이 절의 목적이며(오케 판정 `.orch/R71/WP-10.md` §2④), 두 칸이 떨어져 있으면
#: 사람이 크기만 보고 순서를 실행 순으로 읽는다.
_EFFECT_TABLE_HEAD = (
    "| # | id | 방안 | lever | 조건 | 근거 축 | Δnpv (원) | 적용 후 npv (원) "
    "| Δ 연간 운영 순수지 (원) | 값의 근거 |",
    "|---:|---|---|---|---|---|---:|---:|---:|---|",
)


def _grouped(effects: Sequence[Effect]) -> tuple[list[Effect], list[Effect]]:
    """표현된 방안을 **두 묶음**으로 — 앞이 근거가 선 것, 뒤가 지금 못 하는 것.

    ★ **각 묶음 «안에서»만 Δ 내림차순이다.** 크기 순 하나로 세우면 근거가 가장 얇은
    것이 맨 위에 선다 — `cp_registration`(Δ 1위 · 조사 판정 `불가`)이 실제로 그랬고,
    그러면 표가 *「할 수 있는 것」* 이 아니라 *「크면 좋겠는 것」* 을 위에 둔다
    (오케 판정 `.orch/R71/WP-10.md` §0).
    """
    ranked = sorted(
        (effect for effect in effects if effect.expressed),
        key=lambda effect: -(effect.delta_won or 0),
    )
    return (
        [effect for effect in ranked if effect.improvement.grounded],
        [effect for effect in ranked if not effect.improvement.grounded],
    )


def _effect_rows(effects: Sequence[Effect], *, start: int) -> list[str]:
    """표의 행들 — 번호는 두 묶음에 걸쳐 **이어 센다**."""
    rows = []
    for rank, effect in enumerate(effects, start=start):
        item = effect.improvement
        mark = "★ 근거 없음" if item.unsourced else "대장·선언에 근거"
        rows.append(
            f"| {rank} | `{item.id}` | {item.title} | {item.lever} | "
            f"{item.precondition} | **{item.feasibility}** | "
            f"**{_won(effect.delta_won)}** | "
            f"{_won(effect.npv_won)} | {_won(effect.delta_annual_won)} | {mark} |"
        )
    return rows


def _effects_section(effects: Sequence[Effect], base_npv: int) -> list[str]:
    """§2 개선 방안별 기대효과 — **두 묶음**, 각 묶음 안에서 Δ 내림차순."""
    grounded, ungrounded = _grouped(effects)
    lines = [
        "## §2 개선 방안별 기대효과 — 한 번에 하나씩 적용한 결과",
        "",
        f"기준 `npv` = **{base_npv:,}원**. Δ 는 그 기준 대비이며 방안마다 "
        "**「기준 + 그 방안 하나」**를 돌려 쟀다 — 사용자 문면이 *「각각 제시」* 다.",
        "",
        "★★ **크기 순은 실행 순이 아니다 — 근거 축을 함께 보라.** 아래는 **두 묶음**"
        "이다: 먼저 「근거가 선 것」(`확인`·`조건부`), 그 뒤에 「지금은 못 하는 것」"
        "(`불가`·`미확인`). **각 묶음 안에서만** Δ 내림차순이다. ⚠ 뒤 묶음도 **Δ 를 "
        "그대로 인쇄한다** — *「이만큼 크지만 지금은 못 한다」* 가 정보이므로 「없음」"
        "으로 끝내지 않는다. 판정의 정본은 `.orch/R71/result_9.md` 이고 대장이 그것을 "
        "`feasibility` 칸으로 나른다.",
        "",
        f"### ★ 근거가 선 방안 — `확인` · `조건부` ({len(grounded)}건)",
        "",
        *_EFFECT_TABLE_HEAD,
        *_effect_rows(grounded, start=1),
        "",
        f"### ⛔ 지금은 못 하는 방안 — `불가` · `미확인` ({len(ungrounded)}건) · "
        "**§4 합계에서 뺀다**",
        "",
    ]
    if ungrounded:
        lines += [*_EFFECT_TABLE_HEAD, *_effect_rows(ungrounded, start=len(grounded) + 1)]
    else:
        # ⚠ §3·§5 와 같은 규약 — 묶음이 비어도 절을 지우지 않고 **0건**이라고 적는다.
        lines.append("**0건.** 이 대장의 방안 전부가 `확인` 또는 `조건부` 다.")
    adverse = [
        effect for effect in (*grounded, *ungrounded) if (effect.delta_won or 0) < 0
    ]
    lines += [
        "",
        "⚠ **악화되는 방안을 숨기지 않는다** — 묶음 안의 정렬이 내림차순이므로 Δ 가 "
        f"음수인 방안은 그 묶음 **맨 아래**에 그대로 선다(이번 실행 {len(adverse)}건).",
        "",
        "### 방안마다 — 왜 이것이 방안인가 · 이 값의 근거 · 제도가 허용하는가",
        "",
    ]
    for effect in (*grounded, *ungrounded):
        item = effect.improvement
        lines += [
            f"#### `{item.id}` — {item.title}",
            "",
            f"- **Δnpv** {_won(effect.delta_won)}원 · 적용 후 `npv` "
            f"{_won(effect.npv_won)}원 · Δ 연간 운영 순수지 "
            f"{_won(effect.delta_annual_won)}원",
            f"- **lever** {item.lever} · **조건** {item.precondition}",
            f"- **왜 방안인가** {item.rationale}",
            f"- **값의 근거** {item.source}",
            f"- **제도가 허용하는가 — `{item.feasibility}`** {item.feasibility_source}",
        ]
        if not item.grounded:
            lines.append(
                f"- ⛔ **`{item.feasibility}` 이므로 §4 합계에서 빼었다.** 위 Δ 는 "
                "«크기»이며 *「이만큼 크지만 지금은 못 한다」* 로 읽는다 — 그 크기를 "
                "지우지 않는 이유는 제도가 열리면 무엇이 달라지는지가 정보이기 때문이다."
            )
        if item.unsourced:
            lines.append(
                "- ⚠⚠ **이 방안의 값에는 근거가 없다.** 위 Δ 는 «크기»일 뿐이며 "
                "제도 근거가 서기 전에는 결론의 부호를 이 수에 맡기지 말 것."
            )
        if item.includes_allocation:
            lines.append(
                "- ⚠ **이 방안은 PV 잉여 배분 변경을 포함한다.** 조합이 아니라 "
                "성립 조건이다 — 역송이 0kWh 인 기본 배분에서는 단가를 아무리 올려도 "
                "0kWh 에 곱해져 Δ=0 이다."
            )
        lines.append("")
    return lines


def _refused_section(effects: Sequence[Effect]) -> list[str]:
    """§3 표현할 수 없는 방안 — **0건이어도 절을 지우지 않는다.**"""
    refused = [effect for effect in effects if not effect.expressed]
    lines = [
        "## §3 표현할 수 없는 방안 — 지금 통로로 표현되지 않거나 거부된 것",
        "",
    ]
    if not refused:
        lines += [
            "**0건.** 위 §2 의 방안 전부가 지금 통로(오버레이 넷)로 표현됐다.",
            "",
            "⚠ 「0건」은 *「표현할 수 없는 방안이 세상에 없다」* 가 아니다 — **이 대장에 "
            "적은 것 중에** 거부된 것이 없다는 뜻이다. `.orch/R71/result_5.md` §4 는 "
            "아직 통로가 없는 수입원을 여럿 세어 두었다(TOU 차익거래·분산특구 직거래·"
            "집합 PPA 등은 대장·계약 입력이 선행이다).",
        ]
        return lines
    lines += [f"**{len(refused)}건.**", "", "| id | 방안 | 거부 사유 |", "|---|---|---|"]
    for effect in refused:
        lines.append(
            f"| `{effect.improvement.id}` | {effect.improvement.title} | "
            f"{effect.refusal} |"
        )
    lines += [
        "",
        "⚠ **값을 바꿔 통과시키지 않았다.** 거부는 *「지금 그 방안을 표현할 수 없다」* "
        "는 발견이며 그것이 이 산출물의 일부다.",
    ]
    return lines


def _total_section(effects: Sequence[Effect], base_npv: int) -> list[str]:
    """§4 합계와 그 한계 — **네 수**(A·B·C·D)와 **건너뜀 목록**을 함께 적는다.

    ⛔ **합 하나로는 거짓이 된다.** 이 절은 두 번 고쳐졌다 — 처음에는 `불가`(CP)의
    Δ 를 품어 낙관적이었고(WP-10), 그다음에는 **같은 자리를 쓰는 방안을 여러 번
    세어** *「결손의 9.5%만 남는다」* 로 읽혔다(검수 판정 `.orch/R71/WP-10-fix.md`
    §0). 그 구성 하나를 실제로 적용한 값은 **결손의 49.2%가 남는** 것이었다.

    ⇒ **A 가 쓸 수 있는 수다** — Δ 내림차순으로 훑어 **앞서 고른 것과 겹치지 않는
    방안만** 더한다. B·C 는 「왜 A 가 그보다 작은가」를 보이려고 **함께 두되 쓰지
    말라고 적는다.**
    """
    gains = [
        effect for effect in effects if effect.expressed and (effect.delta_won or 0) > 0
    ]
    grounded = [effect for effect in gains if effect.improvement.grounded]
    picked, skipped = choose_without_overlap(grounded)
    usable = sum(effect.delta_won or 0 for effect in picked)
    doubled = sum(effect.delta_won or 0 for effect in grounded)
    everything = sum(effect.delta_won or 0 for effect in gains)
    remaining = base_npv + usable
    share = remaining / base_npv * 100.0 if base_npv else 0.0
    lines = [
        "## §4 합계와 그 한계",
        "",
        "| 항목 | 값 |",
        "|---|---:|",
        f"| ★ **A — 겹치지 않게 고른 {len(picked)}건의 합** | **{usable:,}원** |",
        f"| B — 근거가 선 **전부**({len(grounded)}건)의 단순 합 | {doubled:,}원 |",
        f"| C — `불가`·`미확인` 까지({len(gains)}건) 더한 합 | {everything:,}원 |",
        f"| 기준 `npv` | {base_npv:,}원 |",
        f"| ★ **D — A 를 적용했을 때 남는 결손** | **{remaining:,}원** |",
        f"| D 가 원래 결손의 | **{share:.1f}%** |",
        "",
        "⛔⛔ **B 는 같은 개선을 여러 번 세므로 사업 판단에 쓰지 마라. 쓸 수 있는 것은 "
        "A 다.** B 에 든 방안들이 **같은 자리**(같은 설계 용량 · 같은 운전 선택 · 같은 "
        "대장 키)를 겹쳐 쓰며, 그 겹침은 단서로 덮을 크기가 아니다 — 아래 목록이 "
        "**무엇이 무엇에 품혔는지** 적는다. C 는 거기에 *「제도가 마련되지 않는 한 0」* "
        "인 크기까지 더한 수다.",
        "",
        f"### A 가 고른 것 {len(picked)}건 · 겹쳐서 건너뛴 것 {len(skipped)}건",
        "",
    ]
    for effect in picked:
        lines.append(f"- ★ **고름** `{effect.improvement.id}` — Δ {_won(effect.delta_won)}원")
    for skip in skipped:
        lines.append(
            f"- **건너뜀** `{skip.effect.improvement.id}` — Δ "
            f"{_won(skip.effect.delta_won)}원 · {skip.reason}"
        )
    lines += [
        "",
        "⚠ **건너뛴 것을 숨기지 않았다 — Δ 를 그대로 적는다.** 건너뜀은 *「그 방안이 "
        "쓸모없다」* 가 아니라 *「이 합 안에서는 이미 세어졌다」* 는 뜻이며, 품은 쪽을 "
        "못 하게 되면 건너뛴 쪽이 다시 후보가 된다. ⚠⚠ 그래도 **A 조차 「함께 적용한 "
        "결과」가 아니다** — 겹치지 않는 자리 사이에도 상호작용이 남는다(실제로 "
        "`small_ess_max_pv_export` 의 Δ 는 그것이 품은 방안들의 단순 합보다 **훨씬 "
        "크다** · 대장 `rationale` 의 실측). ⇒ **A 는 상한도 하한도 아니다.**",
        "",
        "⚠ 결손의 배분도 함께 읽어야 한다 — §1 의 검산 줄이 초기투자·운영·교체잔존을 "
        "가른다. 운영 단계를 전부 고쳐도 초기투자 항은 그대로 남는다.",
    ]
    return lines


def _not_improvements_section(effects: Sequence[Effect]) -> list[str]:
    """§5 참고 — 방안이 **아닌** 것. 「방안이 아니다」와 그 이유를 함께 적는다."""
    lines = [
        "## §5 참고 — 방안이 «아닌» 것",
        "",
        "아래는 **같은 오버레이로 재었으나 방안 목록에서 뺀** 축이다. 크기를 함께 적는 "
        "이유는, 크기를 적지 않으면 *「방안이 아니다」* 만 말하고 **얼마인지 말하지 "
        "못하기 때문**이다. ⛔ **위 §4 합계에 넣지 않았다.**",
        "",
        "| id | 무엇 | Δnpv (원) | 왜 방안이 아닌가 |",
        "|---|---|---:|---|",
    ]
    if not effects:
        # ⚠ §3 과 같은 규약 — 절을 지우지 않고 **0건**이라고 적는다.
        lines += ["| (0건) | — | — | 이 대장에 참고 축이 없다 |"]
    for effect in effects:
        item = effect.improvement
        lines.append(
            f"| `{item.id}` | {item.title} | {_won(effect.delta_won)} | "
            f"{item.why_not or effect.refusal} |"
        )
    lines += [
        "",
        "★ 앞의 둘은 **사업 규모의 지표**로 읽는다 — 그 부하(전기차·냉난방 전기화)가 "
        "이 사업의 목적이므로 *「목적을 지우면 경제성이 좋아진다」* 는 답은 방안이 "
        "아니다(`docs/decisions-2026-09-18-R71.md` §5 ⑤).",
        "",
        "★ 마지막 것은 **부호가 반대인 증거**다 — 「저장장치를 더 넣자」가 이 구성에서 "
        "개선이 아님을 보이며, 그래서 §2 의 `ess_capacity_down`(줄이는 쪽)이 방안으로 "
        "선다.",
    ]
    return lines


def render(
    base: CaseReport,
    effects: Sequence[Effect],
    references: Sequence[Effect],
    *,
    scenario_path: Path,
    spent: float,
) -> str:
    """다섯 절을 한 마크다운으로. **절을 지우지 않는다** — 0건도 인쇄한다."""
    base_npv = _conclusion(base)
    blocks = [
        _head(base, scenario_path, (len(effects), len(references)), spent),
        _now_section(base),
        _effects_section(effects, base_npv),
        _refused_section(effects),
        _total_section(effects, base_npv),
        _not_improvements_section(references),
    ]
    # ⚠ 절 사이에 **빈 줄**을 둔다 — 표·문단 바로 뒤에 붙은 `##` 을 제목으로
    #   읽지 않는 렌더러가 있다.
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"


def _golden_expectation(scenario_path: Path) -> int | None:
    """골든 픽스처가 적은 기대 `npv`. 없으면 `None`.

    ★ **수를 이 소스에 박지 않는다.** 기준 실행이 딴 사업을 그리지 않았는지는
    골든이 이미 아는 사실이며, 박아 두면 골든이 갱신되는 날 이 파일만 옛말을 한다.
    """
    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    expected = (data.get("expected_values") or {}).get("npv_won")
    return int(expected) if isinstance(expected, (int, float)) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.improvement_effects",
        description="현 상황과 개선 방안별 기대효과를 낸다 (R71/WP-7)",
    )
    parser.add_argument(
        "--scenario", default=DEFAULT_SCENARIO, help=f"기준 시나리오 (기본 {DEFAULT_SCENARIO})"
    )
    parser.add_argument(
        "--improvements", type=Path, default=IMPROVEMENTS_PATH, help="방안 대장 경로"
    )
    parser.add_argument(
        "--assumptions", type=Path, default=ASSUMPTIONS_PATH, help="분석 설정 대장 경로"
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="쓸 파일 경로. 주지 않으면 표준출력"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario_path = GOLDEN_DIR / f"{args.scenario}.yaml"
    if not scenario_path.exists():
        print(f"시나리오가 없습니다: {scenario_path}", file=sys.stderr)
        return 2
    try:
        improvements, references = load_improvements(args.improvements)
    except (ValidationError, OSError, yaml.YAMLError) as exc:
        print(f"방안 대장을 읽지 못했습니다 — {exc}", file=sys.stderr)
        return 2

    started = time.monotonic()
    print("기준 실행 …", file=sys.stderr)
    base = _run(scenario_path, {}, args.assumptions)
    base_npv = _conclusion(base)
    expected = _golden_expectation(scenario_path)
    print(f"  기준 npv = {base_npv:,}원", file=sys.stderr)
    if expected is not None and expected != base_npv:
        # ⛔ 여기서 멈춘다 — 오버레이를 얹는 방식이 틀린 것이고 그 위에서 잰 Δ 는
        #    전부 못 쓴다. 기대값을 고쳐 맞추는 것은 이 도구가 할 일이 아니다.
        print(
            f"기준 실행이 골든 기대값과 다릅니다 — 골든 {expected:,} · 실행 "
            f"{base_npv:,} (어긋남 {base_npv - expected:,}). 오버레이를 얹는 방식이 "
            "기준 실행을 바꾸고 있으므로 Δ 를 내지 않습니다",
            file=sys.stderr,
        )
        return 1

    effects: list[Effect] = []
    for group, items in (("방안", improvements), ("참고", references)):
        for index, item in enumerate(items, start=1):
            print(f"{group} {index}/{len(items)} {item.id} …", file=sys.stderr)
            effect = measure(
                item,
                base=base,
                scenario_path=scenario_path,
                assumptions_path=args.assumptions,
            )
            note = (
                f"Δ {effect.delta_won:,}원" if effect.expressed else "거부 — §3 에 적는다"
            )
            print(f"  {note}", file=sys.stderr)
            effects.append(effect)

    text = render(
        base,
        effects[: len(improvements)],
        effects[len(improvements) :],
        scenario_path=scenario_path,
        spent=time.monotonic() - started,
    )
    if args.out is None:
        print(text)
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(
        f"{args.out} 에 썼습니다 — 방안 {len(improvements)}건 · 참고 "
        f"{len(references)}건 · 대장 판 {base.assumption_set_version}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
