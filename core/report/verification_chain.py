"""목차의 **의존 연결표** — 어느 마디가 어느 단계에서 나오고 그 단계가 무엇을
넘기는가 (R68/WP-4-fix · 검토서 §2.2).

## 무엇이 없었나

검토서 §2.2: *「현재 파일은 다음 단계로 넘긴 값을 적고 있으나, **어떤 계산이
어떤 값에 의존하는지 한눈에 보이는 연결표가 없다.** 최소한 목차에 다음 연결을
표시해야 한다」* — 그 사슬이 아래 `CHAIN_NODES` 다.

단계 파일 열은 각자의 **ⓒ 다음 단계로 넘긴 값**을 이미 갖고 있었다. 없던
것은 **그 열을 한자리에 모아 보여 주는 곳**이고, 그 자리는 목차다(`00-목차.md`
— 단계 파일을 열기 전에 읽는 곳).

## ★ 모았다 — 베끼지 않았다

가운데 칸(**그 단계가 넘긴 값**)은 `core/report/verification.py::StageBlock` 의
`handoff`, 즉 **단계 본문의 ⓒ 절 그대로**다. 목차가 그 문면을 따로 적으면 두
곳에 같은 말이 생기고, 그때 한쪽만 고쳐진다 — 이 저장소가 형상·기준선·REC 에서
이미 밟은 형태다.

⛔ **완성된 마크다운을 되읽어 ⓒ 절을 찾지 않는다.** 그 갈래는 절 이름
(「ⓒ 다음 단계로 넘긴 값」)에 매이고, 이름을 고치는 날 **조용히 빈 표**가 된다.
대신 단계를 지을 때 이미 손에 있던 `c` 를 `StageBlock` 이 함께 실어 온다.

## ⚠ 오른쪽 칸도 사람이 정한 목록이 «아니다»

**받는 단계**는 ⓒ 문면이 **스스로 이름 부른 단계**를 세어 낸다(`3단계` ·
`9단계` · `2~10단계`). 그러므로 ⓒ 를 고치면 이 칸이 함께 바뀌고, ⓒ 가 아무
단계도 이름 부르지 않으면 **그 사실을 적는다**(`NO_STAGE_NAMED`) — 지어내지
않는다.

⚠ **자기 단계 번호는 세지 않는다.** 「이 표의 키가 2~10단계 전체에서」처럼 자기를
포함해 적은 문면이 있고, 자기가 자기에게 넘긴다는 칸은 뜻이 없다.

⚠⚠ **부정문을 읽지 못한다** — *「1단계가 아니라 5단계가 받는다」* 라고 적힌 ⓒ 는
둘을 다 이름 부른 것으로 센다. 그래서 칸 이름이 「받는 단계」가 **아니라**
**「ⓒ 가 이름 부른 단계」**다 — 낱말이 그 한계를 산출물에 적어 두며, 시험이 그
한계를 고정한다(`tests/report/test_verification.py`). 문장을 해석해 「진짜 받는
단계」를 판정하려 들면 그것은 **모으는 일이 아니라 짓는 일**이고, 지어낸 판정은
검토자가 대조할 근거가 없다.

## ⚠ 왼쪽 칸만 «사람이 정한다» — 그리고 그것이 검토서의 것이다

「사슬의 어느 마디가 어느 단계에서 나오는가」는 코드가 알 수 없다 — 사슬은
**검토서가 그린 것**이고 단계는 이 저장소가 세운 것이다. 그래서 그 대응만
`CHAIN_NODES` 가 손으로 갖는다. ⚠ **틀리게 가리키면 멈춘다** —
`dependency_chain_lines` 가 없는 단계 번호를 보면 예외를 낸다(빈 칸으로 지나가면
검토자는 그 마디가 어디서도 안 나온다고 읽는다).

## ⚠ 새 단계를 만들지 않는다

이 모듈이 내는 줄은 **목차 파일에만** 실리고 `## N단계 — ` 로 시작하는 줄을
내지 않는다 — `app/services/verify_steps.py::split_stages` 가 그 머리글로 단계를
쪼개고 `app/services/verify_steps.py::STAGE_COUNT` 는 **10** 이다.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from core.report.verification import StageBlock

#: 검토서 §2.2 가 그린 **사슬**과 각 마디가 나오는 **단계 번호**.
#:
#: 마디 이름은 검토서 문면 그대로다 — 「편익·전력구매비」를 둘로 쪼개지 않는다
#: (그 마디 하나가 5단계 편익과 6단계 운영비에 걸쳐 있고, 쪼개면 검토서가 적은
#: 사슬과 이 표가 다른 모양이 된다).
#:
#: ⚠ **「시간대별 부하」가 1단계인 이유**: 그 마디의 «값»은 계절 몫과 하루 안에서
#: 옮길 수 있는 비율이며 1단계가 그것을 싣는다. 그 형상으로 **실제로 돈** 스텝별
#: 표는 3단계(사슬의 `dispatch` 마디)가 싣는다. 사슬의 차례(부하 → 용량 → 운전)도
#: 그 읽기와 같다 — 용량 역산이 부하의 시간 분포를 이미 쓰기 때문이다.
CHAIN_NODES: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("수요 구성", (1,)),
    ("시간대별 부하", (1,)),
    ("PV·ESS 용량", (2,)),
    ("dispatch", (3,)),
    ("수전·역송", (3,)),
    ("편익·전력구매비", (5, 6)),
    ("현금흐름", (8,)),
    ("NPV", (9,)),
)
#: ★ **R69/WP-1 이 번호를 밀었다** — 옛 4·5 → 5·6(편익·운영비) · 옛 7 → 8
#: (현금흐름) · 옛 8 → 9(NPV). 마디 «이름»은 검토서의 것이라 그대로다.
#:
#: ⚠ 사슬이 이름 부르지 않는 단계가 **셋**이 되었다 — 4(경제성 입력) ·
#: 7(생애주기) · 10(변형). 검토서 §2.2 의 사슬에 그 마디가 없기 때문이며
#: **없는 마디를 지어 넣지 않는다**: 아래 `dependency_chain_lines` 가 그 사실을
#: 「사슬이 이름 부르지 않은 단계」 줄로 적는다.

#: 절 제목. ⚠ 「전제」를 쓰지 않는다(판정 R63b §1).
CHAIN_TITLE = "단계 의존 연결 — 어느 마디가 어느 단계에서 나오고 무엇을 넘기는가"

#: ⓒ 가 받는 단계를 이름 부르지 않았을 때의 칸. **빈칸으로 두지 않는다** —
#: 빈칸은 「없다」와 「적지 않았다」를 구별해 주지 않는다
#: (`core/report/_format.py::NO_VALUE` 가 같은 사유를 적는다).
NO_STAGE_NAMED = "ⓒ 가 이름 부른 단계가 없다"

#: ⓒ 절에 문장이 없을 때의 칸(표 행만 있거나 비어 있을 때).
NO_HANDOFF_PROSE = "ⓒ 절에 문장이 없다 — 그 단계 파일의 표가 인계를 진다"

#: 「N단계」·「N~M단계」를 그대로 집는다. `app/services/verify_steps.py::
#: split_stages` 의 단계 머리글 정규식과 **같은 낱말**을 보되, 이쪽은 문장 안에
#: 있는 것을 센다.
_STAGE_MENTION = re.compile(r"\d+(?:~\d+)?단계")


def _prose(block: StageBlock) -> list[str]:
    """ⓒ 절의 **문장 줄만** — 표 행(`|`)은 뺀다.

    ⚠ **칸 안에 표를 넣을 수 없다.** 4단계의 ⓒ 는 문장 하나와 대장 키 표
    열일곱 행인데, 그 표를 한 칸에 밀어 넣으면 목차의 표가 깨진다. ⇒ 문장만
    싣고 **표가 있다는 사실은 그 단계 파일이 진다** — 목차는 그 파일을 가리키는
    표를 이미 갖는다.
    """
    return [line for line in block.handoff if line.strip() and not line.startswith("|")]


def handoff_text(block: StageBlock) -> str:
    """가운데 칸 — ⓒ 문장들을 이어 붙인다. **다시 쓰지 않는다.**

    ⚠ `|` 를 탈출시킨다 — ⓒ 문면에 그 글자가 들어오는 날 목차의 표가 조용히
    깨지고, 깨진 표는 「연결이 없다」로 읽힌다.
    """
    prose = _prose(block)
    if not prose:
        return NO_HANDOFF_PROSE
    return " ".join(prose).replace("|", r"\|")


def named_stages(block: StageBlock) -> str:
    """오른쪽 칸 — **ⓒ 가 스스로 이름 부른 단계들**(자기 자신은 뺀다)."""
    own = f"{block.number}단계"
    found = [
        mention
        for mention in dict.fromkeys(_STAGE_MENTION.findall(" ".join(_prose(block))))
        if mention != own
    ]
    return " · ".join(found) if found else NO_STAGE_NAMED


def _chain_line() -> str:
    """사슬 한 줄 — **마디 이름을 두 번 적지 않는다**(위 표와 같은 자료에서 온다)."""
    return " → ".join(label for label, _stages in CHAIN_NODES)


def _stage_label(numbers: Sequence[int]) -> str:
    return " · ".join(f"{number}단계" for number in numbers)


def _assert_nodes_point_at_real_stages(blocks: Sequence[StageBlock]) -> None:
    """사슬의 마디가 **없는 단계**를 가리키면 멈춘다.

    빈 칸으로 지나가면 검토자는 *「그 마디는 어디서도 안 나온다」* 로 읽는다 —
    단계 번호가 바뀌는 날 조용히 틀리는 대신 여기서 예외를 낸다(이 저장소가
    `split_stages` 의 단계 수 검사에서 내린 것과 같은 판단이다).
    """
    have = {block.number for block in blocks}
    missing = sorted(
        {number for _label, numbers in CHAIN_NODES for number in numbers} - have
    )
    if missing:
        raise ValueError(
            f"사슬이 없는 단계를 가리킨다 — {_stage_label(missing)}. "
            f"이 실행의 단계는 {_stage_label(sorted(have))} 다. "
            "CHAIN_NODES 의 단계 번호를 고치거나, 단계를 되돌리십시오"
        )


def dependency_chain_lines(blocks: Sequence[StageBlock]) -> list[str]:
    """목차에 실을 **의존 연결표** 줄들 (검토서 §2.2).

    ⚠ 목차 파일에만 실린다 — 단계 본문은 이 함수를 부르지 않는다. 한 덩어리
    갈래(`--split-stages` 없이)의 머리말도 그대로다: 그 갈래는 열 단계가 한
    파일에 이어 있어 사슬을 눈으로 따라갈 수 있고, 목차가 없다.
    """
    _assert_nodes_point_at_real_stages(blocks)
    mapped = {number for _label, numbers in CHAIN_NODES for number in numbers}
    unnamed = [block.number for block in blocks if block.number not in mapped]
    lines = [
        f"## {CHAIN_TITLE}",
        "",
        f"검토서 §2.2 가 적은 사슬 — `{_chain_line()}`",
        "",
        "| 사슬의 마디 | 나오는 단계 |",
        "| --- | --- |",
        *(
            f"| {label} | {_stage_label(numbers)} |"
            for label, numbers in CHAIN_NODES
        ),
        "",
    ]
    if unnamed:
        lines += [
            f"- 사슬이 이름 부르지 않은 단계 — **{_stage_label(unnamed)}**. 그 "
            "단계도 인계가 있다 — 아래 표의 가운데 칸이 그것을 진다",
            "",
        ]
    lines += [
        "| 단계 | 그 단계가 넘긴 값 — **ⓒ 절 그대로** | ⓒ 가 이름 부른 단계 |",
        "| --- | --- | --- |",
        *(
            f"| {block.number}단계 | {handoff_text(block)} | {named_stages(block)} |"
            for block in blocks
        ),
        "",
        "- 가운데 칸은 **단계 파일의 「ⓒ 다음 단계로 넘긴 값」 절을 모은 것**이다 "
        "— 목차가 따로 적지 않으므로 단계가 바뀌면 이 표도 함께 바뀐다. "
        "⚠ 그 절의 **표 행은 옮기지 않았다**(칸에 표를 넣을 수 없다) — 표는 그 "
        "단계 파일이 진다",
        "- 오른쪽 칸은 **ⓒ 문면이 스스로 이름 부른 단계**다(사람이 정한 목록이 "
        f"아니다). 자기 단계는 세지 않으며, 이름 부른 단계가 없으면 「{NO_STAGE_NAMED}」"
        "라고 적는다",
    ]
    return lines
