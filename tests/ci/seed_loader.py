"""공개/비공개 시드 로더 — FR-1101-AC2·AC3.

비공개 시드는 **공개 저장소에 담지 않는다.** 기본 자리
(`DEFAULT_PRIVATE_SEED_PATH`)는 `.gitignore` 가 막고 있고, 배포 시에는
`PRIVATE_SEED_PATH_ENV` 로 다른 자리를 주입한다 — AC2 가 말하는 「별도 비공개
저장소 **또는** 배포 시 주입되는 시드 파일」의 두 형태가 각각 그것이다.

**경로 결정을 순수 함수로 뺀 이유.** 모듈 안에서 `os.getenv` 를 직접 읽고
그대로 분기하면 검사가 **소스 문자열밖에 볼 수 없다** — R20 의 `SC-5` 결함이
정확히 그 모양이었고(환경변수를 읽고 버려도 통과했다), 순수 함수의 반환값을
단언하는 형태로 고쳐서 붙들었다. 여기도 같은 처방을 쓴다.
"""

import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from core.assumption.provider import AssumptionSet

#: 배포 시 비공개 시드 파일 자리를 주입하는 환경변수 (FR-1101-AC2).
PRIVATE_SEED_PATH_ENV = "DER_PRIVATE_SEED_PATH"

#: 주입이 없을 때의 기본 자리. **`.gitignore` 가 이 디렉터리를 막는다** —
#: 그것이 「공개 저장소에 유입되지 않는다」의 실물이다.
DEFAULT_PRIVATE_SEED_PATH = "data/private/seeds.yaml"

#: 비공개 시드가 없을 때 쓰는 합성 예시 시드 (FR-1101-AC3). 공개 파일이다.
SYNTHETIC_SEED_FILENAME = "synthetic_seeds.yaml"


class SeedOrigin(StrEnum):
    """시드가 **어디서 왔는가** — `FR-1101-AC2` / R31 (결정 §6).

    **결정: 비공개 시드는 공개 시드를 「대체」한다. 병합하지 않는다.**

    병합하면 어떤 값이 어디서 왔는지 결과만 보고 알 수 없고, 그 상태에서 골든
    대조(`NFR-104`)가 어긋나면 **원인이 시드인지 코드인지 가릴 수 없다.** 대체하면
    「어느 시드로 돌렸는가」 한 줄이 출처를 결정한다.

    ⚠ **그 한 줄을 결과에 남기지 않으면 대체의 이점이 사라진다.** 종전에는
    `stderr` 로만 알렸고, 그것은 결과에 남지 않으므로 리포트도 골든 비교도 그
    사실을 말할 수 없었다 — `DV-6` 의 경고를 `BillBreakdown.notices` 에 실은 것과
    같은 판단이다.
    """

    PRIVATE = "비공개 시드"
    SYNTHETIC = "합성 예시 시드"


@dataclass(frozen=True)
class LoadedSeeds:
    """읽은 시드와 **그 출처**. 출처가 결과와 함께 다닌다."""

    assumptions: AssumptionSet
    origin: SeedOrigin
    path: Path

    @property
    def provenance(self) -> str:
        """결과 메타·리포트에 그대로 싣는 한 줄."""
        return f"{self.origin.value} ({self.path})"


def private_seed_path() -> Path:
    """비공개 시드의 자리 — 환경변수 주입이 기본 자리를 덮는다."""
    return Path(os.getenv(PRIVATE_SEED_PATH_ENV, DEFAULT_PRIVATE_SEED_PATH))


def synthetic_seed_path() -> Path:
    """합성 예시 시드의 자리 — 저장소 안에 함께 놓인다."""
    return Path(__file__).parent / SYNTHETIC_SEED_FILENAME


def load_seeds() -> LoadedSeeds:
    """비공개 시드가 있으면 그것을, 없으면 합성 시드를 읽는다 — **대체이지 병합이 아니다.**

    ★ **출처를 반환값에 싣는다 (R31).** 종전에는 `AssumptionSet` 만 돌려주고 출처는
    `stderr` 로만 알렸다. 그러면 「어느 시드로 돌렸는가」가 결과에 남지 않으므로
    골든 대조가 어긋났을 때 **원인이 시드인지 코드인지 가릴 수 없다** — 대체를
    택한 이유 자체가 사라진다.

    `stderr` 출력은 남긴다. 사람이 실행 중에 보는 것과 결과에 기록되는 것은 서로를
    대신하지 않는다.
    """
    private = private_seed_path()
    if private.exists():
        print(f"Using PRIVATE seed data from {private}", file=sys.stderr)
        return LoadedSeeds(
            assumptions=AssumptionSet.load_from_yaml(str(private)),
            origin=SeedOrigin.PRIVATE,
            path=private,
        )

    synthetic = synthetic_seed_path()
    print(f"Using SYNTHETIC seed data (fallback) from {synthetic}", file=sys.stderr)
    return LoadedSeeds(
        assumptions=AssumptionSet.load_from_yaml(str(synthetic)),
        origin=SeedOrigin.SYNTHETIC,
        path=synthetic,
    )
