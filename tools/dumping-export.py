#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LOS BYTES CRUDOS DE UNA EXPORTACION -- para poder decir que es cada uno.

POR QUE EXISTE
--------------
`cc-studytools/tools/package.py` dice DONDE esta cada objeto (`SerialOffset`, `SerialSize`) y
`probe-properties.py` sabe LEER un flujo de propiedades taggeadas. Pero entre
los dos falta lo mas simple y lo que mas veces hace falta: **ver los bytes**.

Y hace falta por una razon concreta, medida el 8/10: la comparacion de la clase
`UIDynamicFieldProvider` entre el juego y lo nuestro **coincidia campo a campo**,
y aun asi el motor dice

    Serial size mismatch: Got 12, Expected 16

**Un `Got`/`Expected` no dice QUE campo falta.** Dice que faltan cuatro bytes y
nada mas. Para saber cuales, hay que mirar los bytes que el paquete trae de
verdad. Eso es todo lo que hace esto: los ensena, agrupados y en hexadecimal y
decimal, sin interpretarlos.

QUE SIGNIFICA `Got` Y `Expected` -- LEIDO DEL CODIGO, NO SUPUESTO
-----------------------------------------------------------------
El mensaje sale de `UnLinker.cpp:3930` y la cadena de `Core.int:64`:

    if( Tell()-Export.SerialOffset != Export.SerialSize )
        appErrorf( LocalizeSecure(LocalizeError(TEXT("SerialSize"),TEXT("Core")),
            *Object->GetFullName(),        // <- el nombre
            Tell()-Export.SerialOffset,    // <- se imprime en "Got"
            Export.SerialSize ) );         // <- se imprime en "Expected"

    Core.int:  SerialSize=`~: Serial size mismatch: Got `~, Expected `~

O sea:

    Got      = lo que NOSOTROS hemos consumido leyendo el objeto
    Expected = lo que el PAQUETE dice que el objeto mide

**`Got < Expected` quiere decir que LEEMOS DE MENOS**: nuestra clase serializa
mas corta que la del juego. Al reves de como se leyo el 8/10.

USO
---
    python -I tools/dumping-export.py <paquete> <subcadena-del-nombre>
        --todos     todas las exportaciones de esa clase, no solo la primera
        --contexto  N bytes antes y despues (para ver de quien son los vecinos)

    python -I tools/dumping-export.py .../UIScene_FrontEnd.ccpk UIDynamicFieldProvider

SOBRE EL EJEMPLO, que estaba MAL
--------------------------------
Aqui ponia `UIDynamicFieldProvider_2`. **Ese nombre no existe en el paquete**: la
busqueda da 0, y sin el sufijo da 30. Un ejemplo del manual que no corre es un
manual que no se puede seguir -- lo cazo `tools/verifica-manuales.py`, y es la
misma familia que el `python tools/package.py <fichero>` de su manual, que
documentaba una orden de linea de ordenes que no existe.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import package  # noqa: E402


def vuelca(d, off, tam, etiqueta):
    """Los `tam` bytes de `off`, en lineas de 16, con hex y decimal."""
    print("  %s  offset=%d  tam=%d" % (etiqueta, off, tam))
    for i in range(0, tam, 16):
        trozo = d[off + i:off + i + 16]
        hexa = " ".join("%02X" % b for b in trozo)
        deci = " ".join("%3d" % b for b in trozo)
        print("    +%-3d  %-47s  %s" % (i, hexa, deci))


def lee_entero(d, off, tam):
    """El primer entero little-endian de la exportacion, que es lo que casi siempre es."""
    if tam >= 4:
        v = int.from_bytes(d[off:off + 4], "little", signed=True)
        return "%d / 0x%08X" % (v, v & 0xFFFFFFFF)
    return "--"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("nombre", help="subcadena del nombre del objeto")
    ap.add_argument("--todos", action="store_true",
                    help="todas las coincidencias, no solo la primera")
    ap.add_argument("--contexto", type=int, default=0,
                    help="bytes de contexto antes/despues")
    a = ap.parse_args()

    p = package.lee_paquete(a.package, estricto=True)
    with open(a.package, "rb") as fh:
        d = fh.read()

    # `camino_export` va por exportacion, no por el set: hace falta el INDICE para
    # llegar a `SerialOffset`, y el set de `rutas_exportaciones` lo pierde.
    aciertos = []
    for i in range(len(p["exports"])):
        r = package.camino_export(p, i)
        if r and a.nombre.lower() in r.lower():
            aciertos.append((i, r))

    if not aciertos:
        print("NINGUNA exportacion contiene %r" % a.nombre)
        print("  (el paquete tiene %d exportaciones)" % len(p["exports"]))
        return 1

    print("== %s ==" % p["ruta"])
    print("   %d exportaciones, %d coinciden con %r"
          % (len(p["exports"]), len(aciertos), a.nombre))
    print()

    for i, ruta in aciertos[:1 if not a.todos else len(aciertos)]:
        e = p["exports"][i]
        clase = package.clase_de(p, e)
        off, tam = e["off"], e["tam"]
        print("  export #%d  %s" % (i + 1, ruta))
        print("    clase       = %s" % clase)
        print("    SerialOffset= %d" % off)
        print("    SerialSize  = %d      <-- esto es lo que imprime `Expected`" % tam)
        print("    primeros 4 B= %s  <-- el prefijo del flujo taggeado" % lee_entero(d, off, tam))
        print()
        if a.contexto:
            vuelca(d, max(0, off - a.contexto), a.contexto, "ANTES")
        vuelca(d, off, tam, "OBJETO")
        if a.contexto:
            vuelca(d, off + tam, a.contexto, "DESPUES")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
