"""전제 대장을 코드가 읽는 경계 — 계약 개정 v1.2 / spec FR-601 · NFR-202.

**왜 계약이 이것을 갖는가.** `docs/assumptions.yaml` 은 08-08에 세워졌으나
**아무도 읽지 않는다.** `tax.vat_rate` 는 대장에 있고 자원의 `vat_rate`
기본값은 `0.0` 이며, 그 `0.0` 은 「세율 0%」가 아니라 **「주입되지 않음」**
이다. 둘은 프로포마에서 구별되지 않는다 — 세액 행이 0원으로 나오고,
그것이 «면세 설비» 인지 «주입을 잊었는지» 는 결과만으로 알 수 없다.

v1.1 에서 정확히 같은 형태를 이미 한 번 만났다. ESS 하나가 `capex_vat()`
를 아예 만들지 않아 **세액이 통째로 사라져 있었고, 어느 검사도 걸리지
않았다.** 그때의 해법은 「잊으면 인스턴스화가 실패하게 둔다」였다. 이번
것은 한 단계 위에서 같은 일이 일어난다 — 메서드는 있고 **값이 없다.**

**계약이 정하는 것은 「누가 값을 읽는가」뿐이다.** 대장의 형식(yaml 스키마)
도, 주입 시점(모델 구성)도 여기서 정하지 않는다. 전자는 WP-2
(`core/assumption/`)가, 후자는 WP-16(`core/model/`)이 소유한다. 계약이
가진 것은 **읽기 인터페이스 하나**이며, 그것이 있어야 WP-3(요금)·WP-7(CBA)
같은 소비 구획이 WP-2의 완성을 기다리지 않고 스텁으로 진행할 수 있다
(§16.1 W-6).

**형제 구획 격리와의 관계.** `.importlinter` 의 `siblings-isolated` 는
`core.regulation` 과 `core.assumption` 의 직접 import 를 금지한다
(NFR-208-AC2). 요금 엔진이 전제값을 읽으려면 **여기를 경유하는 수밖에
없고, 그것이 의도한 바다.**
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Literal

from core.contracts.schemas import AssumptionRef

#: 근거 표기 기준 2절 축 2. `미확인` 은 축 1 전용이므로 여기 없다 —
#: 같은 토큰을 두 축에 쓰면 어느 뜻인지 판정할 수 없다 (spec v0.5 어휘 정정).
Confidence = Literal["확정", "추정", "가정"]


class MissingAssumption(LookupError):
    """요구한 전제가 대장에 없다.

    **기본값으로 메우지 않는다.** 메우는 순간 「대장에 없다」가 「대장에
    0이 있다」와 구별되지 않고, 그 상태는 결과가 그럴듯해서 스스로
    드러나지 않는다. 없으면 멈추는 것이 유일하게 안전한 처리다.
    """

    def __init__(self, key: str, *, set_name: str = "", set_version: str = "") -> None:
        where = f" ({set_name} {set_version})".rstrip() if set_name else ""
        super().__init__(
            f"전제 `{key}` 가 대장{where} 에 없습니다. "
            "기본값으로 대체하지 마십시오 — 「없음」을 「0」으로 바꾸면 "
            "비용이 사라지거나 편익이 생기고, 어느 쪽도 오류로 보이지 "
            "않습니다. 값이 필요하면 docs/assumptions.yaml 에 등재하십시오 "
            "(NFR-202 — 소스에 리터럴로 적으면 lint 가 잡습니다)"
        )
        self.key = key


@dataclass(frozen=True)
class AssumptionValue:
    """대장 항목 1건 — 값과 **부기 7종**을 함께 나른다 (FR-601-AC5).

    **값만 돌려주지 않는 이유.** 값만 넘기면 리포트가 *"그 값이 어디서
    왔는가"* 에 답할 수 없다. FR-1001은 산식과 출처 표시를, FR-1002는
    영향도 순위와 함께 신뢰도 표시를 요구하며 **둘 다 부기 없이는
    성립하지 않는다.** 소비 구획이 값을 꺼낸 뒤 출처를 따로 찾아 붙이는
    구조라면 반드시 빠지고, 빠진 자리는 «출처 미상» 이 아니라 그냥
    빈칸으로 나타난다.

    부기 7종은 [[근거 표기 기준]] 이 정본이며 여기서 재정의하지 않는다.
    이 클래스는 그 7종을 **자리로 고정**할 뿐이다.
    """

    key: str
    #: 값. 스칼라형은 수치, 참조형은 다른 항목의 key (FR-601-AC6)
    value: float | int | str
    # ── 부기 7종 (FR-601-AC5) ────────────────────────────────────────
    value_unit: str
    base_year: str
    applicable_scope: str
    derivation_method: str
    source: str
    verified_at: date | None
    confidence: Confidence
    #: **이용조건 — 부기 7종이 아니다** (v1.2 후속, `SC-7`).
    #:
    #: `SC-7` 은 *"외부 데이터의 **출처·이용조건** 보관"* 을 요구한다. 부기 7종의
    #: `source` 가 출처를 담당하고 이 칸이 이용조건(라이선스·재배포 조건·출처
    #: 표기 의무)을 담당한다. **7종에 넣지 않은 이유**는 그 목록의 정본이
    #: [[근거 표기 기준]] 이고 우리가 그것을 바꿀 수 없기 때문이다.
    #:
    #: **경계까지 나르는 이유.** R1 점검이 *"마커는 있으나 이용조건은 아직
    #: 어디에도 없다"* 를 잡았다 — 매핑표는 초록불인데 조항은 검증되지 않은
    #: 상태였다. 대장과 구획 내부 자료구조에만 두면 **리포트가 이용조건을
    #: 표시할 수 없고**, 표시할 수 없는 보관은 「보관했다」의 증거가 되지
    #: 않는다. 공개 단가표에는 재배포 금지·출처 표기 의무가 실제로 붙는다.
    #:
    #: `None` 은 「제약 없음」이 아니라 **「확인하지 않음」**이다. 제약이 없으면
    #: 그렇게 적는다 — 빈 칸은 두 상태를 구별하지 못한다.
    usage_terms: str | None = None
    # ── 출처 추적 ────────────────────────────────────────────────────
    set_name: str = ""
    set_version: str = ""

    def as_ref(self) -> AssumptionRef:
        """경계를 넘는 참조로 축약한다.

        `AssumptionValue` 자체를 경계로 넘기지 않는 이유: 부기 본문은
        길고 프로포마 한 행에 수십 건이 붙는다. 경계에는 **어디서
        왔는지** 만 실리면 되고, 본문은 리포트가 다시 조회한다.
        """
        return AssumptionRef(
            set_name=self.set_name,
            set_version=self.set_version,
            key=self.key,
            confidence=self.confidence,
            source=self.source or None,
            verified_at=self.verified_at,
        )

    def as_float(self) -> float:
        """수치 값. 참조형·문자열이면 멈춘다.

        `float("0.1")` 로 조용히 통과시키지 않는다 — 참조형 항목의 key
        문자열이 숫자로 해석되는 일은 없지만, **그 경계를 무르게 두면
        다음 사람이 단위 문자열을 값 자리에 넣는다.**
        """
        if isinstance(self.value, str):
            raise TypeError(
                f"전제 `{self.key}` 의 값이 문자열입니다: {self.value!r}. "
                "참조형 항목이라면 먼저 해석한 뒤에 수치를 꺼내십시오 "
                "(FR-601-AC6)"
            )
        return float(self.value)


class AssumptionProvider(ABC):
    """전제 대장 읽기 인터페이스 — **코드가 대장을 읽는 유일한 경로**.

    구현은 WP-2(`core/assumption/`)가 소유한다. 소비 구획(WP-3 요금,
    WP-7 CBA, WP-8 지원)은 **이 추상에만 의존**하므로 WP-2의 완성을
    기다리지 않고 스텁으로 자기 검증을 완료할 수 있다 (§16.1 W-6).

    **쓰기 메서드가 없는 것은 누락이 아니다.** 오버라이드·버전·diff
    (FR-601-AC8, FR-602)는 전제 구획의 내부 관심사이며, 계산 구획이
    전제를 고칠 수 있으면 *"어느 값으로 계산했는가"* 가 실행 도중에
    바뀐다. 그러면 실행 매니페스트 재현(FR-1005-AC1)이 성립하지 않는다.
    """

    @property
    @abstractmethod
    def set_name(self) -> str:
        """전제 집합 이름 — 리포트·매니페스트에 그대로 기록된다."""

    @property
    @abstractmethod
    def set_version(self) -> str:
        """전제 집합 판. **같은 이름의 다른 판은 다른 결과를 낳는다.**"""

    @abstractmethod
    def get(self, key: str) -> AssumptionValue | None:
        """없으면 `None`.

        「없음」과 「0」을 호출부가 **구별해야 하는** 자리에서만 쓴다.
        대부분의 자리에서는 `require()` 가 맞다 — 구별할 생각이 없으면서
        `get()` 을 쓰면 `or 0.0` 이 따라붙고, 그 순간 대장의 결손이
        계산 결과에 0으로 스며든다.
        """

    def require(self, key: str) -> AssumptionValue:
        """없으면 `MissingAssumption` 으로 멈춘다.

        **기본 구현을 주는 이유.** `get()` 하나만 추상으로 두면 구현체가
        `require()` 를 각자 짓고, v1.1 에서 여섯 자원이 `capex_vat()` 를
        각자 지어낸 것과 같은 일이 일어난다. 「없을 때 무엇을 하는가」는
        구현이 정할 문제가 아니라 계약이 정할 문제다.
        """
        value = self.get(key)
        if value is None:
            raise MissingAssumption(
                key, set_name=self.set_name, set_version=self.set_version
            )
        return value

    def require_float(self, key: str) -> float:
        """수치 전제를 꺼내는 통로. 없거나 문자열이면 멈춘다."""
        return self.require(key).as_float()
