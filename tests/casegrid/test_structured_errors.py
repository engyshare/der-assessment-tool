"""§7.3 대장 밖 입력 검증 — 구조화만 (`rule=` 비움), NFR-303.

`core/casegrid/{grid,execution,models}.py` 의 나머지 raise 지점 17곳은 어느
DV 규칙에도 없다. 그래도 NFR-303(«어떤 필드가 / 왜 / 어떻게») 은 대장 밖
입력 검증에도 적용되므로 `ValidationError` 로 구조화하되 `rule` 은 비운다.

행 번호는 `.orch/R24-레인대상표.md` 뽑은 시점 것이라 함수 이름을 근거로 쓴다.
`execution.py` 의 `case_count < 0`(33행, `execution_plan`)과
`CaseGridExecutionCancelled`(154행)은 **대상아님**이라 여기 없다 — 전자는
내부에서 계산된 값에 대한 호출측 계약이고, 후자는 사용자 취소이지 입력
검증이 아니다 (`.orch/R24-WP34A-결과.md` 참고).
"""

from __future__ import annotations

import pytest

from core.casegrid.execution import execution_plan
from core.casegrid.grid import CaseGrid
from core.casegrid.models import Case, CaseVariable, CoupledSet
from core.contracts.validation import ValidationError


def _assert_structured(caught: pytest.ExceptionInfo[ValidationError], field: str) -> None:
    parts = caught.value.as_dict()
    assert parts["field"] == field, parts
    assert (parts["reason"] or "").strip(), parts
    assert (parts["action"] or "").strip(), parts
    assert parts["rule"] is None, "대장 밖 검증이므로 rule 은 비워야 한다"


# ── core/casegrid/grid.py :: CaseGrid.__init__ ──────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_casegrid_init_rejects_empty_variables() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseGrid(variables=())
    _assert_structured(caught, "casegrid.variables")


@pytest.mark.req("NFR-303-M1")
def test_casegrid_init_rejects_negative_confirmation_threshold() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseGrid(
            variables=(CaseVariable("x", ("a", "b")),),
            confirmation_threshold=-1,
        )
    _assert_structured(caught, "casegrid.confirmation_threshold")
    assert "-1" in caught.value.reason


@pytest.mark.req("NFR-303-M1")
def test_casegrid_init_rejects_negative_seconds_per_case() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseGrid(
            variables=(CaseVariable("x", ("a", "b")),),
            seconds_per_case=-2.0,
        )
    _assert_structured(caught, "casegrid.seconds_per_case")
    assert "-2" in caught.value.reason


# ── core/casegrid/grid.py :: CaseGrid.preview ───────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_casegrid_preview_rejects_negative_limit() -> None:
    grid = CaseGrid(variables=(CaseVariable("x", ("a", "b")),))
    with pytest.raises(ValidationError) as caught:
        grid.preview(limit=-1)
    _assert_structured(caught, "casegrid.preview_limit")


# ── core/casegrid/grid.py :: CaseGrid._validate_variable_names ─────────────


@pytest.mark.req("NFR-303-M1")
def test_casegrid_rejects_duplicate_variable_names() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseGrid(
            variables=(
                CaseVariable("x", ("a", "b")),
                CaseVariable("x", ("c", "d")),
            ),
        )
    _assert_structured(caught, "casegrid.variables")
    assert "x" in caught.value.reason


# ── core/casegrid/grid.py :: CaseGrid._validate_coupled_sets (DV-9 아닌 둘) ──


@pytest.mark.req("NFR-303-M1")
def test_coupled_set_rejects_unknown_variable_reference() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseGrid(
            variables=(CaseVariable("x", ("a", "b")),),
            coupled_sets=(CoupledSet("bundle", ("x", "missing")),),
        )
    _assert_structured(caught, "casegrid.coupled_sets")
    assert "missing" in caught.value.reason


@pytest.mark.req("NFR-303-M1")
def test_coupled_set_rejects_variable_in_multiple_sets() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseGrid(
            variables=(
                CaseVariable("x", ("a", "b")),
                CaseVariable("y", ("a", "b")),
                CaseVariable("z", ("a", "b")),
            ),
            coupled_sets=(
                CoupledSet("bundle1", ("x", "y")),
                CoupledSet("bundle2", ("x", "z")),
            ),
        )
    _assert_structured(caught, "casegrid.coupled_sets")
    assert "x" in caught.value.reason


# ── core/casegrid/execution.py :: execution_plan ────────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_execution_plan_rejects_negative_seconds_per_case() -> None:
    with pytest.raises(ValidationError) as caught:
        execution_plan(10, seconds_per_case=-1.0)
    _assert_structured(caught, "casegrid.seconds_per_case")


@pytest.mark.req("NFR-303-M1")
def test_execution_plan_rejects_non_positive_parallelism() -> None:
    with pytest.raises(ValidationError) as caught:
        execution_plan(10, parallelism=0)
    _assert_structured(caught, "casegrid.parallelism")


@pytest.mark.req("NFR-303-M1")
def test_execution_plan_rejects_negative_threshold() -> None:
    with pytest.raises(ValidationError) as caught:
        execution_plan(10, threshold=-5)
    _assert_structured(caught, "casegrid.confirmation_threshold")


# ── core/casegrid/models.py :: CaseVariable.__post_init__ ───────────────────


@pytest.mark.req("NFR-303-M1")
def test_case_variable_rejects_blank_name() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseVariable("   ", ("a", "b"))
    _assert_structured(caught, "casegrid.variable_name")


@pytest.mark.req("NFR-303-M1")
def test_case_variable_rejects_empty_values() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseVariable("x", ())
    _assert_structured(caught, "casegrid.variable_values")
    assert "x" in caught.value.reason


@pytest.mark.req("NFR-303-M1")
def test_case_variable_rejects_blank_target() -> None:
    with pytest.raises(ValidationError) as caught:
        CaseVariable("x", ("a", "b"), target="   ")
    _assert_structured(caught, "casegrid.variable_target")
    assert "x" in caught.value.reason


# ── core/casegrid/models.py :: CoupledSet.__post_init__ ─────────────────────


@pytest.mark.req("NFR-303-M1")
def test_coupled_set_model_rejects_blank_name() -> None:
    with pytest.raises(ValidationError) as caught:
        CoupledSet("   ", ("x", "y"))
    _assert_structured(caught, "casegrid.coupled_set_name")


@pytest.mark.req("NFR-303-M1")
def test_coupled_set_model_rejects_fewer_than_two_variables() -> None:
    with pytest.raises(ValidationError) as caught:
        CoupledSet("bundle", ("x",))
    _assert_structured(caught, "casegrid.coupled_set_variables")
    assert "bundle" in caught.value.reason


@pytest.mark.req("NFR-303-M1")
def test_coupled_set_model_rejects_duplicate_variable_names() -> None:
    with pytest.raises(ValidationError) as caught:
        CoupledSet("bundle", ("x", "x"))
    _assert_structured(caught, "casegrid.coupled_set_variables")
    assert "bundle" in caught.value.reason


# ── core/casegrid/models.py :: Case.__post_init__ ───────────────────────────


@pytest.mark.req("NFR-303-M1")
def test_case_model_rejects_negative_index() -> None:
    with pytest.raises(ValidationError) as caught:
        Case(index=-1, values={})
    _assert_structured(caught, "casegrid.case_index")
