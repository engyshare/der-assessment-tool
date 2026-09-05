"""배포가 저장 자리를 정하면 시나리오 저장이 **컨테이너를 넘어 산다** — R63/V3.

`NFR-503-AC1`(단일 컨테이너 로컬 실행) · `FR-902-AC1`(시나리오 저장·조회).

## 왜 이 파일이 생겼는가

앞 축(P3)이 저장 계층(`JsonFileScenarioStore`)을 세웠고 라우터는 환경변수
`DER_SCENARIO_STORE` 가 있을 때만 그것을 쓴다. **그 「있을 때만」이 배포에서
실제로 성립하는가** 는 별개의 질문이다 — 저장 계층을 만들었다는 것과 저장이
된다는 것은 다르다. 이 파일은 `Dockerfile` 이 그 자리를 실제로 정하는지, 그리고
정했다면 라우터의 저장이 프로세스를 넘어 사는지를 잰다.

## Dockerfile 을 문자열로 읽는다

`docker build` 를 돌리지 않는다 — 검사 환경에 도커가 없을 수 있고, 조항이
요구하는 것은 「이미지가 무엇을 **선언했는가**」다. 선언은 텍스트이므로 텍스트로
읽어 재는 것이 이 검사의 방식이다.

⚠ **이름이 두 곳에 산다.** `Dockerfile` 은 파이썬을 import 할 수 없으니 환경변수
이름을 문자열로 적을 수밖에 없다. 시험은 그 문자열을 리터럴로 박지 않고
`SCENARIO_STORE_ENV` 상수를 import 해 대조한다 — 어느 한쪽이 이름을 바꾸면
이 검사가 빨간불이 된다. 이름이 어긋나면 컨테이너의 저장은 오류로 죽지 않고
**조용히 인메모리로 되돌아간다** (앱은 그대로 뜬다). `DER_DB_URL` 이
`app/deps.py` 와 `Dockerfile` 에서 같은 처지다.

## 앱을 두 번 짓는다

`create_app()` 은 라우터 모듈이 import 될 때 묶은 저장소를 가져온다 — 앱
팩토리를 두 번 부르는 것만으로는 저장소가 새로 지어지지 않는다. 그래서
라우터 모듈을 다시 실행해 저장소 묶음을 새로 만든 다음 앱을 짓는다. 같은 앱
인스턴스로 읽으면 인메모리 저장과 구별되지 않는다 — `tests/app/
test_scenario_store_file.py` 머리말이 같은 경계를 적는다.

## 없으면 인메모리 — 그것은 결함이 아니다

자리를 정하지 않았을 때 인메모리로 되돌리는 것은 `app/deps.py::DEFAULT_DB_URL`
과 같은 규약이다 — 정하지 않은 배포가 사용자 홈에 파일을 만들기 시작하면 검사가
서로의 저장을 물려받아 실행 순서에 따라 결과가 달라진다. 아래 시험이 그
기본값을 못박는다 — 다음 사람이 그것을 결함으로 오해해 되돌리지 않게.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path, PurePosixPath

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.scenario_store import InMemoryScenarioStore
from app.services.scenario_store_file import (
    SCENARIO_STORE_ENV,
    STORE_FILENAME,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _dockerfile_text() -> str:
    """이미지가 선언한 것 — `docker build` 없이 텍스트로 읽는다."""
    return DOCKERFILE.read_text(encoding="utf-8")


def _declared_store_place() -> PurePosixPath | None:
    """`ENV <이름>=<값>` 에서 저장 자리를 읽는다. **이름은 import 한 상수로 짠다.**

    정규식에 리터럴로 박으면 「이름이 두 곳에 산다」를 검사가 지키지 못한다 —
    상수 쪽이 이름을 바꿔도 초록불이기 때문이다.
    """
    match = re.search(
        rf"^ENV\s+{re.escape(SCENARIO_STORE_ENV)}=(\S+)\s*$",
        _dockerfile_text(),
        re.M,
    )
    return None if match is None else PurePosixPath(match.group(1))


def _declared_workdir() -> PurePosixPath:
    """`WORKDIR` — `COPY . .` 로 소스가 들어가고 재빌드에 덮이는 자리."""
    match = re.search(r"^WORKDIR\s+(\S+)", _dockerfile_text(), re.M)
    assert match is not None, "Dockerfile 에 WORKDIR 선언이 없다"
    return PurePosixPath(match.group(1))


def _fresh_app() -> FastAPI:
    """라우터 모듈을 **다시 실행해** 저장소 묶음을 새로 만들고 앱을 짓는다.

    라우터는 import 시 한 번만 저장소를 묶는다 — `create_app()` 을 두 번
    부르는 것만으로는 인메모리 저장과 구별되지 않는다. 다시 실행하면 그때의
    환경변수가 가리키는 자리의 **파일**을 읽는 저장소가 묶인다.
    """
    import app.routers.scenarios as scenarios_module

    importlib.reload(scenarios_module)
    return create_app()


@pytest.mark.req("NFR-503-AC1")
def test_dockerfile_declares_the_store_env_under_its_canonical_name() -> None:
    """★★ 배포가 `SCENARIO_STORE_ENV` 이름으로 저장 자리를 정한다.

    선언이 없으면 컨테이너 안 저장은 인메모리이고 프로세스가 죽는 순간
    사라진다 — 저장 계층이 있어도 「저장이 된다」가 성립하지 않는 형태다.
    """
    declared = _declared_store_place()
    assert declared is not None, (
        f"Dockerfile 이 {SCENARIO_STORE_ENV} 를 선언하지 않는다 — 단일 컨테이너"
        " 경로(NFR-503)에서 시나리오 저장이 프로세스와 함께 사라진다"
    )


@pytest.mark.req("NFR-503-AC1")
def test_the_declared_store_place_is_outside_the_workdir() -> None:
    """★ 저장 자리가 소스 나무(`WORKDIR`) 안이 아니다.

    안에 두면 사용자 데이터가 소스 트리에 섞이고 이미지 재빌드에 덮인다 —
    「저장이 남는다」는 조건이 오류 없이 조용히 깨진다.
    """
    place = _declared_store_place()
    assert place is not None, "먼저 자리를 선언해야 이 검사가 성립한다"
    workdir = _declared_workdir()

    assert place.is_absolute(), (
        f"상대 경로({place})다 — WORKDIR({workdir}) 안으로 풀려 재빌드에 덮인다"
    )
    assert workdir not in place.parents, (
        f"저장 자리({place})가 WORKDIR({workdir}) 안이다 — 사용자 데이터가"
        " 소스 트리에 섞이고 재빌드에 덮인다"
    )


@pytest.mark.req("NFR-503-AC1")
def test_the_dockerfile_declares_the_store_place_as_a_volume() -> None:
    """저장 자리를 `VOLUME` 로 선언한다 — 「여기가 영속해야 하는 자리다».

    선언이 없으면 사람과 도구 모두 그 경로가 사라져도 되는 자리인지 알 수
    없고, `docker run -v` 로 붙일 자리도 스스로 찾아야 한다.
    """
    place = _declared_store_place()
    assert place is not None, "먼저 자리를 선언해야 이 검사가 성립한다"

    volumes = [
        line.strip()
        for line in _dockerfile_text().splitlines()
        if line.strip().upper().startswith("VOLUME")
    ]
    assert volumes and any(str(place) in line for line in volumes), (
        f"VOLUME 선언이 저장 자리({place})를 가리키지 않는다: {volumes or '선언 없음'}"
    )


@pytest.mark.req("FR-902-AC1")
def test_the_router_persists_when_the_env_names_a_place(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """★★★ 환경변수가 자리를 정하면 라우터의 저장이 **프로세스를 넘어 산다**.

    앱을 **두 번 짓는다** — 첫째 앱에서 저장한 것이 둘째 앱에서 보여야 하고,
    파일이 실제로 디스크에 있어야 한다. 같은 앱 인스턴스로 읽으면 인메모리
    저장과 구별되지 않는다.
    """
    monkeypatch.setenv(SCENARIO_STORE_ENV, str(tmp_path))
    try:
        first = TestClient(_fresh_app())
        created = first.post(
            "/scenarios",
            params={
                "name": "배포 저장 검사",
                "owner_id": 50,
                "definition_json": '{"baseline_arrangement": "자가용 유지"}',
            },
        )
        assert created.status_code == 200, created.text
        scenario_id = int(created.json()["id"])

        assert (tmp_path / STORE_FILENAME).is_file(), (
            "라우터가 저장을 받았는데 파일이 없다 — 인메모리로 돌고 있다"
        )

        second = TestClient(_fresh_app())
        listed = second.get("/scenarios", params={"owner_id": 50})
        assert listed.status_code == 200, listed.text
        assert [row["name"] for row in listed.json()] == ["배포 저장 검사"], (
            "둘째 앱이 첫째 앱의 저장을 보지 못한다 — 저장이 프로세스 안에서만 산다"
        )

        detail = second.get(
            f"/scenarios/{scenario_id}", params={"requesting_user_id": 50}
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["definition_json"] == '{"baseline_arrangement": "자가용 유지"}', (
            "내용까지 함께 살아와야 수정·저장이 성립한다 — 이름만 남으면 부활이 아니다"
        )
    finally:
        # 이 시험의 파일 저장소 묶음을 다른 검사가 물려받지 않게 되돌린다.
        monkeypatch.delenv(SCENARIO_STORE_ENV, raising=False)
        import app.routers.scenarios as scenarios_module

        importlib.reload(scenarios_module)


@pytest.mark.req("FR-902-AC1")
def test_without_the_env_the_in_memory_store_is_the_intended_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """환경변수가 없으면 인메모리다 — **의도된 기본값**이지 결함이 아니다.

    `app/deps.py::DEFAULT_DB_URL` 과 같은 규약이다 — 정하지 않은 배포가 사용자
    홈에 파일을 만들기 시작하면 검사가 서로의 저장을 물려받아 실행 순서에 따라
    결과가 달라진다. 이 시험이 그 의도를 못박는다.
    """
    import app.routers.scenarios as scenarios_module

    monkeypatch.delenv(SCENARIO_STORE_ENV, raising=False)
    reloaded = importlib.reload(scenarios_module)

    bound = getattr(reloaded, "_store", None)
    assert isinstance(bound, InMemoryScenarioStore), (
        "환경변수가 없는데 파일 저장소가 묶였다 — 기본값이 규약이 아니라 "
        "우연히 성립한 것이 되어, 어느 날 조용히 깨진다"
    )
