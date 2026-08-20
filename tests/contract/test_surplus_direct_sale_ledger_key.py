"""「잉여 직거래」 조립기가 **대장의 Q-16 항목과 같은 키**를 쓰는가.

`FR-205-AC1.SurplusDirectSale`.

## 왜 이 파일이 따로 있는가

`tests/casegrid/test_surplus_sale_price_wiring.py::test_the_default_path_prices_the_surplus_like_the_surplus_structure`
는 이미 `core.casegrid.ledger_levels.ledger_backed_variables()` (배포 경로의
케이스 변수 → 대장 키 표) 가 `SURPLUS_SALE_KEY` 와 같은 키를 가리키는지 본다.
**그런데 그 표도 `core/casegrid/ledger_levels.py` 안의 리터럴이다** — 조립기의
상수와 배포 경로의 리터럴이 우연히 같은 문자열을 베껴 적었을 뿐, 어느 쪽도
**대장 원본(`docs/assumptions.yaml`)** 을 직접 보지 않는다. 둘이 함께 틀리면
(예: 두 리터럴을 나란히 오타 낸 채 커밋하면) 그 대조는 초록불인 채로
아무것도 붙들지 못한다.

그래서 이 파일은 **대장 원본**을 다시 읽어 `Q-16`(spec 491행이 인용하는
가정 회신 번호) 항목을 찾고, 그 항목의 `key` 필드가 조립기 상수
`SURPLUS_SALE_KEY` 와 같은 문자열인지 본다. `Q-16` 은 조립기도 배포 경로도
정의하지 않는 **제3의 식별자**이므로, 이 대조는 두 리터럴이 함께 틀리는
경우까지 잡는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from core.valuestream.settlement import SURPLUS_SALE_KEY, TARIFF_KEY

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS_YAML = _REPO_ROOT / "docs" / "assumptions.yaml"


def _q16_entry() -> dict:
    items = yaml.safe_load(_ASSUMPTIONS_YAML.read_text(encoding="utf-8"))["assumptions"]
    entry = next((item for item in items if item.get("q_ref") == "Q-16"), None)
    assert entry is not None, (
        "대장에서 `Q-16` 항목을 찾지 못했습니다 — spec 491행이 인용하는 "
        "회신 번호가 대장에서 사라졌거나 번호가 바뀌었습니다"
    )
    return entry


@pytest.mark.req("FR-205-AC1.SurplusDirectSale", "NFR-202-M1")
def test_the_assembler_constant_matches_the_ledger_s_q16_key() -> None:
    """★★★ 조립기 상수가 **대장 원본의 `Q-16` 키**와 같다.

    `Q-16` 은 조립기도 배포 경로(`ledger_levels.py`)도 정의하지 않는 대장
    쪽 식별자다 — 그것을 기준으로 삼아야 두 리터럴이 함께 틀리는 경우까지
    붙든다. 어긋나면 조립기가 엉뚱한 대장 항목(가령 약관요금)을 «잉여 직거래»
    단가로 읽고 있다는 뜻이다.
    """
    entry = _q16_entry()
    assert entry["key"] == SURPLUS_SALE_KEY, (
        f"조립기 상수 SURPLUS_SALE_KEY={SURPLUS_SALE_KEY!r} 가 대장 Q-16 항목의 "
        f"key({entry['key']!r})와 다릅니다"
    )
    # 약관요금과 다른 항목이어야 한다 — 같으면 「잉여 직거래」가 소매가로
    # 파는 사업이 되고, 그 값은 상계거래가 *회피한 요금*으로 쓰는 것이다.
    assert entry["key"] != TARIFF_KEY, (
        "대장 Q-16 항목이 약관요금과 같은 키를 가리킵니다 — 「잉여 직거래」와 "
        "「상계거래」가 같은 대장 줄에 묶이면 두 구조가 항상 같은 금액을 냅니다"
    )
