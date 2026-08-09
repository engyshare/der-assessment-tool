# 점검 — R1 / WP-3 (점검자: Sisyphus)

> 대상: WP-3 담당(codex) 이 작성한 `core/regulation/**` · `tests/regulation/**`.
> 점검자는 소스를 한 줄도 고치지 않았다.

## 판정

| # | 항목 | 판정 | 근거 |
|---|---|---|---|
| ① | 구획 경계 | **통과** | `git status --porcelain` — WP-3 담당이 건드린 파일은 `core/regulation/{compliance,profile,tariff}.py` · `tests/regulation/test_{compliance,profile,tariff}.py` 6건 전부 소유 경로 안. `core/contracts/**`·`tests/contract/**`·`pyproject.toml`·`docs/traceability.md`(자동생성)·`rslt/**` 침범 0건 |
| ② | 게이트 전건 | **통과** | `pytest tests/regulation` rc=0 (15 passed) · `ruff` rc=0 · `mypy core/regulation` rc=0 (4 files clean) · `check_file_size --code-strict` rc=0 (코드 스프롤 0건, regulation/* 위반 목록 없음) · `check_hardcoded_params` rc=0 (NFR-205 0건, NFR-202 차단 0건) · `check_disclosure` rc=0 |
| ③ | 수용기준 매핑 | **통과** | `gen_traceability` 가 FR-501~504 미매핑 0건 보고(21 AC 전부 "자동\| test_*.py" 로 갱신, `git diff docs/traceability.md` 62줄 ±). `check_task_mapping` rc=0 (통과). `@pytest.mark.req` 인용 ID 가 전부 실재 조항 — check_task_mapping 의 «실재하지 않는 인용» 보고 없음 |
| ④ | 자기충족 검증 | **통과 (지적)** | 자기충족 기대값 없음 — 모든 금액 기대값을 손계산으로 재현했음(노트 참조). 다만 **오라클 산식 명시가 부실** — `test_tariff.py` 의 "Oracle: closed-form hand calculation" 이라는 한 줄만 있고, "200 kWh × 100원 = 20,000원, subtotal 17,900원 × 0.037 = 662원(to_won 사사오입)" 같은 **단계별 산식이 독스트링에 없다**. 다음 점검자가 같은 검산을 반복하게 됨(§13.0.2 순위 1 의 «손계산으로 재현 가능한 산식이 적혀 있는가») |
| ⑤ | 음성 능력 | **판정 불가** | 담당 구획이 «위반을 심어 checker 가 잡는가» 검증을 **작성하지 않았다**. `compliance.py::_ratio` 가 0~1 범위 검사를 하지만, 경계 밖(예: 1.5·-0.1) 입력 케이스가 테스트에 없다 — «0건 통과»가 «규칙이 안 걸렸다»인지 «위반이 없다»인지 구별 안 됨(§13.0.1 ④). 저장소 상주 negtest 5종은 전부 rc=0 — 담당 구획이 깨뜨린 음성 테스트 없음 |
| ⑥ | 반복 함정 | **해당 없음** | 담당 구획이 문자열 스캔 자기검사 코드를 새로 쓰지 않았다 — `tariff.py`·`compliance.py`·`profile.py` 전부 계산·데이터 클래스 코드. «서술이 선언으로 세어지는» 구조 자체가 없음 |
| ⑦ | 계약 준수 | **지적** | `core.contracts.{assumptions,units,regulation}` 만 import — 형제 구획 직접 import 0건(NFR-208-AC2 ✓). 비율 전부 소수(vat 0.10·fund 0.037·discount 0.20) ✓. 금액 `Money`/`to_won` 단일 경로 ✓. 전역 가변 0건(NFR-205 ✓). **그러나 NFR-202 사각지대 위반** — 아래 차단 사유는 아니나 남길 것 참조 |

## 차단 사유 (있으면)

없음. ① 구획 경계가 유일한 차단 기준이며 침범 0건이다.

## 지적 사항 (차단은 아니나 남길 것)

### ⑦-1. NFR-202 사각지대 — `tariff.power_fund_rate = 0.037` 이 FR-501-AC7 정책 수치를 테스트에 박음

`tests/regulation/test_tariff.py:95` 의 `_engine()` stub:

```python
"tariff.power_fund_rate": 0.037,   # ← FR-501-AC7 의 「전력산업기반기금 3.7%」
```

이 값은 **대장(`docs/assumptions.yaml`)에 없다** (`yaml.safe_load` 로 전 항목 순회 확인).
그래서:

- `check_hardcoded_params.py` 가 `tests/` 를 `TARGETS=("core","app","infra")` 에서 제외하여 **잡지 못한다**.
- 값이 0.037 (< 1,000) 이라 대장에 있어도 `JUDGE_FLOOR=1_000` 미만이라 판정 안 함.
- 사용자가 브리프에서 명시적으로 지적한 사각지대 대역.

FR-501-AC7 의 문면: *"부가가치세(10%)와 전력산업기반기금(3.7%)을 별도 항목으로 계산한다 … 두 항목의 요율은 **요금표 데이터에 포함되어** 개정 시 …"*. AC7 자체가 «데이터에 포함»을 요구하는데, 그 AC7 을 검증하는 테스트가 값을 소스에 박았다. 테스트가 자기가 검증하는 조항을 위반하는 형태.

**권고**: `docs/assumptions.yaml` 에 `tariff.power_fund_rate`(0.037) 항목을 추가하고, 테스트 stub 이 대장에서 읽게 하거나, 최소한 «대장에 없는 테스트 전용 가짜 값»임을 주석으로 명시(예: `0.05` 로 바꿔 정책값과 다르게). 현재 값은 «진짜 정책값이 우연히 박힌 것»인지 «테스트용 가짜»인지 코드만 보고 구별 불가.

### ⑦-2. 대장값-동일 복제 — `fee.direct_trade_support: 5`, `tax.vat_rate: 0.10`

같은 stub 의:

```python
"fee.direct_trade_support": 5,      # 대장값 5 원/kWh 과 정확히 동일
"tax.vat_rate": 0.10,               # 대장값 0.1 과 동일
```

대장(`docs/assumptions.yaml`) 확인 결과 두 값이 그대로 있다. NFR-202 의 «대장은 정본» 원칙에 어긋난다 — 대장값이 바뀌면 테스트 stub 은 안 바뀌어, production 은 새 값을 쓰는데 테스트는 옛 값으로 통과한다. 이것이 «정책 수치 하드코딩»의 정의다.

`fee.direct_trade_support`(5원)는 사용자가 브리프에서 명시적으로 언급한 사각지대 대역이기도 하다.

### ④-1. 오라클 산식 명시 부실

`tests/regulation/test_tariff.py` 의 5개 테스트 전부 «Oracle: hand calculation» 한 줄만. 특히:

- `test_bill_breakdown_contains_vat_power_fund_and_traceable_lines`: vat 1,790원·fund 662원 이 **subtotal × rate 의 사사오입 결과**라는 것이 독스트링에 안 적혀있다. subtotal 17,900 × 0.037 = 662.3 → 662(to_won) 라는 단계가 생략되어, 다음 점검자가 662 의 출처를 다시 계산한다.
- `test_tou_uses_season_weekday_hour_matrix_and_special_discount`: 10 kWh × 200원 = 2,000원, 10 × 100 = 1,000원, 1,000 × 0.20 = 200원 할인 이 과정이 안 적혀있다.

자기충족은 아니다(기대값 전부 손계산으로 재현됨). 그러나 §13.0.2 순위 1 의 «손계산으로 재현 가능한 산식이 적혀 있는가» 기준을 엄밀히 적용하면 부족.

### ④-2. `pytest.approx` 가 금액이 아닌 비율·kWh 에만 쓰임 — 양호

`test_compliance.py::test_supply_duty_separates_allowed_and_excess_external_energy` 가 `fulfillment_ratio`·`required_procurement_kwh` 등에 `pytest.approx(0.65)` 를 쓴다. 이것은 float 비율·kWh 에 대한 것이고 **금액에는 `Money(30_000)` 으로 정확히 일치**를 요구한다. NFR-103 «금액은 원 단위 완전 일치» 준수. 이 점은 양호.

### ⑤-1. `compliance._ratio` 의 0~1 범위 위반 케이스 부재

`core/regulation/compliance.py:35-39`:

```python
def _ratio(profile, key, *, when):
    value = _profile_float(profile, key, when=when)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"regulation ratio {key!r} must be between 0 and 1")
    return value
```

이 검사가 작동하는지(예: `required_ratio=1.5` 입력 시 ValueError)를 본 테스트가 없다. «0건 통과» 가 «규칙이 안 걸렸다»인지 «위반이 없다»인지 구별이 안 됨(§13.0.1 ④). `assess_supply_duty` 가 음수 kwh·operation_year<1 에 대해 ValueError 를 던지는 검사도 마찬가지로 누락.

### ④-3. 누진 요금 구간 경계 — 양호

`test_residential_progressive_boundaries_are_inclusive` 의 parametrize:

```
(199.0, 900, 19_900, -4_000)   # ← 구간 1 경계 바로 아래
(200.0, 900, 20_000, -4_000)   # ← 구간 1·2 경계 정확히
(201.0, 1_600, 20_200, 0)      # ← 구간 2 경계 바로 위
(400.0, 1_600, 60_000, 0)      # ← 구간 2·3 경계 정확히
(401.0, 7_300, 60_300, 0)      # ← 구간 3 첫 단위
```

사용자가 브리프에서 요구한 «경계 바로 위/아래/정확히 같은 값» 3종이 2개 구간 경계(200, 400)에 모두 있음. 또한 essential_discount 경계(200 kWh)도 같이 검증 — discount 가 200 이하일 때만 적용, 201 부턴 0. 이것은 이 구획에서 가장 잘 된 부분.

### ④-4. TOU·직접거래 청구에 부가세·기반기금 누락 — 의심

`test_tou_uses_season_weekday_hour_matrix_and_special_discount` 의 total 2,800원, `test_scenario_combines...` 의 common meter total 2,000원 모두 **vat·fund 가 안 들어있다**. 이유는 `_tou_table()`·`_direct_table()` 이 `tax_and_fund=None` 으로 생성해서. 실제 청구서는 부가세가 붙는데, 테스트는 안 붙인다.

이것이 «설계적 결함»인지 «TOU/직접거래는 부가세 제외가 맞다»인지 spec 이 명시하는지 확인이 필요. FR-501-AC7 은 «부가가치세와 전력산업기반기금을 별도 항목으로 계산하고 청구액에 합산한다» 라고만 — 누진·TOU·직접거래 차이를 명시 안 함. 지적 사항.

### 수용기준 21건 vs 테스트 15건 — 충분성

- 21 AC 전부 매핑(③ 항목). 15 테스트(parametrize 5건 포함) 로 커버. 평균 1.4 AC/테스트.
- FR-502-AC1·AC2·AC4 가 한 테스트(`test_supply_duty_separates...`)에 뭉쳐있음 — 같은 supply_duty 계산의 다른 측면이라 정당하나, AC2 가 깨져도 AC1·AC4 가 같이 fail 하여 어느 AC 가 문제인지 좁히기 어렵다.
- FR-504-AC2·AC3·AC4·AC7 이 한 테스트에 뭉쳐있음 — 마찬가지.
- **충분성 판정**: 15건이 21 AC 를 기계적 커버는 하지만, 한 테스트가 다루는 AC 가 많아 결함 isolation 이 약하다. AC7·AC8 처럼 명세 분해 + 세금 항목을 한 테스트가 다루는 것은 자연스럽지만, FR-502 의 «충족률 계산(AC1)»·«이중구조 요금(AC2)»·«경고(AC4)» 를 분리하면 좁히기 쉽다. **지적 사항** — 결함 isolation 강화 권고.

## 실행한 명령과 출력

```
> git status --porcelain
?? core/regulation/compliance.py
?? core/regulation/profile.py
?? core/regulation/tariff.py
?? tests/regulation/test_compliance.py
?? tests/regulation/test_profile.py
?? tests/regulation/test_tariff.py
(나머지 17건은 WP-2/WP-13/오케스트레이터 소유)

> python -m pytest tests/regulation/ -p no:cacheprovider --no-cov -q
...............                                                          [100%]
15 passed
rc=0

> python -m ruff check core/regulation tests/regulation
All checks passed!
rc=0

> python -m mypy --cache-dir .mypy_cache_inspect core/regulation
Success: no issues found in 4 source files
rc=0

> python scripts/check_file_size.py --code-strict
…총 줄 수 초과 7건 — 그중 코드 줄 수도 초과한 것 **0건**…
(regulation/* 파일은 위반 목록에 없음; tariff.py 424줄)
rc=0

> python scripts/check_hardcoded_params.py
· NFR-202 전제값 복제 — 차단 0건 / 경고 1건
  · core/contracts/units.py:125  3600 ← 대장 load.household.annual.value … [값 충돌 가능]
  판정하지 않은 대장 수치 18건 — |값| < 1,000
    …fee.direct_trade_support, tariff.hv_single_contract.avg, tax.vat_rate…
· NFR-205 전역 가변 상태 — 0건
통과
rc=0
```

(check_hardcoded_params 의 «판정하지 않은 대장 수치 18건» 안에 사용자가 지적한
`fee.direct_trade_support`(5)·`tariff.hv_single_contract.avg`(150)·`tax.vat_rate`(0.1)
이 보인다 — 이 대역이 lint 사각지대임이 도구 자체에 적혀 있음)

```
> python scripts/check_disclosure.py
…비공개 입력 없음… rc=0

> python scripts/gen_traceability.py
생성: docs\traceability.md
요구사항 105건 / 수용기준 307건 / 자동 112건 / 수동 8건 / 수동 스텁 0건 / Phase 미지정 9건
Must-have 미매핑 160건
(FR-50* 항목은 미매핑 목록에 0건 = 21 AC 전부 매핑)
rc=1 (미매핑 잔존은 정상)

> python scripts/check_task_mapping.py
…통과…  rc=0

> git diff --stat docs/traceability.md
docs/traceability.md | 124 +++++++++++++++++++++++++--------------------------
1 file changed, 62 insertions(+), 62 deletions(-)
(FR-501~504 21행이 «미매핑» → «자동 | test_*.py» 로 전환)

> python scripts/negtest_traceability.py    rc=0   (양성·음성 8/8)
> python scripts/negtest_assumptions.py     rc=0   (감지 19/19)
> python scripts/negtest_file_size.py       rc=0   (기준 준수)
> python scripts/negtest_hardcoded_params.py rc=0  (양성 7+음성 4+경계 5 = 16/16)
> python scripts/negtest_disclosure.py      rc=0   (양성 9+음성 6+경계 2 = 17/17)

# 대장값 확인 (NFR-202 사각지대 검증)
> python -c "…yaml.safe_load(docs/assumptions.yaml)…"
k= tariff.hv_single_contract.avg v= 150 u= 원/kWh (기본요금 안분 포함 실효단가)
k= fee.direct_trade_support v= 5 u= 원/kWh
k= tax.vat_rate v= 0.1 u= 소수 (0~1). 0.10 = 10%
# tariff.power_fund_rate 는 대장에 없음 — ⑦-1 지적의 근거
```

## 자기충족 검증 — 손계산 재현 노트 (④ 근거)

사용자가 브리프에서 «요금 계산 기대값이 구현을 돌려 나온 값을 붙여넣은 것이
아닌지» 를 집중 확인하라고 한 부분. 모든 금액 기대값을 손으로 재현했다.

### 누진 요금 (`test_residential_progressive_boundaries_are_inclusive`)

단가 stub: block1=100원, block2=200원, block3=300원. basic: 900/1600/7300.

| kWh | basic 단가 | energy 계산 | expected energy |
|---|---|---|---|
| 199 | block1 → 900 | 199×100 = 19,900 | 19,900 ✓ |
| 200 | block1 → 900 | 200×100 = 20,000 | 20,000 ✓ |
| 201 | block2 → 1,600 | 200×100 + 1×200 = 20,200 | 20,200 ✓ |
| 400 | block2 → 1,600 | 200×100 + 200×200 = 60,000 | 60,000 ✓ |
| 401 | block3 → 7,300 | 200×100 + 200×200 + 1×300 = 60,300 | 60,300 ✓ |

essential_discount: 200 kWh 이하일 때만 -4,000원(고정). 199/200 → -4,000, 201+ → 0 ✓

기대값 전부 손계산과 일치. 자기충족 아님.

### 청구 명세 (`test_bill_breakdown_contains_vat_power_fund_and_traceable_lines`) 200 kWh

```
basic              = 900
energy             = 200 × 100 = 20,000
climate            = 200 × 10 = 2,000
fuel               = 200 × (-5) = -1,000
essential_discount = -4,000 (고정)
─────────────────────────────────────
subtotal           = 900 + 20,000 + 2,000 - 1,000 - 4,000 = 17,900
vat                = to_won(17,900 × 0.10) = 1,790
power_fund         = to_won(17,900 × 0.037) = to_won(662.3) = 662 (사사오입)
total              = 17,900 + 1,790 + 662 = 20,352 ✓
```

기대값 1,790 / 662 / 20,352 전부 일치. 자기충족 아님.

### TOU (`test_tou_uses_season_weekday_hour_matrix_and_special_discount`)

```
energy.summer_peak     = 10 kWh × 200원 = 2,000
energy.spring_weekend  = 10 kWh × 100원 = 1,000
discount.spring_weekend_discount = 1,000 × 0.20 = 200 (할인)
total = 2,000 + 1,000 - 200 = 2,800 ✓
```

### 시나리오 (`test_scenario_combines_independent_meter_points...`)

```
household (200 kWh residential, full tax):
  subtotal = 17,900 → vat 1,790 + fund 662 → total 20,352
common (TOU 10 kWh summer_peak, tax_and_fund=None):
  total = 2,000
trade (50 kWh direct, energy 80원, support 5원, tax_and_fund=None):
  energy = 50 × 80 = 4,000
  support_fee = 50 × 5 = 250
  total = 4,250
─────────────────────────────────────
총 total = 20,352 + 2,000 + 4,250 = 26,602 ✓
```

### supply_duty (`test_supply_duty_separates_allowed_and_excess_external_energy`)

```
required         = 1,000 × 0.70 = 700
external         = max(1,000 - 650, 0) = 350
allowed_external = 1,000 × (1 - 0.70) = 300
excess_external  = max(350 - 300, 0) = 50
shortfall        = max(700 - 650, 0) = 50
fulfillment      = 650 / 1,000 = 0.65
allowed_charge   = min(350, 300) × 100원 = 30,000
excess_charge    = 50 × 300원 = 15,000
warning          = excess > 0 → True ✓
```

전부 기대값과 일치. 자기충족 아님.
```

INSPECT WP-3 | 차단 0건 | 지적 4건 | 판정불가 1건
