"""심의보고서 **붙임** 렌더러 — 양식 `docs/report-form-심의보고서.md` 3절.

## 왜 본문과 갈랐는가

`NFR-206` 코드 스프롤 검사가 `narrative.py` 를 522줄로 잡았다(상한 500). 쪼갤
자리를 **본문/붙임 경계**로 잡은 이유는 그것이 양식이 이미 그은 선이기 때문이다 —
임의로 쪼개면 파일 경계와 문서 구조가 어긋나 다음 사람이 어느 절이 어느 파일에
있는지 매번 찾아야 한다.

⚠ **순서의 소유자는 여전히 `narrative.py` 하나다.** 여기서는 붙임을 만들기만
한다. 순서가 두 곳에서 정해지면 조항(`FR-1002-AC1`)이 어느 파일 소관인지 갈린다.
"""
from __future__ import annotations

from core.report._format import NO_VALUE, _date, _num, _unit_head, _won
from core.report.case_report import AssumptionRow, CaseReport


def influence_section(report: CaseReport) -> list[str]:
    """붙임 2 — 영향도 상세. **표를 둘로 가른다.**

    ## 왜 한 표가 아닌가

    부기 7종을 순위와 같은 행에 두면 열이 열한 개가 되고, 그 표는 **화면에서도
    인쇄에서도 읽히지 않는다.** `FR-1002-AC3` 이 요구하는 것은 *「각 인자마다
    함께 표시」* 이지 *「한 표에」* 가 아니다 — 같은 인자가 두 표에 같은 이름으로
    있으면 「함께」는 성립하며, 읽히지 않는 표는 표시한 것이 아니다.

    그래서 **판단용**(순위·변동폭·전환)과 **감사·추적용**(대장 키·신뢰도·출처·
    기준연도·최종확인)으로 가른다. 앞의 것은 심의위원이, 뒤의 것은 검증하는
    사람이 읽는다.
    """
    lines = [
        "## 붙임 2. 영향도 산출 상세",
        "",
        "각 인자를 **대장이 밝힌 변동 범위**에서 하나씩 움직여 파이프라인을 다시",
        "돌리고, 결론이 움직인 폭으로 순위를 매겼다 (`FR-1002-AC2` 1변수 스윕).",
        "",
        "여기 있는 것은 **틀릴 수 있는 값**뿐이다 — 즉 이 표는 *「어느 자료를 먼저",
        "확보해야 하는가」* 에 답한다. 평가자가 정하는 값(할인율 등)은 불확실성이",
        "아니라 선택이므로 본문 5.2 에서 따로 본다.",
        "",
        "### 판단용",
        "",
        "| 순위 | 인자 | 사용값 | 단위 | 변동 범위 | 결론 변동폭 | 전환 |",
        "|---|---|---|---|---|---|---|",
    ]
    for rank, entry in enumerate(report.uncertain_influences, start=1):
        flips = "**뒤집힘**" if entry.flips_conclusion else "—"
        if entry.unread_by_pipeline:
            flips = "⚠ 미반영 의심"
        lines.append(
            f"| {rank} | {entry.variable} | {_num(entry.used_value)} | "
            f"{_unit_head(entry.value_unit) or NO_VALUE} | "
            f"{_num(entry.low)}~{_num(entry.high)} | {_won(entry.delta_won)} | "
            f"{flips} |"
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
            f"| {entry.variable} | `{entry.ledger_key or NO_VALUE}` | "
            f"{entry.confidence} | {entry.source} | "
            f"{entry.base_year or NO_VALUE} | {_date(entry.verified_at)} | "
            f"{_first_sentence(entry.derivation_method)} |"
        )
    lines.append("")
    if report.unread_variables:
        names = " · ".join(e.variable for e in report.unread_variables)
        lines += [
            f"> ⚠ **{names} 의 변동폭이 정확히 0원이다.** 범위를 끝에서 끝까지",
            "> 흔들어도 결론이 한 원도 움직이지 않는 일은 경제적으로 일어나지",
            "> 않는다 — **계산이 이 인자를 읽지 않고 있을 가능성이 크다.**",
            "> 「영향이 없다」로 읽지 말 것. 확인 전까지 이 인자에 대한 판단은",
            "> 이 보고서로 내릴 수 없다.",
            "",
        ]
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
    """붙임 1 의 한 행. **신뢰도 열이 없다** — 절 제목이 이미 말한다."""
    return (
        f"| `{row.key}` | {row.value} | {row.value_unit or NO_VALUE} | "
        f"{row.source} | {row.base_year or NO_VALUE} | "
        f"{_date(row.verified_at)} |"
    )

def appendix_section(report: CaseReport) -> list[str]:
    """붙임 1 — 전 가정 목록. **신뢰도별로 가른다** (`FR-1002-AC6`).

    스물 몇 줄을 한 표에 늘어놓으면 *「무엇을 확인해야 하는가」* 가 보이지 않는다.
    `확정`(출처 있음)과 `가정`(확인 필요)을 가르면 **뒤쪽 표가 곧 확인 목록**이
    된다 — 조항이 요구하는 「전 항목 제공」은 그대로 지키면서.
    """
    by_confidence: dict[str, list[AssumptionRow]] = {}
    for row in report.assumptions:
        by_confidence.setdefault(row.confidence, []).append(row)

    lines = [
        "## 붙임 1. 전제 대장 전건",
        "",
        f"재현·검증용이다. 전제 대장 `{report.assumption_set_name}` "
        f"판 {report.assumption_set_version} 의 **전 항목**이며, 본문 5절 순위에",
        "오르지 않은 것도 포함한다.",
        "",
    ]
    # `확정` → `추정` → `가정` 순. 뒤로 갈수록 확인이 필요하다.
    for confidence in ("확정", "추정", "가정"):
        rows = by_confidence.pop(confidence, [])
        if not rows:
            continue
        note = {
            "확정": "출처가 확인된 값이다.",
            "추정": "근거는 있으나 확정은 아니다.",
            "가정": "**출처가 아직 없다 — 확인 대상이다.**",
        }[confidence]
        lines += [
            f"### 신뢰도 `{confidence}` — {len(rows)}건",
            "",
            note,
            "",
            "| 대장 키 | 값 | 단위 | 출처 | 기준연도 | 최종확인 |",
            "|---|---|---|---|---|---|",
        ]
        lines += [_appendix_row(row) for row in rows]
        lines.append("")
    for confidence, rows in sorted(by_confidence.items()):
        lines += [
            f"### 신뢰도 `{confidence}` — {len(rows)}건",
            "",
            "| 대장 키 | 값 | 단위 | 출처 | 기준연도 | 최종확인 |",
            "|---|---|---|---|---|---|",
        ]
        lines += [_appendix_row(row) for row in rows]
        lines.append("")
    return lines

def glossary_section() -> list[str]:
    """붙임 6 — 용어 설명.

    ## 왜 필요한가

    `MC-1` 의 검토자는 **비개발자**이며 조항이 그렇게 못 박고 있다. 「할인
    회수기간」·「SOH」·「1변수 스윕」을 설명 없이 쓰면 검토자가 막히는 자리가
    **리포트의 인과가 아니라 어휘**가 되고, 그 미달은 원인을 짚기도 어렵다.

    ⚠ **본문에 풀어 쓰지 않고 붙임에 둔다.** 본문에서 매번 풀면 4~5쪽을 넘고,
    아는 사람에게는 읽기를 끊는다.
    """
    return [
        "## 붙임 6. 용어 설명",
        "",
        "이 보고서에 나오는 용어를 풀어 적는다. 검토자가 막히는 자리가 **인과가",
        "아니라 어휘**가 되지 않도록 둔다.",
        "",
        "| 용어 | 뜻 |",
        "|---|---|",
        "| **순현재가치(NPV)** | 미래 현금흐름을 현재 가치로 할인해 더한 뒤 "
        "초기투자를 뺀 값. 0 이상이면 분석기간 안에 회수된다는 뜻이다 |",
        "| **할인율** | 미래의 돈을 현재 가치로 환산할 때 쓰는 비율. 높을수록 "
        "먼 미래의 편익이 작게 평가된다 |",
        "| **할인 회수기간** | 할인한 누적 현금흐름이 초기투자에 도달하는 데 "
        "걸리는 시간. 분석기간 안에 도달하지 못하면 「미회수」다 |",
        "| **이용률(Capacity Factor)** | 설비를 최대 출력으로 연중 돌렸을 때 "
        "대비 실제 발전량의 비율 |",
        "| **첨두 절감(Peak Shaving)** | 저장장치로 전력 사용 최대치를 낮춰 "
        "기본요금을 줄이는 운전 방식 |",
        "| **SOC** | 배터리의 현재 충전 상태(%). 운전 범위를 제한해 수명을 "
        "지킨다 |",
        "| **SOH** | 배터리의 잔존 성능(%). 신품 대비 용량이며, 이 값이 수명 "
        "종료 기준에 닿으면 교체 대상이다 |",
        "| **프로포마** | 연도별 편익·비용·순현금흐름을 정리한 표 |",
        "| **1변수 스윕** | 인자 하나만 변동 범위에서 움직이고 나머지는 고정해 "
        "결과가 얼마나 변하는지 보는 민감도 분석 |",
        "| **결론 전환 임계값** | 그 인자가 어느 값이 되면 결론(회수 여부)이 "
        "뒤바뀌는가. 이 보고서는 그 값을 실제로 다시 계산해 확인한다 |",
        "| **전제 대장** | 계산에 쓰인 모든 값과 그 출처·신뢰도를 모아 둔 정본 "
        "(`docs/assumptions.yaml`). 붙임 1 이 그 전건이다 |",
        "| **신뢰도** | 값의 근거 수준. `확정`(출처 확인) · `추정`(근거는 있음) "
        "· `가정`(출처 없음, 확인 대상) 셋이다 |",
        "",
    ]

def formula_section(report: CaseReport) -> list[str]:
    """`FR-1001-AC2`·`AC3` — 산식을 자연어·수식·대입값 셋으로."""
    lines = [
        "## 붙임 3. 산식 3중 표기",
        "",
        "각 산식을 **자연어 · 수식 · 대입값** 셋으로 적는다. 대입값의 각 인자는",
        "2절 표에서 출처·기준연도·신뢰도를 확인할 수 있다 (`FR-1001-AC4`).",
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
        "> **회수기간과 순현재가치는 같은 판정의 두 얼굴이다.** 분석기간 말",
        "> 누적 할인 현금흐름이 초기투자를 넘으면 순현재가치가 0 이상이고, 그것이",
        "> 곧 「분석기간 안에 회수된다」이다. 위 1·2절이 순현재가치(원)로 전환을",
        "> 재는 이유는 회수기간에는 **뒤집힐 부호가 없기 때문**이다 — 회수하지",
        "> 못하면 값이 존재하지 않아 「얼마나 못 미쳤는지」를 말할 수 없다.",
        "",
    ]
    return lines




def reproduction_section(report: CaseReport) -> list[str]:
    """부록 B — **다른 사람(또는 다른 에이전트)이 이 결과를 다시 낼 수 있는가**
    (R33 검토 지적 5).

    지적 원문은 *「타 에이전트가 보고서의 내용을 보고 분석결과를 재현할 수
    있도록 자세한 정보가 기재되어야 함」* 이었다. 첫 판에는 매니페스트 해시
    한 줄뿐이었는데, **해시는 같은지 다른지만 말하고 어떻게 만드는지는 말하지
    않는다** — 재현의 근거가 아니라 재현 뒤의 대조 수단이다.

    그래서 ⓐ 명령 ⓑ 입력의 좌표 ⓒ 계산이 서 있는 규약 ⓓ 대조할 해시를 함께
    적는다. 넷이 다 있어야 「해 보았더니 다른 수가 나왔다」가 **어디서** 갈렸는지
    말할 수 있다.
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
        "",
        "설비 제원은 0절 표가 전부이며 그 값의 소유자는",
        "`core/casegrid/e2e_runner.py` 의 모듈 상수다 — 대장이 아니다(설비 제원은",
        "금액이 아니기 때문이다). 단가·분석기간만 대장에서 온다.",
        "",
        "### 대조",
        "",
        f"- 실행 매니페스트 해시 **`{report.manifest_hash}`**",
        "- 위 입력이 전부 같으면 해시가 같고, 하나라도 다르면 달라진다",
        "  (`FR-1005-AC1`). **해시가 같은데 수치가 다르면 코드가 바뀐 것**이다.",
        "- 골든 회귀는 `fixtures/golden/` 이 따로 붙든다 — 그쪽 기준값은 대장",
        "  가정에 묶여 있어 **대장을 갱신하면 재산출이 필요하다.** 회귀 실패가",
        "  곧 결함은 아니다.",
        "",
        "### 이 수치의 유효기간",
        "",
        "붙임 1 에 신뢰도 `가정` 항목이 포함되어 있다. **대장이 갱신되면 이",
        "리포트의 모든 수치가 바뀐다** — 리포트를 손으로 고치지 말고 위 명령을",
        "다시 돌려 새로 뽑을 것.",
        "",
    ]
