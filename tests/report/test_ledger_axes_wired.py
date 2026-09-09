"""**「모든 수치는 변경 가능」을 축마다 실제로 잰다** — 대장 스윕 축 전건 (R68/WP-8).

검토서 §4.5(`docs/verification-report-improvement-2026-09-09.md`):

    「“모든 수치는 변경 가능”하다고 적는 것만으로는 부족하다. … 하나씩 바꿨을
      때 수요 단계부터 dispatch 와 경제성까지 움직이는지 **테스트해야 한다**」

## 재는 것 셋 — `tests/report/test_household_count_wired.py` 머리말 그대로

    ① 값을 바꾸면 **본 실행**의 수가 움직인다
    ② **스윕**(5절 민감도 · 6절 용량 검토)도 같은 값으로 돈다
    ③ 산출물이 **그 값으로 돌았음**을 인쇄한다

②가 이 저장소가 네 번 밟은 자리다(형상 R37 · 기준선 R60 · REC R52 · 가구수
R64) — 본문과 민감도가 서로 다른 값으로 돌아도 **둘 다 자기 기준에서는 매끈해
아무 검사도 안 걸린다.**

## ⚠ 왜 축을 손으로 세지 않고 `ledger_backed_variables()` 를 훑는가

형제 넷(`test_household_count_wired.py` · `test_appliance_load_wired.py` ·
`test_irradiance_wired.py` · `test_load_shift_wired.py`)은 **대장 스윕 축이
아닌** 통로를 하나씩 잰다 — 가구 수·기기 부하는 시나리오 필드가 이기고,
형상은 자산 파일에서 오며, 부하 이동 비율은 러너 안에서 갈래를 켠다. 그
넷은 축마다 재는 모양이 다르므로 파일이 따로 있는 것이 맞다.

**이 파일이 맡는 것은 나머지 전부** — `core/casegrid/ledger_levels.py::
_LEDGER_VARS` 가 세운 대장 스윕 축이며, 그 축들은 **재는 모양이 하나로
같다**: 시나리오의 `assumption_overrides` 로 그 키를 고치면 결론축이 움직여야
한다. 목록을 여기 손으로 옮겨 적으면 **축이 늘어난 날 이 검사가 조용히
낡는다** — R42 가 `capex.replacement_real_trend` 를 대장에 세우고도 스윕 축에
올리지 않아 5.1 표에 행이 안 나온 것이 그 형태였다(그 모듈의 같은 이름 옆
주석이 정본이다). 그래서 **목록의 정본을 읽는다.**

## ★★★ 이 검사가 **끊긴 축을 잇지 않는다** — 잰 뒤에 신고만 한다

실측(R68/WP-8)으로 대장 스윕 축 17 중 셋은 값을 고쳐도 결론축이 **0원** 움직인다:
`escalation.electricity_tariff` · `tariff.surplus_direct_sale` ·
`policy.grid_supply_allowance`. 그 셋은 **엔진 배선이 끊긴 것**이고, 여기서
이으면 결론축이 움직인다 — 이 라운드가 할 일이 아니다.

⇒ 그래서 이 파일이 세우는 규칙은 *「전부 움직여야 한다」* 가 아니라
**「움직이거나, 안 움직인다는 사실을 산출물이 신고하거나」** 다. 그 신고 자리가
「미반영 항목」 표(`core/report/unreflected.py::_unread_items`)이며, 축 하나가
새로 끊기면 그 표가 자동으로 그 행을 세우므로 이 검사는 **끊김을 못 잡는
것이 아니라 「말없이 끊기는 것」을 잡는다.**

## ⚠ 자기참조가 아니다 — 두 경로는 다른 코드다

「미반영」 판정(`InfluenceEntry.unread_by_pipeline`)은 **스윕**이 `low`·`high`
수준으로 돌려 낸 것이고, 이 검사가 흔드는 것은 **사용자 통로**(시나리오
`assumption_overrides` → `build_level_map(overrides=…)` → `base` 수준)다.
R63 의 브라우저 검수 D10 이 실물로 보인 것이 정확히 *그 둘이 갈릴 수 있다* 는
사실이다 — 스윕은 돌고 사용자가 고친 값만 안 먹었다
(`tests/casegrid/test_override_reaches_the_level_map.py` 머리말).

## ⚠ 흔드는 값을 **지어내지 않는다** — 대장의 `sensitivity.high` 를 쓴다

배수를 곱하면 값이 0인 축(`capex.replacement_real_trend` 의 `base` 는 **0.0**)
에서 아무것도 안 흔들리고, 그 축은 *「안 움직였다」* 로 **잘못** 신고된다.
대장이 항목마다 조사해 둔 띠의 위 끝(`sensitivity.high`)은 그 항목이 스스로
「여기까지는 그럴 수 있다」고 적은 값이므로 지어낸 수가 아니다.

## ⚠ `@pytest.mark.req(...)` 를 달지 않았다

형제 넷과 같은 사유다 — spec 에 「입력 변경이 전 단계에 전파되는가」를 요구하는
수용기준이 없다. 근거 없는 마커는 `docs/traceability.md` 에 거짓 인용을 싣는다.
"""
from __future__ import annotations

import tempfile
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.assumption.scenario_overrides import ASSUMPTION_OVERRIDES_FIELD
from core.casegrid.ledger_levels import LEVEL_NAMES, ledger_backed_variables
from core.report._format import _num
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import CaseReport, build_case_report
from core.report.unreflected import build_unreflected
from core.report.verification import render_verification_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 흔들 값을 고를 때 읽는 대장 칸. `LEVEL_NAMES` 의 마지막이 「위 끝」이다 —
#: 이름을 리터럴로 적으면 그 셋을 고치는 날 여기만 남는다.
_UPPER_LEVEL = LEVEL_NAMES[-1]

#: 결론축이 「움직였다」로 인정되는 최소 폭(원). 원 단위 반올림이 여러 층에서
#: 일어나므로 **한 원 차이를 움직임으로 읽지 않는다** — 형제 파일들이 쓰는
#: `abs=1.0` 과 같은 자리이며 부호는 보지 않는다(축마다 좋아지는 쪽이 다르다).
_MOVED_WON = 1.0

#: 이 라운드 착수 시점에 **끊겨 있던** 축. 값을 고쳐도 결론축이 0원 움직이고,
#: 「미반영 항목」 표가 그 사실을 셋 다 신고한다(R68/WP-8 실측).
#:
#: ⛔ **여기에 축을 더해 검사를 통과시키지 마라.** 이 목록이 길어지는 것은
#: 「배선이 하나 더 끊겼다」이며, 그것이 이 파일이 잡으려는 사건이다.
#: ⚠ 반대로 **줄어드는 것은 좋은 일**이다 — 그때 이 목록을 함께 줄인다.
DEAD_AXES: frozenset[str] = frozenset(
    {
        "escalation.electricity_tariff",
        "tariff.surplus_direct_sale",
        "policy.grid_supply_allowance",
    }
)


def _live_pairs() -> tuple[tuple[str, str], ...]:
    """끊기지 않은 축의 `(케이스 변수, 대장 키)` — 결론축이 움직여야 하는 것들.

    ⚠ 변수 이름을 함께 나르는 이유는 ③ 이 1단계 ⓒ 표의 **행 전체**를 대조하기
    때문이다. 키만으로 훑으면 같은 키를 싣는 다른 표(ⓑ)에 걸려도 통과한다.
    """
    return tuple(
        sorted(
            (variable, key)
            for variable, key in ledger_backed_variables().items()
            if key not in DEAD_AXES
        )
    )


def _ledger_item(key: str) -> dict[str, Any]:
    """대장 파일에서 그 항목 한 벌. ⚠ **읽기만 한다** — 고치지 않는다."""
    doc = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    for item in doc["assumptions"]:
        if item.get("key") == key:
            return dict(item)
    raise AssertionError(f"대장에 `{key}` 항목이 없다 — 스윕 축의 정본이 낡았다")


def _band_top(key: str) -> float:
    """그 항목이 스스로 적은 띠의 **위 끝**. 지어낸 수가 아니다."""
    band = _ledger_item(key).get("sensitivity") or {}
    top = band.get(_UPPER_LEVEL)
    assert isinstance(top, (int, float)) and not isinstance(top, bool), (
        f"`{key}` 의 `sensitivity.{_UPPER_LEVEL}` 이 수가 아니다({top!r}) — "
        "흔들 값을 대장에서 읽을 수 없다"
    )
    return float(top)


def _report(key: str | None = None) -> CaseReport:
    """골든 시나리오, 또는 **대장 키 하나만 띠의 위 끝으로 고친** 실행.

    ⚠ **골든 픽스처도 대장도 고치지 않는다.** 읽어서 사본을 짓고 그 사본은
    `tempfile.TemporaryDirectory()` 안에서만 산다 — `app/services/ui_run.py::
    run_ui_case` 가 배포 경로에서 지나는 통로(시나리오 필드 하나)와 같은
    모양이며, 그래야 이 검사가 **사용자가 실제로 쓰는 자리**를 잰다.
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    if key is not None:
        fields[ASSUMPTION_OVERRIDES_FIELD] = [
            {"key": key, "value": _band_top(key), "reason": "변경 전파를 재는 검사"}
        ]
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / _GOLDEN.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return build_case_report(path, assumptions_path=_ASSUMPTIONS)


@cache
def _cached(key: str | None) -> CaseReport:
    """축 하나당 실행 **한 번**. 한 벌이 5초쯤 걸리므로 ①②③ 이 나눠 쓴다."""
    return _report(key)


def _conclusion(report: CaseReport) -> float:
    return float(report.metrics[CONCLUSION_METRIC])


@pytest.mark.parametrize("key", sorted(ledger_backed_variables().values()))
def test_every_ledger_axis_either_moves_the_conclusion_or_is_declared_dead(
    key: str,
) -> None:
    """★★★ ① **축마다 하나씩 흔들어 결론축이 움직이는지 잰다** (검토서 §4.5).

    끊긴 축이면 움직이지 않는 것이 **현재의 사실**이고, 그때 요구하는 것은
    배선이 아니라 **신고**다 — 「미반영 항목」 표에 그 축의 행이 서 있어야
    한다. 빈칸으로 두면 검토자는 *「반영했는데 영향이 없었다」* 로 읽는다.
    """
    base = _conclusion(_cached(None))
    moved = abs(_conclusion(_cached(key)) - base)
    if key in DEAD_AXES:
        labels = " / ".join(item.label for item in build_unreflected(_cached(None)))
        assert moved < _MOVED_WON, (
            f"`{key}` 가 이제 결론축을 {moved:,.0f}원 움직인다 — 배선이 이어졌다. "
            "좋은 일이며, 이 파일의 `DEAD_AXES` 에서 그 축을 빼라"
        )
        assert f"`{key}`" in labels, (
            f"`{key}` 는 값을 고쳐도 결론축이 0원인데 「미반영 항목」 표가 그 사실을 "
            f"신고하지 않는다 — 신고 없는 0원은 「영향이 없다」로 읽힌다. 표: {labels}"
        )
        return
    assert moved >= _MOVED_WON, (
        f"`{key}` 를 대장 띠의 위 끝({_band_top(key):,.4g})으로 고쳤는데 결론축이 "
        f"{moved:,.0f}원 움직였다 — 사용자가 바꾼 값이 계산에 닿지 않는다. "
        "끊긴 것이 사실이면 잇지 말고 `DEAD_AXES` 에 올려 산출물이 신고하게 하라"
    )


@pytest.mark.parametrize("key", [key for _, key in _live_pairs()])
def test_the_sweep_runs_on_the_same_value_as_the_body(key: str) -> None:
    """★★★ ② **5·6절의 스윕도 고친 값으로 돈다** — 두 절이 다른 사업을 그리지 않는다.

    ## 어떻게 재는가 — 「읽지 않는 인자」가 스윕의 **기준선**을 드러낸다

    끊긴 축은 끝에서 끝까지 흔들어도 결론축이 0원 움직인다. 그러므로 그 축의
    `npv_low`·`npv_high` 는 **스윕의 기준선 그 자체**이며, 스윕이 본문과 다른
    값으로 돌면 그 수가 본문의 결론과 갈린다.
    `tests/report/test_household_count_wired.py::
    test_the_sweep_runs_on_the_same_site_size_as_the_body` 가 가구 수 축에서
    같은 방법을 쓰고, `test_irradiance_wired.py` 가 형상 축에서 쓴다.
    """
    report = _cached(key)
    conclusion = _conclusion(report)
    unread = [entry for entry in report.influences if entry.unread_by_pipeline]
    assert unread, (
        "파이프라인이 읽지 않는 인자가 0건이다 — 이 검사가 0회 순회로 통과한다"
    )
    for entry in unread:
        assert entry.npv_low == pytest.approx(conclusion, abs=_MOVED_WON), (
            f"`{key}` 를 고친 실행의 스윕 기준선이 {entry.npv_low:,.0f}원인데 "
            f"본문 결론은 {conclusion:,.0f}원이다 — 5·6절이 고치기 «전» 값으로 "
            f"돌고 있다(`{entry.variable}` 행에서 보인다)"
        )
        assert entry.npv_high == pytest.approx(conclusion, abs=_MOVED_WON)


@pytest.mark.parametrize(("variable", "key"), _live_pairs())
def test_the_report_prints_the_value_it_ran_on(variable: str, key: str) -> None:
    """★★ ③ **산출물이 「이 값으로 돌았다」를 인쇄한다** — 옛 값을 싣지 않는다.

    1단계 ⓒ 표(`| 변수 | 대장 키 | 사용값 | 단위 |`)가 *「파이프라인이 실제로
    읽어 결론에 반영한」* 축만 골라 싣는 자리다. 여기서 옛 값이 인쇄되면
    R63/D10 의 상태 — *「화면은 고친 값을 인쇄하고 수는 옛 값으로 돈다」* 의
    거울상 — 이 되고, 검토자는 결론이 어느 수 위에 섰는지 알 수 없다.

    ⚠ **표기를 여기서 다시 짓지 않는다** — `core/report/_format.py::_num` 이
    그 규약의 정본이고, 검사가 자기 서식을 지으면 규약이 바뀌는 날 둘이 갈린다.
    """
    row = f"| {variable} | `{key}` | {_num(_band_top(key))} |"
    text = render_verification_markdown(_cached(key))
    assert row in text, (
        f"1단계 ⓒ 표에 「{row}」 행이 없다 — `{key}` 를 고쳤는데 산출물이 "
        "그 값으로 돌았다고 말하지 않는다"
    )


def test_the_dead_axes_are_exactly_the_ones_the_unreflected_table_names() -> None:
    """★★★ **끊긴 축의 목록이 두 자리에서 같다** — 한쪽만 낡지 않게 한다.

    위 검사는 축을 하나씩 본다. 이 검사는 **집합**을 본다 — 축 하나가 새로
    끊기면 「미반영 항목」 표에 행이 늘고, 그때 이 파일의 `DEAD_AXES` 가
    따라오지 않으면 **아무도 그 끊김을 읽지 않는다.** 반대로 배선이 이어져
    행이 줄어도 여기서 걸린다.
    """
    declared = {entry.ledger_key for entry in _cached(None).unread_variables}
    assert declared == set(DEAD_AXES), (
        f"산출물이 신고하는 끊긴 축은 {sorted(declared)} 인데 이 파일은 "
        f"{sorted(DEAD_AXES)} 를 적고 있다 — 배선이 바뀌었으면 목록을 함께 고쳐라"
    )
