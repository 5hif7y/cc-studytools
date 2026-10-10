#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EL ARBOL DE EXPRESIONES UNIFORMES DE UN MATERIAL, LEIDO DEL PAQUETE.

POR QUE EXISTE
--------------
El motor mata la carga de un material con

    MaterialShared.cpp:1122   check(Type);

cuando el paquete trae un `FMaterialUniformExpression` cuyo tipo no esta
registrado. La sonda `[MAT-EXPR]` de ese mismo fichero da **el nombre, el paquete
y la posicion**; esto coge esa posicion y **camina la cadena**, que es lo que hace
falta para saber cuantos bytes ocupa cada cosa.

COMO SE PUEDE CAMINAR SIN EL MOTOR
----------------------------------
Dos hechos, los dos medidos con control:

  1. **`Ar.Tell()` ES el offset del fichero** en estos `.ccpk`. Comprobado sobre
     `lobby_textures_banners_01.ccpk` en la posicion 59954: los bytes del fichero
     son identicos a los que leyo el motor por el archivo. Asi que no hace falta
     reconstruir ni correr nada.

  2. **La serializacion de una expresion es `[FName del tipo][los datos del tipo]`**
     (`MaterialShared.cpp:1104`, `operator<<(FArchive&, FMaterialUniformExpression*&)`):
     primero el NOMBRE del tipo, y despues su `Serialize()`.

Y la tabla de "los datos del tipo" sale de NUESTRO propio `MaterialShared.cpp`, que
ya tiene los 22 tipos que el motor registra. Cada entrada dice que escribe su
`Serialize`, en orden.

LA AUTOVALIDACION, que es lo que la hace util
---------------------------------------------
Cada paso lee un `FName` que TIENE que ser un tipo de la tabla. Si el paseo se
desincroniza, el nombre que sale no esta en la tabla y **el programa lo dice** en
vez de devolver un arbol plausible. Un paseo que no puede fallar tampoco demuestra
nada.

    python -I tools/decode-material.py <paquete.ccpk> <pos>        # el arbol
    python -I tools/decode-material.py <paquete.ccpk> <pos> --n 6  # 6 hermanos
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import package  # noqa: E402

# ---------------------------------------------------------------------------
# La tabla: que escribe el Serialize de cada tipo, en orden.
# Sale de `MaterialShared.cpp`; la columna de la derecha es la linea del Serialize.
#   'ref' -> TRefCountPtr<FMaterialUniformExpression> = FName(8) + subarbol
# ---------------------------------------------------------------------------
TABLA = {
    "FMaterialUniformExpressionTime": [],
    "FMaterialUniformExpressionRealTime": [],
    "FMaterialUniformExpressionConstant": [("Value", "FLinearColor"), ("ValueType", "BYTE")],
    "FMaterialUniformExpressionVectorParameter": [("ParameterName", "FName"), ("DefaultValue", "FLinearColor")],
    # OJO: el DefaultValue del ESCALAR es un FLOAT (4 B), no un color. Lo delata su
    # propio constructor -- `FMaterialUniformExpressionScalarParameter(FName, FLOAT)`
    # (MaterialShared.cpp:2965) -- y lo confirmo el paseo: con 16 el flujo se desplaza
    # 12 bytes y el siguiente nombre sale fuera de la tabla. El VECTOR si es color.
    "FMaterialUniformExpressionScalarParameter": [("ParameterName", "FName"), ("DefaultValue", "FLOAT")],
    "FMaterialUniformExpressionSine": [("X", "ref"), ("bIsCosine", "UBOOL")],
    "FMaterialUniformExpressionSquareRoot": [("X", "ref")],
    "FMaterialUniformExpressionLength": [("X", "ref")],
    "FMaterialUniformExpressionFoldedMath": [("A", "ref"), ("B", "ref"), ("Op", "BYTE")],
    "FMaterialUniformExpressionPeriodic": [("X", "ref")],
    "FMaterialUniformExpressionAppendVector": [("A", "ref"), ("B", "ref"), ("NumComponentsA", "INT")],
    "FMaterialUniformExpressionMin": [("A", "ref"), ("B", "ref")],
    "FMaterialUniformExpressionMax": [("A", "ref"), ("B", "ref")],
    "FMaterialUniformExpressionClamp": [("Input", "ref"), ("Min", "ref"), ("Max", "ref")],
    "FMaterialUniformExpressionFloor": [("X", "ref")],
    "FMaterialUniformExpressionCeil": [("X", "ref")],
    "FMaterialUniformExpressionFrac": [("X", "ref")],
    "FMaterialUniformExpressionFmod": [("A", "ref"), ("B", "ref")],
    "FMaterialUniformExpressionAbs": [("X", "ref")],
    "FMaterialUniformExpressionTexture": [("Texture", "ref_tex")],
    "FMaterialUniformExpressionTextureParameter": [("Texture", "ref_tex"), ("ParameterName", "FName")],
    "FMaterialUniformExpressionFlipBookTextureParameter": [("Texture", "ref_tex"), ("ParameterName", "FName")],
}

TAM = {"FName": 8, "FLinearColor": 16, "UBOOL": 4, "BYTE": 1, "INT": 4, "FGuid": 16, "FLOAT": 4}


class Desincronizado(Exception):
    pass


class Lector(object):
    def __init__(self, datos, nombres, pos):
        self.d, self.n, self.p = datos, nombres, pos
        # TRAZA: cada FName leido, con su posicion y si es un tipo conocido. Es lo
        # que dice DONDE se torcio el paseo -- sin ella, el fallo solo dice donde
        # se NOTO, que no es lo mismo.
        self.traza = []

    def i32(self):
        v = int.from_bytes(self.d[self.p:self.p + 4], "little", signed=True)
        self.p += 4
        return v

    def nombre(self):
        """Un FName: indice (4) + numero (4)."""
        pos = self.p
        i = self.i32()
        num = self.i32()
        if not (0 <= i < len(self.n)):
            self.traza.append((pos, "<FUERA DE RANGO %d>" % i, False))
            raise Desincronizado("indice de nombre %d fuera de rango (NameCount=%d) en %d"
                                 % (i, len(self.n), pos))
        nom = self.n[i]
        self.traza.append((pos, nom, nom in TABLA))
        return nom, num, i


def camina_arbol(L, hondo, tope, linea):
    """Lee `[FName tipo][datos]` recursivamente. Devuelve (nombre, bytes)."""
    ini = L.p
    if hondo > tope:
        raise Desincronizado("demasiado hondo en %d" % ini)
    nom, num, idx = L.nombre()
    if nom not in TABLA:
        raise Desincronizado("tipo '%s' (indice %d) NO esta en la tabla, en offset %d" % (nom, idx, ini))
    # OJO: `nombre()` YA ha consumido los 8 bytes del FName. No sumar 8 mas aqui
    # -- hacerlo desplaza todo 8 bytes y el paseo "casi" cuadra, que es la peor
    # forma de fallar. Lo destapo la traza, no el sintoma.
    for campo, tipo in TABLA[nom]:
        if tipo == "ref":
            camina_arbol(L, hondo + 1, tope, linea)
        elif tipo == "ref_tex":
            # la textura tambien es una expresion, pero puede venir nula: un FName None.
            camina_arbol_si_no_nulo(L, hondo + 1, tope)
        else:
            L.p += TAM[tipo]
    linea.append("  " * hondo + "%-46s %6d B  [%d..%d]" % (nom, L.p - ini, ini, L.p))
    return nom, L.p - ini


def camina_arbol_si_no_nulo(L, hondo, tope):
    """Un puntero a expresion puede venir como `None` (nombre 0 del paquete)."""
    guarda = L.p
    try:
        return camina_arbol(L, hondo, tope, [])
    except Desincronizado:
        L.p = guarda + 8  # solo el FName del None
        return None, 8


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("pos", type=int, help="posicion que dio la sonda [MAT-EXPR]")
    ap.add_argument("--n", type=int, default=8, help="cuantos hermanos leer (8)")
    ap.add_argument("--hondo", type=int, default=64)
    a = ap.parse_args()

    p = package.lee_paquete(a.package, estricto=True)
    d = open(a.package, "rb").read()
    nombres = p["nombres"]
    L = Lector(d, nombres, a.pos)

    print("== %s ==" % p["ruta"])
    print("   arranque en %d, NameCount=%d, fichero=%d B" % (a.pos, len(nombres), len(d)))
    print()
    print("   Los %d hermanos de nivel 0 (cada uno = [FName tipo][subarbol]):" % a.n)
    print()

    for k in range(a.n):
        ini = L.p
        linea = []
        try:
            nom, tam = camina_arbol(L, 1, a.hondo, linea)
        except Desincronizado as ex:
            print("   ** HERMANO %d SE DESINCRONIZO en %d: %s" % (k, ini, ex))
            print("      bytes ahi: %s" % " ".join("%02X" % b for b in d[ini:ini + 16]))
            print()
            print("   LA TRAZA -- cada FName leido, en orden (pos, nombre, es tipo?):")
            for pos, nom, es in L.traza:
                print("      %7d  %-46s %s" % (pos, nom, "" if es else "  <-- NO ES UN TIPO"))
            return 1
        print("   --- hermano %d: %s  (%d B, pos %d..%d)" % (k, nom, tam, ini, L.p))
        for l in linea[:12]:
            print("      " + l)
        if len(linea) > 12:
            print("      ... (%d niveles mas)" % (len(linea) - 12))
        print()

    print("   fin del paseo en %d" % L.p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
