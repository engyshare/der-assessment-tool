"""4.3 DoD 기계 강제 — 폐기 어휘 «미확인» 이 core/assumption/ 코드에
남아 있으면 실패.

§13.0.1 ④ 의 함정 — «검사가 통과했다» 와 «검사가 무언가를 검사했다» 는 다르다.
이 검사를 쓰는 순간 **검사 자신이 그 어휘를 리터럴로 들게 되어 스스로 걸린다**
— 이 저장소가 아홉 번 만난 유형이다. 해법은 §8 에 정해져 있다:

  * **면제 목록을 넓히지 않는다** — 특정 파일을 통과시키는 SELF_EXEMPT 같은
    경로 면제는, 다음 사람이 같은 패턴으로 또 면제를 추가하게 만든다.
  * **대상을 바꾼다** — `ast` 로 코드의 **문자열 리터럴** 만 뽑고, 주석
    (ast 가 애초에 잡지 않음) 과 **독스트링** (`ast.get_docstring` 으로 식별해
    제외) 을 뺀다. 코드의 «식별자» (ast.Name · ast.Attribute) 도 잡지 않는다.
  * **검사 자신의 대상 어휘는 조각으로 조립한다** — `chr(0xBBF8) + chr(0xD655)
    + chr(0xC778)` 로 조립해 이 파일 소스에 «미확인» 이라는 3글자가 연속으로
    남지 않게 한다. `scripts/check_disclosure.py` 의 `_DASHES = "-" + chr(0x2013)`
    이 같은 패턴이다 (ruff 회피 + 자기 매치 회피).

범위가 ``core/assumption/`` 인 이유 — 4.3 은 전제 계층의 신뢰도 enum 에 관한
것이다. ``core/der/ev_v2g.py`` 의 «제도 미확인» 런타임 경고 문자열은 confidence
값이 아니라 일반 서술이며 잡으면 오탐이다. ``tests/`` 의 양성 테스트 입력
(``ConfidenceLevel("...")``) 도 코드 잔류가 아니다.

음성·양성을 함께 본다 (§13.0.1 ④):
  * 음성 — 폐기 어휘를 문자열 리터럴로 심으면 잡히는가
  * 양성 — 주석·독스트링 서술과 합법 어휘(«확정»·«추정»·«가정») 는 안 잡히는가
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# 검사 자신이 «미확인» 을 리터럴로 들면 자기를 잡는다. chr 결합으로 조립해
# 이 소스에 «미»+«확»+«인» 이 연속으로 붙지 않게 한다. **면제로 풀지 않는다**
# — 범위·대상을 바꿔 푼다 (§8).
_DEPRECATED = chr(0xBBF8) + chr(0xD655) + chr(0xC778)  # 미·확·인


def _string_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """ast 에서 문자열 리터럴(``ast.Constant`` 의 ``str`` 값) 만 뽑는다.

    * **주석** — ast 가 토큰 단계에서 버리므로 애초에 안 잡힘.
    * **독스트링** — 모듈·함수·클래스 body 의 첫 ``ast.Expr(ast.Constant)``.
      ``ast.get_docstring`` 으로 식별해 제외한다. «서술» 과 «선언» 을 가른다.
    * **코드 식별자**(변수명·속성 접근) — ``ast.Name`` · ``ast.Attribute``
      로, ``ast.Constant`` 가 아니므로 여기서 안 잡힌다.
    """
    docstring_node_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            ds = ast.get_docstring(node, clean=False)
            if ds is not None and node.body:
                first = node.body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                ):
                    docstring_node_ids.add(id(first.value))

    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_node_ids
        ):
            results.append((node.lineno, node.value))
    return results


def _check_dir(root: Path) -> list[tuple[Path, int, str]]:
    """root 아래 .py 파일에서 폐기 어휘가 **문자열 리터럴** 로 쓰인 곳을 찾는다."""
    findings: list[tuple[Path, int, str]] = []
    for py in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(
                py.read_text(encoding="utf-8"), filename=str(py)
            )
        except SyntaxError:
            continue
        for lineno, val in _string_literals(tree):
            if _DEPRECATED in val:
                findings.append((py, lineno, val))
    return findings


@pytest.mark.req("FR-601-AC7")
def test_no_deprecated_confidence_vocabulary_in_core_assumption() -> None:
    """4.3 DoD — 폐기 어휘가 core/assumption/ 코드에 남아 있으면 실패.

    오라클: 순위 4 (교차 구현 대조) — ConfidenceLevel enum 의 거부 동작과
    정적 검사의 거부가 **같은 어휘 집합** 을 지킨다. enum 이 런타임에 «미확인»
    을 거부하듯, 코드는 그 어휘를 문자열 리터럴로도 두지 않는다.
    """
    root = (
        Path(__file__).resolve().parent.parent.parent / "core" / "assumption"
    )
    findings = _check_dir(root)
    assert not findings, (
        f"폐기 어휘 가 core/assumption/ 코드에 {len(findings)}건 남아 있습니다 "
        f"(4.3 DoD): "
        + "; ".join(f"{p.name}:{n}" for p, n, _ in findings)
    )


def test_negative_synthesized_violation_is_caught(tmp_path: Path) -> None:
    """음성 능력 — 폐기 어휘를 문자열 리터럴로 심으면 실제로 잡히는가.

    오라클: 순위 4 (검사 도구 자체의 정합 — §13.0.1 ④).

    «0건 통과»가 «위반이 없다» 인지 «규칙이 아무것도 매치하지 않는다» 인지
    결과만으로 구별되게 한다. 위반을 심었을 때 반드시 잡혀야 한다.
    """
    poisoned = tmp_path / "poisoned.py"
    poisoned.write_text(
        f'x = "{_DEPRECATED}"\n',  # 폐기 어휘를 문자열 리터럴로 심음
        encoding="utf-8",
    )
    findings = _check_dir(tmp_path)
    assert findings, (
        "폐기 어휘를 문자열 리터럴로 심었는데 잡지 못했다 — 검사가 "
        "«무언가를 검사했다» 는 것을 보여야 한다 (§13.0.1 ④)"
    )
    assert findings[0][0].name == "poisoned.py"


def test_positive_docstring_and_comment_not_flagged(tmp_path: Path) -> None:
    """양성 능력 — 정당한 서술(주석·독스트링·합법 어휘) 을 오판하지 않는가.

    오라클: 순위 4 (검사 도구 자체의 정합 — §13.0.1 ④).

    주석과 독스트링에서 폐기 어휘를 **서술** 하는 것은 코드 잔류가 아니다.
    합법 어휘(«확정»·«추정»·«가정») 도 잡히면 안 된다. 제외를 넓게 잡아
    진짜 위반이 초록불이 되는 반대 방향 함정도 여기서 잡는다.
    """
    legitimate = tmp_path / "legitimate.py"
    legitimate.write_text(
        # 주석으로 서술 — 코드 잔류가 아니다
        f"# 이 enum 은 {_DEPRECATED} 을 받지 않는다 (4.3).\n"
        f'"""독스트링: confidence 값으로 «{_DEPRECATED}» 은 폐기되었다."""\n'
        # 합법 어휘 — 전부 허용
        'A = "확정"\n'
        'B = "추정"\n'
        'C = "가정"\n',
        encoding="utf-8",
    )
    findings = _check_dir(tmp_path)
    assert not findings, (
        "정당한 서술(주석·독스트링·합법 어휘) 을 위반으로 오판했다 — "
        "제외가 넓으면 진짜 위반도 초록불이 된다: " + repr(findings)
    )
