# ---------------------------------------------------------------------------
# inspect-function.ps1 -Clase <Nombre> [-Funcion <Nombre>] [-Paquete <ruta.u>]
#
# MIRA, EN EL PAQUETE DEL JUEGO, QUE DICE UNA CLASE O UNA FUNCION.
#
# POR QUE HACE FALTA. El SDK con el que compilamos es de otra version del motor
# (10897) que el juego (4701). Cuando el compilador se queja de algo del SDK
# --un `final`, una firma, un modificador-- hay SIEMPRE dos explicaciones y hay
# que distinguirlas:
#
#   a) el juego tambien lo dice, y el stub esta mal
#   b) el juego NO lo dice: es una DERIVA del SDK, y alinearse con el juego
#      es RESTAURAR fidelidad, no romper nada
#
# Esto responde cual de las dos, leyendo el export table. Solo LEE.
#
# EJEMPLO
#   .\inspect-function.ps1 -Clase Weapon -Funcion SetPendingFire
# ---------------------------------------------------------------------------

param(
    [Parameter(Mandatory=$true)][string]$Clase,
    [string]$Funcion,
    [string]$Paquete,
    [string]$Dll
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent

if (-not $Dll) {
    $candidatos = @(
        (Join-Path $raiz 'ue-explorer-1.6.2-net48-portable\ue-explorer\Eliot.UELib.dll'),
        (Join-Path $raiz 'UE-Explorer\UE Explorer\bin\Release\Eliot.UELib.dll')
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) { $Dll = (Resolve-Path $c).Path; break }
    }
}
[void][Reflection.Assembly]::LoadFrom($Dll)

# OJO: el paquete donde vive una clase NO es siempre el obvio. `Weapon` vive en
# Engine.u, pero las clases del juego pueden estar en CrimeCraft.u. Si no se
# indica, se buscan por orden -- y se dice donde se encontro, porque "no esta"
# y "no lo busque" son cosas distintas.
if (-not $Paquete) {
    $cooked = Join-Path $raiz 'CrimeCraft\CrimeCraftGame\CookedPC'
    $Paquete = @('Engine.u','Core.u','GameFramework.u','CrimeCraft.u') |
        ForEach-Object { Join-Path $cooked $_ } |
        Where-Object { Test-Path $_ }
}

foreach ($p in $Paquete) {
    $pkg = [UELib.UnrealLoader]::LoadPackage($p, [System.IO.FileAccess]::Read)
    $pkg.InitializePackage([UELib.UnrealPackage+InitFlags]::All)
    $nomPkg = [System.IO.Path]::GetFileName($p)

    $cls = $pkg.Objects | Where-Object {
        $_ -is [UELib.Core.UClass] -and $_.Name.ToString() -eq $Clase
    } | Select-Object -First 1

    if (-not $cls) { $pkg.Stream.Close(); continue }

    Write-Output ("RESULTADO|{0}|en {1}  super={2}" -f $Clase, $nomPkg,
        $(if ($cls.Super) { $cls.Super.Name.ToString() } else { '(ninguno)' }))

    $funcs = $cls.EnumerateFields() | Where-Object { $_ -is [UELib.Core.UFunction] }
    if ($Funcion) {
        $funcs = $funcs | Where-Object { $_.Name.ToString() -eq $Funcion }
    }
    if (-not $funcs) {
        Write-Output ("RESULTADO|(sin resultados)|no esta '{0}' en {1}" -f $Funcion, $nomPkg)
    }

    # OJO: `[Enum]::$variable` NO resuelve en PowerShell -- da "Cannot find an
    # overload for HasFlag" en vez de un error de sintaxis, que despista. Los
    # valores van LITERALES.
    $BANDERAS = [ordered]@{
        'FINAL'     = [UELib.Flags.FunctionFlag]::Final
        'native'    = [UELib.Flags.FunctionFlag]::Native
        'simulated' = [UELib.Flags.FunctionFlag]::Simulated
        'event'     = [UELib.Flags.FunctionFlag]::Event
        'operator'  = [UELib.Flags.FunctionFlag]::Operator
        'static'    = [UELib.Flags.FunctionFlag]::Static
        'defined'   = [UELib.Flags.FunctionFlag]::Defined
        'latent'    = [UELib.Flags.FunctionFlag]::Latent
        'const'     = [UELib.Flags.FunctionFlag]::Const
    }
    foreach ($f in $funcs) {
        $fl = $f.FunctionFlags
        $txt = @()
        foreach ($k in $BANDERAS.Keys) {
            if ($fl.HasFlag($BANDERAS[$k])) { $txt += $k }
        }
        $cuerpo = if ($f.ScriptText) { 'CON CUERPO' } else { 'sin cuerpo (nativa o vacia)' }
        Write-Output ("RESULTADO|{0}|{1}|{2}" -f $f.Name.ToString(), ($txt -join ' '), $cuerpo)
    }

    $pkg.Stream.Close()
    Write-Output ""
}
