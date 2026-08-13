"""3.4 — Parquet 시계열 저장소 + 체크섬.

**이 테스트의 핵심**: 「썼다」가 아니라 「읽은 것이 쓴 것과 같다」를 검증한다.
Parquet 은 조용히 성공하는 경로가 많다 — 메타데이터가 깨져도 빈 DataFrame 을
돌려주는 경우가 있고, 그것은 에러로 보이지 않는다.

그래서 세 종류의 검사를 한다:
    1. 라운드트립 — 쓴 DataFrame 을 읽어 값이 같은지 비교.
    2. 체크섬 — 쓸 때 받은 checksum 으로 읽을 때 검증.
    3. 변조 검출 — COMMON.md §8. 1바이트를 바꿔 checksum 이 실제로 변하는지.

오라클: 4 순위(항등식) — checksum 은 정의상 같은 파일에 같은 값.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from core.contracts.units import HOURS_PER_LEAP_YEAR, LEAP_YEAR_POLICY
from core.contracts.validation import ValidationError
from infra.tsstore import (
    ALLOWED_ROW_COUNTS,
    CURRENT_FORMAT_VERSION,
    TS_KINDS,
    TimeSeriesIntegrityError,
    TimeSeriesShapeError,
    compute_checksum,
    parse_meta,
    read_series,
    write_series,
)


#: 8760 행짜리 테스트용 부하 시계열. 계절 패턴을 흉내 낸 단순 사인파.
def _synthetic_load(year: int = 2024) -> pa.Table:
    import math

    n = 8760
    vals = [100.0 + 50.0 * math.sin(2 * math.pi * h / 24) for h in range(n)]
    return pa.table({"load_kw": pa.array(vals, type=pa.float64())})


def _synthetic_smp(year: int = 2024) -> pa.Table:
    n = 8760
    # SMP: 낮에 높고 밤에 낮음
    vals = [80.0 + 40.0 * ((h % 24) > 7 and (h % 24) < 22) for h in range(n)]
    return pa.table({"smp_krw_per_kwh": pa.array(vals, type=pa.float64())})


# ── 라운드트립: 읽은 것이 쓴 것과 같다 ─────────────────────────────────


def test_roundtrip_preserves_values(tmp_path: Path) -> None:
    """쓴 시계열을 읽어 값·행 수·컬럼이 같은지 비교."""
    src = _synthetic_load()
    path = tmp_path / "load_2024.parquet"

    checksum = write_series(path, src, kind="load", year=2024)
    read_back = read_series(path, expected_checksum=checksum)

    assert read_back.num_columns == src.num_columns
    assert read_back.num_rows == src.num_rows == 8760
    # 값 비교 — pyarrow 의 column equals.
    assert read_back.column(0).equals(src.column(0)), (
        "읽은 값이 쓴 값과 다릅니다 — Parquet writer/reader 가 손실을 일으켰거나 "
        "체크섬이 메타데이터만 검사하고 본문은 무시하고 있습니다."
    )


def test_checksum_matches_compute_checksum(tmp_path: Path) -> None:
    """write_series 가 반환한 checksum 이 compute_checksum 과 일치한다."""
    path = tmp_path / "smp.parquet"
    returned = write_series(path, _synthetic_smp(), kind="smp", year=2024)
    direct = compute_checksum(path)
    assert returned == direct
    # 형식: SHA256 hex (64자).
    assert len(returned) == 64
    int(returned, 16)  # hex 파싱이 되어야 정상


# ── COMMON.md §8 — 변조를 심어 체크섬이 잡는가 ─────────────────────────


def test_checksum_detects_byte_modification(tmp_path: Path) -> None:
    """1바이트를 바꿨을 때 체크섬이 달라지고 read_series 가 거부하는지 확인.

    Parquet 의 치명적 함정: 메타데이터가 부분 손상되어도 빈 DataFrame 을
    돌려주며 종료 코드 0 인 경로가 있다. 체크섬이 그것을 잡아야 한다.
    """
    path = tmp_path / "pv.parquet"
    table = pa.table({"pv_kw": pa.array([1.0 * h for h in range(8760)])})
    original_checksum = write_series(path, table, kind="pv", year=2024)

    # 파일 끝의 1바이트를 뒤집는다. Parquet footer 가 깨지면서 read 가 에러를
    # 내거나, 정상 읽기가 되더라도 checksum 이 달라져야 한다.
    with Path(path).open("r+b") as f:
        f.seek(-1, 2)  # 끝에서 1바이트 전
        original_byte = f.read(1)
        flipped = bytes([original_byte[0] ^ 0xFF])
        f.seek(-1, 2)
        f.write(flipped)

    modified_checksum = compute_checksum(path)
    assert modified_checksum != original_checksum, (
        "1바이트를 뒤집었는데 checksum 이 같습니다 — compute_checksum 이 "
        "파일을 실제로 읽지 않고 있을 수 있습니다."
    )

    with pytest.raises(TimeSeriesIntegrityError, match="체크섬 불일치"):
        read_series(path, expected_checksum=original_checksum)


def test_read_without_checksum_does_not_verify(tmp_path: Path) -> None:
    """expected_checksum 없는 read 는 검증을 건너뛴다 — 호출부 책임.

    이 테스트는 read_series 의 *기본 동작* 을 고정한다. 호출부가 checksum 을
    넘기지 않으면 read 는 값을 돌려준다 — 검증은 opt-in 이다. 이 정책이
    바뀌면 백업·복원 루틴이 깨지므로 여기 고정해 둔다.
    """
    path = tmp_path / "load.parquet"
    write_series(path, _synthetic_load(), kind="load", year=2024)
    table = read_series(path)  # expected_checksum 없음
    assert table.num_rows == 8760


# ── DV-4 — 행 수 강제 ──────────────────────────────────────────────────


def test_write_rejects_wrong_row_count(tmp_path: Path) -> None:
    """8760 또는 35040 이 아닌 행 수를 거부한다 — DV-4.

    임의 해상도를 허용하면 잘린 시계열이 "그런 해상도인가 보다" 로 통과한다.
    """
    path = tmp_path / "bad.parquet"
    bad = pa.table({"x": pa.array([1.0] * 100)})  # 100행 — 허용 아님

    with pytest.raises(TimeSeriesShapeError, match="8760"):
        write_series(path, bad, kind="load", year=2024)

    assert path.exists() is False, (
        "거부된 쓰기가 파일을 남겼습니다 — write_series 가 검사 전에 디스크를 "
        "건드리고 있습니다."
    )


@pytest.mark.req("NFR-303-M1")
def test_write_rejects_wrong_row_count_carries_field_reason_action(
    tmp_path: Path,
) -> None:
    """NFR-303 — DV-4 위반은 필드·사유·조치 3요소를 구조로 갖고 rule="DV-4" 다.

    `TimeSeriesShapeError` 는 그대로 유지된다 — `ValidationError` 를 상속하게
    바꿨을 뿐이다. 기존 `except TimeSeriesShapeError` 호출부가 계속 잡는지는
    `test_write_rejects_wrong_row_count` 가 이미 고정하고 있고, 여기서는
    그 예외가 **동시에** `ValidationError` 이며 3요소를 갖는지를 본다.
    """
    path = tmp_path / "bad2.parquet"
    bad = pa.table({"x": pa.array([1.0] * 100)})  # 100행 — 허용 아님

    with pytest.raises(ValidationError) as exc_info:
        write_series(path, bad, kind="load", year=2024)

    err = exc_info.value
    assert isinstance(err, TimeSeriesShapeError), (
        "기존 except TimeSeriesShapeError 호출부가 더는 못 잡습니다."
    )
    assert err.field == "timeseries.rows"
    assert "100" in err.reason, "사유에 실제 행 수(100)가 없습니다"
    assert "8760" in err.action and "35040" in err.action, (
        "조치에 허용 행 수(8760, 35040)가 없습니다 — 「값을 고치십시오」류의 "
        "공허한 문장이면 안 됩니다"
    )
    assert err.rule == "DV-4"


def test_write_rejects_unknown_kind(tmp_path: Path) -> None:
    """kind CHECK 제약과 동일 — DB 를 거치지 않고도 시계열 저장이 종류를 강제."""
    path = tmp_path / "x.parquet"
    with pytest.raises(ValueError, match="지원하지 않는 시계열 종류"):
        write_series(path, _synthetic_load(), kind="unknown_kind", year=2024)


@pytest.mark.req("NFR-303-M1")
def test_write_rejects_unknown_kind_carries_field_reason_action(
    tmp_path: Path,
) -> None:
    """NFR-303 — kind 위반은 필드·사유·조치 3요소를 구조로 갖는다.

    「예외가 났다」만 보면 셋이 실제로 이 위반에 맞는 내용인지 알 수 없다.
    각 칸을 따로 단언한다 — action 은 허용값 목록을 담아야 한다(공허한
    "값을 고치십시오" 이면 안 됨). 이 규칙은 §7.3 대장(DV-N) 밖의 일반
    입력 검증이므로 rule 은 비운다.
    """
    path = tmp_path / "x.parquet"
    with pytest.raises(ValidationError) as exc_info:
        write_series(path, _synthetic_load(), kind="unknown_kind", year=2024)

    err = exc_info.value
    assert err.field == "timeseries.kind"
    assert "unknown_kind" in err.reason, "사유에 실제로 위반한 값이 없습니다"
    for allowed in sorted(TS_KINDS):
        assert allowed in err.action, f"조치에 허용값 {allowed!r} 이 없습니다"
    assert err.rule is None, "kind 검증은 §7.3 대장 밖이므로 rule 이 비어야 합니다"


@pytest.mark.parametrize("allowed", sorted(ALLOWED_ROW_COUNTS))
def test_write_accepts_both_supported_resolutions(
    tmp_path: Path, allowed: int
) -> None:
    """8760(1시간) 과 35040(15분) 둘 다 받는다."""
    path = tmp_path / f"res_{allowed}.parquet"
    table = pa.table({"v": pa.array([1.0] * allowed)})
    checksum = write_series(path, table, kind="temp", year=2024)
    assert len(checksum) == 64


# ── 메타데이터 — 파일 단독 복구 ────────────────────────────────────────


def test_metadata_embeds_kind_year_and_format(tmp_path: Path) -> None:
    """파일 메타데이터에 kind·year·format_version 이 새겨진다.

    DB 가 날아가도 파일만 있으면 무엇인지 알 수 있어야 한다 — 그래서 Parquet
    자체 메타데이터에 식별 정보를 새긴다. parse_meta 로 꺼낸다.
    """
    path = tmp_path / "load_meta.parquet"
    write_series(path, _synthetic_load(), kind="load", year=2024)

    table = read_series(path)
    meta = parse_meta(table)
    assert meta.get("der_kind") == "load"
    assert meta.get("der_year") == "2024"
    assert meta.get("der_format_version") == str(CURRENT_FORMAT_VERSION)


# ── COMMON.md §8 반대 — checksum 자체가 올바른가 ───────────────────────


def test_checksum_is_actually_sha256_of_file_bytes(tmp_path: Path) -> None:
    """compute_checksum 이 hashlib.sha256 과 동일한 값을 내는지 직접 대조.

    compute_checksum 이 잘못된 알고리즘을 쓰거나 일부 바이트만 읽으면, 변조
    검출 테스트는 통과하지만 checksum 은 의미 없는 값이다. 독립 구현과
    대조한다 — COMMON.md §7 「교차 구현 대조」 (4 순위 항등식).
    """
    path = tmp_path / "load.parquet"
    write_series(path, _synthetic_load(), kind="load", year=2024)

    raw_bytes = Path(path).read_bytes()
    expected = hashlib.sha256(raw_bytes).hexdigest()
    assert compute_checksum(path) == expected, (
        "compute_checksum 이 hashlib.sha256(file_bytes) 와 다릅니다 — "
        "chunked read 가 drop 하거나 알고리즘이 다릅니다."
    )


# ── DV-4 후반부 — 윤년 처리 규칙이 **사용자에게 닿는가** ────────────────────
#
# 규칙의 선언과 그것이 참인지는 `tests/contract/test_leap_year_policy.py` 가
# 붙든다. 여기서 보는 것은 **선언이 닿는가** — 366일 자료를 가져온 사람이
# 그 문면을 실제로 받는가다. 닿지 않는 선언은 주석과 다르지 않다.


@pytest.mark.req("NFR-303-M1")
def test_write_rejects_leap_year_rows_and_hands_over_the_policy(
    tmp_path: Path,
) -> None:
    """366일 시계열은 「잘린 자료」가 아니라 **규약이 다른 자료**다.

    같은 문장으로 거절하면 사용자는 자기 8784행이 온전한데 왜 거부되는지 알 수
    없고, 이 저장소의 윤년 규칙이 무엇인지도 끝내 알 수 없다. 조치 자리에
    선언 그대로가 실려야 한다 — **문면을 여기서 다시 쓰지 않는다**(두 벌이 되면
    갈리고, 갈린 것을 붙드는 검사를 또 놓아야 한다).
    """
    path = tmp_path / "leap.parquet"
    leap = pa.table({"load_kw": pa.array([1.0] * HOURS_PER_LEAP_YEAR)})

    with pytest.raises(TimeSeriesShapeError) as caught:
        write_series(path, leap, kind="load", year=2024)

    err = caught.value
    assert err.rule == "DV-4"
    assert err.field == "timeseries.rows"
    assert str(HOURS_PER_LEAP_YEAR) in err.reason, "받은 행 수가 사유에 없다"
    assert "윤년" in err.reason or "366일" in err.reason, (
        f"윤년 자료임을 알아보지 못하고 일반 문장으로 거절했다: {err.reason!r}"
    )
    assert err.action == LEAP_YEAR_POLICY, (
        "조치가 선언 그대로가 아니다 — 문면을 두 곳에 두면 반드시 갈린다"
    )
    assert not path.exists(), "거부했는데 파일이 남았다"


@pytest.mark.req("NFR-303-M1")
def test_write_accepts_common_year_rows_even_in_a_leap_year_by_declared_policy(
    tmp_path: Path,
) -> None:
    """★ 윤년(2024)에도 **8760행이 맞다** — 우연이 아니라 선언에 따른 것이다.

    이 파일의 다른 테스트들은 예전부터 `year=2024` 에 8760행을 써 왔고 전부
    통과했다. **그러나 그것은 윤년 규칙을 검사한 것이 아니라 규칙이 없는 채로
    한쪽 결과를 고정한 것**이었다 — R24 인수에서 그 형태가 드러났다(「조항의
    반대를 고정한 테스트」). 같은 사실을 **이유와 함께** 붙들어 둔다.

    2024는 윤년이다. 그 해의 실제 달력은 8784시간이지만, 이 도구는 평년 규약을
    쓰므로 8760행이 정상이며 거부되면 안 된다. 이 테스트가 빨간불이면 규약이
    바뀐 것이고, 그때 고칠 것은 이 테스트가 아니라 **선언**이다.
    """
    path = tmp_path / "load_leapyear_2024.parquet"

    checksum = write_series(path, _synthetic_load(), kind="load", year=2024)

    assert path.exists()
    assert checksum, "윤년 연도의 평년 길이 시계열이 거부됐다"
    assert read_series(path, expected_checksum=checksum).num_rows == 8760
