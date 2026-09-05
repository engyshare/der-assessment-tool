"""시나리오 저장을 **프로세스 밖으로** 내보낸다 — `FR-902-AC1`~`AC3` · R63/P3.

## 왜 이 파일이 생겼는가

`InMemoryScenarioStore` 는 인터페이스와 비즈니스 규칙(소프트 삭제 · 버전 이력 ·
30일 보관)을 고정했고 그 일을 다 했다. 못 하던 것은 **저장**이다 — 프로세스가
죽으면 사라지므로 사용자 문면(*「시나리오를 수정, 저장할 수 있어야 함」* ·
*「기본 설정도 쉽게 변경, 저장, 로드할 수 있어야 함」* — `docs/decisions-2026
-09-05-R63.md` §1)이 성립하지 않는다.

## ⚠ DB 를 세우지 않는다

`infra/orm/scenario.py` 에 테이블(`scenarios`·`scenario_overrides`)이 있으나
alembic 마이그레이션과 세션 배선을 이 라운드에 세우는 것은 범위가 아니다.
사용자가 요구한 것은 **화면이 저장·로드를 하는 것**이고, 그것은 파일 하나로
선다. 그 테이블로 옮길 때 이 구현은 **같은 프로토콜**을 구현한 다른 클래스로
갈아 끼우면 되고, 호출부는 아무것도 고치지 않는다 — `ScenarioStore` 를 고치지
않은 이유가 그것이다.

## ★ 프로토콜을 고치지 않는다

`ScenarioStore` 는 `InMemoryScenarioStore` 와 **같은 인터페이스**여야 한다.
고치면 인메모리 저장소를 쓰는 기존 검사가 함께 깨지고, 그때 무엇이 회귀이고
무엇이 새 규약인지 가릴 수 없다.

## 저장 자리를 코드에 박지 않는다

    생성자 인자        시험이 `tmp_path` 를 준다
    환경변수           배포가 자리를 정한다 (`SCENARIO_STORE_ENV`)
    아무것도 없으면    사용자 홈 밑 점 디렉터리

⛔ **저장소 안(`fixtures/`·`docs/`)에 쓰지 않는다.** 쓰면 사용자의 저장이 골든
픽스처·대장과 같은 나무에 섞이고 `git status` 가 그것을 변경으로 센다.

## 매 호출마다 파일을 다시 읽는다

객체 안에 상태를 캐시해 두면 **같은 인스턴스에서 읽는 검사만 초록불**이 되고,
그것은 인메모리 저장과 구별되지 않는다. 게다가 한 파일을 여러 프로세스(웹
워커)가 볼 수 있으므로 캐시는 조용히 낡는다.

## ★★ 모르면 멈춘다 — **메우지 않는다** (R63/F1 · `result_R1.md` D-2·D-12)

`core/model/parameters.py::ParameterCatalogueError` 와
`core/assumption/provider.py` 의 `price_basis` 거부가 이 저장소의 규약을
정했다: *「경고로 흘리지 않는 이유 — 아는 것만 돌려주면 화면은 그대로 그려지고
검사도 통과한다. 빠진 것은 사용자가 알아차릴 때까지 아무 데도 나타나지 않는다」*.

이 파일은 **그 규약을 어기고 메우고 있었다.** `int(loaded.get(next_id, 1))` 이
`next_id` 를 모르는 파일에 id 1 을 다시 발급해 **기존 시나리오와 그 버전 이력을
통째로 덮었고, 예외가 없었다.** 그래서 지금은 저장 파일이 어긋나면
`ValidationError`(`NFR-303` 3요소)로 **거부한다.**

⛔ **조용히 `max(id)+1` 로 고쳐 쓰지 않는다** — 그러면 파일이 왜 어긋났는지
아무도 모르고, 다음 사람은 그 파일을 정상으로 읽는다.

## ⚠ 다중 쓰기는 **「잃지 않게」까지**다 — 잠금을 발명하지 않는다

`_read`→`_write` 사이에 잠금이 없어 **성공을 돌려받은 저장이 사라졌다**
(실측: 두 프로세스가 각각 30번 저장 → 성공 52 · 파일에 남은 것 30).
`_update` 가 읽은 뒤 쓰기 직전에 파일의 지문을 다시 재어, 바뀌었으면 **한 번
다시 읽고 다시 적용**하고 또 바뀌었으면 **거부한다.**

⚠ **이것은 잠금이 아니다.** 지문을 다시 잰 뒤 `os.replace` 가 끝나기까지의
틈은 남아 있다. 파일 잠금은 플랫폼마다 다르고 이 라운드의 범위가 아니다 —
여기까지가 「잃지 않게」이며, **「성공」을 돌려주고 잃는 것만은 하지 않는다.**
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from app.services.scenario_store import (
    SOFT_DELETE_RETENTION_DAYS,
    InMemoryScenarioStore,
    ScenarioRecord,
    ScenarioStore,
)
from core.contracts.validation import ValidationError

#: 저장 자리를 정하는 환경변수. `app/deps.py::DB_URL_ENV` 와 같은 규약이다 —
#: 이름을 여기 한 곳이 갖는다.
SCENARIO_STORE_ENV = "DER_SCENARIO_STORE"

#: 자리를 정하지 않았을 때 쓰는 홈 밑 점 디렉터리. **경로 전체를 리터럴로
#: 박지 않는다** — 조각을 상수로 두고 `Path.home()` 위에서 짓는다.
HOME_STORE_DIRNAME = ".der-evaluator"
HOME_STORE_SUBDIR = "scenarios"

#: 한 디렉터리 안의 저장 파일 이름.
STORE_FILENAME = "scenarios.json"

_RECORDS = "records"
_HISTORY = "history"
_NEXT_ID = "next_id"

#: 거부의 `field` 경로 — `core/contracts/validation.py` 의 「경로 관례」에서
#: **그 밖**에 해당한다(`<도메인>.<필드>`). 표시 층이 키로 쓰므로 사용자가 지은
#: 자유 문자열(경로·이름)을 여기 싣지 않는다 — 그것은 `reason` 이 적는다.
_FIELD_FILE = "scenario_store.file"
_FIELD_NEXT_ID = "scenario_store.next_id"
_FIELD_DIRECTORY = "scenario_store.directory"

#: 옆에 쓰는 자리의 꼬리. **이름 전체가 고정이면 두 쓰기가 부딪힌다** —
#: 앞은 `tempfile.mkstemp` 이 호출마다 다르게 짓는다 (`result_R1.md` D-1 ⓐ).
_STAGING_SUFFIX = ".tmp"

_T = TypeVar("_T")


def default_scenario_store_dir() -> Path:
    """자리를 정하지 않았을 때의 저장 자리 — **사용자 홈 밑**이다."""
    return Path.home() / HOME_STORE_DIRNAME / HOME_STORE_SUBDIR


def resolve_scenario_store_dir() -> Path | None:
    """배포가 정한 저장 자리. **정하지 않았으면 `None`** 이다.

    **함수로 빼 둔 이유**는 `app/deps.py::resolve_db_url` 이 적어 두었다 —
    모듈 수준에서 `os.environ` 을 직접 읽으면 검사가 「소스에 그 이름이
    있는가」밖에 볼 수 없고, **환경변수를 읽고 그 값을 버리도록 고쳐도
    통과한다.**

    **절대경로만 받는다.** 빈 문자열·공백문자열은 「설정하지 않음」이고,
    상대경로는 거부한다 — 빈 경로도 상대경로도 저장을 **현재 작업 디렉터리**
    (저장소 뿌리일 수 있다)로 떨어뜨린다. 종전 방어는 `""` **하나만** 잡아
    `"   "`·`"."`·`"fixtures"` 가 통과했고, `"."` 은 이 독스트링이 막으려던
    결과를 정확히 냈다 (`result_R1.md` D-11). 모듈 머리말의 ⛔ *「저장소
    안(`fixtures/`·`docs/`)에 쓰지 않는다」* 를 강제하는 것은 이 거부다.

    ⚠ **윈도에서 `/data/scenarios` 같은 값도 상대경로로 본다** —
    `os.path.isabs` 가 그렇게 판정하고, 실제로도 그 값은 **현재 드라이브**에
    달려 있어 자리가 하나로 정해지지 않는다. 컨테이너(POSIX) 안에서는 같은
    값이 절대경로이므로 `Dockerfile` 의 선언은 그대로 산다.
    """
    configured = os.environ.get(SCENARIO_STORE_ENV, "")
    place = configured.strip()
    if not place:
        return None
    if not os.path.isabs(place):
        raise ValidationError(
            field=_FIELD_DIRECTORY,
            reason=(
                f"{SCENARIO_STORE_ENV} 가 절대경로가 아닙니다: {configured!r}. "
                "상대경로는 저장을 현재 작업 디렉터리 밑으로 떨어뜨리고, 그 자리는"
                " 프로세스를 띄운 곳에 따라 달라집니다 — 저장소 뿌리일 수 있습니다"
            ),
            action=(
                f"{SCENARIO_STORE_ENV} 를 절대경로로 고치거나, 저장 자리를 정하지"
                " 않으려면 값을 비우십시오(그러면 인메모리 저장소를 씁니다)"
            ),
        )
    return Path(place)


def build_scenario_store(directory: Path | None) -> ScenarioStore:
    """자리가 있으면 파일 저장소, 없으면 인메모리.

    ⚠ **인자를 받는 순수 함수다** — 환경변수를 여기서 읽으면 위 함수의
    독스트링이 적은 함정을 그대로 다시 밟는다.

    ⚠ **자리를 정하지 않았을 때 인메모리로 되돌리는 것**은
    `app/deps.py::DEFAULT_DB_URL`(`"sqlite://"`)과 같은 규약이다 — 그 자리
    주석이 *「기존 테스트가 이것을 전제한다」* 로 사유를 적는다. 정하지 않은
    배포가 사용자 홈에 파일을 만들기 시작하면, 검사가 서로의 저장을 물려받아
    **실행 순서에 따라 결과가 달라진다.**
    """
    if directory is None:
        return InMemoryScenarioStore()
    return JsonFileScenarioStore(directory)


def _encode(record: ScenarioRecord) -> dict[str, Any]:
    """레코드 하나를 JSON 이 담을 수 있는 모양으로."""
    return {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "tags": list(record.tags),
        "definition_json": record.definition_json,
        "owner_id": record.owner_id,
        "version": record.version,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "deleted_at": None if record.deleted_at is None else record.deleted_at.isoformat(),
    }


def _decode(raw: dict[str, Any]) -> ScenarioRecord:
    """JSON 한 벌을 레코드로.

    ⚠ **태그를 튜플로 되돌린다.** `ScenarioRecord.tags` 가 튜플인 것은 밖에서
    고칠 수 없게 하려는 것이고(`NFR-205`), 목록으로 되살리면 저장을 한 번
    거친 레코드만 가변이 된다 — 그 차이는 예외 없이 조용하다.

    ⚠ **시각의 tz 를 잃지 않는다.** 잃으면 `purge_expired` 의 비교가
    `TypeError` 로 죽거나(둘 중 하나만 naive), 더 나쁘게는 다른 시각대의 값과
    조용히 견주어진다.
    """
    deleted_at = raw.get("deleted_at")
    return ScenarioRecord(
        id=int(raw["id"]),
        name=str(raw["name"]),
        description=str(raw.get("description", "")),
        tags=tuple(raw.get("tags", ())),
        definition_json=str(raw.get("definition_json", "")),
        owner_id=int(raw.get("owner_id", 0)),
        version=int(raw.get("version", 1)),
        created_at=datetime.fromisoformat(raw["created_at"]),
        updated_at=datetime.fromisoformat(raw["updated_at"]),
        deleted_at=None if deleted_at is None else datetime.fromisoformat(deleted_at),
    )


def _serialize(state: dict[str, Any]) -> str:
    """상태를 파일에 쓸 문자열로. **`_update` 가 「바뀌었나」를 이것으로 본다.**"""
    return json.dumps(state, ensure_ascii=False, indent=2)


def _highest_id(records: dict[str, Any]) -> int:
    """파일이 이미 쓴 가장 큰 id — **키와 레코드의 `id` 를 둘 다** 본다.

    둘이 어긋난 파일이 실재한다(`result_R1.md` §1 ⓐ5 「키/id 불일치」).
    어느 한쪽만 보면 `next_id` 가 다른 쪽과 부딪히는 것을 못 본다.
    """
    highest = 0
    for key, raw in records.items():
        stored_id = raw.get("id") if isinstance(raw, dict) else None
        for candidate in (key, stored_id):
            if isinstance(candidate, bool) or not isinstance(candidate, (str, int)):
                continue
            try:
                highest = max(highest, int(candidate))
            except ValueError:
                continue
    return highest


class JsonFileScenarioStore:
    """`ScenarioStore` 의 **파일 구현** — 저장이 프로세스를 넘어 산다.

    `InMemoryScenarioStore` 와 **같은 규칙**을 지킨다: 새 저장은 버전 1 로
    이력에 서고, 수정은 버전을 올려 이력에 쌓이며, 삭제는 소프트 삭제이고
    `SOFT_DELETE_RETENTION_DAYS` 가 지나야 행이 진짜 사라진다. 규칙을 여기서
    다시 정하지 않는다 — 두 구현이 다른 규칙을 가지면 저장 자리를 바꾸는 것이
    동작을 바꾸는 것이 된다.
    """

    def __init__(self, directory: Path | str | None = None) -> None:
        self._path = Path(directory or default_scenario_store_dir()) / STORE_FILENAME

    # ── 파일 입출력 ────────────────────────────────────────────────────

    def _read(self) -> dict[str, Any]:
        """저장 파일 한 벌. **없으면 빈 상태**이지 오류가 아니다.

        ⚠ **어긋난 파일을 메우지 않는다** — 모듈 머리말의 「모르면 멈춘다」.
        """
        return self._read_with_fingerprint()[1]

    def _read_with_fingerprint(self) -> tuple[tuple[int, str], dict[str, Any]]:
        """상태와 그 지문을 **같은 바이트에서** 낸다 — 둘 사이에 창이 없다.

        지문을 따로 재면 그 사이에 남이 쓴 것을 「안 바뀌었다」로 읽을 수 있고,
        그 방향의 오판은 **조용히 잃는다.**
        """
        try:
            data = self._path.read_bytes()
            mtime_ns = self._path.stat().st_mtime_ns
        except FileNotFoundError:
            return (0, ""), {_NEXT_ID: 1, _RECORDS: {}, _HISTORY: {}}
        return (mtime_ns, hashlib.sha256(data).hexdigest()), self._parse(data)

    def _fingerprint(self) -> tuple[int, str]:
        """지금 파일의 지문. **없으면 `(0, "")`** — 「아직 없다」도 한 상태다.

        내용 해시를 드는 이유: `mtime_ns`·크기만 보면 윈도의 파일 시각 해상도가
        굵어 **빠른 두 쓰기가 같은 값을 갖고**, 같은 길이의 다른 상태도 있다.
        파일이 작고 어차피 매 호출마다 통째로 읽으므로(머리말) 값이 싸다.
        """
        try:
            data = self._path.read_bytes()
            return (self._path.stat().st_mtime_ns, hashlib.sha256(data).hexdigest())
        except FileNotFoundError:
            return (0, "")

    def _parse(self, data: bytes) -> dict[str, Any]:
        """저장 파일의 바이트를 상태로. **어긋나면 거부한다** (`NFR-303` 3요소).

        종전에는 최상위가 목록·문자열·`null` 이면 맨 `AttributeError` 로
        죽었고(`'list' object has no attribute 'get'`), 세 칸 중 없는 것은
        기본값으로 메웠다 — `next_id` 결손이 **기존 레코드를 통째로 덮는**
        자리였다 (`result_R1.md` D-2·D-12).
        """
        try:
            loaded = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError(
                field=_FIELD_FILE,
                reason=f"저장 파일을 JSON 으로 읽을 수 없습니다 ({self._path}): {exc}",
                action=(
                    f"{STORE_FILENAME} 이 온전한 JSON 인지 확인하고, 쓰다가 잘린"
                    " 것이면 백업으로 되돌리십시오. 빈 저장소로 다시 시작하려면"
                    " 그 파일을 지우십시오(저장한 것은 함께 사라집니다)"
                ),
            ) from exc
        if not isinstance(loaded, dict):
            raise ValidationError(
                field=_FIELD_FILE,
                reason=(
                    f"저장 파일의 최상위가 매핑이 아닙니다 ({self._path}): "
                    f"{type(loaded).__name__}"
                ),
                action=(
                    f"최상위에 {_NEXT_ID}·{_RECORDS}·{_HISTORY} 세 칸을 갖는 매핑"
                    "이어야 합니다. 다른 판이 쓴 파일이라면 그 판으로 옮기십시오"
                ),
            )
        records = self._section(loaded, _RECORDS)
        history = self._section(loaded, _HISTORY)
        return {
            _NEXT_ID: self._checked_next_id(loaded, records),
            _RECORDS: records,
            _HISTORY: history,
        }

    def _section(self, loaded: dict[str, Any], key: str) -> dict[str, Any]:
        """`records`·`history` 한 칸. **없는 것과 빈 것을 가른다.**

        `_write` 는 언제나 세 칸을 함께 쓰므로 **한 칸이 없는 파일은 이 저장소가
        쓴 것이 아니다.** 빈 값으로 메우면 `list_versions` 가 조용히 빈 목록을
        주고 `restore_version` 이 뒤늦게 `KeyError` 로 죽는다.

        ⚠ **빈 목록 `[]` 은 유효한 상태다** — 정말 다 지운 뒤일 수 있다.
        종전에는 `dict([])` 가 `{}` 로 풀려 **내용이 있는 목록까지** 조용히
        빈 상태가 됐다 (`result_R1.md` D-12).
        """
        if key not in loaded:
            raise ValidationError(
                field=_FIELD_FILE,
                reason=(
                    f"저장 파일에 {key} 칸이 없습니다 ({self._path}). 이 저장소가"
                    " 쓴 파일은 언제나 세 칸을 함께 갖습니다"
                ),
                action=(
                    f"{key} 칸을 되살리거나 백업으로 되돌리십시오. 비어 있는 것이"
                    f" 맞다면 {key} 를 빈 매핑({{}})으로 적으십시오 — 「없다」와"
                    " 「모른다」는 다릅니다"
                ),
            )
        value = loaded[key]
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list) and not value:
            return {}
        raise ValidationError(
            field=_FIELD_FILE,
            reason=(
                f"저장 파일의 {key} 칸이 매핑이 아닙니다 ({self._path}): "
                f"{type(value).__name__}"
            ),
            action=(
                f"{key} 는 id 를 키로 갖는 매핑이어야 합니다. 비어 있는 것이"
                " 맞다면 빈 매핑({}) 으로 적으십시오"
            ),
        )

    def _checked_next_id(self, loaded: dict[str, Any], records: dict[str, Any]) -> int:
        """다음에 발급할 id. **모르거나 어긋나면 거부한다** (`result_R1.md` D-2).

        두 갈래를 함께 막는다 — 칸이 **없는** 것과, 있으나 파일 안 최대 id
        **이하**인 것. 뒤엣것도 같은 덮어쓰기를 낸다(손편집·백업 되돌리기·
        경합으로 잃은 쓰기). 실측 `새 id = 5  사업E 살아있나: 새`.
        """
        if _NEXT_ID not in loaded:
            raise ValidationError(
                field=_FIELD_NEXT_ID,
                reason=(
                    f"저장 파일에 {_NEXT_ID} 칸이 없습니다 ({self._path}). 메우면"
                    " 이미 쓴 id 를 다시 발급해 기존 시나리오와 그 버전 이력을"
                    " 통째로 덮습니다 — 예외 없이 조용히"
                ),
                action=(
                    f"{_NEXT_ID} 를 파일 안 최대 id 보다 큰 값으로 적으십시오"
                    " (다른 판이 쓴 파일이라면 그 판으로 옮기십시오)"
                ),
            )
        raw = loaded[_NEXT_ID]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValidationError(
                field=_FIELD_NEXT_ID,
                reason=(
                    f"{_NEXT_ID} 가 정수가 아닙니다 ({self._path}): {raw!r}"
                ),
                action=f"{_NEXT_ID} 를 정수로 적으십시오",
            )
        highest = _highest_id(records)
        if raw <= highest:
            raise ValidationError(
                field=_FIELD_NEXT_ID,
                reason=(
                    f"{_NEXT_ID}({raw}) 가 파일 안 최대 id({highest}) 이하입니다"
                    f" ({self._path}). 다음 저장이 살아 있는 레코드를 덮습니다"
                ),
                action=(
                    f"{_NEXT_ID} 를 {highest + 1} 이상으로 고치십시오 — 저장소가"
                    " 스스로 고치지 않는 것은 파일이 왜 어긋났는지를 남기기"
                    " 위해서입니다"
                ),
            )
        return raw

    def _open_staging(self) -> tuple[int, Path]:
        """옆에 쓸 자리를 **호출마다 다르게** 연다 (`result_R1.md` D-1 ⓐ).

        이름이 `scenarios.json.tmp` 로 고정이면 두 쓰기가 부딪혀
        `PermissionError` 가 `save()` 밖으로 나가고 `POST /scenarios` 가 500 이
        된다 — 실측 `A: 성공=26 PermissionError=4`.

        ⚠ **같은 디렉터리에 짓는다.** `os.replace` 가 원자적인 것은 같은
        파일시스템 안에서이고, 다른 자리에 쓰면 교체가 복사가 되어 `_write` 가
        막으려던 「반쯤 쓰인 파일」이 되돌아온다.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(
            prefix=f"{self._path.name}.", suffix=_STAGING_SUFFIX, dir=self._path.parent
        )
        return handle, Path(name)

    def _write(self, payload: str) -> None:
        """**옆에 쓰고 갈아 끼운다.**

        같은 파일에 곧바로 쓰면 도중에 죽었을 때 반쯤 쓰인 JSON 이 남고, 그때
        저장소는 「비었다」가 아니라 **읽을 수 없다** 가 된다 — 사용자가 저장한
        것 전부를 한 번에 잃는 형태다.
        """
        handle, staging = self._open_staging()
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
            staging.replace(self._path)
        except BaseException:
            # 갈아 끼우지 못했으면 **치운다.** 남겨 두면 저장 자리에 이름이
            # 다른 찌꺼기가 쌓이고, 그것을 아무도 지우지 않는다.
            staging.unlink(missing_ok=True)
            raise

    def _update(self, mutate: Callable[[dict[str, Any]], _T]) -> _T:
        """읽고-고치고-쓰기를 **그 사이에 파일이 바뀌지 않았을 때만** 확정한다.

        `result_R1.md` D-1 ⓑ 가 잰 것: 잠금이 없어 **성공을 돌려받은 저장이
        사라졌다**(두 프로세스가 각각 30번 저장 → 성공 52 · 파일에 남은 것 30).
        예외는 아무 데서도 나지 않았으므로 사용자는 목록에서 없어진 것을
        나중에 안다.

        ⇒ 쓰기 직전에 지문을 다시 재어 바뀌었으면 **한 번 다시 읽고 `mutate` 를
        다시 적용**하고, 또 바뀌었으면 **거부한다.** 「성공」을 돌려주고 잃는
        것만은 하지 않는다.

        ⚠ **잠금이 아니다** — 지문을 다시 잰 뒤 교체가 끝나기까지의 틈은 남아
        있다(모듈 머리말). ⚠ `mutate` 는 **여러 번 불릴 수 있으므로** 상태
        밖에 부작용을 두지 않는다.
        """
        attempts_left = 2
        while True:
            before, state = self._read_with_fingerprint()
            unchanged = _serialize(state)
            result = mutate(state)
            payload = _serialize(state)
            if payload == unchanged:
                # 바뀐 것이 없으면 파일을 만들지도 건드리지도 않는다 —
                # `purge_expired` 가 지울 것이 없을 때가 그 경우다.
                return result
            if self._fingerprint() == before:
                self._write(payload)
                return result
            attempts_left -= 1
            if attempts_left == 0:
                raise ValidationError(
                    field=_FIELD_FILE,
                    reason=(
                        "저장 파일이 읽고 쓰는 사이에 두 번 바뀌었습니다"
                        f" ({self._path}) — 다른 쓰기와 겹쳤습니다"
                    ),
                    action=(
                        "잠시 뒤 다시 저장하십시오. 같은 저장 자리를 여러"
                        " 프로세스가 동시에 쓰고 있다면 그 자리를 나누십시오"
                    ),
                )

    # ── ScenarioStore 프로토콜 ─────────────────────────────────────────

    def save(self, record: ScenarioRecord) -> ScenarioRecord:
        """새 시나리오는 버전 1 로, 기존 시나리오는 **버전을 올려** 저장한다.

        ⚠ `now` 를 `_update` 밖에서 잡는다 — 안에서 잡으면 다시 읽어 재시도할
        때 시각이 달라지고, 그러면 「같은 저장이 두 시각을 갖는다」가 된다.
        """
        now = datetime.now(UTC)

        def mutate(state: dict[str, Any]) -> ScenarioRecord:
            if record.id == 0:
                new_id = int(state[_NEXT_ID])
                state[_NEXT_ID] = new_id + 1
                fresh = dataclasses.replace(
                    record, id=new_id, version=1, created_at=now, updated_at=now
                )
                state[_RECORDS][str(new_id)] = _encode(fresh)
                state[_HISTORY][str(new_id)] = [_encode(fresh)]
                return fresh

            stored = state[_RECORDS].get(str(record.id))
            if stored is None:
                raise KeyError(f"시나리오 {record.id} 가 없습니다")
            existing = _decode(stored)

            # ⚠ 소유자·생성시각·삭제표시는 **기존 것을 이긴다.** 수정 요청이
            # 소유자를 바꿀 수 있으면 남의 시나리오를 가져올 수 있고, 그 이동은
            # 목록에서 「없어졌다」로만 보인다 (인메모리 구현과 같은 판단이다).
            updated = dataclasses.replace(
                record,
                id=existing.id,
                owner_id=existing.owner_id,
                version=existing.version + 1,
                created_at=existing.created_at,
                updated_at=now,
                deleted_at=existing.deleted_at,
            )
            state[_RECORDS][str(record.id)] = _encode(updated)
            state[_HISTORY].setdefault(str(record.id), []).append(_encode(updated))
            return updated

        return self._update(mutate)

    def load(self, scenario_id: int) -> ScenarioRecord | None:
        stored = self._read()[_RECORDS].get(str(scenario_id))
        return None if stored is None else _decode(stored)

    def list_active(self, owner_id: int) -> list[ScenarioRecord]:
        """**자기 것만** 준다. 한 파일에 여러 사용자의 시나리오가 함께 쌓인다."""
        records = (_decode(raw) for raw in self._read()[_RECORDS].values())
        return [r for r in records if r.owner_id == owner_id and not r.is_deleted]

    def list_versions(self, scenario_id: int) -> list[ScenarioRecord]:
        """버전 이력 — 저장된 버전 전체 목록 (`FR-902-AC2`)."""
        return [_decode(raw) for raw in self._read()[_HISTORY].get(str(scenario_id), [])]

    def restore_version(self, scenario_id: int, version: int) -> ScenarioRecord:
        """이전 버전 복원 (`FR-902-AC2`). 복원도 **새 버전으로** 이력에 남는다."""
        now = datetime.now(UTC)

        def mutate(state: dict[str, Any]) -> ScenarioRecord:
            history = state[_HISTORY].get(str(scenario_id), [])
            target = next(
                (_decode(raw) for raw in history if int(raw["version"]) == version),
                None,
            )
            if target is None:
                raise KeyError(f"시나리오 {scenario_id} 의 버전 {version} 이 없습니다")

            stored = state[_RECORDS].get(str(scenario_id))
            if stored is None:
                raise KeyError(f"시나리오 {scenario_id} 가 없습니다")

            restored = dataclasses.replace(
                target,
                version=_decode(stored).version + 1,
                updated_at=now,
                deleted_at=None,
            )
            state[_RECORDS][str(scenario_id)] = _encode(restored)
            state[_HISTORY].setdefault(str(scenario_id), []).append(_encode(restored))
            return restored

        return self._update(mutate)

    def soft_delete(self, scenario_id: int) -> None:
        """소프트 삭제 — `deleted_at` 만 찍는다 (`FR-902-AC3`). 행은 남는다."""
        def mutate(state: dict[str, Any]) -> None:
            stored = state[_RECORDS].get(str(scenario_id))
            if stored is None:
                raise KeyError(f"시나리오 {scenario_id} 가 없습니다")
            record = _decode(stored)
            record.soft_delete()
            state[_RECORDS][str(scenario_id)] = _encode(record)

        self._update(mutate)

    def restore(self, scenario_id: int) -> ScenarioRecord:
        """소프트 삭제 복원 (`FR-902-AC3`)."""

        def mutate(state: dict[str, Any]) -> ScenarioRecord:
            stored = state[_RECORDS].get(str(scenario_id))
            if stored is None:
                raise KeyError(f"시나리오 {scenario_id} 가 없습니다")
            record = _decode(stored)
            record.restore()
            state[_RECORDS][str(scenario_id)] = _encode(record)
            return record

        return self._update(mutate)

    def purge_expired(self, now: datetime | None = None) -> int:
        """보관 기간이 지난 소프트삭제 행을 **진짜** 지운다 (`FR-902-AC3`).

        보관 기간의 정의는 `scenario_store.SOFT_DELETE_RETENTION_DAYS` 하나가
        갖는다 — 여기서 다시 적으면 두 저장소의 창이 갈릴 수 있고, 그 어긋남은
        「복원이 안 된다」로만 나타난다.
        """
        cutoff = (now or datetime.now(UTC)) - timedelta(days=SOFT_DELETE_RETENTION_DAYS)

        def mutate(state: dict[str, Any]) -> int:
            expired = [
                key
                for key, raw in state[_RECORDS].items()
                if raw.get("deleted_at") is not None
                and datetime.fromisoformat(raw["deleted_at"]) < cutoff
            ]
            for key in expired:
                del state[_RECORDS][key]
                state[_HISTORY].pop(key, None)
            return len(expired)

        # ⚠ 지울 것이 없으면 `_update` 가 파일을 건드리지 않는다 — 상태가
        # 그대로면 쓰지 않기 때문이다(그 자리 주석). 종전 `if expired:` 가
        # 하던 일을 그 규칙이 대신한다.
        return self._update(mutate)
