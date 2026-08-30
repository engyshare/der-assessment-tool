"""교체비·잔존가치 배선이 **자기 자신과 어긋나지 않는가** — R39-E2.

R39-E 가 `core/casegrid/e2e_runner.py::_lifecycle_rows()` 로 교체비·잔존가치를
실행 경로에 배선했다. 그 함수는 **한 번에 두 가지**를 만든다 — 프로포마
`CashFlowRow`(지표에 들어가는 것)와 `OneOffLine`(붙임 4·8 이 인쇄하고 판정하는
것). 둘이 갈리면 **표시와 계산이 다른 사업을 말하고**, 그 어긋남은 어느 지표도
움직이지 않으므로 다른 검사가 잡지 못한다.

## 이 파일이 붙드는 넷

    ⓐ 교체 흐름과 잔존 흐름이 **함께** 선다 — 한쪽만 반영한 수는 양식이 금지한다
    ⓑ `OneOffLine` 의 금액이 프로포마 행과 **같은 부호·같은 수**다
    ⓒ 잔존가치가 세는 취득분이 `replacement_schedule()` 과 **일치**한다
    ⓓ 자원이 물가 계수를 받고도 **교체비에 곱하지 않는** 자리의 목록(래칫)
      — **해마다** 견주므로 「배터리만 굴리고 PCS 는 안 굴린다」도 잡는다(R40)
    ⓔ 그 행들이 **지표까지 닿는다** — 붙임 4 가 인쇄하는 것과 NPV 가 센 것이 같다

## 왜 지표로는 잡히지 않는가

ⓑ 의 부호를 뒤집으면 붙임 4 는 여전히 매끈한 표를 인쇄한다 — 「순액」 한 칸이
바뀔 뿐이고, 그 칸이 맞는지는 프로포마를 따로 보지 않으면 알 수 없다. ⓒ 가
갈리면 *교체비는 계상되는데 그 취득분의 잔존가치는 안 세어지는* 상태가 되는데,
그것은 **결론을 한 방향으로만 나쁘게** 만들어 「보수적이라 안전하다」로 읽힌다.

⚠⚠ **ⓔ 는 변이가 만들게 했다.** 처음 판은 ⓐ~ⓓ 넷이었는데, `e2e_runner` 의
`cost_rows` 에서 `*lifecycle_rows,` 한 줄을 뺀 변이가 **★초록불★** 이었다 —
그 줄이 없어도 `one_off_flows` 는 `CaseBasis` 에 그대로 실리므로 **붙임 4 는
표를 인쇄하고 붙임 8 은 「계상됐다」고 판정하는데 NPV 에는 들어가지 않는다.**
러너에 자리가 둘(프로포마 행 · 표시용 흐름)이라는 사실 자체가 그 구멍이며,
`test_grid_purchase_cost_row.py` 가 전력 구매 행에서 만난 것과 **같은 형태**다
(그쪽은 *「단가를 올리면 NPV 가 줄어든다」* 로 닫았다).

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 대조하는 두 값이 **서로 다른 산출물**이다.
   ⓑ 는 `CashFlowRow.amounts`(프로포마 층) 대 `OneOffLine.amount_won`(표시 층),
   ⓒ 는 `salvage_value()` 가 쓰는 `_acquisitions()` 대 `replacement_schedule()`.
   어느 쪽도 상대에게서 값을 읽지 않는다 — 같은 사실을 두 경로가 각각 말하고,
   그 둘이 같다는 것 자체가 검사가 된다.
② **이 설명이 이 검사에 걸리는가** — 아니다. 소스 문면을 보지 않는다.
③ **이름보다 넓게 주장하는가** — 아래 각 검사의 독스트링이 **붙들지 못하는
   것**을 갈라 적는다. 특히 ⓒ 는 *이 파일이 세우는 구성*에 대해서만 성립한다
   (부속설비를 더 준 PV 는 재지 않았다 — 확인 못 함).
   ⚠ **ⓒ·ⓓ 는 PCS 를 준 ESS 까지 잰다** — ⓓ 는 R40 이, ⓒ 는 R42 가 세웠다.
   ⓐ·ⓑ·ⓔ 는 여전히 위 괄호 그대로다.
④ **수와 그 조건의 짝** — 이 파일은 **금액을 오라클로 적지 않는다.** 자원
   제원은 관계를 드러내기 위한 탐침값이며 대장에서 오지 않는다(대장값을 적으면
   대장이 바뀔 때마다 이 파일이 낡는다). 재는 것은 전부 **두 산출물 사이의
   관계**다.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType

import pytest

from core.casegrid import e2e_runner
from core.casegrid.e2e_runner import _lifecycle_rows, run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.casegrid.models import ONE_OFF_REPLACEMENT, ONE_OFF_SALVAGE
from core.contracts.der import EOL_RETIRE
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV, OperatingMode

#: 탐침 분석기간 — **PV 인버터(12년)와 ESS 본체가 둘 다 이 안에서 교체되도록**
#: 고른 값이다. 하나라도 교체가 없으면 ⓒ·ⓓ 가 「빈 것과 빈 것」을 견주게 되어
#: 무엇을 망가뜨려도 통과한다(공통 §4 ①).
_HORIZON = 20

#: 탐침 물가 계수. 0 이 아니어야 ⓓ 가 「곱했는가」를 가릴 수 있다.
_ESCALATION = 0.02


def _pv(**overrides: object) -> PV:
    kwargs: dict = {
        "name": "탐침PV",
        "capacity_kw": 3.0,
        "capacity_factor": 0.15,
        "lifetime": 25,
        "inverter_lifetime": 12,
        "unit_capex_won_per_kw": 1_500_000.0,
        "fixed_om_won_per_year": 100_000.0,
        "escalation_rate": _ESCALATION,
        "self_consumption_ratio": 0.0,
        "operating_mode": OperatingMode.FULL_EXPORT,
    }
    kwargs.update(overrides)
    return PV(**kwargs)  # type: ignore[arg-type]


def _ess(**overrides: object) -> ESS:
    kwargs: dict = {
        "name": "탐침ESS",
        "capacity_kwh": 10.0,
        "power_kw": 5.0,
        "capex_unit_won_per_kwh": 500_000.0,
        "fixed_om_won_per_year": 100_000.0,
        "escalation_rate": _ESCALATION,
        "operating_mode": ESSOperatingMode.PEAK_SHAVING,
    }
    kwargs.update(overrides)
    return ESS(**kwargs)  # type: ignore[arg-type]


def _reacquisitions(resource: PV | ESS) -> dict[int, int]:
    """`_acquisitions()` 가 아는 **재취득분**만 `{연차: 금액}` 으로 편다.

    **둘 다 부품별 `(수명, {연차: 취득가})` 의 튜플이다**(`ESS` 는 R42 에
    `replacement_schedule()` 을 `_acquisitions()` 에서 파생시키며 부품별 튜플이 됐다).
    수명이 다른 부품 둘을 가지므로 접을 수 없다(사유는 `PV._acquisitions` 독스트링).
    딴 모양이 오면 여기서 터지는 편이 낫다 — 갈래를 남겨 두면 다음 사람이
    「`ESS` 는 다른 모양을 낼 수 있다」로 읽는다.
    여기서 그 배열을 풀되 **최초 취득(1년차)은 뺀다** — 그것은 교체가 아니라 초기
    투자이고 `replacement_schedule()` 에도 없다.
    """
    parts = resource._acquisitions(horizon=_HORIZON)
    flat: dict[int, int] = {}
    for _life, acquired in parts:
        for year, cost in acquired.items():
            if year == 1:
                continue
            flat[year] = flat.get(year, 0) + int(cost)
    return flat


# ── ⓐ 교체와 잔존은 한 단위다 ────────────────────────────────────────

@pytest.mark.req("FR-104-AC2", "FR-104-AC5")
def test_every_replacement_flow_is_accompanied_by_a_salvage_flow() -> None:
    """★ 교체비만 반영한 상태는 **양식이 금지한다** — 그 중간 상태를 붙든다.

    교체비만 넣으면 결론이 나빠지고 잔존가치만 넣으면 좋아진다. 양식이
    *「한쪽만 반영한 수를 결론으로 올리지 않는다」*(NSPM 대칭성,
    `docs/report-form-심의보고서.md:252-256`)로 그 중간을 금지하므로 **한 함수가
    둘을 함께** 만든다. 갈라 두면 한쪽만 부르는 호출자가 생기고, 그 실행의
    결론은 **한 방향으로만 틀린 채 그럴듯하다.**

    ⚠ **붙들지 못하는 것**: 「자원이 교체를 필요로 하는데 흐름이 아예 없다」는
    여기서 재지 않는다 — 그것은 리포트 붙임 8 의 판정이며
    `tests/report/test_unreflected.py` 가 갖는다.
    """
    _rows, lines = _lifecycle_rows(pv=_pv(), ess=_ess(), horizon_years=_HORIZON)

    replaced = {ln.resource_name for ln in lines if ln.kind == ONE_OFF_REPLACEMENT}
    salvaged = {ln.resource_name for ln in lines if ln.kind == ONE_OFF_SALVAGE}

    assert replaced, (
        "이 구성에서 교체 흐름이 하나도 없다 — 탐침 제원이 바뀌어 "
        f"분석기간 {_HORIZON}년 안에 교체가 사라졌다면 이 파일 전체가 "
        "빈 것을 재게 된다(`_HORIZON` 주석 참조)"
    )
    assert replaced <= salvaged, (
        f"교체비만 실린 자원이 있다: {sorted(replaced - salvaged)} — 양식이 "
        "금지하는 중간 상태다(한쪽만 반영한 수를 결론으로 올리지 않는다)"
    )


# ── ⓑ 표시 층과 프로포마 층이 같은 수를 말한다 ───────────────────────

@pytest.mark.req("FR-1001-AC3")
def test_one_off_lines_carry_the_same_signed_amount_as_the_proforma_rows() -> None:
    """★★ 붙임 4 의 금액이 **프로포마에 들어간 그 수**다 — 부호까지 같다.

    표시 층이 「보기 좋게」 부호를 뒤집으면 붙임 4 와 프로포마가 서로 다른 부호를
    말하고, 검토자는 **어느 쪽이 계산에 들어갔는지 가릴 수 없다.** 뒤집는 자리는
    `net_operating_flows()` **하나**여야 한다(두 곳에서 뒤집으면 다시 양수가
    된다 — 그 함수 독스트링의 경고).

    잔존가치가 **음수 비용**으로 실리는 것이 이 검사의 요점 중 하나다: 양수 =
    지출, 음수 = 유입이며 두 층이 그 규약을 같이 쓴다.

    ⚠ **붙들지 못하는 것**: 「그 금액이 옳은가」는 재지 않는다 — 두 층이 **같은
    수를 말하는가**만 본다. 금액의 오라클은 자원 검증 케이스(`tests/der/`)가
    갖는다.
    """
    rows, lines = _lifecycle_rows(pv=_pv(), ess=_ess(), horizon_years=_HORIZON)

    by_tag: dict[str, dict[int, Decimal]] = {}
    for row in rows:
        assert row.tag is not None, f"일회성 행에 tag 가 없다: {row.label}"
        by_tag.setdefault(row.tag, {}).update(row.amounts)

    assert lines, "일회성 흐름이 하나도 없다 — 대조할 것이 없다"
    for line in lines:
        amounts = by_tag.get(line.tag)
        assert amounts is not None, (
            f"붙임 4 가 인쇄하는 `{line.tag}` 에 대응하는 프로포마 행이 없다 — "
            "표시만 되고 계산에는 들어가지 않는 항목이다"
        )
        assert line.year in amounts, (
            f"`{line.tag}` 의 연차가 갈렸다 — 표시 {line.year}년차 · "
            f"프로포마 {sorted(amounts)}"
        )
        assert amounts[line.year] == Decimal(line.amount_won), (
            f"`{line.tag}` {line.year}년차 금액이 갈렸다 — 프로포마 "
            f"{amounts[line.year]:,} · 붙임 4 {line.amount_won:,}. 부호까지 "
            "같아야 한다(양수 = 지출 · 음수 = 유입)"
        )

    # 두 방향이 각각 제 부호로 서 있는지 — 규약 자체를 한 번 못 박는다.
    #
    # ⚠ **둘 다 필요하다.** 위 대조는 두 층이 **같은** 수를 말하는지만 보므로,
    # 두 층이 **함께** 뒤집히면 조용하다(변이로 확인했다 — `_lifecycle_rows`
    # 안에서 `amount = int(cost)` 를 `-int(cost)` 로 바꾸면 행과 표시가 같이
    # 뒤집힌다). 그때 교체비는 **수입**이 되어 결론이 좋아지는데, 붙임 4 는
    # 여전히 「교체비」라는 이름으로 그 수를 인쇄한다.
    salvage = [ln for ln in lines if ln.kind == ONE_OFF_SALVAGE and ln.amount_won]
    assert salvage and all(ln.amount_won < 0 for ln in salvage), (
        "잔존가치가 유입(음수 비용)으로 서 있지 않다 — 양수로 두면 지출로 "
        "합산되어 결론이 조용히 나빠진다"
    )
    replacement = [ln for ln in lines if ln.kind == ONE_OFF_REPLACEMENT]
    assert replacement and all(ln.amount_won > 0 for ln in replacement), (
        "교체비가 지출(양수 비용)로 서 있지 않다 — 음수로 두면 유입이 되어 "
        "**설비를 새로 살 때마다 돈이 들어오는 사업**이 된다"
    )


# ── ⓒ 잔존가치가 세는 취득분 = 교체 스케줄 ───────────────────────────

@pytest.mark.req("FR-104-AC5")
@pytest.mark.parametrize(
    "resource_factory",
    [
        pytest.param(_pv, id="PV"),
        pytest.param(_ess, id="ESS"),
        #: PCS 를 준 갈래 — **R42 가 세웠다.** 이 줄이 없으면 배터리 하나뿐인
        #: 구성만 재게 되고, 「PCS 교체비는 계상되는데 잔존가치는 없다」가 그
        #: 사각에 그대로 남는다(R40 ② 가 실제로 그렇게 남겼다). ⓓ 래칫은
        #: 이미 이 갈래를 재고 있었으나 **`replacement_schedule()` 만** 본다.
        pytest.param(
            lambda **kw: _ess(pcs_lifetime=7, pcs_cost_won=2_000_000.0, **kw),
            id="ESS(+PCS)",
        ),
    ],
)
def test_salvage_counts_exactly_the_acquisitions_that_were_paid_for(
    resource_factory,
) -> None:
    """★★★ **산 것만 잔존가치를 갖는다** — 두 경로가 같은 취득분을 본다.

    `salvage_value()` 는 `_acquisitions()` 를 통해 *마지막 취득 시점*을 알고,
    교체비는 `replacement_schedule()` 이 계상한다. **두 곳이 갈리면 조용하다** —
    갈리는 방향이 둘 다 나쁘다:

        스케줄에만 있다  → 교체비는 냈는데 그 설비의 잔존가치가 사라진다
        취득분에만 있다  → 사지도 않은 설비의 잔존가치를 갖는다

    ⚠ **뒤쪽이 실제로 있었다.** R39-E 의 `PV._acquisitions()` 가
    `retires_at_end_of_life()` 를 보지 않아 `retire` 자원에 인버터 재취득분을
    붙였다(`replacement_schedule()` 은 그때 이미 비어 있었다). 그래서 아래
    `retire` 갈래가 이 검사의 첫 실물이다.

    ⚠⚠ **앞쪽도 실제로 있었다** (R42). R40 ② 가 PCS **교체비**만
    `replacement_schedule()` 에 배선하고 `_acquisitions()` 를 건드리지 않아,
    PCS 를 준 `ESS` 는 *교체비를 내고도 그 잔존가치가 없는* 상태였다 — 결론을
    **한 방향으로만** 나쁘게 만드는 형태다. 그 갈래를 위 `ESS(+PCS)` 가 잰다.

    ⚠ **붙들지 못하는 것**: 이 파일이 세우는 제원에 대해서만 성립한다.
    부속설비를 더 준 `PV` 는 **재지 않았다**(확인 못 함) — 그 구성에서 두 경로가
    같은지는 이 검사가 아무 말도 하지 않는다.

    ⚠ **이 검사가 재는 자원(`PV`·`ESS`)은 이제 둘 다 두 경로가 같은 출처를 본다**
    — `PV` 도 `ESS` 처럼 `replacement_schedule()` 이 `_acquisitions()` 에서
    파생된다(R44 WP-13, 커밋 `e4ce901`). 이 검사는 그 둘(위 `PV`·`ESS`·
    `ESS(+PCS)` 세 갈래)에 대해 **동어반복에 가깝다**(1년차를 거르는 규약만
    남는다). ⚠ **`HeatPump` 도 R43 WP-D2 로 파생됐지만 이 검사는 `HeatPump`
    를 parametrize 하지 않는다** — 그 자원에 대해서는 이 검사가 아무 말도
    하지 않는다. 새 자원이 어느 모양을 고를지는 여전히 모른다.
    """
    for resource in (
        resource_factory(),
        resource_factory(end_of_life_action=EOL_RETIRE),
    ):
        schedule = {
            year: int(cost)
            for year, cost in resource.replacement_schedule(horizon=_HORIZON).items()
        }
        assert _reacquisitions(resource) == schedule, (
            f"{type(resource).__name__}"
            f"({resource.end_of_life_action}): 잔존가치가 세는 재취득분과 "
            f"교체 스케줄이 갈렸다 — 취득 {_reacquisitions(resource)} · "
            f"스케줄 {schedule}"
        )


def test_zero_unit_cost_components_do_not_produce_zero_won_replacements() -> None:
    """단가가 0인 부품은 교체 스케줄에 0원 재취득 연도를 남기지 않는다.

    HeatPump에는 있던 가드가 PV와 ESS에는 빠져 있어 단가가 0이어도 미래 교체 연도에
    0원 행을 내고 있었고, 이로 인해 교체가 없는데도 프로포마에 교체 기록이 표시되었다.
    """
    pv_res = _pv(inverter_unit_capex_won_per_kw=0.0)
    pv_schedule = pv_res.replacement_schedule(horizon=_HORIZON)
    assert 13 not in pv_schedule, (
        f"단가 0인 PV 인버터가 13년차에 재취득 일정을 냈습니다: {pv_schedule.get(13)}"
    )

    ess_res = _ess(replacement_unit_won_per_kwh=0.0)
    ess_schedule = ess_res.replacement_schedule(horizon=_HORIZON)
    assert 16 not in ess_schedule, (
        f"단가 0인 ESS 배터리가 16년차에 재취득 일정을 냈습니다: {ess_schedule.get(16)}"
    )


# ── ⓓ 계수를 받고도 곱하지 않는 자리 (래칫) ──────────────────────────

#: 물가 계수를 **받고도 교체비에 곱하지 않는** 자원의 목록 — 실측 부채다.
#:
#: `tests/contract/test_escalation_debt.py` 는 **인자가 넘어가는가**를 `ast` 로
#: 본다. 그것이 비어도 *자원이 그 값을 쓰는가*는 별개이며, 호출 그래프를
#: 따라가야 해서(`replacement_schedule` → `_acquisitions` → `_battery_cost`)
#: **문면으로는 볼 수 없다.** 그래서 여기서 **행동으로** 잰다.
#:
#: **지금은 비어 있다** — R40 이 `ESS` 를 여기서 뺐다. 그 한 줄(`_acquisitions()`
#: 가 재취득분에 계수를 곱한다)이 결론축을 **−6,066,881 → −6,289,675원**으로
#: 움직였고 골든 여섯 값을 같은 단위에서 다시 뽑았다. 래칫이 설계대로 동작한
#: 자리다 — **줄어도 빨간불**이 나서 목록과 기준값을 함께 옮기라고 알렸다.
#:
#: 비어 있다고 지우지 않는다. 새 자원이 계수를 받고도 무시하면 이 검사가 그것을
#: **늘어난 쪽으로** 잡는다.
KNOWN_ESCALATION_IGNORED_IN_REPLACEMENT: frozenset[str] = frozenset()


@pytest.mark.contract
def test_resources_that_ignore_the_escalation_they_were_given_do_not_grow() -> None:
    """★★ 계수를 **받는 것**과 **쓰는 것**은 다르다 — 그 차이를 행동으로 잰다.

    같은 자원을 계수 `0.02` 와 `0.0` 으로 세워 `replacement_schedule()` 을
    견준다. 두 스케줄이 **같으면** 그 자원은 받은 계수를 교체비에 쓰지 않는
    것이다. `copy.copy` 로 복제해 속성 하나만 바꾸는 이유는, 생성자를 다시
    부르면 *다른 인자가 함께 달라졌을 가능성*이 남기 때문이다.

    ⚠ **교체가 없는 자원은 판정하지 않는다** — 빈 스케줄 둘은 언제나 같아서
    「안 쓴다」로 잘못 세어진다. 확인 못 한 것을 부채로 세면 다음 사람이 없는
    일을 한다.

    ⚠⚠ **스케줄 전체를 견주므로 「한 항만 굴린다」는 잡지 못한다** — `ESS` 는
    배터리와 PCS 두 항을 같은 사전에 넣고 같은 해면 **합산**한다. 한쪽만 계수를
    받아도 사전은 달라지므로 이 검사는 초록불이다. 그래서 **PCS 를 준 `ESS` 를
    탐침에 함께 세운다** — 배터리 없이 PCS 만 교체되는 해가 생겨 그 해의 금액이
    따로 드러난다(파일 머리 ③ 이 「PCS 를 준 ESS 는 재지 않았다 — 확인 못 함」
    으로 적어 두었던 자리다. R40 이 재고 그 문장을 뗐다).

    ⚠⚠ **R42 부터 교체비가 보는 계수는 `replacement_escalation_rate` 다.**
    그래서 이 검사는 그쪽을 눕힌다 — `escalation_rate` 를 눕히면 교체비는 이제
    반응하지 않고, 그것은 결함이 아니라 **계수를 가른 결과**다(`Q-17` 이 O&M 을
    적용범위에서 뺐다. 사유는 `DER.replacement_escalation_factor()`).
    ★ 이 검사가 바로 그 변화를 **처음 잡았다** — 계수를 가르자마자 빨간불이 났고,
    래칫이 설계대로 「무엇이 달라졌는지 사람이 보라」고 말한 자리다.

    ★★ **함께 잰다: O&M 은 교체 계수에 반응하지 않는다.** 교체 계수가 O&M 으로
    새면 `Q-17` 하단 −2.0 이 *「물가 계수를 태우지 않았다면」* 이 아니라 *「O&M
    물가까지 꺼 버렸다면」* 을 재게 되고, 그 오염은 5.1 의 한 행으로 나간다.
    여기 탐침은 **금액이 있는** 제원이라 그 누수가 수로 드러난다 —
    `tests/contract/test_der_contract.py` 의 같은 단언은 계약 픽스처가 단가를
    주지 않아 `PV` 에서 0원끼리 견주게 된다.

    ⚠ **붙들지 못하는 것**: 이 검사는 `replacement_schedule()` 과 `fixed_om()`
    만 본다. `variable_om()`·`salvage_value()` 는 재지 않는다(그쪽은 각각 자원
    검증 케이스와 ⓒ 가 갖는다).
    ★ **종전 이 자리에 「`ESS._acquisitions()` 는 PCS 취득분을 아예 담지 않는다」가
    적혀 있었다** — R42 가 그것을 닫았고 ⓒ 의 `ESS(+PCS)` 갈래가 붙든다.
    """
    ignored: set[str] = set()
    #: PCS 를 준 갈래를 **별도 이름**으로 센다 — 같은 `ESS` 이름으로 접으면
    #: 한쪽만 반응해도 「반응했다」가 되어 위 ⚠⚠ 가 도로 열린다.
    probes: tuple[tuple[str, PV | ESS], ...] = (
        ("PV", _pv()),
        ("ESS", _ess()),
        ("ESS(+PCS)", _ess(pcs_lifetime=7, pcs_cost_won=2_000_000.0)),
    )
    for label, resource in probes:
        with_escalation = resource.replacement_schedule(horizon=_HORIZON)
        if not with_escalation:
            continue  # 교체가 없다 — 판정 대상 아님

        flat = copy.copy(resource)
        flat.replacement_escalation_rate = 0.0
        without = flat.replacement_schedule(horizon=_HORIZON)
        # **해마다** 견준다 — 사전 전체를 견주면 한 항만 반응해도 통과한다
        if any(with_escalation[y] == without[y] for y in with_escalation):
            ignored.add(label)

        # 교체 계수만 눕혔는데 O&M 이 따라 누웠다면 두 계수가 새고 있다
        assert flat.fixed_om(year=10) == resource.fixed_om(year=10), (
            f"{label}: 교체비 계수를 눕혔는데 **고정 O&M 이 따라 움직였습니다** — "
            "대장(`capex.replacement_real_trend`)이 O&M 을 적용범위에서 뺐으므로, "
            "이 누수는 스윕 한 축을 통째로 다른 것으로 만듭니다"
        )

    assert ignored == set(KNOWN_ESCALATION_IGNORED_IN_REPLACEMENT), (
        f"교체비에 물가 계수를 쓰지 않는 자원의 목록이 실측과 다릅니다.\n"
        f"  실측: {sorted(ignored)}\n"
        f"  기대: {sorted(KNOWN_ESCALATION_IGNORED_IN_REPLACEMENT)}\n"
        "늘었다면 새 자원이 계수를 받고도 무시합니다. 줄었다면 누가 고친 "
        "것이므로 이 목록을 함께 줄이고 **골든 기준값을 재산출**하십시오 — "
        "그 한 줄이 결론축을 움직입니다."
    )


# ── ⓔ 그 행들이 지표까지 닿는가 ──────────────────────────────────────

#: 러너 탐침 구성. **대장을 읽지 않는다** — 이 검사가 보는 것은 금액이 아니라
#: *표시와 지표의 관계*다. 대장값을 베끼면 대장이 바뀔 때 이 파일이 낡는다.
def _level_map() -> Mapping[str, Mapping[str, float]]:
    return {
        "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
        "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
        "discount_rate": MappingProxyType({"base": 0.045}),
        "grid_purchase_price": MappingProxyType({"base": 120.0}),
        "surplus_sale_price": MappingProxyType({"base": 90.0}),
        # 교체 설비단가의 실질 추세 — 러너가 요구한다(R42 에 스윕 축으로 올렸다).
        # **0 은 대장의 사본이 아니라 중립값이다** — 0 이면 명목 교체단가가 물가
        # 계수만 타므로 이 축을 흔들지 않는 것과 같다. 이 파일은 그 축을 재지
        # 않으므로 중립을 고른다(대장의 base 가 바뀌어도 여기는 따라오지 않아야
        # 한다 — 따라오면 이 파일이 대장의 사본을 갖게 된다).
        "replacement_real_trend": MappingProxyType({"base": 0.0}),
        # PV 설비단가 중 인버터 몫 — 러너가 요구한다(R43 에 스윕 축으로 올렸다).
        # **대장의 15 와 다른 수를 일부러 쓴다** — 같은 수를 쓰면 이 파일이 대장의
        # 사본을 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도 아무 일이
        # 없다(위 두 단가와 같은 규약이다). 이 파일은 이 축을 재지 않는다.
        # ⚠ **아무 수나 되는 것은 아니다** — 아래 ⓔ 가 지표 차이와 흐름 현가를
        # **1원 이내**로 대조하는데, 이 몫이 정하는 교체비·잔존가치의 원 단위
        # 반올림 잔차가 그 여유를 넘길 수 있다(0.12 는 1.27원이 나온다).
        # 허용오차를 넓히지 않고 **잔차를 내지 않는 탐침**을 골랐다.
        "pv_inverter_share": MappingProxyType({"base": 0.11}),
        # 첨두 기본요금 단가 — 러너가 요구한다(R43 에 대장·스윕 축으로 올렸다).
        # **대장의 8,320 과 다른 수를 일부러 쓴다** — 같은 수를 쓰면 이 파일이
        # 대장의 사본을 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도
        # 아무 일이 없다(위 단가들과 같은 규약이다). 이 파일은 이 축을 재지 않는다.
        "demand_charge": MappingProxyType({"base": 7_700.0}),
        **design_levels(),
    }


@pytest.mark.req("FR-703-AC1.npv")
def test_the_one_off_flows_reach_the_npv(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★★ 붙임 4 가 인쇄하는 흐름이 **NPV 에 실제로 들어간다**.

    러너에는 자리가 둘이다 — `cost_rows` 에 들어가는 프로포마 행과 `CaseBasis`
    에 실리는 표시용 `OneOffLine`. **`*lifecycle_rows,` 한 줄만 빼면** 표시는
    그대로인 채 계산에서만 빠지고, 그때 붙임 4 는 교체비 표를, 붙임 8 은
    「계상됐다」를 계속 말한다. **실측으로 확인했다 — 그 변이는 ⓐ~ⓓ 넷과
    리포트 검사 전건을 통과했다**(★초록불★).

    ## 어떻게 재는가 — 두 층을 견준다

    `_lifecycle_rows` 를 「아무것도 만들지 않는」 것으로 갈아 끼워 한 번 더
    돌리고, **두 NPV 의 차이**가 붙임 4 가 인쇄하는 흐름의 **현가 합**과 같은지
    본다. 왼쪽은 프로포마·NPV 파이프라인이 낸 수이고, 오른쪽은 표시용 흐름과
    `basis.discount_rate` 로 이 검사가 다시 세운 수다 — **어느 쪽도 상대에게서
    값을 읽지 않는다**(공통 §4 ①).

    ⚠ **1원의 허용 오차를 둔다.** `npv` 는 합계를 **한 번** 원 단위로 접고, 이
    검사는 행마다 할인해 더한다 — 접는 지점이 달라 마지막 1원이 갈릴 수 있다.
    그보다 넓게 두지 않는다(NFR-103: 금액은 원 단위).

    ⚠ **붙들지 못하는 것**: 「그 금액이 옳은가」는 여전히 재지 않는다. 표시된
    흐름이 **그대로** 지표에 들어갔는가만 본다 — 둘이 함께 틀리면 조용하다.
    """
    wired = run_single_case_e2e({}, level_map=_level_map(), horizon_years=_HORIZON)
    flows = wired.basis.one_off_flows
    assert flows, (
        "탐침 구성이 일회성 흐름을 하나도 내지 않는다 — 이 검사가 «없는 것이 "
        "지표에 안 닿는다»를 재게 된다"
    )

    monkeypatch.setattr(e2e_runner, "_lifecycle_rows", lambda **_kw: ([], ()))
    unwired = run_single_case_e2e({}, level_map=_level_map(), horizon_years=_HORIZON)
    assert not unwired.basis.one_off_flows, (
        "갈아 끼운 `_lifecycle_rows` 가 쓰이지 않았다 — 러너가 다른 경로로 "
        "흐름을 만들고 있다면 이 검사의 전제가 깨진다"
    )

    rate = wired.basis.discount_rate
    present_value = sum(
        line.amount_won / (1 + rate) ** line.year for line in flows
    )
    measured = unwired.metrics["npv"] - wired.metrics["npv"]

    assert abs(measured - present_value) <= 1, (
        f"일회성 흐름이 지표에 닿지 않는다 — 흐름을 없앴을 때 NPV 가 "
        f"{measured:,.0f}원 움직였는데 붙임 4 가 인쇄하는 흐름의 현가는 "
        f"{present_value:,.0f}원이다. 러너의 `cost_rows` 가 "
        "`*lifecycle_rows,` 를 싣는지 확인하십시오"
    )
