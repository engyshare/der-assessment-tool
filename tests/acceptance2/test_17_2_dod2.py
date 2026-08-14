"""17.2 DoD 2 — 종단 27케이스 90초 이내 실행 + 히트맵 생성 (SG-2).

이 테스트는 실제 DER → Engine → Benefit → CBA 파이프라인을 27케이스에 대해
실행하고 소요 시간을 잰다. 기준 환경은 CPU 1코어 · 메모리 512MB이나,
이 테스트가 돌아가는 환경은 그보다 좋을 수 있으므로 실측 환경을 함께 기록한다.

`tests/acceptance/test_phase1_dod.py` 의 `test_dod2_casegrid_27cases_performance_and_heatmap`
는 가짜 lambda 주입으로 그리드 자체의 성능(케이스 생성·수집·병렬)만 잰다.
이것과는 독립된 측정이다 — 이 테스트가 17.2 판정이고, 저것은 그리드 성능
벤치마크이다.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from core.assumption.provider import AssumptionSet
from core.casegrid import feasible_region, quick_preset_grid, run_cases
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.report.variant_report import build_variant_table

THRESHOLD_SECONDS = 90.0

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS_YAML = _REPO_ROOT / "docs" / "assumptions.yaml"

# ★ **수준표를 만드는 코드가 여기 있었다 (R33).** 대장을 읽어 `level_map` 을
# 만드는 것은 **배포 경로가 해야 하는 일**인데 그 코드가 이 파일 안에만
# 있었다 — 즉 「대장이 정본이다」가 이 인수 테스트가 도는 동안에만 성립했고,
# 러너를 부르는 배포 코드에는 대장을 읽는 자리가 아예 없었다.
# 지금 소유자는 `core/casegrid/ledger_levels.py` 이며 여기서는 그것을 쓴다 —
# 사본을 남기면 대장 스키마가 바뀔 때 한쪽만 고쳐진다.

@pytest.mark.req("FR-801-AC7.quick", "FR-803-AC1")
def test_dod2_e2e_27cases_within_90s_with_environment() -> None:
    """17.2 DoD 2: 종단 파이프라인 27케이스 90초 이내 (SG-2).

    손계산 기대값:
    - quick_preset_grid 는 결합 3수준 × 3수준 × 3수준 = 27 케이스를 생성함.
    - 각 케이스는 PV + ESS 자원 생성 → RuleBasedEngine 디스패치
      → SurplusSale + PeakShaving 편익 산출 → 프로포마 → NPV/회수기간.
    - 금액 파라미터(PV/ESS 단가)는 docs/assumptions.yaml 의 sensitivity 에서
      읽으므로 대장 갱신 시 자동 반영됨 (NFR-202).
    - 27케이스 전체 소요 시간을 실측하고 90.0초와 비교.
    - 환경(CPU 코어 수)을 함께 기록하여 기준 환경과의 차이를 판단 가능하게 함.
    """
    grid = quick_preset_grid()
    cases = grid.generate()
    assert len(cases) == 27

    level_map = build_level_map(_ASSUMPTIONS_YAML)
    cpu_count = os.cpu_count() or 1

    # ★ **분석기간을 대장에서 읽는다 (R31).** 종전에는 러너의 모듈 상수
    # `HORIZON_YEARS = 20` 이 이 값이었는데, §7.1 O-1 은 소유자를
    # `AssumptionSet` 으로 못 박고 있었다 — 소유자는 정해져 있고 값만 다른 층에
    # 있던 상태다. 여기서 대장을 지나게 하는 것이 그 배선의 실물 확인이다.
    horizon_years = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS_YAML)).analysis_years()
    assert horizon_years >= 1

    start_time = time.perf_counter()

    results = run_cases(
        cases,
        lambda case: run_single_case_e2e(
            case.values, level_map=level_map, horizon_years=horizon_years
        ),
    )

    elapsed = time.perf_counter() - start_time

    # 결과가 전건 NPV 값을 가졌는지 확인 (파이프라인이 실제로 돌았는가)
    assert len(results) == 27
    for r in results:
        assert "npv" in r.metrics, (
            f"케이스 {r.case_index}: 파이프라인이 NPV를 반환하지 않았습니다"
        )
        # ★ **변형 표가 실제 실행 결과로 선다 (FR-607-AC1 · R32).** 여기가 이
        # 저장소의 실제 종단 실행 경로이므로, 「모든 실행에서 자동 포함」은 이
        # 27건에서 성립해야 한다. R31 까지는 이 자리에서 표를 부르면
        # `ValidationError`(변형별 결과가 없습니다)가 났다 — 기계는 옳게
        # 거부하는데 아무도 부르지 않는 상태였다.
        assert build_variant_table(r).baseline_row.baseline is True, (
            f"케이스 {r.case_index}: 변형 표의 맨 위가 기준선이 아닙니다"
        )

    # 히트맵 셀 매트릭스 생성 검증
    cells = feasible_region(
        results, x="discount_rate", y="tariff_escalation", metric="npv", target=0.0
    )
    assert len(cells) > 0

    # 성능 판정 — 90초 초과여도 assert로 기록하여 CI에서 확인 가능하게 함.
    passed = elapsed < THRESHOLD_SECONDS
    assert passed, (
        f"17.2 DoD 2 실패: 종단 27케이스 {elapsed:.2f}초 >= {THRESHOLD_SECONDS}초 "
        f"(CPU {cpu_count}코어)"
    )
