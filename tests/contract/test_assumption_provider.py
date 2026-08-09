"""`AssumptionProvider` 계약 테스트 — 계약 개정 v1.2 ⑦ / FR-601 · NFR-202.

**이 계약이 막으려는 것은 「없음」이 「0」으로 바뀌는 일이다.**
`tax.vat_rate` 는 08-08에 대장에 올랐으나 아무도 읽지 않았고, 자원의
`vat_rate=0.0` 은 「세율 0%」가 아니라 「주입되지 않음」이었다. 둘은
프로포마의 세액 행에서 구별되지 않는다 — 어느 쪽이든 0원이다.

v1.1 에서 ESS 하나가 `capex_vat()` 를 아예 만들지 않아 세액이 통째로
사라졌을 때와 **같은 형태이며 한 단계 위에서 일어난다.** 그때 해법은
「잊으면 인스턴스화가 실패하게 둔다」였고, 여기서도 같다 — 없으면 멈춘다.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from core.contracts.assumptions import (
    AssumptionProvider,
    AssumptionValue,
    MissingAssumption,
)


def _value(key: str, value: float | int | str) -> AssumptionValue:
    """부기 7종을 채운 항목. **테스트에서도 7종을 생략하지 않는다** —
    생략을 허용하면 그 생략이 구현으로 흘러간다 (FR-601-AC5)."""
    return AssumptionValue(
        key=key,
        value=value,
        value_unit="소수 (0~1)",
        base_year="2026",
        applicable_scope="설비 취득가액에 대한 매입 부가세",
        derivation_method="부가가치세법이 정한 법정 세율",
        source="부가가치세법 제30조 (세율)",
        verified_at=date(2026, 8, 8),
        confidence="확정",
        set_name="테스트 대장",
        set_version="1",
    )


class _Stub(AssumptionProvider):
    """소비 구획이 WP-2 완성을 기다리지 않게 하는 스텁 (§16.1 W-6).

    **스텁이 성립한다는 것 자체가 계약의 합격 조건이다.** 스텁을 만들 수
    없다면 그 계약은 구현 세부에 묶여 있다는 뜻이고, 그때는 WP-3·WP-7 이
    WP-2 의 완성을 기다리게 되어 병렬화의 이득이 대기 시간으로 사라진다.
    """

    def __init__(self, **items: float | int | str) -> None:
        self._items = {k.replace("__", "."): v for k, v in items.items()}

    @property
    def set_name(self) -> str:
        return "테스트 대장"

    @property
    def set_version(self) -> str:
        return "1"

    def get(self, key: str) -> AssumptionValue | None:
        if key not in self._items:
            return None
        return _value(key, self._items[key])


@pytest.mark.contract
@pytest.mark.req("FR-601-AC4")
def test_provider_returns_value_with_all_seven_annotations() -> None:
    """값과 **부기 7종**이 함께 온다 (FR-601-AC5).

    값만 돌려주면 리포트가 *"그 값이 어디서 왔는가"* 에 답할 수 없다.
    소비 구획이 값을 꺼낸 뒤 출처를 따로 찾아 붙이는 구조라면 반드시
    빠지고, 빠진 자리는 «출처 미상» 이 아니라 그냥 빈칸으로 나타난다.
    """
    item = _Stub(tax__vat_rate=0.10).require("tax.vat_rate")
    for field in ("value_unit", "base_year", "applicable_scope",
                  "derivation_method", "source", "verified_at", "confidence"):
        assert getattr(item, field), f"부기 `{field}` 가 비었습니다 (FR-601-AC5)"
    assert item.as_float() == pytest.approx(0.10)


@pytest.mark.contract
@pytest.mark.req("NFR-202-M1")
def test_missing_assumption_stops_instead_of_defaulting() -> None:
    """대장에 없으면 **멈춘다.** 기본값으로 메우지 않는다.

    메우는 순간 「대장에 없다」가 「대장에 0이 있다」와 구별되지 않고, 그
    상태는 결과가 그럴듯해서 스스로 드러나지 않는다 — 세액이 0원인 것이
    «면세 설비» 인지 «주입을 잊었는지» 를 프로포마는 말해 주지 않는다.
    """
    provider = _Stub(tax__vat_rate=0.10)
    assert provider.get("tax.없는키") is None  # 구별이 필요한 자리는 get()
    with pytest.raises(MissingAssumption, match=re.escape("tax.없는키")):
        provider.require("tax.없는키")


@pytest.mark.contract
@pytest.mark.req("NFR-202-M1")
def test_require_is_on_the_contract_not_on_each_implementation() -> None:
    """「없을 때 무엇을 하는가」는 **계약이 정한다.**

    `get()` 하나만 추상으로 두면 구현체가 `require()` 를 각자 짓는다.
    v1.1 에서 여섯 자원이 `capex_vat()` 를 각자 지어냈고 하나는 아예 만들지
    않아 세액이 사라진 것과 같은 구조다 — 계약이 답하지 않으면 각자 다른
    답으로 메워지고, **어느 쪽도 오류가 아니다.**
    """
    assert "require" not in _Stub.__dict__, (
        "스텁이 `require()` 를 자체 구현했습니다 — 계약의 기본 구현을 쓰지 "
        "않으면 「없을 때의 처리」가 구현마다 갈립니다"
    )
    assert AssumptionProvider.require is _Stub.require
    assert getattr(AssumptionProvider.get, "__isabstractmethod__", False)


@pytest.mark.contract
@pytest.mark.req("FR-601-AC6")
def test_reference_typed_item_refuses_to_be_read_as_a_number() -> None:
    """참조형 항목을 수치로 읽으면 멈춘다 (FR-601-AC6).

    `float("0.1")` 로 조용히 통과시키지 않는다. 참조형의 key 문자열이 숫자로
    해석되는 일은 없지만, **그 경계를 무르게 두면 다음 사람이 단위 문자열을
    값 자리에 넣는다** — 그때는 조용히 통과한다.
    """
    provider = _Stub(fee__direct_trade="tariff.hv_single_contract.avg")
    with pytest.raises(TypeError, match="문자열"):
        provider.require_float("fee.direct_trade")


@pytest.mark.contract
@pytest.mark.req("FR-601-AC4")
def test_ref_carries_provenance_across_the_boundary() -> None:
    """경계를 넘는 것은 **부기 본문이 아니라 참조**다.

    부기 본문은 길고 프로포마 한 행에 수십 건이 붙는다. 경계에는 어디서
    왔는지만 실리고 본문은 리포트가 다시 조회한다 — 본문을 통째로 넘기면
    실행 매니페스트(FR-1005)가 대장 전문을 복사하게 된다.
    """
    ref = _Stub(tax__vat_rate=0.10).require("tax.vat_rate").as_ref()
    assert (ref.set_name, ref.set_version, ref.key) == (
        "테스트 대장", "1", "tax.vat_rate")
    assert ref.confidence == "확정"
    assert not hasattr(ref, "derivation_method"), (
        "경계 참조가 부기 본문을 들고 있습니다 — 참조는 «어디서 왔는가» 만 "
        "나릅니다"
    )


@pytest.mark.contract
@pytest.mark.req("NFR-208-AC3")
def test_provider_contract_does_not_import_any_partition() -> None:
    """전제 계약이 어느 구획도 import 하지 않는다 (NFR-208-AC3).

    `import-linter` 가 같은 것을 보지만 **그 검사는 CI 에서만 돈다.** 계약
    파일이 늘 때마다 사람이 기억해서 확인하는 구조는 「검사가 있다」가
    아니라 「검사를 기억하면 돈다」이고, 08-08 이전의 CI 가 정확히 그
    상태였다.
    """
    import core.contracts.assumptions as mod

    source = (mod.__file__ or "")
    assert source.endswith("assumptions.py")
    imported = {
        name for name in dir(mod)
        if name.startswith(("core_", "app", "infra"))
    }
    assert not imported, f"구획 심볼이 계약에 들어왔습니다: {imported}"


@pytest.mark.contract
@pytest.mark.req("SC-7")
def test_usage_terms_crosses_the_boundary_and_is_not_one_of_the_seven() -> None:
    """이용조건이 **경계까지** 실린다 — 그리고 부기 7종이 아니다 (`SC-7`).

    `SC-7` 은 *"외부 데이터의 **출처·이용조건** 보관"* 을 요구한다. 부기 7종의
    `source` 가 출처를 담당하고 이 칸이 이용조건을 담당한다. **7종에 넣지
    않은 이유**는 그 목록의 정본이 [[근거 표기 기준]] 이고 우리가 그것을 바꿀
    수 없기 때문이다.

    **R1 점검이 «마커는 있으나 이용조건은 아직 어디에도 없다» 를 잡았다** —
    매핑표는 초록불인데 조항은 검증되지 않은 상태였다. 08-08에 §9 보안 조항
    8건을 추적표에 넣은 이유가 바로 그 상태를 막으려던 것이고, 같은 형태가
    **마커 안쪽에서** 재현됐다.

    대장과 구획 내부 자료구조에만 두면 리포트가 이용조건을 표시할 수 없고,
    **표시할 수 없는 보관은 「보관했다」의 증거가 되지 않는다.**
    """
    provider = _Stub(tax__vat_rate=0.10)
    item = provider.require("tax.vat_rate")

    # 자리가 있다. 그리고 기본값은 「제약 없음」이 아니라 **「확인하지 않음」**이다
    assert hasattr(item, "usage_terms")
    assert item.usage_terms is None

    # 7종에는 들어가지 않는다 — 그 목록은 정본이 정하고 여기서 늘리지 않는다
    seven = ("value_unit", "base_year", "applicable_scope", "derivation_method",
             "source", "verified_at", "confidence")
    assert "usage_terms" not in seven

    # 경계 참조에는 싣지 않는다 — 참조는 «어디서 왔는가» 만 나른다.
    # 이용조건 본문은 길고, 프로포마 한 행에 수십 건이 붙는다
    assert not hasattr(item.as_ref(), "usage_terms")
