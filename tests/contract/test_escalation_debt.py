"""R38-D2/A3 — 물가 계수(escalation_rate) 이관 부채 래칫.

## 무엇을 붙드는가 — **두 개의 다른 자리**

이 래칫은 명목 기준(`price_basis: "명목"`, `DV-7`)을 따르지 않는 자리를 두
층에서 붙든다. **같은 뿌리가 아니다** — 하나가 닫혀도 다른 하나는 그대로다:

**① 자원 생성자 경로** — `core/casegrid/e2e_runner.py` 가 `PV`·`ESS` 를 만들
때 `escalation_rate=` 를 넘기는가. 이 값은 그 자원의 `replacement_schedule()`
(교체비, 먼 미래 연도)과 `variable_om()` 에 **연차별로** 걸린다. `PV` 는
`PV_ESCALATION_RATE` 를 받고 `ESS` 는 받지 않는다(기본값 `0.0`).

**② 프로포마 행 경로** — `core/cba/proforma.py` 의 `fixed_om_row()` 는 **자기
`escalation_rate` 인자로 직접** 연차를 굴린다(`current *= (1+i)` 루프,
`proforma.py:85-89`) — 자원의 `escalation_factor()` 를 거치지 않는다.
`e2e_runner.py` 의 `cost_rows` 조립부가 `fixed_om_row("PVFixedOM", ...,
escalation_rate=0.02)` 는 넘기고 `fixed_om_row("ESSFixedOM", ...)` 는 넘기지
않는다.

**① 과 ② 가 독립인 이유(실측):** `cost_rows` 가 넘기는 `annual_amount_won` 은
`ess.fixed_om(year=1)` 처럼 **`year=1` 로 고정 평가한 값**이다. `fixed_om()`
자체는 `A × (1+i)^(y-1)` 이므로 `year=1` 에서는 지수가 `0` 이 되어 자원의
`escalation_rate` 가 무엇이든 **그 기준액에 영향이 없다**. 즉 다음 라운드가
`ESS(..., escalation_rate=...)` 를 배선해 ①을 닫아도, `ESSFixedOM` 행이 여러
해에 걸쳐 물가를 타려면 ②(그 행 자신의 `escalation_rate` 인자)가 **별도로**
필요하다. 하나가 초록불이 되어도 다른 하나가 그대로면 「명목 기준이 지켜진다」
는 여전히 거짓이다 — 이 저장소가 열여섯 번 만난 「검사가 실제보다 넓게
주장한다」의 형태다.

**대상 밖(③, 판정 근거를 남긴다):** `energy_purchase_row()`(`GridPurchase`)와
`fee_row()`(정산 수수료)는 애초에 `escalation_rate` **매개변수 자체가 없다**
— 있는데 안 받는 것이 아니다. 두 함수의 독스트링이 그 이유를 적는다: 요금
인상률은 비용·편익 **양쪽에 동시에** 실려야 NSPM 대칭이 맞는데, 편익 쪽
경로(`tariff_escalation` 케이스 그리드 축)가 아직 파이프라인에 배선되지 않아
`status.md`「미해결」에 이미 한 행으로 서 있다. 이 함수들에 `escalation_rate`
가 없는 것은 **그 미해결 항목과 같은 사실의 다른 노출면**이며, 이 래칫이 새로
붙들 부채가 아니다 — 그래서 아래 측정은 **`escalation_rate` 매개변수를 가진
프로포마 행 함수만** 대상으로 한다(지금은 `fixed_om_row` 하나뿐이며, 이 목록도
`inspect` 로 기계 판정한다 — 손으로 나열하지 않는다).

**이 래칫이 주장하는 것은 「명목 기준이 지켜진다」가 아니다.** 주장하는 것은
**「지켜지지 않는 자리의 목록이 지금 아는 것(`KNOWN_ESCALATION_DEBT`)보다
늘지도 줄지도 않는다」** 뿐이다 — 늘면 새 자원/행이 같은 구멍으로 샌 것이고,
줄면 누가 이관을 시작한 것이므로 **어느 쪽도 조용히 넘어가면 안 된다**. 두
방향 다 이 목록을 사람이 다시 확인하고 함께 고치라는 뜻으로 빨간불을 낸다
(`test_dv_rule_enforcement.py` 의 집합-일치 관례와 같다).

## 이 래칫이 결함을 고정하는 것이 아닌 이유

**목록에 있는 자리는 정상이 아니라 「배선 라운드가 아직 닫지 않은 어긋남」이다.**
`ESS` 에 물가 계수를 넘기는 배선이 들어가면 `("resource", "ESS")` 를, `ESS
FixedOM` 행에 넘기는 배선이 들어가면 `("row", "ESSFixedOM")` 을 목록에서
**각각** 빼야 하고, 그 순간 이 검사가 빨개져 그 사실을 놓치지 않게 한다. 이
파일이 이관을 대신하지는 않는다 — 배선은 별도 라운드다.

## 세는 방법 — 손으로 세지 않는다

**① 자원 경로:**

1. `discover(core.der, DER)` 로 자원 레지스트리를 순회한다. 각 클래스의
   `__init__` 시그니처에서 이름에 `capex`·`replacement` 가 들어간 매개변수가
   하나라도 있으면 「미래 연도의 취득/교체 지출을 가질 수 있는 자원」으로 본다.
   손으로 자원 이름을 나열하지 않는 이유는 나열이 늘 낡기 때문이다 — 새 자원이
   등록되면 이 조건이 자동으로 다시 판정한다.
2. `core/casegrid/e2e_runner.py` 소스를 `ast` 로 파싱해, 1) 에서 찾은 클래스
   이름과 같은 이름의 `Call` 노드(그 자원을 실제로 생성하는 자리)를 찾고, 그
   호출의 키워드 인자 집합에 `escalation_rate` 가 있는지 본다.
3. 1)에 해당하지만 2)에서 생성 호출 자체를 찾지 못한 자원은 **대상 밖**이다 —
   이 파이프라인이 아예 생성하지 않는 자원(`EV_V2G`·`HeatPump`·`ThermalLoad`,
   실측으로 확인함)에는 이 래칫이 아무 주장도 하지 않는다.

**② 프로포마 행 경로:**

1. `core/cba/proforma.py` 모듈의 모든 함수를 `inspect.getmembers` 로 훑어,
   시그니처에 `escalation_rate` 매개변수가 **있는** 함수만 남긴다(손으로
   `fixed_om_row` 라고 적지 않는다 — 그 함수가 이름을 바꾸거나, 다른 행
   함수가 나중에 이 매개변수를 얻어도 자동으로 다시 판정한다).
2. `e2e_runner.py` 를 `ast` 로 파싱해 1) 의 함수 이름과 같은 `Call` 노드를
   찾는다. 그 호출이 (키워드로든 충분한 개수의 위치 인자로든)
   `escalation_rate` 를 실제로 넘기는지 본다.
3. 넘기지 않으면 그 호출의 첫 인자(관례상 `tag`)를 문자열 상수로 읽어
   `("row", tag)` 로 부채에 더한다. 태그를 문자열 상수로 읽을 수 없는 호출
   (예: 변수·속성 표현식)은 **라벨을 못 붙이므로 건너뛴다** — 확인 못 함이며
   부채로 세지 않는다(모르는 것을 부채로 세면 다음 사람이 없는 일을 한다).
4. `escalation_rate` 매개변수 자체가 없는 함수(위 대상 밖 문단의
   `energy_purchase_row`·`fee_row`)는 애초에 1) 의 목록에 들지 않으므로 이
   경로가 아무 주장도 하지 않는다.

## 공통 §4 의 네 물음

① 정본이 어디서 오는가 — `core/casegrid/e2e_runner.py` 의 실제 `Call` 노드
   키워드/위치 인자와 `core/cba/proforma.py` 함수 시그니처(모두 실측)다.
   `KNOWN_ESCALATION_DEBT` 는 그 실측과 **대조되는** 기대값이지 실측의
   출처가 아니다 — 대상이 스스로 정하지 않는다.
② 이 검사를 설명하는 이 문서(독스트링)가 이 검사에 걸리는가 — 아니다. `ast`
   가 보는 것은 `Call` 노드뿐이고 모듈 독스트링·주석은 애초에 트리에 없다
   (주석은 토큰화 단계에서 버려진다). `inspect.signature` 도 매개변수 이름만
   보고 독스트링을 읽지 않는다.
③ 이름이 붙드는 것보다 넓게 주장하는가 — **좁게** 갈라 적는다: 자원 경로는
   `e2e_runner.py` 가 생성하는 자원만, 행 경로는 `escalation_rate` 매개변수를
   가진 프로포마 행 함수의 호출만 본다. 레지스트리에 있지만 이 파일이 생성
   하지 않는 자원, `capex`·`replacement` 이름 패턴에 걸리지 않는 자원, 그리고
   `escalation_rate` 매개변수 자체가 없는 행 함수(`energy_purchase_row`·
   `fee_row` — 그 이유는 위 「대상 밖」 문단과 각 함수의 독스트링 참조)는
   붙들지 못한다.
④ 수를 실었는가 — 싣지 않았다. 이 검사는 금액을 계산하지 않고 「인자가
   있는가/없는가」라는 구조적 사실만 본다. 그래서 검증할 「같은 층의 조건」이
   없다 — 존재 여부 자체가 정본이다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import core.der
from core.casegrid import e2e_runner
from core.cba import proforma
from core.contracts.der import DER
from core.contracts.registry import discover

#: `e2e_runner.py`/`proforma.py` 가 명목 기준(`escalation_rate`)을 물리지
#: 않는 자리의 **실측 목록** — 자리마다 `("resource", 자원태그)` 또는
#: `("row", 행태그)` 로 구별해 적는다. 늘어도 줄어도 빨간불이어야 한다(위
#: 독스트링 참조). **이 목록에 있는 것은 어긋남이며, 각 배선 라운드가 그
#: 항목을 지운다.** 지금은 정상이 아니라 부채다.
KNOWN_ESCALATION_DEBT: frozenset[tuple[str, str]] = frozenset({
    ("resource", "ESS"),
    ("row", "ESSFixedOM"),
})

#: 생성자 매개변수 이름이 이 부분 문자열 중 하나를 포함하면 그 자원은 「미래
#: 연도의 취득/교체 지출」을 가질 수 있다고 본다 — `RC-ALL-C1`(capex)과
#: `RC-ALL-C4`(교체비)가 이 이름 관례를 쓴다(`unit_capex_won_per_kw`·
#: `capex_unit_won_per_kwh`·`replacement_cost_won`·`replacement_unit_won_per_kwh` 등).
_FUTURE_OUTLAY_PARAM_HINTS = ("capex", "replacement")

#: 소스 경로를 **모듈에게 묻는다** — 저장소 구조를 문자열로 다시 적지 않는다.
#:
#: ⚠ 처음 판은 `parents[2] / "core" / "casegrid" / "e2e_runner.py"` 로 경로를
#: 조립했다. 그러면 두 가지가 생긴다 — ⓐ 파일이 옮겨지면 이 검사가 조용히
#: **없는 파일**을 읽으려 하고 ⓑ **`check_test_accompaniment` 에 이 검사가 보이지
#: 않는다**(그 게이트는 「그 모듈을 `import` 하는 테스트」를 찾는다. R38 실측 —
#: `e2e_runner.py` 를 고쳤는데 동반 테스트가 0건이라 `NFR-105` 위반으로 잡혔다).
#: **import 로 바꾸면 둘이 함께 해소된다** — 재는 대상과 의존 관계가 같아진다.
_E2E_RUNNER_PATH = Path(inspect.getsourcefile(e2e_runner) or "")


def _future_outlay_capable_tags() -> dict[str, type[DER]]:
    """레지스트리를 순회해, 생성자가 취득/교체 비용 인자를 받는 자원만 남긴다."""
    result: dict[str, type[DER]] = {}
    for tag, cls in discover(core.der, DER).items():
        params = inspect.signature(cls.__init__).parameters
        if any(
            hint in name for name in params for hint in _FUTURE_OUTLAY_PARAM_HINTS
        ):
            result[tag] = cls
    return result


def _resource_construction_kwargs() -> dict[str, set[str]]:
    """`e2e_runner.py` 소스에서, 클래스 이름과 같은 이름의 생성 호출이 받는
    키워드 인자 집합. 같은 클래스가 여러 번 생성되면 인자 집합을 합친다.

    ⚠ **문서 문자열은 걸리지 않는다** — `ast.parse` 가 만드는 트리에서
    `Call` 노드만 본다. 독스트링·주석은 `Call` 이 아니다.
    """
    tree = ast.parse(_E2E_RUNNER_PATH.read_text(encoding="utf-8"))
    sites: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
            sites.setdefault(node.func.id, set()).update(kwargs)
    return sites


def _measure_resource_escalation_debt() -> set[str]:
    """① 자원 생성자 경로 — 자원 태그(문자열)만의 집합."""
    capable = _future_outlay_capable_tags()
    sites = _resource_construction_kwargs()

    debt: set[str] = set()
    for tag, cls in capable.items():
        kwargs = sites.get(cls.__name__)
        if kwargs is None:
            continue  # e2e_runner.py 가 이 자원을 생성하지 않는다 — 대상 밖 (③)
        if "escalation_rate" not in kwargs:
            debt.add(tag)
    return debt


def _row_generator_signatures() -> dict[str, inspect.Signature]:
    """`core/cba/proforma.py` 의 함수 중 `escalation_rate` 매개변수를 **가진**
    것만 남긴다. 손으로 `fixed_om_row` 라 적지 않는다 — 지금은 그 함수
    하나뿐이지만, 이 목록도 기계로 다시 판정한다(대상 밖 ③).
    """
    return {
        name: inspect.signature(fn)
        for name, fn in inspect.getmembers(proforma, inspect.isfunction)
        if "escalation_rate" in inspect.signature(fn).parameters
    }


def _row_construction_calls() -> list[ast.Call]:
    tree = ast.parse(_E2E_RUNNER_PATH.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


def _measure_row_escalation_debt() -> set[tuple[str, str]]:
    """② 프로포마 행 경로 — `("row", 행태그)` 의 집합.

    `escalation_rate` 매개변수가 없는 행 함수(`energy_purchase_row`·
    `fee_row`)는 `_row_generator_signatures()` 에 애초에 들지 않으므로 이
    함수가 아무 주장도 하지 않는다(대상 밖 ③, 위 모듈 독스트링 참조).
    """
    generators = _row_generator_signatures()
    if not generators:
        return set()

    debt: set[tuple[str, str]] = set()
    for node in _row_construction_calls():
        sig = generators.get(node.func.id)
        if sig is None:
            continue  # escalation_rate 를 받지 않는 함수(또는 무관한 호출) — 대상 밖

        esc_index = list(sig.parameters).index("escalation_rate")
        kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
        received = "escalation_rate" in kwargs or len(node.args) > esc_index
        if received:
            continue

        tag: str | None = None
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
            node.args[0].value, str
        ):
            tag = node.args[0].value
        else:
            tag_kw = next((kw for kw in node.keywords if kw.arg == "tag"), None)
            if (
                tag_kw is not None
                and isinstance(tag_kw.value, ast.Constant)
                and isinstance(tag_kw.value.value, str)
            ):
                tag = tag_kw.value.value
        if tag is None:
            continue  # 태그를 문자열 상수로 못 읽음 — 확인 못 함, 부채로 세지 않는다
        debt.add(("row", tag))
    return debt


def _measure_escalation_debt() -> set[tuple[str, str]]:
    resource_debt = {("resource", tag) for tag in _measure_resource_escalation_debt()}
    row_debt = _measure_row_escalation_debt()
    return resource_debt | row_debt


@pytest.mark.contract
def test_escalation_rate_debt_does_not_grow_or_shrink_unnoticed() -> None:
    """`e2e_runner.py`/`proforma.py` 가 명목 기준을 물리지 않는 자리(자원
    생성자 경로 + 프로포마 행 경로)의 집합이 `KNOWN_ESCALATION_DEBT` 와
    **정확히** 같아야 한다 (R38-D2/A3).

    같지 않은 두 방향 다 사람이 봐야 한다:
    - **늘었다** → 새 자원/행이 같은 구멍으로 샜다. `escalation_rate` 를
      넘기거나, 의도적으로 명목 기준을 깨는 이유를 대장에 적어야 한다.
    - **줄었다** → 누가 물가 계수 이관을 시작했다. `KNOWN_ESCALATION_DEBT`
      를 그 실측에 맞춰 함께 줄이십시오 — 줄이지 않으면 이 래칫이 이미 고친
      것을 계속 부채로 우긴다. **자원 경로가 닫혀도 행 경로는 별도로
      닫혀야 한다** — 위 모듈 독스트링의 「① 과 ② 가 독립인 이유」 참조.
    """
    measured = _measure_escalation_debt()
    assert measured == set(KNOWN_ESCALATION_DEBT), (
        f"물가 계수 부채 목록이 실측과 다릅니다.\n"
        f"  실측: {sorted(measured)}\n  기대: {sorted(KNOWN_ESCALATION_DEBT)}\n"
        "늘었다면 새 자원/행이 같은 구멍(escalation_rate 미전달)으로 샙니다 — "
        "escalation_rate 를 넘기거나 그러지 않는 이유를 대장에 적으십시오. "
        "줄었다면 이관이 진행된 것이므로 KNOWN_ESCALATION_DEBT 를 함께 "
        "줄이십시오(자원 경로와 행 경로는 따로 닫힙니다)."
    )
