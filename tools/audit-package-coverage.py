#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIDE CUANTO DE CADA PAQUETE SE PUEDE LEER -- en bytes, por clase de exportacion.

POR QUE EXISTE
--------------
El proyecto llevaba meses diciendo "el editor abre el mapa" sin una cifra de
COBERTURA. Se sabia que un export concreto se leia entero (la malla, el guion),
pero no QUE FRACCION DEL CORPUS representa eso. Y sin esa cifra no se puede
decidir que falta: todo parece igual de lejos.

Lo que mide, y por que se puede medir sin el motor
--------------------------------------------------
Un paquete UE3 es una CABECERA + TABLAS + los DATOS de cada exportacion, y las
tablas dicen donde empieza y cuanto mide cada una. Con eso:

  - bytes de cabecera y tablas            (se leen SIEMPRE: son indices)
  - bytes de datos, AGRUPADOS POR CLASE   (la clase sale de ClassIndex)

La clase se resuelve por la tabla de importaciones (ClassIndex negativo) o por
la de exportaciones (positivo). Y `OuterIndex` esta en +8, con la convencion
1-based (export n -> n+1), medido sobre CoverHint -> CCBotPawnDebugInfo.

Eso separa dos cosas que se confundian:
  - **estructura leida**: cabecera, nombres, imports, exports, dependencias
  - **carga util**: los bytes de los exports, y de que clase son

Uso:
    python tools/audit-package-coverage.py <dir o fichero> [--top N] [--solo .u]

Interpretacion: `--top` ordena las clases por bytes. Las clases de la cola son
las que no hemos tocado nunca, y el numero dice cuanto costarian.
"""
import os
import struct
import sys
from collections import defaultdict

# La consola de Windows es cp1252 y este informe lleva `⚠️`. Reventaba con
# UnicodeEncodeError JUSTO cuando tenia algo que decir -- el aviso de los
# registros largos, que es el caso para el que existe la herramienta.
# Medido el 5/10 sobre EntryLevel.ccmap: traceback en la linea del aviso.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

CABECERA = 0x9E2A83C1   # magia de un paquete UE3


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def u32(d, p):
    return struct.unpack_from("<I", d, p)[0]


def lee_cabecera(d):
    """Devuelve el resumen, o None si no es un paquete UE3."""
    if len(d) < 64 or u32(d, 0) != CABECERA:
        return None
    e = {}
    folder_len = i32(d, 12)
    p = 16 + folder_len
    e["PackageFlags"] = u32(d, p); p += 4
    e["NameCount"] = i32(d, p); p += 4
    e["NameOffset"] = i32(d, p); p += 4
    e["ExportCount"] = i32(d, p); p += 4
    e["ExportOffset"] = i32(d, p); p += 4
    e["ImportCount"] = i32(d, p); p += 4
    e["ImportOffset"] = i32(d, p); p += 4
    e["DependsOffset"] = i32(d, p); p += 4
    p += 16
    gen = i32(d, p); p += 4
    p += gen * 12
    e["EngineVersion"] = i32(d, p)
    return e


def lee_nombres(d, off, cuenta):
    nombres, p = [], off
    for _ in range(cuenta):
        n = i32(d, p); p += 4
        if n < 0:
            s = d[p:p - n * 2].decode("utf-16-le", "replace"); p += -n * 2
        else:
            s = d[p:p + n].decode("latin-1"); p += n
        p += 8
        nombres.append(s.rstrip("\x00"))
    return nombres


def lee_imports(d, off, cuenta):
    """28 B: ClassPackage(FName) ClassName(FName) OuterIndex ObjectName(FName)."""
    fuera, p = [], off
    for _ in range(cuenta):
        fuera.append({"cn": i32(d, p + 8), "on": i32(d, p + 20), "outer": i32(d, p + 16)})
        p += 28
    return fuera


def lee_exports(d, off, cuenta):
    """PASO VARIABLE -- y esto es lo que casi nadie espera.

    `FObjectExport::operator<<` (UnLinker.cpp:267) escribe, en este orden:

        ClassIndex SuperIndex OuterIndex ObjectName(8) ArchetypeIndex ObjectFlags
        SerialSize SerialOffset
        [LegacyComponentMap]        <- solo si Ver < VER_REMOVED_COMPONENT_MAP (543)
        ExportFlags
        GenerationNetObjectCount    <- TArray<INT>: VARIABLE
        PackageGuid(16) PackageFlags

    Con `GenerationNetObjectCount` VACIO el registro mide 68 B -- que es de donde
    sale el 68 que usan varias herramientas del proyecto. **Pero cuando trae N
    elementos mide 68 + 4N, y todo lo que viene detras se desplaza.**

    Medido sobre CrimeCraft.u: 65 registros traen 1 elemento. Leer con paso fijo
    deja la tabla 260 B corta (65 x 4) -- y ese es exactamente el desajuste que
    se midio contra `DependsOffset`. Con paso variable la tabla acaba EN
    `DependsOffset` clavado: es la validacion de que el paso es este.

    Con `Ar.Ver()=576` la puerta del mapa NO se cumple (576 >= 543), asi que ese
    campo no se escribe y no hay que leerlo.
    """
    fuera, p = [], off
    for _ in range(cuenta):
        n = max(0, min(i32(d, p + 44), 1 << 20))     # cordura: una cuenta absurda no desplaza
        fuera.append({"ci": i32(d, p), "outer": i32(d, p + 8), "nombre": i32(d, p + 12),
                      "tam": i32(d, p + 32), "off": i32(d, p + 36), "n_generaciones": n})
        p += 68 + 4 * n
    return fuera


def nombre_de(nombres, i):
    return nombres[i] if 0 <= i < len(nombres) else "<?>"


def clase_de(exp, exports, imports, nombres):
    """ClassIndex: >0 exportacion (1-based), <0 importacion (-1-based).

    `ClassIndex == 0` NO es "sin clase": esta definido en UnLinker.h:29 como
    `UCLASS_INDEX`, o sea que el export ES una `UClass`. Llamarlo "<sin clase>"
    metia 1414 exports y 1,7 GB en un cajon equivocado.
    """
    ci = exp["ci"]
    if ci > 0 and ci - 1 < len(exports):
        return nombre_de(nombres, exports[ci - 1]["nombre"])
    if ci < 0 and -ci - 1 < len(imports):
        # ⚠️ EL `ObjectName` DEL IMPORT, NO SU `ClassName`.
        #
        # Un import que apunta a una CLASE trae: ClassPackage=Core,
        # ClassName=Class, ObjectName=AmbientSound -- o sea que ES la UClass
        # `Engine.AmbientSound`, cuya clase es `Class` y cuyo NOMBRE es el que
        # nos interesa. Medido sobre EntryLevel.ccmap: leer `ClassName` metia
        # 1711 de 1711 exports en el cajon "Class", y en todo el corpus 10,05
        # GB de 10,57 (el 95,09%) -- un numero que parece dato y es un error.
        return nombre_de(nombres, imports[-ci - 1]["on"])
    if ci == 0:
        return "Class (UCLASS_INDEX=0)"
    return "<fuera de rango>"


def analiza(ruta):
    d = open(ruta, "rb").read()
    e = lee_cabecera(d)
    if e is None:
        return None
    nombres = lee_nombres(d, e["NameOffset"], e["NameCount"])
    imports = lee_imports(d, e["ImportOffset"], e["ImportCount"])
    exports = lee_exports(d, e["ExportOffset"], e["ExportCount"])

    # El fin de la tabla NO se calcula con 68 fijos: se mide sumando los pasos.
    # Y se comprueba contra DependsOffset, porque si no cuadra el resto sobra.
    fin_exports = e["ExportOffset"] + sum(68 + 4 * x["n_generaciones"] for x in exports)
    fin_tablas = max(fin_exports, e["ImportOffset"] + e["ImportCount"] * 28, e["NameOffset"])
    cuadra = (fin_exports == e["DependsOffset"])
    por_clase = defaultdict(lambda: [0, 0])   # clase -> [bytes, n exports]
    cubierto, malos = 0, 0
    for x in exports:
        # UN REGISTRO QUE NO CUADRA NO SE SUMA. Medido en CrimeCraft.u: 133 de
        # 185.659 (el 0,07%), todos en el tramo [108227, 108467]. Sumarlos daba
        # "5.940.190.696 bytes" en un fichero de 366.986.751 -- un 1618 %, que
        # es como se descubrio que habia registros que no son lo que parecen.
        # Se cuentan y se declaran, que es lo que hace un instrumento honesto.
        if not (0 <= x["off"] < len(d) and 0 <= x["tam"] < len(d)
                and 0 <= x["nombre"] < e["NameCount"] and x["off"] + x["tam"] <= len(d)):
            malos += 1
            continue
        c = clase_de(x, exports, imports, nombres)
        por_clase[c][0] += x["tam"]
        por_clase[c][1] += 1
        cubierto += x["tam"]
    largos = sum(1 for x in exports if x["n_generaciones"])
    return {"ruta": ruta, "bytes": len(d), "cab": e, "tablas": fin_tablas,
            "por_clase": por_clase, "datos": cubierto, "malos": malos,
            "cuadra": cuadra, "largos": largos,
            "nv": e["EngineVersion"], "pkgflags": e["PackageFlags"]}


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    raiz = sys.argv[1]
    tope = 15
    solo = None
    for k, a in enumerate(sys.argv):
        if a == "--top":
            tope = int(sys.argv[k + 1])
        if a == "--solo":
            solo = sys.argv[k + 1]

    rutas = []
    if os.path.isfile(raiz):
        rutas = [raiz]
    else:
        for base, _, fs in os.walk(raiz):
            for f in fs:
                if f.lower().endswith((".u", ".ccmap", ".ccpk")) and (solo is None or f.lower().endswith(solo)):
                    rutas.append(os.path.join(base, f))
    rutas.sort()

    total = defaultdict(lambda: [0, 0])     # clase global -> [bytes, n]
    gran_total = tablas_total = datos_total = 0
    malos_total = 0
    largos_total = 0
    leidos = fallos = 0

    print("=" * 74)
    print("  COBERTURA DE PAQUETES -- que fraccion se puede leer, por clase")
    print("=" * 74)
    print("  paquetes encontrados: %d" % len(rutas))

    for r in rutas:
        try:
            a = analiza(r)
        except Exception as ex:
            print("  !! %-58s  NO SE PUDO LEER: %s" % (os.path.basename(r), ex))
            fallos += 1
            continue
        if a is None:
            print("  -- %-58s  no es un paquete UE3 (magia distinta)" % os.path.basename(r))
            fallos += 1
            continue
        leidos += 1
        gran_total += a["bytes"]
        tablas_total += a["tablas"]
        datos_total += a["datos"]
        malos_total += a["malos"]
        largos_total += a["largos"]
        if not a["cuadra"]:
            print("  ⚠️  %-52s la tabla NO acaba en DependsOffset" % os.path.basename(r))
        for c, (b, n) in a["por_clase"].items():
            total[c][0] += b
            total[c][1] += n

    print("  leidos: %d   no leidos: %d" % (leidos, fallos))
    if leidos == 0:
        return 0
    print()
    print("  bytes totales      %14s  100,0%%" % "{:,}".format(gran_total))
    print("  cabecera + tablas  %14s  %5.1f%%   <- se leen SIEMPRE" % (
        "{:,}".format(tablas_total), 100.0 * tablas_total / gran_total))
    print("  datos de exports   %14s  %5.1f%%   <- depende de la CLASE" % (
        "{:,}".format(datos_total), 100.0 * datos_total / gran_total))
    resto = gran_total - tablas_total - datos_total
    if resto:
        print("  sin atribuir       %14s  %5.1f%%" % ("{:,}".format(resto), 100.0 * resto / gran_total))
    if largos_total:
        print()
        print("  ⚠️  %d registros traen `GenerationNetObjectCount` NO vacio, o sea que" % largos_total)
        print("      miden 68+4N y NO 68. Leer la tabla con paso FIJO de 68 desplaza")
        print("      todo lo que viene detras, 4 B por cada uno -- y los valores")
        print("      desplazados PARECEN buenos. Medido en CrimeCraft.u: 65 largos,")
        print("      65x4 = 260 B, que es EXACTAMENTE lo que la tabla quedaba corta.")
        print("      Este lector usa paso variable y lo valida contra DependsOffset.")
    print()
    print("=" * 74)
    print("  LAS %d CLASES QUE MAS BYTES OCUPAN" % tope)
    print("=" * 74)
    print("  %-32s %14s %7s %8s" % ("clase", "bytes", "del total", "n"))
    for c, (b, n) in sorted(total.items(), key=lambda kv: -kv[1][0])[:tope]:
        print("  %-32s %14s %6.2f%% %8d" % (c, "{:,}".format(b), 100.0 * b / gran_total, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
