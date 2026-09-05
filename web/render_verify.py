"""검증 모드 화면의 문맥 — **네 걸음에 얹은 9단계를 사전으로 옮긴다.**

사용자 문면(`docs/decisions-2026-09-05-R63.md` §1 「결과」): *「분석결과는
순차적으로 분석 과정 상의 중간값을 사용자가 확인할 수 있는 형태로 제시하는
검증 모드를 제공해야 함」*.

## 이 파일이 값을 짓지 않는 이유

단계 본문은 `core/report/verification.py` 가 낸 **문자열 그대로**이고, 걸음
구성과 빈 칸은 `app/services/verify_steps.py` 가 정한다. 여기가 하는 일은
**그것을 템플릿이 읽는 사전으로 옮기는 것**뿐이다 — `web/render.py` 의
`*_context()` 들이 같은 자리를 지키며, 출구가 문맥까지 지으면 출구마다 다른
문맥이 생기고 그중 하나가 걸음을 줄여 그려도 아무 검사도 걸리지 않는다.

## ⚠ Jinja 환경을 새로 짓지 않는다

`web/render.py` 의 `_ENV` 를 **가져다 쓴다.** 여기서 `Environment(...)` 를
다시 지으면 자동 이스케이프 정책이 두 곳에 살고, 한쪽만 고쳐지는 날 한 화면만
이스케이프가 풀린 채 남는다 — 그리고 그 상태는 아무 검사도 걸리지 않는다.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from app.services.verify_steps import build_verify_groups
from core.report.case_report import CaseReport

# ⚠ 사설 이름을 가져오는 자리다. `web/render.py` 는 이 라운드에서 **고칠 수 없는
# 파일**이라 `__all__` 에 이름을 더할 수 없고, 환경을 여기서 새로 지으면 위
# 머리말의 사고가 난다. 둘 중 덜 나쁜 쪽을 고른 것이며 그 사유를 여기 적는다.
from web.render import _ENV

#: 걸음 번호의 화면 문면. **사용자가 예시를 넷으로 들었고** 그 번호가 화면에서
#: 보여야 「순차적」이 성립한다. 목록을 여기 두는 이유는 `verify_steps` 가 정한
#: 걸음 수와 이 문면이 **같은 파일에 살면 안 되기 때문이 아니라**, 이것이
#: 표기이지 구성이 아니기 때문이다 — 걸음이 늘면 아래 `_ordinal` 이 번호를
#: 그대로 낸다(문면이 없어도 조용히 비지 않는다).
_ORDINALS = ("①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨")


def _ordinal(number: int) -> str:
    if 1 <= number <= len(_ORDINALS):
        return _ORDINALS[number - 1]
    # 걸음이 아홉을 넘으면 동그라미가 없다. 조용히 비우지 않고 번호를 낸다 —
    # 빈 제목은 「걸음이 없다」와 구별되지 않는다.
    return f"{number}."


def verify_context(report: CaseReport) -> dict[str, Any]:
    """검증 모드 화면이 읽는 사전.

    ⚠ 수를 하나도 서식하지 않는다. 단계 본문·순수요 표는 이미 서식이 입혀져
    있고, 여기서 다시 손대면 화면과 CLI 산출물의 표기가 갈린다.
    """
    return {
        "scenario_name": report.scenario_name,
        "assumption_set": (
            f"{report.assumption_set_name} 판 {report.assumption_set_version}"
        ),
        "manifest": report.manifest_hash[:16],
        "groups": tuple(
            {**dataclasses.asdict(group), "ordinal": _ordinal(group.number)}
            for group in build_verify_groups(report)
        ),
    }


def render_verify(context: dict[str, Any]) -> str:
    """검증 모드 화면(또는 거부)을 그린다.

    ⚠ **거부를 다른 템플릿으로 가르지 않는다.** 가르면 검증 화면이 머리·탐색을
    고칠 때마다 거부 화면만 낡고, 그 낡음은 사람이 실제로 거부당할 때까지
    보이지 않는다 — `web/render.py::render_run_result` 가 같은 판단을 적는다.
    """
    return _ENV.get_template("verify.html").render(context)
