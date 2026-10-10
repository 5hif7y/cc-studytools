#!/usr/bin/env python3
"""
Convierte la salida cruda de `ue3-packer types` sobre un paquete del juego en la
entrada que lee `generate-stubs.py`.

POR QUE HACE FALTA
------------------
`ue3-packer types` vuelca **una linea por exportacion**, y de las 185.659 de
`CrimeCraft.u` casi todas son funciones, constantes y buffers de texto que el
generador **no mira**. Versionar el volcado entero son 16 MB para guardar lo
que cabe en menos de la mitad.

ASI QUE FILTRA, Y EL FILTRO NO ES UNA OPINION: son exactamente los generos que
`tipos_del_juego()` consume.

    ScriptStruct / Enum              -> el GENERO de un tipo
    los de PROPIEDAD_A_TIPO          -> el TIPO de un miembro
    los de SIN_TIPO                  -> un miembro que NO se puede tipar desde
                                        la tabla de exportaciones (el nombre del
                                        struct va en el `FPropertyTag`), y que
                                        por eso BLOQUEA la declaracion del tipo
                                        entero. Se conservan a proposito: son
                                        la lista de lo que falta.

Y NO SE ORDENA. El orden de las exportaciones ES el orden de declaracion, y el
orden de los miembros de un struct **es su layout**. Un `sort -u` lo destruye en
silencio, y ya paso una vez.

Uso:
    ue3-packer types <paquete>.u > crudo.txt
    python tools/generate-game-catalog.py crudo.txt tools/tipos-crimecraft.txt
"""
import io
import sys

# Los mismos conjuntos que `generate-stubs.py`. Si alli cambian, aqui tambien:
# se comprueba al final, y el script FALLA si no coinciden.
TIPOS = ("ScriptStruct", "Enum")
PROPIEDADES = ("ObjectProperty", "ClassProperty", "InterfaceProperty",
               "NameProperty", "IntProperty", "FloatProperty", "BoolProperty",
               "StrProperty", "ByteProperty")
SIN_TIPO = ("StructProperty", "ArrayProperty")

CABECERA = """# GENERADO por `ue3-packer types` sobre los paquetes del JUEGO, y filtrado.
#
# Formato: genero<TAB>nombre<TAB>contenedor.
#
# Este es el catalogo del PAQUETE DEL JUEGO (`CrimeCraft.u`), que es el otro
# sitio donde viven los tipos que al SDK le faltan. El de los paquetes del
# MOTOR es `tipos-del-juego.txt`, y los dos se leen.
#
# Se conservan solo los generos que `tipos_del_juego()` consume; el resto son
# funciones y constantes que el generador no mira. Ver el docstring de
# `tools/generate-game-catalog.py`.
#
# Y NO SE ORDENA: el orden de las exportaciones ES el de declaracion, y el de
# los miembros de un struct ES su layout.
#
# Para regenerarlo:
#   ue3-packer types <CookedPC>/CrimeCraft.u > crudo.txt
#   python tools/generate-game-catalog.py crudo.txt tools/tipos-crimecraft.txt
"""


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    crudo, destino = sys.argv[1], sys.argv[2]
    conservados = ("ScriptStruct", "Enum") + PROPIEDADES + SIN_TIPO
    total, fuera = 0, 0
    with io.open(destino, "w", encoding="utf-8", newline="\n") as out:
        out.write(CABECERA)
        for linea in io.open(crudo, encoding="utf-8", errors="replace"):
            if linea.startswith("#") or chr(9) not in linea:
                continue
            total += 1
            partes = linea.rstrip(chr(10)).split(chr(9))
            if len(partes) == 3 and partes[0] in conservados:
                out.write(linea if linea.endswith(chr(10)) else linea + chr(10))
            else:
                fuera += 1
    print(f"{destino}: {total - fuera} de {total} lineas conservadas "
          f"({fuera} descartadas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
