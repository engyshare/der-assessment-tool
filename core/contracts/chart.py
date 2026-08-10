"""`Chart` 계약 — spec FR-1004-AC1 · FR-803-AC1 · FR-802-AC2.

**이 계약이 없던 동안 `core/report/charts.py` 는 열 줄짜리 함수 하나였다.**

    def generate_charts() -> dict[str, Any]:
        \"\"\"Generate charts using matplotlib. Mocks the outputs for tests.\"\"\"
        return {"cashflow_line": "Cumulative Cash Flow Chart with BEP", ...}

`matplotlib` 을 import 하지도 않으면서 독스트링이 그것을 쓴다고 적었고, 그
위에 `FR-1001`~`FR-1005`(전부 Must-have·Phase 1)가 얹혀 있었다. 검증하던
테스트는 **dict 에 키 세 개가 있는지**만 보았다.

**왜 함수가 아니라 레지스트리인가** (§16.1 W-3 · NFR-207 과 같은 근거):

    지금 형태로 차트를 더하면 **여섯 사람이 같은 함수의 같은 dict 을
    편집한다.** 자원 6종에서 이미 겪은 구조이고, 그래서 `core/der/` 는
    중앙 등록 파일을 두지 않는다. 차트도 같다 — **차트 1종 = 파일 1개**이며,
    새 차트를 넣을 때 `core/report/charts/__init__.py` 를 포함해 어떤 공유
    파일도 바뀌지 않는다.

**`tag` 는 자원의 `tag` 와 성격이 다르다 — 여기서는 spec 리터럴이 아니다.**

    자원은 spec 이 `FR-102-AC1.PV` 처럼 **키를 부여해 두었으므로** `tag` 가
    그 리터럴이다. 차트는 그렇지 않다 — `FR-1004-AC1` 은 여섯 차트를 한 줄에
    나열할 뿐 키가 없다. 없는 키를 여기서 지어내면 그것은 **spec 개정을
    코드로 하는 것**이고, 나중에 저자가 다른 키를 부여하면 두 곳이 어긋난다
    (v0.7 구조의 재현).

    그래서 `tag` 는 **레지스트리 키**이고, 이 차트가 어느 조항을 그리는지는
    `clauses` 가 따로 선언한다. 조항 쪽 추적은 테스트 마커가 맡는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from core.contracts.validation import ValidationError


@dataclass(frozen=True)
class ChartArtifact:
    """렌더 결과 — **실제 바이트다.**

    문자열 설명을 돌려주지 않는 이유는 이 계약이 생긴 이유 그 자체다.
    `payload` 가 비면 «그렸다» 고 말할 수 없다.
    """

    tag: str
    label: str
    mime: str
    payload: bytes
    clauses: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.payload:
            raise ValueError(
                f"{self.tag}: 빈 산출물은 차트가 아닙니다. 렌더가 실패했다면 "
                "예외를 올리십시오 — 빈 결과를 돌려주면 리포트에 «그렸다» 로 "
                "집계되고, 그 자리는 비어 있는 채로 심의자료에 실립니다"
            )


class Chart(ABC):
    """대시보드·리포트 시각화 1종.

    구현은 `core/report/charts/<tag>.py` 파일 하나이며, 등록은
    `discover(core.report.charts, Chart)` 가 자동으로 한다.
    """

    #: 레지스트리 키. 파일명과 같게 두는 것을 권하지만 강제하지 않는다 —
    #: 강제하면 파생 규약이 하나 늘고, 파생은 조용히 깨진다.
    tag: ClassVar[str]

    #: 사람이 읽는 이름. 리포트 캡션에 그대로 쓰인다
    label: ClassVar[str]

    #: 이 차트가 그리는 spec 수용기준. 비워 두지 않는다 — 어느 조항도 그리지
    #: 않는 차트는 리포트에 있을 이유가 없고, 있다면 조항이 빠진 것이다
    clauses: ClassVar[tuple[str, ...]] = ()

    #: `render()` 가 요구하는 입력 키
    required_keys: ClassVar[tuple[str, ...]] = ()

    #: 산출물 MIME. 지금은 전부 PNG 이나 SVG 차트가 섞일 수 있어 선언으로 둔다
    mime: ClassVar[str] = "image/png"

    def check_data(self, data: Mapping[str, Any]) -> None:
        """입력을 검증한다 — **3요소 오류로** 던진다 (NFR-303).

        `KeyError` 로 두면 사용자에게 키 이름 하나만 도달하고 «어떻게 고치는가»
        가 없다. 차트는 리포트 맨 앞에 오므로 여기서 실패하면 사용자가 가장
        먼저 보는 오류가 된다.
        """
        missing = [key for key in self.required_keys if key not in data]
        if missing:
            raise ValidationError(
                field=f"chart.{self.tag}",
                reason=f"필요한 입력이 없습니다: {', '.join(missing)}",
                action=(
                    f"{self.label} 을 그리려면 "
                    f"{', '.join(self.required_keys)} 를 모두 넘기십시오"
                ),
            )

    @abstractmethod
    def draw(self, data: Mapping[str, Any]) -> bytes:
        """실제 렌더. 구현이 채운다 — **바이트를 돌려준다.**"""

    def render(self, data: Mapping[str, Any]) -> ChartArtifact:
        """검증 → 렌더 → 산출물. 구현이 덮어쓸 필요가 없다."""
        self.check_data(data)
        return ChartArtifact(
            tag=self.tag,
            label=self.label,
            mime=self.mime,
            payload=self.draw(data),
            clauses=self.clauses,
        )
