"""**개선 방안 대장을 읽는다** — `docs/improvements.yaml` 의 해석과 거부 (R71/WP-7).

`scripts/improvement_effects.py` 에서 갈라 나온 모듈이다. **가른 이유는 규모**다 —
한 파일에 두니 코드 565줄이 되어 `NFR-206`(소스 파일 500줄) 을 넘었고,
`scripts/check_file_size.py --code-strict` 가 *「「코드 스프롤」은 조항 취지 그대로의
위반이다. 파일을 쪼개십시오」* 로 그 조치를 그대로 지시했다. 같은 사유로 갈라진
자리가 이미 있다 — `core/assumption/scenario_overrides.py` 가
`core/report/case_report.py` 에서 나온 것이 그것이며, 그 파일 머리말이 같은 판단을
적어 둔다.

## 이 파일이 지는 것 · 지지 않는 것

    진다    한 항목의 서식 · 받는 값 · **3요소 거부**(`NFR-303`) · `id` 유일성
    안 진다 방안을 돌리는 일 · 현가 · 인쇄 — 그것은 `improvement_effects.py` 다

⚠ **여기서 값의 범위를 보지 않는다.** 대장 키가 실재하는가 · 그 자리에 이 형의 값이
들어갈 수 있는가는 `core/assumption/scenario_overrides.py` 가 이미 판정한다 — 여기서
흉내내면 같은 사실을 판정하는 자리가 둘이 되고, 한쪽만 고쳐진 상태를 아무도 보지
않는다.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.assumption.scenario_overrides import ASSUMPTION_OVERRIDES_FIELD
from core.casegrid.ledger_levels import (
    DESIGN_CAPACITY_FIELD,
    OPERATION_OPTIONS_FIELD,
)
from core.contracts.validation import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
IMPROVEMENTS_PATH = REPO_ROOT / "docs" / "improvements.yaml"

#: 방안 대장의 두 목록. 앞은 §2 에 서고 뒤는 **§5** 에 선다(합계에 넣지 않는다).
IMPROVEMENTS_KEY = "improvements"
NOT_IMPROVEMENTS_KEY = "not_improvements"

#: 받는 `lever` · `precondition`. **모르는 값은 거부한다** — 오타를 흘려보내면
#: 표의 한 칸이 조용히 뜻을 잃고, 그 상태는 「안 적었다」와 구별되지 않는다.
LEVERS = ("제도", "구성", "단가")
PRECONDITIONS = ("ⓐ", "ⓑ", "ⓒ")

#: `apply` 가 받는 오버레이 키 전건. 시나리오가 닿는 자리는 이 넷뿐이다
#: (`.orch/R71/result_5.md` §3ⓖ · R71/WP-4·WP-6 가 뒤의 둘을 열었다).
APPLY_KEYS = (
    ASSUMPTION_OVERRIDES_FIELD,
    OPERATION_OPTIONS_FIELD,
    DESIGN_CAPACITY_FIELD,
    "subsidy_rate",
)

#: 한 항목의 칸. `why_not` 은 `not_improvements` 에서만 **필수**다.
REQUIRED_FIELDS = ("id", "title", "lever", "precondition", "rationale", "source", "apply")
OPTIONAL_FIELDS = ("why_not",)

#: 근거가 없는 값의 표시. 이 문면이 `source` 에 있으면 산출물이 **그대로**
#: 인쇄한다 — 고쳐 쓰거나 줄이지 않는다.
NO_SOURCE_MARK = "근거 없음"

#: 역송이 없으면 잉여판매·REC 가 0kWh 에 곱해지므로, 배분 변경을 포함한 방안은
#: 그것을 **행에 적어야** 한다(오케 판정 §2④).
_ALLOCATION_KEY = "pv_allocation_priority"


def _refused(reason: str, action: str) -> ValidationError:
    """거부 하나 — **3요소를 갖춘다**(`NFR-303`). 문면을 한 곳에만 둔다."""
    return ValidationError(field="improvements.ledger", reason=reason, action=action)


@dataclass(frozen=True)
class Improvement:
    """방안 하나 — `docs/improvements.yaml` 한 항목 그대로."""

    id: str
    title: str
    lever: str
    precondition: str
    rationale: str
    source: str
    apply: Mapping[str, Any]
    #: `not_improvements` 만 갖는다 — *왜 방안이 아닌가*.
    why_not: str | None = None

    @property
    def unsourced(self) -> bool:
        """근거 없이 크기만 보는 값인가."""
        return NO_SOURCE_MARK in self.source

    @property
    def includes_allocation(self) -> bool:
        options = self.apply.get(OPERATION_OPTIONS_FIELD) or {}
        return isinstance(options, Mapping) and _ALLOCATION_KEY in options


@dataclass(frozen=True)
class Effect:
    """한 방안을 얹어 돌린 결과. 거부되었으면 `refusal` 만 찬다."""

    improvement: Improvement
    npv_won: int | None
    delta_won: int | None
    annual_net_won: int | None
    delta_annual_won: int | None
    refusal: str | None = None

    @property
    def expressed(self) -> bool:
        return self.refusal is None


def _item(raw: object, *, position: int, need_why_not: bool) -> Improvement:
    """한 항목을 읽어 검증한다. **모르는 칸·빈 칸을 흘려보내지 않는다.**

    ⚠ `source` 를 특히 본다 — 비어 있으면 *「근거를 적지 않았다」* 와 *「근거가
    없다」* 가 산출물에서 구별되지 않는다. 후자를 적는 자리는
    `NO_SOURCE_MARK` 문면이고, 그 표시는 §2 가 그대로 인쇄한다.
    """
    if not isinstance(raw, Mapping):
        raise _refused(
            f"{position}번째 항목이 매핑이 아닙니다: {raw!r}",
            f"한 항목은 {' · '.join(REQUIRED_FIELDS)} 칸을 갖는 매핑입니다",
        )
    known = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    unknown = sorted(str(name) for name in raw if name not in known)
    if unknown:
        raise _refused(
            f"{position}번째 항목에 모르는 칸이 있습니다: {', '.join(unknown)}",
            f"오타가 아닌지 보십시오. 쓸 수 있는 칸: {' · '.join(sorted(known))}",
        )
    missing = [name for name in REQUIRED_FIELDS if not raw.get(name)]
    if missing:
        raise _refused(
            f"{position}번째 항목({raw.get('id', '이름 없음')})의 칸이 비어 있습니다: "
            f"{', '.join(missing)}",
            "빈 칸을 채우십시오 — 근거가 없는 값이면 `source` 에 "
            f"「{NO_SOURCE_MARK} — 크기만 보는 가정」 이라고 적으십시오",
        )
    if need_why_not and not raw.get("why_not"):
        raise _refused(
            f"{raw['id']} 에 `why_not` 이 없습니다 — {NOT_IMPROVEMENTS_KEY} 의 항목은 "
            "**왜 방안이 아닌가**를 함께 적어야 합니다",
            "그 칸이 비면 산출물 §5 가 「방안이 아니다」만 말하고 사유를 말하지 "
            "못합니다",
        )
    if raw["lever"] not in LEVERS:
        raise _refused(
            f"{raw['id']} 의 lever 가 {raw['lever']!r} 입니다",
            f"lever 는 {' · '.join(LEVERS)} 중 하나입니다",
        )
    if raw["precondition"] not in PRECONDITIONS:
        raise _refused(
            f"{raw['id']} 의 precondition 이 {raw['precondition']!r} 입니다",
            f"precondition 은 {' · '.join(PRECONDITIONS)} 중 하나입니다 — "
            "ⓐ배선 · ⓑ구성 · ⓒ제도·사업판단",
        )
    apply = raw["apply"]
    if not isinstance(apply, Mapping) or not apply:
        raise _refused(
            f"{raw['id']} 의 apply 가 비었거나 매핑이 아닙니다: {apply!r}",
            f"얹을 것을 적으십시오 — 받는 키는 {' · '.join(APPLY_KEYS)} 뿐입니다",
        )
    unknown_apply = sorted(str(name) for name in apply if name not in APPLY_KEYS)
    if unknown_apply:
        raise _refused(
            f"{raw['id']} 의 apply 에 모르는 키가 있습니다: {', '.join(unknown_apply)}",
            f"시나리오가 닿는 자리는 {' · '.join(APPLY_KEYS)} 뿐입니다",
        )
    return Improvement(
        id=str(raw["id"]),
        title=str(raw["title"]),
        lever=str(raw["lever"]),
        precondition=str(raw["precondition"]),
        rationale=" ".join(str(raw["rationale"]).split()),
        source=" ".join(str(raw["source"]).split()),
        apply=apply,
        why_not=" ".join(str(raw["why_not"]).split()) if raw.get("why_not") else None,
    )


def load_improvements(
    path: Path = IMPROVEMENTS_PATH,
) -> tuple[tuple[Improvement, ...], tuple[Improvement, ...]]:
    """방안 대장을 읽는다 → (방안, 방안이 아닌 것).

    ⚠ **`id` 는 두 목록에 걸쳐 유일해야 한다.** 겹치면 산출물의 §2 와 §5 가 같은
    이름으로 다른 것을 말하고, 그 상태는 표에서 구별되지 않는다.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping) or IMPROVEMENTS_KEY not in data:
        raise _refused(
            f"{path.name} 에 `{IMPROVEMENTS_KEY}:` 목록이 없습니다",
            f"최상위 키는 `{IMPROVEMENTS_KEY}` 와 `{NOT_IMPROVEMENTS_KEY}` 입니다",
        )
    groups: list[tuple[Improvement, ...]] = []
    for key, need_why_not in ((IMPROVEMENTS_KEY, False), (NOT_IMPROVEMENTS_KEY, True)):
        raw = data.get(key) or []
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise _refused(
                f"{key} 가 목록이 아닙니다: {raw!r}", "목록으로 적으십시오"
            )
        groups.append(
            tuple(
                _item(item, position=index, need_why_not=need_why_not)
                for index, item in enumerate(raw)
            )
        )
    seen: set[str] = set()
    for item in (*groups[0], *groups[1]):
        if item.id in seen:
            raise _refused(
                f"같은 id 를 두 번 적었습니다: {item.id}",
                "id 는 두 목록에 걸쳐 한 번만 씁니다",
            )
        seen.add(item.id)
    return groups[0], groups[1]
