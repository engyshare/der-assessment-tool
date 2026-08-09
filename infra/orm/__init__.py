"""infra.orm — §7.2 엔티티 전건을 한 곳에서 노출.

이 패키지를 import 하면 모든 모델이 `Base.metadata` 에 등록된다. 그래서
`Base.metadata.create_all(engine)` 한 번으로 전 테이블이 만들어진다.

별도 서브모듈로 나눈 이유는 NFR-206 (파일 500줄 이내) — 22개 엔티티가 한 파일에
들어가면 코드 스프롤 임계치를 넘는다. 분할 기준은 도메인 경계(§7.2 의 분류) 다.
"""
from __future__ import annotations

from infra.orm.assumption import AssumptionItem, AssumptionSet
from infra.orm.catalog import (
    CommonAsset,
    IncentiveScheme,
    TariffTable,
    TechCatalog,
)
from infra.orm.identity import Project, User
from infra.orm.regulation import (
    BenefitExclusionRule,
    RegulationItem,
    RegulationProfile,
    TimeSeriesDataset,
)
from infra.orm.run import (
    CaseResult,
    InfluenceRank,
    ProformaLine,
    ResultMetric,
    Run,
)
from infra.orm.scenario import (
    CaseGrid,
    DERDatasetBinding,
    DERInstance,
    Scenario,
    ScenarioOverride,
)

# `__all__` 을 알파벳순이 아닌 도메인 분류순으로 두었다 — 같은 컨텍스트의
# 엔티티가 나란히 보이는 것이 읽기에 유리하다.
#
# **tuple 로 둔 이유 (NFR-205)**: 모듈 수준 list 는 가변이다. 지금 아무도
# append·remove 하지 않지만, DER-VET `Params.py` 의 클래스 변수가 정확히
# 이 형태였고 런타임 변형이 병렬 실행(FR-805)에서 다른 케이스 결과를
# 조용히 바꿨다. tuple 로 두면 변형 자체가 불가능해진다. 파이썬은
# `__all__` 에 tuple 을 허용한다.
__all__ = (  # noqa: RUF022
    # identity
    "User",
    "Project",
    # assumption
    "AssumptionSet",
    "AssumptionItem",
    # scenario
    "Scenario",
    "ScenarioOverride",
    "DERInstance",
    "DERDatasetBinding",
    "CaseGrid",
    # catalog
    "TechCatalog",
    "TariffTable",
    "IncentiveScheme",
    "CommonAsset",
    # regulation
    "RegulationProfile",
    "RegulationItem",
    "BenefitExclusionRule",
    "TimeSeriesDataset",
    # run
    "Run",
    "CaseResult",
    "ProformaLine",
    "ResultMetric",
    "InfluenceRank",
)
