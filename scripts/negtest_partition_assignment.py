import subprocess
import sys
import tempfile
from pathlib import Path


def plant(text: str, old: str, new: str) -> str:
    """위반을 **실제로 심었는지 확인하고** 심는다.

    `str.replace` 는 대상이 없으면 **아무 일도 하지 않고 원본을 돌려준다.**
    그러면 심지 않은 spec 을 검사에 넣고 «위반을 못 잡았다» 는 결과를 받는다 —
    검사가 멀쩡한데도 빨간불이 나거나, 판정 문구가 느슨하면 **심지 않은 것을
    통과로 읽는다.**

    실제로 일어났다 (R9). `WP-1` 행이 `FR-101~106` 이었는데 `FR-101` 을
    `WP-0` 단독으로 배정하면서 `FR-102~106` 이 됐고, 아래 심기 문자열은
    **손으로 유지되는 리터럴**이라 조용히 빈 치환이 됐다.

    **이 저장소가 반복해서 세는 형태다** — 손으로 유지하는 목록·패턴은
    대상이 바뀔 때 따라 바뀌지 않고, 그 순간부터 아무것도 검사하지 않는다.
    그래서 여기서 닫는다: **치환이 실제로 일어나지 않으면 실패한다.**
    """
    out = text.replace(old, new)
    if out == text:
        print(f"FAILED: 심기 실패 — spec 에서 {old!r} 를 찾지 못했다.")
        print("  spec 이 바뀌었고 이 음성 테스트가 따라가지 않은 것이다.")
        print("  **검사가 고장난 것이 아니라 심기가 고장난 것이다** — 문자열을")
        print("  지금 spec 에 맞게 고칠 것. 그냥 지우면 이 검사는 죽는다.")
        sys.exit(1)
    return out


def main():
    spec_path = Path("rslt/spec-분산특구-경제성평가.md")
    original = spec_path.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)

        # 1. Test missing assignment
        # `WP-1` 행에서 `FR-102` 를 빼 미배정으로 만든다. (R9: `FR-101` 이
        # `WP-0` 단독이 되면서 이 행은 `FR-101~106` → `FR-102~106` 이 됐다)
        missing_spec = plant(original, "FR-102~106", "FR-103~106")
        p_missing = temp_dir / "missing.md"
        p_missing.write_text(missing_spec, encoding="utf-8")

        print("Running negtest: Missing FR-102")
        result = subprocess.run(
            [sys.executable, "scripts/check_partition_assignment.py", str(p_missing)],
            capture_output=True, text=True)
        if "미배정: FR-102" not in result.stdout:
            print("FAILED: Did not detect missing FR-102")
            print(result.stdout)
            sys.exit(1)

        # 2. Test duplicate assignment
        # `WP-4` 행에 `FR-301`(`WP-6` 것)을 더해 중복으로 만든다.
        dup_spec = plant(
            original,
            "| FR-401, FR-402, FR-404 |",
            "| FR-401, FR-402, FR-404, FR-301 |")
        p_dup = temp_dir / "dup.md"
        p_dup.write_text(dup_spec, encoding="utf-8")

        print("Running negtest: Duplicate FR-301")
        result = subprocess.run(
            [sys.executable, "scripts/check_partition_assignment.py", str(p_dup)],
            capture_output=True, text=True)
        if "중복 배정: FR-301" not in result.stdout:
            print("FAILED: Did not detect duplicate FR-301")
            print(result.stdout)
            sys.exit(1)

    print(
        "Negative testing passed! The tool successfully detected missing and duplicate "
        "assignments."
    )

if __name__ == "__main__":
    main()
