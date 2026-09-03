"""§7.3 대장의 규칙이 **실제 코드에서 구조로 던져지는가** — NFR-303-M1 · DV-14.

**이 파일이 붙드는 것은 `ValidationError` 가 아니다.** 그것은
`test_validation_contract.py` 가 이미 붙든다 — 다만 **그 파일은 예외를 손으로
만들어 검사한다.** 그래서 `rule="DV-2"` 가 그 안에 두 번 나오지만 `DV-2` 를
실제로 던지는 코드는 저장소에 한 줄도 없다. 사람이 읽으면 「DV-2 가 검증됐다」로
보이고, 추적표도 그렇게 센다.

R21 실측 — 대장 14규칙 중 **실제 코드가 `rule=` 로 던지는 것은 넷**이다:

    DV-4   infra/tsstore.py                 (R20 전환)
    DV-12  core/valuestream/exclusion_table.py
    DV-13  core/contracts/valuestream.py
    DV-14  core/contracts/der.py            ← R21 이 전환. 그전에는 맨 ValueError

`DV-14` 는 **강제하는 코드가 처음부터 있었다**(`_check_operating_mode`). 없던
것은 규칙 ID 를 나르는 형태였고, 그래서 `tests/der/test_pv.py` 의 독스트링이
*「선언 목록 밖의 운전 방법은 거부한다 (DV-14)」* 라 적으면서도 그 주장을
기계가 확인할 방법이 없었다. **주장은 독스트링에 있고 근거는 없었다.**

아래 둘째 테스트가 대장을 «던지는 것»과 «아직 아닌 것»으로 **가른다.** 열다섯
번째 규칙이 대장에 들어오면 그 테스트가 빨간불이 되어 분류를 요구한다 — 그것이
「대장에는 있는데 아무도 던지지 않는 규칙」이 조용히 늘지 않게 하는 유일한
방법이다 (`core/contracts/validation.py` 독스트링이 예고한 형태).
"""

from __future__ import annotations

import ast
from itertools import combinations
from pathlib import Path

import pytest

from core.contracts.validation import DV_RULES, ValidationError
from tests.contract.test_smoke_wave0 import ReferencePV

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 배포 코드의 뿌리. 테스트는 여기 들지 않는다 — 테스트가 손으로 만든
#: `ValidationError` 는 「코드가 그 규칙을 던진다」의 근거가 아니다.
DEPLOY_ROOTS = ("core", "infra", "app", "web")


class ModelessPV(ReferencePV):
    """운전 방법을 **선언하지 않은** 자원 — 셋째 거부 경로를 위한 것.

    `OPERATING_MODES` 가 비었는데 `operating_mode` 를 받으면 그 값은 「선언
    목록에 속한다」를 만족할 수 없다. 이 경로를 빼면 남은 둘만 검사되고, 그
    사이 이 분기가 맨 `ValueError` 로 되돌아가도 초록불이다.
    """

    OPERATING_MODES = ()

# ── 대장의 분할 — **이 둘의 합집합이 대장 전체여야 한다** ──────────────────
#
# `실제로 던진다` 의 뜻: 배포 코드(`core/`·`infra/`·`app/`·`web/`)의 어느
# 지점이 `ValidationError(..., rule="DV-N")` 을 올리고, **그것을 실제 진입점으로
# 발동시키는 테스트가 있다.** 예외를 손으로 만들어 보는 것은 여기에 들지 않는다.
THROWN_BY_REAL_CODE: dict[str, str] = {
    # ↓ R24 WP-34D — `core/incentive/schemas.py` 가 보조금+융자 초과를 실제로 던진다.
    "DV-1": "tests/incentive/test_incentive.py::"
            "test_dv1_subsidy_plus_loan_exceeds_capex_raises_validation_error",
    # ★ **`DV-4` 는 R24 인수까지 규칙의 「절반」만 붙들고 있었다 — R25 에 닫았다.**
    # 원문은 「시계열 행수 = 8760 (또는 35,040), **윤년 처리 규칙 명시**」인데
    # 강제되는 것은 앞쪽뿐이었다. 저장소 전체에 `8784`·`35136`·`isleap` 이
    # **0건**이었고, 윤년을 말하는 것은 「윤년을 쓰지 않는다」는 모듈 내부 주석
    # 둘뿐이라 **자기 모듈의 사정**이었지 규칙의 선언이 아니었다. 게다가
    # `tests/infra/test_tsstore.py` 가 `year=2024`(윤년)에 8760행을 쓰고 통과하는
    # 것을 여러 곳에서 붙들고 있었다 — **규칙 없이 한쪽 결과만 고정한 형태.**
    #
    # 「명시」는 던지는 일이 아니라 **선언하는 일**이므로 닫는 방법도 달랐다.
    # `core/contracts/units.py` 의 `LEAP_YEAR_POLICY` 가 규칙을 선언하고,
    # `tests/contract/test_leap_year_policy.py` 가 **선언의 실재와 그것이 참인지**
    # 를 붙든다(문면 · 스텝 수가 연도를 못 받는다 · 윤년 행 수가 허용에 없다).
    # 366일 자료를 가져온 사람에게 그 문면이 닿는지는
    # `tests/infra/test_tsstore.py::test_write_rejects_leap_year_rows_and_hands_over_the_policy`
    # 가 본다. 변이 6종 전건 확인.
    "DV-4": "tests/infra/test_tsstore.py::test_write_rejects_wrong_row_count_"
            "carries_field_reason_action",
    "DV-12": "tests/contract/test_exclusion_rules_contract.py",
    "DV-13": "tests/contract/test_payer_structure_contract.py::"
             "test_structure_absent_falls_back_and_is_refused_when_unspecified",
    "DV-14": "tests/contract/test_dv_rule_enforcement.py::"
             "test_dv14_is_thrown_by_the_real_constructor",
    # ↓ R58 — `core/cba/baseline.py::get_baseline_branch` 가 「자가용 집합자원화」
    # 갈래를 실제로 던져 거부한다. 그 갈래는 **구분 계측 선언**(판정 정본 §2)과
    # **포기분 비용 항**(§4④ 대칭성)이 함께 서야 평가할 수 있는데 둘 다 없다 —
    # **「평가할 수 없다」를 0 으로 채우지 않기 위한 규칙이다.**
    "DV-15": "tests/cba/test_baseline.py::test_pool_branch_is_rejected",
    # ↓ R22 — `core/der/ess.py` 생성자가 실제로 던진다. **R21 이 「대장에는
    # 있는데 던지는 코드가 한 줄도 없다」고 짚었던 바로 그 둘**이다.
    "DV-2": "tests/der/test_ess.py::"
            "test_constructor_validation_errors_carry_field_reason_action",
    "DV-3": "tests/der/test_ess.py::"
            "test_constructor_validation_errors_carry_field_reason_action",
    # ↓ R24 — `core/casegrid/grid.py` 가 결합 집합 길이 불일치를 실제로 던진다.
    "DV-9": "tests/casegrid/test_dv9_dv10.py::"
            "test_dv9_mismatched_coupled_set_lengths_raise_structured_error",
    # ↓ R24 — `core/casegrid/execution.py` 의 `run_cases()` 가 확인 없이는
    # 러너를 부르기 전에 거부한다. 그전에는 `RunPlan.requires_confirmation`
    # 깃발만 계산되고 아무도 읽지 않았다.
    #
    # ⚠ **R24 인수 기록 — 임계치의 출처가 둘이다.** `CaseGrid` 는 자기
    # `confirmation_threshold` 를 갖고 `execution_plan()` 에 넘기는데,
    # `run_cases()` 는 케이스 목록만 받으므로 **호출측이 `threshold=` 를 넘기지
    # 않으면 기본 500 을 쓴다.** 그리드를 10 으로 설정해도 20건이 확인 없이
    # 돈다는 뜻이다 — 규칙 문면의 「기본 500」은 지켜지지만 **사용자가 바꾼
    # 임계치는 지켜지지 않는다.** 지금은 그리드에서 실행으로 잇는 배포 경로가
    # 아예 없어(앱·웹에 `run_cases` 호출 0곳) 드러날 자리가 없다. **그 경로를
    # 놓는 라운드가 두 값을 하나로 이어야 한다.**
    "DV-10": "tests/casegrid/test_dv9_dv10.py::"
             "test_dv10_rejects_over_threshold_execution_without_confirmation_before_running",
    # ↓ R24 — `core/cba/proforma.py` 의 `check_analysis_period()` 가 분석기간
    # 상한(최장 자원 수명의 2배)을 실제로 던진다. 신설 검사(그전에는 이 자리에
    # 강제 코드 자체가 없었다) — WP-34C.
    #
    # ✔ **R30 — 배선됐다. R24 가 적어 둔 「아무도 부르지 않는다」는 이제 틀렸다.**
    # `core/casegrid/e2e_runner.py::run_single_case_e2e` 가 자원을 세운 직후,
    # **디스패치·편익·CBA 어느 것도 돌기 전에** 이 함수를 부른다. 배선을 붙드는
    # 것은 `tests/casegrid/test_e2e_analysis_period_wiring.py` 다 — 함수 층만
    # 검사하면 배선이 되돌아가도 전건 초록불이기 때문이다(R27 이 `DV-12` 에서
    # 만난 형태이며 이것이 같은 자리의 둘째다).
    #
    # ⚠ **그래도 「강제된다」로 다 읽지 말 것.** 닫힌 것은 *「케이스 실행이
    # 상한을 지난다」* 이고, **사용자가 고르는 분석기간이 어느 층에 사는가는
    # 여전히 미결**이다(자연스러운 자리인 `Scenario` 를 `DV-11` 이 명시적으로
    # 금지한다). 그 결정이 나면 그 층에서도 이 함수를 지나야 한다 —
    # `status.md` 「미해결」에 남아 있다.
    "DV-5": "tests/cba/test_proforma.py::"
            "test_check_analysis_period_rejects_over_double_the_longest_lifetime",
    # ↓ R24 — `core/assumption/catalog.py` 의 `escalate_with_detail()` 이
    # base_year 에서 연도를 못 읽으면 실제로 던진다(「기준연도 보유」는 필수
    # 필드로 이미 타입이 강제 — ENFORCED_WITHOUT_A_THROW 아님, DV-8 의
    # 「물가 조정」 절반이 여기서 구조로 던지므로 THROWN 이 맞다) — WP-34C.
    "DV-8": "tests/assumption/test_catalog.py::"
            "test_escalate_with_detail_rejects_unparseable_base_year",
    # ↓ R31 — 원문은 선언 자리를 **`AssumptionSet` 수준**으로 못 박고 **전 항목에
    # 강제**하라고 한다. 둘 다 실제로 던진다: 대장에 최상위 `price_basis` 선언이
    # 없으면 `load_from_yaml` 이 거부하고(1회 선언), 항목의 `value_unit` 이
    # 실질/명목을 다시 말하면 집합 생성이 거부한다(전 항목에 강제).
    #
    # ⚠ **값이 집합 선언과 같아도 거부한다.** 같은 사실이 두 곳에 있으면 집합
    # 선언을 바꿀 때 항목 문면이 따라오지 않고, 바꾼 사람은 성공했다고 믿는다 —
    # R31 이 실제로 그 사본 하나를 대장에서 지웠다
    # (`escalation.electricity_tariff` 의 `value_unit` 이 「%/년 (명목)」이었다).
    "DV-7": "tests/assumption/test_price_basis.py::"
            "test_an_item_that_redeclares_the_basis_is_refused",
    # ↓ R31 — **이 규칙은 「던진다」의 뜻이 다르다.** 원문은 *「요금표 유효기간이
    # 분석연도를 포함 **(미포함 시 경고 후 최근접 표)**」* 이므로 미포함은 거부가
    # 아니라 **폴백**이다(R24 가 사본의 절단 때문에 「거부」로 읽었던 자리).
    #
    # 그래서 던지는 자리는 **폴백조차 성립하지 않는 경우**다 — 요금표가 하나도
    # 없으면 대체할 대상이 없고, 빈 표로 계산하면 요금이 0 원으로 나와 「요금표가
    # 없다」가 「요금이 없다」와 구별되지 않는다.
    #
    # 폴백 자체(경고 후 최근접, 과거 방향 우선)는
    # `tests/regulation/test_tariff_fallback.py` 가 전건 붙든다.
    "DV-6": "tests/regulation/test_tariff_fallback.py::"
            "test_no_table_at_all_is_refused_not_silently_zero",
}

#: 대장에 있으나 **아직 구조로 던지는 코드가 없는** 규칙.
#: 줄어들면 위 표에 옮긴다. `NOT_YET` 이 비는 날 이 상수를 지운다.
NOT_YET_THROWN: frozenset[str] = frozenset({
    # ★ **`DV-7` 이 여기 있었다. R31 이 옮겼다 — 그리고 이 파일이 그것을
    # 스스로 잡았다.** R22 가 놓은 `ast` 대조(배포 코드의 `rule=` 상수를 뽑아
    # 이 표와 맞춘다)가 `price_basis` 강제를 배선한 순간 빨간불을 냈다 —
    # 분류가 뒤처지는 방향을 붙드는 것이 그 검사의 목적이었고, 실제로 그렇게
    # 동작했다. R22 가 *「래칫이 자기가 막으려던 드리프트를 못 잡았다」* 를
    # 고친 값이 여기서 나왔다.
    #
    # R24 가 남긴 판정(「발동시킬 사건이 없는 것이 아니라 강제가 아직 없다」)은
    # 정확했다. 없던 것은 **선언할 자리**였고, R31 이 그것을 만들었다 —
    # 계약의 `PriceBasis`(기본값 없음) · `AssumptionSet.price_basis` ·
    # ORM 컬럼(NOT NULL + CHECK) · 대장 최상위 `price_basis: 명목`.
    # ★★★ **`DV-6` 이 마지막이었고 R31 이 옮겼다 — 이 집합은 이제 비어 있다.**
    # 이 상수를 지우라고 아래 주석이 적어 두었으나 **지우지 않는다**: 열다섯 번째
    # 규칙이 대장에 들어올 때 「아직 던지지 않는다」를 놓을 자리가 필요하고, 자리가
    # 없으면 그 규칙이 `THROWN_BY_REAL_CODE` 에 억지로 들어가거나 분류에서 빠진다.
    # `test_every_catalogue_rule_is_classified` 가 그때 빨간불을 낸다.
})

#: ★★ **던지지 않지만 이미 강제되는** 규칙 — R24 가 신설한 세 번째 분류.
#:
#: 위 둘만 있던 동안 `DV-7`·`DV-11` 은 `NOT_YET_THROWN` 에 있었다. 그 이름이
#: 뜻하는 것은 **「아직 아무도 강제하지 않는다」**인데 **둘 다 강제되고 있었다.**
#: `DV-11` 은 위반을 심어서 확인하는 음성 테스트까지 있다.
#:
#: **이것은 이 저장소가 고치러 온 결함의 거울상이다.** 지금까지 찾은 열여섯 건은
#: 전부 「검사가 실제보다 **넓게** 주장한다」였는데, 이 표는 **좁게** 주장하면서
#: 강제 사실을 숨겼다. 다음 라운드가 이 표를 읽으면 「손대지 않았다」로 보고
#: **이미 있는 것을 다시 만들려 한다.**
#:
#: 여기 드는 조건은 **런타임 사건이 없다**는 것이다 — 발동시킬 순간이 없으므로
#: `ValidationError` 를 놓을 자리가 없다. 「귀찮아서 안 던진다」는 여기 들지
#: 않는다. 그 판정 근거를 아래 두 경로로 적고, 검사가 **경로의 실재**를 본다.
#:
#:     규칙 → (강제하는 자리, 그것을 붙드는 테스트)
ENFORCED_WITHOUT_A_THROW: dict[str, tuple[str, str]] = {
    # `Scenario` 가 금지 필드를 **갖지 않는다**. 클래스에 필드가 없는 것은
    # 실행 중에 일어나는 사건이 아니므로 던질 순간이 없다. **원문이 「스키마
    # 검사로 강제」라고 직접 적고 있어**(R24 가 사본을 원문으로 되돌리며
    # 드러났다) 이 분류는 규칙 문면 자신이 뒷받침한다.
    "DV-11": ("infra/orm/scenario.py", "tests/infra/test_scenario_ownership.py"),
}
#
# ⚠ **`DV-7` 은 여기 있었고, R24 인수에서 `NOT_YET_THROWN` 으로 되돌렸다.**
# 사본이 원문보다 짧아서 「이미 강제됨」으로 보였다 — 그 경위를 위 칸에 적었다.
# 이 칸은 **강제 사실을 숨긴 분류**를 고치려고 만들었는데, 첫 라운드에 그
# 반대(강제되지 않는 것을 강제된다고 적는 것)를 한 번 냈다.


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
@pytest.mark.req("FR-105-AC1")
def test_dv14_is_thrown_by_the_real_constructor() -> None:
    """**실제 생성자를 지나야** 한다 — 예외를 손으로 만들지 않는다 (DV-14).

    세 거부 경로가 전부 규칙 ID 를 나른다. 셋을 한 표로 도는 이유는 **경로마다
    따로 붙들어야** 하기 때문이다 — 하나만 검사하면 나머지 둘이 맨
    `ValueError` 로 되돌아가도 초록불이다.

    ⚠ **R22 인수에서 이 단언들이 「미지정」 경로를 붙들지 못하는 것이 드러났다.**
    `if mode is None:` 가드를 지워도 바로 아래 `if mode not in OPERATING_MODES:`
    가 `None` 을 걸러 **같은 `DV-14` 를 던지므로** 아래 공통 단언은 전부
    통과한다. 위 독스트링이 「경로마다 따로 붙든다」고 말하는데 실제로는
    **셋 중 둘만** 붙들고 있었다 — 주장이 근거보다 넓었다.

    그래서 `needle` 을 더한다. **경로를 가르는 것은 그 경로에만 있는 문면**이고,
    그것을 단언해야 경로가 사라졌을 때 빨간불이 된다.
    """
    cases = [
        # (설명, 클래스, 값, **그 경로에만 있는 문면**)
        ("목록 밖", ReferencePV, "야간 발전", "알 수 없는 운전 방법"),
        ("미지정", ReferencePV, None, "지정되지 않았습니다"),
        ("선언 없음", ModelessPV, "야간 발전", "선언 목록이 비어 있습니다"),
    ]
    for label, cls, mode, needle in cases:
        with pytest.raises(ValidationError) as caught:
            cls(operating_mode=mode)  # type: ignore[arg-type]

        parts = caught.value.as_dict()
        assert parts["rule"] == "DV-14", f"{label}: 규칙 ID 가 붙지 않았다"
        # **필드는 어긋난 입력의 이름을 가리킨다** — 자원 이름만으로는
        # 사용자가 어느 칸을 고쳐야 하는지 알 수 없다
        assert parts["field"] == "pv.operating_mode", label
        # 인스턴스 이름은 **필드가 아니라 사유**에 있다 — 필드 키는 열거
        # 가능해야 하고 자원 이름은 사용자가 지은 자유 문자열이다
        assert "옥상PV" in (parts["reason"] or ""), f"{label}: 어느 인스턴스인지 없다"
        assert "옥상PV" not in (parts["field"] or ""), f"{label}: 필드에 이름이 섞였다"
        assert (parts["action"] or "").strip(), f"{label}: 조치가 비었다"
        # ★ **이 경로에만 있는 문면** — 이것이 없으면 경로가 사라져 이웃
        # 분기로 흡수돼도 위 단언이 전부 통과한다 (R22 인수에서 실측)
        assert needle in (parts["reason"] or ""), (
            f"{label}: 이 경로 고유의 사유가 없다 — {needle!r} 를 기대했는데 "
            f"{parts['reason']!r} 였다. 가드가 사라져 이웃 분기가 대신 "
            "던지고 있지 않은지 보십시오"
        )

    # 지원 목록이 **있는** 경로는 조치에 그 목록을 실제로 넣는다. 「목록 안의
    # 값으로 고치십시오」만 적으면 그 목록을 찾으러 코드를 열어야 한다.
    # (`선언 없음` 경로는 목록이 없으므로 이 단언의 대상이 아니다)
    for mode_value in (None, "야간 발전"):
        with pytest.raises(ValidationError) as caught:
            ReferencePV(operating_mode=mode_value)  # type: ignore[arg-type]
        action = caught.value.as_dict()["action"] or ""
        for supported in ReferencePV.OPERATING_MODES:
            assert supported in action, f"{mode_value!r}: 조치에 {supported} 가 없다"


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_dv14_stays_catchable_as_valueerror() -> None:
    """`except ValueError` 로 받던 자리가 그대로 받는다.

    `tests/der/test_pv.py`·`test_ev_v2g.py` 가 `pytest.raises(ValueError,
    match="운전 방법")` 으로 물려 있다. 기반 예외를 갈아 끼우면 그 둘이
    **조용히 통과**하게 되고, 그 변화는 아무 오류도 내지 않는다.
    """
    with pytest.raises(ValueError, match="운전 방법"):
        ReferencePV(operating_mode="야간 발전")


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
@pytest.mark.req("FR-105-AC1")
def test_both_layers_emit_the_same_key_for_the_same_rule() -> None:
    """★★ **같은 규칙을 두 층이 던지면 키가 같아야 한다** — R21 에 달랐다.

    `core/der/pv.py`(자원 구현)와 `core/contracts/der.py`(계약)가 **둘 다**
    `DV-14` 를 던진다. R21 에 전자는 `pv.operating_mode`, 후자는
    `der.<인스턴스이름>.operating_mode` 였다 — 표시 층이 `field` 를 키로 쓰면
    같은 조항이 **두 칸으로 갈린다.**

    **이 검사가 R22 의 109곳 전환을 붙든다.** 파일마다 다른 모양이 되면
    표시 층은 결국 문자열을 파싱하게 되고, 그때 메시지 형식이 바뀌면 표시가
    조용히 깨진다 (`as_dict()` 를 둔 이유가 그것이다).
    """
    from core.der.pv import PV

    # 자원 구현 쪽 — 실제 생성자를 지난다
    with pytest.raises(ValidationError) as from_resource:
        PV(name="옥상PV", capacity_kw=3.0, operating_mode="야간 발전")

    # 계약 쪽 — 같은 규칙, 같은 자원 태그(`PV`)
    with pytest.raises(ValidationError) as from_contract:
        ReferencePV(operating_mode="야간 발전")

    r, c = from_resource.value, from_contract.value
    assert r.rule == c.rule == "DV-14"
    assert r.field == c.field == "pv.operating_mode", (
        f"두 층이 다른 키를 냈다 — 자원 {r.field!r} · 계약 {c.field!r}. "
        "`core/contracts/validation.py` 「경로 관례」를 볼 것"
    )
    # 인스턴스 이름은 **키가 아니라 사유**에 있다
    assert "옥상PV" in r.reason and "옥상PV" not in r.field


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_field_must_be_a_dotted_key_without_free_text() -> None:
    """`field` 는 **생성 시점에** 경로 모양을 요구한다 — 검사가 아니라 조건이다.

    사람이 읽는 문장이나 인스턴스 이름이 키 자리에 오면 표시 층이 칸을 찾을
    수 없다. 검사로 두면 그 검사를 지나지 않는 경로가 생긴다.
    """
    for wrong in ("자원 이름이 없습니다", "operating_mode", "pv operating_mode"):
        with pytest.raises(ValueError, match="점으로 이은 경로"):
            ValidationError(field=wrong, reason="r", action="a")

    # 관례에 맞는 것은 통과한다 — 자원 · 편익 · 차트 · 그 밖
    for ok in ("pv.operating_mode", "valuestream.REC.payer",
               "chart.cashflow_line.cashflows", "timeseries.rows"):
        assert ValidationError(field=ok, reason="r", action="a").field == ok


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_the_catalogue_is_split_with_nothing_left_unclassified() -> None:
    """★ **대장 전체가 분류돼 있어야 한다** — 열다섯 번째가 오면 빨간불이다.

    이것이 이 파일의 요점이다. 「구조화된 오류를 쓴다」는 방침은 규칙이 늘 때
    조용히 새는데, 새는 자리가 **대장과 코드 사이**라 어느 테스트도 보지
    않는다. 합집합을 단언하면 그 자리가 검사 대상이 된다.

    **R24 에 칸이 셋으로 늘었다.** 둘일 때는 「던지지 않지만 이미 강제된다」를
    적을 자리가 없어 `DV-7`·`DV-11` 이 「아직」에 섞여 있었다 —
    `ENFORCED_WITHOUT_A_THROW` 독스트링을 볼 것.
    """
    buckets = {
        "THROWN_BY_REAL_CODE": set(THROWN_BY_REAL_CODE),
        "NOT_YET_THROWN": set(NOT_YET_THROWN),
        "ENFORCED_WITHOUT_A_THROW": set(ENFORCED_WITHOUT_A_THROW),
    }
    classified: set[str] = set().union(*buckets.values())
    catalogue = set(DV_RULES)

    # **셋이 서로 겹치지 않아야 한다** — 칸이 늘면 짝을 손으로 세게 되고 그때
    # 한 짝을 빠뜨린다. 짝을 돌려서 센다
    for (left, lhs), (right, rhs) in combinations(buckets.items(), 2):
        assert not (lhs & rhs), (
            f"한 규칙이 {left} 와 {right} 양쪽에 있습니다: {sorted(lhs & rhs)} — "
            "셋 중 하나로 정하십시오"
        )
    assert classified == catalogue, (
        "대장과 분류가 어긋납니다. 대장에만 있는 것: "
        f"{sorted(catalogue - classified)} / 분류에만 있는 것: "
        f"{sorted(classified - catalogue)}. 새 DV 규칙을 대장에 넣었다면 "
        "던지는 코드를 함께 놓고 THROWN_BY_REAL_CODE 에, 아직이면 "
        "NOT_YET_THROWN 에, 던질 순간이 없는 규칙이면 "
        "ENFORCED_WITHOUT_A_THROW 에 적으십시오"
    )


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_every_rule_said_to_be_thrown_names_where_it_is_proven() -> None:
    """던진다고 적은 규칙은 **그것을 발동시키는 테스트 경로**를 함께 적는다.

    경로 없이 목록에 올리면 이 표가 곧 「손으로 유지되는 주장」이 되고, 그것이
    이 파일이 고치러 온 결함과 같은 형태다.
    """
    for rule, where in THROWN_BY_REAL_CODE.items():
        assert rule in DV_RULES, f"{rule} 은 대장에 없다 (매달린 참조)"
        assert where.startswith("tests/"), f"{rule}: 근거 경로가 테스트가 아니다"
        assert "::" in where or where.endswith(".py"), f"{rule}: 경로 형식"


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_rules_enforced_without_a_throw_name_places_that_exist() -> None:
    """★ 세 번째 칸도 **경로를 대며** 적는다 — 아니면 새 형태의 빈 약속이다.

    이 칸은 「던지지 않아도 강제된다」를 주장한다. 그 주장이 경로 없이 서면 이
    파일이 고치러 온 결함과 **똑같은 것**이 하나 더 생기는 셈이다 — 그것도
    「검증됨」으로 세어지는 자리에.

    파일이 옮겨지거나 지워지면 여기서 빨간불이 난다. 그때 할 일은 경로를 고치는
    것이거나, 강제가 정말 사라졌으면 `NOT_YET_THROWN` 으로 되돌리는 것이다.
    """
    for rule, (enforced_at, proven_by) in ENFORCED_WITHOUT_A_THROW.items():
        assert rule in DV_RULES, f"{rule} 은 대장에 없다 (매달린 참조)"
        assert (REPO_ROOT / enforced_at).is_file(), (
            f"{rule}: 강제한다고 적은 자리가 없다 — {enforced_at}"
        )
        assert proven_by.startswith("tests/"), (
            f"{rule}: 근거가 테스트가 아니다 — {proven_by}"
        )
        assert (REPO_ROOT / proven_by).is_file(), (
            f"{rule}: 근거 테스트가 없다 — {proven_by}. 강제가 사라졌다면 "
            "NOT_YET_THROWN 으로 되돌리십시오"
        )


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_a_rule_enforced_without_a_throw_is_not_secretly_thrown() -> None:
    """★★ 세 번째 칸의 **드리프트 방향** — 던지기 시작하면 옮기라고 막는다.

    `NOT_YET_THROWN` 이 코드보다 뒤처지는 것은 아래
    `test_not_yet_list_cannot_hide_a_rule_the_code_already_throws` 가 막는다.
    새 칸에도 같은 구멍이 있다 — 어느 라운드가 `DV-7` 에 진짜 던질 자리를
    찾아내 `rule="DV-7"` 을 달아도, 이 칸에 적힌 채면 **전건 초록불**이다.
    그러면 「던질 순간이 없다」는 판정이 **틀렸는데도 남는다.**

    R22 가 `NOT_YET_THROWN` 에서 정확히 그 상태를 만들었다. 칸을 늘릴 때
    같은 구멍을 함께 늘리지 않으려고 이 검사를 짝으로 놓는다.
    """
    thrown = _rules_carried_by_deployment_code()
    stale = sorted(set(ENFORCED_WITHOUT_A_THROW) & thrown.keys())

    assert not stale, (
        "「던질 순간이 없다」고 분류된 규칙을 배포 코드가 던집니다: "
        + " / ".join(f"{r} ← {', '.join(sorted(thrown[r]))}" for r in stale)
        + ". 던질 자리가 있었다는 뜻이므로 THROWN_BY_REAL_CODE 로 옮기고 "
        "그것을 발동시키는 테스트 경로를 함께 적으십시오."
    )


def _rules_carried_by_deployment_code() -> dict[str, set[str]]:
    """배포 코드가 `ValidationError(..., rule="DV-N")` 으로 **실제로 나르는** 규칙.

    `ast` 로 읽는 이유는 문자열 훑기가 주석·독스트링·이 파일 자신의 표까지
    세기 때문이다. `rule=` 이 상수가 아닌 경우(변수·f-string)는 여기서 셀 수
    없으므로 **세지 않는다** — 못 세는 것을 센 척하면 그것이 다시 「아무것도
    붙들지 않는 검사」가 된다.
    """
    found: dict[str, set[str]] = {}
    for root in DEPLOY_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else getattr(func, "attr", "")
                )
                if name != "ValidationError":
                    continue
                for kw in node.keywords:
                    if kw.arg != "rule":
                        continue
                    if isinstance(kw.value, ast.Constant) and isinstance(
                        kw.value.value, str
                    ):
                        found.setdefault(kw.value.value, set()).add(
                            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                        )
    return found


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_not_yet_list_cannot_hide_a_rule_the_code_already_throws() -> None:
    """★★ **분류가 코드보다 뒤처지면 빨간불이다** — R22 가 뚫린 것을 막는다.

    위 `test_the_catalogue_is_split_...` 는 **합집합이 대장과 같은지**와
    **양쪽에 겹치지 않는지**만 본다. 그래서 어떤 규칙이 `NOT_YET_THROWN` 에
    적힌 채로 배포 코드에서 던져지기 시작해도 **전건 초록불**이었다.

    R22 에 실제로 그 상태가 됐다 — `core/der/ess.py` 가 `DV-2`(SOC)·`DV-3`(RTE)
    를 던지기 시작했는데 분류는 여전히 「아직」이었고, 스위트 전체가 통과했다.
    **대장이 조용히 새지 않게 하려고 세운 래칫이, 정작 라운드가 만드는 방향의
    드리프트는 못 잡았다.**

    이 검사가 그 방향을 막는다. 규칙을 전환하면 분류를 **함께** 옮기게 된다.
    """
    thrown = _rules_carried_by_deployment_code()
    stale = sorted(NOT_YET_THROWN & thrown.keys())

    assert not stale, (
        "「아직 던지지 않는다」고 분류된 규칙을 배포 코드가 이미 던집니다: "
        + " / ".join(f"{r} ← {', '.join(sorted(thrown[r]))}" for r in stale)
        + ". THROWN_BY_REAL_CODE 로 옮기고 그것을 발동시키는 테스트 경로를 "
        "함께 적으십시오 — 분류가 코드보다 뒤처지면 이 표는 「손으로 유지되는 "
        "주장」이 됩니다."
    )


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_every_rule_classified_as_thrown_is_still_carried_by_the_code() -> None:
    """반대 방향의 썩음 — **던진다고 적었는데 그 코드가 사라진** 경우.

    전환한 코드를 나중에 되돌리거나 파일을 옮기면 표만 남는다. 그러면 추적표는
    그 규칙을 검증된 것으로 세고, 실제로는 아무도 던지지 않는다 — R21 이
    `DV-2` 에서 만난 형태 그대로다.
    """
    thrown = _rules_carried_by_deployment_code()
    missing = sorted(set(THROWN_BY_REAL_CODE) - thrown.keys())

    assert not missing, (
        f"던진다고 분류됐으나 배포 코드에 `rule=` 이 없습니다: {missing}. "
        "코드를 되돌렸다면 NOT_YET_THROWN 으로 옮기십시오 — 표만 남으면 "
        "추적표가 검증되지 않은 규칙을 검증된 것으로 셉니다."
    )
