# 수용기준 ↔ 검증 항목 추적 매핑표

> **이 파일은 자동 생성됩니다. 직접 편집하지 마십시오.**
> 생성: `python scripts/gen_traceability.py`
> 입력: `spec-분산특구-경제성평가.md` · `docs/manual-checks.yaml` · `tests/`
> 근거: spec **NFR-107**

## 요약

| 항목 | 수 |
|---|---|
| 요구사항 | 105 |
| 그중 Must-have | 79 |
| 수용기준 총계 | 308 |
| 자동 검증 매핑 | 278 |
| 수동 검증 매핑 | 4 |
| **Must-have 미매핑** | **8** |
| 우선순위 미지정 요구사항 | 0 |
| **Phase 미지정 요구사항** | **9** |
| **차단 미수행 (판정불가)** | **1** |

> **Phase 미지정 9건 — §4.0 R-1 위반입니다.**
>
> `FR-203, FR-303, FR-503, FR-609, FR-804, FR-805, FR-903, FR-904, FR-1102`
>
> 그중 **Must-have 0건**
>
> 우선순위(중요도)와 Phase(시점)는 별개 축이며 §4.0 R-1은 **둘 다** 요구합니다.
> `Priority:` 줄의 인라인 표기와 부록 A.1 배정표 어느 쪽에서도 찾지 못했습니다.
> 부록 A.1은 **Must-have만** 등재하는 표이므로, 위 목록이 전부 Should-have 이하라면
> 그 표의 「미배정 0건」 표기와 모순되지 않습니다.
>
> **둘의 긴급도는 다릅니다.** Must-have가 여기 있으면 미매핑 게이트가 그 수용기준을
> 감시하면서도 *언제까지* 지켜야 하는지는 말하지 못하는 상태입니다. Should-have만
> 남았다면 R-1 정비 사항이며 게이트 판정에는 영향이 없습니다.

> **차단 미수행(판정불가) 1건.**
> `blocking_dod: true` 인 수동 검사가 아직 수행되지 않았습니다. Phase DoD
> 판정에서 이 항목들은 **"충족"이 아니라 "판정불가"** 로 셉니다.
>
> CI는 이 때문에 실패하지 않습니다 — 실패시키면 사람이 수행할 때까지 CI가
> 영구히 빨간불이 되며, 그것은 `manual-checks.yaml` 머리말이 스스로 막으려는
> 두 상황 중 하나입니다. 대신 Phase 완료 판정을 사람이 이 목록을 보고
> 내려야 합니다.
>
> · `FR-1001-AC5` — MC-1 (미수행)

> **미매핑 8건.** NFR-107은 미매핑 0건을 요구합니다.
>
> 현재 저장소에 테스트가 없으므로 전건 미매핑인 것이 정상입니다. 이 표는
> **Wave 0 시점의 작업 목록**으로 읽으십시오 — 각 행이 곧 작성해야 할 테스트
> 하나입니다. 구현이 진행되면서 `자동`으로 채워집니다.
>
> 테스트에 `@pytest.mark.req("FR-104-AC3")` 마커를 달면 이 표에 반영됩니다.

## 매핑

| 요구사항 | 우선순위 | Phase | 수용기준 | 내용 | 검증 | 위치 |
|---|---|---|---|---|---|---|
| `FR-101` | Must-have | 1 | `FR-101-AC1` | 속성: name, tag, dt, carries_electric, carries_heat, carries_cool, consumes_fuel, lifetime,… | 자동 | test_der_contract.py 6건, test_ess.py, test_heatpump.py |
|  |  | 1 | `FR-101-AC2` | 메서드: capex(), fixed_om(), variable_om(), replacement_schedule(), salvage_value(), dispatc… | 자동 | test_der_contract.py 5건, test_ess.py 5건, test_ev_v2g.py 3건, test_heatpump.py 5건, test_load.py 4건, test_pv.py 8건, test_thermal_load.py 3건 |
|  |  | 1 | `FR-101-AC3` | 신규 자원 클래스가 위 인터페이스만 구현하면 코어 엔진 수정 없이 동작 (단위 테스트로 실증) | 자동 | test_der_contract.py, test_smoke_wave0.py |
|  |  | 1 | `FR-101-AC4` | 매체 플래그에 따라 엔진이 전기·열·냉 수지를 자동으로 분리 집계한다 | 자동 | test_der_contract.py 3건, test_heatpump.py 3건, test_pv.py 2건, test_rule_based.py |
| `FR-102` | Must-have | 1 | `FR-102-AC1.PV` | PV 태양광 (옥상/벽면 BIPV 구분) — 용량(kW), 이용률(%) 또는 8760 발전 시계열, 방위·경사, 연간 열화율, 인버터 수명 | 자동 | test_pv.py 9건, test_pv_validation.py 2건 |
|  |  | 1 | `FR-102-AC1.ESS` | ESS 배터리 (신품/사용후배터리) — 정격용량(kWh), 정격출력(kW), RTE(%), SOC 상하한, 사이클수명, 달력수명, EOL 잔존율 | 자동 | test_ess.py 6건 |
|  |  | 1 | `FR-102-AC1.EV_V2G` | EV_V2G 전기차 + 양방향 충전기 — 대수, 배터리(kWh), 최대 충방전(kW), 접속가능시간대, 참여율, 열화 보상단가 | 자동 | test_ev_v2g.py 18건 |
|  |  | 1 | `FR-102-AC1.HeatPump` | HeatPump 히트펌프 (난방/급탕) — 정격 열출력(kW), COP 곡선(외기온 함수), 열부하 대응 방식 | 자동 | test_heatpump.py 11건 |
|  |  | 1 | `FR-102-AC1.Load` | Load 전기부하 (가구/공용부/상업) — 8760 부하 시계열 또는 월사용량+표준 프로파일, 연간 증가율 | 자동 | test_load.py 15건 |
|  |  | 1 | `FR-102-AC1.ThermalLoad` | ThermalLoad 열부하 (난방·급탕) — 8760 열부하 시계열 또는 난방도일 기반 추정 | 자동 | test_thermal_load.py 10건 |
|  |  | 2 | `FR-102-AC1.VPP` | VPP 통합발전소 (자원 집합 + 시장참여) — 집합 자원 ID 목록, 운영수수료(%), 시장참여 유형 | **미매핑** | — |
|  |  | 2 | `FR-102-AC1.Boiler` | Boiler 보조 열원 (가스/전기) — 열효율, 연료단가, 연료종 | **미매핑** | — |
|  |  | 3 | `FR-102-AC1.Genset` | Genset 비상·상시 발전기 — 정격출력, 열소비율, 연료단가, 최소부하율 | **미매핑** | — |
| `FR-103` | Must-have | 1 | `FR-103-AC1` | 한 시나리오 내에 PV#1(햇빛소득마을 조건), PV#2(자가용 조건)이 동시 존재 | 자동 | test_financial_isolation.py |
|  |  | 1 | `FR-103-AC2` | 각 인스턴스는 독립적인 IncentiveScheme 참조를 가진다 (FR-604) | 자동 | test_financial_isolation.py |
|  |  | 1 | `FR-103-AC3` | 두 인스턴스의 현금흐름이 프로포마에서 분리된 행으로 표시된다 | 자동 | test_financial_isolation.py |
| `FR-104` | Must-have | 1 | `FR-104-AC1` | PV: 연 degradation_rate(%/년) 발전량 감소 | 자동 | test_smoke_wave0.py, test_ev_v2g.py, test_heatpump.py, test_pv.py 2건 |
|  |  | 1 | `FR-104-AC2` | ESS: 사이클 누적 + 달력 열화 중 보수적 값 적용, EOL(기본 80%) 도달 시 교체비 계상 | 자동 | test_ess.py 6건 |
|  |  | 1 | `FR-104-AC3` | 수명 도달 자원은 replace / retire 선택 가능. 선택의 결과는 아래 「retire 의 의미」 다섯으로 정한다 (v0.14 명확화 — 조항이 선택지만… | 자동 | test_der_contract.py 2건, test_ess.py 5건, test_ev_v2g.py 4건, test_heatpump.py 4건, test_load.py 7건, test_pv.py 5건, test_thermal_load.py 6건 |
|  |  | 1 | `FR-104-AC4` | 인버터 등 부속설비의 독립 수명(10~12년)을 본체와 분리 관리 | 자동 | test_smoke_wave0.py, test_ess.py, test_ev_v2g.py, test_heatpump.py 2건, test_load.py, test_pv.py 3건, test_thermal_load.py 3건 |
|  |  | 1 | `FR-104-AC5` | 분석기간 종료 시 잔존 수명 비례 잔존가치를 최종연도에 계상 | 자동 | test_der_contract.py 2건, test_ess.py 2건, test_ev_v2g.py, test_heatpump.py 2건, test_load.py 2건, test_pv.py 3건, test_thermal_load.py |
| `FR-105` | Must-have | 1 | `FR-105-AC1` | 자원 클래스는 자신이 지원하는 운전 방법 목록을 선언한다. 예: | 자동 | test_der_contract.py, test_dv_rule_enforcement.py 2건, test_ess.py 3건, test_ev_v2g.py 4건, test_heatpump.py 5건, test_operating_mode_mapping.py, test_pv.py 5건, test_pv_validation.py |
|  |  | 1 | `FR-105-AC2` | 운전 방법은 자원 클래스에 함께 정의되며, 신규 운전 방법 추가 시 코어 엔진 수정이 발생하지 않는다 (NFR-201과 동일 기준) | 자동 | test_17_11_sg5.py, test_pv.py |
|  |  | 1 | `FR-105-AC3` | 동일 시나리오 내에서 같은 유형의 두 인스턴스가 서로 다른 운전 방법을 가질 수 있다 (예: 가구용 ESS는 자가소비 우선, 공용부 ESS는 피크 저감) | 자동 | test_ess.py, test_pv.py |
|  |  | 1 | `FR-105-AC4` | 선택한 운전 방법이 FR-302 디스패치 우선순위와 어떻게 결합되는지 리포트에 표기한다 | 자동 | test_dispatch_notes.py 5건 |
|  |  | 1 | `FR-105-AC5` | 운전 방법을 케이스 그리드의 탐색 변수로 지정할 수 있다 (FR-801) | 자동 | test_operating_mode_mapping.py |
| `FR-106` | Must-have | 1 | `FR-106-AC1` | CommonAsset은 capex() / fixed_om() / lifetime / replacement_schedule() / salvage_value() 를… | 자동 | test_common_asset.py 4건 |
|  |  | 1 | `FR-106-AC2` | 기본 제공 유형: CEMS(단지 통합 제어·모니터링), HEMS(가구 단위), 공용 계량·통신 설비 | 자동 | test_common_asset.py 3건 |
|  |  | 1 | `FR-106-AC3` | 소프트웨어 개발비와 하드웨어를 분리 계상한다. 감가상각 내용연수와 교체 주기가 다르며(SW는 재개발, HW는 교체), 잔존가치 산정도 달라진다 | 자동 | test_common_asset.py 7건 |
|  |  | 1 | `FR-106-AC4` | 연간 운영비(라이선스·클라우드·유지보수·관제 인건비)를 fixed_om()으로 계상하고 물가상승률을 적용한다 | 자동 | test_common_asset.py 3건 |
|  |  | 1 | `FR-106-AC5` | 안분 규칙을 선언적으로 지정한다: 가구 균등 배분 / 설비용량 비례 / 안분하지 않고 단지 총계로만 표시. 선택한 규칙이 리포트에 명시된다 | 자동 | test_common_asset.py 10건 |
|  |  | 1 | `FR-106-AC6` | 가구 단위 경제성 산출 시 안분된 공통비용이 별도 행으로 표시되어, 가구 자체 설비 비용과 구분된다 | 자동 | test_common_asset.py 3건 |
|  |  | 1 | `FR-106-AC7` | CommonAsset이 없는 모델(단독주택 등)도 정상 동작한다 (기본값 없음) | 자동 | test_common_asset.py 4건 |
| `FR-201` | Must-have | 1 | `FR-201-AC1` | GUI에서 자원 추가/삭제/복제로 구성 가능하며, 구성 변경 시 엔진 코드 변경이 발생하지 않는다 | 자동 | test_model_composition_router.py 4건, test_composition.py 7건, test_model_composer_view.py 5건 |
|  |  | 1 | `FR-201-AC2` | 모델 정의 전체가 단일 JSON 문서로 export/import 된다 | 자동 | test_model.py |
| `FR-202` | Must-have | 1 | `FR-202-AC1` | 하나의 AssumptionSet을 참조하는 여러 모델을 일괄 실행한다 | 자동 | test_comparison.py 3건 |
|  |  | 1 | `FR-202-AC2` | 비교표에 모델별 NPV·IRR·회수기간·필요 지원율을 나란히 표시한다 | 자동 | test_comparison.py 3건 |
|  |  | 1 | `FR-202-AC3` | 전제가 동일함이 시스템적으로 보장되며(동일 AssumptionSet ID 표시), 모델별로 다른 값이 사용된 항목은 별도 강조된다 | 자동 | test_comparison.py 3건 |
|  |  | 2 | `FR-202-AC4` | 모델 간 구성 차이(자원 유무·용량)를 diff 뷰로 제시한다 | **미매핑** | — |
| `FR-203` | Should-have | - | `FR-203-AC1` | Site(가구/건물) N개를 Community(단지)로 묶을 수 있다 | **미매핑** | — |
|  |  | - | `FR-203-AC2` | 가구 단위 경제성과 단지 통합 경제성을 모두 산출한다 | **미매핑** | — |
|  |  | - | `FR-203-AC3` | 통합 시 발생하는 상계·공유 효과를 "통합 편익" 항목으로 분리 정량화한다 | **미매핑** | — |
| `FR-204` | Must-have | 1 | `FR-204-AC1` | Phase 1: 에너지자립가구 모델 — PV + 히트펌프 + EV/V2G + ESS, 10~20가구, 기존주택형/모듈러주택형 2 변형 | 자동 | test_phase1_dod.py, test_templates.py |
|  |  | 2 | `FR-204-AC2` | 마을단위 분산특구 6개 모델, 아파트 마이크로그리드 모델 | 자동 | test_templates.py |
|  |  | 1 | `FR-204-AC3` | 템플릿 로드 시 모든 파라미터에 기본값과 출처가 채워진다 | 자동 | test_phase1_dod.py, test_templates.py |
| `FR-205` | Must-have | 1 | `FR-205-AC1` | 다음이 정산 로직에 반영된다 — 개별 세대 직접계약 / 단일계약+관리주체 경유 / 분산특구 직접거래 / 상계거래 / 잉여 직거래 / 집합 PPA / VPP 경유 | 자동 | test_e2e_settlement_wiring.py 5건, test_payer_structure_contract.py 4건, test_settlement.py 9건 |
| `FR-301` | Must-have | 1 | `FR-301-AC1` | 매 스텝 자원별 충·방전·발전·소비량과 계통 수·송전량을 산출 | 자동 | test_der_contract.py 2건, test_ess.py, test_ev_v2g.py, test_rule_based.py |
|  |  | 1 | `FR-301-AC2` | 전력·열 수지 균형식이 모든 스텝에서 오차 < 1e-6 kWh | 자동 | test_ess.py, test_thermal_load.py 2건, test_rule_based.py |
|  |  | 1 | `FR-301-AC3` | 시계열 행수 불일치 시 명확한 오류로 중단 | 자동 | test_der_contract.py 5건, test_leap_year_policy.py, test_heatpump.py, test_pv_validation.py, test_thermal_load.py 2건, test_rule_based.py 2건 |
|  |  | 1 | `FR-301-AC4` | (v0.14 신설) 계통 연계 용량 상한을 초과하는 운전 계획은 명확한 | 자동 | test_ess.py, test_pv_validation.py |
| `FR-302` | Must-have | 1 | `FR-302-AC1` | 다음 우선순위를 설정 가능한 순서로 적용 | 자동 | test_rule_based.py |
|  |  | 1 | `FR-302-AC2` | TOU 하 경부하 충전 / 최대부하 방전 차익거래 규칙을 옵션 활성화 | 자동 | test_ess.py, test_rule_based.py |
|  |  | 1 | `FR-302-AC3` | 규칙 순서·활성화를 UI에서 변경 가능하며 효과가 결과에 반영된다 | 자동 | test_rule_based.py |
| `FR-303` | Should-have | - | `FR-303-AC1` | 목적함수: 분석기간 총비용 최소화. 자원·SOC·계통 제약을 선형 제약으로 표현 | **미매핑** | — |
|  |  | - | `FR-303-AC2` | 최적화 창: 월 또는 연 단위 선택 | **미매핑** | — |
|  |  | - | `FR-303-AC3` | 동일 시나리오에서 MILP 총비용 ≤ 룰기반 총비용 을 회귀 테스트로 보장 | **미매핑** | — |
|  |  | - | `FR-303-AC4` | Infeasible 시 어떤 제약이 충돌했고 어느 편익이 원인인지 진단 (FR-403 연계) | **미매핑** | — |
| `FR-304` | Nice-to-have | 3 | `FR-304-AC1` | PV·ESS 용량을 결정변수로 NPV 최대화 조합 산출. 연간 손익과 자본비의 시간 스케일 정합을 위해 연금 환산 계수를 적용한다 (부록 C.3 B-2) | **미매핑** | — |
| `FR-305` | Nice-to-have | 3 | `FR-305-AC1` | 임의 시점 N시간 정전 시 부하 지속 시간 산출, EENS 화폐가치를 편익 계상 | **미매핑** | — |
| `FR-401` | Must-have | 1 | `FR-401-AC1` | 편익 1종 = 독립 클래스 1개로 구현되고, 각 편익은 활성화 여부를 개별 토글할 수 있다. 편익을 추가하거나 비활성화해도 코어 엔진(core/engine/·c… | 자동 | test_der_contract.py 2건, test_formulas.py |
|  |  | 1 | `FR-401-AC2.SelfConsumption` | SelfConsumption 자가소비 전기요금 절감 — (기존요금 − 신규요금), 누진·TOU 구조 반영 | 자동 | test_pv.py, test_formulas.py |
|  |  | 1 | `FR-401-AC2.SurplusSale` | SurplusSale 잉여전력 판매 — 잉여량 × 판매단가(직거래/상계/SMP) | 자동 | test_pv.py 2건, test_formulas.py |
|  |  | 1 | `FR-401-AC2.REC` | REC REC 수익 — 발전량 × 가중치 × REC 단가 | 자동 | test_pv.py 2건, test_formulas.py |
|  |  | 1 | `FR-401-AC2.DirectTrade` | DirectTrade 분산특구 직접거래 차익 — (약관요금 − 직접거래단가) × 거래량 − 거래지원수수료 | 자동 | test_formulas.py |
|  |  | 1 | `FR-401-AC2.PeakShaving` | PeakShaving 기본요금(피크) 절감 — 월 최대수요 저감분 × 기본요금 단가 | 자동 | test_ess.py, test_formulas.py |
|  |  | 1 | `FR-401-AC2.HeatCostSaving` | HeatCostSaving 열 비용 절감 (히트펌프) — (기존 열원 연료비 − 히트펌프 전력비) | 자동 | test_heatpump.py 2건, test_formulas.py |
|  |  | 2 | `FR-401-AC2.DemandResponse` | DemandResponse 수요반응 정산금 — 감축량 × 정산단가 (중복·배타 규칙 반영) | **미매핑** | — |
|  |  | 2 | `FR-401-AC2.VPPMarket` | VPPMarket VPP 시장참여 수익 — 시장정산 − 운영수수료 | **미매핑** | — |
|  |  | 3 | `FR-401-AC2.Resilience` | Resilience 정전 회피 편익 — EENS × VoLL | **미매핑** | — |
|  |  | 3 | `FR-401-AC2.DistributedBenefit` | DistributedBenefit 분산편익 크레딧 — 송배전 회피 + 손실 감소 + 계통서비스 + 온실가스 + 회복력 (기본 0, FR-404) | 자동 | test_formulas.py |
|  |  | 3 | `FR-401-AC2.CarbonCredit` | CarbonCredit 배출권 수익 — 감축량(tCO2) × KAU 단가 | **미매핑** | — |
| `FR-402` | Must-have | 1 | `FR-402-AC1` | 동시 발생 효과는 중복이 아니다 — 지불 주체가 다르거나 물리량이 다르면 정상 계상한다. 중복은 같은 화폐 흐름을 두 번 세는 것으로 한정한다. 시스템은 자가소… | 자동 | test_phase1_dod.py, test_exclusion_rules_contract.py, test_exclusion.py, test_exclusion_reject_wp28b.py |
|  |  | 1 | `FR-402-AC2.A` | 동일 물리량 이중 판매 — 같은 1 kWh를 자가소비 절감과 잉여판매로 동시 계상하거나 같은 시각 ESS 방전을 피크저감과 DR로 동시 계상하는 조합은 선언적 … | 자동 | test_phase1_dod.py, test_e2e_exclusion_wiring.py 3건, test_exclusion_rules_contract.py, test_pv.py, test_pv_validation.py, test_exclusion.py 2건, test_exclusion_reject_wp28b.py, test_settlement.py |
|  |  | 1 | `FR-402-AC2.B` | 인과 하류 편익이 상류에 이미 포함 — 배전망 회피 편익 ↔ 전기요금 절감처럼 망 비용이 이미 망이용요금으로 회수된 경우, 하류 편익은 요금에 미반영된 증분만 … | 자동 | test_exclusion.py |
|  |  | 1 | `FR-402-AC2.C` | 동일 효과의 이중 화폐화 — 같은 tCO2에 배출권 수익(사업자 현금)과 사회적 탄소비용(사회 편익)을 동시 계상하지 않는다. 관점당 하나의 화폐화 방법만 허용… | 자동 | test_exclusion.py |
|  |  | 1 | `FR-402-AC2.D` | 제도적 배타 — 상계거래 참여 시 REC 발급 제한, DR 정산금과 요금 인센티브 중복 수취 금지 등은 규제 프로파일에 종속된 배타 규칙으로 관리하고 제도 개정… | 자동 | test_exclusion.py, test_exclusion_reject_wp28b.py |
|  |  | 1 | `FR-402-AC4` | 배타 규칙은 코드가 아닌 선언적 규칙 테이블로 관리한다. 각 규칙은 (편익A, 편익B, 배타유형 A~D, 근거, 적용 규제 프로파일) 을 보유한다 | 자동 | test_exclusion_rules_contract.py 4건, test_mapping_requirements.py |
|  |  | 1 | `FR-402-AC5` | 편익을 활성화할 때 시스템은 분산자원 경제성 평가 원칙 「부록 A. 편익 항목 추가 시 실무 적용 절차」 의 4문항 판정을 통과했는지 확인하고, 지불 주체가 특… | 자동 | test_payer_structure_contract.py 3건, test_mapping_requirements.py, test_settlement.py |
|  |  | 1 | `FR-402-AC6` | 리포트에 "편익 계상 내역" 을 표시한다: 계상된 편익 / 배타로 제외된 편익 / 증분만 계상된 편익(유형 B) / 미화폐화로 0 처리된 편익 | 자동 | test_phase1_dod.py, test_mapping_requirements.py |
|  |  | 1 | `FR-402-AC7` | 관점별(FR-704) 편익 집합이 서로 다름을 리포트에 명시하고, 보조금은 사회 관점에서 이전지출로 처리하여 편익에 포함하지 않는다 | 자동 | test_transfer.py |
| `FR-403` | Must-have | 1 | `FR-403-AC1` | 편익별 제약을 개별 제약으로 쌓지 않고, 제약 유형별 단일 시계열로 min/max 합성한다 | 자동 | test_conflict.py 3건 |
|  |  | 1 | `FR-403-AC2` | 각 시각별로 어느 편익이 그 제약값에 기여했는지 기록한다 | 자동 | test_conflict.py |
|  |  | 1 | `FR-403-AC3` | 시뮬레이션·최적화 실행 전에 min > max 충돌을 검사하고, 충돌 시 "2027-01-15 18:00에 ESS 방전 하한(예비력 확보)과 상한(SOC 제약)… | 자동 | test_conflict.py |
|  |  | 1 | `FR-403-AC4` | 무한대 표현에는 math.inf를 사용하며 유한 대형 상수를 sentinel로 쓰지 않는다 | 자동 | test_conflict.py |
| `FR-404` | Must-have | 1 | `FR-404-AC1` | 활성화 시 "정책 가정 편익 — 현행 제도 미반영" 경고를 리포트 상단에 표시 | 자동 | test_ev_v2g.py 4건 |
|  |  | 1 | `FR-404-AC2` | 활성화하더라도 본편익 합계와 분리된 별도 소계로 표시하며, 주 지표(할인 회수기간)는 본편익 기준값과 크레딧 포함값을 모두 제시한다 | 자동 | test_mapping_requirements.py |
|  |  | 1 | `FR-404-AC3` | 하위 항목(송배전 회피·손실 감소)은 FR-402 유형 B에 해당하므로, 현행 요금에 이미 반영된 부분을 제외한 미래 증설 회피 증분만 계상한다. 증분 분리 근… | 자동 | test_mapping_requirements.py |
| `FR-501` | Must-have | 1 | `FR-501-AC1` | 주택용 누진제 (구간별 단가·기본요금·필수사용량 공제) | 자동 | test_tariff.py |
|  |  | 1 | `FR-501-AC2` | TOU (계절 × 요일 × 시간대 매트릭스) — 2026 계절시간대별 개편안 반영 | 자동 | test_tariff.py |
|  |  | 1 | `FR-501-AC3` | 봄·가을 주말 할인 등 특례 할인 | 자동 | test_tariff.py |
|  |  | 1 | `FR-501-AC4` | 요금표는 코드가 아닌 데이터 파일(YAML/DB) 로 관리 (개정 시 코드 변경 불필요) | 자동 | test_tariff_loader.py 2건 |
|  |  | 1 | `FR-501-AC5` | 요금표에 유효기간(from~to) 부여, 분석연도에 맞는 표 자동 선택 | 자동 | test_tariff.py |
|  |  | 1 | `FR-501-AC6` | 한 시나리오 내에서 가구부(누진) / 공용부(고압 TOU) / 거래분(직접거래)에 서로 다른 체계 동시 적용 | 자동 | test_tariff.py |
|  |  | 1 | `FR-501-AC7` | 부가가치세(10%)와 전력산업기반기금(3.7%)을 별도 항목으로 계산하고 청구액에 합산한다 (v0.3 추가). 두 항목의 요율은 요금표 데이터에 포함되어 개정 … | 자동 | test_tariff.py |
|  |  | 1 | `FR-501-AC8` | 요금 명세를 항목별로 분해 표시한다: 기본요금 / 전력량요금 / 기후환경요금 / 연료비조정 / 부가세 / 기반기금. 편익 산식이 어느 항목을 절감했는지 추적 가… | 자동 | test_tariff.py |
| `FR-502` | Must-have | 1 | `FR-502-AC1` | 연간 충족률 = (특구 내 조달 전력량) / (총 사용량) | 자동 | test_compliance.py |
|  |  | 1 | `FR-502-AC2` | 70% 미달 시 부족전력량에 이중구조 요금(70% 도달분 / 초과분 분리) 적용 | 자동 | test_compliance.py |
|  |  | 1 | `FR-502-AC3` | 면제기간(현행 3년, 개정안 5~7년)을 파라미터화 | 자동 | test_compliance.py |
|  |  | 1 | `FR-502-AC4` | 미달 여부와 추가 비용을 대시보드에 경고로 강조 | 자동 | test_compliance.py, test_dashboard.py 3건 |
| `FR-503` | Should-have | - | `FR-503-AC1` | 산정식·결과 표시, 미달 시 경고. 산정 기준(자급량 기준 / 계통부담 기준) 선택 가능 | 자동 | test_compliance.py |
| `FR-504` | Must-have | 1 | `FR-504-AC1` | 기본 구성: RegulationProfile = {70% 의무 비율, 면제기간, 최소계약기간, 초과발전량 우선공급, 망이용요금 예외, 거래지원수수료, 자급률 기… | 자동 | test_profile.py |
|  |  | 1 | `FR-504-AC2` | 항목 추가 확장성: 제도가 신설 항목을 요구할 때 스키마 변경·코드 배포 없이 항목을 추가할 수 있어야 한다. 프로파일은 고정 컬럼이 아닌 (항목키, 값, 단위… | 자동 | test_profile.py |
|  |  | 1 | `FR-504-AC3` | 웹에서 편집: admin 권한 사용자가 웹 UI에서 프로파일을 생성·복제·수정할 수 있다. 파일 수정이나 재배포를 요구하지 않는다 | 자동 | test_regulation_admin_router.py 5건, test_profile_editing.py 6건, test_regulation_admin_view.py 4건 |
|  |  | 1 | `FR-504-AC4` | 개정 이력: 프로파일은 버전을 가지며 이전 버전으로 복원 가능하다. 두 버전 간 diff 뷰를 제공한다 | 자동 | test_profile.py, test_dashboard.py |
|  |  | 1 | `FR-504-AC5` | 유효기간: 각 항목에 유효기간(from~to)을 부여하여 분석연도에 맞는 값이 자동 선택된다. 분석기간 중 제도가 바뀌는 경우(예: 면제기간 3년 → 5년 개정… | 자동 | test_profile.py |
|  |  | 1 | `FR-504-AC6` | 근거 추적: 각 항목에 근거 고시·조문 링크와 최종확인일 필드를 보유한다 | 자동 | test_profile.py |
|  |  | 1 | `FR-504-AC7` | 프로파일 교체 영향: 시나리오의 프로파일 참조를 바꾸면 재실행 없이 어떤 항목이 달라지는지 미리보기를 제공하고, 재실행 시 결과 차이를 강조 표시한다 | 자동 | test_profile.py |
|  |  | 1 | `FR-504-AC8` | 비교 실행: "현행 / 개정안 / 메가특구 준용" 등 복수 프로파일을 케이스 그리드의 탐색 변수로 지정하여 한 번의 실행으로 제도 시나리오를 비교할 수 있다 (… | 자동 | test_regulation_axis.py 3건, test_profile.py |
| `FR-601` | Must-have | 1 | `FR-601-AC1` | 소유 범위 (v0.3 확정 — 이중 소유 금지): AC2.*가 열거하는 분류의 항목은 AssumptionSet이 단독 소유하며, Scenario는 이를 직접 보… | 자동 | test_scenario_ownership.py 3건 |
|  |  | 1 | `FR-601-AC2.cost` | 비용 — 설비 단가, 설치·시공비, O&M 비율, 교체비 | 자동 | test_scenario_ownership.py 2건 |
|  |  | 1 | `FR-601-AC2.performance` | 성능·수명 — 이용률, COP, RTE, 수명, 열화율 | 자동 | test_scenario_ownership.py 2건 |
|  |  | 1 | `FR-601-AC2.market_price` | 시장 단가 — SMP, REC, PPA/직접거래 단가 | 자동 | test_scenario_ownership.py 2건 |
|  |  | 1 | `FR-601-AC2.finance` | 재무 — 할인율(명목/실질 구분 포함), 분석기간, 건설기간 | 자동 | test_scenario_ownership.py 2건 |
|  |  | 1 | `FR-601-AC2.escalation` | 상승률 — 일반 물가상승률 / 전기요금 인상률 / 연료비 상승률 / 인건비 상승률을 각각 별도 항목으로 보유 | 자동 | test_scenario_ownership.py 2건 |
|  |  | 1 | `FR-601-AC2.reference` | 참조 — 요금표 참조, 규제 프로파일 참조 | 자동 | test_scenario_ownership.py 3건 |
|  |  | 1 | `FR-601-AC3` | 전기요금 인상률 분리 (v0.3 추가): 물가상승률과 별개 항목으로 관리한다. 자가소비·열비용 절감 편익의 20년 누계를 좌우하는 최대 민감 인자이며, 일반 물… | 자동 | test_loader.py |
|  |  | 1 | `FR-601-AC4` | 항목 메타데이터 (v0.5 정정 — 6종 → 7종): 모든 항목이 근거 표기 기준 5절이 정한 경제성 입력값 필수 부기 항목 7종을 보유한다. 이 목록은 정본이… | 자동 | test_items.py, test_loader.py, test_assumption_provider.py |
|  |  | 1 | `FR-601-AC5.value_unit` | 값·단위 — 스키마는 value_json + unit 두 컬럼이므로 이 조항과 1:1 대응이 아니다. 두 컬럼이 모두 채워져야 충족한다 | 자동 | test_items.py |
|  |  | 1 | `FR-601-AC5.base_year` | 기준일·기준연도·버전 — 언제 시점의 값인지. 항목명은 3요소이나 스키마 컬럼은 base_year 하나뿐이다. 이는 스키마 쪽 결손이며 같은 이름을 씀으로써 결… | 자동 | test_items.py |
|  |  | 1 | `FR-601-AC5.applicable_scope` | 적용 범위·조건 — 대상·구간·통계 집계 범위 (v0.5 추가) | 자동 | test_items.py |
|  |  | 1 | `FR-601-AC5.derivation_method` | 산출 방법·표본 — 추정치/실측치 구분, 표본 규모 (v0.5 추가) | 자동 | test_items.py |
|  |  | 1 | `FR-601-AC5.source` | 출처 — 문서명 · 위치(조항·페이지·표 번호) · 전체 URL | 자동 | test_items.py |
|  |  | 1 | `FR-601-AC5.verified_at` | 최종확인일 — 실제로 열어본 날짜 | 자동 | test_items.py |
|  |  | 1 | `FR-601-AC5.confidence` | 신뢰도 (축 2) — 확정 / 추정 / 가정 | 자동 | test_items.py |
|  |  | 1 | `FR-601-AC6` | 항목 유형: 항목은 스칼라형(단가·비율 등)과 참조형(요금표·규제 프로파일 등 다른 엔티티를 가리키는 항목) 두 가지를 지원한다. 참조형 항목도 동일한 7종 메… | 자동 | test_items.py, test_assumption_provider.py |
|  |  | 1 | `FR-601-AC7` | 신뢰도 (v0.5 정정): 확정 / 추정 / 가정 3단계. 정의는 근거 표기 기준 2절을 따르며 여기서 재정의하지 않는다. 가정 항목이 결과에 미친 영향도를 리… | 자동 | test_items.py, test_no_deprecated_vocabulary.py |
|  |  | 1 | `FR-601-AC8` | 버전·diff: 이름·버전으로 저장되고 두 버전 간 diff 뷰를 제공한다 | 자동 | test_set.py |
|  |  | 1 | `FR-601-AC9` | 공유: 하나의 AssumptionSet을 여러 사업모델이 공유 참조한다 (FR-202의 전제 동일성 보장 근거) | 자동 | test_set.py |
| `FR-602` | Must-have | 1 | `FR-602-AC1` | 시나리오 수준에서 특정 항목만 덮어쓸 수 있다 | 자동 | test_set.py |
|  |  | 1 | `FR-602-AC2` | 리포트에 "기준 전제 대비 변경 항목" 목록이 자동 생성된다 | 자동 | test_set.py |
|  |  | 1 | `FR-602-AC3` | 오버라이드 시 사유 입력을 권장 필드로 제공한다 | 자동 | test_set.py |
| `FR-603` | Must-have | 1 | `FR-603-AC1` | 항목 필드 (v0.5 정정): (자원유형, 규격, 단가·단위, 기준일·기준연도·버전, 적용 범위·조건, 산출 방법·표본, 출처(문서명·위치·전체URL), 최종확… | 자동 | test_catalog.py |
|  |  | 1 | `FR-603-AC2` | 카탈로그 값과 사용자 변경값이 리포트에서 시각적으로 구분된다 | 자동 | test_catalog.py |
|  |  | 1 | `FR-603-AC3` | 기준연도가 분석연도와 다르면 물가 조정 후 사용하며 조정 내역을 표시한다 | 자동 | test_catalog.py 2건 |
| `FR-604` | Must-have | 1 | `FR-604-AC1` | 스킴 구성 | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC2` | 보조: 보조율(%) 또는 정액(원), 상한, 대상 비용 범위(설비비만 / 설치비 포함) | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC3` | 융자: 융자율(%), 연이자율, 거치기간(년), 상환기간(년), 상환방식(원리금균등/원금균등/만기일시) | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC4` | 자부담: 잔여 비율 자동 계산 | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC5` | 세제: 세액공제율, 감가상각 방식·내용연수 | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC6` | 지원 주체: 국비 / 지방비 / 민간 | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC7` | 보조 확정액 + 융자 확정액 + 자부담액 = 대상 총사업비 (오차 1원 이내) | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC8` | 보조 확정액 = min(대상비용 × 보조율, 보조 상한) 또는 정액 | 자동 | test_incentive.py |
|  |  | 1 | `FR-604-AC9` | 자부담액은 잔여로 자동 계산되며 음수가 될 수 없다 | 자동 | test_incentive.py 4건 |
| `FR-605` | Must-have | 1 | `FR-605-AC1` | 자원 유형별 상이한 조건이 한 시나리오에서 동시 적용되고 프로포마에 분리 표시된다 | 자동 | test_incentive.py |
| `FR-606` | Must-have | 1 | `FR-606-AC1` | 거치기간 중 이자만, 상환기간 중 원리금 상환 스케줄 생성 | 자동 | test_casevariant_contract.py, test_incentive.py |
|  |  | 1 | `FR-606-AC2` | 상환 스케줄이 프로포마 독립 행으로 표시되고 총 이자비용이 별도 집계된다 | 자동 | test_incentive.py |
| `FR-607` | Must-have | 1 | `FR-607-AC1` | 모든 실행에서 지원 0 케이스가 자동 포함되어 결과 상단에 표시된다 | 자동 | test_phase1_dod.py, test_incentive_cases.py 4건, test_casevariant_contract.py 4건, test_incentive.py |
|  |  | 1 | `FR-607-AC2` | "무지원 시 회수기간 XX년 / 목표 대비 부족분 YY년" 형태로 격차를 명시한다 | 자동 | test_incentive.py |
|  |  | 1 | `FR-607-AC3` | 기준선의 정의 (v0.5 추가): 지원 0은 본 사업의 지원이 0을 뜻한다. 타 사업으로 확정 지원된 설비는 기준선에 포함하고, 지원 예정(미확정)은 제외한다.… | 자동 | test_casevariant_contract.py, test_incentive.py |
| `FR-608` | Must-have | 1 | `FR-608-AC1` | 목표 지정: "할인 회수기간 ≤ 10년" / "NPV ≥ 0" / "IRR ≥ 5%" 중 택일 또는 복수 | 자동 | test_phase1_dod.py, test_incentive.py 4건 |
|  |  | 1 | `FR-608-AC2` | 지정한 단일 변수(기본: 보조율)를 이분 탐색하여 목표 달성 최소값을 0.1%p 정밀도로 산출 | 자동 | test_phase1_dod.py, test_incentive.py |
|  |  | 1 | `FR-608-AC3` | 단조성 검사 (v0.3 추가): 이분 탐색은 목표 지표가 탐색 변수에 대해 단조라는 가정에 의존한다. 보조 상한·정액 보조·계단형 조건이 섞이면 비단조 구간이 … | 자동 | test_incentive.py |
|  |  | 1 | `FR-608-AC4` | 해가 없으면(보조 100%에도 미달) 그 사실과 부족분을 명시 | 자동 | test_incentive.py 2건 |
|  |  | 1 | `FR-608-AC5` | 역산 대상 변수를 보조율 외 융자금리·거치기간·직접거래단가·REC단가로도 지정 가능 | 자동 | test_incentive.py 3건 |
| `FR-609` | Should-have | - | `FR-609-AC1` | 보조율 × 융자조건 2차원 평면에서 목표 지표를 동일하게 달성하는 조합 곡선을 산출 | 자동 | test_incentive.py |
|  |  | - | `FR-609-AC2` | 각 조합의 정부 재정 부담 현가를 병기하여 최소 부담 조합을 강조 표시 | 자동 | test_incentive.py |
|  |  | - | `FR-609-AC3` | 사업자 관점 지표와 정부 재정 관점 지표를 동시 표시 | 자동 | test_incentive.py |
| `FR-610` | Must-have | 1 | `FR-610-AC1` | 확정된 지원안(예: ESS 50%·MG 70%)을 직접 입력하여 그 조건 하 경제성을 평가한다. 이 모드에서도 무지원 기준선(FR-607)은 함께 표시된다 | 자동 | test_incentive.py |
| `FR-611` | Must-have | 1 | `FR-611-AC1` | IncentiveScheme에 funding_program(재원 사업명)과 is_prefunded(타 사업 기지원 여부), prefunded_status(확정 … | 자동 | test_ess.py, test_incentive.py |
|  |  | 1 | `FR-611-AC2` | is_prefunded=True인 설비의 취득원가는 금액을 0으로 만들지 않고 전액 계상한다. 관점별 처리는 AC3. 각 조항이 정한다 (v0.9: v0.8까지… | 자동 | test_ess.py, test_incentive.py |
|  |  | 1 | `FR-611-AC3.OWNER` | 사업자·주민 — 자기부담 0 (현금흐름 미발생). 근거: 실제 지출이 없음 | 자동 | test_ess.py, test_incentive.py |
|  |  | 1 | `FR-611-AC3.SOCIAL` | 사회 — 전액 비용. 근거: 재원이 어디서 왔든 자원은 소모됨 (분산자원 경제성 평가 원칙 원칙 2-3 관점 분리) | 자동 | test_incentive.py 3건 |
|  |  | 1 | `FR-611-AC3.GOV` | 정부 — 본 사업 재정부담에서 제외하되 타 사업 국비 행으로 분리 표시. 근거: 본 사업의 필요 지원액과 섞이면 안 됨 | 자동 | test_ess.py, test_incentive.py |
|  |  | 1 | `FR-611-AC4` | 지원 예정 상태는 미확정 리스크로 취급한다. 해당 설비를 제외한 케이스를 함께 산출하여 "지원 무산 시 회수기간"을 병기한다 | 자동 | test_incentive.py |
|  |  | 1 | `FR-611-AC5` | 프로포마에 기지원 설비가 별도 행으로 표시되고, 재원 사업명이 함께 출력된다 | 자동 | test_ess.py |
|  |  | 1 | `FR-611-AC6` | O&M·교체비·잔존가치는 기지원 여부와 무관하게 정상 계상한다. 무상으로 받은 설비도 유지비는 사업자가 낸다 | 자동 | test_ess.py |
| `FR-701` | Must-have | 1 | `FR-701-AC1` | 행: 자원별 자본비, 자원별 고정 O&M, 변동 O&M, 교체비, 융자 상환, 편익 항목별 수익, 세금, 잔존가치 | 자동 | test_proforma.py 2건, test_ev_v2g.py |
|  |  | 1 | `FR-701-AC2` | 열: 건설연도 ~ 분석 종료연도 | 자동 | test_proforma.py |
|  |  | 1 | `FR-701-AC3` | 항목별 상이한 에스컬레이션(물가상승률) 적용 가능 | 자동 | test_proforma.py, test_der_contract.py 2건 |
|  |  | 1 | `FR-701-AC4` | 수명 종료 자원의 비용·편익은 해당 연도 이후 0 처리 | 자동 | test_proforma.py |
| `FR-702` | Should-have | 2 | `FR-702-AC1` | 대표 연도만 시뮬레이션하고, 이전 연도는 역-에스컬레이션, 중간은 선형 보간, 이후는 에스컬레이션으로 채운다 | **미매핑** | — |
|  |  | 2 | `FR-702-AC2` | O&M 비용은 별도 처리 — 운전량이 아니라 설비 보유에 비례하므로 보간이 아닌 전후 채움 후 일괄 물가 적용 | **미매핑** | — |
|  |  | 2 | `FR-702-AC3` | 자원 수명 종료로 구성이 바뀌는 해는 자동으로 시뮬레이션 대상에 추가된다 | **미매핑** | — |
|  |  | 2 | `FR-702-AC4` | 보간으로 계산된 연도는 리포트에서 실계산 연도와 구분 표기된다 | **미매핑** | — |
| `FR-703` | Must-have | 1 | `FR-703-AC1.npv` | NPV 할인 순현재가치 — 할인율 파라미터화 (공공 4.5~5.5% 기본). 오라클 §13.0.2 순위 1 / 원 단위 완전 일치 | 자동 | test_metrics.py |
|  |  | 1 | `FR-703-AC1.irr` | IRR 내부수익률 — 오라클 §13.0.2 순위 2 / 0.01%. FR-704-AC2(사업자 관점)가 이 조항만 인용한다 | 자동 | test_metrics.py |
|  |  | 1 | `FR-703-AC1.mirr-value` | MIRR 수정내부수익률 (값) — 오라클 §13.0.2 순위 2 / 0.01% | 자동 | test_metrics.py |
|  |  | 1 | `FR-703-AC1.mirr-order` | MIRR 우선 표시 규칙 — 현금흐름의 부호변경이 다수일 때 MIRR을 IRR보다 우선 표시한다. 값이 아니라 조건부 표시 규칙이므로 AC1.mirr-value… | 자동 | test_indicators.py |
|  |  | 1 | `FR-703-AC1.bcr` | B/C 총편익 현가 / 총비용 현가 — 오라클 §13.0.2 순위 1. (v0.12 배정) 분자·분모를 각각 원 단위 완전 일치로 판정하고 비율 자체에는 별도 … | 자동 | test_metrics.py |
|  |  | 1 | `FR-703-AC1.lcoe-resource` | LCOE (자원별) 균등화발전원가 — 발전 자원(PV 등)별로만 산출한다 | 자동 | test_indicators.py |
|  |  | 1 | `FR-703-AC1.lcoe-mixed` | 혼합 모델 전체 LCOE 미산출 — 히트펌프·ESS가 섞인 모델의 전체 LCOE는 분모 정의가 성립하지 않으므로 산출하지 않는다 (v0.3 정정). 모델 전체 … | 자동 | test_indicators.py |
|  |  | 1 | `FR-703-AC1.payback-simple` | 단순 회수기간 누적 현금흐름 0 도달 — 소수점 보간 | 자동 | test_indicators.py |
|  |  | 1 | `FR-703-AC1.payback-discounted` | 할인 회수기간 할인 후 누적 0 도달 — 주 지표. 오라클 §13.0.2 순위 2 / 0.01% | 자동 | test_metrics.py |
|  |  | 1 | `FR-703-AC1.household-saving` | 가구당 월 절감액 원/호·월 — 주민 설득용 | 자동 | test_indicators.py |
|  |  | 1 | `FR-703-AC1.self-consumption` | 연간 자가소비율 % | 자동 | test_indicators.py |
|  |  | 1 | `FR-703-AC1.supply-duty` | 초과발전량 우선공급 의무 충족률 % — 제도 준수 지표. 현행 기준값 70%는 규제 프로파일(FR-504)이 들고 있으며 이 조항에 고정하지 않는다 | 자동 | test_indicators.py |
|  |  | 1 | `FR-703-AC1.fiscal-pv` | 정부 재정 부담 현가 원 — 지원 조합 비교용 (FR-609) | 자동 | test_indicators.py |
| `FR-704` | Must-have | 1 | `FR-704-AC1` | 주민: 자부담액 대비 요금 절감 회수기간 | 자동 | test_transfer.py |
|  |  | 1 | `FR-704-AC2` | 사업자: 총투자 대비 IRR | 자동 | test_transfer.py |
|  |  | 1 | `FR-704-AC3` | 정부: 투입 국비 1억원당 확보 설비용량(kW)·감축량(tCO2)·유발 민간투자액 — 재정효율 지표 | 자동 | test_transfer.py |
|  |  | 1 | `FR-704-AC4` | 세 관점이 하나의 리포트에 병렬 표시 | 자동 | test_perspective_report.py 7건 |
|  |  | 1 | `FR-704-AC5` | 사회 관점 산출 시 보조금은 이전지출로 처리하여 편익에 포함하지 않는다 (분산자원 경제성 평가 원칙 원칙 2-3 관점 분리 — 「핵심 규칙 세 가지」 1항) | 자동 | test_transfer.py |
|  |  | 1 | `FR-704-AC6` | 타 사업 기지원 설비(FR-611)의 관점별 계상 (v0.5 추가): 정부 관점 재정효율 지표의 분모(투입 국비)에는 본 사업 국비만 포함한다. 타 사업 국비는… | 자동 | test_transfer.py |
|  |  | 1 | `FR-704-AC7` | 관점 전환 시 어떤 항목이 왜 포함/제외되었는지를 리포트에 표시한다 (관점 섞기가 가장 흔한 중복 오류 — 도메인 원칙 2-3) | 자동 | test_transfer.py, test_perspective_report.py |
| `FR-705` | Must-have | 1 | `FR-705-AC1` | "설비 미설치 시 전기·열 비용"을 기준선으로 계산하고 모든 편익을 증분으로 산출. 기준선 자체 비용도 리포트에 표시 | 자동 | test_baseline.py, test_heatpump.py |
| `FR-801` | Must-have | 1 | `FR-801-AC1` | 임의 파라미터를 "탐색 변수"로 지정하고 값 목록(예: [저, 중, 고] 또는 [100, 150, 200])을 부여 | 자동 | test_casegrid.py |
|  |  | 1 | `FR-801-AC2` | 탐색 변수로 지정 가능한 대상에는 스칼라 파라미터뿐 아니라 자원 운전 방법(FR-105), 규제 프로파일(FR-504), 시계열 데이터셋(FR-905) 도 포함… | 자동 | test_casegrid.py |
|  |  | 1 | `FR-801-AC3` | 시스템이 전조합(Cartesian product)을 생성하고 일괄 실행한다 | 자동 | test_casegrid.py |
|  |  | 1 | `FR-801-AC4` | 케이스 수를 실행 전에 표시하고, 임계치(기본 500) 초과 시 경고 후 확인을 요구한다 | 자동 | test_casegrid.py, test_dv9_dv10.py 3건 |
|  |  | 1 | `FR-801-AC5` | 결과를 단일 테이블(케이스 × 지표)로 집계하고 CSV/XLSX 내보내기 가능 | 자동 | test_casegrid.py |
|  |  | 1 | `FR-801-AC6` | 기본 탐색 변수 프리셋 — 2단계 제공 (v0.5 정정): 사용자가 백지에서 시작하지 않도록 기본 세트를 제시하되, 기본 선택은 빠른 탐색 으로 한다 | 자동 | test_casegrid.py |
|  |  | 1 | `FR-801-AC7.quick` | 빠른 탐색 (기본값) — 결합 집합 1(설비단가·시공비) 3수준 × 할인율 3 × 전기요금 인상률 3 = 27 케이스, 예상 실행시간 81초(1 vCPU, NF… | 자동 | test_phase1_dod.py, test_17_2_dod2.py, test_casegrid.py |
|  |  | 1 | `FR-801-AC7.full` | 전체 탐색 (명시 선택) — 아래 6변수 전건 = 729 케이스, 예상 실행시간 2,187초(36.5분). DV-10 경고 후 백그라운드 실행으로 전환된다 (N… | 자동 | test_casegrid.py |
| `FR-802` | Must-have | 1 | `FR-802-AC1` | 여러 변수를 하나의 결합 집합으로 선언할 수 있다 | 자동 | test_casegrid.py |
|  |  | 1 | `FR-802-AC2` | 결합 집합 내 변수들은 동일 인덱스끼리만 조합된다. 예: {PV단가, ESS단가, 시공비}를 결합하고 각각 3수준을 주면 27개가 아닌 3개 케이스(저/저/저,… | 자동 | test_casegrid.py |
|  |  | 1 | `FR-802-AC3` | 결합 집합 내 값 목록의 길이가 다르면 명확한 오류로 거부한다 | 자동 | test_casegrid.py, test_dv9_dv10.py 2건 |
|  |  | 1 | `FR-802-AC4` | 결합 집합과 독립 변수를 혼용할 수 있다. 예: 결합 3케이스 × 독립 할인율 3수준 = 9케이스 | 자동 | test_casegrid.py |
|  |  | 1 | `FR-802-AC5` | 실행 전 생성될 케이스 목록을 미리보기로 제시한다 | 자동 | test_casegrid.py |
| `FR-803` | Must-have | 1 | `FR-803-AC1` | 2변수 히트맵: 축 변수 2개 선택 → 지표 등고선. "목표 달성 영역"을 음영으로 구분 | 자동 | test_phase1_dod.py, test_17_2_dod2.py, test_casegrid.py, test_charts_feasible_region.py 13건 |
|  |  | 1 | `FR-803-AC2` | 1변수 토네이도: 각 변수가 지표에 미치는 영향도 순위 | 자동 | test_casegrid.py |
|  |  | 1 | `FR-803-AC3` | 케이스 테이블에서 목표 달성/미달 케이스를 필터링 | 자동 | test_casegrid.py |
| `FR-804` | Should-have | - | `FR-804-AC1` | 주요 변수별로 NPV=0이 되는 임계값을 표로 제시 | **미매핑** | — |
| `FR-805` | Should-have | - | `FR-805-AC1` | 실행 중 완료 케이스 수·예상 잔여 시간 표시, 중단 가능 | 자동 | test_casegrid.py |
| `FR-901` | Must-have | 1 | `FR-901-AC1` | 회원가입, 로그인, 비밀번호 재설정, 세션 만료(기본 24시간) | 자동 | test_auth.py 8건 |
| `FR-902` | Must-have | 1 | `FR-902-AC1` | 이름·설명·태그·최종수정일시 부여 | 자동 | test_scenarios.py 2건 |
|  |  | 1 | `FR-902-AC2` | 저장 시 버전 이력이 남아 이전 버전 복원 가능 | 자동 | test_scenarios.py 2건 |
|  |  | 1 | `FR-902-AC3` | 삭제는 소프트 삭제(30일 보관) | 자동 | test_scenarios.py 2건 |
| `FR-903` | Should-have | - | `FR-903-AC1` | admin(카탈로그·요금표 관리) / analyst(시나리오 생성·실행) / viewer(공유 결과 열람) | **미매핑** | — |
| `FR-904` | Should-have | - | `FR-904-AC1` | 만료기한 설정 가능한 공유 토큰, 비로그인 열람 옵션 | **미매핑** | — |
| `FR-905` | Must-have | 1 | `FR-905-AC1` | 인스턴스 단위 바인딩: 데이터셋은 시나리오 전체가 아니라 개별 자원·부하 인스턴스에 바인딩된다. 가구부 부하와 공용부 부하, PV#1과 PV#2가 각각 다른 시… | 자동 | test_timeseries.py |
|  |  | 1 | `FR-905-AC2` | 교체 용이성: 인스턴스의 데이터셋 참조를 드롭다운 선택 한 번으로 교체할 수 있으며, 모델 구성이나 다른 인스턴스에 영향을 주지 않는다 | 자동 | test_timeseries.py |
|  |  | 1 | `FR-905-AC3` | 교체 영향 미리보기: 교체 시 재실행 전에 연간 총량·피크·부하율 등 요약 통계 비교를 제시하여 어떤 변화가 예상되는지 알 수 있다 | 자동 | test_timeseries.py |
|  |  | 1 | `FR-905-AC4` | 대체 입력 허용: 8760 시계열이 없는 경우 월사용량 + 표준 프로파일, 이용률, 난방도일 기반 추정 으로 대체 입력할 수 있고, 나중에 실측 시계열로 교체해… | 자동 | test_timeseries.py |
|  |  | 1 | `FR-905-AC5` | 탐색 변수화: 데이터셋 자체를 케이스 그리드의 탐색 변수로 지정하여 여러 연도·지역 시계열을 한 번에 비교할 수 있다 (FR-801) | 자동 | test_timeseries.py, test_dataset_axis.py 3건 |
|  |  | 1 | `FR-905-AC6` | 검증: CSV 업로드 시 스키마·행수·결측·이상치 검증 후 요약 통계 표시. 결측 처리 방식(선형보간/전월 평균/오류) 선택 가능 | 자동 | test_timeseries.py 3건 |
|  |  | 1 | `FR-905-AC7` | 공유·중복 방지: 동일 데이터셋을 여러 시나리오·인스턴스가 참조하며 중복 저장하지 않는다. 데이터셋 삭제 시 참조 중인 시나리오를 먼저 안내한다 | 자동 | test_timeseries.py |
|  |  | 1 | `FR-905-AC8` | 출처 메타데이터: 데이터셋도 (출처, 계측기간, 해상도, 신뢰도, 최종확인일) 을 보유하고 리포트에 표기한다 | 자동 | test_timeseries.py |
| `FR-1001` | Must-have | 1 | `FR-1001-AC1` | (가) 영향 인자 우선 제시 — 각 결과 지표 옆에 그 값을 좌우한 상위 인자를 영향도 순으로 제시한다. 순위는 감이 아니라 민감도 계산 결과로 정한다 (FR-… | 자동 | test_phase1_dod.py, test_report.py |
|  |  | 1 | `FR-1001-AC2` | (나) 산식 확인 — 임의 지표·프로포마 항목에서 그것을 만든 산식과 대입값을 그 자리에서 펼쳐볼 수 있다. 이동 횟수를 제약하지 않으며, "펼치면 보인다"가 … | 자동 | test_report.py |
|  |  | 1 | `FR-1001-AC3` | (다) 3중 표기 — 각 산식은 자연어 설명 + 수식 + 대입값으로 표기한다 | 자동 | test_phase1_dod.py, test_report.py 3건 |
|  |  | 1 | `FR-1001-AC4` | (라) 출처 동반 — 산식에 등장하는 모든 입력값에 출처·기준연도·신뢰도가 함께 표시된다 | 자동 | test_report.py |
|  |  | 1 | `FR-1001-AC5` | (마) 판정 기준 — 비개발자 검토자가 리포트만 보고 "이 회수기간이 왜 이 값인지"와 "어떤 가정이 바뀌면 결론이 달라지는지"를 설명할 수 있다. 측정: 심의… | 수동 | test_report.py (스텁) + MC-1 (미수행) |
| `FR-1002` | Must-have | 1 | `FR-1002-AC1` | 영향도 순 정렬이 1순위: 리포트 첫 화면은 주 지표(할인 회수기간)에 대한 인자별 영향도 순위로 시작한다. 입력 순·분류 순 나열은 부록으로 보낸다 | 자동 | test_phase1_dod.py, test_report.py, test_sensitivity_real.py, test_dashboard.py |
|  |  | 1 | `FR-1002-AC2` | 영향도 산출 방식: 각 인자를 합리적 변동 범위(전제의 신뢰구간, 없으면 기본 ±20%)에서 변동시켜 주 지표가 움직인 폭으로 측정한다. 케이스 그리드를 실행하… | 자동 | test_report.py, test_sensitivity_real.py |
|  |  | 1 | `FR-1002-AC3` | 각 인자마다 함께 표시: 사용값 / 단위 / 기준연도 / 출처 / 신뢰도 / 최종확인일 / 지표 변동폭 / 결론이 뒤집히는 임계값 존재 여부 | 자동 | test_report.py |
|  |  | 1 | `FR-1002-AC4` | 결론 전환 강조: 합리적 변동 범위 안에서 목표 달성 여부가 뒤바뀌는 인자는 최상단에 별도 강조한다. 이것이 정책 판단에서 가장 중요한 정보다 | 자동 | test_report.py, test_sensitivity_real.py 2건 |
|  |  | 1 | `FR-1002-AC5` | 가정 값 결합 표시 (v0.5 어휘 정정): 신뢰도 가정 인자는 영향도와 함께 표시하여, "영향도 낮은 가정"과 "영향도 높은 가정"을 구분할 수 있게 한다. … | 자동 | test_report.py 2건 |
|  |  | 1 | `FR-1002-AC6` | 전체 가정 목록: 영향도 순위와 별개로 전 가정 목록을 부록 시트로 제공한다 (재현·검증용) | 자동 | test_report.py 2건 |
| `FR-1003` | Must-have | 1 | `FR-1003-AC1` | XLSX: 엑셀에서 검산 가능한 형태 — 입력·프로포마·시계열·결과 시트를 분리하고, 주요 계산은 값이 아닌 셀 수식으로 출력하여 기존 엑셀 검토 방식과 병행 … | 자동 | test_report.py 3건 |
|  |  | 1 | `FR-1003-AC2` | PDF: 심의자료용 요약 (표지·가정·결과·조합탐색·결론 5부) | 자동 | test_report.py 2건 |
|  |  | 1 | `FR-1003-AC3` | JSON: 시나리오+전제 정의 전체 (재현용) | 자동 | test_report.py |
| `FR-1004` | Must-have | 1 | `FR-1004-AC1` | 일간 대표일 디스패치 스택, 월별 에너지 수지, 누적 현금흐름 곡선, 토네이도, 케이스 히트맵, 모델 비교 바 차트 | 자동 | test_chart_contract.py 5건, test_charts_wp28a.py 8건, test_report.py |
| `FR-1005` | Must-have | 1 | `FR-1005-AC1` | 실행마다 {실행ID, 시각, 코드 커밋 해시, 전제집합 버전, 시나리오 해시, 데이터셋 해시, 엔진 종류, 결과 요약} 기록. 동일 매니페스트 재실행 시 비트 … | 자동 | test_report.py |
| `FR-1101` | Must-have | 1 | `FR-1101-AC1` | 공개 저장소: 소스코드, 테스트, 계약, 골든 시나리오의 구조(입력 스키마·기대값 형식), 문서(README·CONTRIBUTING·이슈/PR 템플릿·docs/… | 자동 | test_license.py |
|  |  | 1 | `FR-1101-AC2` | 비공개 시드: 설비 단가·업계 견적·미공표 제도 검토 내용을 담은 AssumptionSet 시드 데이터와 골든 시나리오의 실제 수치. 별도 비공개 저장소 또는 … | 자동 | test_private_seed.py 2건 |
|  |  | 1 | `FR-1101-AC3` | 공개 저장소만으로 실행 가능해야 한다 — 비공개 시드가 없으면 합성 예시 전제(공개 가능한 대표값, 신뢰도 가정)로 동작한다. 외부 기여자가 코드를 돌려보고 개… | 자동 | test_seed_fallback.py |
|  |  | 1 | `FR-1101-AC4` | CI는 공개 저장소만으로 통과해야 한다. 비공개 수치에 의존하는 골든 회귀는 별도 잡으로 분리하고, 공개 CI에는 합성 전제 기반 회귀를 둔다 | 자동 | test_seed_fallback.py |
|  |  | 1 | `FR-1101-AC5` | 비공개 데이터가 공개 저장소에 유입되지 않도록 커밋 전 스캔을 pre-commit·CI에 둔다 (SC-7) | 자동 | test_ci_gates.py 3건 |
| `FR-1102` | Should-have | - | `FR-1102-AC1` | 카탈로그 값에 "정정 제안" 버튼 → 근거 URL·새 값 입력 → GitHub Issue 자동 생성 | **미매핑** | — |
| `FR-1103` | Must-have | 1 | `FR-1103-AC1` | GitHub Actions에서 pytest, ruff, 골든 시나리오 3종 수치 회귀 통과 시에만 머지 | 자동 | test_17_7_dod7.py 8건, test_phase1_measurements.py, test_regression_scenarios.py |
| `NFR-001` | Must-have | 1 | `NFR-001-M1` | 무료 티어(1 vCPU / 512MB) 벤치마크 10회 평균 | 자동 | test_casegrid.py 2건 |
| `NFR-002` | Must-have | 1 | `NFR-002-M1` | 27 / 100 / 500 케이스 3개 지점 종단 측정 | 자동 | test_casegrid.py 2건 |
| `NFR-003` | Should-have | 2 | `NFR-003-M1` | 초과 시 비동기 큐 전환 + 진행률 표시 | **미매핑** | — |
| `NFR-004` | Should-have | 1 | `NFR-004-M1` | 동시 사용자 20명 부하 테스트 | 자동 | test_performance_and_golden.py 2건 |
| `NFR-101` | Must-have | 1 | `NFR-101-M1` | 동일 시나리오 10회 실행 결과 해시 일치 | 자동 | test_rule_based.py, test_report.py |
| `NFR-102` | Must-have | 1 | `NFR-102-M1` | 시뮬레이션 종료 시 자동 assertion, 위반 시 실행 실패 | 자동 | test_rule_based.py |
| `NFR-103` | Must-have | 1 | `NFR-103-M1` | 20년 프로포마 합계와 항목별 합계 일치 검증 | 자동 | test_common_asset.py, test_der_contract.py, test_money_boundary.py 7건, test_smoke_wave0.py, test_ev_v2g.py |
| `NFR-104` | Must-have | 1 | `NFR-104-M1` | CI 회귀 테스트 | 자동 | test_17_7_dod7.py 3건, test_performance_and_golden.py 3건, test_regression_scenarios.py |
| `NFR-105` | Must-have | 1 | `NFR-105-AC1` | 모든 계산 코드는 테스트 우선(TDD) 으로 작성되어야 한다. 구현보다 그 구현을 규정하는 실패 테스트가 먼저 존재해야 한다 | 자동 | test_ci_gates.py 21건 |
| `NFR-106` | Must-have | 1 | `NFR-106-M1` | CI가 자원 레지스트리를 순회하여 각 자원에 대해 비용측 5종·편익측 전건 케이스의 존재와 통과를 확인한다. 케이스가 누락된 자원이 1건이라도 있으면 실패 | 자동 | test_17_8_dod8.py 7건, test_phase1_measurements.py |
| `NFR-107` | Must-have | 1 | `NFR-107-AC1.auto` | 자동 검증 — 매핑 형식은 @pytest.mark.req("FR-104-AC3"). CI는 테스트를 실행하고 통과를 확인한다 | 자동 | test_traceability_gate.py |
|  |  | 1 | `NFR-107-AC1.manual` | 수동 검증 — 매핑 형식은 @pytest.mark.req(...) + @pytest.mark.manual 로 skip 처리된 명세 스텁, 또는 docs/manu… | 자동 | test_traceability_gate.py |
|  |  | 1 | `NFR-107-AC2` | 미매핑 0건을 CI가 확인한다. 단 "매핑됨"에는 수동 검증 항목이 포함된다 | 자동 | test_traceability_gate.py |
|  |  | 1 | `NFR-107-AC3` | 수동 검증 항목은 수행 일자·수행자·결과를 docs/manual-checks.yaml에 기록한다. 기록이 없는 항목은 미수행으로 간주한다 | 자동 | test_traceability_gate.py 3건 |
|  |  | 1 | `NFR-107-AC4` | 매핑표(docs/traceability.md)는 CI가 자동 생성하며 자동/수동을 구분 표시한다 | 자동 | test_traceability_gate.py |
|  |  | 1 | `NFR-107-AC5` | 수동 검증 분류의 정본은 docs/manual-checks.yaml이다. spec은 어느 수용기준이 수동인지 열거하지 않는다. 대장의 전건에 대해 ⓐ crite… | 자동 | test_traceability_gate.py |
|  |  | 1 | `NFR-107-M1` | CI가 spec 수용기준 목록과 마커·YAML을 대조하여 미매핑 0건 확인. 구현: scripts/gen_traceability.py (Wave 0 산출물 0.… | 자동 | test_17_9_dod9.py, test_marker_substance.py 11건, test_traceability_gate.py 4건 |
| `NFR-201` | Must-have | 1 | `NFR-201-M1` | 신규 자원 추가 PR에서 core/engine/, core/cba/ diff 0줄 | 자동 | test_phase1_measurements.py |
| `NFR-202` | Must-have | 1 | `NFR-202-M1` | 소스 전체 수치 리터럴 스캔 lint 통과 | 자동 | test_e2e_settlement_wiring.py, test_ci_gates.py, test_der_contract.py 2건, test_tariff.py, test_settlement.py 2건 |
| `NFR-203` | Should-have | 1 | `NFR-203-M1` | pytest-cov CI 게이트 | 자동 | test_ci_gates.py |
| `NFR-204` | Should-have | 1 | `NFR-204-M1` | mypy strict 통과 | 자동 | test_ci_gates.py |
| `NFR-205` | Must-have | 1 | `NFR-205-M1` | 코드 리뷰 + lint 규칙. 근거: DER-VET Params.py의 클래스 변수 전역 상태는 동시 실행·테스트 격리를 불가능하게 만든다 (부록 C.5) | 자동 | test_ci_gates.py 2건, test_ess.py |
| `NFR-206` | Should-have | 1 | `NFR-206-M1` | lint 경고. 근거: DER-VET Params.py 1,830줄의 유지보수 실패 사례 | 자동 | test_17_12_scale.py 2건, test_phase1_measurements.py 2건, test_load.py, test_thermal_load.py |
| `NFR-207` | Must-have | 1 | `NFR-207-AC1` | 등록은 패키지 디렉터리 스캔 또는 데코레이터 자동 수집으로 수행한다. 신규 자원 추가 시 core/der/__init__.py, REGISTRY = [...] … | 자동 | test_router_collection.py, test_chart_contract.py, test_registry.py 6건 |
|  |  | 1 | `NFR-207-AC2` | 등록 충돌(동일 tag 중복)은 기동 시점에 명확한 오류로 검출된다 | 자동 | test_registry.py 3건 |
|  |  | 1 | `NFR-207-M1` | 신규 자원 추가 PR의 diff에 §16.4 공유 파일 목록의 변경 0줄 | 자동 | test_17_10_dod10.py, test_registry.py 2건 |
| `NFR-208` | Must-have | 1 | `NFR-208-AC1` | 상위 계층은 하위 계층을 import할 수 있으나 역방향 import는 금지한다 (예: core/der/ → core/engine/ 금지) | 자동 | test_import_boundaries.py |
|  |  | 1 | `NFR-208-AC2` | 동일 계층의 형제 구획 간 직접 import를 금지한다 (예: core/valuestream/ → core/regulation/ 직접 참조 금지, core/co… | 자동 | test_import_boundaries.py, test_thermal_load.py |
|  |  | 1 | `NFR-208-AC3` | core/contracts/는 어떤 구획도 import하지 않는 순수 인터페이스·타입·단위 정의만 포함한다 | 자동 | test_import_boundaries.py, test_assumption_provider.py 2건, test_registry.py |
|  |  | 1 | `NFR-208-M1` | import-linter 계약(layers + independence)을 CI에서 강제. 위반 0건 | 자동 | test_17_10_dod10.py, test_import_boundaries.py 2건 |
| `NFR-301` | Should-have | 1 | `NFR-301-M1` | 사용자 5명 태스크 수행 테스트 | 수동 | test_manual_stubs.py (스텁) + MC-2 (미수행) |
| `NFR-302` | Should-have | 1 | `NFR-302-M1` | UI 검수 체크리스트 | 자동 | test_dashboard.py 2건 |
| `NFR-303` | Should-have | 1 | `NFR-303-M1` | 오류 메시지 리뷰 체크리스트 | 자동 | test_analysis_period.py 5건, test_price_basis.py 6건, test_dv9_dv10.py 2건, test_e2e_analysis_period_wiring.py 6건, test_e2e_exclusion_wiring.py, test_structured_errors.py 22건, test_proforma.py 4건, test_chart_contract.py, test_dv_catalogue_matches_spec.py 3건, test_dv_rule_enforcement.py 10건, test_leap_year_policy.py 3건, test_validation_contract.py 5건, test_ess.py 6건, test_ev_v2g.py 8건, test_heatpump.py 15건, test_load.py 17건, test_pv_validation.py 9건, test_thermal_load.py 15건, test_incentive.py 3건, test_tsstore.py 4건, test_charts_feasible_region.py, test_charts_wp28a.py 3건, test_dashboard.py |
| `NFR-304` | Nice-to-have | 1 | `NFR-304-AC1` | 주요 화면은 1366×768 이상에서 가로 스크롤 없이 표시되어야 한다 | 수동 | test_manual_stubs.py (스텁) + MC-5 (미수행) |
| `NFR-401` | Must-have | 1 | `NFR-401-AC1` | 비밀번호는 Argon2id 또는 bcrypt(cost≥12)로 해싱 저장 | 자동 | test_hashing.py 2건 |
| `NFR-402` | Must-have | 1 | `NFR-402-AC1` | 모든 통신은 TLS 1.2 이상 | 자동 | test_phase1_measurements.py |
| `NFR-403` | Must-have | 1 | `NFR-403-AC1` | 사용자는 타인 시나리오에 접근 불가 (유효 공유 토큰 제외) | 자동 | test_authorization.py 2건 |
| `NFR-404` | Must-have | 1 | `NFR-404-AC1` | 업로드 CSV는 크기(10MB)·행수(100,000)·MIME 검증 | 자동 | test_timeseries.py |
| `NFR-405` | Should-have | 1 | `NFR-405-AC1` | 의존성 취약점 CI 자동 스캔 (pip-audit / Dependabot) | 자동 | test_phase1_measurements.py |
| `NFR-501` | Should-have | 1 | `NFR-501-AC1` | 동시 사용자 20명, 등록 200명, 시나리오 5,000건 규모에서 정상 동작 | 자동 | test_phase1_measurements.py |
| `NFR-502` | Must-have | 1 | `NFR-502-AC1` | SQLite 파일 일 1회 이상 자동 백업, 분기 1회 복원 리허설 | 자동 | test_backup_restore.py 6건 |
| `NFR-503` | Must-have | 1 | `NFR-503-AC1` | 단일 컨테이너로 로컬 실행 가능 (docker run 1회) | 자동 | test_phase1_measurements.py |
| `NFR-504` | Must-have | 1 | `NFR-504-AC1` | 무료 티어 제약(메모리 512MB, 콜드스타트, 디스크 비영속) 하에서 데이터 유실 없이 운영 | 자동 | test_freetier.py 4건 |
| `UI-1` | Should-have | 1 | `UI-1-AC1` | 마법사 방식으로 초심자를 안내하되, 숙련자용 전체 파라미터 단일 화면(고급 모드) 병행 | 자동 | test_parameters.py 6건, test_dashboard.py 6건 |
| `UI-2` | Must-have | 1 | `UI-2-AC1` | 모든 수치 입력 옆에 단위 상시 표시 (kW, kWh, 원/kWh, %, 년) | 자동 | test_parameters.py 2건, test_dashboard.py |
| `UI-3` | Must-have | 1 | `UI-3-AC1` | 신뢰도 가정 항목은 노란 배지로 표시하고, 결과에서 해당 값의 영향도와 함께 명시 (FR-1002) (v0.5: 배지 라벨 미확인 → 가정. DB enum도 동… | 자동 | test_dashboard.py |
| `UI-4` | Must-have | 1 | `UI-4-AC1` | 결과 지표 카드는 항상 무지원 기준선 대비 증분을 함께 표시 | 자동 | test_dashboard.py |
| `UI-5` | Should-have | 1 | `UI-5-AC1` | 한국어 우선. 영어 병기는 지표명(NPV, IRR, LCOE)에 한정 | 수동 | test_manual_stubs.py (스텁) + MC-7 (미수행) |
| `UI-6` | Should-have | 2 | `UI-6-AC1` | 접근성: WCAG 2.1 AA 목표 (색상 단독 정보전달 금지, 명암비 4.5:1 이상, 키보드 내비게이션) | 자동 | test_dashboard.py |
| `UI-7` | Must-have | 1 | `UI-7-AC1` | 결과 화면은 영향도 순위를 최상단에 둔다. 입력값 나열은 부록으로 보낸다 (FR-1002) | 자동 | test_dashboard.py |
| `SC-1` | Must-have | 1 | `SC-1` | 이메일 + 비밀번호, 세션 쿠키(HttpOnly, Secure, SameSite=Lax) | 자동 | test_auth.py 2건 |
| `SC-2` | Must-have | 1 | `SC-2` | 시나리오 접근은 소유자 또는 유효 공유 토큰 보유자로 제한 | 자동 | test_authorization.py 2건 |
| `SC-3` | Must-have | 1 | `SC-3` | 수집을 이메일·이름으로 최소화. 실증 참여 가구의 개별 식별정보 미저장 (부하 데이터는 익명 집계본만) | 자동 | test_sc3.py 2건, test_ci_gates.py, test_privacy_procedure.py |
| `SC-4` | Must-have | 1 | `SC-4` | 로그인, 시나리오·전제 생성·수정·삭제, 관리자 카탈로그 변경 기록 | 자동 | test_audit.py |
| `SC-5` | Must-have | 1 | `SC-5` | DB 경로·시크릿 키는 환경변수. 저장소 커밋 금지, gitleaks CI 스캔 | 자동 | test_auth.py 5건, test_ci_gates.py 2건, test_phase1_measurements.py 2건, test_precommit_installed.py 4건 |
| `SC-6` | Must-have | 1 | `SC-6` | DER-VET 코드를 사용하지 않으므로 BSD 3-Clause 전파 의무 없음. 설계 참조 사실은 README에 명기 (부록 C) | 자동 | test_license.py |
| `SC-7` | Must-have | 1 | `SC-7` | 요금표·단가 등 외부 데이터의 출처·이용조건을 메타데이터로 보관 | 자동 | test_catalog.py, test_items.py 2건, test_assumption_provider.py |
| `SC-8` | Must-have | 1 | `SC-8` | 전제 데이터는 민감도 등급을 보유한다 — 공개 가능(공시·고시 등 공개 출처) / 비공개(업계 견적, 미공표 제도 검토, 제공자가 비공개를 조건으로 준 값). … | 자동 | test_ci_gates.py |

## ID 규약

ID는 **spec이 직접 들고 있습니다.** 이 표를 만드는 스크립트는 읽기만 하며
번호를 부여하지 않습니다.

```markdown
  - Acceptance Criteria:
    - **AC1** 속성: `name`, `tag`, ...
    - **AC2** 메서드: `capex()`, ...
  - Measurement:
    - **M1** 동일 시나리오 10회 실행 결과 해시 일치
```

그래서 수용기준을 **중간에 삽입해도 이후 ID가 밀리지 않습니다.** v0.7까지는
선언 순서에서 ID를 뽑았기 때문에 삽입 한 번에 이후 번호가 전부 밀렸고, 작업
목록 인용과 테스트 마커가 조용히 다른 조항을 가리켰습니다(실제 7건).

**번호는 연속일 필요가 없습니다.** AC3을 삭제하면 AC1·AC2·AC4로 남는 것이
정상입니다. 빈 번호를 메우려고 재배열하면 그 사고를 그대로 재현합니다.

표 수용기준은 **행 단위로 전개되어 있습니다** (2.15 ①, spec v0.9). 각 행은
`FR-102-AC1.PV` 처럼 `<기존AC>.<키>` 형식이며, 키는 **저자가 1회 부여하고
동결하는 리터럴**입니다 — 행 위치도 슬러그화도 대소문자 변환도 파생이므로
쓰지 않습니다(`PV`를 `pv`로 낮추는 것 자체가 파생입니다). 점은 한 단계까지입니다.

**수용기준을 만드는 것은 `- **AC…**` 불릿 줄뿐입니다.** `|` 로 시작하는 표
행은 읽지 않으므로, 표에 ID 열을 넣어도 조항이 생기지 않습니다. 새 표를
수용기준으로 쓰려면 선언 불릿 목록으로 적으십시오.

행마다 Phase가 다르면 줄 끝에 `[Phase N]` 을 답니다. 표기가 없는 조항은
요구사항의 Phase를 물려받습니다.

## 수동 검증

자동화할 수 없는 수용기준은 `docs/manual-checks.yaml` 에 등재하고 여기서
`수동`으로 표시합니다. 수행 이력(일자·수행자·표본·결과)이 없으면 `미수행`이며,
Phase DoD 판정 시 미수행 건수를 확인합니다.

수동 등재는 예외이지 도피처가 아닙니다. 등재 기준과 제외 사유는
`manual-checks.yaml` 머리말에 있습니다.

각 항목은 `blocking_dod` 칸을 갖습니다 — 미수행이면 Phase 완료를 막아야
하는가를 사람이 미리 표시한 값입니다. `true` 이고 아직 수행되지 않았으면
위 요약과 "차단 미수행" 절에 **판정불가**로 표기됩니다. "충족"과 혼동되지
않도록 별도 상태로 셉니다 — CI는 이 상태로 실패하지 않습니다.
