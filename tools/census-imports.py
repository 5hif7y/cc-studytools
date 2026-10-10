#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DE MINA A LISTA: que importa un paquete, y que de eso NO existe en lo nuestro.

POR QUE EXISTE
--------------
El proyecto lleva meses cayendose de uno en uno. Cada corrida destapa **un**
objeto que falta, y detras hay otro. La causa esta dicha en el propio proyecto:
**`CreateImport` devuelve NULL CALLANDO** -- un objeto que falta no avisa. Y
cuando el que falta es un struct o un enum, ademas **cambia el tamano leido**, y
la carga se desincroniza.

Este instrumento cambia eso: resuelve **las 1.992 importaciones de un paquete de
una pasada**, offline, y da la lista entera ordenada por peligro.

COMO RESUELVE, Y POR QUE NO POR SUBCADENA
------------------------------------------
Por **cadena de `outer` completa**. Esta medido y documentado que la subcadena
miente: `BoneAtom` aparece **153 veces** en nuestro `Engine.u`, pero como
`Core.BoneAtom`; el camino `Engine.AnimNode.BoneAtom` no existia. La busqueda por
subcadena dijo «esta» y era falso.

EL CONTROL, QUE ES LO QUE LO HACE CREIBLE
------------------------------------------
**Diferencial, y no es lo que parece.** El control NO es «el juego resuelve
1.992/1.992» -- eso es falso: la familia `noexport` (`Core.Class`, `Core.Package`,
`Engine.StaticMesh`) **no resuelve en ninguno de los dos**, porque no se exporta,
se resuelve nativamente.

El control de verdad: se corre **el mismo censo con los paquetes del juego** como
proveedores. Lo que salga ahi **es ruido de fondo por construccion** -- el juego
es internamente coherente, se envio asi. Se resta. Lo que queda es la brecha real.

Medido el 5/10 sobre `CrimeCraft.u`: control 25, contra lo nuestro 196,
**diferencia real 171**. El documento tenia 167 medidos por subcadena: dos metodos
independientes coinciden en ~170.

Uso:
    python tools/census-imports.py                       # CrimeCraft.u contra lo nuestro
    python tools/census-imports.py --consumidor X.ccmap  # cualquier paquete
    python tools/census-imports.py --todos               # la lista entera, sin cortar
"""
import argparse
import collections
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from package import lee_paquete, camino_import, rutas_exportaciones, nombre_de  # noqa: E402

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Los proveedores por defecto: los paquetes que CONSTRUIMOS, y los del juego
# como control.
NUESTROS = os.path.join(RAIZ, "Script")
DEL_JUEGO = os.path.join(RAIZ, "CookedPC")
CONSUMIDOR = os.path.join(DEL_JUEGO, "CrimeCraft.u")

# Grado de peligro, por la CLASE del objeto importado.
#
# Los dos primeros estan MEDIDOS, cada uno con su caso:
#   ScriptStruct -> UStructProperty::Link hace Ar.Preload(Struct) SIN guarda y la
#                   linea siguiente es Struct->PropertiesSize. Un struct nulo no
#                   degrada: MATA.  (AdditionalHitInfo, 4/10)
#   Enum         -> UByteProperty::SerializeItem decide por `Enum == NULL` y lee
#                   UN BYTE donde el fichero tiene OCHO. Desfase de 7 y a partir
#                   de ahi todo es basura.  (ECoverHint, 5/10)
GRADO_1 = {"ScriptStruct", "Enum"}
# El grado 2 es el mismo riesgo una capa mas arriba: la PROPIEDAD cuyo tipo es
# uno de los de arriba. No esta medido; se marca aparte para no confundirlo.
GRADO_2 = {"StructProperty", "ByteProperty"}


def carga_proveedores(carpeta, patrones=("*.u", "*.upk", "*.ccpk")):
    fuera = {}
    for pat in patrones:
        for r in sorted(glob.glob(os.path.join(carpeta, pat))):
            try:
                p = lee_paquete(r)
            except Exception:
                continue
            fuera[p["nombre"]] = p
    return fuera


def indice(proveedores):
    return {k: rutas_exportaciones(v) for k, v in proveedores.items()}


def censo(consumidor, idx_proveedores):
    """Devuelve (faltantes, raices, sin_camino, total_que_apunta_a_lo_nuestro).

    `faltantes` es una lista de (camino, clase_del_objeto).
    """
    faltan, raices, sin_camino = [], collections.Counter(), 0
    for i in range(len(consumidor["imports"])):
        c = camino_import(consumidor, i)
        if c is None:
            sin_camino += 1
            continue
        raiz = c.split(".")[0]
        raices[raiz] += 1
        if raiz in idx_proveedores and c not in idx_proveedores[raiz]:
            imp = consumidor["imports"][i]
            clase = "%s.%s" % (nombre_de(consumidor["nombres"], imp["cp"]),
                               nombre_de(consumidor["nombres"], imp["cn"]))
            faltan.append((c, clase))
    total = sum(raices[k] for k in idx_proveedores)
    return faltan, raices, sin_camino, total


def grado(clase):
    nombre = clase.split(".")[-1]
    if nombre in GRADO_1:
        return 1
    if nombre in GRADO_2:
        return 2
    return 3


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--consumidor", default=CONSUMIDOR)
    ap.add_argument("--nuestros", default=NUESTROS, help="carpeta de paquetes que construimos")
    ap.add_argument("--control", default=DEL_JUEGO, help="carpeta de paquetes del juego (control)")
    ap.add_argument("--sin-control", action="store_true")
    ap.add_argument("--todos", action="store_true", help="no cortar la lista")
    ap.add_argument("--tope", type=int, default=40)
    args = ap.parse_args()

    cons = lee_paquete(args.consumidor)
    print("=" * 74)
    print("  CENSO DE IMPORTACIONES -- que falta en lo nuestro, por cadena de outer")
    print("=" * 74)
    print("  consumidor : %s  (%d importaciones, %d exportaciones, %s)"
          % (os.path.relpath(args.consumidor, RAIZ), len(cons["imports"]),
             len(cons["exports"]), cons["cabecera"]["FileVersion"]))
    if cons["problemas"]:
        print("  !! EL CONSUMIDOR NO CUADRA: %s" % "; ".join(cons["problemas"]))
        return 2

    prov = carga_proveedores(args.nuestros)
    idx = indice(prov)
    print("  nuestros   : %d paquetes" % len(prov))

    faltan, raices, sin_camino, total = censo(cons, idx)
    print("\n  raices referenciadas: %s"
          % "  ".join("%s %d" % (k, v) for k, v in raices.most_common()))
    if sin_camino:
        print("  (importaciones cuyo outer es una exportacion local, no un paquete: %d)" % sin_camino)
    print("  importaciones que apuntan a paquetes nuestros: %d" % total)

    ruido = set()
    if not args.sin_control:
        prov_ctrl = carga_proveedores(args.control)
        idx_ctrl = indice(prov_ctrl)
        faltan_ctrl, _, _, _ = censo(cons, idx_ctrl)
        ruido = set(faltan_ctrl)
        print("\n  CONTROL -- los paquetes del JUEGO (%d) como proveedores:" % len(prov_ctrl))
        print("     no resuelven: %d   <- ruido de fondo por construccion (noexport)" % len(ruido))
        if ruido:
            for k, v in collections.Counter(c for _, c in faltan_ctrl).most_common(6):
                print("        %-34s %d" % (k, v))
        if not ruido:
            print("     !! el control da CERO: o el juego no es coherente, o los paquetes")
            print("        del control no son los que el consumidor importa. Revisar ANTES de creer la lista.")

    real = [x for x in faltan if x not in ruido]
    print("\n  contra lo nuestro no resuelven : %d" % len(faltan))
    print("  DIFERENCIA REAL                : %d" % len(real))
    if not args.sin_control:
        print("  (el documento tenia 167 por subcadena -- dos metodos coinciden en ~170)")

    por_grado = collections.defaultdict(list)
    for c, cl in real:
        por_grado[grado(cl)].append((c, cl))

    títulos = {
        1: "GRADO 1 -- CAMBIA EL TAMANO LEIDO (los dos medidos: AdditionalHitInfo y ECoverHint)",
        2: "GRADO 2 -- la PROPIEDAD cuyo tipo es de grado 1 (mismo riesgo, una capa mas arriba; NO medido)",
        3: "GRADO 3 -- referencia NULL: degrada, o aborta MAS TARDE y lejos del sitio",
    }
    for g in (1, 2, 3):
        lista = sorted(por_grado.get(g, []))
        if not lista:
            continue
        print("\n" + "=" * 74)
        print("  %s" % títulos[g])
        print("  (%d objetos)" % len(lista))
        print("=" * 74)
        corte = lista if args.todos else lista[:args.tope]
        for c, cl in corte:
            print("    %-34s %s" % (cl, c))
        if len(lista) > len(corte):
            print("    ... y %d mas (--todos para verlos)" % (len(lista) - len(corte)))

    print("\n" + "-" * 74)
    print("  por clase del objeto, entero:")
    for k, v in collections.Counter(c for _, c in real).most_common(20):
        print("    %-34s %d" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
