import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class Manifest:
    hash: str

def create_manifest(inputs: dict[str, Any]) -> Manifest:
    """Create execution manifest and return deterministic hash."""
    serialized = json.dumps(inputs, sort_keys=True)
    h = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    return Manifest(hash=h)
