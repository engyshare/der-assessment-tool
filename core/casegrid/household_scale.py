"""단지 규모 — **가구 수**로 총부하를 키우는 자리 (착수 순서 47ⓐ · R64/WP-1).

## 무엇을 여는가

`docs/assumptions.yaml` 의 `load.household.annual` 은 단위가 **kWh/호·년**,
즉 **가구 한 호당** 값이다. 그런데 러너
(`core/casegrid/e2e_runner.py::run_single_case_e2e`)가 그것을 **단지 총량으로
그대로** 써 왔다 — 그래서 이 저장소에는 세대 수를 바꿀 방법이 없었고, 검증
모드 1단계의 「가구 수」 칸이 *「자료형 수준으로 없다」* 로 서 있었다
(`app/services/verify_steps.py` 의 `_GAPS`).

    단지 총부하 = 가구 수 × (가구 한 호의 연간 사용량 + 그 호의 추가 기기)

이 모듈은 그 곱을 **한 자리에서** 판정하고 곱한다.

## ⚠⚠⚠ 값을 지어내지 않는다 — 이 모듈에 기본 가구 수가 없는 이유

`docs/assumptions.yaml` 의 `load.household.count` 는 `track: blocked` ·
`value: null` 이고, 그 항목의 `derivation_method` 가 이렇게 못 박았다:
*「**가정하면 안 된다.** 이것은 추세를 외삽할 수 있는 단가가 아니라 **사업
계획이 정하는 사실**이다」*. 우리가 「40호쯤」을 여기 적으면 그 수가 단지
총량·계약전력·설비 용량을 통째로 정하고, 그 뒤에 검토자가 보는 것은 **우리가
고른 규모로 우리가 돌린 계산**이 된다(§13.0.2 자기충족).

⇒ 그래서 **기본 가구 수가 없다.** 안 주면 `None` 이고, 그때 배수는 `1` 이며
러너는 **가구 한 호 기준**으로 돈다 — 이 배선이 생기기 전과 원소 하나까지
같다. 골든 회귀(`tests/golden/test_regression_scenarios.py`)가 그 동일성을
잰다.

## ⚠ 왜 러너 안이 아니라 별도 모듈인가

`core/casegrid/e2e_runner.py` 는 **코드 495/500**(`scripts/check_file_size.py
--code-strict` 실측, 2026-09-06)이라 판정문을 담을 자리가 없다. 같은 이유로
같은 파일이 이미 두 번 갈라졌고 — `core/casegrid/pv_allocation.py`(R51/WP-5) ·
`core/casegrid/ess_build.py`(R57/WP-5) — 두 모듈의 머리말이 그 사유를 적는다.
⛔ **상한을 올려 푸는 것은 금지다**(NFR-206 · spec §16.5 절차).

## 판정하는 자리는 하나다

`resolve_household_count` 를 **두 곳이 함께 부른다** — 시나리오를 읽는
`core/report/case_report.py::build_case_report` 와 실제로 곱하는
`household_scale`. 거부 문면을 층마다 새로 적으면 둘이 갈리고, 갈린 뒤에는
같은 입력이 화면에서는 통과하고 러너에서는 거부되는 상태가 조용히 선다 —
`core/cba/baseline.py::resolve_baseline_arrangement` 가 같은 판단을 적어 둔
자리다.
"""
from __future__ import annotations

from core.contracts.validation import ValidationError

#: 시나리오 yaml 이 가구 수를 싣는 **필드 이름**.
#:
#: ⚠ **통로는 이 필드 하나다.** 케이스 그리드 변수축·환경 변수·CLI 플래그를
#: 따로 세우지 않는다 — 통로가 둘이면 어느 것이 이겼는지 산출물에서 알 수
#: 없다(`app/services/ui_run.py` 머리말의 ★★★ 가 같은 판단을 적는다).
HOUSEHOLD_COUNT_FIELD = "household_count"

#: 이 수의 **대장 자리**. 값은 비어 있고(`track: blocked` · `value: null`)
#: 이 코드가 채우지 않는다 — 위 머리말 ⚠⚠⚠ 참조.
HOUSEHOLD_COUNT_LEDGER_KEY = "load.household.count"

#: 가구 수를 주지 않은 실행이 산출물에 **글자로** 남기는 문면.
#:
#: ⚠⚠ **빈칸으로 두지 않는다.** 빈칸은 「반영됐다」와 「반영하지 않았다」를
#: 구별해 주지 않고, 사용자는 앞쪽으로 읽는다. 이 저장소의 규약이 *「못 하는
#: 것은 「칸 + 사유」로 남긴다」* 이며 `core/report/_format.py::NO_VALUE` 가
#: 같은 사유를 적는다.
HOUSEHOLD_COUNT_UNSPECIFIED = "미지정 — 가구 한 호 기준으로 돌았다"


def resolve_household_count(value: object | None) -> int | None:
    """시나리오·화면이 적은 가구 수 → `int`(1 이상) 또는 `None`(미지정).

    `None` 과 빈 문자열이 **「적지 않았다」**이며 그것이 기본이다. 여기서
    기본 가구 수로 바꿔 내지 않는다 — 「적지 않았다」와 「한 호라고 적었다」는
    다른 진술이고, 앞의 것만이 *「단지 규모를 아직 모른다」* 를 뜻한다
    (`core/cba/baseline.py::resolve_pool_metering` 이 같은 구별을 적는다).

    ## 왜 정수만 받는가

    가구 수는 **세는 값**이다. `40.5호` 는 입력 실수이고, 실수를 반올림해
    받아 주면 산출물이 인쇄하는 수와 사용자가 적은 수가 갈린다. 문자열은
    화면의 빈 칸(`""`)과 숫자 문면(`"40"`)만 받는다 — 폼이 GET 질의로
    보내는 모양이 그 둘뿐이기 때문이다(`app/routers/ui.py::run_case` 의
    `arrangement` 가 같은 규약을 따른다).

    ⚠ `bool` 을 막는다. 파이썬에서 `True` 는 `int` 의 하위형이라 그냥 두면
    `가구 수 = True` 가 **1호**로 조용히 통과한다.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if not text.isdigit():
            raise _rejected(text)
        return resolve_household_count(int(text))
    if isinstance(value, bool) or not isinstance(value, int):
        raise _rejected(value)
    if value < 1:
        raise _rejected(value)
    return value


def _rejected(value: object) -> ValidationError:
    """거부 하나 — **3요소를 갖춘다** (`NFR-303`).

    ⚠ 문면을 한 곳에만 둔다. 갈래마다 새로 적으면 같은 실수에 다른 사유가
    나가고, 그때 사용자는 「무엇이 다른가」를 찾느라 시간을 쓴다.
    """
    return ValidationError(
        field=HOUSEHOLD_COUNT_LEDGER_KEY,
        reason=(
            f"가구 수는 1 이상의 정수여야 합니다 (받은 값 {value!r}). "
            "이 수는 대장이 갖지 않는다 — 사업 계획이 정하는 값이므로 "
            "저장소가 기본값으로 메우지 않습니다"
        ),
        action=(
            "가구 수를 비우거나(그때 가구 한 호 기준으로 돕니다) "
            "1 이상의 정수로 지정하십시오"
        ),
    )


def household_scale(household_count: int | None) -> int:
    """총량에 곱할 **배수** — 미지정이면 `1`(가구 한 호 기준)이다.

    ⚠ `household_count or 1` 을 호출부에 적지 않는 이유: 그 표현은 `0` 도
    조용히 `1` 로 바꾼다. 여기서는 `0` 이 위 `resolve_household_count` 에서
    **거부**되고, 거부되지 않은 값만 배수가 된다.
    """
    return resolve_household_count(household_count) or 1
