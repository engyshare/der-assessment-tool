"""입력 검증 오류의 3요소 계약 — spec NFR-303 · §7.3 DV-1~DV-14.

NFR-303 은 오류 메시지가 **«어떤 필드가 / 왜 / 어떻게 고쳐야 하는지»** 를
제시할 것을 요구한다. 그런데 지금까지 DV 규칙들은 **라벨 없는 단일 문자열**을
각자 던져 왔다 — 여섯 파일 열 몇 곳이 제각기 `ValueError("...")` 를 올리고,
사람이 읽으면 셋이 다 들어 있는 것처럼 보이지만 **기계가 그 셋을 분리해
확인할 방법이 없다.**

    ValueError("SOC 하한이 상한보다 큽니다")      ← 필드는? 조치는?

**그래서 문자열이 아니라 구조로 던진다.** 세 칸이 비면 예외 자체가 만들어지지
않으므로, 「3요소를 갖췄는가」는 검사가 아니라 **생성 조건**이 된다.

**왜 이것이 확장점인가.** 지금 규칙은 DV-1~DV-14 열넷이다. 열다섯 번째가
생길 때 필요한 것은 `ValidationError(...)` 한 번을 올리는 일뿐이고, 메시지
품질 검사·UI 표시·리포트 표기는 **아무것도 고치지 않는다.** 규칙마다 메시지를
손으로 짜는 구조라면 열다섯 번째는 반드시 어느 한 요소를 빠뜨린다 —
그리고 그 누락은 그 규칙이 실제로 발동하는 입력을 넣어 보기 전에는 안 드러난다.

**`ValueError` 를 상속하는 이유.** 기존 호출부가 `except ValueError` 로 받고
있다. 새 기반 예외를 만들면 그 호출부들이 조용히 통과시키게 되고, 그 변화는
**아무 오류도 나지 않는 형태**로 나타난다 (§13.0.1 ④ — 검사가 통과한 것과
검사가 무언가를 검사한 것은 다르다).
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Final

#: `§7.3` 검증 규칙 대장 — 규칙 ID 와 그 규칙이 무엇을 지키는가.
#:
#: **여기 있는 것은 «설명»뿐이고 «판정»이 아니다.** 판정은 각 규칙이 발동하는
#: 자리에 있으며, 이 표는 규칙 ID 가 spec 에 실재하는지를 대조하는 데 쓴다.
#: 데이터 파일로 빼지 않은 이유는 **새 규칙이 어차피 발동 지점(코드)을
#: 요구하기 때문**이다 — 설명만 파일로 빼면 「대장에는 있는데 아무도 던지지
#: 않는 규칙」이 조용히 생기고, 그것이 이 저장소가 반복해 만난 형태다.
DV_RULES: Final[MappingProxyType[str, str]] = MappingProxyType({
    "DV-1": "보조 확정액 + 융자 확정액 + 자부담액 = 대상 총사업비 (오차 1원 이내)",
    "DV-2": "ESS SOC 하한 < SOC 상한, 둘 다 [0,100]",
    "DV-3": "RTE ∈ (0,100], 열화율 ∈ [0,10] %/년",
    "DV-4": "시계열 행수 = 8760 (또는 35,040)",
    "DV-5": "분석기간 ≤ 최장 자원 수명의 2배, 기본 20년",
    "DV-6": "요금표 유효기간이 분석연도를 포함",
    "DV-7": "모든 금액은 명목 원(KRW), 실질/명목 구분을 1회 선언",
    "DV-8": "카탈로그·전제 단가는 기준연도 보유, 분석연도로 물가 조정",
    "DV-9": "결합 집합 내 변수들의 값 목록 길이가 모두 동일 (FR-802)",
    "DV-10": "케이스 그리드 생성 수가 임계치(기본 500) 초과 시 사용자 확인",
    "DV-11": "`Scenario` 는 규제 프로파일·요금표·할인율·분석기간 필드를 보유할 수 없다",
    "DV-12": "활성 편익 조합이 배타 규칙을 위반하지 않아야 한다 (FR-402). 위반 시 실행 거부",
    "DV-13": "모든 활성 편익은 지불 주체가 특정되어야 한다 (FR-402 공통 기준)",
    "DV-14": "자원의 운전 방법(FR-105)은 해당 자원 클래스가 선언한 목록에 속해야 한다",
})

#: 규칙 ID 형식. `DV-<번호>` 만 받는다 — 자유 문자열을 허용하면 오타가 대장에
#: 없는 규칙으로 조용히 통과하고, 그러면 대장 대조가 무의미해진다.
_RULE_PATTERN: Final = re.compile(r"^DV-\d+$")


class ValidationError(ValueError):
    """입력 검증 실패 — **필드·사유·조치 셋을 반드시 갖는다** (NFR-303).

        raise ValidationError(
            field="ess.soc_min",
            reason="SOC 하한(80)이 상한(20)보다 큽니다",
            action="하한을 상한보다 작은 값으로 고치십시오",
            rule="DV-2",
        )

    셋 중 하나라도 비면 **이 예외를 만드는 시점에** 다른 예외가 난다. 검사로
    두면 「검사를 돌리지 않은 경로」가 생기지만, 생성 조건으로 두면 그런 경로가
    없다 — 빈 조치를 가진 `ValidationError` 는 **존재할 수 없다.**

    `rule` 은 선택이다. `§7.3` 대장에 있는 규칙이면 ID 를 달고, 대장 밖의
    일반 입력 검증이면 비운다. **다는 경우에는 대장에 실재해야 한다** —
    없는 ID 를 달면 추적표가 그 규칙을 검증된 것으로 세고, 실제로는 아무
    조항도 가리키지 않는다 (매달린 참조, NFR-107).
    """

    def __init__(
        self,
        *,
        field: str,
        reason: str,
        action: str,
        rule: str | None = None,
    ) -> None:
        missing = [
            name
            for name, value in (("field", field), ("reason", reason), ("action", action))
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            raise ValueError(
                "ValidationError 는 필드·사유·조치 셋을 모두 요구합니다 "
                f"(NFR-303). 빠진 것: {', '.join(missing)}. "
                "셋을 갖추지 못하는 오류라면 그것은 검증 오류가 아니라 "
                "내부 결함이므로 다른 예외를 쓰십시오"
            )
        if rule is not None:
            if not _RULE_PATTERN.match(rule):
                raise ValueError(
                    f"규칙 ID 형식이 아닙니다: {rule!r}. `DV-<번호>` 여야 합니다"
                )
            if rule not in DV_RULES:
                raise ValueError(
                    f"§7.3 검증 규칙 대장에 없는 ID 입니다: {rule!r}. "
                    "대장 밖 ID 를 달면 추적표가 그 규칙을 검증된 것으로 세지만 "
                    "실제로는 어느 조항도 가리키지 않습니다 (매달린 참조, NFR-107). "
                    f"대장: {', '.join(DV_RULES)}"
                )

        self.field = field
        self.reason = reason
        self.action = action
        self.rule = rule
        super().__init__(str(self))

    def __str__(self) -> str:
        """사람이 읽는 한 줄 — **셋이 눈에 보이는 순서로** 들어간다.

        `[규칙] 필드 — 사유. 조치` 형식이며, 이 순서는 NFR-303 본문의
        «어떤 필드가 / 왜 / 어떻게» 와 같다.
        """
        head = f"[{self.rule}] " if self.rule else ""
        return f"{head}{self.field} — {self.reason}. {self.action}"

    def as_dict(self) -> dict[str, str | None]:
        """UI·리포트가 쓰는 구조 표현.

        **문자열을 다시 파싱하게 두지 않는다.** 표시 쪽이 `__str__` 을 쪼개
        쓰면 메시지 형식이 바뀔 때마다 표시가 조용히 깨지고, 그 깨짐은 오류가
        실제로 날 때만 드러난다.
        """
        return {
            "field": self.field,
            "reason": self.reason,
            "action": self.action,
            "rule": self.rule,
        }
