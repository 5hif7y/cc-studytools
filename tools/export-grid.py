#!/usr/bin/env python3
"""
EN QUE REJILLA ESTAN LOS DATOS DE UNA EXPORTACION. PAR O IMPAR.

POR QUE MIDE ESTO
-----------------
El 5/10 se cerro, al byte, por que el editor revienta al abrir `EntryLevel.ccmap`:

  a +8253 de la export 82 de `Characters_Male_combocloth.ccpk` el motor leyo
  `0x5B0FE30D`, lo tomo por el contador de un `TArray<short>`, y pidio
  1.527.767.821 x 2 = 3.055.535.642 bytes de golpe. VirtualAlloc dijo que no.

Pero `0x5B0FE30D` no es un contador: **es el interior del bufer de indices**.
Los indices son `WORD` y estan en la rejilla PAR -- leidos de tres en tres son
triangulos (3357, 3413, 4049), todos con el byte alto en 0x0C..0x0F, que es lo
que da un modelo de ~4.096 vertices.

**Y +8253 es IMPAR.**

Un `TArray<WORD>` empieza en par y mide un numero par de bytes, asi que
**termina en par**. Que el lector acabe en impar significa que la desalineacion
no la produjo el bufer de indices: venia de ANTES, y era impar.

Eso descarta toda la familia "leyo un contador de mas" y deja una sola:
**alguien leyo un BYTE que no estaba, o no leyo uno que si.**

QUE HACE
--------
Recorre la exportacion y, para cada offset, mide la racha de `u16` que caen en
un rango plausible de indice de vertice. Con eso se ve DONDE empieza y DONDE
acaba el bufer de indices, y si su rejilla es par o impar.

Uso:  python tools/export-grid.py <paquete> <indice-export> [--desde N] [--hasta N]
      python tools/export-grid.py <paquete> 82
"""
import struct
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))

# Rango plausible de un indice de vertice. Medido: los del bufer de
# `CH_MNPCguard01_lobby` van de 0x0CDF a 0x0FE3, todos por debajo de 0x1000.
BANDA = (0x0C00, 0x1000)   # medido: los indices de esta malla van de 0x0CDF a 0x0FE3
MIN_RACHA = 24


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def u32(d, p):
    return struct.unpack_from("<I", d, p)[0]


def lee_encabezado(d):
    folder_len = i32(d, 12)
    p = 16 + folder_len
    e = {}
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
    e["EngineVersion"] = i32(d, p); p += 4
    return e


def lee_exportaciones(d, off, cuenta):
    fuera = []
    p = off
    for _ in range(cuenta):
        fuera.append({
            "nombre": i32(d, p + 12),
            "tamano": i32(d, p + 32),
            "offset": i32(d, p + 36),
        })
        # Paso VARIABLE: el registro mide 68 + 4N, con N = i32(p+44). Con `p += 68`
        # fijo se resuelve la exportacion equivocada tras el primer registro largo
        # -- y los valores desplazados PARECEN buenos (41,7 % en CrimeCraft.u,
        # 53,1 % en EntryLevel.ccmap). Corregido el 5/10.
        # El lector de referencia, con las cuatro comprobaciones que no se pueden
        # falsear, es `cc-studytools/tools/package.py`.
        p += 68 + 4 * i32(d, p + 44)
    return fuera


def racha(d, p, fin, lo, hi):
    """Cuenta cuantos u16 seguidos desde p caen dentro de [lo, hi)."""
    n = 0
    while p + 2 <= fin:
        if not (lo <= struct.unpack_from("<H", d, p)[0] < hi):
            break
        n += 1
        p += 2
    return n


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ruta = sys.argv[1]
    k = int(sys.argv[2])
    desde = int(sys.argv[sys.argv.index("--desde") + 1]) if "--desde" in sys.argv else 0
    lo, hi = BANDA
    if "--banda" in sys.argv:
        lo = int(sys.argv[sys.argv.index("--banda") + 1], 0)
        hi = int(sys.argv[sys.argv.index("--banda") + 2], 0)

    with open(ruta, "rb") as f:
        d = f.read()
    e = lee_encabezado(d)
    exports = lee_exportaciones(d, e["ExportOffset"], e["ExportCount"])
    x = exports[k]
    ini = x["offset"]
    fin = ini + x["tamano"]

    print(f"export {k}  offset={ini}  tamano={x['tamano']}")
    print(f"banda de indice = [0x{lo:X}, 0x{hi:X})   racha minima = {MIN_RACHA}")
    print()

    # Se recorren las DOS rejillas por separado: si el bufer esta en par, la
    # racha larga aparece en par y la de impar son migajas. Ese contraste es
    # justo la medida.
    for paridad in (0, 1):
        p = ini + desde + ((paridad - (ini + desde)) % 2)
        hallazgos = []
        while p + 2 * MIN_RACHA <= fin:
            n = racha(d, p, fin, lo, hi)
            if n >= MIN_RACHA:
                hallazgos.append((p - ini, n))
                p += n * 2
            else:
                p += 2
        total = sum(n for _, n in hallazgos)
        print(f"=== rejilla {'PAR' if paridad == 0 else 'IMPAR'}   "
              f"rachas={len(hallazgos)}  u16 totales={total} ===")
        hallazgos.sort(key=lambda t: -t[1])
        for rel, n in hallazgos[:12]:
            print(f"   +{rel:<8} {n:>7} u16  ({n * 2} bytes)")
        if len(hallazgos) > 12:
            print(f"   ... y {len(hallazgos) - 12} mas")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
