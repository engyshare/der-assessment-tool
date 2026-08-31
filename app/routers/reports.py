"""리포트 내보내기 라우터 — FR-1003 · FR-1001-AC5(MC-1 의 산출물).

## 왜 이 파일이 R33 에 생겼는가

`app/routers/` 에 리포트·내보내기 엔드포인트가 **0건**이었다. `core/report/` 는
부품이 일습이었는데 그것을 밖으로 내보내는 구멍이 없었고, 그래서 `MC-1`
(Phase 1 인수를 막는 유일한 차단 수동검증)이 **시작될 수 없었다** — 검토자에게
줄 것을 만드는 통로가 없었기 때문이다.

## 이 라우터가 조립을 하지 않는 이유

조립은 `core.report.case_report.build_case_report()` 하나가 한다. 출구가
조립까지 하면 출구마다 다른 조립 순서가 생기고, 그중 하나가 영향도 절을
빠뜨려도 아무 검사도 걸리지 않는다. 여기가 하는 일은 **경로를 고르고 형식을
고르는 것**뿐이다.
"""
from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.report.case_report import CaseReport, build_case_report
from core.report.narrative import render_markdown

router = APIRouter(prefix="/reports", tags=["reports"])

#: 저장소 뿌리 — `app/routers/reports.py` 에서 두 단계 위.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_DIR = _REPO_ROOT / "fixtures" / "golden"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"


def _scenario_path(name: str) -> Path:
    """이름을 골든 시나리오 경로로 옮긴다.

    ⚠ **이름을 경로로 그대로 잇지 않는다.** `../` 이 섞이면 저장소 밖 파일을
    읽게 된다. 목록에 있는 것만 연다 — 화이트리스트가 아니라 경로 정규화로
    막으면 다음 사람이 형식을 늘릴 때 그 정규화를 다시 짜야 한다.
    """
    available = sorted(path.stem for path in _GOLDEN_DIR.glob("scenario_*.yaml"))
    if name not in available:
        raise HTTPException(
            status_code=404,
            detail=(
                f"시나리오 {name!r} 이(가) 없습니다. 사용할 수 있는 것: "
                f"{', '.join(available)}"
            ),
        )
    return _GOLDEN_DIR / f"{name}.yaml"


@router.get("/golden", response_model=list[str])
def list_golden_scenarios() -> list[str]:
    """리포트를 낼 수 있는 시나리오 이름 목록."""
    return sorted(path.stem for path in _GOLDEN_DIR.glob("scenario_*.yaml"))


@router.get("/golden/{name}", response_class=PlainTextResponse)
def golden_report(
    name: str,
    fmt: str = Query(
        default="markdown",
        pattern="^(markdown|json)$",
        description="markdown = 검토자에게 그대로 주는 한 장 · json = 재현용",
    ),
) -> PlainTextResponse:
    """골든 시나리오 하나를 돌려 심의용 리포트를 낸다.

    `markdown` 이 기본인 이유는 `MC-1` 이 *「리포트만 준다」* 이기 때문이다 —
    받는 쪽이 다시 조립해야 하는 형식은 그 검사에서 산출물이 되지 못한다.
    """
    report = build_case_report(_scenario_path(name), assumptions_path=_ASSUMPTIONS)
    if fmt == "json":
        return PlainTextResponse(
            _as_json(report), media_type="application/json; charset=utf-8"
        )
    return PlainTextResponse(
        render_markdown(report), media_type="text/markdown; charset=utf-8"
    )


def _plain(value: object) -> object:
    """`date`·`MappingProxyType`·중첩 dataclass 를 표준 JSON 자료형으로.

    `dataclasses.asdict()` 하나로 끝내지 않는 이유: 그것은 깊은 복사를 하며
    읽기 전용 매핑(`MappingProxyType`)에서 멈춘다. 자료형이 읽기 전용인 것은
    의도(NFR-205)이므로 **자료형을 무르게 만드는 대신 여기서 옮긴다.**

    ## ★ 재무 계층 자료형도 받는다 (R49/WP-3)

    `CaseReport` 가 엔진의 현금흐름 행(`CashFlowRow`)을 나르기 시작하면서
    **dataclass 가 아닌 것**이 처음으로 여기 닿았다 — 그 자료형은 pydantic
    모델이고, 금액은 `Decimal` 이다(NFR-103 재무 계층 규약). 종전에는 둘 다
    아래 `return value` 로 빠져 `json.dumps` 가 그 자리에서 멈췄다.

    ⚠ **자료형 쪽을 무르게 만들어 고치지 않는다** — 위와 같은 이유다. 읽기
    전용도 `Decimal` 도 의도이며, 표준 JSON 으로 옮기는 것은 **출구의 일**이다.
    """
    # ⚠ **둘은 되돌려 보내지 않고 그 자리에서 표준형으로 바꾼다.** 각각을
    # `return _plain(...)` 로 두면 이 함수의 반환 자리가 여덟이 되어 `PLR0911`
    # (상한 여섯)에 걸린다 — 갈래를 늘린 것이 아니라 **모양만 맞춰** 아래
    # 갈래들이 이어 받게 한다(모델 → 매핑 · `Decimal` → `float`).
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if isinstance(value, Decimal):
        # JSON 에 `Decimal` 이 없다. `int` 로 자르지 않는 이유는 이 함수가 금액
        # 전용이 아니기 때문이다 — 비율·계수가 조용히 버려진다.
        value = float(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[attr-defined,no-any-return]
    if isinstance(value, float) and value == float("inf"):
        # JSON 에 `Infinity` 를 내면 표준 파서가 거부한다. 「미회수」는 값이
        # 없는 것이 아니라 **분석기간을 넘었다**는 사실이므로 그렇게 적는다.
        return "분석기간 내 미회수"
    return value


def _as_json(report: CaseReport) -> str:
    """재현용 JSON (`FR-1003-AC3`)."""
    return json.dumps(_plain(report), ensure_ascii=False, indent=2)
