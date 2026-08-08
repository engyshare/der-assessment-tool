"""NFR-105 게이트 ① 입력 검증 — 작업 2.5. diff-cover 직전에 돌린다.

**왜 별도 검사가 필요한가 — diff-cover 는 판정할 수 없을 때 통과한다.**

실측했다(diff-cover 10.4.2). `coverage.xml` 의 `filename` 이 저장소 상대 경로와
어긋나면 diff-cover 는 이렇게 말하고 **종료 코드 0** 을 낸다.

    No lines with coverage information in this diff.

문서만 고친 PR 에서는 이것이 옳다 — 판정할 라인이 없으니 통과다. 그러나 `core/`
파일을 고친 PR 에서 같은 문장이 나오면 뜻이 정반대다: **커버리지 산출물이 변경된
파일을 담고 있지 않다.** 두 경우가 같은 출력·같은 종료 코드를 내므로 로그를 봐도
구별되지 않는다.

어긋나는 원인은 흔하고 조용하다 — `--cov` 대상 경로가 다름, 작업 디렉터리가 다른
상태에서 측정, 윈도우 역슬래시, 산출물이 이전 실행의 잔재. 어느 것이든 결과는
같다: **게이트 ①이 켜져 있는 채로 아무것도 판정하지 않는다.**

**그래서 무엇을 단언하는가.** 변경된 `core/**/*.py` 전건이 `coverage.xml` 에
등장한다. `pyproject.toml` 의 `[tool.coverage.run] source = ["core"]` 때문에
**테스트가 import하지 않은 파일도 0% 로 등장한다** — 즉 커버리지가 낮아서 빠지는
경우는 없다. 빠졌다면 측정이 그 파일을 보지 못한 것이며 도구 결함이다.

    종료 코드 0  판정 가능하다 (diff-cover 를 이어서 돌린다)
    종료 코드 2  판정할 수 없다 — 기준 ref 부재, 산출물 부재, 경로 불일치

**종료 코드 1 이 없는 것은 의도다.** 커버리지 «부족» 을 판정하는 것은 diff-cover
이고 이 검사가 아니다. 같은 판정을 두 곳에서 하면 기준이 어긋난다.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from _gitdiff import CheckError, changed_files

IMPL_ROOT = "core"


def measured_files(coverage_xml: Path) -> set[str]:
    """`coverage.xml` 이 측정한 파일들의 저장소 상대 POSIX 경로.

    Cobertura 는 `<source>` 루트와 `<class filename=...>` 상대 경로로 나뉘어
    있고 도구마다 어느 쪽에 무엇을 담는지 다르다. 그래서 **두 조합을 모두**
    후보로 둔다 — 한쪽만 보면 경로가 맞는데도 불일치로 보고하게 되고, 그
    오탐은 정당한 PR 을 막아 게이트를 꺼지게 만든다.
    """
    root = ET.parse(coverage_xml).getroot()
    sources = [
        (s.text or "").strip().replace("\\", "/").rstrip("/")
        for s in root.findall("./sources/source")
    ]

    found: set[str] = set()
    for cls in root.findall(".//class"):
        raw = (cls.get("filename") or "").strip().replace("\\", "/")
        if not raw:
            continue
        found.add(raw)
        for src in sources:
            tail = src.rsplit("/", 1)[-1] if src else ""
            if tail:
                found.add(f"{tail}/{raw}")
    return found


def missing(changed: list[str], measured: set[str]) -> list[str]:
    """측정 대상에서 빠진 변경 파일.

    꼬리 일치도 인정한다 — 절대 경로가 담긴 산출물에서도 판정이 성립해야 한다.
    """
    absent: list[str] = []
    for path in changed:
        if path in measured or any(m.endswith(path) for m in measured):
            continue
        absent.append(path)
    return absent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="NFR-105 게이트 ① 입력 검증 (작업 2.5)"
    )
    parser.add_argument("--base", required=True, help="비교 기준 ref (예: origin/main)")
    parser.add_argument("--coverage", default="coverage.xml", help="Cobertura XML 경로")
    parser.add_argument("--root", default=".", help="저장소 루트")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    coverage_xml = Path(args.coverage)
    if not coverage_xml.is_absolute():
        coverage_xml = root / coverage_xml

    print(f"게이트 ① 입력 검증 — 기준 {args.base} / 산출물 {args.coverage}")
    print("─" * 78)

    if not coverage_xml.is_file() or coverage_xml.stat().st_size == 0:
        print(f"커버리지 산출물이 없거나 비어 있습니다: {coverage_xml}", file=sys.stderr)
        print("판정할 대상이 없는 것을 통과로 읽지 않습니다 (§13.0.1 ④)", file=sys.stderr)
        return 2

    try:
        changes = changed_files(args.base, root)
    except CheckError as exc:
        print(f"검사를 수행할 수 없습니다: {exc}", file=sys.stderr)
        return 2

    try:
        measured = measured_files(coverage_xml)
    except ET.ParseError as exc:
        print(f"커버리지 산출물을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return 2

    if not measured:
        print("커버리지가 측정된 파일이 0건입니다 — 산출물이 비어 있습니다",
              file=sys.stderr)
        return 2

    impl = sorted(
        c.path for c in changes
        if not c.deleted and c.path.startswith(f"{IMPL_ROOT}/") and c.path.endswith(".py")
    )
    print(f"· 측정된 파일 {len(measured)}건 / 변경된 {IMPL_ROOT}/ 파일 {len(impl)}건")

    absent = missing(impl, measured)
    print("─" * 78)

    if absent:
        print(f"변경된 파일 {len(absent)}건이 커버리지 산출물에 없습니다 — "
              "diff-cover 가 이것을 판정하지 못합니다")
        for path in absent:
            print(f"  · {path}")
        print()
        print("  이 상태에서 diff-cover 는 «No lines with coverage information in")
        print("  this diff» 를 출력하고 **종료 코드 0** 을 냅니다 — 게이트 ①이")
        print("  켜져 있는 채로 아무것도 판정하지 않습니다.")
        print()
        print("  커버리지 측정 대상과 실행 위치를 확인하십시오 —")
        print("  `pytest --cov=core --cov-report=xml` 을 저장소 루트에서 돌려야")
        print("  `coverage.xml` 의 경로가 저장소 상대 경로가 됩니다.")
        return 2

    if not impl:
        print(f"변경된 `{IMPL_ROOT}/` 파일이 없습니다 — diff-cover 가 «판정할 "
              "라인 없음» 으로 통과하는 것이 이 PR 에서는 정상입니다")
    else:
        print("통과 — 변경된 구현 전건이 커버리지 산출물에 있습니다")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
