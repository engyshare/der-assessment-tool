# 점검 — R1b / WP-14 (점검자: Sisyphus)

대상: WP-14 검증자산 — `fixtures/golden/**` · `fixtures/oracle/**` · `tests/golden/**` · `docs/privacy-procedure.md` (담당 agy)
점검 일자: 2026-08-09
`lint-imports`는 지시대로 제외.

> **R1 정정 (WP-2)**: 오케스트레이터 정정에 따라 `docs/assumptions.yaml` 의 `tariff.power_fund_rate` 추가는 WP-2 결함이 아님 → R1 보고서 B-1 차단 1건은 취소. 공유 작업트리에서 git status 만으로 작성자를 특정할 수 없는 모호함이 W-1 이 막으려는 것이 맞음. 이 점검에서도 같은 한계가 있다 (① 참조).

---

## 판정

| # | 항목 | 판정 | 근거 |
|---|---|---|---|
| ① | 구획 경계 | 지적 | `M` 파일 4종 (`.github/workflows/*` 2건 · `README.md` · `pyproject.toml` · `docs/traceability.md`) 은 COMMON §1상 WP-15/오케스트레이터 소유. diff 내용(partition-assignment 잡·pip-audit·SC-6 라이선스 갱신)이 작업 2.11·2.14·NFR-405 계열로 보이며 **WP-14 산물이 아님**. R1 정정 사유와 마찬가지로 공유 트리에서 작성자 특정이 불가하나, WP-14 소유 파일(`fixtures/**`·`tests/golden/**`·`docs/privacy-procedure.md`) 은 전부 untracked(??) 신규 생성이고 수정이 없으므로 **WP-14 자체의 소유 경계 침범은 없음**. check_partition_assignment.py rc=0 |
| ② | 게이트 전건 | **차단** | **mypy rc=1** — `tests/golden/test_privacy_procedure.py:7: Function is missing a return type annotation [no-untyped-def]`. 함수에 `-> None` 이 없음. pytest 1/1 통과, ruff 통과, check_file_size·check_hardcoded_params·check_disclosure 전부 통과. lint-imports 제외 |
| ③ | 수용기준 매핑 | **지적** | SC-3 매핑 추가 — `test_privacy_procedure.py:6` 의 `@pytest.mark.req("SC-3")` 가 traceability.md 에 반영 (SC-3 14/16). ✓ 그러나 **16.4 수용기준 `NFR-104-M1` 이 미매핑** — `fixtures/golden/*.yaml` 은 yaml 파일이라 `@pytest.mark.req` 마커를 붙일 수 없고, 16.4 산출물을 검증하는 테스트가 `tests/golden/` 에 없음 (SC-3 테스트만 존재). check_task_mapping.py rc=0 이지만 이것은 작업 목록 인용 검사지 AC 매핑 검사가 아님 |
| ④ | 자기충족 검증 | 통과 | **16.4 골든 3종 전부 `null` (TBD)** — 자원 구현을 돌려 나온 값이 아님. **16.5 `control_cases_6.yaml` 은 해석해 기대값** — 손계산으로 NPV 298,843 재현 확인 (`-1,000,000 + 300,000 × ((1-1.05^-5)/0.05) = 298,843` ✓). 각 기대값 옆에 오라클 순위 명시 (NPV·융자: 순위 1 원 단위 일치, IRR·MIRR·회수기간: 순위 2 0.01%) — INSPECT ④ 요구사항 충족 |
| ⑤ | 음성 능력 | 판정 불가 | WP-14가 새로 만든 검사·판정 로직은 `test_privacy_procedure.py` 하나. 이 테스트는 「문서 존재 + 키워드 포함」만 검사 → 문서 삭제·키워드 제거 위반은 잡으나, **「반입 전 차단」이 실제로 이뤄지는지는 검사 못 함** (절차의 존재만 검증, 이행은 미검증). 위반을 심어 잡는지 (문서 삭제 케이스) — 잡음. 그러나 §13.0.1 ④ 「검사가 통과했다 ↔ 무언가를 검사했다」 구분이 여기서 다시 발생: 이 테스트는 절차 **문서의 존재**를 검사할 뿐 절차 **자체의 준수**를 검사하지 않음. negtest 5종 전부 통과 (WP-14가 깨뜨린 것 없음) |
| ⑥ | 반복 함정 | 지적 | `test_privacy_procedure.py:20-25` 가 검사하는 어휘("식별 정보 제거 규칙"·"익명 집계 단위"·"데이터 반입 시점 검증 절차"·"반입 전 차단"·"저장소 외부 격리 환경"·"원천 차단")를 **리터럴로 들고 있음**. `docs/privacy-procedure.md` 도 같은 어휘. 검사와 피검사가 어휘를 공유 → §13.0.1 ④ · §8 반복 함정. 위험: 누군가 문서에서 어휘를 빼면 잡지만(양호), 테스트와 문서 양쪽에서 같이 바꾸면 조용히 통과(조용한 실패). 해법은 `ast` 등으로 식별자를 뽑아 서술과 선언을 가르는 것이나, 테스트가 너무 단순해 그 수준까지 갈 필요는 아님 — 다만 어휘 공유 사실은 기록 |
| ⑦ | 계약 준수 | 통과 | WP-14 산출물이 문서·yaml·테스트 1개. 계약 추상 의존 해당 없음, 형제 구획 import 해당 없음. `fixtures/golden/*.yaml` 의 `subsidy_rate: 0.0/0.20/0.80` 은 시나리오 입력값(전제 대장이 아님), `control_cases_6.yaml` 의 `discount_rate: 0.05` 등도 테스트 입력값 — 전제값 리터럴 박힘 없음 ✓. 비율 전부 소수 ✓. 금액 int 원 단위 ✓ (NFR-103 반올림 경로와 무관한 해석해 기대값). 전역 가변 상태 없음 ✓ |

---

## 차단 사유

### B-1. mypy 실패 — `test_privacy_procedure.py` return annotation 누락 (②)

```
> python -m mypy --cache-dir .mypy_cache_inspect tests/golden
tests\golden\test_privacy_procedure.py:7: error: Function is missing a return type annotation  [no-untyped-def]
tests\golden\test_privacy_procedure.py:7: note: Use "-> None" if function does not return a value
Found 1 error in 1 file (checked 2 source files)
rc=1
```

`tests/golden/test_privacy_procedure.py:7` 의 `def test_privacy_procedure_document_exists_and_valid():` 에 `-> None` 이 없음. R1/WP-2 의 대상 코드는 mypy 통과였으므로, 이것은 WP-14 의 mypy 게이트가 실패하는 유일한 원인. pytest·ruff 는 통과라 발견되지 않았을 것 — mypy 를 돌려야만 잡히는 결함.

**파일을 고치지 않음 — 보고만 함.**

---

## 지적 사항

### I-1. 16.4 골든 기준값 유보 — 정당하나 DoD 형식 요건 미충족 (사용자 점검 1·2)

`fixtures/golden/scenario_{unsubsidized,subsidy_20,subsidy_80}.yaml` 세 파일 모두:

```yaml
expected_values:
  payback_period_years: null   # TBD
  npv_won: null                # TBD
```

각 파일 헤더가 투명하게 사유를 명시:
> 현재 엔진 및 CBA 모듈이 Wave 2에 해당하여 실제 종단 산출 경로가 없음.
> 본 파일은 확보 가능한 외부 공표 실적 기준값만 정의하며 나머지는 미완(TBD) 상태임.

**사용자 점검 1 (유보 정당성)**: **정당함**. 16.4 오라클은 §13.0.2 순위 3(외부 공표 실적) 인데, 16.1b 가 Q-4(선행 실증) 발송 완료 상태이고 16.2(Q-5 엑셀) 는 「유예(가정 불가)」 — 외부 자료가 아직 없음. 엔진도 없고 외부 자료도 없으니 유보가 유일한 정당한 선택.

**사용자 점검 2 (자기충족 최악 결함 회피)**: **회피했음. ✓** 3개 파일 전부 `null`. 자원 구현을 돌려 나온 값을 기대값으로 적지 않았음. 이 라운드 최악의 결함(자기충족 골든)을 유보로 피한 것은 올바른 판단. 작업 목록 16.4 노트가 「기준값이 `docs/assumptions.yaml`의 가정에 묶여 있으므로, 이 3종이 통과한다는 것은 *계산이 어제와 같다* 는 뜻이지 *계산이 맞다* 는 뜻이 아니다」라고 명시한 것과 일관됨.

**DoD 형식 요건**: 16.4 DoD 「시나리오당 1파일, 기준값 출처를 파일에 명기」중 「출처 명기」는 충족(`oracle_source`, `oracle_rank`, `assumptions_version` 전부 명시). 그러나 「기준값」 자체는 null. DoD 를 형식대로 읽으면 미충족이나, 노트가 종단 산출 경로 부재를 투명하게 명시하므로 절차적 정당성은 있음.

### I-2. `NFR-104-M1` (16.4 수용기준) 미매핑 (③)

16.4 의 수용기준이 `NFR-104-M1` 인데, 이것이 `@pytest.mark.req` 마커로 어디에도 붙지 않음. `fixtures/golden/*.yaml` 은 yaml 파일이라 마커를 붙일 수 없고, 16.4 산물을 검증하는 테스트가 `tests/golden/` 에 없음 (`test_privacy_procedure.py` 는 SC-3 만 검증). 결과적으로 `gen_traceability.py` 출력에서 `NFR-104` 검색 결과 없음 → **16.4 인용 자체가 매핑으로 이어지지 않음**.

이것은 16.4 가 유보 상태라는 것과 일관 (기준값이 없으니 검증할 것도 없음) 되지만, NFR-104-M1 이 Must-have 라면 미매핑 상태로 남는 것은 게이트에 걸림. 매핑만 놓고 보면, 「골든 시나리오 파일이 존재하는가」를 검사하는 최소한의 테스트가 있어야 NFR-104-M1 마커를 붙일 수 있음.

### I-3. `test_privacy_procedure.py` 가 절차 문서의 존재·어휘만 검사 (⑤·⑥)

```python
assert "식별 정보 제거 규칙" in content
assert "익명 집계 단위" in content
assert "데이터 반입 시점 검증 절차" in content
assert "반입 전 차단" in content or "저장소 외부 격리 환경" in content or "원천 차단" in content
```

SC-3 의 DoD (작업 목록 16.3): 「익명화되지 않은 원본이 저장소·DB 어디에도 들어오지 않음을 **절차로 보장**」. 이 테스트는 절차 **문서의 존재와 어휘 포함**만 검사 → 절차 **자체의 준수**는 검사 못 함. 물론 절차 준수는 기계 검사 영역이 아님 (수동 절차). 다만 이 테스트가 SC-3 매핑을 전부 담당하므로, SC-3 가 「절차 문서가 있다」로 좁혀져 있음.

또한 테스트가 검사하는 어휘를 리터럴로 들고 있어 §8 반복 함정 관련 — 어휘가 문서와 테스트 양쪽에 같이 있으면, 어휘를 같이 바꿀 때 위반이 조용히 통과할 수 있음. 다만 테스트가 매우 단순하므로 `ast` 기반 분리까지 갈 필요는 아니나, 어휘 공유 사실은 기록.

### I-4. 16.3 「반입 전 차단」 명시 — 충족 (사용자 점검 3)

`docs/privacy-procedure.md`:
- :3 「반입 후 삭제는 허용되지 않는다」 — 명시적 거부 ✓
- :5 절 제목 「식별 정보 제거 규칙 (**반입 전 차단**)」 ✓
- :6 「반입 **전** 저장소 외부 격리 환경에서 다음 식별 정보를 완전히 제거한다」 ✓
- :16 「데이터를 저장소의 `fixtures/` 또는 DB에 커밋/복사하기 **직전에** 다음 절차를 거친다」 ✓

**사용자 점검 3 (반입 전 차단 vs 반입 후 제거)**: **반입 전 차단으로 쓰였음. ✓** 작업 목록 16.3 DoD 「반입 후 제거가 아니라 반입 전 차단이어야 한다」충족.

다만 한계: :17 「수동 검사(사람의 훑기)」에 크게 의존. 기계 검사(`check_disclosure.py` + gitleaks)는 파일 경로·패턴·전화번호·주민번호 형태를 잡지만(negtest_disclosure 9종 음성 통과), 실제 가구 식별 메타데이터(계량기 번호 등)를 맥락적으로 잡지는 못함. 절차 문서의 성질상 수동 검사 의존은 감수하나, 「사람이 한 번 훑으면 안전하다」는 보장은 없음 — 절차 자체가 최소 기계 보조와 함께 수동에 의존.

### I-5. 16.5 해석해 기대값 검증 (④·사용자 점검 2 확장)

`fixtures/oracle/control_cases_6.yaml` 의 NPV 기대값 손계산 검증:

```
NPV = -1,000,000 + 300,000 × ((1 - 1.05^-5) / 0.05)
1.05^-5 = 0.783526
(1 - 0.783526) / 0.05 = 4.32948
300,000 × 4.32948 = 1,298,843
-1,000,000 + 1,298,843 = 298,843 ✓ (yaml: npv_won: 298843)
```

B/C ratio: PV(benefits) 1,298,843 / PV(costs) 1,000,000 = 1.298843 ✓ (yaml 일치)
융자 상환: 500,000 × (0.03 × 1.03^5) / (1.03^5 - 1) = 109,177 ✓ (yaml 일치)

IRR 15.238%·MIRR 10.620%·할인 회수기간 3.7416년 — 모두 산식이 주석으로 명시되어 손계산/재현 가능. **자기충족 아님** (순위 1 해석해). 16.5 는 Q-5 엑셀이 없어 해석해로 갈아탔다고 헤더에 명시 — 작업 목록 16.5 노트 「엑셀 확보 전 — 닫힌 형태 해석해를 기대값으로 하는 케이스 표」충족.

다만 **현재 `control_cases_6.yaml` 을 소비하는 테스트가 `tests/golden/` 에 없음** — 해석해 표만 있고 그것을 대조에 쓰는 테스트(10.3 [T] NPV·IRR·MIRR·B/C·할인회수기간)는 아직 Wave 2 라 미구현. 이것은 16.5 의 성질(케이스 **표 작성**이지 테스트 실행이 아님)과 일관되나, 매핑 관점에서 `FR-703-AC1.npv` 등이 아직 미매핑 상태로 남음.

---

## 실행한 명령과 출력

```
> git status --porcelain
 M .github/workflows/source-rules.yml     ← WP-15 추정 (작업 2.11 partition-assignment)
 M .github/workflows/tests.yml            ← WP-15 추정 (NFR-405 pip-audit)
 M README.md                              ← WP-15 추정 (작업 2.14 SC-6 라이선스)
 M docs/traceability.md                   ← CI 자동생성 (gen_traceability.py)
 M pyproject.toml                         ← WP-15 (COMMON §1 명시, +pip-audit>=2.7.3)
?? docs/privacy-procedure.md              ← WP-14 신규 (16.3)
?? fixtures/golden/scenario_subsidy_20.yaml  ← WP-14 신규 (16.4)
?? fixtures/golden/scenario_subsidy_80.yaml  ← WP-14 신규 (16.4)
?? fixtures/golden/scenario_unsubsidized.yaml ← WP-14 신규 (16.4)
?? fixtures/oracle/                       ← WP-14 신규 (16.5 control_cases_6.yaml)
?? tests/golden/                          ← WP-14 신규 (test_privacy_procedure.py)
(나머지 ?? 는 WP-2·WP-3·WP-13·WP-15 산물)

> $env:COVERAGE_FILE=".coverage.wp14-inspect"; python -m pytest tests/golden/ -p no:cacheprovider --no-cov -q
.                                                                        [100%]
rc=True (1 통과)

> python -m ruff check tests/golden
All checks passed!
rc=True

> python -m mypy --cache-dir .mypy_cache_inspect tests/golden          ← B-1 차단
tests\golden\test_privacy_procedure.py:7: error: Function is missing a return type annotation  [no-untyped-def]
Found 1 error in 1 file (checked 2 source files)
rc=False (rc=1)

> python scripts/check_file_size.py --code-strict
(WP-14 파일 전부 매우 작음 — 통과)

> python scripts/check_hardcoded_params.py
통과 — 차단 0건 / 경고 1건 (core/contracts/units.py — WP-14 외)
rc=True

> python scripts/check_disclosure.py
통과 — 추적 대상에 비공개 유입 없음 (privacy-procedure.md·fixtures/golden 전부 공개 내용)
rc=True

> python scripts/check_partition_assignment.py
[경고] 사전려된 spec 결함 (무시함) - 미배정: FR-611
[경고] 사전려된 spec 결함 (무시함) - 중복 배정: FR-101 -> WP-0, WP-1
[경고] 사전려된 spec 결함 (무시함) - 중복 배정: FR-1103 -> WP-14, WP-15
Phase 1 Must-have FR 중 미배정 0건 · 중복 배정 0건 확인 완료
rc=0

> python scripts/gen_traceability.py
(SC-3 매핑에 test_privacy_procedure.py 추가 반영됨 — 14/16)
(NFR-104-M1 검색 결과 없음 — 미매핑)
rc=1 (미매핑 잔존 — 정상)

> python scripts/check_task_mapping.py
rc=0

> git diff HEAD -- docs/traceability.md | Select-String "SC-3"
-| `SC-3` | ... | 자동 | test_ci_gates.py |
+| `SC-3` | ... | 자동 | test_ci_gates.py, test_privacy_procedure.py |
```

---

INSPECT WP-14 | 차단 1건 | 지적 5건 | 판정불가 1건
