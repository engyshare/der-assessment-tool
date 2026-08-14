"""계약·거래 구조별 정산 — FR-205-AC1.

⚠ **금액은 아직 스텁이다** — 어느 구조를 넣어도 `0.0` 이다. 조립 규칙(구조마다
어느 편익을 켜고 단가를 어디서 가져오는가)이 정해지지 않았기 때문이고, 그
사실은 spec §FR-205 주석과 `docs/decisions-2026-08-14-R31.md` §2 에 있다.
**여기에 임시 산식을 채우지 않는다** — 근거 없는 값이 한 번 들어가면 다음
라운드가 그것을 「검증된 값」으로 읽는다.

## R31 이 고친 것은 금액이 아니라 **구조 어휘의 소유자**다

이 파일은 `SUPPORTED_STRUCTURES` 라는 자기 목록을 들고 있었고, **일곱 중 셋이
계약과 달랐다.**

    이 파일이 적던 것        계약(`CONTRACT_STRUCTURES`, spec 리터럴)
    개별 직접계약        →   개별 세대 직접계약
    단일계약+관리주체    →   단일계약+관리주체 경유
    상계                 →   상계거래

**그 어긋남은 조용하다.** 사용자가 spec 문면대로 「상계거래」를 고르면 이 엔진이
거부하고, 이 파일 문면대로 「상계」를 고르면 엔진은 통과시키지만
`ValueStream.payer_by_structure` 의 어느 키와도 맞지 않아 **그 편익이 기본
`payer` 로 조용히 떨어진다.** 계약 독스트링이 *「오타는 영영 매치되지 않고 기본
payer 로 조용히 떨어집니다」* 라고 경고해 둔 바로 그 상태이며, **실제로 그
상태였다** — 경고는 편익 클래스의 표만 기동 시점에 대조하고 정산엔진의 목록은
보지 않았다.

**정본은 `core.contracts.valuestream.CONTRACT_STRUCTURES` 하나다.** 여덟 번째
구조가 생기면 거기 한 줄이 늘고 이 파일은 바뀌지 않는다 — 그것이 이 저장소가
`payer_by_structure` 를 `if structure == ...` 대신 선언표로 둔 이유와 같다.
사본이 다시 생기는 것은 `tests/contract/test_payer_structure_contract.py` 의
`test_structure_vocabulary_has_exactly_one_owner` 가 막는다.
"""

from __future__ import annotations

from core.contracts.validation import ValidationError
from core.contracts.valuestream import CONTRACT_STRUCTURES
from core.model.schemas import ContractConfig


class SettlementEngine:
    """구조를 받아 정산 결과를 낸다. **지금은 구조 검증만 실질이다.**"""

    def calculate(self, contract: ContractConfig) -> dict[str, float | str]:
        if contract.structure not in CONTRACT_STRUCTURES:
            raise ValidationError(
                field="model.contract.structure",
                reason=(
                    f"지원하지 않는 계약·거래 구조입니다: {contract.structure!r}. "
                    f"spec FR-205-AC1 이 열거한 일곱: {', '.join(CONTRACT_STRUCTURES)}"
                ),
                action=(
                    "열거된 구조 이름을 **문면 그대로** 주십시오. 비슷한 이름은 "
                    "거부되는 편이 낫습니다 — 통과시키면 그 구조가 편익의 "
                    "`payer_by_structure` 어느 키와도 맞지 않아 지불 주체가 "
                    "기본값으로 조용히 떨어집니다"
                ),
            )
        # 임시 정산식 (스텁) — 모듈 독스트링의 경고를 먼저 읽을 것
        return {"structure": contract.structure, "amount": 0.0}
