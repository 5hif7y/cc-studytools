# ---------------------------------------------------------------------------
# generate-native-table.ps1 [-Paquetes <rutas.u>] [-Salida <fichero.NTL>]
#
# GENERA la tabla de nativas (.NTL) DE LOS PROPIOS PAQUETES DEL JUEGO.
#
# POR QUE ESTO ES LA VIA DIRECTA Y NO UNA DEDUCCION
#   UELib pone nombre a las llamadas nativas con una tabla de nativas por
#   version del motor. CrimeCraft es un build de licenciatario y UELib no trae
#   la suya, asi que cada nativa sale como `__NFUN_<indice>__`.
#
#   Pero la tabla NO hay que adivinarla ni buscarla fuera: cada UFunction
#   marcada Native conserva su NativeToken EN EL EXPORT TABLE del paquete. Es
#   decir, **los .u del juego LLEVAN la tabla dentro**. Esto lo hace el mismo
#   UELib: es exactamente lo que hace
#   `Eliot.Extensions.NativesTableListGenerator/UC_NativeGenerator.cs:64-75`.
#
#   Esto solo LEE paquetes. Es la misma operacion que extract_uscript.ps1.
#
# FORMATO DE SALIDA (.NTL), de UELib/src/NativesTablePackage.cs:
#   uint32 firma 0x2C8D14F1 | int32 cuantas | por entrada:
#   string Nombre | byte OperPrecedence | byte Type | int32 ByteToken
#   Type: 1=Function 2=Operator 3=PreOperator 4=PostOperator
#
# EJEMPLO
#   .\generate-native-table.ps1
#   .\generate-native-table.ps1 -SoloListar        # no escribe .NTL, solo informa
# ---------------------------------------------------------------------------

param(
    [string[]]$Paquetes,
    [string]$Salida,
    [string]$Dll,
    [switch]$SoloListar
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
if (-not $Dll -or -not (Test-Path $Dll)) {
    Write-Output "ERROR: no se encuentra Eliot.UELib.dll. Indicarla con -Dll."
    exit 1
}
[void][Reflection.Assembly]::LoadFrom($Dll)

# --- Que paquetes ----------------------------------------------------------
#
# Los nativos se declaran en el paquete donde vive su C++. Core y Engine traen
# la mayoria; los demas traen los suyos. Se cargan TODOS los que haya.

if (-not $Paquetes) {
    $cooked = Join-Path $raiz 'CrimeCraft\CrimeCraftGame\CookedPC'
    $Paquetes = Get-ChildItem -Path $cooked -Filter '*.u' |
        Sort-Object Length |                # los pequenos primero: se ve avanzar
        ForEach-Object { $_.FullName }
}

Write-Output ("DLL      : {0}" -f $Dll)
Write-Output ("Paquetes : {0}" -f $Paquetes.Count)
Write-Output ""

# --- Cargar y recoger ------------------------------------------------------

$tabla = @{}          # token -> objeto con Nombre/Precedencia/Tipo
$duplicados = 0
$reclasificados = 0   # prefijos que UELib habria pintado como postfijos
$conflictos = @()

foreach ($ruta in $Paquetes) {
    $nomPkg = [System.IO.Path]::GetFileName($ruta)
    $t0 = Get-Date
    try {
        $pkg = [UELib.UnrealLoader]::LoadPackage($ruta, [System.IO.FileAccess]::Read)
        $pkg.InitializePackage([UELib.UnrealPackage+InitFlags]::All)
    } catch {
        Write-Output ("  {0,-22} ERROR al cargar: {1}" -f $nomPkg, $_.Exception.Message)
        continue
    }

    $nativas = 0
    foreach ($f in $pkg.Objects) {
        if (-not ($f -is [UELib.Core.UFunction])) { continue }
        if (-not $f.FunctionFlags.HasFlag([UELib.Flags.FunctionFlag]::Native)) { continue }
        $tok = [int]$f.NativeToken
        if ($tok -eq 0) { continue }
        $nativas++

        # El tipo. OJO: NO se copia el orden de NativeTableItem(UFunction).
        #
        # UELib hace `if (IsPost()) ... else if (IsPre()) ...`, y **ese orden
        # es un bug para los PREFIJOS**: `IsPost()` solo mira `OperPrecedence
        # == 0`, que es cierto para `!` y para la negacion, y como va PRIMERO
        # se los traga. Medido en el paquete del juego:
        #
        #   129  !   prec=0   ...PreOperator...   IsPre=True  IsPost=True
        #   165  ++  prec=0   (sin PreOperator)   IsPre=False IsPost=True
        #
        # El descompilador pinta el PostOperator DETRAS del operando, y salia
        # `bBlockRotation!`. **El discriminante bueno es la bandera**, asi que
        # aqui se comprueba IsPre() PRIMERO.
        #
        # Y esto vale para cualquier tabla, tambien las que trae UELib: la de
        # DukeNukemForever2011 tiene `!` como PostOperator por el mismo motivo.
        if     ($f.IsOperator() -and $f.IsPre())  { $tipo = 3 }
        elseif ($f.IsOperator() -and $f.IsPost()) { $tipo = 4 }
        elseif ($f.IsOperator())                  { $tipo = 2 }
        else                                      { $tipo = 1 }
        if ($tipo -eq 3) { $reclasificados++ }

        $nombre = $f.FriendlyName
        if (-not $nombre) { $nombre = $f.Name.ToString() }

        $ent = [PSCustomObject]@{
            Token       = $tok
            Nombre      = $nombre.ToString()
            Precedencia = [int]$f.OperPrecedence
            Tipo        = $tipo
            Paquete     = $nomPkg
        }

        if ($tabla.ContainsKey($tok)) {
            $duplicados++
            # Si dos paquetes dan el MISMO token con nombres distintos, uno manda
            # y callarse seria peor: se anota.
            if ($tabla[$tok].Nombre -ne $ent.Nombre) {
                $conflictos += ("{0}: {1} ({2}) vs {3} ({4})" -f $tok,
                    $tabla[$tok].Nombre, $tabla[$tok].Paquete, $ent.Nombre, $nomPkg)
            }
        } else {
            $tabla[$tok] = $ent
        }
    }
    $seg = [int]((Get-Date) - $t0).TotalSeconds
    Write-Output ("  {0,-22} {1,5} nativas   {2,3}s" -f $nomPkg, $nativas, $seg)
    $pkg.Stream.Close()
}

Write-Output ""
Write-Output ("Tokens distintos : {0}" -f $tabla.Count)
Write-Output ("Repetidos        : {0}" -f $duplicados)
Write-Output ("PREFIJOS rescatados de UELib : {0}  (su IsPost() se los tragaba)" -f $reclasificados)
if ($conflictos.Count -gt 0) {
    Write-Output ("CONFLICTOS       : {0}  (mismo token, nombre distinto entre paquetes)" -f $conflictos.Count)
    $conflictos | Select-Object -First 20 | ForEach-Object { Write-Output ("    {0}" -f $_) }
}
if ($tabla.Count -gt 0) {
    $min = ($tabla.Keys | Measure-Object -Minimum).Minimum
    $max = ($tabla.Keys | Measure-Object -Maximum).Maximum
    Write-Output ("Rango            : {0}..{1}" -f $min, $max)
}
Write-Output ""

# --- La prueba falsable ----------------------------------------------------
#
# Estos usos se leyeron del codigo del juego y su significado es SEGURO por el
# contexto. Si la tabla es la correcta, tienen que salir asi:
#
#   __NFUN_113__('CCAIDebugSpectating')            -> GotoState
#   __NFUN_280__(TickRate, true, 'CheckPawns...')  -> SetTimer
#   __NFUN_112__(a, b, c)  concatenacion de cadenas -> $
#   __NFUN_119__(X, none)                           -> != o ==
#
# Y si NO salen asi, la tabla no es la del juego y hay que decirlo.

# OJO: claves como CADENA. Con claves enteras, `$esperado[$k]` devuelve vacio
# en silencio (el diccionario ordenado indexa por objeto y no coerciona) y la
# columna sale en blanco -- que es justo como salio la primera vez.

$esperado = [ordered]@{
    '113' = 'GotoState'
    '280' = 'SetTimer'
    '112' = '$'
    '195' = 'FRand'
    '150' = '<'
    '129' = '!'
    '151' = '>'
    '114' = '=='
    '119' = '!='
    '130' = '||'
    '132' = '&&'
}
Write-Output "PRUEBA: lo que el codigo del juego dice que son estos indices"
Write-Output ("  {0,-6} {1,-14} {2,-14} {3}" -f "token", "esperado", "en la tabla", "veredicto")
foreach ($k in $esperado.Keys) {
    $t = [int]$k
    $tiene = $tabla.ContainsKey($t)
    $real = if ($tiene) { [string]$tabla[$t].Nombre } else { '-- no esta --' }
    $veredicto = if (-not $tiene) { 'FALTA' }
                 elseif ($real -eq $esperado[$k]) { 'OK' }
                 else { 'NO CUADRA' }
    Write-Output ("  {0,-6} {1,-14} {2,-14} {3}" -f $k, $esperado[$k], $real, $veredicto)
}
Write-Output ""

if ($SoloListar) { return }

# --- Escribir la .NTL ------------------------------------------------------

if (-not $Salida) {
    $Salida = Join-Path $PSScriptRoot 'NativesTableList_CrimeCraft.NTL'
}

$fs = [System.IO.File]::Create($Salida)
$bw = New-Object System.IO.BinaryWriter($fs)
try {
    $bw.Write([uint32]0x2C8D14F1)
    $bw.Write([int32]$tabla.Count)
    foreach ($tok in ($tabla.Keys | Sort-Object)) {
        $e = $tabla[$tok]
        $bw.Write($e.Nombre)        # string con prefijo de longitud 7-bit
        $bw.Write([byte]$e.Precedencia)
        $bw.Write([byte]$e.Tipo)
        $bw.Write([int32]$e.Token)
    }
} finally {
    $bw.Close(); $fs.Close()
}
Write-Output ("Escrita: {0}  ({1} bytes, {2} entradas)" -f $Salida, (Get-Item $Salida).Length, $tabla.Count)
