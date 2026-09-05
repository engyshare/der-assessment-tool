"""시나리오가 실은 **전제 오버라이드**를 실행 경로에 얹는다 — `FR-602` · §7.2 O-2.

## 왜 이 파일이 생겼는가 (R63)

전제를 덮어쓰는 층은 R22 부터 **이미 있었다** — `AssumptionSet.override()` 가
대장을 복제하지 않고 오버라이드만 얹은 새 집합을 돌려주고,
`overridden_items()` 가 `{base, override, reason}` 을 함께 내주며,
`CaseReport.overrides` 와 `_overrides(provider)` 가 그것을 붙임 표로 그린다.

**없던 것은 통로 하나**다. `build_case_report()` 는 대장을 그대로 싣고
오버라이드를 걸지 않았고, 그래서 붙임 1 의 「기준 전제 대비 변경 항목」은
배포 경로에서 **영영 비어 있었다.** 사용자 문면(*「분석에 필요한 사항을 수정,
저장, 로드할 수 있어야 함」*)이 가리키는 자리가 정확히 그 구멍이다.

## ★★★ 통로는 **시나리오 필드 하나**다 — 새 통로를 내지 않는다

`baseline_arrangement`(기준선 갈래)·`pool_metering`(ⓒ 계측 선언)이 이미 그
모양이고, 그 규약의 정본은 `app/services/ui_run.py` 머리말과
`build_case_report()` 안의 ★★★ 주석 둘이다. 전제 오버라이드도 **같은 자리**로
들어온다 — 케이스 그리드 변수축·환경변수·CLI 플래그를 따로 세우지 않는다.
통로가 둘이면 어느 것이 이겼는지 **산출물에서 알 수 없다.**

    assumption_overrides:
      - key: benefit.rec_price
        value: 120
        reason: 2026년 계약 단가로 고쳤다

⚠ **평평한 매핑(키에 값을 바로 붙인 사전)으로 두지 않는다.** 그러면 `reason`
을 실을 자리가 없어지고 `FR-602-AC3`(사유는 **권장** 필드)이 자료형에만 남는다
— 채울 수 없는 필드는 없는 필드와 같다.

★ 이 모양은 `infra/orm/scenario.py::ScenarioOverride` 의 컬럼
(`assumption_key`·`value_json`·`reason`)과 **같다.** 저장 층과 실행 층이 같은
모양을 쓰면 저장→불러오기 왕복에서 사유가 사라지지 않는다.

## ⚠⚠ 대장을 무르게 만들지 않는다 (`NFR-202` · 사용자 판정 R63 §3 ⓐ)

사용자가 요구한 것은 *「내가 값을 고쳐 저장하고 다시 부를 수 있어야 한다」*
이지 *「대장을 없애라」* 가 아니다. 그래서 이 층은 **대장 위에 얹히고** 대장을
여는 문이 아니다:

    ⛔ 대장에 없는 키로 새 전제를 만들 수 없다
    ⛔ `price_basis` 는 오버라이드로 바뀌지 않는다 — 기준은 값이 아니라 규약이며
       `override()` 가 애초에 그것을 인자로 받지 않는다 (`DV-7` · `FR-202`)

**거부하지 조용히 무시하지 않는다.** `overridden_items()` 는 대장 밖 키를
`if key in self._items` 로 이미 걸러 내므로, 무시하면 그 값은 **계산에도 안 먹고
붙임에도 안 뜬다** — 사용자가 값을 고쳤는데 아무 데도 나타나지 않는 상태가
가장 나쁘다. 화면은 고친 값을 인쇄하고 수는 옛 값으로 돈다.

## ★★★ **키만 보지 않는다 — 값의 형을 대장과 맞댄다** (R1 D-3 · D-4)

첫 판은 키가 대장에 있는지만 보고 **값은 안 봤다.** 그래서 둘이 새어 나갔다:

    ⓐ `analysis.period_years: true` → `bool` 이 스칼라로 통과 → `int(True) == 1`
       → **분석기간 1년**. 무보조 `npv` −11,552,270 → **−924,900**(Δ +10,627,370).
       붙임은 `20 → True` 로 인쇄하므로 검토자는 그것이 「1년」임을 **산출물에서
       알 수 없다.** ⚠⚠ YAML 이 `yes`·`on`·`true` 를 전부 `True` 로 읽는다
    ⓑ `analysis.period_years: "스무해"` → 관문 통과 → `build_case_report()` 깊은
       곳에서 맨 `TypeError`. `NFR-303` 3요소가 **없다** — 이 파일의 다른 거부
       다섯은 전부 갖는데 이 갈래만 없었다

⇒ `resolve_assumption_overrides` 는 이제 **키가 아니라 `키 → 값`** 을 받고,
대장 값의 형 갈래(`수`/`문자열`)와 오버라이드 값의 갈래를 맞댄다.

★ **형만 본다.** 범위(음수·0·상한)와 정수성은 각 항목의 조항(`DV-5` 등)이
보며, 여기서 흉내내면 **같은 사실을 판정하는 자리가 둘**이 되고 한쪽만 고쳐진
상태를 아무도 보지 않는다. `int`/`float` 를 가르지 않는 사유는 `_kind` 에 있다.

## ⚠ 아직 남은 것 — 「인쇄되는데 안 먹는 키」(R1 D-5)

`tax.vat_rate` 는 대장 **안**에 있으나 아무도 읽지 않는다
(`core/contracts/der.py:34` · `core/contracts/assumptions.py:4` 가 이미 적어
두었다). 그래서 `vat_rate: 1e9` 는 이 관문을 정당하게 통과하고 붙임은
`0.1 → 1000000000.0` 을 인쇄하는데 **수는 한 푼도 안 움직인다** — 이 머리말이
위에서 「가장 나쁘다」로 지목한 바로 그 상태다. **거부가 답이 아니다**(어느
키가 읽히는지는 실행마다 다르고, 목록을 여기 박으면 낡는다). 필요한 것은
「거부도 통과도 아닌 **표시**」이고 그것이 설 자리는 이 함수의 반환값 밖이다 —
판정과 사유는 `.orch/R63/result_F2.md` §1·§6 에 적었다.

## ★★★ 필드가 없으면 **같은 객체**를 그대로 돌려준다

`apply_scenario_overrides(provider, None) is provider` 다. 같은 값을 가진 새
객체를 돌려주면 기본값 실행이 다른 객체로 다른 경로를 돌게 되고, 그때 결론축
(무보조 `npv`)이 움직여도 「오버라이드 때문인가 복제 때문인가」를 가릴 수 없다.
**기본값 실행의 불변은 이 동일성이 근거다.**

## 왜 `core/report/case_report.py` 가 아니라 여기인가

그 파일은 총 927줄 · 코드 478줄이고 `NFR-206` 코드 상한이 500 이다 — 해석
함수와 검증을 넣으면 남은 22줄을 넘긴다. **상한을 올리는 것은 `spec §16.5`
절차**이므로 모듈을 가른다. 그 파일이 얻는 변경은 import 한 줄과 재대입 한
줄뿐이다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from core.assumption.provider import AssumptionSet
from core.contracts.validation import ValidationError

#: 시나리오 yaml 에서 전제 오버라이드가 들어오는 **필드 이름의 정본**.
#:
#: ⚠ 문면을 다른 층이 다시 적지 않는다. `_ARRANGEMENT_FIELD`(`ui_run.py`)가
#: 상수 없이 문면을 다시 적어야 했던 사유를 그 자리 주석이 적어 두었다 —
#: 여기서는 처음부터 상수를 둔다. 어긋나면 조용하다: 필드 이름이 갈리면
#: 오버라이드가 시나리오에 실리지 않고 붙임만 비어 있다.
ASSUMPTION_OVERRIDES_FIELD = "assumption_overrides"

#: 거부 문면의 `field` 경로 (`NFR-303` · 경로 관례 「`<도메인>.<필드>`」).
#: 어느 줄이 틀렸는지는 `field` 가 아니라 `reason` 이 적는다 — 줄 번호를 키에
#: 넣으면 키 공간이 무한해지고 표시 층이 찾을 수 없다.
_FIELD = f"scenario.{ASSUMPTION_OVERRIDES_FIELD}"

_KEY = "key"
_VALUE = "value"
_REASON = "reason"

#: 한 원소가 가질 수 있는 필드 전건. **모르는 필드는 거부한다** — `reason` 의
#: 오타(`resaon`)를 흘려보내면 사유가 조용히 사라지고, 그 상태는 「사유를 적지
#: 않았다」와 붙임에서 구별되지 않는다.
_ROW_FIELDS = frozenset({_KEY, _VALUE, _REASON})

#: 오버라이드 값으로 받는 스칼라. 목록·사전을 받지 않는 이유는 대장 항목이
#: 스칼라형과 참조형뿐이고(`FR-601-AC6`), 구조를 받으면 「값을 바꾼다」가
#: 「대장 스키마를 바꾼다」로 번지기 때문이다.
#:
#: ⚠⚠ **`bool` 이 여기 있었고, 그것이 결론축을 움직였다**(R1 D-3). YAML 은
#: 따옴표 없는 `yes`·`on`·`true` 를 전부 `True` 로 읽으므로
#: `analysis.period_years: true` 가 스칼라로 통과했고 `int(True) == 1` 이 되어
#: **분석기간이 1년**(무보조 `npv` −11,552,270 → −924,900)이 됐다. 붙임은
#: `20 → True` 로 인쇄해서 검토자가 그것을 알 수도 없었다.
#: ★★ **그런데 이 목록에서 빼는 것만으로는 아무것도 달라지지 않는다** —
#: `bool` 은 `int` 의 하위형이라 `isinstance(True, _SCALARS)` 가 여전히 참이다.
#: 관문은 아래 `_row` 의 `type(value) is bool` 이며, 이 목록은 **그 뒤에**
#: 선다. 그 줄을 「스칼라 목록이 이미 본다」며 지우면 D-3 이 그대로 돌아온다.
_SCALARS = (int, float, str)

#: 값의 **형 갈래**. 대장 값과 오버라이드 값을 견주는 단위이며, `int` 와
#: `float` 를 가르지 않고 한 갈래(`수`)로 묶는다 — 사유는 `_kind` 독스트링.
_NUMBER = "수"
_TEXT = "문자열"
_BOOLEAN = "참·거짓"
_UNKNOWN = "알 수 없는 형"

_HOW_TO_WRITE = (
    f"`{ASSUMPTION_OVERRIDES_FIELD}` 는 목록이고 한 원소는 "
    f"`{{{_KEY}: <대장 키>, {_VALUE}: <스칼라>, {_REASON}: <사유·선택>}}` 입니다"
)


def _refuse(reason: str, action: str) -> NoReturn:
    """`NFR-303` 3요소를 갖춘 거부 하나. **부분만 읽고 넘어가지 않는다.**"""
    raise ValidationError(field=_FIELD, reason=reason, action=action)


def _kind(value: object) -> str:
    """값을 대장 값과 **견줄 수 있는 형 갈래**로 줄인다.

    ★ **`int` 와 `float` 를 가르지 않는다.** 대장의 `int`/`float` 는 선언된
    계약이 아니라 **yaml 이 그 값을 어떻게 적었는가의 흔적**이다 — 같은 「%」
    축인데 `escalation.electricity_tariff` 는 `2.5`(`float`)이고
    `capex.modular_house.premium` 은 `15`(`int`)이며, 같은 「원/kWh」 축인데
    `benefit.rec_price` 는 `70`(`int`)이다. 그 흔적을 계약으로 읽으면
    `rec_price: 120.5` 같은 **정당한 편집이 정수 항목 전부에서 막힌다.**

    ⚠ **그래서 못 잡는 것이 남는다**: 뒤에 정수 검사가 없는 정수 항목에
    `2.7` 을 넣으면 소비자가 `int()` 로 자를 수 있다. 그것은 *형*이 아니라
    *정수성*이고 판정 자리는 `DV-5` 다 — 여기서 흉내내면 같은 사실을
    판정하는 자리가 둘이 된다.

    ⚠ **`bool` 을 `수` 로 접지 않는다.** `isinstance(True, int)` 가 참이므로
    접으면 `True` 가 정수 항목에 그대로 앉는다(D-3).
    """
    if type(value) is bool:
        return _BOOLEAN
    if isinstance(value, (int, float)):
        return _NUMBER
    if isinstance(value, str):
        return _TEXT
    return _UNKNOWN


def _row(position: int, row: object) -> tuple[str, Any, str | None]:
    """원소 하나의 모양을 보고 `(키, 값, 사유)` 로 편다."""
    if not isinstance(row, Mapping):
        _refuse(
            f"{position}번째 원소가 매핑이 아닙니다: {row!r}",
            _HOW_TO_WRITE,
        )
    unknown = sorted(str(name) for name in row if name not in _ROW_FIELDS)
    if unknown:
        _refuse(
            f"{position}번째 원소에 모르는 필드가 있습니다: {', '.join(unknown)}",
            f"오타가 아닌지 보십시오. {_HOW_TO_WRITE}",
        )
    key = row.get(_KEY)
    if not isinstance(key, str) or not key.strip():
        _refuse(
            f"{position}번째 원소에 대장 키(`{_KEY}`)가 없습니다: {row!r}",
            _HOW_TO_WRITE,
        )
    if _VALUE not in row:
        _refuse(
            f"{position}번째 원소({key})에 값(`{_VALUE}`)이 없습니다",
            f"바꿀 값을 적으십시오. 되돌리려면 그 원소를 지우십시오. {_HOW_TO_WRITE}",
        )
    value = row[_VALUE]
    # ★★ **`_SCALARS` 보다 **먼저** 본다.** `bool` 은 `int` 의 하위형이라
    # `isinstance(True, _SCALARS)` 가 참이고, 그래서 스칼라 목록에서 `bool` 을
    # 빼는 것만으로는 아무것도 막히지 않는다 — R1 D-3 이 그 자리다.
    if type(value) is bool:
        _refuse(
            f"{position}번째 원소({key})의 값이 {_BOOLEAN}입니다: {value!r}",
            "YAML 은 따옴표 없는 `yes`·`on`·`true`(그리고 `no`·`off`·`false`)를 "
            f"{_BOOLEAN}으로 읽습니다 — 수로 적으려면 `1`·`0` 처럼, 글자 그대로 "
            '두려면 `"true"` 처럼 따옴표로 감싸십시오. 전제 값은 '
            f"{_BOOLEAN}일 수 없습니다",
        )
    if not isinstance(value, _SCALARS):
        _refuse(
            f"{position}번째 원소({key})의 값이 스칼라가 아닙니다: {value!r}",
            f"수 또는 문자열 하나로 적으십시오. {_HOW_TO_WRITE}",
        )
    reason = row.get(_REASON)
    if reason is not None and not isinstance(reason, str):
        _refuse(
            f"{position}번째 원소({key})의 사유가 문자열이 아닙니다: {reason!r}",
            f"사유는 문장 하나로 적거나 생략하십시오. {_HOW_TO_WRITE}",
        )
    return key, value, reason


def resolve_assumption_overrides(
    raw: object, *, base_values: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, str]]:
    """시나리오가 적은 것을 `AssumptionSet.override()` 의 두 인자로 편다.

    `base_values` 는 **대장이 가진 `키 → 값` 전건**이다. 인자로 받는 이유는 이
    함수가 대장을 직접 열지 않게 하려는 것이며, 선택 인자로 두지 않은 이유는
    **거를 수 있는 경로를 남기면 그 경로가 쓰이기 때문**이다 — 대장 밖 키를
    통과시키는 호출이 하나만 있어도 `NFR-202` 는 선언만 남는다.

    ⚠⚠ **키만 받던 자리다.** 키만 보면 「대장에 있는 키인가」까지만 답하고
    「그 자리에 이 형의 값이 들어갈 수 있는가」는 **아무도 안 봤다** — 그래서
    `analysis.period_years: "스무해"` 가 관문을 지나 계산 깊은 곳에서 맨
    `TypeError` 로 터졌고 `NFR-303` 3요소가 없었다(R1 D-4). 값을 함께 받는
    것이 그 판정의 근거다.

    ★ **여기서 보는 것은 형뿐이다.** 범위(음수·0·상한)·정수성은 각 조항
    (`DV-5` 등)이 보며, 여기서 흉내내면 같은 사실을 판정하는 자리가 둘이 되고
    한쪽만 고쳐진 상태를 아무도 보지 않는다.
    """
    if isinstance(raw, Mapping):
        _refuse(
            "평평한 매핑으로 적혀 있습니다 — 그러면 사유를 실을 자리가 없습니다 "
            f"(`FR-602-AC3`): {raw!r}",
            _HOW_TO_WRITE,
        )
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        _refuse(
            f"목록이 아닙니다: {raw!r}",
            _HOW_TO_WRITE,
        )

    overrides: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    for position, item in enumerate(raw):
        key, value, reason = _row(position, item)
        if key in overrides:
            # 사전 갱신으로 **뒤가 이기고** 앞 줄은 흔적 없이 사라진다.
            _refuse(
                f"같은 대장 키를 두 번 적었습니다: {key}",
                "한 키는 한 번만 적으십시오 — 두 번 적으면 어느 값이 쓰였는지 "
                "산출물에서 알 수 없습니다",
            )
        if key not in base_values:
            _refuse(
                f"전제 대장에 없는 키입니다: {key}",
                "오버라이드는 대장 위에 얹는 층이며 새 전제를 만들지 않습니다 "
                "(`NFR-202`). 대장에 있는 키로 적거나, 항목이 필요하면 "
                "`docs/assumptions.yaml` 에 부기 7종을 갖춰 세우십시오",
            )
        base = base_values[key]
        # ★★★ **대장 값의 형과 맞댄다** (R1 D-4). 형이 갈리면 여기서 멈춘다 —
        # 흘려보내면 잡히는 것은 **우연히 뒤에 검사가 있는 키뿐**이고, 나머지는
        # `build_case_report()` 안에서 맨 예외로 터져 3요소 없는 오류가 된다.
        if _kind(value) != _kind(base):
            _refuse(
                f"{key} 의 값이 대장 항목과 다른 형입니다 — 대장은 "
                f"{_kind(base)}({base!r})인데 오버라이드는 "
                f"{_kind(value)}({value!r})입니다",
                f"대장 값과 같은 형으로 적으십시오. 참조형 항목"
                f"(`FR-601-AC6`)은 {_TEXT}이고 나머지는 {_NUMBER}입니다. "
                "범위(음수·상한)는 이 관문이 아니라 각 항목의 조항이 봅니다",
            )
        overrides[key] = value
        if reason is not None:
            reasons[key] = reason
    return overrides, reasons


def apply_scenario_overrides(provider: AssumptionSet, raw: object) -> AssumptionSet:
    """대장 위에 시나리오의 오버라이드를 얹는다 — **없으면 그대로 돌려준다.**

    ★★★ `raw is None`(= 시나리오가 필드를 적지 않았다)이면 **같은 객체**가
    돌아온다. 그래서 기본값 실행은 오버라이드 통로가 생기기 전과 **같은 객체로
    같은 경로**를 돌고, 결론축(무보조 `npv`)이 움직이지 않는다.
    """
    if raw is None:
        return provider
    overrides, reasons = resolve_assumption_overrides(
        raw,
        # ⚠ **항목 자체가 아니라 값만 넘긴다.** 해석 층이 `AssumptionItem` 을
        # 손에 쥐면 부기 7종·`price_basis` 까지 판정하게 되고, 그때 대장을 여는
        # 문이 하나 더 생긴다. 여기가 지는 것은 **형 대조 하나**다.
        base_values={key: item.value for key, item in provider.items().items()},
    )
    return provider.override(overrides, reasons)
