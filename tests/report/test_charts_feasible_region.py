"""R19 — `FR-803-AC1` 2변수 지표 등고선 + 목표 달성 영역 음영.

차트 6종 중 **마지막 미구현**이었다. R16 이 `Chart` 계약과
`core/report/charts/` 레지스트리를 세우고 R17 이 셋을 놓았으며, 이 조항만
남아 있었다 (`.orch/R18-WP29A-재검증표.md` D1·D2).

## 이 파일이 「PNG 가 나왔다」에서 멈추지 않는 이유

조항 문면이 **둘**을 요구한다 — *「축 변수 2개 선택 → 지표 등고선. "목표 달성
영역" 을 음영으로 구분」*. 그런데 **음영을 한 줄도 그리지 않아도 PNG 는
나온다.** 그러면 검사는 초록불이고 리포트에는 등고선만 실린다. 이 저장소가
열두 번 만난 「검사는 있었는데 아무것도 붙들지 않았다」가 정확히 그 형태다.

그래서 **두 층을 각각 붙든다** — 입력의 한 층만 바꿔 PNG 바이트가 달라지는지
본다. 구현이 그 층을 무시하면 두 PNG 가 같아지고 테스트가 빨간불이 된다.

| 무엇을 바꾸나 | 무엇이 붙들리나 |
|---|---|
| `achieved` 만 뒤집는다 | **음영 층** — 무시하면 바이트가 같다 |
| `metric_value` 만 바꾼다 | **등고선 층** — 무시하면 바이트가 같다 |

그리고 그 검사에 이가 있는지 **음영을 실제로 무력화해 확인한다**
(`test_the_shading_check_actually_has_teeth`, COMMON.md §2③).
"""

from __future__ import annotations

from typing import Any

import pytest

from core.contracts.chart import Chart, ChartArtifact
from core.contracts.validation import ValidationError
from core.report.charts import chart_registry, render_charts
from core.report.charts import feasible_region as module
from core.report.charts.feasible_region import FeasibleRegion

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: 3×3 격자. 축은 보조율(0·10·20%)과 할인율(3·5·7%)이고 지표는 NPV(만원)다.
#:
#: 지표값은 **손 계산 가능한 닫힌 형태**로 둔다 —
#:     NPV(x, y) = 1000·x − 5000·y + 200
#: 목표는 `NPV ≥ 0` 이므로 달성 여부도 손으로 셀 수 있다. 이 값은 정책·시장
#: 파라미터가 아니라 그림을 검사하기 위한 대표 격자이므로 대장 대조 대상이
#: 아니다 (`docs/assumptions.yaml` 은 정책·시장 파라미터만 다룬다).
_XS: tuple[float, ...] = (0.0, 0.10, 0.20)
_YS: tuple[float, ...] = (0.03, 0.05, 0.07)


def _npv(x: float, y: float) -> float:
    return 1000.0 * x - 5000.0 * y + 200.0


def _cells(
    *,
    achieved_override: bool | None = None,
    metric_scale: float = 1.0,
    achieved_at: frozenset[tuple[float, float]] | None = None,
) -> list[dict[str, Any]]:
    """대표 격자. `achieved_at` 이 주어지면 **그 좌표만** 달성으로 둔다."""
    out: list[dict[str, Any]] = []
    for x in _XS:
        for y in _YS:
            if achieved_at is not None:
                achieved = (x, y) in achieved_at
            elif achieved_override is not None:
                achieved = achieved_override
            else:
                achieved = _npv(x, y) >= 0.0
            out.append(
                {
                    "x_value": x,
                    "y_value": y,
                    "metric_value": _npv(x, y) * metric_scale,
                    "achieved": achieved,
                }
            )
    return out


#: 달성 **칸 수는 같고 자리가 다른** 두 배치. 범례 문구가 `6/9` 로 동일해지므로
#: 두 그림의 차이는 **음영이 칠해진 자리**밖에 없다.
_SIX_LOWER: frozenset[tuple[float, float]] = frozenset(
    {(x, y) for x in _XS for y in _YS if _npv(x, y) >= 0.0}
)
_SIX_UPPER: frozenset[tuple[float, float]] = frozenset(
    {(x, y) for x in _XS for y in _YS} - _SIX_LOWER
) | frozenset({(0.0, 0.03), (0.10, 0.03), (0.20, 0.03)})


def _data(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "cells": _cells(),
        "x_label": "보조율",
        "y_label": "할인율",
        "metric_label": "NPV (만원)",
    }
    base.update(overrides)
    return base


SAMPLE: dict[str, Any] = _data()


# ── 손 계산으로 표본을 먼저 고정한다 ────────────────────────────────────


@pytest.mark.req("FR-803-AC1")
def test_sample_grid_has_a_hand_counted_achieved_split() -> None:
    """★ 표본 자체가 「일부만 달성」이어야 음영 검사가 뜻을 갖는다.

    전부 달성이거나 전부 미달이면 음영을 그려도 안 그려도 **영역이 하나**여서
    「구분」을 검사할 수 없다. 손 계산:

        NPV(x, y) = 1000x − 5000y + 200,  목표 NPV ≥ 0
        y=0.03 → 50 + 1000x        ≥ 0  전부 달성 (3칸)
        y=0.05 → -50 + 1000x       ≥ 0  x=0 미달, x=0.1·0.2 달성 (2칸)
        y=0.07 → -150 + 1000x      ≥ 0  x=0 미달, x=0.1(-50) 미달, x=0.2(50) 달성 (1칸)
        합 6칸 달성 / 9칸
    """
    achieved = [cell for cell in SAMPLE["cells"] if cell["achieved"]]
    assert len(SAMPLE["cells"]) == 9
    assert len(achieved) == 6
    # 경계 세 칸을 값으로 못 박는다 — 부호가 갈리는 자리다.
    #
    # `approx` 를 쓰는 이유: 0.05·0.07 은 2진 부동소수로 정확히 표현되지 않아
    # `5000 * 0.05 == 250.00000000000003` 이다. **부호 판정은 이 오차에
    # 흔들리지 않는다**(경계에서 50 만원 떨어져 있다) — 그래서 달성 여부는
    # 정확 비교로 두고 금액만 approx 로 본다.
    assert _npv(0.0, 0.05) == pytest.approx(-50.0)
    assert _npv(0.10, 0.07) == pytest.approx(-50.0)
    assert _npv(0.20, 0.07) == pytest.approx(50.0)


# ── 실렌더 ──────────────────────────────────────────────────────────────


@pytest.mark.req("FR-803-AC1")
def test_renders_real_png() -> None:
    """등고선 차트가 실제 PNG 바이트를 낸다."""
    artifact = FeasibleRegion().render(SAMPLE)
    assert isinstance(artifact, ChartArtifact)
    assert artifact.payload.startswith(PNG_MAGIC), "PNG 서명이 아니다"
    assert len(artifact.payload) > 1000, "그림이라기에 너무 작다"
    assert artifact.mime == "image/png"
    assert "FR-803-AC1" in artifact.clauses


@pytest.mark.req("FR-803-AC1")
def test_is_registered_without_editing_any_shared_file() -> None:
    """레지스트리가 자동 발견한다 — `__init__.py` 를 고치지 않았다.

    이것이 R16 확장점 ①의 요지다. 고쳐야 했다면 차트 1종 추가가 공유 파일
    편집이 되고, 여섯 사람이 같은 자리를 편집하게 된다.
    """
    registry = chart_registry()
    assert "feasible_region" in registry
    assert issubclass(registry["feasible_region"], Chart)
    # 이제 여섯 조항 차트가 모두 등록돼 있다 (FR-1004-AC1 여섯 + 이 조항)
    assert len(registry) >= 7


@pytest.mark.req("FR-803-AC1")
def test_render_charts_includes_it_by_tag() -> None:
    """`render_charts(tags=[...])` 경로로도 그려진다."""
    artifacts = render_charts(SAMPLE, tags=["feasible_region"])
    assert set(artifacts) == {"feasible_region"}
    assert artifacts["feasible_region"].payload.startswith(PNG_MAGIC)


# ── 조항의 두 층을 각각 붙든다 ──────────────────────────────────────────


@pytest.mark.req("FR-803-AC1")
def test_shading_layer_responds_to_achieved() -> None:
    """**「목표 달성 영역을 음영으로 구분」** — `achieved` 만 바꿔 확인한다.

    격자와 지표값은 그대로 두고 달성 여부만 전부 참 / 전부 거짓으로 바꾼다.
    음영을 그리지 않는 구현은 **두 PNG 가 같다.**
    """
    all_on = FeasibleRegion().render(_data(cells=_cells(achieved_override=True)))
    all_off = FeasibleRegion().render(_data(cells=_cells(achieved_override=False)))
    assert all_on.payload != all_off.payload, (
        "달성 여부를 뒤집었는데 그림이 같다 — 음영이 그려지지 않는다"
    )

    # 부분 달성(표본)은 둘 **어느 쪽과도** 달라야 한다. 6/9 칸만 칠해지므로
    # 전부 칠한 그림도 전혀 칠하지 않은 그림도 아니다.
    partial = FeasibleRegion().render(SAMPLE)
    assert partial.payload != all_on.payload
    assert partial.payload != all_off.payload


@pytest.mark.req("FR-803-AC1")
def test_shading_is_drawn_at_the_achieved_cell_positions() -> None:
    """★ **음영이 「자리」를 구분하는지** 본다 — 이것이 조항의 「영역」이다.

    위 테스트만으로는 부족하다. 달성 **개수**가 바뀌면 범례 문구
    (`목표 달성 영역 (n/9 케이스)`)도 바뀌므로, **음영을 한 칸도 칠하지 않는
    구현조차 두 그림을 다르게 만든다.** 실제로 이 파일을 처음 쓸 때 그렇게
    돼 있었고 `test_the_shading_check_actually_has_teeth` 가 그것을 잡았다.

    그래서 **개수는 같고 자리만 다른** 두 배치를 비교한다. 범례가 양쪽 다
    `6/9` 이므로 차이는 **칠해진 자리**밖에 없다.
    """
    lower = FeasibleRegion().render(_data(cells=_cells(achieved_at=_SIX_LOWER)))
    upper = FeasibleRegion().render(_data(cells=_cells(achieved_at=_SIX_UPPER)))
    assert len(_SIX_LOWER) == len(_SIX_UPPER) == 6, "두 배치의 칸 수가 같아야 한다"
    assert _SIX_LOWER != _SIX_UPPER, "두 배치의 자리가 달라야 한다"
    assert lower.payload != upper.payload, (
        "달성 칸 수는 같고 자리만 다른데 그림이 같다 — 음영이 자리를 "
        "구분하지 않는다"
    )


@pytest.mark.req("FR-803-AC1")
def test_contour_layer_responds_to_metric_values() -> None:
    """**「지표 등고선」** — 지표값만 바꿔 확인한다.

    달성 여부는 고정하고 지표값만 배로 늘린다. 등고선을 그리지 않는 구현은
    **두 PNG 가 같다.**
    """
    base = FeasibleRegion().render(_data(cells=_cells(achieved_override=True)))
    scaled = FeasibleRegion().render(
        _data(cells=_cells(achieved_override=True, metric_scale=3.0))
    )
    assert base.payload != scaled.payload, (
        "지표값을 3배로 했는데 그림이 같다 — 등고선이 지표를 그리지 않는다"
    )


@pytest.mark.req("FR-803-AC1")
def test_the_shading_check_actually_has_teeth() -> None:
    """★ 위 음영 검사가 **실제로 잡는지** 확인한다 (COMMON.md §2③).

    음영을 완전히 투명하게 만들어 「음영을 그리지 않는 구현」을 흉내내고,
    그때 `test_shading_is_drawn_at_the_achieved_cell_positions` 의 단언이
    무너지는지 본다. 무너지지 않으면 그 테스트는 통과만 하고 아무것도 붙들지
    않는다.

    > **이 테스트가 실제로 결함을 잡았다.** 처음에는 달성 **개수**가 다른 두
    > 배치를 비교했는데, 그러면 범례 문구(`n/9 케이스`)가 함께 바뀌어 **음영을
    > 한 칸도 칠하지 않아도 두 그림이 달라진다.** 투명화 뒤에도 차이가 남아
    > 그것이 드러났고, 그래서 비교를 **개수 같음 · 자리 다름**으로 바꿨다.

    확인한 뒤 반드시 원복한다 — 이 테스트 안에서만 바꾼다.
    """
    original = module._SHADE_ALPHA
    try:
        module._SHADE_ALPHA = 0.0        # 투명 = 그리지 않은 것과 같다
        lower = FeasibleRegion().render(_data(cells=_cells(achieved_at=_SIX_LOWER)))
        upper = FeasibleRegion().render(_data(cells=_cells(achieved_at=_SIX_UPPER)))
        assert lower.payload == upper.payload, (
            "음영을 투명하게 했는데도 그림이 다르다 — 자리 검사가 붙드는 것이 "
            "음영이 아니라 다른 무엇이다"
        )
    finally:
        module._SHADE_ALPHA = original

    # 원복 확인 — 다시 음영이 그려져 두 그림이 달라진다
    lower = FeasibleRegion().render(_data(cells=_cells(achieved_at=_SIX_LOWER)))
    upper = FeasibleRegion().render(_data(cells=_cells(achieved_at=_SIX_UPPER)))
    assert lower.payload != upper.payload


# ── 거부 경로 — 전부 3요소 오류다 (NFR-303) ────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_missing_input_is_three_part_error() -> None:
    """`required_keys` 를 뺀 입력은 `KeyError` 가 아니라 `ValidationError` 다."""
    with pytest.raises(ValidationError) as caught:
        FeasibleRegion().render({"cells": _cells()})
    err = caught.value
    assert err.field == "chart.feasible_region"
    assert "x_label" in err.reason
    assert err.action.strip()


@pytest.mark.req("FR-803-AC1")
def test_empty_cells_are_refused() -> None:
    """셀이 없으면 빈 그림을 내지 않고 거부한다."""
    with pytest.raises(ValidationError, match="비어 있습니다"):
        FeasibleRegion().render(_data(cells=[]))


@pytest.mark.req("FR-803-AC1")
def test_one_level_axis_is_refused() -> None:
    """★ **2변수 조항이므로 한 축이 1수준이면 거부한다.**

    막지 않으면 matplotlib 이 등고선 없는 그림을 돌려주고, 그것은 바이트가
    있으므로 `ChartArtifact` 의 빈-산출물 검사를 통과한다. 즉 **「그렸다」로
    집계되는 빈 등고선**이 리포트에 실린다.
    """
    single = [c for c in _cells() if c["x_value"] == 0.0]
    with pytest.raises(ValidationError, match="축 수준이 모자랍니다"):
        FeasibleRegion().render(_data(cells=single))


@pytest.mark.req("FR-803-AC1")
def test_incomplete_grid_is_refused() -> None:
    """★ 격자에 빈 칸이 있으면 거부한다 — **등고선이 값을 지어내지 못하게.**

    빈 칸을 0 으로 메우면 등고선이 그 자리를 지나가고, 그림은 **실행하지
    않은 조합**에 대해 지표값을 주장한다. 심의자료에서 그것은 없는 근거다.
    """
    holed = [
        c for c in _cells() if not (c["x_value"] == 0.10 and c["y_value"] == 0.05)
    ]
    with pytest.raises(ValidationError, match="빈 칸"):
        FeasibleRegion().render(_data(cells=holed))


@pytest.mark.req("FR-803-AC1")
def test_non_numeric_axis_is_refused() -> None:
    """범주형 축은 등고선을 그릴 수 없으므로 3요소 오류로 거부한다."""
    categorical = [
        {"x_value": "저", "y_value": 0.03, "metric_value": 1.0, "achieved": True},
        {"x_value": "고", "y_value": 0.05, "metric_value": 2.0, "achieved": False},
    ]
    with pytest.raises(ValidationError) as caught:
        FeasibleRegion().render(_data(cells=categorical))
    assert caught.value.field.startswith("chart.feasible_region.")
    assert "수치가 아닙니다" in caught.value.reason
    # 조치가 대안 차트를 가리킨다 — 「안 된다」로 끝내지 않는다
    assert "model_comparison" in caught.value.action


@pytest.mark.req("FR-803-AC1")
def test_empty_draw_output_is_caught_by_the_contract() -> None:
    """★ 빈 산출물이 계약에 막히는지 확인한다 (COMMON.md §2③)."""
    original_draw = FeasibleRegion.draw
    try:
        FeasibleRegion.draw = lambda self, data: b""  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="빈 산출물"):
            FeasibleRegion().render(SAMPLE)
    finally:
        FeasibleRegion.draw = original_draw  # type: ignore[method-assign]

    assert FeasibleRegion().render(SAMPLE).payload.startswith(PNG_MAGIC)
