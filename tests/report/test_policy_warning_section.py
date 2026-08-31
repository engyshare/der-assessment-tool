"""리포트가 **정책 가정 경고를 상단에 인쇄하는가** — `FR-404-AC1` · R48 §7.

## 무엇이 없었나

조항은 *「활성화 시 경고를 리포트 상단에 표시」* 를 요구하는데, R48 착수 시점에
`core/report/` 안에 `policy_warnings` 를 부르는 곳이 **0곳**이었다. 즉 제도 근거
없는 가정 위에서 편익이 켜져 있어도 리포트는 아무 말도 하지 않았다.

## ★ 왜 **가짜 자원**으로 재는가

기준 실행(PV+ESS)에는 경고가 없다. 실물 실행만으로 재면 *「절이 없다」* 밖에
확인할 수 없고, 그 상태는 **인쇄 코드를 통째로 지워도 초록불**이다. 그래서 경고를
내는 자원 행을 지어 넣는다 — `tests/report/conftest.py::unwired_report` 가 「배선이
끊긴 구성」을 짓는 것과 같은 자리다.

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 문면은 이 파일이 밖에서 지어 넣는다. 실물 자원의
   문구를 베끼지 않는다 — 베끼면 자원이 문구를 다듬을 때 함께 빨간불이 되고,
   재는 것은 문구가 아니라 *그대로 실리는가* 다.
② **이 설명이 이 검사에 걸리는가** — 아니다. 소스 문면을 보지 않는다.
③ **이름보다 넓게 주장하는가** — 아니다. 자원 → `ResourceLine` 통로는
   `tests/casegrid/test_policy_warning_wiring.py` 가 따로 붙든다.
④ **수와 그 조건의 짝** — 이 파일은 어느 수치도 보지 않는다. 경고는 문면이므로
   금액을 움직이지 않는다.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.casegrid.models import ResourceLine
from core.report.case_report import build_case_report
from core.report.narrative import render_markdown
from core.report.policy_warnings import SECTION_HEADING, policy_warning_section

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

#: 지어 넣는 문면 둘. **R48 판정 §6 이 가른 두 갈래를 그대로 쓴다** — 「제도
#: 필요」(제도 자체가 없다)와 「제도 보완 필요」(제도는 있으나 이 사업에 적용할
#: 산정 기준이 없다). 리포트가 그 구분을 **짓지 않고 나르기만** 하는지 보려면
#: 두 갈래가 다 있어야 한다.
_NEEDS_SCHEME = "탐침 — 제도 필요: 이 편익의 제도 자체가 아직 설계 중입니다"
_NEEDS_AMENDMENT = (
    "탐침 — 제도 보완 필요: 제도는 현행이나 이 사업에 적용할 산정 기준이 없습니다"
)


def _line(name: str, *warnings: str) -> ResourceLine:
    """제원은 이 검사가 보는 것이 아니다 — 이름·종류·경고만 뜻이 있다."""
    return ResourceLine(
        name=name,
        kind=f"{name} 종류",
        capacity="—",
        operating_mode="—",
        lifetime_years=20,
        unit_capex="—",
        capex_won=0,
        fixed_om_won_per_year=0,
        produces=(),
        policy_warnings=warnings,
    )


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


@pytest.mark.req("FR-404-AC1")
def test_the_section_prints_every_warning_with_the_resource_it_came_from() -> None:
    """★★ 경고 전건이 **어느 자원의 것인지와 함께** 인쇄된다 (판정 D2-2).

    문면만 나열하면 검토자가 *「무엇에 대한 경고인가」* 를 물을 자리가 없다.
    """
    lines = policy_warning_section(
        (
            _line("탐침-갑", _NEEDS_SCHEME),
            _line("탐침-을"),
            _line("탐침-병", _NEEDS_AMENDMENT),
        )
    )
    body = "\n".join(lines)

    assert lines[0] == SECTION_HEADING, f"절 제목이 맨 위가 아니다 — {lines[:1]}"
    for name, warning in (
        ("탐침-갑", _NEEDS_SCHEME),
        ("탐침-병", _NEEDS_AMENDMENT),
    ):
        carrier = [
            line for line in lines if line.startswith("- ") and name in line
        ]
        assert len(carrier) == 1, f"{name} 의 경고 줄이 하나가 아니다 — {carrier}"
        assert warning in carrier[0], (
            f"{name} 의 문면이 그대로 실리지 않았다 — 「{carrier[0]}」"
        )
    assert "탐침-을" not in body, (
        "경고가 없는 자원이 절에 실렸다 — 경고 절은 경고만 싣는다"
    )


@pytest.mark.req("FR-404-AC1")
def test_the_section_does_not_classify_the_warning_text() -> None:
    """★★ 「제도 필요」와 「제도 보완 필요」의 구분은 **문면이 나른다** (판정 D2-3).

    리포트가 문자열을 보고 갈래를 치면 자원이 문구를 다듬을 때 분류가 조용히
    틀려진다. 그래서 재는 것은 *두 갈래가 서로 다른 글자로 인쇄되는가* 이지
    *리포트가 둘을 알아보는가* 가 아니다 — 리포트는 알아보지 않는다.
    """
    scheme_only = "\n".join(policy_warning_section((_line("갑", _NEEDS_SCHEME),)))
    amendment_only = "\n".join(
        policy_warning_section((_line("갑", _NEEDS_AMENDMENT),))
    )

    assert _NEEDS_SCHEME in scheme_only and _NEEDS_AMENDMENT not in scheme_only
    assert _NEEDS_AMENDMENT in amendment_only and _NEEDS_SCHEME not in amendment_only
    assert scheme_only != amendment_only, (
        "두 갈래가 같은 글자로 인쇄됐다 — 심의회가 요구하는 답이 서로 다르다"
    )


@pytest.mark.req("FR-404-AC1")
def test_no_warning_means_no_section_at_all() -> None:
    """경고가 하나도 없으면 **절 자체가 없다** (판정 D2-2).

    *「해당 없음」* 한 줄을 세우지 않는다 — 상시로 뜨는 경고는 읽히지 않고,
    읽히지 않는 경고는 경고가 아니다.
    """
    assert policy_warning_section(()) == []
    assert policy_warning_section((_line("갑"), _line("을"))) == []


@pytest.mark.req("FR-404-AC1")
def test_the_real_report_prints_the_section_above_the_summary() -> None:
    """★★ **진입점을 지난 리포트**가 경고를 요약보다 위에 인쇄한다.

    ⚠ 절 함수만 재면 **아무도 그것을 부르지 않아도 초록불**이다 — 착수 시점의
    결함이 정확히 그것이었다(`core/report/` 호출자 0곳). 그래서 실물 리포트를
    한 번 뽑아 자원 행만 갈아 끼운다.
    """
    report = _report()
    warned = replace(
        report,
        basis=replace(
            report.basis,
            resources=(
                _line("탐침-자원", _NEEDS_SCHEME),
                *report.basis.resources,
            ),
        ),
    )
    rendered = render_markdown(warned).splitlines()

    assert SECTION_HEADING in rendered, "진입점이 경고 절을 인쇄하지 않았다"
    assert any(_NEEDS_SCHEME in line for line in rendered), (
        "절은 섰는데 문면이 실리지 않았다"
    )
    heading = rendered.index(SECTION_HEADING)
    summary = next(i for i, line in enumerate(rendered) if line.startswith("## 1. "))
    assert heading < summary, (
        f"경고가 요약보다 아래에 있다 — 조항 문면은 「리포트 상단에」다 "
        f"(경고 {heading}행 · 요약 {summary}행)"
    )


@pytest.mark.req("FR-404-AC1")
def test_the_base_report_carries_no_warning_section() -> None:
    """기준 구성(PV+ESS)의 실물 리포트에는 그 절이 **없다.**

    위 검사의 대조군이다 — 절이 상시로 서고 있지 않다는 것을 함께 재야
    「활성화 시」라는 조항 문면이 지켜진 것이 된다.
    """
    rendered = render_markdown(_report())

    assert SECTION_HEADING not in rendered, (
        "경고가 없는 실행에 경고 절이 섰다 — 상시 경고는 읽히지 않는다"
    )
