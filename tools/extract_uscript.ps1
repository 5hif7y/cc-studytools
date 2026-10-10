# ---------------------------------------------------------------------------
# extract_uscript.ps1 -Paquete <ruta.u> [-Salida <dir>] [-Filtro <texto>]
#
# Recupera el UnrealScript de un paquete COCINADO de UE3.
#
# Un paquete cocinado no lleva el fuente .uc, pero si lleva el BYTECODE, y el
# bytecode conserva la estructura: nombres de clase, herencia, variables,
# enums, estados y el cuerpo de las funciones. UELib lo reconstruye.
#
# POR QUE FUNCIONA CON CRIMECRAFT
#   Los paquetes del juego son UE3 estandar sin comprimir (version 576,
#   licensee 5, motor 4701). UELib los reconoce e identifica incluso el
#   build: imprime "Build:CrimeCraft" al cargarlos.
#
# LO QUE NO SE RECUPERA
#   Los comentarios del codigo original: no llegan al bytecode. El fuente que
#   sale es funcionalmente equivalente pero no es el que escribio Vogster.
#   Las clases marcadas "native" salen solo como declaracion, porque su
#   cuerpo esta en C++ y nunca estuvo en el paquete.
#
# REQUISITOS
#   Eliot.UELib.dll de UE Explorer. Por defecto se busca en la instalacion
#   portable que hay en la raiz del workspace.
#
# EJEMPLO
#   .\extract_uscript.ps1 -Paquete ..\CrimeCraft\CrimeCraftGame\CookedPC\CrimeCraftEd.u
# ---------------------------------------------------------------------------

param(
    [Parameter(Mandatory=$true)][string]$Paquete,
    [string]$Salida,
    [string]$Dll,
    [string]$Filtro = '',
    [string]$Tabla,
    [switch]$SinTabla
)

$ErrorActionPreference = 'Stop'

# --- Localizar UELib -------------------------------------------------------

if (-not $Dll) {
    $candidatos = @(
        (Join-Path $PSScriptRoot '..\ue-explorer-1.6.2-net48-portable\ue-explorer\Eliot.UELib.dll'),
        (Join-Path $PSScriptRoot '..\UE-Explorer\UE Explorer\bin\Release\Eliot.UELib.dll')
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) { $Dll = (Resolve-Path $c).Path; break }
    }
}
if (-not $Dll -or -not (Test-Path $Dll)) {
    Write-Output "ERROR: no se encuentra Eliot.UELib.dll. Indicarla con -Dll."
    exit 1
}
[void][Reflection.Assembly]::LoadFrom($Dll)

$pkgPath = (Resolve-Path $Paquete).Path
$nombre  = [System.IO.Path]::GetFileNameWithoutExtension($pkgPath)

if (-not $Salida) { $Salida = Join-Path (Get-Location) ('uscript_' + $nombre) }
if (-not (Test-Path $Salida)) { New-Item -ItemType Directory -Path $Salida | Out-Null }
$Salida = (Resolve-Path $Salida).Path

Write-Output ("Paquete : {0}" -f $pkgPath)
Write-Output ("Salida  : {0}" -f $Salida)

# --- Cargar el paquete -----------------------------------------------------

$pkg = [UELib.UnrealLoader]::LoadPackage($pkgPath, [System.IO.FileAccess]::Read)

# --- La tabla de nativas ---------------------------------------------------
#
# SIN ESTO, cada llamada nativa sale como `__NFUN_<indice>__`: UELib no sabe
# como se llama y la deja con un nombre generado. Son 151 nombres distintos y
# 35.340 llamadas, y NO son solo operadores -- `__NFUN_280__` es SetTimer y
# `__NFUN_113__` es GotoState.
#
# La tabla NO hay que buscarla fuera: **los .u del juego la llevan dentro**.
# Cada UFunction nativa conserva su NativeToken en el export table, y
# tools/generate-native-table.ps1 los recoge y escribe la .NTL.
#
# EL ORDEN IMPORTA. Tiene que estar puesta ANTES de InitializePackage:
# EngineBranch.GetTokenFactory cachea la factoria (`if (_TokenFactory != null)
# return`), y la factoria lee NTLPackage al construirse. Si se asigna despues,
# la tabla se ignora EN SILENCIO.

if (-not $SinTabla) {
    if (-not $Tabla) {
        $candidata = Join-Path $PSScriptRoot 'NativesTableList_CrimeCraft.NTL'
        if (Test-Path $candidata) { $Tabla = $candidata }
    }
    if ($Tabla -and (Test-Path $Tabla)) {
        $fs = [System.IO.File]::OpenRead((Resolve-Path $Tabla).Path)
        try {
            $ntl = New-Object UELib.NativesTablePackage
            $ntl.Deserialize($fs)
        } finally { $fs.Close() }
        $pkg.NTLPackage = $ntl
        Write-Output ("Tabla   : {0}  ({1} entradas)" -f (Split-Path $Tabla -Leaf), $ntl.NativeTableList.Count)
    } else {
        Write-Output "Tabla   : NINGUNA -- las nativas saldran como __NFUN_<indice>__"
        Write-Output "          Generarla con: tools/generate-native-table.ps1"
    }
}

$pkg.InitializePackage([UELib.UnrealPackage+InitFlags]::All)

# --- Recorrer las clases ---------------------------------------------------
#
# OJO al comparar nombres: UObject.Name es un objeto UELib.Core.UName, no una
# cadena. "-eq 'Texto'" falla en silencio y devuelve vacio; hay que llamar a
# ToString(). "-like" si funciona, porque PowerShell coerciona para ese
# operador, y eso hace el fallo mas dificil de ver.

$clases = @($pkg.Objects | Where-Object { $_ -is [UELib.Core.UClass] })
if ($Filtro -ne '') {
    $clases = @($clases | Where-Object { $_.Name.ToString() -like "*$Filtro*" })
}

$total = 0; $conCuerpo = 0; $soloNative = 0
foreach ($c in $clases) {
    $n = $c.Name.ToString()
    try {
        $txt = $c.Decompile()
    } catch {
        Write-Output ("  AVISO: fallo al descompilar '{0}': {1}" -f $n, $_.Exception.Message)
        continue
    }
    if (-not $txt) { continue }

    $destino = Join-Path $Salida ($n + '.uc')
    [System.IO.File]::WriteAllText($destino, $txt, [System.Text.Encoding]::UTF8)
    $total++

    if ($txt.Length -lt 200) { $soloNative++ } else { $conCuerpo++ }
}

Write-Output ""
Write-Output ("Clases escritas : {0}" -f $total)
Write-Output ("  con cuerpo    : {0}" -f $conCuerpo)
Write-Output ("  solo nativas  : {0}  (declaracion; su cuerpo esta en C++)" -f $soloNative)
