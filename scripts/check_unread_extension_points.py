#!/usr/bin/env python3
"""**읽는 배포 코드가 있는가** — 계약이 내놓은 훅·필드 중 아무도 읽지 않는 것.

## 왜 이 검사가 필요한가

이 저장소가 **다섯 번** 만난 형태다. 매번 「선언·계산은 있는데 읽는 쪽이 없다」
였고, **전부 사람이 변이를 심어서야** 드러났다.

    R32  CaseVariant.overrides()   소비자 0곳 → 보조율 15% 변형이 입력안과
                                   **똑같은 NPV** 를 냈다
    R32  ValueStream.exclusions()  소비자 0곳 → 배타 선언을 지우는 변이가
                                   **전건 초록불**이었다
    R32  비용 행 부호 규약          읽는 쪽이 없어 고정 O&M 이 편익으로 더해졌다
    R33  build_dispatch_notes()    `FR-105-AC4` 가 「자동」인데 표기하는
                                   리포트가 **없었다**
    R33  replacement_schedule()    조항은 「자동」인데 실행 경로 호출 0곳

공통점은 **매핑표가 초록불이었다**는 것이다 — 단위 테스트가 그 함수를 직접
부르므로 조항은 검증된 것으로 세어진다. 그런데 *제품이 그것을 쓰는가* 는
아무도 묻지 않았다. 지금까지는 사람이 `grep -rn "\\.exclusions()" core app infra`
를 해야 알 수 있었다.

## 판정 규칙

**선언** — `core/contracts/**` 의 클래스가 내놓는 공개 이름:
메서드(`def name`, `_` 로 시작하지 않는 것)와 주석 붙은 클래스 필드.

**읽기** — `core/` · `app/` · `infra/` · `web/` 의 **속성 접근**(`ast.Attribute`)
중 그 이름을 쓰는 것. 단 **선언한 파일 자신은 세지 않는다** — 자기 모듈 안에서만
쓰이는 훅은 밖으로 내놓은 적이 없는 것과 같다.

**위반** — 선언됐는데 읽는 배포 코드가 0곳.

### ★ 문자열을 세지 않는다 — 반대 방향의 실패

`grep` 으로 세면 *「`core.der.pv` 를 예로 들면」* 이라고 적은 **주석이 소비자로
세어져 게이트가 조용히 초록불**이 된다. 이 저장소의 6.7·2.6 이 정확히 그
형태였고, 7번은 「위반이 통과로 보고되는」 조용한 실패라 더 나빴다. 그래서
`ast` 로 **속성 접근만** 뽑는다 — 독스트링·주석·문자열 리터럴은 애초에 후보가
아니다.

### ★ `assert` 안에서만 읽히는 것은 따로 센다 (R24)

`python -O` 는 `assert` 를 통째로 지운다. 그 안에서만 읽는다면 **최적화된
런타임에는 읽는 코드가 없다.** 세지 않으면 놓치고, 그냥 세면 사라질 읽기를
읽기로 친다 — 그래서 세되 **별도로 표시**한다.

## ⚠ 아래 목록은 **면제 목록이 아니라 부채 목록**이다

지금 37건이 있고 그것을 이 라운드에 다 배선할 수는 없다. 그래서 **얼어붙인다** —
`KNOWN_UNREAD` 와 실측이 다르면 종료 코드 1 이다. **늘면 즉시 빨개지고**,
줄었는데 목록을 안 고쳐도 빨개진다(고인 항목은 래칫을 조용히 느슨하게 만든다).

**여기 이름을 더해 통과시키지 말 것.** 더하는 것은 *「이 훅을 아무도 읽지
않는 채로 두기로 했다」* 는 선언이며, 커밋 메시지에 그 이유를 적어야 한다.

    python scripts/check_unread_extension_points.py     rc=0 이면 목록과 일치
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 훅을 **내놓는** 층. 계약이 여기 있고, 계약이 내놓은 것을 제품이 읽어야 한다.
DECLARING_ROOTS: tuple[str, ...] = ("core/contracts",)

#: 훅을 **읽어야 하는** 층. `tests/` 는 여기 없다 — 그것이 이 검사의 요점이다.
CONSUMING_ROOTS: tuple[str, ...] = ("core", "app", "infra", "web")

#: 배포 코드가 읽지 않는 것으로 **이미 알려진** 이름. 부채 목록이며 면제
#: 목록이 아니다 (위 머리말 참조). 2026-08-17 실측.
KNOWN_UNREAD: frozenset[str] = frozenset({
    "annual_steps",
    "as_float",
    "as_ref",
    "capex_hardware",
    "capex_software",
    "capex_vat",
    "carries_cool",
    "carries_electric",
    "carries_heat",
    "check_data",
    "clauses",
    "consumes_fuel",
    "describe",
    "draw",
    "end_of_life_action",
    "exclusions",
    "fuel_price_signal_won_per_kwh",
    "is_full_year",
    "notes",
    "order",
    "payer_by_structure",
    # R42 신설. **접근자를 통해서만 읽는 속성**이며 `end_of_life_action` 과 같은
    # 갈래다 — 배포 코드가 읽는 것은 `replacement_escalation_factor()` 쪽이고
    # (`pv.py`·`ess.py`·`ev_v2g.py`·`load.py`·`thermal_load.py` 의 교체 경로),
    # 원시 속성을 밖에서 읽으면 「계수」와 「그 해의 계수」가 한 이름에 겹친다.
    # 러너는 이 이름을 **생성자 인자로** 넘긴다(읽기가 아니다).
    "replacement_escalation_rate",
    "require",
    "resource_tag",
    "salvage_hardware",
    "salvage_software",
    "source_total",
    "total_unmet",
    "unallocated",
    "unmet_cool",
    "unmet_electric",
    "unmet_fuel",
    "unmet_heat",
    # ⚠ `value_streams` 는 **R57/WP-4 에 목록에서 빠졌다** — `core/casegrid/
    # ess_share_benefits.py` 가 몫 자원의 `value_streams()` 를 불러 그 몫의
    # 편익 태그를 얻는다(표를 베끼지 않으려고 정본을 호출한다). 이 검사가
    # 「읽히기 시작했다」로 rc=1 을 냈고 그것이 옳은 판정이라 지웠다.
    #
    # ✔ **이제 실행 경로가 읽는다** (R57/WP-6 · `dd19cdc`). R57/WP-4 시점에
    # 이 자리는 *「읽는 자리가 아직 실행 경로는 아니다 — 러너 배선이 서면
    # 그때 실행 경로에서도 읽힌다」* 라고 적었고, **그 배선이 WP-6 에 섰다**:
    # `run_single_case_e2e` → `ess_build.build_case_ess_fleet` →
    # `split_ess` → `build_share_benefits` → `plan.resource.value_streams()`.
    # ⚠ 그 예고 문장을 지우지 않고 여기 남긴 이유는, **한 라운드 안에서
    # 「배선을 기다리는 읽기」가 「실행 경로의 읽기」로 바뀐 경위**가 이
    # 래칫을 읽는 다음 사람에게 그 자체로 재료이기 때문이다.
    "variable_om",
    "year_fraction",
})

LINE = "─" * 78


def _python_files(roots: tuple[str, ...]) -> list[Path]:
    seen: dict[Path, None] = {}
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            seen.setdefault(path, None)
    return list(seen)


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _declarations() -> dict[str, list[tuple[Path, str]]]:
    """계약 층이 내놓는 공개 이름 → [(파일, 클래스)]."""
    found: dict[str, list[tuple[Path, str]]] = {}
    for path in _python_files(DECLARING_ROOTS):
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                name = _public_name(item)
                if name is not None:
                    found.setdefault(name, []).append((path, node.name))
    return found


def _public_name(item: ast.stmt) -> str | None:
    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
        return None if item.name.startswith("_") else item.name
    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
        return None if item.target.id.startswith("_") else item.target.id
    return None


def _reads() -> tuple[dict[str, set[Path]], dict[str, set[Path]]]:
    """(전체 읽기, `assert` 안에서만인 읽기).

    ★ `ast.Assert` 안을 **함께 걷는다** — 걷지 않으면 놓치고, 구별하지 않으면
    `python -O` 에서 사라질 읽기를 읽기로 친다 (R24).
    """
    everywhere: dict[str, set[Path]] = {}
    asserted: dict[str, set[Path]] = {}
    for path in _python_files(CONSUMING_ROOTS):
        tree = _parse(path)
        if tree is None:
            continue
        in_assert: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                for inner in ast.walk(node):
                    in_assert.add(id(inner))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            everywhere.setdefault(node.attr, set()).add(path)
            if id(node) in in_assert:
                asserted.setdefault(node.attr, set()).add(path)
    return everywhere, asserted


def main() -> int:
    declarations = _declarations()
    everywhere, asserted = _reads()

    unread: list[str] = []
    assert_only: list[tuple[str, set[Path]]] = []
    for name, sites in declarations.items():
        owners = {path for path, _cls in sites}
        consumers = everywhere.get(name, set()) - owners
        if not consumers:
            unread.append(name)
            continue
        if consumers <= (asserted.get(name, set()) - owners):
            assert_only.append((name, consumers))

    measured = frozenset(unread)
    print("확장점 소비 검사 — 계약이 내놓은 것을 배포 코드가 읽는가")
    print(LINE)
    print(f"· 선언 {len(declarations)}건 / 읽는 배포 코드 0곳 {len(measured)}건")

    if assert_only:
        print()
        print("⚠ `assert` 안에서만 읽힌다 — `python -O` 에서 사라진다 (R24)")
        for name, paths in sorted(assert_only):
            where = " · ".join(sorted(str(p.relative_to(ROOT)) for p in paths))
            print(f"    {name}  ←  {where}")

    added = sorted(measured - KNOWN_UNREAD)
    healed = sorted(KNOWN_UNREAD - measured)
    if not added and not healed:
        print(LINE)
        print("통과 — 부채 목록과 실측이 같습니다")
        return 0

    print(LINE)
    if added:
        print(f"✗ 읽는 배포 코드가 없는 것이 {len(added)}건 늘었습니다")
        for name in added:
            sites = declarations[name]
            where = " · ".join(
                f"{path.relative_to(ROOT)}::{cls}" for path, cls in sites
            )
            print(f"    {name}  ←  {where}")
        print()
        print("  훅을 내놓았으면 **제품이 그것을 읽어야** 합니다. 단위 테스트가")
        print("  직접 부르는 것은 매핑표를 초록불로 만들 뿐, 제품이 쓴다는 뜻이")
        print("  아닙니다 — 이 저장소가 다섯 번 만난 형태입니다.")
        print("  읽는 자리를 만들 수 없다면 KNOWN_UNREAD 에 더하고 **커밋")
        print("  메시지에 그 이유를 적으십시오.**")
    if healed:
        print(f"✓ 읽히기 시작한 것이 {len(healed)}건 있습니다 — 목록에서 지우십시오")
        for name in healed:
            print(f"    {name}")
        print()
        print("  고인 항목은 래칫을 조용히 느슨하게 만듭니다. 그 이름이 다시")
        print("  읽히지 않게 되어도 아무도 모릅니다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
