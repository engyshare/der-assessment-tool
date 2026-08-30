#!/usr/bin/env python3
"""**그물 ③-1** — 조항이 지목한 구획을 그 조항의 인용이 실제로 만지는가.

## 왜 이 검사가 필요한가

R37 이 세운 두 그물은 인용의 **내용을 보지 않는다** — 하나는 인용 건수를 세고
(1건뿐인 조항), 다른 하나는 Phase 를 견준다. R38 이 `FR-101-AC3` 에서 그 둘
사이로 빠져나가는 형태를 찾았다: *「인용이 여럿인데 그 전부가 다른 조항을
잰다」*. 그때 조항은 **「코어 엔진」을 명시**하는데 인용 2건 어느 쪽도
`core.engine` 을 **import 하지 않았다** — 문자열로 `"core.engine"` 을 **금지
목록에 담고 있었을 뿐**이다 (`.orch/R38/result_ac3_empty.md:325-339`).

    조항 문면이 구획을 명시한다
        → 그 조항의 인용 **중 적어도 하나**는 그 구획을 실제로 `import` 한다

★ **`import` 문만 세고 문자열 리터럴은 세지 않는다.** 그 구분이 이 검사의
판정 그 자체다 — 위 결함이 정확히 「문자열로는 적혀 있는데 만지지는 않는다」
였다. `check_docstring_references.py`·`check_test_accompaniment.py` 가 이미
쓰는 `ast` 판단과 같다.

★ **조항 단위로 묻는다.** 검사 하나씩 훑어 「이 검사는 엔진을 안 만진다」로
빨간불을 내면 정당한 분업이 전부 위반이 된다. 인용 여럿 중 **하나라도**
만지면 그 조항은 구획에 닿아 있다.

## 사전을 **좁게** 둔다

R38 이 스스로 적었다 — *「조항이 구획을 은유로 적을 때 오탐이 난다. 사전을
좁게 두고 못 잡는 것을 감수한다」*. 그래서 `PARTITIONS` 는 R38 이 이름을 든
셋(엔진·리포트·요금엔진)만 담는다. **넓히려면 아래 부채 대장이 함께 움직이며,
그 움직임이 곧 사람이 검토할 자리다.**

## 부채 대장 — `KNOWN_GAPS`

실측하면 지금 저장소에 **9건**이 걸린다(R44 · WP-14 가 10건으로 세웠고 WP-15 가
`FR-402-AC7` 하나를 닫았다). 면제 목록이 아니라 **부채 목록**이며
(R42 `check_dependency_audit` 가 세운 형태 — *「막는 것은 취약점이 아니라
아무도 안 본 취약점이다」*), 두 갈래가 섞여 있고 사유에 갈래를 적었다.

    사각지대   조항이 구획을 **만지지 말라**고 적은 경우(`import 금지` ·
               `diff 0줄` · `수정이 발생하지 않는다`). 그물의 물음이 뒤집히므로
               판정할 수 없다. **저장소의 어긋남이 아니라 그물의 한계다.**
    부채       조항이 리포트 표시를 요구하는데 그 조항의 인용 중 `core.report`
               를 만지는 것이 하나도 없다. **실물 결손이다.**

★ **남은 부채 6건은 「시험이 없다」가 아니라 「리포트가 그 표시를 내지 않는다」
다.** WP-15 가 여섯을 하나씩 실물 대조했다 — `AllocationResult`(FR-106-AC5) ·
`DistributedBenefit.is_policy_assumed()`(FR-404-AC1) ·
`AssumptionSet.overridden_items()`(FR-602-AC2) ·
`TechCatalogItem`/`EscalationDetail`(FR-603-AC2) ·
`BaselineComparison.baseline_total()`(FR-705-AC1) ·
`TimeSeriesDataset.source_metadata()`(FR-905-AC8) 가 전부 *「리포트가 표시하도록」*
독스트링에 적혀 있으면서 **`core/report/` 에 호출자가 0곳**이다. 그러므로 이
여섯은 시험을 더해서 닫을 수 없고, 닫으려면 리포트 문면이 먼저 생겨야 한다
(`.orch/R44/result_15.md` 「판정 요구」).

실측과 대장이 어긋나면 — 늘어도, 줄었는데 대장을 안 고쳐도 — **종료 코드 1**
이다. 그래야 새로 생긴 결손이 조용히 섞이지 않는다.

## 종료 코드

    0  실측이 대장과 같다 (`--ledger off` 면 결손 0건)
    1  대장에 없는 결손이 생겼다 · 대장에 있는데 실측되지 않았다
       (`--ledger off` 면 결손이 1건이라도 있다)
    2  검사가 성립하지 않는다 (spec 파싱 결함 · 조항 0건 · 인용 0건 ·
       구획을 명시한 조항 0건)

    python scripts/check_clause_partition.py
    python scripts/check_clause_partition.py --spec ... --tests ... --ledger off
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _citations import DEFAULT_SPEC, DEFAULT_TESTS, by_clause, collect, criteria

#: 조항 문면의 낱말 → 그 낱말이 가리키는 구획(모듈 접두).
#:
#: **좁게 둔다** (위 머리말 참조). `코어 엔진` 과 `core/engine` 을 둘 다 두는
#: 것은 같은 구획을 spec 이 두 표기로 적기 때문이며, 판정은 구획 단위로
#: 합쳐진다.
PARTITIONS: dict[str, str] = {
    "코어 엔진": "core.engine",
    "core/engine": "core.engine",
    "요금엔진": "core.regulation.tariff",
    "리포트": "core.report",
}

#: (수용기준 ID, 구획) → 사유. **부채 목록이며 면제 목록이 아니다.**
#: 2026-08-30 실측 (R44 · WP-14).
KNOWN_GAPS: dict[tuple[str, str], str] = {
    ("FR-401-AC1", "core.engine"): (
        "사각지대 — 조항이 「편익을 추가·비활성화해도 코어 엔진(core/engine/·"
        "core/cba/) 수정이 발생하지 않는다」로 **만지지 말 것**을 요구한다. "
        "그 부재를 재는 검사에게 import 를 요구하는 것은 물음이 뒤집힌 것이다"
    ),
    ("NFR-201-M1", "core.engine"): (
        "사각지대 — 「신규 자원 추가 PR에서 core/engine/, core/cba/ diff 0줄」. "
        "diff 는 git 이 재는 것이지 import 로 재는 것이 아니다. ⚠ 이 조항을 "
        "실제로 재는 것이 없다는 별개의 부채는 R38 이 이미 신고했다"
        "(.orch/R38/result_ac3_empty.md:419)"
    ),
    ("NFR-208-AC1", "core.engine"): (
        "사각지대 — 「역방향 import 금지 (예: core/der/ → core/engine/ 금지)」. "
        "금지를 재는 검사는 그 구획을 **문자열 금지 목록**으로 들고 있는 것이 "
        "옳다. R38 이 본 `FR-101-AC3` 의 인용 2건이 바로 이 검사들이었고, "
        "AC3 쪽은 마커가 옮겨져 지금 초록불이다"
    ),
    ("FR-106-AC5", "core.report"): (
        "부채 — 「선택한 안분 규칙이 리포트에 명시된다」인데 인용 10건이 전부 "
        "tests/asset/test_common_asset.py 이고 core.report 를 만지지 않는다. "
        "안분 계산은 재고 **리포트 표기는 아무도 재지 않는다**"
    ),
    ("FR-404-AC1", "core.report"): (
        "부채 — 「«정책 가정 편익 — 현행 제도 미반영» 경고를 리포트 상단에 "
        "표시」인데 인용 4건이 전부 tests/der/test_ev_v2g.py 다"
    ),
    ("FR-602-AC2", "core.report"): (
        "부채 — 「리포트에 «기준 전제 대비 변경 항목» 목록이 자동 생성된다」인데 "
        "인용 1건(tests/assumption/test_set.py)은 전제 집합만 잰다"
    ),
    ("FR-603-AC2", "core.report"): (
        "부채 — 「카탈로그 값과 사용자 변경값이 리포트에서 시각적으로 구분된다」"
        "인데 인용 1건(tests/assumption/test_catalog.py)은 카탈로그만 잰다"
    ),
    ("FR-705-AC1", "core.report"): (
        "부채 — 「기준선 자체 비용도 리포트에 표시」. 인용 2건"
        "(tests/cba/test_baseline.py · tests/der/test_heatpump.py)이 계산만 잰다"
    ),
    ("FR-905-AC8", "core.report"): (
        "부채 — 「출처 메타데이터를 보유하고 리포트에 표기한다」. 인용 1건"
        "(tests/assumption/test_timeseries.py)은 보유만 잰다"
    ),
}


def touches(imported: frozenset[str], module: str) -> bool:
    """`import` 이름 하나라도 그 구획 **안**을 가리키는가."""
    return any(
        name == module or name.startswith(f"{module}.") for name in imported
    )


def find_gaps(
    clause_texts: dict[str, str], cited: dict[str, list]
) -> tuple[list[tuple[str, str, int]], int]:
    """(조항, 구획, 인용 건수) 결손 목록. 그리고 판정한 (조항, 구획) 쌍 수.

    인용이 **0건**인 조항은 건너뛴다 — 미매핑은 `check_task_mapping.py` 와
    `NFR-107` 의 소관이고, 여기서 함께 세면 같은 사실을 두 게이트가 소유한다.
    """
    gaps: list[tuple[str, str, int]] = []
    judged = 0
    for cid, text in sorted(clause_texts.items()):
        modules = sorted(
            {mod for word, mod in PARTITIONS.items() if word in text}
        )
        cites = cited.get(cid, [])
        if not cites:
            continue
        for module in modules:
            judged += 1
            if not any(touches(c.imports, module) for c in cites):
                gaps.append((cid, module, len(cites)))
    return gaps, judged


def main() -> int:
    ap = argparse.ArgumentParser(description="그물 ③-1 — 조항이 지목한 구획을 인용이 만지는가")
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    ap.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    ap.add_argument(
        "--ledger",
        choices=("enforce", "off"),
        default="enforce",
        help="off 면 부채 대장을 무시하고 실측 결손을 그대로 판정한다 "
             "(결손 1건이라도 있으면 rc=1). 합성 입력용이다",
    )
    args = ap.parse_args()

    clause_texts, spec_defects = criteria(args.spec)
    if spec_defects:
        print(f"ERROR: spec 파싱 결함 {len(spec_defects)}건 — 조항 목록을 믿을 수 없다",
              file=sys.stderr)
        for d in spec_defects[:10]:
            print(f"  {d}", file=sys.stderr)
        return 2
    if not clause_texts:
        print("ERROR: 수용기준 0건 — 검사를 수행하지 못했다", file=sys.stderr)
        return 2

    citations, cite_defects = collect(args.tests)
    if cite_defects:
        print(f"ERROR: 테스트 파싱 결함 {len(cite_defects)}건", file=sys.stderr)
        for d in cite_defects[:10]:
            print(f"  {d}", file=sys.stderr)
        return 2
    if not citations:
        print("ERROR: 인용 0건 — 검사를 수행하지 못했다", file=sys.stderr)
        return 2

    cited = by_clause(citations)
    gaps, judged = find_gaps(clause_texts, cited)
    if judged == 0:
        print("ERROR: 구획을 명시한 조항이 0건 — 사전이 spec 문면과 갈렸다",
              file=sys.stderr)
        return 2

    print(
        f"조항 {len(clause_texts)}건 · 인용 {len(citations)}건 · "
        f"구획을 명시한 (조항,구획) {judged}쌍 · 결손 {len(gaps)}건"
    )

    if args.ledger == "off":
        # 대장 없이 **실측 그대로** 판정한다. 합성 입력에는 대장이 적용될 수
        # 없으므로(대장은 실물 조항 ID 로 적혀 있다) 음성 시험은 이 갈래로
        # 「심은 위반이 잡히는가」를 잰다.
        for cid, module, n in gaps:
            print(f"  {cid}  구획 {module}  인용 {n}건 — 만지는 인용 없음")
        return 1 if gaps else 0

    measured = {(cid, module) for cid, module, _ in gaps}
    fresh = sorted(measured - set(KNOWN_GAPS))
    vanished = sorted(set(KNOWN_GAPS) - measured)

    if fresh:
        print(f"\n대장에 없는 결손 {len(fresh)}건 — 조항이 구획을 명시하는데 "
              "그 구획을 만지는 인용이 하나도 없다:")
        counts = {(cid, mod): n for cid, mod, n in gaps}
        for cid, module in fresh:
            print(f"  {cid}  구획 {module}  인용 {counts[(cid, module)]}건")
    if vanished:
        print(f"\n대장에 있는데 실측되지 않은 항목 {len(vanished)}건 — "
              "결손이 닫혔거나 문면이 바뀌었다. 대장에서 빼라:")
        for cid, module in vanished:
            print(f"  {cid}  구획 {module}")
    if fresh or vanished:
        return 1

    print(f"실측이 부채 대장과 같다 (사각지대·부채 {len(KNOWN_GAPS)}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
