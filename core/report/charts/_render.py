"""렌더 도우미 — 차트 구현이 공유하는 것만 둔다.

**`_` 로 시작하므로 레지스트리가 스캔하지 않는다** (`load_package_modules` 가
비공개 모듈을 건너뛴다). 자원 패키지에서 쓰던 규약과 같은 자리다.

`pyplot` 을 쓰지 않는 이유: `pyplot` 은 전역 그림 상태를 들고 있어 병렬
케이스 실행(FR-805)에서 그림이 서로 섞이고, 닫지 않으면 누수가 난다.
`Figure` 를 직접 만들면 그 전역이 없다.
"""

from __future__ import annotations

import io
from functools import lru_cache

from matplotlib import font_manager, rc_context
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

#: 한국어 라벨이 두부(□)로 나오지 않도록 쓰는 글꼴 후보. 앞에서부터 실재하는
#: 것을 고른다. **없으면 조용히 기본 글꼴로 간다** — 글꼴 부재로 리포트 생성
#: 자체를 막을 이유는 없고, 그 판단은 사람이 그림을 보면 바로 드러난다.
FONT_CANDIDATES: tuple[str, ...] = (
    "Malgun Gothic",     # Windows
    "AppleGothic",       # macOS
    "NanumGothic",       # Linux 배포판 다수
    "Noto Sans CJK KR",
)


@lru_cache(maxsize=1)
def korean_font() -> str | None:
    """설치돼 있는 한국어 글꼴 이름. 없으면 ``None``.

    `lru_cache` 를 두는 이유는 글꼴 목록 조회가 느리기 때문이다 — 케이스
    그리드는 차트를 수백 번 그린다.
    """
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in FONT_CANDIDATES:
        if name in available:
            return name
    return None


def new_figure(*, width: float = 8.0, height: float = 4.5) -> Figure:
    """축 하나를 가진 그림. 한국어 글꼴이 있으면 적용한다."""
    figure = Figure(figsize=(width, height), dpi=120)
    figure.add_subplot(1, 1, 1)
    font = korean_font()
    if font is not None:
        for text in figure.findobj(match=lambda obj: hasattr(obj, "set_fontfamily")):
            text.set_fontfamily(font)   # type: ignore[attr-defined]
        figure.set_layout_engine("tight")
    return figure


def to_png(figure: Figure, *, font: str | None = None) -> bytes:
    """그림을 PNG 바이트로. **여기서만 바이트가 만들어진다.**

    글꼴은 그림을 다 그린 뒤에 한 번 더 적용한다 — 축 라벨·범례는 `new_figure`
    시점에는 아직 없기 때문이다.
    """
    chosen = font if font is not None else korean_font()
    if chosen is not None:
        for text in figure.findobj(match=lambda obj: hasattr(obj, "set_fontfamily")):
            text.set_fontfamily(chosen)   # type: ignore[attr-defined]
    figure.set_layout_engine("tight")
    canvas = FigureCanvasAgg(figure)
    buffer = io.BytesIO()
    # **음수 눈금을 ASCII 하이픈으로 그린다.** matplotlib 은 기본으로 유니코드
    # 마이너스(U+2212)를 쓰는데 한국어 글꼴 다수가 그 글리프를 갖지 않아
    # 음수 축에 두부(□)가 찍힌다. 누적 현금흐름은 초반이 전부 음수이므로
    # 이 차트에서 가장 먼저 드러나는 자리다.
    #
    # 전역 `rcParams` 를 고치지 않고 문맥으로 두는 이유: 이 저장소는 라이브러리
    # 성격의 모듈이 전역 상태를 바꾸면 호출 순서에 따라 결과가 달라진다는 것을
    # 이미 겪었다 (`pyplot` 전역 그림 상태와 같은 종류).
    with rc_context({"axes.unicode_minus": False}):
        canvas.print_png(buffer)   # type: ignore[no-untyped-call]
    return buffer.getvalue()
