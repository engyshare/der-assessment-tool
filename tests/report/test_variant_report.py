"""변형별 결과가 **한 표에 상단부터** 오는가 — `FR-607-AC1` / R31 (결정 §5).

조항: *「모든 실행에서 `지원 0` 케이스가 자동 포함되어 **결과 상단에 표시**된다」*

R21 이 「자동 포함」을 닫았고(`run_order()` + `ordered_variants()`), R31 이 담을
자리(`CaseResult.variants`)와 **표시 층**을 만들었다. 이 파일은 표시를 붙든다.

붙드는 것 다섯:

    ① 기준선이 **맨 위**다                  「상단에 표시」
    ② 순서를 표시 층이 정하지 않는다         `run_order()` 가 정본이다
    ③ 빠진 변형을 **조용히 빼지 않는다**     「자동 포함」이 표에서 깨진 것을 본다
    ④ 지표 열이 변형마다 다르면 거부한다     빈칸은 0 과 구별되지 않는다
    ⑤ 변형이 **피클을 지난다**              병렬 실행에서만 사라지는 것을 막는다

**⑤가 이 파일에서 가장 조용한 자리다.** 케이스 그리드는 `ProcessPool` 로 병렬
실행되므로(`FR-805-AC1`) 결과가 피클을 지난다 — `__getstate__` 에 빠뜨리면 **직렬
실행에서는 보이고 병렬에서만 변형이 사라지고**, 그 차이는 케이스가 적은 테스트에서
드러나지 않는다.
"""

from __future__ import annotations

import pickle

import pytest

from core.casegrid.models import CaseResult
from core.casegrid.variants import run_order
from core.contracts.validation import ValidationError
from core.report.variant_report import build_variant_table


def _result(**variants: dict[str, float]) -> CaseResult:
    return CaseResult(
        case_index=0, values={"discount_rate": "base"}, metrics={"npv": 1.0},
        variants=variants,
    )


def _full_result() -> CaseResult:
    """등록된 변형 전부에 지표를 채운 결과 — 변형 목록을 여기 베끼지 않는다."""
    return _result(**{
        variant.tag: {"npv_won": float(index * 1000), "payback_years": float(index + 5)}
        for index, variant in enumerate(run_order())
    })


# ── ①② 기준선이 맨 위이고, 순서는 run_order() 가 정한다 ──────────────

@pytest.mark.req("FR-607-AC1")
def test_the_baseline_row_comes_first() -> None:
    """★ 「결과 상단에 표시」 — 기준선이 첫 행이다.

    **인덱스로 확인하는 것이 요점이다.** 「표에 있다」만 보면 맨 아래에 있어도
    통과하고, 그러면 조항의 「상단」이 사라진다.
    """
    table = build_variant_table(_full_result())

    assert table.rows[0].baseline is True
    assert table.baseline_row is table.rows[0]
    # 기준선이 **정확히 하나**다 — `ordered_variants()` 의 보증이 표까지 온다
    assert sum(1 for row in table.rows if row.baseline) == 1


@pytest.mark.req("FR-607-AC1")
def test_the_row_order_is_the_registry_order_not_the_tables_own() -> None:
    """★★ 순서를 표시 층이 정하지 않는다 — `run_order()` 가 정본이다.

    표가 자기 나름대로 정렬하면 **조항이 리포트마다 다르게 지켜진다.** 그리고
    `ordered_variants()` 가 보증하는 「기준선이 맨 위」가 표시 층에서 무의미해진다.
    """
    expected = [variant.tag for variant in run_order()]

    table = build_variant_table(_full_result())

    assert [row.tag for row in table.rows] == expected


@pytest.mark.req("FR-607-AC1")
def test_every_row_carries_the_registered_label() -> None:
    """행이 tag 만이 아니라 **표시 이름**을 나른다.

    tag 만 나르면 표시 층이 이름을 다시 지어야 하고, 그 이름이 갈린다.
    """
    labels = {variant.tag: variant.label for variant in run_order()}

    table = build_variant_table(_full_result())

    assert {row.tag: row.label for row in table.rows} == labels
    assert all(row.label.strip() for row in table.rows)


# ── ③ 빠진 변형을 조용히 빼지 않는다 ─────────────────────────────────

@pytest.mark.req("FR-607-AC1")
def test_a_missing_variant_is_refused_not_dropped() -> None:
    """★★★ 등록된 변형의 결과가 없으면 **거부한다.**

    조용히 빼면 그 표는 「그 변형이 산출되지 않았다」가 아니라 **「그 변형이
    없다」**로 읽히고, 조항이 요구하는 「모든 실행에서 자동 포함」이 표 위에서
    깨진 것을 아무도 보지 못한다.
    """
    registered = list(run_order())
    assert len(registered) >= 2, "변형이 하나면 이 검사가 성립하지 않는다"
    partial = _result(**{registered[0].tag: {"npv_won": 0.0}})

    with pytest.raises(ValidationError) as caught:
        build_variant_table(partial)

    assert registered[1].tag in caught.value.reason
    assert caught.value.action.strip()


@pytest.mark.req("FR-607-AC1")
def test_an_empty_variants_map_is_refused() -> None:
    """변형이 아예 없으면 거부한다 — 빈 표를 그리지 않는다.

    빈 표는 그럴듯하게 그려지고, 그러면 「자동 포함」이 깨진 실행이 리포트를
    통과한다.
    """
    with pytest.raises(ValidationError) as caught:
        build_variant_table(_result())

    assert "변형별 결과가 없습니다" in caught.value.reason


# ── ④ 지표 열이 변형마다 다르면 거부한다 ─────────────────────────────

@pytest.mark.req("FR-607-AC1")
def test_variants_with_different_metrics_are_refused() -> None:
    """★ 한 변형만 가진 지표가 있으면 거부한다.

    통과시키면 그 열이 빈칸이 되고, **빈칸은 「0」인지 「계산하지 않았다」인지
    구별되지 않는다** — 그 구별이 `MissingAssumption` 이 존재하는 이유다.
    """
    registered = list(run_order())
    uneven = _result(**{
        registered[0].tag: {"npv_won": 1.0, "irr": 0.08},
        **{v.tag: {"npv_won": 2.0} for v in registered[1:]},
    })

    with pytest.raises(ValidationError) as caught:
        build_variant_table(uneven)

    assert "irr" in caught.value.reason


@pytest.mark.req("FR-607-AC1")
def test_metric_columns_are_in_a_fixed_order() -> None:
    """열 순서가 고정이다 — 사전 순회 순서에 기대지 않는다.

    삽입 순서나 파이썬 판올림으로 열이 뒤바뀌면 **사람이 열을 잘못 읽고**, 그
    오독은 값이 정상이므로 드러나지 않는다.
    """
    table = build_variant_table(_full_result())

    assert table.metric_names == tuple(sorted(table.metric_names))
    # 모든 행이 같은 열을 든다
    for row in table.rows:
        assert tuple(sorted(row.metrics)) == table.metric_names


# ── ⑤ 변형이 피클을 지난다 (병렬 실행) ───────────────────────────────

@pytest.mark.req("FR-607-AC1", "FR-805-AC1")
def test_variants_survive_pickling() -> None:
    """★★★ 변형이 **피클을 지난다** — 병렬 실행에서만 사라지는 것을 막는다.

    `CaseResult` 는 `__getstate__`/`__setstate__` 를 손으로 갖고 있고, 케이스
    그리드는 `ProcessPool` 로 돈다(`FR-805-AC1`). 새 필드를 그 둘에 빠뜨리면
    **직렬 실행에서는 보이고 병렬에서만 변형이 사라진다** — 그 차이는 케이스가
    적은 테스트에서 드러나지 않고, 27케이스 실행 결과의 변형 열이 통째로 비는
    것으로만 나타난다.
    """
    original = _full_result()

    restored = pickle.loads(pickle.dumps(original))

    assert restored.variants == original.variants, (
        "피클을 지나며 변형이 바뀌었습니다 — `__getstate__`/`__setstate__` 를 "
        "보십시오"
    )
    assert restored.variants, "피클을 지나며 변형이 사라졌습니다"
    # 표가 복원된 결과로도 그려진다
    assert build_variant_table(restored).rows[0].baseline is True


@pytest.mark.req("FR-607-AC1")
def test_the_variants_mapping_is_read_only_two_levels_deep() -> None:
    """중첩 사전이 **두 층 모두** 읽기 전용이다.

    바깥만 얼리면 안쪽 지표 사전을 밖에서 고칠 수 있고, 병렬 실행에서 그것은
    `NFR-205` 가 막으려는 전역 가변 상태와 같은 결과가 된다.
    """
    result = _full_result()
    tag = next(iter(result.variants))

    with pytest.raises(TypeError):
        result.variants["새변형"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        result.variants[tag]["npv_won"] = 0.0  # type: ignore[index]
