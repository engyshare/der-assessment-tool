"""§7.3 대장의 **코드 사본이 spec 원문과 같은가** — NFR-303-M1 · NFR-107.

R24 가 이것을 만든 이유는 한 워커가 자기 구획에서 **브리프가 인용한 규칙이
원문보다 짧다**는 것을 발견했기 때문이다.

    DV_RULES 사본  요금표 유효기간이 분석연도를 포함
    spec 원문      요금표 유효기간이 분석연도를 포함 (미포함 시 경고 후 최근접 표)

괄호 안이 빠져 있었고, **그 괄호가 요구하는 동작은 거부의 반대**였다 — 원문은
「경고를 내고 최근접 표로 계속 진행」인데 사본만 읽으면 「포함하지 않으면
거부」로 읽힌다. 오케스트레이터의 설계서·대상표·브리프 셋이 같은 절단을
물려받았고, **그 구획에 사람이 와서야 드러났다.**

전건 대조해 보니 **14규칙 중 10이 원문과 달랐다.** 잘린 것들:

    DV-1   자부담액 음수 불가 · v0.3 정정
    DV-4   윤년 처리 규칙 명시
    DV-6   (미포함 시 경고 후 최근접 표)
    DV-7   AssumptionSet 수준에서 선언 · 전 항목에 강제
    DV-8   조정 «후 사용»
    DV-11  스키마 검사로 강제
    DV-13  미특정 편익은 활성화 불가

**이것이 이 저장소의 열일곱 번째 형태다.** 다만 자리가 새롭다 — 지금까지는
「검사가 코드를 붙들지 않는다」였고, 이번은 **규칙 자신이 원문보다 작다.**
검사가 사본을 정확히 붙들어도 붙드는 대상이 이미 줄어 있으면 아무 소용이 없다.

`DV-7` 의 절단이 특히 값을 냈다. 사본에는 「실질/명목 구분을 1회 선언」이라고만
있어서 오케스트레이터가 「`Money` 타입과 `to_won()` 경계가 이미 강제한다」로
판정했다. 원문은 **선언 자리를 `AssumptionSet` 으로 못 박고 「전 항목에 강제」를
요구한다.** `AssumptionSet` 에 그런 필드는 없다(`name`·`version`·
`parent_version_id`·`notes` 뿐). **판정이 틀렸고 사본이 그것을 가렸다.**
(검증 구획의 워커가 사본만 보고도 독립적으로 같은 반박을 냈다.)

왜 「대장에 있는지」만 보는 것으로는 안 되는가
---------------------------------------------
`tests/contract/test_dv_rule_enforcement.py` 는 **대장의 키**를 붙든다 —
열다섯 번째 규칙이 들어오면 분류를 요구하고, 던진다고 적은 규칙에 `rule=` 이
없으면 막는다. **그런데 키만 본다.** 문면이 원문에서 얼마나 줄어들었는지는
어느 검사도 보지 않았고, 그래서 열 규칙이 조용히 작아진 채로 다섯 라운드를
지났다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.contracts.validation import DV_RULES

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "rslt" / "spec-분산특구-경제성평가.md"

#: spec §7.3 표의 한 줄 — `| DV-N | 문면 |`
_ROW = re.compile(r"^\|\s*(DV-\d+)\s*\|\s*(.+?)\s*\|\s*$", re.M)


def _normalise(text: str) -> str:
    """마크다운 강조와 공백만 지운다 — **낱말은 지우지 않는다.**

    원문은 표 안에서 `**...**` 와 백틱으로 강조한다. 사본은 평문 메시지에
    쓰이므로 강조를 그대로 나를 수 없다. 그래서 **강조 표시만** 걷어내고
    비교한다.

    ⚠ 여기서 낱말을 지우기 시작하면 이 검사가 무의미해진다. 예를 들어 괄호를
    지우면 `DV-6` 의 「(미포함 시 경고 후 최근접 표)」가 사라져 **이 파일이
    고치러 온 결함이 그대로 통과한다.** 지우는 것은 `*` 와 `` ` `` 와
    연속 공백뿐이다.
    """
    text = text.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _spec_catalogue() -> dict[str, str]:
    rows = {
        m.group(1): _normalise(m.group(2))
        for m in _ROW.finditer(SPEC.read_text(encoding="utf-8"))
    }
    assert rows, (
        f"{SPEC} 에서 §7.3 대장 표를 찾지 못했습니다 — 표 형식이 바뀌었다면 "
        "이 검사의 정규식을 함께 고치십시오. **찾지 못한 것을 통과로 읽으면** "
        "이 파일이 고치러 온 결함이 되돌아옵니다."
    )
    return rows


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_every_code_rule_exists_in_the_spec_ledger() -> None:
    """사본에만 있는 규칙이 없어야 한다 — 매달린 참조(`NFR-107`)."""
    spec = _spec_catalogue()
    orphans = sorted(set(DV_RULES) - set(spec))
    assert not orphans, (
        f"코드 대장에만 있는 규칙입니다: {orphans}. spec §7.3 에 없는 ID 에 "
        "`rule=` 을 달면 추적표가 그것을 검증된 것으로 세지만 어느 조항도 "
        "가리키지 않습니다 (매달린 참조)."
    )


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_every_spec_rule_exists_in_the_code_catalogue() -> None:
    """원문에만 있는 규칙이 없어야 한다 — 사본이 뒤처지는 방향."""
    spec = _spec_catalogue()
    missing = sorted(set(spec) - set(DV_RULES))
    assert not missing, (
        f"spec §7.3 에 있는데 코드 대장에 없는 규칙입니다: {missing}. "
        "`DV_RULES` 에 추가하고 "
        "`tests/contract/test_dv_rule_enforcement.py` 의 세 분류 중 하나에 "
        "함께 넣으십시오."
    )


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_the_wording_is_not_shortened_anywhere() -> None:
    """★★ **문면이 원문과 같아야 한다** — 이것이 이 파일의 요점이다.

    키가 맞는지만 보면 규칙이 **조용히 작아진다.** R24 에 열 규칙이 그 상태
    였고, 그중 `DV-6` 은 잘린 괄호가 **거부의 반대 동작**을 요구했다. 사본을
    근거로 판정한 사람은 규칙을 반대로 구현하게 된다.

    특히 **사본이 원문의 접두인 경우**(뒤가 잘린 경우)를 따로 알려 준다 —
    그것이 가장 흔하고, 읽는 사람이 「같은 말을 줄여 적었다」로 넘기기 쉽다.
    """
    spec = _spec_catalogue()
    problems: list[str] = []
    for rid, code_text in DV_RULES.items():
        if rid not in spec:
            continue  # 위 두 검사가 본다
        code_norm, spec_norm = _normalise(code_text), spec[rid]
        if code_norm == spec_norm:
            continue
        how = (
            "**뒤가 잘렸다**" if spec_norm.startswith(code_norm)
            else "문면이 다르다"
        )
        problems.append(
            f"\n  {rid} — {how}\n"
            f"    코드: {code_norm}\n"
            f"    원문: {spec_norm}"
        )

    assert not problems, (
        "코드 대장의 문면이 spec §7.3 원문과 다릅니다:"
        + "".join(problems)
        + "\n\n원문을 그대로 옮기십시오. 줄여 적으면 그 규칙을 근거로 한 판정이 "
        "**줄인 만큼 작아집니다** — R24 에 `DV-6` 의 잘린 괄호가 「경고 후 "
        "최근접 표」를 요구하는데 사본만 읽고 「거부」로 구현할 뻔했습니다."
    )
