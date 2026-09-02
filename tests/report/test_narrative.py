"""리포트 한 장이 **조항이 정한 순서**로 서는가 — FR-1002-AC1 · UI-7.

`FR-1002-AC1` 은 *「리포트 첫 화면은 영향도 순위로 시작한다. 입력 순·분류 순
나열은 부록으로 보낸다」* 이고 `UI-7` 이 화면에 같은 것을 요구한다. 즉 **절의
순서 자체가 조항**이므로, 여기서 보는 것은 문장이 아니라 자리다.

    영향도가 가정 목록보다 앞에 온다     ← 뒤바뀌면 조항 위반이다
    전환 인자가 순위보다도 앞에 온다     ← FR-1002-AC4 「최상단에 별도 강조」
    ★ 지수 표기가 없다                  ← `1.6e+06` 은 검토자가 읽는 수가 아니다
    미반영 의심을 본문이 말한다          ← 「영향 0」을 조용히 최하위로 두지 않는다
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from core.report._format import _recovery
from core.report.appendix_sections import UNREAD_BY_PIPELINE
from core.report.case_report import CONCLUSION_METRIC, build_case_report
from core.report.method_sections import (
    PERSPECTIVE,
    PERSPECTIVE_QUALIFIER,
    UNCOUNTED_BENEFITS,
    cost_benefit_section,
    method_section,
    resource_detail_section,
)
from core.report.narrative import NONE_IN_RANGE, render_markdown
from core.report.unreflected import DIRECTION_ADVERSE, build_unreflected
from tests.report.conftest import unwired_report, with_variable_om_row

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _markdown(name: str = "scenario_unsubsidized") -> str:
    report = build_case_report(
        _GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS
    )
    return render_markdown(report)


@pytest.mark.req("FR-1002-AC1", "UI-7-AC1")
def test_influence_ranking_comes_before_the_assumption_list() -> None:
    """입력 나열이 위로 올라오면 조항 위반이다."""
    text = _markdown()
    # 조항이 말하는 「영향도 순위」는 **본문**의 것이다. 붙임끼리의 앞뒤는
    # 양식(`docs/report-form-심의보고서.md`)이 정하며 조항 소관이 아니다.
    ranking = text.index("## 5. 결론을 좌우하는 요인")
    listing = text.index("## 붙임 1. 전제 대장 전건")
    assert ranking < listing, (
        "가정 목록이 영향도 순위보다 앞에 있다 — FR-1002-AC1 은 나열을 "
        "붙임으로 보내라고 한다"
    )
    assert text.index("# 붙임") < listing, "전 가정 목록이 본문에 있다"


@pytest.mark.req("FR-1002-AC4")
def test_flipping_factors_are_the_first_section() -> None:
    """결론을 뒤집는 인자가 **맨 앞**이다."""
    text = _markdown()
    flip = text.index("### 5.1 불확실 인자")
    ranking = text.index("## 붙임 2. 영향도 산출 상세")
    assert flip < ranking


def test_no_scientific_notation_reaches_the_reviewer() -> None:
    """★ `1.6e+06` 은 검토자가 읽는 수가 아니다.

    `MC-1` 이 재는 것은 「리포트만 보고 설명할 수 있는가」다. 읽으려면 변환이
    필요한 표기는 그 자체로 미달 사유이며, 그 미달은 **리포트가 아니라
    서식**에서 온 것이라 원인을 짚기도 어렵다.

    ⚠ **`req("FR-1001-AC5")` 를 달지 않았다.** 달아 보았고, 그 순간 매핑표에서
    `FR-1001-AC5` 가 「수동 + MC-1(미수행)」에서 **「자동」으로 바뀌었다** —
    Phase 1 인수를 막고 있는 유일한 차단 수동검증이 표에서 사라진 것이다.
    조항이 재는 것은 **사람의 이해**이고 이 검사가 재는 것은 서식이다.
    spec §16.5 가 *「분류를 규정하는 조항에 수동 항목을 걸지 말라」* 며 막으려는
    자기충족과 같은 형태이므로, 마커 없이 둔다. **읽히지 않는 조항 하나를 얻고
    차단 표시를 잃는 거래는 하지 않는다.**
    """
    text = _markdown()
    offenders = re.findall(r"\d+\.?\d*e[+-]\d+", text)
    assert not offenders, f"지수 표기가 리포트에 남았다: {offenders[:5]}"


def test_no_machine_local_path_reaches_the_reviewer() -> None:
    """★ **절대 경로가 리포트에 새지 않는다.**

    검토자에게 나가는 문서에 개발 기계의 경로(`D:/...` · `/home/...`)가 박히면
    ⓐ `SC-3` 비공개 정보 유입이고 ⓑ 무엇보다 **다른 기계에서 같은 리포트를
    다시 뽑을 수 없다** — 재현 정보로서 쓸모가 없어진다.

    실물을 처음 뽑았을 때 실제로 새어 있었고, 변이를 심어 보니 **이 검사가
    없으면 아무것도 붙들지 않았다.** `req()` 마커는 달지 않았다 — `SC` 표의
    행은 수용기준 파서가 읽는 형식이 아니라 인용하면 매달린 참조가 된다
    (`status-human.md` 7단계의 승격 판단 대기 항목).
    """
    text = _markdown()
    offenders = re.findall(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt)/)\S*", text)
    assert not offenders, f"기계 지역 경로가 리포트에 남았다: {offenders[:3]}"


@pytest.mark.req("FR-1001-AC4")
def test_every_ranked_factor_carries_its_provenance_in_the_same_row() -> None:
    """출처·기준연도·신뢰도가 **같은 행**에 있다.

    별표로 미루면 검토자가 두 표를 대조해야 하고, 그 대조는 `MC-1` 이 금지한
    「부연」에 해당한다 — 대조 방법을 설명해야 하기 때문이다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    section = text[text.index("## 붙임 2. 영향도 산출 상세") : text.index("## 붙임 3.")]
    for entry in report.uncertain_influences:
        row = next(
            line
            for line in section.splitlines()
            if line.startswith(f"| `{entry.variable}` ")
        )
        assert entry.confidence in row, f"{entry.variable}: 신뢰도가 행에 없다"
        assert entry.source in row, f"{entry.variable}: 출처가 행에 없다"


@pytest.mark.req("FR-1002-AC1")
def test_policy_parameters_are_not_ranked_with_the_uncertain_ones() -> None:
    """★ **할인율은 영향도 순위표에 없다** (R33 검토 지적 4).

    영향도 순위가 답하려는 물음은 *「어느 자료를 먼저 확보할 것인가」*다.
    할인율은 확보할 자료가 아니라 **평가자가 정하는 값**이므로, 한 표에 섞이면
    1위가 「확보 대상」이 아니게 되고 표를 읽은 사람이 우선순위를 잘못 잡는다.

    ⚠ **빼는 것과 버리는 것은 다르다.** 5절에 반드시 있어야 한다 — 할인율
    선택이 결론을 바꾸는 것은 사실이고, 그것을 지우면 리포트가 덜 정직해진다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    ranking = text[text.index("## 붙임 2. 영향도 산출 상세") : text.index("## 붙임 3.")]
    policy = text[text.index("### 5.2 정책 설정값") : text.index("## 6. 종합")]

    assert report.policy_influences, "정책 설정값이 하나도 없다 — 전제가 바뀌었다"
    for entry in report.policy_influences:
        assert f"`{entry.variable}`" not in ranking, (
            f"{entry.variable} 은 정해 놓고 쓰는 값인데 영향도 순위에 섞였다"
        )
        assert f"| `{entry.variable}` " in policy, (
            f"{entry.variable} 이 5절에도 없다 — 빼는 것과 버리는 것은 다르다"
        )


@pytest.mark.req("FR-1005-AC1")
def test_reproduction_appendix_carries_what_another_agent_needs() -> None:
    """★ **다른 사람이 이 결과를 다시 낼 수 있는가** (R33 검토 지적 5).

    매니페스트 해시만으로는 부족하다 — 해시는 **같은지 다른지**만 말하고
    어떻게 만드는지는 말하지 않는다. 명령 · 입력 좌표 · 규약 · 대조 수단 넷이
    다 있어야 「해 보았더니 다른 수가 나왔다」가 어디서 갈렸는지 말할 수 있다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    appendix = text[text.index("## 붙임 5. 재현 절차") :]

    assert "app.run.report_cli" in appendix, "재현 명령이 없다"
    assert report.scenario_name_slug in appendix, "어느 시나리오인지 없다"
    assert report.manifest_hash in appendix, "대조할 매니페스트 해시가 없다"
    assert report.assumption_set_version in appendix, "전제 대장 판이 없다"
    assert f"{report.basis.horizon_years}년" in appendix, "분석기간이 없다"
    assert "e2e_runner" in appendix, "설비 제원의 소유자를 밝히지 않는다"


@pytest.mark.req("FR-1001-AC2")
def test_the_report_says_what_it_evaluated_and_how() -> None:
    """★ **대상과 방법이 리포트 안에 있다** (R33 검토 지적 1·3).

    첫 판은 결론과 민감도만 실었다 — 검토자는 *무엇을 평가했는지* 모르는 채
    *그 결론이 무엇에 민감한지*를 읽었고, 그것으로 `MC-1` 의 「이 회수기간이
    왜 이 값인가」에 답할 수는 없다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    model = text[text.index("## 2. 평가 개요") : text.index("## 3. 평가 방법")]

    assert report.basis.resources, "평가 대상 자원이 비어 있다"
    for resource in report.basis.resources:
        assert resource.kind in model, f"{resource.kind} 가 대상 표에 없다"
        assert resource.capacity in model, f"{resource.kind}: 용량이 없다"
        assert f"{resource.lifetime_years}년" in model, f"{resource.kind}: 수명이 없다"

    method = text[text.index("## 3. 평가 방법") : text.index("## 4. 평가 결과")]
    assert "이 평가가 하지 않은 것" in method, "한계를 밝히지 않는다"
    assert report.basis.dispatch_note in method, "시간 해상도 규약이 없다"


@pytest.mark.req("FR-1001-AC2")
def test_each_resource_shows_what_it_cost_and_what_it_earns() -> None:
    """★ **자원마다 얼마를 넣고 얼마를 버는가** (R33 검토 지적 2).

    지적 원문은 *「pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이 적정한지는
    어떻게 보는가」*였다. 연 편익을 한 덩어리로만 실으면 답할 자리가 없다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    section = text[text.index("### 4.3 자원별 수지") : text.index("## 5. 결론을 좌우하는 요인")]
    detail = text[text.index("## 붙임 4.") : text.index("## 붙임 5.")]

    assert report.basis.benefits, "편익 갈래가 비어 있다"
    for line in report.basis.benefits:
        # 편익 갈래 표·산식은 **붙임 4 로 내렸다** — 본문 4.4(적정 용량)가
        # 들어오며 본문이 양식의 분량 규정을 넘었기 때문이다. **버린 것이
        # 아니라 옮긴 것**이므로 붙임에 있는지 본다. 본문이 지는 것은
        # 「자원마다 얼마를 넣고 얼마를 버는가」의 대조표 하나다.
        assert line.label in detail, f"{line.tag}: 편익 갈래가 붙임 4 에 없다"
        assert f"{line.annual_won:,}원" in detail, f"{line.tag}: 금액이 없다"
        assert line.formula in detail, f"{line.tag}: 산식이 붙임 4 에도 없다"
        assert f"{line.annual_won:,}원" in section, (
            f"{line.tag}: 자원별 수지표가 그 자원의 연 편익을 싣지 않는다"
        )
    for resource in report.basis.resources:
        assert f"{resource.capex_won:,}원" in section, (
            f"{resource.kind}: 초기투자가 수지표에 없다"
        )


@pytest.mark.req("FR-1001-AC2")
def test_each_cost_item_shows_its_amount_and_formula() -> None:
    """★★ 편익의 **반대편** — 비용도 항목·금액·산식으로 실린다 (R34).

    위 검사가 편익 갈래를 붙드는 동안 비용 쪽에는 같은 자리가 없었다. 그래서
    붙임 4 의 「비용 항목」 표를 통째로 지워도 **아무것도 빨간불이 되지 않았다**
    (2026-08-17 실측 · 변이 6a). 그 상태가 위험한 이유는 R34 가 이미 한 번
    밟았다 — 합계 하나(「1년차 운영비 200,000원」)만 있는 표에서는 **빠진 행이
    드러나지 않고**, 계통에서 산 전력이 값 없이 쓰이는 동안에도 그 수는
    그럴듯했다.

    산식까지 보는 이유: 금액만 실으면 검토자가 수량과 단가 중 어느 쪽이
    틀렸는지 가릴 수 없고, 그 둘은 서로 다른 사람이 고친다(단가는 대장,
    수량은 운전).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    # ★ **절을 만드는 함수에 직접 묻고, 그 결과가 문서에 실리는지 따로 본다.**
    # 렌더된 문면만 보면 「붙임 4 를 짓는 코드」와 이 검사가 이름으로 이어지지
    # 않아, `method_sections.py` 를 고치는 사람이 여기를 함께 보지 않는다
    # (`check_test_accompaniment` 가 그것을 잡는다).
    detail = "\n".join(resource_detail_section(report.basis))
    assert detail in render_markdown(report), "붙임 4 절이 문서에 실리지 않았다"

    assert report.basis.costs, "비용 항목이 비어 있다"
    for line in report.basis.costs:
        assert line.label in detail, f"{line.tag}: 비용 항목이 붙임 4 에 없다"
        assert f"{line.annual_won:,}원" in detail, f"{line.tag}: 금액이 없다"
        assert line.formula in detail, f"{line.tag}: 산식이 없다"
    assert f"**{report.basis.annual_cost_won:,}원**" in detail, (
        "비용 항목 표에 합계가 없다 — 항목만 있으면 본문의 「1년차 운영비」와 "
        "이 표가 같은 것을 말하는지 검토자가 맞춰 볼 수 없다"
    )


@pytest.mark.req("FR-1001-AC2")
def test_the_resource_table_carries_the_costs_that_belong_to_no_resource() -> None:
    """★★ 4.3 이 **자원에 붙지 않는 운영비**를 잔차로 싣는다 (R34).

    자원별 수지표는 자원마다 고정 운영비만 세므로, 계통 전력 구매·정산 수수료가
    **표에서 사라진다.** 사라지면 「연 순편익」과 「단순 회수」가 실제보다 좋게
    나오고, 합계를 적지 않는 표에서 그 차이는 아무에게도 보이지 않는다.

    그 잔차 행을 지우는 변이가 **리포트 스위트 전건에서 초록불**이었다
    (2026-08-17 실측 · 변이 6b).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    basis = report.basis
    attributed = sum(r.fixed_om_won_per_year for r in basis.resources)
    unattributed = basis.annual_cost_won - attributed
    assert unattributed, (
        "이 구성은 자원에 귀속되지 않는 운영비(계통 전력 구매)를 가져야 한다 — "
        "0이면 이 검사가 잔차 행의 부재를 정당한 상태로 읽는다"
    )

    # 위 검사와 같은 이유로 절을 만드는 함수에 직접 묻는다.
    section = "\n".join(cost_benefit_section(basis))
    assert section in render_markdown(report), "4.3 절이 문서에 실리지 않았다"

    assert "자원 미귀속" in section, "자원에 붙지 않는 운영비가 4.3 에서 사라졌다"
    assert f"{unattributed:,}원" in section, (
        f"자원 미귀속 운영비 {unattributed:,}원이 4.3 에 실리지 않았다 — "
        "자원 행의 합만 보면 연 순편익이 실제보다 좋게 읽힌다"
    )


#: ★ **밖에서 고정한 4.3 오라클** (R43-E2 · WP-E 가 실측했다). 검사가 스스로
#: 계산하면 귀속 규칙이 바뀔 때 기대값도 함께 따라가 **아무것도 붙들지 않는다.**
#:
#:     계통 송전 18.80kWh = 태양광 10.80 + 저장장치 8.00   (붙임 7 대표일)
#:     잉여 판매 754,820원 → 433,620원 / 321,200원
#:     첨두 절감 199,680원 → 저장장치 전액
#:     연 편익 몫  태양광 433,620원 · 저장장치 520,880원 (합 954,500원)
#: R48 이 재산출했다(WP-F, 2026-08-31) — ESS 운전 축이 §11 판정(잉여는 ESS 로 ·
#: 저녁·피크 방전 · 모자라면 용량만큼만)으로 바뀌고 가구 부하가 본 실행에 서면서
#: PV 잉여(따라서 `SurplusSale` 총량)가 크게 줄고 `PeakShaving` 이 새로 붙어
#: 귀속 자체가 갈렸다 — `attribution.py`(이 라운드에서 건드리지 않은 코드)의
#: 산식이 아니라 **입력 경제성이 움직인 결과**다(§9). 손으로 고치지 않았다 —
#: `docs/evidence/MC-1-검토용-리포트-2026-08-31.md` 의 4.3 표를 그대로 옮겼다.
#:
#: ★ **R51/WP-6 이 다시 재산출했다**(2026-09-02) — 사용자 판정 §1 에 따라 낮
#: 전기의 배분 **기본값**이 「배터리 우선」에서 **「집 우선」**으로 뒤집혔다
#: (`core/casegrid/pv_allocation.py::PV_ALLOCATION_PRIORITY_DEFAULT`). 가구가
#: 그 스텝의 PV 를 먼저 쓰므로 계통 역송이 줄고, **역송 수량으로 안분되는**
#: `SurplusSale` 의 총량과 자원별 몫이 함께 움직였다(태양광 43,954 →
#: 25,274원 · 저장장치는 `PeakShaving` 을 더해 298,106 → 176,626원). 여기서도
#: `attribution.py` 는 건드리지 않았다 — 움직인 것은 **운전**이다. 손으로
#: 고치지 않았다 — `docs/evidence/MC-1-검토용-리포트-2026-09-02.md` 의 4.3
#: 표를 그대로 옮겼다(R48 이 이 자리에서 한 것과 같은 방식).
#: ⚠ **R52/WP-6 이 값을 갱신했다** — REC 편익(0 → 70원/kWh)이 자원별 몫으로
#: 더해져 두 행 모두 연 편익이 늘었다(태양광 +16,123원 · ESS +64,907원).
_ATTRIBUTED_PAYBACK = (
    ("태양광 (옥상 고정형)", "41,397원", "-58,603원", "회수 불가"),
    ("에너지저장장치 (신품)", "241,533원", "141,533원", "35.3년"),
)

#: 종전 4.3 이 표 아래에 **문장으로 박아 두었던** 성립 조건. 이 실행에서
#: 거짓이었고(잉여 판매의 근거 수량에 저장장치 방전분이 섞여 있다) 그 거짓을
#: 재는 자리가 없었다. **되돌아오면 이 검사가 먼저 빨간불이 되어야 한다.**
_RETIRED_ONE_TO_ONE_SENTENCE = "편익이 자원에 1:1 로 귀속될 때"


@pytest.mark.req("FR-1001-AC2")
def test_the_resource_table_splits_a_benefit_that_two_resources_earned() -> None:
    """★★★ 4.3 이 **자기가 적어 둔 성립 조건을 지킨다** (R43-E2 · 문의사항 가-2).

    표는 *「편익이 자원에 1:1 로 귀속될 때」* 를 성립 조건으로 적으면서 잉여
    판매 754,820원 **전액**을 태양광 몫으로 실었다. 그 금액의 근거 수량은 계통
    송전 18.80kWh 이고 그중 8.00kWh 는 **저장장치 방전분**이므로(붙임 7 대표일
    13~16시) 조건이 이 실행에서 **거짓**이었다 — 태양광 단순 회수가 7.3년으로
    인쇄됐고, 심의회에서 *「그럼 태양광만 하면 7년에 회수되는 것 아닌가」* 가
    나오면 그 답이 틀린다.

    ⚠ **결론축은 움직이지 않는다.** 바뀌는 것은 *이미 난 돈을 누구 몫으로
    적는가* 뿐이며 연 편익 합계도 NPV 도 그대로다 — 아래 마지막 단언이 그
    항등식을 잰다. 어느 편익을 켜고 끌지는 사람 판정이다
    (`docs/evidence/판정요구-이중계상-2026-08-29.md`).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    section = "\n".join(cost_benefit_section(report.basis))
    assert section in render_markdown(report), "4.3 절이 문서에 실리지 않았다"

    for kind, earned, net, payback in _ATTRIBUTED_PAYBACK:
        assert f"| {kind} |" in section, f"{kind} 행이 4.3 에서 사라졌다"
        row = next(line for line in section.splitlines() if line.startswith(f"| {kind} |"))
        assert row.endswith(f"| {earned} | {net} | {payback} |"), (
            f"{kind} 의 연 편익·순편익·단순 회수가 밖에서 고정한 값과 다르다: {row}"
        )

    assert _RETIRED_ONE_TO_ONE_SENTENCE not in section, (
        "4.3 이 「1:1 귀속」을 다시 무조건으로 선언한다 — 이 구성에서 그것은 "
        "거짓이며, 그 거짓이 표 아래에 인쇄되던 것이 이 검사가 고치러 온 상태다"
    )


@pytest.mark.req("FR-1001-AC2")
def test_the_resource_table_states_an_attribution_that_is_true_of_this_run() -> None:
    """★★ 성립 조건을 **문장이 아니라 실행에서 짓는다** (R43-E2).

    앞 검사가 *수*를 붙든다면 여기는 *문면이 그 수의 조건을 말하는가*를 붙든다.
    갈래마다 **누구에게 얼마가 · 어떤 수량 근거로** 갔는지가 표 아래에 있어야
    하고, 마지막 줄의 **귀속 합 = 연 편익 합계**가 4.3 과 프로포마가 같은
    편익을 말한다는 유일한 증거다.

    ⚠ 「1:1 귀속」이라는 말은 **자원 하나에만 간 갈래에만** 붙어야 한다. 이
    단언이 없으면 표가 갈린 갈래에도 1:1 을 붙일 수 있고, 그것이 종전 상태다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    basis = report.basis
    section = "\n".join(cost_benefit_section(basis))

    split = [
        line for line in basis.benefits
        if len([s for s in basis.benefit_attributions if s.tag == line.tag]) > 1
    ]
    assert split, (
        "이 구성에는 두 자원이 함께 만든 편익이 있어야 한다 — 없으면 아래 "
        "단언이 공허하다(계통 송전에 저장장치 방전분이 섞여 있다)"
    )

    for share in basis.benefit_attributions:
        assert share.basis_note in section, (
            f"{share.tag}/{share.resource_name} 의 안분 근거가 표 아래에 없다"
        )
    for line in split:
        marked = next(
            row for row in section.splitlines() if row.lstrip().startswith(f"- {line.label} ")
        )
        assert "1:1" not in marked, (
            f"{line.tag} 은 두 자원에 갈렸는데 표가 1:1 귀속이라고 말한다: {marked}"
        )

    assert (
        f"귀속 합계 **{basis.annual_benefit_won:,}원** = 연 편익 합계 "
        f"**{basis.annual_benefit_won:,}원**"
    ) in section, (
        "귀속 합과 연 편익 합계가 같다는 줄이 없거나 두 수가 다르다 — 다르면 "
        "4.3 의 「연 편익」 열이 프로포마가 쓴 편익과 다른 사업을 말한다"
    )


@pytest.mark.req("FR-1002-AC4")
def test_the_flip_condition_table_is_never_left_empty() -> None:
    """★ 6.2 가 **머리만 남은 빈 표**로 인쇄되지 않는다 (R34 · 실물을 읽고 찾았다).

    전환 인자가 0건이 되자 이 표는 행이 하나도 없는 채로 나왔다. 검토자에게
    빈 표는 *「없다」* 와 *「싣지 못했다」* 를 구별해 주지 않고, 1절 요약은 같은
    사실을 이미 「없음」으로 적고 있어 **두 자리가 다른 말을 하는 것처럼**
    읽힌다.

    ⚠ 「없음」을 문장으로 박지 않는다 — 전환 인자가 생기면 그 행이 대신
    들어와야 하므로, 여기서는 **어느 경우에도 행이 있다**를 본다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    section = text[
        text.index("### 6.2 결론 전환 조건") : text.index("### 6.3 미해소 항목")
    ]
    rows = [
        line
        for line in section.splitlines()
        if line.startswith("|") and not line.startswith("|---")
    ]

    assert len(rows) >= 2, f"6.2 표에 머리 말고 행이 없다 — {rows}"
    if not report.flipping:
        assert NONE_IN_RANGE in section, (
            "전환 인자가 0건인데 그 사실을 적은 행이 없다 — 요약(1절)은 이미 "
            f"「{NONE_IN_RANGE}」 로 적고 있다"
        )


@pytest.mark.req("FR-1002-AC3")
def test_unread_variable_is_called_out_in_the_body() -> None:
    """변동폭 0 을 **「영향 최하위」로 흘려보내지 않는다.**

    ⚠ 종전 이 검사는 *「계산이 이 인자를 읽지 않고 있을 가능성이 크다」* 라는
    **경고 문장**을 찾았다. 양식 0절이 해설을 금지한 뒤로는 같은 사실을
    `산출` 열의 라벨과 3.4 미반영 표가 나른다 — 문장이 아니라 **자리**를
    본다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    limits = text[text.index("### 3.4 이 평가가 하지 않은 것") : text.index("## 4. 평가 결과")]
    ranking = text[text.index("## 붙임 2. 영향도 산출 상세") : text.index("## 붙임 3.")]

    for entry in report.unread_variables:
        row = next(
            line
            for line in ranking.splitlines()
            if line.startswith("| ") and f"`{entry.variable}`" in line
        )
        assert UNREAD_BY_PIPELINE in row, (
            f"{entry.variable}: 변동폭 0 이 「영향 최하위」로만 실렸다 — "
            "산출 열이 미반영을 말해야 한다"
        )
        assert entry.variable in limits, (
            f"{entry.variable}: 미반영 인자가 본문 3.4 에 없다"
        )


@pytest.mark.req("FR-607-AC1")
def test_baseline_is_the_first_row_of_the_variant_table() -> None:
    """무지원 기준선이 변형 표 맨 위다 — 「결과 상단에 표시」."""
    report = build_case_report(
        _GOLDEN / "scenario_subsidy_80.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    section = text[text.index("### 4.2 지원 유무 비교") : text.index("### 4.3")]
    # 머리행(`| 변형 | …`)에도 「무지원 대비 증분」때문에 「원」이 들어 있다.
    # 그래서 문자열 포함이 아니라 **금액 칸이 있는 행**을 고른다.
    rows = [
        line
        for line in section.splitlines()
        if re.match(r"^\| [^|]+\| [\d,-]+원 \|", line)
    ]
    assert rows, "변형 표에 금액 행이 하나도 없다"
    assert rows[0].startswith("| 무지원 기준선 "), f"기준선이 맨 위가 아니다: {rows[0]}"


def test_resources_outliving_the_horizon_are_flagged_as_uncosted() -> None:
    """★ **분석기간 안에 수명이 끝나는 자원을 리포트가 스스로 짚는다.**

    ⚠ **`req("FR-104-AC2")` 를 달지 않았다.** 그 조항은 *「EOL 도달 시 교체비를
    **계상**한다」* 인데 이 검사가 보는 것은 정반대 — **계상하지 않았다는 사실을
    리포트가 밝히는가**다. 마커를 달면 「교체비를 계상한다」가 검증된 것으로
    세어지고, 실제로는 계상되지 않는다.

    ## ★ R39-E 가 배선했다 — 그래서 **두 방향**을 함께 잰다

    종전 실측은 *「`ESS.replacement_schedule()`·`salvage_value()` 는 있으나
    프로포마에 넣는 배포 코드가 0곳」* 이었고, 이 검사는 그 결손이 3.4 에
    **드러나는가**만 보았다. R39-E 가 실행 경로에 배선하면서 그 전제가 깨졌다 —
    **지금 실물 리포트에는 교체비 행이 없어야 맞다.**

    ⚠ **한 방향만 재면 이 검사는 두 번 다 무의미해진다.** 「없어야 한다」만
    재면 *배선이 끊겨도* 초록불이고(3.4 는 그때 행을 내놓는데 아무도 안 본다),
    「있어야 한다」만 재면 지금이 빨간불이다. 그래서 **배선된 리포트와 흐름을
    비운 리포트를 둘 다 렌더링해** 행이 조건 따라 움직이는지를 본다 —
    `test_unreflected.py` 가 같은 배선에 대해 세운 방식과 같고, 헬퍼도 같은
    것(`conftest.unwired_report`)을 쓴다.

    지금 구성은 ESS 수명 17년 · 분석기간 20년이라 **교체가 한 번 일어난다** —
    즉 「대상이 아예 없어서 조용한 것」과 구별해야 하는 구성이며, 그 구별이
    아래 `short` 판정이다.

    ⚠ **문면을 고정하지 않는다.** 「ESS 는 교체비가 빠졌다」로 박아 두면 제원이
    바뀔 때(수명 25년 ESS) 리포트가 틀린 경고를 계속 인쇄하고, 분석기간을
    늘리면 PV 도 대상인데 아무 말도 하지 않는다. 그래서 **수명과 분석기간을
    견주어** 판정한다 — 이 검사도 같은 방식으로 본다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    limits = text[text.index("### 3.4 이 평가가 하지 않은 것") : text.index("## 4. 평가 결과")]

    basis = report.basis
    short = [r for r in basis.resources if r.lifetime_years < basis.horizon_years]

    if not short:
        # 수명이 넉넉하면 대상 자체가 없다 — 배선 여부와 무관하게 조용해야 한다.
        assert "| 교체비 |" not in limits, (
            "수명이 넉넉한데도 「교체비 미계상」 행을 계속 인쇄한다"
        )
        return

    # ① 배선된 지금 — 계상됐으므로 3.4 가 「하지 않은 것」으로 적으면 안 된다.
    assert basis.one_off_flows, (
        "ESS 수명 17년 < 분석기간 20년인데 실행 경로가 일회성 흐름을 하나도 "
        "싣지 않는다 — 배선이 끊겼다면 `_lifecycle_rows` 를 먼저 볼 것"
    )
    assert "| 교체비 |" not in limits, (
        "교체비가 프로포마에 계상됐는데 3.4 가 여전히 「하지 않은 것」으로 "
        "적는다 — 검토자가 반영된 비용을 결손으로 두 번 읽는다"
    )

    # ② 배선이 끊긴 구성 — 그때는 반드시 드러나야 한다.
    unwired_text = render_markdown(unwired_report(report))
    unwired_limits = unwired_text[
        unwired_text.index("### 3.4 이 평가가 하지 않은 것") : unwired_text.index(
            "## 4. 평가 결과"
        )
    ]
    unwired_detail = unwired_text[
        unwired_text.index("## 붙임 8. 미반영 항목") : unwired_text.index("## 붙임 9.")
    ]
    assert "| 교체비 |" in unwired_limits, (
        "실행 경로가 교체 흐름을 싣지 않는데 3.4 에 교체비 행이 없다"
    )
    assert DIRECTION_ADVERSE in unwired_limits, "교체비의 방향이 3.4 에 없다"
    for resource in short:
        assert resource.kind in unwired_detail, (
            f"{resource.kind}(수명 {resource.lifetime_years}년)이 붙임 8 에 없다"
        )


def test_summary_section_stands_alone_for_the_committee() -> None:
    """★ **1절 요약만 읽고도 판단의 뼈대가 잡히는가.**

    양식(`docs/report-form-심의보고서.md`)이 요구하는 셋이 다 있어야 한다 —
    결론 한 문장 · 결론을 좌우하는 요인 · 읽을 때의 유의사항. 심의위원이 본문
    전체를 읽지 않는다는 전제가 그 양식의 근거이며, 요약이 비면 **뒤 절이
    아무리 충실해도 그 전제가 무너진다.**

    ⚠ `req()` 마커는 달지 않았다 — 양식은 이 저장소의 서식 규정이지 spec 조항이
    아니다. `FR-1003` 에 「사람이 읽는 문서」 형식이 신설되면 그때 단다
    (`status-human.md` 7단계).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    assert "## 1. 요약" in text, "요약 절이 없다"
    summary = text[text.index("## 1. 요약") : text.index("## 2. 평가 개요")]

    # ① 결론 한 문장 — 본문의 결론과 **같은 수**여야 한다
    assert str(report.basis.horizon_years) in summary, "요약에 분석기간이 없다"
    assert _recovery(report.recovers_within_horizon) in summary, "회수 판정이 없다"
    assert f"{report.metrics[CONCLUSION_METRIC]:,.0f}원" in summary, (
        "요약의 결론 수치가 본문과 다르다"
    )

    # ② 결론을 좌우하는 요인 — 단독과 결합 **둘 다**
    for entry in report.flipping:
        assert entry.variable in summary, f"{entry.variable} 이 요약에 없다"
    for sweep in report.coupled_sweeps:
        recovering = [
            p for p in sweep.points if p.is_combined and p.recovers
        ]
        if recovering:
            assert sweep.bundle in summary, (
                f"{sweep.bundle}: 결합에서 회수되는데 요약에 없다 — "
                "단독만 실으면 사업을 실제보다 어렵게 그린다"
            )

    # ③ 유의사항 — 있는 것만 적되, 있으면 반드시 적는다
    if report.provisional_warning:
        assert "가정" in summary, "전환 인자의 신뢰도가 요약에 없다"
    unreflected = build_unreflected(report)
    if unreflected:
        assert str(len(unreflected)) in summary, "미반영 건수가 요약에 없다"
        assert "붙임 8" in summary, "미반영 전문의 자리를 가리키지 않는다"


def _benefit_branch_cell(appendix_four: str, label: str) -> str:
    """붙임 4 「편익 갈래」 표에서 `label` 행의 **임자 칸**을 꺼낸다.

    행을 이름으로 찾고 칸을 자리로 꺼낸다 — 문면을 통째로 `in` 으로 보면
    같은 붙임의 다른 표(비용 항목·일회성 흐름)가 우연히 통과시킨다.
    """
    row = next(
        line
        for line in appendix_four.splitlines()
        if line.startswith(f"| {label} |")
    )
    return [cell.strip() for cell in row.strip().strip("|").split("|")][1]


def test_appendix_four_prints_the_two_resource_conventions_side_by_side() -> None:
    """★ 붙임 4 의 「귀속 자원」 칸이 **표마다 다른 규약**을 인쇄한다 (R43-B).

    같은 붙임의 표 셋이 자원을 가리키는데 문면이 셋으로 갈린다:

        비용 항목    →  짧은 코드   `PV` · `ESS` · `—`     (`CostLine.resource_code`)
        일회성 흐름  →  자원 이름   `` `e2e-pv` ``          (`OneOffLine.resource_name`)
        편익 갈래    →  자원 종류   `태양광 (옥상 고정형)`  (**귀속** · 아래 R48-E2)

    **그것이 정상이다** — 앞 둘은 자료형의 규약이 다르고
    (`core/casegrid/models.py` 「두 규약」), 붙임 8 이 조인하는 것은 가운데뿐이다.
    이 검사가 고정하는 것은 *어느 쪽이 옳은가* 가 아니라 **문면이 지금 그대로
    라는 사실**이다: 「일관되게 만들자」로 한쪽을 다른 쪽에 맞추면 골든·수용
    검사가 보는 표가 바뀌고, 그 전에 붙임 8 의 조인이 조용히 빈 교집합이 된다.

    ## ⚠ 편익 갈래는 **셋째 칸이 되었다** (R48-E2)

    종전 이 칸도 짧은 코드였고 그것은 `BenefitLine.resource_code` — 즉 자원의
    **선언**이었다. 그런데 잉여 판매처럼 여러 자원의 송전이 만든 갈래에서
    선언은 임자를 하나로만 적고, 같은 실행이 4.3·2.1 에는 갈린 몫을 인쇄한다.
    그래서 이 칸은 이제 **귀속**(`basis.benefit_attributions`)에서 지으며,
    귀속이 조인하는 키는 `ResourceLine.name` 이므로 인쇄되는 문면은 그 자원의
    `kind` 다. `resource_code` 는 인쇄에서 빠졌을 뿐 **살아 있다** — 러너가
    `e2e_runner.py` 에서 같은 코드로 조인한다.

    읽는 값이 규약을 지키는지는 `tests/casegrid/test_from_resource_conventions.py`
    가, 조인 쪽은 `tests/report/test_unreflected.py` 가 본다. 여기는 **인쇄된
    문면**만 본다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    basis = report.basis
    text = "\n".join(resource_detail_section(basis))
    names = {r.name for r in basis.resources}

    assert basis.one_off_flows, "일회성 흐름이 없다 — 아래 단언이 공허하다"
    for line in basis.one_off_flows:
        assert f"| `{line.resource_name}` |" in text, (
            f"일회성 흐름의 귀속 자원이 자원 이름 {line.resource_name!r} 로 "
            "인쇄되지 않는다"
        )

    for line in basis.costs:
        printed = line.resource_code or "—"
        assert f"| {printed} |" in text, f"비용 항목 귀속 자원 문면이 바뀌었다: {printed!r}"
        assert line.resource_code not in names, (
            f"비용 항목에 자원 이름이 인쇄된다: {line.resource_code!r} — "
            "짧은 코드 규약이 무너졌다"
        )

    kinds = {r.name: r.kind for r in basis.resources}
    for line in basis.benefits:
        cell = _benefit_branch_cell(text, line.label)
        assert cell not in {line.resource_code, ""}, (
            f"{line.tag}: 편익 갈래의 임자가 여전히 선언 코드 "
            f"{line.resource_code!r} 다 — 귀속으로 짓지 않는다"
        )
        for share in basis.benefit_attributions:
            if share.tag != line.tag:
                continue
            assert kinds.get(share.resource_name, "자원 미귀속") in cell, (
                f"{line.tag}: 귀속 자원 {share.resource_name!r} 이 붙임 4 의 "
                f"임자 칸에 없다 — {cell}"
            )
        assert not (names & set(re.findall(r"[\w-]+", cell))), (
            f"편익 갈래에 자원 이름이 인쇄된다 — {cell}"
        )


# ─────────────────────────────────────────────────────────────────────────
# R48-E2 — 붙임 4 「편익 갈래」의 임자가 **귀속**인가
#
# 앞 라운드가 같은 형태의 자리 둘을 닫았다(붙임 1 의 기준값 · 2.1 의 선언
# 목록). 셋째가 이 칸이다 — 잉여 판매를 `PV` 단독으로 적는데 같은 실행이
# 그 금액을 수량으로 갈라 4.3·2.1 에 인쇄하고 있었다.
#
# ⚠ **값을 박지 않는다.** 아래 셋은 금액도 비율도 기대값으로 적지 않고
# `basis` 와 **다른 절의 인쇄물**에서 지어 맞춘다 — 같은 라운드의 다른 WP 가
# ESS 운전 축을 바꾸므로 수는 달라지고 성질만 남아야 한다.
# ─────────────────────────────────────────────────────────────────────────


def _won_amounts(text: str) -> list[int]:
    """문면에 실린 금액을 **자리 순서대로** 전부 꺼낸다."""
    return [int(found.replace(",", "")) for found in re.findall(r"([\d,]+)원", text)]


def _split_branches(basis) -> list:
    """귀속이 **자원 둘 이상으로 갈린** 편익 갈래."""
    return [
        line
        for line in basis.benefits
        if len({s.resource_name for s in basis.benefit_attributions if s.tag == line.tag})
        > 1
    ]


def test_appendix_four_names_the_earner_from_attribution_not_declaration() -> None:
    """★★ 붙임 4 의 임자 칸이 말하는 **자원 집합**이 그 갈래의 귀속 집합과 같다.

    이것이 이 자리의 성질이다 — *「누가 만든다고 선언했는가」* 가 아니라
    *「운전 결과로 누가 벌었는가」* 를 적는가. 선언으로 지으면 갈린 갈래에서
    집합이 작아지고(잉여 판매 → `PV` 하나), 같은 리포트의 4.3·2.1 이 말하는
    집합과 어긋난다.

    ⚠ **양방향으로 잰다.** 「귀속 자원이 다 있는가」만 보면 선언까지 함께
    적는 변이가 통과한다.

    ⚠⚠ **귀속 행을 금액으로 거르지 않는다** (R51/WP-6 이 고쳤다). 종전 이
    단언은 `s.annual_won` 이 참인 행만 모아 견주었고, 그래서 **금액이 0 인
    편익에서 거짓 빨간불**을 냈다 — `REC` 가 화폐화 경로에 서면서(사용자
    판정 §4 · 대장 단가 0) 실제로 그 상태가 났다. 리포트 쪽
    (`method_sections._earner_cell`)은 금액을 보지 않고 **귀속 행 전부로**
    칸을 짓는다. 즉 어긋남의 원인은 리포트가 아니라 **두 집합을 다르게 거른
    것**이었고, 리포트는 일관돼 있었다(실측으로 확인 — `REC` 귀속 행 둘이
    각각 0원으로 실재하고 안분 근거 수량도 `SurplusSale` 과 같다).

    ★ 거르지 않는 편이 **더 강하다** — 몫이 0 인 자원이 임자 칸에서 조용히
    빠지는 것도 이제 걸린다. 이 검사가 원래 잡으러 온 결함(칸을 **선언**으로
    짓는 것)은 그대로 걸린다: 그러면 잉여 판매의 칸이 `PV` 하나가 되는데
    귀속은 둘이다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    basis = report.basis
    text = "\n".join(resource_detail_section(basis))
    kinds = {r.name: r.kind for r in basis.resources}

    assert basis.benefit_attributions, "귀속이 비어 있다 — 아래 단언이 공허하다"
    for line in basis.benefits:
        cell = _benefit_branch_cell(text, line.label)
        attributed = {
            kinds.get(s.resource_name, "자원 미귀속")
            for s in basis.benefit_attributions
            if s.tag == line.tag
        }
        printed = {kind for kind in set(kinds.values()) | {"자원 미귀속"} if kind in cell}
        assert printed == attributed, (
            f"{line.tag}: 붙임 4 가 {printed} 를 임자로 적는데 귀속은 "
            f"{attributed} 다 — 한 리포트가 한 편익의 임자를 두 가지로 말한다"
        )


def test_appendix_four_shows_each_share_and_its_basis_for_a_split_branch() -> None:
    """★ 갈린 갈래는 **자원마다 몫과 안분 근거**가 보인다.

    집합만 맞으면 *「둘이 나눠 벌었다」* 까지는 말하지만 **얼마씩인지**는
    말하지 않는다. 심의회에서 나오는 물음(*「그럼 태양광만 하면」*)은 몫을
    물으므로 붙임이 그 자리를 가져야 한다.

    ⚠ **금액을 박지 않는다.** 몫은 귀속 행에서, 근거 문면은 같은 행의
    `basis_note` 에서 지어 맞춘다 — 여기서 다시 나누면 4.3 이 적는 비율과
    반올림에서 갈릴 수 있고, 그것이 이 칸을 고치러 온 결함이다.

    ⚠ 이 구성에 갈린 갈래가 없으면 검사가 스스로 건너뛴다 — **없는 것을
    있다고 박아 두지 않는다.**
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    basis = report.basis
    split = _split_branches(basis)
    if not split:
        pytest.skip("이 구성에는 갈린 편익 갈래가 없다")

    text = "\n".join(resource_detail_section(basis))
    for line in split:
        cell = _benefit_branch_cell(text, line.label)
        for share in basis.benefit_attributions:
            if share.tag != line.tag:
                continue
            assert f"{share.annual_won:,}원" in cell, (
                f"{line.tag}/{share.resource_name}: 이 자원 몫이 붙임 4 에 없다 — {cell}"
            )
            assert share.basis_note in cell, (
                f"{line.tag}/{share.resource_name}: 안분 근거 문면이 없다 — {cell}"
            )


def test_appendix_four_and_four_three_split_a_branch_the_same_way() -> None:
    """★★ 붙임 4 와 4.3 이 **같은 몫**을 말한다 — 인쇄물끼리 대조한다.

    두 절이 같은 출처를 읽는지는 코드를 봐야 알지만 **검토자가 보는 것은
    인쇄물**이다. 한쪽만 새로 세는 변경이 들어오면 여기가 먼저 빨간불이 된다
    (2.1 ↔ 4.3 을 같은 방식으로 붙든 검사가
    `tests/report/test_overview_sections.py` 에 있다).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    basis = report.basis
    split = _split_branches(basis)
    if not split:
        pytest.skip("이 구성에는 갈린 편익 갈래가 없다")

    appendix = "\n".join(resource_detail_section(basis))
    ledger = "\n".join(cost_benefit_section(basis))
    for line in split:
        cell = _benefit_branch_cell(appendix, line.label)
        note = next(
            row
            for row in ledger.splitlines()
            if row.strip().startswith(f"- {line.label} ")
        )
        # 4.3 의 줄은 「갈래 금액 → 자원 몫 …」이므로 첫 금액을 떼어 낸다.
        assert _won_amounts(cell) == _won_amounts(note)[1:], (
            f"{line.tag}: 붙임 4 가 {cell} · 4.3 이 {note.strip()} 를 말한다 — "
            "한 리포트가 한 편익을 두 가지로 가른다"
        )


#: 3.2 의 비용 행 단서 **문면 그대로**. ⚠ 여기서 조립하지 않는다 — 검사가
#: 기대값을 스스로 지으면 문면이 바뀌어도 같이 바뀌어 아무것도 붙들지 않는다.
_VARIABLE_OM_CAVEAT = "(변동 O&M 미포함 · 3.4)"


def test_the_cost_row_caveat_is_built_from_the_judgement_not_from_a_sentence() -> None:
    """★★ **3.2 의 「미포함」 단서가 붙임 8 의 판정에서 나온다** (R43-C).

    한 줄 안에서 절반은 규약을 지키고 절반은 지키지 않았다 — 실린 항목은
    재어 짓는데 뒤의 단서는 **리터럴로 박혀** 있었고, 종전 문면 *「교체 ·
    잔존가치 미포함」* 은 R39-E 배선 뒤 **거짓이 된 채로 검토용 리포트에
    실려 나갔다.** 남은 「변동 O&M 미포함」은 지금 참이지만 같은 형태이며,
    그것이 낡는 날을 붙드는 자리가 여기다.

    ⚠ **절을 만드는 함수에 직접 묻고, 그 결과가 문서에 실리는지 따로 본다** —
    위 두 검사와 같은 이유다(렌더된 문면만 보면 `method_sections.py` 를 고치는
    사람이 여기를 함께 보지 않는다).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    section = "\n".join(method_section(report))
    assert section in render_markdown(report), "3절이 문서에 실리지 않았다"

    (row,) = [line for line in section.splitlines() if "| 프로포마 비용 행 |" in line]
    assert _VARIABLE_OM_CAVEAT in row, (
        f"3.2 의 비용 행 칸에 「{_VARIABLE_OM_CAVEAT}」 단서가 없다 — 붙임 8 은 "
        "이 항목을 미반영으로 판정했는데 규약 표는 말하지 않는다"
    )
    assert any(i.label == "변동 O&M" for i in build_unreflected(report)), (
        "단서는 붙어 있는데 붙임 8 에 항목이 없다 — 두 자리가 갈렸다"
    )

    # ★ **배선되면 단서가 저절로 사라지고 항목으로 등장하는가.** 사라지지
    # 않으면 이 자리는 여전히 문장이다.
    wired = with_variable_om_row(report)
    wired_section = "\n".join(method_section(wired))
    (wired_row,) = [
        line for line in wired_section.splitlines() if "| 프로포마 비용 행 |" in line
    ]
    assert _VARIABLE_OM_CAVEAT not in wired_row, (
        "변동 O&M 을 비용 행으로 실었는데 「미포함」 단서가 남는다 — "
        "R39-E 뒤의 「교체 · 잔존가치 미포함」과 같은 거짓 문면이다"
    )
    assert "태양광 변동 운영비" in wired_row, (
        "단서는 사라졌는데 실린 항목 목록에 변동 O&M 이 없다 — 규약 표가 "
        "붙임 4 와 서로 다른 사업을 말한다"
    )


# ── R43-G — **검토자가 거꾸로 읽은 자리 둘**을 검사가 붙든다 ─────────────────
#
# 두 검사가 재는 것은 문면의 예쁨이 아니라 **수의 출처**다. 지방정부 담당자가
# 리포트를 읽고 잘못 읽은 자리 다섯 중 셋(나-3·4·7)은 순수 문면이라 붙들 것이
# 없고, 아래 둘만 *「그 수가 어디서 왔는가」* 를 잴 수 있다
# (`docs/evidence/문의사항-지방정부담당자-2026-08-29.md`).

_LEDGER_TALLY = re.compile(r"전제 (\d+)건 중 (\d+)건은 신뢰도 `가정`")


def _ledger_tally(text: str) -> tuple[int, int]:
    """리포트가 인쇄한 (전제 건수, `가정` 건수)."""
    match = _LEDGER_TALLY.search(text)
    assert match is not None, (
        "「전제 N 건 중 M 건은 신뢰도 `가정`」이 리포트에 없다 — 잠정성 칸이 "
        "대장의 신뢰도 구성을 싣지 않으면 「전환 인자에 `가정` 없음」이 "
        "「이 결론은 가정에 기대지 않는다」로 읽힌다"
    )
    return int(match.group(1)), int(match.group(2))


def _ledger_with_one_more_assumed_row(tmp_path: Path) -> Path:
    """실물 대장 + **신뢰도 `가정` 한 건** 을 더한 사본의 경로.

    손으로 적은 대장을 두지 않는 이유는 `conftest.py` 의 탐침과 같다 — 사본은
    대장이 바뀌어도 조용히 옛 값을 들고 있다. 씨앗도 실물에서 고른다.

    ⚠ `track` 을 `fixed` 로 낮추고 `sensitivity` 를 비운다. 스윕 축을 하나
    늘리면 이 사본이 **다른 사업**을 재게 되고, 이 검사가 보려는 것은 사업이
    아니라 **세는 방식**이다.
    """
    data = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    seed = next(
        item for item in data["assumptions"] if item.get("confidence") == "가정"
    )
    probe = copy.deepcopy(seed)
    probe["key"] = f"{seed['key']}.probe_one_more_assumption"
    probe["track"] = "fixed"
    probe["sensitivity"] = None
    data["assumptions"].append(probe)
    path = tmp_path / "assumptions-one-more-assumed.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def test_the_provisional_cell_counts_the_ledger_instead_of_quoting_a_number(
    tmp_path: Path,
) -> None:
    """★ 「전제 N 건 중 M 건이 `가정`」이 **대장을 세어 지어진 값인가** (R43-G).

    ## 무엇이 이 검사를 부르는가

    1. 요약 「잠정성」 칸은 *「전환 인자에 신뢰도 `가정` 없음」* 한 줄이었고,
    검토자가 그것을 **「이 결론은 가정에 기대지 않는다」**로 읽었다 — 실제로는
    전환 인자가 아예 없어 그중에 `가정` 도 없는 것이며 대장은 대부분 `가정`
    이다. 문의사항은 *「이 22 라는 합계는 자료에 없고 내가 절별 소계를 더한
    것이다」* 라고 적는다(나-1).

    그래서 그 합계를 리포트가 싣게 했는데, **문장에 박으면 대장이 늘어난 날
    문장만 참인 채로 남는다.** 이 검사가 그것을 막는다 — 대장에 `가정` 한 건을
    더하고 **두 수가 함께 움직이는가**를 본다. 리터럴이면 움직이지 않는다.
    """
    text = _markdown()
    total, assumed = _ledger_tally(text)
    assert 0 < assumed < total, (
        f"전제 {total}건 중 {assumed}건 — 「일부가 가정」이라는 사실을 재는 "
        "검사인데 전건이거나 0건이면 리터럴과 구별되지 않는다"
    )
    # 요약(1절)과 판정(6.1)이 **같은 문면**을 쓴다. 갈리면 두 자리가 서로 다른
    # 대장을 말하는 것으로 읽힌다.
    assert text.count(f"전제 {total}건 중 {assumed}건") == 2, (
        "잠정성 칸과 6.1 「전환 인자의 신뢰도」 칸이 같은 문면을 쓰지 않는다"
    )

    probe = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml",
        assumptions_path=_ledger_with_one_more_assumed_row(tmp_path),
    )
    moved = _ledger_tally(render_markdown(probe))
    assert moved == (total + 1, assumed + 1), (
        f"대장에 신뢰도 `가정` 한 건을 더했는데 수가 {(total, assumed)} → "
        f"{moved} 다 — 이 문장은 대장을 세지 않고 수를 박아 두었다"
    )


def test_the_break_even_subsidy_rate_is_one_number_in_four_places() -> None:
    """★ 64.2% 가 **요약 · 5.1 · 6.2 · 붙임 3 에서 같은 수인가** (R43-G).

    ## 무엇이 이 검사를 부르는가

    6.2 「결론 전환 조건」은 *「없음 (검토 범위 내)」* 한 줄이었고, 종합만 떼어
    인용한 검토자가 그것을 **「무엇을 해도 회수 못 한다」**로 읽었다 — 같은
    자료의 1. 요약과 5.1 은 *지원율 64.2% 면 전환된다*고 적는데도 그렇다
    (문의사항 나-2). 그래서 6.2 에 지원 행을 넣었다.

    ⚠ **네 번째 자리가 생겼다는 것이 이 검사의 이유다.** 같은 물음에 답하는
    자리가 늘수록 **한 곳이 스스로 환산할 위험**이 커지고, 그 어긋남은 검토자가
    두 표를 대조할 때에야 드러난다. 값의 옳고 그름은 여기서 재지 않는다 —
    그쪽은 `test_conclusion_gap.py` 다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    text = render_markdown(report)
    formula_at = text.index("`s* = s - NPV / I_total`")
    printed = {
        "1. 요약": _percent_after(text, "| 결론 전환 지원율 |"),
        "5.1": _percent_after(text, "- 결론 전환 지원율 — "),
        "6.2": _percent_after(text, "| 지원 (보조율) |"),
        "붙임 3": _percent_after(text[formula_at:], "- 대입값 — "),
    }
    expected = f"{report.break_even_subsidy_rate:.1%}"
    assert set(printed.values()) == {expected}, (
        f"결론 전환 지원율이 자리마다 다르다: {printed} (환산 한 곳이 내는 "
        f"값은 {expected}) — 어느 자리가 스스로 환산했다"
    )


def _percent_after(text: str, marker: str) -> str:
    """`marker` 뒤에 처음 나오는 백분율 문면."""
    start = text.index(marker)
    match = re.search(r"-?\d+\.\d%", text[start : start + 200])
    assert match is not None, f"{marker!r} 뒤에 지원율이 없다"
    return match.group(0)


def test_the_summary_and_the_verdict_carry_the_evaluation_perspective() -> None:
    """★★ **관점 한정이 결론 옆에 있다** (R43-H · 문의사항 나-6).

    3.3 은 관점을 사업주로 두고 *「계상하지 않는 편익 — 사회적 편익」* 이라
    분명히 적는다. 그런데 **1. 요약과 6.1 에는 그 한정이 없었다** — 그리고
    발췌돼 인용되는 절은 3.3 이 아니라 그 둘이다. 한정이 없으면
    *「이 사업의 값어치가 −6,289,675원」* 이라는 진술이 되어 나가고, 지자체가
    지원하는 근거는 정확히 그 **「계상하지 않은」** 쪽에 있다.

    ★ **행 둘을 함께 잰다** (R43-L). 「결론」 행만 재면 그 아래 「결론 축 ·
    순현재가치」 행 — **실제로 발췌돼 인용되는 −숫자원이 있는 자리** — 은
    한정 없이 나갈 수 있다. 나-6 이 지적한 형태가 바로 그것이므로 두 행을
    같은 기준으로 붙든다.
    """
    text = _markdown()
    summary = text[text.index("## 1. 요약") : text.index("## 2. ")]
    verdict = text[text.index("### 6.1") : text.index("### 6.2")]

    for prefix in ("| 결론 |", "| 결론 축 · 순현재가치 |"):
        rows = [line for line in summary.splitlines() if line.startswith(prefix)]
        assert rows, f"요약에 「{prefix.strip('| ')}」 행이 없다"
        assert PERSPECTIVE_QUALIFIER in rows[0], (
            f"요약 「{prefix.strip('| ')}」 행에 관점 한정이 없다 — {rows[0]}"
        )
    assert PERSPECTIVE_QUALIFIER in verdict, "6.1 판정에 관점 한정이 없다"


def test_the_perspective_wording_has_exactly_one_owner() -> None:
    """★ **한정구가 3.3 에서 온다** — 두 곳에 적으면 한쪽만 고쳐진다.

    요약·6.1 이 자기 문장을 지으면 관점이 **세 자리에 각각** 적히고, 3.3 을
    고치는 날 나머지 둘은 옛 관점을 계속 인쇄한다. 그것을 막는 방법은 3.3 이
    쓰는 문면 그 자체로 한정구를 짓는 것이며, **여기서 재는 것은 그 관계**다.

    ⚠ 문면을 이 파일에 베끼지 않는다 — 베끼면 사본이 하나 더 는다. 상수를
    가져와 **3.3 표가 그 상수를 인쇄하는지**만 본다: 상수를 고치면 3.3 도
    함께 움직이고, 그래서 한정구와 3.3 이 갈릴 수 없다.
    """
    text = _markdown()
    method = text[text.index("### 3.3 평가 관점") : text.index("### 3.4")]

    assert PERSPECTIVE in method, "3.3 이 관점 상수를 인쇄하지 않는다"
    assert UNCOUNTED_BENEFITS in method, "3.3 이 미계상 편익 상수를 인쇄하지 않는다"

    for piece in (PERSPECTIVE, UNCOUNTED_BENEFITS):
        head = piece.split("(", maxsplit=1)[0].strip()
        assert head and head in PERSPECTIVE_QUALIFIER, (
            f"한정구가 3.3 의 「{head}」에서 오지 않는다 — 따로 지은 문장이면 "
            "3.3 을 고쳐도 요약·6.1 은 옛 관점을 계속 인쇄한다"
        )
