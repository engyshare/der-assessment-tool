from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from core.contracts.der import DER
from core.contracts.engine import SystemDispatch
from core.contracts.validation import ValidationError
from core.engine.rule_based import DispatchRule


@dataclass(frozen=True)
class CaseVariable:
    name: str
    values: tuple[object, ...]
    target: str = "scalar"
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))
        if not self.name.strip():
            raise ValidationError(
                field="casegrid.variable_name",
                reason="케이스 변수 이름이 비어 있습니다",
                action="공백이 아닌 이름을 지정하십시오",
            )
        if not self.values:
            raise ValidationError(
                field="casegrid.variable_values",
                reason=f"케이스 변수 {self.name!r} 의 값 목록이 비어 있습니다",
                action="값을 최소 1개 이상 지정하십시오",
            )
        if not self.target.strip():
            raise ValidationError(
                field="casegrid.variable_target",
                reason=f"케이스 변수 {self.name!r} 의 target 이 비어 있습니다",
                action="공백이 아닌 target 값을 지정하십시오",
            )


@dataclass(frozen=True)
class CoupledSet:
    name: str
    variable_names: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_names", tuple(self.variable_names))
        if not self.name.strip():
            raise ValidationError(
                field="casegrid.coupled_set_name",
                reason="결합 집합 이름이 비어 있습니다",
                action="공백이 아닌 이름을 지정하십시오",
            )
        if len(self.variable_names) < 2:
            raise ValidationError(
                field="casegrid.coupled_set_variables",
                reason=(
                    f"결합 집합 {self.name!r} 이 변수를 "
                    f"{len(self.variable_names)}개만 가지고 있습니다"
                ),
                action="결합 집합에 변수를 2개 이상 지정하십시오",
            )
        if len(set(self.variable_names)) != len(self.variable_names):
            raise ValidationError(
                field="casegrid.coupled_set_variables",
                reason=f"결합 집합 {self.name!r} 에 같은 변수가 중복 지정되었습니다",
                action="변수 이름을 서로 다르게 지정하십시오",
            )


@dataclass(frozen=True)
class Case:
    index: int
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValidationError(
                field="casegrid.case_index",
                reason=f"케이스 인덱스가 음수입니다: {self.index}",
                action="0 이상의 정수를 지정하십시오",
            )
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def __getstate__(self) -> dict[str, object]:
        return {"index": self.index, "values": dict(self.values)}

    def __setstate__(self, state: dict[str, object]) -> None:
        object.__setattr__(self, "index", state["index"])
        val = state["values"]
        if isinstance(val, Mapping):
            object.__setattr__(self, "values", MappingProxyType(dict(val)))
        else:
            object.__setattr__(self, "values", MappingProxyType({}))


@dataclass(frozen=True)
class CaseResult:
    """케이스 하나의 결과.

    ## `variants` — 변형 축을 **자료구조로** 세운다 (`FR-607-AC1` / R31 결정 §5)

    조항은 *「모든 실행에서 `지원 0` 케이스가 자동 포함되어 결과 상단에 표시」* 다.
    `run_order()` 가 그 목록을 보증하고 `incentive_cases` 가 현금흐름을 만드는데,
    **결과에 변형별 지표를 담을 자리가 없었다.**

    `metrics` 에 키 접두어(`"무지원.npv_won"`)를 붙이는 안을 버렸다. 접두어는
    **소비자마다 문자열 파싱을 만들게 하고 그 파싱이 갈린다** — 어느 소비자는
    첫 점에서 자르고 어느 소비자는 마지막 점에서 자른다. 그리고 변형이 셋 넷으로
    늘면 키가 곱으로 폭발한다.

    ⚠ **`__getstate__`/`__setstate__` 에 함께 넣어야 한다.** 케이스 그리드는
    `ProcessPool` 로 병렬 실행되므로(`FR-805-AC1`) 결과가 피클을 지난다 — 여기
    빠뜨리면 **직렬 실행에서는 보이고 병렬 실행에서만 변형이 사라진다.** 그 차이는
    케이스 수가 적은 테스트에서 드러나지 않는다.
    """

    case_index: int
    values: Mapping[str, object]
    metrics: Mapping[str, float]
    #: 변형 tag → 그 변형의 지표. 비어 있으면 「변형을 산출하지 않은 실행」이다.
    #:
    #: ⚠⚠ **`default_factory` 여야 한다 — `MappingProxyType({})` 를 직접 기본값으로
    #: 두면 Python 3.11 이 거부한다** (`ValueError: mutable default <class
    #: 'mappingproxy'> … use default_factory`). **3.12 부터는 허용하므로 3.13 로컬에서는
    #: 보이지 않고 CI(3.11)에서만 수집 오류가 난다** — R31 이 실제로 그렇게 겪었고,
    #: `pyproject.toml` 의 `requires-python = ">=3.11"` 이 정본이므로 3.11 이 기준이다.
    variants: Mapping[str, Mapping[str, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "variants", _freeze_variants(self.variants))

    def __getstate__(self) -> dict[str, object]:
        return {
            "case_index": self.case_index,
            "values": dict(self.values),
            "metrics": dict(self.metrics),
            # 병렬 실행이 이 줄에 달려 있다 — 위 독스트링 참조
            "variants": {tag: dict(m) for tag, m in self.variants.items()},
        }

    def __setstate__(self, state: dict[str, object]) -> None:
        object.__setattr__(self, "case_index", state["case_index"])
        val = state["values"]
        if isinstance(val, Mapping):
            object.__setattr__(self, "values", MappingProxyType(dict(val)))
        else:
            object.__setattr__(self, "values", MappingProxyType({}))
        met = state["metrics"]
        if isinstance(met, Mapping):
            object.__setattr__(self, "metrics", MappingProxyType(dict(met)))
        else:
            object.__setattr__(self, "metrics", MappingProxyType({}))
        var = state.get("variants")
        object.__setattr__(
            self, "variants", _freeze_variants(var) if isinstance(var, Mapping) else
            MappingProxyType({})
        )


def _freeze_variants(
    variants: Mapping[str, Mapping[str, float]],
) -> Mapping[str, Mapping[str, float]]:
    """중첩 사전을 **두 층 모두** 읽기 전용으로 만든다.

    바깥만 얼리면 안쪽 지표 사전을 밖에서 고칠 수 있고, 그것은 `NFR-205` 가
    막으려는 전역 가변 상태와 같은 결과다 — 병렬 실행에서 특히 나쁘다.
    """
    return MappingProxyType({
        tag: MappingProxyType(dict(metrics)) for tag, metrics in variants.items()
    })


# ── 리포트 자료형이 자원을 가리키는 **두 규약** (R43-B) ────────────────────
#
# 종전에는 셋 다 칸 이름이 `from_resource` 하나였는데, **담기는 값이 두 갈래**
# 였다. 이름이 같으니 두 규약이 하나로 보이고, 실제로는 **서로 조인되지 않는
# 두 이름공간**이다:
#
#   ① 자원 이름(`resource_name`) — `ResourceLine.name` 과 같은 키(`"e2e-pv"`).
#      `OneOffLine` 이 이 규약이며 **붙임 8 이 조인한다**
#      (`core/report/unreflected.py::_replacement_items`).
#   ② 짧은 코드(`resource_code`) — `"PV"` · `"ESS"` · 귀속 없으면 `""`.
#      `CostLine`·`BenefitLine` 이 이 규약이며, 붙임 4 가 **표시**하고 러너가
#      같은 코드 리터럴끼리 조인한다(`_resource_lines::produced_by`).
#
# ## ⚠ 지금은 틀린 값을 인쇄하지 않는다 — 그래서 더 위험하다
#
# 붙임 8 은 `OneOffLine` 쪽만 조인하고 그쪽 규약은 맞다. 무너지는 것은 **다음
# 사람이 `CostLine` 으로 같은 조인을 쓰는 날**이다: 짧은 코드와 자원 이름은
# 절대 같지 않으므로 **아무 예외 없이 빈 교집합**이 나오고, 붙임 8 의 판정은
# 조용히 *「미반영」* 쪽으로 넘어간다. `unreflected.py` 독스트링이 이미 그
# 형태를 적어 두었다 — *「배선이 들어오면 그 판정은 참인 조건 위에서 거짓을
# 계속 인쇄한다」*.
#
# **그래서 주석이 아니라 칸 이름으로 갈랐다.** 규약을 주석으로만 적으면 조인을
# 쓰는 자리에서는 보이지 않는다 — 이름으로 갈라 두면 `resource_code` 를
# `ResourceLine.name` 과 맞춰 보는 코드가 **읽는 순간 어긋나 보인다.**
#
# 붙드는 것: `tests/casegrid/test_from_resource_conventions.py` — 실행 경로를
# 한 번 돌려 ① 이 자원 이름 집합에 **속하고** ② 가 **속하지 않는지**를 잰다.
# 짧은 코드 목록은 그 검사가 계산하지 않고 밖에서 고정한다.


@dataclass(frozen=True)
class ResourceLine:
    """**무엇을 평가했는가** — 리포트 0절의 한 행 (`FR-1001-AC2`).

    ## 왜 자원 제원이 경계를 넘는가

    리포트 첫 판을 검토에 걸었더니 *「분석 대상 모델에 대한 소개가 없다」* 가
    첫 지적이었다. 맞다 — 리포트는 「NPV −865,881원」과 「PV 단가가 결론을
    뒤집는다」를 말하면서 **PV 를 몇 kW 놓았는지, 무엇과 함께 놓았는지**를 한
    번도 말하지 않았다. 검토자는 대상을 모르는 채 민감도만 읽은 것이다.

    ⚠ **리포트가 자원을 다시 세우게 두지 않는다.** 표시 층이 `PV(...)` 를
    똑같이 한 번 더 만들면 그것은 사본이고, 러너의 제원이 바뀔 때 리포트는
    **옛 제원을 그럴듯하게 계속 인쇄한다.** 아무 예외도 나지 않는다.
    """

    name: str
    #: 자원 종류 — 클래스 이름이 아니라 사람이 읽는 말.
    kind: str
    #: 용량 문면. 단위가 자원마다 다르므로(kW · kWh) 문자열로 나른다.
    capacity: str
    operating_mode: str
    lifetime_years: int
    #: 단가 문면 — 「1,600,000원/kW」처럼 **무엇당 얼마인지**까지.
    unit_capex: str
    capex_won: int
    fixed_om_won_per_year: int
    #: 이 자원이 만드는 편익의 태그. 비어 있으면 **비용만 내는 자원**이다.
    produces: tuple[str, ...]


@dataclass(frozen=True)
class BenefitLine:
    """편익 한 갈래가 **얼마이며 무엇에서 나왔는가** — 리포트 2절의 한 행.

    ## 왜 갈래별로 나누는가

    검토 지적 둘째가 *「pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이
    적정한지는 어떻게 보는가」* 였다. 연 편익을 **한 덩어리(904,860원)** 로만
    실으면 그 물음에 답할 자리가 없다 — 검토자는 PV 에 480만원을 쓴 것이
    타당한지 판단하려는데, 리포트는 PV 가 그중 얼마를 벌어 오는지 말하지
    않았다.
    """

    tag: str
    label: str
    #: 1년차 금액(원).
    annual_won: int
    #: 이 편익을 만든 자원의 **짧은 코드** — `"PV"` · `"ESS"` (위 「두 규약」).
    #: 러너가 같은 코드 리터럴로 조인한다
    #: (`e2e_runner._resource_lines::produced_by`), 그리고 붙임 4 가 표시한다
    #: (`core/report/method_sections.py`). **자원 이름이 아니다** —
    #: `ResourceLine.name` 과 조인하면 빈 교집합이 나온다.
    resource_code: str
    #: 산식 문면 — 대입값까지 (`FR-1001-AC3`).
    formula: str


#: 일회성 흐름의 종류 — **문자열 하나를 러너와 리포트가 나누어 갖는다.**
#: 붙임 8(`core/report/unreflected.py`)이 *「이 자원의 교체비가 실제로
#: 계상됐는가」* 를 이 값으로 판정하므로, 러너가 종류를 바꾸면 그 판정이 조용히
#: 「미반영」으로 돌아선다 — 그래서 리터럴을 양쪽에 적지 않고 **자료형 모듈이
#: 갖는다**(`_GRID_PURCHASE_TAG` 가 두 파일에 나뉘어 있던 것의 교정판).
ONE_OFF_REPLACEMENT = "replacement"
ONE_OFF_SALVAGE = "salvage"

#: 변동 O&M **비용 항목**의 태그 접미어 — 같은 사유로 자료형 모듈이 갖는다.
#: 붙임 8(`core/report/unreflected.py::_variable_om_item`)이 *「변동 O&M 이
#: 프로포마에 실렸는가」* 를 이 값으로 판정하고, 본문 3.2 의 「미포함」 단서가
#: 그 판정에서 나온다. 배선하는 쪽이 다른 말을 쓰면 그 둘이 **반영된 뒤에도
#: 「미반영」을 계속 인쇄한다.**
#:
#: ⚠ **태그가 아니라 접미어다.** 고정 O&M 이 자원마다 행을 갖듯
#: (`PVFixedOM`·`ESSFixedOM`) 변동 O&M 도 자원마다 서므로 태그 하나로 고정할 수
#: 없다 — 고정하면 `PVVariableOM` 이 판정에 걸리지 않는다. 접미어로 두면
#: 자원별 행과 이 값 그대로인 태그가 **둘 다** 걸린다.
COST_TAG_VARIABLE_OM = "VariableOM"


@dataclass(frozen=True)
class OneOffLine:
    """**특정 연차 한 번만** 생기는 흐름 한 건 — 교체비·잔존가치 (R39-E).

    ## 왜 `CostLine` 을 늘리지 않았나 (붙임 4 판정)

    `CostLine.annual_won` 은 **1년차 금액**이고, 리포트가 그 칸의 합을
    `CaseBasis.annual_cost_won`(프로포마 1년차 합계)과 **대조해 어긋남을 잡는다**
    (`tests/report/test_narrative.py`). 교체비(18년차)·잔존가치(20년차)를 같은
    자료형에 담으면 두 갈래뿐이다 — 1년차 금액을 `0` 으로 적어 **금액 칸이
    0원인 비용 행**을 만들거나(*「합계만 있는 표에서는 빠진 행이 드러나지
    않는다」* 의 재발이며 이미 배제된 안), 아니면 그 대조 항등식을 항목마다
    예외를 두어 무르게 만드는 것이다.

    **그래서 표를 둘로 갈랐다.** 연간 항목은 `CostLine`, 일회성 흐름은 이
    자료형이 담고 붙임 4 가 표 둘로 싣는다. 연차 칸이 **선택이 아니라 필수**인
    것이 요점이다 — 언제 나가는 돈인지 없이 금액만 적으면 검토자가 그것을
    연간액으로 읽는다.

    ⚠ **부호는 비용 행을 그대로 옮긴다** — 양수 = 지출(교체비), 음수 = 유입
    (잔존가치). `CostLine` 이 「비용은 양수」인 것과 달리 이 자료형은 두 부호를
    다 갖는데, 그것이 부호를 뒤집는 둘째 자리가 되지는 않는다: 뒤집는 곳은
    여전히 `net_operating_flows()` 하나이고 이 칸은 **그 앞의 비용 행과 같은
    수**다. 같은 수여야 표시가 프로포마를 말할 수 있고, 그 일치는 검사가 잡는다
    (`tests/casegrid/test_lifecycle_wiring.py`).
    """

    tag: str
    label: str
    #: `ONE_OFF_REPLACEMENT` · `ONE_OFF_SALVAGE` 중 하나. 위 상수 참조.
    kind: str
    #: 계상 연차(1-base). **필수다** — 위 독스트링 참조.
    year: int
    #: 그 연차의 금액(원). **양수 = 지출 · 음수 = 유입.**
    amount_won: int
    #: 이 흐름을 낸 자원의 **이름** — `ResourceLine.name` 과 **같은 키**다
    #: (위 「두 규약」). 붙임 8 이 자원별로 「이 자원의 교체비가 계상됐는가」를
    #: 묻기 때문이며(`core/report/unreflected.py::_replacement_items`), 조인 키가
    #: 없으면 그 판정이 건수만 세다 어느 자원인지를 잃는다.
    #: **짧은 코드가 아니다** — `"PV"` 를 적으면 그 조인이 빈 교집합을 내고
    #: 붙임 8 이 조용히 「미반영」으로 넘어간다.
    resource_name: str
    #: 산식 문면 — 단가·수량·물가 계수까지 (`FR-1001-AC3`).
    formula: str


@dataclass(frozen=True)
class CostLine:
    """운영비 한 항목이 **얼마이며 무엇에서 나왔는가** — `BenefitLine` 의 반대편.

    ## 왜 편익 쪽만 갈래로 나누어 두었는가 — 그것이 결함을 가렸다

    `BenefitLine` 은 R33 이 *「PV 에 480만원을 쓴 것이 타당한가」* 에 답하려고
    만들었고, 비용 쪽은 **합계 하나(`annual_cost_won`)** 로 남았다. 그래서
    리포트는 「1년차 운영비 200,000원」만 싣고 **그것이 무엇 둘의 합인지**
    말하지 않았다. 비용 항목이 고정 O&M 둘뿐일 때는 아무도 그것을 아쉬워하지
    않았는데, 바로 그 상태가 *「계통에서 산 전력이 공짜다」* 를 눈에 보이지
    않게 했다 — **합계만 있는 표에서는 빠진 행이 드러나지 않는다.**

    ⚠ **수량과 단가를 산식에 함께 적는다.** 「전력 구매 271,080원」만으로는
    단가가 틀렸는지 수량이 틀렸는지 검토자가 가를 수 없고, 그 둘은 서로 다른
    사람이 고친다(단가는 대장, 수량은 운전).

    ⚠ **비용은 양수로 담는다** — 부호를 뒤집는 자리는 `net_operating_flows()`
    하나여야 한다(R32 가 *「수수료율을 올릴수록 NPV 가 커진다」* 로 만난 형태).
    """

    tag: str
    label: str
    #: 1년차 금액(원). **양수 = 비용.**
    annual_won: int
    #: 이 비용을 일으킨 자원의 **짧은 코드** — `"PV"` · `"ESS"` (위 「두 규약」).
    #: 자원에 귀속되지 않는 거래 비용은 **빈 문자열**이다(수전·정산 수수료).
    #: 읽는 곳은 붙임 4 의 표시 하나뿐이며(`method_sections.py`) **조인 키가
    #: 아니다** — `ResourceLine.name` 과 맞춰 보면 빈 교집합이 나온다.
    resource_code: str
    #: 산식 문면 — 수량·단가까지 (`FR-1001-AC3`).
    formula: str


@dataclass(frozen=True)
class CaseBasis:
    """산식의 **대입값** — `FR-1001-AC3` 의 3중 표기 중 셋째 줄이 여기서 온다.

    ## 왜 지표만으로는 안 되는가

    `MC-1` 은 *「비개발자 검토자가 리포트만 보고 **회수기간의 근거**를 설명할 수
    있는가」* 를 잰다. 지표 사전(`{"npv": …, "payback_years": …}`)은 **답이지
    근거가 아니다** — 검토자가 「왜 10.5년인가」를 재구성하려면 초기투자·연
    편익·할인율·분석기간이 그 자리에 있어야 하고, 없으면 리포트가 *"계산했더니
    그렇습니다"* 로 끝난다. 그것이 이 저장소가 `AssumptionValue` 에서 이미 한 번
    내린 판단이다(*「값만 넘기면 리포트가 그 값이 어디서 왔는가에 답할 수
    없다」*).

    ⚠ **선택 필드로 두지 않았다.** 두면 안 채운 실행에 근거가 없고 **빠졌을 때
    나는 증상이 없다** — 리포트가 조용히 빈 산식을 그린다. R21 이 `is_baseline`
    깃발에서, R32 가 `with_variants` 에서 두 번 없앤 형태다.

    ⚠ **여기 담는 것은 「무엇을 넣었는가」이지 「무엇이 나왔는가」가 아니다.**
    지표는 `CaseOutcome.metrics` 가 갖는다. 같은 수를 두 곳에 담으면 한쪽만
    고쳐진다.
    """

    #: `t=0` 초기투자(원). 지원을 반영하지 않은 **케이스 기준** 총사업비다 —
    #: 변형별 초기지출은 `CaseOutcome.variants` 가 따로 갖는다.
    initial_investment_won: int
    #: 1년차 편익 합계(원).
    annual_benefit_won: int
    #: 1년차 운영비 합계(원). **양수로 담는다** — 부호를 뒤집는 자리는
    #: `net_operating_flows()` 하나여야 한다(R32).
    annual_cost_won: int
    discount_rate: float
    horizon_years: int
    #: 계통에서 산 전력의 **한계단가**(원/kWh) — 대장
    #: `tariff.hv_single_contract.energy_only`.
    #:
    #: ⚠ **비용 산식 안에도 문면으로 있는데 왜 값으로 또 담는가.** 이 단가는
    #: 사지 **않은** 전력의 값도 정한다 — 자가소비 절감은 「사지 않아서 아낀
    #: 돈」이므로 같은 단가를 쓴다. 즉 소비자가 둘이고, 그중 하나(붙임 8)는
    #: 프로포마 행이 없는 항목의 크기를 재는 쪽이다. 산식 문면을 되파싱해
    #: 쓰게 두면 **표기를 다듬을 때 크기가 조용히 0 이 된다.**
    grid_purchase_price_won_per_kwh: float
    #: 평가 대상 자원 — 위 `ResourceLine` 참조.
    resources: tuple[ResourceLine, ...]
    #: 편익 갈래별 금액 — 위 `BenefitLine` 참조.
    benefits: tuple[BenefitLine, ...]
    #: 운영비 항목별 금액 — 위 `CostLine` 참조. **합계(`annual_cost_won`)와
    #: 함께 담는 이유**: 합계는 프로포마 행에서 세고 항목은 러너가 지으므로,
    #: 둘이 어긋나면 그것 자체가 결함이다. 리포트가 그 어긋남을 잰다
    #: (`tests/report/test_narrative.py`).
    costs: tuple[CostLine, ...]
    #: **특정 연차 한 번만** 나가거나 들어오는 흐름 — 교체비·잔존가치.
    #: 위 `OneOffLine` 참조. 연간 항목(`costs`)과 **갈라 담는** 이유가 그
    #: 독스트링에 있다.
    #:
    #: ⚠ **비어 있는 것이 「없다」가 아니다.** 수명이 분석기간보다 길지도
    #: 짧지도 않은 구성에서는 정말로 비고, 배선이 끊긴 구성에서도 빈다 — 둘을
    #: 가르는 것은 붙임 8 이며 그 판정은 자원 수명과 이 목록을 **함께** 본다
    #: (`core/report/unreflected.py::_replacement_items`).
    one_off_flows: tuple[OneOffLine, ...]
    #: 디스패치 규약 문면 — 「대표일 24스텝 × 365일」처럼 **결과를 읽는 데
    #: 필요한 전제**다. 규약을 적지 않으면 검토자가 시간해상도를 모른 채
    #: 연간 금액을 읽는다(재현도 불가능하다).
    dispatch_note: str


@dataclass(frozen=True)
class CaseOutcome:
    """케이스 러너 하나의 산출 — 지표 **와 변형별 지표** (`FR-607-AC1` / R32).

    ## 왜 자료형을 하나 더 두는가

    `CaseRunner` 의 반환형이 `Mapping[str, float]` 하나였다. 그래서 R31 이
    `CaseResult.variants` 를 만들어도 **러너가 그것을 채울 통로가 없었고**,
    실제로 `variants=` 를 쓰는 배포 코드가 0곳이었다(채우는 것은 테스트뿐).
    소비자(`core/report/variant_report.py`)는 있고 생산자가 없었다.

    통로를 `run_cases()` 의 **선택 인자**(`variant_runner=…`)로 두는 안을 버렸다.
    안 넘기면 변형이 그냥 없고 **빠졌을 때 나는 증상이 없다** — R21 이
    `build_capex_cashflows(..., is_baseline=True)` 에서 없앤 깃발과 같은 형태다
    (`core/contracts/casevariant.py` 머리말).

    ⚠ **`run_cases()` 는 지표 사전만 돌려주는 러너도 계속 받는다.** 그것이
    깃발의 부활이 아닌 이유: `run_cases` 는 케이스 목록을 도는 **범용 기반**이고
    「변형 없는 실행」(민감도 스윕·성능 측정)은 정당한 상태다. `FR-607-AC1` 이
    말하는 「모든 실행」은 **평가 파이프라인**이며 그 진입점
    (`core/casegrid/e2e_runner.py::run_single_case_e2e`)은 이 자료형을 **항상**
    돌려준다 — 거기에는 켜고 끄는 인자가 없다.
    """

    metrics: Mapping[str, float]
    #: 변형 tag → 그 변형의 지표. `run_order()` 의 변형 **전부**가 들어 있어야
    #: 하며, 그 확인은 표시 층(`build_variant_table`)이 거부로 한다.
    variants: Mapping[str, Mapping[str, float]]
    #: 산식의 대입값 — 위 `CaseBasis` 참조. 리포트가 근거를 그리는 재료다.
    basis: CaseBasis
    #: ★ **이 케이스가 실제로 세운 자원 객체** (검토 「1차 의견」 2 · R33).
    #:
    #: 의견 원문은 *「규칙 기반 엔진이 적용되었다는데 규칙이 붙임에 기재되지
    #: 않으면 내용을 이해할 수 없음」* 이었다. 그 규칙은 자원마다 다르고
    #: (`rule_for()`), 무엇에 어떤 규칙이 붙었는지는 **자원 객체를 봐야**
    #: 알 수 있다 — `ResourceLine` 은 사람이 읽는 제원이라 그 물음에 답하지
    #: 못한다.
    #:
    #: ⚠ **리포트가 자원을 다시 세우게 두는 대신 넘긴다.** 표시 층이
    #: `PV(...)` 를 한 번 더 만들면 사본이 되고, 러너가 운전 방법을 바꿔도
    #: 리포트는 옛 규칙을 그럴듯하게 계속 인쇄한다(`ResourceLine` 독스트링과
    #: 같은 이유이며, 거기서는 **제원**이 이 판단을 이미 한 번 받았다).
    #: 계층은 어긋나지 않는다 — `DER` 은 `core.contracts` 소속이다.
    resources: tuple[DER, ...]
    #: ★ **대표일 운전 결과** (검토 「1차 의견」 3 · R33).
    #:
    #: 의견은 *「시간대별 디스패치 표」* 를 요구했다. 파이프라인은 24스텝을
    #: 실제로 돌리는데 그 결과가 **경계를 넘지 않아** 리포트는 연간 합계만
    #: 실었다 — 검토자는 「대표일 904,860원」이 어느 시간대에서 왔는지 물을
    #: 자리가 없었다.
    #:
    #: ⚠ **여기가 `CaseBasis` 가 아닌 이유**: `CaseBasis` 는 *「무엇을
    #: 넣었는가」* 를 담는다고 스스로 못 박고 있다. 운전 결과는 **나온 것**이다.
    dispatch: SystemDispatch
    #: 이 실행이 **실제로 적용한** 디스패치 규칙 순서 (`FR-302-AC1`·`AC3`).
    #:
    #: ⚠ 리포트가 `DEFAULT_RULE_ORDER` 를 다시 읽게 두지 않는다. 순서는 엔진
    #: 인스턴스마다 다를 수 있고(조항이 「설정 가능」이다), 그때 리포트는
    #: **기본 순서를 실행 순서로 인쇄한다** — 아무 예외도 나지 않는다.
    rule_order: tuple[DispatchRule, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "variants", _freeze_variants(self.variants))


@dataclass(frozen=True)
class RunPlan:
    case_count: int
    threshold: int
    estimated_seconds: float
    requires_confirmation: bool
    should_run_background: bool


@dataclass(frozen=True)
class Progress:
    completed_cases: int
    total_cases: int
    estimated_remaining_seconds: float | None


@dataclass(frozen=True)
class EnvironmentProfile:
    label: str
    cpu_count: int | None
    memory_mb: int | None
    free_tier_like: bool


@dataclass(frozen=True)
class PerformancePoint:
    case_count: int
    repeat_count: int
    average_seconds: float
    samples_seconds: tuple[float, ...]
    environment: EnvironmentProfile


@dataclass(frozen=True)
class FeasibleCell:
    """달성영역 격자의 칸 하나 — `FR-803-AC1`.

    ## `x_index`/`y_index` — **수치 축** (R31 결정 §8)

    프리셋 축의 값은 `"low"`/`"base"`/`"high"` **문자열**이라 등고선·음영 차트가
    원리상 그려지지 않는다(차트는 수치 좌표를 받는다). 그래서 축의 **수준
    인덱스**를 함께 싣는다.

    **문자열을 정렬해서 지수를 만들지 않는다** — 사전순으로는
    `base < high < low` 가 되어 **중간 수준이 맨 앞에 오고**, 그 격자는 좌표가
    뒤섞인 채 그럴듯하게 그려진다. 인덱스는 케이스 그리드가 **선언한 수준
    순서**에서만 나온다(`feasible_region(axis_levels=…)`).

    `None` 은 「수준 순서를 받지 못했다」이며 「0번 수준」이 아니다 — 그 둘을 같은
    값으로 두면 축을 못 그린 격자가 첫 수준에 뭉친다.
    """

    x_value: object
    y_value: object
    metric_value: float
    achieved: bool
    case_index: int
    x_index: int | None = None
    y_index: int | None = None


@dataclass(frozen=True)
class TornadoInfluence:
    variable_name: str
    influence: float
