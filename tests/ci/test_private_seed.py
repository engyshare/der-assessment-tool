"""FR-1101-AC2 — 비공개 시드가 **있을 때**의 경로.

`test_seed_fallback` 은 비공개 시드가 **없을 때**만 실행한다(그것이 AC3·AC4 다).
그래서 AC2(「설비 단가·업계 견적을 담은 시드를 별도 비공개 저장소 또는 배포 시
주입되는 시드 파일로 관리한다」)는 **분기를 한 번도 지나지 않은 채** 다섯 라운드
동안 「자동 검증됨」으로 세어졌다 — R14·R15·R20 이 세 번 같은 판정을 적었다.

여기서 붙드는 것은 셋이다.

① **주입된 자리의 파일이 실제로 읽힌다** — 합성 시드로 조용히 되돌아가지 않는다
② **읽은 값이 그 파일의 값이다** — 경로만 보고 합성값을 내는 구현은 걸린다
③ **비공개 시드의 기본 자리는 공개 저장소에 담기지 않는다** (`.gitignore`)

②를 값 하나로 두지 않고 «주입한 경우와 주입하지 않은 경우가 서로 다른 값을
낸다» 로 적은 이유: 값 하나만 단언하면 «항상 그 값을 내는» 구현도 통과한다.
"""

from pathlib import Path

import pytest

from tests.ci.seed_loader import (
    DEFAULT_PRIVATE_SEED_PATH,
    PRIVATE_SEED_PATH_ENV,
    SeedOrigin,
    load_seeds,
    private_seed_path,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: 배포 시 주입되는 비공개 시드의 모양. 값은 합성 시드와 **일부러 다르게** 둔다 —
#: 같으면 어느 파일을 읽었는지 판정할 수 없다.
_INJECTED_SEED_YAML = """\
version: "private-2026.1"
price_basis: "명목"
assumptions:
  - key: "capex.pv"
    value: 1450000
    value_unit: "원/kW"
    confidence: "확정"
  - key: "quote.vendor_premium"
    value: 88000
    value_unit: "원/kW"
    confidence: "추정"
"""


def _write_injected_seed(tmp_path: Path) -> Path:
    """배포 시 주입되는 시드 파일을 저장소 **밖**에 쓴다.

    `tmp_path` 에 쓰는 것 자체가 AC2 의 형태다 — 이 파일은 공개 저장소에
    커밋되지 않으며, 배포 시점에 주입되어 존재하게 된다.
    """
    path = tmp_path / "seeds.yaml"
    path.write_text(_INJECTED_SEED_YAML, encoding="utf-8")
    return path


@pytest.mark.req("FR-1101-AC2")
def test_injected_private_seed_is_read_instead_of_synthetic(monkeypatch, tmp_path, capsys):
    """주입된 비공개 시드가 읽히고, 그 값이 합성 시드와 다르다."""
    injected = _write_injected_seed(tmp_path)

    monkeypatch.setenv(PRIVATE_SEED_PATH_ENV, str(injected))
    assert private_seed_path() == injected, "환경변수 주입이 경로 결정에 반영되지 않았다"

    loaded_private = load_seeds()
    private_seeds = loaded_private.assumptions
    private_err = capsys.readouterr().err
    assert "Using PRIVATE seed data" in private_err
    assert str(injected) in private_err, "어느 파일을 읽었는지 로그가 말하지 않는다"

    # ① 파일이 실제로 파싱됐다 — 버전은 그 파일에만 있는 값이다
    assert private_seeds.set_version == "private-2026.1"
    # ② 비공개 파일에만 있는 항목이 해석된다
    vendor = private_seeds.get("quote.vendor_premium")
    assert vendor is not None, "비공개 시드에만 있는 항목이 읽히지 않았다"
    assert vendor.value == 88000

    injected_capex = private_seeds.get("capex.pv")
    assert injected_capex is not None
    assert injected_capex.value == 1450000

    # ③ 주입을 걷으면 **다른** 값이 나온다 — 「항상 같은 값」 구현을 배제한다
    monkeypatch.setenv(PRIVATE_SEED_PATH_ENV, str(tmp_path / "absent.yaml"))
    loaded_synthetic = load_seeds()
    synthetic_seeds = loaded_synthetic.assumptions
    capsys.readouterr()
    synthetic_capex = synthetic_seeds.get("capex.pv")
    assert synthetic_capex is not None
    assert synthetic_capex.value != injected_capex.value, (
        "주입한 경우와 주입하지 않은 경우가 같은 값을 냈다 — 주입 경로가 "
        "실제로 쓰이지 않는다"
    )
    assert synthetic_seeds.get("quote.vendor_premium") is None, (
        "비공개 항목이 합성 시드에서도 나온다 — 두 시드가 섞였다"
    )

    # ★★ **출처가 결과에 남고, 두 경우가 다르다 (R31 결정 §6).**
    #
    # 「대체이지 병합이 아니다」를 택한 이유가 *「어느 시드로 돌렸는가 한 줄이
    # 출처를 결정한다」* 인데, 그 한 줄이 결과에 없으면 이점이 사라진다 — 골든
    # 대조(`NFR-104`)가 어긋났을 때 원인이 시드인지 코드인지 가릴 수 없다.
    #
    # **두 경우를 대조한다** — 한쪽만 보면 「늘 같은 출처를 적는」 구현도 통과한다.
    assert loaded_private.origin is SeedOrigin.PRIVATE
    assert loaded_synthetic.origin is SeedOrigin.SYNTHETIC
    assert loaded_private.origin is not loaded_synthetic.origin
    # 출처 문면이 **어느 파일인지**까지 말한다 — 종류만으로는 주입 자리를 모른다
    assert str(injected) in loaded_private.provenance


@pytest.mark.req("FR-1101-AC2")
def test_default_private_seed_location_is_excluded_from_public_repo():
    """비공개 시드의 기본 자리가 `.gitignore` 로 막혀 있다.

    주입 경로만 검사하면 「기본 자리에 그냥 커밋하면 된다」가 열린 채로 남는다.
    AC2 의 「별도 비공개 저장소」 절반이 이것이다.
    """
    ignored = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    patterns = {line.strip() for line in ignored if line.strip()}

    default = Path(DEFAULT_PRIVATE_SEED_PATH)
    parent = default.parent.as_posix()
    assert f"{parent}/" in patterns or parent in patterns, (
        f"비공개 시드 기본 자리 {DEFAULT_PRIVATE_SEED_PATH!r} 의 디렉터리 "
        f"{parent!r} 가 .gitignore 에 없다 — 공개 저장소로 유입될 수 있다"
    )
