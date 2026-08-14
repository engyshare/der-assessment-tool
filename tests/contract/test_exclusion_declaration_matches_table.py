"""편익 클래스의 배타 **선언**이 정본 표와 같은가 — `FR-402-AC4` / R32.

## ★★★ R32 가 변이로 찾은 것 — 선언을 읽는 배포 코드가 0곳이었다

`ValueStream.exclusions()` 는 계약이 제공하는 훅이고 편익 클래스 여섯이 그것을
구현하고 있다. 그런데 **그 값을 읽는 배포 코드가 한 줄도 없다** —
`assert_no_exclusions()`·`collect_exclusions()` 는 `docs/exclusion-rules.yaml`
(정본)만 본다(`grep -rn "\\.exclusions()" core app infra` → 0건).

R32 가 `AggregatedPPA` 를 신설하고 **클래스 선언에서 자가소비 배타를 지우는
변이**를 심었더니 **전건 초록불**이었다. 즉 클래스가 *「나는 자가소비와 배타다」*
라고 적든 안 적든, 심지어 **표와 반대로** 적어도 아무 일도 일어나지 않는다.

> **이 저장소가 반복해 만난 형태의 17번째다.** 앞선 것들은 「검사가 실제보다 넓게
> 주장한다」였고, 이것은 **선언이 아무것도 강제하지 않는다** — R24 가 `DV-10`
> 에서 만난 「계산하고 저장만 하며 읽는 코드가 0곳」과 같은 자리다.

## 무엇을 여기서 붙드는가 — **한 방향이다**

`docs/exclusion-rules.yaml` **이 정본**이므로 선언을 강제 경로로 바꾸지 않는다
(그렇게 하면 규칙이 다시 코드로 돌아가고 `FR-402-AC4` 가 깨진다). 대신 **선언이
정본과 어긋나지 못하게** 한다:

    클래스가 선언한 (상대, 유형) 은 정본 표에 같은 유형으로 있어야 한다

반대 방향(표의 모든 행을 클래스가 선언해야 한다)은 **두지 않는다** — 제도 한정
규칙(유형 D)은 편익의 물리적 성질이 아니라 제도가 금지하는 것이므로 클래스가
선언할 근거가 없다. 그 방향까지 요구하면 제도 규칙을 클래스에 베껴 적게 되고,
그것이 정본을 둘로 만든다.
"""

from __future__ import annotations

import pytest

from core.contracts.valuestream import ExclusionType, ValueStream
from core.valuestream.exclusion_table import DEFAULT_EXCLUSION_RULES


#: 인스턴스를 만들지 않고 선언만 읽는다 — 생성자 인자가 편익마다 다르므로
#: 인스턴스화를 요구하면 이 검사가 **편익 목록의 사본**을 갖게 된다.
#:
#: `exclusions()` 가 `self` 를 보지 않는 것이 그 전제이며, 보게 되면 여기서
#: `TypeError` 가 나서 드러난다(조용히 통과하지 않는다).
def _declared_pairs() -> list[tuple[str, str, ExclusionType, str]]:
    import core.valuestream  # noqa: F401  — 서브클래스를 import 로 등재한다

    out: list[tuple[str, str, ExclusionType, str]] = []
    for cls in ValueStream.__subclasses__():
        tag = getattr(cls, "tag", None)
        if not tag:
            continue
        try:
            declared = cls.exclusions(cls)  # type: ignore[arg-type]
        except TypeError:
            pytest.fail(
                f"{cls.__qualname__}.exclusions() 가 인스턴스 상태를 봅니다 — "
                "배타 선언은 클래스의 성질이어야 합니다(인스턴스마다 달라지면 "
                "정본 표와 대조할 수 없습니다)"
            )
        for other, kind, rationale in declared:
            out.append((tag, other, kind, rationale))
    return out


@pytest.mark.contract
@pytest.mark.req("FR-402-AC4")
def test_every_class_declaration_exists_in_the_canonical_table() -> None:
    """★★★ 클래스가 선언한 배타는 **정본 표에 같은 유형으로** 있어야 한다.

    없으면 그 선언은 아무것도 강제하지 않는 문장이고, 읽는 사람은 금지가 걸려
    있다고 믿는다. 표는 양방향 대칭이므로(한 번만 적는 규약) 두 순서를 함께 본다.
    """
    table = {
        frozenset((r.benefit_a, r.benefit_b)): r.exclusion_type
        for r in DEFAULT_EXCLUSION_RULES
    }
    declared = _declared_pairs()

    assert declared, (
        "편익 클래스의 배타 선언을 하나도 읽지 못했습니다 — 이 검사가 아무것도 "
        "붙들지 않는 상태입니다"
    )

    missing = [
        (tag, other, kind)
        for tag, other, kind, _ in declared
        if frozenset((tag, other)) not in table
    ]
    assert not missing, (
        "정본 표에 없는 배타를 클래스가 선언하고 있습니다: "
        f"{missing} — `docs/exclusion-rules.yaml` 에 더하거나 선언을 지우십시오. "
        "선언만으로는 아무것도 막히지 않으므로, 그대로 두면 「금지돼 있다고 믿는데 "
        "통과하는」 조합이 남습니다"
    )

    mismatched = [
        (tag, other, kind, table[frozenset((tag, other))])
        for tag, other, kind, _ in declared
        if table.get(frozenset((tag, other))) not in (None, kind)
    ]
    assert not mismatched, (
        "클래스 선언과 정본 표의 **유형**이 다릅니다 (클래스, 상대, 선언, 정본): "
        f"{mismatched} — 유형이 수용 수준을 정하므로(A 는 거부·B~D 는 표시) "
        "어긋나면 같은 조합이 층마다 다르게 판정됩니다"
    )
