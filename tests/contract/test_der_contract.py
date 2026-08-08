"""`DER` 계약 테스트 스위트 — 작업 1.1 / FR-101.

**계약 테스트는 계약 문서보다 강하다** (spec §16.2). 문서로 *"capex()는 원 단위
정수를 반환한다"* 고 써 두면 누군가는 float를 반환한다. 계약 테스트로 두면 그
순간 실패한다.

이 스위트는 **자원 클래스를 구현하는 쪽이 상속받아 자동으로 통과해야 하는**
검사 묶음이다. `DERContractTests` 를 상속하고 `make()` 하나만 채우면 6개
메서드·9개 속성·매체 플래그 규약이 전부 검사된다 (§13.0.3 L3).

    class TestPVContract(DERContractTests):
        def make(self):
            return PV(name="옥상PV", capacity_kw=3.0)

**왜 이 형태인가.** NFR-201은 *"신규 자원 추가는 코어 엔진 수정 없이"* 를
요구하고 NFR-106은 *"레지스트리를 순회해 케이스 누락을 검사"* 한다. 두 요구를
만족시키려면 계약 준수 여부가 **자원마다 다시 쓰이는 테스트**가 아니라
**상속으로 따라오는 것**이어야 한다. 자원마다 손으로 쓰면 반드시 빠진다.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from core.contracts.der import DER, DispatchContext
from core.contracts.units import Money, Year

# spec FR-101-AC1 이 열거한 속성. 이름을 여기서 다시 짓지 않고 그대로 옮긴다 —
# 옮겨 적는 순간 spec과 코드가 갈릴 수 있으므로, 갈리면 이 테스트가 깨진다.
REQUIRED_ATTRS = [
    "name",
    "tag",
    "dt",
    "carries_electric",
    "carries_heat",
    "carries_cool",
    "consumes_fuel",
    "lifetime",
    "degradation_rate",
]

# spec FR-101-AC2 가 열거한 메서드.
REQUIRED_METHODS = [
    "capex",
    "fixed_om",
    "variable_om",
    "replacement_schedule",
    "salvage_value",
    "dispatch",
]

MEDIA_FLAGS = ["carries_electric", "carries_heat", "carries_cool", "consumes_fuel"]


class DERContractTests:
    """자원 구현체가 상속해 통과시키는 계약 테스트."""

    def make(self) -> DER:
        raise NotImplementedError("구현체 테스트가 make() 를 정의해야 합니다")

    # ── 속성 (FR-101-AC1) ────────────────────────────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC1")
    def test_required_attributes_exist(self) -> None:
        der = self.make()
        missing = [a for a in REQUIRED_ATTRS if not hasattr(der, a)]
        assert not missing, f"FR-101-AC1 속성 누락: {missing}"

    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC1")
    def test_media_flags_are_bool(self) -> None:
        der = self.make()
        for flag in MEDIA_FLAGS:
            value = getattr(der, flag)
            assert isinstance(value, bool), (
                f"{flag} 는 bool 이어야 합니다 (실제 {type(value).__name__}). "
                "매체 플래그로 수지를 분리 집계하므로(AC4) 참/거짓이 아니면 "
                "집계 분기가 성립하지 않습니다"
            )

    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC1")
    def test_lifetime_is_positive_int_years(self) -> None:
        der = self.make()
        assert isinstance(der.lifetime, int) and not isinstance(der.lifetime, bool), (
            "lifetime 은 정수 년이어야 합니다 (§7.5 기간 — 년(정수))"
        )
        assert der.lifetime > 0

    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC1")
    def test_degradation_rate_is_normalized_fraction(self) -> None:
        der = self.make()
        assert isinstance(der.degradation_rate, float)
        assert 0.0 <= der.degradation_rate < 1.0, (
            "degradation_rate 는 코드 내부에서 소수(0~1)로 정규화합니다 (§7.5 비율). "
            "3%를 3.0으로 넣으면 1년 만에 발전량이 음수가 됩니다"
        )

    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC1")
    def test_dt_is_positive_seconds(self) -> None:
        der = self.make()
        assert isinstance(der.dt, int) and der.dt > 0, (
            "dt 는 시간스텝(초)입니다 (§7.5). 8760 해상도면 3600"
        )

    # ── 메서드 (FR-101-AC2) ──────────────────────────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC2")
    def test_required_methods_exist_and_callable(self) -> None:
        der = self.make()
        missing = [m for m in REQUIRED_METHODS
                   if not callable(getattr(der, m, None))]
        assert not missing, f"FR-101-AC2 메서드 누락: {missing}"

    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC2")
    def test_money_methods_return_whole_won(self) -> None:
        """금액을 돌려주는 메서드는 **정수 원**을 준다 (NFR-103).

        float를 허용하면 20년 프로포마 합계와 항목별 합계가 어긋난다.
        그 어긋남은 화면상 정상으로 보이므로 사후 발견이 어렵다.
        """
        der = self.make()
        for name in ("capex", "fixed_om", "variable_om", "salvage_value"):
            value = getattr(der, name)(year=1)
            assert isinstance(value, Money), (
                f"{name}() 는 Money(Decimal 원)를 반환해야 합니다 "
                f"(실제 {type(value).__name__}). NFR-103 재무 계층 규약입니다"
            )
            assert value == value.to_integral_value(), (
                f"{name}() 가 원 미만 소수를 반환했습니다: {value}. "
                "반올림은 경계 함수 한 곳에서만 일어납니다 (NFR-103 경계 정의)"
            )

    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC2")
    def test_replacement_schedule_within_lifetime_horizon(self) -> None:
        der = self.make()
        schedule = der.replacement_schedule(horizon=20)
        assert isinstance(schedule, dict)
        for year, amount in schedule.items():
            assert isinstance(year, int) and 1 <= year <= 20, (
                f"교체 연도 {year} 가 분석기간(1~20) 밖입니다"
            )
            assert isinstance(amount, Money) and amount >= 0

    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC2")
    def test_dispatch_accepts_context_and_returns_series(self) -> None:
        der = self.make()
        ctx = DispatchContext(steps=24, dt=der.dt, year=1)
        result = der.dispatch(ctx)
        assert len(result.electric) == 24, (
            "dispatch()는 컨텍스트가 요구한 스텝 수만큼 돌려줘야 합니다 "
            "(FR-301-AC3 — 시계열 행수 불일치는 명확한 오류)"
        )

    # ── 매체 플래그와 수지 분리 (FR-101-AC4) ────────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC4")
    def test_dispatch_respects_media_flags(self) -> None:
        """플래그가 꺼진 매체에 값을 실으면 안 된다.

        이것이 AC4의 실질이다. 엔진은 플래그를 보고 수지를 분리 집계하므로,
        플래그가 거짓인데 값이 실리면 **그 값은 어느 수지에도 잡히지 않고
        사라진다.** 조용히 사라지는 에너지는 NFR-102 수지 검증도 통과한다 —
        애초에 집계 대상이 아니기 때문이다.
        """
        der = self.make()
        ctx = DispatchContext(steps=24, dt=der.dt, year=1)
        result = der.dispatch(ctx)

        for flag, series_name in (
            ("carries_electric", "electric"),
            ("carries_heat", "heat"),
            ("carries_cool", "cool"),
            ("consumes_fuel", "fuel"),
        ):
            series = getattr(result, series_name)
            if not getattr(der, flag):
                assert all(v == 0.0 for v in series), (
                    f"{flag}=False 인데 {series_name} 계열에 0이 아닌 값이 "
                    f"있습니다. 이 값은 어느 수지에도 집계되지 않고 사라집니다"
                )

    # ── 확장성 (FR-101-AC3) ─────────────────────────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-101-AC3")
    def test_implements_der_without_engine_knowledge(self) -> None:
        """구현체가 코어 엔진을 import하지 않는다.

        NFR-208-AC1(역방향 import 금지)을 자원 단위로 앞당겨 잡는다.
        import-linter가 CI에서 같은 것을 보지만, 여기서 걸리면 어느 자원이
        원인인지 즉시 드러난다.
        """
        der = self.make()
        assert isinstance(der, DER)

        module = inspect.getmodule(type(der))
        assert module is not None
        source = inspect.getsource(module)
        for forbidden in ("core.engine", "core.cba", "core.casegrid"):
            assert forbidden not in source, (
                f"자원 구현이 {forbidden} 를 참조합니다. 자원은 계약만 보고 "
                "동작해야 합니다 (FR-101-AC3, NFR-208-AC1)"
            )


# ── 계약 자체에 대한 검사 ────────────────────────────────────────────
#
# 위 스위트는 *구현체*를 검사한다. 아래는 *계약 정의*를 검사한다 —
# 계약이 spec과 어긋나면 모든 구현체가 함께 어긋난다.

@pytest.mark.contract
@pytest.mark.req("FR-101-AC1")
def test_der_declares_all_spec_attributes() -> None:
    for attr in REQUIRED_ATTRS:
        assert attr in DER.__annotations__ or hasattr(DER, attr), (
            f"DER 계약이 FR-101-AC1 속성 `{attr}` 을 선언하지 않았습니다"
        )


@pytest.mark.contract
@pytest.mark.req("FR-101-AC2")
def test_der_declares_all_spec_methods_as_abstract() -> None:
    """6개 메서드가 **추상**이어야 한다.

    기본 구현을 주면 구현체가 잊어도 통과한다. 잊힌 메서드는 기본값을
    돌려주며, 그 기본값이 0원이면 비용이 조용히 사라진다.
    """
    abstracts = getattr(DER, "__abstractmethods__", frozenset())
    missing = [m for m in REQUIRED_METHODS if m not in abstracts]
    assert not missing, (
        f"다음 메서드가 추상이 아닙니다: {missing}. 기본 구현이 있으면 "
        "구현체가 잊어도 통과하고, 잊힌 비용은 0원으로 계상됩니다"
    )


@pytest.mark.contract
@pytest.mark.req("FR-101-AC3")
def test_der_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        DER()  # type: ignore[abstract]


@pytest.mark.contract
@pytest.mark.req("FR-101-AC4")
def test_dispatch_result_carries_all_four_media() -> None:
    """매체 4종이 전부 계약에 있어야 한다.

    하나라도 빠지면 그 매체를 다루는 자원이 값을 실을 곳이 없어지고,
    구현자는 다른 계열에 섞어 넣는다. 섞인 값은 수지 분리를 무의미하게 만든다.
    """
    from core.contracts.der import DispatchResult

    result = DispatchResult.zeros(steps=3)
    for media in ("electric", "heat", "cool", "fuel"):
        assert hasattr(result, media), f"DispatchResult 에 {media} 계열이 없습니다"
        assert len(getattr(result, media)) == 3


@pytest.mark.contract
@pytest.mark.req("FR-301-AC3")
def test_dispatch_context_rejects_step_mismatch() -> None:
    """시계열 행수 불일치는 **명확한 오류로 중단**한다 (FR-301-AC3).

    조용히 자르거나 채우면 어느 해의 어느 시각이 어긋났는지 영영 모른다.
    """
    with pytest.raises(ValueError, match="스텝"):
        DispatchContext(steps=0, dt=3600, year=1)

    ctx = DispatchContext(steps=24, dt=3600, year=1)
    with pytest.raises(ValueError, match="스텝"):
        ctx.check_series(list(range(23)), name="발전량")


@pytest.mark.contract
@pytest.mark.req("FR-101-AC2")
def test_year_is_one_based() -> None:
    """분석 연도는 1부터 센다.

    0-base와 1-base가 섞이면 20년 분석이 19년이 되거나 잔존가치가 한 해
    밀린다. 두 오류 모두 결과가 그럴듯해서 눈으로는 잡히지 않는다.
    """
    with pytest.raises(ValueError):
        Year(0)
    assert int(Year(1)) == 1
    assert Money(Decimal("0")) == 0
