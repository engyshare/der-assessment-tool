"""**히트펌프 부하가 「난방+냉방+급탕」 셋으로 서고, 간절기에 급탕이 남는다**
— 사용자 지시 (R66/WP-5 · 조사는 R66/WP-3).

사용자 문면 둘이 이 파일을 만들었다
(`docs/decisions-2026-09-07-R66.md` §1ⓑ·§1ⓒ):

    「히트펌프에 대한 월별 난방, 냉방, 급탕 전력을 조사한 후에 적용해줘」

    「간절기에는 냉난방부하 사실상 0에 수렴, **급탕 탱크만 히팅** 발생」

## ★★ 종전에는 무엇이 어긋나 있었나

대장 `load.heatpump.annual` 의 제목이 **「(난방+냉방)」** 이고 값 2,675 =
난방 2,075 + 냉방 600 이었다 — **급탕 항이 없었다.** 그래서 위 둘째 문면이
말하는 *「간절기에 급탕 탱크만 히팅」* 은 **모형에서 0** 이었고, 계절 형상을
세워도 **곱할 값이 없었다**(그 판정문 §2-2 「선행 ②」).

⇒ R66/WP-5 가 급탕을 세워 값이 **3,289.0** 이 됐고, 계절 몫 넷이
`0.1121/0.2019/0.1533/0.5327` → **`0.1293/0.2331/0.1662/0.4714`** 로 갈렸다.

## ★ 이 파일이 재는 것 — 셋

    ⓐ 한 호의 히트펌프 부하가 3,289 이고 20호 단지가 **그 20배**다
    ⓑ 계절 몫 넷의 합이 **정확히 1.0000** 이다
    ⓒ **간절기(봄·가을) 몫에 급탕이 남아 있다** — 위 사용자 문면을 재는 시험

## ⚠ 리터럴 셋(2,075 · 712.4 · 501.6)을 쓰는 것은 **의도다**

이 저장소의 관례는 *「기대값을 시험에 박지 않는다」* 이고, 그 근거는 *「대장을
고칠 때 시험이 따라오지 않으면 아무 일도 없다」* 다. **여기서는 반대가
필요하다** — 재는 것이 크기가 아니라 **셋이 더해져 등재값이 된다는 사실**이고,
칸 하나가 조용히 갈리면 그것은 **빨간불이어야 하는 변경**이다(대장 항목의
`derivation_method` ★★★ 절이 그 셋의 산식을 갖는다. 시험이 그 부기를
**대조**한다).
⇒ 그래서 **합계는 대장에서 읽고**(사본을 만들지 않는다) **칸 셋은 박는다.**

## ⚠ `req()` 마커를 달지 않았다

spec 에 「히트펌프 급탕 부하」를 요구하는 수용기준이 없다. 가까워 보이는 ID 를
짐작해 붙이면 `docs/traceability.md` 에 거짓 인용이 실린다 —
`tests/casegrid/test_appliance_load.py` 머리말이 같은 자리에서 같은 판정을
적었다.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from core.assumption.provider import AssumptionSet
from core.casegrid.appliance_load import (
    HEATPUMP_LOAD_LEDGER_KEY,
    NO_APPLIANCE_LOADS,
    asset_appliance_season_shares,
    with_ledger_defaults,
)
from core.casegrid.household_scale import household_scale
from core.casegrid.profiles import load_daily_shapes
from core.casegrid.seasonal_dispatch import _household_load_if_total_given

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 조사·엑셀이 낸 **칸 셋** (kWh(e)/호·년). 위 머리말 ⚠ 절이 왜 박는지를 갖는다.
#:
#:   난방  참고 엑셀 `전력수요_산출!C16` **유지** — 조사가 크기를 반박하나
#:         대상(제주 평균 기존주택)이 이 단지(4인·표준모델·전열원)와 다르다
#:   냉방  조사값 그대로 — 제주 가구당 에어컨 연간전력 (1차 통계 · 2023년 기준)
#:   급탕  조사 환산 — 41.8 kWh/월 × 12. **없던 항목**이다
_HEATING = 2075.0
_COOLING = 712.4
_DHW_MONTHLY = 41.8
_DHW = _DHW_MONTHLY * 12  # 501.6

#: 사업 주관 측이 정한 단지 규모(`load.household.count`). 20호는 골든이 도는
#: 규모이며, 여기서 재는 것은 **곱하는 순서**다.
_COUNT = 20


def _ledger_heatpump_kwh() -> float:
    """대장이 가진 히트펌프 연간 소비전력량 — **여기서 사본을 만들지 않는다.**"""
    items = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))["assumptions"]
    item = next(i for i in items if i["key"] == HEATPUMP_LOAD_LEDGER_KEY)
    return float(item["value"])


def test_the_heatpump_cell_is_heating_plus_cooling_plus_hot_water() -> None:
    """ⓐ-1 **한 호의 부하가 셋의 합이다** — 급탕이 항목으로 서 있다.

    ⚠ 이 검사가 붙드는 것은 *「합이 얼마인가」* 가 아니라 **급탕 칸이 살아
    있는가**다. 급탕을 지우면 합이 2,787.4 가 되고 이 검사가 빨간불이 된다 —
    종전 2,675 로 되돌아가지도 않으므로(냉방이 조사값으로 갈렸다) **어느 칸이
    사라졌는지**가 실패 문면에서 읽힌다.
    """
    ledger = _ledger_heatpump_kwh()
    assert ledger == pytest.approx(_HEATING + _COOLING + _DHW), (
        f"대장의 {ledger} 가 난방 {_HEATING} + 냉방 {_COOLING} + 급탕 {_DHW} "
        "와 다르다 — 칸 하나가 갈렸거나 사라졌다. 대장 항목의 "
        "`derivation_method` ★★★ 절이 그 셋의 산식을 갖는다"
    )
    assert ledger == pytest.approx(3289.0), (
        "적용값이 조사 권고안(3,289.0)과 다르다 — "
        ".orch 조사 결과 §1-1 권고안 표가 재료다"
    )
    #: 급탕은 **없던 항목**이다. 그 사실이 지워지지 않게 크기를 함께 잰다.
    assert _DHW / ledger == pytest.approx(0.1525, abs=5e-4), (
        "급탕이 이 항목의 15.25% 다 — 종전에는 0% 였다"
    )
    #: ★ **배포 경로가 그 값을 읽는가** — 시나리오가 칸을 비운 실행은
    #: `with_ledger_defaults` 가 대장으로 채운다(R65/WP-2 의 차례 ②).
    #: 여기가 어긋나면 대장은 고쳐졌는데 **실행은 옛 값으로 돈다.**
    filled = with_ledger_defaults(
        NO_APPLIANCE_LOADS, AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))
    )
    assert filled.heatpump_kwh == pytest.approx(ledger)


def test_the_site_load_is_the_household_cell_times_the_count() -> None:
    """ⓐ-2 **20호 단지가 한 호의 20배다** — 곱한 뒤에 더하지 않는다.

    ⚠ **더한 뒤에 곱해야 한다.** 곱한 뒤에 더하면 히트펌프가 단지에 딱 한 대
    있는 사업이 되고, 그 실행은 「모든 가구에 히트펌프를 놓았다」와 산출물에서
    구별되지 않는다(`core/casegrid/appliance_load.py` 머리말 · 대장
    `load.household.annual` 의 `applicable_scope` 가 근거다).

    ⚠ **기저 부하를 0 으로 두고 잰다** — 재는 것이 히트펌프 칸의 배수이므로,
    기저를 섞으면 실패했을 때 어느 항이 어긋났는지 읽히지 않는다.
    """
    heatpump = _ledger_heatpump_kwh()
    shapes = load_daily_shapes()

    one = _household_load_if_total_given(
        shapes, 0.0, heatpump, None, escalation_rate=0.0
    )
    site = _household_load_if_total_given(
        shapes, 0.0, heatpump, _COUNT, escalation_rate=0.0
    )
    assert one is not None and site is not None

    assert one.annual_energy_kwh(year=1) == pytest.approx(heatpump)
    assert site.annual_energy_kwh(year=1) == pytest.approx(heatpump * _COUNT)
    assert household_scale(_COUNT) == _COUNT


def test_the_four_season_shares_add_up_to_exactly_one() -> None:
    """ⓑ **몫 넷의 합이 정확히 1.0000 이다** — 정규화하지 않는다.

    합이 1 이 아니면 **연간 에너지가 조용히 사라지거나 없던 것이 생긴다.**
    읽는 쪽(`resolve_appliance_season_shares`)이 그래서 거부하며, 이 검사는
    **자산이 그 관문을 통과하는 값을 갖고 있는가**를 따로 잰다 — 관문이 있는
    것과 자산이 그것을 만족하는 것은 다른 사실이다.

    ⚠ **네 자리로 끊은 뒤에** 재야 한다. 조사가 「1.0000 이다」라고 적었어도
    저장소가 다시 센다 — `math.fsum` 으로 세는 이유는 float 덧셈 순서에 따라
    끝자리가 흔들리는 것을 배제하기 위해서다.
    """
    shares = asset_appliance_season_shares()
    assert shares is not None

    values = [share for _name, share in shares.by_season]
    assert len(values) == 4, f"계절 넷이 아니다 — {shares.by_season}"
    assert all(round(v, 4) == v for v in values), (
        f"네 자리로 끊겨 있지 않다 — {values}"
    )
    assert math.fsum(values) == 1.0, (
        f"합이 {math.fsum(values)!r} 다 — 정확히 1.0000 이어야 한다"
    )
    #: 갈린 방향도 함께 잰다 — **겨울이 희석됐다**(급탕이 열두 달에 깔린다).
    by_name = dict(shares.by_season)
    assert by_name["겨울"] < 0.5327, (
        "겨울 몫이 종전(0.5327) 이하로 내려오지 않았다 — 급탕이 열두 달에 "
        "깔리면 겨울 비중은 희석되어야 한다"
    )


def test_the_shoulder_seasons_keep_the_hot_water_tank_running() -> None:
    """ⓒ ★★ **간절기(봄·가을) 몫에 급탕이 남아 있다** — 사용자 문면을 잰다.

    사용자 문면: *「간절기에는 냉난방부하 사실상 0에 수렴, **급탕 탱크만
    히팅** 발생」*.

    **봄(3~5월)** 은 난방이 3월 300 만 있고 4·5월이 0 이며 냉방이 0 이다.
    급탕이 없으면 봄 몫 × 총량 = **300** 이어야 한다. 실제로는 거기에
    **41.8 × 3 = 125.4** 가 남아 **425.4** 다 — 그 잔량이 곧 「급탕 탱크만
    히팅」이다.

    **가을(9~11월)** 도 같다: 난방 350(11월) + 냉방 71.2(9월) = 421.2 에
    급탕 125.4 가 얹혀 546.6 이다.

    ⚠ **네 자리로 끊은 몫에서 되짚으므로 오차가 있다** — 그 폭을 `abs=0.2`
    (kWh) 로 명시한다. 끊기 전 값(0.129340…)으로 재면 정확히 425.4 다.
    """
    shares = dict(asset_appliance_season_shares().by_season)  # type: ignore[union-attr]
    total = _ledger_heatpump_kwh()
    three_months_of_hot_water = _DHW_MONTHLY * 3

    spring_kwh = shares["봄"] * total
    autumn_kwh = shares["가을"] * total

    #: 봄에서 급탕을 빼면 **3월 난방 300** 만 남는다.
    assert spring_kwh - three_months_of_hot_water == pytest.approx(300.0, abs=0.2), (
        f"봄 {spring_kwh:.2f} kWh 에서 급탕 {three_months_of_hot_water} 를 빼면 "
        "3월 난방 300 만 남아야 한다 — 남지 않으면 간절기 급탕이 몫에 없다"
    )
    #: 가을에서 급탕을 빼면 **11월 난방 350 + 9월 냉방 71.2** 만 남는다.
    assert autumn_kwh - three_months_of_hot_water == pytest.approx(421.2, abs=0.2), (
        f"가을 {autumn_kwh:.2f} kWh 의 잔량이 난방 350 + 냉방 71.2 와 다르다"
    )
    #: ★ **급탕이 없으면 성립하지 않는 진술** — 봄 몫이 「난방만」의 몫보다 크다.
    assert shares["봄"] > 300.0 / total, (
        "봄 몫이 「3월 난방 300 ÷ 총량」과 같다 — 간절기에 급탕이 0 이라는 뜻이고, "
        "그것이 R66 이전 상태다"
    )
