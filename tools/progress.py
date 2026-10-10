#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CUANTO LLEVAMOS, EN FRACCION -- el medidor que faltaba desde el primer dia.

POR QUE EXISTE
--------------
Durante una semana entera, la unica forma de contestar «¿cuanto llevamos?» fue
mirar si `[SZ]` subia. **Y `[SZ]` sube, pero no es una fraccion.** Con eso no se
puede decidir si el camino converge: se ve que hay movimiento, no si hay avance.

Este script da las tres cifras que si lo dicen, y las guarda para ver la
tendencia:

    clases tocadas   / clases del paquete   ->  la fraccion del trabajo de CLASES
    objetos que faltan (censo, offline)     ->  el trabajo que queda por nombre
    delta desde la ultima corrida           ->  si CONVERGE o no

COMO MIDE LA FRACCION, y por que asi
------------------------------------
La sonda `[SZ]` imprime una linea por struct serializado, con su nombre. Contando
los `CrimeCraft.<Clase>` DISTINTOS que aparecen y dividiendo por las clases que el
paquete declara, sale la fraccion.

**Y usé dos medidas antes que esta, las dos malas, y conviene saber por que:**

1. **`bcstart` / tamaño del fichero.** Parecia lo natural -- `bcstart` es la
   posicion en el fichero. **Pero `bcstart` BAJA dentro de cada clase**: los
   miembros van en orden inverso en el fichero, asi que la secuencia sube y baja.
   Medido: de 16.580 lecturas, **15.499 bajan**. Como fraccion no vale.
2. **El ultimo objeto del log.** No es el maximo: la carga se para en el primer
   fallo, y el ultimo `[SZ]` puede estar por detras del punto mas lejano
   alcanzado.

La de clases es la que se sostiene, y ademas cuadra con el censo: **el censo dice
que falta por NOMBRE, esto dice por DONDE va.**

Uso:
    python tools/progress.py                      # el log de la ultima corrida
    python tools/progress.py --guardar            # y apunta la fila en el CSV
    python tools/progress.py <otro.log>
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from package import lee_paquete, camino_export, camino_import, rutas_exportaciones, nombre_de  # noqa: E402

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOG = os.path.join(RAIZ, "Launch.log")
CSV = os.path.join(RAIZ, "docs", "progreso.csv")
CONSUMIDOR = os.path.join(RAIZ, "CookedPC", "CrimeCraft.u")
NUESTROS = os.path.join(RAIZ, "Script")
DEL_JUEGO = os.path.join(RAIZ, "CookedPC")

# `[SZ] Function CrimeCraft.CCPawn:TakeDamage ver=576 ...`
RE_SZ = re.compile(r"\[SZ\]\s+\w+\s+CrimeCraft\.([A-Za-z_]\w*)")


def clases_del_paquete():
    p = lee_paquete(CONSUMIDOR)
    fuera = set()
    for i, x in enumerate(p["exports"]):
        if x["ci"] == 0:                      # UCLASS_INDEX: la exportacion ES una clase
            c = camino_export(p, i)
            if c:
                fuera.add(c.split(".")[-1])
    return fuera, p


def clases_tocadas(ruta_log):
    vistas = set()
    with open(ruta_log, "r", encoding="latin-1", errors="replace") as fh:
        for linea in fh:
            m = RE_SZ.search(linea)
            if m:
                vistas.add(m.group(1))
    return vistas


def faltantes():
    """El censo, en corto: cuantos objetos importa el contenido y no tenemos."""
    import glob
    prov = {}
    for pat in ("*.u", "*.upk"):
        for r in glob.glob(os.path.join(NUESTROS, pat)):
            try:
                q = lee_paquete(r)
            except Exception:
                continue
            prov[q["nombre"]] = rutas_exportaciones(q)
    ctrl = {}
    for pat in ("*.u", "*.upk"):
        for r in glob.glob(os.path.join(DEL_JUEGO, pat)):
            try:
                q = lee_paquete(r)
            except Exception:
                continue
            ctrl[q["nombre"]] = rutas_exportaciones(q)

    c = lee_paquete(CONSUMIDOR)

    def cuenta(idx):
        fuera = set()
        for i in range(len(c["imports"])):
            cam = camino_import(c, i)
            if cam is None:
                continue
            r = cam.split(".")[0]
            if r in idx and cam not in idx[r]:
                fuera.add(cam)
        return fuera

    return len(cuenta(prov) - cuenta(ctrl))


def main():
    # `global` va AQUI, al principio, y no junto a la asignacion: los `default=`
    # de mas abajo YA LEEN `NUESTROS`, y Python no admite usar un nombre antes de
    # declararlo global en el mismo ambito. Lo cazo el verificador de manuales.
    global NUESTROS, DEL_JUEGO, CONSUMIDOR, CSV
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", nargs="?", default=LOG)
    ap.add_argument("--guardar", action="store_true", help="apunta la fila en el CSV")
    # LAS CUATRO RUTAS SON ARGUMENTOS, con el defecto de este proyecto. Estaban
    # cableadas, y eso ataba la herramienta a ESTE arbol: en otro sitio no
    # encontraria ni el log, ni los paquetes, ni donde apuntar la fila.
    # **Un valor por defecto no es un fork.**
    ap.add_argument("--nuestros", default=NUESTROS, help="carpeta de paquetes que construimos")
    ap.add_argument("--juego", default=DEL_JUEGO, help="carpeta de paquetes del juego")
    ap.add_argument("--consumidor", default=CONSUMIDOR, help="el paquete del juego que se mide")
    ap.add_argument("--csv", default=CSV, help="donde apunta la fila con --guardar")
    args = ap.parse_args()

    NUESTROS, DEL_JUEGO = args.nuestros, args.juego
    CONSUMIDOR, CSV = args.consumidor, args.csv

    if not os.path.isfile(args.log):
        print("no existe el log: %s" % args.log)
        return 2

    total, _ = clases_del_paquete()
    vistas = clases_tocadas(args.log)
    vistas &= total                                  # solo las que el paquete declara
    faltan = faltantes()

    print("=" * 70)
    print("  PROGRESO -- cuanto llevamos, en fraccion")
    print("=" * 70)
    print("  log : %s" % os.path.relpath(args.log, RAIZ))
    print()
    print("  clases tocadas  : %d de %d   (%.1f %%)" % (len(vistas), len(total),
                                                        100.0 * len(vistas) / max(1, len(total))))
    print("  objetos que faltan (censo) : %d" % faltan)

    # La fila anterior, si la hay, para el delta. Sin ella esto es una foto; con
    # ella es una tendencia, que es lo que decide si el camino converge.
    previas = []
    if os.path.isfile(CSV):
        with open(CSV, "r", encoding="utf-8") as fh:
            for l in fh:
                p = l.strip().split(",")
                if len(p) == 4 and p[0] != "fecha":
                    previas.append(p)
    if previas:
        f = previas[-1]
        print()
        print("  la anterior (%s): clases %s/%s, faltan %s" % (f[0], f[1], f[2], f[3]))
        print("  delta           : clases %+d, faltan %+d"
              % (len(vistas) - int(f[1]), faltan - int(f[3])))

    if args.guardar:
        import datetime
        nuevo = not os.path.isfile(CSV)
        with open(CSV, "a", encoding="utf-8") as fh:
            if nuevo:
                fh.write("fecha,clases_tocadas,clases_totales,faltan\n")
            fh.write("%s,%d,%d,%d\n" % (datetime.date.today().isoformat(),
                                        len(vistas), len(total), faltan))
        print("\n  fila apuntada en %s" % os.path.relpath(CSV, RAIZ))

    print()
    print("  (la fraccion de CLASES es la que se sostiene: `bcstart` NO vale como")
    print("   medida -- baja dentro de cada clase, 15.499 de 16.580 lecturas.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
