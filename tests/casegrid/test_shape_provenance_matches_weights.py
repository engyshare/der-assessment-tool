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
    DailyShape,
    load_daily_shapes,
)

#: 부기가 「0 이 아닌 구간」을 적는 꼴. 두 수만 꺼낸다.
_SPAN = re.compile(r"0 이 아닌 구간은 \*\*인덱스 (\d+)~(\d+)\*\*")
#: 부기가 「최대 위치」를 적는 꼴.
_PEAK = re.compile(r"최대는 인덱스 (\d+)")
#: 부기가 **계절마다** 구간을 적는 꼴 (R60/WP-4). 계절 이름과 두 수를 꺼낸다.
_SEASON_SPAN = re.compile(r"(봄|여름|가을|겨울) 인덱스 (\d+)~(\d+)")

#: 부기의 구간·최대 주장이 겨누는 계절. 자산이 *「기준은 봄·가을 계절 형상」*
#: 이라고 적으므로 그 계절에서 사실을 꺼낸다. 계절을 안 쓰는 자산이면
#: `YEAR_ROUND` 한 계절뿐이라 아래 `_weights_of()` 가 그것을 돌려준다.
_BASELINE_SEASON = "봄"


def _weights_of(shape: DailyShape, name: str) -> tuple[float, ...]:
    """계절 하나의 가중치. **계절이 하나면 그것을 돌려준다.**

    ⚠ `DailyShape.weights` 를 쓰지 않는다 — 계절이 여럿이면 거부하는 것이
    그 속성의 설계이고(조용히 첫 계절을 돌려주면 *「봄만 보고 형상을 읽었다」*
    가 성립한다), 이 검사는 **어느 계절을 보는지 말하고 있으므로** 거부에
    걸릴 이유가 없다.
    """
    if len(shape.by_season) == 1:
        return shape.by_season[0][1]
    for season, weights in shape.by_season:
        if season.name == name:
            return weights
    raise AssertionError(
        f"{shape.key} 에 계절 {name!r} 이 없다 — 부기가 그 이름으로 구간을 "
        f"적고 있는데 자산의 계절은 {[s.name for s in shape.seasons]} 다"
    )


def test_the_generation_provenance_names_the_real_nonzero_span() -> None:
    """★★ 부기가 적은 **0 이 아닌 구간**이 가중치의 실제 구간과 같다."""
    shape = load_daily_shapes().generation
    span = _SPAN.search(shape.derivation_method)
    assert span is not None, (
        f"발전 형상의 부기에 「0 이 아닌 구간」이 없다 ({PROFILE_PATH.name}) — "
        "구간을 적지 않으면 부기와 배열을 맞춰 볼 방법이 없다"
    )
    claimed = (int(span.group(1)), int(span.group(2)))
    weights = _weights_of(shape, _BASELINE_SEASON)
    nonzero = [i for i, w in enumerate(weights) if w != 0.0]
    assert nonzero, "발전 형상이 전 스텝 0 이다"
    actual = (nonzero[0], nonzero[-1])
    assert claimed == actual, (
        f"부기는 인덱스 {claimed[0]}~{claimed[1]} 이라 적었는데 「{_BASELINE_SEASON}」 "
        f"가중치가 0 이 아닌 구간은 {actual[0]}~{actual[1]} 이다 — 부기가 낡았다. "
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
    weights = _weights_of(shape, _BASELINE_SEASON)
    actual = max(range(len(weights)), key=lambda i: weights[i])
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
        assert shape.steps == 24, (
            f"{key} 가 {shape.steps}스텝이다 — 머리말의 「인덱스 0 이 "
            "00~01시」 관례는 24스텝을 전제한다"
        )


def test_the_generation_provenance_names_every_season_span() -> None:
    """★★ 부기가 **계절마다** 적은 0 이 아닌 구간이 그 계절 배열과 같다 (R60/WP-4).

    ## 왜 계절마다 봐야 하는가

    자산이 계절 넷을 선언한 뒤로 「그 형상」은 하나가 아니다. 위 두 검사는
    기준 계절(`_BASELINE_SEASON`) 하나만 보므로, **여름·겨울의 낮 길이를
    부기와 다르게 적어도 초록불**이다 — 그런데 낮 길이 차이가 바로 이 라운드가
    가정으로 세운 것이다(`derivation_method` ⓒ). 그 주장을 배열에서 꺼낸
    사실과 맞춘다.

    ⚠ **여기서도 스텝 값을 옮겨 적지 않는다.** 부기가 적는 것은 **구간**이고
    이 검사가 배열에서 꺼내는 것도 구간이다 — 값은 어느 쪽에도 없다.
    """
    shape = load_daily_shapes().generation
    claimed = {
        name: (int(lo), int(hi))
        for name, lo, hi in _SEASON_SPAN.findall(shape.derivation_method)
    }
    declared = [season.name for season in shape.seasons]
    assert set(claimed) == set(declared), (
        f"부기가 구간을 적은 계절은 {sorted(claimed)} 인데 자산이 선언한 "
        f"계절은 {declared} 다 — 한쪽이 낡았다"
    )
    for name in declared:
        weights = _weights_of(shape, name)
        nonzero = [i for i, w in enumerate(weights) if w != 0.0]
        assert nonzero, f"계절 「{name}」 의 발전 형상이 전 스텝 0 이다"
        actual = (nonzero[0], nonzero[-1])
        assert claimed[name] == actual, (
            f"부기는 「{name}」 을 인덱스 {claimed[name][0]}~{claimed[name][1]} "
            f"이라 적었는데 실제 구간은 {actual[0]}~{actual[1]} 이다"
        )
        assert nonzero == list(range(actual[0], actual[1] + 1)), (
            f"계절 「{name}」 의 0 이 아닌 인덱스가 이어지지 않는다: {nonzero}"
        )


def test_the_daylight_span_is_longest_in_summer_and_shortest_in_winter() -> None:
    """★★ 낮 길이의 **계절 순서**가 자산에 실제로 서 있다 (R60/WP-4).

    위 검사는 *「부기와 배열이 같다」* 만 본다 — 둘을 함께 여름 = 겨울로
    적으면 그대로 통과한다. 이 자산이 가정으로 세운 것은 *「겨울은 낮이 짧고
    여름은 길다」* 이므로 **그 부등호 자체**를 잰다.

    ⚠ **수를 박지 않는다.** 스텝 수가 몇인지가 아니라 **순서**를 재므로,
    낮 길이를 고쳐도 계절성이 살아 있으면 이 검사는 초록불이다.
    """
    shape = load_daily_shapes().generation
    lit = {
        season.name: sum(1 for w in weights if w != 0.0)
        for season, weights in shape.by_season
    }
    assert lit["겨울"] < lit["봄"] <= lit["여름"], (
        f"낮 길이(0 이 아닌 스텝 수)가 겨울 {lit['겨울']} · 봄 {lit['봄']} · "
        f"여름 {lit['여름']} 이다 — 겨울이 가장 짧고 여름이 가장 길어야 한다"
    )
    assert lit["겨울"] < lit["가을"] <= lit["여름"], (
        f"가을 {lit['가을']} 이 겨울 {lit['겨울']}·여름 {lit['여름']} 사이에 "
        "있지 않다"
    )
