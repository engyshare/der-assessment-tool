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
            **근거 축 두 칸의 해석**(`feasibility` · `feasibility_source` — R71/WP-10)
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

#: 받는 `feasibility` — **제도가 이것을 허용하는가**. 넷 밖은 거부한다.
#:
#: ⚠⚠ `source` 와 **다른 축**이다. `source` 는 *「이 값(150원/kWh)이 어디서 왔나」*
#: 이고 이 칸은 *「이 사업이 그것을 실제로 «할 수» 있나」* 다. 조사
#: (`.orch/R71/result_9.md`)가 둘을 따로 판정했으므로(§1 표에 「값이 현실적인가」와
#: 「적용 가능?」이 따로 있다) 대장도 따로 들며, 합치면 *「값이 시장에서 관측된다」*
#: 가 *「제도가 허용한다」* 로 조용히 승격된다 — 이 저장소가 반복해 경계한 그것이다.
FEASIBILITIES = ("확인", "조건부", "불가", "미확인")

#: 그중 **근거가 선 것**. `불가`·`미확인` 은 §4 합계에서 빠지고 §2 의 **뒤 묶음**에
#: 선다 — 크기는 그대로 인쇄한다(*「이만큼 크지만 지금은 못 한다」* 가 정보다).
GROUNDED_FEASIBILITIES = ("확인", "조건부")

#: 한 항목의 칸. `why_not` 은 `not_improvements` 에서만 **필수**다.
REQUIRED_FIELDS = (
    "id",
    "title",
    "lever",
    "precondition",
    "rationale",
    "source",
    "feasibility",
    "feasibility_source",
    "apply",
)
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
    #: **제도가 이것을 허용하는가** — `FEASIBILITIES` 넷 중 하나.
    feasibility: str
    #: 왜 그렇게 판정했나 + **근거의 등급**(원문 확인 / 간접자료 / 미확인).
    feasibility_source: str
    apply: Mapping[str, Any]
    #: `not_improvements` 만 갖는다 — *왜 방안이 아닌가*.
    why_not: str | None = None

    @property
    def unsourced(self) -> bool:
        """근거 없이 크기만 보는 값인가."""
        return NO_SOURCE_MARK in self.source

    @property
    def grounded(self) -> bool:
        """**제도 근거가 선 방안인가** — `불가`·`미확인` 이면 거짓.

        ⚠ 이것이 거짓이라고 Δ 를 지우지 않는다. 산출물은 그 크기를 그대로 인쇄하고
        **묶음을 갈라** 세우며 §4 합계에서만 뺀다 — 크기를 숨기면 *「이만큼 크지만
        지금은 못 한다」* 를 말하지 못한다(오케 판정 `.orch/R71/WP-10.md` §2④).
        """
        return self.feasibility in GROUNDED_FEASIBILITIES

    @property
    def includes_allocation(self) -> bool:
        options = self.apply.get(OPERATION_OPTIONS_FIELD) or {}
        return isinstance(options, Mapping) and _ALLOCATION_KEY in options

    @property
    def slots(self) -> frozenset[str]:
        """이 방안이 **손대는 자리**들 — 겹침 판정의 단위다 (R71/WP-10-fix).

        ★ **왜 「자리」로 재는가.** 두 방안이 같은 자리를 쓰면 그 Δ 를 더하는 것은
        **같은 개선을 두 번 세는 일**이다. 검수가 실물로 잡은 것이 그것이며
        (`small_ess_max_pv_export` 가 `pv_capacity_up`·`ess_capacity_down`·
        `pv_allocation_battery_first` 를 **이미 품고 있었다**), 그 합은
        *「결손의 9.5%만 남는다」* 로 읽혔으나 그 구성 하나를 실제로 적용한 값은
        **결손의 49.2%가 남는** 것이었다. 「상호작용 미반영」 단서로 덮을 크기가
        아니다 — **합을 내는 방식을 고쳐야 한다.**

        자리의 이름은 **사람이 읽는 문면 그대로** 만든다(`design_capacity.
        pv_capacity_kw`) — 산출물의 건너뜀 사유가 이 문자열을 그대로 인쇄하므로,
        내부 표기를 따로 두면 그 자리를 찾아갈 수 없다.
        """
        found: set[str] = set()
        overrides = self.apply.get(ASSUMPTION_OVERRIDES_FIELD) or []
        if isinstance(overrides, Sequence) and not isinstance(overrides, (str, bytes)):
            for entry in overrides:
                if isinstance(entry, Mapping) and entry.get("key"):
                    found.add(f"{ASSUMPTION_OVERRIDES_FIELD}.{entry['key']}")
        for field in (OPERATION_OPTIONS_FIELD, DESIGN_CAPACITY_FIELD):
            options = self.apply.get(field) or {}
            if isinstance(options, Mapping):
                found.update(f"{field}.{name}" for name in options)
        if "subsidy_rate" in self.apply:
            # ⚠ 지원율은 값 하나짜리 자리다 — 둘이 쓰면 그것만으로 겹친다.
            found.add("subsidy_rate")
        return frozenset(found)

    def overlapping_slots(self, other: Improvement) -> tuple[str, ...]:
        """이 방안과 `other` 가 **함께 쓰는 자리** — 비어 있으면 겹치지 않는다."""
        return tuple(sorted(self.slots & other.slots))


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


@dataclass(frozen=True)
class Skipped:
    """합계 A 에서 **건너뛴** 방안 하나 — 무엇과 어느 자리에서 겹쳤는가.

    ⚠ 건너뛴 것을 **숨기지 않는다.** 사유를 함께 나르는 자료형을 두는 이유가
    그것이며(오케 판정 `.orch/R71/WP-10-fix.md` §1①), 크기도 그대로 인쇄한다.
    """

    effect: Effect
    #: 앞서 고른 방안 — 이것과 겹쳐서 건너뛰었다.
    against: Improvement
    slots: tuple[str, ...]

    @property
    def reason(self) -> str:
        """산출물에 그대로 인쇄하는 한 줄."""
        return (
            f"`{self.against.id}` 와 `{'` · `'.join(self.slots)}` 에서 겹침 — "
            "그 방안이 이 개선을 이미 품고 있다"
        )


def choose_without_overlap(
    effects: Sequence[Effect],
) -> tuple[tuple[Effect, ...], tuple[Skipped, ...]]:
    """**Δ 내림차순으로 훑으며 앞서 고른 것과 겹치지 않는 것만 고른다.**

    ★ 이것은 *「서로 겹치지 않는 방안들의 최대 조합」* 이 **아니다** — 그것은 탐색이고
    이 도구가 지는 일이 아니다(오케 판정 `.orch/R71/WP-10-fix.md` §1①이 규칙을
    그렇게 정했다). 탐욕 규칙이므로 **큰 것이 먼저 들고** 그것이 품은 작은 방안들이
    건너뛰어진다.

    ⚠ 부르는 쪽이 **후보를 먼저 가른다** — 표현된 것 · Δ 가 양수인 것 · 근거가 선 것.
    여기서 그 셋을 다시 판정하지 않는다(같은 사실을 판정하는 자리가 둘이 되면 한쪽만
    고쳐진 상태를 아무도 보지 않는다).
    """
    picked: list[Effect] = []
    skipped: list[Skipped] = []
    for effect in sorted(effects, key=lambda one: -(one.delta_won or 0)):
        clash = next(
            (
                chosen
                for chosen in picked
                if effect.improvement.overlapping_slots(chosen.improvement)
            ),
            None,
        )
        if clash is None:
            picked.append(effect)
            continue
        skipped.append(
            Skipped(
                effect=effect,
                against=clash.improvement,
                slots=effect.improvement.overlapping_slots(clash.improvement),
            )
        )
    return tuple(picked), tuple(skipped)


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
            f"「{NO_SOURCE_MARK} — 크기만 보는 가정」 이라고 적고, 제도가 허용하는지 "
            f"모르면 `feasibility` 를 「미확인」 으로 적으십시오({' · '.join(FEASIBILITIES)})",
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
    if raw["feasibility"] not in FEASIBILITIES:
        raise _refused(
            f"{raw['id']} 의 feasibility 가 {raw['feasibility']!r} 입니다",
            f"feasibility 는 {' · '.join(FEASIBILITIES)} 중 하나입니다 — "
            "「제도가 이것을 허용하는가」이며 `source`(값의 근거)와 다른 축입니다",
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
        feasibility=str(raw["feasibility"]),
        feasibility_source=" ".join(str(raw["feasibility_source"]).split()),
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
