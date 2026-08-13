"""제도 프로파일 웹 편집의 앱 계층 — FR-504-AC3.

조항: *「**admin 권한** 사용자가 **웹 UI** 에서 프로파일을 생성·복제·수정할 수
있다. **파일 수정이나 재배포를 요구하지 않는다**」*

셋으로 갈린다.

    생성·복제·수정   `core/regulation/profile.py` 의 초안 연산 (WP-3 소유)
    admin 권한       `app/security/authorization.py` 의 역할 판정
    파일·재배포 불요  **이 계층이 값을 들고 있는다** — 편집이 파일을 건드리지 않는다

**세 조작이 인가를 여기서 지난다.** 라우터마다 가드를 흩어 두면 네 번째 조작이
생길 때 잊는 자리가 되고, 잊었다는 사실은 «권한 없는 사람이 실제로 눌러 볼 때»
까지 드러나지 않는다. 대신 **거부 사유가 조작 이름을 싣는다** — 그래야 한
경로에서 가드가 빠진 것이 이웃 경로의 같은 메시지에 묻히지 않는다.
"""
from __future__ import annotations

from datetime import date

from app.security.authorization import assert_can_edit_regulation_profile
from core.contracts.regulation import RegulationItem
from core.regulation.profile import (
    DataRegulationProfile,
    ProfileHistory,
    RegulationProfileDraft,
    diff_profiles,
)

#: 조작 이름 — 거부 사유와 감사 로그가 같은 어휘를 쓴다. 조항 문면의 세 낱말이다.
OPERATION_CREATE = "생성"
OPERATION_CLONE = "복제"
OPERATION_UPDATE = "수정"


class RegulationProfileAdminService:
    """제도 프로파일 보관 + admin 편집 (FR-504-AC3).

    **값을 메모리에 든다.** 조항이 금지하는 것은 「파일 수정이나 재배포」이므로
    편집 경로가 파일을 쓰지 않는 것이 요구의 실물이다. 영속화는 `infra/` 의
    몫이며 그때도 **소스 파일이 아니라 저장소**에 쓴다.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, DataRegulationProfile] = {}
        self._history: dict[str, ProfileHistory] = {}

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def get(self, name: str) -> DataRegulationProfile | None:
        return self._profiles.get(name)

    def history(self, name: str) -> ProfileHistory:
        return self._history.get(name, ProfileHistory(()))

    def create(self, *, role: str, name: str, version: str) -> DataRegulationProfile:
        """빈 프로파일 생성 (FR-504-AC3 「생성」)."""
        assert_can_edit_regulation_profile(role=role, operation=OPERATION_CREATE)
        return self._publish(RegulationProfileDraft.create(name=name, version=version))

    def clone(
        self, *, role: str, source_name: str, name: str, version: str
    ) -> DataRegulationProfile:
        """기존 프로파일 복제 (FR-504-AC3 「복제」)."""
        assert_can_edit_regulation_profile(role=role, operation=OPERATION_CLONE)
        source = self._require(source_name)
        draft = RegulationProfileDraft.from_profile(source, version=source.version)
        return self._publish(draft.clone(name=name, version=version))

    def upsert_item(
        self, *, role: str, name: str, item: RegulationItem, version: str
    ) -> DataRegulationProfile:
        """항목 추가·개정 (FR-504-AC3 「수정」 · FR-504-AC2 「스키마 변경 없이」).

        새 버전으로 발행한다 — 제자리에서 고치면 FR-504-AC4 의 「이전 버전으로
        복원」이 성립하지 않는다.
        """
        assert_can_edit_regulation_profile(role=role, operation=OPERATION_UPDATE)
        current = self._require(name)
        draft = RegulationProfileDraft.from_profile(current, version=version)
        return self._publish(draft.upsert(item))

    def changes_since(self, name: str, *, version: str, when: date) -> tuple[str, ...]:
        """이전 버전 대비 바뀐 항목 키 (FR-504-AC4 diff 뷰의 입력)."""
        return diff_profiles(
            self.history(name).restore(version), self._require(name), when=when
        ).changed_keys

    def _publish(self, draft: RegulationProfileDraft) -> DataRegulationProfile:
        published = draft.publish()
        self._profiles[published.name] = published
        self._history[published.name] = self.history(published.name).record(published)
        return published

    def _require(self, name: str) -> DataRegulationProfile:
        profile = self._profiles.get(name)
        if profile is None:
            raise KeyError(f"제도 프로파일이 없습니다: {name!r}")
        return profile
