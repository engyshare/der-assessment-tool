from __future__ import annotations

import ast
import random
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import core.der
from core.contracts.der import DER, DispatchContext, DispatchResult
from core.contracts.engine import DispatchEngine, SystemDispatch
from core.contracts.registry import discover
from core.contracts.units import SECONDS_PER_HOUR, Money
from core.engine import DispatchRule, RuleBasedEngine, dispatch_digest, media_balance_error
from core.engine import rule_based as _engine_module
from core.engine.rule_based import rule_for


def ctx(steps: int = 4) -> DispatchContext:
    return DispatchContext(steps=steps, dt=SECONDS_PER_HOUR, year=1)


@dataclass
class StubResource:
    name: str
    electric: list[float]
    tag: str = "Stub"
    #: 자원이 스스로 선언하는 디스패치 규칙 (`DER.DISPATCH_RULE` · FR-101-AC3).
    #: 기본값 빈 문자열은 「선언하지 않았다」이며 엔진의 기본 갈래로 떨어진다 —
    #: 스텁도 실물과 **같은 경로**로 순위를 받아야 이 파일의 순서 검사가
    #: 실물을 말한다.
    DISPATCH_RULE: str = ""
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
    # ⚠ **규칙은 자원이 선언한다** (R59 · FR-101-AC3). 엔진은 태그를 보지
    # 않으므로 `tag=` 만 주면 넷이 모두 기본 갈래로 떨어져 이 검사가 순서를
    # 재지 못한다 — 실물 자원(`core/der/*.py`)이 하는 선언을 스텁도 한다.
    resources = [
        StubResource("load", [-1.0], tag="Load"),
        StubResource("ev", [0.0], tag="EV_V2G", DISPATCH_RULE="v2g_charge"),
        StubResource("ess", [0.0], tag="ESS", DISPATCH_RULE="ess_charge"),
        StubResource("pv", [1.0], tag="PV", DISPATCH_RULE="pv_self_consumption"),
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


# ── FR-101-AC3 확장성 — 「인터페이스만 구현하면 엔진 수정 없이 동작」 ────────
#
# **R38-B2 가 세웠다. 그전까지 이 조항을 재는 검사가 0건이었다.**
# 인용 2건(`test_der_contract.py::test_implements_der_without_engine_knowledge`·
# `test_smoke_wave0.py::test_reference_impl_imports_only_contracts`)은 **자원이
# 엔진을 import 하지 않는가**를 보았고 그것은 `NFR-208-AC1`(역방향 import 금지)
# 이다. 그 둘이 초록불인 채로 이 엔진은 `_rule_for()` 에서 자원 태그 셋을
# **리터럴로 알고 있었다** — 즉 「자원이 엔진을 모른다」가 참이면서 「엔진이 자원을
# 모른다」가 거짓일 수 있다. 두 조항이 같은 것을 다른 말로 하는 것이 아니다.
#
# **R59 가 그 셋을 없앴다.** 자원이 `DER.DISPATCH_RULE` 로 자기 규칙을 선언하고
# 엔진이 그것을 읽는다 — 엔진은 이제 어느 자원도 이름으로 알지 못한다. 아래
# 넷이 그 상태를 잰다: ⓐ 계약만 구현한 자원이 **돈다**, ⓑ 엔진 소스에 자원 태그
# 문면이 **한 건도 없다**, ⓒ 자원이 선언한 문자열이 엔진 어휘에 **실재한다**,
# ⓓ 모르는 문자열·빈 문자열이 **기본 갈래로 떨어져 그래도 돈다**.

#: 엔진이 `_rule_for()` 에서 **디스패치 순위를 배정하려고** 리터럴로 아는 태그.
#:
#: **★ R59 에 비었다.** R38-B2 가 이 자리를 세울 때는 셋(`PV`·`ESS`·`EV_V2G`)이
#: 「선언된 예외」였고, 그 시험의 오류 문면이 갈 방향을 적어 두었다 — *「줄었다면:
#: 좋은 방향이다. 선언에서 지우십시오」*. R59 가 방향을 뒤집어(**자원이 규칙을
#: 선언하고 엔진이 읽는다** · `DER.DISPATCH_RULE`) 엔진에서 태그 리터럴이 **전부**
#: 사라졌으므로 셋을 지웠다.
#:
#: **빈 채로 남겨 두는 것이 요점이다.** 목록을 손으로 유지하는 것이 목적이 아니라
#: **늘어나는 것을 보이게** 하는 것이 목적이고, 이제 문턱이 0 이라 태그 리터럴이
#: **한 건이라도** 되돌아오면 아래 검사가 빨간불이 된다.
ENGINE_KNOWN_TAGS: frozenset[str] = frozenset()


class ContractOnlyResource(DER):
    """`DER` 계약의 **추상 메서드 7종만** 구현한 새 자원.

    `__init__` 을 정의하지 않는다 — `DER.__init__` 을 그대로 쓰므로 인스턴스
    속성이 계약이 세우는 것 **그대로**이고, 「인터페이스만」이 서술이 아니라
    **구조**가 된다. `OPERATING_MODES` 도 선언하지 않는다(빈 튜플이면 계약이
    `operating_mode` 를 빈 문자열로 둔다).

    `tag` 는 **엔진이 모르는 값**이다 — `ENGINE_KNOWN_TAGS` 와 겹치면 이 자원은
    특별 취급되는 경로로 돌아 「모르는 자원도 돈다」를 증명하지 못한다.
    """

    tag = "R38B2ContractOnly"

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

    def dispatch(self, context: DispatchContext) -> DispatchResult:
        zeros = [0.0] * context.steps
        return DispatchResult(
            electric=[3.0] * context.steps,
            heat=list(zeros),
            cool=list(zeros),
            fuel=list(zeros),
        )


def _engine_tag_literals() -> set[str]:
    """엔진 소스의 문자열 리터럴(**독스트링 제외**)을 casefold 해 돌려준다.

    ⚠ **독스트링을 제외하는 것이 핵심이다** (공통 4절 ②). 제외하지 않으면
    엔진 독스트링에 자원 이름을 적는 순간 빨간불이 나고, 사람은 **설명을 고쳐
    통과시키게** 된다 — 이 저장소가 일곱 번 만난 형태다. 주석은 `ast` 에 남지
    않으므로 따로 걸러낼 필요가 없다.
    """
    source = Path(_engine_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    return {
        node.value.casefold()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


@pytest.mark.req("FR-101-AC3")
def test_a_contract_only_resource_dispatches_through_the_unmodified_engine() -> None:
    """★★ 조항의 ⓐ「인터페이스만 구현하면」 + ⓒ「동작」을 **실행으로** 잰다.

    조항 문면: 「신규 자원 클래스가 위 인터페이스만 구현하면 코어 엔진 수정
    없이 동작 (**단위 테스트로 실증**)」 — 괄호가 검증 방법을 지정하므로
    **엔진을 실제로 돌리는 것**이 이 조항의 실증이다.

    ⓐ 는 **측정한다.** `ContractOnlyResource` 의 클래스 namespace 가 추상 7종 +
    `tag` 뿐이고 `__init__` 이 없음을 단언한다 — 훅을 하나라도 더하면 빨간불이다.

    ⓑ 는 여기서 **사실로** 확인한다: 이 자원의 `tag` 가 엔진 소스의 태그 리터럴에
    없는데도 돌았다. 즉 엔진은 이 자원을 알지 못한 채 처리했다. ⓑ 가 **계속**
    참이게 하는 것은 아래
    `test_engine_source_names_no_resource_tag_beyond_the_declared_three` 가 맡는다.

    ⚠ **붙들지 못하는 것 — 갈라 적는다.**
    ① 모르는 태그는 `GRID_IMPORT`(기본 갈래)로 배정되어 **디스패치 순서가
       맨 뒤**다. 새 자원이 고유한 순위를 필요로 하면 엔진을 고쳐야 하며,
       그 순위는 `FR-302` 소관이다. 이 검사는 「돈다」까지만 잰다
    ② 「엔진 diff 0줄」은 실행 시점에 볼 수 없다 — `NFR-201-M1` 의 계측이며
       PR 단위다. 여기서는 **원인**(엔진이 태그를 아는 것)을 아래 검사가 막는다
    """
    # ⓐ — 계약이 자라면 여기서 멈춘다. 7종을 손으로 적지 않고 계약에서 읽는다.
    abstracts = set(DER.__abstractmethods__)
    assert len(abstracts) == 7, (
        f"`DER` 추상 메서드가 7종이 아니다: {sorted(abstracts)}. 계약이 자랐으면 "
        "이 검사의 「인터페이스만」 기준도 사람이 다시 보아야 한다"
    )
    declared = {
        name
        for name in vars(ContractOnlyResource)
        if not name.startswith("__") and name != "_abc_impl"
    }
    extra = sorted(declared - abstracts - {"tag"})
    assert declared == abstracts | {"tag"}, (
        f"새 자원이 계약 밖의 것을 선언했다: {extra}. 그러면 「인터페이스만 "
        "구현하면」을 증명하지 못한다"
    )
    assert "__init__" not in vars(ContractOnlyResource), (
        "새 자원이 자기 `__init__` 을 두었다 — 인스턴스 속성이 계약이 세우는 것과 "
        "같다는 보장이 사라진다"
    )

    resource = ContractOnlyResource(name="newkind", lifetime=5, carries_electric=True)

    # ⓑ 사실 확인 — 엔진 소스에 이 태그가 없다.
    assert resource.tag.casefold() not in _engine_tag_literals(), (
        f"엔진이 {resource.tag!r} 를 리터럴로 알고 있다 — 이 검사는 「엔진이 "
        "모르는 자원도 돈다」를 증명하지 못한다"
    )
    # 모르는 태그가 **정의된 기본 갈래**로 떨어진다. 여기서 예외가 나면 새 자원은
    # 엔진을 고치지 않고는 아예 돌지 않는다.
    assert rule_for(resource) is DispatchRule.GRID_IMPORT

    # ⓒ — 실제로 돌린다. 기존 자원과 **함께** 넣어 수지가 닫히는지 본다.
    load = StubResource("load", [-1.0, -1.0, -1.0], tag="Load")
    dispatch = RuleBasedEngine().run([resource, load], ctx(steps=3))

    assert set(dispatch.per_resource) == {"newkind", "load"}, (
        "새 자원이 결과에서 빠졌다 — 조용히 누락되면 그 자원의 편익·비용이 "
        "통째로 사라지면서 수지 검사는 통과한다"
    )
    assert dispatch.per_resource["newkind"].electric == [3.0, 3.0, 3.0]
    # 3.0(내보냄) − 1.0(받아들임) = 2.0 이 계통으로 나간다. 새 자원이 집계에서
    # 빠졌다면 이 값이 0 이 되므로, 위 `set(...)` 단언과 **다른 경로**로 같은
    # 누락을 잡는다.
    assert dispatch.grid_export == [2.0, 2.0, 2.0]
    assert dispatch.grid_import == [0.0, 0.0, 0.0]
    assert max(abs(error) for error in dispatch.electric_balance_error()) == 0.0


@pytest.mark.req("FR-101-AC3")
def test_engine_source_names_no_resource_tag_beyond_the_declared_three() -> None:
    """★★ 조항의 ⓑ「코어 엔진 수정 없이」를 **원인 쪽에서** 막는다.

    「엔진이 수정되지 않았다」는 실행 시점에 볼 수 없다. **R23 이 같은 벽을
    만나 「바뀌게 만드는 원인」을 막았다** — 편집기 소스에 자원 `tag` 문면이
    없는지 `ast` 로 대조하는 형태다. 여기도 같다: 엔진이 자원 태그를 리터럴로
    알면 **자원 1종을 더할 때 엔진이 그 목록을 늘려야** 하고, 그 순간 조항이
    깨진다.

    **엔진이 아는 태그는 이제 0종이다** (R59). R38-B2 시점에는 `_rule_for()` 가
    `PV`·`ESS`·`EV_V2G` 를 디스패치 **순위 배정**에 썼고, 그것을 0 으로 만드는
    것은 그 구획의 일이 아니어서 셋을 **선언된 예외**로 고정해 두었다. R59 가
    방향을 뒤집어 그 셋을 없앴다 — 자원이 `DER.DISPATCH_RULE` 로 규칙을
    선언하고 엔진이 그것을 `DispatchRule(...)` 로 되돌린다. 그래서 문턱이
    0 이고, 태그 리터럴이 **한 건이라도 되돌아오면 빨간불**이다.

    ⚠ **순위 자체가 사라진 것이 아니다.** `DEFAULT_RULE_ORDER` 는 그대로이고
    자원 여섯의 규칙 배정도 R59 전후로 한 건도 달라지지 않았다 — 바뀐 것은
    **누가 그 배정을 아는가**뿐이다.

    비교 대상을 **레지스트리에서 읽는다**(`discover(core.der, DER)`) — 손으로
    적으면 자원을 추가할 때 반드시 빠지고, 빠진 자원은 검사받지 않는다.

    ⚠ **붙들지 못하는 것 — 갈라 적는다.**
    ① `core/engine/` 만 본다. `core/cba/`·`core/casegrid/` 가 태그를 리터럴로
       아는지는 보지 않는다(`NFR-201-M1` 이 그 두 디렉터리를 PR diff 로 본다)
    ② **정확히 일치하는 태그 문면만** 잡는다. `pv_self_consumption` 처럼
       태그를 **부분 문자열로 품은** 리터럴은 통과한다 — 규칙 이름이 자원
       이름을 딴 것은 정상이므로 부분 일치로 넓히면 규칙 상수 전부가 걸린다
    ③ 태그가 아닌 방식의 결합(`isinstance` 분기, 클래스 이름 대조)은 보지
       않는다. 그것이 생기면 이 검사는 조용히 통과한다
    """
    tags = {tag.casefold(): tag for tag in discover(core.der, DER)}
    assert len(tags) >= 4, (
        f"레지스트리 자원이 {len(tags)}종이다 — 「엔진이 아는 것보다 자원이 "
        "많다」가 성립하지 않으면 이 검사는 아무것도 말하지 않는다"
    )

    named = {tags[key] for key in _engine_tag_literals() & tags.keys()}
    grown = sorted(named - set(ENGINE_KNOWN_TAGS))
    shrunk = sorted(set(ENGINE_KNOWN_TAGS) - named)
    assert named == set(ENGINE_KNOWN_TAGS), (
        f"엔진이 리터럴로 아는 자원 태그가 선언된 예외와 다르다.\n"
        f"  선언: {sorted(ENGINE_KNOWN_TAGS)}\n"
        f"  실측: {sorted(named)}\n"
        f"  더 늘었다면: {grown} — 자원 1종을 더할 때 엔진을 고쳐야 한다는 "
        "뜻이며 FR-101-AC3 이 금지하는 것이다. 정말 필요하면 "
        "`ENGINE_KNOWN_TAGS` 에 근거와 함께 적으십시오.\n"
        f"  줄었다면: {shrunk} — 좋은 방향이다. 선언에서 지우십시오"
    )
    assert set(ENGINE_KNOWN_TAGS) < set(tags.values()), (
        "엔진이 자원 전건을 리터럴로 알고 있다 — 새 자원마다 엔진을 고쳐야 하는 "
        "상태이며 FR-101-AC3 이 성립하지 않는다"
    )


@pytest.mark.req("FR-101-AC3")
def test_every_declared_dispatch_rule_exists_in_the_engine_vocabulary() -> None:
    """★ 조항의 ⓑ 를 **뒤집은 방향에서** 지킨다 — 선언이 어휘에 실재하는가.

    R59 가 태그 리터럴을 없앤 대가로 결합이 **평문 문자열**이 됐다
    (`DER.DISPATCH_RULE = "pv_self_consumption"`). 자원은 `DispatchRule` 을
    import 할 수 없으므로(`NFR-208-AC1` 역방향 import 금지) 열거형이 오타를
    막아 주지 않는다 — 그리고 **오타는 조용하다**: 엔진이 모르는 문자열을
    기본 갈래로 떨어뜨리므로 `ess_charrge` 라고 적힌 ESS 는 예외 없이 돌면서
    디스패치 순서만 맨 뒤로 간다. 그 조용함을 여기서 끊는다.

    목록을 손으로 적지 않고 **레지스트리 전건**을 훑는다
    (`discover(core.der, DER)`) — 위 검사가 쓰는 것과 같은 정본이다. 손으로
    적으면 자원을 추가할 때 반드시 빠지고, 빠진 자원은 검사받지 않는다.

    ⚠ **선언하지 않은 자원은 위반이 아니다.** `heatpump`·`load`·
    `thermal_load` 는 선언이 없고 기본 갈래로 떨어지는데 그것이 **정상**이며,
    「이 속성을 모르는 자원도 돈다」가 `FR-101-AC3` 의 증거다. 여기서 재는
    것은 *「적었다면 실재하는가」* 뿐이다.
    """
    vocabulary = {rule.value for rule in DispatchRule}
    registry = discover(core.der, DER)
    assert len(registry) >= 4, (
        f"레지스트리 자원이 {len(registry)}종이다 — 전건 순회가 성립하지 않는다"
    )

    declared = {
        tag: cls.DISPATCH_RULE for tag, cls in registry.items() if cls.DISPATCH_RULE
    }
    assert declared, (
        "규칙을 선언한 자원이 0종이다 — 그러면 엔진의 순위 배정이 전부 기본 "
        "갈래로 무너진 것이고, 이 검사는 아무것도 말하지 않는다"
    )

    unknown = {
        tag: value for tag, value in declared.items() if value not in vocabulary
    }
    assert not unknown, (
        f"자원이 선언한 디스패치 규칙이 엔진 어휘에 없다: {unknown}.\n"
        f"  어휘: {sorted(vocabulary)}\n"
        "평문 문자열이라 오타가 조용하다 — 이 자원은 예외 없이 돌면서 "
        "디스패치 순서만 맨 뒤(기본 갈래)로 간다. `DispatchRule` 의 **값 "
        "문자열**을 그대로 적으십시오 (열거형을 import 하지 않는 이유는 "
        "`DER.DISPATCH_RULE` 독스트링에 있다)"
    )

    fell_back = {
        tag: value
        for tag, value in declared.items()
        if DispatchRule(value) is DispatchRule.GRID_IMPORT
    }
    assert not fell_back, (
        f"자원이 기본 갈래를 명시적으로 선언했다: {fell_back}. 선언하지 않은 "
        "것과 구별되지 않으므로 선언을 지우십시오 — 두 상태가 한 결과로 "
        "겹치면 「선언을 잊었다」를 아무도 볼 수 없다"
    )


@pytest.mark.req("FR-101-AC3")
def test_unknown_and_missing_dispatch_rule_declarations_still_dispatch() -> None:
    """★ 조항의 ⓒ「동작」을 **예외가 새는 쪽에서** 못 박는다.

    선언을 읽는 구조는 「읽을 것이 없을 때」와 「읽은 것이 틀렸을 때」 두 구멍을
    함께 연다. 둘 중 하나라도 예외가 되면 **새 자원은 엔진을 고치지 않고는
    아예 돌지 않으므로** 조항이 깨진다 — R59 가 태그 리터럴을 없애면서 산
    위험이 정확히 이것이라 여기서 실행으로 잰다.

    ⚠ 이 검사는 「기본 갈래로 떨어진다」를 **바람직하다고 말하지 않는다.**
    오타를 잡는 것은 위
    `test_every_declared_dispatch_rule_exists_in_the_engine_vocabulary` 의
    몫이고, 여기서 재는 것은 *「그래도 돈다」* 뿐이다.
    """
    typo = StubResource("typo", [1.0], tag="ESS", DISPATCH_RULE="ess_charrge")
    silent = StubResource("silent", [1.0], tag="HeatPump")
    empty_ish = StubResource("blank", [1.0], tag="Load", DISPATCH_RULE="")
    declared = StubResource("ess", [0.0], tag="ESS", DISPATCH_RULE="ess_charge")

    assert rule_for(typo) is DispatchRule.GRID_IMPORT
    assert rule_for(silent) is DispatchRule.GRID_IMPORT
    assert rule_for(empty_ish) is DispatchRule.GRID_IMPORT
    # 대조군 — 선언이 옳으면 그 규칙을 그대로 받는다. 없으면 위 셋은 「무엇을
    # 해도 기본 갈래」와 구별되지 않아 아무것도 증명하지 못한다.
    assert rule_for(declared) is DispatchRule.ESS_CHARGE

    load = StubResource("load", [-3.0], tag="Load")
    dispatch = RuleBasedEngine().run([typo, silent, empty_ish, declared, load], ctx(steps=1))

    assert set(dispatch.per_resource) == {"typo", "silent", "blank", "ess", "load"}
    assert dispatch.grid_export == [0.0]
    assert dispatch.grid_import == [0.0]
    # 선언한 자원이 앞, 선언하지 않은 셋은 기본 갈래라 **입력 순서**로 뒤에 선다.
    assert list(dispatch.per_resource) == ["ess", "typo", "silent", "blank", "load"]
