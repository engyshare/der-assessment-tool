"""NFR-105 게이트 ①② 공용 — 기준 ref 해석과 변경 목록.

**왜 두 게이트가 이것을 공유하는가.** 둘 다 «기준 브랜치와의 차이» 위에서만
판정한다. 기준 ref 를 못 찾았을 때의 처리를 각자 쓰면 반드시 갈리고, 갈린 쪽이
느슨한 쪽이면 그 게이트가 조용히 무력화된다 — 08-08 계약 개정에서 자원 여섯이
`capex_vat()` 를 각자 지어낸 것과 같은 구조다(§16.1 W-4 단일 소유).

**기준 ref 부재는 예외이지 빈 목록이 아니다.** 얕은 클론(`fetch-depth: 1`)에서는
대상 브랜치가 로컬에 없고, 그때 `git diff` 는 조용히 실패하거나 빈 결과를 낸다.
빈 결과는 「변경 없음」과 구별되지 않으므로 게이트가 아무것도 검사하지 않은 채
초록불이 된다 (§13.0.1 ④).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

#: git diff 의 상태 문자 중 «파일이 사라진» 것.
DELETED = "D"


class CheckError(Exception):
    """검사를 수행할 수 없다 — 호출부에서 종료 코드 2 에 대응한다."""


@dataclass(frozen=True)
class Change:
    """변경된 파일 하나. `path` 는 저장소 상대 POSIX 경로다."""

    path: str
    status: str = "M"

    @property
    def deleted(self) -> bool:
        return self.status.startswith(DELETED)


def git(args: list[str], root: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", check=False,
    )
    if result.returncode != 0:
        raise CheckError(
            f"git {' '.join(args)} 실패 (코드 {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def require_ref(base: str, root: Path) -> None:
    """기준 ref 가 실재하는지 먼저 단언한다."""
    try:
        git(["rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"], root)
    except CheckError as exc:
        raise CheckError(
            f"기준 ref 를 찾을 수 없습니다: {base!r}. CI 라면 얕은 클론일 수 "
            f"있습니다 — actions/checkout 에 fetch-depth: 0 을 주거나 대상 "
            f"브랜치를 먼저 fetch 하십시오. (원인: {exc})"
        ) from exc


def changed_files(base: str, root: Path) -> list[Change]:
    """`base` 와의 병합 기점 이후 변경 목록.

    `...`(세 점)을 쓰는 이유: 두 점은 «기준 브랜치가 그 뒤에 받은 커밋»까지
    차이로 잡아, 남이 올린 변경이 내 PR 의 판정 대상이 된다.
    """
    require_ref(base, root)

    out = git(["diff", "--name-status", "--no-renames", f"{base}...HEAD"], root)
    changes: list[Change] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        if path:
            changes.append(
                Change(path=path.strip().replace("\\", "/"), status=status.strip())
            )
    return changes


def head_reader(root: Path):
    """«변경 후» 소스를 읽는 함수를 돌려준다 — `HEAD` 의 내용이 기준이다.

    `base...HEAD` 로 diff 를 떴으므로 판정 대상은 HEAD 다. CI 는 HEAD 를
    체크아웃하므로 보통 작업 트리와 같지만, 로컬에서 미커밋 변경이 섞이면
    갈린다. 조용히 작업 트리를 읽으면 «무엇을 판정했는가» 가 실행 시점에 따라
    달라진다.
    """

    def read(path: str) -> str:
        try:
            return git(["show", f"HEAD:{path}"], root)
        except CheckError:
            candidate = root / path
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
            return ""

    return read


def base_reader(base: str, root: Path):
    """«변경 전» 소스를 읽는 함수를 돌려준다 — `head_reader` 의 짝.

    **작업 트리로 물러나지 않는다.** `head_reader` 는 미커밋 변경을 만나면 작업
    트리를 읽는 예외 경로가 있으나, 이전 이미지는 작업 트리에 없다 — 거기 있는
    것은 «변경 후» 내용이다. 물러나면 「이전과 이후가 같다」가 항상 참이 되어
    이 검사가 조용히 사라진다.

    **기준은 `base` 의 끝이 아니라 병합 기점이다.** `changed_files` 가
    `base...HEAD`(세 점)로 목록을 뽑으므로 그 목록의 «이전» 도 같은 기점이어야
    한다. 끝을 읽으면 남이 기준 브랜치에 올린 변경이 내 diff 의 이전 이미지로
    섞인다.

    **«없었다» 와 «비어 있었다» 를 구분한다.** 그 시점에 없던 파일은 `None`
    이고, 실제로 빈 파일이었던 것은 `""` 다. 신규 파일을 빈 파일로 뭉개면
    「이전에도 코드가 없었다」로 읽혀 새로 들어온 구현이 면제된다.
    """
    merge_base = git(["merge-base", base, "HEAD"], root).strip()

    def read(path: str) -> str | None:
        try:
            return git(["show", f"{merge_base}:{path}"], root)
        except CheckError:
            return None

    return read
