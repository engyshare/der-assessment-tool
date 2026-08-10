"""배타 규칙 YAML 로더 — FR-402-AC4 · FR-504-AC1.

**규칙이 코드가 아닌 데이터라는 요건은 v0.3 부터 있었다.** `exclusion_table.py`
는 그것을 「`if` 문으로 옮기지 말 것」이라 적고 튜플 상수로 두었는데, **상수도
코드다** — 제도가 바뀌면 파이썬 파일을 고쳐 배포해야 하고, 그것이 FR-402-AC4
가 막으려던 상태다.

R15 가 요금표(`FR-501-AC4`)에서 정확히 같은 판단을 했다. 그때 배운 것은
**로더를 만드는 것이 아니라 로더가 실제 경로가 되게 하는 것**이 요점이라는
점이다 — 그래서 `DEFAULT_EXCLUSION_RULES` 가 이 로더를 지나 만들어진다.
아무도 쓰지 않는 로더는 없는 것과 같다.

**파일이 없으면 멈춘다.** `AssumptionProvider.require()` 와 같은 판단이다 —
규칙표가 비면 배타 검사는 「위반 0건」을 내고 통과하는데, 그것은 규칙이 없는
것이 아니라 **검사가 없는 것**이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.contracts.valuestream import ExclusionRule, ExclusionType

#: 배타 규칙 정본. `docs/` 에 두는 이유는 요금표·전제 대장과 같은 성격이기
#: 때문이다 — 제도 데이터이며 코드가 아니다.
DEFAULT_RULES_PATH: Path = (
    Path(__file__).resolve().parents[2] / "docs" / "exclusion-rules.yaml"
)


class ExclusionRulesError(ValueError):
    """규칙표를 읽을 수 없다 — **기동을 막는다.**

    경고로 흘리면 규칙 0건으로 계산이 진행되고 배타 검사가 「위반 없음」을
    낸다. 그 결과는 정상 결과와 구분되지 않는다.
    """


def load_exclusion_rules(path: str | Path = DEFAULT_RULES_PATH) -> tuple[ExclusionRule, ...]:
    """YAML 에서 배타 규칙표를 읽는다."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExclusionRulesError(
            f"배타 규칙표를 읽지 못했습니다: {source} ({exc}). "
            "규칙표가 없으면 배타 검사는 「위반 0건」을 내고 통과합니다 — "
            "규칙이 없는 것이 아니라 검사가 없는 것입니다 (FR-402-AC4)"
        ) from exc
    return load_exclusion_rules_from_text(text, source=str(source))


def load_exclusion_rules_from_text(
    text: str, *, source: str = "<yaml>"
) -> tuple[ExclusionRule, ...]:
    """문자열에서 읽는다 — 테스트가 파일을 만들지 않고도 쓸 수 있게."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExclusionRulesError(f"{source}: YAML 구문 오류 — {exc}") from exc

    if not isinstance(doc, dict):
        raise ExclusionRulesError(f"{source}: 최상위가 사전이어야 합니다")

    raw_rules = doc.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ExclusionRulesError(
            f"{source}: `rules` 목록이 비어 있습니다. 빈 규칙표는 「배타 없음」이 "
            "아니라 「검사 없음」이므로 명시적 오류로 막습니다"
        )

    rules: list[ExclusionRule] = []
    seen: set[frozenset[str]] = set()
    for index, entry in enumerate(raw_rules, start=1):
        rules.append(_build_rule(entry, where=f"{source} rules[{index}]", seen=seen))
    return tuple(rules)


def _build_rule(
    entry: Any, *, where: str, seen: set[frozenset[str]]
) -> ExclusionRule:
    if not isinstance(entry, dict):
        raise ExclusionRulesError(f"{where}: 규칙 1건은 사전이어야 합니다")

    benefit_a = _require_text(entry, "benefit_a", where=where)
    benefit_b = _require_text(entry, "benefit_b", where=where)
    if benefit_a == benefit_b:
        raise ExclusionRulesError(
            f"{where}: 같은 편익끼리 배타 관계를 둘 수 없습니다 ({benefit_a})"
        )

    # **양방향 대칭이므로 쌍을 집합으로 센다.** `(A,B)` 와 `(B,A)` 를 둘 다
    # 적으면 `collect_exclusions` 의 중복 제거에 기대게 되고, 규칙표를 읽는
    # 사람은 둘이 다른 규칙이라고 읽는다.
    pair = frozenset({benefit_a, benefit_b})
    if pair in seen:
        raise ExclusionRulesError(
            f"{where}: 이미 선언된 쌍입니다 ({benefit_a} ↔ {benefit_b}). "
            "배타 관계는 양방향 대칭이므로 한 번만 적습니다"
        )
    seen.add(pair)

    raw_type = _require_text(entry, "type", where=where)
    try:
        exclusion_type = ExclusionType(raw_type)
    except ValueError as exc:
        raise ExclusionRulesError(
            f"{where}: 배타 유형이 A~D 가 아닙니다 — {raw_type!r}. "
            "유형은 spec FR-402-AC2.<키> 와 같은 리터럴이며, 행마다 수용 수준이 "
            "반대입니다 (A 는 차단 100%, B~D 는 오탐 0)"
        ) from exc

    profile = entry.get("applies_to_profile")
    if profile is not None and not isinstance(profile, str):
        raise ExclusionRulesError(f"{where}: `applies_to_profile` 은 문자열이어야 합니다")

    return ExclusionRule(
        benefit_a=benefit_a,
        benefit_b=benefit_b,
        exclusion_type=exclusion_type,
        rationale=_require_text(entry, "rationale", where=where),
        applies_to_profile=profile,
    )


def _require_text(entry: dict[str, Any], key: str, *, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExclusionRulesError(f"{where}: `{key}` 가 없거나 비어 있습니다")
    return value.strip()
