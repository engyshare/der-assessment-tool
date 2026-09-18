"""**개선 방안별 기대효과 도구가 재는 값인가** — R71/WP-7.

`scripts/improvement_effects.py` 는 사용자 판정 2026-09-18 이 요구한 둘
(*「현 상황에 대한 분석 결과」* 와 *「개선 방안을 적용할 때의 기대효과를 각각」*)을
한 산출물로 낸다. 이 파일이 보는 것은 그 산출물이 **표시가 아니라 실물인가**다.

    ★  방안 대장이 읽힌다        ← 아홉 건이 서고 필수 칸이 다 있는가
    ★★ 서식 위반이 거부된다      ← `source` 없음 · 모르는 lever·조건 · 빈 apply
    ★★ 기준을 «망가뜨리지 않는다» ← 오버레이 얹기 «전» 실행이 골든과 같은가
    ★  정렬이 Δ 내림차순이다     ← 음수가 맨 아래로 간다
    ★  §3 이 0건이어도 인쇄된다  ← 절을 지우면 「없다」와 「못 실었다」가 갈리지 않는다

## R71/WP-10-fix 가 더한 넷 — **겹침**

    ★★  겹침이 «자리 이름»으로 탐지된다 — 같은 `design_capacity` 키를 쓰면 겹친다
    ★★★ A 가 겹친 것을 **안 더한다** — 가장 큰 것이 들고 품힌 것이 건너뛰어진다
    ★★  **A < B** · 건너뜀이 **사유와 함께** 산출물에 인쇄된다
    ★★★ **회귀** — 판정·합계를 고쳐도 방안의 Δ 는 하나도 안 변한다

## R71/WP-10 이 더한 다섯 — **근거 축**

    ★★★ `feasibility` 가 넷 밖이면 3요소 거부 · **없으면 거부**
    ★★  §4 합계가 `불가`·`미확인` 을 **뺀다**(CP 의 Δ 가 합에 없다)
    ★★  §2 정렬이 **두 묶음**이다 — `불가` 는 Δ 가 가장 커도 **뒤 묶음**에 선다
    ★★★ **회귀** — 기존 방안의 Δ 가 안 변했고 새 방안이 실측값을 낸다

## ⚠ 여덟 방안을 다 돌리지 않는다 — **느리다**

방안 하나가 6~20초다(실측: 여덟 + 참고 셋 + 기준이 81초). 그래서 **돌리는 시험은
`tmp_path` 에 지은 방안 한두 건짜리 작은 대장**을 쓰고, 여덟 건 전건은 **대장 파일이
서식에 맞는지만** 본다.

## ⚠ 기대값을 이 파일에 박지 않는다 — **예외는 회귀 하나뿐이다**

기준 실행이 딴 사업을 그리지 않았는지는 **골든 픽스처가 이미 아는 사실**이다
(`fixtures/golden/scenario_unsubsidized.yaml` 의 `expected_values.npv_won`). 수를
여기 박으면 골든이 갱신되는 날 이 시험만 옛말을 한다 — `scripts/verify_ladder.py`
가 기준선을 파일로 잡은 것과 같은 판단이다.

★ **예외** — 맨 아래 회귀 시험은 Δ 를 **일부러 박는다.** R71/WP-10 이 요구한 것이
*「기존 방안들의 Δ 가 하나도 안 변했다」* 와 *「새 방안이 실측값을 낸다」* 이고
(그 §4⑤ · §5 — *「어긋나면 멈추고 적어라 · 기대값을 고쳐 맞추지 마라」*), 그 물음은
**수를 박지 않으면 물을 수 없다.** 박은 수의 출처는 `.orch/R71/result_7.md` §2 와
`.orch/R71/out/combo2-2026-09-18.md` 이며, 골든이 갱신되면 **이 시험이 빨간불이 되는
것이 옳다** — 그때 고칠 것은 이 수가 아니라 「왜 움직였는가」다.

⚠ `req()` 마커는 달지 않았다 — 이 도구는 리포트 절이 아니라 오케 판정 §5 ⑦ 이
*「먼저 도구로 답을 내고, 리포트 절로 승격할지는 사용자가 그 답을 본 뒤 정한다」* 로
spec 밖에 세운 자리다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.contracts.validation import ValidationError
from scripts.improvement_effects import (
    _conclusion,
    _run,
    main,
    measure,
    render,
)
from scripts.improvement_ledger import (
    IMPROVEMENTS_PATH,
    NO_SOURCE_MARK,
    Effect,
    Improvement,
    choose_without_overlap,
    load_improvements,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 지시문이 세운 방안 아홉. **수만 세지 않고 이름을 맞댄다** — 수만 보면 하나가
#: 사라지고 다른 하나가 들어온 상태를 통과시킨다.
#: ⚠ 아홉 번째(`small_ess_max_pv_export`)는 R71/WP-10 이 세운 것이다.
_EXPECTED_IDS = (
    "pv_allocation_battery_first",
    "surplus_sale_at_current_price",
    "surplus_sale_price_up",
    "rec_price_up",
    "cp_registration",
    "grid_tariff_down",
    "pv_capacity_up",
    "ess_capacity_down",
    "small_ess_max_pv_export",
)

#: 조사(`.orch/R71/result_9.md`)가 판정하고 대장이 나르는 근거 축 — **`불가`·`미확인`
#: 은 §4 합계에서 빠지고 §2 의 뒤 묶음에 선다**(R71/WP-10 §2② · WP-10-fix §1③).
#: ⚠ `grid_tariff_down` 은 **`미확인`** 이다 — 「할 수 없다」가 확정된 것이 아니라
#: **선행 사실(이 사업의 실제 계약 형태)을 모른다**는 것이 오케 판정이다.
_EXPECTED_FEASIBILITY = {
    "pv_allocation_battery_first": "확인",
    "surplus_sale_at_current_price": "확인",
    "ess_capacity_down": "확인",
    "surplus_sale_price_up": "조건부",
    "rec_price_up": "조건부",
    "pv_capacity_up": "조건부",
    "small_ess_max_pv_export": "조건부",
    "grid_tariff_down": "미확인",
    "cp_registration": "불가",
}

#: 작은 대장 한 건 — **돈이 안 드는 운전 변경**이라 값 근거가 없고 빠르다.
_TINY_ITEM: dict[str, Any] = {
    "id": "tiny_battery_first",
    "title": "PV 잉여 배분을 배터리 우선으로",
    "lever": "구성",
    "precondition": "ⓑ",
    "rationale": "역송을 열어 잉여판매·REC 가 0원을 벗어나는지 본다",
    "source": "core/der/pv.py 가 선언한 선택지 — 값이 없다",
    "feasibility": "확인",
    "feasibility_source": "운전 파라미터 하나라 제도·계약이 필요 없다 — 원문 확인 불요",
    "apply": {"operation_options": {"pv_allocation_priority": "배터리 우선"}},
}


def _tiny_ledger(tmp_path: Path, items: list[dict[str, Any]], **extra: Any) -> Path:
    """작은 방안 대장 하나를 `tmp_path` 에 쓴다. **실물 대장을 고치지 않는다.**"""
    path = tmp_path / "improvements.yaml"
    payload: dict[str, Any] = {"improvements": items}
    payload.update(extra)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def _golden_npv() -> int:
    data = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    return int(data["expected_values"]["npv_won"])


# ── ① 방안 대장이 읽힌다 ────────────────────────────────────────────────────


def test_the_real_ledger_declares_nine_improvements_with_every_required_field() -> None:
    """실물 대장이 아홉 건을 세우고 필수 칸이 다 있는가 — **돌리지 않고** 본다."""
    improvements, references = load_improvements(IMPROVEMENTS_PATH)

    assert tuple(item.id for item in improvements) == _EXPECTED_IDS
    for item in improvements:
        assert item.title and item.rationale and item.source
        assert item.apply, f"{item.id} 의 apply 가 비었다"
    # 「방안이 아닌 것」은 **왜 아닌지**를 반드시 갖는다 — 그 칸이 §5 의 본문이다.
    assert references, "참고 목록이 비면 §5 가 크기를 말하지 못한다"
    for item in references:
        assert item.why_not, f"{item.id} 에 why_not 이 없다"


def test_the_cp_improvement_says_out_loud_that_its_price_has_no_basis() -> None:
    """CP 단가는 `track: default0` 이다 — 그 방안은 **근거 없음을 적어야** 한다.

    ★ 이 저장소는 *「없는 시장의 수익이 결론의 부호를 만든다」* 를 반복해 경계해
    왔다. 크기가 가장 큰 방안이 바로 그 자리이므로 표시가 살아 있는지 잰다.
    """
    improvements, _ = load_improvements(IMPROVEMENTS_PATH)
    cp = next(item for item in improvements if item.id == "cp_registration")

    assert NO_SOURCE_MARK in cp.source
    assert cp.unsourced


def test_every_improvement_carries_the_feasibility_verdict_the_survey_reached() -> None:
    """★ **근거 축**이 조사 판정 그대로 실려 있는가 — `source` 와 «다른 축»이다.

    조사(`.orch/R71/result_9.md` §1·§3)가 방안마다 *「이 사업이 그것을 실제로 할 수
    있나」* 를 따로 판정했다. 대장이 그것을 나르지 않으면 표는 **크기 순**만 갖게
    되고, 그러면 근거가 가장 얇은 `cp_registration` 이 맨 위에 선다.
    """
    improvements, _ = load_improvements(IMPROVEMENTS_PATH)

    assert {
        item.id: item.feasibility for item in improvements
    } == _EXPECTED_FEASIBILITY
    for item in improvements:
        assert item.feasibility_source, f"{item.id} 에 feasibility_source 가 없다"
    # ⛔ CP 는 **불가**다 — 산정 기준이 부재하다는 것이 대장의 1차 판단이고 조사가
    #    그것을 뒤집지 못했다. 그래서 §4 합계에서 빠진다(아래 ⑥).
    cp = next(item for item in improvements if item.id == "cp_registration")
    assert cp.feasibility == "불가"
    assert not cp.grounded
    # ⚠ 계약종별은 **선행 사실을 모른다** — `불가` 가 아니라 `미확인` 이고, 그 선행
    #   질문(`todo-개선방안조사.md` 1번 — 이 사업의 실제 계약 형태)이 사유에 있어야
    #   한다. 그것이 없으면 「모른다」가 「없다」로 굳는다.
    tariff = next(item for item in improvements if item.id == "grid_tariff_down")
    assert tariff.feasibility == "미확인"
    assert not tariff.grounded
    assert "todo-개선방안조사.md" in tariff.feasibility_source
    assert "계약 형태" in tariff.feasibility_source


# ── ② 서식 위반이 거부된다 (3요소를 갖추는가) ───────────────────────────────


@pytest.mark.parametrize(
    ("broken", "expected_in_reason"),
    [
        ({"source": ""}, "source"),
        ({"lever": "운전"}, "lever"),
        ({"precondition": "ⓓ"}, "precondition"),
        ({"apply": {}}, "apply"),
        ({"apply": {"ess_power_kw": 10.0}}, "모르는 키"),
        # ★★★ R71/WP-10 — 근거 축이 넷 밖이거나 사유가 비면 거부한다.
        ({"feasibility": "가능"}, "feasibility"),
        ({"feasibility": ""}, "feasibility"),
        ({"feasibility_source": ""}, "feasibility_source"),
    ],
)
def test_a_malformed_item_is_refused_with_all_three_elements(
    tmp_path: Path, broken: dict[str, Any], expected_in_reason: str
) -> None:
    """서식 위반은 **3요소 거부**로 멈춘다 — 조용히 넘어가지 않는다.

    ⚠ `ValidationError` 는 필드·사유·조치 셋을 **생성 시점에** 요구하므로
    (`core/contracts/validation.py`), 셋이 다 있는지는 그 생성자가 이미 붙든다.
    여기서 잰 것은 **무엇이 틀렸는지 사유가 말하는가**다 — 말하지 않으면 사용자가
    어느 칸을 고칠지 모른다.
    """
    item = {**_TINY_ITEM, **broken}
    path = _tiny_ledger(tmp_path, [item])

    with pytest.raises(ValidationError) as caught:
        load_improvements(path)

    assert expected_in_reason in caught.value.reason
    assert caught.value.action


def test_an_item_that_simply_omits_the_feasibility_field_is_refused(
    tmp_path: Path,
) -> None:
    """★★★ **칸을 «빠뜨린» 항목이 조용히 지나가지 않는다.**

    ⚠ 이것이 위 「넷 밖이면 거부」와 다른 물음이다. 값이 틀린 것은 눈에 띄지만
    **칸이 없는 것은 안 띈다** — 새 방안을 더하는 사람이 두 칸을 모르면 그 방안은
    근거 축 없이 표에 서고, 그 상태는 *「근거를 확인했다」* 와 구별되지 않는다.
    """
    naked = {
        key: value for key, value in _TINY_ITEM.items() if key != "feasibility"
    }
    path = _tiny_ledger(tmp_path, [naked])

    with pytest.raises(ValidationError) as caught:
        load_improvements(path)

    assert "feasibility" in caught.value.reason
    assert "비어 있습니다" in caught.value.reason
    assert caught.value.action


def test_the_same_id_twice_across_both_lists_is_refused(tmp_path: Path) -> None:
    """`id` 가 겹치면 §2 와 §5 가 같은 이름으로 다른 것을 말한다."""
    reference = {**_TINY_ITEM, "why_not": "참고 축이다"}
    path = _tiny_ledger(tmp_path, [_TINY_ITEM], not_improvements=[reference])

    with pytest.raises(ValidationError) as caught:
        load_improvements(path)

    assert _TINY_ITEM["id"] in caught.value.reason


def test_a_reference_item_without_why_not_is_refused(tmp_path: Path) -> None:
    """참고 축은 **왜 방안이 아닌가**가 없으면 §5 가 사유를 말하지 못한다."""
    path = _tiny_ledger(tmp_path, [], not_improvements=[dict(_TINY_ITEM)])

    with pytest.raises(ValidationError) as caught:
        load_improvements(path)

    assert "why_not" in caught.value.reason


# ── ③ 오버레이가 기준 실행을 망가뜨리지 않는다 ──────────────────────────────


def test_the_base_run_through_the_overlay_path_matches_the_golden_npv() -> None:
    """**빈 오버레이로 돈 기준 실행이 골든과 같은 `npv` 를 내는가.**

    ★★ 이것이 *「도구가 딴 사업을 그리지 않는다」* 의 증거다. 여기가 어긋나면 그
    위에서 잰 Δ 는 **전부 못 쓴다** — 그래서 도구도 이 어긋남을 만나면 Δ 를 내지
    않고 종료 코드 1 로 멈춘다.
    """
    base = _run(_GOLDEN, {}, _ASSUMPTIONS)

    assert _conclusion(base) == _golden_npv()


def test_a_measured_improvement_moves_the_axis_and_reports_both_deltas() -> None:
    """방안 하나를 얹으면 축이 움직이고 **연간 순수지 Δ 도 함께** 나온다.

    ⚠ Δ 의 **크기를 박지 않는다** — 값은 대장 판과 엔진이 정하고, 이 시험이 묻는
    것은 *「기준과 다른 실행이 실제로 돌았는가」* 다. 크기의 정본은
    `.orch/R71/result_7.md` 의 대조표이며 골든·사다리가 그 불변을 지킨다.
    """
    base = _run(_GOLDEN, {}, _ASSUMPTIONS)
    item = Improvement(**_TINY_ITEM)

    effect = measure(
        item, base=base, scenario_path=_GOLDEN, assumptions_path=_ASSUMPTIONS
    )

    assert effect.expressed
    assert effect.delta_won is not None and effect.delta_won > 0
    assert effect.npv_won == _conclusion(base) + effect.delta_won
    assert effect.delta_annual_won is not None


def test_a_refused_overlay_becomes_a_finding_not_a_crash() -> None:
    """거부는 **발견**이다 — 예외로 올려 실행을 끊지 않는다.

    `design_capacity.ess_power_kw` 는 실행이 명시로 거부하는 자리다(R71/WP-4 가
    `NFR-206` 을 사유로 막아 두었다). 그 방안은 §3 에 실려야 하며, 값을 바꿔
    통과시키는 것이 아니다.
    """
    base = _run(_GOLDEN, {}, _ASSUMPTIONS)
    item = Improvement(
        **{**_TINY_ITEM, "apply": {"design_capacity": {"ess_power_kw": 10.0}}}
    )

    effect = measure(
        item, base=base, scenario_path=_GOLDEN, assumptions_path=_ASSUMPTIONS
    )

    assert not effect.expressed
    assert effect.refusal is not None
    assert "ess_power_kw" in effect.refusal
    assert effect.delta_won is None


# ── ④ 정렬 · ⑤ §3 은 0건이어도 인쇄된다 ────────────────────────────────────


def _effect(name: str, delta: int, *, feasibility: str = "확인") -> Effect:
    """수만 갖춘 결과 하나 — **인쇄를 재는 데 실행이 필요하지 않다.**"""
    item = Improvement(**{**_TINY_ITEM, "id": name, "feasibility": feasibility})
    return _effect_of(item, delta)


def _effect_of(item: Improvement, delta: int) -> Effect:
    """**실물 대장의 항목**에 수만 얹은 결과 — 근거 축을 베끼지 않고 그대로 쓴다."""
    return Effect(
        improvement=item,
        npv_won=-404_000_000 + delta,
        delta_won=delta,
        annual_net_won=0,
        delta_annual_won=delta // 20,
    )


def _ledger_item(item_id: str) -> Improvement:
    improvements, _ = load_improvements(IMPROVEMENTS_PATH)
    return next(item for item in improvements if item.id == item_id)


@lru_cache(maxsize=1)
def _base() -> Any:
    """기준 실행 하나를 **이 모듈 안에서 한 번만** 돌린다 — 한 번이 6~20초다."""
    return _run(_GOLDEN, {}, _ASSUMPTIONS)


def _rendered(effects: list[Effect]) -> str:
    return render(_base(), effects, [], scenario_path=_GOLDEN, spent=0.0)


def test_the_table_is_ordered_by_delta_and_the_adverse_one_sinks_to_the_bottom() -> None:
    """정렬이 Δ 내림차순인가 — **음수가 맨 아래로 간다.**

    순서가 이 산출물의 내용 중 하나다. 흐트러지면 *「무엇부터 손댈 것인가」* 를
    고르는 사람이 작은 방안부터 읽는다.
    """
    text = _rendered([_effect("small", 1_000), _effect("bad", -9_000), _effect("big", 90_000)])

    positions = [text.index(f"`{name}` |") for name in ("big", "small", "bad")]
    assert positions == sorted(positions)
    assert "-9,000" in text


def test_section_three_is_printed_as_zero_cases_rather_than_deleted() -> None:
    """거부가 없어도 §3 을 **지우지 않는다.**

    ⚠ 절을 지우면 *「표현할 수 없는 방안이 없다」* 와 *「그 절을 못 실었다」* 가
    산출물에서 구별되지 않는다. 「없음」으로 끝내지 않고 **0건**이라고 적는다.
    """
    text = _rendered([_effect("only", 1_000)])

    assert "## §3 표현할 수 없는 방안" in text
    assert "**0건.**" in text


def test_every_section_and_the_manifest_row_are_present(tmp_path: Path) -> None:
    """다섯 절과 **머리말의 대장 판**이 다 인쇄되는가 — 도구를 `main()` 으로 돌린다.

    ★ 머리말이 대장 판·매니페스트를 적는 것은 오케 판정 ③의 대가를 막는 장치다
    (*「같은 대장 판에서 나왔는가를 아무도 안 지킨다」*). 리포트 «밖»의 도구이므로
    그 물음에 **산출물이 스스로** 답해야 한다.
    """
    ledger = _tiny_ledger(tmp_path, [_TINY_ITEM])
    out = tmp_path / "낸 것.md"

    code = main(
        [
            "--improvements",
            str(ledger),
            "--assumptions",
            str(_ASSUMPTIONS),
            "--out",
            str(out),
        ]
    )

    assert code == 0
    text = out.read_text(encoding="utf-8")
    for heading in ("## §1 ", "## §2 ", "## §3 ", "## §4 ", "## §5 "):
        assert heading in text
    assert "기준 실행 매니페스트" in text
    assert "어긋남 = 0원" in text
    # ⚠ §4 는 **한계를 함께** 적는다 — R71/WP-10-fix 가 그 문면을 「상호작용 미반영」
    #    에서 「A 조차 함께 적용한 결과가 아니다」로 옮겼다(합계 규칙이 바뀌었으므로).
    assert "A 는 상한도 하한도 아니다" in text


# ── ⑥ 근거 축이 표와 합계를 «가른다» (R71/WP-10) ────────────────────────────


def test_the_total_excludes_the_deltas_of_what_cannot_be_done_yet() -> None:
    """★★ **§4 합계가 `불가`·`미확인` 을 뺀다** — 그리고 **수를 함께** 적는다.

    예전 이 절은 `cp_registration`(조사 판정 `불가`)의 Δ 를 포함해 합을 냈다. 그러면
    *「제도가 마련되지 않는 한 0」* 인 크기가 합 안에 섞여 **그 합이 낙관적**이 된다.
    ⚠ 그렇다고 그 수를 지우지 않는다 — A(쓸 수 있는 합) 와 C(거기까지 더한 합)를
    함께 적어 **근거 없는 몫이 얼마인지**를 말한다.

    ⚠ 문면은 R71/WP-10-fix 가 **네 수(A·B·C·D)**로 옮겼다. 여기 둘은 자리가 겹치지
    않으므로 **A = B** 이고, 이 시험이 묻는 것은 *「CP 의 Δ 가 A 에 없는가」* 다.
    """
    cp = _ledger_item("cp_registration")
    down = _ledger_item("ess_capacity_down")
    assert cp.feasibility == "불가" and down.feasibility == "확인"
    assert not cp.overlapping_slots(down)

    text = _rendered([_effect_of(cp, 107_586_392), _effect_of(down, 31_290_236)])

    assert "| ★ **A — 겹치지 않게 고른 1건의 합** | **31,290,236원** |" in text
    assert "| B — 근거가 선 **전부**(1건)의 단순 합 | 31,290,236원 |" in text
    assert "| C — `불가`·`미확인` 까지(2건) 더한 합 | 138,876,628원 |" in text
    # 크기를 숨기지 않았다 — CP 의 Δ 는 §2 에 그대로 인쇄된다.
    assert "**107,586,392**" in text


def test_the_impossible_improvement_stands_in_the_second_group_even_when_largest() -> None:
    """★★ **정렬이 두 묶음이다** — Δ 가 가장 커도 `불가` 는 **뒤 묶음**에 선다.

    이 저장소가 밟은 것이 바로 그것이다: Δ 내림차순 하나로 세우니 1위가 `불가` 인
    `cp_registration` 이었고, 그러면 표가 *「할 수 있는 것」* 이 아니라 *「크면
    좋겠는 것」* 을 위에 둔다(오케 판정 `.orch/R71/WP-10.md` §0).
    """
    cp = _ledger_item("cp_registration")
    down = _ledger_item("ess_capacity_down")

    # CP 의 Δ 를 **더 크게** 준다 — 크기 순이면 맨 위에 서야 하는 배치다.
    text = _rendered([_effect_of(cp, 107_586_392), _effect_of(down, 31_290_236)])

    grounded = text.index("### ★ 근거가 선 방안")
    ungrounded = text.index("### ⛔ 지금은 못 하는 방안")
    assert grounded < text.index("`ess_capacity_down` |") < ungrounded
    assert ungrounded < text.index("`cp_registration` |")
    assert "§4 합계에서 빼었다" in text


@pytest.mark.parametrize(
    ("item_id", "expected_delta"),
    [
        ("ess_capacity_down", 31_290_236),
        ("pv_capacity_up", 60_583_606),
        # ⚠ 이 방안은 R71/WP-10-fix 가 판정을 `조건부` → `미확인` 으로 내린 자리다.
        #    판정을 바꿨어도 **Δ 는 그대로여야 한다** — 판정은 합계와 묶음만 가른다.
        ("grid_tariff_down", 38_845_195),
        ("small_ess_max_pv_export", 205_168_638),
    ],
)
def test_the_measured_delta_of_each_improvement_has_not_moved(
    item_id: str, expected_delta: int
) -> None:
    """★★★ **회귀** — 기존 방안의 Δ 가 안 변했고 새 방안이 실측값을 낸다.

    출처 — 앞의 둘은 `.orch/R71/result_7.md` §2 의 대조표, 마지막은 오케스트레이터
    실측 `.orch/R71/out/combo2-2026-09-18.md`(같은 오버레이를 `pv9_ess2` 라는 이름으로
    돌린 결과)다. ⚠ **박은 수를 고쳐 맞추지 말 것** — 어긋나면 그것은 *「내 변경이
    계산을 건드렸다」* 는 신호이며, R71/WP-10 §5 가 **멈추고 적으라**고 정했다.

    ⚠ 아홉 건을 다 돌리지 않는다(하나가 6~20초다). 네 건은 **근거 축·합계 규칙을
    고친 변경이 계산에 닿지 않았다**를 보이기에 족한 표본이다 — 대장 오버레이 네 자리
    (`design_capacity` 둘 · `assumption_overrides` 하나 · 그 둘과 `operation_options`
    의 조합)를 함께 덮는다. **아홉 건 전건의 회귀는 도구 실행이 보인다**
    (`.orch/R71/result_10-fix.md` §3).
    """
    effect = measure(
        _ledger_item(item_id),
        base=_base(),
        scenario_path=_GOLDEN,
        assumptions_path=_ASSUMPTIONS,
    )

    assert effect.expressed, effect.refusal
    assert effect.delta_won == expected_delta


# ── ⑦ 겹침 — **같은 자리를 쓰는 방안을 합계가 여러 번 세지 않는다** (WP-10-fix) ──

#: 방안 아홉의 Δ 실측 — 출처는 `.orch/R71/result_7.md` §2(여덟)와 오케스트레이터
#: 실측 `.orch/R71/out/combo2-2026-09-18.md`(`small_ess_max_pv_export`)다.
#:
#: ⚠ **여기 박은 수는 「인쇄와 합계」를 재는 재료일 뿐이다** — 이 수가 실물인지는 위
#: 회귀 시험이 **실제로 돌려** 붙든다. 아홉 건을 다 돌리면 시험 하나가 80초를 넘으므로
#: 합계 규칙은 «실행 없이» 재고, 실행은 표본 넷으로 가른다.
_MEASURED_DELTA = {
    "pv_allocation_battery_first": 322_053,
    "surplus_sale_at_current_price": 322_053,
    "surplus_sale_price_up": 14_551_499,
    "rec_price_up": 14_546_752,
    "cp_registration": 107_586_392,
    "grid_tariff_down": 38_845_195,
    "pv_capacity_up": 60_583_606,
    "ess_capacity_down": 31_290_236,
    "small_ess_max_pv_export": 205_168_638,
}


def _ledger_effects() -> list[Effect]:
    """실물 대장 아홉 건에 실측 Δ 를 얹은 결과 — **돌리지 않는다.**"""
    improvements, _ = load_improvements(IMPROVEMENTS_PATH)
    return [_effect_of(item, _MEASURED_DELTA[item.id]) for item in improvements]


def test_two_improvements_that_write_the_same_slot_are_detected_as_overlapping() -> None:
    """★ **겹침이 탐지된다** — 같은 자리를 쓰는 둘을 자리 이름째로 짚는다.

    `small_ess_max_pv_export` 는 설계 용량 둘과 배분 하나를 함께 쓴다. 그래서 그것은
    `pv_capacity_up`·`ess_capacity_down`·`pv_allocation_battery_first` 를 **이미 품고
    있다** — 그 Δ 들을 함께 더하면 같은 개선을 두 번·세 번 세는 일이다.
    """
    combo = _ledger_item("small_ess_max_pv_export")
    pv_only = _ledger_item("pv_capacity_up")
    ess_only = _ledger_item("ess_capacity_down")

    assert combo.overlapping_slots(pv_only) == ("design_capacity.pv_capacity_kw",)
    assert combo.overlapping_slots(ess_only) == ("design_capacity.ess_capacity_kwh",)
    assert combo.overlapping_slots(_ledger_item("pv_allocation_battery_first")) == (
        "operation_options.pv_allocation_priority",
    )
    # ⚠ 자리가 다른 둘은 겹치지 않는다 — 규칙이 「무엇이든 겹친다」가 아님을 본다.
    assert not pv_only.overlapping_slots(ess_only)
    assert not _ledger_item("cp_registration").overlapping_slots(pv_only)


def test_the_greedy_pick_takes_the_largest_and_skips_what_it_already_contains() -> None:
    """★ **A 가 겹친 것을 안 더한다** — 가장 큰 것이 들고 품힌 것들이 건너뛰어진다."""
    gains = [effect for effect in _ledger_effects() if effect.improvement.grounded]
    picked, skipped = choose_without_overlap(gains)

    assert tuple(effect.improvement.id for effect in picked) == (
        "small_ess_max_pv_export",
    )
    assert {skip.effect.improvement.id for skip in skipped} == {
        "pv_capacity_up",
        "ess_capacity_down",
        "pv_allocation_battery_first",
        "surplus_sale_at_current_price",
        "surplus_sale_price_up",
        "rec_price_up",
    }
    # 건너뜀은 **무엇과 어느 자리에서** 겹쳤는지를 나른다 — 사유 없는 건너뜀은 없다.
    for skip in skipped:
        assert skip.against.id == "small_ess_max_pv_export"
        assert skip.slots and all(skip.slots)
        assert "겹침" in skip.reason


def test_the_total_prints_four_numbers_and_every_skip_with_its_reason() -> None:
    """★ **A < B** · 건너뜀 사유가 **산출물에 인쇄된다** · D 가 남는 결손을 적는다.

    ⛔ 검수가 잡은 결함이 이 자리다 — 예전 §4 는 B 를 A 라고 적어 *「결손의 9.5%만
    남는다」* 로 읽혔다. 실제로 그 구성 하나를 적용하면 **49.2%가 남는다.**
    """
    effects = _ledger_effects()
    grounded_total = sum(
        _MEASURED_DELTA[effect.improvement.id]
        for effect in effects
        if effect.improvement.grounded
    )

    text = _rendered(effects)

    # A — 겹치지 않게 고른 한 건. **B 보다 작다.**
    assert grounded_total > 205_168_638
    assert "| ★ **A — 겹치지 않게 고른 1건의 합** | **205,168,638원** |" in text
    assert f"| B — 근거가 선 **전부**(7건)의 단순 합 | {grounded_total:,}원 |" in text
    assert "| C — `불가`·`미확인` 까지(9건) 더한 합 | 473,216,424원 |" in text
    # D — A 를 적용했을 때 남는 결손. ★ 이것이 사람이 읽을 수 있는 수다.
    assert "| ★ **D — A 를 적용했을 때 남는 결손** | **-198,873,218원** |" in text
    assert "| D 가 원래 결손의 | **49.2%** |" in text
    # 쓰지 말라는 한 줄과, 건너뜀 여섯이 **사유와 함께** 인쇄된다.
    assert "B 는 같은 개선을 여러 번 세므로 사업 판단에 쓰지 마라" in text
    assert "- ★ **고름** `small_ess_max_pv_export` — Δ 205,168,638원" in text
    assert (
        "- **건너뜀** `pv_capacity_up` — Δ 60,583,606원 · "
        "`small_ess_max_pv_export` 와 `design_capacity.pv_capacity_kw` 에서 겹침"
    ) in text
    for skipped_id in ("ess_capacity_down", "pv_allocation_battery_first"):
        assert f"- **건너뜀** `{skipped_id}` —" in text
