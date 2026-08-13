import pytest

from tests.ci.seed_loader import load_seeds


@pytest.mark.req("FR-1101-AC3")
@pytest.mark.req("FR-1101-AC4")
def test_seed_fallback(monkeypatch, capsys):
    # FR-1101-AC2 마커를 여기서 뗐다 — 이 테스트는 비공개 시드가 **없을 때**만
    # 실행하므로 「비공개 시드로 관리한다」를 한 줄도 지나지 않는다. 그 조항은
    # `test_private_seed.py` 가 존재 분기를 실제로 지나면서 붙든다.
    # 비공개 시드가 없는 경우 합성 시드로 fallback 되는지 확인
    monkeypatch.setenv("DER_PRIVATE_SEED_PATH", "nonexistent_path.yaml")
    seeds = load_seeds()

    assert seeds is not None
    assert seeds.get("capex.pv") is not None
    assert seeds.get("capex.pv").value == 1200000

    captured = capsys.readouterr()
    assert "Using SYNTHETIC seed data" in captured.err
