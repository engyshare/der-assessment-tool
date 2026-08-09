from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from enum import StrEnum

from core.contracts.der import DER, MEDIA, DispatchContext, DispatchResult
from core.contracts.engine import DispatchEngine, SystemDispatch
from core.contracts.units import ENERGY_TOLERANCE_KWH


class DispatchRule(StrEnum):
    PV_SELF_CONSUMPTION = "pv_self_consumption"
    ESS_CHARGE = "ess_charge"
    V2G_CHARGE = "v2g_charge"
    GRID_EXPORT = "grid_export"
    ESS_DISCHARGE = "ess_discharge"
    V2G_DISCHARGE = "v2g_discharge"
    GRID_IMPORT = "grid_import"


DEFAULT_RULE_ORDER: tuple[DispatchRule, ...] = (
    DispatchRule.PV_SELF_CONSUMPTION,
    DispatchRule.ESS_CHARGE,
    DispatchRule.V2G_CHARGE,
    DispatchRule.GRID_EXPORT,
    DispatchRule.ESS_DISCHARGE,
    DispatchRule.V2G_DISCHARGE,
    DispatchRule.GRID_IMPORT,
)

PriceSignalProvider = Callable[[DispatchContext], Sequence[float]]

_PRICE_MODE_TOKENS: tuple[str, ...] = (
    "tou",
    "price",
    "tariff",
    "arbitrage",
    "요금",
    "가격",
)


class RuleBasedEngine(DispatchEngine):
    """Phase 1 rule-based dispatch engine.

    DER implementations own their physical schedules. The engine owns the common
    context, shared price signal, deterministic execution order, grid balancing,
    and cross-resource media balance checks.
    """

    def __init__(
        self,
        *,
        rule_order: Sequence[DispatchRule | str] = DEFAULT_RULE_ORDER,
        price_signal_provider: PriceSignalProvider | None = None,
    ) -> None:
        self.rule_order = self._normalize_rule_order(rule_order)
        self.price_signal_provider = price_signal_provider

    def run(self, resources: list[DER], ctx: DispatchContext) -> SystemDispatch:
        prepared_ctx = self._prepare_context(resources, ctx)
        ordered = self._ordered_resources(resources)
        per_resource: dict[str, DispatchResult] = {}

        for resource in ordered:
            if resource.name in per_resource:
                raise ValueError(
                    f"duplicate resource name {resource.name!r}; per-resource dispatch "
                    "rows would overwrite each other"
                )
            result = resource.dispatch(prepared_ctx)
            self._validate_result(resource, result, prepared_ctx)
            per_resource[resource.name] = result

        grid_import, grid_export = self._grid_exchange(per_resource, prepared_ctx.steps)
        dispatch = SystemDispatch(
            per_resource=per_resource,
            grid_import=grid_import,
            grid_export=grid_export,
        )
        DispatchEngine.verify_balance(dispatch)
        self.verify_media_balance(dispatch)
        return dispatch

    @staticmethod
    def verify_media_balance(dispatch: SystemDispatch) -> None:
        for media, _flag in MEDIA:
            if media == "electric":
                continue
            errors = media_balance_error(dispatch, media)
            bad = [
                (i, error)
                for i, error in enumerate(errors)
                if abs(error) >= ENERGY_TOLERANCE_KWH
            ]
            if bad:
                head = ", ".join(f"step {i}: {error:+.3e} kWh" for i, error in bad[:5])
                raise ValueError(
                    f"{media} media balance violation {len(bad)}/{len(errors)} steps "
                    f"(tolerance {ENERGY_TOLERANCE_KWH:g} kWh): {head}"
                )

    @staticmethod
    def _normalize_rule_order(
        rule_order: Sequence[DispatchRule | str],
    ) -> tuple[DispatchRule, ...]:
        rules = tuple(DispatchRule(rule) for rule in rule_order)
        required = set(DEFAULT_RULE_ORDER)
        if set(rules) != required or len(rules) != len(required):
            raise ValueError(
                "rule_order must contain each Phase 1 dispatch rule exactly once"
            )
        return rules

    def _prepare_context(
        self, resources: Sequence[DER], ctx: DispatchContext
    ) -> DispatchContext:
        prepared = ctx
        if prepared.price_signal_won_per_kwh is None and self.price_signal_provider:
            series = [float(value) for value in self.price_signal_provider(prepared)]
            prepared.check_series(series, name="price_signal_won_per_kwh")
            prepared = replace(prepared, price_signal_won_per_kwh=series)

        if any(_needs_price_signal(resource) for resource in resources):
            if prepared.price_signal_won_per_kwh is None:
                raise ValueError(
                    "price signal is required for price-linked dispatch; "
                    "the engine must receive a price_signal_provider or a context "
                    "with price_signal_won_per_kwh"
                )
            prepared.require_price_signal()
        return prepared

    def _ordered_resources(self, resources: Sequence[DER]) -> list[DER]:
        rank = {rule: index for index, rule in enumerate(self.rule_order)}
        return [
            resource
            for _key, resource in sorted(
                (
                    (rank[_rule_for(resource)], index, resource.name),
                    resource,
                )
                for index, resource in enumerate(resources)
            )
        ]

    @staticmethod
    def _grid_exchange(
        per_resource: dict[str, DispatchResult], steps: int
    ) -> tuple[list[float], list[float]]:
        imports: list[float] = []
        exports: list[float] = []
        for step in range(steps):
            net = math.fsum(result.electric[step] for result in per_resource.values())
            imports.append(max(-net, 0.0))
            exports.append(max(net, 0.0))
        return imports, exports

    @staticmethod
    def _validate_result(
        resource: DER, result: DispatchResult, ctx: DispatchContext
    ) -> None:
        for media, flag in MEDIA:
            series = getattr(result, media)
            ctx.check_series(series, name=f"{resource.name}.{media}")
            unmet = result.unmet(media)
            ctx.check_series(unmet, name=f"{resource.name}.unmet_{media}")

            carries = bool(getattr(resource, flag))
            if not carries and _has_energy(series):
                raise ValueError(
                    f"{resource.name}: {media} series has energy but {flag} is false"
                )
            if not carries and _has_energy(unmet):
                raise ValueError(
                    f"{resource.name}: unmet_{media} has energy but {flag} is false"
                )


def media_balance_error(dispatch: SystemDispatch, media: str) -> list[float]:
    if media == "electric":
        return dispatch.electric_balance_error()
    _check_media(media)
    steps = len(dispatch.grid_import)
    return [
        math.fsum(
            getattr(result, media)[step] + result.unmet(media)[step]
            for result in dispatch.per_resource.values()
        )
        for step in range(steps)
    ]


def dispatch_digest(dispatch: SystemDispatch) -> str:
    """SHA-256 over raw step series, not rounded summaries."""
    payload = {
        "grid_import": _float_series(dispatch.grid_import),
        "grid_export": _float_series(dispatch.grid_export),
        "resources": [
            {
                "name": name,
                "electric": _float_series(result.electric),
                "heat": _float_series(result.heat),
                "cool": _float_series(result.cool),
                "fuel": _float_series(result.fuel),
                "unmet_electric": _float_series(result.unmet("electric")),
                "unmet_heat": _float_series(result.unmet("heat")),
                "unmet_cool": _float_series(result.unmet("cool")),
                "unmet_fuel": _float_series(result.unmet("fuel")),
            }
            for name, result in sorted(dispatch.per_resource.items())
        ],
    }
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rule_for(resource: DER) -> DispatchRule:
    tag = str(getattr(resource, "tag", "")).casefold()
    if tag == "pv":
        return DispatchRule.PV_SELF_CONSUMPTION
    if tag == "ess":
        return DispatchRule.ESS_CHARGE
    if tag == "ev_v2g":
        return DispatchRule.V2G_CHARGE
    return DispatchRule.GRID_IMPORT


def _needs_price_signal(resource: DER) -> bool:
    mode = str(getattr(resource, "operating_mode", "")).casefold()
    return any(token.casefold() in mode for token in _PRICE_MODE_TOKENS)


def _has_energy(series: Sequence[float]) -> bool:
    return any(abs(value) >= ENERGY_TOLERANCE_KWH for value in series)


def _check_media(media: str) -> None:
    if media not in {name for name, _flag in MEDIA}:
        raise ValueError(f"unknown media {media!r}")


def _float_series(series: Sequence[float]) -> list[float]:
    return [float(value) for value in series]
