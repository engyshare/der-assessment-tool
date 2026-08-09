import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    spec_path = Path("rslt/spec-분산특구-경제성평가.md")
    original = spec_path.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as d:
        temp_dir = Path(d)

        # 1. Test missing assignment
        # We will modify the table to remove FR-102 from WP-1a
        missing_spec = original.replace("FR-101~106", "FR-101, FR-103~106")
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
        # Add FR-301 to WP-4
        dup_spec = original.replace(
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
