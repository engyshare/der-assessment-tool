"""**가구 수가 리포트까지 간다** — 시나리오 → 러너 → 스윕 → 산출물 (R64/WP-1).

사용자 요구 1(*「가구수를 변경할 수 있어야 함」*)이 성립하려면 세 가지가 함께
서야 한다:

    ① 시나리오가 적은 수가 **본 실행**의 총부하를 키운다
    ② **스윕**(5절 민감도 · 6절 용량 검토)도 같은 규모로 돈다
    ③ 산출물이 **몇 호로 돌았는지**를 인쇄한다 — 안 준 실행도 인쇄한다

②가 빠지면 본문 4절은 n호 단지인데 5·6절은 한 호가 되고, **두 절 모두 자기
기준에서는 매끈하므로 아무 검사도 걸리지 않는다** — 이 저장소가 형상(R37)·
기준선 갈래(R60)·REC(R52)에서 세 번 밟은 형태이며, 그래서 그 셋과 **같은
방식**으로 붙든다.

③이 빠지면 검토자가 아래 모든 금액을 단지 전체의 것으로 읽는다. 40호 단지라면
40배 틀리게 읽는 것이고, 그 오독은 심의 자료가 인쇄된 뒤에 발견된다.

## ⚠ 「안 준 실행이 종전과 같다」는 여기서 재지 않는다

그 동일성의 정본은 `tests/golden/test_regression_scenarios.py::
test_golden_scenarios_match_current_regression_snapshot` 이다 — 골든 셋에
`household_count` 필드가 없으므로 그 회귀가 통째로 이 축의 불변을 잰다.
부하 자원 수준의 동일성은 `tests/casegrid/test_household_count.py` 가 잰다.
여기서는 **필드를 준 실행**만 본다.

## ⚠ `req()` 마커를 달지 않았다

사유는 `tests/casegrid/test_household_count.py` 머리말이 갖는다 — spec 에서
「가구수」는 화면 구조도 한 줄뿐이고 수용기준이 아니다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.assumption.provider import AssumptionSet
from core.casegrid.household_scale import (
    HOUSEHOLD_COUNT_FIELD,
    HOUSEHOLD_COUNT_LEDGER_KEY,
    HOUSEHOLD_COUNT_UNSPECIFIED,
    ledger_household_count,
)
from core.contracts.validation import ValidationError
from core.report.appendix_sections import HOUSEHOLD_SCALE_TABLE, appendix_section
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import CaseReport, build_case_report

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 잉여가 남는 규모. 사유는 `tests/casegrid/test_household_count.py::_COUNT`.
_COUNT = 2

#: 대장이 답하는 가구 수 (R65 · 사용자 요구 *「가구수를 20가구로 설정」*).
#: ⚠ **여기 리터럴로 박지 않는다** — 대장이 바뀌는 날 이 시험만 조용히 낡는다.
_LEDGER_COUNT = ledger_household_count(
    AssumptionSet.load_from_yaml(_ASSUMPTIONS)
)


def _blocked_ledger_text() -> str:
    """★ **가구 수를 «아무 통로도» 갖지 않는 대장** (R65/WP-2c).

    R65 가 `load.household.count` 를 `track: blocked` → `fixed`·**20** 으로
    세우면서 *「안 준 실행」* 의 뜻이 달라졌다 — 시나리오에 안 적어도 **대장이
    답한다.** 그래서 「미지정」 갈래를 재려면 그 항목이 답하지 않는 대장이
    있어야 하고, 이 함수가 **R65 이전과 같은 모양**(`blocked` · 값 없음)으로
    되돌린 사본을 만든다.

    ⛔ **`docs/assumptions.yaml` 을 고치는 것이 아니다** — 읽어서 사본을 짓고
    그 사본은 `tempfile` 안에서만 산다. ⚠ 값을 지어내지 않는다 — 지우는 것뿐이다.
    """
    doc = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    for item in doc["assumptions"]:
        if item.get("key") == HOUSEHOLD_COUNT_LEDGER_KEY:
            item["track"] = "blocked"
            item["value"] = None
            item["sensitivity"] = None
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


def _report(count: object | None = None, *, ledger_answers: bool = True) -> CaseReport:
    """골든 시나리오 + 가구 수 → 리포트 하나.

    ⚠ **골든 픽스처를 고치지 않는다.** 읽기만 하고 쓰는 곳은
    `tempfile.TemporaryDirectory()` 안이다 — `app/services/ui_run.py::
    run_ui_case` 가 배포 경로에서 하는 것과 같은 모양이며, 그래야 이 검사가
    화면이 실제로 지나는 통로(시나리오 필드 하나)를 잰다.

    `ledger_answers=False` 면 **대장 통로까지 닫은** 사본으로 돈다
    (`_blocked_ledger_text` 참조) — 「어느 통로에도 값이 없다」를 재는 자리다.
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    if count is not None:
        fields[HOUSEHOLD_COUNT_FIELD] = count
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / _GOLDEN.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        ledger = _ASSUMPTIONS
        if not ledger_answers:
            ledger = Path(workspace) / "assumptions.yaml"
            ledger.write_text(_blocked_ledger_text(), encoding="utf-8")
        return build_case_report(path, assumptions_path=ledger)


def test_the_scenario_field_wins_over_the_ledger() -> None:
    """★★ 시나리오 yaml 의 필드 하나가 리포트까지 그대로 가고, **대장을 이긴다.**

    ## ⚠ 이 시험이 재던 것이 뒤집혔다 — **낡은 것이 아니라 반대 사실이었다**

    옛 이름은 `test_the_scenario_field_is_the_only_channel` 이었고
    *「통로가 하나다 — 시나리오에 안 적으면 `None` 이다」* 를 쟀다. 그때는 그것이
    옳았다: 대장의 `load.household.count` 가 `track: blocked` 였고 그 항목이
    *「**가정하면 안 된다.** 사업 계획이 정하는 사실이다」* 로 못 박았으므로
    값의 통로가 실행 입력 하나뿐이었다.

    **R65 에 그 사실을 정하는 쪽이 값을 주었다** — 사용자 요구 원문
    *「가구수를 20가구로 설정」*(2026-09-07). 저장소가 고른 수가 아니라 회신을
    받아 적은 것이므로 §13.0.2 자기충족이 아니고, 대장이 그 값을 갖는 것이
    옳다(`core/casegrid/household_scale.py::ledger_household_count` 가 정본).

    ⇒ 그러므로 **통로는 둘이고 차례가 있다.** 이 시험이 재는 것은 이제
    *「통로가 하나인가」* 가 아니라 **「차례가 지켜지는가」**다 — 뒤집히면
    사용자가 화면에서 적은 수를 대장이 덮어쓴다. ⚠ 통로를 **세는** 자리는
    그대로 여기 하나다.
    """
    assert _report().household_count == _LEDGER_COUNT, (
        "시나리오가 안 적은 실행이 대장의 가구 수로 돌지 않는다"
    )
    assert _report(_COUNT).household_count == _COUNT, (
        "시나리오가 적은 수를 대장이 덮어썼다 — 차례가 뒤집혔다"
    )
    assert _report(ledger_answers=False).household_count is None, (
        "어느 통로에도 값이 없는데 가구 수가 섰다 — 어딘가 기본값을 지어냈다"
    )


def test_the_body_runs_on_the_bigger_site() -> None:
    """★★★ 가구 수를 주면 **결론축이 실제로 움직인다.**

    이 단언이 없으면 아래 검사들은 *「필드를 나르기만 하고 계산에 안 쓴다」*
    로도 통과한다 — 이 저장소가 반복해 만난 「표시만 하는 구현」이다.
    """
    one = float(_report().metrics[CONCLUSION_METRIC])
    many = float(_report(_COUNT).metrics[CONCLUSION_METRIC])
    assert many != pytest.approx(one, abs=1.0), (
        f"{_COUNT}호 단지의 결론축이 한 호와 같다({one:,.0f}원) — 가구 수가 "
        "계산에 들어가지 않았다"
    )


def test_the_sweep_runs_on_the_same_site_size_as_the_body() -> None:
    """★★★ **5·6절의 스윕도 같은 규모로 돈다** — 두 절이 다른 사업을 그리지 않는다.

    ## 어떻게 재는가 — 「읽지 않는 인자」가 스윕의 **기준선**을 드러낸다

    `unread_by_pipeline` 인 인자는 끝에서 끝까지 흔들어도 결론축이 0원
    움직인다. 그러므로 그 인자의 `npv_low`·`npv_high` 는 **스윕의 기준선
    그 자체**이며, 스윕이 본 실행과 다른 규모로 돌면 그 값이 본문의 결론과
    갈린다. `tests/report/test_irradiance_wired.py::
    test_the_influence_endpoints_move_with_the_shaped_run` 이 형상 축에서
    같은 방법을 쓴다.
    """
    report = _report(_COUNT)
    conclusion = float(report.metrics[CONCLUSION_METRIC])
    unread = [entry for entry in report.influences if entry.unread_by_pipeline]
    assert unread, (
        "파이프라인이 읽지 않는 인자가 0건이다 — 이 검사가 0회 순회로 통과한다"
    )
    for entry in unread:
        assert entry.npv_low == pytest.approx(conclusion, abs=1.0), (
            f"`{entry.variable}` 의 스윕 기준선이 {entry.npv_low:,.0f}원인데 "
            f"본문 결론은 {conclusion:,.0f}원이다 — 스윕이 다른 가구 수로 "
            "돌고 있다"
        )
        assert entry.npv_high == pytest.approx(conclusion, abs=1.0)


def test_the_appendix_prints_the_size_it_ran_on() -> None:
    """★★ 붙임 1 이 **몇 호로 돌았는지**를 표로 싣는다."""
    lines = appendix_section(_report(_COUNT))
    assert any(HOUSEHOLD_SCALE_TABLE in line for line in lines), (
        f"붙임 1 에 「{HOUSEHOLD_SCALE_TABLE}」 표가 없다"
    )
    assert any(f"{_COUNT:,}호" in line for line in lines), (
        f"붙임 1 이 가구 수 {_COUNT}호를 인쇄하지 않는다"
    )


def test_an_unspecified_size_is_printed_as_words_not_left_blank() -> None:
    """★★★ **안 준 실행도 글자로 말한다** — 빈칸으로 두지 않는다 (판정 ③).

    빈칸은 「반영됐다」와 「반영하지 않았다」를 구별해 주지 않고, 사용자는
    앞쪽으로 읽는다. 그 오독이 단지 총부하를 통째로 틀리게 만든다.

    ⚠ **「안 준 실행」의 뜻이 R65 에 달라졌다** — 시나리오에 안 적어도 대장이
    답하므로, 여기서는 **대장 통로까지 닫은** 사본으로 돈다
    (`_blocked_ledger_text`). 재는 것은 그대로다: *「어느 통로에도 값이 없는
    실행이 그 사실을 글자로 말하는가」*.
    """
    lines = appendix_section(_report(ledger_answers=False))
    assert any(HOUSEHOLD_COUNT_UNSPECIFIED in line for line in lines), (
        f"가구 수를 안 준 실행의 붙임 1 에 「{HOUSEHOLD_COUNT_UNSPECIFIED}」가 "
        "없다 — 빈칸으로 두면 검토자가 단지 전체의 금액으로 읽는다"
    )


def test_a_scenario_that_asks_for_no_households_is_refused() -> None:
    """★ 시나리오가 적은 값도 **같은 자리에서** 판정된다 (`NFR-303`).

    거부 문면이 층마다 생기지 않게 `resolve_household_count` 하나가 진다.
    """
    with pytest.raises(ValidationError, match="가구 수"):
        _report(0)
