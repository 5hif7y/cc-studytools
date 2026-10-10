#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EL CENSO DE TODO EL CORPUS DE CRIMECRAFT: los `.u`, los `.ccmap` y los `.ccpk`.

QUE MIDE, Y DE DONDE SALE LA DEFINICION
---------------------------------------
La columna `Porcentaje entendido` **NO se inventa aqui**: es la misma que usa
`tools/census-ccmap.py` desde el 5/10 y que ya esta validada alli.

    entendido_pct = 100 * (bytes de las exportaciones cuya CLASE resuelve
                           nuestro SDK) / (bytes de todas las exportaciones)

O sea: **de los datos del paquete, que fraccion sabemos LEER** -- porque sabemos de
que clase es. Un export cuya clase no esta en nuestro `Engine.u` no se puede
interpretar aunque sus bytes esten ahi.

POR QUE EXISTE ESTE Y NO VALE `census-ccmap.py`
----------------------------------------------
`census-ccmap.py` esta atado a `.ccmap` (su recorrido filtra por esa extension). La
METRICA es generica; el recorrido no. Y el proyecto tiene **tres** corpus, no uno:

    .u       12   los paquetes de codigo del juego (Engine.u, CrimeCraft.u, ...)
    .ccmap  218   los mapas
    .ccpk   320   los paquetes de contenido

Aqui se reusa el mismo `census-imports.py` -- cargado POR RUTA, para que el guion
del nombre no obligue a copiar nada -- y las mismas funciones `mide()`, `pct()`,
`clave_de_clase()` y `resuelve()`. **No hay una segunda definicion de «entendido».**

LO QUE ESTE CENSO **NO** DICE, Y HAY QUE DECIRLO
------------------------------------------------
**El porcentaje mide CLASES resueltas, no CONTENIDO comprendido.** Un `.ccmap` al
100 % significa que sabemos de que clase es cada exportacion -- **no** que sepamos
interpretar todos sus campos ni que el mapa cargue. Las dos cosas se han medido por
separado muchas veces en este proyecto, y confundirlas es el error que el §63
documenta.

**Y es una foto del SDK de HOY.** Sube cuando se reponen clases. La fecha va en cada
CSV justamente por eso: un porcentaje sin fecha es una cifra vieja esperando a que
alguien la lea mal.

USO
---
    python -I tools/census-corpus.py              # los tres CSV
    python -I tools/census-corpus.py --tipo ccpk  # solo uno
    python -I tools/census-corpus.py --limite 5   # corrida parcial, no escribe
    python -I tools/census-corpus.py --raiz <dir> # OTRO corpus

LA RAIZ, y por que dejo de estar cableada
-----------------------------------------
Estaba cableada a `CrimeCraft/CrimeCraftGame/CookedPC`, que es la raiz de ESTE
proyecto. En un repo publicado esa carpeta no existe, y el recorrido no falla:
**devuelve cero ficheros y un censo vacio, que se lee como un dato.** Por eso la
raiz es un argumento Y hay una comprobacion que aborta si no encuentra nada --
un cero silencioso es peor que un error.

El DEFECTO sigue siendo el de siempre, asi que las corridas de este proyecto no
cambian ni un byte. **Un valor por defecto no es un fork.**
"""

import argparse
import csv
import datetime
import importlib.util
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.normpath(os.path.join(AQUI, ".."))
sys.path.insert(0, AQUI)

from package import lee_paquete  # noqa: E402


def _carga_censo_imports():
    """Carga `tools/census-imports.py` POR RUTA: el guion no es un identificador."""
    spec = importlib.util.spec_from_file_location(
        "censo_imports", os.path.join(AQUI, "census-imports.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _carga_censo_ccmap():
    """Carga `tools/census-ccmap.py` POR RUTA, y **para reusar SU metrica**.

    Importarlo y no copiar `mide()`/`pct()`/`clave_de_clase()` es deliberado: dos
    copias de la misma definicion divergen, y este proyecto ya pago eso -- hubo
    **seis copias** del lector de la tabla de exportaciones y tres formas distintas
    de paso. Ver la cabecera de `cc-studytools/tools/package.py`.
    """
    spec = importlib.util.spec_from_file_location(
        "censo_ccmap", os.path.join(AQUI, "census-ccmap.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CI = _carga_censo_imports()
CC = _carga_censo_ccmap()

CENSO = os.path.join(RAIZ, "CrimeCraft", "CrimeCraftGame", "CookedPC")

TIPOS = {"u": ".u", "ccmap": ".ccmap", "ccpk": ".ccpk"}

TITULO = {"u": "los paquetes de codigo", "ccmap": "los mapas",
          "ccpk": "los paquetes de contenido"}


def rutas_de(raiz, ext):
    fuera = []
    for base, dirs, ficheros in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in ficheros:
            if f.lower().endswith(ext):
                fuera.append(os.path.join(base, f))
    return sorted(fuera)


def mide_uno(ruta, idx):
    """(tam, pct_entendido, exports, clases, desconocidas, nota)."""
    tam = os.path.getsize(ruta)
    try:
        p = lee_paquete(ruta)
    except Exception as exc:
        return tam, None, 0, 0, 0, "EXCEPCION al leer: %s" % str(exc)[:110]

    if p["problemas"]:
        return tam, None, len(p["exports"]), 0, 0, \
            "las tablas NO cuadran: %s" % "; ".join(p["problemas"])[:110]

    claves = [CC.clave_de_clase(p, e) for e in p["exports"]]
    a = CC.mide(p["exports"], claves, idx)
    pct = CC.pct(a["bytes_ok"], a["bytes_tot"])

    nota = ""
    if a["desconocidas"]:
        nota = "%d de %d clases sin resolver" % (a["desconocidas"], a["clases"])
    return tam, pct, len(p["exports"]), a["clases"], a["desconocidas"], nota


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tipo", choices=sorted(TIPOS), action="append",
                    help="solo estos tipos (por defecto, los tres)")
    ap.add_argument("--limite", type=int, default=0, help="corta tras N ficheros, sin escribir")
    ap.add_argument("--raiz", default=CENSO,
                    help="raiz del corpus (por defecto, la del juego en este proyecto)")
    # EL SDK CONTRA EL QUE SE MIDE. Sin esto se mide contra NADA: el defecto
    # apunta a la raiz del guion, y si ahi no hay paquetes el censo da "0
    # paquetes nuestros de 0 candidatos" y sigue, con cifras que parecen un dato.
    # Medido: eso es exactamente lo que paso al mover el guion a cc-studytools/.
    ap.add_argument("--nuestros", default=CI.NUESTROS,
                    help="carpeta de paquetes que construimos (el SDK)")
    ap.add_argument("--control", default=CI.DEL_JUEGO,
                    help="carpeta de paquetes del juego, para el control")
    a = ap.parse_args()
    CI.NUESTROS, CI.DEL_JUEGO = a.nuestros, a.control

    # LA COMPROBACION QUE IMPIDE EL CERO SILENCIOSO. Sin ella, una raiz que no
    # existe -- o que existe y no tiene paquetes -- recorre cero ficheros y
    # escribe tres CSV vacios, que es un resultado con la forma de un dato.
    if not os.path.isdir(a.raiz):
        print("ERROR: la raiz del corpus no existe: %s" % a.raiz)
        print("       (--raiz <dir>  para indicar otra)")
        return 2

    tipos = a.tipo or sorted(TIPOS)

    print("cargando el indice de NUESTRO SDK ...")
    prov, cand, malos = CC.proveedores(CI.NUESTROS)
    idx = CI.indice(prov)
    print("   %d paquetes nuestros de %d candidatos" % (len(prov), len(cand)))

    hoy = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    for t in tipos:
        rutas = rutas_de(a.raiz, TIPOS[t])
        print()
        print("== .%s -- %s: %d ficheros" % (t, TITULO[t], len(rutas)))

        # Un tipo sin ficheros NO es un censo de cero: es que no se miro donde
        # era. Se dice y se sigue con los otros tipos, que si pueden tenerlos.
        if not rutas:
            print("   !! cero ficheros .%s bajo %s"
                  % (t, os.path.relpath(a.raiz, RAIZ)))
            print("      no es un censo de cero: es que no estan ahi")
            continue

        filas = []
        for i, r in enumerate(rutas, 1):
            if a.limite and i > a.limite:
                break
            tam, pct, nex, ncl, ndesc, nota = mide_uno(r, idx)
            filas.append([os.path.relpath(r, RAIZ).replace("\\", "/"), tam, pct, nota])
            if i % 40 == 0 or i == len(rutas):
                print("   %d/%d" % (i, len(rutas)))

        if a.limite:
            continue

        destino = os.path.join(RAIZ, "docs", "crimecraft-%s.csv" % t)
        with open(destino, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Archivo", "Tamaño", "Porcentaje entendido", "Nota"])
            for nombre, tam, pct, nota in filas:
                w.writerow([nombre, tam, "" if pct is None else "%.1f" % pct, nota])

        medidos = [f[2] for f in filas if f[2] is not None]
        print("   -> %s   (%d filas, %d con porcentaje, media %.1f %%)"
              % (os.path.relpath(destino, RAIZ), len(filas), len(medidos),
                 sum(medidos) / len(medidos) if medidos else 0.0))
        print("      medido el %s -- el porcentaje SUBE cuando se reponen clases" % hoy)

    return 0


if __name__ == "__main__":
    sys.exit(main())
