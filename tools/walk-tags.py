#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Camina un flujo de PROPIEDADES ETIQUETADAS (tagged properties) de un paquete UE3
y dice, etiqueta a etiqueta, DONDE cae cada una en el fichero.

Para que sirve
--------------
`FPropertyTag` es AUTODESCRIPTIVO:

    nombre(FName=8)  tipo(FName=8)  tamano(i32=4)  indice(i32=4)
    + segun el tipo: StructName(8) | BoolVal(1 o 4) | EnumName(8)
    + el VALOR, que ocupa exactamente `tamano` bytes.

Con la tabla de nombres resuelta, el flujo se recorre ENTERO sin el motor
delante. Eso lo hace el instrumento para responder "el flujo se desalinea:
¿en QUE propiedad?", que en el motor cuesta recompilar y correr, y aqui cero.

El desvio se ve asi: cada etiqueta imprime su POSICION. Si la aritmetica del
motor coincide con la del fichero, las posiciones avanzan de forma regular; el
primer salto raro es el culpable -- y la etiqueta ANTERIOR es la que se leyo
con el tamano equivocado.

Uso:
    python tools/walk-tags.py <paquete> <offset> [--hasta N] [--bool 1|4]

    python tools/walk-tags.py CrimeCraft/.../CrimeCraft.u 18758994

`--bool` elige el ancho del campo BoolVal: 1 byte (optimizado) o 4 (UBOOL).
Recorrer con los dos y ver cual llega entero es, en si, la medida.
"""
import importlib.util
import os
import struct
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def carga(fichero):
    # El directorio PROPIO: al moverse aqui, `probe-properties.py` es hermano.
    # Antes era `RAIZ/tools`, cableado a la raiz, y por eso esta arista rompia.
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), fichero)
    spec = importlib.util.spec_from_file_location(fichero.replace("-", "_"), ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def nombre_de(nombres, idx):
    if 0 <= idx < len(nombres):
        return nombres[idx]
    return "<FUERA:%d>" % idx


def camina(d, nombres, ini, fin, ancho_bool, ancho_enum, tope=300):
    """Devuelve (lista de etiquetas, parada). Cada etiqueta es un dict.

    `ancho_enum` es lo que el motor lee de `Tag.EnumName` en un ByteProperty:
    0 si su puerta `VER_BYTEPROP_SERIALIZE_ENUM` (633) no se cumple, 8 si si.
    """
    tags = []
    p = ini
    for _ in range(tope):
        if p + 16 > fin:
            return tags, "se acabo el margen en pos=%d" % p
        pos = p
        idx, num = i32(d, p), i32(d, p + 4); p += 8
        nombre = nombre_de(nombres, idx)
        if nombre == "None":
            tags.append({"pos": pos, "nombre": "None", "fin": p})
            return tags, None
        if nombre.startswith("<FUERA"):
            return tags, "nombre FUERA DE RANGO %d en pos=%d" % (idx, pos)
        tidx, tnum = i32(d, p), i32(d, p + 4); p += 8
        tipo = nombre_de(nombres, tidx)
        if tipo.startswith("<FUERA"):
            return tags, "tipo FUERA DE RANGO %d en pos=%d" % (tidx, p - 8)
        size, aidx = i32(d, p), i32(d, p + 4); p += 8
        extra = ""
        if tipo == "StructProperty":
            extra = nombre_de(nombres, i32(d, p)); p += 8
        elif tipo == "BoolProperty":
            p += ancho_bool
        elif tipo == "ByteProperty":
            extra = nombre_de(nombres, i32(d, p)); p += ancho_enum
        valor_en = p
        p += size
        if p > fin:
            return tags, "el valor de %r se sale del margen (pos=%d size=%d)" % (nombre, valor_en, size)
        tags.append({"pos": pos, "nombre": nombre, "tipo": tipo, "size": size,
                     "idx": aidx, "extra": extra, "valor": valor_en, "fin": p})
    return tags, "tope de %d etiquetas" % tope


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 1
    paquete, ini = args[0], int(args[1], 0)
    hasta = ini + 4096
    anchos = [1, 4]
    enums = [0, 8]
    for k, a in enumerate(sys.argv):
        if a == "--hasta":
            hasta = int(sys.argv[k + 1], 0)
        if a == "--bool":
            anchos = [int(sys.argv[k + 1])]
        if a == "--enum":
            enums = [int(sys.argv[k + 1])]

    d = open(paquete, "rb").read()
    sp = carga("probe-properties.py")
    e = sp.lee_encabezado(d)
    nombres = sp.lee_nombres(d, e["NameOffset"], e["NameCount"])
    print("paquete : %s  (%d bytes)" % (paquete, len(d)))
    print("nombres : %d   arranque: %d   margen hasta: %d" % (len(nombres), ini, hasta))
    print()

    for ancho in anchos:
      for enum in enums:
        tags, parada = camina(d, nombres, ini, hasta, ancho, enum)
        print("=== BoolVal = %d byte(s), EnumName = %d byte(s)  ->  %d etiquetas%s ===" % (
            ancho, enum, len(tags), "" if parada is None else "   PARADA: " + parada))
        for t in tags:
            print("   pos=%-10d %-26s %-18s size=%-6d idx=%-3d %s" % (
                t["pos"], t["nombre"], t.get("tipo", ""), t.get("size", -1),
                t.get("idx", -1), t.get("extra", "")))
        # Bytes en la parada: es donde hay que mirar a mano.
        if parada is not None and tags:
            p = tags[-1]["fin"]
            print("   --- bytes en la parada (%d) ---" % p)
            for k in range(p, min(p + 48, len(d)), 16):
                print("     %d: %s" % (k, " ".join("%02X" % b for b in d[k:k + 16])))
        print()


if __name__ == "__main__":
    sys.exit(main())
