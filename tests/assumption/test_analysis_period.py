"""분석기간을 **대장이 소유하는가** — §7.1 O-1 · `DV-5` 「기본 20년」 / R31.

`infra/orm/scenario.py` 는 `analysis_years` 를 `Scenario` **금지 필드**로 열거하며
*「전제 분류에 해당 값은 `AssumptionSet` 에 넣고 여기서는 `assumption_set_id` 만
들고 있다」* 고 적는다(§7.1 O-1 · `DV-11`). **소유자는 그렇게 이미 정해져 있었다.**

그런데 실제 기본값은 `core/casegrid/e2e_runner.py` 의 모듈 상수
`HORIZON_YEARS = 20` 에 있었다. R30 이 그 상수를 인자로 끌어내 실행 경로가
상한 검사를 지나게 했지만, *「분석기간의 소유자를 정한 것이 아니다」* 라고 스스로
적어 두었다. **열려 있던 것은 「어느 층인가」가 아니라 「그 층에 아직 값이
없다」였다** — 그 상태에서는 사용자가 분석기간을 고를 통로가 아예 없고, 러너의
모듈 상수를 고치는 것이 유일한 방법이었다.

붙드는 것 넷:

    ① 대장이 그 값을 갖는다                    소유자가 실제로 갖고 있다
    ② 사용자가 오버라이드로 바꿀 수 있다        「고르는 값」이 되었다
    ③ 분석기간일 수 없는 값은 거부한다          0·음수·소수
    ④ 코드에 기본값 상수가 되살아나지 않았다    사본이 다시 생기는 것을 막는다

**④가 이 파일의 래칫이다.** ①~③만 두면 「대장에 있다」를 확인할 뿐이고, 러너가
자기 기본값을 다시 갖는 것을 아무도 막지 않는다 — 그때 대장을 고쳐도 계산은 옛
값을 쓰고, **그 어긋남은 NPV 를 바꾸면서 아무 예외도 내지 않는다.**
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import (
    ANALYSIS_PERIOD_KEY,
    MissingAssumption,
    PriceBasis,
)
from core.contracts.validation import ValidationError

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/assumptions.yaml"

#: `DV-5` 문면의 「기본 20년」. **대장의 기대값이므로 여기 적는다** — 이 파일이
#: 확인하는 것이 「대장이 그 값을 갖는가」이고, 기대값을 대장에서 다시 읽어 오면
#: 그 비교는 항진이 된다(R29 가 걷어낸 형태).
DV5_DEFAULT_YEARS = 20

#: 배포 코드에 되살아나면 안 되는 상수 이름 — R31 이 지운 그것.
_FORBIDDEN_CONSTANT = "HORIZON_YEARS"


def _identifiers(source: Path) -> set[str]:
    """소스의 **식별자** — 이름·속성·대입 대상. 주석·독스트링은 들지 않는다."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.rsplit(".", 1)[-1])
    return names


def _set(value: object) -> AssumptionSet:
    """분석기간 항목 하나만 든 최소 대장."""
    return AssumptionSet(
        name="검사", version="1",
        items={
            ANALYSIS_PERIOD_KEY: AssumptionItem(
                key=ANALYSIS_PERIOD_KEY,
                value=value,  # type: ignore[arg-type]
                value_unit="년",
                base_year="2026",
                applicable_scope="검사용",
                derivation_method="검사용",
                source=None,
                verified_at=None,
                confidence=ConfidenceLevel.ASSUMED,
            )
        },
        price_basis=PriceBasis.NOMINAL,
    )


# ── ① 대장이 그 값을 갖는다 ──────────────────────────────────────────

@pytest.mark.req("NFR-303-M1")
def test_the_real_ledger_owns_the_analysis_period() -> None:
    """실물 대장이 `DV-5` 의 「기본 20년」을 갖는다.

    기대값을 대장에서 다시 읽지 않고 **문면의 20 을 직접 적는다** — 대장에서
    읽어 대장과 비교하면 무엇을 넣어도 통과한다.
    """
    assumptions = AssumptionSet.load_from_yaml(str(LEDGER))

    assert assumptions.analysis_years() == DV5_DEFAULT_YEARS


@pytest.mark.req("NFR-303-M1")
def test_a_ledger_without_the_period_stops_instead_of_defaulting() -> None:
    """항목이 없으면 `MissingAssumption` 으로 멈춘다 — 20 으로 메우지 않는다.

    메우면 「대장에 없다」가 「대장에 20이 있다」와 구별되지 않고, 그것이
    `MissingAssumption` 이 존재하는 이유 그대로다.
    """
    empty = AssumptionSet(
        name="검사", version="1", items={}, price_basis=PriceBasis.NOMINAL
    )

    with pytest.raises(MissingAssumption) as caught:
        empty.analysis_years()

    assert caught.value.key == ANALYSIS_PERIOD_KEY


# ── ② 사용자가 고를 수 있다 ──────────────────────────────────────────

@pytest.mark.req("NFR-303-M1")
def test_a_scenario_override_changes_the_analysis_period() -> None:
    """★ **오버라이드가 값을 바꾼다 — 그래서 「사용자가 고르는 값」이다.**

    이것이 전용 필드가 아니라 대장 항목으로 둔 이유다. 항목이면 `FR-602` 의
    오버라이드 기계가 그대로 쓰이고, 바꾼 사실이 리포트에 표기된다 — 전용
    필드로 두면 그 셋을 따로 지어야 한다.
    """
    base = AssumptionSet.load_from_yaml(str(LEDGER))
    chosen = base.override(
        {ANALYSIS_PERIOD_KEY: 15}, reasons={ANALYSIS_PERIOD_KEY: "특구 지정 기간"}
    )

    assert chosen.analysis_years() == 15
    # 원본은 그대로다 — 오버라이드는 복제다
    assert base.analysis_years() == DV5_DEFAULT_YEARS
    assert chosen.get_override_reasons()[ANALYSIS_PERIOD_KEY] == "특구 지정 기간"


# ── ③ 분석기간일 수 없는 값은 거부한다 ───────────────────────────────

@pytest.mark.req("NFR-303-M1")
@pytest.mark.parametrize("bad", [0, -5, 12.5])
def test_a_value_that_cannot_be_an_analysis_period_is_refused(bad: object) -> None:
    """0·음수·소수를 거부한다.

    통과시키면 프로포마의 연도 범위가 비거나(0년) 거꾸로 돌고, 그 결과는
    「편익이 없는 사업」으로 그럴듯하게 나온다.

    ⚠ **상한은 여기서 재지 않는다** — 상한(최장 자원 수명 × 2)은 자원 수명을
    알아야 하므로 `core/cba/proforma.py::check_analysis_period()` 가 재며, 그것은
    전제 층보다 위에 산다(계층 규칙상 `core.assumption` 은 `core.cba` 를 import
    할 수 없다). 여기가 보는 것은 **값 자체가 분석기간일 수 있는가**뿐이다.
    """
    with pytest.raises(ValidationError) as caught:
        _set(bad).analysis_years()

    assert caught.value.rule == "DV-5"
    assert caught.value.field == "assumption_set.analysis_years"


@pytest.mark.req("NFR-303-M1")
def test_an_integer_valued_float_is_accepted() -> None:
    """`20.0` 은 받는다 — YAML 이 정수를 실수로 싣는 경우가 있다.

    거부하면 대장 편집자가 이유를 알 수 없는 실패를 만난다. 거부 대상은
    **정수가 아닌 값**이지 실수 표기가 아니다.
    """
    assert _set(20.0).analysis_years() == 20


# ── ④ 코드에 기본값 상수가 되살아나지 않았다 ─────────────────────────

def test_no_analysis_period_default_lives_in_the_calculation_layers() -> None:
    """★★ **`HORIZON_YEARS` 같은 상수가 배포 코드에 없다.**

    R31 이 `core/casegrid/e2e_runner.py` 에서 그 상수를 지웠다. 되살아나면
    대장을 고쳐도 계산이 옛 값을 쓰고, **그 어긋남은 NPV 를 바꾸면서 아무 예외도
    내지 않는다** — 위 셋은 전부 초록불인 채다.

    이름으로 찾는다. 이름을 바꿔 되살리면 이 검사를 피할 수 있지만, 그때는
    `test_e2e_analysis_period_wiring.py::test_the_runner_declares_no_default_horizon`
    가 **시그니처의 기본값**을 붙든다 — 두 검사가 같은 결함의 앞뒤를 본다.

    ⚠ **문자열이 아니라 `ast` 식별자를 본다.** 문면으로 찾으면 *「이 상수를
    지웠다」* 고 설명하는 주석 자신이 위반으로 잡힌다 — 실제로 첫 실행에서
    `e2e_runner.py` 가 그렇게 걸렸고, 이 저장소가 일곱 번째로 만난 형태다.
    주석은 AST 에 남지 않고 독스트링은 식별자가 아니므로 저절로 빠진다.
    """
    offenders = [
        str(source.relative_to(ROOT))
        for package in ("core", "app", "infra")
        for source in sorted((ROOT / package).rglob("*.py"))
        if _FORBIDDEN_CONSTANT in _identifiers(source)
    ]

    assert offenders == [], (
        f"분석기간 기본값 상수가 배포 코드에 있습니다: {offenders}. "
        "소유자는 `AssumptionSet` 입니다(§7.1 O-1) — 대장 항목 "
        f"`{ANALYSIS_PERIOD_KEY}` 를 `provider.analysis_years()` 로 읽으십시오"
    )
