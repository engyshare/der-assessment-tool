"""WP-28A — 잔여 차트 3종 (`dispatch_stack`·`energy_balance`·`model_comparison`).

FR-1004-AC1 이 요구하는 여섯 차트 중 이 셋이 없었다. `core/report/charts.py`
가 열 줄짜리 함수였을 때 이 셋은 존재조차 하지 않았고, 검증하던 테스트는
dict 에 키가 있는지만 보았다 (`core/contracts/chart.py` 참조). 그래서 이
파일의 합격 기준은 「키가 생겼는가」가 아니라 **「PNG 바이트가 실제로
나왔는가」** 다.

기대값은 대부분 손 계산이 아니라 **형식 검증**이다 — PNG 서명·최소 바이트
길이·레지스트리 등록·오류 3요소. 이 셋은 계산값이 아니라 계약 준수 여부이므로
손 계산이 적용되지 않는다 (COMMON.md §2②는 «기대값을 계산한다» 를 요구하며,
형식 검증은 계산할 기대값이 없는 종류다).
"""

from __future__ import annotations

from typing import Any

import pytest

from core.contracts.chart import Chart, ChartArtifact
from core.contracts.validation import ValidationError
from core.report.charts import chart_registry, render_charts
from core.report.charts.dispatch_stack import DispatchStack
from core.report.charts.energy_balance import EnergyBalance
from core.report.charts.model_comparison import ModelComparison

#: PNG 파일 서명. 이것으로 「그렸다」와 「그렸다고 적었다」가 갈린다.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: 24스텝(시간) 대표일 — PV 는 낮에만, ESS 는 저녁 피크에만 방전한다.
#: 값은 임의의 대표일 프로파일이며 요금·단가가 아니므로 대장 대조 대상이
#: 아니다 (docs/assumptions.yaml 은 정책·시장 파라미터만 다룬다).
_PV_PROFILE: tuple[float, ...] = (
    0, 0, 0, 0, 0, 0, 10, 30, 60, 80, 90, 95,
    95, 90, 80, 60, 30, 10, 0, 0, 0, 0, 0, 0,
)
_ESS_DISCHARGE: tuple[float, ...] = (
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 10, 20, 20, 10, 0, 0, 0,
)
_LOAD: tuple[float, ...] = (40.0,) * 24

SAMPLE: dict[str, Any] = {
    "resource_dispatch": {"PV": list(_PV_PROFILE), "ESS": list(_ESS_DISCHARGE)},
    "load": list(_LOAD),
    "production": [1000.0] * 12,
    "self_consumption": [600.0] * 12,
    "export": [400.0] * 12,
    "import": [200.0] * 12,
    "model_comparison": {"기본안": 120000.0, "대안A": 150000.0, "대안B": -30000.0},
}


def _assert_real_png(artifact: ChartArtifact, *, clause: str) -> None:
    assert isinstance(artifact, ChartArtifact)
    assert artifact.payload.startswith(PNG_MAGIC), f"{artifact.tag}: PNG 서명이 아니다"
    assert len(artifact.payload) > 1000, f"{artifact.tag}: 그림이라기에 너무 작다"
    assert artifact.mime == "image/png"
    assert clause in artifact.clauses


@pytest.mark.req("FR-1004-AC1")
def test_dispatch_stack_renders_real_png() -> None:
    """디스패치 스택이 실제 PNG 바이트를 낸다."""
    artifact = DispatchStack().render(SAMPLE)
    _assert_real_png(artifact, clause="FR-1004-AC1")


@pytest.mark.req("FR-1004-AC1")
def test_energy_balance_renders_real_png() -> None:
    """월별 에너지 수지가 실제 PNG 바이트를 낸다."""
    artifact = EnergyBalance().render(SAMPLE)
    _assert_real_png(artifact, clause="FR-1004-AC1")


@pytest.mark.req("FR-1004-AC1")
def test_model_comparison_renders_real_png() -> None:
    """모델 비교 바 차트가 실제 PNG 바이트를 낸다."""
    artifact = ModelComparison().render(SAMPLE)
    _assert_real_png(artifact, clause="FR-1004-AC1")


@pytest.mark.req("FR-1004-AC1")
def test_three_charts_are_registered() -> None:
    """레지스트리가 자동 발견으로 세 `tag` 를 모두 잡는다.

    `core/report/charts/__init__.py` 를 고치지 않았는데도 잡혀야 한다 —
    그것이 이 구획이 파일 하나만 놓으면 되는 이유다.
    """
    registry = chart_registry()
    for tag in ("dispatch_stack", "energy_balance", "model_comparison"):
        assert tag in registry, f"{tag} 가 레지스트리에 없다"
        assert issubclass(registry[tag], Chart)


@pytest.mark.req("FR-1004-AC1")
def test_render_charts_draws_all_three_together() -> None:
    """`render_charts(data)` 로 세 차트가 함께 그려진다."""
    artifacts = render_charts(
        SAMPLE, tags=["dispatch_stack", "energy_balance", "model_comparison"]
    )
    assert set(artifacts) == {"dispatch_stack", "energy_balance", "model_comparison"}
    for artifact in artifacts.values():
        assert artifact.payload.startswith(PNG_MAGIC)


@pytest.mark.req("NFR-303-M1")
def test_dispatch_stack_missing_input_is_three_part_error() -> None:
    """`required_keys` 를 뺀 입력은 필드·사유·조치를 갖춘 오류를 낸다."""
    with pytest.raises(ValidationError) as caught:
        DispatchStack().render({"resource_dispatch": {"PV": list(_PV_PROFILE)}})
    err = caught.value
    assert err.field == "chart.dispatch_stack"
    assert "load" in err.reason
    assert err.action.strip()


@pytest.mark.req("NFR-303-M1")
def test_energy_balance_missing_input_is_three_part_error() -> None:
    """`required_keys` 를 뺀 입력은 `KeyError` 가 아니라 `ValidationError` 다."""
    with pytest.raises(ValidationError) as caught:
        EnergyBalance().render({"production": [1.0] * 12})
    err = caught.value
    assert err.field == "chart.energy_balance"
    assert "self_consumption" in err.reason
    assert err.action.strip()


@pytest.mark.req("NFR-303-M1")
def test_model_comparison_missing_input_is_three_part_error() -> None:
    """`required_keys` 를 뺀 입력은 `KeyError` 가 아니라 `ValidationError` 다."""
    with pytest.raises(ValidationError) as caught:
        ModelComparison().render({})
    err = caught.value
    assert err.field == "chart.model_comparison"
    assert "model_comparison" in err.reason
    assert err.action.strip()


@pytest.mark.req("FR-1004-AC1")
def test_dispatch_stack_rejects_mismatched_resolution() -> None:
    """부하와 스텝 수가 다른 자원 시계열은 렌더 전에 거부된다.

    거부하지 않으면 `stackplot` 이 길이가 다른 배열을 조용히 잘라 그리고,
    그림은 만들어지지만 부하가 실제와 다른 시각으로 보인다.
    """
    bad = {**SAMPLE, "resource_dispatch": {"PV": [1.0, 2.0, 3.0]}}
    with pytest.raises(ValidationError, match="시간 해상도"):
        DispatchStack().render(bad)


@pytest.mark.req("FR-1004-AC1")
def test_energy_balance_rejects_mismatched_month_counts() -> None:
    """네 항목의 개월 수가 어긋나면 렌더 전에 거부된다."""
    bad = {**SAMPLE, "export": [400.0] * 11}
    with pytest.raises(ValidationError, match="다릅니다"):
        EnergyBalance().render(bad)


@pytest.mark.req("FR-1004-AC1")
def test_empty_draw_output_is_caught_by_the_contract() -> None:
    """★ 검사가 실제로 잡는지 확인 — 일부러 빈 산출물을 만들어 본다 (COMMON.md §2③).

    `DispatchStack.draw()` 가 `b""` 를 돌려주도록 원숭이패치하면
    `ChartArtifact.__post_init__` 이 막아야 한다. 막지 못하면 「PNG 바이트가
    실제로 나왔는가」검증이 통과만 하고 아무것도 잡지 못하는 검사라는 뜻이다.
    막는 것을 확인한 뒤 반드시 원복한다 — 이 테스트 안에서만 패치한다.
    """
    original_draw = DispatchStack.draw
    try:
        DispatchStack.draw = lambda self, data: b""  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="빈 산출물"):
            DispatchStack().render(SAMPLE)
    finally:
        DispatchStack.draw = original_draw  # type: ignore[method-assign]

    # 원복 확인 — 패치 이전과 같이 다시 정상 렌더된다.
    artifact = DispatchStack().render(SAMPLE)
    assert artifact.payload.startswith(PNG_MAGIC)
