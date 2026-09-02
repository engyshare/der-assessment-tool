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
    ④ 방식 「나」의 `PeakShaving` 0원은 **「꺼짐」이지 「우연한 0」이 아니다** —
       기본요금 단가를 크게 줘도 방식 「나」에서는 npv 가 한 원도 안 움직인다
       (사용자 판정 §1 · `docs/decisions-2026-09-02-R54.md` · R54/WP-1)

⚠ **래칫 검사가 없다** — `REC` 의 `test_rec_weight_moves_to_the_ledger_when_
the_price_does` 와 짝이 되는 검사는 여기 없다. `NWAs`·`CP` 는 REC 가중치
(`benefit.rec_weight_pv`) 같은 별도 가중치 값을 두지 않는다(단가 하나로
산식이 끝난다 — `계통 방전 kWh × 단가`, `등록 용량 kW × 단가 × 12개월`) —
잊을 「함께 옮길 값」이 애초에 없다.
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
#: 기본요금 단가 탐침값(원/kW·월) — 대장 기준값(8,320)의 10배 넘는 큰 수.
#: 「`PeakShaving` 이 꺼져서 0원」과 「애초에 없음」을 가르는 검사가 쓴다.
#: **0 으로 두고 재지 않는다** — 그러면 꺼짐과 0원이 구별되지 않는다.
_PROBE_DEMAND_CHARGE_WON_PER_KW_MONTH = 100_000.0


def _run(
    *,
    ess_operating_mode: ESSOperatingMode | str | None = None,
    nwas_price: float = 0.0,
    cp_price: float = 0.0,
    demand_charge_won_per_kw_month: float | None = None,
) -> CaseOutcome:
    """대장 수준표를 **그대로** 쓴다 — `test_rec_wiring.py::_run` 과 같은 이유.

    `demand_charge_won_per_kw_month` 만 예외다 — 수준표의 `demand_charge` 칸을
    그 값으로 바꾼다. 러너는 이 값을 `PeakShaving` 에만 넘기므로(다른 비용
    행은 안 쓴다), 방식 「나」에서 단가를 흔들어도 npv 가 안 움직이면 그것은
    `PeakShaving` 이 구조적으로 꺼진 증거다.
    """
    level_map = build_level_map(_ASSUMPTIONS)
    if demand_charge_won_per_kw_month is not None:
        level_map = {**level_map, "demand_charge": {"base": demand_charge_won_per_kw_month}}
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
    """★★ 「계통 방전」을 고르면 `NWAs` 만 서고 실행이 **성립**한다 (R54 판정 §1).

    배포 기본 운전 방법에서는 단가를 올려도 **결론축이 움직이지 않는다** —
    그것이 §3 ⚠ 이 요구한 「기본 비활성」이다(위쪽은 R51/WP-7 그대로).

    ⚠⚠ **아래쪽은 R54/WP-1 이 다시 뒤집었다.** R52/WP-3 이 이 자리를 「유형
    E 로 거부된다」로 적었는데, 그것은 러너가 운전 방법과 무관하게
    `PeakShaving` 을 항상 만들던 탓이었다. 사용자 판정 §1
    (`docs/decisions-2026-09-02-R54.md`)은 「한 번에 하나」를 *둘이 있으면
    막는다*가 아니라 *한 가지만 한다*로 정했다 — 방식 「나」에서는
    `PeakShaving` 을 **애초에 만들지 않으므로**(`grid_support.py::
    peak_shaving_enabled`) 거부할 쌍이 없고, 단가를 올리면 `NWAs` 만 npv
    를 움직인다.
    """
    default_off = _run(nwas_price=0.0).metrics["npv"]
    default_on = _run(nwas_price=_PROBE_NWAS_PRICE_WON_PER_KWH).metrics["npv"]
    assert default_on == default_off, (
        "배포 기본 운전 방법에서 NWAs 단가를 올렸는데 npv 가 움직였다 — "
        f"{default_off:,.0f} → {default_on:,.0f}. 사용자 판정 §3 의 「기본 "
        "비활성」이 깨졌다"
    )

    grid_off = _run(
        ess_operating_mode=ESSOperatingMode.GRID_DISCHARGE, nwas_price=0.0
    ).metrics["npv"]
    grid_on = _run(
        ess_operating_mode=ESSOperatingMode.GRID_DISCHARGE,
        nwas_price=_PROBE_NWAS_PRICE_WON_PER_KWH,
    ).metrics["npv"]
    assert grid_on > grid_off, (
        "「계통 방전」에서 NWAs 단가를 올렸는데 npv 가 움직이지 않았다 — "
        f"{grid_off:,.0f} → {grid_on:,.0f}. 방식 「나」에서 NWAs 가 화폐화 "
        "경로에 서지 않았다 (사용자 판정 §1)"
    )


def test_cp_enabled_only_when_semi_central_dispatch_selected() -> None:
    """★★ 「준중앙급전 등록」을 고르면 `CP` 만 서고 실행이 **성립**한다 — 위와 대칭.

    ⚠⚠ **아래쪽은 R54/WP-1 이 뒤집었다** — 이유는 위 시험과 같다(사용자 판정
    §1). 종전의 「유형 E 로 거부된다」(R52/WP-3)는 러너가 `PeakShaving` 을
    항상 만들던 탓이었고, 이제 방식 「나」에서는 `PeakShaving` 이 애초에
    없으므로 `CP` 단가만 npv 를 움직인다.
    """
    default_off = _run(cp_price=0.0).metrics["npv"]
    default_on = _run(cp_price=_PROBE_CP_PRICE_WON_PER_KW_MONTH).metrics["npv"]
    assert default_on == default_off, (
        "배포 기본 운전 방법에서 CP 단가를 올렸는데 npv 가 움직였다 — "
        f"{default_off:,.0f} → {default_on:,.0f}. 사용자 판정 §3 의 「기본 "
        "비활성」이 깨졌다"
    )

    semi_off = _run(
        ess_operating_mode=ESSOperatingMode.SEMI_CENTRAL_DISPATCH, cp_price=0.0
    ).metrics["npv"]
    semi_on = _run(
        ess_operating_mode=ESSOperatingMode.SEMI_CENTRAL_DISPATCH,
        cp_price=_PROBE_CP_PRICE_WON_PER_KW_MONTH,
    ).metrics["npv"]
    assert semi_on > semi_off, (
        "「준중앙급전 등록」에서 CP 단가를 올렸는데 npv 가 움직이지 않았다 — "
        f"{semi_off:,.0f} → {semi_on:,.0f}. 방식 「나」에서 CP 가 화폐화 "
        "경로에 서지 않았다 (사용자 판정 §1)"
    )


def test_peak_shaving_structurally_absent_in_grid_directed_modes() -> None:
    """★★ 방식 「나」의 `PeakShaving` 0원은 **「꺼짐」이지 「우연한 0」이 아니다**.

    값이 0인 것만 재는 검사는 변이를 전부 놓친다 — R53/WP-2 실측에서 유형
    E 는 단가 0원에서도 걸렸다(판정은 `enabled` 를 보지 값을 보지 않았다).
    이 검사는 **기본요금 단가를 크게** 흔들어 「켜져 있는가」를 잰다.

    ⚠ **단가를 0으로 두고 재지 않는다** — 그러면 「꺼짐」과 「0원」이
    구별되지 않는다. 대장 기준값(8,320원/kW·월)과 10만원 탐침값을 잰다.

    - 방식 「가」(배포 기본 운전 방법): 단가를 크게 하면 npv 가 **움직인다**
      — `PeakShaving` 이 실제로 값을 만든다(결론축은 방식 「가」의 동작을
      따르므로 이 단언이 곧 「안 움직였다」의 대조군이다)
    - 방식 「나」(「계통 방전」): 같은 크기의 단가를 줘도 npv 가 **한 원도**
      움직이지 않는다 — 러너는 이 단가를 `PeakShaving` 에만 넘기므로
      (`e2e_runner.py` 의 `demand_charge` 대입), 안 움직인다는 것은 그
      편익이 구조적으로 꺼졌다는 증거다 (사용자 판정 §1 · R54)
    """
    owner_ledger = _run().metrics["npv"]
    owner_probe = _run(
        demand_charge_won_per_kw_month=_PROBE_DEMAND_CHARGE_WON_PER_KW_MONTH
    ).metrics["npv"]
    assert owner_probe > owner_ledger, (
        "방식 「가」에서 기본요금 단가를 크게 했는데 npv 가 움직이지 않았다 — "
        f"{owner_ledger:,.0f} → {owner_probe:,.0f}. PeakShaving 이 값을 "
        "만들지 못한다(대조군이 이미 빨간불)"
    )

    grid_ledger = _run(ess_operating_mode=ESSOperatingMode.GRID_DISCHARGE).metrics["npv"]
    grid_probe = _run(
        ess_operating_mode=ESSOperatingMode.GRID_DISCHARGE,
        demand_charge_won_per_kw_month=_PROBE_DEMAND_CHARGE_WON_PER_KW_MONTH,
    ).metrics["npv"]
    assert grid_probe == grid_ledger, (
        "방식 「나」에서 기본요금 단가를 흔들었는데 npv 가 움직였다 — "
        f"{grid_ledger:,.0f} → {grid_probe:,.0f}. PeakShaving 이 구조적으로 "
        "꺼지지 않았다 (사용자 판정 §1 — 「애초에 만들지 않는다」)"
    )


def test_peak_shaving_is_still_the_last_annualised_entry() -> None:
    """★★ `NWAs`·`CP` 를 `settlement_streams` **안**에 넣었다 — `peak` 가 마지막이다.

    `_resolve_nwas_cp()` 를 `*` 로 풀어 기존 튜플 안에 넣었을 뿐이므로 자리가
    흔들리지 않아야 한다(`test_rec_wiring.py` 의 같은 검사와 같은 근거 —
    `annualised[:-1]`·`annualised[-1]` 자리 쪼개기).

    ⚠⚠ **세 운전 방법 중 하나만 잰다.** 종전에는 이 시험이 `None`·
    `GRID_DISCHARGE`·`SEMI_CENTRAL_DISPATCH` 셋을 매개변수화했다. R52/WP-3
    이 뒤 둘이 유형 E 로 거부되어 출력 자체가 나지 않는다고 적었으나
    R54/WP-1(사용자 판정 §1)이 그 거부를 「애초에 만들지 않음」으로
    바꾸어 출력이 다시 나온다 — 이 시험은 여전히 배포 기본값 `None` 만 잰다
    (방식 「나」에서 `peak` 는 꺼진 채 마지막 자리에 서는지도 잴 수 있으나
    이 WP 가 정한 범위가 아니다).
    """
    tags = _stream_tags(_run(ess_operating_mode=None))
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
