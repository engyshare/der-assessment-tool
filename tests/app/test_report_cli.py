"""`MC-1` 이 실제로 쓰는 출구 — 파일 하나가 나오는가.

`MC-1` 진행에 필요한 것은 서버가 아니라 **파일**이다(`manual-checks.yaml` 의
`evidence` 칸이 경로를 요구한다). 이 파일이 붙드는 것은 그 파일이 실제로
쓰이는가, 그리고 **없는 시나리오를 조용히 통과시키지 않는가**다.
"""
from __future__ import annotations

from pathlib import Path

from app.run.report_cli import DEFAULT_SCENARIO, available_scenarios, main


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
    assert text.startswith("# 경제성 평가 리포트"), "머리글이 리포트가 아니다"
    assert "## 2. 영향도 순위" in text
    assert "## 부록. 전 가정 목록" in text


def test_missing_scenario_stops_with_a_nonzero_code(capsys) -> None:
    """없는 이름은 **멈춘다** — 0 을 돌려주면 빈 파일이 증거가 된다."""
    assert main(["--scenario", "없는시나리오"]) == 2
    message = capsys.readouterr().err
    assert "없는시나리오" in message, "무엇이 없는지 말하지 않는다"
    assert DEFAULT_SCENARIO in message, "무엇을 쓸 수 있는지 말하지 않는다"


def test_default_scenario_exists() -> None:
    """기본 시나리오가 실재한다 — 픽스처 이름이 바뀌면 여기서 잡힌다."""
    assert DEFAULT_SCENARIO in available_scenarios()
