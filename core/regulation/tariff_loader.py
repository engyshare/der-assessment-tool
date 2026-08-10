"""요금표 YAML 로더 — `core/regulation/tariff.py` 의 구조를 데이터 파일에서 만든다.

spec **FR-501-AC4**: 요금표는 코드가 아닌 데이터 파일(YAML/DB)로 관리하며, 개정 시
코드 변경이 불필요해야 한다. `tariff.py` 는 이미 표 구조·유효기간 선택 로직을 갖고
있었지만, 그 구조를 **만드는 곳**이 코드(테스트가 직접 dataclass를 구성)뿐이었다 —
그래서 AC4 는 검증되지 않은 채 남아 있었다. 이 모듈은 그 한 층(YAML → 구조체)만
추가한다.

**실제 요금 단가는 여기 없다.** 이 모듈은 각 항목이 가리키는 `AssumptionProvider`
키(문자열)만 YAML에서 읽는다 — 그 키가 가리키는 실제 값(요율·기본요금 등)은
`docs/assumptions.yaml` 이 관리한다(`tariff.*`). 값을 이 모듈이나 그 픽스처에 지어
넣으면 도메인 데이터 발명이자 NFR-202 위반이 로더 계층으로 옮겨질 뿐이다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.regulation.tariff import (
    DirectTradeTariffTable,
    ResidentialBlock,
    ResidentialTariffTable,
    TariffCatalog,
    TaxAndFundScheme,
    TouDiscountRule,
    TouPeriod,
    TouTariffTable,
)

#: 최상위에 있어야 하는 표 종류 — 값이 빈 목록이어도 되지만, 키 자체가 없으면
#: "작성자가 이 종류를 잊었다"와 "이 시나리오에 이 종류가 없다"를 구별할 수
#: 없으므로 명확한 오류로 막는다.
_TOP_LEVEL_KEYS = ("residential", "tou", "direct_trade")


class TariffLoaderError(ValueError):
    """요금표 YAML 형식 오류 — 조용한 기본값 대신 위치를 담아 즉시 중단시킨다."""


def load_tariff_catalog(path: str | Path) -> TariffCatalog:
    """운영 요금표 YAML 파일에서 `TariffCatalog` 를 만든다."""
    resolved = Path(path)
    if not resolved.is_file():
        raise TariffLoaderError(f"요금표 파일이 없습니다: {resolved}")
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise TariffLoaderError(f"요금표 파일을 읽을 수 없습니다: {resolved} ({exc})") from exc
    return load_tariff_catalog_from_text(text, source=str(resolved))


def load_tariff_catalog_from_text(text: str, *, source: str = "<yaml>") -> TariffCatalog:
    """YAML 문자열에서 `TariffCatalog` 를 만든다 — 테스트가 파일 없이 쓰는 진입점."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TariffLoaderError(f"{source}: YAML 파싱 실패 — {exc}") from exc
    if not isinstance(doc, dict):
        raise TariffLoaderError(f"{source}: 최상위는 매핑(dict)이어야 합니다")
    return _build_catalog(doc, source=source)


def _build_catalog(doc: dict[str, Any], *, source: str) -> TariffCatalog:
    for key in _TOP_LEVEL_KEYS:
        if key not in doc:
            raise TariffLoaderError(f"{source}: 최상위 키 `{key}` 가 없습니다")

    residential = tuple(
        _build_residential(item, where=f"{source}: residential[{i}]")
        for i, item in enumerate(_as_list(doc["residential"], where=f"{source}: residential"))
    )
    tou = tuple(
        _build_tou(item, where=f"{source}: tou[{i}]")
        for i, item in enumerate(_as_list(doc["tou"], where=f"{source}: tou"))
    )
    direct_trade = tuple(
        _build_direct_trade(item, where=f"{source}: direct_trade[{i}]")
        for i, item in enumerate(_as_list(doc["direct_trade"], where=f"{source}: direct_trade"))
    )

    _check_no_overlap(residential, kind="residential", source=source)
    _check_no_overlap(tou, kind="tou", source=source)
    _check_no_overlap(direct_trade, kind="direct_trade", source=source)

    return TariffCatalog(residential=residential, tou=tou, direct_trade=direct_trade)


def _as_list(value: Any, *, where: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TariffLoaderError(f"{where}: 목록(list)이어야 합니다 (실제 {type(value).__name__})")
    return value


def _require(entry: dict[str, Any], key: str, *, where: str) -> Any:
    if key not in entry:
        raise TariffLoaderError(f"{where}: 필수 키 `{key}` 가 없습니다")
    return entry[key]


def _parse_date(value: Any, *, where: str, key: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise TariffLoaderError(
                f"{where}: `{key}` 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD): {value!r}"
            ) from exc
    raise TariffLoaderError(
        f"{where}: `{key}` 는 날짜여야 합니다 (실제 {type(value).__name__})"
    )


def _build_tax_and_fund(raw: Any, *, where: str) -> TaxAndFundScheme | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TariffLoaderError(f"{where}.tax_and_fund: 매핑(dict)이어야 합니다")
    inner = f"{where}.tax_and_fund"
    return TaxAndFundScheme(
        vat_rate_key=_require(raw, "vat_rate_key", where=inner),
        power_fund_rate_key=_require(raw, "power_fund_rate_key", where=inner),
    )


def _build_residential(entry: dict[str, Any], *, where: str) -> ResidentialTariffTable:
    name = _require(entry, "name", where=where)
    valid_from = _parse_date(
        _require(entry, "valid_from", where=where), where=where, key="valid_from"
    )
    valid_to = _parse_date(_require(entry, "valid_to", where=where), where=where, key="valid_to")

    blocks_raw = _as_list(_require(entry, "blocks", where=where), where=f"{where}.blocks")
    if not blocks_raw:
        raise TariffLoaderError(f"{where}.blocks: 비어 있지 않은 목록이어야 합니다")
    blocks = tuple(
        ResidentialBlock(
            upper_kwh=block.get("upper_kwh"),
            energy_rate_key=_require(block, "energy_rate_key", where=f"{where}.blocks[{i}]"),
            basic_charge_key=_require(block, "basic_charge_key", where=f"{where}.blocks[{i}]"),
        )
        for i, block in enumerate(blocks_raw)
    )

    return ResidentialTariffTable(
        name=name,
        valid_from=valid_from,
        valid_to=valid_to,
        blocks=blocks,
        climate_rate_key=entry.get("climate_rate_key"),
        fuel_adjustment_rate_key=entry.get("fuel_adjustment_rate_key"),
        essential_discount_key=entry.get("essential_discount_key"),
        essential_discount_max_kwh=entry.get("essential_discount_max_kwh"),
        tax_and_fund=_build_tax_and_fund(entry.get("tax_and_fund"), where=where),
    )


def _build_tou(entry: dict[str, Any], *, where: str) -> TouTariffTable:
    name = _require(entry, "name", where=where)
    valid_from = _parse_date(
        _require(entry, "valid_from", where=where), where=where, key="valid_from"
    )
    valid_to = _parse_date(_require(entry, "valid_to", where=where), where=where, key="valid_to")

    periods_raw = _as_list(_require(entry, "periods", where=where), where=f"{where}.periods")
    if not periods_raw:
        raise TariffLoaderError(f"{where}.periods: 비어 있지 않은 목록이어야 합니다")
    periods = tuple(
        TouPeriod(
            key=_require(p, "key", where=f"{where}.periods[{i}]"),
            months=tuple(_require(p, "months", where=f"{where}.periods[{i}]")),
            weekdays=tuple(_require(p, "weekdays", where=f"{where}.periods[{i}]")),
            start_hour=_require(p, "start_hour", where=f"{where}.periods[{i}]"),
            end_hour=_require(p, "end_hour", where=f"{where}.periods[{i}]"),
            energy_rate_key=_require(p, "energy_rate_key", where=f"{where}.periods[{i}]"),
        )
        for i, p in enumerate(periods_raw)
    )

    discounts_raw = _as_list(entry.get("discounts"), where=f"{where}.discounts")
    discounts = tuple(
        TouDiscountRule(
            key=_require(d, "key", where=f"{where}.discounts[{i}]"),
            months=tuple(_require(d, "months", where=f"{where}.discounts[{i}]")),
            weekdays=tuple(_require(d, "weekdays", where=f"{where}.discounts[{i}]")),
            discount_rate_key=_require(d, "discount_rate_key", where=f"{where}.discounts[{i}]"),
            period_keys=tuple(d.get("period_keys") or ()),
        )
        for i, d in enumerate(discounts_raw)
    )

    return TouTariffTable(
        name=name,
        valid_from=valid_from,
        valid_to=valid_to,
        periods=periods,
        discounts=discounts,
        tax_and_fund=_build_tax_and_fund(entry.get("tax_and_fund"), where=where),
    )


def _build_direct_trade(entry: dict[str, Any], *, where: str) -> DirectTradeTariffTable:
    name = _require(entry, "name", where=where)
    valid_from = _parse_date(
        _require(entry, "valid_from", where=where), where=where, key="valid_from"
    )
    valid_to = _parse_date(_require(entry, "valid_to", where=where), where=where, key="valid_to")

    return DirectTradeTariffTable(
        name=name,
        valid_from=valid_from,
        valid_to=valid_to,
        energy_rate_key=_require(entry, "energy_rate_key", where=where),
        support_fee_key=_require(entry, "support_fee_key", where=where),
        tax_and_fund=_build_tax_and_fund(entry.get("tax_and_fund"), where=where),
    )


def _check_no_overlap(tables: tuple[Any, ...], *, kind: str, source: str) -> None:
    for i in range(len(tables)):
        for j in range(i + 1, len(tables)):
            a, b = tables[i], tables[j]
            if _periods_overlap(a.valid_from, a.valid_to, b.valid_from, b.valid_to):
                raise TariffLoaderError(
                    f"{source}: {kind} 표 `{a.name}` 와 `{b.name}` 의 유효기간이 "
                    "겹칩니다 — 어느 표를 쓸지 판정할 수 없습니다"
                )


def _periods_overlap(
    a_from: date | None, a_to: date | None, b_from: date | None, b_to: date | None
) -> bool:
    starts_before_b_ends = a_from is None or b_to is None or a_from <= b_to
    ends_after_b_starts = a_to is None or b_from is None or a_to >= b_from
    return starts_before_b_ends and ends_after_b_starts
