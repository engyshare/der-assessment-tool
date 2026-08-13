"""Parquet 시계열 저장소 — 작업 3.4 / spec §10.1.

**8760 시간의 부하·발전·SMP 데이터를 SQLite 테이블이 아닌 Parquet 파일에 담는다.**
이유는 §10.1 의 영속성 계층 박스:

    SQLite          : 트랜잭션 자료, 메타데이터, 케이스 결과
    Parquet (+ DB)  : 시계열 데이터 — 파일은 Parquet, 메타데이터는 DB

Parquet 이 SQLite 보다 열 기반 압축에서 5~10배 효율적이며, 20년×케이스 수×시간
행렬을 메모리 512MB 무료 티어에서 다룰 수 있게 한다.

왜 체크섬인가
-------------
§7.2 TimeSeriesDataset.checksum 컬럼이 요구하는 무결성 지표. NFR-504(무료 티어)
는 디스크가 비영속이고 컨테이너가 슬립된다. 그 사이 Parquet 파일이 손상될 수
있고 — Parquet 은 메타데이터가 깨지면 조용히 빈 DataFrame 을 돌려주는 경로가
많다. 그래서 **읽을 때마다 체크섬을 다시 계산하고 저장할 때의 값과 비교**한다.

이 모듈이 제공하는 것
---------------------
    `write_series(path, df, kind, year)`  → checksum 반환, Parquet 파일 생성
    `read_series(path, expected_checksum)`→ DataFrame, checksum 불일치 시 raise
    `compute_checksum(path)`              → 파일의 SHA256 (hex)

`compute_checksum` 은 파일 단위로 한다 — Parquet 의 메타데이터 체크섬이 아니라
전체 바이트의 해시. Parquet 자체 체크섬은 row group 단위라 부분 손상이
누락될 수 있다. 파일 해시가 더 강하다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from core.contracts.units import (
    HOURS_PER_LEAP_YEAR,
    HOURS_PER_YEAR,
    LEAP_YEAR_POLICY,
    STEPS_15MIN_PER_LEAP_YEAR,
    STEPS_15MIN_PER_YEAR,
)
from core.contracts.validation import ValidationError

#: 검증하는 시계열 종류 — TimeSeriesDataset.kind CHECK 제약과 동일.
TS_KINDS: Final[frozenset[str]] = frozenset({"load", "pv", "smp", "temp"})

#: 허용 행 수 (DV-4). 8760(1시간) 또는 35040(15분). 임의 해상도는 거부한다.
ALLOWED_ROW_COUNTS: Final[frozenset[int]] = frozenset(
    {HOURS_PER_YEAR, STEPS_15MIN_PER_YEAR}
)

#: 366일(윤년) 시계열의 행 수 — **허용값이 아니다.** 거부할 때 「이것은 윤년
#: 자료다」를 알아보고 `LEAP_YEAR_POLICY` 를 사용자에게 건네기 위한 것이다.
#: 규칙 자체는 `core/contracts/units.py` 가 선언한다 (DV-4 후반부).
LEAP_YEAR_ROW_COUNTS: Final[frozenset[int]] = frozenset(
    {HOURS_PER_LEAP_YEAR, STEPS_15MIN_PER_LEAP_YEAR}
)

#: Parquet 파일의 메타데이터에 새기는 키. 읽을 때 다시 꺼내서 정합을 본다.
#: pyarrow 는 메타데이터 키·값으로 bytes 만 받으므로 Final[bytes] 로 선언한다.
META_KIND_KEY: Final[bytes] = b"der_kind"
META_YEAR_KEY: Final[bytes] = b"der_year"
META_CHECKSUM_KEY: Final[bytes] = b"der_checksum_sha256"
META_FORMAT_VERSION: Final[bytes] = b"der_format_version"
CURRENT_FORMAT_VERSION: Final[int] = 1


class TimeSeriesIntegrityError(RuntimeError):
    """Parquet 파일의 체크섬이 저장 시점과 다르다 — 파일이 손상되었거나 변조됨."""


class TimeSeriesShapeError(ValidationError):
    """행 수가 8760 또는 35040 이 아니다 (DV-4 위반).

    `ValidationError` 를 상속해 NFR-303 3요소(필드·사유·조치)를 강제한다.
    기존 `except TimeSeriesShapeError` 호출부는 그대로 받는다 —
    `ValidationError` 도 `ValueError` 이므로 이 클래스는 여전히 `ValueError` 다.
    """


def compute_checksum(path: Path) -> str:
    """파일 전체 바이트의 SHA256 (hex).

    Parquet 의 자체 checksum (row group 단위) 이 아니라 파일 해시를 쓰는 이유:
    row group checksum 은 부분 손상을 못 잡는다. 파일 해시는 1바이트만 바뀌어도
    바뀐다. 대가는 계산 비용인데, GB 단위가 아니므로 수십 ms 다.
    """
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_series(
    path: Path,
    table: pa.Table,
    *,
    kind: str,
    year: int,
) -> str:
    """Parquet 파일을 쓰고 체크섬을 반환.

    **주의 — 체크섬은 파일을 쓴 *뒤* 에 계산한다.** Parquet writer 가 메타데이터를
    flush 한 시점이어야 파일의 최종 바이트가 정해진다. 메타데이터 안에 체크섬을
    적어넣으면 체크섬 자체가 메타데이터에 들어가 무한 재귀가 된다 — 그래서
    체크섬은 DB(TimeSeriesDataset.checksum) 에 따로 보관한다.

    행 수를 검사한다 (DV-4) — 8760 또는 35040 이 아니면 거부. 임의 해상도를
    허용하면 잘린 데이터가 "그런 해상도인가 보다" 로 통과한다.
    """
    if kind not in TS_KINDS:
        raise ValidationError(
            field="timeseries.kind",
            reason=f"지원하지 않는 시계열 종류입니다: {kind!r}",
            action=f"허용값 중 하나를 쓰십시오: {', '.join(sorted(TS_KINDS))}",
        )
    if table.num_rows not in ALLOWED_ROW_COUNTS:
        # ★ **윤년 행 수는 따로 알아본다 (DV-4 후반부).** 366일 시계열은 「잘리거나
        # 중복된」 자료가 아니라 **규약이 다른** 자료다. 같은 문장으로 거절하면
        # 사용자는 자기 자료가 온전한데 왜 거부되는지 알 수 없고, 이 저장소의
        # 윤년 규칙이 무엇인지도 끝내 알 수 없다 — 그것이 `LEAP_YEAR_POLICY` 를
        # 선언한 이유이고, 선언은 **닿아야** 선언이다.
        is_leap_shaped = table.num_rows in LEAP_YEAR_ROW_COUNTS
        raise TimeSeriesShapeError(
            field="timeseries.rows",
            reason=(
                f"행 수가 {table.num_rows} 입니다 — 366일(윤년) 시계열로 보입니다. "
                "이 도구는 평년 규약을 쓰므로 8760(1시간)·35040(15분)만 받습니다."
                if is_leap_shaped
                else
                f"행 수가 {table.num_rows} 입니다 — 8760(1시간) 또는 35040(15분)만 "
                "받습니다. 잘리거나 중복된 시계열이 조용히 통과하는 것을 막는다."
            ),
            action=(
                LEAP_YEAR_POLICY
                if is_leap_shaped
                else
                "시계열을 8760행(1시간 해상도) 또는 35040행(15분 해상도)으로 "
                "맞춰 다시 저장하십시오"
            ),
            rule="DV-4",
        )

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Parquet 메타데이터에 종류·연도를 새겨, 파일 단독으로도 정체를 알 수 있게.
    # 나중에 DB 가 없어져도 파일만 있으면 복구 가능.
    meta: dict[bytes, bytes] = {
        META_KIND_KEY: kind.encode(),
        META_YEAR_KEY: str(year).encode(),
        META_FORMAT_VERSION: str(CURRENT_FORMAT_VERSION).encode(),
    }
    existing = table.schema.metadata or {}
    merged: dict[bytes, bytes] = {**existing, **meta}
    table_with_meta = table.replace_schema_metadata(merged)
    pq.write_table(table_with_meta, path)

    checksum = compute_checksum(path)
    return checksum


def read_series(
    path: Path,
    expected_checksum: str | None = None,
) -> pa.Table:
    """Parquet 파일을 읽는다. expected_checksum 이 있으면 검증.

    **brief 3.4 의 핵심**: 「썼다」가 아니라 「읽은 것이 쓴 것과 같다」를 검증한다.
    Parquet 은 조용히 성공하는 경로가 많다 — expected_checksum 없이 읽으면
    손상 여부를 알 수 없다.

    반환은 pyarrow.Table. pandas 변환은 호출부 책임이다 — 영속성 계층은
    pandas 에 의존하지 않는다 (NFR-208 관점: 영속성은 contracts·pyarrow 만 본다).
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"시계열 파일이 없습니다: {p}")

    if expected_checksum is not None:
        actual = compute_checksum(p)
        if actual != expected_checksum:
            raise TimeSeriesIntegrityError(
                f"체크섬 불일치: 파일 {p.name}\n"
                f"  저장 시 checksum = {expected_checksum}\n"
                f"  현재 파일 checksum = {actual}\n"
                "Parquet 파일이 손상되었거나 변조되었습니다. 백업에서 복원하거나 "
                "원본 시계열을 다시 로드하십시오."
            )

    table = pq.read_table(p)
    return table


def parse_meta(table: pa.Table) -> dict[str, str]:
    """Parquet 메타데이터를 사람이 읽을 수 있는 dict 로 돌려준다.

    파일 단독 복구 시 파일이 무엇인지 알아내는 통로. DB 가 없어도 파일만 있으면
    kind·year 를 알 수 있다.
    """
    raw = table.schema.metadata or {}
    out: dict[str, str] = {}
    for raw_k, raw_v in raw.items():
        key = raw_k.decode("utf-8", errors="replace") if isinstance(raw_k, bytes) else raw_k
        val = raw_v.decode("utf-8", errors="replace") if isinstance(raw_v, bytes) else raw_v
        out[key] = val
    return out
