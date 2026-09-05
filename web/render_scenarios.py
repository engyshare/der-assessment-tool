"""시나리오·설정 화면의 문맥 — `FR-902` · `FR-602` · 사용자 판정 R63 §1.

## 왜 이 파일이 R63/S2 에 생겼는가

저장 계층(`app/services/scenario_store.py`·`scenario_store_file.py`)과 전제
오버라이드 통로(`core/assumption/scenario_overrides.py`)는 이미 섰다. 못 하던
것은 **사람이 화면에서 그것을 쓰는 것**이다 — 사용자 문면(*「시나리오를 수정,
저장할 수 있어야 함」* · *「기본 설정도 쉽게 변경, 저장, 로드할 수 있어야 함」*
· `docs/decisions-2026-09-05-R63.md` §1)이 가리키는 자리가 그 구멍이다.

## ★ `web/render.py` 의 `Environment` 를 그대로 쓴다 — 새로 짓지 않는다

새 `Environment` 를 지으면 `autoescape` 설정이 **두 곳**에 살고, 한쪽만 고쳐지는
날 한 화면만 조용히 이스케이프를 잃는다 — 사용자가 지은 시나리오 이름이
그대로 태그로 들어가는 자리가 정확히 여기다. 그 모듈이 그것을 공개 이름으로
내놓지 않아 **사설 이름을 가져온다**(오케스트레이터 판정 R63/WP-S2 §3 ②
*「`web/render.py` 에서 가져와 쓰되 그 파일을 고치지는 마라」*). 공개 접근자를
두는 것이 옳으나 그 파일은 이 축이 고칠 자리가 아니다 — **판정 ① 의 금지 파일**
이며, 같은 시간에 다른 축이 고치고 있다.

## ★★ 라벨·목록을 손으로 적지 않는다

대장 항목 목록은 `AssumptionSet` 이, 시계열 파라미터 목록은
`core.model.parameters` 카탈로그가 정본이다. 화면이 자기 안에 목록을 적어 두면
항목이 늘 때 그 목록이 낡고, **낡은 것은 사람이 없는 칸을 찾을 때까지
드러나지 않는다** (`web/render.py::equipment_setting_fields` 가 같은 판단을 적었다).

⚠ **사용자가 든 다섯**(전기요금·태양광 발전 프로파일·전기사용자 부하·설비별
단가·이용률)만은 사람의 말이므로 여기 적는다. 그러나 **「대장의 어느 키인가」는
적지 않는다** — 접두사로 대장에 물어서 답을 짓는다. 키를 적어 두면 항목이
이름을 바꾸는 날 화면이 없는 키를 가리키고, 그것은 「없다」와 구별되지 않는다.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from core.assumption.provider import AssumptionSet
from core.model.composition import available_resource_tags
from core.model.parameters import ParameterKind, resource_parameters
from core.report._format import NO_VALUE, _won
from core.report.case_report import CaseReport, OverrideRow
from web.render import _ENV

__all__ = (
    "SERIES_OUT_OF_SCOPE",
    "applied_settings_context",
    "ledger_groups",
    "render_scenarios",
    "render_settings",
    "scenarios_context",
    "series_fields",
    "settings_context",
    "user_named_items",
)

#: 시계열을 이 라운드에서 편집하지 않는 사유 — **화면에 글자로 나간다**
#: (오케스트레이터 판정 R63/WP-S2 §2 ④). ⚠ 자리를 지우지 않는다: 지우면
#: 사용자가 요구한 항목이 화면에서 **사라지고**, 그 상태는 「없는 기능」과
#: 「안 그린 칸」이 구별되지 않는 §13.0.1 ④ 그것이다.
SERIES_OUT_OF_SCOPE = (
    "시계열은 별도 편집기가 필요하다 — 이 라운드 범위 밖. "
    "8,760 스텝짜리 열은 수치 입력 칸 하나로 그릴 수 없다."
)

#: 사용자가 든 다섯 — **사람의 말 그대로**다 (`docs/decisions-2026-09-05-R63.md`
#: §1 「설정」). 값은 `(대장 키 접두사들, 자원 파라미터 이름 조각들)` 이며,
#: **어느 키가 답인지는 여기 적지 않고 대장·카탈로그에 물어서 짓는다.**
_USER_NAMED: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("전기요금", ("tariff.", "escalation.electricity_tariff"), ("price_profile",)),
    ("태양광 발전 프로파일", (), ("generation_profile",)),
    ("전기사용자 부하", ("load.",), ("hourly_kwh", "monthly_kwh")),
    ("설비별 단가", ("capex.", "opex."), ()),
    ("이용률", ("capacity_factor.",), ()),
)

#: 대장에 그 이름으로 등재된 항목이 **없을 때** 화면이 적는 말.
_NOT_IN_LEDGER = "전제 대장에 이 이름으로 등재된 항목이 없다"

#: 그룹 머리에 붙이는 이름 — 대장 키의 **첫 마디**다. 한국어 이름을 손으로
#: 적지 않는 이유는 이 파일 머리말의 ★★ 와 같다.
_GROUP_DEPTH = 1

#: 읽기 전용으로 둔다 — 모듈 수준 가변 컨테이너는 `NFR-205` 가 막는 것이다
#: (`web/render_run.py::_POOL_PREREQUISITE_LABELS` 가 같은 자리에서 같은 모양).
_KIND_LABELS = MappingProxyType({"scenario": "시나리오", "settings": "설정"})


def _text(value: object) -> str:
    """값 하나를 **폼 칸에 넣을 글자**로. 서식을 입히지 않는다.

    ⚠ `_won()` 같은 서식을 여기 쓰지 않는다. 이 글자는 사람이 고쳐 되돌려
    보내는 값이며, 서식을 입히면 다음 제출에서 `1,600,000원` 을 수로 되돌려야
    한다 — 그 되돌림은 자리마다 달라지고 갈린 뒤에도 화면은 멀쩡해 보인다.
    """
    return "" if value is None else str(value)


def user_named_items(ledger: AssumptionSet) -> tuple[dict[str, Any], ...]:
    """사용자가 든 다섯이 **대장의 어느 키인가** — 대장에 물어서 답한다.

    ⚠ **지어내지 않는다.** 접두사로 걸리는 항목이 하나도 없으면 「없다」로
    적고, 그 이름이 자원 파라미터 카탈로그의 **시계열**로 살아 있으면 그것을
    함께 적는다 — 「대장에 없다」와 「어디에도 없다」는 다른 진술이다.
    """
    known = tuple(ledger.items())
    rows: list[dict[str, Any]] = []
    for word, prefixes, series_hints in _USER_NAMED:
        keys = tuple(
            key for key in known if any(key.startswith(p) for p in prefixes)
        )
        series = tuple(
            field
            for field in series_fields()
            if any(hint in field["name"] for hint in series_hints)
        )
        # ⚠ 키 이름을 `keys` 로 두지 않는다 — Jinja 의 `row.keys` 는 **사전의
        # 메서드**를 먼저 집고, 그때 화면은 예외 없이 엉뚱한 것을 그리려 든다.
        rows.append({
            "word": word,
            "ledger_keys": keys,
            "present": bool(keys),
            "series": series,
            "note": "" if keys else _NOT_IN_LEDGER,
        })
    return tuple(rows)


def series_fields() -> tuple[dict[str, str], ...]:
    """카탈로그가 가진 **시계열 파라미터 전건** — 판정 ④ 의 「남기는 자리」다.

    ⚠ 목록을 손으로 적지 않는다. 시계열 파라미터가 하나 늘면 이 자리도 함께
    늘어야 하며, 손으로 적으면 늘어난 것이 화면에서 조용히 빠진다.
    """
    fields: list[dict[str, str]] = []
    for tag in available_resource_tags():
        for spec in resource_parameters(tag):
            if spec.kind is ParameterKind.SERIES:
                fields.append({
                    "tag": tag,
                    "name": spec.name,
                    "unit": spec.unit or NO_VALUE,
                    "reason": SERIES_OUT_OF_SCOPE,
                })
    return tuple(fields)


def ledger_groups(
    ledger: AssumptionSet,
    *,
    mine: dict[str, str] | None = None,
    reasons: dict[str, str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """대장 항목 **전건**을 첫 마디로 묶어 편다 — 목록을 줄이지 않는다.

    `mine` 은 사람이 방금 넣은 글자다. **거부돼도 그대로 되돌려 그린다**
    (오케스트레이터 판정 ⑥ · 착수 목록 44번 ⓑ) — 거부될 때마다 고치던 값을
    잃으면 사람은 그것을 「고칠 수 없다」로 읽는다.

    ⚠ **빈 「내 값」은 「안 고쳤다」이지 `0` 이 아니다.** 대장 값을 미리 채워
    두지 않는 것이 그 구별을 화면에서 서게 한다 — 채워 두면 사람이 손대지
    않은 칸이 전부 오버라이드가 된다 (`app/routers/ui_forms.py::_edited` 가
    같은 판단을 적었다).
    """
    typed = mine or {}
    why = reasons or {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for key, item in ledger.items().items():
        head = key.split(".")[0] if _GROUP_DEPTH else key
        groups.setdefault(head, []).append({
            "key": key,
            "base_text": _text(item.value),
            "mine": typed.get(key, ""),
            "reason": why.get(key, ""),
            "unit": item.value_unit or NO_VALUE,
            "confidence": item.confidence.value,
            "source": item.source or NO_VALUE,
            "overridden": bool(typed.get(key, "").strip()),
        })
    return tuple(
        {"prefix": head, "items": tuple(items)} for head, items in groups.items()
    )


def _override_rows(rows: tuple[OverrideRow, ...]) -> tuple[dict[str, str], ...]:
    """리포트의 「기준 전제 대비 변경 항목」을 **두 칸으로** 편다 (`FR-602-AC2`).

    ★ 「대장 값」과 「내 값」을 나란히 둔다 — 무엇이 바뀌었는지가 화면에서
    갈려 보여야 검토자가 *「왜 이 수인가」* 에 답할 수 있다. 한 칸만 그리면
    「기준 전제 그대로 돌렸다」와 구별되지 않는다.
    """
    return tuple(
        {
            "key": row.key,
            "base": _text(row.base_value),
            "mine": _text(row.override_value),
            "reason": row.reason or NO_VALUE,
        }
        for row in rows
    )


def applied_settings_context(
    report: CaseReport, *, settings_id: int, settings_name: str
) -> dict[str, Any]:
    """「이 설정으로 돌리면 결론이 어떻게 되나」 — **수를 다시 계산하지 않는다.**

    ⚠ `CaseReport` 가 준 값을 옮겨 적기만 한다. 화면이 인쇄하는 수가 리포트와
    어긋나면 그것이 새 결함이다 (`web/render_run.py::run_result_context` 가
    같은 자리에서 같은 판단을 적었다).

    ★ `npv_raw` 를 **날값 그대로** 함께 싣는다 — 서식을 입힌 문면만 두면
    「화면의 수가 리포트의 수와 같은가」를 기계가 대조할 수 없다. 이름
    (`data-npv`)은 `run_result.html` 이 쓰는 것과 **같게** 둔다: 두 화면이
    같은 축을 다른 이름으로 실으면 대조가 화면마다 따로 짜인다.
    """
    return {
        "id": settings_id,
        "name": settings_name,
        "scenario_name": report.scenario_name,
        "npv": _won(report.metrics["npv"]),
        "npv_raw": report.metrics["npv"],
        "overrides": _override_rows(report.overrides),
    }


def settings_context(
    ledger: AssumptionSet,
    *,
    scenario: str,
    saved: tuple[dict[str, Any], ...] = (),
    applied: dict[str, Any] | None = None,
    error: dict[str, str] | None = None,
    form: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """설정 화면의 문맥 — `FR-601`(대장 전건 표시) · `FR-602`(오버라이드).

    `form` 은 **방금 제출된 폼 그대로**다. 거부 화면이 이것을 되돌려 그린다.
    """
    submitted = form or {}
    return {
        "scenario": scenario,
        "settings_name": str(submitted.get("name", "")),
        "settings_description": str(submitted.get("description", "")),
        "user_items": user_named_items(ledger),
        "series_fields": series_fields(),
        "groups": ledger_groups(
            ledger,
            mine=submitted.get("mine"),
            reasons=submitted.get("reasons"),
        ),
        "unknown": tuple(submitted.get("unknown", ())),
        "saved": saved,
        "applied": applied,
        "error": error,
        "series_note": SERIES_OUT_OF_SCOPE,
    }


def scenarios_context(
    *,
    scenarios: tuple[dict[str, Any], ...],
    settings: tuple[dict[str, Any], ...],
    golden: tuple[str, ...],
    arrangements: tuple[str, ...],
    prerequisites: tuple[dict[str, str], ...],
    versions: tuple[dict[str, Any], ...] = (),
    versions_of: int = 0,
    saved_id: int = 0,
    deleted_id: int = 0,
    deleted_name: str = "",
    retention_days: int = 0,
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    """시나리오 화면의 문맥 — `FR-902-AC1`~`AC3`.

    ⚠ **고를 거리를 여기서 짓지 않는다.** 골든 시나리오 이름은
    `app/services/ui_run.py::golden_scenario_names`, 갈래는
    `web/render_run.py::baseline_arrangement_choices`, ⓒ 전제는
    `pool_prerequisite_fields` 가 정본이며 라우터가 그것을 건넨다.

    ⚠ **보관 기간을 화면이 적지 않는다** — `SOFT_DELETE_RETENTION_DAYS` 가
    정본이고 라우터가 건넨다. 여기 `30` 을 적으면 그 창이 두 곳에 살고,
    한쪽만 고쳐지는 날 화면이 거짓을 인쇄한다 (`FR-902-AC3`).
    """
    return {
        "scenarios": scenarios,
        "settings": settings,
        "kind_labels": _KIND_LABELS,
        "golden": golden,
        "arrangements": arrangements,
        "prerequisites": prerequisites,
        "versions": versions,
        "versions_of": versions_of,
        "saved_id": saved_id,
        "deleted_id": deleted_id,
        "deleted_name": deleted_name,
        "retention_days": retention_days,
        "error": error,
    }


def render_scenarios(context: dict[str, Any]) -> str:
    """시나리오 목록·저장 화면을 그린다 (`FR-902`)."""
    return _ENV.get_template("scenarios.html").render(context)


def render_settings(context: dict[str, Any]) -> str:
    """설정(전제) 화면을 그린다 (`FR-601`·`FR-602`)."""
    return _ENV.get_template("settings.html").render(context)
