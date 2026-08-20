"""spec 의 줄 끝 `[Phase N]` 표기가 조용히 사라지는 회귀를 잡는다.

## 왜 이 파일이 필요한가

`.orch/R37/phase_mismatch_sweep.md` 가 spec 전체에서 `[Phase 2]`·`[Phase 3]`
줄 끝 표기가 붙은 자리 12곳을 **1회성으로** 전수 대조했다 — 그런데 그것은
회귀 검사가 아니었다. `tests/` 전체에서 spec 의 `[Phase` 문면을 읽는 파일은
둘뿐이었다:

  - `tests/acceptance2/test_17_9_dod9.py` — `docs/traceability.md` 의 Phase
    **칼럼**을 읽을 뿐, spec 원문의 줄 끝 표기 자체는 보지 않는다
  - `tests/contract/test_vpp_rejection_matches_spec_precursor.py` — `AC1.VPP`
    의 선행 조항 **ID** 만 보고 Phase 는 보지 않는다

그래서 누군가 640행의 `[Phase 2]` 를 지워도 빨간불이 될 자리가 없었다.

## 어떻게 채우는가 — 12곳을 리터럴로 옮기지 않는다

목록을 베끼면 spec 이 개정될 때마다 낡는다. 대신 spec 이 **스스로 두 층**에
걸쳐 적어 둔 규칙을 서로 대조한다:

  ① 부록 A.1 배정표(§4.0 R-2) — 요구사항(FR) 단위 baseline Phase, 그리고
     baseline 을 벗어나는 수용기준을 괄호로 예외 표기한다
     (`FR-202(``AC4`` ...)`, `FR-205(v0.16 — ``AC1.VPP`` 제외)`)
  ② 본문 수용기준 목록 — 그 예외 대상 AC 줄 끝의 실측 `[Phase N]` 표기

①이 예외라 적었는데 ②에 그 표기가 없거나 값이 다르면 spec 의 두 층이 서로
어긋난 것이고, 그것이 R37 이 찾은 공백이 실제로 벌어지는 순간이다.

추가로 spec 안에 유일하게 존재하는 「... 이 선행이다」 인용(`AC1.VPP` →
`FR-401-AC2.VPPMarket`)에 대해 ③ 인용된 조항이 실재하는지(매달린 참조
방지), ④ 인용하는 쪽의 Phase 가 그 선행 조항의 Phase 보다 앞서지 않는지를
본다 — v0.16 머리말이 *「구조의 Phase 가 편익의 Phase 를 넘을 수 없다」* 라고
적은 규칙 그 자체이며, 정본은 spec 산문에 있지 이 검사가 지어낸 것이 아니다.

## 세우지 않은 것 — ⓑ (배타 규칙의 Phase, `FR-402-AC2.C` 사례)

`AC2.C` 본문은 그것이 다루는 유일한 편익 `CarbonCredit` 을 **자연어**로만
가리킨다(`동일 tCO2에 배출권 수익...` — `FR-401-AC2.CarbonCredit` 같은 백틱
인용이 없다). spec 전체에서 「... 이 선행이다」 인용은 `AC1.VPP` 것 **하나뿐**
이라는 것을 grep 으로 확인했다(공통 4절 ①: 검사 대상이 스스로 정하지 않는
값이 최소 하나 있어야 하는데, `AC2.C` → `CarbonCredit` 링크는 spec 문면에서
기계로 읽을 방법이 없다). 그래서 ⓑ는 세우지 않는다 — 짓지 못하는 것을
지어내지 않는다.

## ⚠ 이 파일의 검사에는 `req` 마커를 달지 않는다 (R38 오케스트레이터 판정)

이 검사들이 재는 것은 **spec 자체의 내적 일관성**(부록 A.1 의 지목 ↔ 본문 줄 끝
표기 · 선행 인용의 실재와 Phase 순서)이고, **그것을 요구하는 조항이 없다.**

초판은 예시로 쓰인 조항 ID 를 마커로 달았고, 그러자 추적표에서
`FR-202-AC4`(모델 간 구성 차이를 **diff 뷰**로 제시)와
`FR-401-AC2.VPPMarket`(**시장정산 − 운영수수료**)이 **미매핑 → 자동**으로
바뀌었다. **이 검사는 diff 뷰도 정산식도 재지 않는다** — 그 조항들은 여기에
자료로 등장할 뿐이다. 마커를 두면 매핑표가 그 둘을 「검증됨」으로 세고, 그것이
R37 이 `FR-402-AC2.C` 에서 찾은 결함과 **같은 형태**다(자동 292 → 290 으로 되돌렸다).

같은 판정을 R38 의 다른 구획이 먼저 내렸다 — `tests/report/test_unreflected.py` 의
조항 인용 대조 검사도 *「거짓 인용을 고치는 검사에 거짓 인용을 달지 않는다」* 로
무마커다. spec 도 같은 방향을 적는다 — **「게이트 자기참조 금지」**
(`NFR-105`~`107` 은 수동 대장에 등재하지 않는다).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "rslt" / "spec-분산특구-경제성평가.md"

#: 최상위 요구사항 헤딩만 — `- **FR-205** 시스템은 ...`. 들여쓴 수용기준
#: 줄과 구분하려고 줄 시작(들여쓰기 없음) 앵커를 쓴다.
_FR_HEADING = re.compile(r"^- \*\*((?:N?FR)-\d+)\*\*")

#: 수용기준 목록 항목 — `    - **AC1.VPP** ...`.
_AC_LINE = re.compile(r"^\s*-\s*\*\*(AC[\w.]+)\*\*")

#: 실제 Phase 표기는 **백틱으로 감싸이지 않은 채 줄 끝**에 온다. 개정 이력
#: 산문이 그 표기를 인용할 때는 항상 백틱으로 감싸고(예: 4행 「...v0.1부터
#: `[Phase 3]` 인데」) 뒤에 조사·설명이 이어져 줄 끝에 오지 않는다 — 실측
#: (4·347·504·541·543·676행 전부 줄 끝이 아님, 386~672행 실제 표기 12곳
#: 전부 줄 끝) 으로 확인했다. 줄 끝 앵커 하나로 표기와 인용이 갈린다.
_TRAILING_PHASE = re.compile(r"\[Phase (\d)\]\s*$")

#: 부록 A.1 표 전체 — 다음 `### ` 제목 전까지.
_APPENDIX_A1 = re.compile(r"### A\.1 Must-have Phase 배정 확인.*?(?=\n### |\Z)", re.S)

#: 부록 A.1 표의 한 Phase 행 — `| **N** | ... |`.
_PHASE_ROW = re.compile(r"^\|\s*\*\*(\d)\*\*\s*\|\s*(.+?)\s*\|\s*$", re.M)

#: Phase 2/3 행 안에서 baseline 을 벗어나는 수용기준을 지목하는 인용 —
#: `FR-202(`AC4` ...)`.
_INCLUSION_CITATION = re.compile(r"FR-(\d+)\(\s*`(AC\d+)`")

#: Phase 1(baseline) 행 안에서 그 baseline 을 벗어난다고 지목하는 인용 —
#: `**FR-205**(v0.16 — `AC1.VPP` 제외)`. baseline 행은 개정으로 바뀐 FR ID 를
#: `**...**` 로 강조하므로(`AC4` 인용의 Phase 2/3 행과 달리) 강조 유무를
#: 함께 받는다.
_EXCLUSION_CITATION = re.compile(r"\*{0,2}FR-(\d+)\*{0,2}\([^)]*?`(AC[\w.]+)`\s*제외\)")

#: 본문 안의 「... 이 선행이다」 인용 — `**AC1.VPP** ... `FR-401-AC2.VPPMarket`
#: 이 선행이다`. 인용 대상과 「이 선행이다」가 **한 줄 안**에 있어야 한다
#: (줄을 건너가면 다른 AC 의 인용을 집어올 위험이 있다 — 기존
#: `test_vpp_rejection_matches_spec_precursor.py` 와 같은 이유).
_PRECURSOR_CITATION = re.compile(
    r"\*\*(AC[\w.]+)\*\*.*?`([A-Za-z]+-\d+-AC[\w.]+)`\s*이 선행이다"
)
_PRECURSOR_ID = re.compile(r"^([A-Za-z]+-\d+)-(AC[\w.]+)$")


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _body_ac_tag(fr_id: str, ac_id: str) -> tuple[bool, str | None]:
    """`(실재하는가, 자기 줄 끝 Phase 값)` — `fr_id` 절 안에서 `ac_id` 를 찾는다.

    다음 최상위 FR/NFR 헤딩 전까지로 범위를 좁힌다. 좁히지 않으면 `AC1`·
    `AC4` 같은 흔한 키가 **다른 요구사항**의 동명 항목을 집어올 수 있다.
    """
    in_section = False
    for line in _spec_text().splitlines():
        heading = _FR_HEADING.match(line)
        if heading:
            in_section = heading.group(1) == fr_id
            continue
        if not in_section:
            continue
        ac_match = _AC_LINE.match(line)
        if ac_match and ac_match.group(1) == ac_id:
            phase_match = _TRAILING_PHASE.search(line)
            return True, (phase_match.group(1) if phase_match else None)
    return False, None


def _appendix_a1_rows() -> list[tuple[str, str]]:
    match = _APPENDIX_A1.search(_spec_text())
    assert match is not None, (
        f"{SPEC} 에서 「### A.1 Must-have Phase 배정 확인」 표를 찾지 못했습니다 — "
        "제목이 바뀌었으면 이 검사의 정규식도 함께 고치십시오"
    )
    rows = _PHASE_ROW.findall(match.group(0))
    assert rows, "부록 A.1 표에서 Phase 행을 찾지 못했습니다 — 표 형식이 바뀌었을 수 있습니다"
    return rows


def _precursor_citations() -> list[dict[str, str | None]]:
    citations: list[dict[str, str | None]] = []
    current_fr: str | None = None
    for line in _spec_text().splitlines():
        heading = _FR_HEADING.match(line)
        if heading:
            current_fr = heading.group(1)
            continue
        match = _PRECURSOR_CITATION.search(line)
        if match:
            phase_match = _TRAILING_PHASE.search(line)
            citations.append(
                {
                    "citing_fr": current_fr,
                    "citing_ac": match.group(1),
                    "citing_phase": phase_match.group(1) if phase_match else None,
                    "precursor_id": match.group(2),
                }
            )
    return citations


@pytest.mark.contract
def test_appendix_a1_inclusion_annotations_match_the_bodys_own_tag() -> None:
    """★ 부록 A.1 이 Phase 2/3 행에서 baseline 을 벗어난다고 괄호로 지목한
    수용기준이, 본문에서도 실제로 그 Phase 를 자기 줄 끝에 달고 있는가.

    지금 이 형식을 만족하는 유일한 예는 `FR-202(`AC4` 구성 diff 뷰 ·
    N≥3 비교)` — Phase 2 행에 있다. **spec 개정으로 같은 형식의 항목이
    늘면 이 검사가 자동으로 함께 본다** — 12곳을 리터럴로 옮기지 않는
    이유가 이것이다. 누군가 본문 467행의 `[Phase 2]` 를 지우거나
    `[Phase 3]` 으로 바꾸면, 부록 A.1 은 여전히 「Phase 2」라 말하는 채로
    남아 두 층이 어긋나야 한다.
    """
    problems: list[str] = []
    checked = 0
    for phase, row_text in _appendix_a1_rows():
        if phase == "1":
            continue  # baseline 행 — 아래 제외 주석 검사가 따로 본다
        for fr_num, ac_id in _INCLUSION_CITATION.findall(row_text):
            checked += 1
            fr_id = f"FR-{fr_num}"
            found, body_phase = _body_ac_tag(fr_id, ac_id)
            if not found:
                problems.append(
                    f"부록 A.1 이 {fr_id}-{ac_id} 를 Phase {phase} 라 적었는데 "
                    f"본문 {fr_id} 절에 {ac_id} 수용기준 자체가 없습니다"
                )
            elif body_phase != phase:
                problems.append(
                    f"부록 A.1 은 {fr_id}-{ac_id} 를 Phase {phase} 라 적었는데 "
                    f"본문 줄 끝 표기는 {body_phase!r} 입니다"
                )
    assert checked, "부록 A.1 Phase 2/3 행에서 `AC숫자` 인용을 하나도 찾지 못했습니다"
    assert not problems, "\n".join(problems)


@pytest.mark.contract
def test_appendix_a1_exclusion_annotations_are_not_phase_1_in_the_body() -> None:
    """★ 부록 A.1 이 Phase 1(baseline) 행에서 「... 제외」라 지목한 수용기준은,
    본문에서 실제로 baseline 이 아닌 자기 Phase 표기를 갖고 있어야 한다.

    지금 유일한 예는 `FR-205(v0.16 — `AC1.VPP` 제외)`. 본문 493행이 그
    표기를 잃으면(지워지거나 `[Phase 1]`이 되면) 부록은 여전히 「제외」라
    말하는데 본문은 baseline 에 남아, 부록과 본문이 서로 다른 것을 말하게
    된다.
    """
    problems: list[str] = []
    checked = 0
    for phase, row_text in _appendix_a1_rows():
        if phase != "1":
            continue
        for fr_num, ac_id in _EXCLUSION_CITATION.findall(row_text):
            checked += 1
            fr_id = f"FR-{fr_num}"
            found, body_phase = _body_ac_tag(fr_id, ac_id)
            if not found:
                problems.append(
                    f"부록 A.1 이 {fr_id}-{ac_id} 를 Phase 1 제외라 적었는데 "
                    f"본문 {fr_id} 절에 {ac_id} 수용기준 자체가 없습니다"
                )
            elif body_phase in (None, "1"):
                problems.append(
                    f"부록 A.1 이 {fr_id}-{ac_id} 를 Phase 1 제외라 적었는데 "
                    f"본문 줄 끝에 baseline(Phase 1) 이 아닌 표기가 없습니다 "
                    f"(실측: {body_phase!r})"
                )
    assert checked, "부록 A.1 Phase 1 행에서 「... 제외」 인용을 하나도 찾지 못했습니다"
    assert not problems, "\n".join(problems)


@pytest.mark.contract
def test_precursor_citations_exist_and_do_not_outrun_their_own_phase() -> None:
    """★★ 「... 이 선행이다」로 선언된 조항이 spec 에 실재하고(매달린 참조
    방지), 인용하는 쪽의 Phase 가 그 선행 조항의 Phase 보다 앞서지 않는다.

    v0.16 머리말: *「정산은 편익 없이 성립하지 않으므로 구조의 Phase 가
    편익의 Phase 를 넘을 수 없다」*. 지금 spec 전체에 이 인용은 `AC1.VPP`
    → `FR-401-AC2.VPPMarket` 하나뿐이다(전수 grep 으로 확인 — 「선행이다」
    는 spec 에 한 번만 나온다). **개정으로 같은 인용이 늘면 이 검사가
    자동으로 함께 본다** — 그래서 인용 패턴 자체를 판정 대상으로 삼았고
    리터럴 목록을 쓰지 않았다.
    """
    citations = _precursor_citations()
    assert citations, (
        "spec 에서 「... 이 선행이다」 인용을 하나도 찾지 못했습니다 — "
        "인용 문구나 정규식 형식이 바뀌었을 수 있습니다"
    )
    problems: list[str] = []
    for citation in citations:
        label = f"{citation['citing_fr']}-{citation['citing_ac']}"
        citing_phase = citation["citing_phase"]
        if citing_phase is None:
            problems.append(
                f"{label} 이 선행 조항을 인용하는데 자기 줄 끝 [Phase N] 표기가 "
                "없습니다 — 표기가 지워졌을 수 있습니다"
            )
            continue

        precursor_id = citation["precursor_id"]
        id_match = _PRECURSOR_ID.match(precursor_id)
        if not id_match:
            problems.append(
                f"{label} 의 선행 인용 ID 형식이 예상과 다릅니다: {precursor_id!r}"
            )
            continue

        precursor_fr, precursor_ac = id_match.groups()
        found, precursor_phase = _body_ac_tag(precursor_fr, precursor_ac)
        if not found:
            problems.append(
                f"{label} 이 선행으로 인용하는 {precursor_id} 가 spec "
                f"{precursor_fr} 절에 없습니다 — 매달린 참조입니다"
            )
            continue
        if precursor_phase is None:
            problems.append(
                f"{precursor_id} (← {label} 의 선행) 자체에 자기 줄 끝 "
                "[Phase N] 표기가 없습니다"
            )
            continue
        if int(citing_phase) < int(precursor_phase):
            problems.append(
                f"{label} 은 Phase {citing_phase} 인데 그 선행 {precursor_id} 은 "
                f"Phase {precursor_phase} 입니다 — 구조가 아직 없는 편익보다 "
                "먼저 서 있습니다"
            )
    assert not problems, "\n".join(problems)
