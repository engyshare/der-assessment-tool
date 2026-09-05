"""붙임이 **「고쳤는데 안 먹었다」를 인쇄한다** — 「거부도 통과도 아닌 표시」.

## 무엇을 재는가 (R63/N3)

`tax.vat_rate` 는 대장 안에 있으나 계산이 읽지 않는다. 오버라이드 통로가
열린 뒤 그 키는 관문을 통과하고 붙임 표에 `0.1 → 1000000000.0` 으로 인쇄되는데
결론축은 한 푼도 안 움직인다 — **화면은 고친 값을 인쇄하고 수는 옛 값으로
돈다.** 이 파일은 그 실행의 그 행에 **표시가 서는지**, 그리고 실제로 읽히는
키의 행에는 **표시가 안 붙는지**를 잰다(정상에 표를 달면 표가 배경이 된다).

## ⚠ 「읽었다」의 정본은 통로가 **둘**이다 — 실측이다

지시문은 `AssumptionSet.get()` 을 유일한 통로로 보았으나 **실물은 그렇지
않았다**. `capex.pv.rooftop` 은 결론축을 −11,552,270 → −11,252,832 로 옮기지만
계산 중에 `get()` 을 지나지 않는다 — 그 값은 `build_level_map()` 이 대장
YAML 에서 **직접** 읽어 수준표(`base`)에 앉히고 엔진이 그 표를 본다.
`get()` 만 세면 그 행에 「읽지 않았다」가 서고, 그것은 **인쇄된 거짓**이다.
그래서 조립부는 둘을 합집합으로 굳힌다 — `get()` 이력 ∪ 수준표가 declare 한
대장 키(`ledger_backed_variables()`). ⚠ 둘째를 **여기서 새로 적지 않는다** —
수준표에게 물어야 갈래가 늘 때 한쪽만 낡지 않는다.

⚠ **조항 마커를 달지 않았다** — 사유는 `tests/assumption/test_unread_override.py`
머리말과 같다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from core.casegrid.ledger_levels import ledger_backed_variables
from core.cba.baseline import POOL_METERING_FIELD, BaselineArrangement
from core.report.appendix_sections import UNREAD_OVERRIDE_MARK, appendix_section
from core.report.case_report import (
    COMPUTE_PHASE_READ_KEYS,
    CaseReport,
    build_case_report,
)

_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 대장 안에 있으나 아무도 읽지 않는 키 (`core/contracts/der.py` ⑦).
_UNREAD = "tax.vat_rate"
#: 실제로 결론축을 옮기는 키 — 아래 `test_...moves_the_conclusion` 이 잰다.
_READ = "capex.pv.rooftop"


def _report(tmp_path: Path, overrides: list[dict[str, Any]] | None) -> CaseReport:
    """골든 시나리오를 **배포 경로 그대로** 돌린다."""
    body = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8"))
    if overrides is not None:
        body["assumption_overrides"] = overrides
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    return build_case_report(path, assumptions_path=_ASSUMPTIONS)


def _row(report: CaseReport, key: str) -> Any:
    return next(row for row in report.overrides if row.key == key)


def _expected_npv(path: Path) -> float:
    """골든 하나가 선언한 `npv` — **여기 수를 적지 않는다.**

    정본은 픽스처이고 `tests/golden/test_regression_scenarios.py` 가 같은
    자리를 읽는다. 리터럴을 들면 정본이 둘이 되고 한쪽만 고쳐진다.
    """
    case = yaml.safe_load(path.read_text(encoding="utf-8"))
    return float(case["expected_values"]["npv_won"])


def _golden_npv() -> float:
    """★ 결론축 — 무보조 골든의 `npv`."""
    return _expected_npv(_GOLDEN)


# ── ① 안 읽히는 키에는 표시가 선다 ──────────────────────────────────────


def test_an_override_on_a_key_nobody_reads_is_marked(tmp_path: Path) -> None:
    """`tax.vat_rate` 를 고친 실행의 그 행이 **「읽지 않았다」**로 선다."""
    report = _report(
        tmp_path, [{"key": _UNREAD, "value": 1e9, "reason": "표시를 잰다"}]
    )

    row = _row(report, _UNREAD)

    assert row.override_value == 1e9, "관문이 값을 안 실었다"
    assert row.read_by_this_run is False, "안 읽히는 키가 「읽었다」로 섰다"


def test_the_run_is_unmoved_by_the_key_nobody_reads(tmp_path: Path) -> None:
    """표시의 **근거**를 함께 잰다 — 그 값을 1e9 로 해도 결론축이 안 움직인다.

    표시만 재고 이것을 안 재면, 그 키가 나중에 계산에 배선되는 날 표시가
    조용히 거짓이 되고 아무 검사도 걸리지 않는다.
    """
    plain = _report(tmp_path, None).metrics["npv"]

    moved = _report(
        tmp_path, [{"key": _UNREAD, "value": 1e9, "reason": "표시를 잰다"}]
    ).metrics["npv"]

    assert moved == plain, f"안 읽힌다던 키가 결론축을 옮겼다 — {plain} → {moved}"


# ── ② 읽히는 키에는 아무 표시도 안 붙는다 ───────────────────────────────


def test_an_override_on_a_key_the_run_reads_carries_no_mark(tmp_path: Path) -> None:
    """읽히는 키의 행에는 **아무 표시도 붙지 않는다** — 정상에 표를 달면
    표가 배경이 되고, 그러면 「안 먹었다」가 눈에 안 띈다."""
    report = _report(
        tmp_path, [{"key": _READ, "value": 1_500_000.0, "reason": "표시를 잰다"}]
    )

    assert _row(report, _READ).read_by_this_run is True, "읽히는 키에 표시가 붙었다"


def test_the_key_the_run_reads_moves_the_conclusion(tmp_path: Path) -> None:
    """★ 위 행이 「읽었다」인 **근거** — 그 키를 고치면 결론축이 실제로 옮긴다.

    ⚠ 이 검사가 없으면 「읽었다」를 그냥 참으로 두는 구현(전부 True)도 위
    검사를 통과한다.
    """
    plain = _report(tmp_path, None).metrics["npv"]

    moved = _report(
        tmp_path, [{"key": _READ, "value": 1_500_000.0, "reason": "표시를 잰다"}]
    ).metrics["npv"]

    assert moved != plain, "읽힌다던 키가 결론축을 안 옮겼다"


# ── ③ ★ 결론축 불변 ─────────────────────────────────────────────────────


def test_the_conclusion_axis_is_unmoved(tmp_path: Path) -> None:
    """오버라이드 없는 기본 실행의 무보조 `npv` 가 골든 그대로다.

    이 축은 **표시**를 붙일 뿐 값을 계산에 배선하지 않는다 — 결론축이 움직이면
    그것은 이 축의 산출이 아니라 **새 결함**이다.
    """
    assert _report(tmp_path, None).metrics["npv"] == _golden_npv()


# ── ④ 붙임 문면 — 사람이 읽는 자리에 실제로 선다 ────────────────────────


#: 아래 두 검사가 붙임에 심는 사유 — **변경 항목 표의 행을 고르는 표지**다.
#: ⚠ 키만으로 줄을 고르면 **주제별 표**의 행이 먼저 잡힌다(그 표에는 사유
#: 칸이 없다).
_REASON = "표시를 잰다"


def _override_line(lines: list[str], key: str) -> str:
    """붙임에서 **변경 항목 표**의 그 행 한 줄."""
    return next(
        li for li in lines if _REASON in li and li.startswith(f"| `{key}`")
    )


def test_the_appendix_prints_the_mark_where_a_reader_sees_it(tmp_path: Path) -> None:
    """자료형에만 서면 검토자는 못 본다 — **붙임 표에** 문면이 실린다."""
    report = _report(
        tmp_path, [{"key": _UNREAD, "value": 1e9, "reason": _REASON}]
    )

    line = _override_line(appendix_section(report), _UNREAD)

    assert UNREAD_OVERRIDE_MARK in line, line


def test_the_appendix_leaves_the_read_row_bare(tmp_path: Path) -> None:
    """읽힌 행에는 그 문면이 **없다.**"""
    report = _report(
        tmp_path, [{"key": _READ, "value": 1_500_000.0, "reason": _REASON}]
    )

    line = _override_line(appendix_section(report), _READ)

    assert UNREAD_OVERRIDE_MARK not in line, line


# ── ⑤ 굳히는 자리가 **순서에 기대지 않는다** (R63/N5 · 착수 55) ──────────
#
# 종전에는 **한쪽 방향만** 붙들렸다:
#
#   굳히는 줄이 **뒤로** 밀린다        모든 키가 「읽었다」로 서서 표시가 통째로
#                                      죽는다 → 위 ① 이 붙든다
#   리포트 쪽 읽기가 그 줄 **앞으로**  그 키가 「읽었다」로 서서 표시가
#                                      **조용히** 거짓이 된다 → 붙드는 것이 없었다
#
# 아래 검사가 그 칸을 닫는다. **소스가 declare 하고**(`COMPUTE_PHASE_READ_KEYS`)
# 여기서는 **재기만 한다** — 선언을 시험에 두면 「무엇이 정본인가」가 시험이 되고,
# 그러면 계산 쪽이 늘 때 시험을 고쳐 통과시키는 길이 열린다.

#: 굳힌 집합을 산출물에서 읽어 내려고 심는 사유. 값은 대장 값 **그대로**다.
_PROBE_REASON = "굳힌 집합을 산출물에서 읽어 낸다"

#: 골든 셋이 사는 곳 — 전건을 이름으로 나열하지 않고 **디렉터리에서 센다**.
#: 골든이 늘면 이 축도 함께 늘어야 하고, 목록을 여기 적으면 그때 낡는다.
_GOLDEN_DIR = _GOLDEN.parent


def _identity_overrides() -> list[dict[str, Any]]:
    """대장 **전 항목을 자기 값으로** 덮는 오버라이드 목록.

    ⚠⚠ **왜 전 항목인가.** 굳힌 집합은 `OverrideRow.read_by_this_run` 으로만
    산출물에 드러나고 그 행은 **오버라이드한 키에만** 선다. 몇 개만 골라 덮으면
    선언 **밖**의 키가 굳힌 집합에 들어와도 행이 없어 **안 보인다** — 그런데
    이 축이 찾으려는 것이 바로 그 키다.

    ⚠ 값을 그대로 두므로 계산은 통로가 열리기 전과 **같은 수**를 낸다
    (`test_the_probe_does_not_move_any_golden_conclusion` 이 그것을 잰다).
    관문을 통과시키려고 값을 흔들면 이 탐침 자체가 결론축을 옮긴다.

    ⚠ **거를 것을 여기서 나열하지 않고 형으로 거른다** — 관문
    (`core/assumption/scenario_overrides.py` 의 `_kind`)이 참·거짓과 비스칼라를
    거부하므로 같은 판정을 이름 목록으로 베끼면 대장이 늘 때 한쪽만 낡는다.
    """
    ledger = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8")) or {}
    return [
        {"key": item["key"], "value": item["value"], "reason": _PROBE_REASON}
        for item in ledger["assumptions"]
        if type(item["value"]) is not bool
        and isinstance(item["value"], (int, float, str))
    ]


def _preconditions() -> list[tuple[str, dict[str, Any]]]:
    """재는 전건 — **골든 전건 + 기준선 갈래 ⓐ·ⓒ** (판정 ⓒ).

    ⚠ 골든 픽스처에는 `baseline_arrangement` 가 없다(기본 ⓑ). 갈래마다 읽는
    키가 다르면 선언은 **합집합**이어야 하므로 갈래를 손으로 세워 함께 잰다 —
    골든만 재면 ⓐ·ⓒ 가 더하는 키를 이 축이 영영 못 본다.
    """
    cases: list[tuple[str, dict[str, Any]]] = [
        (path.stem, yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(_GOLDEN_DIR.glob("scenario_*.yaml"))
    ]
    cases.append((
        "branch_none",
        {
            "scenario": "n5-branch-none",
            "subsidy_rate": 0.0,
            "baseline_arrangement": BaselineArrangement.NONE.value,
        },
    ))
    cases.append((
        "branch_pool",
        {
            "scenario": "n5-branch-pool",
            "subsidy_rate": 0.0,
            "baseline_arrangement": BaselineArrangement.POOL.value,
            # ⓒ 는 계측 선언이 없으면 `DV-15` 로 거부된다 (R60/WP-3).
            POOL_METERING_FIELD: {
                "ownership_or_operation_transferred": True,
                "metering_separated": True,
            },
        },
    ))
    return cases


@pytest.fixture(scope="module")
def probed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, CaseReport]:
    """전건마다 **전 항목을 자기 값으로 덮은** 리포트. 조립은 한 번씩만 돈다."""
    folder = tmp_path_factory.mktemp("n5-freeze")
    rows = _identity_overrides()
    reports: dict[str, CaseReport] = {}
    for name, body in _preconditions():
        body["assumption_overrides"] = rows
        path = folder / f"{name}.yaml"
        path.write_text(
            yaml.safe_dump(body, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        reports[name] = build_case_report(path, assumptions_path=_ASSUMPTIONS)
    return reports


def _frozen_get_side(report: CaseReport) -> frozenset[str]:
    """굳힌 집합 중 **`get()` 이력 몫** — 수준표가 declare 한 몫은 뺀다.

    ⚠ **판정 ⓓ.** 둘째 통로(`ledger_backed_variables()`)는 수준표가 이미
    declare 한 것이고 굳히는 줄이 그것을 **물어서** 합집합한다. 그것까지 이
    선언에 베끼면 같은 사실이 두 곳에 살고 한쪽만 낡는다 — 이 라운드가 두 번
    밟은 함정이다. 여기서 세는 것은 `provider.keys_read()` 쪽뿐이다.
    """
    marked = frozenset(row.key for row in report.overrides if row.read_by_this_run)
    return marked - frozenset(ledger_backed_variables().values())


def test_the_frozen_history_stays_inside_what_the_compute_phase_declares(
    probed: dict[str, CaseReport],
) -> None:
    """★★★ **굳힌 집합 ⊆ 선언** — 전건 전부.

    리포트 쪽 읽기가 굳히는 줄 **앞으로** 오면 선언 밖의 키가 굳힌 집합에
    들어와 여기서 빨간불이 된다. ⚠⚠ **선언을 넓혀 통과시키지 마라** — 선언
    밖의 키가 들어왔다면 그것이 이 축이 찾으려던 것이다.
    """
    outside = {
        name: sorted(_frozen_get_side(report) - COMPUTE_PHASE_READ_KEYS)
        for name, report in probed.items()
    }

    assert not any(outside.values()), (
        "굳히는 줄이 **선언 밖의 키**를 들고 있다 — 리포트 쪽 읽기가 그 줄 "
        "앞으로 왔는지 보라. 계산 쪽에 정당한 새 읽기가 생긴 것이면 "
        f"COMPUTE_PHASE_READ_KEYS 를 함께 고쳐라: {outside}"
    )


def test_the_declaration_carries_no_key_the_compute_phase_never_reads(
    probed: dict[str, CaseReport],
) -> None:
    """★ 선언에 **죽은 이름**이 없다 — 넓혀서 통과시키는 길을 막는다.

    ⊆ 만 재면 선언을 대장 전체로 넓혀도 늘 초록불이고, 그러면 위 검사는
    아무것도 붙들지 않는다. 전건 합집합과 선언이 **같아야** 한다.
    """
    union: frozenset[str] = frozenset().union(
        *(_frozen_get_side(report) for report in probed.values())
    )

    assert COMPUTE_PHASE_READ_KEYS - union == frozenset(), (
        "선언에 어느 전건도 읽지 않는 키가 있다 — 넓혀서 통과시킨 것이 아닌지 "
        f"보라: {sorted(COMPUTE_PHASE_READ_KEYS - union)}"
    )


def test_the_probe_does_not_move_any_golden_conclusion(
    probed: dict[str, CaseReport],
) -> None:
    """★ **결론축 불변** — 전 항목을 자기 값으로 덮었으니 수가 그대로다.

    이 검사가 없으면 탐침이 값을 흔들어도 위 둘은 초록불이고, 그때 재고 있는
    것은 **이 저장소의 실행이 아니다.**
    """
    moved = {
        path.stem: (probed[path.stem].metrics["npv"], _expected_npv(path))
        for path in sorted(_GOLDEN_DIR.glob("scenario_*.yaml"))
        if probed[path.stem].metrics["npv"] != _expected_npv(path)
    }

    assert not moved, f"탐침이 결론축을 옮겼다 — {moved}"
