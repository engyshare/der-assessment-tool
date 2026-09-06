"""검증 보고서에 **빠져 있던 다섯 자리**가 실제로 실렸는가 (R64/WP-TXT).

## 이 파일이 붙드는 것

사용자 요구 여섯(`docs/decisions-2026-09-06-R64.md` §0) 중 검증 보고서
379줄이 **말하지 않던** 다섯이다. 착수 실측: 「히트펌프」·「전기차」·
「적정」·「역산」·「미반영」이 **0건**이었고 계절은 낱말 하나뿐이었다.

    요구 1 가구 수      요구 2 히트펌프·전기차·「AI 가전」
    요구 3·6 계절별 운전  요구 4 적정 용량 역산      미반영 항목

★★★ **「문자열이 비어 있지 않다」로 재지 않는다.** 항목마다 따로 잰다 —
한 낱말이라도 빠지면 그 줄만 빨간불이 되어야 *무엇이* 사라졌는지 알 수 있다.

## ⚠ CLI 를 지나서 잰다

`scripts/dump_verification.py` 를 통과해 **파일로 뽑은** 문면을 본다.
렌더러 함수만 직접 부르면 CLI 배선이 끊겨도 초록불이다 —
`tests/report/test_verification.py` 머리말이 같은 자리에서 같은 판정을 적었고,
`status.md` 의 함정 「검사가 배포 코드가 부르지 않는 함수를 직접 불러
통과한다」가 그 형태다.

⚠ **`@pytest.mark.req(...)` 를 달지 않았다.** spec 을 훑어 이 산출물(검증
보고서)에 대응하는 수용기준을 찾지 못했다 — `tests/report/test_verification.py`
가 같은 사유로 마커를 달지 않은 전례를 그대로 따른다. 맞지 않는 조항을 달면
`docs/traceability.md` 에 거짓 인용이 실린다.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

from app.services.verify_steps import STAGE_COUNT, split_stages
from core.casegrid.appliance_load import (
    APPLIANCE_LOAD_UNSPECIFIED,
    APPLIANCE_SEASON_SHARE_FIELD,
    APPLIANCE_SEASON_SHARE_UNSPECIFIED,
    EV_LOAD_FIELD,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_FIELD,
    HEATPUMP_LOAD_TITLE,
)
from core.casegrid.household_scale import (
    HOUSEHOLD_COUNT_FIELD,
    HOUSEHOLD_COUNT_UNSPECIFIED,
)
from core.casegrid.profiles import load_daily_shapes
from core.report.case_report import CaseReport, build_case_report
from core.report.verification import render_verification_markdown
from core.report.verification_inputs import _NO_OPERATING_MODE, dispatch_note_rows

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 시험용 기기 부하. 참고자료의 값을 박지 않는 사유는
#: `tests/casegrid/test_appliance_load.py::_HEATPUMP` 가 갖는다.
_HEATPUMP = 900.0
_EV = 600.0
#: 시험용 가구 수 — **2 호다.** 3 호부터는 낮에도 부하가 발전을 넘어
#: 태양광 잉여가 사라지고, 그러면 이 골든 구성의 ESS(충전원 = 태양광 잉여)가
#: `ValidationError` 로 거부한다(실측 2026-09-06: 3·4·5·8 호 모두 거부).
#: ⚠ 그 거부는 **결함이 아니라 옳은 판정**이므로 여기서 큰 수를 우겨 넣지
#: 않는다 — 이 검사가 재는 것은 「가구 수가 산출물에 실리는가」 하나다.
_HOUSEHOLDS = 2


def _cli():
    """`scripts/` 는 패키지가 아니므로 경로로 불러온다.

    `tests/ci/test_ci_gates.py::_script` 와 같은 통로다 — 거기 머리말이
    `sys.modules` 에 먼저 등록해야 하는 사유를 갖는다.
    """
    import importlib.util

    name = "_wp_txt_dump_verification"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, _REPO_ROOT / "scripts" / "dump_verification.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _scenario_file(workspace: Path, **fields_given: object) -> Path:
    """골든 시나리오 + 준 필드 → **임시** 시나리오 파일.

    ⚠ **골든 픽스처를 고치지 않는다** — 읽기만 하고 쓰는 곳은 임시 디렉터리
    안이다(`tests/report/test_appliance_load_wired.py::_report` 와 같은 모양).
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    fields.update(fields_given)
    path = workspace / _GOLDEN.name
    path.write_text(
        yaml.safe_dump(fields, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _dumped(tmp_path: Path, **fields_given: object) -> str:
    """CLI 를 지나 **파일로 뽑은** 검증 보고서 문면."""
    with tempfile.TemporaryDirectory() as workspace:
        scenario = _scenario_file(Path(workspace), **fields_given)
        target = tmp_path / "verification.md"
        rc = _cli().main(
            [
                "--scenario", str(scenario),
                "--assumptions", str(_ASSUMPTIONS),
                "--out", str(target),
            ]
        )
        assert rc == 0, f"CLI 가 rc={rc} 로 끝났다"
        assert target.is_file(), "CLI 가 rc=0 을 냈는데 파일이 없다"
        return target.read_text(encoding="utf-8")


def _report(**fields_given: object) -> CaseReport:
    with tempfile.TemporaryDirectory() as workspace:
        return build_case_report(
            _scenario_file(Path(workspace), **fields_given),
            assumptions_path=_ASSUMPTIONS,
        )


def _season_names() -> list[str]:
    """자산이 선언한 계절 이름 — **개수를 4로 박지 않는다**(자산 머리말 ★)."""
    return [season.name for season in load_daily_shapes().load.seasons]


def _season_heavy() -> dict[str, float]:
    """마지막 계절에 몰아 준 몫 — 합이 1 이다."""
    names = _season_names()
    rest = (1.0 - 0.7) / (len(names) - 1)
    return {name: (0.7 if name == names[-1] else rest) for name in names}


# ── ① 내용 — 빠졌던 다섯이 «항목마다» 실렸는가 ──────────────────────────────


def test_the_household_count_is_printed_as_a_number_when_given(tmp_path: Path) -> None:
    """요구 1 — 몇 호로 돌았는지 **수로** 읽힌다."""
    text = _dumped(tmp_path, **{HOUSEHOLD_COUNT_FIELD: _HOUSEHOLDS})
    assert f"{_HOUSEHOLDS:,}호" in text, "가구 수가 검증 보고서에 없다"
    assert HOUSEHOLD_COUNT_UNSPECIFIED not in text, (
        "가구 수를 적었는데 「미지정」이 함께 실렸다"
    )


def test_the_two_appliance_loads_each_have_their_own_name(tmp_path: Path) -> None:
    """요구 2 — 히트펌프와 전기차가 **각자 이름과 값**을 갖는다.

    뭉뚱그린 칸 하나면 검토자가 어느 기기가 얼마인지 알 수 없다.
    """
    text = _dumped(
        tmp_path, **{HEATPUMP_LOAD_FIELD: _HEATPUMP, EV_LOAD_FIELD: _EV}
    )
    assert HEATPUMP_LOAD_TITLE in text, "히트펌프 칸이 없다"
    assert EV_LOAD_TITLE in text, "전기차 칸이 없다"
    assert f"{_HEATPUMP:,.0f}" in text
    assert f"{_EV:,.0f}" in text


def test_the_shiftable_share_is_printed(tmp_path: Path) -> None:
    """요구 2 「AI 가전」 — 옮길 수 있는 부하 비율이 실린다.

    ⚠ 값을 여기 박지 않는다 — 대장이 정하는 수이므로 리포트에서 읽어 맞댄다.
    """
    text = _dumped(tmp_path)
    assert "AI 가전" in text, "「AI 가전」축이 검증 보고서에 없다"
    assert f"{_report().dr_shiftable_share_pct:,.1f}" in text


def test_the_capacity_review_and_the_two_back_calculations_are_printed(
    tmp_path: Path,
) -> None:
    """요구 4 — 「적정 용량」과 **역산 둘**(자립 PV · 하루 결손 ESS)이 실린다."""
    text = _dumped(tmp_path)
    assert "적정 용량 검토" in text, "적정 용량 검토가 검증 보고서에 없다"
    assert "역산" in text, "역산이 검증 보고서에 없다"
    report = _report()
    for finding in report.capacity_review:
        assert finding.label in text, f"설계 변수 {finding.label} 이 빠졌다"
    for point in report.self_sufficiency.points:
        assert point.source_label in text, f"자립 역산의 {point.source_label} 이 빠졌다"


def test_the_unreflected_items_are_printed_with_their_direction(
    tmp_path: Path,
) -> None:
    """미반영 — 항목과 **방향**이 함께 실린다.

    방향 없이 이름만 실으면 검토자가 그것을 한 방향의 여유로 읽는다.
    """
    text = _dumped(tmp_path)
    assert "미반영 항목" in text, "미반영 절이 검증 보고서에 없다"
    from core.report.unreflected import build_unreflected

    items = build_unreflected(_report())
    assert items, "픽스처 전제가 깨졌다 — 미반영 항목이 하나도 없다"
    for item in items:
        assert item.label in text, f"미반영 항목 {item.label} 이 빠졌다"
        assert item.direction in text


# ── ② `None` 은 빈칸이 아니라 진술이다 ──────────────────────────────────────


def test_unspecified_inputs_print_a_sentence_not_a_blank(tmp_path: Path) -> None:
    """★★ 가구 수·기기 부하·계절 몫을 **안 적은** 실행 (판정 ③).

    빈칸으로 두면 검토자가 「반영됐다」로 읽고, 그 오독이 단지 총부하를 수십 배
    틀리게 만든다. 세 문면의 정본은 `core/casegrid/` 의 상수 셋이며 여기서
    베껴 적지 않고 들여와 대조한다.
    """
    text = _dumped(tmp_path)
    for sentence in (
        HOUSEHOLD_COUNT_UNSPECIFIED,
        APPLIANCE_LOAD_UNSPECIFIED,
        APPLIANCE_SEASON_SHARE_UNSPECIFIED,
    ):
        assert sentence in text, f"「미지정」 문장이 빠졌다: {sentence!r}"
    assert "| — |" not in text.split("### 미반영")[0].split("## 1단계")[1].split(
        "## 2단계"
    )[0].split("**ⓑ")[0], "1단계 실행 입력 표에 빈칸(`—`)이 있다"


def test_the_season_shares_are_printed_when_given(tmp_path: Path) -> None:
    """★ 계절 몫을 **적었으면** 계절마다의 몫이 실린다 (요구 3).

    ⚠ 「시나리오에서도 못 바꾼다」로 적으면 거짓이다 — 이 검사가 그 통로가
    실제로 산출물까지 오는 것을 붙든다.
    """
    text = _dumped(tmp_path, **{APPLIANCE_SEASON_SHARE_FIELD: _season_heavy()})
    assert APPLIANCE_SEASON_SHARE_UNSPECIFIED not in text, (
        "계절 몫을 적었는데 「미지정」이 실렸다"
    )
    for name, share in _season_heavy().items():
        assert f"{name} {share:.1%}" in text, f"계절 {name} 의 몫이 빠졌다"


# ── ③ 단계 수 — 웹을 깨뜨리지 않았다는 증거 ─────────────────────────────────


def test_the_report_still_splits_into_nine_stages(tmp_path: Path) -> None:
    """★★★ `split_stages` 가 **여전히 9단계**로 가른다 (판정 ①).

    화면(`app/services/verify_steps.py`)은 `STAGE_COUNT` 를 기대하고, 어긋나면
    `VerificationStageError` 로 멈춘다. 단계를 늘리면 웹 코드와 e2e 가 딸려
    오는데 사용자가 그것을 미뤘다 — 이 검사가 그 경계를 지킨다.
    """
    stages = split_stages(_dumped(tmp_path))
    assert len(stages) == STAGE_COUNT
    assert [stage.number for stage in stages] == list(range(1, STAGE_COUNT + 1))


def test_the_new_sections_do_not_add_stage_headings(tmp_path: Path) -> None:
    """보탠 절이 `## N단계 —` 머리글을 늘리지 않았다.

    ⚠ 미반영 절은 `###` 이며 9단계 본문의 끝으로 실린다 — 그것이 위 검사가
    통과하는 이유다. 여기서는 그 사실을 **자리로** 확인한다.
    """
    text = _dumped(tmp_path)
    assert text.count("## 9단계 — ") == 1
    ninth = split_stages(text)[-1]
    assert "### 미반영 항목" in ninth.body, (
        "미반영 절이 9단계 본문 안에 있지 않다 — 새 단계가 됐을 수 있다"
    )


# ── ④ 계절 — 넷이 «각각» 나오는가 ───────────────────────────────────────────


def test_every_season_appears_with_its_own_days_and_yearly_share(
    tmp_path: Path,
) -> None:
    """요구 3·6 — 계절이 **각각** 이름·일수·연간 기여로 실린다.

    ⚠ 계절 개수를 박지 않는다 — 자산이 선언한 만큼을 그대로 요구한다.
    """
    text = _dumped(tmp_path)
    seasons = _report().seasons
    assert seasons, "픽스처 전제가 깨졌다 — 계절이 서지 않았다"
    assert [s.name for s in seasons] == _season_names()
    for season in seasons:
        assert season.name in text, f"계절 {season.name} 이 빠졌다"
        assert f"{season.days}일" in text, f"계절 {season.name} 의 일수가 빠졌다"
    assert f"**{sum(s.days for s in seasons)}일**" in text, "계절 일수 합이 빠졌다"


def test_the_seasonal_table_does_not_replace_the_representative_day(
    tmp_path: Path,
) -> None:
    """★ 계절 표가 대표일 표를 **대신하지 않는다.**

    결론(프로포마)이 선 하루는 연간등가 하루이며, 그것이 보고서에서 사라지면
    검토자가 「무엇 위에 결론이 섰는가」를 잃는다.
    """
    body = split_stages(_dumped(tmp_path))[2].body
    assert "대표일" in body
    assert "계절별 운전" in body


# ── ⑤ 검증이 찾은 결함 셋 — 각각 «따로» 잰다 (R64/WP-FIX) ───────────────────


def test_the_discount_rate_is_in_stage_one_where_stage_eight_points(
    tmp_path: Path,
) -> None:
    """★★ 결함 1 — 8단계의 **「1단계 할인율」이 실제로 1단계에 있다.**

    종전에는 그 교차참조가 거짓이었다: 할인율은 대장 항목이 아니라 케이스
    수준표의 모형 파라미터라 1단계 대장 표에 행이 없었고, 검토자가 1단계에서
    찾으면 없었다. 「손계산으로 따라올 수 있게 한다」는 이 문서의 목적에
    정면으로 어긋나는 끊김이다.

    ⚠ 값을 여기 박지 않는다 — 리포트가 읽는 그 칸에서 가져와 맞댄다.
    """
    assert "discount" not in _ASSUMPTIONS.read_text(encoding="utf-8"), (
        "전제가 깨졌다 — 대장에 할인율 항목이 생겼다면 이 행의 「대장에 없다」가 "
        "거짓이 된다(`core/casegrid/ledger_levels.py` 머리말이 그날을 예고한다)"
    )
    stages = split_stages(_dumped(tmp_path))
    rate = f"{_report().basis.discount_rate:.1%}"
    first, eighth = stages[0].body, stages[7].body
    assert "할인율" in first, "1단계에 할인율 행이 없다 — 8단계의 참조가 거짓이 된다"
    assert rate in first, f"1단계 할인율 행에 값({rate})이 없다"
    assert f"1단계 할인율 {rate}" in eighth, (
        "8단계가 1단계 할인율을 가리키지 않는다 — 두 자리가 갈렸다"
    )


def test_the_resource_table_carries_the_allocation_not_only_the_label(
    tmp_path: Path,
) -> None:
    """★★★ 결함 2 — 3단계 운전방식 칸이 **본 실행의 배분**까지 싣는다 (요구 5).

    종전에는 `dispatch_notes` 의 짧은 선언 라벨(「전량 판매」)만 실렸고, 그래서
    *「ESS 가 가구 부하를 보고 방전한다」* 를 이 문서 어디에서도 가릴 수 없었다
    (`부하 추종` 0건). 3단계 「전량 판매」와 2단계 「자가소비율」의 병치도 그
    때문에 초독자에게 모순으로 읽혔다.
    """
    stage3 = split_stages(_dumped(tmp_path))[2].body
    resources = _report().basis.resources
    assert resources, "픽스처 전제가 깨졌다 — 자원이 하나도 없다"
    for line in resources:
        assert line.operating_mode in stage3, (
            f"자원 {line.name} 의 운전방식 긴 문면이 3단계에 없다 — "
            f"「{line.operating_mode}」"
        )
    assert any("배분: " in line.operating_mode for line in resources), (
        "픽스처 전제가 깨졌다 — 「본 실행 배분」을 적는 자원이 하나도 없다"
    )


def test_a_resource_only_in_the_notes_falls_back_instead_of_going_blank() -> None:
    """★ 결함 2 의 뒷면 — `basis.resources` 에 **없는** 자원의 칸.

    ⚠ 이름으로 맞추므로 두 목록의 길이가 다를 수 있다. 못 찾았을 때 빈칸을
    인쇄하면 「운전 방법을 안 적었다」로 읽히므로, 종전 값으로 떨어지고 그
    값마저 비면 **문장**을 적는다(이 모듈 ★★ 「빈칸이 아니라 진술」).
    """
    report = _report()
    named = {line.name for line in report.basis.resources}
    orphans = [n for n in report.dispatch_notes if n.resource_name not in named]
    assert orphans, "픽스처 전제가 깨졌다 — `dispatch_notes` 에만 있는 자원이 없다"
    rows = dispatch_note_rows(report)
    for note in orphans:
        row = next(r for r in rows if r.startswith(f"| {note.resource_name} |"))
        cell = row.split("|")[2].strip()
        assert cell, f"{note.resource_name} 의 운전방식 칸이 빈칸이다 — 「{row}」"
        assert cell == (str(note.operating_mode) or _NO_OPERATING_MODE), (
            f"{note.resource_name} 이 종전 값으로 떨어지지 않았다 — 「{cell}」"
        )


def test_the_item_count_says_what_those_items_are(tmp_path: Path) -> None:
    """★ 결함 3 — 「항목 N건」이 **그 N 이 무엇인지** 말한다.

    그 수는 대장 파일의 항목 수가 아니라 **provider 를 지나 값이 실린** 항목
    수다. 그렇게 적지 않으면 항목 수를 세는 검토자가 파일에서 다른 수를 얻는다.

    ⛔ 그렇다고 여기서 파일을 새로 세어 싣지 않는다 — 정본이 둘이 되고,
    그러면 provider 를 지나지 않은 수가 보고서에 실린다. 이 검사가 그 둘을
    **함께** 붙든다.
    """
    printed = len(_report().assumptions)
    ledger = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))["assumptions"]
    assert len(ledger) > printed, (
        "픽스처 전제가 깨졌다 — 값이 비어 있는 대장 항목이 하나도 없다"
    )
    text = _dumped(tmp_path)
    first = split_stages(text)[0].body
    assert f"항목 {printed}건" in first, f"1단계에 「항목 {printed}건」이 없다"
    assert "값을 읽어 온" in first, (
        "그 40이 무엇인지 말하지 않는다 — 검토자는 대장 파일의 항목 수로 읽는다"
    )
    assert f"항목 {len(ledger)}건" not in text, (
        "대장 파일을 새로 세어 그 수를 실었다 — 정본이 둘이 됐다"
    )


# ── ⑥ CLI — 인자를 주면 파일이 실제로 생긴다 ────────────────────────────────


def test_the_cli_help_explains_all_three_arguments() -> None:
    """`--help` 가 인자 셋을 설명한다 (판정 ⑤)."""
    text = _cli().build_parser().format_help()
    for flag in ("--scenario", "--assumptions", "--out"):
        assert flag in text, f"{flag} 가 --help 에 없다"
    assert "검증 보고서" in text


def test_the_cli_refuses_a_missing_scenario_with_a_sentence(
    tmp_path: Path, capsys
) -> None:
    """없는 경로는 **역추적이 아니라 한 줄**로 거부한다.

    역추적을 뱉으면 사람이 자기 오타인지 프로그램 결함인지 가릴 수 없다.
    """
    rc = _cli().main(
        [
            "--scenario", str(tmp_path / "없다.yaml"),
            "--out", str(tmp_path / "out.md"),
        ]
    )
    assert rc == 2
    assert "시나리오 파일이 없습니다" in capsys.readouterr().err
    assert not (tmp_path / "out.md").exists(), "거부했는데 파일을 만들었다"


def test_the_cli_writes_the_same_text_the_renderer_makes(tmp_path: Path) -> None:
    """★★ CLI 가 **서식을 짓지 않는다** (판정 ⑤).

    파일 안의 글자가 `render_verification_markdown()` 의 것과 한 자도 다르지
    않아야 한다 — 다르면 화면과 파일의 표기가 갈린다.
    """
    with tempfile.TemporaryDirectory() as workspace:
        scenario = _scenario_file(Path(workspace), **{HOUSEHOLD_COUNT_FIELD: _HOUSEHOLDS})
        target = tmp_path / "verification.md"
        assert (
            _cli().main(
                [
                    "--scenario", str(scenario),
                    "--assumptions", str(_ASSUMPTIONS),
                    "--out", str(target),
                ]
            )
            == 0
        )
        expected = render_verification_markdown(
            build_case_report(scenario, assumptions_path=_ASSUMPTIONS)
        )
    assert target.read_text(encoding="utf-8") == expected
