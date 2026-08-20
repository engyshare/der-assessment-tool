"""리포트 검사가 함께 쓰는 **탐침 대장** — 전환 인자가 존재하는 대장 한 벌.

## 왜 이것이 필요해졌는가 (R34)

계통 전력 구매 비용이 배선되기 전까지 골든 세 시나리오는 **전환 인자를 하나씩
갖고 있었다**(할인율 3.44% 에서 뒤집힌다 등). 그래서 임계값 탐색을 보는 검사들이
실물 대장으로 그냥 돌 수 있었다. 구매 비용이 들어오며 순현재가치가 −5,284,586원
(무보조)으로 내려가고, **대장 `sensitivity` 범위 안에서 결론을 뒤집는 인자가
하나도 없어졌다.**

그 상태 자체는 리포트가 정직하게 싣는다(5.1 「단독 전환 인자 — 없음」 · 붙임 2 의
`전환` 열 전건 `—`). **문제는 검사 쪽이다** — 전환 인자가 없으면

    assert plain_flips != subsidised_flips     # set() != set() → 빨간불
    for entry in flipping: ...                 # 순회가 0회 → 조용한 초록불

이 되어, 하나는 정당한 상태를 빨간불로 만들고 다른 하나는 **검사가 아무것도
보지 않은 채 통과**한다. 뒤쪽이 이 저장소가 반복해서 경계해 온 형태다(R33 의
`_find_flip_threshold` 허용오차 결함은 **전환 인자가 있었기 때문에** 잡혔다).

## 무엇을 바꾸는가 — **한 항목의 검토 범위 하나뿐**

구매 단가의 `sensitivity.high` 만 넓힌다. 값(`value`)·기준값·다른 항목은 건드리지
않으므로 **기준선 수치는 실물과 같고**, 달라지는 것은 *「이 인자를 어디까지
흔들어 보는가」* 다. 즉 탐침은 사업을 바꾸지 않고 **스윕 구간만** 넓힌다.

⚠ **골든 산출물에는 쓰지 않는다.** 이 대장으로 리포트를 뽑으면 실물과 다른
범위가 실린다 — 탐침은 *탐색 기계가 도는가*를 보는 자리에만 쓴다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from core.casegrid.profiles import DailyShapes, load_daily_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"


def report_shapes() -> DailyShapes:
    """리포트가 **결론에** 쓰는 대표일 형상 — 진입점을 다시 돌리는 검사가 쓴다.

    ## 왜 검사 쪽이 자산을 직접 읽는가 (R37)

    R37 이 일사 곡선을 `build_case_report` 의 본 실행·스윕에 배선했다. 그래서
    *「보고된 값으로 다시 돌려 본다」* 형태의 검사들(R33·R35 가 세운 것)은 **같은
    배선으로** 돌려야 한다 — 형상 없이 돌리면 리포트의 수를 **다른 사업**의 0 선에
    대고 재게 되고, 그때 옳은 리포트가 빨간불이 된다.

    ⚠ **`case_report` 에게 「무엇을 넘겼는지」 묻지 않는다.** 물어 오면 배선을
    지우는 변이가 검사를 따라와 *「리포트는 자기가 넘긴 것을 넘겼다」* 만 확인하는
    동어반복이 된다(status.md 「검사가 자기 검사 대상에서 정본을 읽어 오면 공허해
    진다」). 검사는 **자산**(`fixtures/profiles/representative-day.yaml`)을 직접
    읽고, 두 자리가 같은 값을 뜻한다는 사실 자체가 검사가 된다.
    """
    return load_daily_shapes()


#: (대장 키, 수준 이름, 넓힌 값). **탐침값이지 전망이 아니다.**
#:
#: 셋을 넓히는 이유는 **살려야 하는 갈래가 둘**이기 때문이다.
#:
#:   구매 단가 상단 400  → *전환* 갈래. 보조 80% 의 결론을 0 선 아래로 끌어내려
#:                        임계값 탐색이 실제로 돌게 한다(실물 상단 170 으로는
#:                        어느 인자도 +2,555,414원을 뒤집지 못한다)
#:   설비단가 하단 둘    → *회수* 갈래. 무보조의 **동반 하락**이 0 선을 넘게
#:                        한다(실물 범위에서 동반 하락은 −3,324,586원이며
#:                        회수하지 못한다). 단독으로는 여전히 넘지 못하므로
#:                        「결합에서만 회수된다」는 대조가 유지된다
_WIDENED: tuple[tuple[str, str, float], ...] = (
    ("tariff.hv_single_contract.energy_only", "high", 400.0),
    ("capex.pv.rooftop", "low", 800_000.0),
    ("capex.ess.new", "low", 200_000.0),
)


@pytest.fixture
def flip_probe_assumptions(tmp_path: Path) -> Path:
    """전환 인자가 **존재하는** 대장 사본의 경로.

    실물 대장을 읽어 한 항목의 `sensitivity.high` 만 바꿔 쓴다. 손으로 적은
    사본을 두지 않는 이유는 그것이 대장의 둘째 정본이 되기 때문이다 — 대장이
    바뀌어도 사본은 조용히 옛 값을 들고 있다.
    """
    data = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    by_key = {item.get("key"): item for item in data["assumptions"]}
    for key, level, value in _WIDENED:
        item = by_key.get(key)
        # 대장에서 항목이 사라지면 **즉시** 알아야 한다 — 조용히 넘기면 탐침이
        # 실물과 같아지고, 그 순간 이 탐침을 쓰는 검사들이 0회 순회로 통과한다.
        assert item is not None, (
            f"대장에 {key} 가 없다 — 탐침이 넓힐 범위를 찾지 못했다"
        )
        item["sensitivity"][level] = value
    path = tmp_path / "assumptions-flip-probe.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path
