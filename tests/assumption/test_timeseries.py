from datetime import date

import pytest

from core.assumption.item import ConfidenceLevel
from core.assumption.timeseries import TimeSeriesBinding, TimeSeriesDataset, validate_csv_upload
from core.assumption.timeseries_estimate import estimate_from_monthly_usage
from core.assumption.timeseries_explore import TimeSeriesExploreAxis
from core.assumption.timeseries_registry import DatasetInUseError, TimeSeriesDatasetRegistry
from core.assumption.timeseries_validation import (
    TimeSeriesMissingValueError,
    TimeSeriesSchemaError,
    validate_and_summarize,
)


@pytest.mark.req("NFR-404-AC1")
def test_csv_upload_validation() -> None:
    """CSV 업로드 검증 — MIME·크기(10MB)·행수(100,000) 상한 위반을 거부.

    오라클: 순위 4 (정의 항등식) — 상한값 자체가 명세이므로 한계값 포함·초과를
    경계 케이스로 직접 검증한다.
    """
    # MIME 검증
    with pytest.raises(ValueError, match="MIME type"):
        validate_csv_upload(b"content", size_bytes=100, mime_type="application/pdf", line_count=10)

    # 크기 검증 (10MB)
    with pytest.raises(ValueError, match="10MB"):
        validate_csv_upload(
            b"content", size_bytes=11 * 1024 * 1024, mime_type="text/csv", line_count=10
        )

    # 행수 검증 (100,000행)
    with pytest.raises(ValueError, match="100,000"):
        validate_csv_upload(b"content", size_bytes=100, mime_type="text/csv", line_count=100001)

    # 정상
    assert (
        validate_csv_upload(b"content", size_bytes=100, mime_type="text/csv", line_count=100)
        is True
    )


@pytest.mark.req("FR-905-AC1", "FR-905-AC2")
def test_timeseries_binding_and_swap() -> None:
    """인스턴스 단위 바인딩과 무중단 교체 — AC1·AC2.

    오라클: 순위 4 (정의 항등식) — ds1=[1.0]*8760, ds2=[2.0]*8760 이므로
    바인딩·교체가 참조 자체를 바꾸는지를 첫 원소 값으로 직접 확인한다.
    """
    ds1 = TimeSeriesDataset(id="ds1", name="Original Dataset", data=[1.0] * 8760)
    ds2 = TimeSeriesDataset(id="ds2", name="New Dataset", data=[2.0] * 8760)

    binding = TimeSeriesBinding(instance_id="pv_01", dataset=ds1)
    assert binding.get_data()[0] == 1.0

    binding.swap(ds2)
    assert binding.get_data()[0] == 2.0


@pytest.mark.req("FR-905-AC3")
def test_timeseries_preview_swap_shows_expected_change() -> None:
    """교체 영향 미리보기 — 재실행 전에 평균 변화가 보여야 한다 (AC3).

    오라클: 순위 4 (정의 항등식) — preview_swap 의 산식(old_mean/new_mean)을
    항등으로 확인한다. 미리보기는 실제 교체를 일으키지 않는다.
    """
    ds1 = TimeSeriesDataset(id="ds1", name="Original Dataset", data=[1.0] * 8760)
    ds2 = TimeSeriesDataset(id="ds2", name="New Dataset", data=[2.0] * 8760)
    binding = TimeSeriesBinding(instance_id="pv_01", dataset=ds1)

    preview = binding.preview_swap(ds2)
    assert preview["old_mean"] == 1.0
    assert preview["new_mean"] == 2.0
    # 미리보기는 교체하지 않는다
    assert binding.get_data()[0] == 1.0


@pytest.mark.req("FR-905-AC4")
def test_timeseries_estimate_from_monthly_usage_when_no_measured_series() -> None:
    """8760 실측 시계열이 없을 때 월사용량 + 표준 프로파일로 대체 입력 (AC4).

    오라클: 순위 1 (해석해) — 균등 프로파일([1/24]*24)이면 매시간 값은
    월사용량/일수/24 로 등속이다. 1월(31일) 총 744kWh → 시간당
    744 / 31 / 24 = 1.0kWh.
    """
    monthly = [744.0] + [0.0] * 11  # 1월만 744kWh, 나머지 0
    flat_profile = [1.0 / 24] * 24

    ds = estimate_from_monthly_usage(
        "est-2026", "2026년 추정", monthly, flat_profile
    )

    assert ds.is_estimated is True
    assert len(ds.data) == 8760
    # 1월 매 시간 등속값 = 744 / 31일 / 24시간 = 1.0
    assert ds.data[0] == pytest.approx(1.0)
    assert ds.data[31 * 24 - 1] == pytest.approx(1.0)
    # 2월은 전량 0kWh였으므로 2월 첫 시간은 0
    feb_first_hour = 31 * 24
    assert ds.data[feb_first_hour] == pytest.approx(0.0)

    # 나중에 실측 시계열로 교체 가능 — 기존 swap() 경로 그대로 쓴다
    binding = TimeSeriesBinding(instance_id="load_01", dataset=ds)
    measured = TimeSeriesDataset(id="measured-2026", name="실측", data=[2.0] * 8760)
    binding.swap(measured)
    assert binding.get_data()[0] == 2.0


@pytest.mark.req("FR-905-AC5")
def test_timeseries_explore_axis_groups_year_variants_for_comparison() -> None:
    """데이터셋을 케이스 그리드 탐색 변수로 지정 — 여러 연도 시계열 비교 (AC5).

    오라클: 순위 4 (정의 항등식) — 축이 등록한 id 목록·선택 결과가 생성 시
    넘긴 데이터셋과 그대로 일치하는지 본다.
    """
    ds_2024 = TimeSeriesDataset(id="load-2024", name="2024년 부하", data=[1.0] * 8760)
    ds_2025 = TimeSeriesDataset(id="load-2025", name="2025년 부하", data=[1.1] * 8760)

    axis = TimeSeriesExploreAxis(tag="load_by_year", datasets=(ds_2024, ds_2025))

    assert axis.dataset_ids() == ("load-2024", "load-2025")
    assert axis.select("load-2025") is ds_2025

    with pytest.raises(KeyError):
        axis.select("load-2026")

    # 중복 id 는 탐색 변수를 만들 수 없다 — 어느 것을 골랐는지 알 수 없다
    with pytest.raises(ValueError, match="중복"):
        TimeSeriesExploreAxis(tag="dup", datasets=(ds_2024, ds_2024))


@pytest.mark.req("FR-905-AC6")
def test_timeseries_csv_schema_and_row_count_are_validated() -> None:
    """CSV 스키마·행수 검증 — 열 구성이나 행수가 다르면 거부한다 (AC6).

    오라클: 순위 4 (정의 항등식) — EXPECTED_COLUMNS·expected_row_count 와의
    불일치가 그대로 예외로 이어지는지 본다.
    """
    with pytest.raises(TimeSeriesSchemaError, match="열 구성"):
        validate_and_summarize(
            ["time", "value"],  # 기대: ("timestamp", "value")
            [1.0, 2.0],
            expected_row_count=2,
            missing_policy="error",
            outlier_z_threshold=3.0,
        )

    with pytest.raises(TimeSeriesSchemaError, match="행수"):
        validate_and_summarize(
            ["timestamp", "value"],
            [1.0, 2.0],
            expected_row_count=3,
            missing_policy="error",
            outlier_z_threshold=3.0,
        )


@pytest.mark.req("FR-905-AC6")
def test_timeseries_csv_missing_value_policy_is_selectable() -> None:
    """결측 처리 방식(선형보간/전월 평균/오류)을 선택할 수 있다 (AC6 후단).

    오라클: 순위 1 (해석해) — 선형보간은 좌우 실값의 평균([10, ?, 30] →
    20), 전월(직전창) 평균은 직전 3개 값의 평균([10,10,10, ?] → 10),
    오류 방식은 결측이 있으면 예외로 멈춘다.
    """
    interpolated, _ = validate_and_summarize(
        ["timestamp", "value"],
        [10.0, None, 30.0, 40.0],
        expected_row_count=4,
        missing_policy="interpolate",
        outlier_z_threshold=3.0,
    )
    assert interpolated == [10.0, 20.0, 30.0, 40.0]

    window_filled, _ = validate_and_summarize(
        ["timestamp", "value"],
        [10.0, 10.0, 10.0, None, 10.0],
        expected_row_count=5,
        missing_policy="prior_month_mean",
        outlier_z_threshold=3.0,
        window_size=3,
    )
    assert window_filled == [10.0, 10.0, 10.0, 10.0, 10.0]

    with pytest.raises(TimeSeriesMissingValueError, match="1건"):
        validate_and_summarize(
            ["timestamp", "value"],
            [10.0, None, 30.0],
            expected_row_count=3,
            missing_policy="error",
            outlier_z_threshold=3.0,
        )


@pytest.mark.req("FR-905-AC6")
def test_timeseries_csv_outlier_detection_and_summary_stats() -> None:
    """이상치 검증과 요약 통계 표시 (AC6 전단).

    오라클: 순위 1 (해석해) — [0,0,0,0,100] 의 평균은 20, 모집단 표준편차는
    sqrt(1600)=40. 100의 z점수는 (100-20)/40=2.0으로 임계값 1.5를 넘는
    유일한 값이다. 나머지 네 값의 z점수는 -0.5로 임계값 미달.
    """
    filled, summary = validate_and_summarize(
        ["timestamp", "value"],
        [0.0, 0.0, 0.0, 0.0, 100.0],
        expected_row_count=5,
        missing_policy="error",
        outlier_z_threshold=1.5,
    )
    assert filled == [0.0, 0.0, 0.0, 0.0, 100.0]
    assert summary.row_count == 5
    assert summary.missing_count == 0
    assert summary.outlier_count == 1
    assert summary.mean == pytest.approx(20.0)
    assert summary.minimum == 0.0
    assert summary.maximum == 100.0


@pytest.mark.req("FR-905-AC7")
def test_timeseries_registry_dedup_share_and_delete_guard() -> None:
    """공유 참조·중복 저장 방지, 삭제 시 참조 시나리오 안내 (AC7).

    오라클: 순위 4 (정의 항등식) — 같은 id 를 두 번 등록해도 저장 개수는
    1이며, 참조가 남아 있으면 삭제가 거부되고 참조자 이름이 메시지에
    나온다.
    """
    registry = TimeSeriesDatasetRegistry()
    ds = TimeSeriesDataset(id="shared-ds", name="공유 데이터셋", data=[1.0] * 8760)

    registry.register(ds)
    registry.register(ds)  # 같은 id 재등록 — 중복 저장되지 않는다
    assert registry.count() == 1

    registry.bind("shared-ds", "scenario_A")
    registry.bind("shared-ds", "scenario_B")
    assert registry.referencing_scenarios("shared-ds") == frozenset(
        {"scenario_A", "scenario_B"}
    )

    with pytest.raises(DatasetInUseError, match="scenario_A"):
        registry.delete("shared-ds")

    registry.unbind("shared-ds", "scenario_A")
    registry.unbind("shared-ds", "scenario_B")
    registry.delete("shared-ds")  # 참조가 없으면 삭제된다
    assert registry.count() == 0


@pytest.mark.req("FR-905-AC8")
def test_timeseries_source_metadata_5_fields_and_report_display() -> None:
    """출처 메타데이터 5종을 보유하고 리포트에 표기한다 (AC8).

    오라클: 순위 4 (정의 항등식) — source_metadata() 가 필드값을 그대로
    반영하는지, 미보유 필드는 「미보유」로 명시되는지 본다.
    """
    ds = TimeSeriesDataset(
        id="load-2026",
        name="2026년 실측 부하",
        data=[1.0] * 8760,
        source="한전 스마트미터 원자료",
        measurement_period="2026-01-01 ~ 2026-12-31",
        resolution="1시간",
        confidence=ConfidenceLevel.CONFIRMED,
        verified_at=date(2026, 8, 8),
    )

    meta = ds.source_metadata()
    assert meta["출처"] == "한전 스마트미터 원자료"
    assert meta["계측기간"] == "2026-01-01 ~ 2026-12-31"
    assert meta["해상도"] == "1시간"
    assert meta["신뢰도"] == "확정"
    assert meta["최종확인일"] == "2026-08-08"

    # 메타데이터를 보유하지 않은 데이터셋은 "빈칸"이 아니라 "미보유"로 표시된다
    bare = TimeSeriesDataset(id="bare", name="메타 없음", data=[0.0] * 8760)
    bare_meta = bare.source_metadata()
    assert all(v == "미보유" for v in bare_meta.values())
