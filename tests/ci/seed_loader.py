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
from pathlib import Path

from core.assumption.provider import AssumptionSet

#: 배포 시 비공개 시드 파일 자리를 주입하는 환경변수 (FR-1101-AC2).
PRIVATE_SEED_PATH_ENV = "DER_PRIVATE_SEED_PATH"

#: 주입이 없을 때의 기본 자리. **`.gitignore` 가 이 디렉터리를 막는다** —
#: 그것이 「공개 저장소에 유입되지 않는다」의 실물이다.
DEFAULT_PRIVATE_SEED_PATH = "data/private/seeds.yaml"

#: 비공개 시드가 없을 때 쓰는 합성 예시 시드 (FR-1101-AC3). 공개 파일이다.
SYNTHETIC_SEED_FILENAME = "synthetic_seeds.yaml"


def private_seed_path() -> Path:
    """비공개 시드의 자리 — 환경변수 주입이 기본 자리를 덮는다."""
    return Path(os.getenv(PRIVATE_SEED_PATH_ENV, DEFAULT_PRIVATE_SEED_PATH))


def synthetic_seed_path() -> Path:
    """합성 예시 시드의 자리 — 저장소 안에 함께 놓인다."""
    return Path(__file__).parent / SYNTHETIC_SEED_FILENAME


def load_seeds() -> AssumptionSet:
    """비공개 시드가 있으면 그것을, 없으면 합성 시드를 읽는다."""
    private = private_seed_path()
    if private.exists():
        print(f"Using PRIVATE seed data from {private}", file=sys.stderr)
        return AssumptionSet.load_from_yaml(str(private))

    synthetic = synthetic_seed_path()
    print(f"Using SYNTHETIC seed data (fallback) from {synthetic}", file=sys.stderr)
    return AssumptionSet.load_from_yaml(str(synthetic))
