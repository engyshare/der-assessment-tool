"""`Chart` 계약 테스트 — FR-1004-AC1 · FR-803-AC2 · NFR-207.

**이 파일이 붙드는 것은 「차트가 예쁜가」가 아니라 셋이다.**

  ① 산출물이 **실제 바이트**인가 (문자열 설명이 아니라)
  ② 조항을 가리키지 않는 차트가 등록돼 있지 않은가
  ③ **파일 하나를 놓으면 실제로 레지스트리가 느는가** — 확장점 증명

③ 이 없으면 ①② 는 「지금 있는 세 개가 괜찮다」는 말일 뿐이고, 그것은
확장점이 있다는 근거가 되지 못한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.contracts.chart import Chart, ChartArtifact
from core.contracts.validation import ValidationError
from core.report.charts import chart_registry, render_charts

#: PNG 파일 서명. 이것으로 「그렸다」와 「그렸다고 적었다」가 갈린다
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

SAMPLE: dict[str, object] = {
    "cashflows": [-1000.0, 200.0, 300.0, 400.0, 500.0],
    "items": {"설비비": 1200.0, "시공비": 400.0, "운영비": 200.0},
    "influences": [
        {"name": "설비단가", "delta": 900.0, "flips_conclusion": True},
        {"name": "할인율", "delta": 300.0, "flips_conclusion": False},
    ],
    # ── R17 (WP-28A): `FR-1004-AC1` 의 잔여 3종이 요구하는 입력 ──────────
    #
    # **차트가 늘면 이 사전도 늘어야 한다.** `render_charts(SAMPLE)` 를 태그
    # 없이 부르면 **등록된 전부**를 그리고, 입력이 모자란 차트를 조용히
    # 건너뛰지 않는다 (`ValidationError`). 그래서 새 차트를 놓으면 이 테스트가
    # 빨간불이 된다 — **그것이 설계다.** 건너뛰게 두면 리포트에서 그림 한 장이
    # 사라지는데 아무 오류도 나지 않고, 그 빈자리는 심의자료가 인쇄된 뒤에
    # 발견된다. 여기서 한 번 아픈 것이 그것보다 싸다.
    "resource_dispatch": {"PV": [0.0, 3.0, 5.0, 2.0], "ESS": [1.0, -2.0, 0.0, 1.0]},
    "load": [4.0, 5.0, 6.0, 3.0],
    "production": [10.0, 12.0, 14.0, 11.0],
    "self_consumption": [6.0, 7.0, 8.0, 6.0],
    "export": [4.0, 5.0, 6.0, 5.0],
    "import": [1.0, 0.5, 0.0, 1.5],
    "model_comparison": {"기본안": 1_200_000.0, "무지원": -300_000.0},
    # ── R19: `FR-803-AC1` 2변수 등고선 + 목표 달성 영역 음영 ──────────────
    #
    # 위 문단이 예고한 그대로 이 테스트가 빨간불이 되어 이 항목을 불렀다.
    # **2×2 가 최소 격자다** — 조항이 2변수이므로 두 축 모두 2수준 이상이어야
    # 하고, 차트가 그것을 `ValidationError` 로 강제한다. 격자에 빈 칸이 있으면
    # 등고선이 실행하지 않은 좌표의 값을 지어내므로 그것도 거부된다.
    "cells": [
        {"x_value": 0.0, "y_value": 0.03, "metric_value": 50.0, "achieved": True},
        {"x_value": 0.0, "y_value": 0.05, "metric_value": -50.0, "achieved": False},
        {"x_value": 0.1, "y_value": 0.03, "metric_value": 150.0, "achieved": True},
        {"x_value": 0.1, "y_value": 0.05, "metric_value": 50.0, "achieved": True},
    ],
    "x_label": "보조율",
    "y_label": "할인율",
    "metric_label": "NPV (만원)",
}


@pytest.mark.contract
@pytest.mark.req("FR-1004-AC1")
def test_every_chart_renders_real_bytes() -> None:
    """**산출물이 PNG 서명으로 시작한다.**

    이 검사가 없던 동안 `generate_charts()` 는 `"Cumulative Cash Flow Chart
    with BEP"` 라는 **영어 문자열**을 돌려주었고, 그것을 검증하던 테스트는
    dict 에 키가 있는지만 보았다. 그 위에 FR-1001~FR-1005 가 얹혀 있었다.
    """
    artifacts = render_charts(SAMPLE)
    assert artifacts, "등록된 차트가 없다"
    for tag, artifact in artifacts.items():
        assert isinstance(artifact, ChartArtifact)
        assert artifact.payload.startswith(PNG_MAGIC), f"{tag}: PNG 가 아니다"
        assert len(artifact.payload) > 1000, f"{tag}: 그림이라기에 너무 작다"


@pytest.mark.contract
@pytest.mark.req("FR-1004-AC1")
def test_every_chart_points_at_a_clause() -> None:
    """조항을 가리키지 않는 차트는 리포트에 있을 이유가 없다.

    있다면 조항이 빠진 것이거나 차트가 남은 것이며, 둘 다 드러나야 한다.
    """
    for tag, cls in chart_registry().items():
        assert cls.clauses, f"{tag}: `clauses` 가 비어 있다"
        assert cls.label, f"{tag}: `label` 이 비어 있다"
        for clause in cls.clauses:
            assert clause.startswith(("FR-", "NFR-", "UI-", "SC-")), (
                f"{tag}: 조항 ID 형식이 아니다 — {clause!r}"
            )


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_missing_input_is_a_three_part_error() -> None:
    """입력이 모자라면 **필드·사유·조치**를 갖춘 오류가 난다.

    `KeyError` 로 두면 사용자에게 키 이름 하나만 도달한다. 차트는 리포트
    맨 앞이므로 여기서 실패하면 사용자가 가장 먼저 보는 오류가 된다.
    """
    with pytest.raises(ValidationError) as caught:
        render_charts({}, tags=["cashflow_line"])
    err = caught.value
    assert err.field == "chart.cashflow_line"
    assert "cashflows" in err.reason
    assert err.action.strip()


@pytest.mark.contract
@pytest.mark.req("FR-1004-AC1")
def test_unknown_tag_is_refused_not_skipped() -> None:
    """없는 차트를 조용히 건너뛰지 않는다.

    건너뛰면 리포트에서 그림 한 장이 사라지는데 아무 오류도 나지 않고,
    그 빈자리는 심의자료가 인쇄된 뒤에 발견된다.
    """
    with pytest.raises(ValidationError, match="등록되지 않은"):
        render_charts(SAMPLE, tags=["없는차트"])


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC1")
def test_dropping_a_file_extends_the_registry() -> None:
    """★ **확장점 증명** — 파일 하나를 놓으면 레지스트리가 는다.

    「확장점이 있다」와 「그 경로로 실제로 확장된다」는 다르다. 그래서 실제로
    파일을 놓아 보고, **어떤 공유 파일도 고치지 않은 채** 등록되는 것을 본다
    (`__init__.py` 를 포함해서다 — §16.1 W-3).

    지운 뒤에 사라지는 것도 함께 본다. `__subclasses__()` 는 클래스 객체가
    살아 있는 한 계속 돌려주므로, 파일을 지워도 남으면 **유령 차트**가 리포트에
    끼어든다 — 08-09 에 자원 쪽에서 실제로 겪은 형태다.
    """
    package_dir = Path(__file__).resolve().parents[2] / "core" / "report" / "charts"
    probe = package_dir / "zz_registry_probe.py"
    before = set(chart_registry())
    assert "zz_registry_probe" not in before

    probe.write_text(
        '"""확장점 증명용 임시 차트 — 이 테스트가 놓고 지운다."""\n'
        "from collections.abc import Mapping\n"
        "from typing import Any, ClassVar\n"
        "\n"
        "from core.contracts.chart import Chart\n"
        "\n"
        "\n"
        "class RegistryProbe(Chart):\n"
        '    tag: ClassVar[str] = "zz_registry_probe"\n'
        '    label: ClassVar[str] = "확장점 증명"\n'
        '    clauses: ClassVar[tuple[str, ...]] = ("NFR-207-AC1",)\n'
        "\n"
        "    def draw(self, data: Mapping[str, Any]) -> bytes:\n"
        "        from core.report.charts._render import new_figure, to_png\n"
        "\n"
        "        figure = new_figure()\n"
        "        figure.axes[0].plot([0, 1], [0, 1])\n"
        "        return to_png(figure)\n",
        encoding="utf-8",
    )
    try:
        chart_registry.cache_clear()
        after = set(chart_registry())
        assert "zz_registry_probe" in after, (
            "파일을 놓았는데 등록되지 않았다 — 확장점이 아니라 그냥 함수다"
        )
        assert after - before == {"zz_registry_probe"}, "다른 차트가 함께 흔들렸다"

        artifact = render_charts(SAMPLE, tags=["zz_registry_probe"])["zz_registry_probe"]
        assert artifact.payload.startswith(PNG_MAGIC)
    finally:
        probe.unlink(missing_ok=True)
        chart_registry.cache_clear()

    assert set(chart_registry()) == before, (
        "파일을 지웠는데 남아 있다 — 유령 차트가 리포트에 낀다"
    )


@pytest.mark.contract
@pytest.mark.req("FR-1004-AC1")
def test_empty_artifact_cannot_exist() -> None:
    """빈 산출물은 만들어지지 않는다.

    빈 결과를 돌려주면 리포트에 「그렸다」로 집계되고, 그 자리는 비어 있는
    채로 심의자료에 실린다.
    """
    with pytest.raises(ValueError, match="빈 산출물"):
        ChartArtifact(
            tag="t", label="l", mime="image/png", payload=b"", clauses=("FR-1004-AC1",)
        )


@pytest.mark.contract
@pytest.mark.req("FR-1004-AC1")
def test_contract_requires_draw() -> None:
    """`draw()` 를 채우지 않은 차트는 인스턴스가 되지 않는다."""

    class Incomplete(Chart):
        tag = "incomplete"
        label = "미완"

    with pytest.raises(TypeError):
        Incomplete()      # type: ignore[abstract]
