"""check_assumptions.py 음성 테스트 — 감지 능력 확인.

통과만 보고 끝내면 아무것도 검사하지 않는 장치일 수 있다 (spec §13.0.1 ④).
결함을 하나씩 심어 넣고, 그 결함이 실제로 잡히는지 본다.
"""
import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import check_assumptions as ca
import yaml

LEDGER = REPO / "docs/assumptions.yaml"
SPEC = next((REPO / "rslt").glob("spec-*.md"))

base_items = yaml.safe_load(LEDGER.read_text(encoding="utf-8"))["assumptions"]
spec_qs = ca.spec_questions(SPEC)

assert not ca.check(copy.deepcopy(base_items), spec_qs), "기준 상태가 이미 결함"


def find(items, key):
    return next(i for i in items if i.get("key") == key)


CASES = []


def case(name, mutate, expect):
    CASES.append((name, mutate, expect))


# 1 — 검증 정박점에 값을 넣는다 (이 검사기의 존재 이유)
def m1(items):
    find(items, "oracle.prior_demo_assumptions")["value"] = 12345
case("blocked 칸에 값 주입", m1, "blocked")

# 2 — blocked 항목의 blocks 제거 (유예가 조용히 통과로 세어짐)
def m2(items):
    del find(items, "oracle.legacy_excel_model")["blocks"]
case("blocked 인데 blocks 없음", m2, "blocks")

# 3 — 근거 없이 신뢰도를 올린다
#
# ⚠ **R52/WP-6 이 이 사례의 전제를 무너뜨렸다.** 판정 §1(*「어떤 조사를 통해서
# 설정된 값임을 기재」*)에 따라 `capex.pv.rooftop` 에 `source`·`verified_at` 이
# 채워졌고, 그러자 `confidence` 만 「확정」으로 올려도 **결함이 0건**이 되어
# 이 음성 사례가 조용히 미감지로 돌아섰다.
# ★ 대장이 좋아진 것이지 검사가 나빠진 것이 아니다 — 그러므로 **대장 항목의
# 상태에 기대지 말고 「근거 없는 확정」이라는 상태를 이 자리가 직접 세운다.**
# 그러면 다음에 어느 항목의 출처가 채워져도 이 사례는 계속 성립한다.
def m3(items):
    item = find(items, "capex.pv.rooftop")
    item["confidence"] = "확정"
    item["source"] = None
    item["verified_at"] = None
case("source 없이 확정 주장", m3, "source")

# 4 — 폐기된 어휘 (축 1 토큰을 축 2에 사용)
def m4(items):
    find(items, "capex.ess.new")["confidence"] = "미확인"
case("폐기 어휘 미확인", m4, "confidence")

# 5 — 산출 근거를 비운다
def m5(items):
    find(items, "capex.heatpump")["derivation_method"] = ""
case("derivation_method 공란", m5, "derivation_method")

# 6 — 교체 경로를 지운다 (영구 가정이 됨)
def m6(items):
    find(items, "load.household.annual")["replace_when"] = None
case("replace_when 공란", m6, "replace_when")

# 7 — value 와 sensitivity.base 가 어긋난다
def m7(items):
    find(items, "escalation.electricity_tariff")["value"] = 9.9
case("value ↔ base 불일치", m7, "base")

# 8 — 민감도 순서가 뒤집힌다
def m8(items):
    find(items, "capex.ess.new")["sensitivity"] = {"low": 900000, "base": 500000, "high": 100000}
case("sensitivity 순서 역전", m8, "순서")

# 9 — assume 인데 민감도가 없다
def m9(items):
    find(items, "fee.direct_trade_support")["sensitivity"] = None
case("assume 인데 민감도 없음", m9, "sensitivity")

# 10 — 제도 미확인 항목에 크기를 추정해 넣는다
def m10(items):
    find(items, "benefit.v2g_discharge")["value"] = 120
case("default0 에 값 주입", m10, "default0")

# 11 — 부기 필드 자체를 없앤다
def m11(items):
    del find(items, "capex.pv.bipv_wall")["applicable_scope"]
case("부기 7종 필드 결손", m11, "applicable_scope")

# 12 — spec 에 있는 Q 를 대장에서 통째로 뺀다
def m12(items):
    items[:] = [i for i in items if i.get("q_ref") != "Q-7"]
case("spec 의 Q 누락", m12, "Q-7")

# 13 — 존재하지 않는 Q 를 대장에 넣는다
def m13(items):
    ghost = copy.deepcopy(find(items, "capex.heatpump"))
    ghost["q_ref"] = "Q-99"
    ghost["key"] = "ghost.item"
    items.append(ghost)
case("유령 Q", m13, "Q-99")

# 14 — key 중복
def m14(items):
    dup = copy.deepcopy(find(items, "capex.heatpump"))
    items.append(dup)
case("key 중복", m14, "중복")

# 15 — track 오타
def m15(items):
    find(items, "capex.modular_house.premium")["track"] = "assumed"
case("track 오타", m15, "track")


# 16~19 — `fixed` 갈래 (08-08 신설). **대장에서 가장 강한 주장이므로 가장
# 엄하게 본다** — 「정해져 있고 회신을 기다릴 것이 없다」는 뜻이라, 근거 없이
# 이 갈래에 넣으면 가정이 사실로 굳는 가장 빠른 길이 된다.
def m16(items):
    find(items, "tax.vat_rate")["confidence"] = "가정"
case("fixed 인데 신뢰도가 가정", m16, "fixed")

def m17(items):
    find(items, "tax.vat_rate")["sensitivity"] = {"low": 0.08, "base": 0.10, "high": 0.12}
case("fixed 인데 민감도 3수준", m17, "fixed")

def m18(items):
    find(items, "tax.vat_rate")["value"] = None
case("fixed 인데 값 없음", m18, "fixed")

def m19(items):
    it = find(items, "tax.vat_rate")
    it["source"] = None
    it["verified_at"] = None
case("fixed 확정인데 근거 없음", m19, "source")


fails = 0
for name, mutate, expect in CASES:
    items = copy.deepcopy(base_items)
    mutate(items)
    defects = ca.check(items, spec_qs)
    hit = any(expect in d for d in defects)
    mark = "OK  " if hit else "MISS"
    if not hit:
        fails += 1
    print(f"  {mark} {name}")
    if not hit:
        print(f"       기대 키워드 {expect!r} 가 결함 {len(defects)}건 어디에도 없음")
        for d in defects:
            print(f"         · {d}")

print()
print(f"음성 테스트 {len(CASES)}종 — 감지 {len(CASES)-fails} / 미감지 {fails}")
sys.exit(1 if fails else 0)
