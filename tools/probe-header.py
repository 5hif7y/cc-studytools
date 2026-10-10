#!/usr/bin/env python3
"""
Sonda del encabezado de un paquete UE3, para dirimir dos lecturas posibles del
mismo layout que consumen exactamente los mismos bytes.

El SDK del proyecto (rama tardia de UE3) ya no conserva las puertas de version de
la epoca de 576: `FGenerationInfo::Serialize` escribe ExportCount, NameCount y
NetObjectCount sin condicion, y no existen constantes VER_ para
PACKAGE_SOURCE ni NET_OBJECT_COUNT. Pero el paquete mide lo que mide.

Con FileVersion = 576 y FolderName de 9 caracteres, el arranque de la tabla de
nombres cae en 109 en AMBAS lecturas:

  A) generaciones de 8 bytes, PackageSource presente
  B) generaciones de 12 bytes, PackageSource ausente

Las dos cuadran con NameOffset = 109. Lo que las separa no es el tamano sino los
VALORES: en EngineVersion y CookedContentVersion ya medidos para CrimeCraft.u
(4701 y 87). La lectura que los reproduzca es la buena.

DESENLACE, para quien lea esto despues: las dos lecturas fallan, y las dos por
lo mismo -- ninguna contempla que AdditionalPackagesToCook este presente. La
buena es la B MAS ese campo, y con eso el encabezado consume exactamente 109
bytes. La B ya acertaba EngineVersion=4701 y CookedContentVersion=87; lo unico
que le faltaba eran 4 bytes. Este fichero se conserva tal cual porque el
razonamiento que lleva a la respuesta esta en que las dos fallen.

Uso:  python probe-header.py <paquete>
"""

import struct
import sys


class Lector:
    def __init__(self, datos):
        self.d = datos
        self.p = 0

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def bytes(self, n):
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def fstring(self):
        n = self.i32()
        if n < 0:                      # negativo = UTF-16
            s = self.bytes(-n * 2).decode("utf-16-le", "replace")
        else:
            s = self.bytes(n).decode("latin-1")
        return s.rstrip("\x00")

    def guid(self):
        return self.bytes(16)


def sondea(datos, generacion_bytes, con_package_source):
    """
    generacion_bytes : 8 o 12, segun si FGenerationInfo lleva NetObjectCount
    con_package_source : si el campo PackageSource existe en esta version

    Las dos lecturas consumen los mismos 109 bytes hasta la tabla de nombres.
    Lo que cambia es donde cae cada campo, y por tanto QUE valor se lee.
    """
    r = Lector(datos)
    try:
        campos = []
        tag = r.u32()
        campos.append(("Tag", hex(tag)))
        if tag not in (0x9E2A83C1, 0xC1832A9E):
            return None, "el magic no es 0x9E2A83C1"
        fv = r.u32()
        campos.append(("FileVersion", fv))
        campos.append(("Version", fv & 0xFFFF))
        campos.append(("Licensee", (fv >> 16) & 0xFFFF))
        campos.append(("TotalHeaderSize", r.i32()))
        campos.append(("FolderName", r.fstring()))
        campos.append(("PackageFlags", hex(r.u32())))
        name_count = r.i32()
        name_offset = r.i32()
        campos.append(("NameCount", name_count))
        campos.append(("NameOffset", name_offset))
        campos.append(("ExportCount", r.i32()))
        campos.append(("ExportOffset", r.i32()))
        campos.append(("ImportCount", r.i32()))
        campos.append(("ImportOffset", r.i32()))
        campos.append(("DependsOffset", r.i32()))
        r.guid()
        gen_count = r.i32()
        campos.append(("GenerationCount", gen_count))
        for i in range(min(gen_count, 64)):
            r.bytes(generacion_bytes)
        campos.append(("EngineVersion", r.i32()))
        campos.append(("CookedContentVersion", r.i32()))
        campos.append(("CompressionFlags", hex(r.u32())))
        chunk_count = r.i32()
        campos.append(("CompressedChunks", chunk_count))
        r.bytes(chunk_count * 16)
        if con_package_source:
            campos.append(("PackageSource", r.i32()))
        else:
            campos.append(("PackageSource", "(ausente en esta version)"))
        campos.append(("AdditionalPackagesToCook", r.i32()))
        campos.append(("_fin", r.p))
        campos.append(("_esperado", name_offset))
        return campos, None
    except struct.error as e:
        return None, str(e)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    ruta = sys.argv[1]
    with open(ruta, "rb") as f:
        datos = f.read(4096)

    print(f"fichero: {ruta}\n")
    lecturas = (
        (8,  True,  "A: generaciones de 8 bytes, PackageSource presente"),
        (12, False, "B: generaciones de 12 bytes, PackageSource ausente"),
    )
    correctas = []
    for gb, cps, nombre in lecturas:
        print(f"--- Lectura {nombre} ---")
        campos, err = sondea(datos, gb, cps)
        if err:
            print(f"  fallo: {err}\n")
            continue
        for k, v in campos:
            print(f"  {k:<24} {v}")
        d = dict(campos)
        engine = d.get("EngineVersion")
        cooked = d.get("CookedContentVersion")

        # Dos comprobaciones independientes, y hacen falta las dos:
        #  1. La tabla de nombres empieza exactamente donde dice NameOffset.
        #     Las dos lecturas la cumplen por construccion, asi que por si sola
        #     no distingue nada -- pero descarta un tercer layout desconocido.
        #  2. EngineVersion cae en un rango de numero de build real, y
        #     CookedContentVersion es un contador pequeno. Aqui es donde se
        #     rompe la lectura equivocada: lee el campo de al lado.
        cuadra_fin = d["_fin"] == d["_esperado"]
        cuadra_val = isinstance(engine, int) and 1000 < engine < 200000 \
            and isinstance(cooked, int) and 0 < cooked < 10000
        ok = cuadra_fin and cuadra_val
        motivos = []
        if not cuadra_fin:
            motivos.append(f"fin={d['_fin']} != NameOffset={d['_esperado']}")
        if not cuadra_val:
            motivos.append(f"EngineVersion={engine} CookedContentVersion={cooked} fuera de rango")
        print(f"  -> Engine={engine} Cooked={cooked}  "
              f"{'CUADRA' if ok else 'NO CUADRA: ' + '; '.join(motivos)}\n")
        if ok:
            correctas.append((nombre, engine, cooked))

    print("=" * 60)
    if len(correctas) == 1:
        print(f"DECIDIDO: {correctas[0][0]}")
    elif not correctas:
        print("NINGUNA lectura cuadra: la hipotesis del layout es falsa.")
    else:
        print("AMBAS cuadran: hacen falta mas datos. Revisar los valores de "
              "EngineVersion contra los ya medidos para este paquete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
