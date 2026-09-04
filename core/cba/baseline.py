"""기준선 증분 분석 — 작업 10.5 / FR-705-AC1.

모든 편익은 «설비 미설치 기준선» 대비 **증분** 이다 (도메인 원칙 1-1·1-2).
기준선 자체 비용도 리포트에 **명시적으로 표시** 해야 한다 (FR-705-AC1).

기준선이 «아무것도 하지 않음» 이 아니라 «현실적 대안» 이라는 점이 핵심이다
(원칙 1-3). 히트펌프의 기준선은 «난방 안 함» 이 아니라 «기존 보일러 유지».
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from core.cba.proforma import aggregate
from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO, Money
from core.contracts.validation import ValidationError


class BaselineArrangement(StrEnum):
    """기준선(Without) 갈래 셋 (FR-705-AC2)."""

    NONE = "자가용 없음"  # Without: 한전 전력 전량
    MAINTAIN = "자가용 유지"  # Without: 한전 전력 + 자가용 자가소비
    POOL = "자가용 집합자원화"  # Without: 자가용 유지(=가 또는 현행)


class SelfConsumptionTreatment(StrEnum):
    """자가소비 처리 방식 (FR-705-AC2)."""

    NONE = "없음"  # 자가용이 없어 자가소비가 애초에 없다
    CANCEL_OUT = "소거"  # Without·With 양쪽에 똑같이 있어 차액에서 사라진다
    FORFEIT = "포기(음의 항)"  # With 에서 사라지므로 비용으로 계상해야 한다


@dataclass(frozen=True)
class BaselineBranch:
    """갈래별 기준선 및 자가소비 처리 선언."""

    without_description: str
    with_description: str
    viability_condition: str
    self_consumption_treatment: SelfConsumptionTreatment
    clause: str


#: 갈래별 선언표.
#: if structure == ... 로 짜지 않는다. 선언표로 두면 여덟 번째 구조가 생겨도
#: 이 계약과 엔진은 바뀌지 않는다.
BASELINE_DECLARATIONS: Mapping[BaselineArrangement, BaselineBranch] = MappingProxyType(
    {
        BaselineArrangement.NONE: BaselineBranch(
            without_description="한전 전력 전량",
            with_description="분산e사업자 공급",
            viability_condition="",
            self_consumption_treatment=SelfConsumptionTreatment.NONE,
            clause="예비타당성조사 수행 총괄지침 제45조② · 판정 정본 §1 첫째",
        ),
        BaselineArrangement.MAINTAIN: BaselineBranch(
            without_description="한전 전력 + 자가용 자가소비",
            with_description="분산e 공급 + 자가용 자가소비",
            viability_condition="분산e 요금 < 한전 요금",
            self_consumption_treatment=SelfConsumptionTreatment.CANCEL_OUT,
            clause="예비타당성조사 수행 총괄지침 제45조② · 판정 정본 §1 둘째",
        ),
        BaselineArrangement.POOL: BaselineBranch(
            without_description="자가용 유지",
            with_description="분산e 로부터 공급 + 집합자원화 대가",
            viability_condition="전기사용자에게 자가용 유지보다 유리",
            self_consumption_treatment=SelfConsumptionTreatment.FORFEIT,
            clause="예비타당성조사 수행 총괄지침 제45조② · 판정 정본 §1 셋째",
        ),
    }
)


#: 갈래를 **적지 않은 평가**가 도는 갈래 — ⓑ「자가용 유지」(`MAINTAIN`).
#:
#: ★★ **근거는 사용자 판정이다** (`docs/decisions-2026-09-04-R59b.md` §1 —
#: *「자가태양광과 히트펌프가 있는 가구를 대상으로 프로그램이 기획되었음.
#: 따라서 ⓑ에 가까움」*). 대상 가구가 자가용 설비를 **이미 갖고 있으므로**
#: 기준선(Without)의 기본 자리가 *「자가용을 유지한 상태」* 다.
#:
#: ⚠⚠ **여기가 이 값을 정하는 유일한 자리다.** 러너와 리포트가 각자 리터럴을
#: 두면 한쪽만 고쳐지고, 그때 「필드를 안 적은 실행」이 층마다 다른 갈래로
#: 돌면서 **아무 예외도 나지 않는다.** 두 층은 아래 `resolve_baseline_arrangement`
#: 를 지나며 그 함수만 이 상수를 읽는다.
#:
#: ⚠ **기본값을 두는 것 자체가 판정이다** — 판정 정본이 그렇게 적는다
#: (*「기본값을 두면 그 기본값으로 결론축이 움직인다」*). 이 값이 고른 갈래의
#: 자가소비 처리(`CANCEL_OUT` — 양쪽에 있어 소거)가 **현행 러너 동작과 같으므로**
#: 이 배선은 결론축을 움직이지 않는다. 다른 갈래를 기본으로 두는 날에는 움직인다.
DEFAULT_BASELINE_ARRANGEMENT: Final = BaselineArrangement.MAINTAIN


def resolve_baseline_arrangement(
    value: BaselineArrangement | str | None,
) -> BaselineArrangement:
    """적힌 문면 → 갈래. **적히지 않았으면** `DEFAULT_BASELINE_ARRANGEMENT`.

    시나리오 yaml 의 `baseline_arrangement` 필드가 이 함수의 입력이며, 값은
    `BaselineArrangement` 의 **문면 그대로**다(`자가용 없음` · `자가용 유지` ·
    `자가용 집합자원화`).

    ⚠⚠ **모르는 문면을 조용히 기본값으로 떨어뜨리지 않는다.** 오타가
    *「ⓑ 로 돌았다」* 로 통과하면 그 평가는 **적은 것과 다른 기준선** 위에
    서고, 산출물의 어디에도 그 어긋남이 드러나지 않는다 — 이 저장소가
    반복해 잡아 온 형태다.

    ⚠ `rule` 을 비운다 — 갈래 문면 오타는 §7.3 대장 밖의 일반 입력 검증이다.
    대장에 있는 `DV-15` 는 *「자리가 다 서지 않은 갈래를 고를 수 없다」* 이며
    (`get_baseline_branch` 가 던진다) 이것과 다른 규칙이다. 없는 ID 를 달면
    추적표가 그 규칙을 검증된 것으로 센다(`ValidationError` 독스트링).
    """
    if value is None:
        return DEFAULT_BASELINE_ARRANGEMENT
    if isinstance(value, BaselineArrangement):
        return value
    try:
        return BaselineArrangement(value)
    except ValueError:
        raise ValidationError(
            field="baseline.arrangement",
            reason=f"기준선 갈래로 모르는 문면이 왔습니다: {value!r}",
            action=(
                "다음 중 하나를 적으십시오 — "
                + " · ".join(f"「{e.value}」" for e in BaselineArrangement)
                + f". 필드를 비우면 「{DEFAULT_BASELINE_ARRANGEMENT.value}」로 "
                "돕니다"
            ),
        ) from None


#: ⓒ「자가용 집합자원화」의 성립 전제 **둘**. 판정 정본
#: `docs/decisions-2026-09-03-R57.md` **§2** 가 그 둘을 적는다 — *「분산에너지
#: 사업자가 자가용 태양광 설비의 **소유 또는 운영권**을 전기사용자로부터
#: 인계받고, **발전량, 전기사용량**을 명확하게 구분할 수 있는 형태로 계측,
#: 정산되야함」*.
#:
#: ⚠ **문면을 상수로 두는 이유** — 거부 메시지와 검사가 **같은 문자열**을 봐야
#: *「어느 쪽이 빠졌는가」* 를 기계가 대조할 수 있다. 양쪽에 베끼면 문면을
#: 다듬는 날 검사가 따라오지 않아도 아무 일이 없다
#: (`tests/cba/test_pool_metering_declaration.py` 가 이 이름들을 읽는다).
POOL_PREREQUISITE_TRANSFER: Final = "자가용 설비의 소유 또는 운영권 인계"
POOL_PREREQUISITE_METERING: Final = "발전량·전기사용량의 구분 계측·정산"

#: 선언이 들어오는 **시나리오 yaml 필드 이름**. 통로는 이 하나다 — 환경변수·
#: CLI 플래그를 따로 세우지 않는다(통로가 둘이면 어느 것이 이겼는지 산출물에서
#: 알 수 없다 · R60/WP-2 가 갈래 선택에서 내린 것과 같은 판단).
POOL_METERING_FIELD: Final = "pool_metering"


@dataclass(frozen=True)
class PoolMeteringDeclaration:
    """ⓒ 의 계측 전제 **선언** — 둘을 함께 받는다 (`FR-705-AC2` · `DV-15`).

    ## ★★★ 기본값이 「갈리지 않았다」인 것이 이 자료형의 본체다

    사용자 판정 `docs/decisions-2026-09-04-R59b.md` §1 4항이 *「ⓒ 경로는
    「계측이 갈렸다」를 **입력으로 요구해야 한다**(가정하지 말고 물어라)」* 로
    못 박는다. 소유·운영권이 누구에게 있고 계량이 어떻게 갈리는지는 **자료가
    아니라 사업 설계**이며(같은 §1 의 ⚠ 마지막 항) 저장소가 채울 수 없다.

    ⚠⚠ **기본값을 `True` 로 두면** 선언을 만들기만 하고 필드를 안 적은 호출이
    ⓒ 를 열어 버린다 — 그때 나오는 수는 **없는 전제를 있다고 가정한 수**이고
    그 실수는 아무 예외도 내지 않는다. 그래서 안전한 쪽이 **거부**다.

    ⚠ **둘을 한 자료형에 담는 이유** — 둘은 함께 서야 성립하는 한 조건이고
    (하나만 참이면 ⓒ 는 여전히 거부된다), 인자 둘로 나르면 호출부마다 하나를
    빠뜨릴 자리가 생긴다. 「무엇이 빠졌는가」를 아는 것도 이 자료형이다
    (`missing()`).
    """

    #: ① 분산e사업자가 자가용 설비의 **소유 또는 운영권**을 인계받았다.
    ownership_or_operation_transferred: bool = False
    #: ② **발전량과 전기사용량**을 명확히 구분할 수 있는 형태로 계측·정산한다.
    metering_separated: bool = False

    def missing(self) -> tuple[str, ...]:
        """아직 서지 않은 전제의 이름 — **빈 튜플이면 둘 다 섰다.**

        ⚠ 거부 문면이 이것을 그대로 인용한다. 「둘 다 있어야 한다」를 되풀이하는
        문면은 **이미 확보한 전제를 다시 확보하라고 말하는** 셈이고, 그때 사업
        설계자에게 남는 선택은 「전부 다시 확인」또는 「그냥 참으로 두기」다.
        """
        return tuple(
            name
            for declared, name in (
                (
                    self.ownership_or_operation_transferred,
                    POOL_PREREQUISITE_TRANSFER,
                ),
                (self.metering_separated, POOL_PREREQUISITE_METERING),
            )
            if not declared
        )


#: 선언에 적을 수 있는 필드 — **자료형에서 읽는다.** 손으로 적으면 필드를
#: 늘리는 날 목록이 따라오지 않아 새 필드가 「모르는 이름」으로 거부된다.
_POOL_METERING_FIELDS: Final = tuple(f.name for f in fields(PoolMeteringDeclaration))

#: 선언 오류의 `field` 키. 관례는 `<도메인>.<필드>` 다(`ValidationError` 독스트링의
#: 「`field` 경로 관례」) — 자유 문자열이 섞이면 표시 층이 키로 찾을 수 없다.
_POOL_METERING_ERROR_FIELD: Final = f"baseline.{POOL_METERING_FIELD}"

#: 선언 문면이 틀렸을 때의 **조치** — 적을 수 있는 필드와 예시를 함께 낸다
#: (NFR-303: 어떤 필드가 / 왜 / **어떻게 고쳐야 하는지**).
_POOL_METERING_ACTION: Final = (
    "적을 수 있는 필드는 "
    + " · ".join(f"`{name}`" for name in _POOL_METERING_FIELDS)
    + " 둘이고 값은 참·거짓입니다. 예 — "
    + POOL_METERING_FIELD
    + ": {"
    + ", ".join(f"{name}: true" for name in _POOL_METERING_FIELDS)
    + "}. 필드를 아예 적지 않으면 「갈리지 않았다」이며 "
    + f"「{BaselineArrangement.POOL.value}」 갈래는 거부됩니다"
)


def resolve_pool_metering(value: object) -> PoolMeteringDeclaration | None:
    """시나리오 yaml 의 `pool_metering` → 선언. **적지 않았으면 `None`** 이다.

    ⚠ **`None` 을 빈 선언으로 바꿔 내지 않는다.** 「적지 않았다」와 「둘 다
    아니라고 적었다」는 다른 진술이고, 둘을 합치면 *선언을 요구했다는 사실*이
    산출물에서 사라진다(둘 다 거부되므로 결과는 같지만 뜻이 다르다).

    ⚠⚠ **모르는 필드·참거짓이 아닌 값을 조용히 무시하지 않는다.** 오타
    (`metering`)가 *「선언이 없어서 거부됐다」* 로 통과하면 사업 설계자는
    **적었는데 왜 거부되나**를 알 수 없고, 그 상태에서 남는 선택은 필드
    이름을 하나씩 바꿔 보는 것이다 — `resolve_baseline_arrangement` 가 갈래
    문면에서 이미 같은 판단을 했다.

    ⚠ `rule` 을 비운다 — 선언 **문면 오타**는 §7.3 대장 밖의 일반 입력
    검증이다. 대장의 `DV-15` 는 *「자리가 다 서지 않은 갈래를 고를 수 없다」*
    (`get_baseline_branch` 가 던진다)로 다른 규칙이며, 없는 ID 를 달면
    추적표가 그 규칙을 검증된 것으로 센다.
    """
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValidationError(
            field=_POOL_METERING_ERROR_FIELD,
            reason=(
                f"「{POOL_METERING_FIELD}」 는 필드 둘을 가진 매핑이어야 하는데 "
                f"{value!r} 가 왔습니다"
            ),
            action=_POOL_METERING_ACTION,
        )
    unknown = tuple(str(key) for key in value if key not in _POOL_METERING_FIELDS)
    if unknown:
        raise ValidationError(
            field=_POOL_METERING_ERROR_FIELD,
            reason=(
                f"「{POOL_METERING_FIELD}」 에 모르는 필드가 있습니다: {unknown}"
            ),
            action=_POOL_METERING_ACTION,
        )
    not_boolean = tuple(
        f"{key}={item!r}" for key, item in value.items() if not isinstance(item, bool)
    )
    if not_boolean:
        raise ValidationError(
            field=_POOL_METERING_ERROR_FIELD,
            reason=(
                f"「{POOL_METERING_FIELD}」 의 값은 참·거짓이어야 합니다: "
                f"{not_boolean}"
            ),
            action=_POOL_METERING_ACTION,
        )
    return PoolMeteringDeclaration(**{str(k): bool(v) for k, v in value.items()})


def get_baseline_branch(
    arrangement: BaselineArrangement,
    *,
    pool_metering: PoolMeteringDeclaration | None = None,
) -> BaselineBranch:
    """갈래 선언을 찾고, **전제가 서지 않은 갈래를 거부한다** (FR-705-AC2 · DV-15).

    ## ★★ 「나」의 거부 사유는 **둘이었고 성격이 달랐다**

    R58~R60/WP-2 동안 이 함수는 ⓒ 를 무조건 거부하며 사유 둘을 한 덩어리로
    적었다:

        ① 계측 전제가 안 섰다 — 상계처리로는 전기사용자의 전력사용량이
           구분되지 않아 **책임공급비율의 분모가 서지 않는다**
           (판정 정본 `docs/decisions-2026-09-03-R57.md` **§2**)
        ② 대칭 항이 없다 — 「집합자원화 대가」를 편익으로 세우려면 「포기한
           자가소비」를 비용으로 세야 하는데 **그 자리가 저장소에 없다**
           (같은 문서 **§4④** · 총괄지침 **제45조③**)

    ★★★ **②는 R60/WP-3 이 닫았다** — `core/cba/proforma.py::
    forfeited_self_consumption_row` 이 그 자리이고, 실행 경로가 ⓒ 에서 그 행을
    싣는다(`core/casegrid/e2e_runner.py::_forfeited_self_consumption_rows`).
    그러므로 ②를 거부 사유로 계속 적으면 **거짓**이다.

    ★★★ **①은 닫을 수 없다.** 소유·운영권 인계와 구분 계측은 자료가 아니라
    **사업 설계**이며(사용자 판정 `docs/decisions-2026-09-04-R59b.md` §1 의
    ⚠ 마지막 항) 저장소가 채울 수 없다. 그래서 ①만 남아 **입력으로 요구된다** —
    `pool_metering` 이 그 통로이고 **적지 않으면 지금까지와 똑같이 거부한다.**

    ⚠⚠ **`DV-15` 를 없애지 않았다 — 조건부로 만들었다.** 거부를 경고로 내리지도
    않았다: *「평가할 수 없다」와 「0 이다」는 다른 말*이고, 0 으로 채우면
    *「없는 제도 위에 편익을 쌓는」* 형태가 된다(이 저장소는 `TouArbitrage`
    단가에서 이미 같은 판단을 했다 — 단가가 없어 0 으로 안 채웠다).

    ⚠ **거부 문면이 어느 쪽이 빠졌는지 말한다** (`PoolMeteringDeclaration.
    missing()`). 둘을 한 덩어리로 적으면 사업 설계자가 무엇을 더 확보해야
    하는지 알 수 없고, 그때 남는 선택은 「그냥 참으로 두기」다.
    """
    branch = BASELINE_DECLARATIONS[arrangement]
    if branch.self_consumption_treatment is SelfConsumptionTreatment.FORFEIT:
        missing = (
            (POOL_PREREQUISITE_TRANSFER, POOL_PREREQUISITE_METERING)
            if pool_metering is None
            else pool_metering.missing()
        )
        if missing:
            raise ValidationError(
                field="baseline.arrangement",
                reason=(
                    f"「{arrangement.value}」의 계측 전제가 안 섰다 — 아직 서지 "
                    f"않은 전제 {len(missing)}건: "
                    + " · ".join(f"「{name}」" for name in missing)
                    + ". 상계처리로는 전기사용자의 전력사용량이 구분되지 않아 "
                    "책임공급비율의 분모가 서지 않는다"
                ),
                action=(
                    f"시나리오의 「{POOL_METERING_FIELD}」 에 그 전제를 선언한 "
                    "뒤에 이 갈래를 고르십시오 — 가정하지 마십시오. "
                    + _POOL_METERING_ACTION
                    + ". 0 으로 채우지 마십시오 — 「평가할 수 없다」와 "
                    "「0 이다」는 다른 말입니다"
                ),
                rule="DV-15",
            )
    return branch


@dataclass(frozen=True)
class BaselineComparison:
    """기준선 vs 신규 비교 — 증분과 기준선 자체를 함께 든다 (FR-705-AC1).

    ``baseline_displayed`` 가 0 이면 «기준선이 표시되지 않았다» — 조항 위반.
    편익이 증분이려면 baseline 이 명시되어야 그 차이가 증분임을 보일 수 있다.
    """

    baseline_rows: tuple[CashFlowRow, ...]
    new_rows: tuple[CashFlowRow, ...]
    incremental_rows: tuple[CashFlowRow, ...]

    def baseline_total(self) -> Money:
        """기준선 총비용 — 리포트에 명시적 표시 (FR-705-AC1)."""
        return aggregate(list(self.baseline_rows))

    def new_total(self) -> Money:
        return aggregate(list(self.new_rows))

    def incremental_total(self) -> Money:
        """편익 증분 총액 = new − baseline."""
        return Money(self.new_total() - self.baseline_total())


def compute_incremental(
    baseline: list[CashFlowRow], new: list[CashFlowRow]
) -> list[CashFlowRow]:
    """new − baseline 의 증분 행.

    같은 tag 끼리 짝지어 빼고, baseline 에만 있는 tag 는 음수(감소),
    new 에만 있는 tag 는 그대로(증가).
    """
    baseline_by_tag: dict[str, CashFlowRow] = {
        (r.tag or r.label): r for r in baseline
    }
    new_by_tag: dict[str, CashFlowRow] = {
        (r.tag or r.label): r for r in new
    }
    all_tags = set(baseline_by_tag) | set(new_by_tag)

    incremental: list[CashFlowRow] = []
    for tag in sorted(all_tags):
        b_row = baseline_by_tag.get(tag)
        n_row = new_by_tag.get(tag)
        b_amounts = b_row.amounts if b_row else {}
        n_amounts = n_row.amounts if n_row else {}
        all_years = set(b_amounts) | set(n_amounts)
        diff_amounts = {
            y: n_amounts.get(y, Money(0)) - b_amounts.get(y, Money(0))
            for y in sorted(all_years)
        }
        # 0 이 아닌 연도만 남긴다 — 0 인 행은 보이지 않는 것이 낫다
        diff_amounts = {y: v for y, v in diff_amounts.items() if v != Money(0)}
        if not diff_amounts:
            continue
        incremental.append(CashFlowRow(
            label=f"{tag} 증분",
            tag=tag,
            amounts=diff_amounts,
        ))
    return incremental


def compare_baseline_vs_new(
    baseline: list[CashFlowRow], new: list[CashFlowRow]
) -> BaselineComparison:
    """기준선 vs 신규 비교 — 증분 행과 함께 기준선 자체도 든다."""
    incremental = compute_incremental(baseline, new)
    return BaselineComparison(
        baseline_rows=tuple(baseline),
        new_rows=tuple(new),
        incremental_rows=tuple(incremental),
    )


def assert_baseline_displayed(comparison: BaselineComparison) -> None:
    """10.5 검증 — 기준선이 명시적으로 표시되었는가 (FR-705-AC1).

    기준선 없이 증분만 보이면 조항 위반이다 — 증분의 타당성을 검증할 수 없다.
    """
    if comparison.baseline_total() == ZERO and not comparison.baseline_rows:
        raise ValueError(
            "기준선이 표시되지 않았다 (FR-705-AC1). 증분만 계산하고 기준선을 "
            "보여 주지 않으면 증분의 타당성을 검증할 수 없다 (도메인 원칙 1-2)"
        )
