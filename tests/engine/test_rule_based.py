from __future__ import annotations

import random
from dataclasses import dataclass, field

import pytest

from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.engine import DispatchEngine, SystemDispatch
from core.contracts.units import SECONDS_PER_HOUR, Money
from core.engine import DispatchRule, RuleBasedEngine, dispatch_digest, media_balance_error


def ctx(steps: int = 4) -> DispatchContext:
    return DispatchContext(steps=steps, dt=SECONDS_PER_HOUR, year=1)


@dataclass
class StubResource:
    name: str
    electric: list[float]
    tag: str = "Stub"
    heat: list[float] | None = None
    cool: list[float] | None = None
    fuel: list[float] | None = None
    unmet_heat: list[float] | None = None
    carries_electric: bool = True
    carries_heat: bool = False
    carries_cool: bool = False
    consumes_fuel: bool = False
    operating_mode: str = ""
    seen_context_ids: list[int] = field(default_factory=list)
    seen_prices: tuple[float, ...] = ()
    price_required: bool = False

    def dispatch(self, context: DispatchContext) -> DispatchResult:
        self.seen_context_ids.append(id(context))
        if self.price_required:
            self.seen_prices = tuple(context.require_price_signal())
        zeros = [0.0] * context.steps
        return DispatchResult(
            electric=list(self.electric),
            heat=list(self.heat if self.heat is not None else zeros),
            cool=list(self.cool if self.cool is not None else zeros),
            fuel=list(self.fuel if self.fuel is not None else zeros),
            unmet_heat=self.unmet_heat,
        )

    def capex(self, *, year: int) -> Money:
        return Money(0)

    def capex_vat(self, *, year: int) -> Money:
        return Money(0)

    def fixed_om(self, *, year: int) -> Money:
        return Money(0)

    def variable_om(self, *, year: int) -> Money:
        return Money(0)

    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        return {}

    def salvage_value(self, *, year: int) -> Money:
        return Money(0)


class PriceLinkedStorage(StubResource):
    def dispatch(self, context: DispatchContext) -> DispatchResult:
        prices = tuple(context.require_price_signal())
        self.seen_context_ids.append(id(context))
        self.seen_prices = prices
        electric = [0.0] * context.steps
        low = min(range(context.steps), key=lambda i: (prices[i], i))
        high = max(range(context.steps), key=lambda i: (prices[i], -i))
        electric[low] = -1.0
        electric[high] = 1.0
        zeros = [0.0] * context.steps
        return DispatchResult(electric=electric, heat=zeros, cool=list(zeros), fuel=list(zeros))


@pytest.mark.req("FR-301-AC1")
@pytest.mark.req("FR-301-AC3")
def test_engine_passes_one_shared_context_to_every_resource() -> None:
    context = ctx(steps=3)
    resources = [
        StubResource("load", [-2.0, -1.0, 0.0], tag="Load"),
        StubResource("pv", [1.0, 3.0, 0.0], tag="PV"),
    ]

    dispatch = RuleBasedEngine().run(resources, context)

    assert dispatch.per_resource["pv"].electric == [1.0, 3.0, 0.0]
    assert dispatch.per_resource["load"].electric == [-2.0, -1.0, 0.0]
    assert dispatch.grid_import == [1.0, 0.0, 0.0]
    assert dispatch.grid_export == [0.0, 2.0, 0.0]
    assert {tuple(r.seen_context_ids) for r in resources} == {(id(context),)}


@pytest.mark.req("NFR-102-M1")
@pytest.mark.req("FR-301-AC2")
def test_electric_balance_holds_for_generated_step_series() -> None:
    rng = random.Random(301)
    engine = RuleBasedEngine()

    for _case in range(40):
        steps = 12
        load = [-rng.uniform(0.0, 8.0) for _ in range(steps)]
        pv = [rng.uniform(0.0, 8.0) for _ in range(steps)]
        storage = [rng.uniform(-2.0, 2.0) for _ in range(steps)]

        dispatch = engine.run(
            [
                StubResource("load", load, tag="Load"),
                StubResource("pv", pv, tag="PV"),
                StubResource("storage", storage, tag="ESS"),
            ],
            ctx(steps=steps),
        )

        assert max(abs(error) for error in dispatch.electric_balance_error()) < 1e-6


@pytest.mark.req("FR-101-AC4")
def test_heat_balance_is_checked_separately_from_electric_balance() -> None:
    engine = RuleBasedEngine()
    context = ctx(steps=2)

    engine.run(
        [
            StubResource("pv", [1.0, 1.0], tag="PV"),
            StubResource("load", [-1.0, -1.0], tag="Load"),
            StubResource("heat-source", [0.0, 0.0], heat=[2.0, 2.0], carries_heat=True),
            StubResource("heat-load", [0.0, 0.0], heat=[-2.0, -2.0], carries_heat=True),
        ],
        context,
    )

    bad_heat = {
        "pv": DispatchResult.zeros(2),
        "load": DispatchResult.zeros(2),
        "heat-source": DispatchResult(
            electric=[0.0, 0.0],
            heat=[1.0, 1.0],
            cool=[0.0, 0.0],
            fuel=[0.0, 0.0],
        ),
        "heat-load": DispatchResult(
            electric=[0.0, 0.0],
            heat=[-2.0, -2.0],
            cool=[0.0, 0.0],
            fuel=[0.0, 0.0],
        ),
    }
    electric_only_dispatch = SystemDispatch(
        per_resource=bad_heat,
        grid_import=[0.0, 0.0],
        grid_export=[0.0, 0.0],
    )
    DispatchEngine.verify_balance(electric_only_dispatch)
    assert media_balance_error(electric_only_dispatch, "heat") == [-1.0, -1.0]

    with pytest.raises(ValueError, match="heat"):
        RuleBasedEngine.verify_media_balance(electric_only_dispatch)


@pytest.mark.req("FR-302-AC2")
def test_price_signal_is_injected_and_missing_signal_is_not_zero_filled() -> None:
    prices = [80.0, 120.0, 240.0]
    tou = PriceLinkedStorage(
        "tou-ess",
        [0.0, 0.0, 0.0],
        tag="ESS",
        operating_mode="TOU arbitrage",
    )

    dispatch = RuleBasedEngine(price_signal_provider=lambda context: prices).run(
        [tou],
        ctx(steps=3),
    )

    assert tou.seen_prices == tuple(prices)
    assert dispatch.per_resource["tou-ess"].electric == [-1.0, 0.0, 1.0]

    with pytest.raises(ValueError, match="price signal"):
        RuleBasedEngine().run(
            [
                StubResource(
                    "tou-ess",
                    [0.0, 0.0, 0.0],
                    tag="ESS",
                    operating_mode="TOU arbitrage",
                    price_required=True,
                )
            ],
            ctx(steps=3),
        )


@pytest.mark.req("FR-301-AC3")
def test_injected_price_signal_must_have_the_context_step_count() -> None:
    with pytest.raises(ValueError, match="price_signal_won_per_kwh"):
        RuleBasedEngine(price_signal_provider=lambda context: [100.0]).run(
            [StubResource("tou-ess", [0.0, 0.0], tag="ESS", operating_mode="TOU")],
            ctx(steps=2),
        )


@pytest.mark.req("NFR-101-M1")
def test_dispatch_digest_is_deterministic_and_uses_raw_step_series() -> None:
    engine = RuleBasedEngine()
    resources = [
        StubResource("pv", [0.1, 0.2, 0.3], tag="PV"),
        StubResource("load", [-0.1, -0.2, -0.3], tag="Load"),
    ]

    digests = [dispatch_digest(engine.run(resources, ctx(steps=3))) for _ in range(10)]

    assert len(set(digests)) == 1

    front_loaded = engine.run(
        [
            StubResource("pv", [1.0, 0.0], tag="PV"),
            StubResource("load", [-1.0, 0.0], tag="Load"),
        ],
        ctx(steps=2),
    )
    flat = engine.run(
        [
            StubResource("pv", [0.5, 0.5], tag="PV"),
            StubResource("load", [-0.5, -0.5], tag="Load"),
        ],
        ctx(steps=2),
    )

    assert sum(front_loaded.per_resource["pv"].electric) == sum(flat.per_resource["pv"].electric)
    assert dispatch_digest(front_loaded) != dispatch_digest(flat)


@pytest.mark.req("FR-302-AC1")
@pytest.mark.req("FR-302-AC3")
def test_rule_order_is_configurable_and_reflected_in_dispatch_order() -> None:
    resources = [
        StubResource("load", [-1.0], tag="Load"),
        StubResource("ev", [0.0], tag="EV_V2G"),
        StubResource("ess", [0.0], tag="ESS"),
        StubResource("pv", [1.0], tag="PV"),
    ]

    default_dispatch = RuleBasedEngine().run(resources, ctx(steps=1))
    custom_dispatch = RuleBasedEngine(
        rule_order=(
            DispatchRule.GRID_IMPORT,
            DispatchRule.PV_SELF_CONSUMPTION,
            DispatchRule.ESS_CHARGE,
            DispatchRule.V2G_CHARGE,
            DispatchRule.GRID_EXPORT,
            DispatchRule.ESS_DISCHARGE,
            DispatchRule.V2G_DISCHARGE,
        )
    ).run(resources, ctx(steps=1))

    assert list(default_dispatch.per_resource) == ["pv", "ess", "ev", "load"]
    assert list(custom_dispatch.per_resource) == ["load", "pv", "ess", "ev"]
