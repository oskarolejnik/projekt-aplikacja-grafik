<#
  Odkryj schemat bazy Gastro - wariant PowerShell, BEZ Pythona.
  Czyta TYLKO DO ODCZYTU (READ UNCOMMITTED / NOLOCK). Niczego nie zapisuje.
  Konfiguracja: agent_rcp.env obok skryptu (ten sam plik co agent_rcp.ps1,
  uzywa wylacznie RCP_CONNECTION_STRING).

  Uzycie (PowerShell w katalogu agenta):
    powershell -NoProfile -ExecutionPolicy Bypass -File odkryj_schemat.ps1
        -> lista wszystkich tabel + kolumn (kandydaci oznaczeni strzalka)
    powershell -NoProfile -ExecutionPolicy Bypass -File odkryj_schemat.ps1 NGastroNazwaTabeli
        -> kolumny + 5 przykladowych wierszy z tej tabeli
    powershell -NoProfile -ExecutionPolicy Bypass -File odkryj_schemat.ps1 > schemat.txt
        -> pelna lista do pliku (latwo szukac w Notatniku)

  WAZNE: plik w ASCII (bez polskich znakow) - Windows PowerShell 5.1 czyta
  skrypty bez BOM jako ANSI i polskie znaki rozsypaly by parser.
#>
param([string]$Tabela = '')

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
$EnvPath = Join-Path $ScriptDir 'agent_rcp.env'

# Slowa-klucze: tabele mogace trzymac rozliczenia kelnerow / raporty kas.
$Podpowiedzi = @('rozlicz', 'deklar', 'zmiana', 'kasjer', 'utarg', 'platnosc', 'raport', 'kasa', 'fiskal', 'dobow', 'terminal', 'zaliczk')

function Get-Config($path) {
    if (-not (Test-Path $path)) {
        Write-Host "BLAD: brak pliku '$path'. Uruchom w katalogu agenta (tam gdzie agent_rcp.env)."
        exit 2
    }
    $cfg = @{}
    foreach ($raw in Get-Content -Path $path -Encoding UTF8) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
        $idx = $line.IndexOf('=')
        $cfg[$line.Substring(0, $idx).Trim()] = $line.Substring($idx + 1).Trim()
    }
    if (-not $cfg.ContainsKey('RCP_CONNECTION_STRING') -or -not $cfg['RCP_CONNECTION_STRING']) {
        Write-Host 'BLAD: brak RCP_CONNECTION_STRING w agent_rcp.env.'
        exit 2
    }
    return $cfg
}

$cfg = Get-Config $EnvPath
$conn = New-Object System.Data.SqlClient.SqlConnection $cfg.RCP_CONNECTION_STRING
$conn.Open()
$c0 = $conn.CreateCommand()
$c0.CommandText = 'SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED'
[void]$c0.ExecuteNonQuery()

try {
    if ($Tabela) {
        # Ochrona przed wstrzykniecem: tylko litery/cyfry/podkreslenia w nazwie tabeli.
        if ($Tabela -notmatch '^[A-Za-z0-9_]+$') {
            Write-Host 'BLAD: nazwa tabeli moze zawierac tylko litery, cyfry i _.'
            exit 2
        }
        Write-Host ('== Kolumny {0} ==' -f $Tabela)
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = 'SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = @t ORDER BY ORDINAL_POSITION'
        [void]$cmd.Parameters.AddWithValue('@t', $Tabela)
        $r = $cmd.ExecuteReader()
        try { while ($r.Read()) { Write-Host ('  - {0} ({1})' -f $r['COLUMN_NAME'], $r['DATA_TYPE']) } }
        finally { $r.Close() }

        Write-Host ''
        Write-Host ('== 5 przykladowych wierszy z {0} ==' -f $Tabela)
        $cmd2 = $conn.CreateCommand()
        $cmd2.CommandText = ('SELECT TOP 5 * FROM [{0}] WITH (NOLOCK)' -f $Tabela)
        $cmd2.CommandTimeout = 30
        $r2 = $cmd2.ExecuteReader()
        try {
            while ($r2.Read()) {
                $pary = New-Object System.Collections.ArrayList
                for ($i = 0; $i -lt $r2.FieldCount; $i++) {
                    $v = if ($r2.IsDBNull($i)) { 'NULL' } else { [string]$r2.GetValue($i) }
                    [void]$pary.Add(('{0}={1}' -f $r2.GetName($i), $v))
                }
                Write-Host ('  ' + ($pary -join ' | '))
            }
        }
        finally { $r2.Close() }
    }
    else {
        # Pelna lista: tabele/widoki + kolumny (jedno zapytanie o kolumny, grupowanie w pamieci).
        $kolumny = @{}
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = 'SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_NAME, ORDINAL_POSITION'
        $cmd.CommandTimeout = 60
        $r = $cmd.ExecuteReader()
        try {
            while ($r.Read()) {
                $t = [string]$r['TABLE_NAME']
                if (-not $kolumny.ContainsKey($t)) { $kolumny[$t] = New-Object System.Collections.ArrayList }
                [void]$kolumny[$t].Add([string]$r['COLUMN_NAME'])
            }
        }
        finally { $r.Close() }

        Write-Host ('Znaleziono {0} tabel/widokow.' -f $kolumny.Count)
        Write-Host ''
        foreach ($t in ($kolumny.Keys | Sort-Object)) {
            $lower = $t.ToLower()
            $hit = $false
            foreach ($p in $Podpowiedzi) { if ($lower.Contains($p)) { $hit = $true; break } }
            $marker = if ($hit) { '   <-- KANDYDAT (rozliczenia/kasy)' } else { '' }
            Write-Host ('[{0}]{1}' -f $t, $marker)
            Write-Host ('    ' + ($kolumny[$t] -join ', '))
            Write-Host ''
        }
        Write-Host 'Nastepnie: odkryj_schemat.ps1 <NazwaTabeli>  (kolumny + 5 przykladowych wierszy)'
    }
}
finally { $conn.Close() }
