#!/usr/bin/env python3
"""
Sonda de la tabla de nombres de un paquete UE3, version 576.

El encabezado ya esta resuelto (ver probe-header.py): con FolderName="None",
generaciones de 12 bytes y PackageSource presente, los campos consumen
exactamente 109 bytes, que es lo que dice NameOffset. Y los valores leidos
reproducen los ya medidos para CrimeCraft.u (Engine=4701, Cooked=87).

Falta el formato de cada entrada. El cierre de la tabla es lo que lo decide: la
tabla tiene NameCount entradas y la siguiente estructura empieza en ImportOffset.
Eso son 1.829.020 bytes que tienen que caer en un punto exacto. Una variante
equivocada se desvia en la primera entrada y ya no vuelve; solo la correcta
recorre las 56.719 y aterriza justo en ImportOffset.

Una coincidencia ahi no es probable: es la comprobacion entera.

Uso:  python probe-name-table.py <paquete>
"""

import struct
import sys


def u32(d, p):
    return struct.unpack_from("<I", d, p)[0]


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def alinea4(p):
    return (p + 3) & ~3


def recorre(d, inicio, cuenta, tope, cola, alinear_entrada, alinear_cola):
    """
    Recorre la tabla entera y devuelve (posicion_final, nombres).

    Cada entrada es:  [i32 len][len bytes][cola bytes]
    `cola`          : cuantos bytes siguen a la cadena (0, 4 u 8)
    `alinear_entrada`: cada entrada empieza en multiplo de 4
    `alinear_cola`  : los bytes de cola empiezan en multiplo de 4

    Devuelve None como posicion si el formato no es sostenible: una longitud
    absurda o pasarse del cierre esperado significa que la lectura ya se
    desincronizo, y no tiene sentido seguir.
    """
    p = inicio
    nombres = []
    for _ in range(cuenta):
        if alinear_entrada:
            p = alinea4(p)
        if p + 4 > len(d):
            return None, nombres
        n = i32(d, p)
        p += 4
        if n < 0:                                   # UTF-16
            nb = -n * 2
            if nb > 4096 or p + nb > len(d):
                return None, nombres
            s = d[p:p + nb].decode("utf-16-le", "replace")
            p += nb
        else:
            if n > 4096 or p + n > len(d):
                return None, nombres
            s = d[p:p + n].decode("latin-1")
            p += n
        nombres.append(s.rstrip("\x00"))
        if alinear_cola:
            p = alinea4(p)
        p += cola
        if p > tope:
            return None, nombres
    return p, nombres


def variantes(d, inicio, cuenta, tope):
    """Las formas plausibles, de la mas simple a la mas rara."""
    for etiqueta, cola, ae, ac in (
        ("cruda, 4 de cola",              4, False, False),
        ("cruda, 8 de cola",              8, False, False),
        ("cruda, sin cola",               0, False, False),
        ("entradas alineadas a 4, 4 cola", 4, True,  False),
        ("entradas alineadas a 4, 8 cola", 8, True,  False),
        ("cola alineada a 4, 4 de cola",   4, False, True),
        ("cola alineada a 4, 8 de cola",   8, False, True),
    ):
        fin, nombres = recorre(d, inicio, cuenta, tope, cola, ae, ac)
        yield etiqueta, fin, nombres


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    ruta = sys.argv[1]
    with open(ruta, "rb") as f:
        d = f.read()

    # Del encabezado, ya resuelto y verificado. Se relee aqui para no depender
    # de que el otro sondeo se haya corrido antes.
    folder_len = i32(d, 12)
    p = 16 + folder_len
    flags = u32(d, p); p += 4
    name_count = i32(d, p); p += 4
    name_offset = i32(d, p); p += 4
    p += 4                       # ExportCount
    p += 4                       # ExportOffset
    p += 4                       # ImportCount
    import_offset = i32(d, p); p += 4
    p += 4                       # DependsOffset
    p += 16                      # Guid
    gen_count = i32(d, p); p += 4
    p += gen_count * 12
    engine = i32(d, p); p += 4
    cooked = i32(d, p); p += 4

    print(f"fichero        {ruta}")
    print(f"NameCount      {name_count}")
    print(f"NameOffset     {name_offset}")
    print(f"ImportOffset   {import_offset}   <- cierre esperado de la tabla")
    print(f"EngineVersion  {engine}")
    print(f"CookedContent  {cooked}")
    print(f"PackageFlags   {flags:#010x}")
    print(f"tamano tabla   {import_offset - name_offset} bytes "
          f"({(import_offset - name_offset) / name_count:.2f} por entrada)")
    print()

    ganadoras = []
    for etiqueta, fin, nombres in variantes(
            d, name_offset, name_count, import_offset):
        cuadra = fin == import_offset
        if fin is None:
            estado = f"se desincroniza en la entrada {len(nombres)}"
        elif cuadra:
            estado = "CIERRA EXACTO"
        else:
            estado = f"desvio {fin - import_offset:+d}"
        print(f"--- {etiqueta:<34} {estado}")
        for s in nombres[:5]:
            print(f"      {s!r}")
        print()
        if cuadra:
            ganadoras.append((etiqueta, nombres))

    print("=" * 66)
    if len(ganadoras) == 1:
        etiqueta, nombres = ganadoras[0]
        print(f"DECIDIDO: formato '{etiqueta}'.")
        print(f"Las 56.719 entradas caen exactamente en ImportOffset.")
        print("\nPrimeros nombres:")
        for s in nombres[:12]:
            print(f"  {s!r}")
    elif not ganadoras:
        print("NINGUNA variante cierra. El formato de entrada es otra cosa.")
    else:
        print(f"AMBIGUO: cierran {len(ganadoras)} variantes. Hacen falta mas datos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
