"""NFR-202 정책·시장 파라미터 하드코딩 · NFR-205 전역 가변 상태 — 작업 2.9.

두 조항을 한 도구에 둔 이유: 둘 다 **소스의 최상위 대입을 훑는** 검사이고, 훑는
방식(`ast` 로 모듈·클래스 수준 바인딩을 본다)이 같다. 따로 두면 같은 순회를 두
번 쓰게 되고, 둘 중 하나만 대상 디렉터리가 늘어나는 표류가 생긴다.

── NFR-202 무엇을 위반으로 보는가 ───────────────────────────────────────

조항 문면은 *"요금표·설비단가·지원 조건 등 **정책·시장 파라미터**는 코드에
하드코딩되지 않아야 한다"* 이고 M1 은 *"소스 전체 수치 리터럴 스캔 lint 통과"*
다. 그런데 **「수치 리터럴 금지」로 구현할 수는 없다** — `core/` 에만 리터럴이
495개 있고 대부분은 0·1·인덱스·단위 상수다. 전부 금지하면 통과할 수 없고,
통과할 수 없는 검사는 꺼진다.

그래서 판정 대상을 **`docs/assumptions.yaml` 의 값이 소스에 복제되었는가**로
잡는다. 작업 16.1이 「나중에 값을 교체할 수 있다」를 세 장치로 성립시켰는데
(대장 · `check_assumptions.py` · **이 검사**), 셋째가 막으려는 것이 정확히
그것이다 — *"대장만 있으면 누군가 값을 소스에 옮겨 적는다."* 옮겨 적히는 순간
회신이 와도 코드가 바뀌어야 하고, 그때 대장은 **정본이 아니라 사본**이 된다.

**차단과 경고를 값의 성질로 가른다.**

    차단     `value_unit` 이 「원」으로 시작하고 |값| ≥ 10,000
             설비단가·요금·예산이다. 이 크기의 «원» 값은 소스에 우연히
             나타나지 않는다 — 물리·시간 상수 중 원 단위인 것은 없다.

    경고     |값| ≥ 1,000 이지만 원 단위가 아닌 것
             `load.household.annual` 은 3,600 kWh 인데 소스의
             `SECONDS_PER_HOUR` 도 3600 이다. 기계가 가를 수 없으므로 대장 키와
             함께 보고하고 사람이 본다.

    판정 안 함  |값| < 1,000
             `fee.direct_trade_support` 는 5원이고 `capex.modular_house.
             premium` 은 15% 다. 4·5·15·30 은 인덱스로도 시간으로도 쓰이며,
             실측하니 이 대역만으로 **경고가 26건** 나왔다. 전부 충돌이었다.

**「판정 안 함」을 조용히 버리지 않고 건수를 출력한다.** 검사가 무엇을 보지
않았는지 말하지 않으면, 읽는 사람은 「전부 검사했고 깨끗하다」로 읽는다. 그리고
**읽히지 않는 경고는 탐지 장치가 아니다** — 26건을 그대로 두면 다음 사람은
경고 절 전체를 건너뛰게 되고, 그때는 진짜 복제가 섞여 들어와도 보이지 않는다.

두 문턱은 **판정을 위한 것이지 조항의 값이 아니다.** 조항은 크기를 말하지
않는다. 문턱을 없애면 첫 실행부터 빨간불이 되고, 통과시키려고 대장을 고치게
된다 — 검사를 통과시키려고 정본을 고치는 것은 이 저장소가 반복해서 경계해 온
유형이다.

**이 검사가 잡지 못하는 것.** 대장에 **없는** 정책 파라미터는 보이지 않는다.
`core/der/heatpump.py` 의 `vat_rate=0.1`(부가세율)이 그 예다 — 실재하는
정책 수치인데 대장에 없어 이 검사를 통과한다. 그것은 lint 의 한계가 아니라
**대장의 결손**이며, 고칠 자리는 `docs/assumptions.yaml` 이다.

**우연한 충돌 — `COINCIDENTAL_LITERALS`(R51/WP-2-fix).** 차단 규칙은 소스
리터럴의 맥락(금액인지 개수인지)을 보지 않는다 — 일부러 그렇다, 사람이 한
번은 보게 만드는 것이 요점이다. 사람이 보고 「우연이다」로 판정한 (경로, 값)
쌍만 이 목록에 올려 차단을 경고로 내린다. **감추지 않는다** — 면제된 줄도
경고로 계속 인쇄되고 사유가 붙는다. **사유가 비면 검사가 거부하고**(rc=2),
**스캔에 있는 경로인데 더 이상 충돌하지 않으면 검사가 rc=1 로 말한다**(낡은
면제는 다음 사람에게 없는 위험이 있다고 거짓말한다).

── NFR-205 무엇을 위반으로 보는가 ───────────────────────────────────────

모듈·클래스 수준에서 **가변 컨테이너**(dict·list·set)에 묶인 이름. 근거는
DER-VET `Params.py` 의 클래스 변수 전역 상태이며, 그것이 동시 실행(FR-805
케이스 그리드)과 테스트 격리(§16 W-5)를 동시에 불가능하게 만들었다.

**읽기 전용으로 쓰고 있어도 위반이다.** 지금 아무도 고치지 않는다는 것은
다음 사람도 고치지 않는다는 보장이 아니고, 병렬 실행에서 한 번의 변형은
**다른 케이스의 결과를 조용히 바꾼다.** `MappingProxyType`·`tuple`·`frozenset`
로 바꾸면 그 가능성 자체가 사라진다.

    종료 코드 0  차단 대상 위반 없음 (경고는 있을 수 있다)
    종료 코드 1  차단 대상 위반
    종료 코드 2  검사가 성립하지 않음 (대장 부재·대상 파일 0개)
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

#: 차단 문턱. 위 독스트링 「두 문턱은 판정을 위한 것이지」 참조.
MONEY_FLOOR = 10_000

#: 이 아래의 대장 값은 **판정하지 않는다.** 4·5·15·30 은 인덱스로도 시간으로도
#: 쓰여 소스 리터럴과 구별되지 않는다. 건수는 출력한다 — 보지 않은 것을 말하지
#: 않으면 「전부 검사했다」로 읽힌다.
JUDGE_FLOOR = 1_000

TARGETS = ("core", "app", "infra")
EXCLUDE_PARTS = {"__pycache__", ".venv", "migrations"}

#: 대장 값이라도 이 값들은 어디에나 있다. 0·1 을 차단하면 모든 파일이 걸린다.
#: `0` 과 `0.0` 을 함께 적지 않는다 — 파이썬에서 같은 값이라 집합에 하나만
#: 남고, 둘 다 적으면 «두 가지를 면제했다»는 인상만 준다 (ruff `B033`).
UBIQUITOUS = {0, 1, -1}

MUTABLE_NODES = (ast.Dict, ast.List, ast.Set, ast.DictComp, ast.ListComp, ast.SetComp)
MUTABLE_CALLS = {"dict", "list", "set", "defaultdict", "OrderedDict", "Counter"}


@dataclass(frozen=True)
class LedgerValue:
    """대장의 수치 하나. `key` 는 `capex.pv.rooftop.low` 처럼 항목+갈래다."""

    key: str
    value: float
    unit: str

    @property
    def is_money(self) -> bool:
        return self.unit.strip().startswith("원")

    @property
    def blocking(self) -> bool:
        return self.is_money and abs(self.value) >= MONEY_FLOOR

    @property
    def judged(self) -> bool:
        """판정 대상인가. 아니면 «보지 않았다» 로 집계한다."""
        return abs(self.value) >= JUDGE_FLOOR


@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    detail: str
    blocking: bool
    #: 면제 사유 — `COINCIDENTAL_LITERALS` 가 이 (경로, 값)을 잡았을 때만 채운다.
    #: `None` 이면 면제되지 않은 보통의 경고/차단이다.
    exempt_reason: str | None = None


#: **대장 값과 우연히 같은 소스 리터럴** — (경로, 리터럴) → 사유.
#:
#: 이 검사의 차단 규칙(`LedgerValue.blocking`)은 일부러 무디다 — 소스 리터럴의
#: 맥락(금액인지 개수인지)을 보지 않는다. 그 무딤이 요점이다: 사람이 한 번은
#: 보게 만든다. **사람이 보고 「우연이다」로 판정한 자리만** 여기 적는다 — 값을
#: 바꾸거나(사용자 판정으로 금지된 경우가 있다) 소스 리터럴의 표기를 비틀어
#: (예: `10 * 10_000`) 리터럴 스캔을 피하는 것은 검사기를 속이는 것이며 이
#: 목록의 대체재가 아니다.
#:
#: ⚠ **사유가 비면 검사가 거부한다** (`_blank_exemption_keys`) — 사유 없는
#: 면제는 면제가 아니다.
#: ⚠ **경로는 슬래시(POSIX)로 적는다** — `Path.relative_to(root).as_posix()`
#: 와 같은 표기여야 매칭된다. 역슬래시로 적으면 조용히 아무것도 면제되지 않는다.
#: ⚠ **낡으면 검사가 말한다** (`_stale_exemptions`) — 스캔에 포함된 경로인데
#: 더 이상 그 값과 충돌하지 않으면 rc=1 로 「지우십시오」를 낸다. 조용히 지우지
#: 않는 이유는 낡은 면제가 다음 사람에게 「여기 위험이 있다」고 거짓말하기
#: 때문이다.
COINCIDENTAL_LITERALS: dict[tuple[str, float], str] = {
    ("core/assumption/timeseries.py", 100_000.0): (
        "CSV 업로드 「행수」 상한이며 금액이 아니다 (FR-905 · NFR-404-AC1). "
        "대장 opex.pv.fixed_om · opex.ess.fixed_om (100,000원/년, R51/WP-2)"
        "과 값만 우연히 같다 — 행수와 금액이므로 어느 쪽을 고쳐도 해소되지 "
        "않는다"
    ),
}


def _blank_exemption_keys(
    mapping: dict[tuple[str, float], str],
) -> list[tuple[str, float]]:
    """사유가 비어 있는 면제 항목. **사유 없는 면제는 면제가 아니다**
    (`tests/casegrid/test_ledger_levels.py` 의 같은 이름의 판정과 같은 형태).
    """
    return [key for key, reason in mapping.items() if not reason.strip()]


def _stale_exemptions(
    mapping: dict[tuple[str, float], str],
    used: set[tuple[str, float]],
    scanned_paths: set[str],
) -> list[tuple[str, float]]:
    """스캔에 **포함된 경로**인데 이번 실행에서 실제로는 걸리지 않은 면제.

    ⚠ **경로가 이번 스캔에 없으면 낡았다고 보지 않는다** — `negtest_
    hardcoded_params.py` 는 임시 저장소 트리 하나만 스캔하며 그 트리에는
    `core/assumption/timeseries.py` 자체가 없다. 「이 실행에 그 파일이
    없다」와 「그 파일은 있는데 값이 더 이상 안 맞는다」는 다르다 — 후자만
    낡은 것이다.
    """
    return [key for key in mapping if key[0] in scanned_paths and key not in used]


def ledger_values(path: Path) -> list[LedgerValue]:
    """대장에서 값과 민감도 3수준을 모은다.

    민감도까지 보는 이유: 케이스 그리드는 `low`·`high` 로도 돈다. 기준값만
    막으면 누군가 상한값을 소스에 적고 그것은 통과한다.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    found: list[LedgerValue] = []
    for item in doc.get("assumptions", []):
        unit = item.get("value_unit") or ""
        pairs = [("value", item.get("value"))]
        pairs += list((k, v) for k, v in (item.get("sensitivity") or {}).items())
        for label, raw in pairs:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            if raw in UBIQUITOUS:
                continue
            found.append(LedgerValue(f"{item['key']}.{label}", raw, unit))
    return found


def source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        base = root / target
        if not base.is_dir():
            continue
        files += [p for p in sorted(base.rglob("*.py"))
                  if not EXCLUDE_PARTS & set(p.parts)]
    return files


def scan_literals(tree: ast.AST) -> list[tuple[int, float]]:
    """소스의 수치 리터럴 전건. **주석·독스트링은 애초에 리터럴이 아니다** —
    `ast` 를 쓰는 것이 곧 그 보장이다.
    """
    out: list[tuple[int, float]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            out.append((node.lineno, node.value))
    return out


def check_hardcoded(
    files: list[Path], values: list[LedgerValue], root: Path,
) -> tuple[list[Finding], set[tuple[str, float]]]:
    """반환값 둘째 자리는 **이번 스캔에서 실제로 쓰인 면제 키 집합**이다 —
    `main()` 이 그것으로 `_stale_exemptions()` 를 물어 낡은 면제를 잡는다.
    """
    by_value: dict[float, list[LedgerValue]] = {}
    for v in values:
        by_value.setdefault(v.value, []).append(v)

    findings: list[Finding] = []
    used_exemptions: set[tuple[str, float]] = set()
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, literal in scan_literals(tree):
            matches = by_value.get(literal)
            if not matches:
                continue
            blocking = any(m.blocking for m in matches)
            keys = ", ".join(m.key for m in matches)
            # ⚠ 사람이 「우연이다」로 판정한 (경로, 값)만 차단에서 내린다 —
            # `COINCIDENTAL_LITERALS` 독스트링 참조.
            reason = COINCIDENTAL_LITERALS.get((rel, float(literal)))
            if reason:
                used_exemptions.add((rel, float(literal)))
                blocking = False
            findings.append(Finding(
                path=rel, lineno=lineno, blocking=blocking,
                detail=f"{literal!r} ← 대장 {keys}", exempt_reason=reason,
            ))
    return findings, used_exemptions


def toplevel_bindings(tree: ast.Module):
    """모듈 수준과 클래스 수준의 대입만 훑는다.

    함수 안의 지역 `dict` 는 전역 상태가 아니다. 그것까지 잡으면 계산 코드가
    거의 전부 걸리고, 조항이 겨냥한 것(모듈·클래스 변수)과 무관해진다.
    """
    scopes: list[tuple[str, list[ast.stmt]]] = [("모듈", tree.body)]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            scopes.append((f"클래스 {node.name}", node.body))
    for label, body in scopes:
        for node in body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if names and node.value is not None:
                yield label, names[0], node.value, node.lineno


def check_global_mutable(files: list[Path], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = path.relative_to(root).as_posix()
        for label, name, value, lineno in toplevel_bindings(tree):
            mutable = isinstance(value, MUTABLE_NODES) or (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in MUTABLE_CALLS
            )
            if mutable:
                findings.append(Finding(
                    path=rel, lineno=lineno, blocking=True,
                    detail=f"{label} 수준 가변 컨테이너 — {name}",
                ))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="NFR-202 파라미터 하드코딩 · NFR-205 전역 가변 상태 (작업 2.9)"
    )
    parser.add_argument("--root", default=".", help="저장소 루트")
    parser.add_argument("--ledger", default="docs/assumptions.yaml")
    args = parser.parse_args(argv)

    blank = _blank_exemption_keys(COINCIDENTAL_LITERALS)
    if blank:
        print("COINCIDENTAL_LITERALS 에 사유 없는 면제 항목이 있습니다:",
              file=sys.stderr)
        for path, literal in blank:
            print(f"  {path}  {literal!r}", file=sys.stderr)
        print("사유 없는 면제는 면제가 아닙니다 — 지우거나 사유를 채우십시오",
              file=sys.stderr)
        return 2

    root = Path(args.root).resolve()
    ledger = root / args.ledger
    if not ledger.is_file():
        print(f"잠정 가정 대장이 없습니다: {ledger}", file=sys.stderr)
        print("대장 없이 하드코딩을 판정할 수 없습니다 (§13.0.1 ④)", file=sys.stderr)
        return 2

    files = source_files(root)
    if not files:
        print(f"검사 대상 파일이 없습니다: {', '.join(TARGETS)}", file=sys.stderr)
        print("검사를 수행하지 못한 것을 통과로 읽지 않습니다 (§13.0.1 ④)",
              file=sys.stderr)
        return 2

    values = ledger_values(ledger)
    judged = [v for v in values if v.judged]
    skipped = [v for v in values if not v.judged]
    hardcoded, used_exemptions = check_hardcoded(files, judged, root)
    globals_ = check_global_mutable(files, root)
    scanned_paths = {p.relative_to(root).as_posix() for p in files}
    stale = _stale_exemptions(COINCIDENTAL_LITERALS, used_exemptions, scanned_paths)

    print(f"NFR-202 · NFR-205 — 대상 {len(files)}개 파일 / 대장 수치 {len(values)}건")
    print("─" * 78)

    blocking = [f for f in hardcoded if f.blocking]
    warning = [f for f in hardcoded if not f.blocking]

    print(f"· NFR-202 전제값 복제 — 차단 {len(blocking)}건 / 경고 {len(warning)}건")
    for f in blocking:
        print(f"  ✗ {f.path}:{f.lineno}  {f.detail}")
    for f in warning:
        if f.exempt_reason:
            print(f"  · {f.path}:{f.lineno}  {f.detail}  [면제: {f.exempt_reason}]")
        else:
            print(f"  · {f.path}:{f.lineno}  {f.detail}  [값 충돌 가능 — 사람이 판정]")

    if stale:
        print(f"  낡은 면제 {len(stale)}건 — 이번 스캔에서 더 이상 충돌하지 않습니다")
        for path, literal in stale:
            print(f"    ⚠ {path}  {literal!r}  ({COINCIDENTAL_LITERALS[(path, literal)]})")

    print(f"  판정하지 않은 대장 수치 {len(skipped)}건 — |값| < {JUDGE_FLOOR:,}")
    if skipped:
        print(f"    {', '.join(sorted({v.key.rsplit('.', 1)[0] for v in skipped}))}")
        print("    이 대역은 인덱스·시간과 값이 겹쳐 소스 리터럴과 구별되지 "
              "않습니다.")
        print("    **검사가 보지 않은 범위이며, 깨끗하다는 뜻이 아닙니다.**")

    print(f"· NFR-205 전역 가변 상태 — {len(globals_)}건")
    for f in globals_:
        print(f"  ✗ {f.path}:{f.lineno}  {f.detail}")

    print("─" * 78)

    if not blocking and not globals_ and not stale:
        if warning:
            print("통과 — 차단 대상 없음. 위 경고는 물리·시간 상수와 값이 겹친")
            print("       것일 수 있습니다. 대장 키를 보고 판정하십시오")
        else:
            print("통과")
        return 0

    if blocking:
        print("**대장의 값이 소스에 복제되어 있습니다.**")
        print("  회신이 오면 대장만 고치면 되던 것이, 이제 소스도 함께 고쳐야")
        print("  합니다. 그 순간 대장은 정본이 아니라 사본이 됩니다 (작업 16.1).")
        print("  값을 지우고 `AssumptionSet` 에서 읽으십시오.")
    if globals_:
        print("**모듈·클래스 수준 가변 컨테이너가 있습니다.**")
        print("  읽기 전용으로 쓰고 있어도 위반입니다 — 지금 아무도 고치지")
        print("  않는다는 것은 다음 사람도 고치지 않는다는 보장이 아니고,")
        print("  병렬 실행에서 한 번의 변형은 다른 케이스의 결과를 조용히")
        print("  바꿉니다 (FR-805 · §16 W-5).")
        print("  `MappingProxyType` · `tuple` · `frozenset` 로 바꾸십시오.")
    if stale:
        print("**COINCIDENTAL_LITERALS 에 낡은 면제가 있습니다.**")
        print("  더 이상 소스와 충돌하지 않는 값을 면제하고 있습니다 — 지우지")
        print("  않으면 다음 사람에게 「여기 위험이 있다」고 거짓말하는 셈입니다.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
