"""`FR-103` — 동일 유형 자원의 **인스턴스별 재무 조건**. 조항 문면 셋을 그대로 둔다.

    AC1  한 시나리오 내에 `PV#1(햇빛소득마을 조건)`, `PV#2(자가용 조건)`이 동시 존재
    AC2  각 인스턴스는 독립적인 `IncentiveScheme` 참조를 가진다 (FR-604)
    AC3  두 인스턴스의 현금흐름이 프로포마에서 **분리된 행**으로 표시된다

## ⚠ 이 파일이 오래 셋을 다 달고 있었는데 잰 것은 `AC1` 하나였다 (R60/WP-6)

한 시험이 `AC1`·`AC2`·`AC3` 셋을 인용했고 세 단언은 이랬다 — 인스턴스 둘이 서로
다른 재무 속성을 갖는다(`AC1`), *「클래스 속성이 아닌 인스턴스 단위 속성」*
(독스트링에만 있던 말이며 **조항 문면이 아니다**), `capex1 != capex2`(값이 다르다).
`AC2` 는 `IncentiveScheme` 을 한 번도 만지지 않았고 `AC3` 은 프로포마 행을 보지
않았다. **매핑표는 셋 다 초록불이었다.**

    AC1  → `test_financial_isolation_between_instances` (종전 시험 · 마커를 이것만 남긴다)
    AC2  → **인용 없음.** 잴 통로가 저장소에 없다 (아래)
    AC3  → `test_two_instances_stand_as_separate_proforma_rows` (이 파일 신설분)

## ★ `AC2` 에 마커를 달지 않은 이유 — 인스턴스가 지원 조건을 들 자리가 없다

`IncentiveScheme`(`core/incentive/schemas.py`)은 실재하고 `FR-604` 도 닫혀 있다.
없는 것은 **그것을 자원 인스턴스에 매는 통로**다.

- `DERConfig`(`core/model/schemas.py`)는 `tag` 와 `params` 뿐이고, 자원 생성자
  (`core/der/pv.py` 등)와 `DER` 계약(`core/contracts/der.py`) 어디에도 지원 조건을
  받는 매개변수가 없다.
- 실행 경로는 지원 조건을 **케이스 하나에 하나** 든다 —
  `core/casegrid/e2e_runner.py::run_single_case_e2e` 의 `scheme` 은 단일 값이고,
  `core/casegrid/incentive_cases.py::build_capex_cashflows_for_all_cases` 는 그 하나를
  **합산 총사업비**에 적용한다. 인스턴스별로 갈리는 자리가 없다.

그래서 「독립적인 참조를 가진다」를 재려면 **먼저 통로가 생겨야 한다.** 통로를 이
자리에서 지으면 조항이 아니라 우리가 설계를 정하는 것이므로 짓지 않았다. 마커를
남겨 두는 쪽도 버렸다 — 남기면 다시 *「인용은 있는데 다른 것을 잰다」* 가 되고, 그
상태가 이 파일이 고치러 온 결함 그 자체다. **Must-have 미매핑 1건이 늘어난 것이
이 판정의 정직한 값이다.**
"""

from decimal import Decimal

import pytest

from core.cba import assert_proforma_identity, capex_row, fixed_om_row, total_row
from core.contracts.assumptions import AssumptionProvider
from core.contracts.schemas import CashFlowRow
from core.model.model import Model
from core.model.schemas import ContractConfig, DERConfig, ModelConfig
from tests.model.test_model import _Assumptions

_HORIZON_YEARS = 20


def _two_pv_model(provider: AssumptionProvider) -> Model:
    """`PV#1(햇빛소득마을 조건)`·`PV#2(자가용 조건)` 을 한 시나리오에 함께 세운다.

    두 시험이 같은 구성을 본다 — 사본을 두면 한쪽만 고쳐지고, 그때 두 시험이
    서로 다른 시나리오를 말하면서 같은 조항을 인용한다.
    """
    pv1_config = DERConfig(
        tag="PV",
        params={
            "name": "PV#1",
            "capacity_kw": 10.0,
            "unit_capex_won_per_kw": 1500000,
            "lifetime": 20,
            "capacity_factor": 0.15,
            "fixed_om_won_per_year": 300000,
        },
    )
    pv2_config = DERConfig(
        tag="PV",
        params={
            "name": "PV#2",
            "capacity_kw": 3.0,
            "unit_capex_won_per_kw": 1800000,
            "lifetime": 25,
            "capacity_factor": 0.15,
            "fixed_om_won_per_year": 90000,
        },
    )

    config = ModelConfig(
        name="테스트 모델",
        resources=[pv1_config, pv2_config],
        contract=ContractConfig(structure="개별 세대 직접계약"),
    )
    return Model(config, provider)


@pytest.mark.req("FR-103-AC1")
def test_financial_isolation_between_instances():
    """`FR-103-AC1` — *「한 시나리오 내에 `PV#1`, `PV#2` 이 동시 존재」*.

    동시에 서는 것만으로는 부족하다 — 같은 유형이므로 **재무 속성이 인스턴스마다
    따로 정해지는지**까지 본다. 클래스 단위로 정해지면 둘이 같은 값을 들고, 그때
    *「인스턴스별로 서로 다른 재무 조건」*(`FR-103` 본문)이 성립하지 않는다.

    ⚠ 이 시험은 `AC2`·`AC3` 을 인용하지 않는다 — 모듈 독스트링 참조.
    """
    provider = _Assumptions()
    model = _two_pv_model(provider)

    assert len(model.resources) == 2
    pv1, pv2 = model.resources

    assert pv1.name == "PV#1"
    assert pv1.lifetime == 20
    assert pv2.name == "PV#2"
    assert pv2.lifetime == 25
    assert pv1.unit_capex_won_per_kw == 1500000
    assert pv2.unit_capex_won_per_kw == 1800000

    # 자본비가 인스턴스마다 따로 계산된다
    capex1 = pv1.capex(year=1)
    capex2 = pv2.capex(year=1)
    # PV#1: 10.0 * 1,500,000 = 15,000,000
    # PV#2: 3.0 * 1,800,000 = 5,400,000
    assert capex1 != capex2, "두 인스턴스의 CAPEX는 달라야 합니다"
    assert int(capex1) > 0 and int(capex2) > 0

    # 고정 O&M 도 인스턴스마다 따로 계산된다
    om1 = pv1.fixed_om(year=1)
    om2 = pv2.fixed_om(year=1)
    assert om1 != om2, "두 인스턴스의 O&M는 달라야 합니다"

    # 잔존가치도 인스턴스마다 따로 계산된다
    salvage1 = pv1.salvage_value(year=20)
    salvage2 = pv2.salvage_value(year=20)
    # PV#1(수명20): 20년차 잔존가치 ≈ 0
    # PV#2(수명25): 20년차 잔존가치 > 0
    assert int(salvage1) != int(salvage2), (
        f"두 인스턴스의 잔존가치는 달라야 합니다: PV#1={int(salvage1)}, "
        f"PV#2={int(salvage2)}"
    )


@pytest.mark.req("FR-103-AC3")
def test_two_instances_stand_as_separate_proforma_rows():
    """`FR-103-AC3` — *「두 인스턴스의 현금흐름이 프로포마에서 **분리된 행**으로 표시된다」*.

    ## 왜 「값이 다르다」로는 이 조항을 재지 못하는가

    종전 시험이 잰 것은 `capex1 != capex2` 였다. 값이 달라도 **행이 하나로
    합쳐지면** 조항은 성립하지 않는다 — 사람이 표를 보고 어느 인스턴스의
    현금흐름인지 말할 수 없고, 그 상태에서 *「PV#1 은 융자 85%, PV#2 는 조건이
    다르다」*(`FR-103` Rationale)를 표로 보여 줄 방법이 없다. 그래서 값이 아니라
    **행의 갈림**을 잰다.

    ## 무엇을 단언하는가

    프로포마 한 행은 `CashFlowRow` 이고 행을 만드는 자리는 `core/cba/proforma.py`
    다(`core/cba/__init__.py` 가 재수출한다). 행의 `tag`·`label` 이 **인스턴스
    이름을 나르므로** 같은 유형 둘이 각각 서고, 그러면 인스턴스별 현금흐름을
    표에서 **다시 갈라낼 수 있다**. 갈라 두어도 합계는 보존된다(`NFR-103-M1`).

    ⚠ **재는 자리는 프로포마 계층이다.** 실행 경로(`core/casegrid/e2e_runner.py::
    run_single_case_e2e` · `core/casegrid/lifecycle.py::lifecycle_rows`)는 자원
    **유형** 단위 태그(`"PVFixedOM"`)를 쓰고 `PV` 를 하나만 받는다 — 같은 유형 둘이
    그 경로를 지나 분리 행으로 서는 것은 아직 배선되어 있지 않다. 그 결손은
    R60/WP-6 판정에 적었고, 이 시험이 그것을 잰다고 주장하지 않는다.
    """
    provider = _Assumptions()
    model = _two_pv_model(provider)
    pv1, pv2 = model.resources

    # 인스턴스를 순회해 **같은 방식으로** 행을 만든다 — 인스턴스마다 다르게
    # 짜면 갈림이 시험 코드에서 오고 프로포마에서 오지 않는다.
    rows: list[CashFlowRow] = []
    for resource in model.resources:
        rows.append(
            capex_row(resource.name, year=1, amount_won=int(resource.capex(year=1)))
        )
        rows.append(
            fixed_om_row(
                resource.name,
                start_year=1,
                end_year=_HORIZON_YEARS,
                annual_amount_won=int(resource.fixed_om(year=1)),
            )
        )

    # ① 행이 인스턴스 단위로 갈린다 — 태그가 인스턴스 이름을 나른다
    assert sorted({row.tag for row in rows}) == ["PV#1", "PV#2"]

    # ② 라벨도 갈린다 — 사람이 표에서 네 행을 서로 구별할 수 있어야 한다
    labels = [row.label for row in rows]
    assert labels == [
        "PV#1 자본비",
        "PV#1 고정 O&M",
        "PV#2 자본비",
        "PV#2 고정 O&M",
    ]
    assert len(set(labels)) == len(labels)

    # ③ 각 행이 **그 인스턴스의** 값을 든다 — 합산값이나 남의 값이 아니다
    capex_rows = {row.tag: row for row in rows if row.label.endswith("자본비")}
    assert capex_rows["PV#1"].amounts[1] == Decimal(int(pv1.capex(year=1)))
    assert capex_rows["PV#2"].amounts[1] == Decimal(int(pv2.capex(year=1)))
    assert capex_rows["PV#1"].amounts[1] != capex_rows["PV#2"].amounts[1]

    om_rows = {row.tag: row for row in rows if row.label.endswith("고정 O&M")}
    assert om_rows["PV#1"].amounts[1] == Decimal(int(pv1.fixed_om(year=1)))
    assert om_rows["PV#2"].amounts[1] == Decimal(int(pv2.fixed_om(year=1)))
    assert om_rows["PV#1"].amounts[1] != om_rows["PV#2"].amounts[1]

    # ④ 인스턴스별 현금흐름을 프로포마에서 **다시 갈라낼 수 있다**
    per_instance = {
        resource.name: sum(
            (row.total() for row in rows if row.tag == resource.name), Decimal(0)
        )
        for resource in model.resources
    }
    assert set(per_instance) == {"PV#1", "PV#2"}
    assert per_instance["PV#1"] != per_instance["PV#2"]

    # ⑤ 갈라 두어도 합계는 보존된다 (`NFR-103-M1`)
    assert sum(per_instance.values(), Decimal(0)) == total_row(rows).total()
    assert_proforma_identity(rows)
