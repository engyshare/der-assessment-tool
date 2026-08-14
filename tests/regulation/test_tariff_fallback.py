"""요금표가 분석연도를 포함하지 않을 때 **경고 후 최근접 표** — `DV-6` / R31.

`DV-6` 원문: *「요금표 유효기간이 분석연도를 포함 **(미포함 시 경고 후 최근접
표)**」*

⚠ **R24 는 이 규칙을 「거부」로 읽었다.** `core/contracts/validation.py` 의
`DV_RULES` 사본이 원문에서 **그 괄호를 잘라 먹었고**, 사본만 읽으면 「포함하지
않으면 거부」가 된다 — 원문은 **거부의 반대**를 요구한다. R24 가 사본을 원문으로
되돌리며 그 절단이 판정을 바꾼 사례로 기록해 두었고, 이 파일이 원문대로 닫는다.

붙드는 것 넷:

    ① 유효한 표가 있으면 경고가 없다        폴백이 정상 경로를 오염시키지 않는다
    ② 없으면 **최근접 표로 계산이 계속된다**  거부가 아니라 폴백이다
    ③ **과거 방향이 우선이다**              미래 요금으로 과거를 정산하지 않는다
    ④ 경고가 **결과에 실려** 사용자에게 닿는다

**③이 이 파일의 핵심이다.** ②만 두면 「무언가 골랐다」는 알 수 있지만, 날짜상
더 가까운 미래 표를 고르는 구현도 통과한다 — 그러면 **아직 시행되지 않은 요금으로
과거를 계산**하고 그 결과는 그럴듯한 숫자로 남는다.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.contracts.validation import ValidationError
from core.regulation.tariff import (
    MeterPoint,
    ResidentialBlock,
    ResidentialTariffTable,
    TariffCatalog,
    TariffEngine,
)

#: 요금표가 참조하는 대장 키 — 값은 이 파일의 관심이 아니다(폴백을 본다).
_KEYS = ("rate.basic", "rate.energy", "rate.climate", "rate.fuel")


def _provider() -> AssumptionProvider:
    return AssumptionSet(
        name="검사", version="1",
        items={
            key: AssumptionItem(
                key=key, value=100.0, value_unit="원", base_year="2026",
                applicable_scope="검사용", derivation_method="검사용",
                source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
            )
            for key in _KEYS
        },
        price_basis=PriceBasis.NOMINAL,
    )


def _table(name: str, valid_from: date | None, valid_to: date | None) -> ResidentialTariffTable:
    return ResidentialTariffTable(
        name=name,
        valid_from=valid_from,
        valid_to=valid_to,
        # 구간 하나만 둔다 — 누진 해석은 이 파일의 관심이 아니다(폴백을 본다).
        blocks=(
            ResidentialBlock(
                upper_kwh=None,
                energy_rate_key="rate.energy",
                basic_charge_key="rate.basic",
            ),
        ),
        climate_rate_key="rate.climate",
        fuel_adjustment_rate_key="rate.fuel",
    )


def _engine(*tables: ResidentialTariffTable) -> TariffEngine:
    return TariffEngine(
        assumptions=_provider(),
        catalog=TariffCatalog(residential=tables, tou=(), direct_trade=()),
    )


# ── ① 유효한 표가 있으면 경고가 없다 ─────────────────────────────────

@pytest.mark.req("NFR-303-M1")
def test_a_table_covering_the_year_produces_no_notice() -> None:
    """정상 경로는 조용하다 — 폴백이 정상 경로를 오염시키지 않는다.

    경고만 검사하면 **늘 경고하는** 구현도 통과하고, 그러면 경고가 정보를 잃는다.
    """
    engine = _engine(_table("2026표", date(2026, 1, 1), date(2026, 12, 31)))

    bill = engine.bill_residential(100.0, when=date(2026, 6, 1))

    assert bill.notices == ()


# ── ②③ 없으면 최근접 표로 계속하며, 과거가 우선이다 ──────────────────

@pytest.mark.req("NFR-303-M1")
def test_the_nearest_past_table_is_used_and_calculation_continues() -> None:
    """★ 거부가 아니라 **폴백**이다 — 청구서가 실제로 나온다.

    종전에는 `KeyError` 를 던져 계산이 멈췄다. `DV-6` 은 「경고 후 최근접 표」를
    요구하므로 그것은 규칙의 반대였다.
    """
    engine = _engine(
        _table("2024표", date(2024, 1, 1), date(2024, 12, 31)),
        _table("2025표", date(2025, 1, 1), date(2025, 12, 31)),
    )

    bill = engine.bill_residential(100.0, when=date(2026, 6, 1))

    assert bill.total != 0, "폴백했는데 청구서가 비어 있습니다 — 계산이 계속되지 않았습니다"
    (notice,) = bill.notices
    assert notice.used_table == "2025표", "과거 중 **가장 늦은** 표가 아닙니다"
    assert notice.direction == "과거"


@pytest.mark.req("NFR-303-M1")
def test_a_nearer_future_table_does_not_win_over_a_farther_past_one() -> None:
    """★★★ **과거 방향이 우선이다** — 날짜가 더 가까워도 미래를 쓰지 않는다.

    요청 2026-06-01 에 대해 미래 표는 **31일** 뒤에 시작하고 과거 표는 **518일**
    전에 끝났다. 거리만 보면 미래가 이긴다.

    **그런데 미래 요금표로 과거를 정산하면 실제로 청구되지 않은 요금이 결과에
    들어간다.** 그 값은 그럴듯하고 아무 예외도 나지 않는다 — 「거리」를 기준으로
    삼은 구현은 이 케이스에서만 갈리고 나머지 셋은 전부 초록불이다.
    """
    engine = _engine(
        _table("2024표", date(2024, 1, 1), date(2024, 12, 31)),   # 518일 전
        _table("2026하반기표", date(2026, 7, 2), date(2026, 12, 31)),  # 31일 뒤
    )

    bill = engine.bill_residential(100.0, when=date(2026, 6, 1))

    (notice,) = bill.notices
    assert notice.used_table == "2024표", (
        "미래 표가 날짜상 더 가깝다는 이유로 선택됐습니다 — 아직 시행되지 않은 "
        "요금으로 과거를 계산하게 됩니다"
    )
    assert notice.direction == "과거"


@pytest.mark.req("NFR-303-M1")
def test_the_future_table_is_used_only_when_there_is_no_past_one() -> None:
    """과거에 아무것도 없으면 미래 최근접으로 내려가고, 방향을 알린다.

    ★ **`direction` 이 그 사실을 나르는 것이 요점이다.** 「과거 표로 계산했다」와
    「미래 표로 계산했다」는 읽는 사람에게 뜻이 다르다 — 전자는 그 뒤의 개정을
    반영하지 않은 것이고 후자는 **시행 전 요금**이다.
    """
    engine = _engine(
        _table("2027표", date(2027, 1, 1), date(2027, 12, 31)),
        _table("2030표", date(2030, 1, 1), date(2030, 12, 31)),
    )

    bill = engine.bill_residential(100.0, when=date(2026, 6, 1))

    (notice,) = bill.notices
    assert notice.used_table == "2027표", "미래 중 **가장 이른** 표가 아닙니다"
    assert notice.direction == "미래"


@pytest.mark.req("NFR-303-M1")
def test_no_table_at_all_is_refused_not_silently_zero() -> None:
    """★ 표가 하나도 없으면 **거부한다** — 폴백할 대상이 없다.

    빈 표로 계산하면 요금이 0 원으로 나오고, 그러면 「요금표가 없다」가 「요금이
    없다」와 구별되지 않는다. `MissingAssumption` 이 값에 대해 하는 판단과 같다.

    ⚠ **`rule == "DV-6"` 만 보면 이 단언은 아무것도 붙들지 않는다.** 같은 함수에
    `DV-6` 거부가 둘 있고(표가 없음 · 최근접을 정할 수 없음) **표가 없으면 둘째도
    발동한다** — 그러면 첫째 거부를 통째로 지워도 초록불이다(R31 변이에서 실측).
    이 라운드에 **같은 형태를 두 번째로 만났다**(첫째는 `parameters_of` 의 열거
    거부). **거부 경로가 여럿이면 어느 거부가 답했는가를 문면으로 갈라야 한다.**
    """
    engine = _engine()

    with pytest.raises(ValidationError) as caught:
        engine.bill_residential(100.0, when=date(2026, 6, 1))

    assert caught.value.rule == "DV-6"
    assert "하나도 없습니다" in caught.value.reason, (
        f"다른 DV-6 거부가 대신 답했습니다: {caught.value.reason!r}"
    )
    assert caught.value.action.strip()


# ── ④ 경고가 결과에 실려 사용자에게 닿는다 ───────────────────────────

@pytest.mark.req("NFR-303-M1")
def test_the_notice_carries_a_readable_message() -> None:
    """경고가 **읽을 수 있는 한 줄**을 갖는다 — 리포트가 그대로 싣는다.

    자료형만 실어 두고 문면을 소비자마다 짓게 하면 그 문면이 갈리고, 갈린 문면은
    같은 사실을 다르게 말한다.
    """
    engine = _engine(_table("2025표", date(2025, 1, 1), date(2025, 12, 31)))

    (notice,) = engine.bill_residential(100.0, when=date(2026, 6, 1)).notices

    message = notice.message
    assert "2026-06-01" in message, "요청 시점이 문면에 없습니다"
    assert "2025표" in message, "실제로 쓴 표 이름이 문면에 없습니다"
    assert "과거" in message, "어느 방향으로 대체했는지가 문면에 없습니다"
    assert "주택용" in message, "어느 요금 종류인지가 문면에 없습니다"


@pytest.mark.req("NFR-303-M1")
def test_a_scenario_gathers_notices_from_every_meter_point() -> None:
    """★★ 계량점이 여럿이면 경고도 **한자리에** 모인다.

    `TU-6` 판단대로 한 단지의 계량점은 여럿이다(가구부 N개 + 공용부 + 거래분).
    계량점마다 흩어 두면 읽는 사람이 하나씩 뒤져야 하고, **뒤져야 하는 경고는 곧
    읽히지 않는 경고다.**
    """
    engine = _engine(_table("2025표", date(2025, 1, 1), date(2025, 12, 31)))

    scenario = engine.bill_scenario(
        (
            MeterPoint.residential("가구1", 100.0),
            MeterPoint.residential("가구2", 200.0),
        ),
        when=date(2026, 6, 1),
    )

    assert len(scenario.notices) == 2, (
        f"계량점 둘의 경고가 모이지 않았습니다: {scenario.notices}"
    )
    assert {n.used_table for n in scenario.notices} == {"2025표"}
    # 계량점 단위로도 여전히 닿는다 — 모으는 것이 흩어진 것을 지우지 않는다
    assert len(scenario.meter_bill("가구1").notices) == 1
