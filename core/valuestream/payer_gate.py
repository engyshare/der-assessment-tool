"""4문항 판정 게이트 — FR-402-AC5 · 도메인 원칙 부록 A.

편익을 활성화할 때 4문항 판정을 통과했는지 확인한다. ``ValueStream.__init__``
이 Q1(지불 주체)을 이미 강제하지만, 여기서 4문항 전부를 한 곳에서 모아
«판정 통과»를 명시적으로 반환한다 — 리포트(FR-402-AC6)가 «판정됨» 과
«판정 안 됨» 을 구분해 표시하려면 이 통로가 있어야 한다.

4문항 (도메인 원칙 부록 A):
    Q1. 이 편익의 돈은 누구 지갑에서 나오는가?  → 특정 불가하면 계상 불가
    Q2. 그 지갑에서 나오는 돈이 다른 편익 항목에도 들어 있는가?
        → 들어 있으면 증분만 계상 (유형 B)
    Q3. 이 편익이 소비하는 물리량을 다른 편익도 소비하는가?
        → 소비하면 배타 규칙 등록 (유형 A)
    Q4. 제도가 동시 수취를 허용하는가?
        → 불허하면 배타 규칙 등록 (유형 D)
        → 확인 못 했으면 보수적으로 배타 처리
"""
from __future__ import annotations

from dataclasses import dataclass

from core.contracts.valuestream import Payer, ValueStream


@dataclass(frozen=True)
class FourQuestionVerdict:
    """4문항 판정 결과 — 편익 1건당 1건."""

    stream_tag: str
    q1_payer_specified: bool
    q2_increment_only: bool
    q3_physical_overlap_registered: bool
    q4_institutional_check_done: bool
    note: str = ""

    @property
    def passed(self) -> bool:
        """Q1 은 필수, Q2~Q4 는 «검사가 이루어졌는지» 가 기준 (결과가 아니다).

        Q1 은 주체 미특정이면 **활성화를 거부**한다 (계약 ValueStream.__init__).
        Q2~Q4 는 «판정이 이루어졌는지» — 이루어지지 않은 편익은 «판정 보류»
        로 리포트에 표시되어야 한다 (FR-402-AC6).
        """
        return self.q1_payer_specified


def assess(stream: ValueStream) -> FourQuestionVerdict:
    """편익 1건에 대한 4문항 판정.

    Q1 은 ``stream.payer`` 로 바로 판정. ``Payer.UNSPECIFIED`` 면 거부.
    Q2~Q4 는 **외부(호출부)에서 채운다** — 이 함수는 «자동으로 답을 내지
    않는다». 답을 내면 «판정됨» 이라는 거짓 표식이 붙고, 검증되지 않은
    편익이 통과한다.
    """
    payer_ok = stream.payer is not Payer.UNSPECIFIED
    return FourQuestionVerdict(
        stream_tag=type(stream).tag,
        q1_payer_specified=payer_ok,
        # 호출부가 명시적으로 채운다 — 기본은 «판정 안 됨».
        q2_increment_only=False,
        q3_physical_overlap_registered=False,
        q4_institutional_check_done=False,
        note="Q2~Q4 는 assess() 호출부가 채운다 — 자동으로 «판정됨» 을 "
        "내지 않는다 (FR-402-AC6 리포트 구분을 위함)",
    )


def assert_activation_allowed(stream: ValueStream) -> None:
    """활성화 게이트 — Q1 실패 시 ValueError.

    ``ValueStream.__init__`` 이 같은 검사를 하지만, 8.5 는 이 통로를
    «4문항 판정» 이라는 맥락에서 명시적으로 노출한다. 리포트가 «왜 거부됐나»
    를 4문항 용어로 설명하려면 이 함수가 한 곳이어야 한다.
    """
    verdict = assess(stream)
    if stream.enabled and not verdict.passed:
        raise ValueError(
            f"{stream.name}: 4문항 판정 Q1(지불 주체) 실패 — 활성화를 거부한다 "
            "(FR-402-AC5). 편익의 돈이 누구 지갑에서 나오는지 특정되어야 한다. "
            "주체가 없으면 같은 화폐 흐름이 두 관점에서 각각 계상되어 이중 계상"
        )
