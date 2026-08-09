from __future__ import annotations

import pytest


@pytest.mark.manual
@pytest.mark.req("NFR-301-M1")
def test_mc2_tutorial_time_manual_stub() -> None:
    """MC-2: 사용자 5명이 튜토리얼 30분 이내 첫 결과 산출 여부를 수행 기록한다."""


@pytest.mark.manual
@pytest.mark.req("NFR-302-M1")
def test_mc3_tooltip_content_manual_stub() -> None:
    """MC-3: 툴팁의 단위·설명·기본값 출처가 필드 의미에 맞는지 사람이 확인한다."""


@pytest.mark.manual
@pytest.mark.req("NFR-303-M1")
def test_mc4_error_message_quality_manual_stub() -> None:
    """MC-4: 오류 메시지가 필드·사유·조치 3요소를 이해 가능하게 설명하는지 확인한다."""


@pytest.mark.manual
@pytest.mark.req("NFR-304-AC1")
def test_mc5_1366_width_manual_stub() -> None:
    """MC-5: 1366x768 주요 화면에서 가로 스크롤과 레이아웃 붕괴가 없는지 확인한다."""


@pytest.mark.manual
@pytest.mark.req("UI-3-AC1")
def test_mc6_assumption_badge_manual_stub() -> None:
    """MC-6: 가정 배지가 노란색과 텍스트·아이콘을 함께 보여 주는지 확인한다."""


@pytest.mark.manual
@pytest.mark.req("UI-5-AC1")
def test_mc7_korean_labels_manual_stub() -> None:
    """MC-7: 한국어 우선 표기이며 영어 병기는 NPV, IRR, LCOE 같은 지표명에 한정되는지 확인한다."""


@pytest.mark.manual
@pytest.mark.req("UI-6-AC1")
def test_mc8_accessibility_manual_stub() -> None:
    """MC-8: axe-core 결과와 키보드 전용 조작 가능 여부를 사람이 수행 기록한다."""

