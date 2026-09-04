"""갈래를 **고를 수 있는가** — 시나리오 yaml 의 `baseline_arrangement` 배선 (FR-705-AC2 · DV-15).

## 이 파일이 붙드는 것 — 함수가 아니라 **배선**이다

R58 이 `FR-705-AC2`·`DV-15`·`core/cba/baseline.py` 로 갈래 셋을 **선언**했다.
그런데 실행 경로(`build_case_report` → `run_single_case_e2e`)가 그 선언을 **한
번도 읽지 않았다** — 착수 시점에 `BaselineArrangement`·`get_baseline_branch` 를
읽는 배포 코드는 `core/cba/baseline.py` **자기 자신뿐**이었다(실측 6곳이 전부
그 파일이다). 그래서 산출된 무보조 `npv` 는 「갈래 미지정」의 수였다
(`docs/decisions-2026-09-04-R59b.md` §1).

    필드가 없으면 ⓑ 로 돈다                   ← 기본값이 기획 의도와 같다(§1 ②)
    ★ ⓐ 를 고르면 `npv` 가 ⓑ 와 다르다        ← 이 축이 장식이 아니다
    ⓒ 는 실행 경로가 거부한다                 ← DV-15 가 실행 경로에 있다
    리포트가 고른 갈래의 선언 다섯을 인쇄한다  ← 어느 기준선인지가 먼저 드러난다

★★ **둘째가 요점이다.** 셋을 「고를 수 있게」만 해 놓고 계산이 갈래를 보지
않으면 나머지 셋은 전부 초록불이다 — 이 저장소가 **다섯 번** 밟은 「선언은
있고 읽는 배포 코드가 0곳」이며(`scripts/check_unread_extension_points.py`
머리말이 그 다섯을 든다) 그 상태는 아무 예외도 내지 않는다.

## 왜 `tests/report/` 인가 — **선택 통로가 시나리오 yaml 이다**

선택은 `core/report/case_report.py::_load_scenario` 가 읽는 yaml 필드 하나로
들어온다. 그러므로 *「필드가 없으면」*·*「필드에 무엇을 적으면」* 을 재려면
`build_case_report` 를 지나야 하고, 이 폴더가 이미 그 형태의 배선 시험을
갖는다(`test_irradiance_wired.py` · `test_case_report.py` — *「부품을 부르지
않는다. 진입점 하나를 지나서 나온 것만 본다」*). `tests/casegrid/` 는 러너를
직접 부르는 자리이며 yaml 을 모른다 — 아래 ⓒ 거부만 **러너에서도 함께** 본다:
거부가 리포트 층에만 있으면 러너를 직접 부르는 경로가 뚫린다.

## 갈래 이름 대응 — 사용자 문면 ↔ `BaselineArrangement`

    ⓐ 자가용 없음          NONE      자가소비 처리 `NONE`(자가소비가 없다)
    ⓑ 「가」 자가용 유지    MAINTAIN  자가소비 처리 `CANCEL_OUT`(양쪽에 있어 소거)
    ⓒ 「나」 집합자원화     POOL      자가소비 처리 `FORFEIT`(포기 — 음의 항)

⚠ **기대 문면을 손으로 베끼지 않는다** — `BASELINE_DECLARATIONS` 에서 읽는다.
베끼면 이 파일이 선언표의 사본을 하나 갖게 되고, 선언이 바뀔 때 여기가
따라오지 않아도 아무 일이 없다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.cba.baseline import (
    BASELINE_DECLARATIONS,
    BaselineArrangement,
    SelfConsumptionTreatment,
)
from core.contracts.validation import ValidationError
from core.report.case_report import CaseReport, build_case_report
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 필드를 **아예 두지 않은** 시나리오를 가리키는 열쇠. `None` 을 쓰는 이유는
#: 「빈 문자열을 적었다」와 「적지 않았다」가 다른 진술이기 때문이다.
_ABSENT = None


def _scenario_file(folder: Path, arrangement: str | None) -> Path:
    """갈래만 다른 시나리오 파일 하나.

    ⚠ 골든 픽스처를 고쳐 쓰지 않는다 — 기본값이 ⓑ 이므로 골든에 필드를 넣을
    필요가 없고, 넣으면 골든 재생성 압력이 생긴다. **필드 부재 = ⓑ** 가 이
    배선의 계약이다.
    """
    data: dict[str, object] = {
        "scenario": "baseline-arrangement-probe",
        "subsidy_rate": 0.0,
    }
    if arrangement is not None:
        data["baseline_arrangement"] = arrangement
    path = folder / f"scenario-{arrangement or 'absent'}.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


@pytest.fixture(scope="module")
def reports(tmp_path_factory: pytest.TempPathFactory) -> dict[str | None, CaseReport]:
    """갈래 셋(부재 · ⓑ · ⓐ)의 리포트. **모듈에 한 번만** 조립한다.

    진입점을 지나는 조립이 한 건에 1초를 넘으므로 검사마다 다시 돌리지 않는다.
    ⓒ 는 여기 없다 — 거부되는 갈래라 리포트가 나오지 않는 것이 정상이며, 그
    거부 자체를 아래 검사가 따로 본다.
    """
    folder = tmp_path_factory.mktemp("baseline-arrangement")
    keys: tuple[str | None, ...] = (
        _ABSENT,
        BaselineArrangement.MAINTAIN.value,
        BaselineArrangement.NONE.value,
    )
    return {
        key: build_case_report(
            _scenario_file(folder, key), assumptions_path=_ASSUMPTIONS
        )
        for key in keys
    }


def _pv_capacity_cell(report: CaseReport) -> str:
    """리포트 2.1 표 PV 줄의 「용량·성능」 칸 — 자가소비율 실측치가 여기 실린다."""
    return next(
        line.capacity for line in report.basis.resources if line.produces
    )


@pytest.mark.req("FR-705-AC2")
def test_a_scenario_without_the_field_runs_as_the_maintain_branch(
    reports: dict[str | None, CaseReport],
) -> None:
    """**T1** — 필드가 없으면 ⓑ(`MAINTAIN` · 「자가용 유지」)로 돈다.

    근거는 사용자 문면이다 — *「자가태양광과 히트펌프가 있는 가구를 대상으로
    프로그램이 기획되었음. 따라서 ⓑ에 가까움」*
    (`docs/decisions-2026-09-04-R59b.md` §1).

    ★ **오라클은 「부재 ≡ 명시한 ⓑ」다.** 「갈래 이름이 ⓑ 다」만 단언하면
    이름만 붙이고 계산은 갈래를 안 보는 구현도 통과한다 — 두 실행의 결론축이
    **원 단위로 같은 것**이 그 기본값이 실제로 계산에 들어갔다는 뜻이다.
    """
    absent = reports[_ABSENT]
    explicit = reports[BaselineArrangement.MAINTAIN.value]

    assert absent.baseline_arrangement is BaselineArrangement.MAINTAIN
    assert (
        absent.baseline_branch.self_consumption_treatment
        is SelfConsumptionTreatment.CANCEL_OUT
    )
    assert absent.metrics["npv"] == explicit.metrics["npv"], (
        "필드를 빼고 돌린 결론과 ⓑ 를 명시하고 돌린 결론이 다릅니다 — "
        "기본값이 계산에 들어가지 않았거나 두 곳에서 따로 정해집니다"
    )


@pytest.mark.req("FR-705-AC2")
def test_choosing_the_no_own_plant_branch_moves_the_conclusion(
    reports: dict[str | None, CaseReport],
) -> None:
    """**T2** ★★ — ⓐ 는 자가소비가 0 이 되고 그래서 `npv` 가 ⓑ 와 **다르다**.

    ⓐ 는 전기사용자에게 자가용 설비가 **없다** — 그 갈래의 자가소비 처리가
    `SelfConsumptionTreatment.NONE`(*「자가용이 없어 자가소비가 애초에
    없다」*)이고, 그러면 낮 전기가 가구로 먼저 가는 몫이 0 이다.

    ★ **두 단언을 함께 둔다.** 「`npv` 가 다르다」만 보면 **아무 수나 흔드는**
    구현도 통과하고, 「자가소비율이 0% 다」만 보면 리포트 문면만 고치고 계산은
    그대로인 구현이 통과한다. 갈래가 계산을 가른다는 증거는 **둘이 함께**
    성립할 때만 선다.
    """
    plain = reports[BaselineArrangement.MAINTAIN.value]
    none = reports[BaselineArrangement.NONE.value]

    assert none.baseline_arrangement is BaselineArrangement.NONE
    assert "자가소비율 0%" in _pv_capacity_cell(none), (
        f"ⓐ 인데 자가소비가 0 이 아닙니다: {_pv_capacity_cell(none)!r}"
    )
    assert "자가소비율 0%" not in _pv_capacity_cell(plain), (
        "ⓑ 의 자가소비가 0 입니다 — 두 갈래를 가르는 대조가 성립하지 않습니다"
    )
    assert none.metrics["npv"] != plain.metrics["npv"], (
        "ⓐ 와 ⓑ 의 순현재가치가 같습니다 — 갈래가 계산을 가르지 않고 "
        "선언만 실려 있습니다(읽는 배포 코드가 0곳인 형태)"
    )


@pytest.mark.req("FR-705-AC2")
def test_the_pool_branch_is_refused_on_the_execution_path(tmp_path: Path) -> None:
    """**T3** — ⓒ(「자가용 집합자원화」)를 고르면 실행 경로가 `DV-15` 로 거부한다.

    거부하는 것이 옳다 — *「계측이 갈리지 않으면 「나」는 **평가할 수
    없다**」*(`docs/decisions-2026-09-03-R57.md` §2)이고, 포기분(대칭 항)을
    비용으로 세는 자리가 저장소에 없다. **0 으로 채우면** 없는 제도 위에
    편익을 쌓는 형태가 된다(`get_baseline_branch` 독스트링).

    ★ **두 진입점에서 함께 본다.** 리포트 층에만 거부가 있으면 러너를 직접
    부르는 경로(케이스 그리드·성능 측정)가 뚫린 채로 남고, 그 구멍은 아무
    예외도 내지 않는다.
    """
    pool = BaselineArrangement.POOL.value
    provider = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))

    with pytest.raises(ValidationError) as from_report:
        build_case_report(
            _scenario_file(tmp_path, pool), assumptions_path=_ASSUMPTIONS
        )

    with pytest.raises(ValidationError) as from_runner:
        run_single_case_e2e(
            {},
            level_map=build_level_map(_ASSUMPTIONS),
            horizon_years=provider.analysis_years(),
            baseline_arrangement=pool,
        )

    for caught in (from_report, from_runner):
        parts = caught.value.as_dict()
        assert parts["rule"] == "DV-15", f"규칙 ID 가 다릅니다: {parts!r}"
        assert parts["field"] == "baseline.arrangement"
        assert "구분" in (parts["reason"] or ""), (
            f"구분 계측 전제가 사유에 없습니다: {parts['reason']!r}"
        )
        assert (parts["action"] or "").strip()


@pytest.mark.req("FR-705-AC2")
def test_the_report_prints_the_five_declarations_of_the_chosen_branch(
    reports: dict[str | None, CaseReport],
) -> None:
    """**T4** — 리포트가 고른 갈래의 **선언 다섯**을 인쇄한다.

    `FR-705-AC1` 이 *「기준선 자체 비용도 리포트에 명시적으로 표시」* 를
    요구하고, 갈래가 갈리면 **어느 기준선인지가 먼저** 드러나야 한다 —
    Without 이 무엇인지 모르면 증분의 타당성을 검토할 수 없다.

    ⚠⚠ **빈 값도 인쇄한다.** ⓐ 의 성립 조건은 `""` 이고 그것이 옳다(비교할
    상대 요금이 없다). 칸을 비우면 검토자가 *「조건이 없다」* 와 *「그 표시를
    싣지 못했다」* 를 가릴 수 없다 — 이 저장소가 붙임 1 의 오버라이드 표에서
    같은 판단을 했다(`CaseReport.overrides` 주석 · R57/WP-8).

    ★ **그 칸은 「비어 있지 않다」로만 본다 — 문면을 지정하지 않는다.** 「없음」
    이라 적을지 「해당 없음」이라 적을지는 표기 판단이고, 검사가 그것을 못 박으면
    문면을 다듬을 때마다 이 파일이 함께 움직여야 한다. 재는 것은 *빈 선언이
    사람이 읽는 문면으로 인쇄되는가* 하나다.
    """
    report = reports[BaselineArrangement.NONE.value]
    branch = BASELINE_DECLARATIONS[BaselineArrangement.NONE]
    rendered = render_markdown(report)

    assert branch.viability_condition == "", (
        "ⓐ 의 성립 조건이 비어 있지 않습니다 — 이 검사가 「빈 값도 인쇄한다」를 "
        "재지 못합니다(선언표가 바뀌었으면 이 검사를 함께 고칩니다)"
    )
    for label, cell in (
        ("기준선 갈래", BaselineArrangement.NONE.value),
        ("기준선(Without)", branch.without_description),
        ("변경 후(With)", branch.with_description),
        ("자가소비 처리", branch.self_consumption_treatment.value),
        ("갈래 근거 조항", branch.clause),
    ):
        assert f"| {label} | {cell} |" in rendered, (
            f"리포트에 「{label}」 줄이 없거나 값이 다릅니다 — 기대: {cell!r}"
        )

    condition = [
        line for line in rendered.splitlines() if line.startswith("| 갈래 성립 조건 |")
    ]
    assert len(condition) == 1, (
        f"「갈래 성립 조건」 줄이 {len(condition)}개입니다 — 빈 선언도 한 줄로 "
        "인쇄되어야 합니다"
    )
    assert condition[0].split("|")[2].strip(), (
        f"성립 조건 칸이 비어 있습니다: {condition[0]!r} — 빈 선언은 「없음」처럼 "
        "사람이 읽는 문면으로 적습니다"
    )
