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

from collections.abc import Collection, Mapping, Sequence
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
_SCALARS = (bool, int, float, str)

_HOW_TO_WRITE = (
    f"`{ASSUMPTION_OVERRIDES_FIELD}` 는 목록이고 한 원소는 "
    f"`{{{_KEY}: <대장 키>, {_VALUE}: <스칼라>, {_REASON}: <사유·선택>}}` 입니다"
)


def _refuse(reason: str, action: str) -> NoReturn:
    """`NFR-303` 3요소를 갖춘 거부 하나. **부분만 읽고 넘어가지 않는다.**"""
    raise ValidationError(field=_FIELD, reason=reason, action=action)


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
    raw: object, *, known_keys: Collection[str]
) -> tuple[Mapping[str, Any], Mapping[str, str]]:
    """시나리오가 적은 것을 `AssumptionSet.override()` 의 두 인자로 편다.

    `known_keys` 는 **대장이 가진 키 전건**이다. 인자로 받는 이유는 이 함수가
    대장을 직접 열지 않게 하려는 것이며, 선택 인자로 두지 않은 이유는 **거를
    수 있는 경로를 남기면 그 경로가 쓰이기 때문**이다 — 대장 밖 키를 통과시키는
    호출이 하나만 있어도 `NFR-202` 는 선언만 남는다.
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
        if key not in known_keys:
            _refuse(
                f"전제 대장에 없는 키입니다: {key}",
                "오버라이드는 대장 위에 얹는 층이며 새 전제를 만들지 않습니다 "
                "(`NFR-202`). 대장에 있는 키로 적거나, 항목이 필요하면 "
                "`docs/assumptions.yaml` 에 부기 7종을 갖춰 세우십시오",
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
        raw, known_keys=provider.items().keys()
    )
    return provider.override(overrides, reasons)
