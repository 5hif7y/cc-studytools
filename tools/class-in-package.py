#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QUE HAY DENTRO DE UNA CLASE, LEIDO DEL PAQUETE -- para poder escribir su `.uc`.

POR QUE EXISTE
--------------
El proyecto repone clases que el `Engine.u` del juego tiene y el nuestro no. El
metodo es: escribir el `.uc` y correr `make` (que genera `EngineClasses.h`, ~40 s).
**Pero para escribir el `.uc` hay que saber que hay dentro.**

Y no siempre se puede sacar del guion exportado: `UELib` **no exporta las clases
sin cuerpo**, asi que las `noexport` y las que solo tienen miembros nativos **no
tienen `.uc` en `uscript_juego_Engine/`**. `DiffObjectData` es una de esas.

Lo que SI esta siempre es **el paquete**. Y de la tabla de exportaciones sale el
arbol entero de la clase: sus structs anidados, sus propiedades, sus funciones, y
**de que CLASE es cada uno** -- que es de donde sale si una propiedad es `int`,
`float`, `array<...>`, un `struct` o una referencia.

LA REGLA QUE HAY QUE ENTENDER
-----------------------------
En UE3 **los miembros de una clase son EXPORTACIONES cuyo `Outer` es la clase**.
No hay que deserializar nada para ver la lista: basta con mirar quien apunta a
quien. Y `ClassIndex` dice de que clase es cada miembro:

    ClassIndex == 0    -> el miembro ES una UClass
    ClassIndex  > 0    -> exportacion (1-based) -- p.ej. `StructProperty`
    ClassIndex  < 0    -> importacion (1-based) -- su ObjectName es la clase

Y ojo con la convencion del `OuterIndex`, que es **la misma en las dos tablas**:
`> 0` exportacion, `< 0` importacion, `0` la raiz.

LO QUE ESTA HERRAMIENTA **NO** HACE, y hay que decirlo
------------------------------------------------------
**No deduce el TIPO EXACTO de una `StructProperty` ni de una `ObjectProperty`**
-- eso vive en los datos de la propiedad, no en la tabla. Para eso:
`tools/probe-properties.py`, que lee los `FPropertyTag`.
Lo que da aqui es **la forma** (cuantos miembros, de que genero, en que orden),
que es lo que hace falta para saber **que** hay que reponer.

Uso:
    python tools/class-in-package.py <paquete> <NombreDeLaClase> [--hondo N]
    python tools/class-in-package.py .../Engine.u DiffObject
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from package import lee_paquete, camino_export, clase_de, nombre_de  # noqa: E402

# Como se escribe cada clase-de-propiedad en UnrealScript. Se busca por el
# NOMBRE SUELTO, sin el paquete, porque el paquete es `Core` casi siempre.
TIPO_UC = {
    "IntProperty": "int", "FloatProperty": "float", "BoolProperty": "bool",
    "ByteProperty": "byte", "StrProperty": "string", "NameProperty": "name",
    "ObjectProperty": "Object", "ClassProperty": "class<>",
    "ComponentProperty": "Component", "InterfaceProperty": "Interface",
    "DelegateProperty": "delegate", "StructProperty": "struct <>",
    "ArrayProperty": "array<>", "MapProperty": "map<>",
}


def hijos(p, k):
    """Las exportaciones cuyo `Outer` es la exportacion `k` (OuterIndex es 1-based)."""
    return [i for i, x in enumerate(p["exports"]) if x["outer"] == k + 1]


def describe(p, i):
    x = p["exports"][i]
    nombre = nombre_de(p["nombres"], x["nm"])
    clase = clase_de(p, x)
    sufijo = ""
    if x["ci"] == 0:
        sufijo = "  <- ES UNA CLASE"
    elif clase in TIPO_UC:
        sufijo = "  -> var %s" % TIPO_UC[clase]
    elif clase.endswith("Property"):
        sufijo = "  -> var <?> (%s)" % clase
    return i, nombre, clase, sufijo


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("clase")
    ap.add_argument("--hondo", type=int, default=2)
    args = ap.parse_args()

    p = lee_paquete(args.package)
    if p["problemas"]:
        print("!! el paquete NO cuadra: %s" % "; ".join(p["problemas"]))
        return 2

    # ¿Cuantas exportaciones se llaman asi? Puede haber varias (nombre repetido
    # en ramas distintas), asi que se listan TODAS con su camino.
    candidatos = [i for i, x in enumerate(p["exports"])
                  if nombre_de(p["nombres"], x["nm"]) == args.clase]
    print("=" * 74)
    print("  %s  en  %s" % (args.clase, os.path.basename(args.package)))
    print("=" * 74)
    print("  %d exportaciones con ese nombre" % len(candidatos))
    for i in candidatos:
        print("    export[%d]  %s%s" % (i, camino_export(p, i),
                                        "   (ES UNA CLASE)" if p["exports"][i]["ci"] == 0 else ""))
    if not candidatos:
        return 1
    print()

    def vuelca(k, prof):
        sangria = "    " * prof
        hs = hijos(p, k)
        if not hs:
            return
        for h in sorted(hs, key=lambda j: p["exports"][j]["nm"]):
            i, nombre, clase, sufijo = describe(p, h)
            print("%s%-38s %-22s%s" % (sangria, nombre, clase, sufijo))
            if prof < args.hondo:
                vuelca(h, prof + 1)

    for i in candidatos:
        print("--- export[%d] ---" % i)
        vuelca(i, 1)
        print()


if __name__ == "__main__":
    sys.exit(main())
