# docs/ — CLAUDE.md

## 구성

- 정본 사본 — `domain-rules.md` · `evidence-standard.md`
- 판정 기록 — `decisions-*.md`(라운드별 기록, 과거형)
- 전제 대장 — `assumptions.yaml`(경제성 입력값 + 근거 부기)
- 자동 생성물 — `traceability.md`
- 사람용 안내 — `README.md`(정본 사본 규약 세부 절차)

## 금지사항

- `domain-rules.md`·`evidence-standard.md`: 볼트 정본의 바이트동일 사본, 편집 금지(`scripts/check_source_rules.py` 해시 대조)
- `traceability.md`: 손편집 금지(NFR-107)
- `assumptions.yaml`: 부기 7종(파일 머리말 참조) 증감 금지, 값 임의 기재 금지
- `decisions-*.md`: 과거 판정 기록 수정 금지

## 허용사항 · 절차

- `domain-rules.md`·`evidence-standard.md` 개정 — 볼트 정본 수정 후 재복사
- `traceability.md` 갱신 — `scripts/gen_traceability.py` 실행 후 결과 커밋
- `assumptions.yaml` 근거 상태 표시 — `track`(assume/default0/blocked)으로 정직하게 표시
- `decisions-*.md` 신규 판정 — 새 파일로 추가

## 참고

심의보고서(경제성 결과, 주 내용)와 검증보고서(대장 값 출처·신뢰도, 붙임)는 별개 문서. `assumptions.yaml` 수정 시 그 부기는 검증보고서(붙임)에만 반영, 심의보고서(주 내용) 미반영.
