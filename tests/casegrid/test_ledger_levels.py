"""수준표를 **대장에서** 만드는가 — NFR-202 · NFR-205.

종전에 이 변환은 `tests/acceptance2/test_17_2_dod2.py` 안에만 있었다. 그래서
*「금액의 정본은 대장이다」* 가 **그 인수 테스트가 도는 동안에만** 성립했고,
러너를 부르는 배포 코드에는 대장을 읽는 자리가 없었다 — R32 가 세 번 만난
「선언은 있는데 읽는 쪽이 없다」의 변형이며, 읽는 쪽이 테스트였으므로 매핑표는
초록불이었다.

이 파일이 붙드는 것은 함수가 아니라 **어디서 값이 오는가**다.

    대장 값이 그대로 온다              ← 사본을 두지 않았다
    `%/년` 은 비율로 환산된다          ← 환산이 호출부에 흩어지지 않는다
    수준표는 읽기 전용이다             ← 병렬 실행이 서로를 바꾸지 않는다 (NFR-205)
    3수준이 없으면 거부한다            ← ±20% 로 조용히 메우지 않는다
    ★ 대장에 할인율이 생기면 빨간불    ← 사본이 남는 유일한 자리를 지킨다
    ★ 설비단가 항목이 축을 잃으면 빨간불 ← 조용히 사라진 스윕 축을 잰다
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.casegrid.ledger_levels import (
    LEVEL_NAMES,
    build_level_map,
    ledger_backed_variables,
    modelling_only_variables,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS_YAML = _REPO_ROOT / "docs" / "assumptions.yaml"


def _ledger_items() -> dict[str, dict]:
    data = yaml.safe_load(_ASSUMPTIONS_YAML.read_text(encoding="utf-8"))
    return {item["key"]: item for item in data["assumptions"]}


@pytest.mark.req("NFR-202-M1")
def test_levels_come_from_the_ledger_not_from_a_copy() -> None:
    """대장 값이 **그대로** 수준표에 온다 — 기대값을 여기 적지 않는다.

    기대 수치를 이 파일에 적으면 그것이 사본이 되고, 대장을 고칠 때 여기가
    따라오지 않아도 아무 일이 없다. 그래서 대장을 **다시 읽어** 대조한다.
    """
    level_map = build_level_map(_ASSUMPTIONS_YAML)
    items = _ledger_items()

    for var_name, ledger_key in ledger_backed_variables().items():
        sensitivity = items[ledger_key]["sensitivity"]
        levels = level_map[var_name]
        assert set(levels) == set(LEVEL_NAMES), (
            f"{var_name}: 3수준 전건이 아니다 — {sorted(levels)}"
        )
        assert levels["low"] < levels["base"] < levels["high"], (
            f"{var_name}: 수준 순서가 무너졌다 — {dict(levels)}"
        )
        # 배율을 여기서 다시 적지 않는다. 비율이 일정한지만 본다.
        #
        # ⚠ **0 인 수준은 비율을 낼 수 없다** — `Q-17`
        # (`capex.replacement_real_trend`)의 `base` 가 0 이고, R42 가 그것을
        # 스윕 축으로 올리며 이 자리를 처음 밟았다(`ZeroDivisionError`).
        # 0 은 어떤 배율을 곱해도 0 이므로 그 수준으로는 「배율이 일정한가」를
        # 물을 수 없다. **0 은 0 으로 오는 것만 확인**하고, 비율은 0 이 아닌
        # 수준끼리 본다 — 확인 못 하는 것을 확인한 척하지 않는다.
        zero_levels = [n for n in LEVEL_NAMES if float(sensitivity[n]) == 0.0]
        for name in zero_levels:
            assert levels[name] == 0.0, (
                f"{var_name}: 대장의 {name} 이 0 인데 수준표가 "
                f"{levels[name]} 을 냈다 — 환산이 0 을 0 이 아닌 것으로 바꿨다"
            )
        ratios = {
            name: levels[name] / float(sensitivity[name])
            for name in LEVEL_NAMES
            if name not in zero_levels
        }
        assert len(set(round(r, 12) for r in ratios.values())) == 1, (
            f"{var_name}: 수준마다 다른 배율이 걸렸다 — {ratios}"
        )


@pytest.mark.req("NFR-202-M1")
def test_percent_per_year_is_converted_once() -> None:
    """`%/년` 항목은 **비율**로 온다 — 환산이 호출부로 새지 않는다.

    새면 호출부마다 `/ 100` 이 흩어지고, 그중 하나가 빠져도 「2.5% 대신
    250%」가 아니라 **그럴듯한 큰 수**가 나온다.
    """
    items = _ledger_items()
    level_map = build_level_map(_ASSUMPTIONS_YAML)

    for var_name, ledger_key in ledger_backed_variables().items():
        unit = items[ledger_key].get("value_unit", "")
        if not unit.startswith("%"):
            continue
        ledger_base = float(items[ledger_key]["sensitivity"]["base"])
        assert level_map[var_name]["base"] == pytest.approx(ledger_base / 100.0), (
            f"{var_name}({ledger_key}): 단위가 {unit!r} 인데 환산되지 않았다"
        )
        assert level_map[var_name]["base"] < 1.0, (
            f"{var_name}: 비율이 1.0 이상이다 — 퍼센트가 그대로 들어왔다"
        )


@pytest.mark.req("NFR-205-M1")
def test_level_map_is_read_only() -> None:
    """수준표를 밖에서 고칠 수 없다 — 케이스 그리드는 병렬로 돈다.

    한 번의 변형이 **다른 케이스의 결과를 조용히 바꾼다**. 읽기 전용으로
    쓰고 있다는 것은 다음 사람도 그럴 것이라는 보장이 아니다.
    """
    level_map = build_level_map(_ASSUMPTIONS_YAML)
    with pytest.raises(TypeError):
        level_map["pv_unit_cost"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        level_map["pv_unit_cost"]["base"] = 1.0  # type: ignore[index]


@pytest.mark.req("NFR-202-M1")
def test_missing_sensitivity_is_refused_not_filled(tmp_path: Path) -> None:
    """3수준이 없으면 **거부한다** — ±20% 로 메우지 않는다.

    메우면 「대장이 3수준을 잃었다」와 「±20% 를 골랐다」가 구별되지 않고,
    그 상태로 27 케이스가 돈다.
    """
    ledger = tmp_path / "assumptions.yaml"
    ledger.write_text(
        "price_basis: 명목\nassumptions:\n"
        '  - key: "capex.pv.rooftop"\n    value: 1\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        build_level_map(ledger)
    message = str(excinfo.value)
    assert "capex.pv.rooftop" in message, "어느 항목인지 말하지 않는다"
    assert "sensitivity" in message, "왜 거부됐는지 말하지 않는다"
    assert "assumptions.yaml" in message, "어디를 고치라는지 말하지 않는다"


@pytest.mark.req("NFR-202-M1")
def test_modelling_parameters_are_not_in_the_ledger() -> None:
    """★ **래칫.** 대장에 할인율 항목이 생기면 이 검사가 빨간불이 된다.

    `discount_rate` 는 지금 대장 항목이 아니므로 `ledger_levels.py` 가 값을
    들고 있다. 대장에 등재되는 날 그 값은 **사본**이 되고, 사본은 한쪽만
    고쳐진다. 그때 아무도 모르는 것이 유일하게 나쁜 결말이므로 여기서 잡는다.
    """
    ledger_keys = set(_ledger_items())
    for var_name in modelling_only_variables():
        suffix = var_name.replace("_", ".")
        offenders = [key for key in ledger_keys if key.endswith(suffix)]
        assert not offenders, (
            f"대장에 {offenders} 가 생겼습니다 — 모형 파라미터 {var_name!r} 의 "
            "값이 이제 사본입니다. core/casegrid/ledger_levels.py 의 "
            "_MODELLING_VARS 에서 그 줄을 지우고 _LEDGER_VARS 로 옮기십시오"
        )


#: **설비 단가 대장 항목 중 스윕 축이 **아닌** 것과 그 사유.**
#:
#: 여기 적히지 않은 `capex.*` 항목은 `_LEDGER_VARS` 에 있어야 한다 — 아래
#: 검사가 그것을 잰다. 사유를 **문자열로 요구하는 것이 요점**이다: 새 항목을
#: 축으로 걸지 않기로 했다면 *왜* 를 한 번은 적게 된다.
#:
#: ⚠ **면제 사유는 전부 「평가 대상 모델에 그 자원이 없다」 한 가지다.**
#: 러너(`core/casegrid/e2e_runner.py`)가 세우는 자원은 `PV`·`ESS`·`Load`
#: 셋뿐이고, 없는 자원의 단가를 흔들면 변동폭 0원이 나와 **「진짜 무영향」과
#: 「미배선」이 구별되지 않는다**(붙임 2 의 `파이프라인 미반영` 표기가 그
#: 구별을 못 한다고 스스로 적는다). 자원이 서는 날 이 목록에서 지운다.
_CAPEX_KEYS_OUTSIDE_THE_SWEEP: dict[str, str] = {
    "capex.pv.bipv_wall": (
        "러너는 옥상 고정형 PV 하나를 세운다 — 벽면 BIPV 변형이 서는 날 축이 된다"
    ),
    "capex.ess.second_life": "러너는 신품 ESS 하나를 세운다 — 재사용 배터리는 별개 변형이다",
    "capex.ev_charger.v2g": (
        "러너에 EV 충전기가 없다 — `Q-8`(제도 존부) 미확인으로 편익도 비활성이다"
    ),
    "capex.heatpump": "러너에 히트펌프가 없다 — 에너지자립가구 변형이 서는 날 축이 된다",
    "capex.modular_house.premium": "러너에 모듈러 주택 증분이 없다 — 모듈러형 변형 전용이다",
}


@pytest.mark.req("NFR-202-M1")
def test_every_capex_ledger_item_is_a_sweep_axis_or_says_why_not() -> None:
    """★ **래칫.** 설비단가 항목이 **스윕 축에서 조용히 빠지면** 빨간불이다.

    ## 무엇이 실제로 일어났는가

    `_LEDGER_VARS` 가 대장 키를 읽지 않으면 그 항목은 **대장에는 보이는데
    흔들리지는 않는** 상태가 된다. 그 상태는 아무 예외도 내지 않고, 리포트
    5.1 은 *그 인자가 애초에 없었던 것처럼* 인쇄된다 — 즉 *「그 값을 골랐다」가
    결론에 얼마를 넣었는지* 를 검토자가 물을 수도 없다.

    실물이 둘 있다. `capex.replacement_real_trend`(`Q-17`)은 R41 이 대장에
    세우고 **R42 가 배선할 때까지 한 라운드 동안** 그 상태였다.
    `capex.pv.inverter_share`(`Q-18`)은 더 오래였다 — 소스 상수
    (`DEFAULT_INVERTER_CAPEX_RATIO`)로 결론에 들어와 있으면서 대장에도
    축에도 없었다.

    ## 왜 「전부 축이어야 한다」가 아닌가

    평가 대상 모델에 없는 자원의 단가는 흔들어도 **변동폭 0원**이고, 그것은
    「진짜 무영향」과 「미배선」을 가르지 못한다(붙임 2 의
    `파이프라인 미반영` 표기가 그 한계를 스스로 적는다). 그래서 면제를
    허용하되 **사유를 적게 한다** — 목록에 없는 새 항목은 둘 중 하나를
    고르지 않으면 통과하지 못한다.
    """
    _assert_prefix_is_swept_or_says_why_not(
        prefix="capex.",
        what="설비단가",
        exemptions=_CAPEX_KEYS_OUTSIDE_THE_SWEEP,
        exemption_name="_CAPEX_KEYS_OUTSIDE_THE_SWEEP",
    )


def _assert_prefix_is_swept_or_says_why_not(
    *,
    prefix: str,
    what: str,
    exemptions: dict[str, str],
    exemption_name: str,
) -> None:
    """대장의 한 접두사 무리가 **전부 스윕 축이거나 사유를 갖는가.**

    ## 왜 함수로 뽑았는가

    같은 판정을 무리마다 베끼면 **사본이 늘고 한쪽만 고쳐진다** — 이 저장소가
    반복해 만난 형태다. 접두사만 다른 네 개의 단정을 두 번 적는 대신 여기서
    한 번 적고, 무리 이름과 면제 목록만 받는다. 실패 메시지가 무리 이름을
    들고 있어야 「어느 표를 고치라는 것인지」가 남는다.
    """
    ledger_keys = set(_ledger_items())
    wired = set(ledger_backed_variables().values())
    keys = {key for key in ledger_keys if key.startswith(prefix)}
    exempt = set(exemptions)

    both = sorted(wired & exempt)
    assert not both, (
        f"{both} 가 스윕 축이면서 동시에 면제 목록에 있습니다 — 한쪽을 "
        "지우십시오. 면제 목록이 낡으면 다음 사람은 그 항목이 축이 아니라고 "
        "읽습니다"
    )

    stale = sorted(exempt - ledger_keys)
    assert not stale, (
        f"면제 목록의 {stale} 가 대장에 없습니다 — 항목이 지워졌거나 키가 "
        "바뀌었습니다. tests/casegrid/test_ledger_levels.py 의 "
        f"{exemption_name} 에서 그 줄을 지우십시오"
    )

    for key, reason in exemptions.items():
        assert reason.strip(), f"{key}: 면제 사유가 비었습니다 — 사유 없는 면제는 면제가 아닙니다"

    missing = sorted(keys - wired - exempt)
    assert not missing, (
        f"{what} 항목 {missing} 가 **스윕 축이 아닙니다.** 대장에는 보이는데 "
        "흔들리지 않으므로 리포트 5.1 영향도 표에 서지 못하고, 그 값을 고른 "
        "것이 결론에 얼마를 넣었는지 검토자가 물을 수 없습니다. "
        "core/casegrid/ledger_levels.py 의 _LEDGER_VARS 에 줄을 더하고 러너가 "
        f"그 값을 읽게 하십시오 — 흔들 수 없는 것이라면 이 파일의 "
        f"{exemption_name} 에 **사유와 함께** 적으십시오"
    )


#: **요금 대장 항목 중 스윕 축이 **아닌** 것과 그 사유** (R43-H).
#:
#: 설비단가 쪽과 같은 형태이나 면제 사유의 성질이 다르다 — 설비단가는
#: *「러너가 그 자원을 세우지 않는다」* 였고, 여기는 *「러너 기본 경로가 정산
#: 구조를 세우지 않는다」* 다. 두 값은 `core/valuestream/settlement.py` 가
#: `provider` 로 **직접** 읽으며(`TARIFF_KEY`·`PPA_RATIO_KEY`), 구조를 준
#: 실행에서만 결론에 들어온다. 그래서 `level_map` 축으로 걸 자리가 없고,
#: 걸어도 기본 경로에서는 변동폭 0원이 나와 **「진짜 무영향」과 「미배선」이
#: 구별되지 않는다.**
#:
#: ⚠ **첨두 기본요금은 이 목록에 없다** — R43-H 에 축이 됐다. 그것이 이
#: 래칫을 세운 이유다: 그 값은 대장에도 축에도 **없이** 결론의 21% 를 정하고
#: 있었고, 어느 검사도 그 상태를 재지 않았다(문의사항 나-8).
_TARIFF_KEYS_OUTSIDE_THE_SWEEP: dict[str, str] = {
    "tariff.hv_single_contract.avg": (
        "러너 기본 경로는 정산 구조를 세우지 않는다 — 이 실효단가는 상계"
        "(`_net_metering`)가 «회피한 요금»으로 읽으며, 구조를 준 실행에서만 "
        "결론에 들어온다"
    ),
    # ⚠ **이 항목은 애초에 축이 될 수 없다** — `track: fixed` 이고
    # `sensitivity` 가 `null` 이라 `build_level_map()` 이 3수준을 찾지 못해
    # 거부한다. 대장 항목 자신이 사유를 적는다: *「정해진 값에 범위를 주면
    # «정해졌다»와 «범위가 있다»가 한 항목에 공존한다」*.
    "tariff.power_fund_rate": (
        "법정 부담금률(`track: fixed`)이며 `sensitivity` 가 없다 — 3수준이 "
        "없으므로 스윕 축이 될 수 없고, 요금 엔진"
        "(`core/regulation/tariff.py`)이 `provider` 로 직접 읽는다"
    ),
    "tariff.aggregated_ppa.ratio": (
        "러너 기본 경로에 집합 PPA 구조가 없다 — `settlement.py` 가 그 구조를 "
        "고른 실행에서만 이 비율을 읽는다"
    ),
}


#: **운영비 대장 항목 중 스윕 축이 아닌 것과 그 사유** (R51/WP-2 신설).
#:
#: 이 이름공간은 지금 막 열렸다(`opex.pv.fixed_om`·`opex.ess.fixed_om` 둘뿐 —
#: R51/WP-2, 사용자 판정 §2). 설비단가 쪽 래칫과 같은 형태다: 러너가 세우지
#: 않는 자원의 운영비를 흔들면 변동폭 0원이 나와 「진짜 무영향」과 「미배선」이
#: 구별되지 않는다.
#:
#: ⚠ **지금은 비어 있다** — 러너가 세우는 자원(`PV`·`ESS`·`Load`)의 고정
#: O&M 둘을 이번에 함께 배선했으므로 면제할 것이 없다. 다음 `opex.*` 항목이
#: 오면(예: 변동 O&M, `status.md` 착수 순서 23번) 이 자리에 사유와 함께 적는다.
_OPEX_KEYS_OUTSIDE_THE_SWEEP: dict[str, str] = {}


@pytest.mark.req("NFR-202-M1")
def test_every_opex_ledger_item_is_a_sweep_axis_or_says_why_not() -> None:
    """★ **래칫.** 운영비 항목이 **축 없이 대장에만 오르면** 빨간불이다.

    `opex.` 이름공간은 R51/WP-2 가 처음 연다. 설비단가·요금 쪽 래칫은
    접두어로 좁혀져 있어 새 이름공간에는 아무 검사도 없었다 — 다음 사람이
    `opex.` 항목을 축 없이 대장에만 올려도 조용히 지나갔을 자리다.
    """
    _assert_prefix_is_swept_or_says_why_not(
        prefix="opex.",
        what="운영비",
        exemptions=_OPEX_KEYS_OUTSIDE_THE_SWEEP,
        exemption_name="_OPEX_KEYS_OUTSIDE_THE_SWEEP",
    )


@pytest.mark.req("NFR-202-M1")
def test_every_tariff_ledger_item_is_a_sweep_axis_or_says_why_not() -> None:
    """★ **래칫.** 요금 단가 항목이 **축 없이 결론에 들어오면** 빨간불이다.

    ## 무엇이 실제로 일어났는가 (문의사항 나-8)

    `tariff.hv_single_contract.demand_charge`(첨두 기본요금 8,320원/kW·월)은
    R43 까지 **대장에도 축에도 없었다.** 그러면서 첨두 절감 편익 199,680원 —
    **전체 편익의 21%** — 을 혼자 정했다. 즉 결론의 5분의 1이 *출처를 말하지
    않는 소스 상수* 위에 서 있었고, 붙임 1 의 어느 행도 그 값의 신뢰도·기준
    연도를 말하지 않았다.

    ⚠ **`check_hardcoded_params` 로는 잡히지 않는 형태다.** 그 검사는 *대장의
    값이 소스에 복제되었는가*를 재므로 **대장에 없는 값은 대조할 상대가
    없다** — 문턱(|값| ≥ 1,000)을 낮춰도 잡히지 않는다. 설비단가 쪽 래칫이
    이 자리를 보지 못한 것도 접두사가 `capex.` 였기 때문이다.

    ⚠ **이 래칫도 그 상태 자체는 못 잡는다** — 대장에 없는 값은 대장을 읽는
    검사에 보이지 않는다. 이것이 붙드는 것은 *올린 뒤에 다시 빠지는 것*과
    *새 요금 항목이 축 없이 들어오는 것*이다.
    """
    _assert_prefix_is_swept_or_says_why_not(
        prefix="tariff.",
        what="요금 단가",
        exemptions=_TARIFF_KEYS_OUTSIDE_THE_SWEEP,
        exemption_name="_TARIFF_KEYS_OUTSIDE_THE_SWEEP",
    )
