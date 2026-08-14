import pytest

from tests.ci.seed_loader import SeedOrigin, load_seeds


@pytest.mark.req("FR-1101-AC3")
@pytest.mark.req("FR-1101-AC4")
def test_seed_fallback(monkeypatch, capsys):
    # FR-1101-AC2 마커를 여기서 뗐다 — 이 테스트는 비공개 시드가 **없을 때**만
    # 실행하므로 「비공개 시드로 관리한다」를 한 줄도 지나지 않는다. 그 조항은
    # `test_private_seed.py` 가 존재 분기를 실제로 지나면서 붙든다.
    # 비공개 시드가 없는 경우 합성 시드로 fallback 되는지 확인
    monkeypatch.setenv("DER_PRIVATE_SEED_PATH", "nonexistent_path.yaml")
    loaded = load_seeds()
    seeds = loaded.assumptions

    assert seeds is not None
    assert seeds.get("capex.pv") is not None
    assert seeds.get("capex.pv").value == 1200000

    captured = capsys.readouterr()
    assert "Using SYNTHETIC seed data" in captured.err

    # ★ **출처가 결과에 남는다 (R31).** `stderr` 는 사람이 실행 중에 보는 것이고
    # 결과에 기록되는 것은 그것을 대신하지 않는다 — 골든 대조가 어긋났을 때
    # 「어느 시드로 돌렸는가」를 결과만 보고 알 수 있어야 한다.
    assert loaded.origin is SeedOrigin.SYNTHETIC
    assert "합성 예시 시드" in loaded.provenance
