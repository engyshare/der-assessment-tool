# CLAUDE.md — 이 저장소에서 파이썬을 부르는 법

## 인터프리터는 `.venv` 하나다

**모든 파이썬 호출은 저장소의 `.venv` 로 한다.**

```bash
./.venv/Scripts/python.exe -m <module> ...
```

⛔ **시스템·전역 파이썬을 쓰지 마라.** 「`python` 이 PATH 에 있으니 그것으로
돌린다」가 이 저장소에서 실제로 일어났고(2026-09-06), 그러면 **저장소 밖 인터프리터의
패키지 구성을 검증하게 된다.** 다른 기계·CI·Docker 에서는 그 구성이 없다.

- `python` · `py` · `pip` 를 맨 이름으로 부르지 않는다. **항상 `./.venv/Scripts/python.exe -m`** 로 시작한다.
- ⚠ **`PYTHONUTF8=1` 을 걸어라.** 이 저장소의 소스·픽스처·상태 파일이 한글이라, 걸지
  않으면 Windows 기본 코드페이지에서 `UnicodeDecodeError` 가 난다.

### 환경을 채우는 것은 **uv 다** — `pip install` 로 넣지 마라

`.venv` 는 `uv` 가 만든 것이다(`.venv/pyvenv.cfg` 의 `uv = 0.9.18`). 설치자는 uv 이고
`pip` 은 `pip-audit` 이 끌고 들어온 부산물이다. **패키지를 손으로 넣지 말고 그룹째 동기화한다:**

```bash
uv lock                  # pyproject 가 바뀌었으면
uv sync --all-extras     # base + api + persistence + dev + e2e 를 .venv 에 제자리 설치
```

- **`uv.lock` 은 `.gitignore` 안이다** — 의존성 정본은 `pyproject.toml` 하나이고 락은 로컬 부산물이다.
- **`No module named pip` 은 고장이 아니다.** `uv venv` 는 기본적으로 pip 을 넣지 않는다.
  2026-09-06 에 그것을 「`.venv` 가 손상됐다」로 읽은 오진이 있었다. **진짜 증상은
  `import fastapi` 가 실패하는 것**이고, 그때의 원인은 **`uv.lock` 이 `api` · `e2e` 그룹이
  `pyproject.toml` 에 append 되기 전에 만들어진 낡은 락**이었다. 진단은 이 한 줄로 한다:

```bash
uv sync --all-extras --locked --dry-run   # 락이 낡았으면 여기서 말해 준다
```

## 서버 실행

```bash
export PYTHONUTF8=1
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**시나리오 저장을 파일로 남기려면 `DER_SCENARIO_STORE` 를 함께 준다.** 없으면 저장이
인메모리로 동작하고 프로세스가 끝나면 사라진다 — 결함이 아니라 규약이다
(`DER_DB_URL` 이 없으면 DB 가 인메모리가 되는 것과 같다. README 「로컬 실행」 절).

## 서버가 떴는지 확인하는 법 — **`/health` 로는 아무것도 증명되지 않는다**

`/health` 는 의존성이 빠져 있어도 200 을 낸다. 화면 여덟을 전부 때려라.

```bash
for p in / /health /ui/run /ui/scenarios /ui/settings /ui/verify /ui/model-composer /ui/regulation-admin; do
  printf "%-24s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000$p)"
done
```

기동조차 안 될 때는 서버를 띄우기 전에 이것으로 가른다 — **`routes 46`** 이 나와야 한다:

```bash
./.venv/Scripts/python.exe -c "import app.main; print('routes', app.main.app.state.route_count)"
```

### 의존성이 빠지면 **어디서 죽는지가 셋 다 다르다** (2026-09-06 실측)

| 빠진 것 | 증상 | 터지는 자리 |
|---|---|---|
| `sqlalchemy` · `argon2-cffi` | **앱 전체가 기동 실패** | `app/routers/auth.py:9` — 라우터 자동 수집이 모듈을 전부 끌어온다 |
| `jinja2` · `python-multipart` | **앱 전체가 기동 실패** | `Form(...)` 라우트를 세우다 죽는다 (README 경고) |
| `matplotlib` | **`/health` 는 200, `/` 만 500** | `core/report/charts/_render.py:16` ← 차트 레지스트리가 **첫 요청 시점에** import 한다 |

세 번째가 `/health` 를 믿으면 안 되는 이유다. `--selftest` 로도 안 잡힌다.

### **떠 있는 것이 `.venv` 인지 증명하는 법**

`200` 여덟 개는 「또 시스템 파이썬이 떴다」와 구별되지 않는다. 듣고 있는 프로세스를 캔다:

```bash
netstat -ano | grep ":8000 .*LISTENING"          # → PID
```
```powershell
(Get-CimInstance Win32_Process -Filter 'ProcessId=<PID>').CommandLine
```
→ 저장소의 `...\.venv\Scripts\python.exe -m uvicorn ...` 이어야 한다.

⚠ **`ExecutablePath` 를 보지 마라 — venv 가 아니라 base 인터프리터 경로가 나온다.**
`.venv\Scripts\python.exe` 는 uv 의 트램폴린 바이너리라 WMI 가 해석된 base 이미지를
보고한다. **이것을 「시스템 파이썬이 떴다」로 읽으면 오진이다.**

⚠⚠ **`Modules` 도 «그냥 찍으면» 같은 함정이다**(2026-09-07 R65 실측). 앞머리가
**base 인터프리터(miniconda)의 `python.exe` · `python3xx.dll`** 로 나온다 — **적재 모듈
목록은 base 이미지부터 싣기 때문**이다. 그 앞머리만 보고 판정하면 `ExecutablePath` 와
**똑같은 오진**이다. ⇒ **거른 뒤에 본다:**

```powershell
(Get-Process -Id <PID>).Modules | Where-Object { $_.FileName -like '*\.venv\Lib\site-packages\*' }
```

**비어 있지 않아야** 한다(실측: 총 89개 중 `.venv` 밑이 **22개**). 믿을 것은 이것과 `CommandLine` 둘이다.

## 게이트

**게이트를 이어 돌리지 말고 따로, 각각 배경 실행한다.** 겹쳐 돌리면 시간초과가 난다.

⚠ **`pytest` 와 다른 게이트를 겹쳐 돌리지 마라.** 음성 검사가 잠깐 만드는
`core/der/temp_acceptance2_bad_import.py` 를 `ruff` 가 잡아 `rc=1` 이 나는데,
그것은 **위반이 아니라 남의 임시 파일을 본 것**이다.

### ⚠⚠ 게이트 ①(변경분 커버리지)은 **로컬에서 재지 마라 — `pull_request` 에서만 돈다**

`.github/workflows/tests.yml` 실측(2026-09-07): `diff-cover … --fail-under=95` 단계가
**`if: github.event_name == 'pull_request'`** 이고 `push` 에서는 「건너뜀」 단계가 돈다.
**초안 PR 도 `pull_request` 실행이 뜬다** — 밀면 실행이 둘 뜬다.

⇒ ★ **밀고 `gh run list --branch <브랜치>` 로 읽어라.** 로컬 계측은 약 8분이 드는데
**그동안 워커를 띄울 수 없다**(겹치면 1단계가 5분 → **23분 52초**가 되고 저장소 훑기
시험이 남의 임시 파일을 보고 실패한다). CI 로 옮기면 그 8분이 **워커 시간과 겹친다**.

### ⚠⚠⚠ 게이트 ②(테스트 동반 · NFR-105)도 **`pull_request` 에서만 돈다 — 그런데 이것은 로컬에서 «잴 수 있다»**

**2026-09-07 R65 가 실물로 밟았다.** `core/report/sizing.py` 에 배수를 넣고 동반 시험을
안 데려왔는데 **`fast_pytest.sh` 전건이 초록불**이었고 CI 만 빨간불이었다:

```
동반 테스트가 없는 구현 변경 1건 — NFR-105 위반
  · core/report/sizing.py
```

★ **게이트 ①과 달리 이것은 몇 초에 로컬에서 돈다.** ⇒ **`core/` 를 고쳤으면 «커밋한 뒤»
밀기 «전에» 이 한 줄을 돌려라** (⚠ **커밋 전에는 못 잡는다** — 이 검사는 «커밋된 diff»를 본다):

```bash
git fetch origin main
./.venv/Scripts/python.exe scripts/check_test_accompaniment.py --base origin/main
```

인정되는 동반은 둘 — ⓐ 그 모듈을 **`import` 하는** 시험 ⓑ 파일명 규약 `tests/<구획>/test_<모듈>.py`.
⚠ **시험 파일이 「있다」로는 안 된다 — 같은 diff 안에서 «함께 바뀌어야» 한다.**

⚠ 다만 **전체 커버리지 85%(`--cov-fail-under=85`)는 `push` 에서도 돈다.**
⚠ **CI 의 `tests` 잡은 pytest 를 직렬로 부른다 — 그 단계만 26분이다**(로컬 병렬 8분).
기다릴 시간을 그렇게 잡아라.

### 시험을 돌리는 법 — **전건은 마지막 수단이다** (2026-09-06 실측)

**먼저 「무엇을 확인하려는가」를 정한다.** 목적이 무엇이든 전건을 도는 것이 이 저장소가
반복해 밟은 낭비다 — 전건은 **직렬 약 13분 · 병렬 약 8분**이다(2026-09-07 실측 · 2,572건).

| 확인하려는 것 | 도는 것 |
|---|---|
| **결론축이 움직였나 · 움직였으면 «어느 층»인가** | ★ `scripts/verify_ladder.py check --deep` — **14초** |
| 결론축(골든값)이 움직였나 | `pytest tests/golden` (약 23초 · 위 사다리의 독립 증거) |
| 내가 고친 모듈이 깨졌나 | **파일을 지목한** 표적 시험 |
| 저장소 규약을 어겼나 | 정적 게이트 (`ruff`·`mypy`·`lint-imports`·`scripts/check_*`) |
| 아무것도 안 깨졌나 | **CI 가 돈다.** 로컬 전건은 그 중복이다 |

#### ★ 「축이 움직였나」는 **사다리**로 묻는다 — 전건 452초 → **14초** (R64 신설)

```bash
export PYTHONUTF8=1
./.venv/Scripts/python.exe scripts/verify_ladder.py snapshot     # 고치기 «전에» 기준선
./.venv/Scripts/python.exe scripts/verify_ladder.py check --deep # 14초 · L0~L6
```

L0(결론축) → L1(지표·지원율) → L2(현금흐름) → L3(편익·운영비·생애주기) → L4(운전) →
L5(자원·초기투자) → L6(전제 대장). **갈린 «층»을 짚어 주므로 「어디부터 볼지」가 나온다.**
⚠ **화면·계약·회귀는 안 잰다** — 「축이 움직였나」 전용이다.
⚠⚠ **단계 「글자」를 늘린 뒤에는 `snapshot` 을 다시 찍어라** — 안 찍으면 그 층이 계속
「상이」로 나오고, 그것을 결함으로 읽게 된다(R64 가 두 번 겪었다).

⚠⚠ **넓게 돌아야 하면 맨손 `pytest` 가 아니라 `bash .orch/R64/fast_pytest.sh` 다**
(병렬 · 워커 = 코어−4 · `--dist loadfile`). ⛔ **`-n auto` 를 맨손으로 붙이지 마라** —
12코어를 다 먹어 **사람의 터미널이 밀린다**(이 저장소는 사람과 에이전트가 같은 기계를 쓴다).
⛔ `pytest tests/report tests/casegrid tests/web tests/app` 를 **직렬로 돌리지 마라** —
사실상 전건이며 실측 **40분**이었다.

⚠ **`pytest` 에 `-q` 를 겹쳐 주지 마라.** `addopts` 가 이미 `-q` 라 `-qq` 가 되어
**`N passed` 요약 줄이 사라진다.** `rc` 는 옳으므로 **조용히** 판정할 근거를 잃는다.
⚠ **명령에 `| tail` 을 붙이지 마라** — `rc` 가 `tail` 의 것이 된다.

### ⚠⚠ `tests_e2e/` 는 **로컬 전건에 들어가지 않는다**

`[tool.pytest.ini_options]` 의 `testpaths = ["tests"]` 가 그것을 수집하지 않는다.
⇒ **화면(`web/` · `app/`)을 만졌으면 로컬이 초록불이어도 CI 가 빨간불일 수 있다.**
2026-09-06 실측: 그래서 e2e 회귀 둘을 **여섯 커밋 동안 아무도 몰랐다.**

### ⛔⛔ 그렇다고 **로컬에서 `pytest tests_e2e` 전건으로 판정하지 마라** (2026-09-07 실측)

| | 로컬 | **같은 커밋의 CI** |
|---|---|---|
| 결과 | `10 failed, 12 passed` | ★ **`2 failed, 20 passed`** |
| 시간 | **555초** | 333초 |

**차이 여덟은 전부 `Locator.click`·`Page.goto` 의 30초 시간초과**다 — 단언 실패가 0건이다.
**사람과 에이전트가 같은 기계를 쓰기 때문**이며, 혼자 돌려도 시간초과가 난다.
⇒ ★ **e2e 의 판정은 CI 가 한다.** 로컬에서는 **이름을 지목한 시험만** 돌린다:

```bash
export PYTHONUTF8=1
./.venv/Scripts/python.exe -m pytest "tests_e2e/파일.py::시험이름" ...
```

⚠ R64 가 화면 하나의 비용을 **49.85초 → 7.46초**로 줄여(`a475b91`) 그 예산이 나아졌으나,
**로컬 전건이 판정 도구가 되지는 않는다.**

## 하지 말 것

- ⛔ **`pyproject.toml` 을 편집하지 마라.** 명세 §16.4 가 그 파일을 **WP-15 단독 소유·
  append-only** 로 못 박았다. 의존성이 빠져 있다고 판단되면 고치지 말고 **요청**한다.
- ⛔ `docs/traceability.md` 를 **손으로 고치지 마라** (NFR-107). ⚠ 다만 **시험을 더했으면
  생성기를 돌려 그 결과를 커밋해야 한다** — 그 파일은 **시험 목록을 훑어 만들어지므로
  시험이 늘면 낡고, 그러면 CI 의 `source-rules` 가 빨간불이 된다**(2026-09-06 실측:
  여섯 커밋 동안 빨간불이었다). 손편집 금지와 어긋나지 않는다 — CI 오류 문면이 이 조치를
  그대로 지시한다:
  ```bash
  ./.venv/Scripts/python.exe scripts/gen_traceability.py   # 그리고 결과를 커밋한다
  ```
- ⛔ `.venv/` · `.orch/` 는 `.gitignore` 안이다. 커밋에 끌어들이지 않는다.

---

라운드 인계 정본은 **`status.md`** 이고, 그 안의 `## 지금 할 일` 부터 읽는다.
