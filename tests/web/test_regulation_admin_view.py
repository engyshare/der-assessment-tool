"""FR-504-AC3 「웹 UI 에서」의 화면 — 편집 조작이 admin 에게만 있는가.

경로가 admin 을 막아도 화면에 조작이 없으면 조항의 「웹 UI 에서 … 할 수 있다」가
성립하지 않고, 반대로 **누구에게나 버튼을 보여 주면** 조항의 「admin 권한
사용자가」가 화면에서 무의미해진다. 그래서 양성과 음성을 같은 무게로 본다
(`app/security/authorization.py` 가 정한 규율).

**화면이 인가 규칙을 스스로 다시 쓰지 않는지도 본다.** 규칙이 두 곳에 있으면
한쪽만 고쳐지고, 그 어긋남은 권한 없는 사용자가 눌러 볼 때까지 드러나지 않는다.
"""
from __future__ import annotations

from datetime import date
from html.parser import HTMLParser

import pytest

from app.security.authorization import ADMIN_ROLE
from core.contracts.regulation import RegulationItem
from core.regulation.profile import RegulationProfileDraft
from web.render import regulation_admin_context, render_regulation_admin

_WHEN = date(2026, 6, 30)


class _AdminViewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[tuple[str, str]] = []  # (operation, 소속 폼 action)
        self.item_keys: list[str] = []
        self.versions: list[str] = []
        self.denied_roles: list[str] = []
        self._current_action = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._current_action = attributes.get("action", "")
        elif tag == "button":
            self.buttons.append((attributes.get("value", ""), self._current_action))
        elif tag == "tr" and "data-item-key" in attributes:
            self.item_keys.append(attributes["data-item-key"])
        elif tag == "li" and "data-version" in attributes:
            self.versions.append(attributes["data-version"])
        elif "data-denied-role" in attributes:
            self.denied_roles.append(attributes["data-denied-role"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current_action = ""


def _profile():
    return (
        RegulationProfileDraft.create(name="현행", version="v2026.1")
        .upsert(
            RegulationItem(
                key="supply_duty.required_ratio",
                value=0.70,
                unit="비율",
                source="분산법 시행령",
            )
        )
        .publish()
    )


def _render(role: str) -> _AdminViewParser:
    html = render_regulation_admin(
        regulation_admin_context(
            _profile(), role=role, when=_WHEN, versions=("v2026.1",)
        )
    )
    parser = _AdminViewParser()
    parser.feed(html)
    return parser


@pytest.mark.req("FR-504-AC3")
def test_admin_sees_create_clone_and_update_each_on_its_own_path() -> None:
    """admin 화면에 세 조작이 있고 서로 다른 경로를 누른다."""
    parsed = _render(ADMIN_ROLE)

    actions = dict(parsed.buttons)
    for operation in ("create", "clone", "update"):
        assert operation in actions, (
            f"admin 화면에 {operation} 조작이 없다 — 조항의 세 낱말 중 하나가 빠졌다"
        )
    assert len(set(actions.values())) == 3, actions
    assert actions["clone"].endswith(f"/clone?role={ADMIN_ROLE}")
    assert "/items?" in actions["update"]
    assert parsed.denied_roles == [], "admin 에게 권한 없음 안내가 나왔다"


@pytest.mark.req("FR-504-AC3")
def test_non_admin_sees_no_edit_controls_and_is_told_why() -> None:
    """admin 아닌 역할에는 편집 조작이 하나도 없고, 이유가 화면에 적힌다."""
    parsed = _render("viewer")

    assert parsed.buttons == [], (
        f"권한 없는 역할에 편집 조작이 남아 있다: {parsed.buttons}"
    )
    assert parsed.denied_roles == ["viewer"]
    # 읽기는 막지 않는다 — 항목은 그대로 보인다
    assert parsed.item_keys == ["supply_duty.required_ratio"]


@pytest.mark.req("FR-504-AC3")
def test_the_view_and_the_authorization_layer_agree_on_every_role() -> None:
    """화면의 `can_edit` 가 인가 층의 판정과 **같은 답을 낸다** — 역할 넷에서.

    **이 검사가 붙드는 것과 붙들지 못하는 것을 갈라 적는다.** 붙드는 것은
    「두 층이 어긋난 답을 내는 상태」다 — 대소문자만 다른 `"ADMIN"` 이나 빈
    문자열에서 한쪽만 허용하면 걸린다. **붙들지 못하는 것**은 화면이 인가 함수를
    부르는 대신 같은 값을 하드코딩한 경우다(오늘은 두 답이 같으므로 통과한다).
    그 어긋남은 인가 규칙이 바뀌는 시점에 비로소 이 검사로 드러난다 — 그래서
    「인가 층에 물어본다」가 아니라 「같은 답을 낸다」로 적는다.
    """
    from app.security.authorization import can_edit_regulation_profile

    for role in (ADMIN_ROLE, "viewer", "", "ADMIN"):
        context = regulation_admin_context(_profile(), role=role, when=_WHEN)
        expected = can_edit_regulation_profile(role=role, operation="편집").allowed
        assert context["can_edit"] is expected, role


@pytest.mark.req("FR-504-AC3")
def test_the_view_shows_the_revision_history() -> None:
    """개정 이력이 화면에 있다 — 편집이 버전을 낳는다는 것이 보여야 한다."""
    parsed = _render(ADMIN_ROLE)
    assert parsed.versions == ["v2026.1"]
