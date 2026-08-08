# 정본 표류 감시 — spec §16.5.3 / 작업 목록 3번 (status.md 「지금 할 일」)
#
# **왜 이것이 필요한가.** 볼트의 규칙 노트는 이 저장소 밖에서, 이 프로젝트와
# 무관한 시각에 개정된다. 2026-08-03T15:17:44 에 「근거 표기 기준」이 개정되었고
# **08-08까지 5일간 아무도 몰랐다.** 탐지 장치가 양쪽 다 눈이 멀어 있었다 —
# 로컬 검사는 `DER_VAULT_ROOT` 미설정으로 볼트 대신 저장소 사본을 보고 있었고
# (사본이 오염되지 않았다는 것만 증명한다), CI 는 볼트가 저장소 밖 로컬 경로라
# **구조적으로 접근할 수 없다.**
#
# 그 개정은 위키링크 1줄 추가였고 규범 절은 무변경이었다. **내용이 사소했던 것은
# 운이다.** 다음에 규범 절이 바뀌면 그때도 5일 늦게 안다.
#
# **로그만 남기면 같은 사고가 반복된다.** 아무도 읽지 않는 로그는 탐지 장치가
# 아니다. 그래서 표류를 감지하면 **마커 파일**을 만들고, 정합하면 **지운다** —
# 세션 시작 절차(status.md)가 그 파일의 존재만 보면 되도록 한다. 상태를 「없음」
# 으로 표현하는 이유는 오래된 마커가 남아 매번 거짓 경보를 내는 것을 막기
# 위해서다.
#
# 사용
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\vault_watch.ps1
#   powershell ... -File scripts\vault_watch.ps1 -Register   # 작업 스케줄러 등록
#   powershell ... -File scripts\vault_watch.ps1 -Unregister
#
# 종료 코드는 `check_source_rules.py` 의 것을 그대로 전달한다 — 감시기가 판정을
# 바꾸면 무엇이 판정했는지 알 수 없게 된다.

[CmdletBinding()]
param(
    # 저장소 루트. 비우면 이 스크립트의 상위 디렉터리로 채운다 — 스케줄러는
    # 작업 디렉터리를 상속하지 않으므로 상대 경로에 의존할 수 없다.
    #
    # **param 기본값으로 계산하지 않는다.** Windows PowerShell 5.1 에서는
    # `$PSScriptRoot` 도 `$MyInvocation.MyCommand.Path` 도 param 블록이 평가되는
    # 시점에는 아직 비어 있다. 기본값에 넣으면 스크립트가 파싱 단계에서 죽고,
    # 그 실패는 「검사가 돌지 않는다」로 나타난다 — 감시기에서 가장 나쁜 고장이다.
    [string]$RepoRoot = '',

    # 볼트 경로. 생략하면 `DER_VAULT_ROOT` 를 쓴다. 저장소가 공개되므로 기본값을
    # 코드에 박지 않는다 (SC-3).
    [string]$Vault = $env:DER_VAULT_ROOT,

    # 파이썬 실행 파일. 생략하면 `DER_PYTHON` → PATH 순으로 찾는다.
    #
    # **왜 이것이 파라미터인가.** 작업 스케줄러는 대화형 셸의 PATH 를 물려받지
    # 않는다. conda 환경의 `python` 은 프로파일 훅으로만 PATH 에 들어오는 경우가
    # 많아, 스케줄러 안에서는 «명령을 찾을 수 없음» 이 된다. 처음 등록했을 때
    # 실제로 그랬다 — 작업은 등록되어 있고 매일 돌지만 **아무것도 하지 않았고,
    # 로그조차 남기지 않았다.** 감시기에서 이보다 나쁜 고장은 없다.
    [string]$Python = '',

    [switch]$Register,
    [switch]$Unregister,

    [string]$TaskName = 'DER-evaluator 정본 대조',
    [string]$At = '09:10'
)

$ErrorActionPreference = 'Stop'

# `Write-Error` 를 쓰지 않는다 — `ErrorActionPreference = 'Stop'` 과 만나면
# 그 자리에서 예외를 던져 **뒤의 `exit 2` 에 도달하지 못하고 종료 코드 1** 이
# 된다. 그러면 「검사를 수행하지 못했다(2)」와 「표류를 감지했다(1)」가 같은
# 코드로 나오고, 감시기의 종료 코드 규약이 무너진다. 실제로 한 번 그랬다.
function Write-Fail([string]$Text) {
    [Console]::Error.WriteLine($Text)
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

$stateDir = Join-Path $env:LOCALAPPDATA 'der-evaluator'
$logPath = Join-Path $stateDir 'vault-check.log'
$markerPath = Join-Path $stateDir 'DRIFT-DETECTED.txt'

function Ensure-StateDir {
    if (-not (Test-Path $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }
}

function Resolve-Python([string]$Explicit) {
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) { return $Explicit }
    if (-not [string]::IsNullOrWhiteSpace($env:DER_PYTHON)) { return $env:DER_PYTHON }
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    return ''
}

# 실패를 기록하고 멈춘다. **기록이 먼저다** — 스케줄러 안에서 죽으면 화면이
# 없으므로, 로그와 마커에 남지 않은 실패는 일어나지 않은 것과 같다.
function Stop-WithFailure([string]$Text, [int]$Code) {
    Ensure-StateDir
    Add-Content -Path $logPath -Value "$(Get-Date -Format s)`tERROR`t$Text" -Encoding utf8
    Set-Content -Path $markerPath -Value $Text -Encoding utf8
    Write-Fail $Text
    exit $Code
}

# ── 등록·해제 ────────────────────────────────────────────────────────

if ($Register) {
    $self = Join-Path $PSScriptRoot 'vault_watch.ps1'

    # **등록 시점에 파이썬 경로를 확정해 작업에 박는다.** 스케줄러는 대화형
    # 셸의 PATH 를 물려받지 않으므로 `python` 을 이름으로 부르면 찾지 못한다.
    # 여기서 못 찾으면 등록 자체를 거부한다 — 돌지 않는 감시기를 등록해 두면
    # 「감시하고 있다」는 잘못된 안심만 남는다.
    $py = Resolve-Python $Python
    if ([string]::IsNullOrWhiteSpace($py)) {
        Write-Fail ('파이썬을 찾을 수 없습니다. -Python 으로 경로를 주거나 ' +
                    'DER_PYTHON 을 설정하십시오')
        exit 2
    }

    # **등록 명령은 짧게 유지한다 — `schtasks` 는 긴 `/TR` 을 조용히 자른다.**
    #
    # 처음에는 `-RepoRoot`·`-Python`·`-Vault` 를 전부 인자로 넘겼다. 그러자
    # 명령이 261자에서 잘려 볼트 경로가 `...\faux-va` 가 되었고, 존재하지 않는
    # 경로이므로 검사는 **저장소 사본으로 내려가 종료 코드 0** 을 냈다. 감시기가
    # 「정합」을 보고했지만 정본은 보지도 않은 상태다 — 08-08까지 5일간 있었던
    # 바로 그 상태를, 그것을 막으려고 만든 장치가 재현했다.
    #
    # 그래서 경로는 인자가 아니라 **사용자 환경변수**로 넘긴다. 스케줄러는
    # 레지스트리에서 사용자 환경을 읽으므로 값이 잘리지 않는다. `RepoRoot` 는
    # 스크립트 자신의 위치에서 나온다.
    [Environment]::SetEnvironmentVariable('DER_PYTHON', $py, 'User')
    if (-not [string]::IsNullOrWhiteSpace($Vault)) {
        [Environment]::SetEnvironmentVariable('DER_VAULT_ROOT', $Vault, 'User')
    }
    $argument = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$self`""

    # 매일 한 번으로 충분하다. 2026-08-02 하루에 정본이 세 번 바뀐 적이 있으나
    # 문제는 «몇 번 바뀌었나» 가 아니라 «며칠 늦게 알았나» 였다.
    #
    # `Register-ScheduledTask` 는 이 환경에서 관리자 권한을 요구했다(Access is
    # denied). 사용자 자신의 작업을 만드는 데 승격이 필요한 것은 과하므로
    # `schtasks.exe` 로 물러선다 — 같은 일을 하고 승격 없이 성공한다.
    try {
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
        $triggers = @(
            (New-ScheduledTaskTrigger -Daily -At $At),
            (New-ScheduledTaskTrigger -AtLogOn)
        )
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
            -MultipleInstances IgnoreNew
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
            -Settings $settings -Description (
                'spec §16.5.3 정본 대조. 볼트는 저장소 밖 로컬 경로이므로 CI 가 ' +
                '구조적으로 접근할 수 없다 — 그래서 로컬 스케줄러가 유일한 수단이다.'
            ) -Force -ErrorAction Stop | Out-Null
        Write-Output "등록: $TaskName  (매일 $At + 로그온 시)"
    } catch {
        schtasks /Create /TN $TaskName /TR "powershell.exe $argument" `
            /SC DAILY /ST $At /F | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "작업 등록에 실패했습니다 (schtasks 종료 코드 $LASTEXITCODE)"
            exit 2
        }
        Write-Output "등록: $TaskName  (매일 $At — schtasks 경유, 로그온 트리거 없음)"
    }

    # **등록된 명령을 읽어 대조한다.** 위의 절단은 오류 없이 「SUCCESS」와 함께
    # 일어났다. 등록이 성공했다는 사실은 등록된 것이 의도한 것과 같다는 뜻이
    # 아니다 — 이 저장소가 CODEOWNERS 에서 만난 유형(없는 팀명을 적으면 그 줄이
    # 조용히 무시된다)과 같다.
    $stored = ''
    try {
        $stored = (Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop).Actions[0].Arguments
    } catch {
        Write-Warning "등록된 명령을 읽지 못해 대조를 건너뜁니다: $_"
    }
    if ($stored) {
        # `schtasks` 는 큰따옴표를 벗긴다. 경로에 공백이 없으면 무해하므로
        # 따옴표를 지우고 비교한다 — 그러나 **공백이 있으면 무해하지 않다.**
        # 그때는 인자가 쪼개져 다른 뜻이 되므로 따로 잡는다.
        $norm = { param($s) ($s -replace '"', '') -replace '\s+', ' ' }
        if ($self -match '\s') {
            Write-Fail ("저장소 경로에 공백이 있습니다: $self`n" +
                        '  schtasks 가 따옴표를 벗기므로 인자가 쪼개집니다. ' +
                        '공백 없는 경로로 옮기거나 관리자 권한으로 ' +
                        'Register-ScheduledTask 를 쓰십시오')
            exit 2
        }
        if ((& $norm $stored).Trim() -ne (& $norm $argument).Trim()) {
            Write-Fail ("등록된 명령이 의도와 다릅니다 — 잘렸을 수 있습니다.`n" +
                        "  의도: $argument`n  등록: $stored")
            exit 2
        }
    }

    Write-Output "파이썬: $py"
    Write-Output "로그: $logPath"
    Write-Output "표류 마커: $markerPath"
    exit 0
}

if ($Unregister) {
    schtasks /Delete /TN $TaskName /F | Out-Null
    Write-Output "해제: $TaskName (종료 코드 $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# ── 감시 실행 ────────────────────────────────────────────────────────

Ensure-StateDir

$script = Join-Path $RepoRoot 'scripts\check_source_rules.py'
if (-not (Test-Path $script)) {
    # 검사를 수행하지 못한 것을 통과로 읽지 않는다 (§13.0.1 ④).
    Stop-WithFailure "검사 스크립트를 찾을 수 없습니다: $script" 2
}

if ([string]::IsNullOrWhiteSpace($Vault)) {
    # 볼트 없이 돌면 저장소 사본으로 내려가 **통과가 뜨지만 정본 개정은 원리상
    # 못 본다.** 08-08까지 5일간 그 상태였다. 감시기가 그 상태로 도는 것은
    # 감시하지 않는 것보다 나쁘다 — 초록불이 방심을 만든다.
    Stop-WithFailure ('DER_VAULT_ROOT 가 설정되지 않았습니다. 볼트 없이 대조하면 ' +
        '저장소 사본만 보게 되어 정본 개정을 원리상 감지할 수 없습니다') 2
}

if (-not (Test-Path -LiteralPath $Vault -PathType Container)) {
    # **경로가 «틀린» 것과 «없는» 것을 검사가 구분하지 않는다.** 실재하지 않는
    # 볼트 경로를 주면 `check_source_rules.py` 는 저장소 사본으로 조용히 내려가
    # **종료 코드 0** 을 낸다 — 감시기는 「정합」을 보고하지만 정본은 보지도
    # 않았다. 실제로 등록 명령이 잘려 `...\faux-va` 가 되었을 때 그 상태가 됐다.
    Stop-WithFailure ("볼트 경로가 존재하지 않습니다: $Vault. 이 상태로 대조하면 " +
        '저장소 사본으로 내려가 「정합」이 뜨지만 정본은 보지 않은 것입니다') 2
}

# **파이썬을 이름으로 부르지 않는다.** 스케줄러 환경의 PATH 에는 conda 의
# `python` 이 없을 수 있고, `ErrorActionPreference = 'Stop'` 아래에서 명령을
# 찾지 못하면 여기서 예외가 터져 **아래 로그 기록에 도달하지 못한다.** 처음
# 등록했을 때 실제로 그랬다 — 작업은 「결과 1」로 끝났고 로그는 비어 있었으며,
# 겉보기로는 감시기가 돌고 있었다.
$py = Resolve-Python $Python
if ([string]::IsNullOrWhiteSpace($py)) {
    Stop-WithFailure ('파이썬을 찾을 수 없습니다. -Python 으로 경로를 주거나 ' +
        'DER_PYTHON 을 설정하십시오. 작업 스케줄러는 대화형 셸의 PATH 를 ' +
        '물려받지 않습니다') 2
}

# **콘솔이 없는 환경에서는 파이썬의 출력 인코딩이 UTF-8 이 아니다.** 스케줄러가
# 띄운 프로세스에는 콘솔이 붙지 않고, 그때 파이썬은 시스템 코드페이지(여기서는
# cp949)로 표준출력을 인코딩한다. 이 저장소의 검사 출력은 한국어이므로 그 자리에서
# UnicodeEncodeError 가 나고, `2>&1` 이 그것을 NativeCommandError 로 감싸며,
# `ErrorActionPreference = 'Stop'` 이 그것을 **종료성 오류**로 만든다 — 아래 로그
# 기록에 도달하지 못한다.
#
# 실제로 그랬다. 작업은 「결과 1」로 끝났고 로그는 비어 있었으며, 같은 명령을
# 콘솔에서 직접 돌리면 정상이었다. **콘솔에서 재현되지 않는 고장**이라 원인을
# 찾기 전까지는 감시기가 도는 것처럼 보인다.
$env:PYTHONIOENCODING = 'utf-8'

$output = & {
    # 네이티브 명령의 stderr 는 판정 대상이지 예외가 아니다. 이 호출에 한해
    # 비종료로 내린다 — 전역으로 내리면 위쪽의 실패 처리가 함께 느슨해진다.
    $ErrorActionPreference = 'Continue'
    # `--require-vault` — 볼트 «디렉터리» 가 있어도 그 안에 규칙 노트가 없으면
    # 검사는 저장소 사본으로 내려가 종료 코드 0 을 낸다. 위의 `Test-Path` 는
    # 그것을 잡지 못한다. 감시기는 정본을 읽지 못한 실행을 「정합」으로 보고해서는
    # 안 되므로 여기서 한 겹 더 막는다 (종료 코드 2).
    & $py $script --vault $Vault --require-vault 2>&1 | Out-String
}
$code = $LASTEXITCODE

Add-Content -Path $logPath -Value (
    "$(Get-Date -Format s)`t종료코드 $code`t볼트 $Vault"
) -Encoding utf8

if ($code -eq 0) {
    # 정합하면 마커를 **지운다.** 남겨 두면 오래된 경보가 매번 울려 사람이
    # 무시하게 되고, 무시되는 경보는 없는 것과 같다.
    if (Test-Path $markerPath) { Remove-Item $markerPath -Force }
    Write-Output "정합 — $(Get-Date -Format s)"
} else {
    $detail = @(
        "정본 표류를 감지했습니다 — $(Get-Date -Format s)  (종료 코드 $code)",
        '',
        'spec §16.5.3 절차 3~5를 수행하십시오.',
        '  1. §16.5.1 파생 관계표를 따라 영향 FR 전수 재검토',
        '  2. 정본 어휘 변경 시 DB enum·UI 라벨·테스트 픽스처까지 추적',
        '  3. python scripts/check_source_rules.py --update  후 검토·커밋',
        '  4. 저장소 사본 동기화',
        '',
        $output
    ) -join [Environment]::NewLine
    Set-Content -Path $markerPath -Value $detail -Encoding utf8
    Add-Content -Path $logPath -Value $output -Encoding utf8
    Write-Warning "정본 표류 감지 — $markerPath 를 보십시오"
}

exit $code
