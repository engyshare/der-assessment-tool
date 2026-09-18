"""**PCS 를 «사기는» 했는데 «교체»가 없다** — 붙임 8 의 한 항목 (R66/WP-2-fix).

## 왜 `unreflected.py` 에서 갈라냈나

R66/WP-2 가 초기투자에 `PCS 단가 × 정격출력` 항을 세우면서 **그 설비의 수명은
세우지 않았고**(`ESS(pcs_lifetime=None)`), 그 누락을 붙임 8 에 인쇄하는 항목이
필요해졌다. 그런데 `core/report/unreflected.py` 는 착수 실측 **코드 490/500 —
여유 10줄**이었고, **이 파일의 항목 하나는 47줄이다**(실측: 그 파일에 직접 넣어
`check_file_size.py --code-strict` 를 돌리면 **537/500** 이 되고 `[코드 스프롤]`
로 빨간불이 난다). `UnreflectedItem` 의 여섯 칸이 전부 여러 줄에 걸치는 f-string
이라 기존 `_variable_om_item`·`_pool_compensation_item` 도 같은 규모다.

⛔ **상한을 올리는 것은 spec 개정(§16.5)이므로 하지 않았고**, 근거 주석을 지워
줄이는 것은 조항이 지키려던 것을 정면으로 해친다. 그리고 이 파일의 문면은
산문이 아니라 **붙임 8 이 인쇄하는 사실**이라 말을 줄이면 항목이 재는 것이
줄어든다. ⇒ **갈래를 하나 떼는 것**이 남는 길이었고, 그것은
`core/report/unreflected.py` 가 **스스로 세운 선례**다 — R64/WP-4 가 같은 자리에서
507/500 을 맞고 `core/report/measured_run.py` 를 뗐다(`core/casegrid/lifecycle.py`
(R39-E2) · `core/casegrid/operating_lines.py`(R43-F)도 같은 판단을 했다).

## ⚠ `measured_run.py` 에는 넣을 수 없다 — 그 모듈이 가른 선의 반대편이다

그 파일 머리말이 **가르는 선을 「재는 것」과 「판정하는 것」** 으로 못 박았다.
이 모듈이 하는 일은 *「미반영인가」* 의 **판정**이므로 그 선의 이쪽이다.

## ⚠⚠ 방향은 `unreflected.py` → 이 파일 **한쪽**이다

`UnreflectedItem` 을 이 파일이 만들지 않는 이유가 그것이다 — 그 자료형은
`unreflected.py` 가 갖고 있고, 여기서 import 하면 두 모듈이 서로를 import 해
**순환**이 된다. 그래서 이 파일은 **칸 셋(크기·사유·해소 조건)만** 내고, 라벨·
방향·`measured` 를 붙여 행을 세우는 것은 `unreflected.py::_pcs_replacement_item`
이 한다. `TypedDict` 로 낸 것은 그 붙이기가 `**` 전개 한 번으로 끝나야
(그 파일에 남는 코드가 여섯 줄이어야) 하기 때문이다.
"""
from __future__ import annotations

from typing import TypedDict

from core.casegrid.models import ONE_OFF_REPLACEMENT
from core.report.case_report import CaseReport

__all__ = ("LABEL_PCS_REPLACEMENT", "PCS_PRICE_LEDGER_KEY", "PCSGap", "pcs_replacement_gap")

#: **PCS 교체비** 미반영 항목의 이름. 검사·리포트가 같은 문자열을 봐야 「그 항목이
#: 섰는가」가 대조된다 — `unreflected.py` 의 `POOL_COMPENSATION_LABEL`·
#: `LABEL_VARIABLE_OM` 과 같은 규약이다.
LABEL_PCS_REPLACEMENT = "PCS 교체비"

#: PCS **출력당 단가**가 선 대장 자리 (R66/WP-1). 좌표를 항목 문면에 싣는 이유는
#: `POOL_COMPENSATION_LEDGER_KEY` 와 같다 — 크기만 적으면 검토자가 *「그 수가
#: 어디서 왔는가」* 를 물을 자리가 없다.
PCS_PRICE_LEDGER_KEY = "capex.ess.pcs_power"

#: PCS 를 초기투자에 실은 자원의 **일회성 흐름 태그 접두사**
#: (`core/casegrid/lifecycle.py` 가 `ESSReplacement`·`ESSSalvage` 로 짓는다).
#:
#: ⚠ **자원을 「종류 문면」으로 찾지 않는다** — `ResourceLine.kind`(「에너지저장장치
#: (신품)」)는 사람이 읽는 말이라 다듬는 날 이 판정이 조용히 빈 집합을 내고, 그
#: 상태는 아무 오류도 내지 않는다. 태그를 판정 재료로 쓰는 것은 `unreflected.py`
#: 의 기존 규약이다(`_GRID_PURCHASE_TAG` · `COST_TAG_VARIABLE_OM`) — 러너가 태그를
#: 바꾸면 계약 시험이 둘을 함께 붙든다.
_ESS_ONE_OFF_PREFIX = "ESS"


class PCSGap(TypedDict):
    """붙임 8 한 행의 **칸 셋** — 라벨·방향·`measured` 는 부르는 쪽이 붙인다."""

    magnitude: str
    reason: str
    resolves_when: str


def pcs_replacement_gap(report: CaseReport) -> PCSGap | None:
    """PCS 교체비가 **누락돼 있는가** — 누락이면 칸 셋, 아니면 `None`.

    ## 무엇이 어긋나 있는가

    R66/WP-2 가 초기투자에 `PCS 단가 × 정격출력` 항을 세웠다(사용자 판정 ③).
    그런데 **그 설비의 수명은 세우지 않았다** — `ESS(pcs_lifetime=None)` 이라
    `ESS._acquisitions()` 가 PCS 갈래를 통째로 건너뛰고 **교체비도 잔존가치도
    없다.** 대칭이라 R40 ② 의 비대칭은 생기지 않지만, 20년 사업에서 **한 번도
    갱신하지 않는 전력변환장치**를 놓은 셈이고 그것은 결론을 **좋은 쪽으로**
    기울인다.

    저장소 안에는 적혀 있었다 — 골든의 R66 블록 · `ess_build.py::_case_ess_spec`
    독스트링 · `.orch/R66/result_2.md`. **그런데 산출물이 말하지 않았다.** 이
    저장소가 반복해 경계해 온 *「선언과 구현이 갈린」* 형태의 표시층 판본이며,
    그 결손을 닫는 것이 이 함수다.

    ## 판정 재료 둘 — 둘 다 **결과에서** 재고 러너의 인자를 읽지 않는다

        ⓐ PCS 가 초기투자에 **있는가**    대장 단가 항목이 등재돼 있는가
        ⓑ 그 설비의 교체가 **계상됐는가**  계상된 교체 연차가 «본체 수명»으로
                                           설명되는가

    ⓑ 가 이 판정의 핵심이다. `unreflected.py::_replacement_items` 가 경고한
    *「배선이 들어오면 참인 조건 위에서 거짓을 계속 인쇄한다」* 를 막는 자리이며,
    그래서 **수명을 켜는 순간 이 항목이 사라져야 한다.**

    재는 방법은 **연차의 나머지**다 — 부품 재취득은 `수명 + 1` 부터 수명마다
    서므로(`core/der/ess.py::ESS._acquisitions`), 본체 수명 `L` 로 설명되는 연차는
    `year % L == 1` 을 만족한다. PCS 수명이 켜지면 그 식을 만족하지 않는 연차가
    생기고(실측: 본체 17년 · PCS 10년 → **11년차**), 그것이 「부품 교체가
    계상됐다」의 증거다. ⇒ 그때 이 함수는 `None` 을 낸다.

    ⚠ **`_replacement_items` 에 넣지 않았다.** 그 함수는 `basis.resources` 를 훑어
    **자원 단위**로 판정하는데 **PCS 는 자원이 아니라 `ESS` 의 부품**이라 그
    목록에 없다 — 넣으면 판정이 성립하지 않는다. 서식은 한 사실에 한 항목을 내는
    `_variable_om_item`·`_pool_compensation_item` 쪽을 따랐다.

    ⚠⚠ **본체 수명과 부품 수명이 같은 구성은 가리지 못한다.** 그때 두 연차가
    겹쳐 `year % L == 1` 을 함께 만족한다 — 그러나 그 구성에서는 부품을 갈라
    담을 이유 자체가 없고(`ESS._acquisitions` 독스트링의 *「접어서 담을 수는
    없다 — 수명이 다르다」*), 갈라 담아도 교체비가 같은 해에 합산된다.

    ⚠ **일회성 흐름이 하나도 없는 구성에서는 서지 않는다** — 자원을 찾을 수 없어
    빈 값을 낸다. 그 상태는 이미 `_replacement_items` 가 「교체비」·「잔존가치」로
    신고하므로 검토자가 어둠 속에 남지 않는다.

    ## ⚠⚠⚠ 크기 — **대장 단가는 읽어 오고, 결론 이동폭은 「어림」으로 적는다**

    단가는 `report.assumptions` 에서 **읽는다**(리터럴로 박으면 대장이 바뀔 때
    낡는다 — R59b §3 이 금지한 형태다). 그러나 **결론 이동폭은 계산할 수 없다**:
    ⓐ 11년차 교체비를 지으려면 **정격출력(kW)**이 필요한데 `CaseReport` 어디에도
    **수로 없다**(자원 표의 `capacity`·`unit_capex` 는 사람이 읽는 문면이고, 그것을
    되파싱하는 것은 `CaseBasis.grid_purchase_price_won_per_kwh` 주석이 금지한
    형태다). ⓑ 현가로 접으려면 **교체비 에스컬레이션**이 필요한데 그 값도
    `CaseBasis` 에 없다. ⓒ 무엇보다 **「10년」 자체가 대장에 없는 가정**이다.
    ⇒ 지어낸 정밀도를 인쇄하지 않고 **가정을 명시한 어림**으로 적는다.
    """
    priced = [row for row in report.assumptions if row.key == PCS_PRICE_LEDGER_KEY]
    basis = report.basis
    owners = {
        line.resource_name
        for line in basis.one_off_flows
        if line.tag.startswith(_ESS_ONE_OFF_PREFIX)
    }
    if not priced or not owners:
        return None
    life = {resource.name: resource.lifetime_years for resource in basis.resources}
    replaced_parts = any(
        line.year % life.get(line.resource_name, 1) != 1
        for line in basis.one_off_flows
        if line.kind == ONE_OFF_REPLACEMENT and line.resource_name in owners
    )
    if replaced_parts:
        return None
    # ⚠ 단위를 다듬지 않고 대장 문면 그대로 싣는다 — `unreflected.py::_unit` 를
    # 여기서 다시 적으면 사본이 되고, 그 함수를 import 하면 순환이 된다(머리말 ⚠⚠).
    # 괄호 안의 「설비비 기준 · 공사비 별도」가 **크기를 읽는 데 필요한 전제**이기도 하다.
    unit = " · ".join(f"{row.value:,} {row.value_unit}" for row in priced)
    return PCSGap(
        magnitude=(
            f"어림 · 대장 단가 {unit} (`{PCS_PRICE_LEDGER_KEY}`)가 초기투자에 서 "
            "있으나 그 설비의 교체비·잔존가치는 0건 · **내용연수 10년을 가정하면** "
            "11년차 교체비 약 2,500만원 · 무보조 순현재가치 약 -1,900만원 "
            "(배포 구성 200 kWh·100 kW 실측 -18,778,570원)"
        ),
        reason=(
            "소규모(200 kWh·100 kW) PCS 내용연수 자료 없음 — 국내 학술값이 "
            "10년(4.5 MWh 산업용)과 25년(가정용 1 kW 일체형)으로 2.5배 갈리고 "
            "갈리는 축이 설비 규모다 · `ESS(pcs_lifetime=None)` · 계상된 교체 연차 "
            "중 본체 수명으로 설명되지 않는 것 0건"
        ),
        resolves_when=(
            f"업계 견적으로 소규모 PCS 내용연수 확인 (`Q-2` — `{PCS_PRICE_LEDGER_KEY}` "
            "와 같은 견적에서 온다) · 인자는 이미 있다: "
            "`ESS(pcs_lifetime=…, pcs_cost_won=…)` — "
            "`core/casegrid/ess_build.py::_case_ess_spec` 한 줄로 켜진다"
        ),
    )
