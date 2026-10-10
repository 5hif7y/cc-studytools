#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EL LECTOR DE PAQUETES DEL PROYECTO -- uno solo, y se autovalida.

POR QUE EXISTE
--------------
Medido el 5/10 sobre `tools/*.py`: habia **6 copias** del lector de la tabla de
exportaciones, **4** del de nombres y **8** del de encabezado, con **tres formas
distintas de paso**. Y el resultado fue el §22 del relevo: cinco sitios leian la
tabla con paso FIJO de 68 sobre registros que miden `68 + 4*N`, y **el valor
desplazado parece bueno** -- 41,7 % de los registros de `CrimeCraft.u` y 53,1 %
de `EntryLevel.ccmap` se leian mal, en silencio.

Es literalmente la leccion que el proyecto ya tenia escrita:

    Un supuesto de formato que comparten varias herramientas no lo audita ninguna.

Aqui el supuesto vive en UN sitio, y ese sitio se comprueba a si mismo.

LAS CUATRO COMPROBACIONES QUE NO SE PUEDEN FALSEAR
--------------------------------------------------
Un paquete UE3 es cabecera + tablas + datos, y las tablas dicen donde empieza y
cuanto mide cada cosa. Eso da cuatro cierres exactos que no dependen de creerle
nada al lector:

  1. la tabla de NOMBRES  acaba en ImportOffset
  2. la tabla de IMPORTS  acaba en ExportOffset   (28 B por entrada)
  3. la tabla de EXPORTS  acaba en DependsOffset  (68 + 4N por entrada)
  4. el ULTIMO export     acaba en el ultimo byte del fichero

Si alguna falla, `lee_paquete` **lo dice en `problemas`** en vez de devolver
numeros plausibles. Y `estricto=True` aborta.

LA CONVENCION DEL `OuterIndex`, que se mide mal con facilidad
-------------------------------------------------------------
Es **la misma en las dos tablas** (es `ULinkerLoad::IndexToObject`, un solo
sitio en el motor):

    > 0   ->  EXPORTACION, indice 1-based
    < 0   ->  IMPORTACION, indice 1-based (0-based: -n-1)
    == 0  ->  el paquete / la raiz

Measured on 5/10: assuming that a negative meant *export* produced **99.95 % of
imports unresolved** in the game's `CrimeCraft.u` -- **a number that looks like
data and is an artefact.**

What caught it was the control: with the right convention the roots come out
`Engine` 1,846 / `Core` 139 / `GameFramework` 4 / `UnScriptTest` 3, **which match
exactly what an independent method had measured beforehand**.

Uso:
    from package import lee_paquete, clase_de, camino_import, rutas_exportaciones
    p = lee_paquete(".../Engine.u")
    p["version"], p["problemas"], len(p["exports"])
"""
import os
import struct

CABECERA = 0x9E2A83C1
TAM_IMPORT = 28


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def u32(d, p):
    return struct.unpack_from("<I", d, p)[0]


def nombre_paquete(ruta):
    """`.../Engine.u` -> `Engine`. Es la raiz de todo camino de importacion."""
    return os.path.splitext(os.path.basename(ruta))[0]


def lee_cabecera(d):
    """`FPackageFileSummary` (`UnLinker.cpp:377-468`). None si no es un paquete UE3.

    **LA CABECERA DEPENDE DE LA VERSION, y hay dos linajes en juego.** Medido el
    5/10: leerla de una sola forma funcionaba en los **547** paquetes del juego
    (576) y reventaba en los **13** nuestros (867) -- `unpack_from requires a
    buffer of at least 12431711321 bytes`.

    Tras `DependsOffset` el serializador tiene dos puertas, y las dos son **> 576**:

        if( Ver >= VER_ADDED_CROSSLEVEL_REFERENCES  = 623 )  +12 B
        if( Ver >= VER_ASSET_THUMBNAILS_IN_PACKAGES = 584 )  +4 B

    O sea que un paquete 867 trae **16 bytes mas** antes del `Guid`, y leerlos de
    menos hace que el `GenerationCount` salga del `Guid` -- un entero enorme que
    parece un dato.

    Ojo tambien con `TotalHeaderSize`: va en **+8**, justo tras las dos WORD de
    version. Leerlo de otro sitio da un numero plausible y falso -- le paso al
    documento de `.ccmap`, que anoto `DependsOffset = 859.406` donde el fichero
    dice `858.382`, y la diferencia (1.024 B) se persiguio cinco dias como si
    fuera del formato.
    """
    if len(d) < 64 or u32(d, 0) != CABECERA:
        return None
    e = {}
    ver = struct.unpack_from("<H", d, 4)[0]
    e["FileVersion"] = ver
    e["LicenseeVersion"] = struct.unpack_from("<H", d, 6)[0]
    e["TotalHeaderSize"] = u32(d, 8)
    long_folder = i32(d, 12)
    p = 16 + long_folder
    e["PackageFlags"] = u32(d, p); p += 4
    e["NameCount"] = i32(d, p); p += 4
    e["NameOffset"] = i32(d, p); p += 4
    e["ExportCount"] = i32(d, p); p += 4
    e["ExportOffset"] = i32(d, p); p += 4
    e["ImportCount"] = i32(d, p); p += 4
    e["ImportOffset"] = i32(d, p); p += 4
    e["DependsOffset"] = i32(d, p); p += 4
    if ver >= 623:               # VER_ADDED_CROSSLEVEL_REFERENCES
        e["ImportExportGuidsOffset"] = i32(d, p)
        e["ImportGuidsCount"] = i32(d, p + 4)
        e["ExportGuidsCount"] = i32(d, p + 8)
        p += 12
    if ver >= 584:               # VER_ASSET_THUMBNAILS_IN_PACKAGES
        e["ThumbnailTableOffset"] = i32(d, p)
        p += 4
    p += 16                      # Guid -- va ANTES de GenerationCount
    gen = i32(d, p); p += 4
    e["GenerationCount"] = gen
    p += gen * 12                # FGenerationInfo
    e["EngineVersion"] = i32(d, p)
    return e


def lee_nombres(d, off, cuenta):
    """`[i32 len][len bytes][QWORD flags]`. len negativo = UTF-16."""
    nombres, p = [], off
    for _ in range(cuenta):
        n = i32(d, p); p += 4
        if n < 0:
            s = d[p:p - n * 2].decode("utf-16-le", "replace"); p += -n * 2
        else:
            s = d[p:p + n].decode("latin-1"); p += n
        p += 8                   # los flags del FName
        nombres.append(s.rstrip("\x00"))
    return nombres, p


def lee_imports(d, off, cuenta):
    """`FObjectImport` = 28 B exactos (`UnLinker.cpp:316-328`):
    ClassPackage(8) + ClassName(8) + OuterIndex(4) + ObjectName(8).

    **El orden no es el que parece**: el paquete de la clase va ANTES que la
    clase. Se midio mal dos veces antes de acertar, y las dos veces el error fue
    silencioso porque daba nombres plausibles.
    """
    imps, p = [], off
    for _ in range(cuenta):
        imps.append({"cp": i32(d, p),      # ClassPackage
                     "cn": i32(d, p + 8),  # ClassName
                     "outer": i32(d, p + 16),
                     "on": i32(d, p + 20)})  # ObjectName
        p += TAM_IMPORT
    return imps, p


def lee_exports(d, off, cuenta):
    """`FObjectExport`, **PASO VARIABLE**: `68 + 4*N`, N = `GenerationNetObjectCount`.

    El orden es el de `FObjectExport::operator<<` (`UnLinker.cpp:267-292`):

        ClassIndex(4) SuperIndex(4) OuterIndex(4) ObjectName(8) ArchetypeIndex(4)
        ObjectFlags(8) SerialSize(4) SerialOffset(4) ExportFlags(4)
        GenerationNetObjectCount(4 + 4N) PackageGuid(16) PackageFlags(4)

    `ObjectFlags` son **8 B**: `typedef QWORD EObjectFlags` (`UnObjBas.h:335`).
    `LegacyComponentMap` NO es un campo de la estructura, es una variable local
    del serializador bajo `Ver < 543`, y con 576 no se cumple.
    """
    exps, p = [], off
    for _ in range(cuenta):
        n = i32(d, p + 44)
        if n < 0 or n > (1 << 20):
            raise ValueError("GenerationNetObjectCount absurdo: %d en offset %d" % (n, p))
        exps.append({"ci": i32(d, p),
                     "si": i32(d, p + 4),
                     "outer": i32(d, p + 8),
                     "nm": i32(d, p + 12),
                     "archetype": i32(d, p + 20),
                     "tam": i32(d, p + 32),
                     "off": i32(d, p + 36),
                     "n_generaciones": n})
        p += 68 + 4 * n
    return exps, p


def lee_paquete(ruta, estricto=False):
    """Lee un `.u`, `.ccmap` o `.ccpk` entero y **se valida**.

    Devuelve un dict con `nombres`, `imports`, `exports` y `problemas` (la lista
    de comprobaciones que NO se cumplieron -- vacia es la respuesta buena).
    """
    with open(ruta, "rb") as fh:
        d = fh.read()
    if len(d) < 64 or u32(d, 0) != CABECERA:
        raise ValueError("no es un paquete UE3: %s" % ruta)

    e = lee_cabecera(d)
    nombres, fin_nombres = lee_nombres(d, e["NameOffset"], e["NameCount"])
    imports, fin_imports = lee_imports(d, e["ImportOffset"], e["ImportCount"])
    exports, fin_exports = lee_exports(d, e["ExportOffset"], e["ExportCount"])

    problemas = []
    if fin_nombres != e["ImportOffset"]:
        problemas.append("nombres acaban en %d, ImportOffset=%d" % (fin_nombres, e["ImportOffset"]))
    if fin_imports != e["ExportOffset"]:
        problemas.append("imports acaban en %d, ExportOffset=%d" % (fin_imports, e["ExportOffset"]))
    if fin_exports != e["DependsOffset"]:
        problemas.append("exports acaban en %d, DependsOffset=%d" % (fin_exports, e["DependsOffset"]))
    fin_datos = max((x["off"] + x["tam"] for x in exports), default=0)
    if fin_datos != len(d):
        problemas.append("el ultimo export acaba en %d, el fichero mide %d" % (fin_datos, len(d)))

    if problemas and estricto:
        raise ValueError("%s NO cuadra: %s" % (ruta, "; ".join(problemas)))

    return {"ruta": ruta, "nombre": nombre_paquete(ruta), "bytes": len(d),
            "cabecera": e, "nombres": nombres, "imports": imports,
            "exports": exports, "problemas": problemas,
            "largos": sum(1 for x in exports if x["n_generaciones"])}


# --------------------------------------------------------------------------
#  Caminos: la parte que NO se puede hacer por subcadena del nombre
# --------------------------------------------------------------------------

def nombre_de(nombres, i):
    return nombres[i] if 0 <= i < len(nombres) else "<fuera>"


def camino_import(p, i, tope=128):
    """Camino completo de la importacion `i`, o None si no lleva a un paquete.

    Sube por la cadena de `outer` hasta llegar a un objeto cuyo outer es 0 (el
    paquete). **Es lo que la busqueda por subcadena no puede hacer**: `BoneAtom`
    aparece 153 veces en nuestro `Engine.u`, pero como `Core.BoneAtom`; el camino
    `Engine.AnimNode.BoneAtom` no existia. La subcadena dijo «esta» y era falso.
    """
    partes, j, n = [], i, 0
    while n < tope:
        n += 1
        partes.append(nombre_de(p["nombres"], p["imports"][j]["on"]))
        o = p["imports"][j]["outer"]
        if o == 0:
            return ".".join(reversed(partes))
        if o < 0:
            k = -o - 1
            if k >= len(p["imports"]):
                return None
            j = k
        else:
            return None          # el outer es una exportacion LOCAL: no es camino a un paquete
    return None


def camino_export(p, i, tope=128):
    """Camino completo de la exportacion `i`, con el nombre del paquete delante."""
    memo = p.setdefault("_memo_export", {})

    def sube(k, prof):
        if k in memo:
            return memo[k]
        if prof > tope:
            return None
        x = p["exports"][k]
        nm = nombre_de(p["nombres"], x["nm"])
        o = x["outer"]
        if o == 0:
            r = "%s.%s" % (p["nombre"], nm)
        elif o < 0:
            base = camino_import(p, -o - 1)
            r = "%s.%s" % (base, nm) if base else None
        else:
            padre = sube(o - 1, prof + 1)
            r = "%s.%s" % (padre, nm) if padre else None
        memo[k] = r
        return r

    return sube(i, 0)


def rutas_exportaciones(p):
    """El CONJUNTO de caminos completos de las exportaciones. Es el indice contra
    el que se resuelve una importacion."""
    fuera = set()
    for i in range(len(p["exports"])):
        c = camino_export(p, i)
        if c:
            fuera.add(c)
    return fuera


def clase_de(p, exp):
    """La clase de una exportacion.

    `ClassIndex`: >0 exportacion (1-based), <0 importacion, **0 = `UCLASS_INDEX`,
    o sea que la exportacion ES una `UClass`** (`UnLinker.h:29`). Tratar el 0
    como «sin clase» metia 1.414 exportaciones y 1,7 GB en un cajon equivocado.

    Y para una importacion se usa su **`ObjectName`, NO su `ClassName`**: un
    import que apunta a una clase trae ClassPackage=Core, ClassName=Class,
    ObjectName=AmbientSound -- o sea que ES la `UClass Engine.AmbientSound`.
    Leer el `ClassName` metio 1.711 de 1.711 exportaciones en el cajon "Class", y
    en todo el corpus 10,05 GB de 10,57 (el **95,09 %**).
    """
    ci = exp["ci"]
    if ci > 0 and ci - 1 < len(p["exports"]):
        return nombre_de(p["nombres"], p["exports"][ci - 1]["nm"])
    if ci < 0 and -ci - 1 < len(p["imports"]):
        return nombre_de(p["nombres"], p["imports"][-ci - 1]["on"])
    if ci == 0:
        return "Class (UCLASS_INDEX=0)"
    return "<fuera de rango>"
