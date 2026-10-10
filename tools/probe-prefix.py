#!/usr/bin/env python3
"""
Sonda del prefijo de 4 bytes que abre los datos de cada exportacion.

Estado de la cuestion:

  - El encabezado y las tres tablas estan medidos y verificados por cierre.
  - El flujo de propiedades esta identificado y comprobado: FPropertyTag es
    Name (FName, 8) + Type (FName, 8) + Size (INT) + ArrayIndex (INT), y sale
    de `UnPropertyTag.h:58`. Resolviendo los indices contra la tabla de nombres
    se leen propiedades reales:
        DefaultViewX    IntProperty    size=4  valor=900
        DefaultViewY    IntProperty    size=4  valor=619
        DefaultViewZoom FloatProperty  size=4  valor=0.8

  - PERO el primer tag empieza en +4, no en +0. Siempre. Y los 4 bytes de
    delante no son parte de ningun tag: cuatro exportaciones distintas dan
    prefijos 2, 3, 4, 190, 203, 205 y todos dejan el tag alineado en +4.

Lo que se busca aqui es QUE es ese entero. La pista que se persigue: en las
exportaciones 3, 4 y 5 el prefijo vale 2, 3 y 4 -- o sea, indice menos uno. Y en
la 1349, 1362 y 1364 vale 190, 203 y 205 -- indice menos 1159. Avanza de uno en
uno en los dos tramos, con una constante distinta.

Eso es compatible con dos cosas muy distintas:
  (a) un contador que solo cuenta algunas exportaciones, y que salta cuando
      aparece una que no cuenta; o
  (b) algo que casualmente correlaciona con el indice en esos tramos.

La diferencia importa, y se distingue mirando TODO el paquete: si (a), la
columna `i - prefijo` sera constante a trozos; si (b), no lo sera.

Uso:  python probe-prefix.py <paquete>
"""

import struct
import sys


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def u32(d, p):
    return struct.unpack_from("<I", d, p)[0]


def fstring(d, p):
    n = i32(d, p)
    p += 4
    if n < 0:
        return d[p:p - n * 2].decode("utf-16-le", "replace").rstrip("\x00"), p - n * 2
    return d[p:p + n].decode("latin-1").rstrip("\x00"), p + n


def lee_encabezado(d):
    carpeta, p = fstring(d, 12)
    e = {"Carpeta": carpeta}
    for k in ("PackageFlags", "NameCount", "NameOffset", "ExportCount",
              "ExportOffset", "ImportCount", "ImportOffset", "DependsOffset"):
        e[k] = i32(d, p); p += 4
    # PackageFlags es unsigned
    e["PackageFlags"] = e["PackageFlags"] & 0xFFFFFFFF
    p += 16                                     # Guid
    gen = i32(d, p); p += 4
    p += gen * 12
    e["EngineVersion"] = i32(d, p); p += 4
    e["CookedContent"] = i32(d, p); p += 4
    e["CompressionFlags"] = u32(d, p); p += 4
    trozos = i32(d, p); p += 4
    p += trozos * 16
    p += 4                                      # PackageSource
    extra = i32(d, p); p += 4
    extras = []
    for _ in range(extra):
        s, p = fstring(d, p)
        extras.append(s)
    e["AdditionalPackagesToCook"] = extras
    e["_fin"] = p
    return e


def lee_exportaciones(d, off, cuenta):
    """Entrada de 68 bytes mas 4 por objeto de red."""
    p = off
    salida = []
    for k in range(cuenta):
        e = {
            "clase": i32(d, p + 0),
            "super": i32(d, p + 4),
            "outer": i32(d, p + 8),
            "nombre": i32(d, p + 12),
            "arquetipo": i32(d, p + 20),
            "desc1": i32(d, p + 24),
            "desc2": i32(d, p + 28),
            "tamano": i32(d, p + 32),
            "offset": i32(d, p + 36),
        }
        cuenta_red = i32(d, p + 44)
        if not (0 <= cuenta_red < 64):
            raise SystemExit(f"desajuste en la exportacion {k}: red={cuenta_red}")
        p += 68 + 4 * cuenta_red
        salida.append(e)
    return salida, p


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], "rb") as f:
        d = f.read()

    e = lee_encabezado(d)
    print(f"carpeta={e['Carpeta']!r}  encabezado hasta {e['_fin']}  "
          f"NameOffset={e['NameOffset']}")
    if e["AdditionalPackagesToCook"]:
        print(f"AdditionalPackagesToCook: {e['AdditionalPackagesToCook']}")
    print()

    exports, fin = lee_exportaciones(d, e["ExportOffset"], e["ExportCount"])
    print(f"exportaciones: {len(exports)}  (la tabla cierra en {fin}, "
          f"DependsOffset={e['DependsOffset']})")
    print()

    filas = []
    for k, x in enumerate(exports):
        if x["tamano"] <= 0:
            continue
        prefijo = i32(d, x["offset"])
        filas.append((k, prefijo, x))
        x["prefijo"] = prefijo

    print("=== 30 primeras exportaciones con datos ===")
    print(f"{'i':>6} {'prefijo':>9} {'i-prefijo':>10} {'tamano':>8} "
          f"{'clase':>7} {'arquetipo':>9}")
    for k, pref, x in filas[:30]:
        print(f"{k:>6} {pref:>9} {k - pref:>10} {x['tamano']:>8} "
              f"{x['clase']:>7} {x['arquetipo']:>9}")
    print()

    # Si el prefijo fuera un contador que solo cuenta algunas exportaciones,
    # `i - prefijo` seria constante a trozos. Se cuentan los tramos.
    print("=== tramos de i - prefijo constante ===")
    tramos = []
    for k, pref, x in filas:
        delta = k - pref
        if tramos and tramos[-1][2] == delta:
            tramos[-1][1] = k
        else:
            tramos.append([k, k, delta])
    print(f"hay {len(tramos)} tramos en {len(filas)} exportaciones con datos")
    for ini, fin_, delta in tramos[:15]:
        print(f"  {ini:>6}..{fin_:<6}  i-prefijo = {delta}")
    if len(tramos) > 15:
        print(f"  ... y {len(tramos) - 15} mas")
    print()

    # La otra posibilidad: el prefijo se repite con frecuencia, como haria un
    # contador pequeno, o es casi unico, como haria un indice.
    unicos = len(set(p for _, p, _ in filas))
    print(f"valores distintos del prefijo: {unicos} de {len(filas)}")
    monton = {}
    for _, p, _ in filas:
        monton[p] = monton.get(p, 0) + 1
    repetidos = sorted(monton.items(), key=lambda kv: -kv[1])[:8]
    print(f"los mas repetidos: {repetidos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
