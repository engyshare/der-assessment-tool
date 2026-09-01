"""심의보고서 **붙임** 렌더러 — 양식 `docs/report-form-심의보고서.md` 3절.

## 왜 본문과 갈랐는가

`NFR-206` 코드 스프롤 검사가 `narrative.py` 를 522줄로 잡았다(상한 500). 쪼갤
자리를 **본문/붙임 경계**로 잡은 이유는 그것이 양식이 이미 그은 선이기 때문이다 —
임의로 쪼개면 파일 경계와 문서 구조가 어긋나 다음 사람이 어느 절이 어느 파일에
있는지 매번 찾아야 한다.

⚠ **순서의 소유자는 여전히 `narrative.py` 하나다.** 여기서는 붙임을 만들기만
한다.

⚠ **해설을 싣지 않는다** (양식 0절 · 2026-08-15). 표와 「항목 — 값」 나열만
낸다. 「이렇게 읽어야 한다」는 프로그램이 참임을 보증할 수 없는 진술이므로
산출물에 두지 않는다.
"""
from __future__ import annotations

from core.report._format import NO_VALUE, _date, _num, _unit_head, _won
from core.report.case_report import AssumptionRow, CaseReport

#: 산출 방법 표기 — 「단독 기여」를 문장 대신 이 라벨이 말한다 (`FR-1002-AC2`).
SOLO_SWEEP = "1변수 스윕"
#: 인자를 끝에서 끝까지 흔들어도 결론 축이 0원 움직인 경우의 표기.
#:
#: ⚠ **「영향 없음」이 아니다.** 기계는 「진짜 무영향」과 「미배선」을 가를 수
#: 없으므로 판정하지 않고 **관측한 것을 그대로** 적는다.
#:
#: ## ★★ 문면을 R43-G 가 바꿨다 — **「0원」이 거꾸로 읽혔다**
#:
#: 종전 표기는 `파이프라인 미반영 (변동폭 0원)` 이었고, 붙임 2 판단용 표는
#: 그 인자의 `결론 변동폭` 칸에 **`0원`** 을 실었다. 지방정부 담당자가 그
#: 표를 읽고 *「영향이 없다」* 로 받아 적었다(문의사항 2026-08-29 나-3):
#: 같은 열의 다른 값(6,248,231원 등)은 **재어 본 크기**인데 이 0 만
#: **재지 않았다는 표시**여서, 한 열에 서면 둘이 구별되지 않는다.
#:
#: 그래서 ① 「0원」을 이 라벨로 **대체**하고(아래 `influence_section`),
#: ② 심의 자료의 말이 아닌 「파이프라인」을 문면에서 뺐다. 상수 이름은
#: 코드의 것이므로 그대로 둔다.
UNREAD_BY_PIPELINE = "미반영 — 측정 안 됨"
#: 위 라벨이 붙은 칸 아래 다는 **정의 한 줄** (양식 0절 「규약은 나열한다」).
#:
#: ⚠ **두 자리가 이 한 줄을 함께 쓴다** — 본문 5.1 「전환까지 남는 거리」 표와
#: 붙임 2 판단용 표. 각자 적으면 한쪽만 낡는다.
UNREAD_NOTE = (
    f"- 「{UNREAD_BY_PIPELINE}」 — 범위를 끝에서 끝까지 흔들어도 결론 축이 "
    "0원 움직인 인자. 그 0 은 **이 값이 이 평가의 계산에 아직 들어가지 "
    "않았다는 표시**이며, 영향의 유무는 이 평가가 말하지 않는다 "
    "(자리와 해소 조건은 붙임 8)"
)

#: 전제 대장 키의 **접두어 → 주제** (검토 「1차 의견」 5 · 2026-08-15).
#:
#: 의견 원문은 *「전제를 주제별로 묶어 달라 — 설비단가/요금/제도/분석조건」*
#: 이었다. 종전 붙임 1 은 **신뢰도별**로만 묶여 있어 *「설비단가를 어디서
#: 보는가」* 에 답하지 못했다. 둘 다 필요하므로 **주제로 묶고 신뢰도를 열로**
#: 옮겼다.
#:
#: ⚠ **대장 키의 접두어가 곧 주제축이다** — 대장이 이미 그렇게 묶여 있으므로
#: 여기서 새 분류를 만들지 않는다. 접두어가 늘고 여기 없으면 「미분류」로
#: **드러난다**(`_TOPIC_UNCLASSIFIED`). 조용히 기타로 흡수하면 새 주제가
#: 생겼다는 사실이 보이지 않는다.
TOPIC_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("설비 단가", ("capex.",)),
    # ★ `opex.` 는 R51/WP-2 가 처음 연 이름공간이다(`capex.` 의 대응짝 — 취득비
    # 대 운영비). 선언하지 않으면 `test_unclassified_key_is_shown_not_absorbed`
    # 가 그 자리를 「미분류」로 드러낸다(실측 확인) — 이 파일은 그 래칫이 지키는
    # 대상이므로 조용히 넘기지 않고 여기서 선언한다.
    ("운영비", ("opex.",)),
    ("설비 성능 · 수요", ("capacity_factor.", "load.")),
    ("요금 · 정산 단가", ("tariff.", "escalation.", "fee.")),
    ("제도 · 세제", ("rule.", "tax.", "benefit.", "cost.")),
    ("분석 조건 · 운영", ("analysis.", "ops.")),
    ("검증 정박점", ("oracle.",)),
)

#: 어느 접두어에도 걸리지 않은 항목이 모이는 자리.
_TOPIC_UNCLASSIFIED = "미분류"

#: 신뢰도 표기 순서. 뒤로 갈수록 확인이 필요하다.
_CONFIDENCE_ORDER: tuple[str, ...] = ("확정", "추정", "가정")

#: 신뢰도 `가정` 의 표기. 대장이 쓰는 낱말이며 여기서 짓지 않는다.
ASSUMED_CONFIDENCE = _CONFIDENCE_ORDER[-1]


def topic_of(key: str) -> str:
    """대장 키의 주제. **선언에 없으면 `미분류`** — 위 `TOPIC_PREFIXES` 참조."""
    for topic, prefixes in TOPIC_PREFIXES:
        if any(key.startswith(prefix) for prefix in prefixes):
            return topic
    return _TOPIC_UNCLASSIFIED


def influence_section(report: CaseReport) -> list[str]:
    """붙임 2 — 영향도 상세. **표를 둘로 가른다.**

    ## 왜 한 표가 아닌가

    부기 7종을 순위와 같은 행에 두면 열이 열한 개가 되고, 그 표는 **화면에서도
    인쇄에서도 읽히지 않는다.** `FR-1002-AC3` 이 요구하는 것은 *「각 인자마다
    함께 표시」* 이지 *「한 표에」* 가 아니다 — 같은 인자가 두 표에 같은 이름으로
    있으면 「함께」는 성립하며, 읽히지 않는 표는 표시한 것이 아니다.

    그래서 **판단용**(순위·변동폭·전환)과 **감사·추적용**(대장 키·신뢰도·출처·
    기준연도·최종확인)으로 가른다.
    """
    lines = [
        "## 붙임 2. 영향도 산출 상세",
        "",
        f"- 산출 — {SOLO_SWEEP} (`FR-1002-AC2`) · 인자 하나를 대장 변동 범위에서 "
        "움직이고 파이프라인 재실행",
        "- 대상 — 전제 대장 항목만 (평가자가 정하는 값은 본문 5.2)",
        "- 결합 이동 결과 — 본문 5.1 결합 시나리오 표",
        "",
        "### 판단용",
        "",
        "| 순위 | 인자 | 사용값 | 단위 | 변동 범위 | 결론 변동폭 | 전환 | 산출 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for rank, entry in enumerate(report.uncertain_influences, start=1):
        flips = "**뒤집힘**" if entry.flips_conclusion else NO_VALUE
        method = UNREAD_BY_PIPELINE if entry.unread_by_pipeline else SOLO_SWEEP
        # ★ **변동폭 칸에 `0원` 을 적지 않는다 (R43-G).** 위 `UNREAD_BY_PIPELINE`
        # 참조 — 재어 본 크기와 재지 않은 자리가 한 열에 서면 구별되지 않는다.
        delta = UNREAD_BY_PIPELINE if entry.unread_by_pipeline else _won(
            entry.delta_won
        )
        lines.append(
            f"| {rank} | `{entry.variable}` | {_num(entry.used_value)} | "
            f"{_unit_head(entry.value_unit) or NO_VALUE} | "
            f"{_num(entry.low)}~{_num(entry.high)} | {delta} | "
            f"{flips} | {method} |"
        )
    lines += [
        "",
        "### 감사·추적용",
        "",
        "| 인자 | 대장 키 | 신뢰도 | 출처 | 기준연도 | 최종확인 | 산출 방법 |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in report.uncertain_influences:
        lines.append(
            f"| `{entry.variable}` | `{entry.ledger_key or NO_VALUE}` | "
            f"{entry.confidence} | {entry.source} | "
            f"{entry.base_year or NO_VALUE} | {_date(entry.verified_at)} | "
            f"{_first_sentence(entry.derivation_method)} |"
        )
    lines += ["", UNREAD_NOTE, ""]
    return lines


def _first_sentence(text: str) -> str:
    """산출 방법의 **첫 문장만** — 표 칸에 문단이 들어가면 표가 무너진다.

    전문은 전제 대장(`docs/assumptions.yaml`)이 갖는다. 붙임 1 이 그 대장의
    판을 밝히므로 되짚을 수 있다 — 여기서 자르는 것이 정보를 없애지 않는다.
    """
    if not text:
        return NO_VALUE
    flat = " ".join(text.split())
    # 첫 문장이 「가정.」처럼 한 낱말이면 그것만 남기는 것은 정보가 아니다.
    # 뜻이 서는 길이가 될 때까지 문장을 더 붙인다.
    head = ""
    for piece in flat.split(". "):
        head = f"{head}. {piece}".strip(". ") if head else piece
        if len(head) >= 20:
            break
    return head if len(head) <= 70 else head[:67] + "…"


def _appendix_row(row: AssumptionRow) -> str:
    """붙임 1 의 한 행. **신뢰도가 열로 들어온다** — 주제별로 묶기 때문이다."""
    return (
        f"| `{row.key}` | {row.value} | {row.value_unit or NO_VALUE} | "
        f"{row.confidence} | {row.source} | {row.base_year or NO_VALUE} | "
        f"{_date(row.verified_at)} |"
    )


def _confidence_tally(rows: list[AssumptionRow]) -> str:
    """주제 머리의 신뢰도 내역 — **주제로 묶어도 신뢰도를 잃지 않게** 한다."""
    counts = {name: 0 for name in _CONFIDENCE_ORDER}
    for row in rows:
        counts[row.confidence] = counts.get(row.confidence, 0) + 1
    parts = [f"{name} {counts[name]}" for name in _CONFIDENCE_ORDER if counts[name]]
    extra = [
        f"{name} {count}"
        for name, count in sorted(counts.items())
        if name not in _CONFIDENCE_ORDER and count
    ]
    return " · ".join([*parts, *extra]) or "0"


def appendix_section(report: CaseReport) -> list[str]:
    """붙임 1 — 전 가정 목록. **주제별로 묶고 신뢰도를 열로** (`FR-1002-AC6`).

    ## 왜 신뢰도별 묶음에서 바꿨는가 (검토 「1차 의견」 5)

    종전에는 `확정`/`추정`/`가정` 으로 묶었다. 그러면 **뒤쪽 표가 곧 확인
    목록**이 되는 장점이 있지만, 검토자가 *「설비 단가를 어디서 보는가」* 를
    물을 때 답하지 못한다 — 같은 주제의 항목이 신뢰도별로 흩어지기 때문이다.

    의견은 주제별을 요구했고 **둘 다 필요하다.** 그래서 주제로 묶고 신뢰도를
    **열과 주제 머리의 내역**으로 옮겼다. 확인 대상은 주제 머리의 `가정` 수로
    바로 보이고, 항목은 주제로 찾을 수 있다.

    ⚠ 주제는 **대장 키의 접두어**에서 온다 — 여기서 새 분류를 만들지 않는다
    (`TOPIC_PREFIXES`).
    """
    by_topic: dict[str, list[AssumptionRow]] = {}
    for row in report.assumptions:
        by_topic.setdefault(topic_of(row.key), []).append(row)

    lines = [
        "## 붙임 1. 전제 대장 전건",
        "",
        f"- 대장 — `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version}",
        f"- 범위 — 전 항목 {len(report.assumptions)}건 "
        "(본문 5절 순위에 오르지 않은 것 포함)",
        "- 묶음 — 주제별 (대장 키 접두어) · 신뢰도는 열",
        "",
    ]
    ordered = [topic for topic, _ in TOPIC_PREFIXES] + [_TOPIC_UNCLASSIFIED]
    for topic in ordered:
        rows = by_topic.pop(topic, [])
        if not rows:
            continue
        lines += [
            f"### {topic} — {len(rows)}건 (신뢰도: {_confidence_tally(rows)})",
            "",
            "| 대장 키 | 값 | 단위 | 신뢰도 | 출처 | 기준연도 | 최종확인 |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [_appendix_row(row) for row in sorted(rows, key=lambda r: r.key)]
        lines.append("")
    lines += [
        "- 신뢰도 `확정` — 출처 확인 · `추정` — 근거 있음 · `가정` — 출처 없음 "
        "(확인 대상)",
        "",
    ]
    return lines


def ledger_confidence_note(report: CaseReport) -> str:
    """「전제 N 건 중 M 건은 신뢰도 `가정`」 — **대장을 세어 짓는다** (R43-G).

    ## 왜 이 한 줄이 생겼는가 — **거꾸로 읽힌 기록이 있다**

    1. 요약 「잠정성」 칸과 6.1 「전환 인자의 신뢰도」 칸은 전환 인자가 0건일 때
    *「전환 인자에 신뢰도 `가정` 없음」* 한 줄이었다. 지방정부 담당자가 그것을
    **「이 결론은 가정에 기대지 않는다」**로 읽었고, 문의사항 끝에 *「그대로
    심의회에 가져갔으면 『전제는 튼튼합니다』라고 말했을 것」* 이라고 적었다
    (`docs/evidence/문의사항-지방정부담당자-2026-08-29.md` 나-1 · 덧).

    실제는 정반대다 — **전환 인자가 아예 없어서** 그중에 `가정` 도 없는 것이고,
    대장 전건은 대부분 `가정` 이다. 그래서 같은 칸이 **대장의 신뢰도 구성**을
    함께 싣는다.

    ⚠ **수를 리터럴로 적지 않는다.** 문의사항 자신이 *「이 22 라는 합계는
    자료에 없고 내가 절별 소계를 더한 것이다」* 라고 적는다 — 그 합계를 문장에
    박으면 대장이 늘어난 날 문장만 참인 채로 남는다. 붙임 1 이 세는 것과 같은
    `report.assumptions` 를 세어 짓는 이유가 그것이다.
    """
    rows = report.assumptions
    assumed = sum(1 for row in rows if row.confidence == ASSUMED_CONFIDENCE)
    return (
        f"전제 {len(rows)}건 중 {assumed}건은 신뢰도 "
        f"`{ASSUMED_CONFIDENCE}` (붙임 1)"
    )


def glossary_section() -> list[str]:
    """붙임 9 — 용어 설명.

    ## 왜 필요한가

    `MC-1` 의 검토자는 **비개발자**이며 조항이 그렇게 못 박고 있다. 「할인
    회수기간」·「SOH」·「1변수 스윕」을 설명 없이 쓰면 검토자가 막히는 자리가
    **리포트의 인과가 아니라 어휘**가 된다.

    ⚠ **정의만 싣는다.** 용어에 대한 논평·독법은 해설이므로 두지 않는다
    (양식 0절).
    """
    return [
        "## 붙임 9. 용어 설명",
        "",
        "| 용어 | 정의 |",
        "|---|---|",
        "| **순현재가치(NPV)** | 미래 현금흐름을 현재 가치로 할인해 더한 뒤 "
        "초기투자를 뺀 값. 0 이상이면 분석기간 내 회수 |",
        # ★ 아래 둘은 R43-G 가 넣었다. 5.1 의 *「결론까지 남은 거리 — …원
        # (결손 · 총사업비 …의 …%)」* 이 이 자료에서 가장 많이 인용될 문장인데
        # 그 안의 두 낱말이 이 붙임에 없었다 (문의사항 2026-08-29 나-7).
        "| **결론 축** | 이 평가가 결론을 재는 자. 여기서는 순현재가치 |",
        "| **결손** | 결론 축이 0 에 못 미치는 금액. 반대쪽은 「여유」 |",
        "| **할인율** | 미래의 돈을 현재 가치로 환산할 때 쓰는 비율 |",
        "| **할인 회수기간** | 할인한 누적 현금흐름이 초기투자에 도달하는 데 "
        "걸리는 시간. 분석기간 내 미도달이면 「미회수」 |",
        "| **이용률(Capacity Factor)** | 설비를 최대 출력으로 연중 돌렸을 때 "
        "대비 실제 발전량의 비율 |",
        "| **첨두 절감(Peak Shaving)** | 저장장치로 전력 사용 최대치를 낮춰 "
        "기본요금을 줄이는 운전 방식 |",
        "| **SOC** | 배터리의 현재 충전 상태(%) |",
        "| **SOH** | 배터리의 잔존 성능(%). 신품 대비 용량 |",
        "| **프로포마** | 연도별 편익·비용·순현금흐름을 정리한 표 |",
        f"| **{SOLO_SWEEP}** | 인자 하나만 변동 범위에서 움직이고 나머지는 "
        "고정해 결과 변화를 보는 민감도 분석 |",
        "| **결합 스윕** | 케이스 그리드가 한 축으로 묶은 인자를 함께 움직여 "
        "결과 변화를 보는 민감도 분석 |",
        "| **상호작용 잔차** | 결합 이동의 결론 변동폭에서 단독 이동 변동폭의 "
        "합을 뺀 값. 0이면 두 효과가 더해진다는 뜻 |",
        "| **설계 변수** | 사업자가 **고르는** 값(설비 용량). 값이 틀릴 수 "
        "있는 대장 항목과도, 평가자가 정하는 모형 파라미터와도 다르다 |",
        "| **한계 기여** | 설계 변수를 한 단위 늘렸을 때 결론 축이 움직이는 "
        "폭. 탐색 구간 양 끝점 사이의 평균이며, 형태가 단조일 때만 구간 "
        "전체를 대표한다 |",
        "| **결론 전환값** | 그 인자가 어느 값이 되면 결론(회수 여부)이 "
        "뒤바뀌는가. 재계산으로 확인한 값 |",
        "| **전제 대장** | 계산에 쓰인 모든 값과 그 출처·신뢰도를 모아 둔 정본 "
        "(`docs/assumptions.yaml`). 붙임 1 이 전건 |",
        "| **신뢰도** | 값의 근거 수준. `확정`(출처 확인) · `추정`(근거 있음) "
        "· `가정`(출처 없음, 확인 대상) |",
        "| **디스패치** | 매 시간 어느 자원이 얼마를 발전·충전·방전할지 정하는 "
        "운전 모의 (규칙: 붙임 6 · 결과: 붙임 7) |",
        "",
    ]


def formula_section(report: CaseReport) -> list[str]:
    """붙임 3 — `FR-1001-AC2`·`AC3`. 산식을 자연어·수식·대입값 셋으로."""
    lines = [
        "## 붙임 3. 산식 3중 표기",
        "",
        "- 표기 — 자연어 · 수식 · 대입값 (`FR-1001-AC3`)",
        "- 각 인자의 출처·기준연도·신뢰도 — 붙임 1 · 붙임 2 (`FR-1001-AC4`)",
        "",
    ]
    for formula in report.formulas:
        lines += [
            f"**{formula.label}**",
            "",
            f"- 자연어 — {formula.natural}",
            f"- 수식 — `{formula.expression}`",
            f"- 대입값 — {formula.substituted}",
            "",
        ]
    lines += [
        "- 회수기간과 순현재가치의 관계 — 분석기간 말 누적 할인 현금흐름이 "
        "초기투자를 넘으면 순현재가치 ≥ 0 이며 그것이 「분석기간 내 회수」다",
        "- 전환 판정에 순현재가치(원)를 쓰는 이유 — 미회수 시 회수기간 값이 "
        "존재하지 않아 변동폭을 정의할 수 없다",
        "",
    ]
    return lines


def reproduction_section(report: CaseReport) -> list[str]:
    """붙임 5 — **다른 사람(또는 다른 에이전트)이 이 결과를 다시 낼 수 있는가**
    (R33 검토 지적 5).

    지적 원문은 *「타 에이전트가 보고서의 내용을 보고 분석결과를 재현할 수
    있도록 자세한 정보가 기재되어야 함」* 이었다. 첫 판에는 매니페스트 해시
    한 줄뿐이었는데, **해시는 같은지 다른지만 말하고 어떻게 만드는지는 말하지
    않는다.**

    그래서 ⓐ 명령 ⓑ 입력의 좌표 ⓒ 계산이 서 있는 규약 ⓓ 대조할 해시를 함께
    적는다.
    """
    basis = report.basis
    return [
        "## 붙임 5. 재현 절차",
        "",
        "### 같은 결과를 다시 내는 명령",
        "",
        "```bash",
        "PYTHONUTF8=1 python -m app.run.report_cli \\",
        f"    --scenario {report.scenario_name_slug} \\",
        "    --out <출력경로>",
        "```",
        "",
        "### 이 결과를 만든 입력",
        "",
        "| 입력 | 좌표 · 값 |",
        "|---|---|",
        f"| 시나리오 파일 | `{report.scenario_path}` (읽는 것은 `subsidy_rate` 하나) |",
        f"| 전제 대장 | `docs/assumptions.yaml` 판 **{report.assumption_set_version}** |",
        f"| 보조율 | {report.subsidy_rate:.0%} |",
        f"| 분석기간 | {basis.horizon_years}년 (`analysis.period_years`) |",
        f"| 할인율 | {basis.discount_rate:.4g} (모형 파라미터 — 대장 항목 아님) |",
        f"| 가격 기준 | {report.price_basis} |",
        f"| 초기투자 | {_won(basis.initial_investment_won)} (지원 반영 전 총사업비) |",
        f"| 1년차 편익 | {_won(basis.annual_benefit_won)} |",
        f"| 1년차 운영비 | {_won(basis.annual_cost_won)} |",
        "| 디스패치 규칙 순서 | 붙임 6 (스텝별 결과는 붙임 7) |",
        "",
        "- 설비 제원 — 2.1 표가 전건 · 소유자는 `core/casegrid/e2e_runner.py` "
        "모듈 상수 (대장 아님)",
        "- 대장에서 오는 값 — 단가 · 분석기간",
        "",
        "### 대조",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 실행 매니페스트 해시 | `{report.manifest_hash}` |",
        "| 해시의 성질 | 위 입력이 전부 같으면 같고, 하나라도 다르면 다르다 "
        "(`FR-1005-AC1`) |",
        "| 해시 일치 · 수치 불일치 | 코드가 바뀐 것 |",
        "| 골든 회귀 | `fixtures/golden/` 이 별도로 붙든다 · 기준값은 대장 "
        "가정에 묶여 있어 대장 갱신 시 재산출 필요 |",
        "| 유효기간 | 대장 갱신 시 전 수치 변경 — 위 명령으로 재생성 "
        "(손으로 고치지 않는다) |",
        "",
    ]
