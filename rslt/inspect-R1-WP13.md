# 점검 — R1 / WP-13 (점검자: Codex)

## 판정

| # | 항목 | 판정 | 근거 |
|---|---|---|---|
| ① | 구획 경계 | 판정 불가 | 전역 작업트리에 `.github/**`, `README.md`, `pyproject.toml`, `docs/traceability.md`, `core/assumption/**`, `core/regulation/**`, `tests/assumption/**`, `tests/regulation/**` 등 다수 구획 변경이 섞여 있음. WP-13 소유 변경(`infra/**`, `tests/infra/**`)은 보이나, 혼재 상태라 외부 변경의 WP-13 귀속 여부를 `git status`만으로 판정할 수 없음. |
| ② | 게이트 전건 | 판정 불가 | `ruff`, `mypy`, `check_file_size`, `check_hardcoded_params`, `check_disclosure`는 rc=0. `pytest tests/infra`는 기본 임시 디렉터리 권한 오류로 rc=1. 작업공간 basetemp 재시도도 접근 권한 오류로 rc=1. |
| ③ | 수용기준 매핑 | 부분 통과 / 판정 불가 | `gen_traceability.py`는 rc=1(브리프상 미매핑 잔존 시 정상) 및 Must-have 미매핑 156건. `check_task_mapping.py` rc=0으로 실재하지 않는 인용 없음. 다만 `docs/traceability.md`가 이미 dirty라 미매핑 n→m 변화량은 판정 불가. |
| ④ | 자기충족 검증 | **차단** | `infra/migrations/versions/0001_initial.py:59`가 현재 `Base.metadata.create_all()`을 실행하고, `tests/infra/test_migration.py:102`가 같은 현재 `Base.metadata`와 비교함. 모델을 바꿔도 초기 마이그레이션이 같이 바뀌므로 drift 검사가 자기 자신을 검증한다. |
| ⑤ | 음성 능력 | 판정 불가 | WP-13 내부에는 `test_scenario_ownership.py`, `test_migration.py`, `test_tsstore.py` 등에 위반 심기 테스트가 있음. 그러나 저장소 상주 음성 테스트 5종 중 4종이 임시 디렉터리 권한 오류로 실행 자체 실패. |
| ⑥ | 반복 함정 | **차단** | `tests/infra/test_freetier.py:61`~`66`은 모듈 독스트링에 `"Litestream"`, `"Turso"`, `"판정 근거"`가 들어 있는지만 검사한다. 서술 문자열이 정책 결정 선언으로 세어지는 구조라 반대 내용의 문장도 통과 가능하다. |
| ⑦ | 계약 준수 | **차단** | NFR-205 반려 2건은 실제 수정됨(`infra/database.py:37` `MappingProxyType`, `infra/orm/__init__.py:48` tuple `__all__`). 그러나 금액 컬럼이 `Mapped[float | None]`로 선언됨(`infra/orm/run.py:83`, `infra/orm/catalog.py:89`, `:90`, `:128`~`:130`)과 동시에 `money()`는 Decimal 컬럼을 반환한다. 또한 `infra/orm/catalog.py:69`는 요율을 “% 단위로 저장”한다고 적어 내부 비율 소수(0~1) 규약과 충돌한다. |

## 차단 사유

1. **초기 마이그레이션 drift 검사가 자기충족이다.**
   `0001_initial.py`가 고정 DDL이 아니라 현재 ORM 메타데이터를 가져와 `create_all()`을 수행한다. 따라서 모델과 마이그레이션이 독립 산출물이 아니며, `compare_metadata(..., Base.metadata)`가 통과해도 “마이그레이션을 안 고친 모델 변경”을 잡을 수 없다.

2. **운영용 Litestream push 경로가 실질적으로 검증되지 않았고 구현도 push가 아니다.**
   `infra/freetier.py:153`~`160`의 `LitestreamReplica.push()`는 `snapshots -o <db> <url>`을 호출한다. 이름과 주석상 `replicate_now()`의 push 경로지만, 실제 데이터 업로드/복제 명령이 아니며 테스트는 `FilesystemReplica`만으로 NFR-504를 검증한다.

3. **서술 문자열이 선언으로 세어진다.**
   `test_tu2_decision_documented_in_freetier_module()`은 독스트링에 단어가 있는지만 본다. 이 저장소가 반복해서 경계한 “서술이 선언으로 세어져 초록불” 유형이다.

4. **금액/비율 계약이 타입 선언과 문서에서 어긋난다.**
   `money()`는 `Numeric[Decimal]`인데 금액 필드가 `Mapped[float | None]`로 선언되어 경계 타입이 거짓말을 한다. `vat_rate`/`fund_rate`는 “% 단위”라고 쓰여 내부 비율 소수 규약과 반대다.

## 지적 사항

- 공식 pytest와 음성 테스트 일부는 현재 환경의 임시 디렉터리 권한 문제 때문에 판정 불가다. 첫 실패 경로: `<사용자 임시 경로>`.
- 재시도 중 생성된 `.tmp_inspect_pytest`는 접근 권한 오류로 제거하지 못했다. 삭제 시도는 도구 안전 정책에 의해 차단되었다.
- 전역 작업트리에 WP-13 외 변경이 많다. 특히 `pyproject.toml`의 `pip-audit` 추가, `.github/**`, `README.md` 변경은 WP-13 브리프 소유 경로가 아니다. 다만 혼재 작업트리라 귀속은 판정하지 않았다.

## 실행한 명령과 출력

```text
git status --porcelain
 M .github/workflows/source-rules.yml
 M .github/workflows/tests.yml
 M README.md
 M docs/traceability.md
 M pyproject.toml
?? .github/ISSUE_TEMPLATE/
?? .github/pull_request_template.md
?? CONTRIBUTING.md
?? Dockerfile
?? LICENSE
?? core/assumption/catalog.py
?? core/assumption/item.py
?? core/assumption/provider.py
?? core/assumption/timeseries.py
?? core/regulation/compliance.py
?? core/regulation/profile.py
?? core/regulation/tariff.py
?? docs/privacy-procedure.md
?? fixtures/golden/scenario_subsidy_20.yaml
?? fixtures/golden/scenario_subsidy_80.yaml
?? fixtures/golden/scenario_unsubsidized.yaml
?? fixtures/oracle/
?? infra/audit.py
?? infra/backup.py
?? infra/database.py
?? infra/freetier.py
?? infra/migrations/
?? infra/orm/
?? infra/tsstore.py
?? rslt/inspect-R1-WP2.md
?? rslt/inspect-R1-WP3.md
?? rslt/inspect-R1b-WP14.md
?? scripts/check_partition_assignment.py
?? scripts/negtest_partition_assignment.py
?? tests/assumption/test_catalog.py
?? tests/assumption/test_items.py
?? tests/assumption/test_loader.py
?? tests/assumption/test_set.py
?? tests/assumption/test_timeseries.py
?? tests/ci/seed_loader.py
?? tests/ci/synthetic_seeds.yaml
?? tests/ci/test_license.py
?? tests/ci/test_seed_fallback.py
?? tests/golden/
?? tests/infra/
?? tests/regulation/test_compliance.py
?? tests/regulation/test_profile.py
?? tests/regulation/test_tariff.py
```

```text
git diff --stat HEAD
 .github/workflows/source-rules.yml |  13 ++++
 .github/workflows/tests.yml        |   3 +
 README.md                          |   5 +-
 docs/traceability.md               | 134 ++++++++++++++++++-------------------
 pyproject.toml                     |   1 +
 5 files changed, 87 insertions(+), 69 deletions(-)
```

```text
$env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest tests/infra/ -p no:cacheprovider --no-cov -q; Write-Output "rc=$LASTEXITCODE"
......EE...E..EEEEE..EEEEE......EEEEEEEEEE                               [100%]
ERROR tests/infra/test_backup_restore.py::test_restore_recovers_all_data_after_db_loss
ERROR tests/infra/test_backup_restore.py::test_restore_rejects_corrupt_backup
ERROR tests/infra/test_backup_restore.py::test_take_backup_produces_byte_identical_copy
ERROR tests/infra/test_freetier.py::test_zero_data_loss_through_disk_loss_cycle
ERROR tests/infra/test_freetier.py::test_zero_data_loss_through_multiple_cold_starts
ERROR tests/infra/test_freetier.py::test_restore_on_startup_skips_when_db_already_present
ERROR tests/infra/test_freetier.py::test_restore_on_startup_skips_when_no_replica_yet
ERROR tests/infra/test_freetier.py::test_filesystem_replica_uses_atomic_rename
ERROR tests/infra/test_migration.py::test_upgrade_creates_all_tables
ERROR tests/infra/test_migration.py::test_no_drift_between_migration_and_models
ERROR tests/infra/test_migration.py::test_downgrade_to_base_drops_all_tables
ERROR tests/infra/test_migration.py::test_drift_checker_catches_added_column
ERROR tests/infra/test_migration.py::test_drift_checker_does_not_flag_in_sync_schema
ERROR tests/infra/test_tsstore.py::test_roundtrip_preserves_values
ERROR tests/infra/test_tsstore.py::test_checksum_matches_compute_checksum
ERROR tests/infra/test_tsstore.py::test_checksum_detects_byte_modification
ERROR tests/infra/test_tsstore.py::test_read_without_checksum_does_not_verify
ERROR tests/infra/test_tsstore.py::test_write_rejects_wrong_row_count
ERROR tests/infra/test_tsstore.py::test_write_rejects_unknown_kind
ERROR tests/infra/test_tsstore.py::test_write_accepts_both_supported_resolutions[8760]
ERROR tests/infra/test_tsstore.py::test_write_accepts_both_supported_resolutions[35040]
ERROR tests/infra/test_tsstore.py::test_metadata_embeds_kind_year_and_format
ERROR tests/infra/test_tsstore.py::test_checksum_is_actually_sha256_of_file_bytes
대표 오류:
PermissionError: [WinError 5] 액세스가 거부되었습니다: '<시스템 임시 경로>'
rc=1
```

```text
$env:PYTHONDONTWRITEBYTECODE='1'; $env:TMP='<시스템 임시 경로>'; $env:TEMP='<시스템 임시 경로>'; python -m pytest tests/infra/ -p no:cacheprovider --no-cov -q --basetemp .tmp_inspect_pytest; Write-Output "rc=$LASTEXITCODE"
......EE...E..EEEEE..EEEEE......EEEEEEEEEE                               [100%]rc=1
PermissionError: [WinError 5] 액세스가 거부되었습니다: '<시스템 임시 경로>'
```

```text
python -m ruff check infra tests/infra; Write-Output "rc=$LASTEXITCODE"
All checks passed!
rc=0
```

```text
python -m mypy --cache-dir .mypy_cache_inspect infra; Write-Output "rc=$LASTEXITCODE"
Success: no issues found in 16 source files
rc=0
```

```text
python scripts/check_file_size.py --code-strict; Write-Output "rc=$LASTEXITCODE"
NFR-206 파일 규모 — 상한 500줄 / 대상 70개 파일
총 줄 수 초과 7건 — 그중 코드 줄 수도 초과한 것 0건
rc=0
```

```text
python scripts/check_hardcoded_params.py; Write-Output "rc=$LASTEXITCODE"
NFR-202 · NFR-205 — 대상 52개 파일 / 대장 수치 50건
· NFR-202 전제값 복제 — 차단 0건 / 경고 1건
  · core/contracts/units.py:125  3600 ← 대장 load.household.annual.value, load.household.annual.base  [값 충돌 가능 — 사람이 판정]
· NFR-205 전역 가변 상태 — 0건
통과 — 차단 대상 없음.
rc=0
```

```text
python scripts/check_disclosure.py; Write-Output "rc=$LASTEXITCODE"
비공개 유입 검사 — 대상 103개 파일
통과 — 추적 대상에 비공개 유입 없음
rc=0
```

```text
python scripts/gen_traceability.py; Write-Output "rc=$LASTEXITCODE"
생성: docs\traceability.md
요구사항 105건 / 수용기준 307건 / 자동 116건 / 수동 8건 / 수동 스텁 0건 / Phase 미지정 9건
Must-have 미매핑 156건
  · FR-102-AC1.VPP — VPP 통합발전소 (자원 집합 + 시장참여) — 집합 자원 ID 목록, 운영수수료(%), 시장참여 유형
  · FR-102-AC1.Boiler — Boiler 보조 열원 (가스/전기) — 열효율, 연료단가, 연료종
  · FR-102-AC1.Genset — Genset 비상·상시 발전기 — 정격출력, 열소비율, 연료단가, 최소부하율
  · FR-103-AC1 — 한 시나리오 내에 PV#1(햇빛소득마을 조건), PV#2(자가용 조건)이 동시 존재
  · FR-103-AC2 — 각 인스턴스는 독립적인 IncentiveScheme 참조를 가진다 (FR-604)
  … 외 146건
rc=1
```

```text
python scripts/check_task_mapping.py; Write-Output "rc=$LASTEXITCODE"
· 형식 이탈 인용 의심 2건
· 범위 초과 인용 없음
· 실재하지 않는 인용 없음
· 미인용 Must-have 수용기준 없음
· 상위 작업 간 중복 인용 27건
통과
rc=0
```

```text
git diff --stat docs/traceability.md; Write-Output "rc=$LASTEXITCODE"
 docs/traceability.md | 134 +++++++++++++++++++++++++--------------------------
 1 file changed, 67 insertions(+), 67 deletions(-)
rc=0
```

```text
python scripts/negtest_traceability.py; Write-Output "rc=$LASTEXITCODE"
PermissionError: [WinError 5] 액세스가 거부되었습니다: '<시스템 임시 경로>'
rc=1

python scripts/negtest_assumptions.py; Write-Output "rc=$LASTEXITCODE"
음성 테스트 19종 — 감지 19 / 미감지 0
rc=0

python scripts/negtest_file_size.py; Write-Output "rc=$LASTEXITCODE"
PermissionError: [WinError 5] 액세스가 거부되었습니다: '<시스템 임시 경로>'
rc=1

python scripts/negtest_hardcoded_params.py; Write-Output "rc=$LASTEXITCODE"
PermissionError: [WinError 5] 액세스가 거부되었습니다: '<시스템 임시 경로>'
rc=1

python scripts/negtest_disclosure.py; Write-Output "rc=$LASTEXITCODE"
PermissionError: [Errno 13] Permission denied: '<시스템 임시 경로>'
rc=1
```

```text
python scripts/check_task_mapping.py --fr FR-601; Write-Output "rc=$LASTEXITCODE"
FR-601-AC1
FR-601-AC2.cost
FR-601-AC2.performance
FR-601-AC2.market_price
FR-601-AC2.finance
FR-601-AC2.escalation
FR-601-AC2.reference
FR-601-AC3
FR-601-AC4
FR-601-AC5.value_unit
FR-601-AC5.base_year
FR-601-AC5.applicable_scope
FR-601-AC5.derivation_method
FR-601-AC5.source
FR-601-AC5.verified_at
FR-601-AC5.confidence
FR-601-AC6
FR-601-AC7
FR-601-AC8
FR-601-AC9
rc=0
```
