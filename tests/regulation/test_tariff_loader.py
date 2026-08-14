"""요금표 YAML 로더 테스트 — FR-501-AC4.

R15-WP26B 가 `test_tariff.py:227` 의 `FR-501-AC4` 마커를 `FR-501-AC5` 로 옮긴 뒤
AC4("요금표는 코드가 아닌 데이터 파일로 관리, 개정 시 코드 변경 불필요")가
미매핑으로 드러났다 — `tariff.py` 의 구조를 **만드는 곳**이 코드(테스트가 직접
dataclass 를 구성)뿐이었기 때문이다. 이 파일은 그 구조를 YAML 에서 만드는
`core/regulation/tariff_loader.py` 를 검증한다.

**실제 요금 단가는 여기 없다.** YAML 픽스처는 `AssumptionProvider` 키 문자열만
담고, 그 키가 가리키는 값은 이 파일의 `_Assumptions` 테스트 더블이 손으로 준
숫자다 — `docs/assumptions.yaml` 이 관리하는 실제 2026년 단가와는 무관하다
(도메인 데이터를 로더 픽스처에 지어 넣지 않는다).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from core.contracts.assumptions import (
    AssumptionProvider,
    AssumptionValue,
    PriceBasis,
)
from core.contracts.units import Money
from core.regulation.tariff import TariffEngine
from core.regulation.tariff_loader import (
    TariffLoaderError,
    load_tariff_catalog,
    load_tariff_catalog_from_text,
)


def _value(key: str, value: float | int) -> AssumptionValue:
    return AssumptionValue(
        key=key,
        value=value,
        value_unit="테스트",
        base_year="2026",
        applicable_scope="WP-26E 로더 테스트",
        derivation_method="테스트 케이스 손계산",
        source="tests/regulation/test_tariff_loader.py",
        verified_at=date(2026, 8, 10),
        confidence="확정",
        set_name="loader-test",
        set_version="1",
    )


class _Assumptions(AssumptionProvider):
    def __init__(self, items: Mapping[str, float | int]) -> None:
        self._items = dict(items)

    @property
    def set_name(self) -> str:
        return "loader-test"

    @property
    def set_version(self) -> str:
        return "1"

    @property
    def price_basis(self) -> PriceBasis:
        """DV-7 — 스텁도 기준을 **선언해야** 한다. 그것이 강제의 실질이다."""
        return PriceBasis.NOMINAL

    def get(self, key: str) -> AssumptionValue | None:
        if key not in self._items:
            return None
        return _value(key, self._items[key])


# ── AC4 본체 — YAML 이 TariffCatalog 를 만든다 ──────────────────────────

_MINIMAL_YAML = """
residential:
  - name: single
    valid_from: 2026-01-01
    valid_to: null
    blocks:
      - upper_kwh: null
        energy_rate_key: loader.energy
        basic_charge_key: loader.basic
tou: []
direct_trade: []
"""


@pytest.mark.req("FR-501-AC4")
def test_load_tariff_catalog_from_yaml_builds_working_table() -> None:
    """YAML 을 주면 실제로 계산 가능한 `TariffCatalog` 가 만들어진다 (AC4 본체).

    기대값 손계산: 10kWh * 100원/kWh + 기본요금 500원 = 1,500원.
    """
    catalog = load_tariff_catalog_from_text(_MINIMAL_YAML, source="<test>")
    engine = TariffEngine(
        assumptions=_Assumptions({"loader.energy": 100, "loader.basic": 500}),
        catalog=catalog,
    )
    bill = engine.bill_residential(10.0, when=date(2026, 6, 1))
    assert bill.amount("basic") == Money(500)
    assert bill.amount("energy") == Money(1_000)
    assert bill.total == Money(1_500)


# ── AC4 의 핵심 — 같은 코드에 다른 YAML 을 주면 결과가 달라진다 ──────────

_YAML_A = """
residential:
  - name: a
    valid_from: 2026-01-01
    valid_to: null
    blocks:
      - upper_kwh: null
        energy_rate_key: loader.energy
        basic_charge_key: loader.basic
tou: []
direct_trade: []
"""

_YAML_B = """
residential:
  - name: b
    valid_from: 2026-01-01
    valid_to: null
    blocks:
      - upper_kwh: 100
        energy_rate_key: loader.energy.low
        basic_charge_key: loader.basic
      - upper_kwh: null
        energy_rate_key: loader.energy.high
        basic_charge_key: loader.basic
tou: []
direct_trade: []
"""

#: 두 YAML 이 공유하는 `AssumptionProvider` 값 — **바뀌지 않는다.** 바뀌는 것은
#: YAML 의 구간 구조(단일 구간 vs 100kWh 경계로 나뉜 2구간)뿐이다.
_SHARED_ASSUMPTIONS = {
    "loader.energy": 150,
    "loader.energy.low": 50,
    "loader.energy.high": 150,
    "loader.basic": 0,
}


@pytest.mark.req("FR-501-AC4")
def test_changing_only_the_yaml_structure_changes_the_bill() -> None:
    """전제값도, 파이썬 코드도 그대로 두고 **YAML 의 구간 구조만** 바꾼다.

    `_YAML_A` 는 200kWh 전량을 구간 하나(고율 150원)로 계산하고, `_YAML_B` 는
    같은 200kWh 를 100kWh 저율(50원)/100kWh 고율(150원) 두 구간으로 나눈다.
    두 경우 모두 같은 `TariffEngine`·같은 `_Assumptions` 값을 쓰며, 함수 호출도
    동일하다 — 다른 것은 로더에 넘긴 YAML 문자열 하나뿐이다.

    기대값 손계산:
    - A: 200kWh * 150원(고율 단일구간) = 30,000원
    - B: 100kWh*50원 + 100kWh*150원 = 5,000 + 15,000 = 20,000원

    A 와 B 가 같은 전제값으로 다른 결과(30,000 vs 20,000)를 내야 한다 —
    그렇지 않으면 구간 경계가 YAML 이 아니라 코드에 박혀 있다는 뜻이다.
    """
    when = date(2026, 6, 1)
    assumptions = _Assumptions(_SHARED_ASSUMPTIONS)

    catalog_a = load_tariff_catalog_from_text(_YAML_A, source="<a>")
    bill_a = TariffEngine(assumptions=assumptions, catalog=catalog_a).bill_residential(
        200.0, when=when
    )
    assert bill_a.amount("energy") == Money(30_000)

    catalog_b = load_tariff_catalog_from_text(_YAML_B, source="<b>")
    bill_b = TariffEngine(assumptions=assumptions, catalog=catalog_b).bill_residential(
        200.0, when=when
    )
    assert bill_b.amount("energy") == Money(20_000)

    assert bill_a.amount("energy") != bill_b.amount("energy"), (
        "구간 구조가 다른 두 YAML 이 같은 결과를 냈다 — 구간 경계가 YAML이 "
        "아니라 코드에 있다는 뜻이다 (FR-501-AC4 위반: 개정 시 코드 변경이 "
        "필요해진다)"
    )


# ── 필수 키 누락 — 명확한 오류로 중단 ────────────────────────────────────

def test_missing_required_key_in_block_raises_clear_error() -> None:
    """블록에 `energy_rate_key` 가 없으면 조용한 기본값 대신 즉시 멈춘다.

    조용히 넘어가면 요율 키가 빈 채로 결제 로직에 들어가 0원 요금이 되고,
    그 0원은 화면상 정상으로 보인다 — 그래서 로더 단계에서 막는다.
    """
    bad_yaml = """
residential:
  - name: bad
    valid_from: 2026-01-01
    valid_to: null
    blocks:
      - upper_kwh: null
        basic_charge_key: loader.basic
tou: []
direct_trade: []
"""
    with pytest.raises(TariffLoaderError, match="energy_rate_key"):
        load_tariff_catalog_from_text(bad_yaml, source="<bad>")


def test_missing_top_level_key_raises_clear_error() -> None:
    """`direct_trade` 최상위 키 자체가 없으면 "빈 목록"이 아니라 오류다."""
    bad_yaml = """
residential: []
tou: []
"""
    with pytest.raises(TariffLoaderError, match="direct_trade"):
        load_tariff_catalog_from_text(bad_yaml, source="<bad>")


# ── 날짜 형식 오류 — 명확한 오류로 중단 ──────────────────────────────────

def test_invalid_date_format_raises_clear_error() -> None:
    """`valid_from` 이 ISO 형식(YYYY-MM-DD)이 아니면 즉시 멈춘다."""
    bad_yaml = """
residential:
  - name: bad-date
    valid_from: "2026/01/01"
    valid_to: null
    blocks:
      - upper_kwh: null
        energy_rate_key: loader.energy
        basic_charge_key: loader.basic
tou: []
direct_trade: []
"""
    with pytest.raises(TariffLoaderError, match="valid_from"):
        load_tariff_catalog_from_text(bad_yaml, source="<bad>")


# ── 유효기간 중첩 — 명확한 오류로 중단 ───────────────────────────────────

def test_overlapping_valid_periods_raises_clear_error() -> None:
    """같은 종류의 두 표가 겹치는 유효기간을 가지면 어느 표를 쓸지 판정할 수 없다."""
    bad_yaml = """
residential:
  - name: first
    valid_from: 2026-01-01
    valid_to: 2026-06-30
    blocks:
      - upper_kwh: null
        energy_rate_key: loader.energy
        basic_charge_key: loader.basic
  - name: second
    valid_from: 2026-06-01
    valid_to: null
    blocks:
      - upper_kwh: null
        energy_rate_key: loader.energy
        basic_charge_key: loader.basic
tou: []
direct_trade: []
"""
    with pytest.raises(TariffLoaderError, match="겹칩니다"):
        load_tariff_catalog_from_text(bad_yaml, source="<bad>")


def test_missing_file_raises_clear_error(tmp_path: Path) -> None:
    """존재하지 않는 경로를 주면 즉시, 분명하게 멈춘다."""
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(TariffLoaderError, match="없습니다"):
        load_tariff_catalog(missing)
