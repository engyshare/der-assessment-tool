"""SC-3·SC-5·SC-8 비공개 데이터 커밋 차단 — 작업 2.3 / `FR-1101-AC5`.

**대장은 `check_assumptions.py` 가 본다. 여기서는 «파일»을 본다.** 둘을 가른
이유는 주체가 다르기 때문이다 — 대장의 민감도 등급은 항목의 속성이고, 여기서
막는 것은 **저장소에 들어오는 파일과 그 내용**이다. 한 도구에 섞으면 대장이
깨끗한 것을 저장소가 깨끗한 것으로 읽게 된다.

── 무엇을 막는가 ────────────────────────────────────────────────────────

    ① 비공개 시드 파일        `FR-1101-AC2` 가 별도 관리하라고 한 것들이
                              추적 대상에 들어오는 경우 (`data/private/`,
                              `*.xlsx`, `*seed*.yaml` 등)

    ② 로컬 절대 경로          `D:\\...`, `C:\\Users\\...`, `/home/<이름>/...`
                              **이 저장소가 실제로 43건 정제한 유형이다**
                              (08-03). 볼트 경로를 lock 에서 뽑아낸 것도
                              같은 이유였다

    ③ 개인 식별 정보 형태     주민등록번호 형태, 전화번호, 이메일
                              SC-3 은 «실증 참여 가구의 개별 식별정보
                              미저장» 을 요구한다

**`.gitignore` 는 방어선이 아니라 안전망이다** — 파일 안에 그렇게 적혀 있다.
무시 규칙은 이미 추적 중인 파일에 적용되지 않고, `git add -f` 한 줄로 뚫린다.
그래서 **추적 대상 자체를 검사한다.**

── 무엇을 막지 못하는가 ─────────────────────────────────────────────────

**비밀 문자열(API 키·토큰)은 gitleaks 가 본다** (SC-5). 여기서 다시 구현하면
규칙이 두 곳에 생기고, 두 곳은 반드시 갈린다. 이 도구는 gitleaks 가 보지
않는 것 — **이 프로젝트 고유의 비공개 유형** — 만 본다.

**서술과 선언을 가르지 않는다.** 로컬 경로는 주석에 있어도 로컬 경로다.
누군가의 홈 디렉터리 이름이 공개 저장소에 남는 것은 그것이 코드든 주석이든
같은 일이며, 이 점에서 NFR-202·NFR-207 검사와 판단이 다르다.

    종료 코드 0  차단 대상 없음
    종료 코드 1  비공개 유입 의심
    종료 코드 2  검사가 성립하지 않음 (git 밖·추적 파일 0개)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: `FR-1101-AC2` 가 비공개로 분리하라고 한 것들. 경로는 POSIX 로 비교한다.
PRIVATE_PATHS = (
    re.compile(r"^data/(raw|private)/"),
    re.compile(r"(^|/)[^/]*seed[^/]*\.(ya?ml|json|csv)$", re.I),
    re.compile(r"\.(xlsx|xls)$", re.I),
)

#: 위 규칙의 예외. **좁게 적는다** — 넓히면 규칙이 사라진다.
PRIVATE_ALLOW = (
    re.compile(r"^fixtures/"),          # 골든 시나리오 «구조» 는 공개다 (AC1)
)

#: 검사 대상에서 뺄 파일. 이 도구 자신과 그 음성 테스트는 **패턴을 리터럴로
#: 들고 있으므로** 자기 자신에 걸린다 — 이 저장소가 일곱 번 만난 유형이다.
SELF_EXEMPT = (
    "scripts/check_disclosure.py",
    "scripts/negtest_disclosure.py",
    ".pre-commit-config.yaml",
)

#: 내용 검사 대상 확장자. 바이너리를 열지 않는다.
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".toml", ".cfg", ".ini",
                 ".txt", ".json", ".ps1", ".sh", ".lock"}

#: 붙임표로 쓰이는 두 문자 (하이픈, EN DASH). **리터럴로 적지 않는다** —
#: ruff `RUF001` 이 EN DASH 를 «모호한 문자» 로 보는데, 규칙을 끄는 대신
#: 코드포인트로 쓴다. 이 저장소가 `RUF002`·`RUF003` 을 면제한 근거는
#: «문서·주석이 한국어» 였고, 여기는 그 근거가 성립하지 않는 **코드**다.
_DASHES = "-" + chr(0x2013)

CONTENT_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "로컬 절대 경로 (Windows)",
        re.compile(r"[A-Za-z]:\\\\?(?:Users|Dev|Obsidian[A-Za-z_]*)[\\/]"),
        "SC-3 — 08-03에 이 유형 43건을 정제했다. 사용자 이름·로컬 구조가 "
        "공개 저장소에 남는다. 환경변수나 인자로 받으십시오",
    ),
    (
        "로컬 절대 경로 (POSIX 홈)",
        re.compile(r"/(?:home|Users)/(?!<)[A-Za-z][\w.-]*/"),
        "SC-3 — 사용자 이름이 드러난다",
    ),
    (
        "주민등록번호 형태",
        # 붙임표를 하이픈과 EN DASH 둘 다 받는다. 문서 편집기가 자동 치환하는
        # 일이 잦아 한 종류만 보면 그 순간 규칙이 조용히 빗나간다.
        #
        # EN DASH 를 **리터럴로 적지 않고 이스케이프로 쓴다.** ruff `RUF001`
        # 이 그것을 «모호한 문자» 로 보는데, 규칙을 끄는 대신 표기를 바꾼다 —
        # 이 저장소에서 `RUF002`·`RUF003` 을 면제한 것은 «문서·주석이 한국어»
        # 라는 이유였고, 여기는 그 이유가 성립하지 않는 **코드**다.
        re.compile(rf"\b\d{{6}}[{_DASHES}]\d{{7}}\b"),
        "SC-3 — 실증 참여 가구의 개별 식별정보는 저장하지 않는다",
    ),
    (
        "전화번호 형태",
        re.compile(r"\b01[0-9][-.\s]?\d{3,4}[-.\s]?\d{4}\b"),
        "SC-3 — 개별 식별정보",
    ),
    (
        "이메일 주소",
        re.compile(r"\b[\w.+-]+@(?!example\.(?:com|org)\b)[\w-]+\.[\w.]+\b"),
        "SC-3 — 수집은 최소화하고 저장소에는 두지 않는다. 예시가 필요하면 "
        "`example.com` 을 쓰십시오",
    ),
)


@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    rule: str
    hint: str
    excerpt: str


def tracked_files(root: Path) -> list[str]:
    """git 이 **추적 중인** 파일. 작업 트리 전체가 아니다.

    `.gitignore` 로 무시되는 파일은 애초에 커밋되지 않으므로 검사 대상이
    아니고, 반대로 **이미 추적 중인 파일은 무시 규칙이 적용되지 않는다** —
    막아야 하는 것은 후자다.
    """
    #: `-z` 로 받는다. **기본 출력은 비ASCII 경로를 따옴표로 감싸고 바이트를
    #: 이스케이프한다** — `"rslt/task-\\353\\266\\204….md"` 처럼 된다. 그러면
    #: 경로 끝이 `"` 가 되어 `\\.xlsx$` 같은 규칙이 전부 빗나가고, **한글 이름을
    #: 가진 파일은 통째로 검사 밖**이 된다. 이 저장소의 spec·작업 목록이
    #: 정확히 그런 이름이며, 음성 테스트가 이 구멍을 잡았다.
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files 실패: {result.stderr.decode('utf-8', 'replace').strip()}"
        )
    raw = result.stdout.decode("utf-8", "replace")
    return [p.replace("\\", "/") for p in raw.split("\0") if p.strip()]


#: **공개 등급을 스스로 선언한 파일**. 파일명 예외가 아니라 **내용 선언**이다.
#:
#: `FR-1101-AC3` 은 합성 예시 시드를 **공개 저장소에 두라고** 요구한다. 그런데
#: 경로 규칙은 이름만 보므로 그 정당한 파일을 잡는다 — 08-09 에 실제로
#: `tests/ci/synthetic_seeds.yaml` 이 걸렸다.
#:
#: **파일명 예외로 풀지 않았다.** 예외를 넓히면 진짜 비공개 시드가 이름만
#: 바꿔 통과한다 — 이 저장소가 반복해서 만난 «제외를 넓혀 규칙을 없애는»
#: 형태다. 대신 `docs/assumptions.yaml` 이 SC-8 에 쓰는 것과 같은 장치를
#: 쓴다: **선언이 없으면 비공개로 간주**하고, 공개하려면 파일이 그렇게
#: 말해야 한다. 선언은 한 줄이고 **잊은 것과 공개하기로 한 것을 구분한다.**
PUBLIC_DECLARATION = re.compile(
    r"^\s*#?\s*disclosure:\s*[\"']?공개 가능", re.M)


def _declares_public(path: str, root: Path) -> bool:
    f = root / path
    try:
        head = f.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return False
    return bool(PUBLIC_DECLARATION.search(head))


def check_paths(paths: list[str], root: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    root = root or Path(".")
    for path in paths:
        if any(a.search(path) for a in PRIVATE_ALLOW):
            continue
        for rule in PRIVATE_PATHS:
            if rule.search(path):
                if _declares_public(path, root):
                    break
                findings.append(Finding(
                    path=path, lineno=0, rule="비공개 시드 경로",
                    hint="FR-1101-AC2 — 별도 비공개 저장소 또는 배포 시 주입되는 "
                         "시드로 관리합니다. 공개 저장소에는 «구조»만 둡니다",
                    excerpt=path,
                ))
                break
    return findings


def check_contents(paths: list[str], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        if path in SELF_EXEMPT or Path(path).suffix not in TEXT_SUFFIXES:
            continue
        full = root / path
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pattern, hint in CONTENT_RULES:
                m = pattern.search(line)
                if m:
                    findings.append(Finding(
                        path=path, lineno=lineno, rule=rule, hint=hint,
                        excerpt=_redact(line.strip(), m.group(0)),
                    ))
    return findings


def _mask(matched: str) -> str:
    return matched[:3] + "…" + "*" * max(0, min(6, len(matched) - 3))


def _redact(line: str, matched: str) -> str:
    """찾은 값을 가린다. **보고서가 새 유출 경로가 되면 안 된다** — CI 로그와
    작업 요약은 저장소보다 넓게 읽힌다.

    **자기 매치만 가리면 안 된다.** 한 줄에 식별정보가 여럿이면(주민번호 ·
    전화번호 · 이메일이 한 줄에 있는 연락처 표가 흔하다) 그 줄에서 발견이
    세 건 나오고, 각 발견이 **나머지 둘을 그대로 싣는다.** 세 줄을 나란히
    읽으면 원문이 복원된다 — 검사가 유출을 막는 대신 **옮기는** 셈이다.
    실제로 그 상태였고, `SC-3` 검증 케이스가 잡았다.

    그래서 규칙 전건을 다시 적용해 **그 줄의 모든 일치**를 가린다.
    """
    shown = line
    for _rule, pattern, _hint in CONTENT_RULES:
        shown = pattern.sub(lambda m: _mask(m.group(0)), shown)
    # 트리거가 된 값은 규칙 순회로 이미 가려졌지만, 호출부가 다른 경로로
    # 넘긴 값도 확실히 지운다 — 가리기에서 «대체로 가려진» 은 실패다.
    if matched in shown:
        shown = shown.replace(matched, _mask(matched))
    return shown[:110]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SC-3·SC-8 비공개 데이터 커밋 차단 (작업 2.3)"
    )
    parser.add_argument("--root", default=".", help="저장소 루트")
    parser.add_argument("files", nargs="*",
                        help="검사할 파일 (pre-commit 이 넘긴다). 생략하면 추적 전체")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        paths = ([f.replace("\\", "/") for f in args.files] if args.files
                 else tracked_files(root))
    except RuntimeError as exc:
        print(f"검사를 수행할 수 없습니다: {exc}", file=sys.stderr)
        print("검사를 수행하지 못한 것을 통과로 읽지 않습니다 (§13.0.1 ④)",
              file=sys.stderr)
        return 2

    if not paths:
        print("검사 대상 파일이 0건입니다 — git 저장소가 맞는지 확인하십시오",
              file=sys.stderr)
        return 2

    findings = check_paths(paths, root) + check_contents(paths, root)

    print(f"비공개 유입 검사 — 대상 {len(paths)}개 파일")
    print("─" * 78)
    for f in findings:
        where = f"{f.path}:{f.lineno}" if f.lineno else f.path
        print(f"  ✗ {where}  [{f.rule}]")
        print(f"      {f.excerpt}")
        print(f"      {f.hint}")
    print("─" * 78)

    if findings:
        print(f"비공개 유입 의심 {len(findings)}건 — 커밋을 멈춥니다")
        print()
        print("  **이미 커밋된 뒤에는 파일을 지워도 이력에 남습니다.** 지우려면")
        print("  저장소 이력을 다시 써야 하고, 공개된 뒤라면 그것으로도 늦습니다.")
        print("  08-03에 git 초기화를 정제 «후에» 한 것이 같은 이유였습니다.")
        return 1

    print("통과 — 추적 대상에 비공개 유입 없음")
    print()
    print("  이 검사는 **비밀 문자열(API 키·토큰)을 보지 않습니다** — gitleaks 의")
    print("  몫입니다(SC-5). 규칙을 두 곳에 두면 반드시 갈립니다.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
