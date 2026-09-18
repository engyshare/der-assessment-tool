"""**개선 방안별 기대효과 도구가 재는 값인가** — R71/WP-7.

`scripts/improvement_effects.py` 는 사용자 판정 2026-09-18 이 요구한 둘
(*「현 상황에 대한 분석 결과」* 와 *「개선 방안을 적용할 때의 기대효과를 각각」*)을
한 산출물로 낸다. 이 파일이 보는 것은 그 산출물이 **표시가 아니라 실물인가**다.

    ★  방안 대장이 읽힌다        ← 여덟 건이 서고 필수 칸이 다 있는가
    ★★ 서식 위반이 거부된다      ← `source` 없음 · 모르는 lever·조건 · 빈 apply
    ★★ 기준을 «망가뜨리지 않는다» ← 오버레이 얹기 «전» 실행이 골든과 같은가
    ★  정렬이 Δ 내림차순이다     ← 음수가 맨 아래로 간다
    ★  §3 이 0건이어도 인쇄된다  ← 절을 지우면 「없다」와 「못 실었다」가 갈리지 않는다

## ⚠ 여덟 방안을 다 돌리지 않는다 — **느리다**

방안 하나가 6~20초다(실측: 여덟 + 참고 셋 + 기준이 81초). 그래서 **돌리는 시험은
`tmp_path` 에 지은 방안 한두 건짜리 작은 대장**을 쓰고, 여덟 건 전건은 **대장 파일이
서식에 맞는지만** 본다.

## ⚠ 기대값을 이 파일에 박지 않는다

기준 실행이 딴 사업을 그리지 않았는지는 **골든 픽스처가 이미 아는 사실**이다
(`fixtures/golden/scenario_unsubsidized.yaml` 의 `expected_values.npv_won`). 수를
여기 박으면 골든이 갱신되는 날 이 시험만 옛말을 한다 — `scripts/verify_ladder.py`
가 기준선을 파일로 잡은 것과 같은 판단이다.

⚠ `req()` 마커는 달지 않았다 — 이 도구는 리포트 절이 아니라 오케 판정 §5 ⑦ 이
*「먼저 도구로 답을 내고, 리포트 절로 승격할지는 사용자가 그 답을 본 뒤 정한다」* 로
spec 밖에 세운 자리다.
"""
from __future__ import annotations

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
    load_improvements,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 지시문이 세운 방안 여덟. **수만 세지 않고 이름을 맞댄다** — 수만 보면 하나가
#: 사라지고 다른 하나가 들어온 상태를 통과시킨다.
_EXPECTED_IDS = (
    "pv_allocation_battery_first",
    "surplus_sale_at_current_price",
    "surplus_sale_price_up",
    "rec_price_up",
    "cp_registration",
    "grid_tariff_down",
    "pv_capacity_up",
    "ess_capacity_down",
)

#: 작은 대장 한 건 — **돈이 안 드는 운전 변경**이라 값 근거가 없고 빠르다.
_TINY_ITEM: dict[str, Any] = {
    "id": "tiny_battery_first",
    "title": "PV 잉여 배분을 배터리 우선으로",
    "lever": "구성",
    "precondition": "ⓑ",
    "rationale": "역송을 열어 잉여판매·REC 가 0원을 벗어나는지 본다",
    "source": "core/der/pv.py 가 선언한 선택지 — 값이 없다",
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


def test_the_real_ledger_declares_eight_improvements_with_every_required_field() -> None:
    """실물 대장이 여덟 건을 세우고 필수 칸이 다 있는가 — **돌리지 않고** 본다."""
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


# ── ② 서식 위반이 거부된다 (3요소를 갖추는가) ───────────────────────────────


@pytest.mark.parametrize(
    ("broken", "expected_in_reason"),
    [
        ({"source": ""}, "source"),
        ({"lever": "운전"}, "lever"),
        ({"precondition": "ⓓ"}, "precondition"),
        ({"apply": {}}, "apply"),
        ({"apply": {"ess_power_kw": 10.0}}, "모르는 키"),
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


def _effect(name: str, delta: int) -> Effect:
    """수만 갖춘 결과 하나 — **인쇄를 재는 데 실행이 필요하지 않다.**"""
    item = Improvement(**{**_TINY_ITEM, "id": name})
    return Effect(
        improvement=item,
        npv_won=-404_000_000 + delta,
        delta_won=delta,
        annual_net_won=0,
        delta_annual_won=delta // 20,
    )


def _rendered(effects: list[Effect]) -> str:
    base = _run(_GOLDEN, {}, _ASSUMPTIONS)
    return render(base, effects, [], scenario_path=_GOLDEN, spent=0.0)


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
    assert "상호작용 미반영" in text
