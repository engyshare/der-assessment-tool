"""리포트 서식 도우미 — 본문·붙임 렌더러가 **같은 표기를 쓰게 하는 자리**.

갈라 두면 「500,000원」과 「500000원」이 같은 문서에 섞이고, 그 어긋남은 아무
검사도 걸리지 않는다. 여기 모은 것은 전부 **표기 규약**이며 계산은 없다.
"""
from __future__ import annotations

#: 값이 없는 칸. 빈칸으로 두면 「없음」과 「빠뜨림」이 구별되지 않는다.
NO_VALUE = "—"


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
