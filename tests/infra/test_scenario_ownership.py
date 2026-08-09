"""3.1 / DV-11 — Scenario 소유권 음성 테스트 (§7.1 O-1).

**이 테스트는 다른 테스트와 방향이 반대다.** 보통의 테스트는 "있어야 할 것이
있다"를 검사하지만, 여기서는 "없어야 할 것이 **없어야** 한다"를 검사한다.

왜 필요한가 — §7.1 O-1 의 기계 검사
-----------------------------------
spec v0.2 까지 `Scenario` 와 `AssumptionSet` 양쪽에 같은 분류의 필드가 있었다.
이 상태에서는 FR-202 (전제 동일성 시스템적 보장) 이 깨진다:

    · 어느 쪽이 우선인지 실행 시점에 갈린다.
    · 갈린 값으로 계산해도 결과는 그럴듯하다 (에러로 보이지 않는다).
    · 스프레드시트에서 자주 생기는 "셀 A1 과 B1 중 어디가 진짜?" 문제의
      DB 판이다.

§7.1 O-1 은 이것을 **스키마 수준에서** 막는다:

    Scenario 는 regulation_profile_id · tariff_table_id · discount_rate ·
    analysis_years 를 **보유하지 않는다** — 전부 assumption_set_id 를 경유.

금지 대상 분류 (FR-601-AC2.*) 와 대표 필드명
-------------------------------------------
    AC2.cost          설비단가·시공비·O&M·교체비
    AC2.performance   이용률·COP·RTE·수명·열화율
    AC2.market_price  SMP·REC·PPA 단가
    AC2.finance       할인율·분석기간·건설기간
    AC2.escalation    물가·전기·연료·인건비 상승률
    AC2.reference     규제 프로파일·요금표 참조

오라클: 1 순위 (해석적 — 스키마 선언 자체가 정답). 허용오차 해당 없음.

COMMON.md §8 (자기검사 함정)
---------------------------
이 테스트 자체가 선언(denylist)에 의존한다. 그래서 **위반을 실제로 심어
checker 가 그것을 잡는지** 확인한다 — 잡지 못하면 denylist 은 빈 약속이다.
역으로, 정당한 필드(incentive_scheme_id 등) 가 오판되지 않는지도 함께 본다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from infra.orm import CommonAsset, DERInstance, Scenario

# ── §7.1 O-1 / DV-11 — Scenario 가 가질 수 없는 필드 전건 ──────────────
#
# 각 항목은 (AC, 필드명) 쌍이다. AC 는 그 필드가 침범한 전제 분류(FR-601-AC2.*).
# 점 표기 AC 는 점 표기 그대로 — COMMON.md §4 「전건 나열, ~ 로 줄이지 않는다」.
#
# 이 목록이 단순한 "연습용 예시" 가 아니라 **스키마 계약의 기계적 표현** 이라는
# 점에 유의. 새 항목이 AC2.* 아래로 추가되면 이 표도 같이 늘어나야 한다 —
# 그렇지 않으면 새 위반이 초록불로 통과한다.
FORBIDDEN_FIELDS: tuple[tuple[str, str], ...] = (
    # AC2.cost — 설비단가·시공비·O&M·교체비. Scenario 가 단가를 들고 있으면
    # 자원 종류·규격에 따라 달라져야 하는 값을 단일 시나리오에 묶어버린다.
    ("FR-601-AC2.cost", "capex"),
    ("FR-601-AC2.cost", "capex_unit"),
    ("FR-601-AC2.cost", "installation_cost"),
    ("FR-601-AC2.cost", "opex_unit"),
    ("FR-601-AC2.cost", "opex_rate"),
    ("FR-601-AC2.cost", "replacement_cost"),
    ("FR-601-AC2.cost", "fixed_om_annual"),
    # AC2.performance — 이용률·COP·RTE·수명·열화율. 자원 파라미터는
    # DERInstance 가 소유한다 (§7.1 표).
    ("FR-601-AC2.performance", "performance_ratio"),
    ("FR-601-AC2.performance", "cop"),
    ("FR-601-AC2.performance", "rte"),
    ("FR-601-AC2.performance", "lifetime"),
    ("FR-601-AC2.performance", "degradation_rate"),
    # AC2.market_price — SMP·REC·PPA 단가. 전제가 시장 단가를 들면 여러
    # 시나리오가 서로 다른 SMP 를 쓰는 일이 벌어진다 (FR-202 위반).
    ("FR-601-AC2.market_price", "smp_price"),
    ("FR-601-AC2.market_price", "rec_price"),
    ("FR-601-AC2.market_price", "ppa_price"),
    # AC2.finance — 할인율·분석기간·건설기간. spec §7.1 O-1 이 이름을 찍어서
    # 금지한 4 필드중 두 개가 이 분류에 속한다.
    ("FR-601-AC2.finance", "discount_rate"),
    ("FR-601-AC2.finance", "analysis_years"),
    ("FR-601-AC2.finance", "construction_period"),
    # AC2.escalation — 상승률. AC3 가 전기요금 인상률을 별도 항목으로 요구하므로
    # 분류 자체가 Scenario 가 들고 있을 수 없다.
    ("FR-601-AC2.escalation", "inflation_rate"),
    ("FR-601-AC2.escalation", "electricity_escalation"),
    ("FR-601-AC2.escalation", "fuel_escalation"),
    ("FR-601-AC2.escalation", "labor_escalation"),
    # AC2.reference — 규제 프로파일·요금표 참조. O-1 이 이름을 찍어서 금지한
    # 나머지 두 필드. 이 둘이 무너지면 AssumptionItem.value_type=ref 경로가
    # 형식적으로만 쓰이고 Scenario 직접 참조가 은밀히 살아남는다.
    ("FR-601-AC2.reference", "regulation_profile_id"),
    ("FR-601-AC2.reference", "tariff_table_id"),
)


# ── §7.1 O-1 핵심: 이름으로 찍어 금지 — 전건 나열 ─────────────────────


@pytest.mark.req("FR-601-AC1")
@pytest.mark.req("FR-601-AC2.cost")
@pytest.mark.req("FR-601-AC2.performance")
@pytest.mark.req("FR-601-AC2.market_price")
@pytest.mark.req("FR-601-AC2.finance")
@pytest.mark.req("FR-601-AC2.escalation")
@pytest.mark.req("FR-601-AC2.reference")
def test_scenario_has_no_forbidden_fields() -> None:
    """DV-11 — Scenario 가 FR-601-AC2.* 분류의 필드를 하나라도 가지면 실패.

    `Scenario` 의 모든 매핑 컬럼을 모아서 금지명과 교차한다. denylist 방식은
    **새 위반을 잡지 못한다**는 한계가 있어 아래 `test_forbidden_field_scanner`
    (패턴) 과 쌍으로 운영한다.
    """
    column_names = _scenario_column_names()
    for ac, field in FORBIDDEN_FIELDS:
        assert field not in column_names, (
            f"DV-11 위반: Scenario.{field} 가 정의되어 있습니다 ({ac} 소유). "
            "이 값은 AssumptionSet 을 경유해야 합니다 (§7.1 O-1). 두 곳에 같은 "
            "분류의 필드가 있으면 어느 쪽이 정본인지 실행 시점에 갈립니다."
        )


@pytest.mark.req("FR-601-AC1")
@pytest.mark.req("FR-601-AC2.cost")
@pytest.mark.req("FR-601-AC2.performance")
@pytest.mark.req("FR-601-AC2.market_price")
@pytest.mark.req("FR-601-AC2.finance")
@pytest.mark.req("FR-601-AC2.escalation")
@pytest.mark.req("FR-601-AC2.reference")
def test_forbidden_field_scanner_catches_pattern_violations() -> None:
    """DV-11 보조 — denylist 외의 필드명도 패턴으로 잡는다.

    새 위반(`smp_2024` 같은)이 생겨도 denylist 에 없으면 첫 테스트는 못 잡는다.
    이 테스트는 컬럼명에 금지 분류 키워드가 들어 있으면 실패시킨다.

    역방향 함정도 있다 — `allocation_rule` 같은 정당한 필드가 `rate` substring
    을 포함해 오판되면 안 된다. 그래서 allowlist 로 정당 필드를 명시한다.
    """
    allowed = {
        # §7.2 가 Scenario 에 명시한 전부
        "id", "project_id", "assumption_set_id", "name", "version",
        "definition_json",
    }
    forbidden_patterns = (
        "rate", "escalation", "capex", "opex", "price", "smp", "rec_",
        "ppa", "cop", "rte", "lifetime", "degradation", "regulation_",
        "tariff_", "analysis_year", "discount", "inflation",
    )
    for name in _scenario_column_names():
        if name in allowed:
            continue
        lower = name.lower()
        for pat in forbidden_patterns:
            assert pat not in lower, (
                f"DV-11 의심: Scenario.{name} 가 금지 패턴 '{pat}' 를 포함합니다. "
                "정당한 필드라면 `allowed` 에 추가하고 왜 허용되는지 적으십시오 — "
                "allowlist 없이 패턴만 쓰면 새 정당 필드가 오판된다."
            )


# ── §7.1 O-1 — 정당한 통로는 존재해야 한다 ───────────────────────────
#
# Scenario 가 아무 것도 들고 있지 않으면 위 두 테스트는 자명하게 통과한다.
# 그 상태는 O-1 이 의도한 것이 아니다 — assumption_set_id 로 전제에 닿는
# 경로가 있어야 한다. 그래서 "없어야 할 것이 없다" 와 "있어야 할 것이 있다"
# 를 함께 검사한다.


@pytest.mark.req("FR-601-AC1")
@pytest.mark.req("FR-601-AC2.reference")
def test_scenario_reaches_assumptions_only_via_assumption_set_id() -> None:
    """O-1 — Scenario 는 전제로 `assumption_set_id` 하나로만 닿는다.

    이 컬럼이 없으면 시나리오가 자기 전제를 참조할 수 없다. 그 상태로
    음성 테스트 두 개가 통과하면 "아무것도 안 들고 있어서 통과" 인데,
    그것은 스키마가 깨진 것이다.
    """
    assert "assumption_set_id" in _scenario_column_names(), (
        "Scenario.assumption_set_id 가 없습니다 — 이것이 유일한 전제 참조 "
        "경로입니다 (§7.1 O-1). 이 컬럼이 빠지면 음성 테스트는 자명해진다."
    )


# ── COMMON.md §8 — checker 가 진짜 잡는가 (위반 심기) ─────────────────
#
# 이 테스트 시리즈는 자기 자신을 검사하는 구조다. denylist·패턴 checker 가
# 실제 위반을 잡지 못하면 모든 테스트가 초록불이며 아무것도 검증하지 않는다.
# 그래서 **위반을 의도로 심어 checker 를 돌려 본다**.
#
# 주의: `Scenario` 자체를 건드리면 다른 테스트가 깨진다. 별도 Base 위에
# "오염된 더미 Scenario" 를 만들어 checker 함수에 먹인다.


class _ContaminatedBase(DeclarativeBase):
    """위반 심기용 별도 메타데이터. Scenario 의 메타데이터를 더럽히지 않는다."""


def _contaminated_scenario() -> type:
    """금지 필드를 일부러 단 Scenario 모조 클래스.

    각 분류(AC2.*)에서 한 필드씩을 골라 한 클래스에 다 단다. 한 클래스에
    전부 달면 패턴 한 번에 여러 AC 위반이 잡혀서 "위반을 심었는가" 검증이
    한방에 끝난다.
    """

    class _BadScenario(_ContaminatedBase):
        __tablename__ = "bad_scenario"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        # AC2.cost
        capex: Mapped[int] = mapped_column(Integer)
        # AC2.performance
        rte: Mapped[int] = mapped_column(Integer)
        # AC2.market_price
        smp_price: Mapped[int] = mapped_column(Integer)
        # AC2.finance — O-1 이 이름을 찍은 것
        discount_rate: Mapped[int] = mapped_column(Integer)
        analysis_years: Mapped[int] = mapped_column(Integer)
        # AC2.escalation
        inflation_rate: Mapped[int] = mapped_column(Integer)
        # AC2.reference — O-1 이 이름을 찍은 것
        regulation_profile_id: Mapped[int] = mapped_column(Integer)
        tariff_table_id: Mapped[int] = mapped_column(Integer)
        # 합법 필드 (이것이 잡히면 checker 가 오판하는 것)
        assumption_set_id: Mapped[int] = mapped_column(Integer)

    return _BadScenario


def test_checker_detects_planted_violations() -> None:
    """COMMON.md §8 — 위반을 심었을 때 checker 가 실제로 걸리는지 확인.

    이 단언이 실패하면 denylist 가 빈 약속이다 — 어느 필드가 빠졌는지 이름을
    알려준다. "checker 가 통과했다" 와 "checker 가 무언가를 검사했다" 는 다르다.
    """
    bad = _contaminated_scenario()
    bad_columns = {c.name for c in bad.__table__.columns}  # type: ignore[attr-defined]

    # 1) denylist — 심어 둔 위반 전건이 잡혀야 한다.
    caught_by_denylist: set[str] = set()
    for _ac, field in FORBIDDEN_FIELDS:
        if field in bad_columns:
            caught_by_denylist.add(field)
    expected_caught = {
        "capex", "rte", "smp_price", "discount_rate", "analysis_years",
        "inflation_rate", "regulation_profile_id", "tariff_table_id",
    }
    assert expected_caught.issubset(caught_by_denylist), (
        f"denylist 가 심어 둔 위반을 못 잡았습니다 — 빠진 항목: "
        f"{expected_caught - caught_by_denylist}. FORBIDDEN_FIELDS 를 "
        "갱신하십시오."
    )

    # 2) 패턴 — denylist 외에도 이름에 키워드가 들면 잡아야 한다.
    forbidden_patterns = (
        "rate", "escalation", "capex", "opex", "price", "smp", "rec_",
        "ppa", "cop", "rte", "lifetime", "degradation", "regulation_",
        "tariff_", "analysis_year", "discount", "inflation",
    )
    caught_by_pattern: set[str] = set()
    for name in bad_columns:
        if name in {"id", "assumption_set_id"}:
            continue
        if any(pat in name.lower() for pat in forbidden_patterns):
            caught_by_pattern.add(name)
    assert expected_caught.issubset(caught_by_pattern), (
        f"패턴 checker 가 심어 둔 위반을 못 잡았습니다 — 빠진 항목: "
        f"{expected_caught - caught_by_pattern}"
    )


def test_checker_does_not_falsely_flag_legitimate_scenario() -> None:
    """COMMON.md §8 반대 방향 — 정당한 필드를 오판하지 않는지 확인.

    `assumption_set_id` 같은 합법 필드가 패턴에 걸리면 안 된다. allowlist 없는
    패턴 checker 는 새 정당 필드를 죽인다 — 이름에 'rate' 만 들어가도 경고하므로.
    """
    legit_columns = _scenario_column_names()
    forbidden_patterns = (
        "rate", "escalation", "capex", "opex", "price", "smp", "rec_",
        "ppa", "cop", "rte", "lifetime", "degradation", "regulation_",
        "tariff_", "analysis_year", "discount", "inflation",
    )
    # Scenario 의 실제 컬럼이 pattern checker 를 통과하는지 직접 돌려 본다.
    for name in legit_columns:
        for pat in forbidden_patterns:
            assert pat not in name.lower(), (
                f"정당 필드 Scenario.{name} 가 패턴 '{pat}' 에 오판 걸렸습니다. "
                "패턴을 좁히거나 allowlist 를 점검하십시오 — 설명을 고쳐 통과시키면 "
                "다음 사람이 같은 위반을 다시 짓는다."
            )


# ── 형제 모델 — incentive_scheme_id 가 DERInstance·CommonAsset 에 있는 것은 합법 ──
#
# §7.2 는 DERInstance 와 CommonAsset 모두 `incentive_scheme_id` 를 들게 한다.
# 이것은 전제가 아니라 **자원에 할당된 지원 조건** 이므로 Scenario 가 아닌
# 자원 레벨에 있어야 한다 (§7.1 소유권 표). 이 테스트는 "incentive_scheme_id
# 를 Scenario 밖에서 찾지 못했다" 가 checker 의 한계로 이어지지 않는지 확인한다.


def test_incentive_scheme_lives_on_instances_not_scenario() -> None:
    """DERInstance·CommonAsset 은 incentive_scheme_id 를 가져야 한다 (§7.2).

    Scenario 밖으로 옮기려다 보면 `incentive_scheme_id` 가 `_rate`/`_price` 패턴
    없이 자원에 붙어 있어야 한다는 것을 같이 고정해 둔다.
    """
    assert "incentive_scheme_id" in {
        c.name for c in DERInstance.__table__.columns
    }
    assert "incentive_scheme_id" in {
        c.name for c in CommonAsset.__table__.columns
    }
    assert "incentive_scheme_id" not in _scenario_column_names(), (
        "incentive_scheme_id 는 자원 단위 필드입니다 (§7.1·§7.2). "
        "Scenario 가 들고 있으면 여러 자원에 서로 다른 지원 조건을 못 건다."
    )


# ── helpers ──────────────────────────────────────────────────────────


def _scenario_column_names() -> set[str]:
    """Scenario 의 컬럼명 집합. 테스트 본문에서 직관적으로 쓰기 위한 얇은 통로."""
    return {c.name for c in Scenario.__table__.columns}
