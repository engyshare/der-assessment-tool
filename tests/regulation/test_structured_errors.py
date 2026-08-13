"""§7.3 대장 밖 입력 검증 — 구조화만 (`rule=` 비움), NFR-303.

`core/regulation/tariff.py` 의 raise 지점 중 다섯 곳(`ResidentialTariffTable`·
`TouTariffTable` 의 `__post_init__` 둘, `bill_residential`·`bill_tou`·
`bill_direct_trade` 의 음수 kWh 거부 셋)은 사용자가 넘긴 값을 검증하지만
어느 `DV` 규칙 문면과도 일치하지 않는다. 그래서 `ValidationError` 로
구조화하되 `rule` 은 비운다 — 대장에 없는 ID 를 달면 추적표가 실재하지
않는 조항을 가리키게 된다 (`core/contracts/validation.py` 참고).

`_select_effective`(`DV-6`)·`_period_for` 의 `KeyError` 는 여기 없다 —
`DV-6` 원문이 「경고 후 최근접 표」를 요구하는데 그 기준(최근접 판정·경고
채널)이 아직 정해지지 않았고, 타입을 바꾸면 구획 밖 `except KeyError`
호출부가 조용히 통과하게 된다. 판정은 `.orch/R24-WP34B-결과.md` 참고.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

import pytest

from core.contracts.assumptions import AssumptionProvider, AssumptionValue
from core.contracts.validation import ValidationError
from core.regulation.tariff import (
    ResidentialTariffTable,
    TariffCatalog,
    TariffEngine,
    TouPeriod,
    TouTariffTable,
    TouUsage,
)


class _NullAssumptions(AssumptionProvider):
    """이 파일의 검증은 전제 조회 전에 걸리므로 값을 담을 필요가 없다."""

    def __init__(self, items: Mapping[str, float | int | str] | None = None) -> None:
        self._items = dict(items or {})

    @property
    def set_name(self) -> str:
        return "regulation-structured-errors-test"

    @property
    def set_version(self) -> str:
        return "1"

    def get(self, key: str) -> AssumptionValue | None:
        if key not in self._items:
            return None
        return AssumptionValue(
            key=key,
            value=self._items[key],
            value_unit="테스트",
            base_year="2026",
            applicable_scope="WP-34B 테스트 스텁",
            derivation_method="테스트 케이스 손계산",
            source="tests/regulation",
            verified_at=date(2026, 8, 13),
            confidence="확정",
            set_name="regulation-structured-errors-test",
            set_version="1",
        )


def _assert_structured(caught: pytest.ExceptionInfo[ValidationError], field: str) -> None:
    parts = caught.value.as_dict()
    assert parts["field"] == field, parts
    assert (parts["reason"] or "").strip(), parts
    assert (parts["action"] or "").strip(), parts
    assert parts["rule"] is None, "대장 밖 검증이므로 rule 은 비워야 한다"


# ── core/regulation/tariff.py :: ResidentialTariffTable.__post_init__ ──────


@pytest.mark.req("NFR-303-M1")
def test_residential_table_rejects_empty_blocks() -> None:
    with pytest.raises(ValidationError) as caught:
        ResidentialTariffTable(
            name="empty",
            valid_from=None,
            valid_to=None,
            blocks=(),
        )
    _assert_structured(caught, "tariff.residential_blocks")


# ── core/regulation/tariff.py :: TouTariffTable.__post_init__ ──────────────


@pytest.mark.req("NFR-303-M1")
def test_tou_table_rejects_empty_periods() -> None:
    with pytest.raises(ValidationError) as caught:
        TouTariffTable(
            name="empty",
            valid_from=None,
            valid_to=None,
            periods=(),
        )
    _assert_structured(caught, "tariff.tou_periods")


# ── core/regulation/tariff.py :: TariffEngine.bill_residential ─────────────


@pytest.mark.req("NFR-303-M1")
def test_bill_residential_rejects_negative_kwh() -> None:
    engine = TariffEngine(
        assumptions=_NullAssumptions(),
        catalog=TariffCatalog(residential=(), tou=(), direct_trade=()),
    )
    with pytest.raises(ValidationError) as caught:
        engine.bill_residential(-1.0, when=date(2026, 1, 1))
    _assert_structured(caught, "tariff.residential_kwh")
    assert "-1" in caught.value.reason


# ── core/regulation/tariff.py :: TariffEngine.bill_tou ──────────────────────


def _tou_catalog_covering(when: date) -> TariffCatalog:
    table = TouTariffTable(
        name="stub",
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        periods=(
            TouPeriod(
                key="all",
                months=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
                weekdays=(0, 1, 2, 3, 4, 5, 6),
                start_hour=0,
                end_hour=24,
                energy_rate_key="tou.stub",
            ),
        ),
    )
    assert table.valid_from is not None and table.valid_to is not None
    assert table.valid_from <= when <= table.valid_to
    return TariffCatalog(residential=(), tou=(table,), direct_trade=())


@pytest.mark.req("NFR-303-M1")
def test_bill_tou_rejects_negative_kwh() -> None:
    when = date(2026, 6, 1)
    engine = TariffEngine(assumptions=_NullAssumptions(), catalog=_tou_catalog_covering(when))
    with pytest.raises(ValidationError) as caught:
        engine.bill_tou((TouUsage(datetime(2026, 6, 1, 10), -1.0),), when=when)
    _assert_structured(caught, "tariff.tou_kwh")
    assert "-1" in caught.value.reason


# ── core/regulation/tariff.py :: TariffEngine.bill_direct_trade ────────────


@pytest.mark.req("NFR-303-M1")
def test_bill_direct_trade_rejects_negative_kwh() -> None:
    engine = TariffEngine(
        assumptions=_NullAssumptions(),
        catalog=TariffCatalog(residential=(), tou=(), direct_trade=()),
    )
    with pytest.raises(ValidationError) as caught:
        engine.bill_direct_trade(-1.0, when=date(2026, 1, 1))
    _assert_structured(caught, "tariff.direct_trade_kwh")
    assert "-1" in caught.value.reason
