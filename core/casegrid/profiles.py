"""대표일 **형상**을 읽는다 — `fixtures/profiles/representative-day.yaml`.

## 왜 형상이 따로 있는가

*「형상을 모른다」* 가 아니라 *「형상을 줄 통로를 쓰지 않았다」* 였다:
`PV(generation_profile_kwh=…)` 와 `Load(hourly_kwh=…)` 는 이미 있었다.

✔ **발전 형상은 R37 에 배포 경로가 쓴다.** `build_case_report` 가 본 실행과
스윕에 이 자산을 넘기므로 결론이 일사 곡선 위에 선다 — 붙임 8 의 「일중 발전
프로파일 (평탄)」 행은 그래서 사라졌다. 자산이 없으면 리포트가 **서지 않는다**
(결론의 입력이므로 조용히 이용률로 되돌아가지 않는다).

**부하 형상은 여전히 운전만 그린다** — 아래 ⚠ 가 그 이유다.

## ⚠ 형상은 **총량을 정하지 않는다**

자산이 정하는 것은 하루 안의 배분뿐이다. 총량은 그대로 대장과 설계 변수가
정한다 — 발전은 `pv_capacity_kw × 이용률`, 부하는 대장 `load.household.annual`.
그래서 형상을 바꿔도 **연간 에너지는 변하지 않고 시간대만 옮겨간다.**

## ⚠ **부하** 형상으로는 프로포마를 다시 계산하지 않는다

부하를 편익 계산에 태우면 잉여판매가 줄어드는데, 그 대가인 자가소비 절감은
**배타 규칙 유형 A** 라 같은 프로포마에 함께 실을 수 없다(`FR-402-AC2.A`).
한쪽만 반영하면 **사업에 불리한 쪽으로 틀린다** — NSPM 대칭성이며 양식 4절이
금지하는 것이다. 그래서 부하를 준 실행은 **운전(물리량)만** 다시 그린다.

⚠ **발전 형상은 다르다.** 발전 곡선은 배타 쌍의 한쪽이 아니라 **같은 편익
갈래(잉여판매)의 수량을 옮기는 것**이므로, 반영하면 잉여판매와 계통 구매가
**둘 다** 제 방향으로 움직인다 — 한쪽만 반영하는 상태가 아니다. R37 이 그것을
재어 배선했다(연 −9,855원 · 순현재가치 −128,194원).

## 계절 축 — **R56 이 자리를 세웠고 R60/WP-4 가 가정으로 채웠다**

R56 이전에는 대표일 하나를 365번 되풀이하는 것이 전부여서, *「겨울철 일사가
여름철보다 약하다」* 를 **적을 자리 자체가 없었다.** 이제 `DailyShape` 는
계절 목록(`by_season`)을 갖는다 — 계절마다 **대표일 형상**과 **연간 총량 중
그 계절의 몫**(`Season.share`)을 함께 갖는다.

⚠ **몫이 형상과 따로 필요한 이유.** 형상만 계절별로 두고 총량을 일수에 비례해
나누면 겨울 하루 발전량과 여름 하루 발전량이 **같아진다** — 계절을 넣고도
계절 차이를 표현하지 못한다. 몫이 그 차이를 담는 유일한 자리다.

⚠⚠ **배포 자산은 이제 계절 넷을 선언한다 — 그 값은 「가정」이며 실측이 아니다**
(R60/WP-4 · 사용자 판정 `docs/decisions-2026-09-04-R59b.md` §3). 근거는 자산의
`derivation_method` 가 갖는다. 선언하지 **않으면** 종전대로 계절 하나
(`연중` · 몫 1.0 · 일수는 읽는 쪽이 준 `days` 전부)로 읽히고, 그때 출력은 R56
이전과 **원소 하나까지 같다**(`tests/casegrid/test_seasonal_axis.py` 가 손계산과
대조한다).

⚠⚠⚠ **계절을 채워도 「겨울 하루 < 여름 하루」는 결론에 서지 않는다.** 배포
실행은 24스텝 하루를 돌려 365배로 연간화하므로, 계절이 여럿인 자산은
`representative_day()` 가 내는 **몫 가중 평균 하루** 하나로 접혀 들어간다
(`e2e_runner`). 접지 않고 `spread()` 를 그대로 넘기면 앞 하루가 **첫 계절의
하루**가 되어 연간 총량이 대장과 어긋난다 — R60/WP-4 가 실측한 자리다. 그래서
계절 몫이 담는 차이는 **선언돼 있고 운전에는 서지 않으며**, 그 결손은 붙임 8 이
신고한다(`core/report/unreflected.py`).
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

#: 자산의 자리. 대장(`docs/assumptions.yaml`)이 아니다 — 값이 아니라 형상이라
#: 대장 항목의 꼴(`value` + `sensitivity` 3수준)에 맞지 않는다.
PROFILE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "profiles" / (
    "representative-day.yaml"
)

LOAD_SHAPE_KEY = "shape.load.household.daily"
GENERATION_SHAPE_KEY = "shape.pv.generation.daily"

#: 자산이 계절을 선언하지 않았을 때 세우는 **한 계절의 이름**. 「없다」가 아니라
#: 「연중 하나로 본다」로 적는다 — 없는 것으로 두면 읽는 쪽이 계절 축을 다시
#: 만들어야 하고, 그때 기본 경로와 계절 경로가 두 갈래로 갈린다.
YEAR_ROUND = "연중"

#: `share` 합이 1 인지 재는 허용 오차. 부동소수 누적분만 허용한다.
SHARE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Season:
    """계절 하나의 **달력과 몫** — 형상이 아니라 「언제·얼마나」다.

    `days` 가 `None` 이면 **읽는 쪽이 준 `days` 전부**를 뜻하며, 계절이 하나일
    때만 허용한다(여럿이면 어느 계절이 나머지를 갖는지 말할 수 없다).

    `share` 는 **연간 총량 중 이 계절의 몫**이다. 형상 가중치와 달리 자동
    정규화하지 않는다 — 아래 `DailyShape.__post_init__` 의 ⚠ 를 볼 것.
    """

    name: str
    days: int | None
    share: float


@dataclass(frozen=True)
class DailyShape:
    """한 자원의 형상 — **계절마다** 대표일 하나. 가중치는 합이 1로 정규화된다.

    `by_season` 은 **계절 순서대로** (계절, 그 계절 대표일의 가중치) 짝이며,
    그 순서가 곧 연중 시간 순서다(`spread()` 가 그 차례로 이어 붙인다).
    """

    key: str
    title: str
    confidence: str
    derivation_method: str
    by_season: tuple[tuple[Season, tuple[float, ...]], ...]

    def __post_init__(self) -> None:
        """계절 축이 **말이 되는가**를 세울 때 한 번 잰다.

        ⚠ **`share` 를 자동 정규화하지 않는다.** 정규화하면 「자산이 틀렸다」와
        「이렇게 쓰기로 했다」가 구별되지 않는다. `_normalised()` 가 가중치에는
        정규화를 쓰지만 그것은 *하루 안의 배분*이라 합이 자유롭기 때문이고,
        `share` 는 **연간 총량의 분해**라 합이 1 이어야 한다는 뜻을 갖는다.
        합이 0.9 면 연간 에너지의 10%가 조용히 사라지고, 1.1 이면 없던 에너지가
        생긴다.
        """
        if not self.by_season:
            raise ValueError(f"형상 {self.key!r} 에 계절이 하나도 없습니다")
        steps = {len(weights) for _season, weights in self.by_season}
        if len(steps) != 1:
            raise ValueError(
                f"형상 {self.key!r} 의 계절마다 스텝 수가 다릅니다 "
                f"({sorted(steps)}) — 같은 시간 격자 위에 서야 이어 붙일 수 "
                "있습니다"
            )
        if len(self.by_season) > 1:
            open_ended = [s.name for s, _w in self.by_season if s.days is None]
            if open_ended:
                raise ValueError(
                    f"형상 {self.key!r} 의 계절 {open_ended} 가 일수를 적지 "
                    "않았습니다 — 계절이 여럿일 때 일수 없는 계절이 있으면 "
                    "나머지를 누가 갖는지 말할 수 없습니다"
                )
        # ★ 일수 0 은 「이 계절은 안 쓴다」는 뜻으로 사람이 충분히 적을 수 있다.
        # 그대로 두면 `spread()` 의 나눗셈이 `ZeroDivisionError` 로 죽어, 무엇이
        # 왜 성립하지 않는지 말하지 않는 예외가 나온다. 음수도 같은 자리에서 건다.
        # ⚠ `days is None`(계절 하나 · 열린 일수)은 **그대로 허용한다** — 그것이
        # 기본 경로이며, 막으면 결론축이 움직인다.
        nonpositive = [
            (s.name, s.days) for s, _w in self.by_season
            if s.days is not None and s.days <= 0
        ]
        if nonpositive:
            raise ValueError(
                f"형상 {self.key!r} 의 계절 일수가 양수가 아닙니다 "
                f"{nonpositive} — 하루도 없는 계절에는 몫을 펼 자리가 없어 "
                "그 계절의 에너지가 갈 곳을 잃습니다. 쓰지 않는 계절은 일수를 "
                "0 으로 적지 말고 목록에서 빼십시오"
            )
        share_total = math.fsum(season.share for season, _w in self.by_season)
        if any(season.share < 0.0 for season, _w in self.by_season):
            raise ValueError(f"형상 {self.key!r} 에 음수 몫(`share`)이 있습니다")
        if abs(share_total - 1.0) > SHARE_TOLERANCE:
            raise ValueError(
                f"형상 {self.key!r} 의 계절 몫(`share`) 합이 {share_total!r} "
                "입니다 — 1 이어야 합니다. 1 이 아니면 연간 에너지가 조용히 "
                "사라지거나 없던 것이 생깁니다 (자동 정규화하지 않습니다)"
            )

    @property
    def steps(self) -> int:
        """대표일 한 벌의 스텝 수. 모든 계절에서 같다(`__post_init__`)."""
        return len(self.by_season[0][1])

    @property
    def seasons(self) -> tuple[Season, ...]:
        """계절 목록 — 형상 없이 **달력만** 물을 때."""
        return tuple(season for season, _weights in self.by_season)

    @property
    def weights(self) -> tuple[float, ...]:
        """**계절이 하나일 때만** 그 계절의 가중치.

        ⚠ 계절이 여럿이면 거부한다 — 조용히 첫 계절을 돌려주면 계절을 넣은
        뒤에도 읽는 쪽이 **봄만 보고 「형상을 읽었다」** 가 성립한다.
        """
        if len(self.by_season) != 1:
            names = [season.name for season in self.seasons]
            raise ValueError(
                f"형상 {self.key!r} 의 계절이 {len(names)}개({names})인데 "
                "「그 형상」 하나를 물었습니다 — 어느 계절인지 말해야 합니다. "
                "계절별 가중치는 `by_season` 으로 읽습니다"
            )
        return self.by_season[0][1]

    def _calendar_days(self, days: int) -> tuple[int, ...]:
        """계절별 일수를 확정한다 — **합이 `days` 와 다르면 거부한다.**"""
        declared = [season.days for season, _w in self.by_season]
        if len(declared) == 1 and declared[0] is None:
            return (days,)
        assigned = [int(d) for d in declared if d is not None]
        if sum(assigned) != days:
            raise ValueError(
                f"형상 {self.key!r} 의 계절 일수 합이 {sum(assigned)} 인데 "
                f"연간 일수로 {days} 를 받았습니다 — 달력이 맞지 않으면 "
                "시계열의 길이가 연도와 어긋납니다"
            )
        return tuple(assigned)

    def representative_day(self, total: float, *, days: int) -> tuple[float, ...]:
        """연간 총량을 **몫 가중 평균 하루** 한 벌로 접는다 — `spread()` 의 형제.

        ## 왜 형제가 필요한가 (R60/WP-4-fix)

        `spread()` 는 계절을 **차례로 이어 붙인다** — 그것이 정의이고 연간 총량을
        보존한다. 그런데 **배포 실행은 8,760 을 쓰지 않는다**: 운전은 24스텝
        하루이고(`e2e_runner` 의 `DispatchContext(steps=STEPS_PER_DAY)`), 자원은
        받은 시계열의 **앞 하루만** 잘라 쓴 뒤(`core/der/pv.py` ·
        `core/der/load.py` 의 `[: ctx.steps]`) 그 결과를 365배로 연간화한다.

        그래서 `spread()` 의 출력을 그대로 넘기면 **앞 하루가 「첫 계절의 하루」**
        가 되고, 그것을 365배 한 총량이 대장·설계 변수가 정한 총량과 어긋난다.
        R60/WP-4 가 실측했다 — 발전이 연 +281kWh 생기고 부하가 −315kWh 사라졌다
        (`tests/report/test_shaped_run_invariants.py` 의 두 성질이 그 자리다).
        **첫 계절이 무엇이냐가 결론을 만든다**는 뜻이며, 계절을 적는 차례만 바꿔도
        수가 달라진다.

        ⚠ **그것은 슬라이싱의 결함이 아니다.** *「대표일 하루를 365일로
        연간화한다」* 는 이 저장소의 설계이고 리포트 문면이 그렇게 적는다
        (`e2e_runner` 의 `dispatch_note`). 결함은 **계절이 선 자산에서 「대표일」이
        무엇인지 아무도 말하지 않은 것**이었다. 이 메서드가 그것을 말한다.

        ## 산식과 항등식

            rep[j] = Σ_계절 ( total × share_계절 × weight_계절[j] ) / days

        계절 하나의 하루 총량은 `total × share / 계절일수` 이고 그 계절이
        `계절일수` 만큼 되풀이되므로, 한 해에서 스텝 `j` 가 갖는 에너지는
        `total × share × weight[j]` 다 — **계절일수가 약분된다.** 그것을 `days`
        로 나눈 것이 이 하루이며, 따라서

            Σ_j rep[j] × days == total

        이 항등식으로 성립한다(가중치 합이 계절마다 1 이므로). ⚠ 그 전제는
        **읽는 쪽이 이미 강제한다** — `_normalised()` 가 계절마다 합으로 나눈 뒤에만
        `by_season` 에 담기므로, 이 메서드는 그 성질 위에 서 있다.

        ⚠ **계절이 하나(`연중`)면 `spread()` 의 앞 하루와 원소 하나까지 같다** —
        `share` 가 1 이므로 `rep[j] = total × weight[j] / days` 이고, 그것이
        `spread()` 가 `per_day = total / days` 로 내는 첫 하루다. 계절 축이 서기
        전과 같은 수라는 성질은 `spread()` 독스트링이 적은 것과 같은 자리다.

        ⚠⚠ **이 하루는 계절 간 차이를 담지 못한다** — 담는 것이 목적이 아니다.
        「겨울 하루 < 여름 하루」를 운전에 세우려면 계절마다 대표일을 돌려 합산해야
        하고, 그것은 이 자료형이 아니라 **러너의 구조**다. 그 결손은 붙임 8 이
        신고한다(`core/report/unreflected.py::_season_reason`).
        """
        # ⚠ **연산 차례가 `spread()` 와 같아야 한다.** `total × share ÷ days` 를
        # 먼저 짓고 가중치를 곱한다 — `spread()` 의 `per_day` 와 **같은 식**이며,
        # 계절이 하나일 때 `days == 계절일수` 이므로 두 결과가 부동소수 마지막
        # 자리까지 같아진다. 묶는 차례를 바꾸면(`Σ(total × share × w) ÷ days`)
        # 값이 1 ULP 어긋나고, 그러면 위 ⚠ 의 「원소 하나까지 같다」가 거짓이 된다.
        steps = self.steps
        return tuple(
            math.fsum(
                total * season.share / days * weights[j]
                for season, weights in self.by_season
            )
            for j in range(steps)
        )

    def spread_over_representative_day(self, total: float, *, days: int) -> list[float]:
        """`representative_day()` 를 `days` 일 되풀이한 연간 시계열.

        길이와 합이 `spread()` 와 **같다**(연간 스텝 수 · 연간 총량). 다른 것은
        **하루하루가 전부 같다**는 것뿐이다 — 그래서 앞 하루를 잘라 쓰는 소비자가
        365배 했을 때 총량이 되돌아온다.

        ⚠ **길이를 하루로 줄이지 않는다.** 자원은 `[: ctx.steps]` 로 앞을 집을
        뿐이지만, 길이는 `PV._resolve_generation` 의 `DV-4` 검증(연간 스텝 수)이
        보는 값이다 — 줄이면 그 검증이 거부한다.
        """
        day = self.representative_day(total, days=days)
        return [value for _day in range(days) for value in day]

    def spread(self, total: float, *, days: int) -> list[float]:
        """연간 총량을 **계절 차례로** 스텝별로 편다.

        계절마다 `계절총량 = total × share` → `per_day = 계절총량 / 계절일수`
        → 그 계절의 가중치를 계절일수만큼 되풀이한다. 계절이 하나(`연중`)이고
        일수가 열려 있으면 `per_day = total / days` 이므로 **계절 축이 서기
        전과 원소 하나까지 같다.**

        ⚠ 여기서 총량을 만들지 않는다 — 받은 총량을 배분할 뿐이다. 형상이
        총량까지 정하면 대장을 고쳐도 그 값이 따라오지 않는다.
        """
        calendar = self._calendar_days(days)
        spread: list[float] = []
        for (season, weights), season_days in zip(self.by_season, calendar, strict=True):
            per_day = total * season.share / season_days
            spread.extend(
                per_day * weight
                for _day in range(season_days)
                for weight in weights
            )
        return spread


@dataclass(frozen=True)
class DailyShapes:
    """읽는 쪽이 받는 한 벌."""

    load: DailyShape
    generation: DailyShape


def _normalised(raw: list[float], *, key: str) -> tuple[float, ...]:
    if not raw:
        raise ValueError(f"형상 {key!r} 의 가중치가 비어 있습니다")
    if any(weight < 0.0 for weight in raw):
        raise ValueError(f"형상 {key!r} 에 음수 가중치가 있습니다")
    total = math.fsum(raw)
    if total <= 0.0:
        raise ValueError(
            f"형상 {key!r} 의 가중치 합이 0 입니다 — 배분할 곳이 없어 "
            "그 자원의 에너지가 통째로 사라집니다"
        )
    return tuple(weight / total for weight in raw)


def _by_season_from(item: Mapping[str, Any], *, key: str) -> tuple[
    tuple[Season, tuple[float, ...]], ...
]:
    """자산 항목 하나에서 계절 축을 세운다.

    `seasons:` 가 **있을 때만** 계절을 세우고, 없으면 항목의 `weights:` 를
    읽어 `YEAR_ROUND` 한 계절로 세운다.

    ⚠ **둘 다 준 항목은 거부한다** — 어느 쪽이 정본인지 말하지 않은 것이고,
    둘 다 받으면 하나가 조용히 무시된다.
    """
    raw_seasons = item.get("seasons")
    raw_weights = item.get("weights")
    if raw_seasons is not None and raw_weights is not None:
        raise ValueError(
            f"형상 {key!r} 이 `seasons:` 와 `weights:` 를 둘 다 갖습니다 — "
            "어느 쪽이 정본인지 말하지 않았습니다. 계절을 쓰려면 항목 수준의 "
            "`weights:` 를 지우십시오"
        )
    if raw_seasons is None:
        if raw_weights is None:
            raise ValueError(
                f"형상 {key!r} 에 `weights:` 도 `seasons:` 도 없습니다"
            )
        weights = _normalised([float(w) for w in raw_weights], key=key)
        return ((Season(name=YEAR_ROUND, days=None, share=1.0), weights),)
    built: list[tuple[Season, tuple[float, ...]]] = []
    for entry in raw_seasons:
        name = str(entry["name"])
        days = entry.get("days")
        built.append((
            Season(
                name=name,
                days=None if days is None else int(days),
                share=float(entry["share"]),
            ),
            _normalised([float(w) for w in entry["weights"]], key=f"{key}/{name}"),
        ))
    return tuple(built)


def _calendar_of(shape: DailyShape) -> tuple[tuple[str, int | None], ...]:
    """두 자원이 **같은 달력 위에 서는가**를 볼 때 대조하는 꼴."""
    return tuple((season.name, season.days) for season in shape.seasons)


def load_daily_shapes(path: Path | None = None) -> DailyShapes:
    """자산을 읽어 정규화한다. **없으면 메우지 않고 거부한다.**"""
    source = path or PROFILE_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    by_key = {item["key"]: item for item in data.get("profiles", [])}

    def one(key: str) -> DailyShape:
        item = by_key.get(key)
        if item is None:
            raise ValueError(
                f"형상 자산에 {key!r} 이(가) 없습니다 ({source}). "
                "기본 형상으로 메우지 않습니다 — 메우면 「자산이 비었다」와 "
                "「이 형상을 골랐다」가 구별되지 않습니다"
            )
        return DailyShape(
            key=key,
            title=str(item["title"]),
            confidence=str(item["confidence"]),
            derivation_method=str(item["derivation_method"]).strip(),
            by_season=_by_season_from(item, key=key),
        )

    load = one(LOAD_SHAPE_KEY)
    generation = one(GENERATION_SHAPE_KEY)
    if load.steps != generation.steps:
        raise ValueError(
            f"두 형상의 스텝 수가 다릅니다 — 부하 {load.steps} · "
            f"발전 {generation.steps}. 같은 대표일을 그려야 합니다"
        )
    # ★ 계절 달력이 다르면 **같은 인덱스가 서로 다른 날을 가리킨다** — 스텝
    # 수가 다를 때 거부하는 것과 같은 이유이며, 이쪽이 더 조용하다(길이는
    # 맞은 채로 어긋나므로 아무 검사도 걸리지 않는다).
    if _calendar_of(load) != _calendar_of(generation):
        raise ValueError(
            f"두 형상의 계절 달력이 다릅니다 — 부하 {_calendar_of(load)} · "
            f"발전 {_calendar_of(generation)}. 이름과 일수가 같아야 두 "
            "시계열의 같은 인덱스가 같은 날을 가리킵니다"
        )
    return DailyShapes(load=load, generation=generation)
