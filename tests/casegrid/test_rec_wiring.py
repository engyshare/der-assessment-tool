"""**`REC` 가 화폐화 경로에 서 있는가** — 그리고 단가가 대장에서 오는가 (R51/WP-6).

## 무엇을 붙드는가

`core/valuestream/rec.py::REC` 는 R16 이래 있었고 **실행 경로에서 부르는 자리가
0곳**이었다(사용자 판정 `docs/decisions-2026-09-01-R51.md` §4 가 그 사실을 실측
으로 적는다). 「구현이 없었다」가 아니라 **받을 자리가 없었다** — `NWAs`·`CP` 가
R51/WP-3 전까지 그랬던 것과 같은 형태이며, 이 저장소가 다섯 번 만난
*「선언·계산은 있는데 읽는 쪽이 없다」* 다.

그래서 이 파일이 재는 것은 **값이 아니라 배선**이다. 지금 단가가 0 이라 편익도
0원이므로 **금액으로는 무엇도 증명할 수 없다** — 0원 편익과 「편익이 아예 없음」은
프로포마에서 똑같이 보인다(러너의 `energy_purchase_row` 주석이 같은 함정을 적어
두었다). 그러므로 세 가지를 따로 잰다.

    ① 편익 목록에 `REC` 태그가 **실제로 선다**            — 배선 자체
    ② 대장 단가를 올리면 **결론 축이 움직인다**            — 「대장 한 줄로 켜진다」
    ③ `peak` 가 여전히 **마지막**이다                      — 자리로 쪼개는 코드를 안 깼다

## ⚠ ③ 을 왜 재는가

`e2e_runner` 는 `_annualise((*settlement_streams, peak), …)` 의 결과를
`annualised[:-1]`(정산 편익) 과 `annualised[-1]`(첨두 절감) 으로 **자리로**
쪼갠다. `REC` 를 그 튜플 **밖**에 더하면 마지막 자리가 `REC` 가 되어 첨두 절감
금액이 조용히 `REC` 의 0원으로 바뀐다 — **예외도 나지 않고 검사도 걸리지 않는다.**
그래서 배선 위치를 금액이 아니라 **자리**로 붙든다.

## ⚠ 마지막 검사는 **래칫이었다 — 발동했다** (R52/WP-6)

`benefit.rec_price` 가 `track: default0`(값 0)을 벗어나는 날, REC 가중치도 함께
대장으로 가야 했다 — 종전에는 `e2e_runner.py` 안의 `REC_WEIGHT_PV`(1.0) 소스
상수였다. 사용자 판정 §5(`docs/decisions-2026-09-02-R52.md`)가 단가를
70원/kWh·`assume`으로 올렸고, 가중치도 **같은 편집에서** 대장의
`benefit.rec_weight_pv` 로 옮겼다. ⚠ **`_LEDGER_VARS`(케이스 그리드 스윕 축)가
아니다** — 그 표는 모든 축에 `low < base < high` 강한 부등호를 요구하는데
(`test_ledger_levels.py::test_levels_come_from_the_ledger_not_from_a_copy`),
이 라운드는 가중치 폭을 조사하지 않아 폭을 지어낼 수 없었다. 그래서
`benefit.rec_price` 와 같은 통로(`AssumptionProvider` 직접 읽기 —
`core/casegrid/ledger_levels.py::required_scalar`)로 `run_single_case_e2e(
rec_weight_pv=...)` 인자에 실린다(`case_report.py`가 이 배선을 진다). 아래
검사는 이제 그 배선을 **재는 것**으로 바뀌었다 — 대장 항목이 있는지, 그리고
러너가 실제로 그 값을 인자로 받아 쓰는지 둘 다 잰다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import load_daily_shapes
from core.report.case_report import REC_PRICE_LEDGER_KEY, REC_WEIGHT_LEDGER_KEY

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_PEAK_TAG = "PeakShaving"
_REC_TAG = "REC"

#: REC 단가 **탐침값**(원/kWh). 대장의 값과 다른 수를 일부러 쓴다 — 대장의 값을
#: 베끼면 이 파일이 사본을 하나 갖게 되고, 대장이 값을 바꾸는 날 여기가 따라오지
#: 않아도 아무 일이 없다(같은 폴더의 `LEVEL_MAP` 규약과 같다).
#: ⚠ **R52/WP-6 이 70.0 → 55.0 으로 바꿨다** — 사용자 판정 §5 가 대장 값을
#: 정확히 70원/kWh 으로 고정해 옛 탐침값이 대장값과 같아졌다
#: (`test_probe_price_is_not_a_copy_of_the_ledger_value` 가 그 상태를 잡는다).
#: 55.0 은 여전히 **전망이 아니다** — 부호와 배선만 재면 되므로 대장값과만
#: 다르면 된다.
_PROBE_REC_PRICE_WON_PER_KWH = 55.0


def _run(rec_price: float, *, rec_weight: float = 1.0) -> CaseOutcome:
    """대장 수준표를 **그대로** 쓴다 — 이 파일이 재는 것이 배선이기 때문이다.

    수준표를 손으로 지으면 대장이 바뀔 때 이 파일이 따라오지 않고, 그때
    「배포 경로와 같은 조건에서 쟀다」가 거짓이 된다.

    ⚠ `rec_weight` 는 `rec_price` 와 같은 자리(러너의 명시 인자)로 넘긴다 —
    `benefit.rec_weight_pv` 가 `level_map` 축이 아니기 때문이다(위 머리말
    참조). 기본값 1.0 은 대장의 실제 값과 **우연히 같다** — 이 파일의
    래칫 검사(`test_rec_weight_moves_to_the_ledger_when_the_price_does`)가
    탐침값(2.0)으로 그 우연에 기대지 않고 배선을 잰다.
    """
    level_map = build_level_map(_ASSUMPTIONS)
    return run_single_case_e2e(
        {},
        level_map=level_map,
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=level_map["household_load_annual_kwh"]["base"],
        rec_price_won_per_unit=rec_price,
        rec_weight_pv=rec_weight,
    )


def _stream_tags(outcome: CaseOutcome) -> list[str]:
    return [line.tag for line in outcome.basis.benefits]


@pytest.mark.req("FR-401-AC2.REC")
def test_rec_stands_in_the_monetisation_path() -> None:
    """★★ 배선 자체 — 편익 목록에 `REC` 가 **선다**(사용자 판정 §4).

    단가가 0 이어도 행을 세운다. 「단가가 0 이라 0원」과 「편익이 없어서 0원」은
    산출물에서 똑같이 보이는데 뜻이 정반대이기 때문이며(하나는 측정, 하나는
    누락), 러너가 전력 구매 비용 행에 이미 같은 판단을 적어 두었다.
    """
    tags = _stream_tags(_run(0.0))
    assert _REC_TAG in tags, (
        f"편익 목록에 REC 가 없다 — 편익 {tags}. 사용자 판정 §4 가 요구한 배선이 "
        "빠졌거나 `settlement_streams` 조립에서 떨어졌다"
    )


@pytest.mark.req("FR-401-AC2.REC")
def test_rec_price_moves_the_conclusion_axis() -> None:
    """★★ 「**대장 한 줄로 켜진다**」 — 단가를 올리면 결론 축이 실제로 움직인다.

    앞 검사만으로는 *「행은 서 있는데 금액이 어디에도 안 들어간다」* 가 통과한다
    (편익 목록에만 있고 `annual_benefit` 합에서 빠지는 형태). 여기서는 **NPV**를
    직접 견주어 그 갈래를 막는다 — 그리고 **오르는 방향**까지 단언한다(수익이
    비용으로 실리는 부호 뒤집힘을 잡는다).
    """
    off = _run(0.0).metrics["npv"]
    on = _run(_PROBE_REC_PRICE_WON_PER_KWH).metrics["npv"]
    assert on > off, (
        f"REC 단가를 0 → {_PROBE_REC_PRICE_WON_PER_KWH}원/kWh 로 올렸는데 NPV 가 "
        f"{off:,.0f} → {on:,.0f} 로 오르지 않았다 — 단가가 계산에 닿지 않았거나 "
        "부호가 뒤집혀 실렸다"
    )


def test_peak_shaving_is_still_the_last_annualised_entry() -> None:
    """★★ `REC` 를 `settlement_streams` **안**에 넣었다 — `peak` 가 마지막이다.

    러너가 연간화 결과를 `annualised[:-1]`·`annualised[-1]` 로 **자리로** 쪼갠다.
    `REC` 를 그 튜플 밖에 더하면 첨두 절감 금액 자리에 REC 의 0원이 들어가고
    **예외도 나지 않는다.** 그 조용한 어긋남을 여기서 붙든다.
    """
    tags = _stream_tags(_run(0.0))
    assert tags[-1] == _PEAK_TAG, (
        f"편익 목록의 마지막이 {tags[-1]!r} 다 — {_PEAK_TAG} 여야 한다. "
        "`_annualise((*settlement_streams, peak), …)` 뒤의 자리 쪼개기가 깨졌다"
    )


def test_rec_weight_moves_to_the_ledger_when_the_price_does() -> None:
    """★★★ **래칫 발동** — 대장이 REC 단가를 얻었다. 가중치도 함께 왔는가.

    이 검사는 R51 이래 *「단가가 등재되는 날 가중치도 함께 대장으로 가야
    한다」*를 지키던 자리다. R52/WP-6 이 사용자 판정 §5 에 따라 단가를
    `default0` → `assume`(70원/kWh)으로 올렸으므로, 이제 이 검사는 **그
    이행이 실제로 일어났는가**를 잰다 — 대장에 항목이 있는지(①)와, 소스
    상수로 되돌아가지 않고 러너가 그 값을 실제로 읽는지(②) 둘 다.
    """
    items = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))["assumptions"]

    price_entry = next((i for i in items if i.get("key") == REC_PRICE_LEDGER_KEY), None)
    assert price_entry is not None, f"대장에 {REC_PRICE_LEDGER_KEY!r} 항목이 없다"
    assert price_entry["track"] == "assume" and float(price_entry["value"]) > 0.0, (
        f"{REC_PRICE_LEDGER_KEY!r} 가 아직 `default0`(값 0)이다 — 이 검사는 "
        "사용자 판정 §5 가 그것을 올린 뒤의 상태를 잰다"
    )

    # ① 가중치도 같은 편집에서 대장으로 왔는가
    weight_entry = next((i for i in items if i.get("key") == REC_WEIGHT_LEDGER_KEY), None)
    assert weight_entry is not None, (
        f"대장에 {REC_WEIGHT_LEDGER_KEY!r} 항목이 없다 — 단가가 `assume`으로 "
        "올라온 지금 가중치도 대장에 있어야 한다(같은 편집)"
    )

    # ② 러너가 소스 상수가 아니라 그 대장 값을 실제로 읽는가 — 배선 자체를 잰다.
    # 단가가 0 이면 가중치를 아무리 흔들어도 편익이 0 원이므로(0 × 가중치 = 0),
    # 탐침 단가로 돌려야 가중치의 배선을 재는 것이 된다.
    base = _run(_PROBE_REC_PRICE_WON_PER_KWH, rec_weight=1.0).metrics["npv"]
    doubled = _run(_PROBE_REC_PRICE_WON_PER_KWH, rec_weight=2.0).metrics["npv"]
    assert doubled > base, (
        f"REC 가중치를 1.0 → 2.0 으로 올렸는데 NPV 가 {base:,.0f} → {doubled:,.0f} "
        "로 오르지 않았다 — 가중치가 대장에는 있어도 러너가 소스 상수를 계속 "
        "쓰고 있을 수 있다"
    )


def test_probe_price_is_not_a_copy_of_the_ledger_value() -> None:
    """★ 탐침값이 대장값의 **사본이 아니다** — 위 두 검사가 동어반복이 아님을 잰다.

    탐침값이 대장의 값과 같아지면 `test_rec_price_moves_the_conclusion_axis` 가
    「0 과 0 을 견주는」 검사가 되어 **아무것도 재지 못한 채 초록불**이 된다.
    """
    items = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))["assumptions"]
    ledger_value = next(
        float(i["value"]) for i in items if i.get("key") == REC_PRICE_LEDGER_KEY
    )
    assert pytest.approx(ledger_value) != _PROBE_REC_PRICE_WON_PER_KWH, (
        f"탐침 단가가 대장값({ledger_value})과 같다 — 견줄 두 실행이 같아진다"
    )
