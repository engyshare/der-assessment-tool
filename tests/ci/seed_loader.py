import os
import sys
from pathlib import Path

from core.assumption.provider import AssumptionSet


def load_seeds() -> AssumptionSet:
    private_path = os.getenv("DER_PRIVATE_SEED_PATH", "data/private/seeds.yaml")
    if Path(private_path).exists():
        print(f"Using PRIVATE seed data from {private_path}", file=sys.stderr)
        return AssumptionSet.load_from_yaml(private_path)

    synthetic_path = Path(__file__).parent / "synthetic_seeds.yaml"
    print(f"Using SYNTHETIC seed data (fallback) from {synthetic_path}", file=sys.stderr)
    return AssumptionSet.load_from_yaml(str(synthetic_path))
