"""계약·거래 구조별 정산 — FR-205-AC1.

⚠ **이 파일은 금액을 단언하지 않는다.** 정산 조립 규칙이 아직 정해지지 않아
`SettlementEngine` 이 어느 구조에서도 `0.0` 을 내고, 그 사실은 spec §FR-205
주석이 *「매핑표는 이 조항을 「자동 검증됨」이라 적었다」* 고 이미 지적해 두었다.
**여기서 금액을 단언하는 척하지 않는다** — 근거 없는 기대값을 적으면 다음
라운드가 그것을 오라클로 읽는다.

**R31 이 이 파일에서 고친 것은 구조 어휘다.** 종전에는 `SettlementEngine` 이
자기 목록을 들고 있어 spec 과 셋이 어긋났고, 이 테스트가 **그 어긋난 목록을
그대로 베껴** 초록불을 내고 있었다 — 「조항의 반대를 고정한 테스트」의 형태다.
"""

from __future__ import annotations

import pytest

from core.contracts.validation import ValidationError
from core.contracts.valuestream import CONTRACT_STRUCTURES
from core.model.schemas import ContractConfig
from core.model.settlement import SettlementEngine


@pytest.mark.req("FR-205-AC1")
def test_every_structure_the_contract_declares_is_accepted() -> None:
    """계약이 선언한 일곱을 **전건** 받는다 — 목록을 여기 베끼지 않는다.

    구조 이름을 이 파일에 적으면 정본이 둘이 되고, 그때 한쪽만 고쳐진 상태가
    초록불이 된다. 실제로 그랬다(R31 이 찾았다).
    """
    engine = SettlementEngine()

    for structure in CONTRACT_STRUCTURES:
        result = engine.calculate(ContractConfig(structure=structure))
        assert result["structure"] == structure

    assert len(CONTRACT_STRUCTURES) == 7


@pytest.mark.req("FR-205-AC1")
def test_the_old_vocabulary_is_refused() -> None:
    """종전에 이 엔진이 받던 셋은 **이제 거부된다.**

    ★ 이 단언이 없으면 목록을 다시 넓혀도 아무것도 빨간불이 되지 않는다.
    받아 주면 그 구조는 `payer_by_structure` 의 어느 키와도 맞지 않아 편익의
    지불 주체가 기본값으로 조용히 떨어진다 — 계약이 경고해 둔 그 상태다.
    """
    engine = SettlementEngine()

    for stale in ("개별 직접계약", "단일계약+관리주체", "상계"):
        assert stale not in CONTRACT_STRUCTURES
        with pytest.raises(ValidationError) as caught:
            engine.calculate(ContractConfig(structure=stale))
        # NFR-303 3요소 — 사유가 열거된 일곱을 실어 「무엇을 고르라」를 말한다
        assert caught.value.field == "model.contract.structure"
        assert "상계거래" in caught.value.reason
        assert caught.value.action.strip()
