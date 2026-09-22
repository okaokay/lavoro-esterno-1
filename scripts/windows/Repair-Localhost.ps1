[CmdletBinding()]
param(
    [switch]$Repair
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory)] [ValidateSet("4", "6", "auto")] [string]$IpMode,
        [Parameter(Mandatory)] [string]$Url
    )

    $arguments = @(
        "--noproxy", "*", "--max-time", "5", "--silent", "--show-error",
        "--output", "NUL", "--write-out", "%{http_code}"
    )
    if ($IpMode -ne "auto") {
        $arguments += "-$IpMode"
    }
    $arguments += $Url
    $previousErrorPreference = $ErrorActionPreference
    try {
        # Windows PowerShell wraps native stderr in an ErrorRecord when the
        # global preference is Stop. A failed probe is data, not a script
        # failure, so capture only stdout and inspect curl's exit code.
        $ErrorActionPreference = "SilentlyContinue"
        $statusCode = & curl.exe @arguments 2>$null
        $curlExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    return [pscustomobject]@{
        Success = $curlExitCode -eq 0 -and $statusCode -eq "200"
        StatusCode = $statusCode
        ExitCode = $curlExitCode
    }
}

function Get-IPv6Port80Listeners {
    return @(
        Get-NetTCPConnection -State Listen -LocalPort 80 -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalAddress -eq "::1" } |
            Sort-Object OwningProcess -Unique
    )
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$ipv4 = Test-HttpEndpoint -IpMode 4 -Url "http://localhost/"
$ipv6 = Test-HttpEndpoint -IpMode 6 -Url "http://localhost/"
$listeners = @(Get-IPv6Port80Listeners)

Write-Host "IPv4 localhost: status=$($ipv4.StatusCode), success=$($ipv4.Success)"
Write-Host "IPv6 localhost: status=$($ipv6.StatusCode), success=$($ipv6.Success)"

if ($listeners.Count -eq 0) {
    Write-Host "No listener is bound to [::1]:80."
} else {
    foreach ($listener in $listeners) {
        $process = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
        Write-Host (
            "[::1]:80 listener: PID=$($process.Id), " +
            "process=$($process.ProcessName), path=$($process.Path)"
        )
    }
}

if (-not $Repair) {
    Write-Host (
        "Diagnostic mode only. Re-run from elevated PowerShell with -Repair " +
        "to remove a verified stale WSL relay."
    )
    exit 0
}

if (-not (Test-IsAdministrator)) {
    throw "Repair mode requires an elevated PowerShell session."
}
if (-not $ipv4.Success) {
    throw "IPv4 nginx is not healthy; refusing to stop any relay process."
}
if ($ipv6.Success) {
    Write-Host "IPv6 already responds correctly; no repair is required."
    exit 0
}
if ($listeners.Count -eq 0) {
    Write-Host "No stale IPv6 listener was found. localhost should fall back to IPv4."
    exit 0
}

$verifiedPids = @()
foreach ($listener in $listeners) {
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
    $expectedPath = Join-Path $env:ProgramFiles "WSL\wslrelay.exe"
    if ($process.ProcessName -ne "wslrelay" -or $process.Path -ne $expectedPath) {
        throw (
            "PID $($process.Id) is not the expected Windows WSL relay; " +
            "refusing to stop it."
        )
    }
    $verifiedPids += $process.Id
}

foreach ($processId in ($verifiedPids | Sort-Object -Unique)) {
    Write-Host "Stopping verified stale wslrelay PID $processId..."
    Stop-Process -Id $processId -Force -ErrorAction Stop
}

$deadline = (Get-Date).AddSeconds(10)
do {
    Start-Sleep -Milliseconds 250
    $remaining = @(Get-IPv6Port80Listeners)
} while ($remaining.Count -gt 0 -and (Get-Date) -lt $deadline)

if ($remaining.Count -gt 0) {
    throw (
        "The IPv6 relay was recreated. Run 'wsl --shutdown', restart Docker " +
        "Desktop, recreate nginx, then run this diagnostic again."
    )
}

$final = Test-HttpEndpoint -IpMode auto -Url "http://localhost/"
if (-not $final.Success) {
    throw "The stale relay was removed, but localhost still does not return HTTP 200."
}

Write-Host "localhost is healthy and returns HTTP 200 through the IPv4 fallback."
