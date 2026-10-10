# ---------------------------------------------------------------------------
# probe-native-flags.ps1 [-Tokens 129,165,160] [-Paquete <ruta.u>]
#
# QUE BANDERAS TIENE DE VERDAD UNA NATIVA, en el export table del JUEGO.
#
# POR QUE HACE FALTA. UELib decide como pintar un operador con esto
# (UELib/src/NativesTablePackage.cs, NativeTableItem):
#
#     if (function.IsPost())        Type = PostOperator;   // IsOperator && prec==0
#     else if (function.IsPre())    Type = PreOperator;    // IsOperator && FUNC_PreOperator
#     else if (function.IsOperator()) Type = Operator;
#
# **`IsPost()` se comprueba PRIMERO y su test es DEBIL** (`prec == 0`), asi que
# se traga todos los prefijos: `!` y la negacion salen como PostOperator y el
# descompilador los pinta DETRAS del operando -- `bBlockRotation!`.
#
# Esta sonda comprueba si el paquete del juego marca `PreOperator` de verdad.
# Si lo marca, el arreglo es NUESTRO: la .NTL la escribimos nosotros, y basta
# con clasificar bien al generarla.
# ---------------------------------------------------------------------------

param(
    [int[]]$Tokens = @(129, 165, 160, 112, 150),
    [string[]]$Paquete,
    [string]$Dll
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent

if (-not $Dll) {
    foreach ($c in @((Join-Path $raiz 'ue-explorer-1.6.2-net48-portable\ue-explorer\Eliot.UELib.dll'),
                     (Join-Path $raiz 'UE-Explorer\UE Explorer\bin\Release\Eliot.UELib.dll'))) {
        if (Test-Path $c) { $Dll = (Resolve-Path $c).Path; break }
    }
}
[void][Reflection.Assembly]::LoadFrom($Dll)

if (-not $Paquete) {
    $Paquete = @(
        (Join-Path $raiz 'CrimeCraft\CrimeCraftGame\CookedPC\Core.u'),
        (Join-Path $raiz 'CrimeCraft\CrimeCraftGame\CookedPC\Engine.u')
    )
}

# Valores LITERALES: `[Enum]::$var` no resuelve en PowerShell.
$BANDERAS = [ordered]@{
    'Final'       = [UELib.Flags.FunctionFlag]::Final
    'PreOperator' = [UELib.Flags.FunctionFlag]::PreOperator
    'Operator'    = [UELib.Flags.FunctionFlag]::Operator
    'Native'      = [UELib.Flags.FunctionFlag]::Native
    'Simulated'   = [UELib.Flags.FunctionFlag]::Simulated
    'Static'      = [UELib.Flags.FunctionFlag]::Static
}

foreach ($p in $Paquete) {
    $pkg = [UELib.UnrealLoader]::LoadPackage($p, [System.IO.FileAccess]::Read)
    $pkg.InitializePackage([UELib.UnrealPackage+InitFlags]::All)

    foreach ($f in $pkg.Objects) {
        if (-not ($f -is [UELib.Core.UFunction])) { continue }
        if (-not $f.FunctionFlags.HasFlag([UELib.Flags.FunctionFlag]::Native)) { continue }
        if ($Tokens -notcontains [int]$f.NativeToken) { continue }

        $puestas = @()
        foreach ($k in $BANDERAS.Keys) {
            if ($f.FunctionFlags.HasFlag($BANDERAS[$k])) { $puestas += $k }
        }
        # Lo que UELib concluye, para comparar con lo que dice el bit
        $post = $f.IsPost(); $pre = $f.IsPre(); $op = $f.IsOperator()
        Write-Output ("SONDA|{0,5}|{1,-16}|prec={2,-3}|{3,-28}|IsOp={4,-5} IsPre={5,-5} IsPost={6,-5}" -f `
            $f.NativeToken, $f.FriendlyName, $f.OperPrecedence, ($puestas -join ' '), $op, $pre, $post)
    }
    $pkg.Stream.Close()
}
