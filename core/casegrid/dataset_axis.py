"""시계열 데이터셋을 케이스 그리드의 **탐색 축**으로 놓는다 — `FR-905-AC5`.

조항은 *「**데이터셋 자체를 케이스 그리드의 탐색 변수로 지정**하여 여러
연도·지역 시계열을 **한 번에** 비교할 수 있다 (FR-801)」* 이다.

**`regulation_axis.py` 와 같은 형태의 두 번째 인스턴스다.** 두 조항
(`FR-504-AC8` 제도 프로파일 · `FR-905-AC5` 시계열)이 같은 말을 한다 —
*「하위 구획이 가진 목록을 그리드 축으로 지정한다」*. 그리고 둘 다 같은
자리에서 끊겨 있었다: 하위 구획이 **축의 재료**를 만들었는데 그것을 그리드가
소비하는 `CaseVariable` 로 바꾸는 일을 아무도 하지 않았다.

**왜 하위 구획이 직접 못 만드는가.** `.importlinter` 의 `layers` 가
`core.casegrid` 를 `core.assumption`·`core.regulation` **위**에 둔다. 하위가
`CaseVariable` 을 알면 역방향 import 이고 `lint-imports` 가 막는다. 그래서
변환은 반드시 위층에서 일어난다 — 그리드는 전제를 알아도 되지만 전제는
그리드를 몰라야 한다.

> **새 축 종류를 더하는 방법**: 이 파일과 같은 모양의 모듈을 하나 놓는다.
> 하위 구획이 `(이름, 값 목록)` 을 내고, 여기서 `target` 표식을 달아
> `CaseVariable` 로 바꾼다. 그리드 자체는 고치지 않는다.
"""

from __future__ import annotations

from core.assumption.timeseries_explore import TimeSeriesExploreAxis
from core.casegrid.models import CaseVariable

#: 이 축의 값이 «시계열 데이터셋 id» 임을 소비 쪽에 알리는 표식.
DATASET_TARGET = "timeseries_dataset"

__all__ = ("DATASET_TARGET", "dataset_axis")


def dataset_axis(axis: TimeSeriesExploreAxis) -> CaseVariable:
    """전제 구획이 낸 축 재료를 그리드가 소비하는 `CaseVariable` 로 바꾼다.

    값은 **데이터셋 id** 다. 데이터셋 본문(8760개 실수)을 케이스 값으로 실으면
    케이스 하나마다 시계열 전체가 복사되고, `Case.values` 는 실행 매니페스트로
    그대로 흘러간다 — id 만 실어 두면 소비 쪽이 필요할 때 레지스트리에서 찾는다
    (`FR-905-AC7` 이 «중복 저장하지 않는다» 고 적는 것과 같은 이유다).
    """
    return CaseVariable(
        name=axis.tag,
        values=axis.dataset_ids(),
        target=DATASET_TARGET,
        label=f"시계열 데이터셋 ({len(axis.datasets)}종)",
    )
