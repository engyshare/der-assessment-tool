"""계통 급전 편익 둘과 **운전 주체 배타** — FR-401-AC2.NWAs · .CP · FR-402-AC2.E.

R48 판정 §4 가 만든 자리다. `ESS.value_streams()` 가 계통 방전분을 받을 항목을
선언하지 않는데 `SurplusSale` 은 **시스템 총 역송량**으로 계산되므로 **ESS 가
내보낸 몫이 태양광 잉여판매 행에 얹혀** 있었다 — 두 번 센 것이 아니라 **받을
자리가 없어서 남의 자리에 얹힌 것**이다. `NWAs`·`CP` 가 그 자리를 만들고,
유형 `E` 배타가 *「그 자리에 서면 사용자 운전 편익은 성립하지 않는다」* 를
선언한다.

**오라클**: 순위 1 (해석해) — 산식이 곱 한두 번이라 손계산으로 재현 가능.
배타 쪽은 순위 4 (§13.0.1 ④ — 검사가 실제로 붙드는가).
"""
from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import to_won
from core.contracts.validation import ValidationError
from core.contracts.valuestream import ExclusionType, Payer
from core.valuestream import (
    CapacityPayment,
    NWAs,
    PeakShaving,
    SelfConsumption,
)
from core.valuestream.exclusion_table import (
    DEFAULT_EXCLUSION_RULES,
    assert_no_exclusions,
    collect_exclusions,
    find_rule,
)
from core.valuestream.report import STATE_EXCLUDED, build_report

#: 계통 급전 편익 × 사용자 운전 편익 — **이 파일이 보는 것은 넷이다** (R48
#: 판정 §2 · spec FR-402-AC2.E). 목록을 여기 한 번만 두고 검사들이 함께 돈다 —
#: 갈래마다 손으로 적으면 하나가 빠져도 초록불이다.
#:
#: ⚠ **축 전체는 여섯이다** (R50). 사업자 운전 편익에 `TouArbitrage` 가 섰으므로
#: `2 × 3 = 6` 이며, 그 셋째 열은 `tests/valuestream/test_tou_arbitrage.py` 가
#: 소유한다 — 여기 목록에 더하지 않는 이유는 이 파일의 나머지 검사들이 **계통
#: 급전 편익 둘의 산식·제도 표시**를 재고 있어서, 편익이 늘 때마다 이 파일이
#: 자라면 「무엇을 재는 파일인가」가 흐려지기 때문이다.
GRID_DISPATCH_TAGS = ("NWAs", "CP")
USER_OPERATED_TAGS = ("SelfConsumption", "PeakShaving")
TYPE_E_PAIRS = [(a, b) for a in GRID_DISPATCH_TAGS for b in USER_OPERATED_TAGS]

#: 운전 주체 축의 유형 `E` 쌍 **총수** — `2 × 3`. R48 은 사업자 운전 편익을
#: **둘**로 세어 4 였고, R50 이 `TouArbitrage` 를 세워 **6** 이 됐다.
#: ⚠ 이 수를 늘릴 때는 `docs/exclusion-rules.yaml` 의 「⚠ 여섯을 다 적는다」
#: 문장도 함께 고쳐야 한다 — 다음 사람이 「빠진 쌍이 없다」를 그 문장으로
#: 판정한다.
TYPE_E_ROWS_IN_TABLE = 6


def _dispatch_electric(values: list[float]) -> DispatchResult:
    """electric 계열만 채운 DispatchResult. 다른 매체는 0."""
    zeros = [0.0] * len(values)
    return DispatchResult(
        electric=list(values), heat=list(zeros), cool=list(zeros), fuel=list(zeros)
    )


def _self_consumption() -> SelfConsumption:
    return SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120)


def _peak_shaving() -> PeakShaving:
    return PeakShaving(
        monthly_peak_reduction_kw=[1.0] * 12, demand_charge_won_per_kw_month=5_000
    )


def _user_operated(tag: str) -> SelfConsumption | PeakShaving:
    return _self_consumption() if tag == "SelfConsumption" else _peak_shaving()


def _grid_dispatch(tag: str, *, enabled: bool = True) -> NWAs | CapacityPayment:
    if tag == "NWAs":
        return NWAs(contribution_price_won_per_kwh=50.0, enabled=enabled)
    return CapacityPayment(
        registered_capacity_kw=10.0,
        capacity_price_won_per_kw_month=6_000.0,
        enabled=enabled,
    )


# ── NWAs — FR-401-AC2.NWAs ───────────────────────────────────────────────


@pytest.mark.req("FR-401-AC1", "FR-401-AC2.NWAs")
def test_nwas_is_grid_discharge_kwh_times_contribution_price() -> None:
    """계통 기여 보상 = **계통 방전 kWh × 보상 단가**.

    오라클: 순위 1 (해석해). `[10, -5, 20]` → 양수 합 30kWh × 50원 = 1,500원.
    음수(수전)는 계통 방전이 아니므로 세지 않는다 — `SurplusSale` 과 같은 규약이다.
    """
    vs = NWAs(contribution_price_won_per_kwh=50.0, enabled=True)
    dispatch = _dispatch_electric([10.0, -5.0, 20.0])

    assert vs.annual_value(dispatch, year=1) == to_won(1_500)
    assert vs.formula(dispatch, year=1) == (
        "계통 방전 30.00kWh × 계통 기여 보상 단가 50원/kWh"  # noqa: RUF001
    )


@pytest.mark.req("FR-401-AC2.NWAs")
def test_nwas_is_disabled_by_default_and_says_the_institution_is_missing() -> None:
    """★ **기본 비활성이다** — 다른 편익과 기본값이 **반대다** (R48 §6).

    없는 것은 **제도 자체**이고(설계 중), 제도가 없으면 편익은 작은 것이 아니라
    **0** 이다. 보상단가를 추정해 넣으면 존재하지 않는 제도 위에 편익을 쌓아
    필요 지원액을 과소 산정하게 된다.

    ⚠ **비활성일 때 0 이 나오는 것까지 함께 고정한다** — 기본값만 재면 「꺼져
    있는데 값이 나온다」가 통과한다.
    """
    default = NWAs(contribution_price_won_per_kwh=50.0)
    dispatch = _dispatch_electric([10.0, 20.0])

    assert default.enabled is False, (
        "NWAs 는 기본 비활성이어야 합니다 — 제도 자체가 없습니다 (R48 §6)"
    )
    assert default.annual_value(dispatch, year=1) == to_won(0)
    assert default.policy_warnings() == [], "꺼져 있으면 경고할 것이 없다"
    # 산식은 비활성 여부를 보지 않는다 (`ValueStream.formula` 계약) — 0원 옆에
    # 빈 산식이 놓이면 「계상하지 않았다」와 「계상했는데 0이다」가 같아 보인다.
    assert "계통 방전" in default.formula(dispatch, year=1)


@pytest.mark.req("FR-401-AC2.NWAs")
def test_nwas_payer_is_declared_because_an_empty_payer_would_be_refused() -> None:
    """`payer` 를 비워 둘 수 없다 — 활성화 시 DV-13 으로 거부된다.

    ⚠ 이 값이 **정확하지 않다는 것을 클래스가 적어 두고 있다** — 열거가 제도
    설계 중인 정산 주체를 아직 구분하지 않는다(`core/valuestream/nwa.py` 독스트링).
    """
    assert NWAs.payer is Payer.GRID_OPERATOR
    assert NWAs.scales_with_dispatch_window is True


# ── CP — FR-401-AC2.CP ───────────────────────────────────────────────────


@pytest.mark.req("FR-401-AC1", "FR-401-AC2.CP")
def test_capacity_payment_is_capacity_times_price_times_twelve_months() -> None:
    """용량정산금 = **등록 용량(kW) × 단가(원/kW·월) × 12개월**.

    오라클: 순위 1 (해석해). 10kW × 6,000원/kW·월 × 12 = 720,000원.

    ⚠ 창을 읽지 않으므로 디스패치가 무엇이든 값이 같다 — 그것을
    `scales_with_dispatch_window = False` 가 선언한다. 짐작이 틀리면 금액이
    365배로 어긋나면서도 아무 예외가 나지 않는다.
    """
    vs = CapacityPayment(
        registered_capacity_kw=10.0,
        capacity_price_won_per_kw_month=6_000.0,
        enabled=True,
    )

    assert vs.annual_value(_dispatch_electric([0.0] * 4), year=1) == to_won(720_000)
    assert vs.annual_value(_dispatch_electric([999.0] * 8760), year=1) == to_won(720_000)
    assert vs.formula(_dispatch_electric([0.0] * 4), year=1) == (
        "등록 용량 10.00kW × 용량정산금 단가 6,000원/kW·월 × 12개월"  # noqa: RUF001
    )
    assert CapacityPayment.scales_with_dispatch_window is False


@pytest.mark.req("FR-401-AC2.CP")
def test_capacity_payment_is_disabled_by_default_for_a_different_reason() -> None:
    """★ **기본 비활성이되 이유가 `NWAs` 와 다르다** (R48 §6).

    CP 는 **현행 제도다.** 없는 것은 **분산특구 내 ESS 에 적용할 산정 기준**
    이며, 현행 CP 는 **등록 발전기 기준**으로 설정돼 있다. 기준이 없으면 단가를
    고를 수 없고, 고른 단가로 편익을 쌓으면 필요 지원액을 과소 산정하게 된다.
    """
    default = CapacityPayment(
        registered_capacity_kw=10.0, capacity_price_won_per_kw_month=6_000.0
    )
    dispatch = _dispatch_electric([0.0] * 4)

    assert default.enabled is False, (
        "CP 는 기본 비활성이어야 합니다 — 분산특구 내 ESS 산정 기준이 부재합니다 "
        "(R48 §6)"
    )
    assert default.annual_value(dispatch, year=1) == to_won(0)
    assert default.policy_warnings() == []
    assert "등록 용량" in default.formula(dispatch, year=1)
    assert CapacityPayment.payer is Payer.POWER_MARKET


@pytest.mark.req("FR-401-AC2.NWAs", "FR-401-AC2.CP")
def test_the_two_grid_dispatch_benefits_are_not_paid_from_the_same_wallet() -> None:
    """★★ **계통 급전 편익 둘의 지불 주체는 서로 다르다** (R50).

    ⚠ 이 단언이 필요한 이유: 위 두 시험은 편익마다 **자기 값**만 재므로, 둘이
    다시 한 값으로 뭉쳐도(예: 누군가 `POWER_MARKET` 을 지우고 `GRID_OPERATOR`
    로 되돌리면) **각각을 고치는 순간 둘 다 초록불이 된다.** 갈라 둔 것은
    「두 값이 각각 무엇인가」가 아니라 **「둘이 같지 않다」** 이므로 그것을
    직접 잰다.

    `NWAs` 는 배전망 증설 회피가 근거라 **배전사업자**이고, `CP` 는 **전력시장
    정산**이다. 한 값으로 두면 시장 정산금이 배전사업자 부담으로 잡히고, 그
    값은 리포트의 「지불 주체」 칸에 **그대로 인쇄된다.**
    """
    assert NWAs.payer is not CapacityPayment.payer, (
        "계통 급전 편익 둘은 지불 주체가 다릅니다 — NWAs 는 배전사업자, "
        "CP 는 전력시장입니다 (R50)"
    )
    assert NWAs.payer.value != CapacityPayment.payer.value, (
        "리포트에 인쇄되는 것은 열거 이름이 아니라 **값**입니다 — 값이 같으면 "
        "검토자에게는 갈린 것이 아닙니다"
    )


# ── 제도 표시 문구 — 뭉뚱그리지 않는다 (R48 §6) ──────────────────────────


@pytest.mark.req("FR-401-AC2.NWAs", "FR-401-AC2.CP")
def test_the_two_policy_warnings_are_not_the_same_sentence() -> None:
    """★★ **두 문구를 뭉뚱그리지 않는다** — 심의회가 요구하는 답이 다르다.

    `NWAs` 는 **제도 신설**을, `CP` 는 **산정 기준 보완**을 요구한다. 한 문구로
    뭉치면 답할 수 없는 것을 물은 것이 된다 (R48 판정 §6 · spec FR-401-AC2.CP
    아래 주석).

    ⚠ 문면 전체를 못 박지 않는다 — 표시가 **어느 갈래인지**와 **둘이 다른지**를
    잰다. 전문을 고정하면 문장을 다듬을 때마다 검사가 빨간불이 되고, 그러면
    사람이 검사를 지우게 된다.
    """
    nwas = _grid_dispatch("NWAs").policy_warnings()
    cp = _grid_dispatch("CP").policy_warnings()

    assert len(nwas) == 1
    assert len(cp) == 1
    assert nwas[0] != cp[0], "두 제도 표시가 같은 문장이면 뭉뚱그린 것이다"

    # NWAs — 없는 것은 **제도 자체**다
    assert "제도 필요" in nwas[0]
    assert "설계 중" in nwas[0]
    assert "산정 기준" not in nwas[0], (
        "NWAs 는 「산정 기준이 없다」가 아니라 「제도가 없다」이다 (R48 §6)"
    )

    # CP — 없는 것은 **이 사업에 적용할 산정 기준**이다
    assert "제도 보완 필요" in cp[0]
    assert "산정 기준" in cp[0]
    assert "등록 발전기" in cp[0], (
        "CP 가 등록 발전기 기준으로 설정돼 있다는 것이 보완 요구의 근거다 (R48 §6)"
    )


# ── 유형 E 배타 — FR-402-AC2.E ───────────────────────────────────────────


@pytest.mark.req("FR-402-AC2.E")
def test_all_four_grid_dispatch_pairs_are_declared_as_type_e() -> None:
    """★ **넷을 다 적었는가** — 계통 급전 둘 × (`SelfConsumption`·`PeakShaving`).

    하나라도 빠지면 그 조합만 조용히 열린 채 남고, 남은 조합은 아무 예외 없이
    그럴듯한 금액을 낸다 — R32 가 집합 PPA 에서 *「잉여판매만 막으면 자가소비와
    동시에 켤 수 있다」* 로 밟은 자리와 같다.

    ⚠ **표의 유형 `E` 총수는 넷이 아니라 `TYPE_E_ROWS_IN_TABLE`(=6)이다** —
    R50 이 `TouArbitrage` 를 사업자 운전 편익으로 세웠다. 그 셋째 열의 쌍 둘은
    `tests/valuestream/test_tou_arbitrage.py` 가 재고, 여기서는 **총수만** 본다.

    ⚠ **`applies_to_profile` 이 비어 있어야 한다** — 제도 한정이 아니다. 제도가
    바뀌어도 성립하지 않으므로 유형 `D` 가 아니며, 프로파일을 달면 프로파일을
    모르는 실행에서 **규칙이 조용히 꺼진다**.
    """
    assert len(TYPE_E_PAIRS) == 4

    for a, b in TYPE_E_PAIRS:
        rule = find_rule(a, b)
        assert rule is not None, (
            f"{a} ↔ {b} 배타 규칙이 docs/exclusion-rules.yaml 에 없습니다 "
            "(R48 판정 §2 · spec FR-402-AC2.E)"
        )
        assert rule.exclusion_type is ExclusionType.E, (
            f"{a} ↔ {b} 의 유형이 {rule.exclusion_type} 입니다 — `A` 로 적으면 "
            "「같은 kWh 를 두 번 판다」가, `D` 로 적으면 「제도가 금지한다」가 "
            "거짓이 되어 다음 사람이 틀린 근거를 반박하게 됩니다"
        )
        assert rule.applies_to_profile is None, (
            f"{a} ↔ {b} 에 규제 프로파일이 달려 있습니다 — 제도 한정이 아닙니다"
        )
        assert rule.applies_to_structure is None
        assert "방전" in rule.rationale

    type_e_rows = [r for r in DEFAULT_EXCLUSION_RULES if r.exclusion_type is ExclusionType.E]
    assert len(type_e_rows) == TYPE_E_ROWS_IN_TABLE, (
        f"유형 E 규칙이 {TYPE_E_ROWS_IN_TABLE}건이 아닙니다 — 운전 주체 축은 계통 "
        "급전 편익 둘 × 사업자 운전 편익 셋입니다"  # noqa: RUF001
        f": {[(r.benefit_a, r.benefit_b) for r in type_e_rows]}"
    )


@pytest.mark.req("FR-402-AC2.E")
@pytest.mark.parametrize(("grid_tag", "user_tag"), TYPE_E_PAIRS)
def test_type_e_pair_is_kept_out_of_accounting_on_the_execution_path(
    grid_tag: str, user_tag: str
) -> None:
    """★★ **실행 경로에서 잰다** — `build_report()` 를 지난다.

    이 저장소는 *「거부 기계는 있는데 배포 코드가 아무도 안 부른다」* 를 실물로
    겪었다(R26 · R17/WP-28B). 그래서 `collect_exclusions()` 를 직접 부르는
    것으로 끝내지 않고, 리포트를 만드는 **그 경로**가 이 조합을 계상에서
    빼는지를 고정한다.

    ⚠ **금액이 있는 상태로 재는 것이 요점이다.** 두 편익 다 0원이면 「배타로
    빠졌다」와 「원래 0이다」가 같아 보인다 — 그래서 계통 급전 편익을 켜서 값이
    나오게 두고, 그 값이 `total_accounted()` 에 **들어가지 않는** 것을 본다.
    """
    grid = _grid_dispatch(grid_tag)
    user = _user_operated(user_tag)
    dispatch = _dispatch_electric([10.0, 20.0])

    # 켜져 있으면 값이 난다 — 0원끼리 비교하는 검사가 되지 않게 먼저 확인한다.
    assert grid.annual_value(dispatch, year=1) > to_won(0)
    assert user.annual_value(dispatch, year=1) > to_won(0)

    report = build_report([grid, user], dispatch, year=1)

    states = {line.tag: line.state for line in report.all_lines()}
    assert states[grid_tag] == STATE_EXCLUDED
    assert states[user_tag] == STATE_EXCLUDED
    assert {line.tag for line in report.accounted} == set()
    assert report.total_accounted() == to_won(0), (
        f"{grid_tag} ↔ {user_tag} 는 동시에 성립할 수 없는 운전인데 계상 합계에 "
        "값이 남았습니다 (FR-402-AC2.E)"
    )


@pytest.mark.req("FR-402-AC2.E")
def test_type_e_does_not_fire_when_the_grid_dispatch_benefit_is_off() -> None:
    """**오탐 0 쪽도 함께 잰다** — 꺼져 있으면 배타가 발동하지 않는다.

    두 편익 다 활성일 때만 걸려야 한다. 기본 비활성이 정상 상태이므로, 여기서
    잘못 걸리면 **아무것도 켜지 않은 기준 구성이 거부된다.**
    """
    grid = _grid_dispatch("NWAs", enabled=False)
    user = _self_consumption()
    dispatch = _dispatch_electric([10.0, 20.0])

    report = build_report([grid, user], dispatch, year=1)

    states = {line.tag: line.state for line in report.all_lines()}
    assert states["SelfConsumption"] != STATE_EXCLUDED
    assert states["NWAs"] != STATE_EXCLUDED
    assert report.total_accounted() > to_won(0)


@pytest.mark.req("FR-402-AC2.E")
def test_type_e_is_not_yet_refused_and_that_gap_is_pinned_as_debt() -> None:
    """★★★ **부채 래칫 — 조항은 「거부」인데 실행 경로는 「표시」까지다.**

    spec `FR-402-AC2.E` 는 *「선언적 배타 규칙 테이블로 금지하고 **선택 시 검증
    오류로 거부**한다. **차단 100%**」* 이다. 그런데 `assert_no_exclusions()` 는
    `kind is ExclusionType.A` 만 거른다 — 유형 `E` 조합은 `ValidationError` 없이
    통과하고 리포트에 「배타제외」로 **표시**될 뿐이다. **표시와 거부는 다르다**
    (R16 이 유형 A 에서 지난 자리와 같은 자리다).

    ## 왜 여기서 고치지 않았는가

    그 거름막은 `core/valuestream/exclusion_table.py` 에 있고, **이 작업 구획이
    바꿔도 되는 파일 목록 밖이다**(R48/WP-C §5). 계약 쪽 주석과 로더 오류 문면도
    유형 `E` 를 *「오탐 0」* 으로 적고 있어 **조항(차단 100%)과 어긋나 있는데**,
    그 둘(`core/contracts/valuestream.py`·`core/valuestream/exclusion_loader.py`)도
    이 구획 밖이다.

    ## 그래서 「같음」이 아니라 **갈림을 부채로 고정한다**

    조항이 요구하는 상태를 우리가 만들어 통과시키지 않고, **지금 갈려 있다는
    사실**을 못 박는다. 거름막에 `E` 가 배선되면 이 검사가 **빨간불이 되어 그
    사실을 알리고**, 그때 이 함수는 `pytest.raises(ValidationError)` 로 바뀐다.

    ⚠ **`xfail` 을 쓰지 않았다** — `tests/der/test_pv.py` 의 부채 래칫과 같은
    형태다. `xfail` 은 「검사가 있다」를 「실행·통과한다」와 다르게 만든다.
    """
    streams = [_grid_dispatch("NWAs"), _self_consumption()]
    rules_hit = [
        (a, b)
        for a, b, kind, _ in collect_exclusions(streams)
        if kind is ExclusionType.E
    ]
    assert rules_hit == [("NWAs", "SelfConsumption")], "유형 E 감지 자체가 되지 않는다"

    try:
        assert_no_exclusions(streams)
    except ValidationError as exc:  # pragma: no cover - 배선되면 이 갈래로 온다
        raise AssertionError(
            "유형 E 가 거부로 배선됐습니다 — 조항 FR-402-AC2.E 가 요구하던 상태이니 "
            "이 부채 래칫을 `pytest.raises(ValidationError)` 로 바꾸고, "
            "`core/valuestream/exclusion_table.py`·`core/contracts/valuestream.py`·"
            "`core/valuestream/exclusion_loader.py` 의 「E 는 오탐 0」 문면도 "
            "「차단 100%」로 함께 고치십시오"
        ) from exc
