"""ⓒ「자가용 집합자원화」의 **계측 선언** — 입력으로 요구하고, **빠진 쪽을 말한다**.

## 이 파일이 붙드는 것 — 거부를 없애는 것이 아니라 **조건부로 만드는 것**

`get_baseline_branch(POOL)` 은 R58 이래 `ValidationError(rule="DV-15")` 를
던져 왔고 그 문면이 사유 **둘**을 한 덩어리로 적었다:

    ① 계측 전제가 안 섰다   ← 사업 설계 사항이다. **가정하지 말고 물어야 한다**
    ② 대칭 항이 없다        ← 저장소에 자리가 없었다. **만드는 것이 R60/WP-3 이다**

★★★ **둘은 성격이 다르다.** ②는 코드로 세우면 닫히지만(`core/cba/proforma.py::
forfeited_self_consumption_row`), ①은 **저장소가 채울 수 없다** — 자가용 설비의
소유·운영권을 누가 갖는지, 발전량과 전기사용량을 구분해 계측하는지는 사업
설계이고, 그것을 기본값 `True` 로 두면 **없는 전제를 있다고 가정한 수**가 나온다
(사용자 판정 `docs/decisions-2026-09-04-R59b.md` §1 4항 — *「ⓒ 경로는 「계측이
갈렸다」를 **입력으로 요구해야 한다**(가정하지 말고 물어라)」*).

⇒ 그래서 ①은 **입력**이 되고, 선언이 없으면 **지금과 똑같이 거부한다.**

## ★★ 무엇이 새로 서는가 — **어느 쪽이 빠졌는지 말한다**

전제는 하나가 아니라 **둘**이다(판정 정본 `docs/decisions-2026-09-03-R57.md`
§2 — *「분산에너지사업자가 자가용 태양광 설비의 **소유 또는 운영권**을
전기사용자로부터 인계받고, **발전량, 전기사용량**을 명확하게 구분할 수 있는
형태로 계측, 정산되야함」*).

    선언 없음        → 거부. **둘 다** 빠졌다고 말한다          (T1)
    소유·운영권만    → 거부. **구분 계측**이 빠졌다고 말한다     (T2)
    구분 계측만      → 거부. **소유·운영권 인계**가 빠졌다고 말한다 (T3)
    둘 다            → 갈래가 선다                              (T4 의 절반)

⚠ **둘을 한 덩어리로 적으면 안 되는 이유**가 T2·T3 이다. 「전제가 안 섰다」만
말하면 사업 설계자는 **무엇을 더 확보해야 하는지 알 수 없고**, 그때 남는 선택은
「전부 다시 확인」또는 「그냥 True 로 두기」다 — 후자가 이 저장소가 막으려는
형태다(NFR-303: 오류는 **어떤 필드가 / 왜 / 어떻게 고쳐야 하는지**를 말한다).

⚠⚠ **기대 문면을 손으로 베끼지 않는다** — 전제 이름은
`core.cba.baseline.POOL_PREREQUISITE_*` 에서 읽는다. 베끼면 이 파일이 선언의
사본을 갖게 되고, 문면을 다듬는 날 검사가 따라오지 않아도 아무 일이 없다.

⚠ **지역 import 를 쓴다** — 이 폴더의 규약이며(`tests/cba/test_baseline.py`),
시험을 구현보다 **먼저** 커밋하는 판에서는 그것이 필수다: 없는 이름을 모듈
수준에서 import 하면 수집 오류(rc=2)가 나 **스위트 전체가 안 돌고**, 그 상태는
「빨간불 N건」이 아니라 「무엇이 빨간불인지 모른다」다(R60/WP-2 실측).
"""
from __future__ import annotations

import pytest

from core.cba.baseline import BaselineArrangement, SelfConsumptionTreatment
from core.contracts.validation import ValidationError


@pytest.mark.req("FR-705-AC2")
def test_the_pool_branch_is_refused_when_nothing_is_declared() -> None:
    """**T1** — 선언이 **없으면** ⓒ 는 `DV-15` 로 거부된다 (**현행 유지**).

    ★ **기본값은 「갈리지 않았다」다.** 선언을 안 적은 것을 「갈렸다」로 읽으면
    ⓒ 가 **저장소 기본값으로** 계산 가능해지고, 그 수는 없는 전제 위에 선다.

    ⚠ **거부를 경고로 내리지 않는다** — 「평가할 수 없다」와 「0 이다」는 다른
    말이다(`get_baseline_branch` 독스트링 · 판정 정본 R57 §2).
    """
    from core.cba.baseline import (
        POOL_PREREQUISITE_METERING,
        POOL_PREREQUISITE_TRANSFER,
        get_baseline_branch,
    )

    with pytest.raises(ValidationError) as caught:
        get_baseline_branch(BaselineArrangement.POOL)

    error = caught.value
    assert error.rule == "DV-15", f"규칙 ID 가 다릅니다: {error.rule!r}"
    assert error.field == "baseline.arrangement"
    for name in (POOL_PREREQUISITE_TRANSFER, POOL_PREREQUISITE_METERING):
        assert name in error.reason, (
            f"선언이 하나도 없는데 사유가 「{name}」를 들지 않습니다 — 둘 다 "
            f"빠진 것이므로 둘 다 말해야 합니다: {error.reason!r}"
        )
    assert "0 으로 채우지 마십시오" in error.action, (
        "조치가 「0 으로 채우지 말라」를 말하지 않습니다 — 그 한 줄이 없으면 "
        "다음 사람이 거부를 0 으로 메워 없는 제도 위에 편익을 쌓습니다"
    )


@pytest.mark.req("FR-705-AC2")
def test_declaring_only_the_transfer_still_refuses_and_names_the_metering() -> None:
    """**T2** — **소유·운영권 인계만** 선언하면 여전히 거부되고, **구분 계측**이 빠졌다고 말한다.

    ★ **둘 중 하나만 참이면 ⓒ 는 서지 않는다.** 소유권만 넘어와도 상계처리로
    계량하면 전기사용자의 전력사용량이 구분되지 않아 **책임공급비율의 분모가
    서지 않는다**(판정 정본 R57 §2).

    ★★ **빠진 쪽만 말하는 것이 이 검사의 본체다.** 「둘 다 있어야 한다」를
    되풀이하는 문면은 이 단언을 통과하지 못한다 — 이미 확보한 전제를 다시
    확보하라고 말하는 오류 메시지는 사람을 헤매게 한다.
    """
    from core.cba.baseline import (
        POOL_PREREQUISITE_METERING,
        POOL_PREREQUISITE_TRANSFER,
        PoolMeteringDeclaration,
        get_baseline_branch,
    )

    with pytest.raises(ValidationError) as caught:
        get_baseline_branch(
            BaselineArrangement.POOL,
            pool_metering=PoolMeteringDeclaration(
                ownership_or_operation_transferred=True
            ),
        )

    error = caught.value
    assert error.rule == "DV-15"
    assert POOL_PREREQUISITE_METERING in error.reason, (
        f"구분 계측이 빠졌다고 말하지 않습니다: {error.reason!r}"
    )
    assert POOL_PREREQUISITE_TRANSFER not in error.reason, (
        "이미 선언한 「소유·운영권 인계」를 빠진 것으로 함께 적습니다 — 그러면 "
        f"어느 쪽이 문제인지 여전히 알 수 없습니다: {error.reason!r}"
    )


@pytest.mark.req("FR-705-AC2")
def test_declaring_only_the_metering_still_refuses_and_names_the_transfer() -> None:
    """**T3** — **구분 계측만** 선언하면 여전히 거부되고, **소유·운영권 인계**가 빠졌다고 말한다.

    T2 의 반대 짝이다. **둘을 함께 두는 이유**: 한쪽만 재면 *「빠진 것 하나를
    이름으로 적는다」* 가 아니라 *「언제나 구분 계측을 적는다」* 도 통과한다.

    ⚠ 계측이 갈렸어도 **소유 또는 운영권이 인계되지 않으면** 그 설비는
    분산e사업자의 집합자원이 아니다 — 대가를 지급할 근거가 서지 않는다.
    """
    from core.cba.baseline import (
        POOL_PREREQUISITE_METERING,
        POOL_PREREQUISITE_TRANSFER,
        PoolMeteringDeclaration,
        get_baseline_branch,
    )

    with pytest.raises(ValidationError) as caught:
        get_baseline_branch(
            BaselineArrangement.POOL,
            pool_metering=PoolMeteringDeclaration(metering_separated=True),
        )

    error = caught.value
    assert error.rule == "DV-15"
    assert POOL_PREREQUISITE_TRANSFER in error.reason, (
        f"소유·운영권 인계가 빠졌다고 말하지 않습니다: {error.reason!r}"
    )
    assert POOL_PREREQUISITE_METERING not in error.reason, (
        "이미 선언한 「구분 계측」을 빠진 것으로 함께 적습니다 — 그러면 어느 "
        f"쪽이 문제인지 여전히 알 수 없습니다: {error.reason!r}"
    )


@pytest.mark.req("FR-705-AC2")
def test_declaring_both_prerequisites_opens_the_branch() -> None:
    """**둘 다** 선언하면 ⓒ 의 선언이 나온다 — 거부가 「이 갈래는 영원히 안 된다」가 아니다.

    ⚠ **거부만 재면 「전부 거부한다」도 통과한다**(같은 판단을
    `tests/cba/test_baseline.py::test_other_two_branches_are_declared_and_not_rejected`
    가 이미 했다). 조건이 채워졌을 때 실제로 열리는 것을 함께 재야 그 거부가
    **조건부**라는 뜻이 된다.

    ★ 이 갈래의 자가소비 처리는 `FORFEIT`(포기 — 음의 항)이며, 그 「음의 항」이
    프로포마에 서는 것은 `tests/report/test_pool_branch_calculated.py` 가 잰다.
    """
    from core.cba.baseline import PoolMeteringDeclaration, get_baseline_branch

    branch = get_baseline_branch(
        BaselineArrangement.POOL,
        pool_metering=PoolMeteringDeclaration(
            ownership_or_operation_transferred=True, metering_separated=True
        ),
    )

    assert branch.self_consumption_treatment is SelfConsumptionTreatment.FORFEIT
    assert branch.without_description == "자가용 유지", (
        "ⓒ 의 Without 이 「자가용 유지」가 아닙니다 — 포기 항이 재는 것은 "
        "그 Without 에서 실제로 있었던 자가소비이므로, 이 문면이 바뀌면 "
        "포기 항의 물량 근거도 함께 바뀝니다"
    )


@pytest.mark.req("FR-705-AC2")
def test_an_undeclared_declaration_defaults_to_not_separated() -> None:
    """자료형의 **기본값이 「갈리지 않았다」**다 — 빠뜨린 필드가 참이 되지 않는다.

    ⚠⚠ 기본값을 `True` 로 두면 **선언을 만들기만 하고 필드를 안 적은 호출**이
    ⓒ 를 열어 버린다. 그 실수는 아무 예외도 내지 않으므로, 안전한 쪽이
    **거부**여야 한다.
    """
    from core.cba.baseline import (
        POOL_PREREQUISITE_METERING,
        POOL_PREREQUISITE_TRANSFER,
        PoolMeteringDeclaration,
    )

    blank = PoolMeteringDeclaration()

    assert blank.missing() == (
        POOL_PREREQUISITE_TRANSFER,
        POOL_PREREQUISITE_METERING,
    ), f"빈 선언이 「둘 다 빠졌다」를 내지 않습니다: {blank.missing()!r}"
    assert (
        PoolMeteringDeclaration(
            ownership_or_operation_transferred=True, metering_separated=True
        ).missing()
        == ()
    )


@pytest.mark.req("FR-705-AC2")
def test_the_declaration_is_read_from_the_scenario_field() -> None:
    """시나리오 yaml 의 `pool_metering` 매핑이 선언이 되고, **없으면 `None`** 이다.

    ★ **통로는 이 필드 하나다** — 환경변수·CLI 플래그를 따로 세우지 않는다
    (R60/WP-2 가 갈래 선택에서 내린 것과 같은 판단: 통로가 둘이면 어느 것이
    이겼는지 산출물에서 알 수 없다).
    """
    from core.cba.baseline import (
        PoolMeteringDeclaration,
        resolve_pool_metering,
    )

    assert resolve_pool_metering(None) is None, (
        "적지 않은 것을 빈 선언으로 바꿔 내면 「적지 않았다」와 「둘 다 "
        "아니라고 적었다」가 구별되지 않습니다"
    )
    assert resolve_pool_metering(
        {"ownership_or_operation_transferred": True, "metering_separated": True}
    ) == PoolMeteringDeclaration(
        ownership_or_operation_transferred=True, metering_separated=True
    )
    assert resolve_pool_metering({"metering_separated": True}) == (
        PoolMeteringDeclaration(metering_separated=True)
    ), "적지 않은 필드가 기본값(거짓)으로 서지 않습니다"


@pytest.mark.req("NFR-303-M1")
def test_a_malformed_declaration_is_refused_with_the_three_parts() -> None:
    """선언 문면이 틀리면 **거부**하고 메시지가 필드·사유·조치 셋을 든다 (NFR-303).

    ⚠⚠ **조용히 「선언하지 않았다」로 떨어뜨리지 않는다.** 오타(`metering`)가
    *「선언이 없어서 거부됐다」* 로 통과하면 사업 설계자는 **적었는데 왜 거부되나**
    를 알 수 없고, 그 상태에서 남는 선택은 필드 이름을 하나씩 바꿔 보는 것이다.
    같은 판단을 `resolve_baseline_arrangement` 가 갈래 문면에서 이미 했다.

    ⚠ `rule` 을 비운다 — 선언 **문면 오타**는 §7.3 대장 밖의 일반 입력 검증이며,
    대장의 `DV-15` 는 *「자리가 다 서지 않은 갈래를 고를 수 없다」*로 다른 규칙이다
    (없는 ID 를 달면 추적표가 그 규칙을 검증된 것으로 센다).
    """
    from core.cba.baseline import POOL_METERING_FIELD, resolve_pool_metering

    for bad, needle in (
        ("true", "true"),
        ({"metering": True}, "metering"),
        ({"metering_separated": "예"}, "예"),
    ):
        with pytest.raises(ValidationError) as caught:
            resolve_pool_metering(bad)
        error = caught.value
        assert error.field == f"baseline.{POOL_METERING_FIELD}", (
            f"필드 키가 열거 가능한 관례를 벗어납니다: {error.field!r}"
        )
        assert needle in error.reason, (
            f"사유가 「무엇이 왔는가」를 되돌려주지 않습니다: {error.reason!r}"
        )
        assert error.rule is None, (
            f"선언 문면 오타에 규칙 ID 가 달렸습니다: {error.rule!r}"
        )
        assert "ownership_or_operation_transferred" in error.action, (
            f"조치가 적을 수 있는 필드를 알려 주지 않습니다: {error.action!r}"
        )


@pytest.mark.req("FR-705-AC2")
def test_the_forfeited_self_consumption_is_a_cost_row() -> None:
    """**포기한 자가소비**는 편익 차감이 아니라 **비용 행**이고, 금액이 **양수**다.

    ## ★★★ 부호 규약을 새로 만들지 않았다

    `CashFlowRow` 는 부호 규약을 갖지 않는다 — **비용은 양수, 편익도 양수**이고
    가르는 것은 어느 계정에 실리는가다(`core/cba/proforma.py::capex_row`
    독스트링). 이 저장소의 비용 행 셋(`fee_row`·`energy_purchase_row`·
    `fixed_om_row`)이 전부 양수를 받고 음수를 거부하며, 뒤집는 자리는
    `net_operating_flows` 경계 **하나**다(`salvage_row` 독스트링의 「뒤집는
    자리 하나」).

    ⚠⚠ **편익에서 빼는 방식을 쓰지 않는다.** `fee_row` 독스트링이 그 함정을
    적었다 — 편익 차감으로 넣으면 **비용 계정에 한 줄도 남지 않아** 정부·사회
    관점에서 그 지출이 없는 사업이 되고 B/C 의 분모도 작아진다. 포기한
    자가소비는 총괄지침 제45조③(대칭성)이 요구하는 **비용**이다.
    """
    from core.cba.proforma import forfeited_self_consumption_row

    row = forfeited_self_consumption_row(
        "ForfeitedSelfConsumption", start_year=1, end_year=3, annual_amount_won=120_000
    )

    assert "포기한 자가소비" in row.label, f"라벨이 뜻을 나르지 않습니다: {row.label!r}"
    assert sorted(row.amounts) == [1, 2, 3]
    assert all(amount > 0 for amount in row.amounts.values()), (
        "포기 항이 음수로 실렸습니다 — 비용 행은 양수이고 뒤집는 자리는 "
        "`net_operating_flows` 경계 하나입니다(두 곳에서 뒤집으면 다시 "
        "양수가 되어 포기분이 편익이 됩니다)"
    )
    assert row.total() == 360_000


@pytest.mark.req("NFR-303-M1")
def test_a_negative_forfeit_and_a_zero_start_year_are_refused() -> None:
    """음수 포기액·0년차는 거부한다 — 다른 비용 행과 **같은 문턱**이다.

    ⚠ 음수를 받으면 「자가소비를 포기해서 돈을 받는 사업」이 되어 결론이
    포기액의 두 배만큼 좋아진다(`energy_purchase_row`·`salvage_row` 가 같은
    문턱을 같은 이유로 둔다). 분석 연도를 1부터 세는 것도 그쪽 규약이다.
    """
    from core.cba.proforma import forfeited_self_consumption_row

    with pytest.raises(ValidationError) as negative:
        forfeited_self_consumption_row(
            "ForfeitedSelfConsumption",
            start_year=1,
            end_year=3,
            annual_amount_won=-1,
        )
    assert negative.value.field == "proforma.forfeited_self_consumption_won"
    assert (negative.value.action or "").strip()

    with pytest.raises(ValidationError) as zero_year:
        forfeited_self_consumption_row(
            "ForfeitedSelfConsumption",
            start_year=0,
            end_year=3,
            annual_amount_won=1,
        )
    assert zero_year.value.field == "proforma.forfeited_start_year"
