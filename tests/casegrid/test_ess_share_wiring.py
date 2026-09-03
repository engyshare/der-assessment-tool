"""**몫이 실행 경로에 배선됐는가** — `run_single_case_e2e(ess_shares=…)` (R57/WP-6).

## 이 파일이 붙드는 것

R57/WP-1 이 몫을 **수**로 만들었고(`core/casegrid/ess_share.py::split_ess`),
WP-4 가 **몫 하나 → 편익 하나** 공장을 세웠다(`core/casegrid/
ess_share_benefits.py::build_share_benefits`). 그런데 **그것을 부르는 실행
경로가 0곳**이었다 — 공장은 섰는데 러너가 부르지 않았다. 이 파일은 그 통로가
실제로 났는지, 그리고 **통로를 내면서 기본 경로가 움직이지 않았는지**를 잰다.

    ① 몫 없음 → 기본 경로가 그대로 돈다        ★★★ 결론축 불변의 앞면
    ② 몫 둘 → 거부 없이 돌고 몫 편익이 **선다**  ★★★ 존재 증명
    ③ 몫 편익이 서면 단일 경로의 그것은 안 선다  ★★ 이중 계상 금지 (FR-402-AC1)
    ④ 비용 행에 몫 **전건**이 실린다             ★★ 사라지면 결론이 좋아진다
    ⑤ 빈 몫 목록은 거부된다                      「가르지 않는다」와 구별된다

**①은 금액을 재지 않는다.** 기본 경로의 수는 골든 회귀
(`tests/golden/test_regression_scenarios.py`)가 세 시나리오의 `npv_won` 을
`fixtures/golden/scenario_*.yaml` 과 **정확 일치**로 이미 붙든다 — 같은 단언을
두 번 두면 기준값의 출처가 둘이 되고, 어느 날 갈리면 어느 쪽이 정본인지 말할
수 없다. 여기서 재는 것은 **인자를 더한 뒤에도 기본 경로가 도는가**다.

**②가 재는 것은 「표찰이 통과를 만든다」가 아니다.** 그것은
`tests/casegrid/test_ess_share_benefits.py` 의 ①이 이미 잰다(같은 조합을 표찰
없이 만들면 거부된다는 대조군까지 함께). 여기서 재는 것은 **실행 경로가 그
편익을 실제로 조립하는가**이며, 그래서 `assert_no_exclusions` 를 가로채
실행이 넘긴 편익 목록을 본다(`tests/valuestream/
test_exclusion_quantity_axis.py` 의 ⑤ 가 쓰는 방식이다).

## 공통 §4 의 네 물음

① **정본이 어디서 오는가** — 몫마다 어느 편익이 서는지는 `ESS.value_streams()`
   가 정하고 이 파일은 그 표를 베끼지 않는다. 대장은 읽지 않는다(아래
   `LEVEL_MAP` 의 탐침값 규약 — `tests/casegrid/test_e2e_exclusion_wiring.py`
   와 같다).
② **이 설명이 이 검사에 걸리는가** — 어느 시험도 소스 문면을 보지 않는다.
   전부 **실행이 실제로 만든 것**을 본다.
③ **이름보다 넓게 주장하는가** — 아니다. 배선만 재고 금액의 크기는 재지
   않는다. ④ 만 금액을 보는데 그것도 **두 실행의 합계가 같은가**라는 항등식이지
   베껴 온 수가 아니다.
④ **수와 그 조건의 짝** — ④ 의 문턱은 **「몫 수 − 1」원**이다. 몫마다
   `to_won()` 이 따로 반올림하기 때문이며(`NFR-103` 경계), 그 한계와 실측은
   `.orch/R57/result_1.md` **6-2** 가 적었다 — *「고정 O&M 1,000,000원을 1/3
   셋으로 가르면 333,333 × 3 = 999,999원이다」*. 여기서 미리 반올림해 맞추면
   반올림이 `to_won()` 한 곳에서만 일어난다는 규약을 깨게 된다.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from core.casegrid import e2e_runner
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ess_share import ESSShare
from core.casegrid.ledger_levels import design_levels
from core.contracts.validation import ValidationError
from core.contracts.valuestream import ValueStream
from core.der.ess import ESSOperatingMode
from core.valuestream import NWAs, PeakShaving

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **배선**이다.
#: 값은 전부 **탐침값**이며 대장의 것과 일부러 다르게 둔다: 같은 수를 쓰면 이
#: 파일이 대장의 사본을 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도
#: 아무 일이 없다(`tests/casegrid/test_e2e_exclusion_wiring.py` 의 규약 그대로).
LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    "grid_purchase_price": MappingProxyType({"base": 100.0}),
    "surplus_sale_price": MappingProxyType({"base": 90.0}),
    "replacement_real_trend": MappingProxyType({"base": 0.0}),
    "pv_inverter_share": MappingProxyType({"base": 0.11}),
    "demand_charge": MappingProxyType({"base": 7_700.0}),
    "pv_fixed_om": MappingProxyType({"base": 70_000.0}),
    #: ⚠ **몫 수로 나누어떨어지지 않는 수를 일부러 고른다** — ④ 가 재는 것이
    #: 「합계가 보존되는가」이므로 반올림 자리가 없으면 그 시험이 문턱을
    #: 시험하지 못한다(1/2 로 갈리면 65,001 은 32,500.5 씩이다).
    "ess_fixed_om": MappingProxyType({"base": 65_001.0}),
    "ess_replacement": MappingProxyType({"base": 350_000.0}),
    **design_levels(),
}

#: 분석기간 **탐침값** — 이 파일이 보는 것은 배선이고 분석기간이 아니다.
_PROBE_HORIZON = 18

#: `NWAs`·`CP` 단가 탐침값. **0 이 아닌 수를 쓴다** — 0 이면 몫 편익이 서 있어도
#: 0원이라 「섰다」와 「안 섰다」가 금액에서 구별되지 않는다. ⚠ 전망이 아니다.
_PROBE_NWAS_PRICE_WON_PER_KWH = 100.0
_PROBE_CP_PRICE_WON_PER_KW_MONTH = 10_000.0

#: 몫 둘 — **계통 방전 0.6 + 피크 저감 0.4** (WP-6 6절 ②가 지정한 조합).
#: 표찰이 서로 다른 것이 요점이다: 같으면 `split_ess` 가 거부하고, 없으면
#: 배타 판정이 유형 `E`(계통 급전 × 사업자 운전)로 거부한다.
_SHARES: tuple[ESSShare, ...] = (
    ESSShare(
        name="계통",
        fraction=0.6,
        operating_mode=ESSOperatingMode.GRID_DISCHARGE,
        quantity_id="물량-계통방전",
    ),
    ESSShare(
        name="피크",
        fraction=0.4,
        operating_mode=ESSOperatingMode.PEAK_SHAVING,
        quantity_id="물량-피크저감",
    ),
)


def _run(*, shares: tuple[ESSShare, ...] | None) -> object:
    """같은 인자로 몫만 갈아 끼운다 — 두 실행의 차이가 **몫뿐**이어야 한다."""
    return run_single_case_e2e(
        {},
        level_map=LEVEL_MAP,
        horizon_years=_PROBE_HORIZON,
        nwas_price_won_per_kwh=_PROBE_NWAS_PRICE_WON_PER_KWH,
        cp_price_won_per_kw_month=_PROBE_CP_PRICE_WON_PER_KW_MONTH,
        ess_shares=shares,
    )


def _intercepted_streams(
    monkeypatch: pytest.MonkeyPatch, *, shares: tuple[ESSShare, ...] | None
) -> tuple[list[ValueStream], object]:
    """실행이 **배타 검사에 실제로 넘긴** 편익 목록을 가로챈다.

    `tests/valuestream/test_exclusion_quantity_axis.py` 의 ⑤ 와 같은 방식이다 —
    소스에 무엇이 적혀 있는가가 아니라 **실행이 무엇을 조립했는가**를 본다.
    가로챈 뒤 진짜 검사를 그대로 부르므로 거부 동작은 바뀌지 않는다.
    """
    seen: list[ValueStream] = []
    real = e2e_runner.assert_no_exclusions

    def _spy(streams: list[ValueStream], *args: object, **kwargs: object) -> None:
        seen.extend(streams)
        real(streams, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(e2e_runner, "assert_no_exclusions", _spy)
    outcome = _run(shares=shares)
    # 가로채기가 실제로 걸렸는지 먼저 본다 — 빈 목록 위에 세운 단언은 배선이
    # 끊겨도 초록불이 된다.
    assert seen, "배타 검사가 실행 경로에서 불리지 않았다 — 단언이 무의미해진다"
    return seen, outcome


# ── ① 몫 없음 → 기본 경로가 그대로 돈다 (★★★ 결론축 불변의 앞면) ─────────

def test_the_default_path_still_runs_when_the_share_argument_exists() -> None:
    """★★★ **몫을 주지 않으면 지금까지와 같다.**

    ⚠ **금액을 이 파일에 박지 않는다.** 기본 경로의 수는 골든 3건이 갖는다
    (머리말 참조). 여기서 재는 것은 *인자 하나를 더한 뒤에도 그 경로가
    성립하는가*이며, 인자의 기본값이 `None`(= 가르지 않는다)임을 함께 못
    박는다 — 기본값이 빈 시퀀스였다면 ⑤ 의 거부가 모든 실행을 막았을 것이다.
    """
    explicit = _run(shares=None)
    implicit = run_single_case_e2e(
        {},
        level_map=LEVEL_MAP,
        horizon_years=_PROBE_HORIZON,
        nwas_price_won_per_kwh=_PROBE_NWAS_PRICE_WON_PER_KWH,
        cp_price_won_per_kw_month=_PROBE_CP_PRICE_WON_PER_KW_MONTH,
    )

    assert "npv" in explicit.metrics  # type: ignore[attr-defined]
    assert explicit.metrics == implicit.metrics, (  # type: ignore[attr-defined]
        "`ess_shares=None` 과 인자를 아예 주지 않은 실행의 지표가 다르다 — "
        "기본값이 「가르지 않는다」가 아니게 됐다"
    )


# ── ② 몫 둘 → 거부 없이 돌고 몫 편익이 선다 (★★★ 존재 증명) ─────────────

@pytest.mark.req("FR-402-AC1")
def test_two_shares_run_and_their_benefits_are_actually_assembled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★★ **실행 경로가 몫 편익을 실제로 조립한다.**

    ⚠ **「표찰이 있으면 통과한다」를 여기서 다시 재지 않는다** — 대조군까지
    갖춘 그 시험은 `tests/casegrid/test_ess_share_benefits.py` 의 ①이다.
    여기서 재는 것은 **배선**이다: 실행이 배타 검사에 넘긴 목록 안에 몫이
    선언한 **물량 표찰**이 실려 있는가. 표찰은 `ESSShare.quantity_id` 에서
    오고 그 밖의 어디에서도 만들어지지 않으므로, 표찰이 목록에 있다는 것은
    `build_share_benefits` 가 실행 경로에서 불렸다는 뜻이다.
    """
    seen, outcome = _intercepted_streams(monkeypatch, shares=_SHARES)

    assert "npv" in outcome.metrics, (  # type: ignore[attr-defined]
        "몫 둘로 가른 실행이 지표를 내지 못했다"
    )
    labels = sorted({s.quantity_id for s in seen if s.quantity_id is not None})
    assert labels == sorted(s.quantity_id for s in _SHARES), (
        f"몫이 선언한 물량 표찰이 실행 경로의 편익에 실리지 않았다: {labels}. "
        "몫 편익 공장이 실행 경로에서 불리지 않았다"
    )
    tags = sorted({type(s).tag for s in seen if s.quantity_id is not None})
    assert tags == sorted([NWAs.tag, PeakShaving.tag]), (
        f"몫의 역할이 그 역할의 편익으로 서지 않았다: {tags}"
    )


# ── ③ 몫 편익이 서면 단일 경로의 그 편익은 서지 않는다 (★★ 이중 계상) ────

@pytest.mark.req("FR-402-AC1")
def test_the_single_path_benefit_does_not_stand_beside_the_share_benefit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★ **같은 편익이 두 번 서지 않는다** — `FR-402-AC1` 이 정의한 중복이다.

    ⚠⚠ 이 중복은 **배타 판정이 막지 못한다** — 규칙표는 서로 다른 태그 쌍을
    다루므로 `PeakShaving` 둘은 어느 규칙에도 걸리지 않는다. 그래서 「거부가
    나지 않았다」로는 이것을 잴 수 없고, **목록 안의 개수**를 세야 한다.

    대조군을 함께 둔다 — 몫 없는 실행에서는 그 하나가 **단일 경로의 것**이다.
    그것을 보이지 않으면 「무엇이든 하나만 세는」 구현도 통과한다.
    """
    with_shares, _ = _intercepted_streams(monkeypatch, shares=_SHARES)
    peaks = [s for s in with_shares if isinstance(s, PeakShaving)]
    assert len(peaks) == 1, (
        f"몫으로 가른 실행에 `PeakShaving` 이 {len(peaks)}개 있다 — 둘이면 "
        "몫 편익과 단일 경로 편익이 함께 서서 같은 절감을 두 번 센다"
    )
    assert peaks[0].quantity_id is not None, (
        "선 `PeakShaving` 이 표찰을 들고 있지 않다 — 몫 편익이 아니라 단일 "
        "경로의 것이 서고 몫 편익이 사라졌다"
    )

    without, _ = _intercepted_streams(monkeypatch, shares=None)
    bare = [s for s in without if isinstance(s, PeakShaving)]
    assert len(bare) == 1 and bare[0].quantity_id is None, (
        "몫 없는 실행의 `PeakShaving` 이 하나가 아니거나 표찰을 들고 있다 — "
        f"{len(bare)}개. 대조군이 성립하지 않으면 위 단언이 아무것도 붙들지 않는다"
    )


# ── ④ 비용 행에 몫 전건이 실린다 (★★ 사라지면 결론이 좋아진다) ───────────

def test_every_share_carries_its_fixed_om_into_the_cost_rows() -> None:
    """★★ **고정 O&M 이 몫 전건에서 걷힌다** — 하나만 걷으면 결론이 좋아진다.

    오라클은 `split_ess` 의 **합계 보존**이다(그 모듈의 「잔차 규약」). 몫으로
    가른 실행의 저장장치 고정 O&M 합계는 몫 없는 실행의 것과 **같아야** 한다 —
    갈랐다고 운영비가 줄지 않는다.

    ⚠ **문턱이 「몫 수 − 1」원이다.** 합계 보존은 **제원(float) 수준**에서
    성립하고, 금액이 된 뒤에는 몫마다 `to_won()` 이 따로 반올림한다(`NFR-103`
    경계). 그 한계와 실측은 `.orch/R57/result_1.md` **6-2** 가 적었다 —
    *「1,000,000원을 1/3 셋으로 가르면 333,333 × 3 = 999,999원」*. 여기서 미리
    반올림해 맞추면 반올림이 한 곳에서만 일어난다는 규약을 깨게 되므로,
    **어긋남을 없애지 않고 문턱으로 인정한다.**
    """
    tag = "ESSFixedOM"
    whole = _run(shares=None)
    split = _run(shares=_SHARES)

    def _fixed_om(outcome: object) -> int:
        rows = [c for c in outcome.basis.costs if c.tag == tag]  # type: ignore[attr-defined]
        assert len(rows) == 1, f"{tag} 비용 행이 하나가 아니다: {len(rows)}개"
        return rows[0].annual_won

    gap = abs(_fixed_om(split) - _fixed_om(whole))
    assert gap <= len(_SHARES) - 1, (
        f"몫으로 가른 실행의 저장장치 고정 O&M 이 {_fixed_om(split):,}원이고 "
        f"몫 없는 실행은 {_fixed_om(whole):,}원이다 — 차이 {gap:,}원은 원 단위 "
        f"반올림 한계(몫 {len(_SHARES)}개 → 최대 {len(_SHARES) - 1}원)를 넘는다. "
        "어느 몫의 고정 O&M 이 비용 행에서 빠졌다"
    )


# ── ⑤ 빈 몫 목록은 거부된다 (「가르지 않는다」와 구별된다) ────────────────

def test_an_empty_share_list_is_refused_not_read_as_no_split() -> None:
    """빈 시퀀스는 **실수**이지 「가르지 않는다」가 아니다.

    가르지 않을 것이라면 `None` 이다(①). 빈 목록을 「가르지 않는다」로 읽으면
    *「몫을 만들었는데 목록이 비었다」* 는 결함이 조용히 정상 실행이 된다.
    거부는 `core/casegrid/ess_share.py::split_ess` 가 하고, 이 시험이 재는 것은
    **그 거부가 러너를 지나 밖으로 나오는가**다.
    """
    with pytest.raises(ValidationError) as caught:
        _run(shares=())

    parts = caught.value.as_dict()
    assert parts["field"] == "ess_share.shares", (
        f"다른 자리가 거부했다: {parts['field']!r}"
    )
    assert (parts["action"] or "").strip(), "조치가 비어 있다 (NFR-303)"
