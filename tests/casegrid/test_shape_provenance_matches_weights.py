"""자산의 **부기가 가중치와 맞는가** — 부기가 낡는 것을 기계가 본다 (R37 후속).

## 왜 이 검사가 필요해졌는가

발전 형상의 `derivation_method` 는 여러 라운드 동안 「일출 06시 · 일몰 19시」라고
적고 있었고 실물 가중치는 인덱스 7~20 이었다 — **일몰 쪽이 두 스텝 어긋났다.**
아무도 잡지 못한 이유는 붙들 자리가 없었기 때문이다: 부기는 사람이 읽는 산문이고
가중치는 배열이라, 둘이 갈려도 어떤 검사도 걸리지 않았다.

R37 이 이 형상을 결론에 배선하면서 **그 부기는 결론의 근거 표기**가 됐다. 즉
낡은 부기는 이제 *「이 순현재가치가 무엇 위에 섰는가」* 를 잘못 안내한다.

## ⚠ 부기를 가중치의 사본으로 만들지 않는다

스텝 값을 부기에 옮겨 적으면 정본이 둘이 되고, 배열을 고칠 때 사본만 낡는다 —
그러면 이 검사는 사본을 사본으로 검산하는 동어반복이 된다. 그래서 부기에는
**구간과 최대 위치만** 적고, 이 검사가 **부기의 그 주장을 배열에서 꺼낸 사실과**
맞춘다. 두 층이 다르다: 주장은 산문, 사실은 `weights` 다.

⚠ **이 검사는 자기 문면에 걸리지 않는다** — 읽는 대상은 YAML 자산이고 이
파일의 소스가 아니다(status.md 「검사 도구를 설명하는 문장이 그 검사에 걸린다」).
"""
from __future__ import annotations

import re

from core.casegrid.profiles import (
    GENERATION_SHAPE_KEY,
    LOAD_SHAPE_KEY,
    PROFILE_PATH,
    load_daily_shapes,
)

#: 부기가 「0 이 아닌 구간」을 적는 꼴. 두 수만 꺼낸다.
_SPAN = re.compile(r"0 이 아닌 구간은 \*\*인덱스 (\d+)~(\d+)\*\*")
#: 부기가 「최대 위치」를 적는 꼴.
_PEAK = re.compile(r"최대는 인덱스 (\d+)")


def test_the_generation_provenance_names_the_real_nonzero_span() -> None:
    """★★ 부기가 적은 **0 이 아닌 구간**이 가중치의 실제 구간과 같다."""
    shape = load_daily_shapes().generation
    span = _SPAN.search(shape.derivation_method)
    assert span is not None, (
        f"발전 형상의 부기에 「0 이 아닌 구간」이 없다 ({PROFILE_PATH.name}) — "
        "구간을 적지 않으면 부기와 배열을 맞춰 볼 방법이 없다"
    )
    claimed = (int(span.group(1)), int(span.group(2)))
    nonzero = [i for i, w in enumerate(shape.weights) if w != 0.0]
    assert nonzero, "발전 형상이 전 스텝 0 이다"
    actual = (nonzero[0], nonzero[-1])
    assert claimed == actual, (
        f"부기는 인덱스 {claimed[0]}~{claimed[1]} 이라 적었는데 가중치가 0 이 "
        f"아닌 구간은 {actual[0]}~{actual[1]} 이다 — 부기가 낡았다. "
        "가중치가 정본이므로 부기를 고칠 것"
    )
    # 구간이 **끊기지 않는가**. 중간에 0 이 섞이면 「구간」이라는 말이 거짓이다.
    assert nonzero == list(range(actual[0], actual[1] + 1)), (
        f"0 이 아닌 인덱스가 이어지지 않는다: {nonzero} — 「구간」으로 적을 수 없다"
    )


def test_the_generation_provenance_names_the_real_peak() -> None:
    """★ 부기가 적은 **최대 위치**가 가중치의 최대와 같다.

    구간만 맞추면 좌우 비대칭(이 형상의 성질)이 드러나지 않는다 — 최대가 구간의
    가운데인지 아닌지가 그 말을 지탱한다.
    """
    shape = load_daily_shapes().generation
    peak = _PEAK.search(shape.derivation_method)
    assert peak is not None, "발전 형상의 부기에 「최대는 인덱스 …」가 없다"
    claimed = int(peak.group(1))
    actual = max(range(len(shape.weights)), key=lambda i: shape.weights[i])
    assert claimed == actual, (
        f"부기는 최대가 인덱스 {claimed} 이라 적었는데 실제 최대는 {actual} 이다"
    )


def test_both_shapes_share_the_index_convention_the_header_declares() -> None:
    """★ 머리말이 선언한 **인덱스 관례**가 두 형상에 함께 성립한다.

    관례가 「인덱스 0 = 00~01시」이므로 24스텝이어야 한다 — 스텝 수가 달라지면
    그 관례 문장이 조용히 거짓이 된다(그리고 붙임 7 의 행 번호와 갈린다).
    """
    text = PROFILE_PATH.read_text(encoding="utf-8")
    assert "인덱스 0 이 00~01시다" in text, (
        f"{PROFILE_PATH.name} 머리말에 인덱스 관례가 없다 — 그것이 없어서 "
        "두 스텝 어긋남이 눈에 띄지 않았다"
    )
    shapes = load_daily_shapes()
    for key, shape in (
        (LOAD_SHAPE_KEY, shapes.load),
        (GENERATION_SHAPE_KEY, shapes.generation),
    ):
        assert len(shape.weights) == 24, (
            f"{key} 가 {len(shape.weights)}스텝이다 — 머리말의 「인덱스 0 이 "
            "00~01시」 관례는 24스텝을 전제한다"
        )
