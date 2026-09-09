"""화면 하나가 리포트를 **한 번만** 세우는가 — R64/WP-PERF.

## 무엇을 재는가 — **시간이 아니라 «몇 번 세웠나»**

`app/services/ui_run_cache.py` 가 닫는 것은 성능이 아니라 **판정 가능성**이다:
`/ui/run` 을 한 번 열면 리포트가 아홉 번 세워져(HTML 1 + 그림 8) 실측 43초가
걸렸고, 그것이 e2e 의 playwright 30초 예산을 이미 넘겨 **로컬에서 화면을
판정할 수 없는 상태**를 만들었다.

⛔ **시간으로 재지 않는다.** 「빨라졌다」는 기계 부하에 흔들리고, 흔들리는
검사는 꺼진다. 재는 것은 `build_case_report` 가 **불린 횟수**다 — 그 수는
부하와 무관하며, 캐시가 하는 일의 정의 그 자체다.

## 넷을 각각 잰다

    ①  같은 질의를 두 번 → **한 번만** 세운다 (그리고 같은 수를 돌려준다)
    ②  다른 질의 → **다른 리포트**를 받는다 (캐시가 남의 답을 주지 않는다)
    ③  ★ **대장을 건드리면 새로 세운다** — `mtime` 과 크기를 따로 잰다
    ④  상한을 넘기면 **가장 오래된 것이 나간다**

①②는 **진짜 러너**를 돈다 — 캐시가 돌려주는 것이 정말 그 리포트인지는 세는
것만으로는 말할 수 없다. ③④는 세는 것이 전부이므로 러너 자리에 **표를 세워**
빠르게 돈다(진짜로 돌면 열여덟 번 × 4.4초다).
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.services.ui_run as ui_run_module
import app.services.ui_run_cache as cache_module
from app.main import create_app
from app.services.ui_run import run_ui_case
from app.services.ui_run_cache import (
    REPORT_CACHE_ENTRIES,
    clear_report_cache,
    report_cache_entries,
)

#: 대조에 쓰는 골든 시나리오 — `tests/app/test_ui_run.py` 와 같은 것.
_SCENARIO = "scenario_unsubsidized"

#: 저장소 뿌리 — `tests/app/test_ui_run_cache.py` 에서 두 단계 위.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: **잉여가 남는** 단지 규모. 사유는 `tests/casegrid/test_household_count.py`
#: 의 `_COUNT` 이며 값도 그것과 같다 — 더 키우면 낮 부하가 발전을 넘어 러너가
#: 정당하게 거부하고, 그러면 이 검사는 캐시가 아니라 그 거부를 재게 된다.
_SURPLUS_SAFE_COUNT = 2


@pytest.fixture(autouse=True)
def _empty_cache() -> Iterator[None]:
    """⚠⚠ **매 검사의 앞뒤에서 캐시를 비운다.**

    비우지 않으면 이 파일의 검사들이 서로의 캐시를 물려받아 **순서에 따라
    빌드 수가 달라진다** — 그때 초록불은 캐시가 옳다는 증거가 아니라 실행
    순서의 우연이다. 뒤에서도 비우는 이유는 같다: 이 파일이 채운 칸이
    `tests/app/` 의 다른 파일에 새면 그쪽 검사가 러너를 안 돈 채 통과한다.
    """
    clear_report_cache()
    yield
    clear_report_cache()


class _Counter:
    """`build_case_report` 가 몇 번 불렸나 — 캐시의 정의를 재는 자.

    ⚠ 세는 자리를 `app/services/ui_run_cache.py` 의 이름으로 잡는다.
    `core/report/case_report.py` 쪽을 갈아 끼우면 **골든 회귀와 다른 검사가
    같은 이름을 쓰는 동안** 그것까지 세게 되고, 그때 이 수는 이 화면의
    빌드 수가 아니다.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, stub: bool) -> None:
        self.calls = 0
        real = cache_module.build_case_report

        def counted(*args: object, **kwargs: object) -> object:
            self.calls += 1
            if stub:
                # ③④ 는 «몇 번 세웠나» 만 재므로 진짜로 돌지 않는다. 서로
                # 다른 객체를 돌려주어 「캐시가 답을 바꿔치기했다」도 잡힌다.
                return f"보고서 #{self.calls}"
            return real(*args, **kwargs)

        monkeypatch.setattr(cache_module, "build_case_report", counted)


def test_the_same_query_builds_the_report_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """① 같은 질의를 두 번 불러도 **리포트는 한 번** 세워진다.

    ⚠⚠ 세는 것만으로 끝내지 않는다. 「한 번만 세웠다」는 「두 번째가 **그**
    리포트를 받았다」와 다른 진술이고, 캐시가 틀리는 방식은 대개 후자다.
    그래서 두 응답의 `manifest_hash` 와 결론축을 함께 맞댄다 — 매니페스트
    해시는 이 실행의 입력·결과 전부에서 나오므로(`core/report/manifest.py::
    create_manifest`) 같으면 같은 실행이다.
    """
    counter = _Counter(monkeypatch, stub=False)

    first = run_ui_case(_SCENARIO)
    second = run_ui_case(_SCENARIO)

    assert counter.calls == 1, (
        f"같은 질의를 두 번 부르는데 리포트를 {counter.calls} 번 세웠다 — "
        "캐시가 키를 못 맞추고 있다"
    )
    assert first.report.manifest_hash == second.report.manifest_hash
    assert first.report.metrics["npv"] == second.report.metrics["npv"]
    # ⚠ `scenario_text` 는 캐시가 짓지 않는다 — 부르는 쪽이 매번 짓는다.
    assert first.scenario_text == second.scenario_text


def test_a_different_query_gets_its_own_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """② **다른 질의**는 남의 리포트를 받지 않는다 — 수가 달라져야 한다.

    가구 수 하나만 바꾼다. 그 한 칸이 단지 총부하를 정하므로(`core/casegrid/
    household_scale.py`) 결론축이 반드시 움직이고, 움직이지 않으면 캐시가
    키를 뭉갠 것이다 — 그것이 이 캐시가 낼 수 있는 **가장 조용한 고장**이다.

    ⚠ **아무 수나 넣을 수 없다.** 규모를 키우면 낮 부하가 발전을 넘어 잉여가
    사라지고, 그때 러너는 *「충전원이 태양광 잉여인데 잉여 시계열이 없거나
    전부 0입니다」* 로 **정당하게** 거부한다(실측: 40호). 그래서
    `tests/casegrid/test_household_count.py::_COUNT` 가 고른 것과 같은
    **잉여가 남는 규모**를 쓴다 — 그 사유의 정본은 그 파일이다.
    """
    counter = _Counter(monkeypatch, stub=False)

    one = run_ui_case(_SCENARIO, household_count="1")
    many = run_ui_case(_SCENARIO, household_count=str(_SURPLUS_SAFE_COUNT))

    assert counter.calls == 2, (
        f"다른 질의 둘인데 리포트를 {counter.calls} 번 세웠다 — "
        "키가 가구 수를 보지 못한다"
    )
    assert one.report.household_count == 1
    assert many.report.household_count == _SURPLUS_SAFE_COUNT
    assert one.report.metrics["npv"] != many.report.metrics["npv"], (
        f"가구 수를 1호에서 {_SURPLUS_SAFE_COUNT}호로 올렸는데 결론축이 "
        "그대로다 — 캐시가 남의 답을 줬다"
    )


def test_touching_the_ledger_makes_the_next_run_build_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """③ ★ **대장이 바뀌면 새로 세운다** — `mtime` 과 크기를 **따로** 잰다.

    ⚠⚠ 이것이 없으면 사용자가 대장 값을 고쳐 저장한 뒤에도 **옛 리포트가
    나오고**, 그것은 R63 이 세운 *「고치면 움직인다」* 를 **조용히 거짓으로
    만든다.** 대장은 `build_case_report` 에 경로로만 넘어가므로 파일의 내용은
    시나리오 매핑에 없다 — 신원을 키에 싣지 않으면 캐시는 그 변경을 못 본다.

    ⚠ **저장소의 대장을 건드리지 않는다.** `tmp_path` 로 복사해 두고
    실행 경로가 그것을 보게 한다 — 저장소 파일의 `mtime` 을 흔들면 다른
    검사·게이트가 그 흔들림을 물려받는다.

    ⚠ 크기 축은 **`mtime` 을 되돌려 놓고** 잰다. 되돌리지 않으면 「크기를
    보는가」가 아니라 「`mtime` 을 보는가」를 두 번 재는 것이 된다.
    """
    ledger = tmp_path / "assumptions.yaml"
    ledger.write_text(_ASSUMPTIONS.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(ui_run_module, "_ASSUMPTIONS", ledger)
    counter = _Counter(monkeypatch, stub=True)

    run_ui_case(_SCENARIO)
    run_ui_case(_SCENARIO)
    assert counter.calls == 1, "같은 대장·같은 질의인데 두 번 세웠다"

    stat = ledger.stat()
    os.utime(ledger, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    run_ui_case(_SCENARIO)
    assert counter.calls == 2, (
        "대장의 `mtime` 이 바뀌었는데 옛 리포트가 나왔다 — 값을 고쳐 저장한 "
        "사용자가 자기 변경이 반영되지 않은 화면을 본다"
    )

    bumped = ledger.stat()
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write("# 검사 — 크기만 바꾼다 (값은 한 자리도 안 건드린다)\n")
    os.utime(ledger, ns=(bumped.st_atime_ns, bumped.st_mtime_ns))
    assert ledger.stat().st_mtime_ns == bumped.st_mtime_ns
    run_ui_case(_SCENARIO)
    assert counter.calls == 3, (
        "대장의 크기가 바뀌었는데 옛 리포트가 나왔다 — 키가 크기를 안 본다"
    )


def test_the_least_recently_used_run_leaves_when_the_bound_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """④ 상한을 넘기면 **가장 오래 안 쓴 것이 나간다** — 캐시가 안 자란다.

    ⚠ 무한 캐시는 서버 메모리를 먹는다(`CaseReport` 는 `repr` 로 64KB 이고
    객체 그래프는 그보다 크다). 상한이 **실제로 듣는가**를 재는 자리가
    여기다 — 상수만 적어 두고 안 듣는 상한은 상한이 아니다.

    ⚠ 상한 + 1 개를 서로 다른 가구 수로 넣는다. 순서대로 한 번씩만 넣으므로
    「가장 오래 안 쓴 것」이 「가장 먼저 넣은 것」과 같다.
    """
    counter = _Counter(monkeypatch, stub=True)
    counts = [str(n) for n in range(1, REPORT_CACHE_ENTRIES + 2)]

    for count in counts:
        run_ui_case(_SCENARIO, household_count=count)

    assert counter.calls == len(counts)
    assert report_cache_entries() == REPORT_CACHE_ENTRIES, (
        f"상한 {REPORT_CACHE_ENTRIES} 인데 {report_cache_entries()} 개를 들고 "
        "있다 — 상한이 듣지 않으므로 서버가 오래 떠 있으면 메모리가 자란다"
    )

    run_ui_case(_SCENARIO, household_count=counts[-1])
    assert counter.calls == len(counts), "방금 넣은 것이 나갔다"

    run_ui_case(_SCENARIO, household_count=counts[0])
    assert counter.calls == len(counts) + 1, (
        "상한을 넘겼는데 첫째가 아직 캐시에 있다 — 무엇이 나가는지 모르는 캐시다"
    )


def test_one_screen_and_its_charts_build_the_report_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★ 이 WP 가 닫은 것 그대로 — **화면 하나가 아홉이 아니라 한 번**.

    위 넷은 서비스 함수를 직접 부른다. 그러나 아홉 번을 부르던 것은
    **브라우저**였다: HTML 한 번과 그 안의 `<figure data-chart=…>` 여덟 장이
    각각 `/ui/chart/<태그>.png` 로 따로 온다. 그래서 이 검사는 라우트를
    지나며, `tests/app/test_ui_run.py` 머리말이 적은 규약과 같다 — 문맥 함수를
    직접 부르면 「배포 코드가 부르지 않는 함수가 초록불을 만든다」를 다시 밟는다.

    ⚠ **그림 태그를 여기 박지 않는다.** 화면의 HTML 에서 뽑는다 — 박으면
    차트가 늘거나 줄는 날 이 검사는 「화면이 실제로 부르는 것」이 아니라
    소스에 적힌 옛 목록을 잰다.
    """
    counter = _Counter(monkeypatch, stub=False)
    client = TestClient(create_app())

    screen = client.get("/ui/run", params={"scenario": _SCENARIO})
    assert screen.status_code == 200
    tags = [
        piece.split('"')[0]
        for piece in screen.text.split('data-chart="')[1:]
    ]
    assert len(tags) >= 6, f"화면이 그림을 {len(tags)} 장만 부른다 — 목록이 낡았다"

    for tag in tags:
        # ⚠ 상태 코드를 여기서 판정하지 않는다. 재료가 없어 못 그리는 그림은
        # **501** 이고(그 라우트의 표), 그것도 리포트를 세운 뒤에 난다 —
        # 이 검사가 재는 것은 그 빌드가 캐시에 걸리는가다.
        client.get(f"/ui/chart/{tag}.png", params={"scenario": _SCENARIO})

    assert counter.calls == 1, (
        f"화면 하나(HTML + 그림 {len(tags)})가 리포트를 {counter.calls} 번 "
        "세웠다 — 실측으로 아홉 번 43초였고 e2e 의 30초 예산을 넘겼다"
    )
