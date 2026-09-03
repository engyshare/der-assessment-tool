"""ESS 용량 **몫**을 「선언」이 아니라 「수」로 만드는 자리 — `core/casegrid/ess_share.py`.

## 이 파일이 붙드는 것

한 대의 `ESS` 를 몫으로 갈라 몫마다 다른 역할을 주려면 몫마다 인스턴스를
세워야 하는데, `power_kw` 와 `fixed_om_won_per_year` 는 **인스턴스마다 통째로
붙는다.** 용량만 갈라 두 대를 세우면 **정격출력이 2배 · 고정 운영비가 2배**가
되고, 그 늘어남은 **아무 예외도 내지 않는다** — 두 몫이 각각 자기(부풀려진)
정격출력 안에서 계획을 세우므로 `ESS._check_power()` 가 통과한다. 그것이 이
파일이 재는 첫째다.

    ① 몫으로 가르면 자원당 값의 **합이 원래 값과 같다**   ← 부풀지 않는다
    ② 단위당·비율 제원은 몫마다 **원래 값 그대로**다      ← 몫으로 나누면 틀린다
    ③ 거부 넷이 각각 `ValidationError` 를 낸다            ← ★ 우회로가 없다
    ④ 물량 표찰이 다르면 배타 판정이 통과하고 같으면 막힌다 ← ★★ 선행 ①과 이어진다
    ⑤ 배포 경로는 이 모듈을 import 하지 않는다            ← ★★★ 결론축 불변

**③ 의 넷째가 이 파일의 핵심이다.** 두 몫이 **같은 `quantity_id`** 를 달 수
있으면 배타 규칙이 몫을 구별하지 못한다 — R56 이 세운 물리량 축
(`tests/valuestream/test_exclusion_quantity_axis.py`)에 그대로 우회로가 난다.

**⑤ 는 「자리를 세웠지만 아직 아무도 쓰지 않는다」를 기계로 못 박는다.** 어느
케이스도 몫을 쓰지 않으므로 배포 경로의 수는 종전과 **같아야** 한다.

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 제원 합계의 오라클은 **입력한 물리 제원**
   (`_PHYSICAL`)이다. 배타 판정의 오라클은 `docs/exclusion-rules.yaml` 의
   유형 `E` 행(`NWAs` × `SelfConsumption`)이며 여기서 유형·근거를 다시 적지 않는다.
② **이 설명이 이 검사에 걸리는가** — ⑤ 만 소스 문면을 본다. 그것도 이 파일이
   아니라 `core/casegrid/e2e_runner.py` 를 본다.
③ **이름보다 넓게 주장하는가** — 아니다. 이 파일은 **몫을 세우는 함수**만
   재고, 몫마다 **어느 편익이 서는지**는 재지 않는다(아직 아무도 정하지 않았다).
④ **수와 그 조건의 짝** — 금액 오라클을 적지 않는다. 재는 것은 **합계 보존**과
   **원래 값 보존**이라는 두 항등식이다.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar

import pytest

from core.casegrid.ess_share import ESSShare, ESSSharePlan, split_ess
from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won, won_sum
from core.contracts.validation import ValidationError
from core.contracts.valuestream import Payer, ValueStream
from core.der.ess import ESSOperatingMode
from core.valuestream.exclusion_table import assert_no_exclusions, collect_exclusions

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 물리 배터리 한 대의 제원. **값은 반올림 자리를 만들지 않도록 골랐다** —
#: 이 파일이 재는 것은 금액의 크기가 아니라 **합계가 보존되는가**이므로,
#: 원 단위 반올림이 끼어들면 무엇 때문에 어긋났는지 구분할 수 없다.
_PHYSICAL: MappingProxyType[str, Any] = MappingProxyType({
    "name": "몫 검사용 ESS",
    "capacity_kwh": 100.0,
    "power_kw": 50.0,
    "rte_pct": 90.0,
    "capex_unit_won_per_kwh": 400_000.0,
    "capex_extra_won": 1_000_000.0,
    "fixed_om_won_per_year": 1_000_000.0,
})

#: 몫 둘의 **역할**과 **물량 표찰**. 저녁에 집에서 쓰는 kWh 와 계통으로
#: 내보내는 kWh 는 **서로 다른 물량**이며, 그래서 두 몫이 동시에 설 수 있다 —
#: 그것을 판정하는 것이 ④ 다.
_HOUSEHOLD_LABEL = "집에서 쓴 kWh"
_GRID_LABEL = "계통으로 내보낸 kWh"


def _shares(
    fractions: Sequence[float],
    *,
    labels: Sequence[str] | None = None,
) -> tuple[ESSShare, ...]:
    """비율만 주면 나머지가 성립하는 몫 목록을 만든다.

    표찰을 주지 않으면 **몫마다 다른** 표찰을 붙인다 — 기본값이 성립하는 쪽이어야
    「거부되는 입력을 실수로 오라클 삼는」 일이 없다.
    """
    marks = list(labels) if labels is not None else [f"물량-{i}" for i in range(len(fractions))]
    return tuple(
        ESSShare(
            name=f"몫{i}",
            fraction=fraction,
            operating_mode=ESSOperatingMode.SELF_CONSUMPTION,
            quantity_id=marks[i],
        )
        for i, fraction in enumerate(fractions)
    )


def _split(fractions: Sequence[float]) -> tuple[ESSSharePlan, ...]:
    return split_ess(_PHYSICAL, _shares(fractions))


# ── ① 자원당 값이 부풀지 않는다 ──────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.ESS")
def test_the_shares_add_back_up_to_the_physical_resource() -> None:
    """★ **몫을 다 더하면 물리 자원이다** — 정격출력도 고정 운영비도.

    이 단언이 없으면 몫 둘을 세운 구성이 **정격출력 2배 · 고정 운영비 2배**로
    돌아가고도 초록불이다(모듈 머리말). 「용량만 갈랐으니 나머지는 그대로 두면
    된다」가 정확히 그 잘못이며, 그것은 **더 낙관적인 쪽**으로 틀린다 — 없는
    출력으로 계획을 세우고 없는 비용은 두 번 든다.

    **비율이 나눠떨어지지 않는 경우도 함께 본다**(1/3 셋). 잔차를 마지막 몫이
    받는 규약(`ess_share.RESIDUAL_HOLDER_INDEX`)이 지켜지지 않으면 여기서
    합계가 어긋난다.

    ⚠ 이 항등식은 **제원 수준**의 것이다. 금액은 몫마다 `to_won()` 이 따로
    반올림하므로(`NFR-103`), 몫으로 나눈 값이 원 단위로 떨어지지 않으면 금액
    합계는 최대 「몫 수 − 1」원까지 어긋날 수 있다 — 그것은 이 함수가 아니라
    반올림의 몫이다. 그래서 위 `_PHYSICAL` 이 반올림 자리를 만들지 않는다.
    """
    for fractions in ((0.6, 0.4), (1 / 3, 1 / 3, 1 / 3)):
        plans = _split(fractions)

        assert math.fsum(p.resource.capacity_kwh for p in plans) == _PHYSICAL["capacity_kwh"]
        assert math.fsum(p.resource.power_kw for p in plans) == _PHYSICAL["power_kw"]

    two = _split((0.6, 0.4))
    fixed_om_total = won_sum(p.resource.fixed_om(year=1) for p in two)
    assert fixed_om_total == to_won(_PHYSICAL["fixed_om_won_per_year"])
    # 몫마다 **다른** 값이어야 한다 — 둘 다 원래 값이면 위 합계 검사는
    # 통과하지 못하지만, 둘 다 절반이 아닌 다른 방식으로 나뉘어도 통과할 수는
    # 있다. 「비율대로」까지 재는 것이 이 줄이다.
    assert [p.resource.power_kw for p in two] == [30.0, 20.0]


# ── ② 단위당·비율 제원은 그대로다 ────────────────────────────────────────

@pytest.mark.req("FR-102-AC1.ESS")
def test_per_unit_and_ratio_specs_are_handed_over_untouched() -> None:
    """**단위당·비율 값을 몫으로 나누면 틀린다.**

    `capex_unit_won_per_kwh` 를 몫 비율로 나누면 단가가 몫만큼 싸지고, 이미
    갈린 용량에 곱해지므로 취득원가가 **몫의 제곱**만큼 작아진다 — 사업비가
    조용히 줄어드는 형태다. `rte_pct` 를 나누면 왕복효율이 몫만큼 떨어진다.

    자본비는 **단가가 그대로이고 용량만 갈렸으므로** 합계가 보존된다 — 그
    보존이 「나누지 않았다」의 증거다.
    """
    plans = _split((0.6, 0.4))

    assert [p.resource.rte for p in plans] == [0.9, 0.9]

    capex_total = won_sum(p.resource.capex(year=1) for p in plans)
    physical_capex = (
        _PHYSICAL["capex_unit_won_per_kwh"] * _PHYSICAL["capacity_kwh"]
        + _PHYSICAL["capex_extra_won"]
    )
    assert capex_total == to_won(physical_capex)


# ── ③ 거부 넷 (★ 우회로가 없다) ──────────────────────────────────────────

#: 거부 넷과 **각각이 내야 할 필드 키·사유 조각**. 필드까지 보는 이유는,
#: 넷을 한 자리에서 같은 메시지로 뭉뜽그려 거부해도 「네 번 다 `ValidationError`
#: 가 났다」는 통과하기 때문이다 — 그러면 고치는 사람이 무엇이 틀렸는지 모른다.
_REFUSALS: tuple[tuple[str, tuple[ESSShare, ...], str, str], ...] = (
    ("몫이 없다", (), "ess_share.shares", "몫이 하나도 없습니다"),
    ("음수 비율", _shares((-0.2, 1.2)), "ess_share.fraction", "음수"),
    ("합이 1이 아니다", _shares((0.5, 0.4)), "ess_share.fraction", "합이 1이 아닙니다"),
    (
        "같은 물량 표찰",
        _shares((0.5, 0.5), labels=(_HOUSEHOLD_LABEL, _HOUSEHOLD_LABEL)),
        "ess_share.quantity_id",
        "같은 물량 표찰",
    ),
)


@pytest.mark.req("NFR-303")
@pytest.mark.parametrize(
    ("label", "shares", "field", "reason_fragment"),
    _REFUSALS,
    ids=[case[0] for case in _REFUSALS],
)
def test_each_broken_declaration_is_refused_with_its_own_cause(
    label: str,
    shares: tuple[ESSShare, ...],
    field: str,
    reason_fragment: str,
) -> None:
    """넷을 **각각** 거부한다 — 특히 **같은 물량 표찰**을.

    ★ 넷째가 배타 판정의 우회로다. 두 몫이 같은 `quantity_id` 를 달면
    `collect_exclusions` 가 두 몫을 구별할 수단을 잃는다(④ 가 그 앞뒤를 잰다).
    몫을 가르는 목적 자체가 **다른 물량을 다른 몫에 싣는 것**이므로, 표찰이
    같은 몫 둘은 애초에 몫 둘이 아니다.

    조치 문면이 비어 있지 않은지도 함께 본다 — `NFR-303` 은 **필드·사유·조치**
    셋을 요구하고, 셋째가 없으면 「무엇이 틀렸는지는 알지만 어떻게 고치는지는
    모르는」 메시지가 된다.
    """
    with pytest.raises(ValidationError) as caught:
        split_ess(_PHYSICAL, shares)

    assert caught.value.field == field, label
    assert reason_fragment in caught.value.reason, label
    assert caught.value.action.strip(), label


# ── ④ 물량 표찰과 배타 판정 (★★ 선행 ①과 이어진다) ──────────────────────

def _stub(tag_name: str, *, quantity_id: str | None) -> ValueStream:
    """`tag` 와 물량 표찰만 다른 최소 편익.

    `tests/valuestream/test_exclusion_quantity_axis.py::_stub` 과 같은 꼴이다 —
    `collect_exclusions` 가 읽는 것은 `type(s).tag`(**클래스 속성**) · `s.enabled` ·
    `s.structure` · `s.quantity_id` 뿐이다. 실물 편익을 쓰지 않는 이유는 **몫마다
    어느 편익이 서는지를 아직 아무도 정하지 않았기 때문**이며(다음 WP 의 몫이다),
    여기서 임의로 정하면 이 검사가 그 결정을 앞질러 고정한다.
    """

    class _Stub(ValueStream):
        tag: ClassVar[str] = tag_name
        payer: ClassVar[Payer] = Payer.OPERATOR
        #: 0원을 돌려주므로 디스패치 창과 무관하다 (R34 계약).
        scales_with_dispatch_window = False

        def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
            return to_won(0)

        def formula(self, dispatch: DispatchResult, *, year: int) -> str:
            return "검사용 스텁 0원"

    return _Stub(name=f"stub:{tag_name}", quantity_id=quantity_id)


#: 오라클은 `docs/exclusion-rules.yaml` 의 유형 `E` 행이다 — *「방전 시점을
#: 계통운영자가 정하면 … 자가소비가 성립하지 않는다」*(R48 판정 §2). 몫 둘이
#: 정확히 그 두 역할이므로, **표찰이 없으면 두 몫은 동시에 설 수 없다.**
_ROLE_TAGS = ("NWAs", "SelfConsumption")


@pytest.mark.req("FR-402-AC2.A")
def test_shares_with_different_quantities_pass_and_the_same_quantity_is_refused() -> None:
    """★★ **몫이 다른 물량을 지면 두 역할이 동시에 선다 — 같은 물량이면 못 선다.**

    이것이 선행 ①(물리량 축, R56)과 이 WP 가 만나는 자리다. 몫을 가르는 일이
    의미를 가지려면 **몫마다 다른 물량**이어야 하고, 그때 비로소 배타 규칙이
    두 역할을 정상 계상으로 읽는다(`FR-402-AC1` 의 *「물리량이 다르면 정상
    계상한다」*).

    뒤집으면, 같은 표찰을 단 두 몫은 **배타 판정에서 여전히 막힌다** — 그래서
    `split_ess` 가 그 선언을 **애초에 세우지 못하게** 거부하는 것이다(③ 넷째).
    두 문단을 한 함수에서 재는 이유는 **앞뒤가 붙어야 주장이 성립하기**
    때문이다: 통과만 재면 「무엇을 적어도 통과한다」와 구별되지 않는다.
    """
    plans = split_ess(
        _PHYSICAL,
        (
            ESSShare(
                name="저녁 자가소비",
                fraction=0.6,
                operating_mode=ESSOperatingMode.SELF_CONSUMPTION,
                quantity_id=_HOUSEHOLD_LABEL,
            ),
            ESSShare(
                name="계통 방전",
                fraction=0.4,
                operating_mode=ESSOperatingMode.GRID_DISCHARGE,
                quantity_id=_GRID_LABEL,
            ),
        ),
    )
    assert [p.share.quantity_id for p in plans] == [_HOUSEHOLD_LABEL, _GRID_LABEL]

    # 몫이 선언한 표찰을 그대로 편익에 싣는다 — 짝짓기가 `ESSSharePlan` 안에
    # 있으므로 순서로 다시 맞출 일이 없다.
    labelled = [
        _stub(_ROLE_TAGS[0], quantity_id=plans[1].share.quantity_id),
        _stub(_ROLE_TAGS[1], quantity_id=plans[0].share.quantity_id),
    ]
    assert not collect_exclusions(labelled), "물량이 다른데도 배타로 감지됐다"
    assert_no_exclusions(labelled)

    # 같은 표찰이면 종전대로 막힌다 — `split_ess` 가 이 선언을 못 세우게 하는
    # 이유가 이것이다(그 거부는 ③ 넷째가 잰다).
    same = [_stub(tag, quantity_id=_HOUSEHOLD_LABEL) for tag in _ROLE_TAGS]
    assert collect_exclusions(same), "같은 물량인데 감지되지 않았다"
    with pytest.raises(ValidationError):
        assert_no_exclusions(same)


# ── ⑤ 배포 경로는 쓰지 않는다 (★★★ 결론축 불변) ─────────────────────────

@pytest.mark.req("NFR-206-M1")
def test_the_deployed_runner_does_not_import_this_module() -> None:
    """★★★ **결론축이 움직이지 않았다** — 러너가 이 모듈을 모른다.

    자리를 세우는 것과 그것을 쓰는 것은 다르다. 어느 케이스도 아직 몫을 쓰지
    않으므로 배포 경로의 수는 종전과 **같아야** 하고, 그 사실은 「수가 같더라」가
    아니라 **의존이 없다**로 재는 것이 강하다 — 수를 다시 뽑아 대조하면 그
    검사는 골든이 갱신되는 날 함께 조용해진다.

    ⚠ 두 파일이 **실재하는지**를 먼저 본다. 경로가 틀리면 「없는 파일에서
    문자열을 못 찾았다」가 통과로 읽힌다 — 이 저장소가 반복해 경계해 온
    「검사하지 않으면서 초록불」의 그 형태다(§13.0.1 ④).
    """
    runner = REPO_ROOT / "core" / "casegrid" / "e2e_runner.py"
    module = REPO_ROOT / "core" / "casegrid" / "ess_share.py"
    assert runner.is_file(), f"러너를 찾지 못했다: {runner}"
    assert module.is_file(), f"검사 대상 모듈을 찾지 못했다: {module}"

    assert "ess_share" not in runner.read_text(encoding="utf-8"), (
        "배포 경로가 몫 모듈을 참조한다 — 결론축이 움직였는지 다시 재야 한다"
    )
