"""플러그인 자동 등록 검증 — 작업 6.7 / spec NFR-207.

**왜 이 파일이 `tests/contract/` 에 있는가.** 검사 대상이 **구획 여섯 개에 걸쳐
있다** — 「자원 6종이 전부 발견되는가」는 어느 한 구획도 단독으로 답할 수 없다.
§16.1 W-5는 교차 구획 검증을 계약 테스트(L3)로만 하라고 규정한다. `tests/der/`
에 두면 그 파일이 형제 구획의 산출물을 알아야 하고, 자원 하나를 추가할 때마다
남의 구획 테스트를 고쳐야 한다 — NFR-207이 없애려는 바로 그 구조다.

**M1을 기계로 확인한다.** *"신규 자원 추가 PR의 diff에 §16.4 공유 파일 목록의
변경 0줄"* 은 PR을 봐야 아는 사실처럼 보이지만, 그 diff가 필요해지는 **원인**은
소스에 있다 — 공유 파일에 자원 이름이 적혀 있으면 추가할 때 그 파일을 고쳐야
한다. 그래서 「공유 파일에 자원 이름이 0건」을 검사한다.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import core.asset
import core.der
from core.contracts.asset import CommonAsset
from core.contracts.der import DER
from core.contracts.registry import (
    REGISTRY_ABSTRACT_FLAG,
    RegistryError,
    discover,
    load_package_modules,
)

#: spec FR-102-AC1 이 열거한 자원 유형 중 **구현이 있는 것**. 없는 셋
#: (`VPP`·`Boiler`·`Genset`)은 미매핑으로 남아 있으며 그 사실이 매핑표에 있다 —
#: 여기에 적어 두면 같은 사실이 두 곳에 남아 어긋난다.
IMPLEMENTED_DER_TAGS = {"PV", "ESS", "EV_V2G", "HeatPump", "Load", "ThermalLoad"}

#: FR-106-AC2 가 열거한 공통설비 유형 3종
COMMON_ASSET_TAGS = {"CEMS", "HEMS", "MeteringComm"}

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── AC1: 중앙 등록 파일 없이 발견된다 ────────────────────────────────

@pytest.mark.contract
@pytest.mark.req("NFR-207-AC1")
def test_der_registry_is_built_by_scanning() -> None:
    """`core/der/` 스캔만으로 자원 전건이 발견된다.

    `tag` 를 키로 쓰는 것이 요점이다 — 클래스명·파일명에서 파생시키면
    `EV_V2G` 가 즉시 문제가 된다(대소문자·밑줄). spec 조항 ID
    `FR-102-AC1.EV_V2G` 는 리터럴이며 파생 대상이 아니다.
    """
    registry = discover(core.der, DER)

    assert set(registry) == IMPLEMENTED_DER_TAGS, (
        f"발견된 자원이 기대와 다릅니다: {sorted(registry)}. "
        "자원을 추가했다면 이 목록도 늘어야 하고, 줄었다면 어떤 자원이 "
        "레지스트리에서 사라진 것입니다"
    )
    for tag, cls in registry.items():
        assert issubclass(cls, DER)
        assert cls.tag == tag, (
            f"{cls.__name__}.tag({cls.tag!r}) 와 레지스트리 키({tag!r}) 가 "
            "다릅니다 — 색인이 tag 를 그대로 쓰지 않고 있습니다"
        )


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC1")
def test_common_asset_registry_uses_the_same_mechanism() -> None:
    """같은 발견기가 `core/asset/` 에도 쓰인다.

    발견기가 특정 구획을 모르기 때문에 그럴 수 있다 — 그것이
    `core/contracts/` 에 둘 수 있었던 이유이기도 하다 (NFR-208-AC3).
    """
    registry = discover(core.asset, CommonAsset)
    assert set(registry) == COMMON_ASSET_TAGS


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC1")
def test_shared_base_class_is_excluded_only_by_explicit_marker() -> None:
    """공유 기반 클래스는 **표식으로** 빠진다 — 그리고 표식은 상속되지 않는다.

    `StandardCommonAsset` 은 구상이지만 FR-106-AC2 가 열거한 «유형» 이 아니다.
    표식을 `getattr` 로 보면 **상속되어 CEMS·HEMS·공용 계량통신 셋 전부가
    등록에서 빠진다** — 그 상태는 「공통설비가 없는 단지」로 계산되고, CEMS
    구축비·운영비가 통째로 사라지는데 결과는 그럴듯하다.

    실제로 구현 중에 한 번 그 상태가 됐고 이 검사가 그것을 고정한다.
    """
    from core.asset.common_asset import CEMS, StandardCommonAsset

    assert StandardCommonAsset.__dict__.get(REGISTRY_ABSTRACT_FLAG) is True
    # 상속된 값은 참이지만 **자기 선언은 없다** — 그래서 등록된다
    assert getattr(CEMS, REGISTRY_ABSTRACT_FLAG, False) is True
    assert REGISTRY_ABSTRACT_FLAG not in CEMS.__dict__
    assert "CEMS" in discover(core.asset, CommonAsset)


# ── AC1 · M1: 공유 파일에 자원 이름이 없다 ──────────────────────────

@pytest.mark.contract
@pytest.mark.req("NFR-207-M1")
def test_no_central_registry_file_names_any_resource() -> None:
    """§16.4 공유 파일에 자원 이름이 **0건**이다.

    이것이 M1(*"신규 자원 추가 PR의 diff에 공유 파일 변경 0줄"*)의 기계 검사
    가능한 형태다. diff가 필요해지는 **원인**은 소스에 있다 — 공유 파일이 자원
    이름을 들고 있으면 추가할 때 그 파일을 고쳐야 한다.

    `core/der/__init__.py` 를 특히 본다. §16.4는 이 파일이 공유 파일 목록에
    **없는 이유가 「존재해서는 안 되기 때문」** 이라고 적었다. 지금은 패키지
    표식으로만 있고, 자원 이름이 들어오는 순간 6명이 같은 줄을 편집하는 구조로
    되돌아간다.

    **서술이 아니라 코드만 본다.** 파일을 문자열로 훑으면 이 검사를 설명하는
    주석과 독스트링이 그대로 걸린다 — 실제로 처음 실행에서 그렇게 됐다. 저장소가
    반복해서 만나 온 유형(*"검사 도구를 설명하는 문장이 그 검사에 걸린다"*)이며,
    해법도 같다: **서술과 선언을 구분한다.** 여기서는 `ast` 로 코드 식별자와
    문자열 리터럴만 뽑는다.
    """
    shared = [
        REPO_ROOT / "core" / "der" / "__init__.py",
        REPO_ROOT / "core" / "asset" / "__init__.py",
        REPO_ROOT / "core" / "contracts" / "__init__.py",
        REPO_ROOT / "core" / "contracts" / "registry.py",
    ]
    names = IMPLEMENTED_DER_TAGS | COMMON_ASSET_TAGS

    offending: list[str] = []
    for path in shared:
        used = _code_names(path) & names
        offending += [f"{path.relative_to(REPO_ROOT)} ← {tag}" for tag in sorted(used)]

    assert not offending, (
        "공유 파일이 자원 이름을 들고 있습니다: " + ", ".join(offending)
        + ". 자원을 추가할 때 이 파일을 고쳐야 하는 구조이며, 6명이 같은 줄을 "
        "편집하게 되어 구획 격리가 선언만 남습니다 (§16.1 W-3 · NFR-207-M1)"
    )


def _code_names(path: Path) -> set[str]:
    """파일의 **코드**에 등장하는 식별자와 문자열 리터럴 (주석·독스트링 제외).

    중앙 등록부는 코드로 나타난다 — `REGISTRY = {"PV": PV, …}` 는 문자열 리터럴
    `"PV"` 와 이름 `PV` 다. 반대로 «PV 를 예로 들면» 같은 서술은 등록부가 아니다.
    문자열 포함 검사로는 이 둘이 구분되지 않고, **구분하지 못한 검사는 서술을
    고치라고 요구하다가 결국 꺼진다.**
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef))
                and node.body
                and ast.get_docstring(node, clean=False) is not None):
            docstrings.add(id(node.body[0]))

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.rsplit(".", 1)[-1])
    return names


@pytest.mark.contract
@pytest.mark.req("NFR-207-M1")
def test_the_central_registry_check_actually_detects_one(tmp_path: Path) -> None:
    """위 검사가 **심어 둔 등록부를 실제로 잡는다** (§13.0.1 ④).

    통과만 보고 끝내면 아무것도 검사하지 않는 장치일 수 있다. 특히 서술을
    제외하도록 고친 직후가 위험하다 — 제외 범위를 넓게 잡으면 **코드도 함께
    빠지고**, 그러면 진짜 등록부가 있어도 초록불이 된다.

    서술과 선언이 갈리는 것도 함께 못 박는다. 같은 이름이 주석에 있으면 통과,
    코드에 있으면 검출이어야 한다.
    """
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""자원 등록부 — 이 독스트링에 PV 를 적어도 등록부가 아니다."""\n'
        "# 주석의 ESS 도 등록부가 아니다\n"
        "from core.der.heatpump import HeatPump\n\n"
        'REGISTRY = {"PV": None, "EV_V2G": None, "CEMS": None}\n',
        encoding="utf-8",
    )
    found = _code_names(planted) & (IMPLEMENTED_DER_TAGS | COMMON_ASSET_TAGS)
    assert found == {"PV", "EV_V2G", "CEMS", "HeatPump"}, (
        f"심어 둔 등록부를 잡지 못했습니다: {sorted(found)}. 검출해야 하는 것은 "
        "문자열 키 3건과 import한 클래스 1건이며, 독스트링의 PV·주석의 ESS 는 "
        "서술이므로 세지 않습니다"
    )

    prose_only = tmp_path / "prose_only.py"
    prose_only.write_text(
        '"""PV·ESS·CEMS 를 예로 들어 설명하는 문서다 — 등록부가 아니다."""\n'
        "# HeatPump 도 서술로만 언급한다\n"
        "VALUE = 1\n",
        encoding="utf-8",
    )
    assert not (_code_names(prose_only) & (IMPLEMENTED_DER_TAGS | COMMON_ASSET_TAGS)), (
        "서술을 등록부로 오판합니다 — 이 오판은 검사를 꺼지게 만듭니다"
    )


@pytest.mark.contract
@pytest.mark.req("NFR-208-AC3")
def test_registry_module_does_not_import_any_partition() -> None:
    """발견기가 구획을 import하지 않는다 (NFR-208-AC3).

    **마커를 `NFR-207-M1` 에서 옮겼다 (R15).** `NFR-207-M1` 은 *「신규 자원
    추가 PR 의 diff 에 §16.4 공유 파일 목록의 변경 0줄」* 이고 이 테스트와
    아무 관계가 없다. 이 검사가 보는 것은 `NFR-208-AC3` 문면 그대로다 —
    *「`core/contracts/` 는 어떤 구획도 import 하지 않는 순수 인터페이스·
    타입·단위 정의만 포함한다」*. **독스트링이 처음부터 그렇게 적고 있었다.**

    import-linter가 CI에서 같은 것을 보지만, 여기서 걸리면 **어느 줄이** 원인
    인지 즉시 드러난다. 발견기가 `core.der` 를 알면 계약이 구획을 참조하게 되어
    순환이 생기고, 「모든 구획이 계약을 경유한다」가 형식적으로만 성립한다.
    """
    source = (REPO_ROOT / "core" / "contracts" / "registry.py").read_text(
        encoding="utf-8"
    )
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import core", "from core")):
            assert stripped.startswith(("from core.contracts", "import core.contracts")), (
                f"발견기가 계약 밖 core 모듈을 import합니다: {stripped!r}"
            )


# ── AC2: 등록 충돌은 기동 시점에 터진다 ─────────────────────────────

@pytest.mark.contract
@pytest.mark.req("NFR-207-AC2")
def test_duplicate_tag_is_detected_at_startup(tmp_path: Path) -> None:
    """같은 `tag` 를 두 클래스가 선언하면 **기동 시점 오류**다.

    늦게 발견되면 두 자원 중 어느 것이 계산에 들어갔는지 결과만 보고는 알 수
    없고, 둘 다 그럴듯한 값을 낸다. 오류 메시지가 **양쪽 위치를 모두** 적는
    것도 그래서다 — 한쪽만 알려 주면 어느 것을 고쳐야 하는지 판단할 수 없다.
    """
    pkg = _make_package(tmp_path, "dup_pkg", {
        "alpha.py": _stub_source("Alpha", tag="DUP"),
        "beta.py": _stub_source("Beta", tag="DUP"),
    })

    with pytest.raises(RegistryError, match="등록 충돌") as exc:
        discover(pkg, _StubContract)

    message = str(exc.value)
    assert "alpha" in message and "beta" in message, (
        f"충돌한 양쪽 위치가 메시지에 없습니다: {message}"
    )


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC2")
def test_missing_tag_is_an_error_not_a_silent_skip(tmp_path: Path) -> None:
    """`tag` 미선언은 **오류**다 — 조용히 건너뛰지 않는다.

    건너뛰면 그 자원은 레지스트리에 나타나지 않고, NFR-106(레지스트리를 순회해
    검증 케이스 누락을 검사)이 **그 자원을 아예 보지 않은 채 초록불**이 된다.
    순회 검사가 검사 대상을 잃는 것이므로 누락 하나가 아니라 검사 자체가
    무의미해진다.
    """
    pkg = _make_package(tmp_path, "notag_pkg", {
        "good.py": _stub_source("Good", tag="GOOD"),
        "bad.py": _stub_source("Bad", tag=None),
    })
    with pytest.raises(RegistryError, match="tag"):
        discover(pkg, _StubContract)

    empty = _make_package(tmp_path, "emptytag_pkg", {
        "blank.py": _stub_source("Blank", tag=""),
    })
    with pytest.raises(RegistryError, match="tag"):
        discover(empty, _StubContract)


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC2")
def test_empty_scan_is_an_error_not_an_empty_registry(tmp_path: Path) -> None:
    """구현을 하나도 못 찾으면 오류다.

    빈 레지스트리를 돌려주면 **스캔이 성립하지 않은 것**과 **구현이 없는 것**이
    같은 결과가 된다. 앞의 경우 호출부는 자원이 없는 시나리오를 정상으로
    계산하고, 비용도 편익도 0인 사업이 그럴듯하게 나온다 (§13.0.1 ④).
    """
    pkg = _make_package(tmp_path, "empty_pkg", {"nothing.py": "VALUE = 1\n"})
    with pytest.raises(RegistryError, match="찾지 못했습니다"):
        discover(pkg, _StubContract)


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC1")
def test_private_modules_are_skipped(tmp_path: Path) -> None:
    """`_` 로 시작하는 모듈은 스캔하지 않는다 — 내부 도우미를 두는 자리다."""
    pkg = _make_package(tmp_path, "private_pkg", {
        "real.py": _stub_source("Real", tag="REAL"),
        "_helper.py": _stub_source("Helper", tag="HELPER"),
    })
    assert "_helper" not in load_package_modules(pkg)
    assert set(discover(pkg, _StubContract)) == {"REAL"}


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC1")
def test_adding_a_module_extends_the_registry_with_no_other_edit(tmp_path: Path) -> None:
    """**파일 하나를 더 놓는 것만으로 레지스트리가 늘어난다** (AC1의 실질).

    이것이 「신규 자원 추가 시 공유 목록 파일에 줄을 추가하지 않는다」를 실제로
    보이는 검사다. 위의 M1 검사는 *공유 파일에 이름이 없음* 을 보고, 이 검사는
    *없어도 실제로 늘어남* 을 본다 — 둘 중 하나만으로는 부족하다. 이름이
    없더라도 발견기가 고정 목록을 들고 있으면 늘지 않는다.
    """
    pkg = _make_package(tmp_path, "grow_pkg", {
        "first.py": _stub_source("First", tag="FIRST"),
    })
    assert set(discover(pkg, _StubContract)) == {"FIRST"}

    (Path(pkg.__path__[0]) / "second.py").write_text(
        _stub_source("Second", tag="SECOND"), encoding="utf-8"
    )
    importlib.invalidate_caches()
    assert set(discover(pkg, _StubContract)) == {"FIRST", "SECOND"}, (
        "파일을 추가했는데 레지스트리가 늘지 않았습니다 — 발견기가 어딘가에 "
        "고정 목록을 들고 있습니다"
    )


# ── 스텁 계약 — 실제 자원을 쓰지 않는 이유 ──────────────────────────
#
# 충돌·미선언 케이스를 진짜 `DER` 로 만들면 그 클래스가 `DER.__subclasses__()`
# 에 영구히 남아, **이후 실행되는 `discover(core.der, DER)` 가 오염된다.**
# pytest 는 한 프로세스에서 전 파일을 돌리므로 테스트 순서에 따라 결과가
# 달라지고, 그 불안정은 「가끔 실패하는 테스트」로 나타나 원인을 찾기 어렵다.


class _StubContract:
    """발견 대상 계약의 스텁. `DER` 을 쓰지 않는 이유는 위 주석에 있다."""

    tag: str


def _stub_source(class_name: str, *, tag: str | None) -> str:
    decl = "" if tag is None else f'\n    tag = {tag!r}'
    return (
        "from tests.contract.test_registry import _StubContract\n\n\n"
        f"class {class_name}(_StubContract):{decl or chr(10) + '    pass'}\n"
    )


def _make_package(root: Path, name: str, files: dict[str, str]):
    """임시 패키지를 만들어 import한다.

    실제 파일로 만드는 이유: 발견기가 검사하는 것은 **디렉터리 스캔**이므로,
    모듈 객체를 손으로 조립하면 정작 검사하려던 경로가 실행되지 않는다.
    """
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "__init__.py").write_text(
        f'"""임시 스캔 대상 — {name}."""\n', encoding="utf-8"
    )
    for rel, body in files.items():
        (path / rel).write_text(body, encoding="utf-8")

    import sys

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    for mod in [m for m in sys.modules if m == name or m.startswith(f"{name}.")]:
        del sys.modules[mod]
    return importlib.import_module(name)


@pytest.mark.contract
@pytest.mark.req("NFR-207-AC1")
def test_registry_ignores_classes_whose_file_is_gone() -> None:
    """**파일이 사라진 모듈의 잔존 클래스는 자원이 아니다.**

    `__subclasses__()` 는 클래스 객체가 살아 있는 한 계속 돌려준다. 파일을
    지우고 `sys.modules` 에서 빼도 그 클래스를 참조하는 무언가가 남아 있으면
    레지스트리에 계속 잡힌다.

    08-09 에 실제로 그랬다 — 인수 판정 시험(17.10·17.11)이 임시 자원 파일을
    놓았다 지웠는데 같은 프로세스 안에서 클래스가 살아남아 **자원이 8종인데
    10종으로 세어졌고** 계약 테스트 3건이 깨졌다.

    그 실패는 «시끄러운» 쪽이라 드러났지만 **반대 방향이 더 위험하다** —
    유령 자원이 검증 케이스 없이 등록되면 `NFR-106`(순회 케이스 누락 검사)이
    없는 자원을 검사하려 들거나, 세지 말아야 할 것을 세고 통과한다.
    """
    import core.der
    from core.contracts.der import DER
    from core.contracts.registry import discover

    before = set(discover(core.der, DER))
    ghost = Path(core.der.__path__[0]) / "zz_ghost_probe.py"
    ghost.write_text(
        "from core.contracts.der import DER\n"
        "class GhostProbe(DER):\n"
        "    tag = 'GhostProbe'\n"
        "    def __init__(self) -> None:\n"
        "        super().__init__(name='g', lifetime=1, carries_electric=True)\n"
        "    def capex(self, *, year): return Money(0)\n"
        "    def capex_vat(self, *, year): return Money(0)\n"
        "    def fixed_om(self, *, year): return Money(0)\n"
        "    def variable_om(self, *, year): return Money(0)\n"
        "    def salvage_value(self, *, year): return Money(0)\n"
        "    def replacement_schedule(self): return ()\n"
        "    def dispatch(self, ctx): raise NotImplementedError\n"
        "from core.contracts.units import Money\n",
        encoding="utf-8")
    try:
        importlib.invalidate_caches()
        # ① 양성 — 파일이 있으면 **실제로 는다.** 이것이 없으면 아래 ②의
        #    「줄었다」가 «필터가 동작했다» 인지 «애초에 안 늘었다» 인지
        #    구별되지 않는다.
        with_ghost = set(discover(core.der, DER))
        assert "GhostProbe" in with_ghost, (
            "파일을 놓았는데 레지스트리가 늘지 않았습니다 — 이 시험 자체가 "
            "성립하지 않습니다 (NFR-207-AC1 의 「파일 하나 = 자원 하나」)"
        )
    finally:
        ghost.unlink(missing_ok=True)
        for pyc in (Path(core.der.__path__[0]) / "__pycache__").glob("zz_ghost_probe*"):
            pyc.unlink(missing_ok=True)
        importlib.invalidate_caches()

    # ② 음성 — 파일이 사라지면 **클래스가 아직 살아 있어도** 빠진다.
    #    `sys.modules` 에서 빼지 않았는데도 빠지는 것이 요점이다.
    after = set(discover(core.der, DER))
    assert "GhostProbe" not in after, (
        "파일이 사라졌는데 레지스트리에 남아 있습니다 — `__subclasses__()` "
        "잔존이 유령 자원을 만듭니다"
    )
    assert after == before, f"레지스트리가 원상태로 돌아오지 않았습니다: {after ^ before}"
