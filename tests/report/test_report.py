
import pytest

from core.contracts.assumptions import (
    AssumptionProvider,
    AssumptionValue,
    PriceBasis,
)
from core.model.model import Model
from core.model.schemas import DERConfig, ModelConfig
from core.report.charts import render_charts
from core.report.manifest import create_manifest


class _StubAssumptions(AssumptionProvider):
    """WP-24F 전용 테스트 스텁 — Model 생성에 필요한 vat_rate만 채운다."""

    @property
    def set_name(self) -> str:
        return "wp24f-test"

    @property
    def set_version(self) -> str:
        return "1.0"

    @property
    def price_basis(self) -> PriceBasis:
        """DV-7 — 스텁도 기준을 **선언해야** 한다. 그것이 강제의 실질이다."""
        return PriceBasis.NOMINAL

    def get(self, key: str) -> AssumptionValue | None:
        if key == "tax.vat_rate":
            return AssumptionValue(
                key=key,
                value=0.1,
                value_unit="소수",
                base_year="2026",
                applicable_scope="",
                derivation_method="가정",
                source="",
                verified_at=None,
                confidence="가정",
            )
        return None


@pytest.mark.req("FR-1003-AC3")
def test_model_to_json_from_json_roundtrip_preserves_scenario() -> None:
    """FR-1003-AC3: 「JSON: 시나리오+전제 정의 전체 (재현용)」.

    이 마커는 원래 엑셀 IRR만 검사하는 테스트에 잘못 붙어 있었다
    (`.orch/R13-WP24E-대장.md` ②). 실제 구현은 `Model.to_json()`/
    `Model.from_json()`(core/model/model.py:54,59)이며, 검증할 것은
    「왕복 후 같은 시나리오가 나오는가」다 — 직렬화 문자열이 비어있지
    않은지만 보면 조항을 검증한 것이 아니다.
    """
    provider = _StubAssumptions()
    config = ModelConfig(
        name="WP-24F 재현성 테스트 모델",
        resources=[
            DERConfig(
                tag="PV",
                params={"name": "PV-A", "capacity_kw": 50.0, "capacity_factor": 0.16},
            )
        ],
    )
    model = Model(config, provider)

    json_str = model.to_json()
    restored = Model.from_json(json_str, provider)

    assert restored.name == "WP-24F 재현성 테스트 모델"
    assert len(restored.resources) == 1
    assert restored.resources[0].name == "PV-A"
    assert restored.resources[0].capacity_kw == 50.0
    # 모델 계층에서 전제(vat_rate)가 재생성 시에도 동일하게 주입되는지 —
    # "전제 정의"가 왕복 후에도 보존됨을 보여준다
    assert restored.resources[0].vat_rate == 0.1


@pytest.mark.req("FR-1005-AC1", "NFR-101-M1")
def test_manifest_reproducibility() -> None:
    """13.6: 실행 매니페스트 재현성 (비트 단위 동일) (FR-1005-AC1, NFR-101-M1)"""
    manifest1 = create_manifest({"seed": 42, "version": "1.0"})
    manifest2 = create_manifest({"seed": 42, "version": "1.0"})
    assert manifest1.hash == manifest2.hash


@pytest.mark.req("FR-1004-AC1")
def test_dashboard_charts() -> None:
    """13.7: 시각화 차트 생성 (FR-1004-AC1)

    **이 테스트는 R16 이전에 아무것도 검증하지 않았다.** `generate_charts()`
    가 돌려주는 dict 에 키 세 개가 있는지만 보았고, 그 값은 영어 문자열
    상수였다 — `"Cumulative Cash Flow Chart with BEP"`. 키 검사는 그 문자열이
    그림인지 설명인지 구분하지 못한다.

    이제 **실제 렌더 바이트**를 본다. 값이 다시 문자열로 돌아가면 여기서
    빨간불이 난다.

    > **R17: `tags` 를 명시로 바꿨다.** 태그를 주지 않으면 `render_charts` 는
    > **등록된 전부**를 그리므로, 차트가 늘 때마다 이 테스트가 요구하는 입력이
    > 함께 늘어난다 — WP-28A 가 `FR-1004-AC1` 의 잔여 3종을 놓자 그렇게 됐다.
    > 이 테스트가 보는 것은 *「이 세 차트가 실제 PNG 로 나오는가」* 이므로
    > 세 개를 **명시**하는 것이 맞다. **「등록된 전부가 그려지는가」는
    > `tests/contract/test_chart_contract.py` 의 몫이고**, 그쪽 표본은 차트가
    > 늘면 함께 늘어야 한다 (계약이 일부러 그렇게 실패한다).
    """
    wanted = ("cashflow_line", "cost_benefit_pie")
    charts = render_charts(
        {
            "cashflows": [-2_000_000.0, 400_000.0, 500_000.0, 600_000.0, 700_000.0],
            "items": {"설비비": 1_500_000.0, "시공비": 400_000.0, "운영비": 100_000.0},
        },
        tags=wanted,
    )
    assert set(wanted) <= set(charts)
    for tag, artifact in charts.items():
        assert artifact.mime == "image/png"
        assert artifact.payload.startswith(b"\x89PNG\r\n\x1a\n"), f"{tag}: PNG 가 아니다"


@pytest.mark.manual
@pytest.mark.req("FR-1001-AC5")
def test_manual_check_mc1_stub() -> None:
    """13.8: 수동 검증 MC-1 명세 스텁 (FR-1001-AC5)
    심의 경험자 3명 대상 설명 재현 테스트를 위한 스텁.
    docs/manual-checks.yaml 에 등재되어야 함.
    """
    pass
