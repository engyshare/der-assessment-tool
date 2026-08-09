import pytest

from core.assumption.timeseries import TimeSeriesBinding, TimeSeriesDataset, validate_csv_upload


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


@pytest.mark.req(
    "FR-905-AC1",
    "FR-905-AC2",
    "FR-905-AC3",
    "FR-905-AC4",
    "FR-905-AC5",
    "FR-905-AC6",
    "FR-905-AC7",
    "FR-905-AC8",
)
def test_timeseries_binding_and_preview() -> None:
    """시계열 바인딩·무중단 교체·미리보기 — AC1·AC2·AC3(부분) 검증.

    오라클: 순위 4 (정의 항등식) — ds1=[1.0]*8760, ds2=[2.0]*8760 이므로
    평균이 1.0·2.0 임은 자명하고 preview_swap 의 산식(old_mean/new_mean)을
    항등으로 확인한다.

    주의(INSPECT R1 I-3 에서 지적): 이 한 테스트가 FR-905-AC1~AC8 8개 조항을
    매핑하지만, 실제로 검증하는 것은 AC1(바인딩)·AC2(swap)·AC3(preview 일부)이며
    AC4~AC8(대체입력·색변환·CSV스키마검증·중복방지·출처메타) 은 구현·검증이
    없다. 다인자 마커가 2.15가 막으려던 상태와 같다 — 담당 구획이 분할해야 한다.
    """
    ds1 = TimeSeriesDataset(id="ds1", name="Original Dataset", data=[1.0]*8760)
    ds2 = TimeSeriesDataset(id="ds2", name="New Dataset", data=[2.0]*8760)

    binding = TimeSeriesBinding(instance_id="pv_01", dataset=ds1)

    assert binding.get_data()[0] == 1.0

    # 미리보기 (교체하지 않고 확인)
    preview = binding.preview_swap(ds2)
    assert preview["old_mean"] == 1.0
    assert preview["new_mean"] == 2.0

    # 무중단 교체
    binding.swap(ds2)
    assert binding.get_data()[0] == 2.0
