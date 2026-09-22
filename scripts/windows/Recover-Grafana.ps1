[CmdletBinding()]
param(
    [switch]$Repair,
    [int]$TimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BackupDirectory = Join-Path $ProjectRoot "backups\grafana"

function Invoke-Docker {
    param([Parameter(Mandatory)] [string[]]$Arguments)

    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& docker @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    $outputText = @($output | ForEach-Object { $_.ToString() })
    if ($exitCode -ne 0) {
        throw "Comando Docker non riuscito: docker $($Arguments -join ' ')`n$outputText"
    }
    return $outputText
}

function Invoke-Compose {
    param([Parameter(Mandatory)] [string[]]$Arguments)

    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& docker compose --project-directory $ProjectRoot @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    $outputText = @($output | ForEach-Object { $_.ToString() })
    if ($exitCode -ne 0) {
        throw "Comando Compose non riuscito: docker compose $($Arguments -join ' ')`n$outputText"
    }
    return $outputText
}

function Invoke-DockerValue {
    param([Parameter(Mandatory)] [string[]]$Arguments)

    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        $output = @(& docker @Arguments 2>$null)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if ($exitCode -ne 0) {
        throw "Comando Docker di diagnostica non riuscito: docker $($Arguments -join ' ')"
    }
    return ([string]::Join("`n", $output)).Trim()
}

function Get-DockerInspectObject {
    param(
        [Parameter(Mandatory)] [ValidateSet("container", "volume")] [string]$Type,
        [Parameter(Mandatory)] [string]$Name
    )

    $arguments = if ($Type -eq "volume") {
        @("volume", "inspect", $Name)
    } else {
        @("inspect", $Name)
    }
    $json = Invoke-DockerValue -Arguments $arguments
    $objects = @($json | ConvertFrom-Json)
    if ($objects.Count -ne 1) {
        throw "Docker ha restituito un risultato inatteso durante l'ispezione di '$Name'."
    }
    return $objects[0]
}

function Get-GrafanaContainerId {
    $containerIds = Invoke-DockerValue -Arguments @(
        "compose", "--project-directory", $ProjectRoot, "ps", "-a", "-q", "grafana"
    )
    $containerId = ($containerIds -split "`n" | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw "Il container Grafana non esiste. Avvia prima lo stack con docker compose up -d."
    }
    return $containerId
}

function Get-GrafanaVolumeName {
    param([Parameter(Mandatory)] [string]$ContainerId)

    $container = Get-DockerInspectObject -Type container -Name $ContainerId
    $mounts = @($container.Mounts | Where-Object {
        $_.Type -eq "volume" -and $_.Destination -eq "/var/lib/grafana"
    })
    if ($mounts.Count -ne 1 -or [string]::IsNullOrWhiteSpace($mounts[0].Name)) {
        throw "Nessun volume nominato e montato su /var/lib/grafana. Operazione annullata."
    }
    $volumeName = $mounts[0].Name

    $volume = Get-DockerInspectObject -Type volume -Name $volumeName
    $composeVolume = $volume.Labels.'com.docker.compose.volume'
    if ($composeVolume -ne "grafana-data") {
        throw "Il volume '$volumeName' non ha l'etichetta Compose grafana-data. Operazione annullata."
    }
    return $volumeName
}

Push-Location $ProjectRoot
try {
    $containerId = Get-GrafanaContainerId
    $volumeName = Get-GrafanaVolumeName -ContainerId $containerId
    $container = Get-DockerInspectObject -Type container -Name $containerId
    $status = $container.State.Status
    $restartCount = $container.RestartCount

    Write-Host "Container Grafana: $containerId"
    Write-Host "Stato: $status; riavvii: $restartCount"
    Write-Host "Volume verificato: $volumeName (etichetta Compose grafana-data)"

    if (-not $Repair) {
        Write-Host "Modalita diagnostica: nessuna modifica eseguita."
        Write-Host "Per creare il backup e ricreare solo Grafana:"
        Write-Host "  .\scripts\windows\Recover-Grafana.ps1 -Repair"
        exit 0
    }

    New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupName = "grafana-data-$timestamp.tar.gz"
    $backupPath = Join-Path $BackupDirectory $backupName

    Write-Host "Arresto del solo servizio Grafana..."
    Invoke-Compose -Arguments @("stop", "grafana") | Out-Host

    Write-Host "Creazione backup $backupPath..."
    Invoke-Docker -Arguments @(
        "run", "--rm", "--user", "0",
        "--mount", "type=volume,src=$volumeName,dst=/data,readonly",
        "--mount", "type=bind,src=$BackupDirectory,dst=/backup",
        "--entrypoint", "sh", "grafana/grafana:13.2.1",
        "-c", "tar -czf /backup/$backupName -C /data ."
    ) | Out-Null

    if (-not (Test-Path -LiteralPath $backupPath) -or (Get-Item $backupPath).Length -eq 0) {
        throw "Il backup non e stato creato correttamente. Il volume originale non verra rimosso."
    }
    $archiveEntries = Invoke-Docker -Arguments @(
        "run", "--rm", "--user", "0",
        "--mount", "type=bind,src=$BackupDirectory,dst=/backup,readonly",
        "--entrypoint", "sh", "grafana/grafana:13.2.1",
        "-c", "tar -tzf /backup/$backupName"
    )
    if (-not ($archiveEntries -match '(^|/)grafana\.db$')) {
        throw "Il backup non contiene grafana.db. Il volume originale non verra rimosso."
    }
    Write-Host "Backup verificato: $backupPath"

    Write-Host "Rimozione del solo container e volume Grafana verificato..."
    Invoke-Compose -Arguments @("rm", "-f", "grafana") | Out-Host
    Invoke-Docker -Arguments @("volume", "rm", $volumeName) | Out-Host

    Write-Host "Ricreazione del solo servizio Grafana..."
    Invoke-Compose -Arguments @("up", "-d", "--no-deps", "grafana") | Out-Host
    $newContainerId = Get-GrafanaContainerId
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 3
        $newContainer = Get-DockerInspectObject -Type container -Name $newContainerId
        $health = if ($null -ne $newContainer.State.Health) {
            $newContainer.State.Health.Status
        } else {
            $newContainer.State.Status
        }
        if ($health -eq "healthy") {
            break
        }
        if ($health -eq "unhealthy" -or (Get-Date) -ge $deadline) {
            $recentLogs = Invoke-Compose -Arguments @("logs", "--tail", "80", "grafana")
            throw "Grafana non e diventato healthy (stato: $health).`n$recentLogs"
        }
    } while ($true)

    $response = Invoke-RestMethod -Uri "http://127.0.0.1:3000/api/health" -TimeoutSec 10
    if ($response.database -ne "ok") {
        throw "L'API health di Grafana non segnala un database operativo."
    }
    Write-Host "Grafana e healthy e il database risponde correttamente."
    Write-Host "Backup conservato in: $backupPath"
} finally {
    Pop-Location
}
