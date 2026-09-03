"""몫이 든 표찰이 **그 몫의 편익까지 닿는가** — `core/casegrid/ess_share_benefits.py`.

## 이 파일이 붙드는 것

R57/WP-1 이 몫을 **수**로 만들었고(`core/casegrid/ess_share.py::split_ess`),
WP-2 가 구상 편익 다섯에 **표찰 받는 자리**를 냈다. 그런데 둘을 잇는 코드가
저장소에 **0곳**이었다 — 몫이 `quantity_id` 를 들고만 있고 그것을 편익에
실어 주는 자리가 없었다. 이 파일은 그 자리가 실제로 섰는지 잰다.

    ① 몫 둘이 배타 판정을 **통과한다** — 표찰이 없으면 거부된다  ★★★ 존재 증명
    ② 태그가 하나가 아니면 거부한다                              몫 = 역할 하나
    ③ 다섯 태그 전건이 다뤄지고, 모르는 태그는 거부한다          조용한 0개 없음
    ④ `SELF_CONSUMPTION` 몫은 거부되고 사유가 메시지에 있다      ★ 명시된 가정
    ⑤ 수량이 몫 크기에 비례한다                                  ★★ 선언이 아니라 수
    ⑥ 배포 경로가 이 공장에 **닿아 있다** — 다리 둘을 다 잰다    ★★★ 배선 (WP-6)

**①의 대조군이 요점이다.** 통과만 재면 「무엇이든 통과시키는」 구현도 초록불이
된다. 같은 편익 둘을 `quantity_id=None` 으로 세우면 **거부돼야** 하고, 그
앞뒤가 붙어야 *「표찰이 통과를 만들었다」* 가 성립한다.

**⑥은 R57/WP-6 에 뒤집혔다.** 종전에는 *「배포 경로가 이 모듈을 모른다」* 였고
그때 그것이 **결론축 불변의 증인**이었다 — WP-6 이 러너에 배선하면서 그 전제가
끝났고, 래칫은 할 일을 하고 울었다. **「결론축이 안 움직였다」의 임자는 이제
골든 3건**(`tests/golden/test_regression_scenarios.py`)이다. ⑥ 이 지금 붙드는
것은 그 반대다 — **배선이 조용히 끊기는 것**.

⚠⚠ **⑥ 의 경로는 한 칸 길다 — 사실대로 잰다.** 러너가 부르는 것은
`core/casegrid/ess_build.py::build_fleet_streams` 이고, 이 공장을 import 하는
것은 **그 파일**이다. 러너의 직접 import 를 단언하면 거짓이 되므로 **다리
둘을 다 잰다**(러너 → `ess_build` → 이 공장). 한 다리만 재면 다른 다리가
끊겨도 초록불이며, 그것이 배선 검사의 존재 이유다
(`tests/casegrid/test_e2e_exclusion_wiring.py` 머리말의 *「함수 층만 검사하면
배선이 되돌아가도 전건 초록불이기 때문이다 … 이 파일이 붙드는 것은 함수가
아니라 배선이다」*).

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 배타 판정의 오라클은 `docs/exclusion-rules.yaml`
   의 유형 `E` 행(`NWAs` × `PeakShaving`)이며 여기서 유형·근거를 다시 적지
   않는다. 다섯 태그의 오라클은 `ESS.value_streams()` 이고, 이 파일은 그 표를
   **베끼지 않고 자원에서 되읽어** 만든다(③).
② **이 설명이 이 검사에 걸리는가** — ⑥ 만 소스를 연다. 그것도 **문면이 아니라
   `ast` 로 뽑은 import 문**이고, 보는 대상은 이 파일이 아니라
   `core/casegrid/e2e_runner.py` 와 `core/casegrid/ess_build.py` 다.
③ **이름보다 넓게 주장하는가** — 아니다. 몫 **하나**가 편익 **하나**가 되는
   자리만 재고, 그 편익들이 리포트·CBA 에 어떻게 들어가는지는 재지 않는다
   (아직 아무도 배선하지 않았다).
④ **수와 그 조건의 짝** — ⑤ 의 오라클은 금액이 아니라 **비례**다. 몫 절반의
   `CP` 를 두 배 하면 몫 전부의 `CP` 와 같아야 한다 — 그래서 이 파일에는
   베껴 온 금액이 없다.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from core.casegrid.ess_share import ESSShare, ESSSharePlan, split_ess
from core.casegrid.ess_share_benefits import (
    ShareBenefitContext,
    benefit_for_tag,
    build_share_benefits,
)
from core.contracts.der import DispatchResult
from core.contracts.validation import ValidationError
from core.contracts.valuestream import ValueStream
from core.der.ess import ESS, ESSOperatingMode
from core.valuestream import CapacityPayment, NWAs, PeakShaving
from core.valuestream.exclusion_table import assert_no_exclusions, collect_exclusions

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 물리 배터리 한 대의 제원. `tests/casegrid/test_ess_share.py` 와 같은 이유로
#: **반올림 자리를 만들지 않는 값**을 골랐다 — 이 파일이 재는 것은 금액의
#: 크기가 아니라 **비례**이므로, 원 단위 반올림이 끼어들면 무엇 때문에
#: 어긋났는지 구분할 수 없다.
_PHYSICAL: MappingProxyType[str, Any] = MappingProxyType({
    "name": "몫 편익 검사용 ESS",
    "capacity_kwh": 100.0,
    "power_kw": 50.0,
    "rte_pct": 90.0,
    "capex_unit_won_per_kwh": 400_000.0,
    "fixed_om_won_per_year": 1_000_000.0,
})

#: 단가 다섯. **값 자체는 이 파일의 오라클이 아니다** — 재는 것은 비례와
#: 표찰의 운반이므로, 생성자가 거부하지 않을 양수면 된다(음수 거부).
_CTX = ShareBenefitContext(
    peak_price_won_per_kwh=200.0,
    offpeak_price_won_per_kwh=70.0,
    demand_charge_won_per_kw_month=8_320.0,
    nwas_price_won_per_kwh=60.0,
    cp_price_won_per_kw_month=7_000.0,
)

#: 몫 둘의 물량 표찰. 계통으로 내보내는 kWh 와 사업장 피크를 낮춘 kW 는
#: **서로 다른 물량**이며, 그래서 두 몫이 동시에 설 수 있다 — 그것이 ① 이다.
_GRID_LABEL = "계통으로 내보낸 kWh"
_PEAK_LABEL = "사업장 피크를 낮춘 kW"

#: 디스패치를 읽는 편익(`NWAs`)도 값을 물어볼 수 있게 하는 최소 결과.
#: **금액은 이 파일의 오라클이 아니므로** 0 으로 둔다.
_STEPS = 24


def _share(
    name: str, fraction: float, mode: ESSOperatingMode, label: str
) -> ESSShare:
    return ESSShare(
        name=name, fraction=fraction, operating_mode=mode, quantity_id=label
    )


def _one_plan(mode: ESSOperatingMode, *, label: str = "물량-단독") -> ESSSharePlan:
    """물리 자원 **전부**를 한 몫으로 세운다 — 모드만 갈아 끼우는 자리."""
    return split_ess(_PHYSICAL, (_share("단독", 1.0, mode, label),))[0]


# ── ① 존재 증명 — 몫 둘이 배타 판정을 통과한다 (★★★) ────────────────────

@pytest.mark.req("FR-402-AC2.E")
def test_two_shares_with_their_own_labels_stand_together() -> None:
    """★★★ **한 대를 갈라 몫마다 다른 역할을 줬고, 그 둘이 함께 선다.**

    이것이 ★분할이 요구한 그림이다 — 사용자 판정 §3 뒷 문장
    (`docs/decisions-2026-09-02-R52.md` §3). 고른 쌍은
    `docs/exclusion-rules.yaml` 의 유형 `E` 행(`NWAs` × `PeakShaving`)이므로
    **표찰이 없으면 거부되는 쌍**이다.

    ⚠ **대조군을 함께 둔다.** 통과만 재면 「무엇이든 통과시키는」 구현도
    초록불이 된다. 같은 편익 둘을 `quantity_id=None` 으로 세우면 거부돼야
    하고, 그 앞뒤가 붙어야 *「표찰이 통과를 만들었다」* 가 성립한다.

    ⚠ 표찰을 **몫 선언에서 그대로 실었는지**도 함께 본다 — 이름에서 만들거나
    편익 클래스에 박은 구현은 이 단언에서 갈린다.
    """
    plans = split_ess(
        _PHYSICAL,
        (
            _share("계통 방전", 0.6, ESSOperatingMode.GRID_DISCHARGE, _GRID_LABEL),
            _share("피크 저감", 0.4, ESSOperatingMode.PEAK_SHAVING, _PEAK_LABEL),
        ),
    )
    benefits = [build_share_benefits(plan, _CTX) for plan in plans]

    assert [type(b).tag for b in benefits] == ["NWAs", "PeakShaving"]
    assert [b.quantity_id for b in benefits] == [_GRID_LABEL, _PEAK_LABEL]

    assert not collect_exclusions(benefits), "물량이 다른데도 배타로 감지됐다"
    assert_no_exclusions(benefits)

    # 대조군 — 같은 편익 둘을 표찰 없이 세우면 종전대로 막힌다.
    unlabelled: list[ValueStream] = [
        NWAs(contribution_price_won_per_kwh=_CTX.nwas_price_won_per_kwh, enabled=True),
        PeakShaving(
            monthly_peak_reduction_kw=[1.0] * PeakShaving.MONTHS,
            demand_charge_won_per_kw_month=_CTX.demand_charge_won_per_kw_month,
            enabled=True,
        ),
    ]
    assert collect_exclusions(unlabelled), "표찰이 없는데 감지되지 않았다"
    with pytest.raises(ValidationError):
        assert_no_exclusions(unlabelled)


# ── ② 태그가 하나가 아니면 거부한다 ──────────────────────────────────────

@pytest.mark.req("NFR-303")
def test_a_share_whose_role_is_not_exactly_one_benefit_is_refused() -> None:
    """**0개도 2개 이상도 거부한다** — 몫은 역할이 하나다.

    ⚠ **혼합 모드 몫은 `split_ess` 로는 만들 수 없다** — 실물에서 확인했다.
    그 함수는 `mode_weights` 를 넘기지 않으므로(`_SHARE_OWNED_FIELDS`),
    `HYBRID` 를 고른 몫은 `ESS._normalize_weights` 가 *「가중치가 필요합니다」*
    로 먼저 거부한다. 그래서 2개 이상 갈래는 **거부 경로를 직접 부르는**
    형태로 잰다 — 혼합 모드 `ESS` 를 직접 세워 `ESSSharePlan` 에 담는다.
    (그 거부가 실제로 나는지도 아래에서 함께 못 박는다. 못 박지 않으면
    「만들 수 없다」가 이 독스트링의 주장으로만 남는다.)

    0개 갈래는 `split_ess` 로 만들 수 있다 — **백업 예비 확보**는
    `ESS.value_streams()` 의 표에 행이 없다(정전 회피 편익은 Phase 3 이라
    선언하지 않는다). 그 몫이 조용히 편익 없이 서는 것을 막는 것이 이 검사다.
    """
    empty = _one_plan(ESSOperatingMode.BACKUP_RESERVE)
    assert empty.resource.value_streams() == (), "표가 바뀌었다 — 오라클을 다시 보라"
    with pytest.raises(ValidationError) as none_caught:
        build_share_benefits(empty, _CTX)
    assert none_caught.value.field == "ess_share_benefits.value_streams"
    assert "0개" in none_caught.value.reason
    assert none_caught.value.action.strip()

    # 혼합 모드는 `split_ess` 를 통과하지 못한다 — 그 사실 자체를 잰다.
    with pytest.raises(ValidationError) as split_caught:
        _one_plan(ESSOperatingMode.HYBRID)
    assert split_caught.value.field == "ess.mode_weights"

    hybrid = ESSSharePlan(
        share=_share("혼합", 1.0, ESSOperatingMode.HYBRID, "물량-혼합"),
        resource=ESS(
            **_PHYSICAL,
            operating_mode=ESSOperatingMode.HYBRID,
            mode_weights={
                ESSOperatingMode.TOU_ARBITRAGE: 0.5,
                ESSOperatingMode.PEAK_SHAVING: 0.5,
            },
        ),
    )
    assert len(hybrid.resource.value_streams()) > 1
    with pytest.raises(ValidationError) as many_caught:
        build_share_benefits(hybrid, _CTX)
    assert many_caught.value.field == "ess_share_benefits.value_streams"
    assert "2개" in many_caught.value.reason


# ── ③ 다섯 태그 전건 · 모르는 태그는 거부 ────────────────────────────────

#: 태그를 **표에서 베끼지 않고 자원에서 되읽는다.** 정본은
#: `ESS.value_streams()` 이므로(모듈 머리말 ①), 여기 다섯을 적으면 같은 표
#: 세 벌이 되고 편익이 한 종 늘 때 이 검사가 낡은 쪽을 오라클로 삼는다.
_SINGLE_MODES = tuple(
    mode for mode in ESSOperatingMode if mode is not ESSOperatingMode.HYBRID
)


@pytest.mark.req("FR-401-AC2.NWAs")
def test_every_tag_the_resource_can_produce_is_handled() -> None:
    """**다섯 전건이 다뤄진다 — 그리고 모르는 태그는 거부한다.**

    「다뤄진다」는 **짓거나 사유를 대고 거부한다**는 뜻이다. 다섯 중 넷은
    편익을 짓고 하나(`SelfConsumption`)는 거부한다(④ 가 그 사유를 잰다) —
    거부도 다룬 것이며, 빠뜨리면 「모르는 태그」로 읽혀 사유를 잃는다.

    ⚠ **오라클을 이 파일에 적지 않는다.** 단일 모드마다 자원을 세워
    `value_streams()` 를 되읽어 태그의 전집을 만든다 — 표를 베끼면 편익이 한
    종 느는 날 이 검사가 낡은 쪽을 오라클로 삼는다.

    ⚠ **모르는 태그를 빈 값으로 떨어뜨리지 않는다.** 떨어뜨리면 그 몫이
    조용히 편익 0개가 되고, 「몫을 갈랐는데 아무 편익도 안 난다」가 아무 예외
    없이 지나간다.
    """
    universe: set[str] = set()
    built: dict[str, str] = {}
    refused: set[str] = set()
    for mode in _SINGLE_MODES:
        plan = _one_plan(mode)
        tags = plan.resource.value_streams()
        universe.update(tags)
        if len(tags) != 1:
            continue
        try:
            built[tags[0]] = type(build_share_benefits(plan, _CTX)).tag
        except ValidationError as refusal:
            # 「모르는 태그」로 떨어진 것이 아니라 그 태그를 **알고서** 거부한
            # 것인지 갈라 둔다 — 둘을 뭉뜽그리면 표에서 빠진 태그가 초록불이다.
            assert refusal.field != "ess_share_benefits.tag", tags[0]
            refused.add(tags[0])

    assert len(universe) == 5, f"태그 전집이 다섯이 아니다: {sorted(universe)}"
    assert built.keys() | refused == universe, "다루지 않은 태그가 있다"
    # 지은 편익의 태그가 자원이 말한 태그와 같아야 한다 — 표가 어긋나면
    # 「짓기는 지었는데 다른 편익」이 통과한다.
    assert all(tag == produced for tag, produced in built.items())

    unknown = "Resilience"
    assert unknown not in universe, "이 태그가 실재하게 됐다 — 예시를 바꿔라"
    with pytest.raises(ValidationError) as caught:
        benefit_for_tag(unknown, _one_plan(ESSOperatingMode.GRID_DISCHARGE), _CTX)
    assert caught.value.field == "ess_share_benefits.tag"
    assert unknown in caught.value.reason
    assert caught.value.action.strip()


# ── ④ 자가소비 몫은 거부되고 사유가 메시지에 있다 (★) ────────────────────

@pytest.mark.req("FR-402-AC1")
def test_a_self_consumption_share_is_refused_with_both_reasons() -> None:
    """★ **자가소비 몫은 이 통로로 편익이 되지 않는다** — 사유 둘이 메시지에 있다.

    ① **인자가 몫 자원에서 나오지 않는다** — `SelfConsumption` 은 요금 차액을
       받는데, 그것은 요금 대장과 부하가 정하지 배터리 몫이 정하지 않는다.
    ② **그 절감은 이미 결론축에 있다** — 자가소비분은 「안 사서」 이미
       `GridPurchase` 를 줄이는 방식으로 계상돼 있어, 편익으로 더하면
       `FR-402-AC1` 이 정의한 **이중 계상**이다(`status.md` 「다음에 집을 것」
       ★관점공백 행의 실측).

    ⚠ **조용히 빈 편익을 내지 않는다.** 거부해야 그 몫을 세운 사람이 *「이
    역할은 이 통로로 편익이 되지 않는다」* 를 그 자리에서 안다. 그래서 이
    검사는 «예외가 났다»에서 그치지 않고 **사유 둘이 문면에 있는지**를 본다.
    """
    plan = _one_plan(ESSOperatingMode.SELF_CONSUMPTION)
    assert plan.resource.value_streams() == ("SelfConsumption",)

    with pytest.raises(ValidationError) as caught:
        build_share_benefits(plan, _CTX)

    assert caught.value.field == "ess_share_benefits.SelfConsumption"
    message = f"{caught.value.reason}\n{caught.value.action}"
    assert "요금 차액" in message, "사유 ①(인자가 자원에서 안 나온다)이 없다"
    assert "이중 계상" in message, "사유 ②(이미 결론축에 있다)가 없다"
    assert "GridPurchase" in message, "어디에 이미 계상돼 있는지가 없다"
    assert caught.value.action.strip()


# ── ⑤ 수량이 몫 크기에 비례한다 (★★) ────────────────────────────────────

@pytest.mark.req("FR-102-AC1.ESS")
def test_the_benefit_of_a_half_share_is_half(capsys: pytest.CaptureFixture[str]) -> None:
    """★★ **몫이 선언이 아니라 수다** — 절반 몫의 `CP` 는 정확히 절반이다.

    `CapacityPayment` 의 등록 용량은 몫 자원의 `power_kw` 에서 온다. 몫을
    0.5/0.5 로 가르면 그 값이 절반이 되므로 **편익 금액도 절반**이다 —
    비율을 편익 쪽에 곱한 것이 아니라 **자원이 갈렸기 때문에** 그렇다.

    ⚠ **금액을 이 파일에 적지 않는다.** 오라클은 *「두 몫을 더하면 몫 전부와
    같다」* 는 항등식이며, 그것이 「몫 크기에 비례한다」의 내용이다. 금액을
    적으면 단가를 바꾸는 날 검사가 낡는다 — 실제로 얻은 수는 아래에서
    인쇄한다(라운드 결과 파일이 그 수를 벤다).

    ⚠ 두 몫의 표찰은 서로 달라야 하므로(`split_ess` 가 거부한다) 같은 편익
    종을 쓰는 몫 둘이어도 표찰은 갈라 준다.
    """
    dispatch = DispatchResult.zeros(_STEPS)
    whole = build_share_benefits(
        _one_plan(ESSOperatingMode.SEMI_CENTRAL_DISPATCH), _CTX
    )
    halves = [
        build_share_benefits(plan, _CTX)
        for plan in split_ess(
            _PHYSICAL,
            (
                _share("앞", 0.5, ESSOperatingMode.SEMI_CENTRAL_DISPATCH, "물량-앞"),
                _share("뒤", 0.5, ESSOperatingMode.SEMI_CENTRAL_DISPATCH, "물량-뒤"),
            ),
        )
    ]

    assert [type(b).tag for b in halves] == [CapacityPayment.tag] * 2
    whole_value = whole.annual_value(dispatch, year=1)
    half_values = [b.annual_value(dispatch, year=1) for b in halves]

    assert half_values[0] == half_values[1]
    assert half_values[0] + half_values[1] == whole_value
    # 자원 쪽이 실제로 갈렸다는 것까지 본다 — 금액만 보면 편익 쪽에서 0.5 를
    # 곱한 구현과 구별되지 않는다.
    assert all(
        b_plan.resource.power_kw * 2 == _PHYSICAL["power_kw"]
        for b_plan in split_ess(
            _PHYSICAL,
            (
                _share("앞", 0.5, ESSOperatingMode.SEMI_CENTRAL_DISPATCH, "물량-앞"),
                _share("뒤", 0.5, ESSOperatingMode.SEMI_CENTRAL_DISPATCH, "물량-뒤"),
            ),
        )
    )
    with capsys.disabled():
        print(f"\n[⑤ 실측] 몫 전부 {whole_value} · 절반 몫 {half_values[0]}")


# ── ⑥ 배포 경로가 이 공장에 닿아 있다 (★★★ 배선 · R57/WP-6) ─────────────

def _imported_names(path: Path) -> dict[str, set[str]]:
    """`ast` 로 **실제 import 문**을 뽑는다 — 「모듈 → 그 모듈에서 가져온 이름」.

    ★★ **문자열을 세지 않는다.** `"ess_share_benefits" in path.read_text()` 로
    재면 *「그 공장을 예로 들면」* 이라 적은 **주석 한 줄이 배선으로 세어져**
    게이트가 조용히 초록불이 된다. `scripts/check_unread_extension_points.py`
    머리말의 *「★ 문자열을 세지 않는다 — 반대 방향의 실패」* 가 같은 근거를
    적었다 — *「위반이 통과로 보고되는 조용한 실패라 더 나빴다」*. 그래서
    거기와 같이 `ast` 로 문법이 보증하는 것만 본다.

    ⚠ `tests/casegrid/test_ess_share.py` 에도 같은 도우미가 있다. **한쪽을
    다른 쪽에서 import 하지 않는다** — 시험 파일이 서로를 부르면 한 파일만
    돌렸을 때 무엇이 함께 실렸는지가 흐려진다.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            found.setdefault(node.module, set()).update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.setdefault(alias.name, set())
    return found


@pytest.mark.req("NFR-206-M1")
def test_the_deployed_path_reaches_this_factory_through_both_legs() -> None:
    """★★★ **배포 경로가 이 공장에 닿아 있다 — 다리 둘을 다 잰다** (R57/WP-6).

    종전 이 자리는 *「러너가 이 모듈을 **모른다**」* 였고 그것이 결론축 불변의
    증인이었다. WP-6 이 배선하면서 그 전제가 끝났다 — 지우는 대신 **반대를
    붙들게 뒤집었다.** 「결론축이 안 움직였다」는 이제 골든 3건
    (`tests/golden/test_regression_scenarios.py`)이 잰다.

    ⚠⚠ **러너는 이 모듈을 직접 import 하지 않는다.** 러너가 부르는 것은
    `core/casegrid/ess_build.py::build_fleet_streams` 이고 이 공장을 부르는
    것은 그 파일이다. 직접 import 를 단언하면 **거짓**이 되므로 다리를 둘로
    나눠 잰다:

        ① 러너 → `core.casegrid.ess_build` 에서 `build_fleet_streams`
        ② `ess_build` → `core.casegrid.ess_share_benefits`

    **한 다리만 재면 다른 다리가 끊겨도 초록불이다** — 그것이 이 검사가
    존재하는 이유다.

    ⚠ 세 파일이 **실재하는지**를 먼저 본다. 경로가 틀리면 「없는 파일에서
    import 를 못 찾았다」가 「import 가 없다」와 같은 모양이 된다(§13.0.1 ④).
    """
    runner = REPO_ROOT / "core" / "casegrid" / "e2e_runner.py"
    build = REPO_ROOT / "core" / "casegrid" / "ess_build.py"
    module = REPO_ROOT / "core" / "casegrid" / "ess_share_benefits.py"
    for path in (runner, build, module):
        assert path.is_file(), f"검사 대상 파일을 찾지 못했다: {path}"

    # ① 러너가 몫 분기의 몸통을 부른다
    from_runner = _imported_names(runner)
    assert "build_fleet_streams" in from_runner.get("core.casegrid.ess_build", set()), (
        "러너가 `core.casegrid.ess_build` 에서 `build_fleet_streams` 를 받지 "
        "않는다 — 첫째 다리가 끊겼다. 러너가 그 모듈에서 받는 이름: "
        f"{sorted(from_runner.get('core.casegrid.ess_build', set()))}"
    )

    # ② 그 몸통이 이 공장을 부른다
    from_build = _imported_names(build)
    assert "core.casegrid.ess_share_benefits" in from_build, (
        "`ess_build.py` 가 몫 편익 공장을 import 하지 않는다 — 둘째 다리가 "
        f"끊겼다. 그 파일이 import 하는 모듈: {sorted(from_build)}"
    )
    assert "build_share_benefits" in from_build["core.casegrid.ess_share_benefits"], (
        "`ess_build.py` 가 공장 모듈을 import 하면서 `build_share_benefits` 를 "
        "받지 않는다 — 몫 하나를 편익 하나로 만드는 함수가 그것이다. 받은 "
        f"이름: {sorted(from_build['core.casegrid.ess_share_benefits'])}"
    )
