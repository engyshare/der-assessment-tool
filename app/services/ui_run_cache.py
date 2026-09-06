"""화면 하나가 리포트를 **아홉 번** 세우던 것을 **한 번**으로 줄이는 캐시.

## ★★★ 무엇이 일어나고 있었나 — 실측이다 (R64/WP-PERF)

`/ui/run` 을 한 번 열면 리포트가 **아홉 번** 세워졌다: HTML 이 한 번,
그리고 그 안의 `<figure data-chart=…>` **여덟 장**이 각각
`/ui/chart/<태그>.png` 로 따로 와서 **자기 리포트를 다시 세운다.**
`TestClient` 로 잰 값(고친 전):

    /ui/run                        4.38s   build_case_report x1
    /ui/chart/<태그>.png 여덟 장   38.96s  build_case_report x8
    ─────────────────────────────────────────────────────────
    화면 하나                      42.10s  build_case_report x9

⇒ **e2e 의 playwright 30초 예산이 원래 빠듯한 것이 아니라 이미 넘어 있었다.**
R64 에서 로컬 `pytest tests_e2e` 가 `10 failed, 12 passed` 였고 차이 여덟은
전부 `Locator.click`·`Page.goto` 의 30초 시간초과였다. 성능이 목적이 아니라
**판정 가능성**이 목적이다 — 지금은 로컬에서 e2e 를 믿을 수 없다.

## 왜 `core/` 가 아니라 여기인가

`core/` 는 순수해야 한다. 캐시를 거기 두면 *「같은 입력 → 같은 출력」*이
**프로세스 상태에 달리게** 되고, 그때 진짜 비결정성이 있다면 캐시에 덮여
**보이지 않게 된다** — `FR-1005`(*「동일 매니페스트 재실행 시 비트 동일」*)를
재는 자리가 바로 그것이다. 그래서 이 파일은 `app/` 에 있고
`core/report/case_report.py::build_case_report` 는 한 글자도 바뀌지 않았다.

⛔ **같은 이유로 `@lru_cache` 를 `build_case_report` 에 직접 붙이지 않는다.**
그것은 위 판단의 위반이고, 게다가 그 함수의 인자는 `Path` 하나라
**대장이 바뀌어도 키가 안 움직인다**(아래 「대장」 절).

## 키가 «정확히» 무엇으로 만들어지는가

    ① 시나리오 이름            — `scenario_unsubsidized` 같은 골든 파일 이름
    ② `scenario_fields()` 반환 매핑 — 이 실행이 무엇인가의 **전부**
    ③ 대장 파일의 신원          — 경로 + 크기 + `st_mtime_ns`

셋을 한 매핑에 담아 `json.dumps(…, sort_keys=True, ensure_ascii=False)` 로
정규 직렬화하고 SHA-256 을 뜬다 — `core/report/manifest.py::create_manifest`
가 이미 쓰는 관용구이며, 여기서 형태를 새로 짓지 않는다.

⛔ **`CaseReport.manifest_hash` 를 키로 쓰지 않는다.** `build_case_report` 가
`create_manifest` 에 넘기는 입력에 **`metrics`(실행 결과)가 들어 있어** 그
해시는 **돌린 뒤에야** 나온다 — 캐시 키로 쓰려면 캐시를 채우려고 캐시하려던
일을 먼저 해야 한다.

### 대장 — ⚠⚠ **바뀌면 무효가 되어야 한다**

`docs/assumptions.yaml` 은 `build_case_report(…, assumptions_path=…)` 에
**경로로만** 넘어간다. 그래서 그 파일의 내용은 위 ②(시나리오 매핑)에 **없다**
— 넣지 않으면 사람이 대장 값을 고친 뒤에도 **옛 리포트가 나오고**, 그것은
R63 이 세운 *「고치면 움직인다」* 를 **조용히 거짓으로 만든다.** 크기와
`st_mtime_ns` 를 함께 보는 이유는 같은 크기로 값만 바뀌는 편집이 흔하기
때문이다.

⚠ **대장을 여기서 읽어 해시하지 않는다.** 매 요청마다 대장 전건을 읽으면
캐시가 줄이려던 비용의 일부가 그대로 돌아온다. `stat()` 한 번이면 족하다 —
같은 크기·같은 나노초로 내용만 바뀌는 편집은 사람의 손으로는 만들 수 없다.

## ⚠ 이 캐시가 **보지 못하는** 것 — 형상 자산

`build_case_report` 는 `core/casegrid/profiles.py::load_daily_shapes` 로
**대표일 형상 자산**(`fixtures/profiles/…`)도 읽는다. 그 파일은 지금 화면이
고칠 수 있는 자리가 아니지만(배포 코드에 그 쓰기가 없다) 대장과 **같은 갈래의
의존**이다. 그래서 그것도 대장과 나란히 키에 싣는다 — 하나만 싣고 다른 하나를
빠뜨리면 「어느 파일을 고치면 화면이 따라오는가」가 **파일마다 다른 답**이 되고,
그 차이는 아무 예외도 내지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.casegrid.profiles import PROFILE_PATH
from core.report.case_report import CaseReport, build_case_report

#: 캐시가 들고 있을 **서로 다른 실행**의 수.
#:
#: 화면 하나(`/ui/run` + 그림 여덟)가 리포트를 아홉 번 부르지만 그 아홉은
#: **같은 키 하나**다. 그러므로 이 수가 덮는 것은 *「동시에 살아 있는 서로
#: 다른 실행이 몇 개인가」* 이다 — 검토자 서넛이 각자 갈래 두셋(ⓐ·ⓑ·ⓒ)을
#: 나란히 열어 비교하는 자리가 이 저장소가 상정한 사용이며, 그것이 12 언저리다.
#: 16 은 거기에 `/ui/verify` · `/ui/scenarios` 의 다른 질의 몇을 더한 값이다.
#:
#: ⚠ 무한으로 두지 않는 이유: `CaseReport` 는 작지 않다(`repr` 로 64KB 이고
#: 객체 그래프는 그보다 크다). 16 개면 수 MB 안이며, 서버가 오래 떠 있어도
#: 그 위로 자라지 않는다.
REPORT_CACHE_ENTRIES = 16


def case_report_for(
    scenario_name: str,
    fields: Mapping[str, Any],
    scenario_text: str,
    *,
    assumptions_path: Path,
) -> CaseReport:
    """이 입력의 리포트 — **이미 세운 것이 있으면 다시 세우지 않는다.**

    ⚠ `fields` 와 `scenario_text` 는 겹쳐 보이지만 하는 일이 다르다.
    `fields` 는 **키를 짓는 것**(위 ②)이고 `scenario_text` 는 임시 파일에
    **실제로 쓰는 글자**다. 둘을 함께 넘겨받아 **둘 다 캐시 키에 실린다** —
    부르는 쪽이 둘을 어긋나게 넘기는 날이 와도(예: 직렬화 방식이 바뀌는데
    한쪽만 고쳐지는 날) 캐시가 *다른 글자로 세운 리포트*를 돌려주지 않는다.
    """
    key = _run_key(scenario_name, fields, assumptions_path=assumptions_path)
    return _report_for(key, scenario_name, scenario_text, assumptions_path)


def clear_report_cache() -> None:
    """캐시를 비운다 — **시험이 서로를 오염시키지 않게 하는 자리**.

    ⚠ 배포 경로는 이것을 부르지 않는다. 무효화는 키가 한다(대장·형상 자산의
    신원이 키에 있다). 이것을 배포 코드에서 부르게 되면 *「무엇이 언제
    지워지는가」* 가 키 밖으로 새고, 그때 캐시는 읽을 수 없는 상태가 된다.
    """
    _report_for.cache_clear()


def report_cache_entries() -> int:
    """지금 들고 있는 서로 다른 실행의 수 — 시험이 상한을 재는 자리."""
    return _report_for.cache_info().currsize


@lru_cache(maxsize=REPORT_CACHE_ENTRIES)
def _report_for(
    key: str, scenario_name: str, scenario_text: str, assumptions_path: Path
) -> CaseReport:
    """리포트를 **한 번** 세운다 — 이 함수의 몸통이 도는 횟수가 곧 빌드 수다.

    ★ 판정은 `key` 하나가 한다. 뒤 셋은 그 키가 이미 정한 값이며 **재료**로
    함께 온다 — `lru_cache` 는 인자 넷을 함께 키로 삼지만, 뒤 셋이 앞 하나에
    종속이므로 **판정 알갱이는 변하지 않는다.**

    ⚠ 대장 경로를 이 파일의 상수로 두지 않고 **받는다.** 이 저장소에는
    `docs/assumptions.yaml` 을 스스로 짓는 자리가 이미 셋(`app/services/
    ui_run.py` · `app/routers/reports.py` · `app/run/report_cli.py`) 있고,
    넷째를 만들면 한쪽만 고쳐지는 날 캐시가 **화면과 다른 대장**으로 세운
    리포트를 화면에 돌려준다.

    ⚠ 절차는 `app/services/ui_run.py::run_ui_case` 가 R62 부터 하던 그대로다.
    임시 파일 이름을 골든과 같게 두는 이유도 같다: `build_case_report` 는
    시나리오 이름이 매핑에 없을 때 `scenario_path.stem` 을 표제로 쓴다.

    ⚠ **거부를 캐시하지 않는다.** `lru_cache` 는 예외를 담지 않으므로 갈래
    문면이 틀린 요청은 매번 같은 3요소 거부를 새로 짓는다 — 그것이 옳다.
    거부는 싸고(러너를 돌기 전에 난다), 거부를 담으면 대장을 고쳐 거부가
    풀린 뒤에도 옛 거부가 나온다.
    """
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / f"{scenario_name}.yaml"
        path.write_text(scenario_text, encoding="utf-8")
        return build_case_report(path, assumptions_path=assumptions_path)


def _run_key(
    scenario_name: str,
    fields: Mapping[str, Any],
    *,
    assumptions_path: Path,
) -> str:
    """「이 실행이 무엇인가」를 한 글자로 — 위 머리말 「키가 «정확히»」 절.

    ⚠ `default=str` 을 두는 이유: 시나리오 yaml 이 날짜를 싣는 날
    `json.dumps` 가 `TypeError` 로 죽는다. 죽는 대신 글자로 낮추면 키가
    **덜 날카로워질** 수는 있으나, 같은 요청의 `scenario_text` 가 `_report_for`
    의 키에 함께 실려 있어 서로 다른 실행이 한 칸을 나눠 갖는 일은 없다.
    """
    payload = {
        "scenario": scenario_name,
        "fields": fields,
        "assumptions": _file_identity(assumptions_path),
        "profiles": _file_identity(PROFILE_PATH),
    }
    serialized = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _file_identity(path: Path) -> list[object]:
    """파일의 **신원** — 경로 + 크기 + `st_mtime_ns`.

    ⚠ 없으면 예외를 올리지 않는다. 파일이 없다는 사실은 `build_case_report`
    가 훨씬 나은 문면으로 말하고(대장이면 `AssumptionSet.load_from_yaml`,
    형상이면 `load_daily_shapes` 의 *「기본 형상으로 메우지 않습니다」*),
    여기서 먼저 죽으면 그 문면이 `FileNotFoundError` 로 덮인다.
    """
    try:
        stat = path.stat()
    except OSError:
        return [str(path), None, None]
    return [str(path), stat.st_size, stat.st_mtime_ns]
