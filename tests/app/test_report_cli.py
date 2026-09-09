"""`MC-1` 이 실제로 쓰는 출구 — 파일 하나가 나오는가.

`MC-1` 진행에 필요한 것은 서버가 아니라 **파일**이다(`manual-checks.yaml` 의
`evidence` 칸이 경로를 요구한다). 이 파일이 붙드는 것은 그 파일이 실제로
쓰이는가, 그리고 **없는 시나리오를 조용히 통과시키지 않는가**다.
"""
from __future__ import annotations

from pathlib import Path

from app.run.report_cli import (
    DEFAULT_SCENARIO,
    INDEX_FILENAME,
    available_scenarios,
    main,
)


def test_cli_writes_a_report_file(tmp_path: Path) -> None:
    """`--out` 이 실제 파일을 남기고 그 안에 리포트가 들어 있다.

    ⚠ **`req()` 마커를 달지 않았다.** `FR-1003` 이 열거하는 내보내기 형식은
    XLSX·PDF·JSON·CSV 넷이며 **마크다운은 거기 없다.** `FR-1003-AC2`(PDF)를
    달아 보았고, 그것은 「PDF 를 냈다」는 거짓 진술이 된다 — 이 저장소가
    반복해서 경계해 온 «검사를 통과시키려고 인용을 맞추는» 형태다.

    조항이 비어 있는 것이 사실이다: `MC-1` 이 요구하는 **사람이 읽는 산출물**
    형식을 spec 이 열거하지 않는다. 이것은 `status-human.md` 7단계(spec 개정
    판단)로 올릴 사항이며, 조항이 생기면 여기에 마커를 단다.
    """
    target = tmp_path / "evidence" / "MC-1.md"
    assert main(["--out", str(target)]) == 0

    text = target.read_text(encoding="utf-8")
    assert text.startswith("# 경제성 평가 심의보고서"), "머리글이 보고서가 아니다"
    assert "## 붙임 2. 영향도 산출 상세" in text
    assert "## 붙임 1. 전제 대장 전건" in text


def test_missing_scenario_stops_with_a_nonzero_code(capsys) -> None:
    """없는 이름은 **멈춘다** — 0 을 돌려주면 빈 파일이 증거가 된다."""
    assert main(["--scenario", "없는시나리오"]) == 2
    message = capsys.readouterr().err
    assert "없는시나리오" in message, "무엇이 없는지 말하지 않는다"
    assert DEFAULT_SCENARIO in message, "무엇을 쓸 수 있는지 말하지 않는다"


def test_default_scenario_exists() -> None:
    """기본 시나리오가 실재한다 — 픽스처 이름이 바뀌면 여기서 잡힌다."""
    assert DEFAULT_SCENARIO in available_scenarios()


def test_the_split_index_says_which_policy_variant_this_run_is(tmp_path: Path) -> None:
    """★ 목차가 **「이 실행이 무슨 정책 변형인가」를 한 문장으로** 싣는다 (R68/WP-9).

    검토서 §3.7 의 마지막 문장이 요구한 것이고, 독립 검증
    (`.orch/R68/result_V.md` 결함 #2)이 안 닫혔음을 실물로 짚었다 — 머리표는
    「평가 대상」만 실었는데 그것은 평가 **대상**이지 **지원 조건**이 아니다.

    ## ⛔ 목차는 **세 시나리오가 함께 쓴다**

    그래서 이 검사는 문장의 «내용»을 리터럴로 견주지 않고 **두 시나리오의
    목차가 서로 다른 말을 하는가**를 본다. 한쪽을 글자로 박으면 지원 20%
    실행의 목차가 자기를 무지원이라고 적게 되고, 그 형태를 이 검사가 잡는다.

    ⚠ 문면의 정본은 `core/report/verification_variants.py::
    policy_variant_sentence` 이고 그 자리의 검사는
    `tests/report/test_verification_variants.py` 가 갖는다 — 여기서 재는 것은
    **CLI 가 실제로 그것을 목차에 싣는가**(배선)뿐이다.
    """
    def index_of(scenario: str) -> str:
        out = tmp_path / scenario
        assert main(
            ["--kind", "verification", "--split-stages",
             "--scenario", scenario, "--out", str(out)]
        ) == 0
        return (out / INDEX_FILENAME).read_text(encoding="utf-8")

    plain = index_of(DEFAULT_SCENARIO)
    assert DEFAULT_SCENARIO in plain, "목차가 어느 시나리오인지 적지 않는다"

    other = next(s for s in available_scenarios() if s != DEFAULT_SCENARIO)
    assert other in index_of(other)
    # ⓐ 지원 조건을 말하는 문장이 실제로 **갈린다** — 두 목차가 같으면 그
    #    문장은 실행이 아니라 글자에서 온 것이다.
    assert index_of(other) != plain
