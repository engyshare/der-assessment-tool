"""리포트 서식 도우미 — 본문·붙임 렌더러가 **같은 표기를 쓰게 하는 자리**.

갈라 두면 「500,000원」과 「500000원」이 같은 문서에 섞이고, 그 어긋남은 아무
검사도 걸리지 않는다. 여기 모은 것은 전부 **표기 규약**이며 계산은 없다.
"""
from __future__ import annotations

#: 값이 없는 칸. 빈칸으로 두면 「없음」과 「빠뜨림」이 구별되지 않는다.
NO_VALUE = "—"


def _cell(text: str) -> str:
    """산문 한 덩이를 **표 한 칸에** 넣는다 — 줄바꿈과 `|` 를 무해하게 만든다.

    ⚠ **자르지 않는다.** 대장의 계측 경계·출처는 길지만, 줄여 실으면 *「무엇을
    재지 않는가」*가 잘려 나가고 그것이 그 칸이 세워진 이유다. 여기서 하는 일은
    **접기**뿐이다 — 줄바꿈이 표를 깨고 `|` 가 열을 하나 더 만든다.

    ⛔ 이것은 산문 「파싱」이 아니다 — 무엇도 뽑아내지 않고 문면 전체를 나른다.

    ## ★★ 왜 이 자리인가 (R68/WP-8)

    R68/WP-7 이 이 함수를 `core/report/verification_demand.py` 안에 두었고, 그
    표는 함정을 피했다. **그런데 대장 전건 표(지금의 4단계 ⓑ)는 피하지 못했다** —
    `docs/assumptions.yaml::load.heatpump.annual` 의 `source` 에 줄바꿈이 들어
    있어 그 행이 마크다운 표에서 **여러 줄로 쪼개져 튕겨 나간다**(R68/WP-7
    실측). 판정은 *「대장을 고치지 말고 표시 층에서 접어라」* 였고
    (`.orch/R68/JUDGMENT-wp7.md`), **접는 자리를 여러 벌 만들지 말라**는 조건이
    붙었다. 그래서 표기 규약의 정본인 이 모듈로 옮겨 두 표가 같은 것을 부른다.

    ⚠ 대장 편집이 아니므로 **값은 한 글자도 바뀌지 않는다** — 인쇄가 바뀐다.
    """
    if not text.strip():
        return NO_VALUE
    return " ".join(text.split()).replace("|", r"\|")

def _won(value: float) -> str:
    return f"{value:,.0f}원"

def _num(value: float) -> str:
    """인자 값 — **지수 표기를 내지 않는다.**

    `1.6e+06` 은 검토자가 읽는 수가 아니다. `MC-1` 이 재는 것이 「리포트만 보고
    설명할 수 있는가」이므로, 읽으려면 변환이 필요한 표기는 그 자체로 미달
    사유가 된다.
    """
    if abs(value) >= 1000.0:
        return f"{value:,.0f}"
    # 1 미만 값에 여섯 자리를 찍으면 **없는 정밀도를 주장하게 된다** —
    # `0.0344389` 는 이진탐색의 수렴 자리이지 그만큼 아는 값이 아니다.
    return f"{value:.4g}"

def _unit_head(unit: str) -> str:
    """단위의 **머리만** — 괄호 안 부연을 뗀다.

    대장의 `value_unit` 은 「원/kWh (PCS·설치 포함 시스템 단가)」처럼 부연을
    안고 있다. 표에서는 그대로가 맞지만 **문장 안에서는 읽기를 끊는다.**
    부연은 붙임 2 의 같은 행에 그대로 남는다.
    """
    return unit.split("(", maxsplit=1)[0].strip()

def _years(value: float) -> str:
    return "분석기간 내 미회수" if value == float("inf") else f"{value:.2f}년"

def _recovery(recovers: bool) -> str:
    """회수 여부 라벨. **두 글자를 한 자리에서만 정한다** — 「회수됨」과
    「회수」가 같은 문서에 섞이면 표를 훑는 눈이 다른 판정으로 읽는다."""
    return "회수" if recovers else "미회수"

def _date(value: object) -> str:
    return str(value) if value else NO_VALUE
