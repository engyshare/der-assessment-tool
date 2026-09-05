"""「전체 파라미터」의 기준 — UI-1-AC1 / WP-16.

조항 문면: *「마법사 방식으로 초심자를 안내하되, **숙련자용 전체 파라미터 단일
화면(고급 모드)** 병행」*

**R29 까지 이 조항을 붙드는 검사는 「전체」를 말할 수 없었다.** 기준이 저장소에
없었기 때문이다 — `ModelConfig` 은 `name`·`resources`·`common_load`·`contract`·
`regulation` 이고 `DERConfig.params` 는 `dict[str, Any]` 다. R28·R29 가 화면 쪽
검사의 항진을 걷어내며 *「기준이 생기기 전에는 어떤 검사도 「전체」를 말할 수
없다」* 를 남겼고, **그때의 이름은 R28 에 없어졌다.** 지금 그 자리를 재는 것은
`tests/web/test_dashboard.py::test_advanced_mode_shows_every_parameter_the_configuration_has` 다.

**R31 이 그 기준을 정했다: 레지스트리에 등록된 자원의 `__init__` 시그니처.**

    전체 파라미터 = 구성에 담긴 자원 각각이 생성자로 받는 인자 전부

손으로 둔 목록을 두지 않는 이유는 **갈리기 때문**이다. `core/der/<tag>.py` 를
놓으면 자원이 늘고(NFR-207-AC1 「파일 하나」), 목록이 따로 있으면 그때 두 곳을
고쳐야 하며 한쪽만 고쳐진 상태를 아무도 보지 않는다. `composition.
available_resource_tags()` 가 *「어떤 자원을 놓을 수 있는가」* 에 대해 이미 같은
일을 하고, 이 파일은 *「그 자원이 어떤 값을 받는가」* 에 대해 같은 일을 한다.

## 이 파일이 멈추는 두 자리 — 둘 다 「전체」가 거짓이 되는 자리다

1. **열거할 수 없는 시그니처.** 자원이 `**kwargs` 를 받으면 받는 이름이
   열거 불가능해진다. 그때 조용히 아는 것만 돌려주면 **화면은 그럴듯하고 조항은
   거짓이 된다** — 「전체」라고 적힌 화면에 없는 파라미터가 생긴다.
2. **단위를 말할 수 없는 수치 파라미터.** `UI-2-AC1` 은 *「모든 수치 입력 옆에
   단위 상시 표시」* 를 요구한다. 카탈로그가 수치 파라미터를 내면서 단위를
   모르면 화면은 단위 없는 입력을 그리게 되고, 그것은 이 저장소가 *「단위 혼동은
   곧 계산 오류다」* 라 적어 둔 자리다(작업 목록 15.2).

**둘 다 예외로 멈춘다.** 아는 것만 돌려주는 쪽을 고르면 새 자원 하나가 조용히
화면에서 빠지거나 단위 없이 나오고, 그 상태로 검사는 전부 초록불이다.

## 단위는 어디서 오는가 — 이름이 말하거나, 사람이 선언하거나

이 저장소의 자원 파라미터 이름은 **이미 단위를 담고 있다**(`capex_unit_won_per_kw`
· `soc_min_pct` · `battery_kwh`). 그래서 단위표를 새로 발명하지 않고 둘로 가른다.

    `UNIT_BY_SUFFIX`   이름이 단위를 **문자 그대로** 담은 것 — 규약을 읽는다
    `UNIT_BY_NAME`     이름이 단위를 담지 않은 것 — 사람이 선언하고 사유를 적는다

**접미어 규칙을 넓히지 않은 이유가 이 가름의 요점이다.** `cycle_life`(회)와
`calendar_life`(년)는 같은 `_life` 로 끝나는데 단위가 다르고, `heating_degree_days`
는 `_days` 로 끝나지만 일(日)이 아니라 난방도일이다. **접미어를 넓히면 규칙이
틀린 단위를 자신 있게 붙이고, 틀린 단위는 없는 단위보다 나쁘다.**

두 표가 겹치면(접미어로 이미 풀리는 이름을 `UNIT_BY_NAME` 이 또 선언하면)
`tests/model/test_parameters.py` 가 빨간불을 낸다 — 겹친 자리는 나중에 접미어
규칙을 고칠 때 어느 쪽이 이기는지가 조용히 뒤집히는 자리다.

## 한국어 라벨도 여기서 온다 — 화면이 손으로 적지 않는다

사용자 판정(`docs/decisions-2026-09-05-R63.md` §1 「용어」)이 *「"옥상 태양광 ·
azimuth_deg" 와 같이 coding 상의 변수명을 병기하지 않음」* 을 요구한다. 변수명을
지우려면 **한국어 라벨이 어딘가에서 와야 하고**, 그 자리는 화면이 아니라 여기다 —
화면 템플릿에 손으로 적으면 카탈로그가 늘 때 그 목록이 낡고, 낡은 것은 사람이
없는 칸을 찾을 때까지 드러나지 않는다.

    `LABEL_BY_NAME`   이름 하나에 라벨 하나. **접미어 규칙을 두지 않는다**

접미어를 두지 않는 사유는 단위와 같고 **더 세다**. 단위는 이름이 문자 그대로
담을 때가 있지만 라벨은 그런 규칙성이 없다 — `capex_unit_won_per_kw`(히트펌프
난방 출력당 설치 단가)와 `unit_cost_won_per_kw`(부하 설비 단가)는 접미어가 같고
가리키는 것이 다르다. 규칙이 라벨을 지어내면 **틀린 이름이 자신 있게 붙는다.**

**라벨이 없는 것은 멈추는 자리가 아니라 세는 자리다.** 단위와 달리 라벨 부재는
계산 오류가 아니라 표시 결함이고, 라벨 하나가 없어서 앱 전체가 못 뜨는 쪽이 더
나쁘다. 그래서 `label` 은 빈 문자열로 나가고 **빠진 수를 시험이 센다**(⑤) —
세지 않으면 화면이 조용히 변수명으로 되돌아간다.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum
from types import MappingProxyType, ModuleType, UnionType
from typing import Any, Union, get_args, get_origin

import core.der
from core.contracts.der import DER
from core.contracts.registry import discover
from core.model.schemas import DERConfig, ModelConfig

#: 생성자의 첫 인자. 파라미터가 아니다.
_SELF = "self"


class ParameterCatalogueError(Exception):
    """카탈로그가 「전체」를 말할 수 없다 — **멈춘다**.

    경고로 흘리지 않는 이유: 카탈로그가 아는 것만 돌려주면 고급 모드 화면은
    그대로 그려지고 검사도 통과한다. 빠진 파라미터는 사용자가 그 값을 넣으려다
    없다는 것을 알아차릴 때까지 아무 데도 나타나지 않는다.
    """


class ParameterKind(StrEnum):
    """화면이 이 파라미터를 **무엇으로 그려야 하는가**.

    「전체 파라미터 단일 화면」이라고 해서 8760개짜리 시계열을 수치 입력 칸
    하나로 그릴 수는 없다. 그리는 방법이 다를 뿐 **화면에 자리는 있어야 한다** —
    자리가 없으면 그것이 곧 「전체」가 아닌 것이다.
    """

    #: 수치 입력 — 단위가 반드시 있어야 한다 (UI-2-AC1)
    NUMBER = "수치"
    #: 예/아니오
    TOGGLE = "예/아니오"
    #: 정해진 값 중 고르기 (운전 방법 등)
    CHOICE = "선택"
    #: 자유 문자열
    TEXT = "문자"
    #: 수치 열 — 시계열·프로파일. 별도 편집기·파일로 다룬다
    SERIES = "시계열"
    #: 그 밖의 구조 — COP 곡선·하위 구성·가중치 사전
    STRUCTURED = "구조"


#: 이름이 단위를 **문자 그대로** 담은 것. 긴 접미어가 먼저 맞는다
#: (`capex_unit_won_per_kwh` 는 `_won_per_kwh` 이지 `_kwh` 가 아니다).
UNIT_BY_SUFFIX: Mapping[str, str] = MappingProxyType({
    "_won_per_kwh": "원/kWh",
    "_won_per_kw": "원/kW",
    "_won_per_year": "원/년",
    "_won": "원",
    "_kwh": "kWh",
    "_kw": "kW",
    "_pct": "%",
    "_deg": "°",
    "_temp_c": "℃",
    "_hours": "시간",
    "_hour": "시",
    "_count": "개",
})

#: 이름이 단위를 담지 않은 것. **사유를 값 옆에 적는다** — 적을 수 없으면 그것은
#: 이름을 고쳐야 한다는 뜻이지 표를 늘려야 한다는 뜻이 아니다.
UNIT_BY_NAME: Mapping[str, str] = MappingProxyType({
    # 스텝 길이. 기본값이 `SECONDS_PER_HOUR` 이므로 초다.
    "dt": "초",
    # 수명 — 연 단위. `_life`/`lifetime` 을 접미어로 두지 않은 이유는 바로 아래
    # `cycle_life` 가 같은 꼴이면서 단위가 다르기 때문이다.
    "lifetime": "년",
    "inverter_lifetime": "년",
    "pcs_lifetime": "년",
    "pump_lifetime": "년",
    "calendar_life": "년",
    # 사이클 수명은 햇수가 아니라 충방전 횟수다.
    "cycle_life": "회",
    "cycles_per_year": "회/년",
    # 무차원 비(0~1). %(백분율)로 받는 `_pct` 인자들과 **자릿수가 100배 다르므로**
    # 단위 표시가 둘을 갈라 준다.
    "capacity_factor": "비율(0~1)",
    "self_consumption_ratio": "비율(0~1)",
    "participation": "비율(0~1)",
    "available_dod": "비율(0~1)",
    "arrival_soc": "비율(0~1)",
    "min_departure_soc": "비율(0~1)",
    "discharge_efficiency": "비율(0~1)",
    "charge_efficiency": "비율(0~1)",
    "vat_rate": "비율(0~1)",
    # 연 단위로 적용되는 비율. 위와 갈라 적는다 — 같은 0.02 라도 뜻이 다르다.
    "degradation_rate": "비율/년",
    "escalation_rate": "비율/년",
    # 교체 재취득 단가 전용 계수 (R42 · `Q-17`). 단위는 위와 **같고 뜻이 다르다** —
    # 이름이 그 차이를 지므로 여기서는 단위만 준다. 왜 갈랐는지는
    # `DER.replacement_escalation_factor()` 독스트링이 갖는다.
    "replacement_escalation_rate": "비율/년",
    "annual_growth_rate": "비율/년",
    # 난방도일. `_days` 로 끝나지만 일(日)이 아니다 — 접미어 규칙을 두지 않은
    # 이유가 이 한 줄이다.
    "heating_degree_days": "난방도일(℃·일)",
    "kwh_per_hdd": "kWh/난방도일",
})

#: 파라미터 이름의 **한국어 라벨**. 화면은 `spec.label` 하나만 읽는다.
#:
#: ⚠ **단위를 라벨에 넣지 마라** — `unit` 이 따로 있고, 같은 사실을 두 곳에 적으면
#: 한쪽만 고쳐진 상태를 아무도 보지 않는다. ⚠ **밑줄과 인자 이름을 넣지 마라** —
#: 그것이 곧 사용자가 지우라고 한 병기다.
#:
#: 사유는 이름마다 적지 않는다 — 단위와 달리 라벨은 이름의 번역이다. **뜻이
#: 갈리는 것만** 주석으로 가른다.
LABEL_BY_NAME: Mapping[str, str] = MappingProxyType({
    # ── 모든 자원이 공통으로 받는 것 ──
    "name": "자원 이름",
    "dt": "시간 간격",
    "operating_mode": "운전 방법",
    "end_of_life_action": "수명 종료 처리",
    "subcomponents": "하위 구성",
    # 수명이 셋이고 **뜻이 갈린다**: 설비가 서 있는 햇수 · 달력 기준 열화 한계 ·
    # 충방전 횟수. `unit`(년/년/회)이 둘째와 셋째를 갈라 주지 못하므로 라벨이 진다.
    "lifetime": "설비 수명",
    "calendar_life": "달력 수명",
    "cycle_life": "사이클 수명",
    "degradation_rate": "연간 성능저하율",
    "vat_rate": "부가가치세율",
    "fixed_om_won_per_year": "연간 고정 운영비",
    "variable_om_won_per_kwh": "변동 운영비 단가",
    # 물가 계수가 둘이고 **단위가 같고 뜻이 다르다**(R42 · `Q-17`) — 하나는 운영비,
    # 하나는 교체 재취득 단가에 붙는다. 구별은 여기서 진다.
    "escalation_rate": "운영비 실질 상승률",
    "replacement_escalation_rate": "교체 단가 실질 상승률",
    # ── 태양광 ──
    # ⚠ `capacity_kw` 는 부하·열부하도 받는다. 거기서는 계약 용량을 뜻하지만
    # 이름별 선언이므로 라벨은 하나다 — 자원 이름이 화면에서 그 차이를 진다.
    "capacity_kw": "설비용량",
    "capacity_factor": "이용률",
    "generation_profile_kwh": "발전 프로파일",
    "azimuth_deg": "방위각",
    "tilt_deg": "경사각",
    "inverter_lifetime": "인버터 수명",
    "unit_capex_won_per_kw": "모듈 설치 단가",
    "bos_capex_won": "부대설비 설치비",
    "inverter_unit_capex_won_per_kw": "인버터 설치 단가",
    "inverter_replacement_unit_won_per_kw": "인버터 교체 단가",
    "self_consumption_ratio": "자가소비 비율",
    # ── 배터리(ESS) ──
    "capacity_kwh": "저장용량",
    "power_kw": "충방전 출력",
    "rte_pct": "왕복 효율",
    "soc_min_pct": "최소 충전율",
    "soc_max_pct": "최대 충전율",
    "backup_reserve_pct": "비상 대비 예비율",
    "eol_soh_pct": "수명 종료 잔존 성능",
    "cycles_per_year": "연간 사이클 수",
    "second_life": "재사용 배터리",
    "charge_source": "충전 전원",
    "mode_weights": "운전 방법별 가중치",
    "pv_surplus_profile_kwh": "태양광 잉여 프로파일",
    "capex_unit_won_per_kwh": "저장용량당 설치 단가",
    "replacement_unit_won_per_kwh": "저장용량당 교체 단가",
    "pcs_cost_won": "전력변환장치 비용",
    "pcs_lifetime": "전력변환장치 수명",
    "capex_extra_won": "추가 설치비",
    # ── 전기차(V2G) ──
    "vehicle_count": "차량 대수",
    "battery_kwh": "차량 배터리 용량",
    "max_charge_kw": "최대 충전 출력",
    "max_discharge_kw": "최대 방전 출력",
    "connect_start_hour": "접속 시작 시각",
    "connect_end_hour": "접속 종료 시각",
    "participation": "참여율",
    "available_dod": "가용 방전심도",
    "arrival_soc": "도착 시 충전상태",
    "min_departure_soc": "출발 시 최소 충전상태",
    "charge_efficiency": "충전 효율",
    "discharge_efficiency": "방전 효율",
    "charger_count": "충전기 수",
    "charger_unit_cost_won": "충전기 단가",
    "ancillary_cost_won": "충전기 부대공사비",
    "degradation_compensation_won_per_kwh": "배터리 열화 보상 단가",
    "replacement_cost_won": "교체 비용",
    "daily_charge_kwh": "일일 충전량",
    "discharge_benefit_enabled": "방전 편익 반영",
    "avoided_price_won_per_kwh": "회피 전력 단가",
    # ── 히트펌프 ──
    "rated_heat_kw": "정격 난방 출력",
    "cop_curve": "성능계수 곡선",
    "heat_load_kwh": "열부하",
    "aux_heater_kw": "보조 히터 용량",
    "annual_ambient_temp_c": "연간 외기온도",
    "default_ambient_temp_c": "기본 외기온도",
    "night_hours": "심야 시간대",
    "price_linked_hours": "가격 연동 운전 시간",
    # 값을 시간별로 받는 것과 한 값으로 받는 것이 갈린다 — 단위는 둘 다 원/kWh다.
    "price_profile_won_per_kwh": "시간별 전력 단가",
    "elec_price_won_per_kwh": "전력 구입 단가",
    "capex_unit_won_per_kw": "난방 출력당 설치 단가",
    "fixed_om_won": "고정 운영비",
    # `pump` 는 히트펌프가 아니라 **순환펌프**다 — 설비 자체의 수명은 `lifetime` 이다.
    "pump_lifetime": "순환펌프 수명",
    "pump_replacement_cost_won": "순환펌프 교체비",
    # ── 전기부하 · 열부하 ──
    "hourly_kwh": "시간별 사용량",
    "monthly_kwh": "월별 사용량",
    "shape": "표준 프로파일",
    "monthly_weights": "월별 가중치",
    "annual_growth_rate": "연간 수요 증가율",
    "unit_cost_won_per_kw": "용량당 설비 단가",
    "incidental_cost_won": "부대비",
    "heating_degree_days": "난방도일",
    "kwh_per_hdd": "난방도일당 사용량",
})


@dataclass(frozen=True)
class ParameterSpec:
    """자원 파라미터 하나. **카탈로그의 원소이고 「전체」의 단위다.**"""

    tag: str
    name: str
    #: 사람이 읽는 이름. **화면은 이것 하나만 읽는다** — 화면이 `LABEL_BY_NAME` 을
    #: 직접 조회하면 조회하는 자리가 여럿이 되고 그중 하나가 빠져도 조용하다.
    #: 선언되지 않았으면 빈 문자열이고, 그 수를 시험이 센다(⑤).
    label: str
    kind: ParameterKind
    unit: str
    required: bool
    default: Any
    type_text: str

    @property
    def default_text(self) -> str:
        """기본값의 표시 문면. 필수 인자는 기본값이 없다."""
        if self.required:
            return ""
        value = self.default
        if isinstance(value, Enum):
            return str(value.value)
        return "" if value is None else str(value)


def resource_parameters(
    tag: str, *, package: ModuleType | None = None
) -> tuple[ParameterSpec, ...]:
    """자원 한 종의 전체 파라미터 — 선언 순서 그대로.

    순서를 정렬하지 않는 이유: 생성자 선언 순서가 곧 저자가 정한 읽는 순서이고
    (필수 인자가 앞, 비용 인자가 뒤), 이름순으로 정렬하면 그 뜻이 사라진다.
    """
    registry = _registry(package)
    cls = registry.get(tag)
    if cls is None:
        raise ParameterCatalogueError(
            f"등록되지 않은 자원 종류입니다: {tag!r}. "
            f"등록된 종류: {', '.join(sorted(registry)) or '(없음)'}"
        )
    return parameters_of(cls)


def catalogue(*, package: ModuleType | None = None) -> dict[str, tuple[ParameterSpec, ...]]:
    """등록된 자원 전체의 파라미터 — `{tag: (ParameterSpec, …)}`.

    화면이 아니라 **기준**이다. 「전체 파라미터」를 주장하는 모든 검사가 여기를
    본다.
    """
    return {tag: parameters_of(cls) for tag, cls in sorted(_registry(package).items())}


def config_parameters(
    config: ModelConfig, *, package: ModuleType | None = None
) -> tuple[tuple[DERConfig, ParameterSpec], ...]:
    """**이 구성**의 전체 파라미터 — 자원 인스턴스마다 자기 종의 카탈로그를 편다.

    카탈로그는 종(種)에 대한 것이고 화면은 인스턴스에 대한 것이다. 같은 `PV` 를
    둘 놓으면 파라미터도 두 벌이며, 한 벌만 그리면 사용자는 둘째 자원의 값을
    고칠 방법이 없다.
    """
    rows: list[tuple[DERConfig, ParameterSpec]] = []
    for resource in config.resources:
        for spec in resource_parameters(resource.tag, package=package):
            rows.append((resource, spec))
    return tuple(rows)


def resolve_unit(name: str) -> str:
    """파라미터 이름에서 단위를 푼다. 풀리지 않으면 빈 문자열이다.

    **접미어를 먼저 본다.** 이름이 단위를 담고 있으면 그것이 정본이고,
    `UNIT_BY_NAME` 은 담고 있지 않은 이름만 다룬다 (모듈 독스트링 참조).
    """
    for suffix in sorted(UNIT_BY_SUFFIX, key=len, reverse=True):
        if name.endswith(suffix):
            return UNIT_BY_SUFFIX[suffix]
    return UNIT_BY_NAME.get(name, "")


def resolve_label(name: str) -> str:
    """파라미터 이름의 한국어 라벨. 선언되지 않았으면 **빈 문자열**이다.

    `resolve_unit()` 과 나란히 두었으나 **두 가지가 다르다**: 접미어를 보지 않고
    (모듈 독스트링 참조), 없다고 해서 카탈로그를 멈추게 하지 않는다. 라벨 부재는
    계산 오류가 아니므로 새 자원 하나가 앱 전체를 못 뜨게 만들 이유가 없다 —
    대신 빠진 수를 `tests/model/test_parameters.py` 가 센다.
    """
    return LABEL_BY_NAME.get(name, "")


def _registry(package: ModuleType | None) -> dict[str, type[DER]]:
    scanned = package if package is not None else core.der
    return discover(scanned, DER)  # type: ignore[type-abstract]


def parameters_of(cls: type, *, tag: str | None = None) -> tuple[ParameterSpec, ...]:
    """**클래스 하나**의 전체 파라미터. 레지스트리를 거치지 않는다.

    등록 여부와 무관하게 시그니처를 읽는 것이 이 함수다 — 그래서 새 자원을
    저장소에 놓기 전에도 「이 자원이 화면에 설 수 있는가」를 물을 수 있고,
    검사가 가짜 자원으로 거부 경로를 밟아 볼 수 있다.
    """
    resource_tag = tag if tag is not None else str(getattr(cls, "tag", cls.__name__))
    # **클래스를 그대로 넘긴다.** `cls.__init__` 를 넘기면 `self` 가 파라미터로
    # 섞이고(아래에서 다시 걸러야 한다), 인스턴스 속성 접근이라 mypy strict 가
    # 「하위 클래스의 것일 수 있다」로 잡는다. 클래스를 넘기면 둘 다 없다.
    signature = inspect.signature(cls, eval_str=True)
    specs: list[ParameterSpec] = []
    unresolved: list[str] = []

    for name, parameter in signature.parameters.items():
        if name == _SELF:
            continue
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise ParameterCatalogueError(
                f"자원 {resource_tag!r} 의 생성자가 {parameter} 를 받습니다 — 받는 이름을 "
                "열거할 수 없으므로 「전체 파라미터」를 말할 수 없습니다. "
                "고급 모드 화면(UI-1-AC1)은 열거한 것만 그릴 수 있고, 열거하지 "
                "못한 파라미터는 사용자가 그 값을 넣으려 할 때까지 어디에도 "
                "나타나지 않습니다. 인자를 이름으로 선언하십시오"
            )

        kind = _classify(parameter.annotation)
        unit = resolve_unit(name)
        if kind is ParameterKind.NUMBER and not unit:
            unresolved.append(name)
        specs.append(
            ParameterSpec(
                tag=resource_tag,
                name=name,
                label=resolve_label(name),
                kind=kind,
                unit=unit,
                required=parameter.default is inspect.Parameter.empty,
                default=None if parameter.default is inspect.Parameter.empty else parameter.default,
                type_text=_type_text(parameter.annotation),
            )
        )

    if unresolved:
        raise ParameterCatalogueError(
            f"자원 {resource_tag!r} 의 수치 파라미터 {', '.join(unresolved)} 의 단위를 알 수 "
            "없습니다. UI-2-AC1 은 「모든 수치 입력 옆에 단위 상시 표시」를 "
            "요구하므로, 단위를 모르는 채로 화면에 내보내면 단위 없는 입력이 "
            "생깁니다. 이름이 단위를 담게 고치거나(`_kw`·`_won_per_kwh` 처럼), "
            "담을 수 없는 뜻이라면 `UNIT_BY_NAME` 에 사유와 함께 선언하십시오"
        )
    return tuple(specs)


def _members(annotation: Any) -> tuple[Any, ...]:
    """`X | None` 같은 합집합을 풀어 `None` 을 뺀 구성원들."""
    if get_origin(annotation) in (Union, UnionType):
        return tuple(arg for arg in get_args(annotation) if arg is not type(None))
    return (annotation,)


def _classify(annotation: Any) -> ParameterKind:
    """주석에서 그리는 방법을 정한다.

    **합집합은 가장 넓은 쪽을 따른다.** `float | Sequence[float]`(히트펌프 열부하)
    처럼 수치도 시계열도 받는 인자를 수치 칸 하나로 그리면 시계열을 넣을 방법이
    사라지고, 그러면 그 자원은 「전체 파라미터」 화면에서 반쪽만 조작된다.
    """
    members = _members(annotation)
    if any(_is_non_scalar(member) for member in members):
        return (
            ParameterKind.SERIES
            if all(_is_number_series(member) for member in members if _is_non_scalar(member))
            else ParameterKind.STRUCTURED
        )
    if any(isinstance(member, type) and issubclass(member, Enum) for member in members):
        return ParameterKind.CHOICE
    if any(member is bool for member in members):
        return ParameterKind.TOGGLE
    if any(member in (int, float) for member in members):
        return ParameterKind.NUMBER
    return ParameterKind.TEXT


def _is_non_scalar(member: Any) -> bool:
    if get_origin(member) is not None:
        return True
    return isinstance(member, type) and not issubclass(
        member, int | float | bool | str | Enum
    )


def _is_number_series(member: Any) -> bool:
    """수치 열인가 — `Sequence[float]` 는 그렇고 `Sequence[Subcomponent]` 는 아니다."""
    if get_origin(member) is None:
        return False
    args = get_args(member)
    return bool(args) and all(arg in (int, float) for arg in args)


def _type_text(annotation: Any) -> str:
    """주석의 표시 문면 — 화면 도움말이 「무엇을 받는가」를 말할 때 쓴다."""
    if annotation is inspect.Parameter.empty:
        return ""
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("core.der.", "").replace("core.contracts.", "")
