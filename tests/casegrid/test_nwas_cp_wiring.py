"""**`NWAs`·`CP` 가 화폐화 경로에 서 있는가** — 그리고 운전 방법이 활성화를 가르는가 (R51/WP-7).

## 무엇을 붙드는가

`core/valuestream/nwa.py::NWAs`·`core/valuestream/capacity_payment.py::CapacityPayment`
는 R48 이래 있었고 **실행 경로에서 부르는 자리가 0곳**이었다(사용자 판정
`docs/decisions-2026-09-01-R51.md` §3 이 그 사실을 실측으로 적는다 ·
`.orch/R51/result_4.md`). `tests/casegrid/test_rec_wiring.py` 가 `REC` 에 대해
잰 것과 같은 세 가지를 여기서도 잰다 — 다만 **`REC` 와 달리 이 둘은 기본
비활성이고, 무엇이 활성화를 가르는지가 이 파일이 더 재는 것**이다.

    ① 편익 목록에 `NWAs`·`CP` 태그가 **실제로 선다** (운전 방법과 무관하게)
    ② `ess_operating_mode` 가 활성화를 가른다 — 「자가소비 우선」(배포 기본값)
       에서는 단가가 얼마이든 켜지지 않는다(결론축 불변, 사용자 판정 §3)
    ③ `peak` 가 여전히 **마지막**이다 — `_resolve_nwas_cp()` 를 `*` 로 풀어
       기존 튜플 안에 넣었을 뿐 자리를 흔들지 않았는가

⚠ **래칫 검사가 없다** — `REC` 의 `test_rec_weight_moves_to_the_ledger_when_
the_price_does` 와 짝이 되는 검사는 여기 없다. `NWAs`·`CP` 는 `REC_WEIGHT_PV`
같은 별도 가중치 상수를 소스에 두지 않는다(단가 하나로 산식이 끝난다 —
`계통 방전 kWh × 단가`, `등록 용량 kW × 단가 × 12개월`) — 잊을 「함께 옮길
값」이 애초에 없다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import load_daily_shapes
from core.der.ess import ESSOperatingMode

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_PEAK_TAG = "PeakShaving"
_NWAS_TAG = "NWAs"
_CP_TAG = "CP"
_NWAS_LEDGER_KEY = "benefit.nwas_price"
_CP_LEDGER_KEY = "benefit.cp_price"

#: 탐침값(원/kWh · 원/kW·월) — 대장의 0 과 다른 수를 일부러 쓴다(`test_rec_
#: wiring.py::_PROBE_REC_PRICE_WON_PER_KWH` 와 같은 규약). ⚠ **전망이 아니다.**
_PROBE_NWAS_PRICE_WON_PER_KWH = 100.0
_PROBE_CP_PRICE_WON_PER_KW_MONTH = 10_000.0


def _run(
    *,
    ess_operating_mode: ESSOperatingMode | str | None = None,
    nwas_price: float = 0.0,
    cp_price: float = 0.0,
) -> CaseOutcome:
    """대장 수준표를 **그대로** 쓴다 — `test_rec_wiring.py::_run` 과 같은 이유."""
    level_map = build_level_map(_ASSUMPTIONS)
    return run_single_case_e2e(
        {},
        level_map=level_map,
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=level_map["household_load_annual_kwh"]["base"],
        ess_operating_mode=ess_operating_mode,
        nwas_price_won_per_kwh=nwas_price,
        cp_price_won_per_kw_month=cp_price,
    )


def _stream_tags(outcome: CaseOutcome) -> list[str]:
    return [line.tag for line in outcome.basis.benefits]


@pytest.mark.req("FR-401-AC2.NWAs")
@pytest.mark.req("FR-401-AC2.CP")
def test_nwas_and_cp_stand_in_the_monetisation_path() -> None:
    """★★ 배선 자체 — 편익 목록에 `NWAs`·`CP` 가 **선다**(사용자 판정 §3).

    배포 기본 운전 방법(「자가소비 우선」)에서도 태그는 선다 — 값이 0 인
    것과 편익이 없는 것은 다르다(`test_rec_wiring.py` 와 같은 이유).
    """
    tags = _stream_tags(_run())
    assert _NWAS_TAG in tags, f"편익 목록에 NWAs 가 없다 — 편익 {tags}"
    assert _CP_TAG in tags, f"편익 목록에 CP 가 없다 — 편익 {tags}"


def test_nwas_enabled_only_when_grid_discharge_selected() -> None:
    """★★ 「계통 방전」을 고른 실행에서만 `NWAs` 가 돈을 번다 (사용자 판정 §3).

    배포 기본 운전 방법에서는 단가를 올려도 **결론축이 움직이지 않는다** —
    그것이 §3 ⚠ 이 요구한 「기본 비활성」이다.
    """
    default_off = _run(nwas_price=0.0).metrics["npv"]
    default_on = _run(nwas_price=_PROBE_NWAS_PRICE_WON_PER_KWH).metrics["npv"]
    assert default_on == default_off, (
        "배포 기본 운전 방법에서 NWAs 단가를 올렸는데 npv 가 움직였다 — "
        f"{default_off:,.0f} → {default_on:,.0f}. 사용자 판정 §3 의 「기본 "
        "비활성」이 깨졌다"
    )

    off = _run(
        ess_operating_mode=ESSOperatingMode.GRID_DISCHARGE, nwas_price=0.0
    ).metrics["npv"]
    on = _run(
        ess_operating_mode=ESSOperatingMode.GRID_DISCHARGE,
        nwas_price=_PROBE_NWAS_PRICE_WON_PER_KWH,
    ).metrics["npv"]
    assert on > off, (
        f"「계통 방전」에서 NWAs 단가를 0 → {_PROBE_NWAS_PRICE_WON_PER_KWH}원/kWh "
        f"로 올렸는데 npv 가 {off:,.0f} → {on:,.0f} 로 오르지 않았다 — 단가가 "
        "계산에 닿지 않았거나 활성화가 `ess.operating_mode` 를 못 읽었다"
    )


def test_cp_enabled_only_when_semi_central_dispatch_selected() -> None:
    """★★ 「준중앙급전 등록」을 고른 실행에서만 `CP` 가 돈을 번다 — 위와 대칭."""
    default_off = _run(cp_price=0.0).metrics["npv"]
    default_on = _run(cp_price=_PROBE_CP_PRICE_WON_PER_KW_MONTH).metrics["npv"]
    assert default_on == default_off, (
        "배포 기본 운전 방법에서 CP 단가를 올렸는데 npv 가 움직였다 — "
        f"{default_off:,.0f} → {default_on:,.0f}. 사용자 판정 §3 의 「기본 "
        "비활성」이 깨졌다"
    )

    off = _run(
        ess_operating_mode=ESSOperatingMode.SEMI_CENTRAL_DISPATCH, cp_price=0.0
    ).metrics["npv"]
    on = _run(
        ess_operating_mode=ESSOperatingMode.SEMI_CENTRAL_DISPATCH,
        cp_price=_PROBE_CP_PRICE_WON_PER_KW_MONTH,
    ).metrics["npv"]
    assert on > off, (
        f"「준중앙급전 등록」에서 CP 단가를 0 → {_PROBE_CP_PRICE_WON_PER_KW_MONTH}"
        f"원/kW·월 로 올렸는데 npv 가 {off:,.0f} → {on:,.0f} 로 오르지 않았다"
    )


@pytest.mark.parametrize(
    "ess_operating_mode",
    [None, ESSOperatingMode.GRID_DISCHARGE, ESSOperatingMode.SEMI_CENTRAL_DISPATCH],
)
def test_peak_shaving_is_still_the_last_annualised_entry(
    ess_operating_mode: ESSOperatingMode | None,
) -> None:
    """★★ `NWAs`·`CP` 를 `settlement_streams` **안**에 넣었다 — `peak` 가 마지막이다.

    `_resolve_nwas_cp()` 를 `*` 로 풀어 기존 튜플 안에 넣었을 뿐이므로 세
    운전 방법 전부에서 자리가 흔들리지 않아야 한다(`test_rec_wiring.py` 의
    같은 검사와 같은 근거 — `annualised[:-1]`·`annualised[-1]` 자리 쪼개기).
    """
    tags = _stream_tags(_run(ess_operating_mode=ess_operating_mode))
    assert tags[-1] == _PEAK_TAG, (
        f"편익 목록의 마지막이 {tags[-1]!r} 다 — {_PEAK_TAG} 여야 한다"
    )


def _ledger_entry(key: str) -> dict:
    items = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))["assumptions"]
    entry = next((i for i in items if i.get("key") == key), None)
    assert entry is not None, f"대장에 {key!r} 항목이 없다 — 사용자 판정 §3 이 요구한 등재가 빠졌다"
    return entry


def test_nwas_and_cp_ledger_entries_are_default_inactive() -> None:
    """★ 대장 두 항목이 `track: default0` · `value: 0` 이다 (사용자 판정 §3 ⚠).

    *「NWAs 는 기본 비활성(값 0)을 유지한다」* — 값을 올려 등재하면 없는
    제도 위에 편익을 쌓게 된다.
    """
    nwas_entry = _ledger_entry(_NWAS_LEDGER_KEY)
    cp_entry = _ledger_entry(_CP_LEDGER_KEY)
    for entry in (nwas_entry, cp_entry):
        assert entry["track"] == "default0" and float(entry["value"]) == 0.0, (
            f"{entry['key']!r} 가 기본 비활성을 벗어났다 "
            f"(track={entry['track']!r} · value={entry['value']!r})"
        )


def test_probe_prices_are_not_copies_of_the_ledger_values() -> None:
    """★ 탐침값이 대장값의 **사본이 아니다** — 위 대조가 동어반복이 아님을 잰다."""
    nwas_ledger = float(_ledger_entry(_NWAS_LEDGER_KEY)["value"])
    cp_ledger = float(_ledger_entry(_CP_LEDGER_KEY)["value"])
    assert pytest.approx(nwas_ledger) != _PROBE_NWAS_PRICE_WON_PER_KWH
    assert pytest.approx(cp_ledger) != _PROBE_CP_PRICE_WON_PER_KW_MONTH
