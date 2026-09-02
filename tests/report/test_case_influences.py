"""**본 실행과 영향도 스윕이 같은 사업을 그리는가** — 분리된 스윕을 기계로 붙든다 (R54).

## 왜 이 파일이 새로 필요한가

R53 이 `_Sweeper` 에 `distributed_credit_won_per_year` 배선 하나를 빠뜨렸고
**아무 검사도 그것을 잡지 못했다.** WP-2(R54) 에서 사람이 두 호출부를 손으로
전수 대조해서야 찾았다 — 다음에 러너가 인자를 하나 더 받으면 같은 일이
되풀이된다. 이 파일은 **그 대조를 검사가 하게 만든다**(WP-2-fix).

## 세 검사의 층

    검사 ①  두 호출부의 **인자 이름 집합**  ← 소스를 AST 로 (ⓐ)
    검사 ②  재수출 여섯이 **같은 객체**      ← 실행하여 `is` 로
    검사 ③  스윕이 값을 **실제로 넘기는가**  ← spy 로 (ⓑ)

①이 「이름이 같다」를 재면 ③은 「값이 흐른다」를 잰다. ①만 있으면 상수를
박아 넘기는 구현이 통과하고, ③만 있으면 인자가 늘어난 날을 못 본다.

## ⚠ `req()` 마커

①·③ 은 `FR-1002-AC2` 를 달았다 — 그 조항이 재는 것은 *「각 인자를 합리적
변동 범위에서 변동시켜 주 지표가 움직인 폭으로 측정한다」* 이고, 스윕이 본
실행과 다른 배선으로 돌면 그 폭은 **다른 사업의 것**이 된다
(`test_case_report.py::test_the_sweep_follows_the_supported_variant_too` 가
같은 조항을 같은 이유로 인용한다). ② 는 조항이 아니라 R54 분리의 「동작을
안 바꾼다」 약속을 붙드는 것이므로 달지 않았다 — 가까워 보이는 ID 를 짐작해
붙이는 것은 `test_irradiance_wired.py` 독스트링이 경계하는 상태다.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.casegrid.profiles import load_daily_shapes
from core.report import case_influences, case_report
from core.report.case_report import CONCLUSION_METRIC, PLAN_VARIANT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAIN_RUN_SOURCE = _REPO_ROOT / "core" / "report" / "case_report.py"
_SWEEP_SOURCE = _REPO_ROOT / "core" / "report" / "case_influences.py"
_RUNNER = "run_single_case_e2e"


def _runner_keywords(source_path: Path, scope: str) -> set[str]:
    """`scope` 함수 안의 `_RUNNER(...)` 호출이 넘기는 키워드 인자 이름 전체.

    ⚠ **호출은 정확히 한 벌이어야 한다.** 0개면 두 집합이 모두 빈 채로 같아
    아래 비교가 공허하게 초록이 되고, 둘 이상이면 어느 지점의 것인지 모른 채
    섞인다 — 둘 다 이 함수의 `assert` 가 먼저 막는다(0회 순회로 통과하는
    검사는 검사가 아니다).

    ⚠ `**전개` 로 넘기는 인자는 이름을 셀 수 없다 — 조용히 건너뛰면 그 인자는
    이 검사의 사각이 되므로 **빨간불로 막는다**.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    scopes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == scope
    ]
    assert len(scopes) == 1, (
        f"{source_path.name} 에 `{scope}` 정의가 {len(scopes)}곳이다 — "
        "1곳이어야 한다"
    )
    calls = [
        node
        for node in ast.walk(scopes[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == _RUNNER
    ]
    assert calls, (
        f"{source_path.name}::{scope} 안에 `{_RUNNER}(...)` 호출이 없다 — "
        "두 집합이 모두 빈 채로 같아져 이 검사가 아무것도 잡지 못한다"
    )
    keywords: set[str] = set()
    for call in calls:
        starred = [k for k in call.keywords if k.arg is None]
        assert not starred, (
            f"{source_path.name}::{scope} 의 `{_RUNNER}(...)` 가 `**전개` 로 "
            "인자를 넘긴다 — 이름 집합을 소스에서 셀 수 없어 이 검사가 못 "
            "본다. 펼쳐 쓰거나 이 검사를 다시 세우라"
        )
        keywords.update(k.arg for k in call.keywords)
    return keywords


@pytest.mark.req("FR-1002-AC2")
def test_the_sweep_and_the_main_run_pass_the_same_runner_kwargs() -> None:
    """★★★ 두 호출부가 러너에 넘기는 **인자 이름 집합**이 같다 (R53 재발 방지).

    `build_case_report()` 의 본 실행과 `_Sweeper.conclusion_at_many()` 의 스윕은
    같은 `run_single_case_e2e` 를 부른다. 한쪽에만 인자가 있으면 **본문과 5.1
    이 서로 다른 사업을 그린다** — 각 절은 자기 기준에서 매끈하므로 아무
    검사도 걸리지 않는다(R37 이 일사 곡선으로, R48/WP-F 가 가구 부하로,
    R52/WP-6 이 REC 로 각각 겪은 함정이며, R53 은
    `distributed_credit_won_per_year` 를 빠뜨리고 이 검사가 없어서 사람이
    찾아야 했다).

    ⚠⚠ **어느 쪽도 손 목록이 아니다.** 두 자리에서 각각 읽어 서로 비교한다 —
    「지금 이 여덟 개다」를 박아 넣으면 인자가 늘 때마다 검사도 손으로
    고쳐야 하고, 그것은 빠뜨림을 잡는 힘이 없다.

    ## 왜 ⓐ AST 인가 (ⓑ spy 가 아니라)

    재는 대상이 **호출부가 쓴 문면**이므로 소스에서 읽는 것이 정직하다 — spy
    는 한 번의 실행을 보므로, 그 실행에서 값이 흐르지 않는 인자는 이름 자체를
    못 본다. `tests/contract/source_scan.py` 본보기 그대로 `ast.walk` 로
    훑는다(R39-A — 줄 필터는 들여쓴 호출을 놓친다). 값이 실제로 흐르는지는
    아래 검사 ③ 이 잰다.
    """
    main = _runner_keywords(_MAIN_RUN_SOURCE, "build_case_report")
    sweep = _runner_keywords(_SWEEP_SOURCE, "conclusion_at_many")

    only_main = sorted(main - sweep)
    only_sweep = sorted(sweep - main)
    assert not (only_main or only_sweep), (
        f"본 실행(`build_case_report`)에만 있는 인자: {only_main} — 스윕이 안 "
        "넘기면 본문과 5.1 이 서로 다른 사업을 그린다(R53 이 빠뜨렸던 형태). "
        f"스윕(`_Sweeper.conclusion_at_many`)에만 있는 인자: {only_sweep} — "
        "본 실행이 안 넘기면 5.1 이 본문이 본 적 없는 사업을 그린다"
    )


def test_the_reexports_are_the_same_objects() -> None:
    """★ `case_report.__all__` 이 재수출하는 이름이 `case_influences` 의 **같은 객체**다.

    ⚠ **왜 값(`==`)이 아니라 동일성(`is`)인가.** 값이 같은 별개 객체로
    갈라지면 — 예컨대 한쪽만 고쳐 상수를 다시 정의하면 — `==` 로는 초록인데,
    밖에서 `case_report` 경로로 읽는 곳(R54/WP-2-fix 실측 12곳 ·
    `narrative.py`·`shortfall.py`·`verification.py`·검사 파일)은 **조용히 다른
    값을 본다**. 문자열·숫자 상수의 `==` 는 값이 같으면 늘 참이므로 갈라짐을
    전혀 못 잡는다.

    재수출 목록을 손으로 여섯 개 적지 않고 `case_report.__all__` 에서 읽는다 —
    하드코딩하면 재수출이 늘어난 날 이 검사가 그것을 덮지 못한 채 초록으로
    남는다.
    """
    missing = [
        name for name in case_report.__all__
        if not hasattr(case_influences, name)
    ]
    assert not missing, (
        f"case_report.__all__ 의 이름이 case_influences 에 없다: {missing} — "
        "재수출의 정본은 case_influences 다"
    )
    forked = [
        name
        for name in case_report.__all__
        if getattr(case_report, name) is not getattr(case_influences, name)
    ]
    assert not forked, (
        f"재수출이 별개 객체다: {forked} — 밖에서 case_report 경로로 읽는 곳이 "
        "정본(case_influences)과 다른 값을 본다. 분리가 「동작을 안 바꾼다」를 "
        "어기는 자리다"
    )


@pytest.mark.req("FR-1002-AC2")
def test_the_sweeper_hands_the_distributed_credit_to_the_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★ 생성자가 받은 `distributed_credit_won_per_year` 가 러너까지 **그대로** 흐른다.

    검사 ① 이 「이름이 있다」를 재면 이것은 「값이 흐른다」를 잰다 — 이름은
    있으면서 다른 값을 넘기는 변이(예: 실수로 상수를 박는다)는 ① 이 못 본다.

    ## 왜 ⓑ spy 인가

    값의 도착은 **실행**으로만 보인다. 이 모듈이 import 한 이름
    (`case_influences.run_single_case_e2e`) 에 대고 가로채 실제로 넘어온
    인자를 녹음한다 — 파이프라인을 안 돌리므로 수 초짜리 검사로 끝난다.
    흘러간 값이 진짜 결론을 움직이는지는 진짜 재실행 검사
    (`test_irradiance_wired.py`) 가 이미 잰다.
    """
    recorded: dict[str, object] = {}

    def fake_runner(*args: object, **kwargs: object) -> object:
        recorded.update(kwargs)
        return SimpleNamespace(variants={PLAN_VARIANT: {CONCLUSION_METRIC: 1.0}})

    monkeypatch.setattr(case_influences, "run_single_case_e2e", fake_runner)

    wired = 123_456.0  # ← 흘러들어온 그 수인지 알 수 있게, 헷갈릴 여지 없는 수
    sweeper = case_influences._Sweeper(
        level_map={
            "household_load_annual_kwh": {"low": 1.0, "base": 2.0, "high": 3.0}
        },
        horizon_years=10,
        scheme=None,
        daily_shapes=load_daily_shapes(),
        rec_price_won_per_unit=70.0,
        rec_weight_pv=0.5,
        distributed_credit_won_per_year=wired,
    )
    sweeper.conclusion_at_many({"household_load_annual_kwh": 5.0})

    assert recorded, "스파이가 호출을 녹음하지 못했다 — 이 검사가 아무것도 보지 못했다"
    assert recorded["distributed_credit_won_per_year"] == wired, (
        f"생성자는 {wired:,.0f}원을 받았는데 러너에는 "
        f"{recorded.get('distributed_credit_won_per_year')!r} 이 닿았다 — "
        "스윕이 본 실행과 다른 사업을 그린다(R53/WP-1 이 저지르고 R54/WP-2 가 "
        "메운 바로 그 배선이다)"
    )
