"""제도 프로파일을 케이스 그리드의 **탐색 축**으로 놓는다 — `FR-504-AC8`.

조항은 *「복수 프로파일을 케이스 그리드의 탐색 변수로 지정하여 **한 번의
실행으로** 제도 시나리오를 비교할 수 있다」* 이다. 두 층이고, 둘 다 있어야
충족이다 —

    ① 프로파일이 그리드의 **축**이 된다 (케이스 수가 프로파일 수만큼 늘어난다)
    ② **한 번의 `generate()`** 가 모든 프로파일 케이스를 함께 낸다

**왜 이 파일이 `core/regulation/` 이 아니라 여기에 있는가.** `.importlinter`
의 `layers` 계약이 `core.casegrid` 를 `core.regulation` **위**에 둔다. 그래서
제도 구획은 그리드 타입(`CaseVariable`)을 알 수 없고, 알게 하면 역방향
import 가 되어 `lint-imports` 가 막는다. 축을 만드는 쪽이 위층인 것이 옳다 —
그리드는 제도를 알아도 되지만 제도는 그리드를 몰라야 한다.

그래서 제도 구획은 **축의 재료**(`ProfileCaseVariable` — 이름과 (이름, 버전)
목록)만 내고, 그것을 그리드가 쓰는 형태로 바꾸는 일이 여기서 일어난다.

> **이 변환이 없으면 조항이 닫히지 않는다.** R20 에 제도 구획이
> `ProfileCaseVariable` 을 만들었는데 그것을 **아무도 소비하지 않았다** —
> `CaseVariable` 과 평행한 별개 타입이라 그리드가 볼 수 없었고, 그러면
> 「축을 만들 수 있다」이지 「축이 된다」가 아니다. 심볼이 있는 것과 조항이
> 충족된 것은 다르다.
"""

from __future__ import annotations

from core.casegrid.models import CaseVariable
from core.regulation.profile import ProfileCaseVariable

#: 이 축의 값이 «제도 프로파일 식별자» 임을 소비 쪽에 알리는 표식.
#: 기본값 `"scalar"` 로 두면 값이 `(이름, 버전)` 튜플인데도 스칼라로 읽힌다.
PROFILE_TARGET = "regulation_profile"

__all__ = ("PROFILE_TARGET", "profile_axis")


def profile_axis(axis: ProfileCaseVariable) -> CaseVariable:
    """제도 구획이 낸 축 재료를 그리드가 소비하는 `CaseVariable` 로 바꾼다.

    값은 `(프로파일 이름, 버전)` 튜플이다. 이름만 실으면 **같은 이름의 다른
    개정판**이 한 값으로 뭉개지는데, 제도 비교는 정확히 그 둘을 가르는 일이다
    (`FR-504-AC4` 가 프로파일에 버전을 두는 이유와 같다).
    """
    return CaseVariable(
        name=axis.name,
        values=axis.values,
        target=PROFILE_TARGET,
        label=f"제도 프로파일 ({len(axis.values)}종)",
    )
