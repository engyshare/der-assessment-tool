"""배타 판정의 **물리량 축** — `FR-402-AC1` · `FR-402-AC2.A` / R56.

## 이 파일이 닫는 것

배타 판정이 **편익 태그 짝**만 보고 거부했다 — *같은 물리량인지 묻지 않았다.*
그런데 규칙표 자신은 *「**같은 1 kWh** 를 자가소비 절감과 잉여판매로 동시
계상할 수 없다」* 라고 적고, 조항 `FR-402-AC1` 은 *「지불 주체가 다르거나
**물리량이 다르면 정상 계상한다**」* 를 **명시로 요구**한다. `FR-402-AC2.A` 의
금지 범위도 *「**같은** 1 kWh」·「**같은 시각** ESS 방전」* 으로 좁혀져 있다.

**즉 구현이 자기 규칙보다 엄격했고, 그것은 조항 위반이었다.** 완화가 아니다 —
`AC1` 이 「정상 계상한다」로 명시한 갈래를 판정이 지우고 있었다.

거부 메시지 자신이 *「물리량이 실제로 다른지 확인하고, 다르다면 …」* 이라고
처방하는데 **「다르다」를 표현할 자리가 계약에 없었다** — 판정이
``active_tags = {type(s).tag for s in active}`` 로, **태그의 집합**으로
이뤄졌기 때문이다. `ValueStream.quantity_id` 가 그 자리다.

## 붙드는 것 여섯

    ① 둘 다 말하지 않았다  → 거부      종전 동작 보존 (회귀 방어)
    ② 한쪽만 말했다        → 거부      ★ **우회로가 없다**
    ③ 둘 다 말했고 같다    → 거부      조항 문면 그대로
    ④ 둘 다 말했고 다르다  → 통과      ★★ **이 축의 존재 증명**
    ⑤ 배포 경로는 축이 비어 있다        ★★★ 결론축이 움직이지 않았다
    ⑥ 유형 B~D 는 여전히 거부되지 않는다  축이 그것들을 건드리지 않았다

**②가 ④만큼 중요하다.** ④만 두면 「다르다고 말하면 통과한다」는 알 수 있지만,
**한쪽 표찰만으로 규칙 전체가 꺼지는** 구현도 함께 통과한다 — 그러면 배타
기계에 우회로가 난다.

**⑤는 「축을 세웠지만 아직 아무도 쓰지 않는다」를 기계로 못 박는다.** 어느
편익도 물량을 선언하지 않았으므로 배포 경로의 판정은 종전과 **같아야** 한다.
R56/WP-1 이 계절 자산을 비운 채 축만 세운 것과 같은 방식이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from core.casegrid import e2e_runner
from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.validation import ValidationError
from core.contracts.valuestream import Payer, ValueStream
from core.report.case_report import build_case_report
from core.valuestream.exclusion_table import assert_no_exclusions, collect_exclusions

REPO_ROOT = Path(__file__).resolve().parents[2]


def _stub(tag_name: str, *, quantity_id: str | None = None) -> ValueStream:
    """`tag` 와 물량 표찰만 다른 최소 편익.

    `collect_exclusions` 가 읽는 것은 `type(s).tag`(**클래스 속성**) · `s.enabled` ·
    `s.structure` · `s.quantity_id` 다. `tests/contract/
    test_exclusion_rules_contract.py` 의 `_stub` 과 같은 꼴이며, 물량 표찰을
    받는 것만 다르다 — 실물 편익을 쓰면 그 편익의 생성자 인자가 이 검사의
    관심사가 되고, 어느 편익이 어느 물량을 지는지는 **아직 아무도 정하지
    않았다**(⑤가 그것을 못 박는다).
    """

    class _Stub(ValueStream):
        tag: ClassVar[str] = tag_name
        payer: ClassVar[Payer] = Payer.OPERATOR
        #: 이 스텁은 0원을 돌려주므로 창과 무관하다 (R34 계약).
        scales_with_dispatch_window = False

        def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
            return to_won(0)

        def formula(self, dispatch: DispatchResult, *, year: int) -> str:
            return "검사용 스텁 0원"

    return _Stub(name=f"stub:{tag_name}", quantity_id=quantity_id)


#: 오라클은 `docs/exclusion-rules.yaml` **첫 행**이다 — 유형 `A`,
#: *「같은 1 kWh 를 자가소비 절감과 잉여판매로 동시 계상할 수 없다」*.
#: 규칙표가 정본이므로 여기서 유형·근거를 다시 적지 않는다.
_PAIR = ("SelfConsumption", "SurplusSale")


# ── ① 둘 다 말하지 않았다 → 거부 (종전 동작 보존) ────────────────────────

@pytest.mark.req("FR-402-AC2.A")
def test_neither_declares_a_quantity_so_the_pair_is_still_refused() -> None:
    """**기본값 `None` 은 엄격한 쪽이다** — 축을 세워도 지금 동작이 그대로다.

    이 단언이 없으면 물리량 축이 **기본적으로 거부를 푸는 방향**으로 잘못
    구현돼도 아무도 모른다. `None` 은 「없다」가 아니라 **「말하지 않았다」**
    이고, 말하지 않았으면 다르다는 것을 증명할 수 없으므로 걸린다.
    """
    streams = [_stub(_PAIR[0]), _stub(_PAIR[1])]

    assert collect_exclusions(streams), "감지 자체가 되지 않는다"
    with pytest.raises(ValidationError) as caught:
        assert_no_exclusions(streams)
    assert caught.value.rule == "DV-12"


# ── ② 한쪽만 말했다 → 거부 (★ 우회로가 없다) ─────────────────────────────

@pytest.mark.req("FR-402-AC2.A")
@pytest.mark.parametrize("declared_index", [0, 1])
def test_declaring_on_one_side_only_does_not_open_a_bypass(
    declared_index: int,
) -> None:
    """★ **한 스트림에 표찰을 다는 것만으로 규칙을 끌 수 없다.**

    통과시키면 배타 규칙 **전체**에 우회로가 난다 — 어느 쌍이든 한쪽에 물량
    이름 하나만 적으면 거부가 사라진다. 한쪽이 말하지 않았으면 두 물량이
    **다르다는 것을 증명할 수 없고**, 증명되지 않은 것을 통과로 읽는 것은
    Q4(*「확인 못 했으면 보수적으로 배타」*, 도메인 원칙 부록 A)의 반대다.

    **양쪽을 다 돌린다** — 한쪽만 검사하면 `benefit_a` 쪽만 보는 구현이
    통과한다.
    """
    labels: list[str | None] = [None, None]
    labels[declared_index] = "pv_kwh"
    streams = [_stub(_PAIR[i], quantity_id=labels[i]) for i in (0, 1)]

    assert collect_exclusions(streams), "한쪽 선언만으로 감지가 사라졌다"
    with pytest.raises(ValidationError):
        assert_no_exclusions(streams)


# ── ③ 둘 다 말했고 같다 → 거부 (조항 문면 그대로) ────────────────────────

@pytest.mark.req("FR-402-AC2.A")
def test_the_same_declared_quantity_is_still_refused() -> None:
    """**같은 1 kWh** 를 두 번 계상하는 것이 조항이 금지하는 바로 그것이다.

    물량을 선언했다는 사실 자체가 통과 사유가 아니다 — 통과 사유는 **다르다**
    는 것이다.
    """
    streams = [_stub(tag, quantity_id="pv_kwh") for tag in _PAIR]

    assert collect_exclusions(streams), "같은 물량인데 감지가 사라졌다"
    with pytest.raises(ValidationError):
        assert_no_exclusions(streams)


# ── ④ 둘 다 말했고 다르다 → 통과 (★★ 이 축의 존재 증명) ─────────────────

@pytest.mark.req("FR-402-AC1")
def test_two_different_declared_quantities_are_counted_normally() -> None:
    """★★ **`FR-402-AC1` 이 명시로 요구하는 갈래** — 물리량이 다르면 정상 계상.

    조항 문면: *「동시 발생 효과는 중복이 아니다 — 지불 주체가 다르거나
    물리량이 다르면 정상 계상한다. 중복은 **같은 화폐 흐름을 두 번 세는 것**
    으로 한정한다」*. 그리고 `FR-402-AC2.A` 의 금지 범위는 *「**같은** 1 kWh」*
    다 — 서로 다른 kWh 는 애초에 그 조항의 대상이 아니다.

    R55 까지 이 갈래가 **없었다.** 판정이 태그 짝만 보았으므로 물량이 다른
    조합까지 거부했고, 그것이 이 WP 가 고치는 조항 위반이다.

    ⚠ **거부되지 않는 데서 그치지 않고 목록에서도 빠져야 한다.**
    `collect_exclusions` 는 리포트가 「배타제외」로 **표시**하는 근거이기도
    하다 — 정상 계상되는 쌍을 배타제외로 인쇄하면 검토자가 계상되지 않은
    편익을 찾게 된다.
    """
    streams = [
        _stub("SelfConsumption", quantity_id="집에서 쓴 kWh"),
        _stub("SurplusSale", quantity_id="계통으로 내보낸 kWh"),
    ]

    assert collect_exclusions(streams) == [], (
        "물리량이 다른 쌍이 여전히 배타로 잡힌다 — FR-402-AC1 위반이다"
    )
    assert_no_exclusions(streams)  # 예외가 나면 안 된다


# ── ⑤ 배포 경로는 축이 비어 있다 (★★★ 결론축이 움직이지 않았다) ─────────

@pytest.mark.req("FR-402-AC1")
def test_no_deployed_benefit_declares_a_quantity_yet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★★ **축만 세웠다** — 배포 경로의 어느 편익도 물량을 말하지 않는다.

    그러므로 배포 경로의 배타 판정은 종전과 **같고**, 결론축(`npv_won`)은
    움직이지 않는다.

    ⚠ **`npv_won` 을 여기서 다시 단언하지 않는다.** 골든 회귀
    (`tests/golden/test_regression_scenarios.py`)가 세 시나리오의 `npv_won` 을
    `fixtures/golden/scenario_*.yaml` 과 **정확 일치**로 이미 붙들고 있다 —
    같은 단언을 두 번 두면 기준값의 출처가 둘이 되고, 어느 날 갈리면 어느
    쪽이 정본인지 말할 수 없다. 대신 **원인 쪽**을 단언한다: 축이 비어 있으면
    판정이 종전과 같고, 판정이 종전과 같으면 수도 종전과 같다.

    실행 경로가 배타 검사에 **실제로 넘기는 편익 목록**을 가로채 본다 —
    「소스에 `quantity_id` 라고 적힌 데가 없다」는 문자열 검사와 다르다.
    조립기는 `build_case_report()` 하나이고(골든 회귀가 쓰는 것과 같다),
    거부는 `e2e_runner` 안의 `assert_no_exclusions()` 가 건다.
    """
    seen: list[ValueStream] = []
    real = e2e_runner.assert_no_exclusions

    def _spy(streams: list[ValueStream], *args: object, **kwargs: object) -> None:
        seen.extend(streams)
        real(streams, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(e2e_runner, "assert_no_exclusions", _spy)

    build_case_report(
        REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml",
        assumptions_path=REPO_ROOT / "docs" / "assumptions.yaml",
    )

    # 가로채기가 실제로 걸렸는지 먼저 본다 — 빈 목록에 「전건 None」을 단언하면
    # 그 단언은 아무것도 붙들지 않는다(배선이 끊겨도 초록불이 된다).
    assert seen, "배타 검사가 실행 경로에서 불리지 않았다 — 단언이 무의미해진다"

    declared = sorted(
        {type(s).tag for s in seen if s.quantity_id is not None}
    )
    assert declared == [], (
        f"배포 편익이 물량을 선언하기 시작했다: {declared}. "
        "축이 비어 있다는 전제가 깨졌으므로 결론축이 움직였을 수 있다 — "
        "골든 회귀를 다시 재고 이 시험의 근거를 다시 쓰십시오"
    )


# ── ⑥ 유형 B~D 는 축이 건드리지 않는다 ──────────────────────────────────

@pytest.mark.req("FR-402-AC1")
def test_types_b_to_d_are_untouched_by_the_quantity_axis() -> None:
    """물리량 축은 **유형 A·E 에만** 걸린다.

    `B`(인과 하류) · `C`(동일 효과의 이중 화폐화) · `D`(제도적 배타)는 「같은
    물리량」이 판정 근거가 **아니다.** 물량으로 걸러 내면 판정 근거가 아닌
    것으로 규칙을 끄게 된다 — 유형 `B` 쌍은 «증분만 계상»해야 하는 관계이지
    「물량이 다르니 둘 다 온전히 세라」가 아니다.

    오라클: 규칙표의 `DistributedBenefit` ↔ `SelfConsumption`(유형 `B`).
    **물량을 서로 다르게 선언해도 감지 목록에 그대로 남는다** — 그리고
    `assert_no_exclusions` 는 종전과 같이 그것을 거부하지 않는다.
    """
    streams = [
        _stub("DistributedBenefit", quantity_id="회피된 망 증설 kW"),
        _stub("SelfConsumption", quantity_id="집에서 쓴 kWh"),
    ]

    found = collect_exclusions(streams)
    assert [(a, b) for a, b, _, _ in found] == [
        ("DistributedBenefit", "SelfConsumption")
    ], "물리량 축이 유형 B 를 껐다 — 증분 계상 관계가 리포트에서 사라진다"
    assert_no_exclusions(streams)  # B~D 는 거부 대상이 아니다 (종전 그대로)
