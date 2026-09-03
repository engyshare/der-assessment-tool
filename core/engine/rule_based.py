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
            # ⚠ **`max(-net, 0.0)` 을 쓰지 않는다 — 음의 0 이 새어 나간다** (R37).
            # `net` 이 정확히 `+0.0` 인 스텝에서 `-net` 은 `-0.0` 이고, 파이썬의
            # `max` 는 둘이 같을 때 **앞의 것**을 돌려주므로 `-0.0` 이 남는다.
            # 수치로는 0 과 같아 어떤 검사도 걸리지 않지만 **붙임 7 이
            # 「-0.00」 을 인쇄한다** — 검토자는 계통 수전에 붙은 음수 부호를
            # 읽는다. R37 이 일사 곡선을 배선해 야간 발전이 0 이 되자 net 이
            # 정확히 0 인 스텝이 처음 생겨 드러났다.
            imports.append(-net if net < 0.0 else 0.0)
            exports.append(net if net > 0.0 else 0.0)
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
    """자원이 **선언한** 규칙(`DER.DISPATCH_RULE`)을 엔진 어휘로 되돌린다.

    ⚠⚠ **여기에 자원 태그를 리터럴로 적지 마라** (`FR-101-AC3`). R59 전까지 이
    함수는 `PV`·`ESS`·`EV_V2G` 셋을 리터럴로 알고 순위를 배정했다 — 그러면
    일곱째 자원이 고유한 규칙을 필요로 하는 순간 **엔진의 그 목록을 고쳐야**
    하고 「인터페이스만 구현하면 코어 엔진 수정 없이 동작」이 깨진다. 방향을
    뒤집었다: **엔진이 자원에게 묻는다.**
    `tests/engine/test_rule_based.py::
    test_engine_source_names_no_resource_tag_beyond_the_declared_three` 가
    엔진 소스에 자원 태그 문면이 **한 건도** 없음을 대조한다.

    선언하지 않은 자원과 어휘 밖 문자열은 **기본 갈래**로 떨어진다. 예외를
    던지지 않는 이유는 `DER.DISPATCH_RULE` 독스트링에 있다 — 오타 하나로 새
    자원이 아예 돌지 못하면 조항이 요구하는 「동작」이 사라진다.
    """
    declared = str(resource.DISPATCH_RULE)
    try:
        return DispatchRule(declared)
    except ValueError:
        return DispatchRule.GRID_IMPORT


def _needs_price_signal(resource: DER) -> bool:
    mode = str(getattr(resource, "operating_mode", "")).casefold()
    return any(token.casefold() in mode for token in _PRICE_MODE_TOKENS)


def rule_for(resource: DER) -> DispatchRule:
    """`_rule_for` 의 공개 접근자. 동작은 그대로다 — 형제 구획(`core.report`
    등)이 사설 함수에 묶이면 엔진 내부 구현을 못 바꾼다."""
    return _rule_for(resource)


def needs_price_signal(resource: DER) -> bool:
    """`_needs_price_signal` 의 공개 접근자. 동작은 그대로다."""
    return _needs_price_signal(resource)


def _has_energy(series: Sequence[float]) -> bool:
    return any(abs(value) >= ENERGY_TOLERANCE_KWH for value in series)


def _check_media(media: str) -> None:
    if media not in {name for name, _flag in MEDIA}:
        raise ValueError(f"unknown media {media!r}")


def _float_series(series: Sequence[float]) -> list[float]:
    return [float(value) for value in series]
