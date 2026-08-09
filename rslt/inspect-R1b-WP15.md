# 점검 — R1b / WP-15 (점검자: Codex)

대상은 사용자 지정 목록만 보았다. 목록 밖 변경(`core/model/**`, `core/constraint/**`, `tests/model/**`, `tests/valuestream/**`, 기존 `.tmp_*`)은 판정하지 않았다. 단, WP-15 게이트가 그 밖 변경 때문에 현재 빨갛게 되는 사실은 명령 출력으로 별도 기록한다.

## 판정

| # | 항목 | 판정 | 근거 |
|---|---|---|---|
| ① | 구획 경계 | 통과 | 최종 `git status` 기준 WP-15 대상 파일은 dirty가 아니며, 목록 밖 변경은 판정 제외. `scripts/negtest_partition_assignment.py`는 사용자 목록 밖이지만 `source-rules.yml`이 호출하므로 2.11 음성 검증 대상으로만 읽었다. |
| ② | 게이트 전제조건 | **차단** | `pytest --collect-only`는 676개 수집·오류 0. 그러나 대상 mypy가 12건 실패하고, 대상 pytest는 로컬 TEMP 권한 오류 5건 + WP-15 밖 NFR-205 위반으로 종료 코드 1. |
| ③ | 수용기준 매핑 | 통과(대상 조항) | SC-6은 `tests/ci/test_license.py` 마커와 `docs/traceability.md` 행에 매핑됨. `gen_traceability.py --check`는 WP-15 밖 `tests/model/*` 유령 마커 때문에 rc=1. |
| ④ | 자기충족 검증 | **차단** | 구획 FR 배정 검사가 실제 결함 3건을 `known_*` 예외로 무시하고 rc=0 및 “0건 확인”을 출력한다. |
| ⑤ | 음성 입력 | 판정 불가 / 지적 | `negtest_partition_assignment.py`는 미배정·중복을 심도록 되어 있으나 이 환경에서 TEMP 쓰기 권한 오류로 실행 실패. 또한 checker return code를 확인하지 않고 stdout 문자열만 본다. |
| ⑥ | 반복 함정·서술 선언 | 지적 | 배정 파서는 `|`로 시작하고 `WP-`를 포함하는 표 행의 4번째 칸만 읽어 일반 산문 FR 토큰은 세지 않는다. 다만 16.3 안의 다른 설명 표가 `WP-`와 `FR-`을 함께 담으면 배정으로 오인될 수 있고, 이를 막는 음성 테스트는 없다. |
| ⑦ | 계약 준수 | **차단** | `Dockerfile`은 `.[persistence]`만 설치하면서 `CMD ["python", "-m", "pytest"]`로 전체 테스트를 실행한다. 전체 테스트에는 dev extra의 `import-linter`가 필요하므로 NFR-503 단일 컨테이너 실행을 만족하지 못한다. |

## 차단 사유

1. `Dockerfile`이 NFR-503 단일 컨테이너 실행을 보장하지 못한다.
   - `Dockerfile:14`는 `pip install --no-cache-dir -e ".[persistence]"`만 수행한다.
   - `Dockerfile:19`는 `python -m pytest`를 실행한다.
   - 전체 테스트에는 `tests/ci/test_import_boundaries.py`의 import-linter 실행이 포함되지만 `import-linter`는 `pyproject.toml:22~31`의 `dev` extra에만 있다. 따라서 Docker 기본 명령은 설치된 환경과 맞지 않는다.

2. WP-15 대상 mypy가 실패한다.
   - `scripts/check_partition_assignment.py`: `main()` 반환 타입, `assigned_to` 타입, untyped call.
   - `scripts/negtest_partition_assignment.py`: `main()` 반환 타입, untyped call.
   - `tests/ci/test_seed_fallback.py`: 테스트 함수 타입 누락 및 `seeds.get(...).value`의 `None` 가능성.
   - `tests/ci/test_license.py`: 테스트 함수 반환 타입 누락.
   - `tests/ci/test_ci_gates.py`, `tests/ci/test_import_boundaries.py`: `yaml` stubs 누락 등.
   - 현재 CI는 `python -m mypy`만 실행하고 `pyproject.toml:89`의 `files = ["core"]` 때문에 이 오류들을 막지 않는다.

3. 구획 FR 배정 검사가 현재 spec 결함을 녹색으로 덮는다.
   - `scripts/check_partition_assignment.py:67~86`에 `known_missing = {"FR-611"}`, `known_dups = {"FR-101", "FR-1103"}`가 하드코딩되어 있다.
   - 실제 실행 출력은 세 경고를 낸 뒤 `Phase 1 Must-have FR 중 미배정 0건 · 중복 배정 0건 확인 완료`, rc=0이다.
   - 2.11의 목적이 “미배정·중복 검출”이라면 known 결함을 CI 통과로 만들면 안 된다.

## 지적 사항

- `tests.yml`의 `pip install -e ".[dev,persistence]"`는 현재 인프라 테스트를 실제로 수집·실행하게 한다. `pytest --collect-only`에서 `tests/infra/*` 43개가 수집되었고 SQLAlchemy import 수집 오류는 없었다. 다만 install extra가 하드코딩되어 있어 다음 구획이 새 optional group을 추가하면 같은 구멍이 재발할 수 있다.
- `CONTRIBUTING.md:8`은 여전히 `pip install -e ".[dev]"`를 안내한다. 사용자가 이 문서대로 공개 클론을 실행하면 persistence 의존성이 빠진다.
- 담당자의 “660건 수집 오류 0” 보고는 현재 작업트리 기준 숫자가 틀렸다. 실제 최신 collect-only는 676개 수집, rc=0, 수집 오류 0이다.
- SC-6 자체는 충족한다. README에 DER-VET 문서 참조와 DER-VET 코드 미사용, BSD 3-Clause 전파 의무 없음이 명기되어 있고, LICENSE는 MIT이며, traceability에 `SC-6 -> test_license.py`가 반영되어 있다.
- 이 점검 중 `scripts/negtest_partition_assignment.py`를 로컬 TEMP 우회로 재실행하다가 `rslt/tmppmdnt793/` 임시 디렉터리가 남았다. 삭제 명령은 정책 차단으로 수행하지 못했다. WP-15 산출물 판정에는 포함하지 않는다.

## 실행한 명령과 출력

```text
git status --porcelain
→ WP-15 대상 파일 dirty 없음. 목록 밖 core/model, core/constraint, tests/model, tests/valuestream 변경만 표시.
→ warning: could not open directory 'rslt/tmppmdnt793/': Permission denied
```

```text
git diff --stat HEAD
→ WP-15 대상 파일 없음. 목록 밖 .tmp_wp13_pytest, core/model, core/constraint 변경만 표시.
```

```text
python -m pytest --collect-only -q -p no:cacheprovider --no-cov
→ tests/infra/test_audit.py: 6
→ tests/infra/test_backup_restore.py: 6
→ tests/infra/test_freetier.py: 8
→ tests/infra/test_migration.py: 7
→ tests/infra/test_scenario_ownership.py: 6
→ tests/infra/test_tsstore.py: 10
→ 총 676개 수집, PYTEST_COLLECT_RECHECK_RC=0, ERROR 섹션 없음
```

```text
python -m pytest tests/ci tests/golden/test_privacy_procedure.py -p no:cacheprovider --no-cov -q
→ .............EE......EE.F...E........
→ 1 failed, 5 errors
→ 실패: core/model/__init__.py:10 __all__, core/model/settlement.py:5 SUPPORTED_STRUCTURES 전역 가변 상태
→ 오류: tmp_path fixture가 <사용자 경로> 접근 거부
→ PYTEST_TARGET_RECHECK_RC=1
```

```text
python -m ruff check scripts/check_partition_assignment.py scripts/negtest_partition_assignment.py tests/ci tests/golden/test_privacy_procedure.py
→ All checks passed!
→ RUFF_RECHECK_RC=0
```

```text
python -m mypy --cache-dir .mypy_cache_inspect scripts/check_partition_assignment.py scripts/negtest_partition_assignment.py tests/ci tests/golden/test_privacy_procedure.py
→ Found 12 errors in 6 files (checked 9 source files)
→ MYPY_RECHECK_RC=1
```

```text
python scripts/check_file_size.py --code-strict
→ 총 줄 수 초과 7건, 그중 코드 줄 수도 초과한 것 0건
→ FILE_SIZE_RC=0
```

```text
python scripts/check_hardcoded_params.py
→ NFR-202 차단 0건 / 경고 1건
→ NFR-205 전역 가변 상태 2건: core/model/__init__.py, core/model/settlement.py
→ HARDCODED_RECHECK_RC=1
```

```text
python scripts/check_disclosure.py
→ 통과 — 추적 대상에 비공개 유입 없음
→ DISCLOSURE_RC=0
```

```text
python scripts/gen_traceability.py --check
→ 요구사항 105건 / 수용기준 307건 / 자동 131건 / 수동 8건
→ 수동 대장 대상 없음 3건: tests/model/* 유령 마커
→ Must-have 미매핑 144건
→ TRACEABILITY_CHECK_RC=1
```

```text
python scripts/check_task_mapping.py
→ 형식 이탈 인용 의심 2건, 범위 초과 없음, 실재하지 않는 인용 없음, 미인용 Must-have 없음
→ 상위 작업 간 중복 인용 27건
→ TASK_MAPPING_RC=0
```

```text
python scripts/check_partition_assignment.py
→ [경고] 알려진 spec 결함 (무시됨) - 미배정: FR-611
→ [경고] 알려진 spec 결함 (무시됨) - 중복 배정: FR-101 -> WP-0, WP-1
→ [경고] 알려진 spec 결함 (무시됨) - 중복 배정: FR-1103 -> WP-14, WP-15
→ Phase 1 Must-have FR 중 미배정 0건 · 중복 배정 0건 확인 완료
→ PARTITION_RC=0
```

```text
python scripts/negtest_partition_assignment.py
→ PermissionError: missing.md 쓰기 실패
→ NEG_PARTITION_RC=1
```

```text
python scripts/negtest_assumptions.py
→ 음성 테스트 19종 — 감지 19 / 미감지 0
→ NEG_ASSUMPTIONS_RC=0
```

```text
python scripts/negtest_traceability.py
python scripts/negtest_file_size.py
python scripts/negtest_hardcoded_params.py
python scripts/negtest_disclosure.py
→ 모두 TEMP 하위 디렉터리/파일 생성 단계에서 PermissionError
→ 각 rc=1
```

INSPECT WP-15 | 차단 3건 | 지적 5건 | 판정불가 1건
