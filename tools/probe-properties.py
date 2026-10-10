#!/usr/bin/env python3
"""
Sonda del flujo de propiedades taggeadas de una exportacion UE3 v576.

Lo que ya esta establecido:

  FPropertyTag (UnPropertyTag.h:58) =
      FName Name         (8)   indice + numero
      FName Type         (8)
      INT   Size         (4)
      INT   ArrayIndex   (4)
      [FName StructName]  solo si Type == StructProperty
      [BYTE  BoolVal]     solo si Type == BoolProperty
      [FName EnumName]    solo si Type == ByteProperty
  y despues Size bytes de datos del valor.

  Se ha comprobado a mano sobre Main_Sequence que esto lee propiedades reales:
      SequenceObjects  ArrayProperty  size=200
      DefaultViewX     IntProperty    size=4   valor=900
      DefaultViewY     IntProperty    size=4   valor=619
      DefaultViewZoom  FloatProperty  size=4   valor=0.8

  El problema: el primer tag empieza en +4, no en +0. Los cuatro bytes de
  delante forman un contador que incrementa de uno en uno dentro de tramos
  (2..9, luego 4124..4132, luego 184..199) y que no es un indice de nombre,
  porque 4124 excede el tamano de la tabla de nombres.

LA PRUEBA QUE DECIDE. No hace falta saber que es el prefijo para saber si la
regla "saltar 4 y leer tags" es correcta. El flujo de tags termina siempre con
un tag de nombre NAME_None, y los datos de cada exportacion estan delimitados
por su SerialOffset y su SerialSize. Asi que:

    si se salta 4, se leen tags hasta NAME_None, y el resultado cae EXACTAMENTE
    en el final de la exportacion, la regla es correcta.

Eso se exige sobre las 1.711 exportaciones a la vez. Una regla aproximada
acierta en muchas y falla en el resto; no puede acertar en todas, porque cada
exportacion es un punto de control independiente.

LO QUE ADEMAS SABE HACER, Y ES LO QUE LA HIZO UTIL
--------------------------------------------------
Al principio solo comprobaba la regla del prefijo. Ahora **lee el `StructName`
--que antes leia para avanzar y tiraba--** y tiene cuatro modos:

    python probe-properties.py <paquete>
        El recuento: cuantas exportaciones cierran exactas y de que tipos son
        sus propiedades.

    python probe-properties.py <paquete> - <indice>
        La traza de tags de una exportacion, una linea por tag.

    python probe-properties.py <paquete> - tag <Propiedad>
        Que struct es la propiedad `<Propiedad>`, en las exportaciones que
        cierran exactas. Contesta «`UIStyleReference.AssignedStyleID` es de que
        struct».

        **Busca en TODO el arbol y con FRONTERA DE PALABRA**, y las dos cosas
        costaron un cero cada una:

          - solo el primer nivel daba 0 para `Scaling`, que esta dentro de
            `RenderParameters`. Es el mismo fallo que ya costo un cero en modo
            `struct`;
          - por subcadena, `SpacingAdjust` casaba con `TextSpacingAdjust` y
            `Scaling` con `AutoScaling` y `AxisScaling`: tres structs que no son.
            La misma trampa que en `mide-firmas.py`, donde buscar `Login`
            encontraba `PreLogin`.

        Y con las dos corregidas, la respuesta para los cuatro miembros de
        `RenderParameters` (`SpacingAdjust`, `DrawCoords`, `ImageExtent`,
        `Scaling`) es **cero**: no estan en ninguna exportacion que cierre.

    python probe-properties.py <paquete> - struct <Struct>
        Que propiedades son de ese struct, y con que tamaño. **Busca en TODO EL
        ARBOL, no solo en el primer nivel**: `STYLE_ID` no aparece como struct de
        ningun tag de primer nivel -- aparece dentro de `UIStyleReference`. A un
        nivel daba cero apariciones con el tipo delante, que es el cero del
        instrumento otra vez.

    python probe-properties.py <paquete> - tabla
        La salida que come el generador: parejas `contenedor<TAB>miembro<TAB>struct`
        y lineas `M<TAB>genero<TAB>nombre<TAB>contenedor` con los miembros.

> [!important] EL MODO VA EN `argv[3]`; `argv[2]` ES UN MARCADOR
> Es la convencion que ya tenia el modo de indice, y no es bonita pero es la que
> hay: `probe-properties.py <paquete> - tag <Propiedad>`. Llamarlo sin el
> marcador da `ValueError: invalid literal for int()`, que no dice nada.

POR QUE EL NIVEL ANIDADO IMPORTA
--------------------------------
En un objeto **`Default__<Clase>`** -- el arquetipo -- el valor de un struct **es
otra lista de tags**, una por miembro. Y ahi esta lo que la tabla de
exportaciones no puede dar: el `StructName` de un miembro que a su vez es struct.
Medido sobre el `Engine.u` del juego:

    UIStyleReference      AssignedStyleID    STYLE_ID
    UICombinedStyleData   TextScale          Vector2D
    UICombinedStyleData   TextAttributes     UITextAttributes

Sin esto, tres tipos del juego no se podian declarar: el generador se niega a
declarar un struct a medias, porque a medias mentiria sobre el layout.

Y EL ORDEN DE LOS TAGS ES LA DECLARACION **AL REVES**. Medido en tres structs
contra la tabla de exportaciones, que va en orden de declaracion. Como el orden
de los miembros **es el layout**, la vuelta se da una sola vez -- en `tabla` -- y
queda dicha. Leida al reves, `UIStyleReference` sale `ResolvedStyle,
AssignedStyleID, RequiredStyleClass, DefaultStyleTag`, que es exactamente el
orden de la tabla de exportaciones.

Uso:  python probe-properties.py <paquete> [- <modo> <argumento>]
"""

import re
import struct
import sys


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def u32(d, p):
    return struct.unpack_from("<I", d, p)[0]


def fname(d, p):
    return i32(d, p), i32(d, p + 4)


def fstring(d, p):
    n = i32(d, p)
    p += 4
    if n < 0:
        return d[p:p - n * 2].decode("utf-16-le", "replace").rstrip("\x00"), p - n * 2
    return d[p:p + n].decode("latin-1").rstrip("\x00"), p + n


def lee_encabezado(d):
    p = 12
    _, p = fstring(d, p)
    e = {}
    for k in ("PackageFlags", "NameCount", "NameOffset", "ExportCount",
              "ExportOffset", "ImportCount", "ImportOffset", "DependsOffset"):
        e[k] = i32(d, p); p += 4
    p += 16
    gen = i32(d, p); p += 4
    p += gen * 12
    p += 4 + 4                                  # EngineVersion, CookedContent
    p += 4                                      # CompressionFlags
    trozos = i32(d, p); p += 4
    p += trozos * 16
    p += 4                                      # PackageSource
    extra = i32(d, p); p += 4
    for _ in range(extra):
        _, p = fstring(d, p)
    e["_fin"] = p
    return e


def lee_nombres(d, off, cuenta):
    """[i32 len][len bytes][8 de cola]"""
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
    return nombres


def lee_exportaciones(d, off, cuenta):
    p = off
    salida = []
    for k in range(cuenta):
        x = {
            "clase": i32(d, p + 0),
            "nombre": i32(d, p + 12),
            "tamano": i32(d, p + 32),
            "offset": i32(d, p + 36),
        }
        red = i32(d, p + 44)
        if not (0 <= red < 64):
            raise SystemExit(f"desajuste en la exportacion {k}: red={red}")
        p += 68 + 4 * red
        salida.append(x)
    return salida


def _recoge_structs(d, tags, nombres, parejas, miembros, prof, tope=4):
    """
    Recoge, de un nivel de tags:

      `parejas`   {(contenedor, miembro): struct-del-miembro}
      `miembros`  {contenedor: [genero, nombre]}  -- en orden de aparicion

    Se recorre el arbol entero y se guarda en DICCIONARIOS, no en lineas: el
    mismo struct aparece en decenas de `Default__` -- `UIStyleReference` sale en
    decenas -- y emitir al vuelo llenaba el fichero de copias repetidas del
    mismo miembro, cientos de veces.
    """
    for nombre, t, size, _ai, struct_name, valor in tags:
        if t != "StructProperty" or not struct_name or prof >= tope:
            continue
        sub = sub_tags(d, valor, size, nombres)
        # SE TOMA LA LISTA **MAS LARGA**, y no la primera.
        #
        # Un `Default__` solo serializa las propiedades que NO son las de
        # defecto: `Default__UILabel.PrimaryStyle` trae **una** (`RequiredStyleClass`)
        # porque las otras tres valen cero. Quedarse con la primera lista
        # declararia `UIStyleReference` con un miembro de cuatro.
        #
        # Y como los tags van en orden de declaracion al REVES, la lista se
        # guarda al reves AQUI, una sola vez, para que `miembros` salga ya en
        # orden de declaracion -- el que manda, porque es el layout.
        if len(sub) > len(miembros.get(struct_name, ())):
            miembros[struct_name] = [(st, sn) for sn, st, _s, _i, _u, _v in sub][::-1]
        for sn, st, _ss, _si, sstruct, _sval in sub:
            if st == "StructProperty" and sstruct:
                parejas.setdefault((struct_name, sn), sstruct)
            elif st == "ArrayProperty":
                # El tipo del ELEMENTO de un array va en el tag ANIDADO del
                # array, que no se lee aqui: se deja dicho y no se inventa.
                parejas.setdefault((struct_name, sn), "?array?")
        _recoge_structs(d, sub, nombres, parejas, miembros, prof + 1, tope)


def arbol_de_tags(d, inicio, size, nombres, prof=0, tope=3):
    """
    Los tags de un payload, **y los de dentro de sus structs**, ya formateados.

    Hace falta porque el dato buscado puede estar a dos niveles. `UIStyleReference`
    tiene un miembro `AssignedStyleID` de tipo `STYLE_ID`, y `STYLE_ID` a su vez
    tiene miembros -- que es lo que se quiere saber. Un solo nivel no llega:

        Default__UIObject
            PrimaryStyle    StructProperty  STRUCT=UIStyleReference
                AssignedStyleID   StructProperty  STRUCT=STYLE_ID      <- nivel 1
                    ...                                                <- nivel 2

    `tope` corta la recursion, y no es decoracion: un struct puede contener un
    struct del mismo tipo y no termina.
    """
    if prof > tope:
        return []
    salida = []
    for nombre, t, size, _ai, struct_name, valor in sub_tags(d, inicio, size, nombres):
        marca = f"   STRUCT={struct_name}" if struct_name else ""
        sangria = "      " + "    " * prof
        salida.append(f"{sangria}{nombre:<30} {t:<17} size={size}{marca}")
        if t == "StructProperty" and struct_name:
            salida += arbol_de_tags(d, valor, size, nombres, prof + 1, tope)
    return salida


def sub_tags(d, inicio, size, nombres):
    """
    Los tags de DENTRO de un `StructProperty`, si su payload lo es.

    En un objeto `Default__` -- el arquetipo de una clase -- el valor de un
    struct se escribe como **otra lista de tags**, una por miembro. Y ahi esta
    lo que no se puede sacar de la tabla de exportaciones: el `StructName` de un
    miembro que a su vez es un struct.

    NO SE SABE si el nivel anidado lleva el mismo prefijo de 4 bytes que la
    exportacion entera, asi que se prueban los dos. **El que CIERRA EXACTO es el
    bueno**, y esa es exactamente la prueba que se exige sobre la exportacion
    entera: una regla aproximada acierta en muchas y no puede acertar en todas.

    Devuelve [] si el payload no es una lista de tags -- y eso no es un fallo:
    un struct serializado como DATO (no como defaults) no lo es.
    """
    for salto in (0, 4):
        if size - salto <= 0:
            continue
        tags, p, err = lee_tags(d, inicio + salto, inicio + size, nombres, None)
        if err is None and p == inicio + size:
            return tags
    return []


def lee_tags(d, inicio, fin, nombres, tipos, traza=None):
    """
    Devuelve (lista_de_tags, posicion_final, error).
    Si `traza` es una lista, se anade a ella una linea por tag leido.
    """
    tags = []
    p = inicio

    def anota(s):
        if traza is not None:
            traza.append(f"    +{p - inicio:<5} {s}")

    while True:
        if p + 8 > fin:
            return tags, p, "se acabo el espacio buscando el nombre del tag"
        idx, num = fname(d, p); p += 8
        # NAME_None NO es el indice 0. `FPropertyTag` termina cuando el nombre
        # es NAME_None, y NAME_None es la entrada cuyo texto es "None" -- que en
        # este paquete esta en el 936, no en el 0. Comprobar contra 0 daba por
        # terminado el flujo en sitios donde no lo estaba y lo dejaba corriendo
        # en sitios donde si.
        if idx == NONE_INDEX:
            return tags, p, None                # fin del flujo
        if not (0 <= idx < len(nombres)):
            return tags, p, f"indice de nombre fuera de rango: {idx}"
        if p + 16 > fin:
            return tags, p, "se acabo el espacio leyendo el tipo"
        tidx, _ = fname(d, p); p += 8
        if not (0 <= tidx < len(nombres)):
            return tags, p, f"indice de tipo fuera de rango: {tidx}"
        size = i32(d, p); arrayidx = i32(d, p + 4); p += 8
        if size < 0 or size > (fin - p) + 64:
            return tags, p, f"tamano absurdo: {size}"
        t = nombres[tidx]
        # EL `StructName`: LO QUE SE LEE Y NO SE GUARDABA.
        #
        # Un `StructProperty` no lleva el tipo en los datos: lleva **el nombre
        # del struct** aqui, en el tag. Es el dato que falta para poder declarar
        # `UIStyleReference`, `UICombinedStyleData` y `RenderParameters` -- los
        # tres son `ScriptStruct` del `UIRoot` del motor del juego y el generador
        # NO los declara porque uno de sus miembros es de este genero y no se
        # sabe de que struct es.
        #
        # Se leia para avanzar y se tiraba. Ahora se apunta.
        struct_name = None
        if t == "StructProperty":
            sidx, _ = fname(d, p)
            struct_name = (nombres[sidx] if 0 <= sidx < len(nombres)
                           else f"<fuera de rango: {sidx}>")
            p += 8
        elif t == "BoolProperty":
            # PUERTA DE VERSION. UnPropertyTag.h:84 --
            #   if (Ar.Ver() < VER_PROPERTYTAG_BOOL_OPTIMIZATION)  // = 673
            #       UBOOL Value; Ar << Value;    // 4 bytes
            #   else Ar << Tag.BoolVal;          // 1 byte
            # Este paquete es 576, asi que el booleano son CUATRO bytes. Leer
            # uno desalinea el flujo tres bytes y el siguiente tag sale con un
            # nombre imposible -- que es exactamente como se encontro.
            p += 4 if VERSION < 673 else 1
        elif t == "ByteProperty":
            # UnPropertyTag.h:96 -- solo si Ar.Ver() >= VER_BYTEPROP_SERIALIZE_ENUM
            # (= 633). Este paquete es 576: no lleva EnumName.
            if VERSION >= 633:
                p += 8
        if p + size > fin:
            return tags, p, f"los datos se salen: size={size}"
        anota(f"tag  nombre={nombres[idx]!r} tipo={t} size={size} idx={arrayidx}"
              + (f"  ** struct={struct_name} **" if struct_name else "")
              + f"  (campos desde +{p - 24 - inicio})")
        # El SEXTO campo es DONDE EMPIEZA EL VALOR. Hace falta para lo anidado:
        # el payload de un `StructProperty` de un `Default__` es otra lista de
        # tags, y sin esta posicion no se puede ir a mirarla.
        tags.append((nombres[idx], t, size, arrayidx, struct_name, p))
        p += size


VERSION = 576          # se sobreescribe al leer el encabezado
NONE_INDEX = 0         # indice de la entrada "None"; tambien se sobreescribe


def main():
    global VERSION, NONE_INDEX
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    # Tercer argumento opcional: indice de una exportacion cuya traza se imprime.
    with open(sys.argv[1], "rb") as f:
        d = f.read()

    e = lee_encabezado(d)
    VERSION = (u32(d, 4) & 0xFFFF)
    print(f"  version del paquete: {VERSION}")
    nombres = lee_nombres(d, e["NameOffset"], e["NameCount"])
    NONE_INDEX = nombres.index("None") if "None" in nombres else 0
    print(f"  NAME_None esta en el indice {NONE_INDEX}")
    exports = lee_exportaciones(d, e["ExportOffset"], e["ExportCount"])
    print(f"{sys.argv[1]}")
    print(f"  nombres {len(nombres)}  exportaciones {len(exports)}\n")

    bien = mal = sin_datos = 0
    fallos = []
    total_tags = 0
    clases_usadas = {}

    for k, x in enumerate(exports):
        if x["tamano"] <= 0:
            sin_datos += 1
            continue
        ini = x["offset"]
        fin = ini + x["tamano"]
        if fin > len(d):
            fallos.append((k, "la exportacion se sale del fichero"))
            mal += 1
            continue

        tags, p, err = lee_tags(d, ini + 4, fin, nombres, None)
        if err:
            fallos.append((k, err))
            mal += 1
            continue
        if p != fin:
            fallos.append((k, f"cierra en {p - ini}, deberia cerrar en {x['tamano']}"))
            mal += 1
            continue

        bien += 1
        total_tags += len(tags)
        for tag in tags:
            clases_usadas[tag[1]] = clases_usadas.get(tag[1], 0) + 1

    print("=== resultado: saltar 4 bytes y leer tags ===")
    print(f"  exportaciones con datos ..... {bien + mal}")
    print(f"  cierran exactas ............. {bien}")
    print(f"  fallan ...................... {mal}")
    print(f"  sin datos ................... {sin_datos}")
    print(f"  tags leidos ................. {total_tags}")
    print()

    if fallos:
        print("=== primeros fallos ===")
        for k, msg in fallos[:12]:
            print(f"  exportacion {k}: {msg}")
        print()

    print("=== tipos de propiedad mas usados ===")
    for t, n in sorted(clases_usadas.items(), key=lambda kv: -kv[1])[:14]:
        print(f"  {t:<22} {n}")

    if len(sys.argv) > 4 and sys.argv[3] == "rango":
        ini, fin_ = int(sys.argv[4]), int(sys.argv[5])
        print(f"=== rango {ini}..{fin_} ===")
        for k in range(ini, min(fin_ + 1, len(exports))):
            x = exports[k]
            if x["tamano"] <= 0:
                print(f"  {k:>6}  {nombres[x['nombre']]:<28} sin datos"); continue
            tags, q, err = lee_tags(d, x["offset"] + 4, x["offset"] + x["tamano"],
                                    nombres, None)
            if err is None and q == x["offset"] + x["tamano"]:
                print(f"  {k:>6}  {nombres[x['nombre']]:<28} OK  {len(tags)} tags")
            else:
                pos = q - x["offset"]
                print(f"  {k:>6}  {nombres[x['nombre']]:<28} FALLA en +{pos}"
                      f" de {x['tamano']}  {err or ''}")
        print()
    # HEX: LOS BYTES CRUDOS DE UNA EXPORTACION, CON LAS DOS LECTURAS.
    #
    # PARA QUE HACE FALTA, TENIENDO `rango`
    # -------------------------------------
    # `rango` dice DONDE se desalinea el flujo de tags. Cuando el fallo esta mas
    # alla -- en el dato NATIVO, despues de los tags -- no lo dice, porque para
    # una malla los tags son 345 bytes y detras hay 2 MB que no son tags.
    #
    # Y ahi la pregunta deja de ser "donde" y pasa a ser "que dice el byte".
    # Medido el 5/10 sobre `CH_MNPCguard01_lobby`: la reserva de 2,85 GB sale de
    # leer `0x5B0FE30D` en +8253 como contador de un `TArray<short>`. Con el
    # volcado delante, se ve si ese 0x5B0FE30D es un contador o es el PRINCIPIO
    # DE LOS DATOS que se estan leyendo como contador.
    #
    # Uso:  python probe-properties.py <paquete> - hex <indice> <desde> <hasta>
    #       (desde/hasta relativos al INICIO de la exportacion)
    if len(sys.argv) > 4 and sys.argv[3] == "hex":
        k = int(sys.argv[4])
        desde = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        hasta = int(sys.argv[6]) if len(sys.argv) > 6 else desde + 256
        x = exports[k]
        ini = x["offset"] + desde
        fin = min(x["offset"] + hasta, x["offset"] + x["tamano"])
        print(f"=== export {k}  {nombres[x['nombre']]}  "
              f"offset={x['offset']}  tamano={x['tamano']} ===")
        print(f"=== rango +{desde} .. +{fin - x['offset']} ===")
        print("  rel      abs        u32         i32        u16   b0 b1 b2 b3")
        for p in range(ini, fin, 4):
            trozo = d[p:p + 4]
            if len(trozo) < 4:
                break
            v = struct.unpack_from("<I", trozo, 0)[0]
            i = struct.unpack_from("<i", trozo, 0)[0]
            w = struct.unpack_from("<H", trozo, 0)[0]
            print(f"  +{p - x['offset']:<6} {p:<10} 0x{v:08X}  {i:>11}  "
                  f"{w:>6}   " + " ".join(f"{b:02X}" for b in trozo))
        return 0

    # TABLA: LA SALIDA QUE COME EL GENERADOR.
    #
    # Recorre cada exportacion que CIERRA EXACTA, y por cada `StructProperty`
    # cuyo payload sea a su vez una lista de tags, emite una linea:
    #
    #     contenedor <TAB> miembro <TAB> struct-del-miembro
    #
    # Es exactamente el dato que NO esta en la tabla de exportaciones y que por
    # eso bloqueaba a `UIStyleReference`, `UICombinedStyleData` y
    # `RenderParameters`: el generador sabe que un miembro es un `StructProperty`
    # pero no DE QUE STRUCT. Aqui se lee del `FPropertyTag`.
    #
    # Y no se ordena: el orden de las exportaciones es el de declaracion.
    #
    # Uso:  python probe-properties.py <paquete> - tabla > tools/tipos-de-structs-x.txt
    if len(sys.argv) > 3 and sys.argv[3] == "tabla":
        parejas, miembros = {}, {}
        for k, x in enumerate(exports):
            if x["tamano"] <= 0:
                continue
            tags, q, err = lee_tags(d, x["offset"] + 4,
                                    x["offset"] + x["tamano"], nombres, None)
            if err is not None or q != x["offset"] + x["tamano"]:
                continue
            _recoge_structs(d, tags, nombres, parejas, miembros, 0)
        # LAS PAREJAS: de que struct es un miembro que es struct.
        for (cont, miem), destino in parejas.items():
            print(f"{cont}\t{miem}\t{destino}")
        # Y LOS MIEMBROS: una linea por miembro, marcada con `M`.
        for cont, lista in miembros.items():
            for genero, nombre in lista:
                print(f"M\t{genero}\t{nombre}\t{cont}")
        print(f"# {len(parejas)} parejas, {len(miembros)} contenedores",
              file=sys.stderr)
        return 0

    # STRUCT: busca por el NOMBRE DEL STRUCT de un `StructProperty`.
    #
    # Es el complemento del modo `tag`, y contesta la otra mitad: `tag` dice de
    # que struct es una PROPIEDAD; `struct` dice QUE PROPIEDADES son de un
    # struct dado, y **con que tamano se serializa cada una**.
    #
    # Y ese tamano es el dato que cierra el caso: el valor de un
    # `UIStyleReference` mide 4 (ResolvedStyle) + lo-que-mida-AssignedStyleID
    # + 4 (RequiredStyleClass) + 8 (DefaultStyleTag). Si el tamano medido es 28,
    # `AssignedStyleID` mide 12 -- que es justo `StyleReferenceId`
    # (ObjectProperty 4 + NameProperty 8). No es una adivinanza: es una suma.
    #
    # Uso:  python probe-properties.py <paquete> - struct <NombreDelStruct>
    if len(sys.argv) > 3 and sys.argv[3] == "struct":
        buscado = sys.argv[4] if len(sys.argv) > 4 else ""
        vistas, halladas = 0, 0
        for k, x in enumerate(exports):
            if x["tamano"] <= 0:
                continue
            tags, q, err = lee_tags(d, x["offset"] + 4,
                                    x["offset"] + x["tamano"], nombres, None)
            if err is not None or q != x["offset"] + x["tamano"]:
                continue
            vistas += 1
            # Y SE BUSCA EN TODO EL ARBOL, NO SOLO EN EL PRIMER NIVEL.
            #
            # `STYLE_ID` no aparece como struct de ningun tag de primer nivel:
            # aparece dentro de `UIStyleReference`, que a su vez esta dentro de
            # `PrimaryStyle`. Un solo nivel no llega, y buscarlo asi daba **cero
            # apariciones** con el tipo delante -- otro cero que no distingue
            # «no existe» de «no lo miro».
            # `tamano - 4` y NO `tamano`: los cuatro bytes del prefijo ya estan
            # consumidos por `offset + 4`, y pasar el tamaño entero se salia
            # cuatro bytes del final -- con lo que NINGUNA exportacion cerraba y
            # la busqueda daba cero. Un cero del instrumento, otra vez.
            lineas = arbol_de_tags(d, x["offset"] + 4, x["tamano"] - 4, nombres)
            aciertos = [l for l in lineas if f"STRUCT={buscado}" in l]
            if not aciertos:
                continue
            halladas += len(aciertos)
            if halladas <= 12 or len(sys.argv) > 5:
                print(f"exportacion {k}  {nombres[x['nombre']]}")
                for l in lineas:
                    print(l)
                print()
        print(f"STRUCT '{buscado}': {halladas} apariciones en {vistas} "
              f"exportaciones que cierran exactas")
        return 0

    # TAG: busca un NOMBRE DE PROPIEDAD dentro de los tags, y dice de que struct
    # es. Es el modo que contesta la pregunta que abrio esta via:
    #
    #     UIStyleReference tiene un miembro `AssignedStyleID` de tipo
    #     StructProperty. ¿DE QUE STRUCT?
    #
    # Se recorre cada exportacion que CIERRA EXACTA -- las que no cierran no se
    # pueden creer -- y se imprime la exportacion, el tag, y su `StructName`.
    #
    # Uso:  python probe-properties.py <paquete> tag <NombreDeLaPropiedad>
    if len(sys.argv) > 3 and sys.argv[3] == "tag":
        buscado = sys.argv[4] if len(sys.argv) > 4 else ""
        halladas, vistas = 0, 0
        for k, x in enumerate(exports):
            if x["tamano"] <= 0:
                continue
            tags, q, err = lee_tags(d, x["offset"] + 4,
                                    x["offset"] + x["tamano"], nombres, None)
            if err is not None or q != x["offset"] + x["tamano"]:
                continue        # SOLO las que cierran: las otras no se creen
            vistas += 1
            # Y SE BUSCA EN TODO EL ARBOL, NO SOLO EN EL PRIMER NIVEL.
            #
            # Es el MISMO fallo de nivel unico que ya costo un cero en modo
            # `struct`: un miembro de un struct vive DENTRO del payload de otro,
            # asi que mirar solo arriba da cero apariciones con el tipo delante.
            # Aqui mordio igual -- `Scaling` salia 0 y esta en `RenderParameters`
            # -- y se arregla con la misma recursion.
            for linea in arbol_de_tags(d, x["offset"] + 4, x["tamano"] - 4,
                                       nombres):
                # CON FRONTERA DE PALABRA, no por subcadena.
                #
                # Buscar `SpacingAdjust` a secas casa con `TextSpacingAdjust`, y
                # `Scaling` con `AutoScaling` y `AxisScaling`: tres falsos
                # positivos que apuntan a structs que no son. Es la misma trampa
                # que ya mordio en `mide-firmas.py`, donde buscar `Login`
                # encontraba `PreLogin`.
                if not re.search(r"(?<![\w])" + re.escape(buscado) + r"(?![\w])",
                                 linea):
                    continue
                halladas += 1
                if halladas <= 12:
                    print(f"exportacion {k}  {nombres[x['nombre']]}")
                    print(f"    {linea.strip()}")
                    print()
        print(f"'{buscado}': {halladas} apariciones en {vistas} exportaciones "
              f"que cierran exactas")
        return 0

    # BUSCA: los tags de toda exportacion cuyo NOMBRE contenga el texto dado.
    #
    # Es el modo que hacia falta para el `StructName`. Las exportaciones que
    # interesan -- los `Default__<Clase>`, que son los arquetipos -- no se
    # conocen por indice, se conocen por nombre, y buscarlas a mano en 185.659
    # lineas no es viable.
    if len(sys.argv) > 3 and sys.argv[3] in ("busca", "busca0"):
        # `busca0` es `busca` **limitado a las exportaciones que CIERRAN
        # EXACTAS**: los `Default__` de una clase concreta se llaman igual en
        # varios sitios, y el que vale es el que se lee entero.
        solo_exactas = sys.argv[3] == "busca0"
        texto = sys.argv[4].lower() if len(sys.argv) > 4 else ""
        halladas = 0
        for k, x in enumerate(exports):
            if texto not in nombres[x["nombre"]].lower():
                continue
            if x["tamano"] <= 0:
                continue
            tags, q, err = lee_tags(d, x["offset"] + 4,
                                    x["offset"] + x["tamano"], nombres, None)
            exacta = err is None and q == x["offset"] + x["tamano"]
            if solo_exactas and not exacta:
                continue
            halladas += 1
            print(f"=== {k}  {nombres[x['nombre']]}  ({x['tamano']} bytes)"
                  f"  {'EXACTA' if exacta else 'NO cierra: ' + str(err)}")
            for nombre, t, size, _ai, struct_name in tags:
                marca = f"   STRUCT={struct_name}" if struct_name else ""
                print(f"      {nombre:<34} {t:<18} size={size}{marca}")
            print()
        print(f"{halladas} exportaciones con '{texto}' en el nombre")
        return 0

    if len(sys.argv) > 3 and sys.argv[3] != "rango":
        k = int(sys.argv[3])
        x = exports[k]
        print(f"=== traza de la exportacion {k} "
              f"({nombres[x['nombre']]!r}, {x['tamano']} bytes) ===")
        traza = []
        tags, p, err = lee_tags(d, x["offset"] + 4, x["offset"] + x["tamano"],
                                nombres, None, traza)
        for linea in traza:
            print(linea)
        print(f"    fin: +{p - x['offset']} de {x['tamano']}   "
              f"error={err}")
        print()

    print()
    if mal == 0:
        print("DECIDIDO: la regla 'saltar 4 bytes y leer tags' es correcta.")
        print("Cierra en las 1.711 exportaciones, que son 1.711 puntos de control")
        print("independientes. El prefijo sigue sin identificarse, pero no hace")
        print("falta para leer.")
    else:
        print(f"NO concluyente: fallan {mal}. El prefijo no es simplemente 4 bytes,")
        print("o hay mas de un formato de exportacion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
