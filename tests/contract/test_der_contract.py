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

from core.contracts.der import DER, MEDIA, DispatchContext
from core.contracts.units import Money, Year, steps_per_year
from tests.contract.source_scan import imported_module_names

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

# spec FR-101-AC2 가 열거한 메서드. `capex_vat` 는 v1.1 계약 개정에서 들어왔다 —
# §13.2.2 C-1(부가세 별도 분리)이 요구하는데 자리가 없어 자원 6종이 각자 지었고
# ESS 하나는 아예 만들지 않았다.
REQUIRED_METHODS = [
    "capex",
    "capex_vat",
    "fixed_om",
    "variable_om",
    "replacement_schedule",
    "salvage_value",
    "dispatch",
]

#: 금액을 돌려주며 `year` 하나만 받는 메서드 — 정수 원 검사 대상
MONEY_METHODS = ["capex", "capex_vat", "fixed_om", "variable_om", "salvage_value"]

MEDIA_FLAGS = [flag for _media, flag in MEDIA]


#: 교체비에 **교체 전용 물가 계수를 쓰지 않는** 자원 — 실측 부채 (R42).
#:
#: **`HeatPump` 는 R43 이 뺐다** — 이 래칫이 그 결함을 처음 드러냈고(R42 가 쟀다),
#: `ESS` 와 같은 근거(대장 최상위 `price_basis: "명목"` 1회 선언 · `DV-7`)로
#: 「탄다」로 판정해 `heatpump.py::replacement_schedule()` 에 배선했다.
#:
#: 남은 `ReferencePV` 는 Wave 0 참조 구현이며 **실행 경로가 아니다.** 러너의
#: 구성에 없어 결론축을 움직이지 않고, 무엇보다 「참조 구현이 실물 자원과 같은
#: 재무 규약을 져야 하는가」는 아직 판정된 적이 없다 — `DV-7` 을 근거로 삼은
#: `ESS`·`HeatPump` 의 선례가 그대로 옮겨 간다고 **가정하지 않는다.**
#:
#: 비어 있지 않다고 방치하지 않는다 — **줄면 빨간불**이 나서 목록을 함께 줄이라고
#: 알린다(`KNOWN_ESCALATION_IGNORED_IN_REPLACEMENT` 와 같은 래칫이다).
KNOWN_REPLACEMENT_RATE_IGNORED: frozenset[str] = frozenset({"ReferencePV"})


class DERContractTests:
    """자원 구현체가 상속해 통과시키는 계약 테스트."""

    def make(self) -> DER:
        raise NotImplementedError("구현체 테스트가 make() 를 정의해야 합니다")

    # ── 수명 도달 처리 (FR-104-AC3) ──────────────────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-104-AC3")
    def test_retire_clears_replacement_schedule(self) -> None:
        """**`retire` 를 고르면 교체비가 사라진다.**

        상속으로 두는 이유는 이 파일이 이미 아는 것과 같다 — **자원마다 각자
        분기를 쓰므로, 한 자원이 빠뜨려도 그 자원의 테스트만 보면 드러나지
        않는다.** 그 자원에는 애초에 retire 케이스가 없기 때문이다.
        여기 두면 **자원을 추가하는 순간 자동으로 걸린다.**

        `replace` 쪽도 함께 본다. `retire` 만 검사하면 **교체비를 아예
        계상하지 않는 구현**도 통과하고, 그러면 이 검사는 아무것도 검사하지
        않는다.
        """
        from core.contracts.der import EOL_RETIRE

        horizon = 40           # 어떤 자원이든 수명을 넘기도록 넉넉히 잡는다
        keeps = self.make()
        booked = keeps.replacement_schedule(horizon=horizon)
        assert booked, (
            f"{type(keeps).__name__}: `replace` 인데 {horizon}년 안에 교체비가 "
            "하나도 없습니다 — 이 상태에서는 아래 검사가 아무것도 검사하지 "
            "못합니다"
        )

        retires = self.make()
        retires.end_of_life_action = EOL_RETIRE
        assert not retires.replacement_schedule(horizon=horizon), (
            f"{type(retires).__name__}: `retire` 인데 교체비가 남아 있습니다 — "
            "사지 않기로 한 설비의 교체비를 계상하면 필요 지원액이 과대 "
            "산정됩니다 (FR-104-AC3)"
        )

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
    @pytest.mark.req("NFR-103-M1")
    def test_money_methods_return_whole_won(self) -> None:
        """금액을 돌려주는 메서드는 **정수 원**을 준다 (NFR-103).

        float를 허용하면 20년 프로포마 합계와 항목별 합계가 어긋난다.
        그 어긋남은 화면상 정상으로 보이므로 사후 발견이 어렵다.

        **마커를 `FR-101-AC2` 에서 옮겼다 (R15).** `AC2` 는 **메서드 목록**이고
        그것은 **바로 위 `test_required_methods_exist` 가 검사한다** — 같은
        조항에 둘이 붙어 있으면서 한쪽은 조항이 말하지 않는 것(반환 자료형)을
        보고 있었다. `NFR-103` 본문이 *「재무 계산은 Decimal 또는 정수 원
        단위로 처리해야 한다」* 이고, 이 단언들이 이미 그것을 인용하고 있다.
        """
        der = self.make()
        for name in MONEY_METHODS:
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

    # ── 부분 창 규약 (v1.1 계약 개정 ①) ─────────────────────────────
    @pytest.mark.contract
    # ↓ v0.15 이관 — 이 검사가 보는 것은 「행수 불일치 시 오류」(AC3)가 아니라
    # **해상도가 달라도 겹치는 구간이 일치한다**(AC5)다. AC5 가 없던 동안 AC3 을
    # 빌려 인용했고, 매핑표는 그것을 AC3 이 검증된 것으로 셌다.
    @pytest.mark.req("FR-301-AC5")
    def test_dispatch_partial_window_is_a_prefix_of_the_year(self) -> None:
        """`steps=24` 는 **연초부터 24스텝**이다 — 짧은 창은 긴 창의 앞부분이다.

        **이것이 계약 개정 1순위였던 구멍이다.** v1.0 은 docstring에 *"한 해 운전
        시뮬레이션"* 이라고만 적고 계약 테스트는 `steps=24` 로 호출했다. 부분 창을
        어떻게 해석할지 근거가 없어 자원 6종이 각자 정했고, 같은 컨텍스트가
        자원마다 다른 시각 구간을 뜻하게 되었다.

        창은 **관측 범위**이지 물리의 변경이 아니다. 24스텝을 요구했다는 사실이
        그 24스텝 안에서 벌어지는 일을 바꿔서는 안 된다. 바꾸면 엔진이 스텝 `i`
        에서 더하는 값들이 서로 다른 시각의 값이 되는데, 총량은 그럴듯하고
        수지 균형(NFR-102)도 통과한다 — 시각의 어긋남은 균형식이 보지 못한다.

        금지되는 해석이 이 검사에 걸린다:
            · 연간 총량을 창 길이에 몰아 담기 → 24스텝 값이 48스텝 때와 다르다
            · 창 안에 사이클을 억지로 압축하기 → 같은 이유로 다르다
        """
        der = self.make()
        short = der.dispatch(DispatchContext(steps=24, dt=der.dt, year=1))
        long = der.dispatch(DispatchContext(steps=48, dt=der.dt, year=1))

        for media, _flag in MEDIA:
            head = getattr(long, media)[:24]
            got = getattr(short, media)
            assert got == pytest.approx(head, abs=1e-9), (
                f"{media} 계열: 24스텝 창의 값이 48스텝 창의 앞부분과 다릅니다. "
                "부분 창은 연초부터의 연속 구간이며, 창 길이가 그 구간의 내용을 "
                "바꾸면 안 됩니다 (DispatchContext 부분 창 규약)"
            )

    @pytest.mark.contract
    @pytest.mark.req("FR-301-AC3")
    def test_dispatch_rejects_resolution_mismatch(self) -> None:
        """`ctx.dt ≠ self.dt` 는 **거부**한다 — 조용히 한쪽을 채택하지 않는다.

        v1.0 에서는 자원마다 달랐다. 어떤 자원은 `self.dt` 로 스텝 길이를 곱하고
        어떤 자원은 `ctx.dt` 를 썼으며, 아무도 불일치를 거부하지 않았다.
        해상도 비(4배)만큼 어긋난 에너지가 그럴듯한 값으로 남는다.
        """
        der = self.make()
        other_dt = der.dt // 4 if der.dt == 3600 else der.dt * 4
        ctx = DispatchContext(steps=24, dt=other_dt, year=1)
        with pytest.raises(ValueError):
            der.dispatch(ctx)

    # ── 편익 훅 (v1.1 계약 개정 ③ · RC-LD-B0) ───────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-401-AC1")
    def test_value_streams_returns_tags(self) -> None:
        """`value_streams()` 는 편익 tag 튜플을 돌려준다.

        `ValueStream` 객체가 아니라 tag 인 이유: 편익은 형제 구획(WP-4)이
        소유하므로 자원이 직접 참조하면 NFR-208-AC2 위반이다.
        """
        der = self.make()
        streams = der.value_streams()
        assert isinstance(streams, tuple), (
            f"value_streams() 는 tuple 을 돌려줍니다 (실제 {type(streams).__name__}). "
            "가변 리스트를 돌려주면 호출부가 자원의 선언을 고칠 수 있습니다"
        )
        for tag in streams:
            assert isinstance(tag, str) and tag, (
                f"편익 tag 는 비어 있지 않은 문자열입니다: {tag!r} "
                "(`FR-401-AC2.<키>` 와 같은 리터럴)"
            )
        assert len(set(streams)) == len(streams), (
            f"편익 tag 가 중복되었습니다: {streams}. 같은 편익을 두 번 선언하면 "
            "이중 계상됩니다 (FR-402-AC2.C)"
        )

    # ── 운전 방법 (v1.1 계약 개정 ④ · FR-105) ───────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-105-AC1")
    def test_operating_mode_is_declared_and_selected(self) -> None:
        """운전 방법 접근자 이름을 계약이 고정한다.

        v1.0 은 이름을 정하지 않아 `mode` 와 `operating_mode` 로 갈렸고,
        열거자도 `OPERATING_MODES`(클래스)와 `operating_modes`(인스턴스)로
        갈렸다. FR-105-AC5 는 케이스 그리드가 운전 방법을 **탐색 변수**로
        쓸 것을 요구하므로, 이름이 균일하지 않으면 자원별 분기가 생긴다 —
        NFR-201(코어 수정 0줄)이 무너지는 지점이다.
        """
        der = self.make()
        modes = type(der).OPERATING_MODES
        assert isinstance(modes, tuple), (
            "OPERATING_MODES 는 클래스 수준 tuple 입니다 (FR-105-AC1)"
        )
        assert isinstance(der.operating_mode, str)
        if modes:
            assert der.operating_mode in modes, (
                f"선택된 운전 방법 {der.operating_mode!r} 가 선언 목록 {modes} 에 "
                "없습니다"
            )
        else:
            assert der.operating_mode == "", (
                "운전 방법을 선언하지 않은 자원은 빈 문자열을 갖습니다 — "
                "선언 없이 값을 가지면 리포트에 근거 없는 방법이 표기됩니다 "
                "(FR-105-AC4)"
            )

    # ── 물가상승률 (v1.1 계약 개정 ⑤) ───────────────────────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-701-AC3")
    def test_escalation_rate_is_a_normalized_fraction(self) -> None:
        """물가상승률은 **소수**이며 이름은 `escalation_rate` 하나다.

        v1.0 에는 자리가 없어 자원이 각자 보유했다 — `inflation_pct`(**%**),
        `inflation_rate`(소수), `om_escalation`(소수)로 이름과 **척도**까지
        갈렸다. 같은 「2%」가 자원에 따라 `2.0` 과 `0.02` 로 들어가고, 어느 쪽도
        오류가 아니므로 아무도 잡지 못한다. 20년 프로포마에서 100배 차이다.
        """
        der = self.make()
        assert isinstance(der.escalation_rate, float)
        assert -1.0 < der.escalation_rate < 1.0, (
            f"escalation_rate 는 -1~1 소수입니다: {der.escalation_rate}. "
            "2%는 0.02 입니다 (§7.5)"
        )
        assert der.escalation_factor(year=1) == pytest.approx(1.0), (
            "1년차 물가 계수는 1.0 이어야 합니다 — 기준연도가 자원마다 다르면 "
            "같은 물가상승률이 한 해씩 어긋난 비용을 냅니다"
        )

    @pytest.mark.contract
    @pytest.mark.req("FR-701-AC3")
    def test_escalation_actually_compounds_over_the_years(self) -> None:
        """물가 계수가 **해마다 복리로** 쌓인다 — `(1+r)^(year−1)`.

        > **R17: 위 테스트는 1년차만 보았다.** 1년차 계수는 어떤 구현이든
        > 1.0 이므로, **물가상승률을 아예 쓰지 않는 구현**도 통과한다
        > (`return 1.0` 이 그렇다). 조항이 요구하는 것은 *「항목별 상이한
        > 에스컬레이션 **적용 가능**」* 이고, 적용되지 않으면 그 「상이」는
        > 아무 효과가 없다.

        기대값은 **손계산**이다 — 계수의 정의가 `(1+r)^(year−1)` 이므로
        `year=3` 이면 `(1+r)²` 이다. 20년차까지 확인하는 이유는 20년 프로포마가
        이 계수를 그대로 곱하기 때문이다.
        """
        der = self.make()
        rate = der.escalation_rate
        for year in (1, 2, 3, 20):
            expected = (1.0 + rate) ** (year - 1)
            assert der.escalation_factor(year=year) == pytest.approx(expected), (
                f"{year}년차 물가 계수가 (1+{rate})^{year - 1} 가 아닙니다 — "
                "물가상승률이 실제로 적용되지 않으면 항목별로 다르게 두어도 "
                "프로포마는 같은 값을 냅니다 (FR-701-AC3)"
            )
        if rate > 0.0:
            assert der.escalation_factor(year=20) > der.escalation_factor(year=2), (
                "물가상승률이 양수인데 계수가 늘지 않습니다"
            )

    @pytest.mark.contract
    @pytest.mark.req("FR-701-AC3")
    def test_replacement_escalation_defaults_to_the_same_rate(self) -> None:
        """교체 재취득 단가의 계수가 **따로 있고, 안 주면 같은 값이다** (R42).

        v1.1 까지 계수는 하나였고 고정 O&M·변동 O&M·교체비가 그것을 함께 받았다.
        대장의 `capex.replacement_real_trend`(`Q-17`)는 적용범위를 *「재취득
        단가에만 걸리고 O&M 은 대상이 아니다」* 로 좁혀 두었으므로, 계수가
        하나뿐이면 **그 항목을 흔들 때 대장이 선언하지 않은 것까지 움직인다.**

        ★ **이 계약이 넓어져도 지금 수는 한 자리도 안 움직인다** — 기본값이
        같기 때문이다. 그 「같음」 자체를 여기서 붙든다: 기본값이 갈리는 순간
        모든 자원의 교체비가 조용히 다른 기준으로 서고, 그 차이는 합계에
        드러나지 않는다.

        ⚠ **붙들지 못하는 것**: *자원이 교체 경로에서 그 계수를 실제로 쓰는가*
        는 여기서 재지 않는다(계약은 자리를 고정하지 손을 잡아끌지 않는다).
        그것은 `tests/casegrid/test_lifecycle_wiring.py` ⓕ 가 **행동으로** 잰다.
        """
        der = self.make()

        assert isinstance(der.replacement_escalation_rate, float)
        assert der.replacement_escalation_rate == der.escalation_rate, (
            "주지 않았는데 교체비 계수가 O&M 계수와 다릅니다 — 기본값이 갈리면 "
            "모든 자원의 교체비가 조용히 다른 기준으로 섭니다"
        )
        for year in (1, 2, 20):
            assert der.replacement_escalation_factor(year=year) == pytest.approx(
                der.escalation_factor(year=year)
            ), f"{year}년차에서 두 계수가 갈렸습니다 (기본값은 같아야 합니다)"

    @pytest.mark.contract
    @pytest.mark.req("FR-701-AC3")
    def test_replacement_follows_the_replacement_rate_and_om_does_not(self) -> None:
        """★★ 계수를 **가른 것**과 자원이 **그것을 쓰는 것**은 다르다 (R42).

        같은 자원을 복제해 `replacement_escalation_rate` 하나만 올리고 두 가지를
        본다:

            교체 스케줄  움직여야 한다  → 교체비가 그 계수를 실제로 읽는다
            고정 O&M     움직이면 안 된다 → 대장이 O&M 을 적용범위에서 뺐다

        뒤쪽이 이 검사의 절반이며 **부채를 허용하지 않는다.** 교체 계수가 O&M 에
        새면 `Q-17` 하단 −2.0 이 *「물가 계수를 태우지 않았다면」* 이 아니라
        *「O&M 물가까지 꺼 버렸다면」* 을 재게 되고, 그 오염은 5.1 의 한 행으로
        나가 검토자가 틀린 것을 배워 간다.

        ⚠ **금액이 0인 자원은 판정하지 않는다** — 계약 픽스처가 단가를 주지
        않으면 스케줄이 전부 0원이라 무엇을 곱해도 0이다. 확인 못 한 것을 부채로
        세면 다음 사람이 없는 일을 한다(ⓓ 래칫이 빈 스케줄에 대해 세운 원칙과
        같다). 그 자원은 `tests/casegrid/test_lifecycle_wiring.py` ⓕ 가 **금액이
        있는 탐침**으로 따로 잰다 — `PV` 가 실제로 그 갈래다.
        """
        import copy

        horizon = 40
        der = self.make()
        base = {y: int(v) for y, v in der.replacement_schedule(horizon=horizon).items()}
        om_before = der.fixed_om(year=10)

        bumped = copy.copy(der)
        bumped.replacement_escalation_rate = der.escalation_rate + 0.05
        after = {y: int(v) for y, v in bumped.replacement_schedule(horizon=horizon).items()}

        assert bumped.fixed_om(year=10) == om_before, (
            f"{type(der).__name__}: 교체비 계수를 올렸는데 **고정 O&M 이 따라 "
            "움직였습니다.** 대장(`capex.replacement_real_trend`)은 O&M 을 적용범위에서 "
            "명시적으로 뺐습니다 — 이 누수는 스윕 한 축을 통째로 다른 것으로 만듭니다"
        )

        if not any(v != 0 for v in base.values()):
            return  # 금액이 없다 — 판정 대상 아님 (위 ⚠)

        ignores = base == after
        name = type(der).__name__
        assert (name in KNOWN_REPLACEMENT_RATE_IGNORED) == ignores, (
            f"{name}: 교체비가 교체 계수를 쓰는지가 실측과 다릅니다.\n"
            f"  실측: {'쓰지 않는다' if ignores else '쓴다'}\n"
            f"  기대: {'쓰지 않는다' if name in KNOWN_REPLACEMENT_RATE_IGNORED else '쓴다'}\n"
            "쓰기 시작했다면 KNOWN_REPLACEMENT_RATE_IGNORED 에서 빼고, 그 자원이 "
            "결론에 들어와 있다면 **기준값을 재산출**하십시오. 반대로 늘었다면 "
            "누군가 교체 경로를 O&M 계수로 되돌린 것입니다"
        )

    @pytest.mark.contract
    @pytest.mark.req("FR-104-AC5")
    def test_salvage_value_tracks_remaining_life_and_is_never_negative(self) -> None:
        """잔존가치가 **잔존 수명을 따라 움직이고 음수가 되지 않는다** (FR-104-AC5).

        조항 문면은 *「분석기간 종료 시 **잔존 수명 비례** 잔존가치를 최종연도에
        계상」* 이다.

        > **R17: 이 조항의 계약 검사는 시그니처뿐이었다.** 바로 위 테스트가
        > 「할인율을 인자로 받지 않는다」를 보는데, 그것은 **명목액인지**를
        > 가리는 검사이고 **잔존 수명을 실제로 반영하는지**는 보지 않는다.
        > 그래서 연차와 무관한 상수를 돌려주는 구현도 계약을 통과했다. 값의
        > 실측은 자원별 테스트에만 있어 **자원이 늘면 함께 늘지 않는다** —
        > 계약 테스트가 있는 이유가 그것이다.

        ### ★ 「비례」를 계약 계층에서 단언하지 않는 이유 — 실측으로 확인했다

        `잔존가치(y)/잔존가치(y') = (L−y)/(L−y')` 를 단언하려 했으나 **자원
        7종 중 둘이 그 형태가 아니고, 그것이 옳다.**

        | 자원 | 단조감소 | 수명연차 0 | 단일자산 비례 |
        |---|---|---|---|
        | PV · ESS · EV_V2G · HeatPump · RefPV | ✓ | ✓ | ✓ |
        | **Load · ThermalLoad** | **✗** | **✗** | **✗** |

        `Load`·`ThermalLoad` 는 **복합자산**이다 — 본체와 부속설비가 수명이
        달라 각자 교체주기를 돌고(`(year−1) % life`), 부속이 교체되는 해에
        잔존가치가 다시 올라간다. 톱니 모양은 결함이 아니라 **교체를 반영한
        결과**이며, 반영하지 않으면 교체분의 잔존가치가 통째로 사라진다.

        **그러므로 단조감소·수명연차 0 은 조항이 정한 것이 아니라 단일자산의
        성질이다.** 계약이 그것을 요구하면 복합자산을 금지하는 셈이고, 그것은
        조항에 없는 규약을 계약으로 만드는 것이다 (`FR-402-AC1` 을 넓은 배타
        규칙이 지워 버리던 것과 같은 방향의 실수). **비례의 실측은 자원별
        테스트가 오라클로 한다** — `tests/der/test_pv.py` 의 `900,000원`.

        여기서는 **모든 구현이 지켜야 하는 것만** 본다.
        """
        der = self.make()
        life = int(der.lifetime)
        assert life >= 2, f"수명이 {life}년이면 잔존가치를 논할 구간이 없습니다"

        # 교체주기를 두 번 돌고 그 다음 해까지 — 주기 경계에서 부호가 뒤집히는
        # 구현을 잡으려면 `% life` 가 0 이 되는 자리를 반드시 지나야 한다
        series = [int(der.salvage_value(year=y)) for y in range(1, 2 * life + 2)]

        # ① **음수가 없다.** 음수 잔존가치는 비용이 아니라 **편익**으로 합산되고,
        #    값이 커지는 방향이므로 「보수적이라 괜찮다」로 넘어가지도 않는다
        negative = {y: v for y, v in enumerate(series, 1) if v < 0}
        assert not negative, (
            f"잔존가치가 음수인 연차가 있습니다: {negative}. 음수 잔존가치는 "
            "프로포마에서 비용을 줄이는 대신 **편익**으로 들어갑니다"
        )

        # ② **잔존 수명을 실제로 반영한다** — 취득가가 있으면 연차에 따라 값이
        #    변해야 한다. 상수(0 포함)를 돌려주는 구현이 여기서 걸린다
        acquisition = int(der.capex(year=1)) + int(der.capex_vat(year=1))
        if acquisition > 0:
            assert len(set(series)) > 1, (
                f"취득가가 {acquisition:,}원인데 잔존가치가 모든 연차에서 "
                f"{series[0]:,}원으로 같습니다 — 잔존 수명이 반영되지 않았습니다 "
                "(FR-104-AC5)"
            )
            assert max(series) > 0, (
                f"취득가가 {acquisition:,}원인데 잔존가치가 어느 연차에서도 "
                "0 을 넘지 않습니다"
            )
        else:
            assert set(series) == {0}, (
                f"취득가가 0 인데 잔존가치가 있습니다: {sorted(set(series))}"
            )

    # ── 잔존가치는 명목액 (v1.1 명문화 · §13.2.2 C-5) ───────────────
    @pytest.mark.contract
    @pytest.mark.req("FR-104-AC5")
    def test_salvage_value_takes_no_discount_rate(self) -> None:
        """`salvage_value()` 는 **할인율을 인자로 받지 않는다.**

        할인율은 사업 단위 전제(FR-701)이지 자원의 속성이 아니다. 자원이
        할인까지 하면 재무 계층이 한 번 더 할인해 **두 번 할인**되는데, 값이
        작아지므로 「보수적으로 보여서」 검출되지 않는다.

        시그니처를 검사하는 이유: 명목액인지 할인액인지는 반환값만 봐서는
        구분할 수 없다. 할인율을 받지 않는다는 사실이 유일하게 기계로 확인
        가능한 근거다.
        """
        der = self.make()
        params = set(inspect.signature(der.salvage_value).parameters)
        forbidden = {"discount_rate", "rate", "wacc", "discount"} & params
        assert not forbidden, (
            f"salvage_value() 가 할인율 인자 {forbidden} 를 받습니다. C-5 의 "
            "잔존가치는 명목액이고 할인은 재무 계층(WP-7)의 몫입니다"
        )
        assert params <= {"year"}, (
            f"salvage_value() 의 인자는 `year` 뿐입니다 (실제 {params})"
        )

    # ── 역방향 import 금지 (NFR-208-AC1) ────────────────────────────
    @pytest.mark.contract
    @pytest.mark.req("NFR-208-AC1")
    def test_implements_der_without_engine_knowledge(self) -> None:
        """구현체가 코어 엔진을 import하지 않는다.

        NFR-208-AC1(역방향 import 금지)을 자원 단위로 앞당겨 잡는다.
        import-linter가 CI에서 같은 것을 보지만, 여기서 걸리면 어느 자원이
        원인인지 즉시 드러난다.

        ⚠ **마커를 `FR-101-AC3` 에서 옮겼다 (R38-B2).** 위 독스트링이 v0.1부터
        스스로 `NFR-208-AC1` 이라 적고 있었는데 마커는 `FR-101-AC3` 이었다.
        `AC3` 는 *「신규 자원 클래스가 위 인터페이스만 구현하면 **코어 엔진 수정
        없이 동작**」* 이고, 이 단언은 **자원이 엔진을 import 하는가**만 본다 —
        방향이 반대이며 `NFR-208-AC1` 이 그 방향을 **허용**한다(*「상위 계층은
        하위 계층을 import할 수 있으나 역방향 import는 금지」*). 실제로 이
        검사가 초록불인 채로 `core/engine/rule_based.py::_rule_for()` 가 자원
        태그 셋을 리터럴로 알고 있다. `AC3` 는 이제
        `tests/engine/test_rule_based.py` 가 **엔진을 돌려** 실증한다.

        ⚠ **줄 필터를 씌운다 (R38-D4).** 예전에는 모듈 전문을 문자열로 봐서
        구현의 독스트링·주석이 설명을 위해 `core.engine` 을 언급하기만 해도
        빨간불이 났다 — 재려는 것(「엔진을 import 하는가」)과 재는 방법
        (「본문 어디에도 그 이름이 없다」)이 어긋나 있었다. 짝인
        `test_smoke_wave0.py::test_reference_impl_imports_only_contracts`
        는 처음부터 import 줄만 걸러 그 함정에 서지 않았다 — 그 필터 형태를
        `tests/contract/source_scan.py` 로 모으고 여기서 가져다 쓴다.

        ⚠ **`ast` 로 바꾼다 (R39-A).** 줄 필터는 `line.startswith("import ")`
        형태라 들여쓴 줄, 즉 함수·메서드 본문 안의 지역 import 를 거짓으로
        읽었다 — `PV.capex()` 본문 안에 `from core.cba import BCResult` 를
        심어도 이 검사가 초록불이었다(`.orch/R39/result_ast_import.md` 1-c).
        위반이 통과로 보고되는 조용한 실패이며 R38-D4 의 반대 방향이다.
        `source_scan.imported_module_names()` 가 `ast.walk` 로 트리 전체를
        훑어 지역 import 도 잡는다. 반환 자료형이 원문 줄에서 **모듈 경로
        문자열**로 바뀌어 아래 판정도 `forbidden in line` 부분 문자열 대조에서
        `forbidden in name`(모듈 경로 대조)으로 바뀐다.
        """
        der = self.make()
        assert isinstance(der, DER)

        module = inspect.getmodule(type(der))
        assert module is not None
        source = inspect.getsource(module)
        module_names = imported_module_names(source)
        for forbidden in ("core.engine", "core.cba", "core.casegrid"):
            offending = [name for name in module_names if forbidden in name]
            assert not offending, (
                f"자원 구현이 {forbidden} 를 참조합니다: {offending}. 자원은 "
                "계약만 보고 동작해야 합니다 (FR-101-AC3, NFR-208-AC1)"
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
@pytest.mark.req("FR-101-AC2")
def test_der_cannot_be_instantiated_directly() -> None:
    """추상 메서드가 실제로 강제되는지 — `AC2` 의 메서드 목록이 선언에 그치지
    않는다는 확인이다.

    **마커를 `FR-101-AC3` 에서 옮겼다 (R15).** `AC3` 은 *「신규 자원 클래스가
    위 인터페이스만 구현하면 코어 엔진 수정 없이 동작」* — **확장성**이고,
    그것을 검사하는 것은 실제로 새 자원을 넣어 엔진을 돌려 보는 테스트다.
    이 테스트가 보는 것은 `DER()` 직접 생성이 막히는가, 즉 **`AC2` 가 요구한
    메서드들이 추상으로 걸려 있는가**다.
    """
    with pytest.raises(TypeError):
        DER()  # type: ignore[abstract]


@pytest.mark.contract
@pytest.mark.req("FR-401-AC1")
def test_value_streams_defaults_to_empty_on_the_contract() -> None:
    """`value_streams()` 만 기본 구현을 갖는다 — **방향이 다르기 때문이다.**

    비용 메서드의 기본값 0은 비용을 지우므로 경제성을 좋아 보이게 만든다.
    편익의 기본값 「없음」은 편익을 지우므로 나빠 보이게 만든다. 나빠 보이는
    결과는 검토를 부르고, 좋아 보이는 결과는 그대로 통과한다.
    """
    assert "value_streams" not in getattr(DER, "__abstractmethods__", frozenset()), (
        "value_streams() 는 기본 구현(빈 튜플)을 갖습니다 — 그래야 RC-LD-B0"
        "(부하는 편익을 만들지 않는다)이 상속으로 강제됩니다"
    )
    assert DER.value_streams(None) == ()  # type: ignore[arg-type]


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
@pytest.mark.req("FR-101-AC4")
def test_dispatch_result_carries_unmet_series_per_media() -> None:
    """미충족 계열이 매체별로 있어야 한다 (v1.1 · `RC-HP-X1`).

    v1.0 은 실적 계열만 실었다. 그래서 히트펌프가 열부하를 못 채운 사실이
    자원 내부 자료구조에만 남고 `dispatch()` 를 통과한 시점에 사라졌다 —
    엔진과 리포트에 남는 것은 「열이 조금 덜 나온 정상 결과」뿐이다.
    """
    from core.contracts.der import DispatchResult

    result = DispatchResult.zeros(steps=3)
    for media, _flag in MEDIA:
        assert result.unmet(media) == [0.0, 0.0, 0.0], (
            f"unmet_{media} 계열이 없거나 0으로 초기화되지 않았습니다"
        )
    assert result.total_unmet() == 0.0

    with_unmet = DispatchResult(
        electric=[0.0], heat=[1.0], cool=[0.0], fuel=[0.0],
        unmet_heat=[2.5], notes=("정격 초과",),
    )
    assert with_unmet.total_unmet() == 2.5
    assert with_unmet.notes == ("정격 초과",)

    with pytest.raises(ValueError, match="음수"):
        DispatchResult(electric=[0.0], heat=[0.0], cool=[0.0], fuel=[0.0],
                       unmet_heat=[-1.0])
    with pytest.raises(ValueError, match="길이"):
        DispatchResult(electric=[0.0], heat=[0.0], cool=[0.0], fuel=[0.0],
                       unmet_heat=[0.0, 0.0])

    # `unmet()` 은 이름을 조립해 `getattr` 로 꺼낸다. 없는 매체를 물으면
    # **오류여야 한다** — 0으로 답하면 오타 하나가 「미충족 없음」이 되고,
    # 그 결과는 열이 다 공급된 것과 구별되지 않는다.
    with pytest.raises(AttributeError):
        result.unmet("얼음")


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

    # 이 검사가 요구하는 것은 `len()` 뿐이다(`Sized`). 계열 표현을 `list` 로
    # 좁히면 자원 구현에 «검사를 통과시키기 위한» 변환을 강요하게 되고, 그런
    # 변환은 스텝 수가 맞는지와 무관하게 조용히 사본을 만든다.
    from array import array

    ctx.check_series(array("d", [0.0] * 24), name="배열 계열")
    ctx.check_series(tuple(range(24)), name="튜플 계열")


@pytest.mark.contract
@pytest.mark.req("FR-301-AC3")
def test_dispatch_context_rejects_windows_longer_than_a_year() -> None:
    """한 컨텍스트는 한 해를 넘지 못한다 (v1.1).

    v1.0 은 상한이 없었다. 그래서 `steps=17520` 이 「2년」인지 「한 해를 두 번
    센 것」인지 계약이 답하지 않았고, 그 창에서는 물가상승률·열화가 한 번만
    걸린다 — 2년차 비용이 1년차 값으로 계상되는데 결과는 그럴듯하다.
    """
    annual = steps_per_year(3600)
    DispatchContext(steps=annual, dt=3600, year=1)  # 딱 한 해는 허용
    with pytest.raises(ValueError, match="연간 스텝 수"):
        DispatchContext(steps=annual + 1, dt=3600, year=1)


@pytest.mark.contract
# ↓ v0.15 이관 — 스텝 길이에서 파생되는 안분 계수는 해상도 정합성(AC5)이다.
@pytest.mark.req("FR-301-AC5")
def test_year_fraction_is_the_only_proration_coefficient() -> None:
    """연간 총량을 부분 창에 실을 때 곱하는 계수는 `year_fraction` 하나다.

    자원이 각자 `/365`·`/8760` 을 쓰면 15분 해상도에서 4배 어긋나고, 그
    어긋남은 **부분 창에서만** 나타나므로 8760 골든 시나리오로는 잡히지 않는다.
    """
    day = DispatchContext(steps=24, dt=3600, year=1)
    assert day.annual_steps == 8760
    assert not day.is_full_year
    assert day.year_fraction == pytest.approx(24 / 8760)
    assert day.hours_per_step == pytest.approx(1.0)

    # 같은 하루를 15분 해상도로 보면 스텝 수는 4배지만 **연 비중은 같다** —
    # 이것이 `/365` 나 `/8760` 대신 이 계수를 쓰는 이유다.
    quarter = DispatchContext(steps=96, dt=900, year=1)
    assert quarter.year_fraction == pytest.approx(day.year_fraction)
    assert quarter.hours_per_step == pytest.approx(0.25)

    full = DispatchContext(steps=8760, dt=3600, year=1)
    assert full.is_full_year and full.year_fraction == 1.0


@pytest.mark.contract
def test_year_is_one_based() -> None:
    """분석 연도는 1부터 센다.

    0-base와 1-base가 섞이면 20년 분석이 19년이 되거나 잔존가치가 한 해
    밀린다. 두 오류 모두 결과가 그럴듯해서 눈으로는 잡히지 않는다.
    """
    with pytest.raises(ValueError):
        Year(0)
    assert int(Year(1)) == 1
    assert Money(Decimal("0")) == 0


# ── 정책 파라미터를 자원이 소유하지 않는다 (NFR-202) ────────────────

@pytest.mark.contract
@pytest.mark.req("NFR-202-M1")
def test_all_implementations_share_the_same_vat_default() -> None:
    """자원·공통설비 전건이 `vat_rate` 기본값을 **똑같이** 갖는다.

    **이것이 v1.1 이 메우지 못하고 남긴 구멍이다.** 계약 개정은 「`capex_vat()`
    가 없다」는 문제를 닫았지만 **기본값의 갈림은 그대로 남았다** — 여덟 중
    일곱이 `0.0`, 히트펌프만 `0.1` 이었다. 같은 프로포마에서 히트펌프만 세액이
    잡히고 나머지 열은 0원이 되는데 **어느 쪽도 오류가 아니다.** 물가상승률이
    `2.0`(%)과 `0.02`(소수)로 갈렸던 것과 정확히 같은 유형이며, 그때와 마찬가지로
    자원별 테스트는 각자 자기 기본값으로 오라클을 맞춰 두어 **전부 초록불**이었다.

    **기본값이 `0.0` 인 것은 「세율 0%」가 아니라 「주입되지 않음」이다.** 법정
    세율의 정본은 `docs/assumptions.yaml` 의 `tax.vat_rate` 이고, 자원이 그것을
    들면 세율 개정이 자원 코드 수정이 된다 (NFR-202).

    레지스트리를 순회하는 이유: 손으로 목록을 적으면 자원을 추가할 때 반드시
    빠지고, 빠진 자원은 검사받지 않은 채 초록불로 남는다 (NFR-106 과 같은 이유).
    """
    import core.asset
    import core.der
    from core.contracts.asset import CommonAsset
    from core.contracts.registry import discover

    registry = {**discover(core.der, DER), **discover(core.asset, CommonAsset)}
    assert registry, "레지스트리가 비었습니다 — 순회 검사가 성립하지 않습니다"

    defaults: dict[str, object] = {}
    for tag, cls in registry.items():
        params = inspect.signature(cls.__init__).parameters
        assert "vat_rate" in params, (
            f"{tag} 이 `vat_rate` 를 받지 않습니다 — §13.2.2 C-1 은 부가세 분리를 "
            "자원과 공통설비를 가리지 않고 요구합니다"
        )
        defaults[tag] = params["vat_rate"].default

    distinct = set(defaults.values())
    assert distinct == {0.0}, (
        f"`vat_rate` 기본값이 자원마다 다릅니다: {defaults}. 정책 수치를 자원이 "
        "기본값으로 들면 ⓐ 세율 개정이 자원 코드 수정이 되고(NFR-202) ⓑ 같은 "
        "프로포마에서 자원에 따라 세액이 잡히거나 사라지는데 어느 쪽도 오류로 "
        "보이지 않습니다. 정본은 docs/assumptions.yaml 의 tax.vat_rate 입니다"
    )


# ── FR-104-AC3 수명 도달 처리 (replace / retire) ──────────────────────

@pytest.mark.contract
@pytest.mark.req("FR-104-AC3")
def test_all_implementations_default_to_replace_at_end_of_life() -> None:
    """자원 전건이 `end_of_life_action` 을 받고 **기본값이 `replace`** 다.

    **기본값이 갈리면 프로포마에서 자원마다 교체비가 잡히거나 사라진다.**
    `vat_rate` 가 여덟 중 일곱은 `0.0`, 히트펌프만 `0.1` 이었던 것과 같은
    유형이고, 그때도 자원별 테스트는 각자 자기 기본값으로 오라클을 맞춰 두어
    **전부 초록불**이었다.

    **`replace` 가 기본값인 이유**: `retire` 가 기본이면 교체비가 조용히 빠져
    회수기간이 실제보다 좋아지고 필요 지원액이 과소 산정된다. **틀렸을 때
    결과가 낙관 쪽으로 기우는 값을 기본값으로 두지 않는다.**

    손 목록 대신 레지스트리를 순회한다 — 손으로 적으면 자원을 추가할 때
    반드시 빠지고, 빠진 자원은 검사받지 않은 채 초록불로 남는다.
    """
    import core.der
    from core.contracts.der import EOL_REPLACE
    from core.contracts.registry import discover

    registry = discover(core.der, DER)
    assert registry, "레지스트리가 비었습니다 — 순회 검사가 성립하지 않습니다"

    defaults: dict[str, object] = {}
    for tag, cls in registry.items():
        params = inspect.signature(cls.__init__).parameters
        assert "end_of_life_action" in params, (
            f"{tag} 이 `end_of_life_action` 을 받지 않습니다 — FR-104-AC3 은 "
            "수명 도달 처리의 선택을 자원을 가리지 않고 요구합니다"
        )
        defaults[tag] = params["end_of_life_action"].default

    assert set(defaults.values()) == {EOL_REPLACE}, (
        f"`end_of_life_action` 기본값이 자원마다 다릅니다: {defaults}. "
        "같은 프로포마에서 자원에 따라 교체비가 잡히거나 사라지는데 "
        "어느 쪽도 오류로 보이지 않습니다"
    )


# ── v1.2 ⑥ 가격 신호는 계약이 나른다 ─────────────────────────────────

@pytest.mark.contract
# ↓ v0.15 이관 — 가격 신호 경로는 AC6 의 전제다. **양성(여기)과 음성(아래)을
# 함께 둔다** — 음성만 두면 「무엇이든 거부하는」 구현도 통과한다.
@pytest.mark.req("FR-301-AC6")
def test_price_signal_rides_on_the_context() -> None:
    """요금·연료 단가는 **자원이 아니라 컨텍스트**가 나른다 (계약 v1.2 ⑥).

    자원이 단가를 들면 요금제 개정이 자원 코드 수정이 되고, 그 수정은 자원
    6종에 흩어진다 — §16.1 W-1(파일 단위 배타 소유)이 막으려는 형태다.
    요금 구조 해석은 WP-3(`core/regulation`) 소관이며, 그 **결과인 스텝별
    단가 하나**만 엔진이 여기 싣는다.
    """
    ctx = DispatchContext(
        steps=24,
        dt=3600,
        year=Year(1),
        price_signal_won_per_kwh=[100.0] * 24,
        fuel_price_signal_won_per_kwh=[60.0] * 24,
    )
    assert ctx.require_price_signal() == [100.0] * 24
    assert ctx.require_price_signal(media="fuel") == [60.0] * 24

    # 행수 불일치는 다른 계열과 **같은 경로**로 막힌다. 가격만 별도 검사를
    # 두면 그 검사가 낡을 때 가격 계열만 조용히 통과한다 (FR-301-AC3).
    with pytest.raises(ValueError, match="price_signal_won_per_kwh"):
        DispatchContext(steps=24, dt=3600, year=Year(1),
                        price_signal_won_per_kwh=[100.0] * 23)


@pytest.mark.contract
# ↓ v0.15 이관 — 「0원 대체 없이 오류」가 AC6 의 문면 그대로다.
@pytest.mark.req("FR-301-AC6")
def test_missing_price_signal_stops_instead_of_defaulting_to_zero() -> None:
    """신호가 없으면 **멈춘다.** 0원으로 메우지 않는다 (계약 v1.2 ⑥).

    `ctx.price_signal_won_per_kwh or [0.0] * ctx.steps` 를 자원마다 쓰면 전
    스텝의 단가가 같아져 **「가장 싼 시각」이 사라지고 가격 연동이 「아무
    때나」와 구별되지 않는다.** 그 결과는 총량이 맞으므로 수지 균형
    (NFR-102)도 통과한다 — v1.1 ①(부분 창 해석)에서 만난 «균형식이 볼 수
    없는 오류» 와 같은 종류이며, 판단이 자원에 흩어지면 여섯 개의 서로 다른
    답이 생기고 어느 것도 오류가 아니다.
    """
    ctx = DispatchContext(steps=24, dt=3600, year=Year(1))
    assert ctx.price_signal_won_per_kwh is None
    with pytest.raises(ValueError, match="가격 신호가 없습니다"):
        ctx.require_price_signal()
    with pytest.raises(ValueError, match="가격 신호가 없습니다"):
        ctx.require_price_signal(media="fuel")


#: **이관 부채 — 계약 v1.2 시점의 실측치다.** 이 셋은 요금·시장가격을 자원
#: 생성자가 들고 있는 잔여분이며, `status.md` 「미해결」이 조치 시점을
#: *"8.0 또는 5.0 착수 전"* 으로 적어 둔 항목이다. 8.0(편익)이 편익 산식의
#: 소유권을 WP-4로 확정할 때 함께 이관한다 — `avoided_price` 는 운전 결정이
#: 아니라 **편익 화폐화** 이므로 ctx 가 아니라 WP-4 로 가는 것이 맞고,
#: 그 판단은 8.0 착수 시점에 내려진다.
#:
#: **이 목록을 늘리는 방향으로 고치지 말 것.** 새 요금 인자를 자원에 두면
#: 이 검사가 즉시 빨개진다. 그것이 이 목록의 유일한 목적이다.
KNOWN_TARIFF_DEBT: dict[str, set[str]] = {
    "EV_V2G": {"avoided_price_won_per_kwh"},
    "HeatPump": {"price_profile_won_per_kwh", "elec_price_won_per_kwh"},
}


@pytest.mark.contract
@pytest.mark.req("NFR-202-M1")
def test_no_new_tariff_parameter_enters_a_resource() -> None:
    """자원이 새 요금·시장가격 인자를 갖는 것을 막는다 (계약 v1.2 ⑥).

    **왜 「0건」이 아니라 실측 목록인가.** 지금 0건을 요구하면 이 검사는
    켜는 즉시 빨간불이고, 통과시키려면 `RC-HP` · `RC-EV` 검증 케이스를
    함께 고쳐야 한다 — 그것은 8.0 이 편익 소유권을 확정한 뒤에 할 일이다.
    2.7 매핑 게이트에서 「미매핑 0건」을 요구하지 않은 것과 같은 판단이다.
    **드러난 부채는 부채이고, 드러나지 않는 부채가 문제다.**

    `price_linked_hours` 처럼 **가격이 아닌** 운전 파라미터는 대상이 아니다.
    이름에 `price` 가 들어간다고 요금인 것은 아니며, 그렇게 판정하면 정당한
    인자가 걸려 검사가 꺼진다 — 이 저장소가 여섯 번 만난 형태다. 판정은
    「원/kWh 단가를 자원이 소유하는가」이고, `capex_unit_won_per_kwh` 같은
    **비용 단가는 자원의 것이 맞다** (§13.2.2 C-1~C-3).
    """
    import core.der
    from core.contracts.registry import discover

    found: dict[str, set[str]] = {}
    for tag, cls in discover(core.der, DER).items():
        params = inspect.signature(cls.__init__).parameters
        hits = {
            name
            for name in params
            if name.endswith("_won_per_kwh")
            and not name.startswith(("capex_", "variable_om_", "fixed_om_",
                                     "replacement_", "degradation_compensation_"))
        }
        if hits:
            found[tag] = hits

    assert found == KNOWN_TARIFF_DEBT, (
        f"자원이 소유한 요금 인자가 실측 부채와 다릅니다.\n"
        f"  실측: {found}\n  기대: {KNOWN_TARIFF_DEBT}\n"
        "늘었다면 요금 구조가 자원 코드로 새고 있습니다 — 단가는 "
        "`DispatchContext.price_signal_won_per_kwh` 로 받습니다(계약 v1.2 ⑥). "
        "줄었다면 이관이 진행된 것이므로 이 목록을 함께 줄이십시오"
    )
