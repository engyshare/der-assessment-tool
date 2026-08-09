# 점검 — R2 / WP-7 (점검자: Codex)

## 판정

| # | 항목 | 판정 | 근거 |
|---|---|---|---|
| ① | 구획 경계 | 통과 | 사용자 제공 대상 파일(`core/cba/{baseline,metrics,perspective,proforma,salvage}.py`, `tests/cba/{conftest,test_baseline,test_indicators,test_metrics,test_proforma,test_transfer}.py`)은 모두 WP-7 소유 경로 안이다. 목록 밖 변경(`core/cba/__init__.py`, `docs/traceability.md`, 타 WP 경로 등)은 판정 대상 아님. |
| ② | 게이트 전건 | **차단** | `pytest tests/cba` rc=0, `ruff core/cba tests/cba` rc=0, `mypy core/cba` rc=0. 단, 점검 대상 테스트까지 포함한 `mypy core/cba tests/cba`는 rc=1, 18건 오류. 나머지 공통 게이트는 rc=0. |
| ③ | 수용기준 매핑 | **차단** | WP-7 담당 미매핑 5건 잔존: `FR-701-AC2`, `FR-704-AC1`, `FR-704-AC2`, `FR-704-AC3`, `FR-704-AC4`. `core/cba/perspective.py`의 산문 인용은 선언으로 세어지지 않았다. |
| ④ | 자기충족 검증 | 통과(지적 있음) | `tests/cba/test_metrics.py`는 구현 결과를 기대값으로 재사용하지 않는다. NPV/B/C는 산식으로 재계산하고 원 단위 `==` 판정, IRR/MIRR/할인 회수기간만 `pytest.approx(rel=1e-4)`를 쓴다. 다만 `fixtures/oracle/control_cases_6.yaml`의 `expected` 값은 대부분 직접 판정에 쓰지 않고, MIRR 기대값 불일치는 xfail로 남아 있다. |
| ⑤ | 음성 능력 | 판정 불가(부분 통과) | WP-7 자체 음성 케이스는 존재한다: `lcoe_mixed()`는 값 대신 `None`, 보조금 누출/기준선 누락/음수 국비는 예외. 저장소 상주 음성 테스트 중 `negtest_assumptions.py`만 rc=0이고, 나머지 4개는 임시 디렉터리 권한 오류로 판정 전에 실패했다. |
| ⑥ | 반복 함정 | 통과 | WP-7은 새 문자열 기반 검사기를 만들지 않았다. 실제로 `core/cba/perspective.py`의 독스트링 `FR-704-AC1~AC4`는 추적표에서 마커로 세어지지 않았으므로 “서술이 선언으로 세어지는” 함정은 재현되지 않았다. |
| ⑦ | 계약 준수 | **차단** | `core/cba/proforma.py:52`가 원 단위 반올림을 `to_won()`이 아니라 Python `round()`로 직접 수행한다. `core/contracts/units.py`의 계약은 `ROUND_HALF_UP`을 쓰는 `to_won()` 단일 경로다. |

## 차단 사유

1. `FR-701-AC2`, `FR-704-AC1`~`AC4`가 실제 테스트 마커로 매핑되지 않았다.
   - `docs/traceability.md:214`, `docs/traceability.md:234`~`237`이 모두 **미매핑**이다.
   - `tests/cba/test_proforma.py:28`은 `FR-701-AC1`만 인용한다. 20년 행을 만들지만 “열: 건설연도~분석 종료연도” 자체를 `FR-701-AC2`로 검증하지 않는다.
   - `tests/cba/test_transfer.py`는 `FR-704-AC5`~`AC7`만 인용한다.
   - `core/cba/perspective.py:3`, `core/cba/perspective.py:29`의 `FR-704-AC1~AC4`는 산문/독스트링일 뿐 테스트 선언이 아니다.

2. 점검 대상 테스트까지 포함한 mypy 게이트가 실패한다.
   - `tests/cba/test_metrics.py:22` PyYAML stub 없음.
   - `tests/cba/test_metrics.py`의 `dict` 타입 인자 누락, `Any` 반환, `object` fixture가 `CashFlowRow` 목록에 들어가는 오류가 다수 있다.
   - `tests/cba/test_indicators.py:58`은 반환값이 없는 `lcoe_mixed()`를 변수에 대입해 `func-returns-value` 오류가 난다.

3. 원 단위 반올림 계약을 우회한다.
   - `core/cba/proforma.py:52`의 `Decimal(round(current))`는 Python 은행가 반올림 경로다.
   - 정본 계약은 `to_won()`의 `ROUND_HALF_UP` 경로 하나만 허용한다. `.5` 경계에서 엑셀 대조와 달라질 수 있다.

## 지적 사항

- `fixtures/oracle/control_cases_6.yaml`의 `expected` 값은 직접 판정 오라클로 거의 쓰이지 않는다. 현재 테스트는 fixture의 입력값을 읽어 독립 산식으로 기대값을 다시 만든다. 자기충족은 아니지만, 파일명과 주석이 말하는 “control case expected”와 실제 검증 방식이 다르다.
- `tests/cba/test_metrics.py:208`의 MIRR expected 일치 검사는 xfail이다. fixture의 `mirr_pct: 10.620`이 산식값과 어긋난다고 명시되어 있으므로, 해당 기대값은 현재 게이트를 세우지 못한다.
- `tests/cba/test_metrics.py:42`의 skip 메시지는 `_ORACLE` 절대경로를 그대로 출력할 수 있다. 현재 fixture가 있어 출력되지는 않았지만, 누락 시 공개 로그에 로컬 경로가 나올 수 있다.
- `tests/cba/test_proforma.py:1`은 `NFR-103-M1`을 설명하지만 해당 마커는 없다. 전역 추적표에서는 다른 테스트가 `NFR-103-M1`을 매핑하므로 미매핑은 아니지만, WP-7 프로포마 합계 항등식과의 직접 추적은 비어 있다.

## 추가 확인

- `lcoe-mixed`는 음성 케이스로 구현되어 있고 우회로는 보이지 않는다. `core/cba/metrics.py:258`의 시그니처가 인자를 받지 않으므로 “분모를 명시하면 산출” 경로는 없다.
- 출력 가리기 규칙: 이 보고서에는 저장소 절대경로, 사용자 홈 경로, 시스템 임시 경로 원문을 붙이지 않았다.

## 실행한 명령과 출력

```text
$ python -m pytest tests\cba -p no:cacheprovider --no-cov -q
......................x.............                                     [100%]
rc=0

$ python -m pytest tests\cba -p no:cacheprovider --no-cov -q -ra
......................x.............                                     [100%]
XFAIL tests/cba/test_metrics.py::test_yaml_expected_mirr_is_consistent_with_formula
  yaml 의 mirr_pct=10.620% 가 닫힌 형태 산식값과 어긋난다
rc=0

$ python -m ruff check core\cba tests\cba
All checks passed!
rc=0

$ python -m mypy --cache-dir .mypy_cache_inspect core\cba
Success: no issues found in 6 source files
rc=0

$ python -m mypy --cache-dir .mypy_cache_inspect core\cba tests\cba
Found 18 errors in 2 files (checked 13 source files)
대표 오류:
  tests/cba/test_metrics.py:22 import-untyped: Library stubs not installed for "yaml"
  tests/cba/test_metrics.py:40 type-arg: Missing type arguments for generic type "dict"
  tests/cba/test_metrics.py:46 no-any-return: Returning Any
  tests/cba/test_metrics.py:83 list-item: object is not CashFlowRow
  tests/cba/test_indicators.py:58 func-returns-value: lcoe_mixed does not return a value
rc=1

$ python scripts\check_file_size.py --code-strict
총 줄 수 초과 7건 — 그중 코드 줄 수도 초과한 것 0건
전건 설명 밀도, 코드 스프롤 없음
rc=0

$ python scripts\check_hardcoded_params.py
NFR-202 전제값 복제 — 차단 0건 / 경고 1건
NFR-205 전역 가변 상태 — 0건
rc=0

$ python scripts\check_disclosure.py
통과 — 추적 대상에 비공개 유입 없음
rc=0

$ git status --porcelain
대상 WP-7 파일:
  ?? core/cba/baseline.py
  ?? core/cba/metrics.py
  ?? core/cba/perspective.py
  ?? core/cba/proforma.py
  ?? core/cba/salvage.py
  ?? tests/cba/conftest.py
  ?? tests/cba/test_baseline.py
  ?? tests/cba/test_indicators.py
  ?? tests/cba/test_metrics.py
  ?? tests/cba/test_proforma.py
  ?? tests/cba/test_transfer.py
목록 밖 변경은 다른 구획 — 판정 대상 아님.
rc=0

$ git diff --stat HEAD
대상 WP-7의 신규 파일은 --stat에 나타나지 않음(미추적). 출력에는 다른 구획 변경과
docs/traceability.md 변경이 섞여 있어 WP-7 판정 대상에서 제외.
rc=0

$ python scripts\gen_traceability.py --check
요구사항 105건 / 수용기준 307건 / 자동 223건 / 수동 8건 / 수동 스텁 0건 / Phase 미지정 9건
Must-have 미매핑 51건
WP-7 관련: FR-701-AC2, FR-704-AC1, FR-704-AC2, FR-704-AC3, FR-704-AC4 미매핑
rc=1

$ python scripts\check_task_mapping.py
범위 초과 인용 없음
실재하지 않는 인용 없음
미인용 Must-have 수용기준 없음
통과
rc=0

$ git diff --stat docs\traceability.md
docs/traceability.md | 223 변경
rc=0

$ python scripts\negtest_assumptions.py
음성 테스트 19종 — 감지 19 / 미감지 0
rc=0

$ python scripts\negtest_traceability.py
PermissionError: <시스템 임시 경로 또는 저장소 임시 경로> 하위 디렉터리 생성 권한 거부
rc=1

$ python scripts\negtest_file_size.py
PermissionError: <시스템 임시 경로 또는 저장소 임시 경로> 하위 디렉터리 생성 권한 거부
rc=1

$ python scripts\negtest_hardcoded_params.py
PermissionError: <시스템 임시 경로 또는 저장소 임시 경로> 하위 디렉터리 생성 권한 거부
rc=1

$ python scripts\negtest_disclosure.py
PermissionError: <시스템 임시 경로 또는 저장소 임시 경로> 파일 생성 권한 거부
rc=1
```

## 점검 환경 메모

- `python scripts/gen_traceability.py`는 출력 파일을 쓰므로 보고서 외 파일 생성 금지 조건에 맞춰 `--check`로 실행했다.
- 상주 음성 테스트 권한 실패를 우회하려고 만든 상대경로 `.tmp_inspect_neg`는 권한 복구와 삭제가 모두 거부되었다. 소스 판정 대상은 아니지만 점검 실행 잔여물이다.
