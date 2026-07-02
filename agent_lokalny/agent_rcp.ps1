<#
  Agent RCP (PowerShell) - wariant BEZ Pythona.

  Dziala na serwerze Gastro LSI (Windows). Czyta odbicia z bazy RCP TYLKO DO ODCZYTU
  (READ UNCOMMITTED / NOLOCK) i WYPYCHA je na VPS po HTTPS. VPS nigdy nie laczy sie tutaj.

  Bezpieczenstwo:
    - Konto SQL/Windows musi miec TYLKO ODCZYT (db_datareader). Tylko SELECT.
    - READ UNCOMMITTED - brak blokad wspoldzielonych na tabelach Gastro.
    - Waskie okno dni (OKNO_DNI) - zapytanie lekkie.
    - Petla odporna: blad bazy/sieci nie wywala agenta, probuje w kolejnym cyklu.

  Konfiguracja: plik agent_rcp.env obok skryptu (patrz agent_rcp.env.example).
  Wymaga tylko wbudowanych komponentow Windows (PowerShell + .NET, System.Data.SqlClient).

  Uruchomienie reczne (test):
    powershell -NoProfile -ExecutionPolicy Bypass -File agent_rcp.ps1

  WAZNE: plik trzymaj w ASCII (bez polskich znakow). Windows PowerShell 5.1 czyta skrypty
  bez BOM jako ANSI - polskie znaki w kodzie rozsypia parser.
#>

$ErrorActionPreference = 'Stop'
# Starsze Windows domyslnie uzywaja TLS1.0 - wymus 1.2 dla HTTPS do VPS.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ScriptDir = $PSScriptRoot
$EnvPath = Join-Path $ScriptDir 'agent_rcp.env'
$LogPath = Join-Path $ScriptDir 'agent_rcp.log'
$Inv = [System.Globalization.CultureInfo]::InvariantCulture

function Write-Log($msg) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    try { Add-Content -Path $LogPath -Value $line -Encoding UTF8 } catch {}
}

function Get-Config($path) {
    if (-not (Test-Path $path)) {
        Write-Log "BLAD: brak pliku konfiguracji '$path'. Skopiuj agent_rcp.env.example -> agent_rcp.env i uzupelnij."
        exit 2
    }
    $cfg = @{}
    foreach ($raw in Get-Content -Path $path -Encoding UTF8) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
        $idx = $line.IndexOf('=')           # split tylko na PIERWSZYM '=' (SQL zawiera '=')
        $cfg[$line.Substring(0, $idx).Trim()] = $line.Substring($idx + 1).Trim()
    }
    foreach ($req in 'RCP_CONNECTION_STRING', 'RCP_SQL', 'VPS_INGEST_URL', 'RCP_INGEST_TOKEN') {
        if (-not $cfg.ContainsKey($req) -or -not $cfg[$req]) {
            Write-Log "BLAD: brak wymaganego klucza w agent_rcp.env: $req"
            exit 2
        }
    }
    return $cfg
}

function Get-Odbicia($cfg, [datetime]$start, [datetime]$end) {
    $odbicia = New-Object System.Collections.ArrayList
    $conn = New-Object System.Data.SqlClient.SqlConnection $cfg.RCP_CONNECTION_STRING
    try {
        $conn.Open()
        $c0 = $conn.CreateCommand()
        $c0.CommandText = 'SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED'
        [void]$c0.ExecuteNonQuery()

        $timeout = 30
        if ($cfg.ContainsKey('QUERY_TIMEOUT') -and $cfg['QUERY_TIMEOUT']) { $timeout = [int]$cfg['QUERY_TIMEOUT'] }
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $cfg.RCP_SQL
        $cmd.CommandTimeout = $timeout
        $ps = $cmd.Parameters.Add('@start', [System.Data.SqlDbType]::Date); $ps.Value = $start.Date
        $pe = $cmd.Parameters.Add('@end', [System.Data.SqlDbType]::Date);   $pe.Value = $end.Date

        $r = $cmd.ExecuteReader()
        try {
            while ($r.Read()) {
                $wej = if ($r['wejscie'] -is [DBNull]) { $null } else { ([datetime]$r['wejscie']).ToString('yyyy-MM-ddTHH:mm:ss', $Inv) }
                $wyj = if ($r['wyjscie'] -is [DBNull]) { $null } else { ([datetime]$r['wyjscie']).ToString('yyyy-MM-ddTHH:mm:ss', $Inv) }
                [void]$odbicia.Add([ordered]@{
                        rcp_id        = [string]$r['rcp_id']
                        imie_nazwisko = ([string]$r['imie_nazwisko']).Trim()
                        data          = ([datetime]$r['data']).ToString('yyyy-MM-dd', $Inv)
                        wejscie       = $wej
                        wyjscie       = $wyj
                    })
            }
        }
        finally { $r.Close() }
    }
    finally { $conn.Close() }
    return $odbicia
}

function Send-ToVps($cfg, $odbicia) {
    $payload = @{ odbicia = @($odbicia) } | ConvertTo-Json -Depth 6
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)   # UTF-8: poprawne polskie znaki w nazwiskach
    return Invoke-RestMethod -Uri $cfg.VPS_INGEST_URL -Method Post `
        -Headers @{ 'X-RCP-Token' = $cfg.RCP_INGEST_TOKEN } `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 30
}

# -- STOLY (opcjonalne, OSOBNA sciezka - RCP nietkniete) -----------------------
function Get-Stoly($cfg) {
    $out = New-Object System.Collections.ArrayList
    $conn = New-Object System.Data.SqlClient.SqlConnection $cfg.RCP_CONNECTION_STRING
    try {
        $conn.Open()
        $c0 = $conn.CreateCommand()
        $c0.CommandText = 'SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED'
        [void]$c0.ExecuteNonQuery()
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $cfg.STOLY_SQL
        $cmd.CommandTimeout = 30
        $r = $cmd.ExecuteReader()
        try {
            while ($r.Read()) {
                [void]$out.Add([ordered]@{ rewir_nr = [int]$r['rewir_nr']; otwarte = [int]$r['otwarte'] })
            }
        }
        finally { $r.Close() }
    }
    finally { $conn.Close() }
    return $out
}

function Send-Stoly($cfg, $stoly) {
    $payload = @{ stoly = @($stoly) } | ConvertTo-Json -Depth 5
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    return Invoke-RestMethod -Uri $cfg.VPS_STOLY_URL -Method Post `
        -Headers @{ 'X-RCP-Token' = $cfg.RCP_INGEST_TOKEN } `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 30
}

# -- STOLY HISTORIA (liczba stolikow / dzien, 30 dni - OSOBNA sciezka) ----------
function Get-StolyHistoria($cfg) {
    $out = New-Object System.Collections.ArrayList
    $conn = New-Object System.Data.SqlClient.SqlConnection $cfg.RCP_CONNECTION_STRING
    try {
        $conn.Open()
        $c0 = $conn.CreateCommand()
        $c0.CommandText = 'SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED'
        [void]$c0.ExecuteNonQuery()
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $cfg.STOLY_HISTORIA_SQL
        $cmd.CommandTimeout = 30
        $r = $cmd.ExecuteReader()
        try {
            while ($r.Read()) {
                $d = [datetime]$r['data']
                [void]$out.Add([ordered]@{ data = $d.ToString('yyyy-MM-dd'); liczba = [int]$r['liczba'] })
            }
        }
        finally { $r.Close() }
    }
    finally { $conn.Close() }
    return $out
}

function Send-StolyHistoria($cfg, $dni) {
    $payload = @{ dni = @($dni) } | ConvertTo-Json -Depth 5
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    return Invoke-RestMethod -Uri $cfg.VPS_STOLY_HISTORIA_URL -Method Post `
        -Headers @{ 'X-RCP-Token' = $cfg.RCP_INGEST_TOKEN } `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 30
}

function Invoke-Cykl($cfg, [int]$oknoDni) {
    # 1) RCP / godziny - wlasny try, zeby blad nie zablokowal stolow
    try {
        $end = (Get-Date).Date
        $start = $end.AddDays(-1 * $oknoDni)
        $odbicia = Get-Odbicia $cfg $start $end
        if ($odbicia.Count -eq 0) {
            Write-Log ('Brak odbic w oknie {0:yyyy-MM-dd}..{1:yyyy-MM-dd}.' -f $start, $end)
        }
        else {
            $wynik = Send-ToVps $cfg $odbicia
            Write-Log ('Wyslano {0} odbic -> VPS: {1}' -f $odbicia.Count, ($wynik | ConvertTo-Json -Compress -Depth 4))
        }
    }
    catch { Write-Log ('Blad RCP (pomijam ten cykl): {0}' -f $_.Exception.Message) }

    # 2) STOLY - tylko jesli skonfigurowane; wlasny try (RCP dziala niezaleznie)
    if ($cfg.ContainsKey('STOLY_SQL') -and $cfg['STOLY_SQL'] -and $cfg.ContainsKey('VPS_STOLY_URL') -and $cfg['VPS_STOLY_URL']) {
        try {
            $stoly = Get-Stoly $cfg
            Send-Stoly $cfg $stoly | Out-Null
            Write-Log ('Stoly: wyslano {0} rewirow -> VPS.' -f $stoly.Count)
        }
        catch { Write-Log ('Blad stolow (pomijam): {0}' -f $_.Exception.Message) }
    }

    # 3) STOLY HISTORIA (30 dni) - tylko jesli skonfigurowane; wlasny try
    if ($cfg.ContainsKey('STOLY_HISTORIA_SQL') -and $cfg['STOLY_HISTORIA_SQL'] -and $cfg.ContainsKey('VPS_STOLY_HISTORIA_URL') -and $cfg['VPS_STOLY_HISTORIA_URL']) {
        try {
            $hist = Get-StolyHistoria $cfg
            Send-StolyHistoria $cfg $hist | Out-Null
            Write-Log ('Stoly-historia: wyslano {0} dni -> VPS.' -f $hist.Count)
        }
        catch { Write-Log ('Blad historii stolow (pomijam): {0}' -f $_.Exception.Message) }
    }

    # 4) ROZLICZENIA KELNEROW (kwoty deklarowane z POS) - tylko jesli skonfigurowane; wlasny try
    if ($cfg.ContainsKey('ROZLICZENIA_SQL') -and $cfg['ROZLICZENIA_SQL'] -and $cfg.ContainsKey('VPS_ROZLICZENIA_URL') -and $cfg['VPS_ROZLICZENIA_URL']) {
        try {
            $end = (Get-Date).Date
            $start = $end.AddDays(-1 * $oknoDni)
            $roz = Get-Rozliczenia $cfg $start $end
            if ($roz.Count -gt 0) {
                Send-Rozliczenia $cfg $roz | Out-Null
                Write-Log ('Rozliczenia: wyslano {0} pozycji -> VPS.' -f $roz.Count)
            }
        }
        catch { Write-Log ('Blad rozliczen (pomijam): {0}' -f $_.Exception.Message) }
    }

    # 5) ZADATKI (KP - dokumenty kasowe "Kasa przyjela", TypOperacji=0) - tylko jesli skonfigurowane
    if ($cfg.ContainsKey('ZADATKI_SQL') -and $cfg['ZADATKI_SQL'] -and $cfg.ContainsKey('VPS_ZADATKI_URL') -and $cfg['VPS_ZADATKI_URL']) {
        try {
            $end = (Get-Date).Date
            $start = $end.AddDays(-120)   # szersze okno: zadatki przyjmowane z duzym wyprzedzeniem
            $zad = Get-Zadatki $cfg $start $end
            if ($zad.Count -gt 0) {
                Send-Zadatki $cfg $zad | Out-Null
                Write-Log ('Zadatki (KP): wyslano {0} pozycji -> VPS.' -f $zad.Count)
            }
        }
        catch { Write-Log ('Blad zadatkow (pomijam): {0}' -f $_.Exception.Message) }
    }

    # 6) STORNA/RABATY/ANULACJE (antyfraud) - tylko jesli skonfigurowane
    if ($cfg.ContainsKey('STORNA_SQL') -and $cfg['STORNA_SQL'] -and $cfg.ContainsKey('VPS_STORNA_URL') -and $cfg['VPS_STORNA_URL']) {
        try {
            $end = (Get-Date).Date
            $start = $end.AddDays(-$oknoDni)
            $st = Get-Storna $cfg $start $end
            if ($st.Count -gt 0) {
                Send-Storna $cfg $st | Out-Null
                Write-Log ('Storna (antyfraud): wyslano {0} pozycji -> VPS.' -f $st.Count)
            }
        }
        catch { Write-Log ('Blad storn (pomijam): {0}' -f $_.Exception.Message) }
    }
}

# -- ROZLICZENIA KELNEROW (opcjonalne, OSOBNA sciezka - RCP nietkniete) ---------
function Get-Rozliczenia($cfg, [datetime]$start, [datetime]$end) {
    $out = New-Object System.Collections.ArrayList
    $conn = New-Object System.Data.SqlClient.SqlConnection $cfg.RCP_CONNECTION_STRING
    try {
        $conn.Open()
        $c0 = $conn.CreateCommand()
        $c0.CommandText = 'SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED'
        [void]$c0.ExecuteNonQuery()
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $cfg.ROZLICZENIA_SQL
        $cmd.CommandTimeout = 30
        $ps = $cmd.Parameters.Add('@start', [System.Data.SqlDbType]::Date); $ps.Value = $start.Date
        $pe = $cmd.Parameters.Add('@end', [System.Data.SqlDbType]::Date);   $pe.Value = $end.Date
        $r = $cmd.ExecuteReader()
        try {
            while ($r.Read()) {
                $zam = if ($r['zamknieto'] -is [DBNull]) { $null } else { ([datetime]$r['zamknieto']).ToString('yyyy-MM-ddTHH:mm:ss', $Inv) }
                [void]$out.Add([ordered]@{
                        poz_id         = [string]$r['poz_id']
                        rozliczenie_id = [string]$r['rozliczenie_id']
                        imie_nazwisko  = ([string]$r['imie_nazwisko']).Trim()
                        data           = ([datetime]$r['data']).ToString('yyyy-MM-dd', $Inv)
                        zamknieto      = $zam
                        zamkniete      = [int]$r['zamkniete']
                        forma          = ([string]$r['forma']).Trim()
                        sprzedaz       = [decimal]$r['sprzedaz']
                        deklarowane    = [decimal]$r['deklarowane']
                    })
            }
        }
        finally { $r.Close() }
    }
    finally { $conn.Close() }
    return $out
}

function Send-Rozliczenia($cfg, $pozycje) {
    $payload = @{ pozycje = @($pozycje) } | ConvertTo-Json -Depth 5
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    return Invoke-RestMethod -Uri $cfg.VPS_ROZLICZENIA_URL -Method Post `
        -Headers @{ 'X-RCP-Token' = $cfg.RCP_INGEST_TOKEN } `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 30
}

# -- ZADATKI / KP (opcjonalne, OSOBNA sciezka - dokumenty kasowe "Kasa przyjela") ---
function Get-Zadatki($cfg, [datetime]$start, [datetime]$end) {
    $out = New-Object System.Collections.ArrayList
    $conn = New-Object System.Data.SqlClient.SqlConnection $cfg.RCP_CONNECTION_STRING
    try {
        $conn.Open()
        $c0 = $conn.CreateCommand()
        $c0.CommandText = 'SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED'
        [void]$c0.ExecuteNonQuery()
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $cfg.ZADATKI_SQL
        $cmd.CommandTimeout = 30
        $ps = $cmd.Parameters.Add('@start', [System.Data.SqlDbType]::Date); $ps.Value = $start.Date
        $pe = $cmd.Parameters.Add('@end', [System.Data.SqlDbType]::Date);   $pe.Value = $end.Date
        $r = $cmd.ExecuteReader()
        try {
            while ($r.Read()) {
                [void]$out.Add([ordered]@{
                        id    = [string]$r['id']
                        numer = if ($r['numer'] -is [DBNull]) { $null } else { ([string]$r['numer']).Trim() }
                        kwota = [decimal]$r['kwota']
                        opis  = if ($r['opis'] -is [DBNull]) { $null } else { ([string]$r['opis']).Trim() }
                        data  = ([datetime]$r['data']).ToString('yyyy-MM-dd', $Inv)
                    })
            }
        }
        finally { $r.Close() }
    }
    finally { $conn.Close() }
    return $out
}

function Send-Zadatki($cfg, $zadatki) {
    $payload = @{ zadatki = @($zadatki) } | ConvertTo-Json -Depth 5
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    return Invoke-RestMethod -Uri $cfg.VPS_ZADATKI_URL -Method Post `
        -Headers @{ 'X-RCP-Token' = $cfg.RCP_INGEST_TOKEN } `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 30
}

# -- STORNA/RABATY/ANULACJE (antyfraud, opcjonalne - RCP nietkniete) ------------
# Kolumny wymagane przez STORNA_SQL: id (GUID pozycji), data (DATE), imie_nazwisko,
# typ ('storno'|'rabat'|'anulacja'), kwota, opis (opcjonalna), godzina (opcjonalna TIME).
# Schemat storn ROZNI SIE miedzy wersjami Gastro - zweryfikuj zapytanie narzedziem
# odkryj_schemat.ps1 przed wlaczeniem (patrz agent_rcp.env.example, sekcja 9).
function Get-Storna($cfg, [datetime]$start, [datetime]$end) {
    $out = New-Object System.Collections.ArrayList
    $conn = New-Object System.Data.SqlClient.SqlConnection $cfg.RCP_CONNECTION_STRING
    try {
        $conn.Open()
        $c0 = $conn.CreateCommand()
        $c0.CommandText = 'SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED'
        [void]$c0.ExecuteNonQuery()
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $cfg.STORNA_SQL
        $cmd.CommandTimeout = 30
        $ps = $cmd.Parameters.Add('@start', [System.Data.SqlDbType]::Date); $ps.Value = $start.Date
        $pe = $cmd.Parameters.Add('@end', [System.Data.SqlDbType]::Date);   $pe.Value = $end.Date
        $r = $cmd.ExecuteReader()
        try {
            while ($r.Read()) {
                [void]$out.Add([ordered]@{
                        id            = [string]$r['id']
                        data          = ([datetime]$r['data']).ToString('yyyy-MM-dd', $Inv)
                        imie_nazwisko = if ($r['imie_nazwisko'] -is [DBNull]) { $null } else { ([string]$r['imie_nazwisko']).Trim() }
                        typ           = if ($r['typ'] -is [DBNull]) { 'storno' } else { ([string]$r['typ']).Trim().ToLower() }
                        kwota         = [decimal]$r['kwota']
                        opis          = if ($r['opis'] -is [DBNull]) { $null } else { ([string]$r['opis']).Trim() }
                        godzina       = if ($r['godzina'] -is [DBNull]) { $null } else { ([datetime]$r['godzina']).ToString('HH:mm:ss', $Inv) }
                    })
            }
        }
        finally { $r.Close() }
    }
    finally { $conn.Close() }
    return $out
}

function Send-Storna($cfg, $storna) {
    $payload = @{ storna = @($storna) } | ConvertTo-Json -Depth 5
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    return Invoke-RestMethod -Uri $cfg.VPS_STORNA_URL -Method Post `
        -Headers @{ 'X-RCP-Token' = $cfg.RCP_INGEST_TOKEN } `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 30
}

# -- main ----------------------------------------------------------------------
$cfg = Get-Config $EnvPath
$poll = if ($cfg.ContainsKey('POLL_SECONDS') -and $cfg['POLL_SECONDS']) { [int]$cfg['POLL_SECONDS'] } else { 30 }
$okno = if ($cfg.ContainsKey('OKNO_DNI') -and $cfg['OKNO_DNI']) { [int]$cfg['OKNO_DNI'] } else { 2 }
Write-Log ('Agent RCP (PowerShell) start. Poll co {0}s, okno {1} dni. Cel: {2}' -f $poll, $okno, $cfg.VPS_INGEST_URL)

while ($true) {
    try { Invoke-Cykl $cfg $okno }
    catch { Write-Log ('Blad cyklu (ponowie za {0}s): {1}' -f $poll, $_.Exception.Message) }
    Start-Sleep -Seconds $poll
}
