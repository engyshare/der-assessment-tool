import pytest

from core.report.charts import generate_charts
from core.report.excel import generate_excel
from core.report.manifest import create_manifest
from core.report.pdf import generate_pdf
from core.report.sensitivity import rank_influences


@pytest.mark.req("FR-1001-AC1")
def test_influence_ranking_no_input_order() -> None:
    """13.1, 13.2: 영향 인자는 입력 순이 아니라
    민감도 계산에 의한 순위로 제시되어야 함 (FR-1001-AC1)
    """
    # 임의로 한 인자를 매우 지배적으로 만듦
    variables = {
        "A": {"base": 100, "impact": 10},
        "B": {"base": 200, "impact": 5000},  # B가 지배적
        "C": {"base": 300, "impact": 5}
    }
    ranked = rank_influences(variables)
    assert ranked[0]["name"] == "B"  # B가 1위로 나와야 함


@pytest.mark.req("FR-1002-AC1", "FR-1002-AC2", "FR-1002-AC4")
def test_sensitivity_thresholds() -> None:
    """13.1: 임계값 산출 및 여유폭 표시 (FR-1002-AC1, AC2, AC4)"""
    variables = {
        "price": {"base": 100, "impact": 10},
    }
    ranked = rank_influences(variables)
    # mock logic for test
    assert "margin_pct" in ranked[0]
    assert "threshold" in ranked[0]


@pytest.mark.req("FR-1002-AC5", "FR-1002-AC6")
def test_assumption_combinations_and_warnings() -> None:
    """13.3: 가정 결합 표시 및 상단 경고 (FR-1002-AC5, AC6)"""
    # PDF나 리포트에 최악 조건 결합 시 경고가 뜨는지 확인하는 mock
    pdf_content = generate_pdf(has_critical_assumptions=True)
    assert "WARNING" in pdf_content["header"]


@pytest.mark.req("FR-1001-AC2", "FR-1001-AC3", "FR-1001-AC4", "FR-1002-AC3")
def test_formula_triple_representation() -> None:
    """13.4: 산식 3중 표기 및 출처/신뢰도 표시 (FR-1001-AC2~AC4, FR-1002-AC3)"""
    pdf_content = generate_pdf(has_critical_assumptions=False)
    # mock verification
    assert "자연어" in pdf_content["formulas"]
    assert "수식" in pdf_content["formulas"]
    assert "대입값" in pdf_content["formulas"]


@pytest.mark.req("FR-1003-AC1", "FR-1003-AC3")
def test_excel_formulas_and_tu7_decision() -> None:
    """13.5: 엑셀 수식 작성 및 TU-7 결정 적용 (FR-1003-AC1, AC3)"""
    # IRR 등 복잡 수식은 값 + 주석으로 대체해야 함
    wb = generate_excel()
    assert "IRR" in wb
    assert wb["IRR"]["type"] == "value_with_comment"


@pytest.mark.req("FR-1005-AC1", "NFR-101-M1")
def test_manifest_reproducibility() -> None:
    """13.6: 실행 매니페스트 재현성 (비트 단위 동일) (FR-1005-AC1, NFR-101-M1)"""
    manifest1 = create_manifest({"seed": 42, "version": "1.0"})
    manifest2 = create_manifest({"seed": 42, "version": "1.0"})
    assert manifest1.hash == manifest2.hash


@pytest.mark.req("FR-1004-AC1")
def test_dashboard_charts() -> None:
    """13.7: 시각화 차트 생성 (FR-1004-AC1)"""
    charts = generate_charts()
    assert "cashflow_line" in charts
    assert "cost_benefit_pie" in charts
    assert "tornado" in charts


@pytest.mark.req("FR-1001-AC5")
def test_manual_check_mc1_stub() -> None:
    """13.8: 수동 검증 MC-1 명세 스텁 (FR-1001-AC5)
    심의 경험자 3명 대상 설명 재현 테스트를 위한 스텁.
    docs/manual-checks.yaml 에 등재되어야 함.
    """
    pass


@pytest.mark.req("FR-1003-AC2")
def test_pdf_report_sections() -> None:
    """13.9: PDF 심의자료 요약 (FR-1003-AC2)"""
    pdf = generate_pdf()
    assert pdf["sections"] == ["cover", "assumptions", "results", "sensitivity", "conclusion"]
