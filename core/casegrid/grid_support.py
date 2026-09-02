"""계통 급전 편익(`NWAs`·`CP`) 배선 — `core/casegrid/e2e_runner.py` 에서 R51/WP-7 이 옮겼다.

`e2e_runner.py` 는 `NFR-206` 코드 줄 상한(500)에 **정확히 걸려 있었다**(R51/WP-1
브리프 실측 — `PLR0915` statement 상한 50 도 함께). WP-5 가 `pv_allocation.py`
를 갈라낸 것과 같은 이유로, 이 배선을 그대로 그 파일 안에 넣으면 두 상한을
함께 넘긴다.

**REC 배선(`e2e_runner.py::_rec`)을 그대로 본보기로 따른다** — 새 설계가
아니다. `NWAs`·`CP` 도 R48 이래 클래스만 있었고 실행 경로에서 부르는 자리가
0곳이었다(`.orch/R51/result_4.md` — 「받을 자리가 없었다」). 사용자 판정 §3
(`docs/decisions-2026-09-01-R51.md` — *「배터리의 운영방식은 … 한전에 도움을
주는 용도로도 사용할 수 있어야 함」*)이 그 자리를 요구한다.
"""
from __future__ import annotations

from core.der.ess import ESS, ESSOperatingMode
from core.valuestream import CapacityPayment, NWAs


def _nwas(*, contribution_price_won_per_kwh: float, enabled: bool) -> NWAs:
    """★★ `NWAs` 인스턴스 — `e2e_runner.py::_rec` 와 같은 형태.

    단가가 0 이면(`docs/assumptions.yaml::benefit.nwas_price` · `track:
    default0`) 켜져도 0원이다 — 그것이 결함이 아니라 대장의 판정이다(사용자
    판정 §3 ⚠ — *「제도가 없기 때문이며, 기본값을 켜면 없는 제도 위에 편익을
    쌓아 필요 지원액을 과소 산정하게 된다」*).
    """
    return NWAs(contribution_price_won_per_kwh=contribution_price_won_per_kwh, enabled=enabled)


def _cp(
    *,
    registered_capacity_kw: float,
    capacity_price_won_per_kw_month: float,
    enabled: bool,
) -> CapacityPayment:
    """★★ `CapacityPayment` 인스턴스 — `_nwas()` 와 같은 이유로 뗀다.

    ⚠ **등록 용량은 호출부가 `ess.power_kw` 를 넘긴다** — 설계 변수가 아니라
    이 사업 모델의 ESS 정격출력이다(`e2e_runner.py::ESS_POWER_KW` 옆 주석).
    """
    return CapacityPayment(
        registered_capacity_kw=registered_capacity_kw,
        capacity_price_won_per_kw_month=capacity_price_won_per_kw_month,
        enabled=enabled,
    )


def _resolve_nwas_cp(
    ess: ESS, nwas_price_won_per_kwh: float, cp_price_won_per_kw_month: float
) -> tuple[NWAs, CapacityPayment]:
    """`NWAs`·`CP` 활성화 여부를 **세운 자원에서** 읽고 인스턴스 둘을 짓는다.

    ⚠ **`ess.operating_mode` 를 읽는다 — 호출부가 넘긴 원시 인자를 다시 보지
    않는다.** `e2e_runner.py::_site_load_kw`·`_resource_lines` 가 이미 지킨
    원칙과 같다(「세운 자원에서 읽는다」) — 세운 자원과 다른 값을 다시 판단하면
    두 벌이 되어 어긋날 수 있다.

    ⚠ **한 실행에서 「계통 방전」·「준중앙급전 등록」을 동시에 고를 통로가
    `run_single_case_e2e` 에는 없다** — `ess_operating_mode` 인자가 하나뿐이고
    `mode_weights`(혼합)를 그 함수가 넘기지 않는다. 그러므로 `nwas_enabled`·
    `cp_enabled` 가 함께 `True` 가 되는 일은 이 통로에서 일어나지 않는다 —
    혼합 모드로 함께 켜는 경우의 배타는 `ESS.value_streams()` 독스트링이 적어
    둔 별개 자리이며 이 함수의 범위 밖이다.
    """
    nwas_enabled = ess.operating_mode == ESSOperatingMode.GRID_DISCHARGE
    cp_enabled = ess.operating_mode == ESSOperatingMode.SEMI_CENTRAL_DISPATCH
    return (
        _nwas(contribution_price_won_per_kwh=nwas_price_won_per_kwh, enabled=nwas_enabled),
        _cp(
            registered_capacity_kw=ess.power_kw,
            capacity_price_won_per_kw_month=cp_price_won_per_kw_month,
            enabled=cp_enabled,
        ),
    )


#: 방식 「나」(배전망 사업자 지시)의 운전 방법 둘 — 사용자 판정 §1
#: (`docs/decisions-2026-09-02-R54.md`). `PeakShaving` 은 방식 「가」의 편익이므로
#: 이 모드들에서는 **애초에 만들지 않는다**(값 0 인 채 태그만 서는 것이 아니다).
#:
#: **`frozenset` 인 이유 (`NFR-205`).** `_MODE_WINDOWS` 가 `MappingProxyType`
#: 인 것과 같은 이유다 — 평범한 `set` 은 모듈 수준 가변 상태이며, 케이스 그리드
#: 병렬 실행에서 한 번의 변형이 다른 케이스의 결과를 조용히 바꾼다.
GRID_DIRECTED_MODES: frozenset[ESSOperatingMode] = frozenset(
    {ESSOperatingMode.GRID_DISCHARGE, ESSOperatingMode.SEMI_CENTRAL_DISPATCH}
)


def peak_shaving_enabled(ess: ESS) -> bool:
    """`PeakShaving` 을 켤지 — 방식 「가」만 켠다 (사용자 판정 §1 · R54).

    ⚠ **`ess.operating_mode` 를 읽는다 — 호출부의 원시 인자를 다시 보지
    않는다.** `_resolve_nwas_cp()` 가 독스트링에 적어 둔 원칙과 같다(「세운
    자원에서 읽는다」) — 호출부가 넘긴 인자로 다시 판단하면 두 벌이 되어
    어긋날 수 있다.

    ⚠ **`HYBRID`(혼합)는 `True` 다 — 건드리지 않는다.** 혼합 모드에서
    `NWAs`·`CP` 와 `PeakShaving` 이 함께 켜지는 경우의 배타는
    `ESS.value_streams()` 독스트링이 적어 둔 별개 자리이며 이 함수의 범위
    밖이다(사용자 판정 §1 ⚠ — 혼합을 함께 끄면 결론축이 움직일 수 있다).
    """
    return ess.operating_mode not in GRID_DIRECTED_MODES
