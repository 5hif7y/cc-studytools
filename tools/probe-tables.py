#!/usr/bin/env python3
"""
Sonda de las tablas de importacion y exportacion de un paquete UE3 v576.

Ya resuelto en las sondas anteriores, y verificado al byte:
  - encabezado: consumen exactamente 109 bytes hasta NameOffset
  - nombres:    entrada = [i32 len][len bytes][8 de cola]

Lo que queda son las dos tablas. El dato duro que las acota viene del propio
encabezado, y son dos cocientes que no dejan margen:

  ImportOffset .. ExportOffset = 55.776 bytes / 1.992 importaciones = 28,0
  TotalHeaderSize - DependsOffset = 742.636 = 185.659 x 4  -> el mapa de
      dependencias son exactamente 4 bytes por export, y cierra el encabezado.

El segundo cociente es el que ancla el final de la tabla de exportaciones. El
primero fija el tamano de la importacion sin ambiguedad.

`FObjectExport::Serialize` en el SDK, para 576, no puede ser la fuente: esta
rama de UE3 ya no conserva las puertas de version de esta epoca. Asi que se mide.

Uso:  python probe-tables.py <paquete>
"""

import struct
import sys


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
    p += 16                                     # Guid
    gen = i32(d, p); p += 4
    p += gen * 12
    e["EngineVersion"] = i32(d, p); p += 4
    e["CookedContentVersion"] = i32(d, p); p += 4
    e["HeaderEnd"] = p + 4 + 4 + 4 + 4          # flags, chunks, source, addl
    return e


def lee_nombres(d, off, cuenta):
    """Formato ya medido: [i32 len][len bytes][8 de cola]."""
    nombres = []
    p = off
    for _ in range(cuenta):
        n = i32(d, p); p += 4
        if n < 0:
            s = d[p:p - n * 2].decode("utf-16-le", "replace")
            p += -n * 2
        else:
            s = d[p:p + n].decode("latin-1")
            p += n
        p += 8
        nombres.append(s.rstrip("\x00"))
    return nombres, p


def nombre(nombres, i):
    if 0 <= i < len(nombres):
        return f"{i}='{nombres[i]}'"
    return f"{i}=<fuera de rango>"


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], "rb") as f:
        d = f.read()

    e = lee_encabezado(d)
    nombres, fin_nombres = lee_nombres(d, e["NameOffset"], e["NameCount"])

    print(f"NameCount={e['NameCount']}  ExportCount={e['ExportCount']}  "
          f"ImportCount={e['ImportCount']}")
    print(f"la tabla de nombres cierra en {fin_nombres}, "
          f"ImportOffset={e['ImportOffset']}  ->  "
          f"{'OK' if fin_nombres == e['ImportOffset'] else 'DESAJUSTE'}")
    print()

    import_span = e["ExportOffset"] - e["ImportOffset"]
    export_span = e["DependsOffset"] - e["ExportOffset"]
    print(f"importaciones: {import_span} bytes / {e['ImportCount']} = "
          f"{import_span / e['ImportCount']:.4f}")
    # `4 * ExportCount` es el SUELO: cada registro mide 68 + 4N, con N = el
    # `GenerationNetObjectCount` de +44. Lo que sobre es la cola variable.
    print(f"exportaciones: {export_span} bytes / {e['ExportCount']} = "
          f"{export_span / e['ExportCount']:.4f}   "
          f"(sobran {export_span - e['ExportCount'] * 68} sobre 68 = la cola variable)")
    print()

    # ------------------------------------------------------------------
    # Importacion: 28 bytes = FName(8) ClassPackage, FName(8) ClassName,
    # i32(4) OuterIndex, FName(8) ObjectName.
    #
    # Lo que delata la lectura es que los dos campos que cambian caen en +8 y
    # +20, y que el valor que los acompana es siempre 0. Eso es un FName de
    # 8 bytes cuyo numero es 0, no dos enteros sueltos.
    # ------------------------------------------------------------------
    print("=== Importaciones ===")
    p = e["ImportOffset"]
    malas = 0
    for k in range(e["ImportCount"]):
        cp_i, cp_n = i32(d, p), i32(d, p + 4)
        cl_i, cl_n = i32(d, p + 8), i32(d, p + 12)
        outer = i32(d, p + 16)
        ob_i, ob_n = i32(d, p + 20), i32(d, p + 24)
        if not (0 <= cp_i < e["NameCount"] and 0 <= cl_i < e["NameCount"]
                and 0 <= ob_i < e["NameCount"]):
            malas += 1
        if k < 5:
            print(f"  [{k}] {nombres[cp_i]}.{nombres[cl_i]}  "
                  f"outer={outer}  obj='{nombres[ob_i]}'  "
                  f"(numeros {cp_n}/{cl_n}/{ob_n})")
        p += 28
    print(f"  indices de nombre fuera de rango: {malas} de {e['ImportCount']}")
    print(f"  cierra en {p}, ExportOffset={e['ExportOffset']}  ->  "
          f"{'OK' if p == e['ExportOffset'] else 'DESAJUSTE'}")
    print()

    # ------------------------------------------------------------------
    # Exportacion: 68 bytes = i32 x3, FName(8), i32 x2, i32 SerialSize,
    # i32 SerialOffset, i32, i32, i32, Guid(16), i32.
    # ------------------------------------------------------------------
    print("=== Exportaciones ===")
    # ⚠️ ESTE BUCLE LEIA MAL, y el error era SILENCIOSO (corregido el 5/10).
    #
    #   `p += 68` FIJO -> el registro mide 68 + 4N, con N = i32(p+44). Tras el
    #   primer registro largo todo lo que imprime es de OTRO registro, y los
    #   valores desplazados PARECEN buenos. Medido: 41,7 % de los registros de
    #   `CrimeCraft.u` y 53,1 % de `EntryLevel.ccmap`.
    #
    # Los offsets de campo de abajo son los BUENOS: `SerialSize` en +32 y
    # `SerialOffset` en +36 (`FObjectExport::operator<<`, UnLinker.cpp:267-292).
    # El lector de referencia del proyecto, con las cuatro comprobaciones que no
    # se pueden falsear, es `cc-studytools/tools/package.py`.
    p = e["ExportOffset"]
    fuera = 0
    largos = 0
    tamanos = []
    for k in range(e["ExportCount"]):
        cls = i32(d, p)
        sup = i32(d, p + 4)
        outer = i32(d, p + 8)
        ob_i, ob_n = i32(d, p + 12), i32(d, p + 16)
        arche = i32(d, p + 20)
        n_red = i32(d, p + 44)
        # `ObjectFlags` es un QWORD en +24 (`typedef QWORD EObjectFlags`,
        # UnObjBas.h:335) -- y sus banderas caen en las DOS mitades:
        #   RF_ArchetypeObject = 0x400  (mitad BAJA, +24)  <- por eso los
        #       objetos `..._Arc0` muestran 0x400 y el resto 0
        #   RF_Public = 0x0400000000    (mitad ALTA, +28)
        # Leer solo 4 bytes da media mascara, y una media mascara parece un dato.
        flags = struct.unpack_from("<Q", d, p + 24)[0]
        ssize = i32(d, p + 32)
        soff = i32(d, p + 36)
        if k < 5:
            print(f"  [{k}] obj='{nombres[ob_i] if 0 <= ob_i < e['NameCount'] else ob_i}'"
                  f"  clase={cls} super={sup} outer={outer} arche={arche}"
                  f"  flags={flags:#x}  SerialSize={ssize}  SerialOffset={soff}")
        if not (0 <= ob_i < e["NameCount"]):
            fuera += 1
        if n_red:
            largos += 1
        tamanos.append((soff, ssize))
        p += 68 + 4 * n_red

    print(f"  nombres de objeto fuera de rango: {fuera} de {e['ExportCount']}")
    print(f"  cierra en {p}; DependsOffset={e['DependsOffset']}  "
          f"-> sobran {e['DependsOffset'] - p} bytes de cola variable")
    print()

    # ------------------------------------------------------------------
    # Donde caen de verdad SerialSize y SerialOffset.
    #
    # En el volcado crudo, el entero 9 de cada exportacion crece de 48 en 48,
    # y el primero vale TotalHeaderSize -- que es exactamente donde empieza el
    # cuerpo del fichero, justo despues del encabezado. Eso no es casualidad:
    # es el desplazamiento de los datos serializados de la exportacion 0.
    #
    # Se comprueba con el encadenado, que es lo que lo vuelve concluyente: si
    # SerialSize esta en +32 y SerialOffset en +36, entonces para casi toda
    # exportacion se cumple
    #     offset[i+1] == offset[i] + size[i]
    # Un par de campos mal puestos no encadena 185.659 veces.
    # ------------------------------------------------------------------
    print("=== Cadena de desplazamientos (valida donde estan los campos) ===")
    for etiqueta, off_size, off_data in (
        ("hipotesis: size en +28, offset en +32", 28, 32),
        ("hipotesis: size en +32, offset en +36", 32, 36),
        ("hipotesis: size en +36, offset en +40", 36, 40),
    ):
        p = e["ExportOffset"]
        encadenan = 0
        primer_fallo = None
        anterior = None
        for k in range(e["ExportCount"]):
            size = i32(d, p + off_size)
            data = i32(d, p + off_data)
            if anterior is not None and size > 0:
                if data == anterior[0] + anterior[1]:
                    encadenan += 1
                elif primer_fallo is None:
                    primer_fallo = k
            if size > 0:
                anterior = (data, size)
            p += 68 + 4 * i32(d, p + 44)   # paso VARIABLE: 68 + 4N (corregido el 5/10)
        print(f"  {etiqueta}")
        print(f"      encadenan {encadenan} de {e['ExportCount']}"
              f"   primer fallo: {primer_fallo}")
    print()

    # ------------------------------------------------------------------
    # La entrada de exportacion mide 68 bytes MAS 4 por cada objeto de red de
    # su generacion. Los 260 bytes que sobran sobre 68 dan 65 en total, que es
    # un numero entero: esa es la cola variable, y explica el fallo de la
    # cadena justo en la exportacion 108.197.
    #
    # Se recorre la tabla entera con esa regla. La prueba es que termine
    # exactamente en DependsOffset: son 12.625.072 bytes y 185.659 entradas,
    # y una regla equivocada se desvia mucho antes de llegar.
    # ------------------------------------------------------------------
    print("=== Recorrido completo con la cola variable ===")
    import os
    total = os.path.getsize(sys.argv[1])
    p = e["ExportOffset"]
    objetos_red = 0
    encadenan = 0
    fuera_de_rango = 0
    dentro_del_encabezado = 0
    anterior = None
    bajo, alto = None, 0
    for k in range(e["ExportCount"]):
        size = i32(d, p + 32)
        data = i32(d, p + 36)
        cuenta_red = i32(d, p + 44)
        if not (0 <= cuenta_red < 64):
            print(f"  DESAJUSTE en la exportacion {k}: cuenta_red={cuenta_red}")
            return 1
        objetos_red += cuenta_red

        if size > 0:
            if data < e["DependsOffset"]:
                dentro_del_encabezado += 1
            if data < 0 or data + size > total:
                fuera_de_rango += 1
            if anterior is not None and data == anterior[0] + anterior[1]:
                encadenan += 1
            anterior = (data, size)
            bajo = data if bajo is None else min(bajo, data)
            alto = max(alto, data + size)

        p += 68 + 4 * cuenta_red

    con_datos = sum(1 for so, ss in tamanos if ss > 0)
    print(f"  entradas recorridas: {e['ExportCount']}")
    print(f"  objetos de red en total: {objetos_red}  ->  "
          f"{objetos_red * 4} bytes de cola")
    print(f"  cierra en {p}, DependsOffset={e['DependsOffset']}  ->  "
          f"{'OK' if p == e['DependsOffset'] else 'DESAJUSTE'}")
    print()
    print("  --- semantica de SerialSize(+32) y SerialOffset(+36) ---")
    print(f"  exportaciones con datos: {con_datos}")
    print(f"  parejas consecutivas que encadenan: {encadenan} de {con_datos - 1}")
    print(f"  datos que empiezan dentro del encabezado: {dentro_del_encabezado}")
    print(f"  datos fuera del fichero: {fuera_de_rango}")
    print(f"  primer dato en {bajo}, ultimo fin en {alto}, fichero {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
