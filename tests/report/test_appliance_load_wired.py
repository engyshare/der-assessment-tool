"""**기기 부하가 리포트까지 간다** — 시나리오 → 러너 → 스윕 → 산출물 (R64/WP-2).

사용자 요구 2(*「가구의 전기 부하 설정을 변경할 수 있어야 함 (EV, heatpump,
AI 가전)」*)가 성립하려면 세 가지가 함께 서야 한다:

    ① 시나리오가 적은 값이 **본 실행**의 총부하를 키운다
    ② **스윕**(5절 민감도 · 6절 용량 검토)도 같은 부하로 돈다
    ③ 산출물이 **무엇을 얼마나 얹었는지**를 인쇄한다 — 안 얹은 실행도 인쇄한다

②가 빠지면 본문 4절은 히트펌프가 있는 가구인데 5·6절은 없는 가구가 되고,
**두 절 모두 자기 기준에서는 매끈하므로 아무 검사도 걸리지 않는다** — 이
저장소가 형상(R37)·기준선 갈래(R60)·REC(R52)·가구 수(R64/WP-1)에서 네 번 밟은
형태이며, 그래서 그 넷과 **같은 방식**으로 붙든다.

③이 빠지면 검토자가 아래 모든 금액을 「기기를 반영한 수」로 읽는다. 사용자가
건넨 참고 표준 모델대로라면 한 호의 연간 수요 9,252kWh 중 **5,087kWh 가 그
둘**이므로, 그 오독은 총부하를 절반 가까이 틀리게 읽는 것이다.

## ⚠ 「안 준 실행이 종전과 같다」는 여기서 재지 않는다

그 동일성의 정본은 `tests/golden/test_regression_scenarios.py::
test_golden_scenarios_match_current_regression_snapshot` 이다 — 골든 셋에 두
필드가 없으므로 그 회귀가 통째로 이 축의 불변을 잰다. 부하 자원 수준의
동일성은 `tests/casegrid/test_appliance_load.py` 가 잰다. 여기서는 **필드를 준
실행**만 본다.

## ⚠ `req()` 마커를 달지 않았다

사유는 `tests/casegrid/test_appliance_load.py` 머리말이 갖는다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.casegrid.appliance_load import (
    APPLIANCE_LOAD_UNSPECIFIED,
    APPLIANCE_SEASON_SHARE_FIELD,
    EV_LOAD_FIELD,
    EV_LOAD_LEDGER_KEY,
    HEATPUMP_LOAD_FIELD,
    HEATPUMP_LOAD_LEDGER_KEY,
)
from core.casegrid.profiles import load_daily_shapes
from core.contracts.validation import ValidationError
from core.report.appendix_sections import APPLIANCE_LOAD_TABLE, appendix_section
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import CaseReport, build_case_report

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 시험용 기기 부하. **참고자료의 값(2,675·2,412)을 박지 않는다** — 사유는
#: `tests/casegrid/test_appliance_load.py::_HEATPUMP` 가 갖는다.
_HEATPUMP = 900.0
_EV = 600.0


def _blocked_ledger_text() -> str:
    """★ **기기 부하를 «아무 통로도» 갖지 않는 대장** (R65/WP-2c).

    R65 가 `load.heatpump.annual`(2,675 · 가정) · `load.ev.annual`(2,784 ·
    조사값)을 `track: blocked` → 값 있음으로 세우면서 *「안 준 실행」* 의 뜻이
    달라졌다 — 시나리오에 안 적어도 **대장이 답한다.** 그래서 「미지정」 갈래를
    재려면 그 두 항목이 답하지 않는 대장이 있어야 하고, 이 함수가 **R65 이전과
    같은 모양**(`blocked` · 값 없음)으로 되돌린 사본을 만든다.

    ⛔ **`docs/assumptions.yaml` 을 고치는 것이 아니다** — 읽어서 사본을 짓고
    그 사본은 `tempfile` 안에서만 산다. ⚠ 값을 지어내지 않는다 — 지우는 것뿐이다.
    ⚠ **`load.household.count` 는 그대로 둔다** — 이 파일이 재는 축이 아니다.
    """
    doc = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    for item in doc["assumptions"]:
        if item.get("key") in {HEATPUMP_LOAD_LEDGER_KEY, EV_LOAD_LEDGER_KEY}:
            item["track"] = "blocked"
            item["value"] = None
            item["sensitivity"] = None
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


def _report(**fields_given: object) -> CaseReport:
    """골든 시나리오 + 기기 부하 → 리포트 하나.

    `ledger_answers=False` 를 주면 **대장 통로까지 닫은** 사본으로 돈다
    (`_blocked_ledger_text` 참조) — 「어느 통로에도 값이 없다」를 재는 자리다.

    ⚠ **골든 픽스처를 고치지 않는다.** 읽기만 하고 쓰는 곳은
    `tempfile.TemporaryDirectory()` 안이다 — `app/services/ui_run.py::
    run_ui_case` 가 배포 경로에서 하는 것과 같은 모양이며, 그래야 이 검사가
    화면이 실제로 지나는 통로(시나리오 필드 둘)를 잰다.
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    ledger_answers = bool(fields_given.pop("ledger_answers", True))
    fields.update(fields_given)
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


def test_the_scenario_fields_win_over_the_ledger() -> None:
    """★★ 시나리오 yaml 의 필드 둘이 리포트까지 그대로 가고, **대장을 이긴다.**

    ## ⚠ 이 시험이 재던 것이 뒤집혔다 — **낡은 것이 아니라 반대 사실이었다**

    옛 이름은 `test_the_scenario_fields_are_the_only_channel` 이었고
    *「통로가 하나다 — 시나리오에 안 적으면 `None` 이다」* 를 쟀다. 그때는 그것이
    옳았다: 대장의 두 항목이 `track: blocked` 였다.

    **R65 에 사용자가 값을 정해 주었다** — *「히트펌프, 전기차 충전 연간
    소비전력량 … 엑셀 파일 상의 수치를 사용(조사 권장)」*(2026-09-07). 그래서
    `load.heatpump.annual`(2,675 · `가정`)·`load.ev.annual`(2,784 · `추정` —
    조사값)이 섰고 **통로가 둘이 되었다.**

    ⇒ 이 시험이 재는 것은 이제 *「통로가 하나인가」* 가 아니라 **「차례가
    지켜지는가」**다 — 뒤집히면 사용자가 화면에서 적은 값을 대장이 덮어쓴다.
    ⚠ 통로를 **세는** 자리는 그대로 여기 하나다.
    """
    from_ledger = _report().appliance_loads
    assert from_ledger.heatpump_kwh is not None, (
        "시나리오가 안 적은 실행이 대장의 히트펌프 부하로 돌지 않는다"
    )
    assert from_ledger.ev_kwh is not None, (
        "시나리오가 안 적은 실행이 대장의 전기차 부하로 돌지 않는다"
    )

    empty = _report(ledger_answers=False).appliance_loads
    assert empty.heatpump_kwh is None
    assert empty.ev_kwh is None

    given = _report(
        **{HEATPUMP_LOAD_FIELD: _HEATPUMP, EV_LOAD_FIELD: _EV}
    ).appliance_loads
    assert given.heatpump_kwh == _HEATPUMP
    assert given.ev_kwh == _EV
    assert given.total_kwh == pytest.approx(_HEATPUMP + _EV)


def test_the_body_runs_on_the_bigger_load() -> None:
    """★★★ 기기 부하를 주면 **결론축이 실제로 움직인다.**

    이 단언이 없으면 아래 검사들은 *「필드를 나르기만 하고 계산에 안 쓴다」*
    로도 통과한다 — 이 저장소가 반복해 만난 「표시만 하는 구현」이다.
    """
    plain = float(_report().metrics[CONCLUSION_METRIC])
    loaded = float(
        _report(**{HEATPUMP_LOAD_FIELD: _HEATPUMP}).metrics[CONCLUSION_METRIC]
    )
    assert loaded != pytest.approx(plain, abs=1.0), (
        f"히트펌프 {_HEATPUMP:,.0f}kWh/호·년을 얹었는데 결론축이 그대로다"
        f"({plain:,.0f}원) — 기기 부하가 계산에 들어가지 않았다"
    )


def test_the_two_appliances_are_not_interchangeable_in_the_output() -> None:
    """★★ **둘이 각자 이름을 갖는다** — 뭉뚱그린 칸 하나가 아니다 (판정 ③).

    합계가 같아도 산출물은 어느 기기가 얼마인지 말해야 한다. 하나로 합치면
    사용자가 따로 바꾸지 못하고, 요구가 기기를 나열한 이유가 사라진다.
    """
    swapped = _report(**{HEATPUMP_LOAD_FIELD: _EV, EV_LOAD_FIELD: _HEATPUMP})
    straight = _report(**{HEATPUMP_LOAD_FIELD: _HEATPUMP, EV_LOAD_FIELD: _EV})
    assert swapped.appliance_loads != straight.appliance_loads
    assert swapped.appliance_loads.total_kwh == straight.appliance_loads.total_kwh
    lines = appendix_section(straight)
    assert any(f"{_HEATPUMP:,.0f}" in line and "히트펌프" in line for line in lines)
    assert any(f"{_EV:,.0f}" in line and "전기차" in line for line in lines)


def test_the_sweep_runs_on_the_same_load_as_the_body() -> None:
    """★★★ **5·6절의 스윕도 같은 부하로 돈다** — 두 절이 다른 사업을 그리지 않는다.

    ## 어떻게 재는가 — 「읽지 않는 인자」가 스윕의 **기준선**을 드러낸다

    `unread_by_pipeline` 인 인자는 끝에서 끝까지 흔들어도 결론축이 0원
    움직인다. 그러므로 그 인자의 `npv_low`·`npv_high` 는 **스윕의 기준선
    그 자체**이며, 스윕이 본 실행과 다른 부하로 돌면 그 값이 본문의 결론과
    갈린다. `tests/report/test_household_count_wired.py::
    test_the_sweep_runs_on_the_same_site_size_as_the_body` 가 가구 수 축에서
    같은 방법을 쓴다.
    """
    report = _report(**{HEATPUMP_LOAD_FIELD: _HEATPUMP, EV_LOAD_FIELD: _EV})
    conclusion = float(report.metrics[CONCLUSION_METRIC])
    unread = [entry for entry in report.influences if entry.unread_by_pipeline]
    assert unread, (
        "파이프라인이 읽지 않는 인자가 0건이다 — 이 검사가 0회 순회로 통과한다"
    )
    for entry in unread:
        assert entry.npv_low == pytest.approx(conclusion, abs=1.0), (
            f"`{entry.variable}` 의 스윕 기준선이 {entry.npv_low:,.0f}원인데 "
            f"본문 결론은 {conclusion:,.0f}원이다 — 스윕이 다른 기기 부하로 "
            "돌고 있다"
        )
        assert entry.npv_high == pytest.approx(conclusion, abs=1.0)


def test_the_appendix_prints_what_it_ran_on() -> None:
    """★★ 붙임 1 이 **무엇을 얼마나 얹었는지**를 표로 싣는다."""
    lines = appendix_section(
        _report(**{HEATPUMP_LOAD_FIELD: _HEATPUMP, EV_LOAD_FIELD: _EV})
    )
    assert any(APPLIANCE_LOAD_TABLE in line for line in lines), (
        f"붙임 1 에 「{APPLIANCE_LOAD_TABLE}」 표가 없다"
    )
    assert any(f"{_HEATPUMP + _EV:,.0f}" in line for line in lines), (
        "붙임 1 이 한 호에 더해진 합계를 인쇄하지 않는다"
    )


def test_an_unspecified_appliance_is_printed_as_words_not_left_blank() -> None:
    """★★★ **안 준 실행도 글자로 말한다** — 빈칸으로 두지 않는다 (판정 ⑦).

    빈칸은 「반영됐다」와 「반영하지 않았다」를 구별해 주지 않고, 사용자는
    앞쪽으로 읽는다. 그 오독이 한 호의 총부하를 절반 가까이 틀리게 만든다.

    ⚠ **「안 준 실행」의 뜻이 R65 에 달라졌다** — 시나리오에 안 적어도 대장이
    답하므로, 여기서는 **대장 통로까지 닫은** 사본으로 돈다
    (`_blocked_ledger_text`). 재는 것은 그대로다: *「어느 통로에도 값이 없는
    실행이 그 사실을 글자로 말하는가」*.
    """
    lines = appendix_section(_report(ledger_answers=False))
    printed = [line for line in lines if APPLIANCE_LOAD_UNSPECIFIED in line]
    assert len(printed) == 2, (
        f"기기를 안 준 실행의 붙임 1 에 「{APPLIANCE_LOAD_UNSPECIFIED}」가 "
        f"{len(printed)}줄이다 — 히트펌프·전기차 두 줄 모두 서야 한다"
    )


def test_a_zero_is_printed_differently_from_an_unspecified_appliance() -> None:
    """★★★ **「0이라고 적었다」와 「적지 않았다」가 산출물에서 갈린다** (판정 ⑦).

    더해지는 값은 둘 다 0 이지만 진술이 다르다 — 같은 글자로 덮으면 검토자가
    *「그 기기가 없는 사업」* 과 *「아직 안 정한 사업」* 을 가릴 수 없다.
    """
    said_none = appendix_section(_report(**{HEATPUMP_LOAD_FIELD: 0}))
    heatpump_rows = [line for line in said_none if line.startswith("| 히트펌프")]
    assert len(heatpump_rows) == 1
    assert APPLIANCE_LOAD_UNSPECIFIED not in heatpump_rows[0], (
        f"0 이라고 적은 히트펌프가 「미지정」으로 인쇄됐다: {heatpump_rows[0]!r}"
    )
    assert "0 kWh" in heatpump_rows[0]


def test_a_scenario_that_asks_for_a_negative_load_is_refused() -> None:
    """★ 시나리오가 적은 값도 **같은 자리에서** 판정된다 (`NFR-303`).

    거부 문면이 층마다 생기지 않게 `resolve_appliance_load` 하나가 진다.
    """
    with pytest.raises(ValidationError, match="히트펌프"):
        _report(**{HEATPUMP_LOAD_FIELD: -1})


# ── 계절 몫 — 냉난방이 자기 계절 몫을 갖는다 (R64/WP-3b-1 · 사용자 요구 3) ──


def _season_heavy() -> dict[str, float]:
    """자산이 선언한 **마지막 계절**에 몰아 준 몫 — 합이 1 이다.

    ⚠ 계절 이름·개수를 박지 않는다(자산 머리말 ★). 사유는
    `tests/casegrid/test_appliance_season_shares.py::_winter_heavy` 가 갖는다.
    """
    names = [season.name for season in load_daily_shapes().load.seasons]
    rest = (1.0 - 0.7) / (len(names) - 1)
    return {name: (0.7 if name == names[-1] else rest) for name in names}


def test_the_season_shares_reach_the_body_and_move_the_conclusion() -> None:
    """★★★ **시나리오의 계절 몫이 본 실행의 결론축을 실제로 움직인다.**

    이 단언이 없으면 아래 검사가 *「필드를 나르기만 하고 계산에 안 쓴다」* 로도
    통과한다 — `test_the_body_runs_on_the_bigger_load` 와 같은 사유다.
    ⚠ 총량은 한 kWh 도 변하지 않는다. 움직이는 것은 **계절 사이의 배분**이며,
    그것이 태양광 잉여와 겹치는 시각을 바꾸므로 결론축이 따라 움직인다.
    """
    fields: dict[str, Any] = {HEATPUMP_LOAD_FIELD: 3000.0}
    plain = float(_report(**fields).metrics[CONCLUSION_METRIC])
    moved = float(
        _report(
            **fields, **{APPLIANCE_SEASON_SHARE_FIELD: _season_heavy()}
        ).metrics[CONCLUSION_METRIC]
    )
    assert moved != pytest.approx(plain, abs=1.0), (
        f"냉난방을 계절마다 차등했는데 결론축이 그대로다({plain:,.0f}원) — "
        "계절 몫이 계산에 들어가지 않았다"
    )


def test_the_sweep_runs_on_the_same_season_shares_as_the_body() -> None:
    """★★★ **5·6절의 스윕도 같은 계절 몫으로 돈다.**

    안 넘기면 본문 4절은 차등한 부하로, 5·6절은 차등하지 않은 부하로 계산되어
    두 절이 서로 다른 사업을 그린다 — 재는 법은 위
    `test_the_sweep_runs_on_the_same_load_as_the_body` 와 같다(읽지 않는 인자의
    스윕 기준선이 곧 스윕이 선 사업이다).
    """
    report = _report(
        **{HEATPUMP_LOAD_FIELD: 3000.0, APPLIANCE_SEASON_SHARE_FIELD: _season_heavy()}
    )
    conclusion = float(report.metrics[CONCLUSION_METRIC])
    unread = [entry for entry in report.influences if entry.unread_by_pipeline]
    assert unread, (
        "파이프라인이 읽지 않는 인자가 0건이다 — 이 검사가 0회 순회로 통과한다"
    )
    for entry in unread:
        assert entry.npv_low == pytest.approx(conclusion, abs=1.0), (
            f"`{entry.variable}` 의 스윕 기준선이 {entry.npv_low:,.0f}원인데 "
            f"본문 결론은 {conclusion:,.0f}원이다 — 스윕이 계절 몫 없이 돌고 있다"
        )
        assert entry.npv_high == pytest.approx(conclusion, abs=1.0)


def test_a_scenario_whose_season_shares_do_not_sum_to_one_is_refused() -> None:
    """★★ 시나리오가 적은 계절 몫도 **같은 자리에서** 판정된다 (`NFR-303`).

    거부 문면이 층마다 생기지 않게 `resolve_appliance_season_shares` 하나가
    진다 — 위 `test_a_scenario_that_asks_for_a_negative_load_is_refused` 와
    같은 규약이다.
    """
    short = {name: share * 0.9 for name, share in _season_heavy().items()}
    with pytest.raises(ValidationError, match="1 이어야 합니다"):
        _report(**{HEATPUMP_LOAD_FIELD: 3000.0, APPLIANCE_SEASON_SHARE_FIELD: short})
