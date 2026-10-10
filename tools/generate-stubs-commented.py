#!/usr/bin/env python3
"""
Genera los stubs de guion que el mapa de CrimeCraft necesita.

POR QUE
-------
El mapa importa clases de `CrimeCraft` (`CCEntryPawn`, `SeqVar_CCBoolStates`,
`PositionPreset`...) y el motor no las encuentra. Cargar el `CrimeCraft.u` del
juego no vale: se cocino en el build 4701 y el motor del SDK es el 10897, y se
desincroniza. La via decidida es **stubs**: declarar las clases para que el motor
pueda deserializar lo que el mapa guardo, sin reproducir comportamiento.

EL VEHICULO, que ya existia y esta documentado en DefaultEngine.ini:

    EditPackagesInPath=..\\..\\Development\\Src
    +EditPackages=<Paquete>          <- y que exista Development\\Src\\<Paquete>\\Classes

El motor compila esos `.uc` a `DemoGame/Script/<Paquete>.u`. `EditPackages=DemoGame`
esta desactivado justo porque no existe su carpeta de fuentes — asi que la
carpeta, no la linea, es lo que decide.

QUE HACE ESTE SCRIPT
--------------------
Coge los `.uc` de `uscript_export/CrimeCraft/` y los adapta a stub. La
transformacion es corta y mecanica:

  - quita `native` de la declaracion de clase: un stub no tiene mitad en C++, y
    sin el, el compilador espera guion, que es lo que le vamos a dar;
  - marca los ARTEFACTOS DE EXTRACCION, que son lineas que no son UnrealScript
    valido: `Components=/* Array type was not detected. */`, los comentarios de
    flags como `/*0x20000000-0x00000000*/`, y las lineas `// Reference:` /
    `// TemplateOwner*` / `// Archetype:`;
  - deja el destino REFLEJANDO la lista: retira los `.uc` de clases que la
    lista ya no pide. El compilador lee la carpeta, no la lista, asi que un
    stub obsoleto se compila igual y arrastra sus propios tipos sin resolver.

LO QUE ESTE SCRIPT NO COMPRUEBA, y su docstring decia que si
------------------------------------------------------------
Aqui ponia "comprueba que TODO tipo referenciado resuelve". **Era falso.**
`tipos_del_sdk()` se calculaba y solo se usaba para imprimir su tamano; no
comprobaba nada. Se descubrio al ir a mirar por que el compilador encontraba
tipos sin resolver que la lista de clases ya tenia.

No se ha implementado, y es a proposito: quien comprueba eso, y bien, es el
compilador de guion. Tarda diez segundos en llegar al paquete y da el nombre
exacto del tipo y la linea. Reimplementarlo aqui en aproximado solo anadiria
una fuente de falsos positivos que habria que depurar aparte.

LO QUE NO HACE, y es a proposito
--------------------------------
No decide nada por su cuenta sobre lo que no entiende: **lo reporta**. Un
generador que arregla en silencio los artefactos que no comprende produce stubs
que compilan y no hacen lo que parece.

Uso:  python tools/generate-stubs.py [--dry-run]
"""

import collections
import io
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# DONDE ESTAN LOS CATALOGOS (`tipos-del-juego.txt` y compania, ~5,5 MB) y la lista
# de clases. **No se distribuyen**: son DERIVADOS -- `ue3-packer types` volcando los
# paquetes del juego -- y los paquetes tampoco se distribuyen. Aqui apuntan al
# lado del propio guion, que es donde los pondria quien los genere; en ESTE
# proyecto se pasan con `--datos tools`.
DATOS = os.path.dirname(os.path.abspath(__file__))
ORIGEN = os.path.join(RAIZ, "uscript_export", "CrimeCraft")
SDK = os.path.join(RAIZ, "ue-CodeRedModding", "Development", "Src")
DESTINO = os.path.join(SDK, "CrimeCraftStubs", "Classes")

# EL NOMBRE DEL PAQUETE ES EL DE LA CARPETA, asi que se DERIVA y no se escribe.
# Si el paquete se renombra, la regla de `reescribe_paquete()` lo sigue sola --
# que es justo lo contrario de lo que pasaba antes: el codigo decia `CrimeCraft.`
# y la reconstruccion vivia en `CrimeCraftStubs`, y nada ataba las dos cosas.
PAQUETE_NUEVO = os.path.basename(os.path.dirname(DESTINO))   # CrimeCraftStubs
PAQUETE_VIEJO = os.path.basename(ORIGEN)                     # CrimeCraft

# Cuantas referencias de paquete se reescribieron, POR CLASE. Es un total que se
# imprime una vez y no un aviso por clase: la regla es uniforme --274 clases, y
# el mismo texto en todas--, y 274 lineas iguales en el informe taparian las
# pocas que de verdad dicen algo. Ver `reescribe_paquete()`.
PAQUETE_REESCRITO = {}

# Cuantos casts a `int` se quitaron, y por que se dejaron los que se dejaron.
# Por clase, y con los motivos: el numero solo no dice si la regla esta
# acertando -- lo que lo dice es que los motivos sean los esperados.
CASTS_INT = {}

# `goto` de `foreach` reescritos a `continue`/`break`, y por que.
GOTO_FOREACH = {}

# Y los pre-operadores sin parentesis que se han arreglado, o dejado.
PREOPERADOR = {}

# La marca de procedencia, EN LOS 742. Antes solo la llevaba `CCStubTipos.uc`
# --que se escribe aparte, fuera del bucle-- y los otros 741 no: un `.uc` sin
# marca no se distingue de uno escrito a mano.
#
# Importa mas desde que `comprueba-cobertura.py limpiar` YA NO regenera: un
# arreglo hecho a mano en un stub ahora persiste, asi que conviene que se vea
# que ese fichero no se edita. Si hay que cambiarlo, se cambia el generador.
#
# SIN BOM, y esto no es un detalle: el BOM ha mordido siete veces en este
# proyecto. `io.open(..., encoding="utf-8")` no lo escribe.
CABECERA = ("// GENERADO POR tools/generate-stubs.py desde uscript_export/ — NO EDITAR A MANO.\n"
            "// Para cambiarlo: se cambia el generador y se vuelve a pasar.\n"
            "\n")


# >>> PALANCA: `exec` delante cuando la declaracion lleva banderas de red.
# Ver el comentario largo en el sitio donde se usa.
#
# >>> MEDIDA, y SE APAGA. Prediccion: 3. Medido: **2** -- y el 2 es FALSO.
# Cierra su error, si, pero con la regla encendida **`CCWeapon` deja de
# analizarse entero** (ni su error ni su aviso), y el recuento no se compara.
# Comprobado con sonda y con su control:
#
#     regla ON,  sonda en CCWeapon -> la sonda NO aparece ..... 2 errores
#     regla OFF, sonda en CCWeapon -> la sonda SI aparece ..... 6 errores
#
# El arreglo es correcto por si solo -- reordena, no quita, y el juego de
# banderas queda identico. Lo que no se puede es COBRARLO: al dejar valida a
# `CCInstanceController`, el error de `GameInfo` corta su subarbol de
# dependencias, y ese subarbol tiene a `CCWeapon`.
#
# Se deja el codigo porque funciona y esta probado, y apagado porque la regla de
# parada es «si no mejora el recuento, se apaga y se anota» -- y aqui lo que
# hay no es una mejora, es una medida que no vale.
EXEC_DELANTE = True

# LA LISTA DE CLASES NO SE ESCRIBE AQUI.
#
# Vive en `tools/clases-del-mapa.txt`, con su procedencia, y sale de las tablas
# de importacion de los 218 mapas del juego.
#
# Antes era una lista literal de 19 nombres --"el cierre de dependencias"-- y
# estaba CORTA. La primera compilacion real, el 29/9, encontro seis tipos sin
# resolver; cuatro de ellos (`SkeletalMeshDynamicAttachment`,
# `AnimNodeSequenceCommon`, `CCPPController_Socket2Something`,
# `CCWeaponPhysMatEffects`) eran clases YA EXTRAIDAS que la lista no incluia.
# Una lista de nombres escrita a mano no puede llevar la cuenta de una clausura
# transitiva, y por eso ahora se deriva de una medicion.
LISTA_CLASES = os.path.join(DATOS, "clases-del-mapa.txt")


def lee_clases(ruta=None):
    """
    La lista de clases, una por linea; `#` comenta.

    Se puede pasar OTRA lista por linea de ordenes, y existe por un experimento
    concreto: compilar solo lo que importa UN mapa en vez de la union de los 218.
    Sirve para separar dos causas que se parecen -- que el conjunto sea demasiado
    grande, o que haya algo de fondo -- sin tocar `clases-del-mapa.txt`, que es
    la lista buena.
    """
    with io.open(ruta or LISTA_CLASES, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


# Tipos que el compilador de guion nombro y que no son superclases: aparecen como
# tipo de una propiedad o una firma, asi que seguirlos por `extends` no los trae.
#
# La lista NO se adivina: sale de `Unrecognized type 'X'` en el log del make. Se
# anaden aqui, se regenera y se vuelve a compilar. Cada vuelta son diez segundos,
# y el compilador nombra el fichero y la linea.
TIPOS_QUE_FALTA = [
    "AnimCompareSetupInfo", "CCRandomAnimationSetPlayer", "CCWeaponAttachmentPreset",
    "CCMotionLawObject", "TurnNode", "CCWeaponAttachment", "CCAvatar",
    "InterpolationSpline", "SeqEvent_CCAdMediaholderUpdate", "CCSquadAI",
    "CCBotBase", "CCDoTarget",
    # Segunda vuelta del compilador. Casi ninguno es un fichero: son structs y
    # enums declarados dentro de una clase, y `duenos()` los traduce.
    "StreamAnimInfo", "MLS_GetDescription", "CCResourcesDB", "SpreadParams",
    "CCWeaponPreset", "YakaLayer", "CCAvatarWeaponSlots",
]


def duenos():
    """
    Tipo declarado -> fichero que lo declara, en la exportacion.

    Existe porque un tipo NO tiene por que llamarse como su fichero. Los tres
    ultimos que el compilador nombro --`AnimCompareSetupInfo`,
    `InterpolationSpline`, `TurnNode`-- no son ficheros: son `struct native`
    declarados DENTRO de una clase. Buscar `TurnNode.uc` no encuentra nada y el
    generador los daba por huecos, cuando la fuente estaba a la vista.

    Con este mapa, un tipo que falta se traduce al fichero que hay que traer.
    """
    m = {}
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8", errors="replace").read()
        for nombre in declarados(t.lstrip(chr(0xFEFF))):
            m.setdefault(nombre, f[:-3])
    return m


# Modificadores que pueden ir DELANTE del tipo en un `var`.
#
# LA LISTA VIVE EN `cc-studytools/tools/modifiers.py`, EN UN SOLO SITIO. Estaba copiada en
# tres ficheros y habia divergido: `analiza-tipos.py` tenia 24 y le faltaban
# siete. Un modificador que falte **se convierte en EL TIPO**, porque
# `tipo_de_var()` se queda con el primer identificador que no reconoce -- y el
# sintoma sale lejos, como `Unrecognized type`, en otro fichero.
#
# La procedencia de las ultimas cinco esta en el modulo, medidas una a una:
#
#   init          1.512   `var init CCSkeletalMeshDynamicDiffStore X;`
#   editconst        59
#   noclear          48
#   retval           45   modificador de PARAMETRO
#   globalconfig     20
#   optional         20   `optional CCRosterEntry rosterEntry`
# El directorio PROPIO, no el de la raiz: `modifiers.py` es hermano. Y hace
# falta insertarlo porque `-I` quita el directorio del guion de `sys.path` -- sin
# `-I` Python lo pondria solo, y este programa se corre de las dos formas.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modifiers import MODIFICADORES

# Como se mide esta lista, por si hay que rehacerla:
#
#   recorrer cada `var`/`local` del paquete y quedarse con los tokens en
#   minuscula que NO esten aqui ni sean tipos intrinsecos. Los que salen muchas
#   veces y no son nombres de variable son modificadores que faltan.
#
# El aviso: los ultimos tokens son el NOMBRE de la variable, asi que la cola de
# la lista (`bot`, `pret`, `msg`...) es ruido y no hay que anadirla.
GENERICOS = {"array", "class", "map"}


def tipo_de_var(declaracion):
    """
    El tipo de una declaracion `var`.

    LA PRIMERA VERSION DE ESTO ESTABA MAL, y merece quedar escrito:

        r"\bvar\s*(?:\([^)]*\))?\s*(?:[A-Za-z_]+\s+)*([A-Za-z_]\w*)"

    Ese `(?:[A-Za-z_]+\s+)*` es CODICIOSO. En

        var transient AnimNodeTriangleBlend TriangleBlendNode;

    se come `transient ` Y `AnimNodeTriangleBlend `, y captura el NOMBRE DE LA
    VARIABLE. La clausura llevaba desde el primer dia anadiendo nombres de
    variable y perdiendo los tipos que iba a buscar.

    Se supo porque el analisis de tipos daba 7.257 "sin declarar" de 8.024
    referenciados, que es imposible: con el arreglo son 263 de 1.095.

    La forma robusta no es una expresion mas lista: es partir la declaracion y
    quedarse con el PRIMER identificador que no sea un modificador.

    Y FALTABA LA CATEGORIA. `var(Categoria) Tipo Nombre;` -- el grupo entre
    parentesis dice en que categoria del editor sale la propiedad -- no se
    quitaba, asi que el "primer identificador que no sea un modificador" era
    **la categoria**:

        var(Text) UIStyleReference OverlaySelectionStyle;
                     ^ devolvia `Text`, no `UIStyleReference`
        var(ListBoxEx) export editinline UIComp_ListElementPresenterEx X;
                     ^ devolvia `ListBoxEx`

    Son **438 declaraciones** en el paquete y **las 438 salian mal**. La clausura
    seguia el tipo equivocado: si la categoria no es una clase conocida no traia
    nada, y si **si lo es** --`Text`, `Setup`-- traia la equivocada, y la de
    verdad no entraba nunca. El sintoma salia en otro fichero, como
    `Unrecognized type`.

    Se recorta el grupo ANTES de tokenizar, y no se anade al bucle de
    modificadores: la categoria no es un modificador y puede llamarse como
    cualquier cosa.
    """
    declaracion = re.sub(r"^(\s*(?:var|local))\s*\([^)]*\)", chr(92) + "1",
                         declaracion)
    ids = re.findall(r"[A-Za-z_]\w*", declaracion)
    if ids and ids[0] in ("var", "local"):
        ids = ids[1:]
    resto = [t for t in ids if t not in MODIFICADORES]
    if not resto:
        return None
    if resto[0] in GENERICOS:
        # Y DENTRO DE LOS `<>` PASA LO MISMO, que es lo que faltaba:
        #
        #     var() editinline array<editinline TutorialAction> Actions;
        #
        # El patron anterior exigia que tras el primer identificador viniera una
        # coma o el `>`. Aqui viene ` TutorialAction`, asi que no casaba y
        # devolvia la lista VACIA -- el tipo no se seguia, y salia como
        # `Unrecognized type 'TutorialAction'`.
        #
        # Se aplica la misma regla que fuera: quedarse con el primer
        # identificador que no sea un modificador. Vale para `array<X>`,
        # `array<mod X>`, `class<X>` y `map<K, V>`.
        dentro = re.findall(r"<([^<>]*)>", declaracion)
        fuera = []
        for trozo in dentro:
            for t in re.findall(r"[A-Za-z_]\w*", trozo):
                if t not in MODIFICADORES and t not in GENERICOS:
                    fuera.append(t)
                    break
        return fuera or None
    return [resto[0]]


def cualifica(t):
    """`Tipo` -> `Dueno.Tipo`, o None si no hay que tocarlo."""
    if t in MODIFICADORES or t in GENERICOS:
        return None
    # >>> Y SI EL TIPO YA SE ALOJO EN `CCStubTipos`, NO SE CUALIFICA.
    #
    # Es el punto donde las DOS reglas se tocan, y no se conocian. La
    # sustitucion de `TIPOS_PERDIDOS` mueve el tipo a `CCStubTipos` -- por eso
    # esta en esa tabla --, y despues `recualifica()` lo veia sin cualificar y
    # le ponia el dueno de ORIGEN encima:
    #
    #     function CCAvatar.CCAvatarWeaponSlots F(...)   (el export)
    #       -> CCStubTipos.CCAvatarWeaponSlots           (la sustitucion, bien)
    #       -> CCStubTipos.CCAvatar.CCAvatarWeaponSlots  (recualifica, MAL)
    #
    # Su guarda de doble cualificacion no lo ve: mira si el texto ya termina en
    # `CCAvatar.`, y lo que hay es `CCStubTipos.` -- **otro cualificador**.
    #
    # Estaba tapado: el compilador para en el primer error de cada clase, y
    # `CCInstanceController` tenia uno antes. Lo destapo alojar la cola.
    #
    # Y NO ROMPE EL CASO LEGITIMO: en `defaultproperties`,
    # `CCStubTipos.UITextAttributes.UIALIGN_Left` es un VALOR cualificado por su
    # struct -- otra cosa --, y lo escribe la sustitucion, no esto; `recualifica`
    # ni siquiera mira dentro de `defaultproperties`.
    if t in TIPOS_PERDIDOS or t in TIPOS_PERDIDOS.values():
        return None
    dueno = DUENOS.get(t)
    if not dueno or dueno == CLASE_ACTUAL or dueno not in CLASES_VALIDAS:
        return None
    if t in DECLARADOS_AQUI:
        return None
    return dueno + "." + t


def tramos_de_tipo(texto):
    """
    (inicio, fin, token) de cada identificador que esta en POSICION DE TIPO.

    **UNA SOLA VERDAD PARA DOS CONSUMIDORES.** La necesitan `recualifica()` --que
    coloca la cualificacion que falta-- y la sustitucion de `TIPOS_PERDIDOS`
    --que lleva un tipo perdido a `CCStubTipos`--. Antes cada uno tenia la suya,
    y la de la sustitucion **no existia**: sustituia el identificador ESTUVIERA
    DONDE ESTUVIERA, y una tabla que no mira donde escribe rompe lo que no
    pretendia tocar.

    POR QUE HACIA FALTA, medido. Al alojar cinco tipos de golpe:

        local int WeaponCarrySlot;      ->  local int CCStubTipos.WeaponCarrySlot;
        SelectTakeHitAnimation(TakeHitInfo TakeHitInfo, ...)
                                        ->  (CCStubTipos.TakeHitInfo CCStubTipos.TakeHitInfo, ...)

    La primera es el NOMBRE de una variable y el segundo el NOMBRE de un
    parametro -- que se llama igual que su tipo, que es legal y pasa. Las dos
    son posicion de NOMBRE, y la sustitucion no lo miraba.

    Y LA REGLA QUE LAS DISTINGUE ES UNA, y es la de `tipo_de_var()`: **el
    primer identificador que no es modificador**. En `Tipo Nombre` el tipo va
    primero; y si es `array<Tipo>`/`class<Tipo>`, el tipo va DENTRO de los
    angulos.

    LOS TOKENS LLEVAN PUNTO. `CCController.EMoveDirection` es UN tramo, no dos:
    si se partiera, la sustitucion no casaria con la clave cualificada y
    `recualifica()` veria el contenedor en vez del tipo.
    """
    fuera = []
    ID = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"

    def ids_de(cuerpo, base):
        """El tramo del TIPO dentro de una declaracion Ya recortada."""
        todos = list(re.finditer(ID, cuerpo))
        if not todos:
            return
        primero = next((mm for mm in todos if mm.group(0) not in MODIFICADORES), None)
        if primero is None:
            return
        if primero.group(0) in GENERICOS:
            # `array<X>`, `class<X>`: el tipo va dentro de los angulos.
            for g in re.finditer(r"<\s*(" + ID + r")\s*(?:,\s*(" + ID + r")\s*)?>", cuerpo):
                for k in (1, 2):
                    if g.group(k):
                        fuera.append((base + g.start(k), base + g.end(k), g.group(k)))
            return
        fuera.append((base + primero.start(), base + primero.end(), primero.group(0)))

    # `var(...)` va PRIMERO y sin `?`: con la categoria opcional, `var(Profile)`
    # casaba solo con `var` y `(Profile)` entraba en el cuerpo como si fuera el
    # tipo. Ya mordio una vez; el porque esta largo en `recualifica()`.
    for m in re.finditer(r"(?m)^([^\S\n]*)(?:var\s*\([^)]*\)|var|local)[ \t]+([^;\n]*);", texto):
        ids_de(m.group(2), m.start(2))

    # FIRMAS: los parametros y el tipo de retorno.
    for m in re.finditer(r"(?m)^[^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*(?:function|event|operator|delegate)\b([^\n]*)", texto):
        firma, base = m.group(1), m.start(1)
        par = re.search(r"\(([^)]*)\)", firma)
        if par:
            for trozo in re.finditer(r"[^,]+", par.group(1)):
                ids_de(trozo.group(0), base + par.start(1) + trozo.start())
        # El tipo de retorno: el identificador antes del nombre de la funcion.
        cab = firma.split("(")[0]
        todos = [mm for mm in re.finditer(ID, cab) if mm.group(0) not in MODIFICADORES]
        if len(todos) >= 2:
            tok = todos[-2]
            fuera.append((base + tok.start(), base + tok.end(), tok.group(0)))

    # Y `defaultproperties`, QUE TAMBIEN TIENE POSICION DE TIPO.
    #
    # Ahi un token CON PUNTO es un valor cualificado por su tipo:
    #
    #     TextAlignment=UITextAttributes.UIALIGN_Left
    #
    # y la CABEZA --`UITextAttributes`-- es el tipo. Sin esta regla, la
    # sustitucion con posicion dejaba de tocar lo que la ciega si tocaba, y
    # **el diff lo enseño**: un solo fichero de los 742, `InWorldTextComponent`.
    # Es justo para esto para lo que se guardo la instantanea antes de tocar.
    for m in re.finditer(r"(?ms)^[ \t]*defaultproperties[ \t]*\r?\n?\s*\{(.*?)^[ \t]*\}", texto):
        for g in re.finditer(r"(?<![\w.])(" + ID + r")\.[A-Za-z_]\w*", m.group(1)):
            fuera.append((m.start(1) + g.start(1), m.start(1) + g.end(1), g.group(1)))

    return fuera


def recualifica(texto):
    """
    Recoloca la cualificacion de los tipos anidados que el descompilador emitio
    sin cualificar. **SOLO EN POSICION DE TIPO.**

    POR QUE SOLO EN POSICION DE TIPO
    --------------------------------
    La version anterior sustituia TODA aparicion del identificador, y eso rompe
    mas de lo que arregla:

        var() ParticleSystem HitEffect;
        ->  var() ParticleSystem CCPawnProps.HitEffect;

    `HitEffect` ahi es el NOMBRE DE LA VARIABLE, no un tipo. Y el compilador lo
    dijo con un `Missing ';' in 'struct'` que no senala ni el fichero logico.

    ESTO ES LO MISMO QUE HACE `tipo_de_var()`, que ya existe: partir la
    declaracion y quedarse con el PRIMER identificador que no sea modificador.
    Aqui ademas se guarda DONDE esta, para sustituir solo ese trozo.

    Se recorren `var` y `local`, que es donde el descompilador dejo la
    cualificacion a medias. Las firmas de funcion tambien podrian llevarla, pero
    no se ha visto el caso: se anadira si el compilador lo pide.
    """
    # EL PATRON, Y POR QUE TIENE ESTA FORMA
    #
    #   (?:var\s*\([^)]*\)|var|local)[ 	]+
    #
    # La categoria de `var(...)` va PRIMERO y sin `?`. Antes era opcional, y con
    # `var(...)` la expresion casaba solo con `var` -- porque el `` que venia
    # despues NO HAY FRONTERA DE PALABRA tras un parentesis cerrado-- y metia
    # `(Profile)` en el cuerpo. Ahi, `Profile` pasaba por TIPO y se recualificaba:
    #
    #     var(Profile) string CharacterPresets;   ->   var(YakaLayer.Profile) ...
    #
    # Con la categoria consumida primero, el cuerpo empieza en `string`, que es
    # el tipo de verdad, y `Profile` ya no se toca.
    cambios = []
    for m in re.finditer(r"(?m)^([^\S\n]*)(?:var\s*\([^)]*\)|var|local)[ \t]+([^;\n]*);", texto):
        cuerpo, base = m.group(2), m.start(2)
        ids = list(re.finditer(r"[A-Za-z_]\w*", cuerpo))
        if not ids:
            continue
        # El primer identificador que no sea modificador es el tipo.
        primero = next((k for k, mm in enumerate(ids)
                        if mm.group(0) not in MODIFICADORES), None)
        if primero is None:
            continue
        tok = ids[primero]
        if tok.group(0) in GENERICOS:
            # `array<X>`, `class<X>`, `map<K,V>`: el tipo va DENTRO de los angulos.
            for g in re.finditer(r"<\s*([A-Za-z_]\w*)\s*(?:,\s*([A-Za-z_]\w*)\s*)?>", cuerpo):
                for k in (1, 2):
                    if not g.group(k):
                        continue
                    c = cualifica(g.group(k))
                    if c:
                        cambios.append((base + g.start(k), base + g.end(k), c))
            continue
        c = cualifica(tok.group(0))
        if c:
            cambios.append((base + tok.start(), base + tok.end(), c))

    # FIRMAS DE FUNCION: el tipo de retorno y los parametros.
    #
    # Faltaban, y se supo porque el compilador nombro `CharacterPreset` en
    # `function ConfigurePreviewSkelMeshForCharPreset(CharacterPreset Preset)`.
    # Un parametro tiene la misma forma que un `var` -- modificadores, tipo,
    # nombre -- asi que se reusa la misma idea.
    #
    # Y EL PATRON EXIGIA `function` JUSTO TRAS EL ESPACIO INICIAL.
    #
    # Es la MISMA trampa que ya se corrigio en el cierre, y aqui seguia: con
    # `^[^\S\n]*(?:function|event|operator)`, una firma con modificadores delante
    # NO CASA, asi que sus parametros no se recualificaban NUNCA.
    #
    #     static simulated function int GetWeaponCarrySlotRBDescIndexFrom(..., const array<WeaponCarrySlotRBDesc> RDDescs)
    #     simulated function PlayTurretFireEffects(TurretFireInfo FireInfo)
    #     delegate bool OnCustomMenuItemsAddition(..., ItemContextMenuDesc MenuDesc)
    #
    # Las tres daban `Unrecognized type` con el tipo declarado en el paquete. Y
    # `delegate` faltaba ademas como palabra: no es `function` ni `event`, y su
    # lista de parametros es la misma cosa.
    #
    # Se acota a IDENTIFICADORES SUELTOS delante -- que es lo que son los
    # modificadores -- y no a `[^\n]*`, que casaria cualquier linea que mencione
    # la palabra, llamadas y comentarios incluidos.
    for m in re.finditer(r"(?m)^[^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*"
                         r"(?:function|event|operator|delegate)\b([^\n]*)", texto):
        firma, base = m.group(1), m.start(1)
        par = re.search(r"\(([^)]*)\)", firma)
        if par:
            for trozo in re.finditer(r"[^,]+", par.group(1)):
                cuerpo = trozo.group(0)
                ids = list(re.finditer(r"[A-Za-z_]\w*", cuerpo))
                primero = next((k for k, mm in enumerate(ids)
                                if mm.group(0) not in MODIFICADORES), None)
                if primero is None:
                    continue
                tok = ids[primero]
                if tok.group(0) in GENERICOS:
                    for g in re.finditer(r"<\s*([A-Za-z_]\w*)\s*>", cuerpo):
                        c = cualifica(g.group(1))
                        if c:
                            cambios.append((base + par.start(1) + trozo.start() + g.start(1),
                                            base + par.start(1) + trozo.start() + g.end(1), c))
                    continue
                c = cualifica(tok.group(0))
                if c:
                    cambios.append((base + par.start(1) + trozo.start() + tok.start(),
                                    base + par.start(1) + trozo.start() + tok.end(), c))
        # El tipo de retorno: el identificador antes del nombre de la funcion.
        # El tipo de retorno: el identificador antes del nombre de la funcion.
        #
        # OJO CON LA DOBLE CUALIFICACION. `sin_mod[-2]` SALTA el cualificador,
        # asi que en
        #
        #     function CCWeaponPreset.EWeaponDamageType GetWeaponDamageType()
        #
        # ve `EWeaponDamageType` y le anade el dueno OTRA VEZ:
        #
        #     function CCWeaponPreset.CCWeaponPreset.EWeaponDamageType ...
        #
        # Por eso se comprueba que no venga ya cualificado.
        cab = firma.split("(")[0]
        ids = list(re.finditer(r"[A-Za-z_]\w*", cab))
        sin_mod = [mm for mm in ids if mm.group(0) not in MODIFICADORES]
        if len(sin_mod) >= 2:
            tok = sin_mod[-2]
            c = cualifica(tok.group(0))
            if c:
                antes = texto[:base + tok.start()].rstrip()
                if not antes.endswith(c[:c.rindex(".") + 1]):
                    cambios.append((base + tok.start(), base + tok.end(), c))

    # De atras hacia adelante: sustituir de delante desplaza las posiciones.
    for ini, fin, nuevo in sorted(cambios, reverse=True):
        texto = texto[:ini] + nuevo + texto[fin:]
    return texto, cambios


def resuelve(t, disponibles, dueno, sdk):
    """
    De un tipo, LA CLASE QUE HAY QUE TRAER para que ese tipo exista.

    Tres casos, y el del medio es el que faltaba:

      - `t` es una clase con fuente   -> se trae `t`.
      - `t` es un tipo ANIDADO        -> se trae LA CLASE QUE LO DECLARA.
        Un `struct` o un `enum` dentro de una clase no tiene fichero propio: su
        fichero es el de su dueno. Buscarlo como fichero da un falso hueco, y ya
        paso con `TurnNode`, `InterpolationSpline` y `AIAbilityEffect`.
      - `t` es del SDK, o no existe   -> None.

    El caso del medio cierra un CIRCULO que dejo el paso 1 del plan bloqueado: la
    recualificacion exige que el dueno este en el conjunto, y una referencia SIN
    CUALIFICAR no le dice a la clausura de quien es. Se rompe por aqui.
    """
    if t in sdk:
        return None
    if t in disponibles:
        return t
    d = dueno.get(t)
    if d and d in disponibles:
        return d
    return None


def clausura(base, sdk, disponibles, dueno):
    """
    Expande la lista hasta que TODO `extends` pueda resolverse.

    Hace falta porque el mapa importa las clases que USA, no sus superclases.
    Una base abstracta --`CCGameObjective`, `AnimNodeBlendByMovementMode`,
    `UIAction`-- no aparece en la tabla de importaciones de ningun mapa, y sin
    embargo no se puede declarar `CCCapturePoint` sin ella.

    Medido: la primera compilacion con la lista cruda de los mapas dio 241 clases
    escritas y **37 errores, todos** de la forma `Superclass X of class Y not
    found`. Las 21 superclases distintas que nombraba tenian las 21 fuente
    extraida, asi que el cierre se hace aqui y no a base de compilar.

    Se para sola por dos motivos: solo sigue un `extends X` si X tiene fuente
    extraida --los del SDK ya estan declarados y no necesitan stub-- y lleva
    cuenta de lo ya visto.

    Devuelve (clases_ordenadas, sin_fuente).
    """
    vistas, pendientes = set(), list(base)
    while pendientes:
        c = pendientes.pop()
        if c in vistas:
            continue
        vistas.add(c)
        ruta = os.path.join(ORIGEN, c + ".uc")
        if not os.path.isfile(ruta):
            continue            # no es de CrimeCraft: o del SDK, o un hueco real
        texto = io.open(ruta, encoding="utf-8", errors="replace").read().lstrip("﻿")
        # NO basta con seguir `extends`. Medido: seguir solo la herencia dejo 266
        # clases y el compilador encontro 11 tipos MAS sin resolver, todos
        # nombrados en propiedades y firmas --`CCAvatar`, `CCWeaponAttachment`,
        # `CCBotBase`, `InterpolationSpline`-- y un `implements`.
        #
        # Se coge todo identificador del texto que sea una clase con fuente
        # extraida. Es a proposito de alta cobertura y no de precision: incluir
        # de mas solo anade un stub, y excluir de menos cuesta una vuelta de
        # compilacion. Un identificador que resulte ser un nombre de variable y
        # coincida con una clase arrastra un stub inutil, que es el error barato.
        # `extends` y `implements`. NO todo identificador del texto: se probo, y
        # la lista paso de 266 a 983 clases, porque un nombre de variable que
        # coincide con una clase ajena --`ByteProperty`, `UIScene`-- arrastra un
        # stub entero. Meter de mas no es gratis: cada stub trae sus propios
        # tipos y sus propios errores.
        #
        # Los tipos que faltan de verdad se anaden a mano abajo, en
        # TIPOS_QUE_FALTA, y salen de lo que el compilador nombra. Sabe mas que
        # esta aproximacion y ademas los da con linea.
        for sup in EXTIENDE.findall(texto):
            if sup not in vistas and sup not in sdk:
                pendientes.append(sup)
        # `implements(RadarPresentInterface_Placable);` -- CON PARENTESIS.
        #
        # El patron que habia exigia un espacio despues de `implements`, y la
        # forma real lleva parentesis. NUNCA CASO: desde el primer dia, todas las
        # interfaces implementadas quedaron fuera de la clausura sin que nada lo
        # dijera. Se supo porque el compilador nombro
        # `RadarPresentInterface_Placable` y el fichero llevaba ahi todo el rato.
        for imp in re.findall(r"^\s*implements\s*\(\s*([A-Za-z_]\w*)", texto, re.M):
            if imp not in vistas and imp not in sdk:
                pendientes.append(imp)

        # LAS CLASES QUE EL CODIGO NOMBRA COMO LITERAL: `Class'CrimeCraft.X'`.
        #
        # ESTA ARISTA NO SE MIRABA, y es la que dejaba 772 referencias apuntando
        # a una clase que no se generaba. Se veia asi en un stub:
        #
        #     foreach WorldInfo.AllControllers(Class'CrimeCraftStubs.CCPVPBot2', bot)
        #
        # --la clase escrita en un literal, que ni es un `extends`, ni un tipo de
        # `var`, ni un parametro, ni un `local`. Ninguna de las aristas de arriba
        # la ve, y por eso `CCPVPBot2` no entraba nunca en el conjunto.
        #
        # MEDIDO SOBRE LA EXPORTACION: 9.929 referencias y **555 clases
        # distintas**, y **las 555 tienen `.uc`**. Cero huecos y cero choques con
        # el SDK, asi que esta arista no puede traer una clase inventada.
        #
        # Se busca en el TEXTO DE LA EXPORTACION, asi que el paquete que aparece
        # es el VIEJO: `PAQUETE_VIEJO`, no `PAQUETE_NUEVO`. Los stubs llevan el
        # nuevo porque `reescribe_paquete()` lo cambia despues; aqui todavia no
        # ha pasado.
        #
        # Y NO se filtra por `disponibles`: un literal de clase no puede nombrar
        # algo que no sea una clase. Se comprobo -- las 555 tienen fuente.
        for t in re.findall(r"Class'\s*" + re.escape(PAQUETE_VIEJO)
                            + r"\.([A-Za-z_]\w*)'", texto):
            if t not in vistas and t not in sdk:
                pendientes.append(t)

        # Y EL ENUM ANIDADO, que lleva la clase en medio:
        #
        #     Enum'CrimeCraft.CCAvatar.CCAvatarWeaponSlots'
        #
        # Son 8 referencias y 4 clases -- pocas, pero es la misma arista y
        # dejarla fuera seria dejar el mismo agujero abierto en pequeño.
        for t in re.findall(r"Enum'\s*" + re.escape(PAQUETE_VIEJO)
                            + r"\.([A-Za-z_]\w*)\.", texto):
            if t not in vistas and t not in sdk:
                pendientes.append(t)

        # Y LA TERCERA FORMA DE NOMBRAR UNA CLASE: `class=` en un `begin object`.
        #
        #     begin object name="SprintEffect" class=CrimeCraft.CCSprintCameraEffect
        #
        # No lleva comilla, asi que no la ve la arista de arriba. Son 8
        # referencias y 7 clases, y **sin ella quedaba una sin resolver**
        # (`CCSprintCameraEffect`, en `CCEffectsManager`) cuando las otras dos
        # aristas ya estaban puestas.
        #
        # NO SE ANCLA A PRINCIPIO DE LINEA. La primera version llevaba `^\s*` y
        # devolvia **0 referencias** -- `class=` va a MITAD de linea, dentro del
        # `begin object`. Es el mismo genero de fallo que el lookbehind que daba 0
        # donde habia 5.033: **un patron que no casa no dice "no hay", dice "mi
        # patron no casa"**, y hay que comprobarlo antes de creerselo.
        for t in re.findall(r"\bclass\s*=\s*" + re.escape(PAQUETE_VIEJO)
                            + r"\.([A-Za-z_]\w*)", texto):
            if t not in vistas and t not in sdk:
                pendientes.append(t)

        # `var` Y `var(...)`: EL TIPO DE UNA PROPIEDAD.
        #
        # Esto NO SE SEGUIA, y es el hueco mas grande que tenia la clausura: la
        # mayoria de los "tipos sin resolver" que quedaban eran tipos de
        # propiedad. Se habian ido tapando a mano en TIPOS_QUE_FALTA, uno por
        # vuelta de compilacion, cuando el patron los saca todos de una vez.
        #
        # Se desenvolviza `array<X>` y `class<X>`, que son los dos genericos que
        # usa el guion. Los modificadores (`transient`, `native`, `const`...) van
        # delante del tipo y se saltan.
        for m in re.finditer(r"^[^\S\n]*var\b[^;\n]*;", texto, re.M):
            for t in (tipo_de_var(m.group(0)) or []):
                if t not in vistas and t not in sdk and t in disponibles:
                    pendientes.append(t)

        # TIPOS USADOS EN EL CUERPO DE LAS FUNCIONES, que ni `extends` ni
        # `implements` traen.
        #
        # Medido con `CCController`: se usa como `local CCController LocalPC;`
        # dentro de una funcion, y no entraba. El compilador lo nombro --
        # `Unrecognized type 'CCController'`-- y la clase existia en la
        # exportacion desde el principio.
        #
        # Se sigue la POSICION DE TIPO y no todo identificador del texto. La
        # version que miraba todo identificador paso de 266 clases a 983: un
        # nombre de variable que coincide con una clase ajena arrastra un stub
        # entero, con sus propios tipos y sus propios errores.
        # Y solo se sigue lo que TIENE FUENTE. Un `extends` que no la tiene
        # interesa reportarlo --es un hueco real--, pero un identificador suelto
        # que casualmente empieza por mayusculas, no: anadirlo llenaba la lista
        # de clases inexistentes. Con `local` y `new` sin este filtro, el
        # conjunto paso de 281 a 771.
        # Y LOS PARAMETROS DE FUNCION, QUE NO SE SEGUIAN.
        #
        # Se supo por `optional class<DamageType> DamageType` en un parametro:
        # `DamageType` tiene fuente extraida y no entraba en el conjunto. El
        # sintoma que da el compilador NO lo dice -- cuando el tipo de dentro de
        # un `class<...>` no existe, dice `Missing variable name`, porque tras
        # leer el tipo espera un identificador y no lo hay.
        #
        # Un parametro tiene la misma forma que un `var` --modificadores, tipo,
        # nombre--, asi que se reusa `tipo_de_var()` sobre cada trozo entre comas.
        # LOS MODIFICADORES DELANTE DE `function`, QUE SE PERDIAN TODOS.
        #
        # El patron empezaba exigiendo `function` JUSTO tras el espacio inicial.
        # Pero UnrealScript escribe `native final function`, `simulated
        # function`, `static function`... asi que **ninguna declaracion con
        # modificadores se leia**, y sus parametros no se seguian nunca.
        #
        # Se supo por `UISkin`, que tiene fuente y no entraba:
        #
        #     native final function bool NotifyResolveStyle(UISkin ActiveSkin, ...)
        #     simulated function OnCauseDamage(SeqAct_CauseDamage Action)
        #
        # Ahora se admite cualquier cosa delante, mientras `function` aparezca
        # como palabra. El `\(( [^)]* )\)` de despues ya acota.
        # `(?:[A-Za-z_]\w*[ \t]+)*` y no `[^\n]*`: delante de `function` solo
        # puede haber MODIFICADORES -- identificadores sueltos --, no cualquier
        # texto. Con `[^\n]*` casaria tambien una linea que solo MENCIONE
        # `function`, y sus parentesis meterian tipos de mas en el cierre.
        for m in re.finditer(
                r"^[^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*\b(?:function|event|operator)\b[^\n]*",
                texto, re.M):
            par = re.search(r"\(([^)]*)\)", m.group(0))
            if not par:
                continue
            for trozo in re.finditer(r"[^,]+", par.group(1)):
                for t in (tipo_de_var("var " + trozo.group(0)) or []):
                    r = resuelve(t, disponibles, dueno, sdk)
                    if r and r not in vistas:
                        pendientes.append(r)
        for t in re.findall(r"\blocal\s+(?:[A-Za-z_]+\s+)*([A-Za-z_]\w*)\s+[A-Za-z_]\w*",
                            texto):
            r = resuelve(t, disponibles, dueno, sdk)
            if r and r not in vistas:
                pendientes.append(r)
        # NO se sigue `new`. Se probo y el patron no distingue `new Foo` de
        # `new(Outer)Foo`: capturaba `Outer` la mitad de las veces. El tipo de lo
        # que se instancia casi siempre aparece ademas en un `var` o en un
        # `local`, que si se siguen.
    # Lo que se quedo sin fuente se informa aparte: es el unico hueco de verdad.
    sin_fuente = sorted(c for c in vistas if not os.path.isfile(os.path.join(ORIGEN, c + ".uc")))
    return sorted(vistas), sin_fuente

# Artefactos de extraccion: lineas que el descompilador emitio y que no son
# UnrealScript.
#
# OJO con lo que este comentario decia antes: afirmaba que se comentan en vez de
# borrarse, y era falso para dos de las tres reglas. Solo la primera comenta.
# Las otras dos BORRAN, y esta bien que lo hagan: son anotaciones del
# descompilador --los flags en hexadecimal y las cabeceras `// Reference:`-- que
# no llevan informacion utilizable y dentro de un `defaultproperties` solo pueden
# estorbar. La primera es distinta: `Prop=/* ... */` es una linea del propio
# `defaultproperties` a la que le falta el valor, y conservarla comentada deja
# ver que el dato existia.
#
# re.M NO es opcional: sin el, `^` y `$` solo casan al principio y al final del
# TEXTO ENTERO, no de cada linea, y ninguna de estas reglas se aplica. Estuvo
# asi en la primera version y el sintoma era que el script decia haber tratado
# cero artefactos y dejaba las lineas rotas.
ARTEFACTOS = [
    # `Class<X>` CON MAYUSCULA. El SDK lo escribe `class<X>` -- 132 casos en
    # Engine-- y la exportacion del juego trae 243 `Class<X>` y CERO en minuscula.
    # O sea que lo capitaliza el descompilador, y el compilador lo rechaza con
    # un `Missing variable name` que no senala ni la palabra.
    #
    # Es de la misma familia que el BOM y que `Array type was not detected`:
    # algo que el descompilador escribe de una forma que el compilador no traga,
    # y cuyo sintoma no lo nombra.
    (re.compile(r"\bClass\s*<"), "class<"),
    # La regla NO puede llevar el nombre de la propiedad escrito a mano. Estuvo
    # asi --solo `Components`-- y el artefacto aparece en la exportacion con 26
    # nombres distintos: Components (206), VariableLinks (131), Children (40),
    # OutputLinks (28), InputLinks (6) y veinte mas de una o dos veces. Con el
    # nombre fijo, 253 de los 459 casos pasaban sin tocar y salian al `.uc` tal
    # cual, que es como se colo el `Children=` de AnimNodeBlendPerBoneEx.
    (re.compile(r"^([ \t]*)([A-Za-z_][A-Za-z0-9_]*[ \t]*=[ \t]*)/\*[ \t]*Array type was not detected\.[ \t]*\*/[ \t]*$",
                re.M),
     r"\1// ARTEFACTO DE EXTRACCION: array sin tipo de elemento. La linea original\n"
     r"\1// era `\2/* Array type was not detected. */`, que no es UnrealScript\n"
     r"\1// valido. Comentada en vez de borrada.\n"
     r"\1// \2/* Array type was not detected. */"),
    (re.compile(r"/\*[ \t]*0x[0-9A-Fa-f]{8}-0x[0-9A-Fa-f]{8}[ \t]*\*/"), ""),
    (re.compile(r"^[ \t]*//[ \t]*(Reference|TemplateOwnerClass|TemplateOwnerName|Archetype):.*$",
                re.M), ""),
]

# Clases cuya fuente extraida es SOLO una declaracion adelantada --`class X;`,
# sin cuerpo--. El compilador las rechaza con `Bad class definition`.
#
# Son clases que en el juego vivian solo en C++ y no tenian guion, y UE Explorer
# las dejo como una referencia suelta. Son TRES, y son las unicas: ni un solo
# `.uc` de los 1.990 del SDK usa esa forma.
#
# La superclase no se puede recuperar de la fuente, porque no hay fuente. Se
# deduce del unico dato que queda -- quien hereda de ellas y que usa:
#
#   ActorMarkingComponent  <- CCActorMarkingComponent, que solo anade sus
#                             propios `var(Marking)`. Un componente.
#   AnimObjectProfileBase  <- CCAnimObjectProfileBase, que solo anade sus
#                             propios `var(Profile)`. Una base sin mas.
#   UIAction               <- UIAction_SendChatMessage, que implementa
#                             `IsValidLevelSequenceObject`. Ese metodo es de
#                             SequenceObject, asi que la base es esa.
#
# QUEDA DICHO QUE ES UNA RECONSTRUCCION, no una extraccion. Si el motor se queja
# de un miembro que falta en alguna de las tres, el sitio es este.
RECONSTRUIDAS = {
    "ActorMarkingComponent": "ActorComponent",
    "AnimObjectProfileBase": "Object",
    "UIAction": "SequenceObject",

    # Segunda tanda, del 29/9 por la tarde. Son ocho clases mas cuya fuente
    # extraida es SOLO `class X;`, y NINGUNA existe en el SDK -- comprobado una a
    # una. El motor del juego tenia otro sistema de UI, y de el vienen cinco.
    #
    # La base se deduce de quien hereda y de lo que hay en el SDK. El SDK declara
    # `class UIRoot extends Object` y nada mas de esa jerarquia: ni UIObject, ni
    # UIPanel, ni UIScene. Asi que la cadena del juego se reconstruye colgando de
    # UIRoot, que si existe.
    #
    # SI EL MOTOR SE QUEJA de un miembro que falta en alguna de estas, el sitio
    # es este: quitarle a la base equivocada no da error, da un miembro que no
    # esta.
    "ReplicationStatsBase":  "Object",     # <- CCReplicationStats
    "SkeletalMeshDynamicDiff": "Object",   # <- CCSkeletalMeshGibDynamicDiff
    "WorldInfoUserObject":   "Object",     # <- CCSomeObjectsList
    "UIObject":              "UIRoot",     # <- CCUIMarkerDB, UIBaseSensor, ...
    "UILabel":               "UIObject",   # <- UICreepingLineLabel
    "UIPanel":               "UIObject",   # <- UIHelpPanel
    "UIScene":               "UIObject",   # <- UIMenu, UIMessageBoxEx
    "UIToggleButton":        "UIObject",   # <- UIMenuToggleButton
    "UILabelButton":         "UIObject",   # <- tras cerrar el hueco de los `var`
    "UITickableObject":      "UIObject",   # <- idem
    # Tercera tanda. Se encuentran de golpe con un grep, en vez de una por vuelta
    # de compilacion: una declaracion adelantada suelta es un error de SINTAXIS,
    # y el compilador se PARA en ella -- asi que detras puede haber cualquier
    # cosa sin contar. Ver la nota de "el recuento no es monotono".
    "UIButton":              "UIObject",   # <- UIComicButton, UIProgressArc
    "UIComponent":           "UIObject",   # <- UIComp_ColorGridPresenter y otros
    "UIImage":               "UIObject",   # <- var const Class<UIImage>
    "UITexture":             "UIObject",   # <- native function UITexture ...

    # >> `UIStyleResolver` NO VA AQUI. Ver SON_INTERFACES: se usa en
    # `implements()`, asi que tiene que ser una INTERFACE, no una clase. Se
    # reconstruyo como clase y el compilador lo dijo con precision:
    #     Implements: Class UIStyleResolver is not an interface
}

# Nombres que SI son clases: los del SDK mas los de este paquete. Lo llena
# main() antes del bucle, y lo usa la inferencia de `DependsOn` para no
# confundir una PROPIEDAD con una clase -- `Children.Something` no es un tipo.
CLASES_VALIDAS = set()

# Tipo anidado -> clase que lo declara. Lo llena main(). Sirve para recolocar
# la cualificacion que el descompilador SE COMIO: el guion del juego escribe
# `AIAbilityEffect` a secas donde el compilador necesita
# `CCAISharedTypes.AIAbilityEffect`.
DUENOS = {}

# Clase -> su padre, leido de `extends` en la exportacion. Lo llena main().
#
# Sirve para NO declarar dependencia de un ANCESTRO, y eso no es estilo:
# `UnScrCom.cpp:6202` la trata como error y **aborta el arbol entero**:
#
#     if( Class->IsChildOf( DependsOnClass ) )
#     {
#         warnf(NAME_Error,TEXT("%s is derived from %s - please remove the dependson"));
#         return 0;                       // <- se para TODO, no esa clase
#     }
#
# Medido sobre los stubs: de 541 referencias en `DependsOn`, **20 apuntan a un
# ancestro** -- `CCInstanceController -> CCController` entre ellas.
PADRES = {}

# Clase -> {const: valor}. Lo llena main(). Sirve para resolver los
# `const X = class'Y'.const.Z;`, que el compilador NO acepta en una declaracion
# `const` aunque si en un cuerpo de funcion. Ver SOLO_EN_CONST.
CONSTS = {}

CLASE_ACTUAL = None
DECLARADOS_AQUI = set()

# NOMBRES QUE HAY QUE DECLARAR COMO INTERFACE, NO COMO CLASE.
#
# El descompilador los emitio como `class X;` -- porque no pudo recuperar el
# cuerpo -- pero el guion los usa en `implements(X)`. No da error de tipo, da:
#
#     Implements: Class UIStyleResolver is not an interface
#
# Que es un mensaje distinto y apunta a otro sitio: no falta una declaracion,
# falta que esa declaracion sea de OTRA CLASE de cosa.
SON_INTERFACES = {"UIStyleResolver"}

# ---------------------------------------------------------------------------
# QUIEN ES INTERFAZ, LEIDO DEL FUENTE EN VEZ DE ESCRITO A MANO
#
# `SON_INTERFACES` es una lista con un solo miembro, y no deberia ser una lista:
# **el fuente dice quien es interfaz**, en dos pasos y los dos derivables.
#
#   1. lo que se declare `interface X`
#   2. TODO LO QUE HEREDE DE UNA INTERFAZ, y es transitivo
#
# Y hacen falta los dos. Con el primero solo, `RadarPresentInterface_Placable`
# se queda fuera, porque el descompilador lo escribio:
#
#     class RadarPresentInterface_Placable extends RadarPresentInterface
#     ^ clase                                     ^ interface
#
# De ahi salen DOS mensajes con la misma causa, uno por cada mitad:
#
#     Implements: Class RadarPresentInterface_Placable is not an interface
#     Class 'RadarPresentInterface_Placable' cannot extend interface
#     'RadarPresentInterface', use 'implements'
#
# El primero lo dan las siete clases que lo implementan; el segundo, el mismo.
#
# Es la leccion de la Fase 0 otra vez: un catalogo escrito a mano se queda corto,
# y el error sale lejos, en otro fichero y con otro sintoma.
# ---------------------------------------------------------------------------
ES_INTERFAZ = set()


def interfaces_declaradas():
    """
    Los nombres que el fuente declara `interface`, mas sus herederos.

    Se lee de la exportacion, que es donde el descompilador SI escribio bien la
    palabra `interface` -- en las que tienen cuerpo. Las que solo tienen
    `class X;` no dicen nada, y de esas se sigue encargando `SON_INTERFACES`.
    """
    declara, extiende = set(), {}
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8",
                    errors="replace").read().lstrip(chr(0xFEFF))
        m = re.match(r"\s*interface\s+([A-Za-z_]\w*)\s*(?:extends\s+([A-Za-z_]\w*))?", t)
        if m:
            declara.add(m.group(1))
            if m.group(2):
                extiende[m.group(1)] = m.group(2)
            continue
        m = re.match(r"\s*class\s+([A-Za-z_]\w*)\s+extends\s+([A-Za-z_]\w*)", t)
        if m:
            extiende[m.group(1)] = m.group(2)

    # 3. Y LO QUE ALGUIEN IMPLEMENTE, que es la regla que faltaba.
    #
    # `implements(X)` significa, por definicion del lenguaje, que X es una
    # interfaz: si fuera una clase el compilador lo rechaza. Asi que no hay nada
    # que suponer -- el guion lo dice al usarlo.
    #
    # Es lo que resuelve `UITickableObject`, cuya unica fuente es `class
    # UITickableObject;` y que dos clases declaran implementar.
    implementadas = set()
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8", errors="replace").read()
        implementadas.update(re.findall(r"implements\(([A-Za-z_]\w*)", t))
    declara |= implementadas

    # Punto fijo: lo que hereda de una interfaz es interfaz, y eso encadena.
    es = set(declara)
    for _ in range(32):
        crecio = False
        for hijo, padre in extiende.items():
            if hijo not in es and padre in es:
                es.add(hijo)
                crecio = True
        if not crecio:
            break
    return es

SOLO_ADELANTADA = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*;\s*$")

# ---------------------------------------------------------------------------
# TIPOS QUE NO EXISTEN EN NINGUNA PARTE
#
# El guion del juego los referencia, y NO estan ni en el SDK ni en la
# exportacion. No son un descuido del descompilador: son tipos que tenia el
# motor DEL JUEGO, que es de otra version que el del SDK.
#
# Medido: `UIRoot.uc` del SDK no tiene NI UNO de los enums de UIRoot que usa el
# guion del juego -- EItemType, EEditBoxCharacterSet, EScreenInputMode,
# EUIAlignment, EUIOrientation, EUIWidgetFace--, y `CoverLink.uc` tampoco tiene
# ECoverHint. Anadirlos al SDK seria inventar medio Engine y obligaria a
# recompilar Core y Engine enteros; se declaran aqui, en una clase propia del
# paquete de stubs, y las referencias se reescriben a ella.
#
# LA CLASE NO PUEDE LLAMARSE COMO NINGUNA DEL SDK.
#
# Los MIEMBROS estan reconstruidos DEL USO, no de la fuente: el descompilador no
# los recupero. Se sacaron buscando los prefijos en toda la exportacion --`CIT_`
# y `CH_`--, que es lo que aparece en los `defaultproperties` y en los cuerpos.
# PUEDEN FALTAR MIEMBROS que el guion no use nunca.
#
# Y EL ORDEN ES UNA SUPOSICION, no un dato. El valor numerico de un miembro de un
# enum es su POSICION, asi que si el orden original era otro, los numeros no
# coinciden. Se pone primero el que aparece como valor por defecto (`CIT_None`,
# `CH_None`), que en un enum suele ser el cero, y el resto por orden alfabetico.
# Para CARGAR el mapa da igual --el valor se conserva tal cual, sea cual sea su
# nombre--; para INTERPRETARLO, no. Queda dicho.
# ---------------------------------------------------------------------------
CLASE_TIPOS_PERDIDOS = "CCStubTipos"

# TIPOS PERDIDOS QUE ERAN STRUCT, NO ENUM.
#
# Va aparte de `TIPOS_PERDIDOS` porque no se declaran igual, y porque la
# diferencia no es cosmetica: un enum ocupa un byte y un struct lo que midan sus
# miembros. Declarar uno por otro COMPILA y MIENTE sobre el layout.
#
# Y estos son los peores de todo el paquete, porque de ellos no hay NADA:
# ni fuente en el SDK, ni fichero en la exportacion, ni `defaultproperties` que
# revele la forma, ni un solo acceso a un miembro en las 1.668 clases. Se
# comprobo uno a uno antes de escribir esta tabla.
STRUCTS_PERDIDOS = {
    # Se usa en seis clases --UIListBoxEx, UIListGrid, UIRichLabel, UIMisc-- y
    # siempre igual: `var UIScreenValue_Extent NodeHeight;`. En el motor del
    # juego era un struct del sistema de UI, que en este SDK no existe ni como
    # `UIScreenValue` ni como nada.
    #
    # UN SOLO MIEMBRO `float`, y es una SUPOSICION. El nombre --`_Extent`, una
    # extension o medida-- y el uso --alturas, anchuras, separaciones, margenes
    # de un widget-- dicen que es una medida; no dicen cuantos campos tiene. En
    # UE3 esa familia de tipos suele llevar el valor y una unidad, y por eso el
    # struct real probablemente mida mas que esto.
    #
    # SI ALGUN DIA IMPORTA LA SERIALIZACION DE LAS CLASES DE UI, este es el
    # sitio. El riesgo hoy es ACOTADO por lo mismo que el de los enums de
    # arriba: quien los usa son clases de UI, y no las importa ningun mapa.
    "UIScreenValue_Extent": ["var float Value;"],
    "UIScreenValue": ["var float Value;"],
    # `RenderParameters`, el ultimo de los que este plan daba por "cerrado por
    # estructura". **NO LO ESTABA, y se corrige aqui.**
    #
    # Decia que sus miembros solo estaban en el `.uc` del motor 4701 que el
    # cooker borro. Es verdad que no estan -- se busco en la exportacion, en el
    # SDK y en todo el workspace --, pero **no hacen falta**, y eso no se habia
    # mirado:
    #
    #     UIListGrid.uc:121   native function bool GetContainerBoundsById(int, out RenderParameters);
    #
    # Se usa SOLO como TIPO, y **no hay un solo acceso a un miembro suyo en toda
    # la exportacion** -- se busco `OutParams.` y no sale nada--. Asi que basta
    # con QUE EXISTA, que es el caso de `EEditBoxCharacterSet`, no el de un
    # struct cuya forma haya que acertar.
    #
    # UN MIEMBRO, y es una SUPOSICION declarada como tal. Es un parametro `out`
    # de una funcion `native` SIN C++ en nuestro SDK -- otra de las 4.378 --,
    # asi que nadie la escribe ni la lee y su tamano no decide nada.
    "RenderParameters": ["var float Value;"],
    # `DynamicTextureCoordExInfo`, y **SUS MIEMBROS SI SE DEDUCEN**, que es lo
    # contrario de lo que decia el plan. No estaban "solo en el .uc del motor
    # 4701": estan en LOS USOS, que es de donde este proyecto saca las cosas
    # cuando no hay fuente.
    #
    #     DynamicTextureCoordExInfoStruct.CoordIndex        = 0;
    #     DynamicTextureCoordExInfoStruct.ProjectionVectorU = vect(0.86, 0.5, 0.0);
    #     DynamicTextureCoordExInfoStruct.ProjectionVectorV = vect(0.0, -0.5, 0.86);
    #
    # TRES miembros, y el tipo de cada uno lo dice EL VALOR QUE SE LE ASIGNA:
    # un `0` para un `int`, y dos `vect(...)` para dos `Vector`. No hay
    # suposicion ninguna en la forma.
    #
    # Y EL ORDEN ES EL DE LOS USOS, que es lo unico que no dicen: `CoordIndex`
    # primero y los dos vectores detras. Se dice, porque el orden es lo que fija
    # el layout y aqui no hay un `structdefaultproperties` que lo confirme.
    "DynamicTextureCoordExInfo": [
        "var int CoordIndex;",
        "var Vector ProjectionVectorU;",
        "var Vector ProjectionVectorV;",
    ],

    # ---------------------------------------------------------------------
    # LOS CUATRO STRUCT DE B-2. No son como los de arriba: de aquellos no
    # habia NADA y hubo que suponer; de estos esta TODO.
    #
    # Los cuatro salen del `struct native` del export, copiado miembro a
    # miembro y EN SU ORDEN -- que es el orden en que UE3 serializa los
    # defaults de un struct, asi que el layout no es una suposicion.
    #
    # Y SE COPIA LA DECLARACION, NO EL `structdefaultproperties`: el literal
    # repite los valores por defecto, y ahi `Endpoint=(X=..,Y=..,Z=..)` se lee
    # como OCHO miembros si no se entienden los parentesis anidados. Es el
    # defecto que dejo sin arreglar a `SkelControlDestLocation`. Aqui no
    # estorba porque las declaraciones ya dicen el tipo, uno a uno.
    #
    # Ver TIPOS_PERDIDOS para por que se alojan y cual es la trampa del
    # cualificador.
    "TurretFireInfo": [
        "var Vector StartTrace;",
        "var Vector EndTrace;",
        "var byte ReplicationHack;",
    ],
    # Dos miembros, y los dos son CLASES del SDK, no structs: por eso el
    # catalogo los da como `ObjectProperty`. `var <Clase> x;` es una referencia
    # a un objeto de esa clase, que es exactamente lo que son.
    "WeaponCarrySlotRBDesc": [
        "var RB_BodyInstance RBBodyInstance;",
        "var RB_BodySetup RBBodySetup;",
    ],
    # Aqui `CurrState` es el que arrastra a `PlacingItemInfo_State`, que va
    # PELADO a proposito: el cualificado `CCInstancePawn.PlacingItemInfo_State`
    # no resuelve desde `CCStubTipos` -- es la enfermedad que se esta
    # arreglando.
    "PlacingItemInfo": [
        "var CCPlaceableItem ItemArchetype;",
        "var PlacingItemInfo_State CurrState;",
        "var Vector PlaceLoc;",
        "var Rotator PlaceRot;",
        "var CCAbilityContext AbilityContext;",
    ],
    # Ocho miembros. `AddInfo` es `AdditionalHitInfo`, que YA estaba alojado
    # aqui por la via automatica -- o sea que este struct depende de otro de
    # esta misma tabla, y el orden importa.
    "InstantTraceEffects_RPC_Info": [
        "var CCPlayerReplicationInfo PRI;",
        "var Vector StartTraceLocation;",
        "var Vector EndTraceLocation;",
        "var byte ShootSpotLocationType;",
        "var Vector HeadLocationForCWF;",
        "var Vector MuzzleLocation;",
        "var bool MuzzleLocationNeedsToBeResolved;",
        "var AdditionalHitInfo AddInfo;",
    ],

    # Y LOS DOS DE `CCInstancePawn` QUE DESTAPO B-4. Copiados del `struct native`
    # del export, miembro a miembro y EN SU ORDEN.
    #
    # `CurrentWeaponSlot` y `WeaponTypeName` van PELADOS a proposito: el
    # cualificado `CCAvatar.CCAvatarWeaponSlots` NO RESUELVE desde
    # `CCStubTipos` -- es la enfermedad que se esta tratando, y por eso los dos
    # contenedores se alojan aqui tambien.
    #
    # Y los tamanos de array son LITERALES (`[5]`, `[3]`), no enums, asi que no
    # dependen de cuantos enumeradores tenga nadie.
    "KillerInfo": [
        "var int ChangesCounter;",
        "var CCPlayerReplicationInfo PRI;",
        "var int AbilityIds[5];",
        "var int AbilityLevels[5];",
        "var int AffectingAbilityIds[5];",
        "var float ResistLight;",
        "var float ResistMedium;",
        "var float ResistHeavy;",
        "var float ResistSplash;",
        "var float DmgAbsorb;",
        "var CCAvatarWeaponSlots CurrentWeaponSlot;",
        "var float WeaponDamage[3];",
        "var int WeaponTemplateId[3];",
        "var EWeaponTypeName WeaponTypeName[3];",
        "var float SummaryDamage;",
        "var float MaxHP;",
        "var float CurrentHP;",
        "var float HP_Regen;",
        "var string PlayerName;",
        "var string GangName;",
        "var int GangLogoId;",
        "var float MaxSTM;",
        "var float STM_Regen;",
        "var float MeeleDamageModifier;",
        "var float BodyShotDamageModifier;",
        "var float HeadShotDamageModifier;",
        "var float LegsShotDamageModifier;",
        "var float SplashRadiusModifier;",
        "var float FireDamageModifier;",
    ],
    # Un solo miembro, y es un array de tamano literal.
    "DynamicKillerInfo": [
        "var int AbilityState[5];",
    ],

    # EL CIERRE ENTERO DE LA COLA, copiado del export EN SU ORDEN. Se calculo
    # antes de escribirlo -- 1.455 tipos indexados de la exportacion -- y son
    # SEIS, uno de ellos ya alojado, y **ninguno con un miembro sin tipo**, que
    # es el riesgo declarado de alojar. Ver TIPOS_PERDIDOS para la historia.
    #
    # SIN `var()` NI `export editinline`: son metadatos de EDITOR, no layout.
    "WeaponCarrySlot": [
        "var array<CarrySlotContent> Content;",
    ],
    "CarrySlotContent": [
        "var name SocketName;",
        "var SkeletalMeshComponent WeaponMesh;",
        "var CCPPController_Socket2Something WeaponPostPhysicsController;",
        "var SkeletalMeshDynamicAttachment DynamicAttachment;",
        "var array<name> WeaponRBBodyNames;",
        "var array<WeaponCarrySlotRBDesc> WeaponRBBodies;",
    ],
    "RagdollStateInfo": [
        "var bool bRagdollState;",
        "var float RagdollBlendInTime;",
        "var TakeHitInfo RagdollImpulseInfo;",
    ],
    "DeathAnimationInfo": [
        "var bool bPlayingDeathAnimation;",
        "var TakeHitInfo THInfo;",
    ],
    "TakeHitInfo": [
        "var int Damage;",
        "var Vector HitLocation;",
        "var Vector Momentum;",
        "var class<DamageType> DamageType;",
        "var name HitBone;",
        "var CCInstancePawn shooter;",
        "var float DamagePercent;",
        "var AdditionalHitInfo AddInfo;",
    ],
}

# Clases cuyo `native` hay que quitar porque su superclase del SDK no lo es.
# Se llena con lo que nombra el compilador, que es quien lo sabe.
# Y SE PROPAGA: si a `CCGameObjective` se le quita, sus derivadas tampoco pueden
# serlo, porque heredan de una que ya no es native. El compilador las nombra una
# vuelta despues, que es como se supo.
NO_PUEDEN_SER_NATIVAS = {'CCGameObjective', 'CCCTTCaptureZone', 'CCDefenceCore',
                         'CCROBBase',
                         # LOS TRES HIJOS DE `CCGameObjective`, que el
                         # compilador nombro uno a uno:
                         #
                         #     Native classes cannot expand non-native classes
                         #
                         # `CCGameObjective` perdio el `native` porque su
                         # superclase del SDK no lo es, y sus hijos heredan de
                         # una que ya no lo es. **La propagacion NO se deriva**:
                         # se intento y sobre-aplica (876 clases, 51 -> 62). Aqui
                         # van los que el compilador dice, y nada mas.
                         'CCCapturePoint', 'CCCaptureZone', 'CCCTFBase'}

# >>> SE INTENTO DERIVAR ESTO Y SALE PEOR. Medido, 29/9, septima tanda.
#
# La regla parecia clara -- `Native classes cannot expand non-native classes`, o
# sea que si tu padre no es native tu tampoco -- y se probaron DOS formas:
#
#   (a) mirando TODOS los ancestros: marca 877 clases, y el recuento pasa de
#       **51 a 62**. Aparecen 14 `Non-native classes not allowed to implement
#       native interfaces` y 6 `Not allowed to declare variables in non-native
#       classes`: los dos sintomas de haber quitado `native` DE MAS.
#   (b) propagando hacia abajo desde el padre directo, en punto fijo: 876 y los
#       mismos 62. Casi identico, asi que el problema no era el recorrido.
#
# O sea que la regla NO es la que parece. El compilador la aplica en un momento
# del analisis que no es el que se supone, o `native` significa aqui algo mas que
# "el padre lo es" -- pero **no se sabe cual**, y cambiar 876 clases a ciegas
# sobre una regla que no se entiende es como se rompen las cosas.
#
# Se queda la lista corta: cuatro nombres, los que el compilador nombro uno a uno
# y se comprobaron. Es menos elegante y esta MEDIDA.
#
# Las funciones `arbol_de_clases()` y `no_pueden_ser_nativas()` SE CONSERVAN sin
# usar: son el instrumento, y el instrumento ya esta escrito y probado.
# `no_pueden_ser_nativas()` se puede llamar desde la consola del generador.


def normaliza_firma(f):
    """Una firma sin espacios de mas, para poder comparar dos."""
    return re.sub(r"\s+", " ", f.strip()).rstrip(";").strip()


DELEGADOS = {}
# Y por clase, que es lo que permite buscar en la descendencia. Ver
# firma_de_delegado.
DELEGADOS_DE_CLASE = {}


def firma_de_delegado(nombre, clase=None):
    """
    La declaracion de `delegate <nombre>(...)`, buscada en la exportacion.

    Se indexa una vez, como las fichas de funciones, para no recorrer los 1.668
    ficheros por cada uso.
    """
    if not DELEGADOS:
        for f in os.listdir(ORIGEN):
            if not f.endswith(".uc"):
                continue
            t = io.open(os.path.join(ORIGEN, f), encoding="utf-8",
                        errors="replace").read()
            # CON CUERPO. Un delegado sin `{ }` no vale:
            #
            #     Missing '{' in delegate
            #
            # Y el cuerpo esta en el fuente --`{ //return; }`--, asi que se copia
            # entero en vez de inventarse uno.
            # CON TIPO DE RETORNO, por lo mismo que arriba: si no, `OnCellClicked`
            # se indexaba con la firma de OTRA clase -- `delegate OnCellClicked(
            # UICalendar Sender, int Index)`, de `UICalendar` -- porque la suya
            # (`delegate bool OnCellClicked(...)`) no casaba y el nombre quedaba
            # libre para el primero que llegara. `os.listdir` no tiene orden.
            for m in re.finditer(r"^[^\S\n]*delegate\s+(?:[A-Za-z_]\w*[ \t]+)*"
                                 r"(\w+)\s*\([^)]*\)[ \t]*\n"
                                 r"[ \t]*\{[^}]*\}", t, re.M):
                firma = m.group(0).strip()
                DELEGADOS.setdefault(m.group(1), firma)
                DELEGADOS_DE_CLASE.setdefault(f[:-3], {})[m.group(1)] = firma
    # Y LA FIRMA BUENA ES LA QUE DECLARA UN DESCENDIENTE DEL QUE LA NECESITA.
    #
    # `UIMenu` usa `delegate<OnResult>` y no lo declara. La copia generica cogia
    # el primero que apareciera -- `UIMessageBoxEx.OnResult(EMessageBoxResult)` --
    # y entonces su subclase protestaba:
    #
    #     UIMessageBox_Edit extends UIMenu, y declara
    #         delegate OnResult(bool IsValid, string Result)
    #     -> UIMessageBox_Edit.uc(13) : Redefinition of 'delegate OnResult'
    #                                   differs from original
    #
    # O sea: la firma que hay que poner en el PADRE es **la que el hijo ya tiene**,
    # porque el hijo manda -- una redefinicion tiene que coincidir. Buscarla en la
    # descendencia no es un atajo: es la unica que compila.
    if clase:
        for otra, suyos in DELEGADOS_DE_CLASE.items():
            if otra != clase and nombre in suyos and clase in ancestros(otra):
                return suyos[nombre]
    return DELEGADOS.get(nombre)


# EL DUENO QUE TIENE QUE IR PRIMERO EN EL `DependsOn` DE CADA CLASE.
#
# De `DependsOn(A, B, C)` **solo se registra `A`** -- ver el comentario largo mas
# abajo -- y si `A` no es el que hace falta, los TIPOS ANIDADOS de la clase
# necesaria no existen para nadie, con el `enum` escrito en la linea 7:
#
#     Unrecognized type 'EMoveDirection' within 'CCController'
#
# Esta lista la da EL COMPILADOR, error a error: son las clases usuarias que
# nombra y el dueno que nombra en cada una. **No se deriva**: se probo a deducir
# cual es el dueno necesario --poner delante el de un tipo anidado que la clase
# usa-- y NO ACIERTA cuando hay varios candidatos. En `CCPawn` elegia
# `CCSkelControl_SingleBone`, que aparece antes en el texto, cuando el que hacia
# falta era `CCController`.
#
# MEDIDO: 47 -> 20 errores; `within` 14 -> 3; `Redefinition` 13 -> 4.
# >>> PALANCA. `True` = se emite `DependsOn` aunque nombre una clase de OTRO
# paquete (el comportamiento hasta hoy). `False` = no se emite.
#
# Prediccion escrita antes de medir: con `False` desaparece el
# `Unparsed class 'GameInfo'`, el recorrido **completa**, y el recuento **SUBE**
# porque pasa a ser el verdadero en lugar del truncado.
#
# Lo refutaria: que el `Unparsed` siga saliendo, o que una sonda en una clase
# tardia siga sin aparecer en el log.
DEPENDSON_DE_OTRO_PAQUETE = False

PRIMERO_EN_DEPENDSON = {
    "CCAbilityActions": "CCInstancePawn",
    "CCAbilitySystem": "CCInstanceController",
    "CCCTFFlag": "CombatLogMessage",
    "CCHQ": "CCHQGameInfo",
    "CCNotificationMessage_BasePopup": "UIHudBasePopupMenu",
    "CCPawn": "CCController",
    "CCPlayerReplicationInfo": "GameInfo",
    "CCSmoothSpecProxy": "CCInstanceController",
    "SeqAct_CCPlayEventMusic": "CCInstanceController",
    "Tutorial": "UIQuasiMode",
    "TutorialSystem": "UICharMenu_BlackMarketNative",
    "UIInstanceSoloSensor": "CCLobbyRemoteController",
    "UILobbySensor": "CCLobbyRemoteController",
    "UIServices_Manager": "UIQuasiMode",
    "CCLobbyRemoteController": "UIQuasiMode",
}

# UNA CLASE PUEDE NECESITAR **MAS DE UNA**, Y `DependsOn` DA PARA MAS DE UNA.
#
# La tabla de arriba da UNA porque fue lo que se midio, pero el limite no es del
# formato: `UnScrCom.cpp:9066` y `ParseDependentClassGroup` (`UnEdFact.cpp:1679`)
# aceptan una LISTA separada por comas, y el segundo hace `AddUniqueItem` por
# cada nombre. Lo que si es cierto es que cada nombre de mas cuesta un recorrido
# de grafo (`UnScrCom.cpp:12813`), y ahi es donde el recuento sube.
#
# Asi que se anaden **solo las que hacen falta y estan medidas**, una a una:
#
#   CCPawn   usa `CCSkelControl_SingleBone.SkelControlDestLocation` y su unico
#            hueco lo ocupaba `CCController`. `CCSkelControl_SingleBone`
#            ordena DESPUES de `CCPawn` ('CCP' < 'CCS'), asi que no esta
#            analizado cuando `CCPawn` lo necesita. Medido: el compilador lo
#            dice con `Unrecognized type 'SkelControlDestLocation' within
#            'CCSkelControl_SingleBone'` -- o sea, encuentra la CLASE y no el
#            tipo anidado.
#
# >>> PROBADO, MEDIDO, Y APAGADO.
#
# `CCPawn` NECESITA LAS DOS: `CCController` por `EMoveDirection` y
# `CCSkelControl_SingleBone` por `SkelControlDestLocation`. Con
# `DependsOn(CCController, CCSkelControl_SingleBone)` **se arregla una y se
# rompe la otra**:
#
#     DependsOn(CCController)                            -> 17 errores
#                                                            SkelControlDestLocation
#     DependsOn(CCController, CCSkelControl_SingleBone)  -> 17 errores
#                                                            EMoveDirection
#
# Neto CERO: es un INTERCAMBIO, no un arreglo. Y el mecanismo se entiende a
# medias -- `DependsOn(X)` no solo ordena X: `ParseScripts`
# (`UnScrCom.cpp:12891`) recursiona tambien sobre sus SUBCLASES, asi que anadir
# un nombre reordena el paquete entero. Es la misma clase de efecto que hace que
# el `DependsOn(GameInfo)` de `CCPlayerReplicationInfo` valga 24 errores.
#
# El mecanismo SE QUEDA -- es correcto y esta probado -- y la tabla se vacia
# porque no hay ninguna entrada que mejore. Si algun dia se entiende el orden,
# aqui esta la palanca.
#
# >>> TRES MECANISMOS PROBADOS, LOS TRES NETOS CERO. NO SE VUELVE.
#
# `CCPawn` usa `CCController.EMoveDirection` (linea 296) y
# `CCSkelControl_SingleBone.SkelControlDestLocation` (linea 47), y las dos
# clases ordenan DESPUES que el en `CCSkelControl_SingleBone` y antes en
# `CCController`. Con un solo hueco de `DependsOn` -- no, con la lista que
# acepta -- se probaron tres formas:
#
#   DependsOn(CCController)                      -> EMoveDirection OK,
#                                                   SkelControlDestLocation NO
#   DependsOn(CCController, CCSkelControl_...)   -> SkelControlDestLocation OK,
#                                                   EMoveDirection NO
#   la cadena: CCSkelControl_SingleBone -> CCController, y CCPawn con uno
#                                                -> igual que la de arriba
#   la cadena al REVES: CCController -> CCSkelControl_SingleBone
#                                                -> vuelve al primer caso
#
# **9 -> 9 las tres veces, y la cuarta.** Y el dato que sale es este: **con DOS
# nombres, `CCPawn` PIERDE `EMoveDirection`; con UNO, lo tiene.** O sea que
# anadir el segundo nombre no suma: quita. El porque no se ha llegado a
# entender, y por eso no se toca.
#
# Es el mismo genero que el `DependsOn(GameInfo)`: correcto el mecanismo, y el
# efecto es de ORDEN sobre el paquete entero.
ADEMAS_EN_DEPENDSON = {
    "CCPawn": ("CCStubTipos", "CCPlayerVisualComponent", "CCWeaponAttachment"),
}

# >>> H1 DEL PLAN v2: la palanca, t irada por SEGUNDA vez.
#  la tira por accidente y vale 23. La pregunta es si el orden es
# REPETIBLE o si aquello fue una casualidad afortunada.
SEGUNDA_PALANCA = {}
#
# >>> H1 DEL PLAN v2: PROBADA Y REFUTADA el 30/9. **6 -> 6**, y sin error
# nuevo: `DependsOn(CCInstancePawn, PlayerController)` en `CCAbilityActions` no
# cambio NADA. Ni mejoro ni dejo un `Unparsed class`.
#
# O sea que la palanca NO es repetible: el `DependsOn(GameInfo)` de
# `CCPlayerReplicationInfo` **fue una casualidad afortunada**, no un mecanismo
# que se pueda tirar a voluntad. Queda como esta, con su medicion: cuesta 1 y
# compra 23.


def sitio_de_declaracion(texto):
    """
    El match de la primera declaracion que esta a NIVEL DE CLASE.

    POR QUE NO VALE UNA EXPRESION SOLA
    ----------------------------------
    En UnrealScript el cuerpo de la clase **no lleva llaves**, pero el de un
    `struct` o un `enum` si. Asi que `^[^\\S\\n]*(?:var|const|...)` encuentra la
    primera `var` -- y esa puede estar DENTRO del primer struct.

    Y ahi un delegado da, medido:

        UIMenu.uc(28) : 'struct': Unexpected 'delegate'

    Por eso hay que contar llaves: se busca la primera declaracion con la
    PROFUNDIDAD a cero, que es donde viven los delegados, al nivel de los tipos.
    """
    #
    # Y VA ANTES DE LA PRIMERA **FUNCION**, NO DE LA PRIMERA `var`.
    #
    # Medido, y sale de comparar los dos casos que ya existian:
    #
    #   `UIMessageBoxEx.uc` ya traia su delegado del descompilador, y NO da
    #   error: esta en la linea 65, **despues** de las `var` y entre funciones.
    #
    #   Puesto antes de las `var`, en cambio:
    #       CCBaseController.uc(11) : 'Var' is not allowed here
    #       UIItemGrid.uc(11)       : 'Var' is not allowed here
    #       UIMenu.uc(62)           : 'Var' is not allowed here
    #
    # O sea: despues de un `delegate` con cuerpo, el analizador **no acepta una
    # `var`** -- y si una funcion. Asi que el sitio es delante de la primera
    # funcion, que es exactamente donde el descompilador lo dejo.
    #
    # El patron lleva modificadores delante porque `native function` y
    # `simulated function` son la forma normal, y anclarlo a `function` a secas
    # los perderia -- la misma trampa que costo tres errores en la
    # recualificacion.
    prof, pos = 0, 0
    for m in re.finditer(r"(?m)^[^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*"
                         r"(?:function|event)\b", texto):
        prof += (texto.count("{", pos, m.start())
                 - texto.count("}", pos, m.start()))
        pos = m.start()
        if prof == 0:
            return m
    return None


def cuenta_de_params(firma):
    """Cuantos parametros tiene una firma. Cero si no tiene lista."""
    p = params_de(firma).strip("() ").strip()
    return 0 if not p else len([x for x in p.split(",") if x.strip()])


def params_de(firma):
    """La lista de parametros de una firma, sin espacios de mas."""
    p = firma.split("(", 1)
    return re.sub(r"\s+", " ", p[1]).strip() if len(p) > 1 else ""


def firma_del_padre(clase, funcion):
    """
    La declaracion de `funcion` en el primer ancestro de `clase` que la tenga.

    Se camina la cadena de padres --que ya esta en `PADRES`, con el SDK dentro--
    y se busca en la exportacion primero y en el SDK despues. Se devuelve UNA
    linea: las del SDK a veces vienen partidas en varias.
    """
    fichas = fichas_de_funciones()
    x, saltos = PADRES.get(clase, ""), 0
    while x and saltos < 64:
        saltos += 1
        f = fichas.get(x, {}).get(funcion)
        if f:
            return f
        x = PADRES.get(x, "")
    return None


FICHAS = {}
FIRMA_DE_FUNCION = re.compile(
    r"^[^\S\n]*(?:\w+[ \t]+)*(?:function|event|operator)\b"
    r"[^\n]*?(?<![\w])(\w+)[ \t]*\([^)]*\)", re.M)


def fichas_de_funciones():
    """
    Clase -> {funcion: firma}, de la exportacion y del SDK, UNA VEZ.

    Esto NO estaba, y el generador se volvio lentisimo: `firma_del_padre()`
    hacia un `os.walk` COMPLETO POR CADA FUNCION DE CADA CLASE -- unos dos mil
    ficheros recorridos decenas de miles de veces.

    Es el MISMO error que este proyecto ya tiene documentado --`clausura()` "se
    colgaba" y tardaba minutos, por un bucle mal orientado-- y se reconocio
    rapido justo por eso: el generador tarda 10 segundos, y dejo de terminar.
    """
    if FICHAS:
        return FICHAS
    for base in (ORIGEN, SDK):
        for dirp, _, fs in os.walk(base):
            if os.path.abspath(dirp).startswith(os.path.abspath(DESTINO)):
                continue
            for f in fs:
                if not f.endswith(".uc"):
                    continue
                nombre = f[:-3]
                if nombre in FICHAS:
                    continue
                t = sin_comentarios(io.open(os.path.join(dirp, f), encoding="utf-8",
                                            errors="replace").read())
                d = {}
                for m in FIRMA_DE_FUNCION.finditer(t):
                    d.setdefault(m.group(1), normaliza_firma(m.group(0)))
                if d:
                    FICHAS[nombre] = d
    return FICHAS


def sin_comentarios(t):
    """
    El texto sin comentarios, para poder mirar la CABECERA de una clase.

    Hace falta y no es un detalle: los `.uc` del SDK empiezan todos con el bloque
    de copyright de Epic, asi que un `re.match` desde el principio del fichero no
    llega nunca a la declaracion y devuelve None. Con eso, el SDK parecia no
    tener NI UNA clase `native` -- `Actor`, `Object`, `Pawn`, todas fuera -- y la
    propagacion de `native` se apoyaba en esa lista.
    """
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def arbol_de_clases():
    """
    (padre de cada clase, clases del SDK que son `native`), en una sola pasada.

    El mapa de padres cubre la exportacion Y el SDK, porque la cadena hay que
    caminarla entera: una clase del juego puede colgar de otra del juego que
    cuelga del SDK.
    """
    padres_todo = dict(padres())
    nativas_sdk = set()

    # La exportacion TAMBIEN cuenta, y no solo el SDK: `Objective.uc` alli es
    # `class Objective;` -- una referencia suelta, sin `native` -- y la version
    # de verdad es la del SDK. Una clase que herede de esa referencia hereda
    # del `Objective` del SDK, y por eso hay que mirarlos juntos.
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = sin_comentarios(io.open(os.path.join(ORIGEN, f), encoding="utf-8",
                                    errors="replace").read().lstrip(chr(0xFEFF)))
        m = re.match(r"\s*(?:class|interface)\s+([A-Za-z_]\w*)", t)
        if m and re.search(r"native", t.split(";", 1)[0]):
            nativas_sdk.add(m.group(1))

    for dirp, _, ficheros in os.walk(SDK):
        if os.path.abspath(dirp).startswith(os.path.abspath(DESTINO)):
            continue
        for f in ficheros:
            if not f.endswith(".uc"):
                continue
            t = sin_comentarios(
                io.open(os.path.join(dirp, f), encoding="utf-8",
                        errors="replace").read().lstrip(chr(0xFEFF)))
            e = EXTIENDE_PADRE.search(t)
            if e:
                padres_todo.setdefault(e.group(1), e.group(2))
            m = re.match(r"\s*(?:class|interface)\s+([A-Za-z_]\w*)", t)
            # `native` EN LA CABECERA, y la cabecera acaba en el primer `;`.
            #
            # Cortar por el primer `{` -- que fue el primer intento -- esta mal:
            # `class Actor extends Object` no lleva llave, y hay clases cuyo
            # primer `{` esta en un comentario o en un struct del cuerpo. Con ese
            # corte, `Actor` y `Object` salian como NO nativas, que es al reves
            # de lo que son, y la propagacion entera se apoyaba en eso.
            cabecera = t.split(";", 1)[0]
            if m and re.search(r"\bnative\b", cabecera):
                nativas_sdk.add(m.group(1))
    return padres_todo, nativas_sdk


def no_pueden_ser_nativas():
    """
    Clases del paquete que NO pueden declararse `native`.

    La regla la dice el compilador con esas palabras:

        Native classes cannot expand non-native classes

    O sea: si alguno de tus ancestros no es native, tu tampoco. Y se **propaga
    sola** por la herencia, que es lo que antes habia que descubrir a base de
    compilar y anotar a mano -- el conjunto de al lado decia "se llena con lo que
    nombra el compilador", y nombraba una por vuelta.

    Se camina hacia arriba y se para en cuanto se sale de la exportacion: a
    partir de ahi manda el SDK, y alli `native` esta escrito.
    """
    padres_todo, nativas_sdk = arbol_de_clases()
    del_paquete = {f[:-3] for f in os.listdir(ORIGEN) if f.endswith(".uc")}
    # SE PROPAGA HACIA ABAJO, NO SE MIRA HACIA ARRIBA ENTERO.
    #
    # El compilador comprueba el PADRE DIRECTO -- `Native classes cannot expand
    # non-native classes` -- asi que la regla es local y el efecto se encadena:
    # si `Objective` deja de ser native, sus hijos tampoco pueden, y los hijos de
    # esos tampoco.
    #
    # Mirar TODOS los ancestros de golpe fue el primer intento, y estaba mal por
    # exceso: marcaba 877 clases y rompia veinte cosas, porque una clase `native`
    # puede tener un abuelo que no lo sea si su padre SI lo es. Lo dijo el
    # compilador al reves -- `Non-native classes not allowed to implement native
    # interfaces` y `Not allowed to declare variables in non-native classes`--,
    # que son los dos sintomas de haber quitado `native` de mas.
    #
    # Punto fijo: se quita `native` mientras alguien tenga un padre sin el.
    fuera = set()
    for _ in range(64):
        crecio = False
        for clase in del_paquete:
            if clase in fuera:
                continue
            padre = padres_todo.get(clase, "")
            if not padre:
                continue
            nativa = padre in nativas_sdk and padre not in fuera
            if not nativa:
                fuera.add(clase)
                crecio = True
        if not crecio:
            break
    return fuera

TIPOS_PERDIDOS = {
    "UIRoot.EItemType":     "EItemType",
    "CoverLink.ECoverHint": "ECoverHint",
    # UN TIPO ANIDADO QUE NO RESUELVE DESDE SU PROPIA CLASE SE ALOJA AQUI.
    #
    # `ENPCQuestTrackingState` esta declarado en la linea 26 de su propio
    # fichero, `CCLobbyRemoteController.uc`, y el compilador contesta:
    #
    #     Unrecognized type 'ENPCQuestTrackingState'
    #         within 'CCLobbyRemoteController'
    #
    # Y lo que lo delata es que **el MISMO tipo, escrito IGUAL, resuelve en unos
    # sitios y no en otros**, dentro del mismo paquete:
    #
    #     UILobbySensor.uc(14)  dentro de un `struct`    FALLA
    #     UILobbySensor.uc(64)  en una firma de funcion  funciona
    #     UILobbySensor.uc(76)  en una firma de funcion  funciona
    #     UIInstanceSoloSensor.uc(11)  en una firma      FALLA
    #
    # O sea que no es `struct` contra funcion, ni la forma de la declaracion:
    # **es de que clase es el tipo**. En el MISMO struct, dos lineas seguidas:
    #
    #     var CCStubTipos.EItemType MinorType;                              <- linea 13, OK
    #     var CCLobbyRemoteController.ENPCQuestTrackingState TrackingState; <- linea 14, FALLA
    #
    # Los tipos de `CCStubTipos` resuelven; los de `CCLobbyRemoteController` no.
    # El porque no se ha llegado a entender -- es de la misma familia que el
    # resto de esta familia -- pero **el arreglo si se entiende**: alojarlo
    # donde los demas, que es lo que ya se hace con `EItemType`.
    #
    # Y no cambia el layout: un enum de UnrealScript es un byte, y los
    # enumeradores son los mismos de la exportacion.
    "CCLobbyRemoteController.ENPCQuestTrackingState": "ENPCQuestTrackingState",

    # Y TRES MAS, DEL MISMO GENERO. Plan 23-errores, B-2: los SIETE tipos
    # declarados que no resuelven. Se empieza por estos TRES porque son ENUM: un
    # enumerador es una POSICION, no hay miembros que tipar, y por tanto no
    # pueden abortar `CCStubTipos` por un miembro sin tipo -- que es el riesgo
    # declarado de alojar.
    #
    # Y se comprobo que el `DependsOn` NO era la via: los siete ya lo tienen, y
    # SEIS lo tienen ademas como PRIMER nombre -- que es el que la tabla
    # `PRIMERO_EN_DEPENDS_ON` controla -- y fallan igual.
    "CCHQGameInfo.eHQStatus":                        "eHQStatus",
    "CCInstanceController.EMusicEventType":          "EMusicEventType",
    "CCInstanceController.ActionBarSlotState_Phase": "ActionBarSlotState_Phase",

    # Y LOS CUATRO STRUCT, con la misma forma y con TRES cosas mas que mirar.
    #
    # LA PRIMERA: aqui SI hay miembros que tipar, y un miembro sin tipo aborta
    # `CCStubTipos` entero -- el riesgo declarado de alojar. Se miraron uno a
    # uno y **los cuatro salen COMPLETOS y TIPADOS del export**, que para esto
    # es la fuente buena: es el guion del propio juego, no una reconstruccion.
    # Los miembros van en `STRUCTS_PERDIDOS`, en el orden del export, que es el
    # orden en que UE3 serializa los defaults de un struct.
    #
    # LA SEGUNDA ES LA CLAVE, Y COSTO UNA VUELTA ENTERA. **La clave tiene que
    # ser la GRAFIA QUE USA EL EXPORT, no la que se ve en el stub.**
    #
    # El compilador dice
    #
    #     Unrecognized type 'TurretFireInfo' within 'CCTurretBase'
    #
    # y en el stub generado lo que hay ESCRITO es `CCTurretBase.TurretFireInfo`,
    # asi que se puso esa clave -- y no arreglo NADA. Porque ese cualificador no
    # viene del export: **lo pone `recualifica()`**, y `recualifica()` corre en
    # la linea 3218, o sea **DESPUES** de esta sustitucion, que es la 3151.
    # Cuando se llega aqui el texto todavia dice `TurretFireInfo` pelado, y una
    # clave con punto no casa nunca.
    #
    # Los tres enum de arriba SI funcionan con punto porque el export los
    # escribe con punto (`CCHQGameInfo.eHQStatus`). La regla no es "pelado" ni
    # "cualificado": es **como lo escriba el export**.
    #
    # Y el sintoma de equivocarse es MUDO: `n` vale 0, no hay aviso, y el
    # fichero sale identico. No lo dijo el compilador -- lo dijo la salida del
    # generador, porque el aviso `N x ... -> CCStubTipos...` NO salia.
    "TurretFireInfo":              "TurretFireInfo",
    "WeaponCarrySlotRBDesc":       "WeaponCarrySlotRBDesc",
    "InstantTraceEffects_RPC_Info": "InstantTraceEffects_RPC_Info",
    "PlacingItemInfo":             "PlacingItemInfo",
    # Y `PlacingItemInfo` ARRASTRA OTRO TIPO, que es lo que el plan avisaba: su
    # miembro `CurrState` es `CCInstancePawn.PlacingItemInfo_State`, otro
    # anidado de la misma clase con la misma enfermedad. Se aloja tambien, con
    # sus cinco enumeradores leidos del export EN ORDEN, `_MAX` incluido.
    #
    # ESTE SI VA CUALIFICADO, por la regla de arriba: el export lo escribe asi
    # en sus dos unicos usos (CCInstancePawn.uc:296 y :3582). PELADO NO CASARIA
    # -- `(?<![\w.])` prohibe entrar detras de un punto.
    #
    # Y ESTO TIENE CONSECUENCIA DE ORDEN: dentro de `CCStubTipos` un tipo tiene
    # que estar declarado ANTES de usarse, y `PlacingItemInfo` <
    # `PlacingItemInfo_State` alfabeticamente, o sea AL REVES de como se
    # necesitan. Ver `orden_declaracion()`.
    "CCInstancePawn.PlacingItemInfo_State": "PlacingItemInfo_State",

    # Y OTRA VUELTA DE LO MISMO, DE `CCInstancePawn` TAMBIEN -- y esta la
    # DESTAPO el arreglo del `exec` de B-4, que tapaba el primer error de
    # `CCInstanceController`:
    #
    #     CCInstanceController.uc(412) : Unrecognized type 'KillerInfo' within 'CCInstancePawn'
    #
    # PELADOS, por la regla de B-2: el export los escribe sin cualificar
    # --`var repnotify KillerInfo FollowKillerInfo;` en `CCInstanceController`,
    # linea 408-- y el cualificador lo pondria `recualifica()` despues.
    #
    # Y `KillerInfo` ARRASTRA DOS TIPOS MAS, que es el riesgo declarado de
    # alojar llevado a su forma larga: sus 29 miembros incluyen
    # `CCAvatar.CCAvatarWeaponSlots` y `CCWeaponPreset.EWeaponTypeName`, que no
    # resolverian desde `CCStubTipos` -- es LA enfermedad que se esta tratando.
    #
    # SE MIDIO EL ARRASTRE ANTES DE DECIDIR, que es lo que pide el plan: **los
    # dos son ENUM, no struct**, y sus enumeradores estan enteros en el export
    # (8 y 16). O sea que el arrastre no arrastra a su vez. Con dos STRUCTS
    # habria que haber mirado otra vez.
    "KillerInfo":        "KillerInfo",
    "DynamicKillerInfo": "DynamicKillerInfo",
    "CCAvatar.CCAvatarWeaponSlots":    "CCAvatarWeaponSlots",
    "CCWeaponPreset.EWeaponTypeName":  "EWeaponTypeName",

    # Y LA COLA DE `CCInstancePawn` SIGUE, que es lo que hace que esto parezca
    # veinte problemas y sea uno: **el compilador para en el primer error de
    # cada clase**, asi que cada alojamiento DESTAPA el siguiente. Ya van
    # cuatro de la misma clase -- `PlacingItemInfo`, `KillerInfo`,
    # `DynamicKillerInfo` y ahora estos dos.
    #
    # SE MIRO LA COLA ENTERA DE UNA VEZ en vez de ir de uno en uno: se buscaron
    # TODAS las referencias a `CCInstancePawn.<algo>` en la exportacion, y solo
    # quedaban dos tipos por alojar. Los otros cuatro nombres que salen
    # --`ParticleSystemComponent1`, `MyLightEnvironment`, `CollisionCylinder`,
    # `AmbientSoundComponent`-- **no son tipos**: son nombres de COMPONENTE en
    # `defaultproperties`, y esos resuelven.
    #
    # Cualificados en el export: `CCInstanceController.uc:9951`.
    "CCInstancePawn.EDeathState":          "EDeathState",
    "CCInstancePawn.EGhostVisibilityType": "EGhostVisibilityType",

    # Y EL RESTO DE LA COLA, QUE YA SE MIDIO ENTERA. En vez de ir de uno en uno
    # --que es lo que el compilador impone, porque para en el primer error de
    # cada clase-- se calculo el CIERRE TRANSITIVO desde los que quedaban:
    #
    #     RagdollStateInfo -> TakeHitInfo
    #     DeathAnimationInfo -> TakeHitInfo
    #     WeaponCarrySlot -> CarrySlotContent -> WeaponCarrySlotRBDesc (ya estaba)
    #     TakeHitInfo -> AdditionalHitInfo (ya estaba)
    #
    # **Seis tipos, uno ya alojado, y NINGUN miembro sin tipo en ninguno** --
    # que es el riesgo declarado de alojar. El cierre se calculo sobre la
    # exportacion entera (1.455 tipos indexados), no a ojo.
    #
    # Y ESTO ES LO QUE HACE QUE PAREZCA VEINTE PROBLEMAS Y SEA UNO: la cola de
    # `CCInstanceController` es larga, y cada alojamiento destapa el siguiente.
    #
    # PELADOS, los cinco: se comprobo la grafia y **no aparecen cualificados en
    # ningun sitio** de la exportacion.
    # Y LOS CINCO QUE ESTABAN BLOQUEADOS POR EL DEFECTO DE LA SUSTITUCION, ya
    # con el arreglo puesto. Su historia, porque es la del dia entero:
    #
    # Se alojaron de golpe ANTES de arreglar nada, y salieron TRES errores de
    # sintaxis -- medido, 14 -> 16 -- porque la sustitucion no miraba DONDE
    # escribia:
    #
    #     local int WeaponCarrySlot;                          nombre de VARIABLE
    #     SelectTakeHitAnimation(TakeHitInfo TakeHitInfo, …)  nombre de PARAMETRO
    #
    # Se revirtieron, se arreglo la sustitucion --`tramos_de_tipo()`, una sola
    # verdad compartida con `recualifica()`-- y ahora entran. **El diff de las
    # 742 clases contra la generacion anterior salio VACIO**, asi que el arreglo
    # no movio nada de lo que ya funcionaba.
    #
    # PELADOS los cinco: se comprobo la grafia y no aparecen cualificados en
    # ningun sitio de la exportacion.
    "WeaponCarrySlot":    "WeaponCarrySlot",
    "CarrySlotContent":   "CarrySlotContent",
    "RagdollStateInfo":   "RagdollStateInfo",
    "DeathAnimationInfo": "DeathAnimationInfo",
    # Y ESTE NO ES DE `CCInstancePawn`, aunque el compilador diga `within
    # 'CCInstancePawn'`: esta declarado en **`CCInstancePawnTakeHitSystem.uc`**.
    # El mensaje nombra la clase por la que lo resolvio, no la que lo declara.
    "TakeHitInfo":        "TakeHitInfo",

    # Y OTRA COLA, LA DE `CCBotPawn`. Se midio igual: declara SEIS tipos
    # anidados y **solo uno sale fuera** de su clase -- lo usa `CCPVPBot`--, en
    # las DOS grafias:
    #
    #     CCPVPBot.uc:2597   function CCBotPawn.ESpecialMove GetSpecialMove()
    #     CCBotPawn.uc:172   var CCBotPawn.ESpecialMove SpecialMove;
    #
    # O sea que esta CUALIFICADO, y la clave va cualificada por la regla de B-2.
    "CCBotPawn.ESpecialMove": "ESpecialMove",


    # Y EL MISMO CASO, EN LA OTRA MITAD DEL INTERCAMBIO.
    #
    # `CCPawn` usa DOS tipos anidados de clases que ordenan distinto que el:
    # `CCController.EMoveDirection` (linea 296) y
    # `CCSkelControl_SingleBone.SkelControlDestLocation` (linea 47). Arreglar
    # uno rompia el otro, TRES VECES medidas:
    #
    #     DependsOn(CCController)                     EMoveDirection OK, el otro NO
    #     DependsOn(CCController, CCSkelControl...)   al reves
    #     la cadena entre las dos                     igual
    #     DependsOn(CCController, CCStubTipos)        EMoveDirection NO
    #
    # Con los DOS alojados aqui, `CCPawn` deja de necesitar a `CCController` para
    # el enum y a `CCSkelControl_SingleBone` para el struct: le basta con
    # `CCStubTipos`, y **los dos resuelven a la vez**.
    "CCController.EMoveDirection": "EMoveDirection",
    # Y EL MISMO CASO, CON UN STRUCT: `SkelControlDestLocation`.
    #
    # >>> ARREGLADO EL 30/9, emparejando FORMAS. Ver `tipo_por_forma`.
    "CCSkelControl_SingleBone.SkelControlDestLocation": "SkelControlDestLocation",
    #
    # El comentario largo de abajo se conserva porque explica POR QUE hubo que
    # arreglar `formas_de_los_defaults()` antes de que esto pudiera funcionar.
    #
    # `CCPawn` lo usa en tres sitios y **solo falla el de la linea 47**, que es
    # una `var`; las 1652 y 1812 son firmas de funcion y funcionan. Misma forma
    # que el enum, misma conclusion: hay que alojarlo aqui.
    #
    # >>> PERO NO SE PUEDE TODAVIA, Y ESTA PROBADO. La entrada esta SIN PONER.
    #
    # Sus cuatro miembros los da el catalogo EN ORDEN -- `Type`, `SocketName`,
    # `Translation`, `Rotation` -- pero los dos ultimos son `StructProperty` y su
    # tipo va en el `FPropertyTag`, que para esta clase no lo tiene nadie: su
    # `Default__` no lo serializa.
    #
    # Se probo a sacarlos del LITERAL de `CCPawn.uc:61`, que si los escribe:
    #
    #     IKLerpingLocation=(Type=EDT_World, SocketName="None",
    #                        Translation=(X=0,Y=0,Z=0), Rotation=(Pitch=0,...))
    #
    # **Y NO VALE: `formas_de_los_defaults()` APLANA los structs anidados.** El
    # `MIEMBRO` de dentro casa tambien los `=` de dentro de los parentesis, asi
    # que el struct salia con OCHO miembros:
    #
    #     var byte Type;  var string SocketName;  var float X;  var float Y;
    #     var float Z;    var int Pitch;  ...
    #
    # Un layout FALSO -- `byte+name+Vector+Rotator` contra `byte+string+3 float+…`
    # -- que es justo lo que este proyecto no hace. Y encima `SocketName` salia
    # `string` donde el catalogo dice `name`.
    #
    # **Lo que falta es que `formas_de_los_defaults()` entienda los parentesis
    # anidados**, y eso toca a los 97 tipos que declara hoy: es un cambio con
    # alcance, no un parche. Queda dicho aqui, que es donde se retoma.
    # Estos dos NO se usan como tipo: se usan como TAMANO DE ARRAY.
    #
    #     var float MarkerBounds[EUIWidgetFace];
    #     var UITexture CellImage[EGridCellState];
    #
    # O sea que lo que importa de ellos no es que existan, es CUANTOS MIEMBROS
    # TIENEN: el tamano del array sale de ahi. Y los miembros NO SON
    # RECUPERABLES -- nada mas los usa en toda la exportacion, asi que no hay
    # uso del que deducirlos, como se hizo con `CIT_` y `CH_`.
    #
    # SE DECLARAN CON UN TAMANO SUPUESTO, y queda dicho que es una suposicion y
    # que es el sitio donde mirar si algun dia importa la serializacion de las
    # clases de UI. `EUIWidgetFace` son las cuatro caras de un widget, que es lo
    # que es en UE3; de `EGridCellState` no hay ni eso, y se pone uno.
    #
    # El riesgo es ACOTADO: quien los usa son clases de UI --UIHudMarker,
    # UIComp_ColorGridPresenter--, que no las importa ningun mapa. Sirven para
    # que el paquete compile, no para que un nivel se vea bien.
    # ESTOS CUATRO SON DE OTRA CLASE: SOLO SE USAN COMO TIPO.
    #
    #     var UIRoot.EUIAlignment Alignment;
    #     var UIRoot.EScreenInputMode StoredInputMode;
    #
    # Nunca como valor --`UIALIGN_Left` y compania no aparecen en ninguna parte
    # de la exportacion--, asi que de ellos solo hace falta QUE EXISTAN. Los
    # miembros no importan, y por eso llevan uno solo. No es un descuido: es que
    # no hay nada que acertar.
    "UIRoot.EEditBoxCharacterSet": "EEditBoxCharacterSet",
    "UIRoot.EScreenInputMode": "EScreenInputMode",
    "UIRoot.EUIAlignment": "EUIAlignment",
    "UIRoot.EUIOrientation": "EUIOrientation",
    "UIRoot.EUIWidgetFace": "EUIWidgetFace",
    "UIRoot.EGridCellState": "EGridCellState",

    # B-5, Y **EL PLAN SE EQUIVOCABA**. Decia que su fuente estaba en
    # `GameInfo.uc` de la exportacion. **La exportacion no tiene `GameInfo.uc`**:
    # solo hay `CrimeCraft/` y `CrimeCraftEd/`. Y el `GameInfo` del SDK tampoco
    # lo declara. Comprobado en los dos sitios y en todo el workspace: **no esta
    # en ningun fichero**, igual que `RenderParameters`.
    #
    # Lo que SI hay es la entrada del catalogo:
    #
    #     tools/tipos-del-juego.txt:11201   Enum   PlayerScoreType   GameInfo
    #
    # O sea que **existir existe**, y eso es todo lo que hace falta: se usa
    # SIEMPRE como tipo, en DOCE clases, y **no hay un solo enumerador suyo en
    # toda la exportacion** -- se busco `PST_` y lo unico que sale es
    # `PSTemplate`, que es otro identificador. Es el caso de
    # `EEditBoxCharacterSet`: de el solo hace falta QUE EXISTA.
    #
    # Y la clave va CUALIFICADA porque es como lo escribe el export
    # --`CCPlayerReplicationInfo.uc:159`, `CCInstanceGameInfo.uc:2200`--, que es
    # la regla que costo una vuelta entera en B-2.
    "GameInfo.PlayerScoreType": "PlayerScoreType",
    # Y `RenderParameters`, que el plan daba por cerrado y NO lo estaba. Ver
    # STRUCTS_PERDIDOS: solo se usa como TIPO, y eso no se habia comprobado.
    # PELADO: el export lo escribe sin cualificar.
    "RenderParameters": "RenderParameters",
    # `DynamicTextureCoordExInfo` va **SIN CUALIFICAR**: se comprobo la grafia y
    # el export lo escribe pelado en sus cuatro apariciones. Sus miembros, que
    # SI se deducen, estan en STRUCTS_PERDIDOS.
    "DynamicTextureCoordExInfo": "DynamicTextureCoordExInfo",
    # Y `WeaponStoppedFiring` es MENOS: `Pawn.uc:1302` tiene DOS y el juego uno.
    # Se le devuelve `Weapon InWeapon` delante y se reenvia en el `super`.
    # (La regla vive mas abajo, con las otras de firma.)

    # SIN CUALIFICAR, y por eso la clave es el nombre pelado: el guion lo escribe
    # `var UIScreenValue_Extent NodeHeight;`, no `Algo.UIScreenValue_Extent`. Se
    # supo por el compilador, que lo nombro dos veces:
    #     UIMisc.uc(332) y UIRichLabel.uc(120) : Unrecognized type 'UIScreenValue_Extent'
    #
    # Y NO ES UN ENUM: era un struct. Se declara como struct -- ver
    # STRUCTS_PERDIDOS -- porque declararlo como enum compilaria y mentiria
    # sobre el tamano.
    "UIScreenValue_Extent": "UIScreenValue_Extent",
    # Y SU HERMANO, que aparecio justo detras. Arreglar el `_Extent` dejo al
    # descubierto `UIMisc.uc(333) : Unrecognized type 'UIScreenValue'`: son dos
    # tipos de la misma familia del sistema de UI, y el compilador nombra uno
    # por vuelta porque para en el primero.
    "UIScreenValue": "UIScreenValue",
}

MIEMBROS_PERDIDOS = {
    "EItemType": ["CIT_None", "CIT_Enemy", "CIT_InstanceType_RadarPlain",
                  "CIT_InstanceType_RadarPlain_Camouflage"],
    # Uno solo: solo se usan como TIPO. Ver TIPOS_PERDIDOS.
    "EEditBoxCharacterSet": ["CHARSET_Default"],
    "EScreenInputMode": ["INPUTMODE_Default"],
    "EUIAlignment": ["UIALIGN_Default"],
    # Los enumeradores son los de la exportacion, leidos de
    # `CCLobbyRemoteController.uc`. Y el ORDEN importa: los valores del enum son
    # las posiciones, y el guion compara contra ellos.
    "ENPCQuestTrackingState": ["ENPCQTS_None", "ENPCQTS_Tracked",
                               "ENPCQTS_TutorialTracked", "ENPCQTS_MAX"],

    # Los tres de B-2 (plan-23-errores). LEIDOS DE LA EXPORTACION Y EN SU ORDEN,
    # porque el valor de un enumerador ES su posicion. El `_MAX` final entra:
    # esta en la exportacion y el guion lo usa como centinela.
    "eHQStatus": ["HQS_Inactive", "HQS_Active", "HQS_Capturing",
                  "HQS_Captured", "HQS_MAX"],
    "EMusicEventType": ["EMT_None", "EMT_Action", "EMT_Stampede", "EMT_Stealth",
                        "EMT_Suspense", "EMT_Background", "EMT_SubgoalComplete",
                        "EMT_MissionComplete", "EMT_Fail", "EMT_PlayerDeath",
                        "EMT_MissionStart", "EMT_CoreDestroyed", "EMT_MAX"],
    "ActionBarSlotState_Phase": ["ASSP_Active", "ASSP_Inactive", "ASSP_Cooldown",
                                 "ASSP_Preparing", "ASSP_Prepared",
                                 "ASSP_Affecting", "ASSP_MAX"],
    # B-5. UNO SOLO, Y **ES INVENTADO**: el enum tiene que tener al menos un
    # enumerador o el compilador dice `Enumeration must contain at least one
    # enumerator`, y de los de verdad no hay ni rastro en ningun fichero. No es
    # un descuido y no hay nada que acertar: **no se usa ninguno**.
    #
    # El prefijo es el de la convencion de la casa para estos casos
    # --`CHARSET_Default`, `INPUTMODE_Default`, `UIALIGN_Default`--, no una
    # suposicion sobre el juego.
    "PlayerScoreType": ["PST_Default"],
    # Y LOS DOS ENUMS QUE ARRASTRA `KillerInfo`. Aqui los enumeradores SI son
    # los de verdad, leidos del export EN ORDEN y con `_MAX` incluido -- que es
    # lo contrario que `PlayerScoreType`, y por la misma razon: alli no se usa
    # ninguno y aqui el struct los lleva como tipo de un miembro.
    "CCAvatarWeaponSlots": ["AWS_Unknown", "AWS_PrimaryWeapon1",
                            "AWS_PrimaryWeapon2", "AWS_SecondaryWeapon",
                            "AWS_MeleeWeapon", "AWS_ThrowingWeapon1",
                            "AWS_ThrowingWeapon2", "AWS_MAX"],
    # Los dos de la cola de `CCInstancePawn`, con sus enumeradores del export
    # EN ORDEN y `_MAX` incluido.
    "EGhostVisibilityType": ["EGVT_None", "EGVT_SameTeam", "EGVT_AllTeams",
                             "EGVT_MAX"],
    # El de `CCBotPawn`, del export EN ORDEN. `SXX_Fix_Max` no es una errata
    # nuestra: esta asi en la exportacion, entre `SM_Test` y el centinela.
    "ESpecialMove": ["SM_None", "SM_Leapfrog_Fwd", "SM_Leapfrog_Bwd",
                     "SM_Leapfrog_Left", "SM_Leapfrog_Right", "SM_Test",
                     "SXX_Fix_Max", "ESpecialMove_MAX"],
    "EDeathState": ["EDS_Alive", "EDS_FeigningDeath", "EDS_FakeDeath",
                    "EDS_Dying", "EDS_MAX"],
    "EWeaponTypeName": ["WTN_Assault_Rifle", "WTN_Shotgun", "WTN_Sniper_Rifle",
                        "WTN_Pistol", "WTN_SMG", "WTN_Grenade_launcher",
                        "WTN_MolotovCocktail", "WTN_LMG", "WTN_FragGrenade",
                        "WTN_PEDGrenade", "WTN_Injection_Gun",
                        "WTN_Rocket_launcher", "WTN_ClasterGrenade",
                        "WTN_ClasterRocket", "WTN_ClasterBomb", "WTN_MAX"],
    # El cuarto de B-2, y el unico que NO se usa como tipo suelto: lo usa
    # `PlacingItemInfo` como tipo de su miembro `CurrState`, y por eso el enum y
    # el struct van juntos. Cinco, en el orden del export.
    "PlacingItemInfo_State": ["PlacingItemInfo_State_BeginSearching",
                              "PlacingItemInfo_State_EndSearching",
                              "PlacingItemInfo_State_BeginPlacing",
                              "PlacingItemInfo_State_EndPlacing",
                              "PlacingItemInfo_State_MAX"],
    # Los diez de la exportacion, y el ORDEN importa: los valores del enum son
    # las posiciones, y el guion compara contra ellos.
    "EMoveDirection": ["EMD_Stay", "EMD_Forward", "EMD_ForwardRight", "EMD_Right",
                       "EMD_RightBackward", "EMD_Backward", "EMD_BackwardLeft",
                       "EMD_Left", "EMD_LeftForward", "EMD_MAX"],
    "EUIOrientation": ["UIORIENT_Default"],
    # Estos dos SI importan por el numero: son TAMANO DE ARRAY.
    "EUIWidgetFace": ["UI_FACE_Left", "UI_FACE_Top", "UI_FACE_Right", "UI_FACE_Bottom"],
    "EGridCellState": ["EGCS_Default"],
    "ECoverHint": [
        "CH_None",
        "CH_AssaultRifles_Skill", "CH_BurstingDamageRes", "CH_CoverNPC01",
        "CH_CoverNPC02", "CH_DamageAbsorb", "CH_ExplosiveDamageRes",
        "CH_GrenadeLauncher_Skill", "CH_HP_Max", "CH_HP_RegenSpdNoAction",
        "CH_HP_RegenSpdOneAction", "CH_HP_RegenSpdTwoActionsOrSprint",
        "CH_MBoots01", "CH_Machineghun_Skill", "CH_McommonU03",
        "CH_MfighterL06", "CH_MfighterU03", "CH_PearcingDamageRes",
        "CH_Pistols_Skill", "CH_ReactiveDamageRes", "CH_RocketLauncher_Skill",
        "CH_SMGs_Skill", "CH_STM_Max", "CH_STM_RegenSpdNoAction",
        "CH_STM_RegenSpdOneActions", "CH_STM_RegenSpdTwoActions",
        "CH_Shotguns_Skill", "CH_SniperRifles_Skill",
    ],
}

# QUE CUENTA COMO DECLARAR UN TIPO.
#
# `interface` faltaba, y costo un falso hueco: `CCDoTarget` tiene declaracion de
# verdad --`interface CCDoTarget extends Interface`-- pero como no empezo por
# `class`, ni `duenos()` ni la clausura ni el recuento del SDK lo veian, y el
# generador lo daba por tipo sin fuente. No lo estaba.
# EL MODIFICADOR VA ENTRE LA PALABRA CLAVE Y EL NOMBRE, Y NO SOLO `native`.
#
# El patron era `(?:class|struct|enum|interface)\s+(?:native\s+)?(\w+)`, o sea
# que contemplaba UN modificador y solo uno. Pero UnrealScript escribe:
#
#     struct immutable Vector2D              Core/Classes/Object.uc:173
#     struct native transient TraceHitInfo   Engine/Classes/Anchor.uc:295
#     struct atomic Box
#
# Y con esto el catalogo del SDK **no veia esos tipos**. La consecuencia es de
# las caras: `tipos_del_sdk()` es el filtro que decide QUE NO SE STUBEA, asi que
# un tipo que "no esta" se acaba declarando OTRA VEZ en el paquete, y quedan dos
# structs con el mismo nombre.
#
# Se captura la cola entera y se filtra despues: el nombre es el PRIMER token
# que no sea un modificador. Es la misma regla que usa `tipo_de_var()`, y es la
# tercera vez que este proyecto tropieza con ella -- las otras dos fueron la
# categoria de un `var` y los modificadores de una firma.
DECLARA = re.compile(r"^\s*(?:class|struct|enum|interface)\s+((?:\w+[ \t]+)*\w+)", re.M)

# Y `interface X extends Y` hereda igual que una clase. Sin esto, la clausura no
# sigue la herencia de las interfaces y sus bases no entran.
EXTIENDE = re.compile(r"^\s*(?:class|interface)\s+\w+\s+extends\s+([A-Za-z_]\w*)", re.M)

# ---------------------------------------------------------------------------
# MODIFICADORES QUE VAN ENTRE LA PALABRA CLAVE Y EL NOMBRE
#
# `struct native transient TurretFireInfo` es la forma que emite el
# descompilador, y DECLARA capturaba `transient` COMO SI FUERA EL NOMBRE.
#
# Con eso, `duenos()` decia que `CCTurretBase` declara un tipo llamado
# `transient` -- y la recualificacion reescribio medio paquete a
# `CCTurretBase.transient`, que no existe. El compilador lo dijo con una
# precision que no dejaba dudas:
#
#     Unrecognized type 'transient' within 'CCTurretBase'
#
# Y ahi esta la leccion de metodo: el fallo no estaba donde se leia el fichero,
# estaba en el CATALOGO. Un catalogo que se cree un tipo llamado `transient`
# contamina todo lo que dependa de el, y el error aparece lejos.
# ---------------------------------------------------------------------------
# Y TRES MAS, medidos igual: recorrer las declaraciones del SDK y quedarse con
# los primeros tokens en minuscula que no esten en el conjunto.
#
#     immutablewhencooked   16
#     immutable             15   `struct immutable Vector2D`
#     pointer                1
#
# Con ellos fuera, el catalogo se creia que el SDK declaraba tipos llamados
# `immutable` y `immutablewhencooked`, y NO veia a `Vector2D`, `IntPoint` ni
# `Box`.
MODIFICADORES_TIPO = {
    "immutable", "immutablewhencooked", "pointer",
    "native", "transient", "atomic", "config", "abstract", "deprecated",
    "notplaceable", "perobjectconfig", "editinlinenew", "instanced",
    "private", "protected", "public", "within",
}


def declarados(texto):
    """
    Nombres de tipo declarados en el texto, SIN los modificadores.

    El nombre es el PRIMER token de la cola que no sea un modificador, y no el
    unico: `DECLARA` ahora devuelve la cola entera --`immutable Vector2D`,
    `native transient TraceHitInfo`-- porque no se puede saber de antemano
    cuantos modificadores van a ir delante.
    """
    nombres = set()
    for cola in DECLARA.findall(texto):
        for t in cola.split():
            if t not in MODIFICADORES_TIPO:
                nombres.add(t)
                break
    return nombres


def tipos_del_sdk():
    """
    Todos los nombres de clase y struct declarados en el arbol .uc del SDK.

    NO cuenta lo que hay en CrimeCraftStubs, y eso no es un detalle: los stubs
    viven dentro de `Development/Src`, asi que recorriendolo entero el SDK
    "declara" todo lo que los propios stubs acaban de escribir. La clausura
    entonces no expande nada --cada superclase ya parece declarada, por si
    misma-- y el recuento BAJA en vez de subir. Paso exactamente eso: 266 clases
    la primera vez, 241 la segunda, con el mismo codigo.
    """
    # DOS FALLOS QUE ESTUVIERON AQUI DESDE EL PRINCIPIO, y los dos hacian que
    # este conjunto fuera MAS PEQUENO de lo que debia:
    #
    #   1. El patron solo contemplaba `class` y `struct`. No `enum` ni
    #      `interface`. Con eso, el SDK "no declaraba" nada de eso, y el filtro
    #      que impide stubear lo que el SDK ya tiene dejaba pasar `Interface`.
    #   2. NO SE QUITABA EL BOM. La primera declaracion de cada fichero quedaba
    #      invisible, porque un BOM delante de `class` hace que `^\s*class` no
    #      case. Es la cuarta vez que ese byte muerde en este proyecto.
    nombres = set()
    for dirp, _, ficheros in os.walk(SDK):
        if os.path.abspath(dirp).startswith(os.path.abspath(DESTINO)):
            continue
        for f in ficheros:
            if not f.endswith(".uc"):
                continue
            try:
                s = io.open(os.path.join(dirp, f), encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            nombres.update(declarados(s.lstrip(chr(0xFEFF))))
    return nombres


# NOMBRES QUE EL MOTOR YA OCUPA AUNQUE NO TENGAN FICHERO `.uc`.
#
# `tipos_del_sdk()` lee ficheros `.uc`, y por eso es CIEGO a toda clase
# `noexport`: no tiene fuente, se declara en C++. Y esas son justo las que peor
# estorban, porque entre ellas esta el METACLASE.
#
# Declarar un `Class` propio no da un error de tipo. SOMBREA el metalclase, y a
# partir de ahi el analizador de tipos no reconoce `class` como el metalclase
# --`UnScrCom.cpp:3671` lo busca con `FindObject<UClass>(ANY_PACKAGE, ...)`, y
# devuelve el nuestro--, asi que la rama que lee `class<...>` no se ejecuta, el
# `<` se queda sin consumir, y el error que sale es:
#
#     Error, Missing variable name
#
# Un mensaje que no nombra ni el tipo, ni el metalclase, ni el fichero donde
# esta la causa. Salieron 16 de golpe, y todos apuntaban a una linea con
# `class<...>` sin decir que el problema era el `Class` de otro fichero.
def nombres_del_motor():
    """
    Los nombres que el motor registra de si mismo, leidos de sus registros.

    Son dos ficheros generados por las herramientas de Epic, y en ellos el
    motor declara los nombres que ya tiene ANTES de cargar ningun paquete:

      - Core/Inc/UnNames.h        REGISTER_NAME( 677, Class)
      - Engine/Inc/EngineNames.h  AUTOGENERATE_NAME(...)

    Es una fuente que no depende de ningun `.uc`, que es exactamente lo que
    hacia falta. De los 781 nombres que salen, UNO choca con los stubs: `Class`.
    """
    nombres = set()
    ficheros = [
        os.path.join(SDK, "Core", "Inc", "UnNames.h"),
        os.path.join(SDK, "Engine", "Inc", "EngineNames.h"),
    ]
    for ruta in ficheros:
        try:
            s = io.open(ruta, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        nombres.update(REGISTRA_NOMBRE.findall(s))
        nombres.update(AUTOGENERA_NOMBRE.findall(s))
    # Los dos ficheros traen su propia definicion de la macro, y ahi el
    # argumento se llama `name`: sin quitarlo, el motor "ocuparia" un nombre
    # llamado `name`.
    nombres.discard("name")
    return nombres


REGISTRA_NOMBRE = re.compile(r"^\s*REGISTER_NAME\(\s*\d+\s*,\s*([A-Za-z_]\w*)\s*\)", re.M)
AUTOGENERA_NOMBRE = re.compile(r"AUTOGENERATE_NAME\(\s*([A-Za-z_]\w*)\s*\)")

# ---------------------------------------------------------------------------
# UN `const` NO PUEDE VALER LO QUE VALE EN UN CUERPO DE FUNCION
#
# `CompileConst()` -- UnScrCom.cpp:1384 -- acepta DOS cosas y solo dos:
#
#     if( ValueToken.TokenType != TOKEN_Const ) {
#         if (ValueToken.Matches(TEXT("sizeof"))) { ... }   // la UNICA excepcion
#         else appThrowf( TEXT("const %s: Value is not constant"), ... );
#     }
#
# Un literal, o `sizeof(X)`. Nada mas.
#
# Y el descompilador emite esto, que SI es legal -- pero en un cuerpo de funcion,
# donde lo evalua el compilador de expresiones:
#
#     const AAI_MaxMeshParameters = class'CCPawn'.const.AdditionalAnimInfo_MaxMeshParameters;
#
# `class'CCPawn'` pasa el filtro como literal, y el `.const.X` que le sigue no lo
# consume nadie. El `;` que el compilador espera se lo encuentra convertido en
# `.`, y el error que sale es:
#
#     Error, Missing ';' before '.'
#
# DE SINTAXIS. O sea que PARA al compilador y falsea todo lo que venga debajo.
#
# Es de la misma familia que el BOM, que `Array type was not detected` y que
# `Class<X>`: legal donde el descompilador lo pone, rechazado donde lo pone.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ARRAYS DIMENSIONADOS POR UN ENUM QUE NO SIRVE PARA DIMENSIONAR
#
# En UnrealScript, `var T Foo[EEnum]` significa "uno por cada valor del enum".
# Hay 30 declaraciones asi en el paquete, y **solo 5 fallan** -- luego el
# mecanismo esta bien y lo que falla son cuatro enums concretos, por dos motivos
# distintos que dan dos mensajes distintos:
#
#   `Bad or missing array size`     el enum NO EXISTE en ninguna parte
#   `Illegal array size 1`          el enum existe, es de TIPOS_PERDIDOS y se
#                                   invento con UN miembro. Y UE3 rechaza un
#                                   array de tamano 1: `[1]` no es un array.
#
# El tamano se pone explicito SOLO donde el enum no vale, y sale de la evidencia
# cuando la hay. NO se toca ninguna de las otras 25.
# ENUMS QUE NO SIRVEN PARA DIMENSIONAR UN ARRAY.
#
#   - `EListCellStateX` NO EXISTE: ni fichero, ni `TIPOS_PERDIDOS`, ni SDK.
#   - Los otros nacieron en `TIPOS_PERDIDOS` con UN miembro inventado, y UE3
#     rechaza un array de tamano 1: `[1]` no es un array.
#
# Y el tamano NO se pone a mano. Estuvo asi, con una tabla, y estaba MAL: ponia
# `EGridCellState -> 2` cuando el mismo enum dimensiona arrays de cinco. El
# error fue creer que el tamano es una propiedad DEL ENUM.
#
# El dato esta en el fichero: el `structdefaultproperties` de ese struct asigna
# `Nombre[0]=`, `Nombre[1]=`..., y el mayor indice dice el tamano. Es un dato
# POR DECLARACION, y por eso se lee por declaracion. Ver `tamano_de_array()`.
ENUMS_QUE_NO_DIMENSIONAN = {
    "EListCellStateX",
    "EGridCellState",
    "EUIOrientation",
    # `EUIAlignment` SE DECLARA CON UN SOLO MIEMBRO, y un enum de uno no
    # dimensiona nada:
    #
    #     UIQuasiMode.uc(90) : Variable declaration LastOpenedCharMenuTemplates:
    #                          Illegal array size 1
    #
    # `var transient UICharMenu LastOpenedCharMenuTemplates[EUIAlignment];`
    # sale con tamano 1, y UE3 lo rechaza. Entra aqui como los otros tres: se le
    # busca tamano en el `structdefaultproperties` y, si no lo dice, se pone el
    # MINIMO LEGAL con su aviso.
    #
    # Y no lo destapa el delegado: lo que hace el delegado es **mover el
    # analisis** hasta que esta clase se compila del todo. El array estaba mal
    # desde antes y no se veia.
    "EUIAlignment",
}
ARRAY_POR_ENUM = re.compile(
    r"^([ \t]*)(var|local)([^;\n]*?)\s([A-Za-z_]\w*)\[([A-Za-z_]\w*)\]([ \t]*;)", re.M)
# El trozo de fichero que va de la declaracion al cierre del struct que la
# contiene. Dentro esta su `structdefaultproperties`, y solo el suyo.
HASTA_EL_CIERRE = re.compile(r"\A.*?^[ \t]*\};", re.M | re.S)


def tamano_de_array(texto, desde, nombre):
    """
    Tamano que la propia declaracion esta pidiendo, o None si no lo dice.

    Se busca el mayor indice de `nombre[i]=` en el `structdefaultproperties` del
    struct que contiene la declaracion -- NO en todo el fichero. La diferencia
    importa y costo una medicion: `UIMisc` tiene DOS structs con un miembro
    llamado `Images`, uno de diez entradas y otro de cinco, y mirando el fichero
    entero el de cinco recibia el tamano del de diez. Ese numero compila, y esta
    mal: el tamano de un array de una clase `native` es LAYOUT.
    """
    trozo = HASTA_EL_CIERRE.match(texto[desde:])
    if not trozo:
        return None
    indices = re.findall(r"^[ \t]*" + re.escape(nombre) + r"\[(\d+)\]",
                         trozo.group(0), re.M)
    return max(int(i) for i in indices) + 1 if indices else None

SOLO_EN_CONST = re.compile(
    r"^([ \t]*)const[ \t]+([A-Za-z_]\w*)[ \t]*=[ \t]*"
    r"class'([A-Za-z_]\w*)'\.const\.([A-Za-z_]\w*)[ \t]*;[ \t]*$", re.M)
DECLARA_CONST = re.compile(r"^[ \t]*const[ \t]+([A-Za-z_]\w*)[ \t]*=[ \t]*(.+?)[ \t]*;", re.M)


# OJO CON EL NOMBRE. Se llamo `EXTIENDE` y ESO YA EXISTIA -- arriba, con UN
# grupo y otro proposito. Al redefinirlo con DOS grupos, el `findall` de la
# clausura empezo a devolver tuplas en vez de cadenas, y el fallo salio a 600
# lineas de distancia:
#
#     clausura(): TypeError: can only concatenate tuple (not "str") to tuple
#
# El sintoma, en `clausura`. La causa, aqui. Otra vez.
EXTIENDE_PADRE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s+extends\s+([A-Za-z_]\w*)", re.M)


def padres():
    """Clase -> su padre, leido de `extends` en la exportacion."""
    m = {}
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8", errors="replace").read()
        e = EXTIENDE_PADRE.search(t.lstrip(chr(0xFEFF)))
        if e:
            m[e.group(1)] = e.group(2)
    return m


# ---------------------------------------------------------------------------
# LA FORMA DE UN TIPO PERDIDO, LEIDA DE LOS `defaultproperties`
#
# Un struct perdido no se puede inventar -- eso compila y MIENTE sobre el
# layout. Pero muchas veces hay un dato, y estaba a la vista:
#
#     var AdditionalHitInfo AddInfo;
#     ...
#     defaultproperties
#     {
#         AddInfo=(HitEffectType=0,bUseHitAnimation=false,ShotFlags=0,
#                  ShootTime=0.0000000,ShotOffGibPreset=none)
#     }
#
# Ese literal da **los cinco miembros y SU ORDEN** -- UE3 serializa los defaults
# de un struct en el orden en que se declararon los miembros. Y el ORDEN era
# justo lo que estaba documentado como suposicion en `MIEMBROS_PERDIDOS`.
#
# El valor de cada miembro dice su tipo, con cuatro reglas y ninguna adivinanza:
#
#     false / true        -> bool
#     none                -> un objeto; se pone `Object`, que es lo mas
#                            general que compila
#     0.0000000           -> float   (lleva punto)
#     0                   -> int     (no lleva)
#     "..."               -> string
#
# Y SI ALGUN MIEMBRO NO SE SABE TIPAR, **no se declara el tipo entero**. A
# medias seria peor: un struct con los miembros de otro tamano miente sobre el
# layout, que es exactamente lo que se quiere evitar.
# ---------------------------------------------------------------------------
DECL_VAR = re.compile(
    r"^[ \t]*var[ \t(][^;\n]*?([A-Z][A-Za-z_0-9]*)[ \t]+([A-Za-z_]\w*)[ \t]*;", re.M)
LITERAL = re.compile(r"^[ \t]*([A-Za-z_]\w*)\s*=\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)", re.M)
MIEMBRO = re.compile(r"([A-Za-z_]\w*)\s*=\s*([^,()]+)")


def tipo_del_valor(v):
    """El tipo UnrealScript de un valor de `defaultproperties`, o None."""
    if v in ("true", "false"):
        return "bool"
    if v == "none":
        return "Object"
    if v.startswith(chr(34)) or v.startswith(chr(39)):
        return "string"
    if re.fullmatch(r"-?\d+\.\d+", v):
        return "float"
    if re.fullmatch(r"-?\d+", v):
        return "int"
    return None          # `Clase.Enum`, o un struct anidado: NO se adivina


def formas_de_los_defaults():
    """
    Tipo -> [(miembro, tipo), ...] en el ORDEN en que se declararon.

    Se une el nombre de la variable con el tipo que declara esa variable, y eso
    es lo que faltaba en el primer intento: el literal va con el NOMBRE, no con
    el tipo, asi que buscarlo por el tipo no encuentra casi nada -- salieron 2
    de 424. Uniendolos bien salen 125.
    """
    var2tipo = {}
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8", errors="replace").read()
        for tipo, nombre in DECL_VAR.findall(t):
            var2tipo.setdefault(nombre, tipo)

    # TODOS los literales, ya partidos por comas DE PRIMER NIVEL.
    crudos = []
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8", errors="replace").read()
        for var, cuerpo in LITERAL.findall(t):
            tipo = var2tipo.get(var)
            if tipo:
                crudos.append((tipo, parte_miembros(cuerpo)))

    # PASO 1: EL INDICE DE FORMAS CONOCIDAS.
    #
    # Solo con lo que se sabe tipar sin ayuda, y solo con formas COMPLETAS: este
    # indice es el que despues se usa para tipar los literales ANIDADOS, asi que
    # una entrada a medias envenenaria el emparejamiento.
    forma, indice = {}, {}
    for tipo, pares in crudos:
        if tipo in forma:
            continue
        simples, vale = [], True
        for m, v in pares:
            tv = tipo_del_valor(v)
            if tv is None:
                vale = False
                break
            simples.append((m, tv))
        if vale and simples:
            forma[tipo] = simples
            indice.setdefault(tuple(simples), tipo)

    # PASO 2: Y AHORA CON ANIDAMIENTO, EMPAREJANDO LA FORMA.
    #
    # `Vector` ya esta en el indice como `((X,float),(Y,float),(Z,float))`. Un
    # literal anidado `(X=0.0,Y=0.0,Z=0.0)` tiene EXACTAMENTE esa forma, y
    # ningun otro tipo conocido la tiene. Eso es el tipo, y es una comprobacion,
    # no una adivinanza: si casara con varios o con ninguno, no se declara.
    for tipo, pares in crudos:
        if tipo in forma:
            continue
        resueltos = []
        for m, v in pares:
            tv = tipo_del_valor(v)
            if tv is None and v.startswith("(") and v.endswith(")"):
                tv = tipo_por_forma(parte_miembros(v[1:-1]), indice)
            # UN HUECO NO TIRA LA FORMA: se guarda, y quien la use puede
            # cerrarlo. Lo que NO se hace es inventarlo aqui.
            resueltos.append((m, tv))
        if resueltos:
            forma[tipo] = resueltos
    return forma


def tipo_por_forma(pares, indice):
    """
    El tipo de un literal ANIDADO, emparejando su FORMA contra las conocidas.

    Devuelve None si algun miembro no se sabe tipar, o si la forma no casa con
    ninguno o casa con mas de uno. Los tres casos son motivo para NO declararlo:
    el emparejamiento vale justo porque es unico.
    """
    forma = []
    for m, v in pares:
        tv = tipo_del_valor(v)
        if tv is None:
            return None
        forma.append((m, tv))
    return indice.get(tuple(forma))


def parte_miembros(cuerpo):
    """
    Los `miembro=valor` de un literal, cortando por comas DE PRIMER NIVEL.

    POR QUE NO VALE UNA EXPRESION SOLA
    ----------------------------------
    `MIEMBRO = ([A-Za-z_]\\w*)\\s*=\\s*([^,()]+)` exigia que el valor **no**
    llevara parentesis. Asi que al llegar a

        Translation=(X=0.0000000,Y=0.0000000,Z=0.0000000)

    **saltaba el miembro** -- el valor empezaba por `(` y no casaba -- y seguia
    buscando dentro, donde si casaba `X=0.0000000`. Ese era el aplanado: un
    struct de cuatro miembros salia con ocho, y con un layout falso.

    Aqui se recorre el cuerpo contando parentesis: **las comas de dentro de un
    parentesis no cortan**, y el valor de un miembro puede ser todo un literal
    anidado.

    `X[1]=` se descarta -- `nombre` tiene que ser un identificador entero -- que
    es como se evitaba antes el duplicado que deja UE3 en los arrays.
    """
    trozos, prof, actual = [], 0, ""
    for c in cuerpo:
        if c == "(":
            prof += 1
        elif c == ")":
            prof -= 1
        if c == "," and prof == 0:
            trozos.append(actual)
            actual = ""
        else:
            actual += c
    if actual:
        trozos.append(actual)
    pares = []
    for t in trozos:
        if "=" not in t:
            continue
        nombre, valor = t.split("=", 1)
        nombre, valor = nombre.strip(), valor.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", nombre):
            pares.append((nombre, valor))
    return pares


# ---------------------------------------------------------------------------
# LOS TIPOS QUE SOLO TIENE EL MOTOR DEL JUEGO
#
# `tools/tipos-del-juego.txt` lo genera `ue3-packer types` sobre los paquetes del
# juego -- la version que SI tenia los tipos que al SDK le faltan -- y trae, por
# cada exportacion: **genero, nombre y contenedor**. Con el contenedor se reunen
# los MIEMBROS de un struct, **en su orden de declaracion**.
#
# La leccion que costo llegar aqui: `ue3-packer clases` **solo lista clases**, y su
# ausencia se leia como «no existe». Seis tipos que se creian perdidos estaban
# en el juego, como `ScriptStruct`, con todos sus miembros.
# ---------------------------------------------------------------------------
TIPO_DEL_JUEGO = {}
MIEMBROS_DEL_JUEGO = {}

# Genero de propiedad -> tipo en UnrealScript.
PROPIEDAD_A_TIPO = {
    "ObjectProperty": "Object",
    "ClassProperty": "class<Object>",
    "InterfaceProperty": "Interface",
    "NameProperty": "name",
    "IntProperty": "int",
    "FloatProperty": "float",
    "BoolProperty": "bool",
    "StrProperty": "string",
    "ByteProperty": "byte",
}
# Y DOS QUE NO SE PUEDEN TIPAR SIN MAS, asi que NO se declara el struct entero.
# A medias mentiria sobre el layout, que es justo lo que se quiere evitar:
#
#   StructProperty   hace falta DE QUE struct, y la tabla de exportaciones no lo
#                    dice: el nombre va en el `FPropertyTag`, en los datos
#                    serializados.
#   ArrayProperty    hace falta el tipo del ELEMENTO, por lo mismo.
SIN_TIPO = {"StructProperty", "ArrayProperty"}


# LOS DOS CATALOGOS, Y SON DOS PORQUE SON DOS SITIOS.
#
#   tipos-del-juego.txt        los paquetes del MOTOR del juego (v4701)
#   tipos-crimecraft.txt       el PAQUETE DEL JUEGO -- CrimeCraft.u
#
# El turno 3 solo miro el primero, y de ahi que seis tipos siguieran sin
# declararse: `ItemContextMenuDesc`, `WeaponCarrySlotRBDesc`, `TurretFireInfo`,
# `ENPCQuestTrackingState` y `SkelControlDestLocation` **no estan en el motor**,
# estan en el paquete del juego. Medido con `ue3-packer types` sobre `CrimeCraft.u`,


# los cinco aparecen con su genero y su dueno.
#
# Los dos se leen EN ESTE ORDEN, y el orden importa poco porque los generos se
# guardan con `setdefault` (gana el primero) y **los contenedores de los dos son
# disjuntos** -- comprobado: cero nombres de struct o enum repetidos entre los
# dos ficheros. Si algun dia dejaran de serlo, los miembros de un struct se
# mezclarian en el orden equivocado y el layout saldria mal EN SILENCIO.
#
# Y EL TERCERO ES DE DEDUCCION, NO DE TABLA:
#
#   tipos-de-miembros.txt   los miembros de los structs que la TABLA DE
#                           EXPORTACIONES no describe. `STYLE_ID` es el caso:
#                           no tiene ni una exportacion propia, y sin esto se
#                           declararia VACIO cuando mide cuatro enteros.
#
# Va ULTIMO, y el generador ignora sus lineas para un contenedor que ya tenga
# miembros: manda la tabla de exportaciones, que es la de declaracion.
CATALOGOS = ("tipos-del-juego.txt", "tipos-crimecraft.txt", "tipos-de-miembros.txt")


# DE QUE STRUCT ES UN MIEMBRO QUE ES STRUCT.
#
# El catalogo dice `StructProperty AssignedStyleID UIRoot.UIStyleReference`: se
# sabe que es un struct y **no de cual**. Ese nombre no esta en la tabla de
# exportaciones -- va en el `FPropertyTag`, en los datos serializados.
#
# Lo lee `tools/probe-properties.py` de los objetos `Default__<Clase>`, donde el
# valor de un struct es otra lista de tags, y lo vuelca
# `tools/genera-tabla-structs.py`.
#
# MEDIDO, y es lo que cierra la familia:
#
#     UIStyleReference   AssignedStyleID   STYLE_ID
#     UICombinedStyleData  TextScale        Vector2D
#     UICombinedStyleData  TextAttributes   UITextAttributes
#     ...
#
# Y la tabla se VALIDA SOLA: trae `UIImageAdjustmentData.ProtectedRegion ->
# UIScreenValue_Extent`, que el catalogo ya tenia declarado como StructProperty
# de ese struct. Coincide.
DE_QUE_STRUCT = {}


def de_que_struct():
    ruta = os.path.join(DATOS, "tipos-de-structs.txt")
    m = {}
    if not os.path.exists(ruta):
        return m
    for linea in io.open(ruta, encoding="utf-8", errors="replace"):
        if linea.startswith("#") or chr(9) not in linea:
            continue
        p = linea.rstrip(chr(10)).split(chr(9))
        if len(p) == 3 and all(p):
            m[(p[0], p[1])] = p[2]
    return m


def tipos_del_juego():
    """
    Lee los catalogos del juego. Devuelve (tipos, miembros, sin_tipar).

    **MANDA EL PRIMER CATALOGO QUE DESCRIBE UN CONTENEDOR**, y la decision se
    toma por contenedor ENTERO, no linea a linea.

    La primera version filtraba linea a linea (`if dueno in miembros: continue`)
    y eso dejaba **un solo miembro por struct**: la primera linea metia el
    contenedor en `miembros`, y las siguientes -- que son los DEMAS miembros del
    mismo struct -- se descartaban. Salieron los nueve tipos declarados con un
    miembro cada uno, y se vio en el propio informe del generador.
    """
    tipos, miembros, sin_tipar = {}, {}, set()
    reclamados = set()
    for nombre in CATALOGOS:
        ruta = os.path.join(DATOS, nombre)
        if not os.path.exists(ruta):
            continue
        locales, por_dentro, sin_tipo = {}, {}, {}
        _lee_catalogo(ruta, locales, por_dentro, sin_tipo)
        for k, v in locales.items():
            tipos.setdefault(k, v)
        for contenedor in list(por_dentro) + list(sin_tipo):
            if contenedor in reclamados:
                continue
            reclamados.add(contenedor)
            if contenedor in por_dentro:
                miembros[contenedor] = por_dentro[contenedor]
            for miembro in sin_tipo.get(contenedor, ()):
                sin_tipar.add((contenedor, miembro))
    return tipos, miembros, sin_tipar


def _lee_catalogo(ruta, tipos, miembros, sin_tipar):
    """Lee un catalogo. `miembros` y `sin_tipar` van POR CONTENEDOR."""
    for linea in io.open(ruta, encoding="utf-8", errors="replace"):
        if linea.startswith("#") or chr(9) not in linea:
            continue
        partes = linea.rstrip(chr(10)).split(chr(9))
        if len(partes) != 3:
            continue
        genero, nombre, contenedor = partes
        if genero in ("ScriptStruct", "Enum"):
            tipos.setdefault(nombre, genero)
        elif nombre and contenedor:
            # Es un MIEMBRO: cuelga de un tipo por su contenedor.
            dueno = contenedor.rsplit(".", 1)[-1]
            if genero in SIN_TIPO:
                # AQUI ESTABA EL BLOQUEO DE TRES TIPOS.
                #
                # `SIN_TIPO` = `StructProperty` y `ArrayProperty`, que no se
                # pueden tipar desde la tabla de exportaciones. Pero SI desde el
                # `FPropertyTag`, y eso es lo que trae `DE_QUE_STRUCT`.
                #
                # `?array?` es un array cuyo tipo de elemento la sonda no lee:
                # se queda como incognita, y el tipo entero sin declarar.
                destino = DE_QUE_STRUCT.get((dueno, nombre))
                if not destino or destino == "?array?":
                    sin_tipar.setdefault(dueno, []).append(nombre)
                elif genero == "ArrayProperty":
                    miembros.setdefault(dueno, []).append(
                        (nombre, "array<" + destino + ">"))
                else:
                    miembros.setdefault(dueno, []).append((nombre, destino))
                continue
            t = PROPIEDAD_A_TIPO.get(genero)
            if t:
                miembros.setdefault(dueno, []).append((nombre, t))


def ancestros(clase):
    """Los nombres de los que `clase` hereda, subiendo por `PADRES`."""
    vistos, x = set(), PADRES.get(clase, "")
    for _ in range(64):
        if not x or x in vistos:
            break
        vistos.add(x)
        x = PADRES.get(x, "")
    return vistos


def consts():
    """
    Clase -> {nombre de const: valor literal}, leido de la exportacion.

    Hace falta porque el valor que hay que poner NO esta en el fichero que lo
    usa: esta en la clase que se lo presta. Sin este mapa la sustitucion no se
    puede hacer, y la alternativa --dejar la linea-- para el compilador.

    Las claves van en minusculas, y no es cosmetico: el guion escribe
    `class'Yakalayer'` donde el fichero se llama `YakaLayer.uc`. El motor compara
    nombres de FName sin distinguir mayusculas, asi que `class'Yakalayer'`
    resuelve; un diccionario de Python, no.
    """
    m = {}
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8", errors="replace").read()
        vals = {n: v for n, v in DECLARA_CONST.findall(t.lstrip(chr(0xFEFF)))}
        if vals:
            m[f[:-3].lower()] = vals
    return m

# NOMBRES QUE EL MOTOR OCUPA Y NO ESTAN EN NINGUN REGISTRO.
#
# `StaticMesh` no tiene `.uc` --igual que `Class`-- y tampoco esta en
# `UnNames.h` ni en `EngineNames.h`. Su existencia la dice la unica fuente que
# queda: el propio motor, al compilar.
#
#     Warning, Duplicate class name: StaticMesh also exists in package Engine
#
# Esa advertencia ES la respuesta autorizada a la pregunta que este filtro
# intenta responder, y el motor la emite para TODOS los choques en una sola
# pasada. Se regenera asi:
#
#     grep "Duplicate class name" ue-CodeRedModding/DemoGame/Logs/Launch.log
SOMBREAN_AL_MOTOR = {
    "StaticMesh",
}


def reescribe_paquete(texto):
    """
    `CrimeCraft.X` -> `CrimeCraftStubs.X`. Devuelve (texto, cuantas).

    EL PROBLEMA, MEDIDO
    -------------------
    Los stubs se reconstruyeron desde la exportacion del juego, y el codigo del
    juego nombra sus propias clases por el paquete DONDE VIVIAN:

        foreach WorldInfo.AllControllers(Class'CrimeCraft.CCPVPBot2', bot)

    Pero la reconstruccion vive en `CrimeCraftStubs`, y `CrimeCraft` --el `.u`
    del juego-- **no es `EditPackage`**: no se compila. El compilador no
    encuentra la clase, y de ahi sale la cadena que tumbaba la compilacion:

        Unresolved class for 'class' expression
        Type mismatch in Call to 'Multiply_MatrixMatrix', parameter 1
        Call to 'Multiply_MatrixMatrix': missing or bad parameter 2
        Critical: Assertion failed: It->PropertyFlags & CPF_OptionalParm

    **La clase no falta: existe como stub. Lo que apunta mal es el PAQUETE.**

    MEDIDO SOBRE LOS 742 STUBS
    --------------------------
        Class'CrimeCraft.X'        5033     (450 clases distintas)
        Enum'CrimeCraft.X.Y'         14     (un enum anidado)
        class=CrimeCraft.X            7     (`begin object`, SIN comillas)
        ----
        De esas, **4286 apuntan a una clase que SI tiene stub**: son las que
        esto arregla. Las otras **781 apuntan a una clase que NO se genero**
        (167 clases: `CCSharedNames`, `CCNotificationSystem`, `CCSNDMessage`...).
        Eso NO se arregla aqui y no se disimula: es un hueco de cobertura, otra
        causa, y necesita que la clausura traiga esas clases. Se deja medido y
        aparte.

    POR QUE NO ES UN `replace`, que es lo que parece
    ------------------------------------------------
    Porque `CrimeCraft` aparece en sitios donde NO es un paquete, y los cuatro
    estan medidos sobre estos mismos ficheros:

        CrimeCraftFootSteps                           una CLASE que se llama asi
        CrimeCraft_Logo                               una VARIABLE
        "CrimeCraftAnimations.Male.AnimTree_Lobby"    otro paquete
        "<Strings:CrimeCraft.Bots.PlayerName_0>"      una clave de LOCALIZACION

    La ultima es la que muerde: **va dentro de una CADENA**, y ahi
    `CrimeCraft.Bots` no es una clase --`Bots` NO existe-- sino la seccion de un
    `.int`. Un `replace` la habria reescrito y el diff habria enseñado una linea
    de mas. De ahi que se enmascaren cadenas y comentarios. (La primera y la
    segunda no llevan punto detras, asi que caen solas; la tercera no casa
    porque tras `CrimeCraft` viene `A`, no `.`.)

    Y **NO se enmascaran las comillas simples**: `Class'...'` va dentro de ellas.
    En UnrealScript la comilla simple no abre una cadena --abre un literal de
    objeto o de nombre-- y el paquete que hay que reescribir vive justo ahi.
    """
    aguja = PAQUETE_VIEJO + "."
    salida, i, n, cuenta = [], 0, len(texto), 0
    while i < n:
        ch = texto[i]
        if ch == '"':
            # Cadena: se copia ENTERA y sin mirar dentro.
            j = i + 1
            while j < n:
                if texto[j] == "\\":
                    j += 2
                    continue
                if texto[j] == '"':
                    j += 1
                    break
                j += 1
            salida.append(texto[i:j])
            i = j
        elif ch == "/" and i + 1 < n and texto[i + 1] == "/":
            j = texto.find("\n", i)
            j = n if j < 0 else j
            salida.append(texto[i:j])
            i = j
        elif ch == "/" and i + 1 < n and texto[i + 1] == "*":
            j = texto.find("*/", i + 2)
            j = n if j < 0 else j + 2
            salida.append(texto[i:j])
            i = j
        elif (texto.startswith(aguja, i) and i > 0
              and not (texto[i - 1].isalnum() or texto[i - 1] in "_.")):
            # El token suelto, seguido de punto. Se excluye lo que NO es el
            # paquete: `CCCrimeCraft.` (letra delante, que no es el caso pero
            # seria el mismo defecto) y `Algo.CrimeCraft.` (punto delante, que
            # seria una CLASE llamada CrimeCraft dentro de otro paquete).
            salida.append(PAQUETE_NUEVO + ".")
            cuenta += 1
            i += len(aguja)
        else:
            salida.append(ch)
            i += 1
    return "".join(salida), cuenta


# =====================================================================
# LOS CASTS A `int` QUE EL DESCOMPILADOR ANADIO, Y QUE EL COMPILADOR RECHAZA
#
# El pase 2 dice, por cada uno:
#
#     No need to cast 'IntProperty' to itself
#     Bad or missing expression after '==': 'int'
#
# Y es un artefacto de la extraccion: el original era `X == 4`, y UELib escribio
# `int(X) == int(4)` porque en el bytecode la comparacion es entre un `EX_IntConst`
# y la propiedad. **Quitar el cast restaura fidelidad ademas de compilar.**
#
# MEDIDO SOBRE LOS 969 STUBS, antes de escribir esto:
#
#     2.244 sitios con la forma `int(A) <op> int(B)` en 280 ficheros
#      1.472 de ellos con A declarado ENTERO/ENUM/BYTE/BOOL   -> el cast SOBRA
#        331 mixtos (el nombre se declara de varias formas)  -> NO se tocan
#        301 sin tipo conocido                              -> NO se tocan
#        102 llamadas (`int(GetTeamNum())`)                  -> necesitan la firma
#         38 FLOAT                                           -> NO SE TOCAN
#
# > LAS 38 DE `float` SON LA RAZON DE QUE ESTO NO SEA UN `replace`.
# > `int(X) == int(0)` con X flotante significa "truncar X y comparar con 0";
# > `X == 0` es OTRA COSA. Un `replace` habria cambiado el programa en silencio,
# > y compilando.
#
# Solo se quita, pues, cuando el INDICE dice que el argumento ya es entero. Lo
# que no se sabe, se deja: un cast de mas da un error con nombre y linea -- que
# es el instrumento -- y uno de menos da un numero equivocado que compila.
TIPOS_DE_NOMBRE = {}
NOMBRES_DE_ENUM = set()
# `"enum"` VA AQUI, y su ausencia costo 2323 sitios.
#
# El indice guarda la CADENA `"enum"` como tipo de lo declarado con
# `var enum ENetMode { ... } NetMode;` -- el enum con cuerpo, con el nombre de la
# variable detras de la llave. La primera version de `CAST_ENTERO` no la tenia, y
# como `"enum"` no es el nombre de ningun enum tampoco caia por `NOMBRES_DE_ENUM`:
# **los sitios de `NetMode` y compania se quedaban fuera sin decir nada.**
#
# Y un enum ES un entero -- se almacena en un byte --, asi que quitarlo es
# correcto. La prueba de que hacia falta: `'X' conversion: Bad or missing
# expression` es la familia MAYOR de las 534, con 131.
CAST_ENTERO = {"int", "byte", "bool", "enum"}
CAST_FLOTANTE = {"float"}
ID_PUNTEADO = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
CAST_INT = re.compile(r"\bint\s*\(")


def indexa_tipos_para_casts():
    """
    nombre -> conjunto de tipos con los que se declara, en la EXPORTACION y el SDK.

    SE LEE DE `ORIGEN` Y NO DE `DESTINO`, y no es un detalle: `DESTINO` se esta
    reescribiendo mientras el bucle corre, asi que un indice leido de ahi
    dependeria del ORDEN en que se hubieran procesado las clases. El resultado
    seria distinto en cada pasada.
    """
    if TIPOS_DE_NOMBRE:
        return
    for base in (ORIGEN, SDK):
        for dirp, _, fs in os.walk(base):
            if base == SDK and os.path.abspath(dirp).startswith(os.path.abspath(DESTINO)):
                continue
            for f in fs:
                if not f.endswith(".uc"):
                    continue
                t = io.open(os.path.join(dirp, f), encoding="utf-8",
                            errors="replace").read()
                # UNA DECLARACION, TODOS SUS NOMBRES -- y el tipo, por
                # `tipo_de_var()`, que YA existe y resuelve la categoria
                # `var(X)`, los modificadores y los genericos.
                #
                # La version anterior llevaba su propia expresion y capturaba
                # solo los DOS ULTIMOS identificadores antes del `;`. En
                #
                #     local float Dmg, AbilityDmgMultiplier, DamageRes;
                #
                # eso deja fuera a `Dmg` -- y el diff lo cazo: a `int(Dmg)`, en
                # OTRA clase, se le quito el cast porque el indice no sabia que
                # `Dmg` es float. **Declarar varias variables de una vez es lo
                # normal en este codigo**, asi que el hueco no era de un caso.
                for m in re.finditer(r"(?m)^[^\S\n]*(?:var|local)\b[^;\n]*;", t):
                    decl = m.group(0)
                    tipos_d = tipo_de_var(decl) or []
                    if not tipos_d:
                        continue
                    # Los genericos fuera, o `array<X>` mete `X` como nombre.
                    cuerpo = re.sub(r"<[^>]*>", "", decl)
                    for x in re.finditer(r"[A-Za-z_]\w*", cuerpo):
                        nom = x.group(0)
                        if (nom in ("var", "local") or nom in MODIFICADORES
                                or nom in tipos_d):
                            continue
                        TIPOS_DE_NOMBRE.setdefault(nom, set()).update(
                            q.lower() for q in tipos_d)
                # `var enum ENetMode { ... } NetMode;` -- EL CUERPO DEL ENUM EN
                # MEDIO, y el nombre de la variable DESPUES de la llave. Un
                # patron de una linea no lo ve: asi se escapaba `NetMode`, que
                # son 197 de los 2.244 sitios y es un enum de `WorldInfo`.
                for m in re.finditer(r"\bvar\s+enum\s+[A-Za-z_]\w*\s*\{[^}]*\}\s*"
                                     r"([A-Za-z_]\w*)\s*;", t, re.S):
                    TIPOS_DE_NOMBRE.setdefault(m.group(1), set()).add("enum")
                for m in re.finditer(r"\bvar\s+enum\s+[A-Za-z_]\w*\s+"
                                     r"([A-Za-z_]\w*)\s*;", t):
                    TIPOS_DE_NOMBRE.setdefault(m.group(1), set()).add("enum")
                # `local` YA ESTA CUBIERTO ARRIBA, en el mismo patron `(?:var|local)`.
                # Estaba aparte, con su propia expresion, y esa es la razon de que
                # `local float Count;` se escapara mientras `var` si se veia:
                # **dos verdades para lo mismo, y una peor que la otra.** Es el
                # mismo defecto que las dos listas de `DrawActorOverlays`.
                #
                # Los parametros: `function T Foo(Type Name, Type Name2)`.
                for m in re.finditer(r"(?m)^[^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*"
                                     r"(?:function|event|operator|delegate)\b[^\n]*?"
                                     r"\(([^)]*)\)", t):
                    for par in re.finditer(r"([A-Za-z_]\w*)[ \t]+([A-Za-z_]\w*)"
                                           r"[ \t]*(?:,|$)", m.group(1)):
                        tipo, nombre = par.group(1), par.group(2)
                        if tipo not in ("optional", "out", "const", "coerce"):
                            TIPOS_DE_NOMBRE.setdefault(nombre, set()).add(tipo.lower())
                # Y los NOMBRES de enum, que son tipos: `eactionrole` no dice
                # "enum" en ningun sitio, es el nombre del enum.
                for m in re.finditer(r"(?m)^[^\S\n]*(?:enum|struct)\s+"
                                     r"([A-Za-z_]\w*)", t):
                    NOMBRES_DE_ENUM.add(m.group(1).lower())


def mascara_de_codigo(texto):
    """
    Una etiqueta por caracter: 'c' codigo, 's' cadena, 'k' comentario.

    `reescribe_paquete()` recorre a mano por su cuenta y no usa esto, porque
    aquel CONSTRUYE la salida mientras recorre y este solo necesita saber DONDE
    se puede escribir. Son dos formas distintas del mismo cuidado.
    """
    m, i, n, est = [], 0, len(texto), "c"
    while i < n:
        ch = texto[i]
        if est == "c":
            if ch == '"':
                est = "s"; m.append("s"); i += 1
            elif ch == "/" and i + 1 < n and texto[i + 1] == "/":
                est = "k"; m.append("k"); i += 1
            elif ch == "/" and i + 1 < n and texto[i + 1] == "*":
                est = "k"; m.append("k"); i += 1
            else:
                m.append("c"); i += 1
        elif est == "s":
            if ch == "\\" and i + 1 < n:
                m.append("s"); m.append("s"); i += 2
            elif ch == '"':
                est = "c"; m.append("s"); i += 1
            else:
                m.append("s"); i += 1
        else:
            if ch == "*" and i + 1 < n and texto[i + 1] == "/":
                m.append("k"); m.append("k"); i += 2; est = "c"
            elif ch == "\n":
                m.append("k"); i += 1; est = "c"
            else:
                m.append("k"); i += 1
    return m


def el_cast_sobra(arg):
    """
    (si, motivo) sobre si `int(<arg>)` se puede quitar.

    LO CONSERVADOR ES NO QUITAR. Un cast de mas da un error de pase 2 con nombre
    y linea, que es el instrumento que este proyecto usa para todo; uno de menos
    da un numero equivocado que compila y no se nota hasta que algo se comporta
    mal.
    """
    if re.fullmatch(r"-?\d+", arg):
        return True, "literal entero"
    if "(" in arg:
        # Una llamada o una expresion: el tipo de retorno esta en la firma, y
        # aqui no se resuelve. Se deja.
        return False, "llamada o expresion"
    if not ID_PUNTEADO.fullmatch(arg):
        return False, "no es un nombre"
    ult = arg.split(".")[-1]
    ts = TIPOS_DE_NOMBRE.get(ult)
    if not ts:
        return False, "sin tipo conocido"
    if ts & CAST_FLOTANTE:
        return False, "float (el cast HACE FALLO)"
    if all(x in CAST_ENTERO or x in NOMBRES_DE_ENUM for x in ts):
        return True, "entero/enum/byte/bool"
    return False, "tipo mixto o no entero"


def quita_casts_int(texto):
    """(texto, cuantas, motivos_de_los_que_se_dejan)."""
    indexa_tipos_para_casts()
    mascara = mascara_de_codigo(texto)
    fuera, dejados = [], {}
    i, n = 0, len(texto)
    while True:
        m = CAST_INT.search(texto, i)
        if not m:
            break
        # El argumento, contando parentesis: `int(Foo(A, B))` no corta en el
        # primero que aparece.
        prof, j = 1, m.end()
        while j < n and prof:
            if texto[j] == "(":
                prof += 1
            elif texto[j] == ")":
                prof -= 1
            j += 1
        if prof:
            break
        if mascara[m.start()] != "c":
            i = j
            continue
        bruto = texto[m.end():j - 1]
        arg = bruto.strip()
        ok, motivo = el_cast_sobra(arg)
        if ok:
            fuera.append((m.start(), j, arg))
        else:
            dejados[motivo] = dejados.get(motivo, 0) + 1
        i = j
    for ini, fin, nuevo in sorted(fuera, reverse=True):
        texto = texto[:ini] + nuevo + texto[fin:]
    return texto, len(fuera), dejados


def parentiza_preoperador(texto):
    """
    `!X ~= Y` -> `!(X ~= Y)`. Devuelve (texto, cuantas, dejados).

    EL BUG DE UELib, Y POR QUE YA NO ES ADIVINAR
    --------------------------------------------
    `DecompilePreOperator` (`FunctionTokens.cs:71`) **no usa `PrecedenceToken`**
    --los binarios si-- asi que `!(A ~= B)` se imprime `!A ~= B`: **precedencia
    rota**. Los sitios tienen nombre y linea desde hace tandas.

    Y ESTA TARDA SE SUPO ALGO MAS: **no era solo un error de compilacion, era lo
    que disparaba el SIGSEGV.** Medido con un parche a mano en un fichero:

        con `!InLastRestoreTime ~= 0.0000000`  ->  muere en AnimNodeRecoilAlgorithmic
        con `!(InLastRestoreTime ~= 0.0000000)` ->  pasa de largo hasta CCA*

    Una tanda anterior descarto arreglarlo por texto -- *"seria adivinar"* -- y
    **tenia razon con el criterio que tenia entonces**: `!A && B` y `!(A && B)`
    son el mismo texto, y `!X == Y` es valido con las dos lecturas.

    LO QUE FALTABA ERA EL TIPO DEL OPERANDO, y ahora esta indexado:

      - `~=` es comparacion de FLOATS. `!X ~= Y` con X float seria `!float`, que
        no existe -- luego el `!` tiene que cubrir la comparacion. **Determinado.**
      - `< > <= >=` son numericos. `!X > Y` con X no-booleano, igual.
      - `==` y `!=` **NO SE TOCAN**: `(!BoolX) == BoolY` es valido y es la otra
        lectura. Ahi si seria adivinar, y ahi no se escribe.

    Solo se toca, pues, cuando el tipo del operando **se conoce y NO es bool**. Lo
    que no se sabe, se deja -- y se cuenta, para que el numero diga si la regla
    esta acertando o simplemente no esta llegando.

    MEDIDO sobre la exportacion: 16 sitios, `~=` 10 y `>` 6.
    """
    indexa_tipos_para_casts()
    mascara = mascara_de_codigo(texto)
    fuera, dejados = [], {}
    for m in re.finditer(r"!\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*"
                         r"(~=|<|>|<=|>=)", texto):
        if mascara[m.start()] != "c":
            continue
        nombre = m.group(1)
        ult = nombre.split(".")[-1]
        ts = TIPOS_DE_NOMBRE.get(ult)
        if not ts:
            dejados["sin tipo conocido"] = dejados.get("sin tipo conocido", 0) + 1
            continue
        if "bool" in ts:
            dejados["bool (las dos lecturas valen)"] = \
                dejados.get("bool (las dos lecturas valen)", 0) + 1
            continue
        # Y EL FINAL DE LA COMPARACION: se para en lo que cierra o separa la
        # expresion QUE LA CONTIENE -- `)` y `,` de fuera, `;`, y los `&&`/`||`,
        # que ligan mas flojo que la comparacion.
        j, prof, n = m.end(2), 0, len(texto)
        while j < n:
            ch = texto[j]
            if ch == "(":
                prof += 1
            elif ch == ")":
                if prof == 0:
                    break
                prof -= 1
            elif prof == 0 and ch in ",;&|\n":
                break
            j += 1
        fuera.append((m.start(), j, "!(" + texto[m.start(1):j].rstrip() + ")"))
    for ini, fin, nuevo in sorted(fuera, reverse=True):
        texto = texto[:ini] + nuevo + texto[fin:]
    return texto, len(fuera), dejados


def arregla_goto_foreach(texto):
    """
    `goto L;` dentro de un `foreach` con la etiqueta FUERA -> `continue;` o `break;`.

    Devuelve (texto, cuantos, desglose).

    LA REGLA DEL COMPILADOR, leida y no supuesta
    --------------------------------------------
    `UnScrCom.cpp:11817` (el `goto`) y `:11918` (la etiqueta) tienen EL MISMO bucle:

        for( iNest=NestLevel-1; iNest>=2; iNest-- )
            if( Nest[iNest].NestType==NEST_State
             || Nest[iNest].NestType==NEST_Function
             || Nest[iNest].NestType==NEST_ForEach )
                break;

    Ni el `goto` ni su etiqueta se ligan al bloque `{}` inmediato: **suben hasta el
    primer `State`, `Function` o `ForEach`**. Y `ForEach` CORTA la busqueda -- asi
    que un `goto` dentro del bucle y su etiqueta fuera caen en DOS listas de
    etiquetas, y sale `Label 'X' not found in this block of code`.

    LO QUE NO SERVIA, y costo un rato
    ---------------------------------
    Contar etiquetas **por fichero** da CERO problemas: las 2.192 de los 969 stubs
    existen. El problema es de AMBITO. Y no es "cruzar un bloque `{}`": es
    especificamente el `foreach`, porque es el unico de los tres que aparece dentro
    de un cuerpo de funcion.

    LA MEDIDA, y por que se elige `continue`
    ----------------------------------------
    **25 sitios en 14 clases**, y los 25 con LA MISMA forma: la etiqueta pegada al
    cierre del `foreach`. Ninguno con un `switch` en medio ni con otro bucle.

    Y de esos 25, **15 llevan la marca `// [Explicit Continue]`** que deja el
    descompilador. Esa marca es el dato: de los **374** `[Explicit Continue]` del
    paquete, **350 estan BIEN colocados** --etiqueta dentro del bucle, mismo
    ambito-- y **15 no**. O sea que **UELib sabe colocar esa etiqueta y en 15 casos
    no**: es un fallo de COLOCACION suyo, no una intencion del juego.

    Se escribe `continue` donde la marca lo dice, y `break` donde no la hay --los
    10 restantes, cuya etiqueta esta tras el cierre, o sea salir del bucle--.

    NO ES ADIVINAR: se esta reescribiendo a la instruccion que el propio
    descompilador dice que habia. Y en los dos casos se BORRA la etiqueta, que se
    queda huerfana.
    """
    # Los tramos de cuerpo de cada `foreach`, con llaves equilibradas.
    tramos = []
    for m in re.finditer(r"\bforeach\b", texto):
        j = texto.find("{", m.end())
        if j < 0:
            continue
        prof, k = 1, j + 1
        while k < len(texto) and prof:
            if texto[k] == "{":
                prof += 1
            elif texto[k] == "}":
                prof -= 1
            k += 1
        tramos.append((j, k))

    def ambito(pos):
        mejor = None
        for a, b in tramos:
            if a <= pos < b and (mejor is None or (a, b) < mejor):
                mejor = (a, b)
        return mejor

    # Las etiquetas -- `J0xNN:` a principio de linea.
    etiquetas = {}
    for m in re.finditer(r"(?m)^[ \t]*([A-Za-z_]\w*):[ \t]*(?=\r?$)", texto):
        etiquetas.setdefault(m.group(1), []).append(m)

    sustituciones = []          # (ini, fin, nuevo)
    usadas = collections.Counter()
    desglose = {"continue": 0, "break": 0}
    for m in re.finditer(r"\bgoto\s+([A-Za-z_]\w*)\s*;", texto):
        nombre = m.group(1)
        sitios = etiquetas.get(nombre)
        if not sitios:
            continue
        ag = ambito(m.start())
        if ag is None:
            continue
        if any(ambito(s.start()) == ag for s in sitios):
            continue                      # hay una etiqueta en el mismo ambito: vale
        # La etiqueta tiene que estar PEGADA al cierre del foreach, o no se toca.
        a, b = ag
        pegada = [s for s in sitios if 0 <= s.start() - b < 40]
        if not pegada:
            continue
        # No se toca si hay un `switch` por medio: `break` saldria del `switch`.
        if re.search(r"\bswitch\b", texto[m.end():b]):
            continue
        # La marca del descompilador, en la linea anterior.
        previa = texto[:m.start()].rstrip().split("\n")[-1]
        marca = "continue" if "[Explicit Continue]" in previa else "break"
        sustituciones.append((m.start(), m.end(), marca + ";"))
        desglose[marca] += 1
        for s in pegada:
            usadas[nombre] += 1

    if not sustituciones:
        return texto, 0, desglose

    # Las etiquetas que se quedan sin nadie: fuera.
    #
    # SE CUENTAN LOS `goto` QUE QUEDAN, NO LOS QUE HABIA. La primera version
    # contaba sobre el texto SIN sustituir, asi que el `goto` que se acaba de
    # reescribir se contaba a si mismo, `quedan` nunca valia 0, y **la etiqueta
    # se quedaba huerfana en los 25 sitios**. Se vio en el diff instrumentado: el
    # cambio era de UNA linea por fichero en vez de dos.
    reemplazados = {(s[0], s[1]) for s in sustituciones}
    quedan = collections.Counter()
    for m in re.finditer(r"\bgoto\s+([A-Za-z_]\w*)\s*;", texto):
        if (m.start(), m.end()) not in reemplazados:
            quedan[m.group(1)] += 1
    for nombre in usadas:
        if quedan.get(nombre, 0) == 0:
            for s in etiquetas.get(nombre, []):
                # Hasta el final de la linea, y el salto si lo lleva.
                fin = texto.find("\n", s.end())
                fin = len(texto) if fin < 0 else fin + 1
                sustituciones.append((s.start(), fin, ""))

    for ini, fin, nuevo in sorted(sustituciones, reverse=True):
        texto = texto[:ini] + nuevo + texto[fin:]
    return texto, len([s for s in sustituciones if s[2].endswith(";")]), desglose


def adapta(texto, clase=None):
    """Devuelve (texto_adaptado, lista_de_avisos)."""
    # `cualifica()` necesita saber en que clase esta trabajando y que declara
    # ella misma, y se llama desde `recualifica()`, que es libre. Se pasan por
    # global en vez de por parametro porque son estado del fichero que se esta
    # procesando, no del algoritmo.
    global CLASE_ACTUAL, DECLARADOS_AQUI
    avisos = []

    # La declaracion adelantada suelta se sustituye por una declaracion de
    # verdad. Ver RECONSTRUIDAS para el porque de cada superclase.
    # `lstrip` y NO `strip`, y con el BOM entre los caracteres a quitar. El
    # motivo es que la retirada del BOM ocurre mas abajo, asi que aqui el texto
    # todavia lo lleva, y un BOM delante de `class` hace que la expresion no
    # case. Es la TERCERA vez en la misma sesion que ese byte muerde igual: no
    # es un caracter invisible, es un byte mas, y todo lo que ancla al principio
    # del fichero --`^` de una expresion, el `head -c3` de un grep-- lo ve.
    m = SOLO_ADELANTADA.match(texto.lstrip("﻿ \t\r\n"))
    # `SON_INTERFACES` es la lista a mano -- la de las que NO tienen fuente que las
    # delate -- y `ES_INTERFAZ` es la derivada. Hay que mirar LAS DOS: si solo se
    # mira la primera, una declaracion adelantada que el guion implementa sigue
    # saliendo como clase, y da `Implements: Class X is not an interface`.
    if m and m.group(1) in (SON_INTERFACES | ES_INTERFAZ):
        # INTERFACE, no clase. Ver SON_INTERFACES: el guion la usa en
        # `implements()`, y una clase ahi da `Implements: Class X is not an
        # interface`, que es un mensaje distinto y apunta a otro sitio.
        avisos.append('declaracion adelantada -> interface (RECONSTRUIDO)')
        texto = 'interface ' + m.group(1) + chr(10) + chr(9) + 'native;' + chr(10)
    elif m:
        # CUALQUIER declaracion adelantada se reconstruye, SIN LISTA.
        #
        # Antes habia que anadir cada una a mano a RECONSTRUIDAS, y por eso
        # aparecian de una en una, vuelta tras vuelta: se encuentran cuando el
        # compilador las nombra. Pero el caso es SIEMPRE el mismo -- un fichero
        # con `class X;` y nada mas -- y la decision tambien.
        #
        # LA BASE SE ELIGE POR REGLA, no por juicio: las del sistema de UI del
        # juego cuelgan de `UIObject`, que es la raiz que SI existe en el SDK
        # (`class UIRoot extends Object`), y el resto de `Object`. Es una
        # suposicion, y esta dicha: si el motor se queja de un miembro que falta
        # en alguna, el sitio es RECONSTRUIDAS, que sigue mandando.
        base = RECONSTRUIDAS.get(m.group(1),
                                 "UIObject" if m.group(1).startswith("UI") else "Object")
        avisos.append(f"declaracion adelantada -> native extends {base} (RECONSTRUIDO)")
        texto = ("class " + m.group(1) + " extends " + base + chr(10) + chr(9) + "native;" + chr(10))
        if m.group(1) in (SON_INTERFACES | ES_INTERFAZ):
            # SIN `native`, y es la diferencia entre poder implementarla o no.
            #
            # Una interfaz `native` solo la pueden implementar clases `native`:
            #
            #     Non-native classes not allowed to implement native interfaces
            #
            # Y ese `native` LO PUSO ESTE SCRIPT, copiando el estilo del SDK. El
            # fuente no lo dice. Quitarlo no quita nada: el SDK declara
            # interfaces de las dos formas -- una con `native` y otra sin el,
            # `interface Otra;` -- y las de aqui no tienen cuerpo que implementar
            # en C++.
            texto = "interface " + m.group(1) + ";" + chr(10)
    elif False:
        base = RECONSTRUIDAS[m.group(1)]
        avisos.append(f"declaracion adelantada -> native extends {base} (RECONSTRUIDO)")
        # `native`, y no es un adorno: una clase SIN NINGUN cuerpo de guion es
        # exactamente una clase que solo vivia en C++. Se puso sin el en la
        # primera version y el compilador lo dijo con precision --
        # `CCActorMarkingComponent : Native classes cannot expand non-native
        # classes`-- porque quien hereda de ellas si es nativa.
        texto = f"class {m.group(1)} extends {base}\n\tnative;\n"
    elif m:
        avisos.append(f"OJO: declaracion adelantada sin superclase conocida ({m.group(1)})")

    # EL BOM, fuera. UE Explorer lo escribe al principio de cada .uc que exporta,
    # y ninguno de los 1.990 `.uc` del SDK lo lleva. No es cosmetico: el
    # compilador de guion tokeniza el fichero por bytes, y un EF BB BF delante de
    # `class` hace que el primer token sea "﻿class" y no `class`.
    #
    # Se quita aqui y no en el fichero exportado, para que la exportacion siga
    # siendo lo que el descompilador emitio.
    if texto.startswith("﻿"):
        texto = texto[1:]
        avisos.append("BOM retirado")

    # `native` SE CONSERVA. Es la opcion fiel: la clase sigue siendo nativa, como
    # en el juego, y su comportamiento vive en C++ -- que es lo que el proyecto
    # ya hace en Stubs.cpp con implementaciones vacias.
    #
    # La alternativa era quitarlo y dar a cada funcion un cuerpo vacio. Se
    # descarto: es menos fiel, y sobre todo obliga a inventar un cuerpo para
    # funciones que en el juego no tenian guion.
    if re.search(r"^\s*native\b", texto, re.M):
        avisos.append("`native` conservado (opcion fiel)")
    else:
        avisos.append("la clase NO era native")

    # Las funciones nativas son lo que la mitad en C++ tiene que implementar.
    # Se cuentan, porque son el tamano real del trabajo.
    nat = len(re.findall(r"^\s*native\b[^\n]*\bfunction\b|\bfunction\b[^\n]*\bnative\b",
                         texto, re.M))
    if nat:
        avisos.append(f"**{nat} funciones nativas** que implementar en C++")

    # UNA CLASE QUE HEREDA DE UNA INTERFAZ **ES** UNA INTERFAZ.
    #
    # El descompilador escribio `class` donde iba `interface`, y el compilador lo
    # dice con precision -- pero solo cuando alguien la usa:
    #
    #     Class 'RadarPresentInterface_Placable' cannot extend interface
    #     'RadarPresentInterface', use 'implements'
    #     Implements: Class RadarPresentInterface_Placable is not an interface
    #
    # Se convierte AQUI, antes de la normalizacion de abajo, para que despues
    # caiga por el mismo camino que las demas interfaces y no haga falta un
    # segundo juego de reglas.
    m_cls = re.match(r"\s*class\s+([A-Za-z_]\w*)(\s+extends\s+([A-Za-z_]\w*))?", texto)
    if m_cls and m_cls.group(3) in ES_INTERFAZ:
        avisos.append(f"**era `class` y es `interface`**: hereda de {m_cls.group(3)}")
        texto = re.sub(r"^(\s*)class(\s+)", chr(92) + "1interface" + chr(92) + "2",
                       texto, count=1)

    # ADOPTAR LA FIRMA DEL PADRE.
    #
    # El compilador exige que una redefinicion COINCIDA:
    #
    #     Redefinition of 'function Init' differs from original;
    #     different number of parameters
    #
    # Y la del padre esta en el fuente del SDK, que tenemos. Aqui se adopta.
    #
    # NO ES UN TRUCO, y el motivo importa: **una firma de funcion no es
    # layout**. El tamano y los desplazamientos de una clase los fijan sus
    # PROPIEDADES; cambiar la firma de un metodo no mueve un byte de la clase y
    # el verificador de layouts del motor no la mira. Lo que si seria un truco es
    # borrar la funcion o renombrarla: eso pierde informacion y esconde el
    # problema.
    #
    # LA GUARDA, que es lo que la hace segura: si el cuerpo declara un `local`
    # que se llama como un parametro del padre, NO se toca. Ahi el local ES el
    # parametro --el descompilador no pudo recuperar la firma y los dejo como
    # variables-- y anadir el parametro chocaria con el:
    #
    #     'ViewRotation' already defined
    #
    # Ese caso pide PROMOVER el local, que es otra transformacion, y son uno de
    # diez. Se deja sin tocar y el compilador lo sigue diciendo.
    # >>> DESACTIVADO. Se probo, se midio, y SALE PEOR: 51 -> 53, y la familia
    # que iba a cerrar --`different number of parameters`, 6 errores-- NO se
    # cierra. Ademas VOLVIERON seis errores de `native` que estaban cerrados:
    # `Native classes cannot expand non-native` (3) y `Non-native classes not
    # allowed to implement native interfaces` (3).
    #
    # Asi que adopta firmas, no arregla lo que dice arreglar, y rompe otra cosa
    # por el camino. Se deja el CODIGO, porque funciona y esta probado, pero
    # apagado: hace falta entender por que antes de encenderlo.
    # =====================================================================
    # LAS CUATRO FIRMAS QUE NO COINCIDEN CON SU PADRE DEL SDK, CASO POR CASO
    #
    # El compilador exige que una redefinicion COINCIDA con la del padre, y la
    # del padre la tenemos: esta en el fuente del SDK. Aplicarlo EN GENERAL se
    # probo y sale peor -- 51 -> 53 -- porque dispara en cientos de funciones a
    # las que el compilador no les dice nada. Asi que van UNA A UNA, con su
    # motivo y con su medicion.
    #
    # Los cuatro son la misma forma de fondo: **el juego compilo contra el build
    # 4701 y nuestro SDK es 10897**, asi que el stub es mas fiel que el padre en
    # unos casos y menos en otros. Lo que decide no es la fidelidad: es que el
    # compilador no admite otra cosa.
    #
    # Y **una firma de funcion NO es layout**: el tamaño y los desplazamientos de
    # una clase los fijan sus PROPIEDADES. Cambiar la firma de un metodo no mueve
    # un byte.
    FINALES_ALINEADAS = {
        # 1. `CCRealm extends YakaLayer`, y los dos son nuestros: salen del
        #    MISMO paquete cocinado. El descompilador escribio `optional int
        #    InSetId = 0` en el hijo y `int InSetId` en el padre.
        #
        #    No hay que elegir cual es "mas fiel": el hijo es el que tiene que
        #    coincidir. Y **todos los llamadores pasan TRES argumentos** --
        #    `UIServiceMenu_JobsVendor.uc:1012` pasa un `0` explicito -- asi que
        #    quitarle el `optional` no rompe ni una llamada.
        ("CCRealm", "DeliverQuest"): {"firma": [(r"optional int InSetId = 0",
                                                 "int InSetId")]},
        # 4. `CCWeapon extends Weapon`, y el TERCER PARAMETRO CAMBIA DE TIPO:
        #
        #        el stub:  optional Object ContextObject
        #        el SDK:   optional int    NumHits
        #
        #    El juego tenia un `Object` ahi; el SDK le puso un `int`. Adoptar la
        #    firma del padre rompe el cuerpo en DOS sitios, y los dos se ven:
        #
        #        ContextObject = PreProcessInstantHit(FiringMode, Impact);
        #        super.ProcessInstantHit(FiringMode, Impact, ContextObject);
        #
        #    Asi que `ContextObject` pasa a ser **local** -- deja de ser el
        #    parametro y sigue existiendo, con el mismo valor que le daba el
        #    descompilador -- y la llamada a `super` pierde el tercer argumento,
        #    que ya no significa lo mismo.
        #
        #    ESTO ES UNA PERDIDA, Y SE DICE: esa llamada pasa de tres argumentos
        #    a dos. El tercero del padre es `optional`, asi que compila; lo que
        #    se pierde es la intencion del original, que no cabe en la firma del
        #    SDK. La alternativa era dejar el error.
        # 5. `CCWeapon.FireAmmunition`: el juego le puso un `float` y el SDK no
        #    tiene ninguno. Es del tipo limpio -- `FireTimeStamp` **solo** se usa
        #    para reenviarlo a `super`, asi que quitar el parametro y el
        #    argumento no pierde nada.
        #
        #    Y `PlayFireEffects`, DE LA MISMA CLASE, **NO SE TOCA**, y se dice:
        #    su cuerpo usa los tres parametros que habria que quitar
        #    (`StartTraceLocation`, `EndTraceLocation`, `AddInfo`) y el padre no
        #    tiene equivalente. Convertirlos en `local` los dejaria a cero y
        #    **la llamada pasaria vectores vacios**: eso no es alinear una firma,
        #    es cambiar lo que el codigo hace. Queda abierto.
        ("CCWeapon", "FireAmmunition"): {
            "firma": [(r"\(float FireTimeStamp\)", "()")],
            "cuerpo": [(r"super\.FireAmmunition\(FireTimeStamp\);",
                        "super.FireAmmunition();")]},
        # 8. `CCInstanceController.ServerMove`: EL MISMO TIPO DE DATO EN DOS
        #    ANCHURAS.
        #
        #        el stub:  float TimeStamp, Vector InAccel, Vector ClientLoc,
        #                  int MoveFlags, byte ClientRoll, int View
        #        el SDK:   ..., byte MoveFlags, byte ClientRoll, int View
        #
        #    `MoveFlags` es `int` en el juego y `byte` en el SDK. Y es del tipo
        #    LIMPIO: se comprobo el cuerpo entero de la funcion, y ahi
        #    `MoveFlags` **solo se reenvia a `super`** -- ni una lectura, ni una
        #    escritura. Cambiar la anchura no pierde nada porque no hay nada que
        #    perder.
        ("CCInstanceController", "ServerMove"): {
            "firma": [(r"ClientLoc, int MoveFlags,", "ClientLoc, byte MoveFlags,")]},
        # 9. `CCInstanceController.Follow`: **LA MISMA CLASE, DOS VECES**.
        #
        #    No es una deriva contra un ancestro -- `Follow` no existe en el SDK;
        #    el grep lo confirma en los dos arboles --, sino contra SI MISMA:
        #
        #        3942    exec function Follow(string pname)               el cuerpo
        #        14534   exec function Follow(optional string pname)     en `state
        #                                                                Spectating`
        #
        #    Y el compilador lo dice tal cual: `'optional' mismatch on parameter
        #    1`. **Es la razon por la que `mide-deriva.py` no lo veia**: su tabla
        #    es de ANCESTROS, y aqui el original esta en el mismo fichero.
        #
        #    SE ANADE `optional` A LA DE LA CLASE, que es la direccion que no
        #    rompe nada: un parametro `optional` sigue aceptando que se le pase
        #    el argumento. Al reves podria romper una llamada sin argumentos, y
        #    ademas `optional` esta ATESTIGUADO en el fuente -- lo lleva la otra
        #    declaracion -- mientras que su ausencia no tiene por que serlo.
        #
        #    Y NO HAY LLAMADORES A QUIEN ROMPER: se buscaron, y los `Follow(` que
        #    salen son `ServerFollow`, `spectator_SwitchFollow` y
        #    `clientSetFollow`, que son otras funciones.
        # 10. `CCSavedMove.CompressedFlags`: MISMA CUENTA, DISTINTO ANCHO.
        #
        #        el stub:  function int  CompressedFlags()
        #        el SDK:   function byte CompressedFlags()
        #
        #     Y AQUI SI HAY UN DATO QUE DECIDE, y es el que hacia dudar: el
        #     cuerpo hace `__NFUN_161__(Result, 256)`, **y 256 NO CABE EN UN
        #     `byte`**. Es la misma deriva de anchura que `MoveFlags`, pero al
        #     reves de comoda.
        #
        #     SE CAMBIA SOLO EL RETORNO, y el `local int Result` SE QUEDA COMO
        #     ESTA. Asi el `256` sigue siendo legal -- vive en un `int`-- y lo
        #     unico que cambia es la conversion al devolver, que es exactamente
        #     donde el SDK la quiere.
        #
        #     Y ADEMAS ALINEA CON LO QUE YA SE HIZO: `ServerMove` recibio
        #     `byte MoveFlags` hace dos tandas, y su llamador es justo este.
        #     O sea que el valor ya iba a acabar en un byte de todas formas.
        # 11. `CCSavedMove.SetFlags`: DOS PARAMETROS DE MAS, Y LOS DOS MUERTOS.
        #
        #        el stub:  static function eDoubleClickDir SetFlags(int Flags,
        #                      out Vector newAccel, out Rotator DeltaRot, PlayerController PC)
        #        el SDK:   static function EDoubleClickDir SetFlags(byte Flags, PlayerController PC)
        #
        #     `PC` SI se usa en la logica, y esta en la firma del SDK: se queda.
        #     Los que sobran son `newAccel` y `DeltaRot`, y se comprobo quien los
        #     usa:
        #
        #       - El UNICO llamador de cuatro argumentos es **el mismo**, en su
        #         `super.SetFlags(Flags, newAccel, DeltaRot, PC)`.
        #       - Y el motor llama con DOS: `PlayerController.uc:3124`,
        #         `SavedMoveClass.static.SetFlags(CompressedFlags, self)`.
        #
        #     Asi que los dos `out` **no los recibe nadie en este motor**. La
        #     unica escritura del cuerpo --`newAccel = vect(0,0,0)`-- pasa a un
        #     local, que es exactamente lo que es: codigo que escribia en un
        #     parametro que aqui no existe.
        # 12. `CCProjectileBase.Init` y `CCProjectile.Init`: 2 contra 1.
        #
        #        el SDK:   `Projectile.uc:110`  native function Init( Vector Direction );
        #        el juego: function Init(Vector Direction, Weapon SourceWeapon)
        #
        #     En `CCProjectileBase` el que sobra **solo se reenvia a `super`**, asi
        #     que se va con la llamada y no queda nada.
        #
        #     En `CCProjectile` SI se usa -- `InitByWeapon(CCWeapon(SourceWeapon))`
        #     -- y por eso pasa a LOCAL. **VALE NONE**, y se dice.
        #
        #     Y LO QUE HACE QUE ESTA PERDIDA NO IMPORTE, que es lo que la vuelve
        #     decision y no apuesta: **`Projectile.Init` es NATIVA**. El C++ llama
        #     a su nativa directamente, sin pasar por el guion, asi que esta
        #     version no la llama el motor. Es la misma pared de E-1, vista desde
        #     el lado bueno: aqui la hace inofensiva.
        ("CCProjectileBase", "Init"): {
            "firma": [(r"Init\(Vector Direction, Weapon SourceWeapon\)",
                       "Init(Vector Direction)")],
            "cuerpo": [(r"super\.Init\(Direction, SourceWeapon\);",
                        "super.Init(Direction);")]},
        ("CCProjectile", "Init"): {
            "firma": [(r"Init\(Vector Direction, Weapon SourceWeapon\)",
                       "Init(Vector Direction)")],
            "cuerpo": [
                (r"(?m)^(function Init\(Vector Direction\)\r?\n\{\r?\n)",
                 r"\1\t// `SourceWeapon` era un parametro del JUEGO; el SDK no lo\n"
                 r"\t// tiene. Vale NONE, y el motor no llama a esta funcion: la del\n"
                 r"\t// SDK es `native` y el C++ va por la suya.\n"
                 r"\tlocal Weapon SourceWeapon;\n"),
                (r"super\.Init\(Direction, SourceWeapon\);", "super.Init(Direction);")]},

        # 13. `CCWeapon.PlayFireEffects`: la BLOQUEADA, y deja de estarlo.
        #
        #        el SDK:  `Weapon.uc:629`  PlayFireEffects(byte FireModeNum, optional vector HitLocation)
        #        el juego: PlayFireEffects(byte FireModeNum, optional Vector StartTraceLocation,
        #                                  optional Vector EndTraceLocation,
        #                                  optional AdditionalHitInfo AddInfo)
        #
        #     **LOS DOS PRIMEROS YA COINCIDEN** -- el nombre del parametro no
        #     cuenta para la comparacion --, asi que lo que sobra son los DOS
        #     ULTIMOS. El proyecto lo tenia por BLOQUEADO porque convertirlos en
        #     local "dejaria la llamada con vectores vacios".
        #
        #     Y ES VERDAD: eso es exactamente lo que pasa. Lo que cambia es que
        #     **dejar el error no es mejor**: el cuerpo no tiene de donde sacar
        #     esos valores, y el SDK no puede nombrar `AdditionalHitInfo` porque
        #     es NUESTRO. Se elige compilar y **se archiva la perdida**.
        ("CCWeapon", "PlayFireEffects"): {
            # LA FORMA ES TOLERANTE A PROPOSITO: la regla general del `AddInfo`
            # corre antes y puede haberlo quitado ya. Se quita lo que quede.
            "firma": [(r"PlayFireEffects\((byte FireModeNum, optional Vector StartTraceLocation)"
                       r", optional Vector EndTraceLocation\)",
                       r"PlayFireEffects(\1)")],
            "cuerpo": [
                (r"(?m)^(simulated function PlayFireEffects\(byte FireModeNum, optional Vector "
                 r"StartTraceLocation\)\r?\n\{\r?\n)",
                 r"\1\t// Los DOS ultimos eran parametros del JUEGO. Valen CERO y el\n"
                 r"\t// reenvio de abajo los pasa vacios. Ver docs/funciones-no-fieles.md.\n"
                 r"\tlocal Vector EndTraceLocation;\n"
                 r"\tlocal AdditionalHitInfo AddInfo;\n")]},

        ("CCSavedMove", "SetFlags"): {
            "firma": [(r"SetFlags\(int Flags, out Vector newAccel, out Rotator DeltaRot, PlayerController PC\)",
                       "SetFlags(byte Flags, PlayerController PC)")],
            "cuerpo": [
                # La unica escritura del cuerpo va a un `out` que aqui no
                # recibe nadie: se RETIRA, que es lo que ya era. Ponerla en un
                # local seria dejar una variable que nadie lee.
                (r"(?m)^[^\S\n]*newAccel = vect\([^)]*\);[ \t]*\r?\n", ""),
                (r"return super\.SetFlags\(Flags, newAccel, DeltaRot, PC\);",
                 "return super.SetFlags(Flags, PC);")]},
        ("CCSavedMove", "CompressedFlags"): {
            "firma": [(r"function int CompressedFlags\(\)",
                       "function byte CompressedFlags()")]},
        # 14. `CCInstancePawn.PlayTakeHitEffects`: **LA MISMA CLASE, DOS VECES**,
        #     como `Follow`. Y por la misma razon `mide-deriva.py` no lo ve: su
        #     tabla es de ANCESTROS y aqui el original esta en el mismo fichero.
        #
        #         7593   simulated function PlayTakeHitEffects(const out TakeHitInfo HitInfo, int NumBullets)
        #         11576  simulated function PlayTakeHitEffects(TakeHitInfo HitInfo, int NumBullets)   <- en un `state`
        #
        #     La bandera `out` esta ATESTIGUADA en la de la clase **y en
        #     `CCTurret.uc:736`**, que es la tercera declaracion del paquete. La
        #     del `state` es la que se sale de la fila.
        #
        #     Se le anade `const out`. **SIN PERDIDA**: `out` no cambia lo que la
        #     funcion hace, cambia lo que el compilador deja escribir al
        #     llamador -- y el llamador aqui es el motor.
        ("CCInstancePawn", "PlayTakeHitEffects"): {
            "firma": [(r"PlayTakeHitEffects\((?:CCStubTipos\.)?TakeHitInfo HitInfo, int NumBullets\)",
                       r"PlayTakeHitEffects(const out CCStubTipos.TakeHitInfo HitInfo, "
                       r"int NumBullets)")]},

        ("CCInstanceController", "Follow"): {
            "firma": [(r"exec function Follow\(string pname\)",
                       "exec function Follow(optional string pname)")]},
        ("CCWeapon", "ProcessInstantHit"): {
            "firma": [(r"optional Object ContextObject", "optional int NumHits")],
            "cuerpo": [
                (r"(function ProcessInstantHit\([^)]*\)\r?\n\{\r?\n)",
                 r"\1\tlocal Object ContextObject;\n"),
                (r"super\.ProcessInstantHit\(FiringMode, Impact, ContextObject\);",
                 "super.ProcessInstantHit(FiringMode, Impact);")]},
        # 7. `CCController.ClientSetHUD` -- **LA MISMA FORMA QUE `FireAmmunition`**,
        #    y por eso es del tipo limpio:
        #
        #        el stub:  ClientSetHUD(class<HUD> newHUDType, class<ScoreBoard> newScoringType)
        #        el SDK:   ClientSetHUD(class<HUD> newHUDType)
        #
        #    `newScoringType` **solo** se usa para reenviarlo a `super`. No lo lee
        #    nadie mas, y no hay ni una llamada que pase dos argumentos.
        #
        #    Y AQUI NO HAY C++ QUE VALGA: `PlayerController.ClientSetHUD` es guion
        #    puro -- ni `native`, ni `exec`, ni UNA linea en `.h`/`.cpp` -- y el
        #    unico llamador del SDK (`GameInfo.uc:1688`) le pasa UN argumento. Lo
        #    que pida el juego no se puede entregar: el motor que compila esto es
        #    el del SDK.
        #
        #    `FUNC_Simulated` NO esta en `FUNC_FuncOverrideMatch` (`UnStack.h:92`),
        #    asi que el `simulated` de mas solo podria dar un aviso -- y ni eso,
        #    porque el aviso va en el sentido contrario. Lo que obliga es la
        #    aridad y los tipos.
        #
        #    >>> Y VAN DOS CLASES, NO UNA. `CCInstanceController extends
        #    CCController` declara y llama LO MISMO, y `mide-deriva.py` no la
        #    marca porque su padre es el stub, que tambien tiene 2: un
        #    instrumento que mide contra el SDK es ciego a lo que se arregla
        #    dentro del paquete. Arreglar una sola ABRE UN ERROR NUEVO.
        #
        #    >>> Y OJO CON `[Cc]lass`: el texto que ve este alineador **todavia
        #    trae `Class<HUD>` con MAYUSCULA**. La normalizacion a minuscula va
        #    DESPUES. Un patron escrito `class<ScoreBoard>` NO CASA -- y el del
        #    `cuerpo` si casa, porque esa linea no lleva `Class<` por ningun
        #    lado. O sea: **la mitad del arreglo se aplica y la otra no, y el
        #    aviso que lo dice no se imprime**. Se vio midiendo, no leyendo.
        ("CCController", "ClientSetHUD"): {
            "firma": [(r",[ \t]*[Cc]lass<ScoreBoard>[ \t]+newScoringType", "")],
            "cuerpo": [(r"super\(PlayerController\)\.ClientSetHUD\(newHUDType, newScoringType\);",
                        "super(PlayerController).ClientSetHUD(newHUDType);")]},
        ("CCInstanceController", "ClientSetHUD"): {
            "firma": [(r",[ \t]*[Cc]lass<ScoreBoard>[ \t]+newScoringType", "")],
            "cuerpo": [(r"super\.ClientSetHUD\(newHUDType, newScoringType\);",
                        "super.ClientSetHUD(newHUDType);")]},
        # 2. `LocalMessage.GetColor` tiene CUATRO parametros en el SDK y el
        #    descompilador escribio CINCO. El quinto, `OptionalData`, lo usa
        #    **solo el cuerpo de `ClientReceive`**, no el de `GetColor`, que
        #    emplea los tres primeros:
        #
        #        return GetMessageTypeColor(GetMessageType(Switch, RelatedPRI_1,
        #                                                  RelatedPRI_2));
        #
        #    Y no hay ni una llamada con argumentos: todas son `GetColor()` a
        #    secas. Quitar el quinto no rompe nada.
        # 6. `UIMisc.LerpColor` -- **CERRADO POR LA OPCION C**, y el historial de
        #    abajo se conserva entero. Lo que lo cerro: quitar `Object.LerpColor`
        #    del SDK -- que no usaba nadie y que el juego (4701) no tenia.
        #    Ver `docs/cambios-sdk.md` §8 para la vuelta.
        #    Y quitar aquel **desarmo ademas un coste ajeno**: era el unico
        #    `LerpColor` FINAL que `UIHudMenu_PlayerInfo` tenia por encima.
        #
        #    Se probo a adoptar la firma del padre, y el compilador responde con
        #    OTRO mensaje:
        #
        #        sin tocar:   Redefinition of 'function LerpColor' differs from original
        #        adoptando:   LerpColor: Can't override a 'final' function
        #
        #    `Object.LerpColor` es **`static final`**, y una funcion `final` no
        #    se puede sobrescribir DE NINGUNA FORMA. O sea: **la firma nunca fue
        #    el problema** -- el primer mensaje solo lo tapaba.
        #
        #    No es un choque de versiones de la misma funcion: es que el juego
        #    tiene una `UIMisc.LerpColor` propia --devuelve `LinearColor` y su
        #    cadena de llamada entera lo es, hasta `SetColor`-- y el SDK le anadio
        #    despues un `Object.LerpColor` que ademas es `final`.
        #
        #    >>> AQUI DECIA UNA COSA FALSA, y se corrige: *"`UIHudMenu_PlayerInfo`
        #    si puede declarar la suya porque no es `static`, y un metodo de
        #    instancia no sobrescribe uno estatico"*. **NO ES ESO.** Se leyo el
        #    compilador:
        #
        #      - NO hay ningun filtro `static` en el recorrido de ancestros.
        #        `UnScrCom.cpp:10550` compara por NOMBRE y luego por FIRMA, y
        #        nada mas.
        #      - `UIMisc` tiene **CERO descendientes** -- medido en los stubs y
        #        en el SDK -- asi que no estaba en esa cadena.
        #
        #    El unico `LerpColor` de la cadena era el de `Object`, y el de
        #    `UIHudMenu_PlayerInfo` **casa con el exactamente** (`Color`, `Color`,
        #    `float`): pasa las comprobaciones de parametros y llega a la rama del
        #    `final`. Por eso salia ESE mensaje y no un `differs`.
        #
        #    >>> Y ESO MANDA SOBRE `UIMisc`: `UIMisc.LerpColor` es `static` y
        #    devuelve `LinearColor`, asi que contra el de `Object` **no casa** --
        #    muere antes, en `Redefinition ... differs from original`. Son las dos
        #    paradas del MISMO recorrido, no dos problemas.
        #
        #    Las salidas que quedan --borrarla, renombrarla, o volverla no
        #    estatica-- son las tres que este proyecto tiene escritas como
        #    TRUCOS: pierden informacion o esconden el problema. **Queda abierto**,
        #    con las dos medidas al lado.
        #
        # 6-bis. `UIMisc.LerpColor` -- **LA OPCION B, PROBADA Y REFUTADA.**
        #
        # Se probo a ADOPTAR LA FIRMA DEL PADRE -- el `Color LerpColor(Color,
        # Color, float)` del SDK -- y a ajustar el cuerpo. La alineacion SE
        # APLICO, comprobada en el fichero:
        #
        #     static function Color LerpColor(Color Start, Color End, float Value)
        #
        # >>> Y NO SIRVE: el mensaje cambia de forma y el recuento NO se mueve.
        #
        #     sin tocar:  Redefinition of 'function LerpColor' differs from original
        #     adoptando:  LerpColor: Can't override a 'final' function
        #     las dos:    **6 errores**
        #
        # O sea que **la firma nunca fue el obstaculo**, y ahora esta probado con
        # la firma realmente puesta, no deducido. El muro es
        # `UnScrCom.cpp:10659` y su `Function->FunctionFlags & FUNC_Final`.
        #
        # Y el llamador no llega ni a protestar: la declaracion falla antes.
        #
        # LA OPCION B NECESITARIA ADEMAS ALGO QUE NO EXISTE: el llamador tiene
        # `LinearColor` y el padre pide `Color`, y el SDK solo trae
        # `ColorToLinearColor` (`Object.uc:1447`) -- **la direccion contraria**.
        # Comprobado en el SDK entero y en los stubs: no hay `LinearColor -> Color`.
        # Escribirlo seria INVENTAR una funcion, que es lo que este proyecto no
        # hace ni para arreglar un error.
    }

    # =====================================================================
    # Y UNA REGLA, PARA UNA DERIVA QUE NO ES UN CASO SUELTO
    #
    # `LocalMessage` EN EL SDK TIENE UN PARAMETRO MENOS QUE EL DEL JUEGO.
    #
    # Los tres primeros casos que salieron -- `GetColor`, `ClientReceive` y
    # `GetString` -- no son tres averias: son **tres funciones distintas de la
    # misma clase, y las tres difieren IGUAL**. El descompilador les anade un
    # `optional int OptionalData` final que el `LocalMessage` del SDK no tiene:
    #
    #     SDK:   GetString(optional int Switch, ..., optional Object OptionalObject)
    #     juego: GetString(optional int Switch, ..., optional Object OptionalObject,
    #                      optional int OptionalData)
    #
    # Es deriva de versiones -- la de siempre, 4701 contra 10897 -- y va como
    # REGLA acotada al subarbol de `LocalMessage`, no como tres entradas.
    #
    # Y SALIERON DE UNO EN UNO, no todos a la vez: el compilador **paraba en el
    # primero y no llegaba al siguiente**, asi que cada arreglo DESTAPABA el
    # que venia detras. Es la forma que este proyecto tiene documentada.
    #
    # Hacen falta DOS sitios: la firma, y las llamadas a `super` que pasaban el
    # argumento que ya no existe.
    if "LocalMessage" in ancestros(clase):
        texto, n = re.subn(r",\s*optional int OptionalData(?=[)\s]*\))", "", texto)
        if n:
            avisos.append(f"{n} firma(s) alineada(s): `optional int OptionalData` "
                          "de mas (el `LocalMessage` del SDK no lo tiene)")
        texto, n = re.subn(r"(super\.\w+\([^;]*?),\s*OptionalData\)", r"\1)", texto)
        if n:
            avisos.append(f"{n} llamada(s) a `super` sin el argumento de mas")

    # =====================================================================
    # Y LA MISMA FAMILIA AL REVES: AQUI **EL SDK TIENE MAS**.
    #
    # Es el cubo MENOS de `clasifica-derivas.py`, y es el UNICO de los cinco
    # que no pierde nada -- porque la deriva va en la direccion contraria. El
    # stub es MAS VIEJO que el SDK, asi que le falta lo que el SDK gano
    # despues. Se le ANADE, y el cuerpo lo REENVIA:
    #
    #     SDK (GameInfo.uc:1192):
    #         Login(string Portal, string Options, const UniqueNetID UniqueID,
    #               out string ErrorMessage)
    #     juego:
    #         Login(string Portal, string Options, out string ErrorMessage)
    #
    # Y SON TRES FICHEROS, no uno --`CCInstanceGameInfo`, `CCPVEGameInfo` y
    # `CCSoloGameInfo`--, y los tres la reenvian con TRES argumentos. Es una
    # FAMILIA, como `LocalMessage`, y por eso va como regla y no como tres
    # entradas de `FINALES_ALINEADAS`.
    #
    # Lo que hace falta son DOS sitios, igual que alli: la firma, y la llamada
    # a `super` que pasa el argumento de menos.
    #
    # El patron exige DECLARACION (`function`/`event` delante) porque el mismo
    # texto aparece en las LLAMADAS, y ahi `Login(` no lleva tipos.
    texto, n = re.subn(
        r"(?m)^([^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*(?:function|event)[^\n]*\bLogin\()"
        r"string Portal, string Options, (out string ErrorMessage\))",
        r"\1string Portal, string Options, const UniqueNetID UniqueID, \2", texto)
    if n:
        avisos.append(f"{n} firma(s) de `Login` con `const UniqueNetID UniqueID` "
                      "anadido (el SDK lo tiene y el juego no)")
    texto, n = re.subn(
        r"((?:super[\.\(][^;\n]*?)Login\([^;\n]*?Options), (ErrorMessage\))",
        r"\1, UniqueID, \2", texto)
    if n:
        avisos.append(f"{n} llamada(s) a `super.Login` con el argumento que faltaba")

    # Y LA MISMA FORMA, EN UNA SOLA CLASE. `Controller.IsInCombat` gano un
    # `optional bool bForceCheck`, y **es `optional`**: los dos llamadores que
    # hay --`SeqCond_CCAIIsInCombat.uc:31` y `:51`, los dos con `bot.`-- pasan
    # cero argumentos y siguen valiendo. No hay nada que ajustar mas que la
    # firma.
    texto, n = re.subn(
        r"(?m)^([^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*(?:function|event)[^\n]*\bIsInCombat\()\)",
        r"\1optional bool bForceCheck)", texto)
    if n:
        avisos.append(f"{n} firma(s) de `IsInCombat` con `optional bool bForceCheck` "
                      "anadido (lo gano el SDK; nadie lo pasa)")

    # =====================================================================
    # EL MURO `final`, Y LA FAMILIA ES **UNA CLASE Y TRES FUNCIONES**.
    #
    # AUDITADO, no supuesto: se cruzaron las 1.144 funciones `final` del SDK con
    # lo que redeclaran los 742 stubs **siguiendo la JERARQUIA** -- porque
    # redeclarar un nombre no es nada si la clase no desciende de la que lo
    # declara: de 36 candidatas quedan **1**.
    #
    #     CCWeapon  <-  Weapon   PendingFire, SetPendingFire, ClearPendingFire
    #
    # Y NO ES UN ERROR CON DOS DETRAS: son TRES en la misma clase, y el
    # compilador para en el primero. Cierran juntos o no cierra ninguno.
    #
    # LA SALIDA ES QUITAR LAS TRES DEL STUB. Las otras dos, descartadas:
    #
    #   - QUITAR `final` DEL SDK: **PROBADA Y REFUTADA.** Dejo el paquete en
    #     1.096 errores, bisecado hasta `Weapon.uc`. No se reintenta.
    #   - QUITARLAS DEL SDK, que es como se resolvio `LerpColor`: **aqui no
    #     vale**, porque alli no la usaba nadie y aqui `Weapon.uc:962` **se llama
    #     a si misma** -- y `Weapon` no puede ver lo que declara un descendiente
    #     suyo. Quitarla obligaria a REESCRIBIR el motor.
    #
    # LO QUE SE PIERDE, MEDIDO LEYENDO LOS TRES CUERPOS ENTEROS, y es la misma
    # forma en los tres: **la indireccion por el gestor de acciones del juego.**
    #
    #     PendingFire       si hay `GetServerActionManager` o
    #                       `GetClientActionManager`, devuelve SU
    #                       `GetIsWantsToDo(1)`; si no, `super`.
    #     SetPendingFire    si NO hay ninguno de los dos, no hace nada; si los
    #     ClearPendingFire  hay, reenvia a `super` solo en autoridad.
    #
    # O sea: **un mecanismo de CrimeCraft que decide si el jugador quiere
    # disparar.** Quitandolas, la clase hereda las de `Weapon`, que hacen
    # directamente lo que el juego hace en el caso en que no hay gestor.
    #
    # NO ES UN ARREGLO: ES UNA DECISION, y esta archivada en
    # `docs/funciones-no-fieles.md`. Lo que la hace aceptable es que **no
    # interviene al cargar un mapa**, que es para lo que existe el paquete.
    # >>> REVERTIDO: quitar las tres del stub TAMBIEN SE CAE (ver el
    # comentario largo de arriba). No se reintenta.

    # =====================================================================
    # `WeaponFired`: MISMA CUENTA, DESPLAZADA.
    #
    #     el SDK:  `Pawn.uc:1280`  WeaponFired(Weapon InWeapon, bool bViaReplication,
    #                                           optional vector HitLocation)
    #     el juego:                WeaponFired(bool bViaReplication,
    #                                           optional Vector StartTraceLocation,
    #                                           optional Vector EndTraceLocation)
    #
    # LOS DOS TIENEN TRES, asi que el mensaje **no** dice `different number of
    # parameters` -- igual que `LocalizedMessage` --, y lo que pasa es que **a
    # partir del primero TODO esta corrido un sitio**: le falta `Weapon InWeapon`
    # delante y le sobra `EndTraceLocation` detras.
    #
    # Se le devuelve `InWeapon` a su sitio -- y NO choca con la propiedad
    # `Weapon` de la clase, que es otro nombre --, se reenvia en el `super`, y
    # `EndTraceLocation` pasa a LOCAL. **VALE EL VECTOR VACIO.**
    # `WeaponStoppedFiring`: la HERMANA de la de arriba, y salio al cerrarla.
    #     el SDK:  `Pawn.uc:1302`  WeaponStoppedFiring(Weapon InWeapon, bool bViaReplication)
    #     el juego:                WeaponStoppedFiring(bool bViaReplication)
    #   **MENOS**, y es la familia de `Login` y `ReduceDamage`: se ANADE delante
    #   y se reenvia.
    if clase == "CCInstancePawn":
        texto, _n = re.subn(
            r"WeaponStoppedFiring\(bool bViaReplication\)",
            "WeaponStoppedFiring(Weapon InWeapon, bool bViaReplication)", texto)
        if _n:
            texto, _m = re.subn(
                r"super\(([A-Za-z_]\w*)\)\.WeaponStoppedFiring\(bViaReplication\)",
                r"super(\1).WeaponStoppedFiring(InWeapon, bViaReplication)", texto)
            avisos.append(f"`WeaponStoppedFiring`: `Weapon InWeapon` anadido en {_n} "
                          f"firma(s) y reenviado en {_m} -- es SIN PERDIDA")

    # Y `WeaponFired` YA NO ESTA DETRAS DE LA CLASE. Estaba en
    # `if clase == "CCInstancePawn"`, y **la cola es mas larga**: `CCBotPawnIllusion`
    # declara LA MISMA forma del juego.
    #
    # Medido: era **el ultimo error que quedaba en el paquete entero** --
    # `Redefinition of 'function WeaponFired' differs from original`, y detras
    # `Unexpected end of file at end of Class`, que es su consecuencia.
    #
    # QUITAR LA GUARDA ES SEGURO PORQUE EL PATRON SE LIMITA SOLO: casa la forma
    # del JUEGO -- `bool bViaReplication` primero -- y esa forma solo la tiene
    # quien la tenga. No hay que preguntar de quien es el fichero.
    #
    # Lo que SI habia que generalizar es el `super(...)`: en `CCInstancePawn` es
    # `super(Pawn)`, y en sus descendientes es `super(CCInstancePawn)` o
    # `super(CCBotPawn)`. Estaba escrito a mano.
    texto, _n = re.subn(
        r"WeaponFired\(bool bViaReplication, optional Vector StartTraceLocation, "
        r"optional Vector EndTraceLocation(?:, optional AdditionalHitInfo AddInfo)?\)",
        "WeaponFired(Weapon InWeapon, bool bViaReplication, "
        "optional Vector StartTraceLocation)", texto)
    if _n:
        texto, _m = re.subn(
            r"super\(([A-Za-z_]\w*)\)\.WeaponFired\(bViaReplication, StartTraceLocation, "
            r"EndTraceLocation(?:, AddInfo)?\)",
            r"super(\1).WeaponFired(InWeapon, bViaReplication, StartTraceLocation)", texto)
        texto, _k = re.subn(
            r"(?m)^([^\S\n]*)(simulated function WeaponFired\(Weapon InWeapon,[^\n]*\)\r?\n\{\r?\n)",
            lambda m: m.group(1) + m.group(2) + m.group(1)
            + "\t// `EndTraceLocation` era un parametro del JUEGO; el SDK tiene\n"
            + m.group(1) + "\t// `HitLocation` en ese sitio. Vale el vector VACIO.\n"
            + m.group(1) + "\tlocal Vector EndTraceLocation;\n", texto)
        avisos.append(f"`WeaponFired`: `Weapon InWeapon` devuelto a su sitio, "
                      f"`EndTraceLocation` a LOCAL (**vector vacio**) y {_m} reenvio(s); "
                      f"{_k} local(es)")

    # =====================================================================
    # `DynamicTextureCoordExInfo`: EL TIPO SI, EL MIEMBRO DEL SDK NO.
    #
    # Son DOS cosas, y es lo que hacia que pareciera un muro:
    #
    #   1. El TIPO. Sus miembros **SI se deducen de los usos**, que es lo
    #      contrario de lo que decia el plan -- alli estaba puesto con
    #      `RenderParameters` y `DynamicTextureCoordExInfo` en el mismo saco:
    #
    #          DynamicTextureCoordExInfoStruct.CoordIndex        = 0;
    #          DynamicTextureCoordExInfoStruct.ProjectionVectorU = vect(...);
    #          DynamicTextureCoordExInfoStruct.ProjectionVectorV = vect(...);
    #
    #      Tres miembros, y sus tipos los dice el valor que se les asigna.
    #
    #   2. `SkeletalMeshComponent.DynamicTextureCoordExInfoStructs`, que el SDK
    #      **no tiene** -- se busco en su `.uc` --, y que en el juego colgaba de
    #      una clase NATIVA.
    #
    # POR QUE NO SE AÑADE AL SDK, que es lo que se hizo con `ScoreKill`:
    # porque NO es el mismo caso. `ScoreKill` es una FIRMA de funcion de guion:
    # no toca el layout de nada. Esto es un MIEMBRO de una clase **nativa** cuyo
    # header de C++ se genera desde el `.uc` -- tiene 116 marcadores
    # `AUTOGENERATE`/`MAP_NATIVE` --, y un miembro de mas ahi es un cambio de
    # layout de una clase del MOTOR.
    #
    # Y el precio de equivocarse no es el mismo: si `ScoreKill` salia mal, se
    # veia al compilar el guion; si esto sale mal, se rompe el build de C++, que
    # es el objetivo 1 del proyecto y esta a cero errores.
    #
    # SE QUEDA EN UN ARRAY LOCAL: los tres accesos al miembro del componente
    # pasan a un array de la propia funcion. **El efecto visual se pierde** -- el
    # componente no queda configurado --, y queda archivado.
    texto, _n = re.subn(r"[A-Za-z_]\w*\.DynamicTextureCoordExInfoStructs",
                        "_CoordInfos", texto)
    if _n:
        texto, _k = re.subn(
            r"(?m)^([^\S\n]*)(simulated function ConfigureDynamicTextureCoordExInfoFor\([^\n]*\)\r?\n\{\r?\n)",
            lambda m: m.group(1) + m.group(2) + m.group(1)
            + "\t// El juego escribia en `SkelComp.DynamicTextureCoordExInfoStructs`,\n"
            + m.group(1) + "\t// un miembro de `SkeletalMeshComponent` que el SDK no tiene.\n"
            + m.group(1) + "\t// Aqui es un array LOCAL: se pierde el efecto.\n"
            + m.group(1) + "\tlocal array<DynamicTextureCoordExInfo> _CoordInfos;\n", texto)
        avisos.append(f"{_n} acceso(s) al miembro del SDK pasan a array LOCAL "
                      f"(**el efecto se pierde**); {_k} declaracion(es)")

    # =====================================================================
    # TRES MAS, Y LAS TRES SIN PERDIDA. Van juntas porque son la misma forma:
    # un parametro que el SDK tiene y el stub no, o al reves.
    #
    # `BeginAnimControl`: MISMA CUENTA, DISTINTO TIPO.
    #     el SDK:  `Pawn.uc:739`  simulated event BeginAnimControl(InterpGroup InInterpGroup)
    #     el juego: simulated event BeginAnimControl(array<AnimSet> InAnimSets)
    #   Y EL CUERPO NO LO USA: busca los nodos por NOMBRE en
    #   `CharacterComponent.Animations`. Solo hay que cambiar el TIPO.
    texto, _n = re.subn(
        r"BeginAnimControl\(array<AnimSet> InAnimSets\)",
        "BeginAnimControl(InterpGroup InInterpGroup)", texto)
    if _n:
        avisos.append(f"{_n} `BeginAnimControl`: el parametro pasa a `InterpGroup` "
                      "(el cuerpo no lo usaba: es SIN PERDIDA)")

    # `ReduceDamage`: MENOS, y de la familia de `Login` y `NotifyKilled`.
    #     el SDK: 7, termina en `Actor DamageCauser`
    #     el juego: 6
    #   Se ANADE y se REENVIA, que es lo que el SDK necesita para llegar al suyo.
    texto, _n = re.subn(r"(ReduceDamage\([^)]*?[Cc]lass<DamageType> DamageType)\)",
                        r"\1, Actor DamageCauser)", texto)
    texto, _n2 = re.subn(r"((?:super[\.\(][^;\n]*?)ReduceDamage\([^;\n]*?DamageType)\)",
                         r"\1, DamageCauser)", texto)
    if _n or _n2:
        avisos.append(f"`ReduceDamage`: `Actor DamageCauser` anadido en {_n} firma(s) y "
                      f"reenviado en {_n2} llamada(s) -- lo tiene el SDK y el juego no")

    # `Explode`: 3 contra 2. `bViaReplication` **se usa en la logica** (una vez),
    # asi que NO se puede tirar sin mas: pasa a local, **vale `false`**, y se
    # archiva. Es la familia de `PlayFireEffects`.
    texto, _n = re.subn(
        r"Explode\(Vector HitLocation, Vector HitNormal, optional bool bViaReplication = false\)",
        "Explode(Vector HitLocation, Vector HitNormal)", texto)
    if _n:
        texto, _m = re.subn(
            r"(?m)^([^\S\n]*)(simulated function Explode\(Vector HitLocation, Vector HitNormal\)\r?\n\{\r?\n)",
            lambda m: m.group(1) + m.group(2) + m.group(1)
            + "\t// `bViaReplication` era un parametro del JUEGO. Vale FALSE.\n"
            + m.group(1) + "\tlocal bool bViaReplication;\n", texto)
        avisos.append(f"`Explode` recortado a 2 parametros; `bViaReplication` pasa a "
                      f"LOCAL (**FALSE**) porque el cuerpo lo usa")

    # `SetAnimPosition`: MENOS. `Pawn.uc:756` tiene SIETE y el juego seis: le
    # falta `bool bEnableRootMotion`. **NO HAY `super.SetAnimPosition` en la
    # exportacion**, asi que no hay nada que reenviar: se ANADE y ya esta.
    texto, _n = re.subn(
        r"(SetAnimPosition\(name SlotName, int ChannelIndex, name InAnimSeqName, "
        r"float InPosition, bool bFireNotifies, bool bLooping)\)",
        r"\1, bool bEnableRootMotion)", texto)
    if _n:
        avisos.append(f"{_n} `SetAnimPosition`: `bool bEnableRootMotion` anadido "
                      "(lo tiene el SDK; el cuerpo no reenvia a `super`)")

    # `ProjectileHurtRadius`: AL REVES. `Projectile.uc:130` tiene DOS y el juego
    # cuatro -- `optional bool bTest, optional out array<Actor> TestVictims` --,
    # y las dos llamadas que hay estan DENTRO de la propia clase. Se recortan
    # las tres: la firma y las dos llamadas.
    texto, _n = re.subn(
        r"(ProjectileHurtRadius\(Vector HurtOrigin, Vector HitNormal), optional bool bTest, "
        r"optional out array<Actor> TestVictims\)", r"\1)", texto)
    if _n:
        texto, _m = re.subn(r"ProjectileHurtRadius\((HitLocation|HurtOrigin), HitNormal, true, TestVictims\)",
                            r"ProjectileHurtRadius(\1, HitNormal)", texto)
        avisos.append(f"`ProjectileHurtRadius` recortado a los 2 del SDK, y {_m} "
                      "llamada(s) con ellos (**`TestVictims` se pierde**)")

    # `PlayHit`: el ultimo de la familia, y el que cierra el circulo de
    # `TakeDamage`. `Pawn.uc:2830` tiene SEIS; el juego SIETE, con el mismo
    # `AdditionalHitInfo AddInfo` que se le quito a `TakeDamage`.
    #
    # Se quita de la FIRMA y de la LLAMADA A `super`, y el llamador de
    # `CCTurret` -- que le pasaba el local que ahora vale cero -- se recorta con
    # el mismo patron, porque la forma es la misma.
    # Y EL PATRON ES GENERAL A PROPOSITO, porque la cola es larga: `PlayHit`
    # cerro y DESTAPO `WeaponFired`, con **la misma forma pero `optional`** --
    # la primera version del patron no lo cubria y se quedo a medias. La forma
    # es la forma: un parametro final `AdditionalHitInfo AddInfo`, con o sin
    # `optional` y con o sin default.
    texto, _n = re.subn(
        r",\s*(?:optional\s+)?additionalhitinfo\s+addinfo(?:\s*=\s*(?:none))?\s*\)",
        ")", texto, flags=re.I)
    if _n:
        avisos.append(f"{_n} firma(s)/llamada(s) con un `AdditionalHitInfo AddInfo` final "
                      "recortadas: era un parametro del juego y el SDK no lo tiene")

    # =====================================================================
    # `ScoreKill`: LA UNICA DE LAS GRANDES QUE NO PIERDE NADA.
    #
    # Ocho declaraciones en el paquete, todas con seis parametros, contra DOS
    # del SDK. Y a diferencia de `TakeDamage`, aqui **los cuatro que sobran son
    # tipos del SDK** -- `class<DamageType>`, `int`, `bool`, `int` --, asi que
    # se pueden declarar EN EL PADRE.
    #
    # Es el cubo "SDK" que este plan identifico, y la razon de elegirlo esta
    # medida: alineando hacia abajo se perderia `DamageType`, que solo en
    # `CCInstanceGameInfo` se usa ONCE veces. Por aqui, ninguna.
    #
    # Lo unico que hay que hacer en el stub es **poner `optional` en
    # `DamageType`**: el SDK tiene que poder llamarla con dos argumentos -- y de
    # hecho la llama asi en `GameInfo.uc:2109` --, y el compilador compara la
    # bandera `optional` parametro a parametro.
    # Y AQUI VOLVIO A MORDER LA TRAMPA NUMERO UNO DE LA TABLA: el export
    # escribe **`Class<DamageType>` con mayuscula** y el patron decia
    # `class<`. No caso, `_n` valio 0, y el error se quedo a medias -- se vio
    # porque el mensaje CAMBIO de `different number of parameters` a
    # `'optional' mismatch on parameter 3`, que es la firma del arreglo a
    # medias.
    texto, _n = re.subn(
        r"(ScoreKill\(Controller Killer, Controller Other, )[Cc]lass<DamageType> DamageType",
        r"\1optional class<DamageType> DamageType", texto)
    if _n:
        avisos.append(f"{_n} `ScoreKill`: `DamageType` pasa a `optional` para poder "
                      "cuadrar con el SDK, que ahora los declara los cuatro")


    # =====================================================================
    # `TakeDamage`: LA DERIVA DE VERSIONES, ENTERA Y DE UNA VEZ.
    #
    # El SDK tiene SIETE parametros -- `Actor.uc:2348` y `Pawn.uc` -- y el juego
    # NUEVE: le anade `optional AdditionalHitInfo AddInfo` y `optional Object
    # ContextObject`. Son TRECE declaraciones en el paquete, todas con nueve.
    #
    # Y HAY QUE ALINEAR LAS TRECE, no las cuatro que el compilador nombra: la
    # regla es contra el ANCESTRO MAS CERCANO, asi que si `CCPawn` baja a siete,
    # sus descendientes de nueve pasan a derivar, y la cascada no se para. Se
    # midio la cadena entera antes de tocar nada.
    #
    # LO QUE SE PIERDE, MEDIDO CUERPO A CUERPO, y son DOS sitios de trece:
    #
    #     CCInstancePawn:6695  lee `AddInfo.ShotFlags` cuatro veces
    #     CCTurret:379         pasa `AddInfo` a `PlayHit`
    #
    # En las otras once, el unico uso es el `super.TakeDamage(...)` que se va con
    # ellos. En las dos que quedan, **`AddInfo` pasa a ser un LOCAL**, que es lo
    # que el proyecto ya hizo con `ContextObject` en `ProcessInstantHit` -- y se
    # dice lo que vale: **cero**. El struct nace a cero, asi que
    # `AddInfo.ShotFlags` es 0 y la rama que lo mira decide distinto.
    #
    # ES UNA PERDIDA, Y ES UNA DECISION: la alternativa era el error permanente,
    # porque el SDK no puede nombrar `AdditionalHitInfo` -- es NUESTRO.
    def _recorta_a_siete(texto):
        """Corta a SIETE argumentos todo `TakeDamage(...)`, sea firma o llamada."""
        fuera, i, n_cortes = [], 0, 0
        while True:
            k = texto.find("TakeDamage(", i)
            if k < 0:
                fuera.append(texto[i:]); break
            abre = k + len("TakeDamage")
            prof, j = 0, abre
            while j < len(texto):
                if texto[j] == "(": prof += 1
                elif texto[j] == ")":
                    prof -= 1
                    if prof == 0: break
                j += 1
            params = texto[abre + 1:j]
            partes, prof, act = [], 0, ""
            for c in params:
                if c in "([": prof += 1
                elif c in ")]": prof -= 1
                if c == "," and prof == 0:
                    partes.append(act); act = ""
                else:
                    act += c
            partes.append(act)
            fuera.append(texto[i:abre + 1])
            if len(partes) > 7:
                fuera.append(",".join(partes[:7]))
                n_cortes += 1
            else:
                fuera.append(params)
            fuera.append(")")
            i = j + 1
        return "".join(fuera), n_cortes

    texto, _cortes = _recorta_a_siete(texto)
    if _cortes:
        avisos.append(f"`TakeDamage` recortado a los 7 parametros del SDK en "
                      f"{_cortes} sitio(s) -- el juego tenia 9")

    # Y LOS DOS LOCALES, SOLO DONDE SE USA.
    #
    # Y AQUI VOLVIO A MORDER LA TRAMPA DE SIEMPRE, la sexta: el patron exigia
    # `function|event` justo tras el margen, y la declaracion de `CCTurret` es
    # **`simulated event TakeDamage(...)`** -- con modificador delante. No caso,
    # `_n` valio 0, y no paso nada. **Los modificadores van delante del todo.**
    if clase in ("CCInstancePawn", "CCTurret"):
        texto, _n = re.subn(
            r"(?m)^([^\S\n]*)(?:[A-Za-z_]\w*[ \t]+)*(?:function|event)"
            r"([^\n]*\bTakeDamage\([^\n]*)\r?\n\{\r?\n",
            lambda m: (m.group(0) + m.group(1) + "\tlocal AdditionalHitInfo AddInfo;\n"),
            texto)
        if _n:
            avisos.append(f"{_n} `AddInfo` convertido en LOCAL: era un parametro del "
                          "juego y el SDK no lo tiene. **VALE CERO** -- se dice, porque "
                          "la rama que lo mira decide distinto")

    # =====================================================================
    # `CCBaseHUD.LocalizedMessage`: LOS PARAMETROS VAN DESFASADOS.
    #
    # Y no por aridad -- **los dos tienen DIEZ** --, que es lo que hace que el
    # mensaje no diga `different number of parameters` y haya que mirarlo:
    #
    #     SDK:   (..., RelatedPRI_1, RelatedPRI_2, string CriticalString, ...)
    #     stub:  (..., RelatedPRI_1, string CriticalString, ...)
    #
    # A partir del tercero TODO esta corrido un sitio, y el compilador lo dice
    # como `differs from original` a secas.
    #
    # SON DOS DEFECTOS EN UNA FIRMA, y los dos tienen la misma causa: el
    # descompilador. **Se ha comido `RelatedPRI_2` Y ha anadido un
    # `optional int OptionalData` al final** -- este segundo es el MISMO que la
    # regla de `LocalMessage` de mas arriba ya quita, y aqui no llegaba porque
    # `CCBaseHUD` es un `HUD`, no un `LocalMessage`.
    #
    # Se arreglan los dos: se devuelve `RelatedPRI_2` a su sitio y se quita el
    # que sobra. El cuerpo no usa `OptionalData` -- lo anadio el descompilador.
    # Y NO SE ACOTA A `CCBaseHUD`, que es como empezo y estaba MAL: el mismo
    # descompilador dejo el mismo defecto en **`CCInstanceHUD`**, y no se supo
    # hasta que el de `CCBaseHUD` cerro y el suyo quedo al descubierto. La FORMA
    # es unica -- `RelatedPRI_1,` seguido de `string CriticalString`, y un
    # `optional int OptionalData` al final --, asi que la regla es la forma.
    texto, n = re.subn(r"(RelatedPRI_1,[ \t]*)(string CriticalString)",
                       r"\1PlayerReplicationInfo RelatedPRI_2, \2", texto)
    texto, n2 = re.subn(r",\s*optional int OptionalData(?=[)\s]*\))", "", texto)
    if n or n2:
        avisos.append(f"`LocalizedMessage`: `RelatedPRI_2` devuelto a su sitio ({n}) y "
                      f"`optional int OptionalData` retirado ({n2}) -- los dos, del descompilador")

    # =====================================================================
    # `DrawActorOverlays`: PROMOVER LOS LOCALES A PARAMETROS.
    #
    # El SDK los tiene en la firma, y el juego los tiene como LOCALES con LOS
    # MISMOS NOMBRES:
    #
    #     HUD.uc:151   native function DrawActorOverlays(vector Viewpoint, rotator ViewRotation);
    #     CCBaseHUD    function DrawActorOverlays()
    #                  {
    #                      local Rotator ViewRotation;
    #                      local Vector ViewPoint, ViewDir;
    #
    # Es la transformacion que este generador tenia APLAZADA y dicha: hay diez
    # casos de este tipo en el paquete y este es uno.
    #
    # Y NO SE PIERDE NADA, y esta COMPROBADO EN EL CUERPO, que es lo que lo hace
    # una decision y no una apuesta:
    #
    #   - `CCBaseHUD` **nunca los lee antes de escribirlos**: la primera cosa que
    #     hace la rama es `PlayerOwner.GetPlayerViewPoint(ViewPoint, ViewRotation)`,
    #     que es `out`. Y donde NO se escriben, un local de UnrealScript vale
    #     CERO. O sea que **pasar ceros es exactamente lo que ya pasaba**.
    #   - `CCInstanceHUD` **no los usa en absoluto** -- cero apariciones --, asi
    #     que alli solo hay que anadir dos parametros que nadie mira.
    #
    # Los cuatro llamadores pasan cero argumentos, y se les pone el cero
    # EXPLICITO. Las llamadas a `super.` de las subclases reenvian los suyos.
    # Las CUATRO clases, y no dos. El conjunto estaba partido en dos mitades que
    # no se hablaban --`("CCBaseHUD", "CCInstanceHUD")` para la declaracion y
    # `(..., "CCRobberyHUD", "CCSNDHUD")` para las llamadas--, y las dos que
    # estaban SOLO en la segunda mitad se quedaban sin promover.
    #
    # EL SINTOMA, medido: `Unrecognized type 'vect'` en `CCRobberyHUD(81)` y
    # `CCSNDHUD(283)`. La regla de las LLAMADAS casa `DrawActorOverlays\(\)`, y
    # **la DECLARACION de estas dos tambien tiene `()`** -- asi que les escribia
    # los ceros EN LA FIRMA:
    #
    #     function DrawActorOverlays(vect(0.0000000, 0.0000000, 0.0000000), rot(0, 0, 0))
    #
    # A `CCBaseHUD` y `CCInstanceHUD` no les mordia porque su declaracion ya la
    # habia reescrito la regla de arriba, y ya no tenia `()`.
    #
    # Es EL MISMO defecto que este generador lleva siete pagados: **una regla que
    # no mira DONDE escribe**. Se arregla juntando las dos listas en una, no
    # afinando el patron de las llamadas -- lo que hay que decir es que las cuatro
    # clases son el mismo caso, y el parrafo de arriba ya lo dice.
    CLASES_DRAWACTOROVERLAYS = ("CCBaseHUD", "CCInstanceHUD",
                                "CCRobberyHUD", "CCSNDHUD")
    if clase in CLASES_DRAWACTOROVERLAYS:
        texto, n = re.subn(r"(?m)^([^\S\n]*)function[ \t]+DrawActorOverlays\(\)",
                           r"\1function DrawActorOverlays(Vector Viewpoint, Rotator ViewRotation)",
                           texto)
        if n:
            avisos.append(f"{n} firma(s) de `DrawActorOverlays` con los parametros "
                          "promovidos del SDK")
    if clase in CLASES_DRAWACTOROVERLAYS:
        # Y SE QUITAN LOS LOCALES, o chocan con los parametros: `'ViewRotation'
        # already defined`. Es el mismo choque que este comentario lleva avisando
        # desde el principio, resuelto en la direccion que toca.
        texto, n = re.subn(r"(?m)^[^\S\n]*local[ \t]+Rotator[ \t]+ViewRotation;[ \t]*\r?\n",
                           "", texto)
        texto, n2 = re.subn(r"(?m)^([^\S\n]*local[ \t]+Vector[ \t]+)ViewPoint,[ \t]*",
                            r"\1", texto)
        if n or n2:
            avisos.append(f"locales `ViewPoint`/`ViewRotation` retirados ({n + n2}): "
                          "ahora son los parametros")
    if clase in CLASES_DRAWACTOROVERLAYS:
        texto, n = re.subn(r"((?:super(?:\([A-Za-z_]\w*\))?\.)?DrawActorOverlays\()\)",
                           r"\g<1>vect(0.0000000, 0.0000000, 0.0000000), rot(0, 0, 0))",
                           texto)
        if n:
            avisos.append(f"{n} llamada(s) a `DrawActorOverlays` con los ceros "
                          "explicitos (que es lo que el local valia)")

    # =====================================================================
    # `ForceActivateOutput`: SE QUITA LA DECLARACION, Y ES LO CORRECTO AQUI.
    #
    # El SDK la tiene `native FINAL` en `SequenceOp.uc:700`:
    #
    #     native final function ForceActivateOutput(int OutputIdx);
    #
    # Y el juego la redeclara con un `optional` de mas:
    #
    #     native function ForceActivateOutput(optional int OutputIdx = 0);
    #
    # Asi que hay DOS muros, y el segundo es el que decide:
    #
    #   1. Alinear la firma NO arregla nada: destapa
    #      `Can't override a 'final' function` (UnScrCom.cpp:10659). Es el muro
    #      de `LerpColor`, ya medido.
    #   2. **Y LA DEL JUEGO NO TIENE CUERPO NI PUEDE TENERLO.** El export lo
    #      dice: `// Export UUIAction_BroadcastStringEvent::execForceActivateOutput`.
    #      O sea que el C++ ERA DEL JUEGO, y **en nuestro SDK no existe**: es la
    #      misma pared de las 4.378 nativas (E-1). Si se dejara declarada,
    #      compilaria y **fallaria AL LLAMARLA**, que es peor que no tenerla.
    #
    # Quitandola, la clase **hereda la de `SequenceOp`**, que si tiene C++ en
    # nuestro SDK. **No se pierde nada que exista**: lo que se pierde es una
    # declaracion de algo que no hay.
    #
    # Y el llamador pasa a llevar el argumento que el juego habria pasado por su
    # propio `= 0` -- o sea `0`. Es lo mismo que ya hacia, escrito.
    if clase == "UIAction_BroadcastStringEvent":
        texto, n = re.subn(
            r"(?m)^[^\S\n]*native[ \t]+function[ \t]+ForceActivateOutput\([^)]*\)[ \t]*;[ \t]*\r?\n",
            "", texto)
        if n:
            avisos.append("`ForceActivateOutput` RETIRADA: el SDK la tiene `native final` "
                          "y su C++ era del juego; se hereda la que si funciona")
    texto, n = re.subn(r"(\.ForceActivateOutput\()\)", r"\g<1>0)", texto)
    if n:
        avisos.append(f"{n} llamada(s) a `ForceActivateOutput` con el `0` explicito")

    # Y LA TERCERA DE LA FAMILIA, con DOS declarantes -- `CCInstanceController` y
    # `CCPVPBot` --, que es lo que la hace familia y no caso:
    #
    #     el SDK:  NotifyKilled(Controller Killer, Controller Killed,
    #                           pawn KilledPawn, class<DamageType> damageTyp)
    #     el juego: los TRES primeros.
    #
    # >>> Y EL LLAMADOR QUE PARECIA NO EXISTIR **APARECIO**.
    #
    # Aqui decia: *"el llamador que parecia bloquearlo NO EXISTE: `CCCheatManager.uc:5927`
    # llama con tres argumentos, pero `CCCheatManager` no esta en el paquete -- se
    # comprobo, no hay fichero -- asi que no se compila y no opina."*
    #
    # **La medicion era correcta y la conclusion caduco.** `CCCheatManager` no
    # estaba en el paquete ENTONCES; entro al arreglar la clausura (los literales
    # `Class'CrimeCraft.X'` que no se seguian), en el commit que trajo **227
    # stubs nuevos**. Y en cuanto entro, OPINO: su llamada de tres argumentos da
    # `Call to 'NotifyKilled': missing or bad parameter 4`, el compilador emite
    # `EX_EmptyParmValue`, y salta la asercion de `UnScrCom.cpp:3934` -- la que
    # llevaba tandas apareciendo sin que se supiera que la disparaba.
    #
    # Es la leccion que este proyecto tiene escrita -- **una medicion correcta con
    # una explicacion equivocada se archiva como conclusion, y luego nadie la
    # revisa** -- pero al reves: aqui la explicacion era correcta y **el mundo
    # cambio debajo**. Una conclusion de la forma "X no existe" caduca sola; hay
    # que volver a mirarla cuando cambia lo que la sostenia.
    #
    # Y POR ESO EL CUARTO PARAMETRO VA `optional`. El juego llamaba con TRES en
    # varios sitios -- esta en su bytecode --, o sea que tres es lo que el motor
    # del juego permitia. `optional` en `Controller.uc` es lo que RESTAURA esa
    # API; y aqui se acompana, porque el compilador compara la bandera
    # `optional` PARAMETRO A PARAMETRO y si la base la lleva y el override no,
    # el error solo cambia de nombre.
    #
    # Los dos cuerpos se miraron: **ninguno usa el cuarto**, y el de
    # `CCInstanceController` lo reenvia a `super`, que es a donde tiene que ir.
    texto, n = re.subn(
        r"(?m)^([^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*(?:function|event)[^\n]*\bNotifyKilled\()"
        r"Controller Killer, Controller Killed, Pawn KilledPawn\)",
        r"\1Controller Killer, Controller Killed, Pawn KilledPawn, "
        r"optional class<DamageType> DamageType)", texto)
    if n:
        avisos.append(f"{n} firma(s) de `NotifyKilled` con `optional class<DamageType>` "
                      "anadido (el SDK lo tiene y el juego no)")
    texto, n = re.subn(
        r"(super\((?:Controller|CCBotBase)\)\.NotifyKilled\("
        r"Killer, Killed, KilledPawn)\)", r"\1, DamageType)", texto)
    if n:
        avisos.append(f"{n} llamada(s) a `super.NotifyKilled` con el argumento que faltaba")

    # =====================================================================
    # `exec` DELANTE, CUANDO LA DECLARACION LLEVA ADEMAS BANDERAS DE RED
    #
    # `CCController.uc` trae DOS funciones asi, y son DOS DE LAS TRES del juego
    # entero -- hay 1.618 `exec function`/`exec event` y solo TRES con banderas
    # de red. La tercera es `LeaveInstance`, un `event` en `CCInstanceController`,
    # y el primer grep NO la vio porque llevaba `function` escrito a mano:
    #
    #     reliable client simulated exec function GoToLobby(string LobbyName)
    #     reliable client simulated exec function ShowExp()
    #
    # Y ASI NO COMPILA: `Exec functions cannot be replicated!`. Pero MIRA DONDE
    # ESTA LA COMPROBACION (`UnScrCom.cpp:9925`):
    #
    #     else if( Token.Matches(NAME_Exec) )
    #     {
    #         FuncInfo.FunctionFlags |= FUNC_Exec;
    #         if( FuncInfo.FunctionFlags & FUNC_Net )   <-- lo YA LEIDO
    #             ScriptErrorf(SCEL_Restricted, "Exec functions cannot be replicated!");
    #     }
    #
    # O sea: **depende del ORDEN**. Y las otras ramas:
    #
    #     NAME_Client    FUNC_Net|FUNC_NetClient|FUNC_Simulated   NO comprueba
    #     NAME_Reliable  FUNC_NetReliable                         NO comprueba
    #     NAME_Server    FUNC_Net|FUNC_NetServer                  SI comprueba
    #
    # `exec reliable client simulated` da **exactamente el mismo juego de
    # banderas** y no dispara nada. Y ESTO NO QUITA NADA: no es como
    # `PlayFireEffects`, donde alinear la firma perdia un parametro. Aqui no se
    # pierde ni un bit -- se REORDENA.
    #
    # POR QUE REORDENAR NO ES FALSIFICAR EL FUENTE, y esta medido: el orden que
    # trae la exportacion **es del descompilador**. Sobre el mismo corpus:
    #
    #     `reliable client simulated function` ... 236 veces, NUNCA permutado
    #     `native static function` ............ 2.973 veces, NUNCA al reves
    #
    # Cero variacion en miles de casos es la firma de un RENDERIZADOR, no la de
    # un fuente. El descompilador reconstruye la lista desde las banderas.
    #
    # Y EL MOTOR NO LO EXIGE AL EJECUTAR: `FUNC_Exec` se usa en dos sitios fuera
    # del analizador -- `UnObj.cpp:2205` y `UnInteraction.cpp:119` -- y NINGUNO
    # mira banderas de red. La restriccion es del analizador, y de un sentido.
    #
    # >>> EL BORDE, Y SE DICE: `exec` + `server` **no se puede expresar en
    # ningun orden**, porque `server` comprueba `FUNC_Exec` y `exec` comprueba
    # `FUNC_Net`: las dos formas fallan. Hoy no hay ninguna en la exportacion
    # (las `ccrepstats_server*` son `exec function` a secas, con "server" en el
    # NOMBRE, no como modificador). Si apareciera, **aqui no se toca**.
    #
    # Y la ancla `\)[ \t]*$` es a proposito: solo casa la LINEA de declaracion,
    # asi que un `exec function` dentro de un cuerpo o de un comentario no entra.
    _cambiados = []

    def _exec_delante(m):
        mods = m.group(2).split()
        if "exec" not in mods or not ({"reliable", "client", "server"} & set(mods)):
            return m.group(0)
        if "server" in mods:
            return m.group(0)
        mods.remove("exec")
        # EL RESTO DE LA LINEA VA ENTERO EN EL GRUPO 4. Reconstruirla a mano
        # --`... + m.group(3)`-- se comio el nombre y los parametros, y el diff
        # lo enseño: la declaracion quedaba en `exec reliable client simulated
        # function`, a secas. Es la trampa de recomponer en vez de sustituir.
        _cambiados.append(m.group(3))
        return (m.group(1) + "exec " + " ".join(mods) + " "
                + m.group(3) + m.group(4))

    if EXEC_DELANTE:
        texto = re.sub(r"(?m)^([ \t]*)((?:[A-Za-z_]\w*[ \t]+)+)(function|event)\b"
                       r"([^\n]*\)[ \t]*)$", _exec_delante, texto)
    if _cambiados:
        avisos.append(f"`exec` puesto delante en {len(_cambiados)} declaracion(es) "
                      "con banderas de red (mismo juego de banderas)")

    for (c, funcion), cambios in FINALES_ALINEADAS.items():
        if c != clase:
            continue
        # La FIRMA: solo la LINEA que declara esa funcion, porque el cuerpo
        # puede llevar el mismo texto y ahi no se toca.
        #
        # >>> Y SON **TODAS** LAS DECLARACIONES, NO LA PRIMERA.
        #
        # Estaba con `re.search`, que devuelve solo la primera, y sustituyendo a
        # mano esa. **Una clase puede declarar la misma funcion MAS DE UNA VEZ,
        # en `state` distintos**, y entonces todas tienen que cuadrar con el
        # ancestro. Lo dijo `CCInstanceController.ServerMove`, que esta declarada
        # DOS veces -- la de la clase y la de un `state`, tabulada:
        #
        #     ServerMove(... int MoveFlags ...)      <- linea 5751, alineada
        #     \tServerMove(... int MoveFlags ...)    <- 16276, INTACTA con search
        #
        # Y ES LA TRAMPA DE SIEMPRE OTRA VEZ: la segunda va **con tabulacion**,
        # que es exactamente lo que ya mordio con `^function`.
        #
        # Con `subn` van todas, y las cinco entradas que ya habia siguen igual
        # --si solo tienen una declaracion, `subn` hace lo mismo que `search`--.
        def _alinea_firma(m):
            linea = m.group(0)
            for patron, nuevo in cambios.get("firma", ()):
                linea = re.sub(patron, nuevo, linea)
            return linea

        texto, n = re.subn(r"(?m)^[^\S\n]*(?:[A-Za-z_]\w*[ \t]+)*"
                           r"(?:function|event|delegate)\b[^\n]*\b"
                           + re.escape(funcion) + r"[ \t]*\([^)\n]*\)[^\n]*$",
                           _alinea_firma, texto)
        if n:
            avisos.append(f"FIRMA ALINEADA con el padre: {funcion} ({n} declaracion(es))")
        # Y EL CUERPO, cuando la firma sola no basta -- una llamada a `super`
        # que pasa el argumento que ya no existe.
        for patron, nuevo in cambios.get("cuerpo", ()):
            texto, n = re.subn(patron, nuevo, texto)
            if n:
                avisos.append(f"cuerpo de {funcion} ajustado a la firma del padre ({n})")

    adoptadas = []
    for m in ([] if True else list(re.finditer(
            r"^([^\S\n]*)(?:[\w]+[ \t]+)*(function|event)\b[^\n]*$", texto, re.M))):
        decl = m.group(0)
        nom = re.search(r"(?:function|event)\s+(\w+)\s*\(", decl)
        if not nom:
            continue
        funcion = nom.group(1)
        firma_padre = firma_del_padre(clase, funcion)
        if not firma_padre:
            continue
        # La guarda: un local del cuerpo con el nombre de un parametro del padre.
        cuerpo = texto[m.end():]
        params_padre = set(re.findall(r"\b(\w+)\s*(?:,|\))", firma_padre.split("(", 1)[-1]))
        choca = [p for p in params_padre
                 if re.search(r"^[^\S\n]*local\s+\w+\s+[^;\n]*\b" + re.escape(p) + r"\b",
                              cuerpo, re.M)]
        if choca:
            continue
        # SE COMPARA LO QUE EL COMPILADOR COMPARA: LA LISTA DE PARAMETROS.
        #
        # Comparando la firma entera disparaba en CIENTOS de funciones --
        # `PostBeginPlay`, `Tick`, `Notify`, `SetActiveChild` -- que al
        # compilador no le molestan: `simulated`, `event`, `final` y el espacio
        # en blanco no son parte de lo que se exige que coincida.
        # Y SOLO CUANDO EL NUMERO DE PARAMETROS DIFIERE, que es lo que el
        # compilador dice con esas palabras:
        #
        #     different number of parameters
        #
        # Comparando la lista entera seguia disparando en 53 clases, con
        # `BeginState`, `Tick` y `EndState` -- funciones que el compilador NO
        # protesta. O sea: la regla se estaba aplicando a casos que no son el
        # problema, y **aplicar una regla que no se entiende a 53 clases es como
        # se rompen las cosas**, que es justo lo que este proyecto tiene escrito.
        #
        # Los otros dos mensajes --`'optional' mismatch`, `differs only by return
        # type`-- son casos sueltos y se hacen a mano, con su motivo.
        if cuenta_de_params(decl) == cuenta_de_params(firma_padre):
            continue
        nueva = re.sub(r"(?:function|event)\s+\w+\s*\([^)]*\)",
                       lambda _: firma_padre.split(None, 1)[-1]
                       if "(" in firma_padre else _.group(0),
                       decl, count=1)
        if nueva == decl:
            continue
        texto = texto.replace(decl, nueva, 1)
        adoptadas.append(funcion)
    if adoptadas:
        avisos.append("**firma adoptada del padre**: " + ", ".join(adoptadas))

    # EL DELEGADO QUE SE USA Y NO SE DECLARA AQUI.
    #
    #     Failed to find delegate function 'UIMenu.OnResult'
    #
    # `delegate<X>` en un PARAMETRO exige que `X` este declarado **en la clase
    # que declara la funcion**, no en cualquier sitio del paquete. Y el
    # descompilador no lo copia: `UIMenu`, `CCBaseController` y `UICharMenu`
    # usan `delegate<OnResult>` y ninguno lo declara.
    #
    # La firma NO se inventa: esta escrita en el paquete, en la clase que si lo
    # declara:
    #
    #     delegate OnResult(UIMessageBoxEx.EMessageBoxResult Result)
    #
    # Asi que se busca en la exportacion y se copia tal cual.
    usados = set(re.findall(r"delegate\s*<\s*([A-Za-z_]\w*)\s*>", texto))
    # Y UN DELEGADO PUEDE TENER TIPO DE RETORNO.
    #
    #     delegate bool OnCellClicked(UIItemGrid Sender, int Index)
    #
    # El patron pedia `delegate` y el NOMBRE seguidos, asi que con un `bool` en
    # medio **no veia la declaracion** -- y entonces creia que faltaba e insertaba
    # una copia, dejando el fichero con DOS declaraciones del mismo nombre:
    #
    #     UIItemGrid.uc(159) : 'OnCellClicked' conflicts with
    #                          'Function CrimeCraftStubs.UIItemGrid:OnCellClicked'
    #
    # **Es la trampa de siempre en este generador** -- un modificador entre la
    # palabra clave y el nombre -- y ya van cuatro: la categoria de un `var`, los
    # modificadores de una firma, los de `DECLARA`, y ahora el tipo de retorno de
    # un `delegate`. Las cuatro veces el sintoma salio LEJOS.
    #
    # Y TAMPOCO HAY QUE PONERLO SI LO DECLARA UN ANCESTRO: SE HEREDA.
    #
    # `UICharMenu` usa `delegate<OnResult>` y no lo declara **en su fichero**,
    # pero extiende `UIMenu`, que si. Con la comprobacion mirando solo el texto
    # propio, se le insertaba una copia -- y con OTRA firma, porque la generica
    # viene de `UIMessageBoxEx`:
    #
    #     UICharMenu.uc(33) : Redefinition of 'delegate OnResult'
    #                        differs from original
    #
    # Se mira el ancestro en su EXPORTACION, no en su stub: cuando se procesa el
    # hijo puede que al padre no le haya tocado turno todavia.
    def lo_usa_un_ancestro(d):
        for a in ancestros(clase):
            ruta = os.path.join(ORIGEN, a + ".uc")
            if not os.path.isfile(ruta):
                continue
            t = io.open(ruta, encoding="utf-8", errors="replace").read()
            if re.search(r"delegate\s*<\s*" + re.escape(d) + r"\s*>", t):
                return True
        return False

    faltan = [d for d in usados
              if not re.search(r"^[^\S\n]*delegate\s+(?:[A-Za-z_]\w*[ \t]+)*"
                               + re.escape(d) + r"\s*\(", texto, re.M)
              and not lo_usa_un_ancestro(d)]
    # NO SE LLAMA `declarados`: ESO YA ES UNA FUNCION de este fichero, y
    # sombrearla da `TypeError: 'list' object is not callable` a 1.000 lineas
    # de distancia. Es la MISMA trampa que `EXTIENDE` hace dos tandas.
    puestos = []
    for d in sorted(faltan):
        firma = firma_de_delegado(d, clase)
        if not firma:
            continue
        # DONDE VA: **DESPUES DE LOS TIPOS**, NO ANTES.
        #
        # La primera version lo ponia antes de la primera declaracion de
        # cualquier clase, y en `UIMenu.uc` esa es `enum EMenuMoveOrder`. Salia:
        #
        #     'Enum' is not allowed here
        #     'Var' is not allowed here
        #
        # que es exactamente lo que dice el analizador cuando el cuerpo `{ ... }`
        # de un delegado se lee como **el final de la clase** y todo lo que viene
        # detras queda fuera. Asi que el problema no era el delegado: era el
        # sitio.
        #
        # Un delegado se declara al nivel de la clase, como un tipo -- y los
        # tipos van antes que las propiedades y las funciones. Ese es el hueco:
        # **antes de la primera `var`, `const`, `function` o `event`, y despues
        # de todos los `enum` y `struct`.**
        #
        # >>> APAGADO, Y AHORA SE SABE POR QUE Y CUANTO.
        #
        # La declaracion FUNCIONA: resuelve los dos `Failed to find delegate
        # function`. Lo que no sale a cuenta es lo que cuesta. Cuatro
        # colocaciones, cuatro medidas, la misma entrada:
        #
        #   apagado ....................................... **17**
        #   antes de la primera `var` de la clase .........  18   (2 resueltos,
        #                                                         3 `'Var' is
        #                                                         not allowed here`)
        #   antes de la primera `function` de la clase ....  20   (2 resueltos,
        #                                                         5 nuevos)
        #   (la version vieja, antes del primer `enum`) ...  47 en su momento
        #
        # Y los nuevos NO son del delegado: son de OTROS ficheros.
        # `UIHudMenu_PlayerInfo.uc(968) : LerpColor: Can't override a 'final'
        # function`, `UIItemGrid.uc(159) : 'OnCellClicked' conflicts with...`,
        # `UIQuasiMode.uc(90) : Illegal array size 1`. O sea: declarar el
        # delegado **mueve el analisis** y destapa cosas que estaban tapadas.
        #
        # Es el mismo genero que el `DependsOn`: el arreglo es correcto y el
        # precio no se entiende. REGLA DE PARADA: se apaga y se anota.
        #
        # Lo que SI se queda es el instrumento: `sitio_de_declaracion()` sabe
        # cual es el unico sitio valido -- nivel de clase, contando llaves -- y
        # esa pregunta ya no hay que volver a hacerla.
        #
        # Y SE VOLVIO A MEDIR EN EL ESTADO DE 9 ERRORES, porque el estado habia
        # cambiado mucho desde la primera vez. **Sale PEOR que antes:**
        #
        #   apagado, a 9 errores .................. **9**
        #   encendido, a 9 errores ................ **12**
        #
        # Cierra los dos que dice cerrar -- `UIMenu.OnResult` y
        # `CCBaseController.OnResult` -- y abre CINCO, todos en otros ficheros:
        #
        #   CCController.uc(703)       Redefinition de ClientSetHUD
        #   UIHudMenu_PlayerInfo.uc    LerpColor: Can't override a 'final' function
        #   UIItemGrid.uc(159)         'OnCellClicked' conflicts consigo mismo
        #   UIMessageBox_Edit.uc(13)   Redefinition de 'delegate OnResult'  <- el
        #                              delegado choca con el de su padre
        #   UIQuasiMode.uc(90)         Illegal array size 1
        #
        # O sea: declarar el delegado **MUEVE EL ANALISIS** y destapa lo que
        # estaba tapado. Es el mismo genero que el `DependsOn`: el arreglo es
        # correcto y el precio no se entiende.
        #
        # >>> TERCERA MEDIDA, a 6 errores: **6 -> 6 otra vez.** Cierra sus dos y
        # abre los dos de la forma sin arreglo. Se apaga.
        #
        # >>> CUARTA MEDIDA, a 5 errores: **5 -> 4. SE QUEDA ENCENDIDO.**
        #
        # La tabla de arriba esta CADUCADA, y la razon es que uno de los dos que
        # abria ya no puede existir. `UIHudMenu_PlayerInfo.uc : LerpColor: Can't
        # override a 'final' function` necesitaba un `LerpColor` FINAL por
        # encima; el unico era `Object.LerpColor`, y la opcion C lo borro.
        #
        #   cierra UIMenu.OnResult + CCBaseController.OnResult ... -2
        #   abre   CCController.ClientSetHUD .................... +1
        #                                                         ---
        #                                                          -1
        #
        # Y LA EXPLICACION VIEJA ERA FALSA: no hay ningun filtro `static` en el
        # recorrido de ancestros (`UnScrCom.cpp:10550` compara nombre y firma, y
        # nada mas). `UIHudMenu_PlayerInfo` no chocaba con `UIMisc.LerpColor`
        # porque **`UIMisc` tiene CERO descendientes** y no estaba en su cadena.
        #
        # Ojo con el bucle: `compila-stubs.sh` NO corre este script. Son dos
        # pasos, y la primera prueba de esto salio identica a la linea base
        # porque el generador no se habia ejecutado.
        if True:
            m = sitio_de_declaracion(texto)
            if m:
                texto = (texto[:m.start()] + chr(9) + firma + chr(10)
                         + texto[m.start():])
                puestos.append(d)
    if puestos:
        avisos.append("**delegado declarado** (copiado del paquete): "
                      + ", ".join(puestos))

    # Las interfaces se normalizan a la forma que usa el SDK.
    #
    # El descompilador emitio `interface CCDoTarget extends Interface` con
    # `abstract` y `native` en lineas aparte, y el compilador lo rechaza con
    # "Missing ';' in 'interface'": `abstract` no vale en una interface. El SDK
    # declara `interface Interface\n\tnative;` y `interface Otra;`, sin `extends`
    # ni `abstract` -- y `extends Interface` es redundante, porque TODA interface
    # extiende de Interface.
    m_int = re.match(r"\s*interface\s+([A-Za-z_]\w*)(?:\s+extends\s+\w+)?[^;{]*;", texto)
    if m_int:
        avisos.append("interface normalizada (sin abstract ni extends redundante)")
        # SIN `native`, y es lo que cierra los tres ultimos errores de `native`.
        #
        # Una interfaz `native` solo la pueden implementar clases `native`:
        #
        #     Non-native classes not allowed to implement native interfaces
        #
        # `RadarPresentInterface_Placable` y compania lo traian de su fuente, y
        # las clases que las implementan no pueden ser native. Se quita, y no se
        # pierde nada: una interfaz de este paquete no tiene cuerpo que
        # implementar en C++, asi que `native` no describia nada real.
        texto = f"interface {m_int.group(1)};\n" + texto[m_int.end():]

    # Referencias a tipos que no existen en ninguna parte: se reescriben a la
    # clase de este paquete que los declara. Ver TIPOS_PERDIDOS.
    # CON FRONTERA DE PALABRA, NO CON `str.replace`.
    #
    # Era `texto.replace(clave, ...)`, y eso casa dentro de palabras mas largas.
    # En cuanto entraron dos tipos de la misma familia --
    # `UIScreenValue_Extent` y `UIScreenValue`-- el segundo reemplazo entro
    # dentro del primero ya sustituido:
    #
    #     var UIScreenValue_Extent NodeHeight;
    #     -> CCStubTipos.UIScreenValue_Extent      (bien)
    #     -> CCStubTipos.CCStubTipos.UIScreenValue_Extent   (encima, mal)
    #
    # El compilador lo dijo con precision: `Unrecognized type 'CCStubTipos'
    # within 'CCStubTipos'`. Es la MISMA doble cualificacion que ya salio una vez
    # con `CCWeaponPreset.CCWeaponPreset.EWeaponDamageType`.
    #
    # Las dos fronteras hacen falta y cada una tapa un caso:
    #   (?<![\w.])  evita entrar detras de un punto -- o sea, en algo ya
    #               cualificado por una vuelta anterior
    #   (?!\w)      evita casar el PREFIJO de un identificador mas largo
    # LA CATEGORIA DE UN `var` NO SE TOCA.
    #
    # `var(Presentation)` es la CATEGORIA del editor, no un tipo. La
    # recualificacion entraba dentro y salia:
    #
    #     var(CCStubTipos.Presentation) noclear const ... UIComp_DrawString X;
    #
    # y un nombre con punto dentro de los parentesis NO es valido:
    #
    #     Missing ')' in ... after editable category
    #
    # Es de sintaxis, asi que PARA al compilador y falsea todos los recuentos de
    # debajo. Se apartan las categorias, se sustituye, y se devuelven.
    categorias = []

    def _aparta(m):
        categorias.append(m.group(1))
        return "var(" + chr(0) + str(len(categorias) - 1) + chr(0) + ")"

    texto = re.sub(r"var\(([^)]*)\)", _aparta, texto)

    # Y LAS DECLARACIONES TAMBIEN, POR LA MISMA RAZON QUE LAS CATEGORIAS.
    #
    # >>> ESTE PATRON SUSTITUYE **TODA** APARICION, y una DECLARACION es una
    # aparicion. `CCSkelControl_SingleBone.uc` declaraba:
    #
    #     export:  struct native SkelControlDestLocation
    #     stub:    struct native CCStubTipos.SkelControlDestLocation
    #
    # y UnrealScript lo rechaza con `struct: 'CCStubTipos' conflicts with class
    # name`. El tipo QUEDABA DECLARADO DOS VECES: bien en `CCStubTipos.uc`, que
    # es donde tiene que estar, y ademas en su clase original con un nombre
    # cualificado, que no es un nombre valido.
    #
    # Se apartan antes de sustituir y se devuelven despues -- que es exactamente
    # lo que ya se hacia con `var(...)` cuatro lineas mas arriba. El caso estaba
    # resuelto al lado; lo que faltaba era aplicarlo a las declaraciones.
    declaraciones = []

    def _aparta_decl(m):
        declaraciones.append(m.group(1))
        return chr(0) + "D" + str(len(declaraciones) - 1) + chr(0)

    texto = re.sub(r"(?m)^([^\S\n]*(?:struct|enum)\b[^;\n]*)", _aparta_decl, texto)

    # >>> Y SOLO EN POSICION DE TIPO, que es el arreglo.
    #
    # Antes esto era un `subn` por cada clave, sobre el texto ENTERO. Una
    # sustitucion que no mira donde escribe toca el NOMBRE de una variable y el
    # de un parametro, y los dos casos pasan de verdad:
    #
    #     local int WeaponCarrySlot;                          (nombre de variable)
    #     SelectTakeHitAnimation(TakeHitInfo TakeHitInfo, …)  (parametro con el
    #                                                          nombre de su tipo)
    #
    # MEDIDO: alojar cinco tipos de golpe con aquello dio 14 -> 16.
    #
    # Ahora se pregunta a `tramos_de_tipo()` DONDE estan los tipos, y se
    # sustituye solo ahi. Las claves dejan de ser patrones y pasan a ser lo que
    # son: **el token que hay en esa posicion**.
    #
    # Y las fronteras de palabra del `subn` ya no hacen falta: el tramo ES el
    # token entero, con sus puntos si los lleva.
    sustituciones, cuenta = [], {}
    for ini, fin, token in tramos_de_tipo(texto):
        nombre = TIPOS_PERDIDOS.get(token)
        if nombre is None:
            continue
        sustituciones.append((ini, fin, CLASE_TIPOS_PERDIDOS + "." + nombre))
        cuenta[token] = cuenta.get(token, 0) + 1
    # De atras hacia adelante: sustituir de delante desplaza las posiciones.
    for ini, fin, nuevo in sorted(sustituciones, reverse=True):
        texto = texto[:ini] + nuevo + texto[fin:]
    for token, n in cuenta.items():
        avisos.append(f"{n} x {token} -> {CLASE_TIPOS_PERDIDOS}.{TIPOS_PERDIDOS[token]} (RECONSTRUIDO)")

    # =====================================================================
    # UN ENUM NATIVO GLOBAL QUE EL DESCOMPILADOR CUALIFICO CON `Actor.`
    #
    #     el stub:  Actor.EDoubleClickDir DoubleClickMove
    #     el SDK:   eDoubleClickDir DoubleClickMove
    #
    # **NO ESTA DECLARADO EN NINGUN `.uc` DEL SDK** -- se busco en los dos
    # arboles -- y sin embargo `PlayerController.uc` lo usa en cinco sitios sin
    # problema: es un **enum NATIVO del motor**, registrado desde C++. Por eso
    # el descompilador, que no veia la declaracion, lo colgo de `Actor`, que es
    # de donde lo hereda el guion.
    #
    # O sea que la grafia del juego es la del SDK, y lo unico que sobra es el
    # cualificador. **No se pierde nada: se quita un prefijo que no existia.**
    #
    # Son 14 apariciones y estan en DOS ficheros --`CCInstanceController` (12) y
    # `CCSavedMove` (2)--, y las dos clases ya estan en la lista de errores.
    texto, n = re.subn(r"(?<![\w.])Actor\.EDoubleClickDir(?!\w)", "eDoubleClickDir", texto)
    if n:
        avisos.append(f"{n} x Actor.EDoubleClickDir -> eDoubleClickDir (el enum es "
                      "NATIVO y global; `Actor.` lo puso el descompilador)")

    for i, d in enumerate(declaraciones):
        texto = texto.replace(chr(0) + "D" + str(i) + chr(0), d)
    for i, c in enumerate(categorias):
        texto = texto.replace("var(" + chr(0) + str(i) + chr(0) + ")", "var(" + c + ")")

    # UNA CLASE NATIVA NO PUEDE HEREDAR DE UNA QUE NO LO ES.
    #
    # Medido con `CCGameObjective extends Objective abstract native`: el
    # compilador lo rechaza. `Objective` existe en Engine/Classes/Objective.uc y
    # alli NO es native -- pero la del motor DEL JUEGO si lo era, y de ahi viene
    # el `native` que el descompilador escribio. Otra vez la deriva de versiones.
    #
    # No se puede arreglar al reves (hacer native la base: es del SDK y no se
    # toca), asi que se quita el `native` de la clase derivada. Es lo menos
    # fiel de todo lo que hace este script, y por eso se avisa.
    # Sin expresion regular: el reemplazo necesitaba un grupo de captura y el
    # grupo se perdia al escribir el fichero desde el shell, que se come las
    # barras invertidas. Partir por lineas no tiene ese problema.
    if clase in NO_PUEDEN_SER_NATIVAS:
        lineas = texto.split(chr(10))
        quitados = 0
        for k, l in enumerate(lineas):
            if l.strip() == 'native' and quitados == 0:
                lineas[k] = l.replace('native', '// native quitado: su superclase del SDK no lo es')
                quitados += 1
            elif 'function' in l and re.search(r'\bnative\b', l):
                # Y hay que quitarselo TAMBIEN A LAS FUNCIONES. Si no:
                # "Only functions of native classes can be declared native".
                lineas[k] = re.sub(r'\bnative\s*', '', l, count=1)
                quitados += 1
        if quitados:
            avisos.append('NATIVE QUITADO (clase y funciones): su superclase del SDK no es native')
        texto = chr(10).join(lineas)

    # LOS CAMPOS VfTable_ LOS CREA EL COMPILADOR, y el descompilador los emitio
    # ademas por su cuenta. Cuando una clase `implements(CCDoTarget)`, el
    # compilador le anade el campo `VfTable_ICCDoTarget` para la tabla virtual de
    # la interfaz; con la declaracion del descompilador encima, choca:
    #
    #   Variable declaration: 'VfTable_ICCDoTarget' already defined
    #
    # Se quitan los declarados. El campo seguira existiendo: lo pone el
    # compilador.
    lineas = texto.split(chr(10))
    vf = [k for k, l in enumerate(lineas)
          if re.match(r'\s*var\b.*\bVfTable_[A-Za-z_0-9]*\s*;', l)]
    if vf:
        for k in reversed(vf):
            del lineas[k]
        avisos.append(f"{len(vf)} VfTable_ retirado(s): los crea el compilador")
        texto = chr(10).join(lineas)
        avisos.append("NATIVE QUITADO: hereda de una clase del SDK que no es native")

    # ---------------------------------------------------------------------
    # `DependsOn(...)`: LA PIEZA QUE FALTABA, Y NO ERA OBVIA
    # con el catalogo -- el coste pasa a depender de lo que el fichero USA.
        # Solo se toca el TOKEN DEL TIPO. Ver `recualifica()` para por que.
    CLASE_ACTUAL = clase
    # Quien declara esta clase, para no cualificar lo que ya es suyo.
    declarados_aqui = declarados(texto)
    DECLARADOS_AQUI = declarados_aqui
    texto, cambios = recualifica(texto)
    if cambios:
        avisos.append(f"{len(cambios)} cualificacion(es) recolocada(s)")
    # ---------------------------------------------------------------------
    #
    # El compilador de guion de UE3 SOLO resuelve un tipo anidado --un enum o un
    # struct declarado DENTRO de una clase-- si esa clase ya se ha compilado. El
    # orden lo fija el nombre del fichero, y el fichero TIENE que llamarse como la
    # clase, asi que no se puede reordenar renombrando: el compilador lo rechaza
    # con "Script vs. class name mismatch".
    #
    # Medido con dos ficheros y nada mas, que es como se supo:
    #
    #     AAAFuente.uc:  var ZZZDestino.EPrueba Valor;
    #     ZZZDestino.uc: enum EPrueba { ... }
    #     -> Error, Unrecognized type 'EPrueba' within 'ZZZDestino'
    #
    # Y con `DependsOn(ZZZDestino)` en la declaracion de AAAFuente:
    #
    #     -> Success - 0 error(s)
    #
    # EL DESCOMPILADOR NO LO EMITE. Es una directiva de COMPILACION: no viaja en
    # el paquete cocinado, asi que no hay forma de recuperarla del `.u`. Solo
    # existe en el fuente, y el fuente no lo tenemos.
    #
    # Esto explica los 119 errores de golpe, y la cascada entera: cada clase que
    # referencia `YakaLayer.EAlgo` -- y YakaLayer empieza por Y -- fallaba, y al
    # fallar impedia compilar las siguientes.
    #
    # Se calcula de las referencias CUALIFICADAS del propio texto: si aparece
    # `Algo.AlgoMas`, se declara dependencia de `Algo`.
    # ---------------------------------------------------------------------
    # EL ORDEN DE ESTA LISTA ES LO QUE MAS PESA DE TODO EL GENERADOR.
    #
    # De `DependsOn(A, B, C)` **solo se registra `A`**: `UnEdFact.cpp:279` busca
    # el texto `dependson(` y toma TODO HASTA EL PARENTESIS como **un** nombre, asi
    # que `"A, B, C"` no es una clase y `FindObject<UClass>` devuelve NULL.
    #
    # Y eso no da un error de dependencia: da que **la clase destino no se
    # analiza**, y sus TIPOS ANIDADOS no existen para nadie:
    #
    #     Unrecognized type 'EMoveDirection' within 'CCController'
    #
    # con `enum EMoveDirection` escrito en la **linea 7** de `CCController.uc`.
    #
    # MEDIDO: poniendo el dueno necesario **el primero** en las 14 clases usuarias
    # que el compilador nombra, el recuento baja de **47 a 20**, los `within` de
    # **14 a 3**, y las `Redefinition` de **13 a 4** -- porque el orden de
    # compilacion cambia con ellos.
    #
    # ASI QUE EL PRIMERO TIENE QUE SER EL QUE HACE FALTA. Y "el que hace falta" es
    # el que declara un tipo anidado que esta clase USA: `CCController.EMoveDirection`
    # es un uso de un tipo anidado, y `DUENOS` ya sabe quien declara cada tipo.
    # ---------------------------------------------------------------------
    refs = [(m.group(1), m.group(2))
            for m in re.finditer(r"\b([A-Z][A-Za-z_0-9]*)\.([A-Za-z_]\w*)", texto)
            if m.group(1) != clase and m.group(1) in CLASES_VALIDAS]
    todos = []
    for dueno, _ in refs:
        if dueno not in todos:
            todos.append(dueno)
    # EL PRIMERO ES EL QUE EL COMPILADOR NOMBRA, y sale de una lista MEDIDA.
    #
    # Se probo a deducirlo --poner delante el dueno de un tipo anidado que la
    # clase usa-- y NO ACIERTA: en `CCPawn` elegia `CCSkelControl_SingleBone`,
    # que aparece antes en el texto, cuando el que hacia falta era `CCController`.
    # Con varios candidatos solo uno puede ir primero, y cual es **no se deduce**.
    # Y VA **SOLO**, SIN COMAS. Es la diferencia que costo dos vueltas: poniendo
    # el dueno primero pero dejando el resto detras,
    #
    #     DependsOn(CCController, CCSkelControl_SingleBone, CCAvatar, ...)
    #
    # `UnEdFact` toma TODO HASTA EL PARENTESIS como **un** nombre, asi que sigue
    # registrando basura y el error sigue: **48 y los 14 `within` intactos**.
    #
    # La forma que funciona --medida, 47 -> 20-- es de **un solo nombre**:
    #
    #     DependsOn(CCController);
    #
    # Las demas dependencias de esas clases se pierden, y es una perdida REAL:
    # el formato no da para mas. Se acepta porque el recuento lo dice.
    # Y EL VALOR DE LA TABLA NO PASABA POR EL FILTRO.
    #
    # Los demas duenos salen de `refs`, que exige `in CLASES_VALIDAS`. El de la
    # tabla se cogia a secas, y por ahi entro el UNICO `DependsOn` del paquete
    # que nombra algo que no esta en el paquete:
    #
    #     CCPlayerReplicationInfo.uc:   DependsOn(GameInfo);
    #
    # `GameInfo` es del `Engine.u` del SDK. `FindClass` lo encuentra -- asi que
    # no da "Failed to find DependsOn" -- pero `AllClasses` es el arbol del
    # paquete QUE SE COMPILA, y `FindNode` devuelve NULL. Y eso es un error
    # contado, aunque no aborte la clase:
    #
    #     Unparsed class 'GameInfo' found while validating DependsOn entries
    #     for 'CCAbilityActions'
    #
    # ...y nombra a `CCAbilityActions` porque llega por la cadena:
    # `CCAbilityActions` -> `CCInstancePawn` -> `CCPlayerReplicationInfo` ->
    # `GameInfo`. Medido: es el UNICO `DependsOn` de los 742 ficheros que
    # nombra algo de fuera, y la UNICA linea de esa familia en el log.
    #
    # Una dependencia entre paquetes no ordena nada: el otro paquete ya esta
    # compilado. Se cae sola.
    # Y SI EL NOMBRE DE LA TABLA NO ES DEL PAQUETE, LA CLASE SE QUEDA **SIN**
    # `DependsOn` -- no se cae a la lista completa.
    #
    # Medido: caer a la lista sube el recuento con fuerza. La tabla manda «una
    # sola» para esas 14 clases, y la razon esta en `UnScrCom.cpp:12788`: por
    # CADA nombre no parseado se recorre su grafo entero con `IsDependentOn`, y
    # ese recorrido **cuenta errores** -- `Unparsed class ...` -- y puede
    # abortar la clase con `circular dependency` o `is derived from`. Cuantos
    # mas nombres, mas grafos.
    #
    # Y para esta clase el nombre de fuera era ademas un NO-OP: `GameInfo` vive
    # en `Engine.u`, que se compila ANTES, asi que ya lleva `CLASS_Parsed` y
    # `UnScrCom.cpp:12802` hace `continue`. Quitarlo deja lo mismo que habia,
    # menos el error que costaba.
    #
    # >>> PROBADO Y REFUTADO EL 30/9. NO SE VUELVE A INTENTAR.
    #
    # `PRIMERO_EN_DEPENDSON["CCPlayerReplicationInfo"] = "GameInfo"` es el UNICO
    # valor de la tabla que nombra una clase que NO es del paquete, y por eso es
    # la unica linea de la familia `Unparsed class` en el log:
    #
    #     Unparsed class 'GameInfo' found while validating DependsOn entries
    #     for 'CCAbilityActions'
    #
    # Se probaron las dos formas de quitarlo, y las dos SALEN PEOR:
    #
    #   el valor de la tabla, tal cual ........................ **21 errores**
    #   la clase sin `DependsOn` ............................. **45 errores**
    #   con el primer dueno del paquete en su lugar .......... **45 errores**
    #
    # Y no es que el nombre importe poco: es que `DependsOn(GameInfo)` **es
    # portante**. Cambiar 24 errores de otros ficheros por tocar una linea no se
    # explica por el nombre -- se explica por el ORDEN, que es lo que ya se midio
    # en el turno 2 (47 -> 21). `ParseScripts` (`UnScrCom.cpp:12832`) recursiona
    # sobre las subclases de cada dependencia, asi que una dependencia de mas
    # reordena el paquete entero.
    #
    # Asi que se deja el error: **cuesta 1 y compra 24**. Va en la familia de
    # «medido y no entendido», con las tres medidas al lado, y NO es un cero del
    # instrumento -- es una cuenta que sube.
    primero = PRIMERO_EN_DEPENDSON.get(clase)
    # UNA DEPENDENCIA A OTRO PAQUETE NO ORDENA NADA -- Y ADEMAS **LANZA**.
    #
    # >>> MEDIDO EL 30/9, LEYENDO EL COMPILADOR. Esto llevaba turnos descrito
    # como «cuesta 1 y compra 23», y era leer un CORTE como una COMPRA:
    #
    #   `ParseScripts` (UnScrCom.cpp:12778) NO tiene try/catch -- comprobado,
    #   entre 12778 y 12900 no hay ninguno. Dentro llama a `IsDependentOn`
    #   (12813), que ante una clase que no esta en su arbol hace
    #   `ScriptErrorf(SCEL_Parse, "Unparsed class ...")` (linea 318).
    #
    #   Y en `ScriptErrorf`, `SCEL_Parse` **deja `bThrow` en TRUE** -- la linea
    #   que lo ponia a FALSE esta COMENTADA. O sea: **lanza**.
    #
    #   El unico `catch` esta FUERA, en quien llamo a `ParseScripts`
    #   (UnScrCom.cpp:13454). Asi que el error **aborta el recorrido entero**.
    #
    # CONSECUENCIA, y es la que importa: **el recuento de errores de este
    # proyecto no es el numero de errores del paquete.** Es el numero de errores
    # encontrados ANTES DE QUE EL RECORRIDO SE CORTE. Todo lo que venga detras de
    # la clase que dispara no se examina -- y por eso `CCWeapon` desaparecio
    # entera cuando la regla del `exec` movio el punto de corte.
    #
    # Y explica de una vez lo que el comentario de abajo daba por no entendido:
    # «registrar una dependencia REAL empeora (69 -> 80)». No empeora: **cambia
    # donde cae el corte.** Los tres caminos de `UnScrCom.cpp:6192` que abortan
    # el arbol con `return 0` no se disparan nunca porque el que se dispara es
    # ESTE, y sale por excepcion.
    #
    # `GameInfo` **no es un fichero del paquete**: esta en la exportacion pero no
    # se stubearon (el motor ya lo declara), asi que no esta en `CLASES`. La
    # entrada de la tabla lo forzaba saltandose el filtro de tipos de mas abajo.
    if primero and primero not in CLASES_VALIDAS:
        if DEPENDSON_DE_OTRO_PAQUETE:
            avisos.append(f"DependsOn FUERA DEL PAQUETE: {primero} (dispara el corte)")
        else:
            avisos.append(f"DependsOn({primero}) NO emitido: no es del paquete")
            primero = None
    duenos_ref = [primero] if primero else todos
    # LA SEGUNDA PALANCA. Ver plan-v2, hipotesis L1. Una compilacion.
    if clase in SEGUNDA_PALANCA:
        duenos_ref = duenos_ref + [SEGUNDA_PALANCA[clase]]
        avisos.append(f"SEGUNDA PALANCA: +{SEGUNDA_PALANCA[clase]}")
    # Y LA ENTRADA DE `GameInfo` VA ADEMAS EN UNA CLASE QUE ORDENA ANTES.
    #
    # >>> MECANISMO, ENCONTRADO. Medido el 30/9.
    #
    # `PRIMERO_EN_DEPENDSON["CCPlayerReplicationInfo"] = "GameInfo"` parecia un
    # NO-OP -- `GameInfo` es del `Engine.u` y ya esta compilado -- y **vale 23
    # errores**. Quitarlo a 7 errores da **30**, y los que vuelven son EXACTAMENTE
    # los 13 `within` que el turno 2 habia cerrado (`AdditionalAnimInfo`,
    # `EServiceType`, `EMusicEventType`, `PlacingItemInfo`, `eHQStatus`...) mas
    # ocho derivas de aridad.
    #
    # Y el `Unparsed class 'GameInfo'` **desaparece**, que es lo que cierra el
    # diagnostico: el mensaje sale de `IsDependentOn` (`UnScrCom.cpp:318`), que
    # recorre el grafo de dependencias del USUARIO y llega a `GameInfo` por
    # `CCPlayerReplicationInfo->DependentOn`.
    #
    # O sea que la entrada hace DOS cosas a la vez:
    #
    #   1. mete `GameInfo` en el grafo, y de ahi el error -- cuesta 1;
    #   2. **fuerza su analisis** dentro del arbol del paquete, y eso REORDENA la
    #      compilacion entera a favor. Compra 23.
    #
    # El error sale de (1) y el beneficio de (2), y son separables: el mensaje se
    # dispara porque `AllClasses.FindNode(GameInfo)` es NULL **cuando el usuario
    # se compila**. Si `GameInfo` ya estuviera en el arbol para entonces, no
    # habria mensaje y el reordenamiento seguiria.
    #
    # Y SE PROBO A SEPARARLOS, PONIENDO LA MISMA DEPENDENCIA EN UNA CLASE QUE
    # ORDENA ANTES (`CCAbilityActions`, 'CCA' < 'CCP'), pensando que esa lo
    # analizaria primero y que cuando llegara `CCPawnWeaponAttachment` el nodo ya
    # existiria.
    #
    # >>> REFUTADO. **7 -> 7**, y el `Unparsed class` **no desaparece**.
    #
    # El mensaje no se quita: **se MUEVE**. Sale del PRIMER recorrido del grafo
    # que llega a `GameInfo`, y anadir otro sitio desde el que recorrer solo
    # cambia cual es ese primero. Es intrinseco a tener el nombre en cualquier
    # `DependentOn` que se recorra.
    #
    # (Y ojo al contarlo: `grep -c "Unparsed class"` da DOS por cada error -- la
    # linea cruda y la del resumen. Contarlas como dos errores fue un error mio
    # de lectura, y la primera version de este comentario lo decia mal.)
    #
    # Asi que no se puede separar: **el error es el precio, y no hay forma de
    # pagar solo el beneficio.** Cuesta 1 y compra 23.
    for extra in ADEMAS_EN_DEPENDSON.get(clase, ()):
        if extra in CLASES_VALIDAS and extra not in duenos_ref:
            duenos_ref.append(extra)
            avisos.append(f"DependsOn: +{extra} (medida)")
    # =====================================================================
    # DEPENDSON: ABIERTO, Y ESTA EN LA FORMA DE LA COMA A PROPOSITO
    #
    # Se investigo a fondo y NO SE ENTENDIO. Lo que esta medido:
    #
    #   1. El compilador de guion (`UnScrCom.cpp:4189`) acepta `DependsOn` UNA
    #      vez como modificador: lee UN identificador y luego exige `)`.
    #      Repetirlo da `Unexpected 'DependsOn'`. PROBADO.
    #
    #   2. La lista que de verdad se consulta (`UClass::DependentOn`) la
    #      rellena `UnEdFact.cpp:279`, y NO parsea: busca el TEXTO `dependson(`
    #      -- `appStrfind`, que no distingue mayusculas -- en todo el fichero y
    #      toma TODO HASTA EL PARENTESIS como UN nombre. Con comas, el nombre
    #      que registra es `"A, B, C"`, que no es una clase.
    #
    #   3. `UnScrCom.cpp:6192` ABORTA el arbol entero -- `return 0` -- si la
    #      dependencia es una clase base tuya, o si ya se parseo.
    #
    #   4. Y aqui esta lo que NO cuadra: con la forma de la coma salen **69**
    #      errores y con los nombres de verdad **80**, sin error de sintaxis en
    #      ninguno de los dos, y **con CERO mensajes de `dependson` en el log**.
    #
    # El punto 4 se comprobo dos veces. Si el metalenguaje del (2) estuviera
    # rellenando la lista, la coma daria `Unknown class ... dependson` y el
    # `return 0` del (3) pararia la compilacion -- no hay tal mensaje. Si no la
    # rellenara, las dos formas serian iguales -- y no lo son.
    #
    # NO SE SABE POR QUE. Y por eso se deja la forma que da 69: no porque sea
    # mejor, sino porque es la que se ha medido mas veces y la que menos afirma.
    # Cambiarla sin entenderla seria quedarse con un numero mejor sin saber de
    # que.
    # OJO: aqui apuntaba a `tools/_prueba-dependson.py`, y ese fichero NO EXISTE
    # (comprobado el 2/10). Si alguien lo tuvo, no se conservo. El experimento
    # hay que rehacerlo desde cero -- y el punto de partida esta en
    # `PROCESSED-session/hipotesis-refutadas.md`, que es donde vive por que se
    # descarto cada forma.
    # =====================================================================
    # UN ANCESTRO NO ES UNA DEPENDENCIA: ES UN ERROR.
    #
    # `UnScrCom.cpp:6204` lo dice con esas palabras -- "please remove the
    # dependson" -- y ademas hace `return 0`, que PARA EL ARBOL ENTERO. Las 20
    # referencias que caen aqui envenenaban las otras 521.
    fuera = ancestros(clase)
    if fuera:
        quitados = [d for d in duenos_ref if d in fuera]
        duenos_ref = [d for d in duenos_ref if d not in fuera]
        if quitados:
            avisos.append(f"{len(quitados)} dependencia(s) a un ancestro RETIRADA(s): "
                          + ", ".join(quitados))

    if duenos_ref:
        # UN `DependsOn` CON NOMBRE, Y EL RESTO COMO TEXTO.
        #
        # Hay DOS analizadores y no coinciden:
        #
        #   UnScrCom.cpp:4189   acepta `DependsOn` UNA vez como modificador:
        #                       lee UN identificador y luego exige `)`.
        #                       Repetirlo da `Unexpected 'DependsOn'`. PROBADO.
        #
        #   UnEdFact.cpp:279    es quien RELLENA la lista, y NO parsea: busca el
        #                       TEXTO `dependson(` -- `appStrfind`, que no
        #                       distingue mayusculas -- y toma TODO HASTA EL
        #                       PARENTESIS como UN nombre. Con comas registra el
        #                       literal `"A, B, C"`, que no es una clase: **solo
        #                       surte efecto el PRIMERO**, y los demas se
        #                       pierden en silencio.
        #
        # Medido: `DependsOn(CCController)` a secas en CCPawn quito su error de
        # `EMoveDirection` de golpe; con la lista de ocho nombres, no.
        #
        # Asi que va una linea con el primer nombre -- lo que UnScrCom exige -- y
        # el resto como texto que UnScrCom ignora por estar comentado y UnEdFact
        # encuentra igual, porque no mira si es codigo.
        # ---------------------------------------------------------------
        # Y AQUI ESTA LO QUE NO SE ENTIENDE. TRES FORMAS, MEDIDAS:
        #
        #   `DependsOn(A, B, C);`                     ->  **69 errores**
        #   `DependsOn(A);`  (un nombre valido)       ->  **80 errores**
        #   `DependsOn(A);` + el resto como texto     ->  **80 errores**
        #
        # Y con el filtro de ancestros puesto -- que quita las 20 referencias que
        # el propio compilador llama error -- **80 tambien**. No son los ancestros.
        #
        # En las tres, **CERO mensajes de `dependson` en el log**: ni `Unknown
        # class ... dependson`, ni `circular dependency`, ni `is derived from`.
        # Los TRES caminos de `UnScrCom.cpp:6192` que abortan el arbol con
        # `return 0` no se disparan nunca.
        #
        # O sea: registrar una dependencia REAL empeora, y no se sabe por que.
        # Lo unico que encaja con las tres medidas es que la coma no registre
        # nada Y ADEMAS cambie el analisis de la cabecera -- `UnScrCom.cpp:4193`
        # lee UN identificador y luego exige `)` -- pero eso dejaria un mensaje,
        # y no lo deja.
        #
        # SE DEJA LA COMA. No porque sea mejor: porque es la que da 69, la que
        # esta medida mas veces, y la que MENOS AFIRMA. Los numeros mejores que
        # no se entienden son justo los que este proyecto persigue.
        # ---------------------------------------------------------------
        fin = texto.index(";")
        texto = (texto[:fin] + chr(10) + chr(9) + "DependsOn("
                 + ", ".join(duenos_ref) + ")" + texto[fin:])
        avisos.append(f"DependsOn({len(duenos_ref)})")

    # ---------------------------------------------------------------------
    # LA CUALIFICACION QUE FALTA
    # ---------------------------------------------------------------------
    #
    # Un tipo anidado en OTRA clase se referencia cualificado --`Dueno.Tipo`--,
    # pero el descompilador emitio muchos a secas: `AIAbilityEffect` donde el
    # compilador necesita `CCAISharedTypes.AIAbilityEffect`. Se supo porque el
    # compilador nombro el tipo y el analisis dijo en que fichero se declara.
    #
    # Se recoloca el dueno SOLO si el tipo no esta declarado en este mismo
    # fichero y no es del SDK: en esos dos casos ya resuelve solo.
    # SE RECORREN LOS IDENTIFICADORES QUE ESTAN EN EL TEXTO, no el catalogo.
    #
    # La version anterior hacia `for t, dueno in DUENOS.items()` y dos
    # expresiones por tipo: unos 800 tipos por 487 clases, casi un millon de
    # barridos sobre textos de hasta 450 KB. Eso era el grueso de los MINUTOS
    # que tarda el generador -- el trabajo por fichero, medido, son 1,1 segundos
    # en los 1.668.
    #
    # Dando la vuelta -- sacar los identificadores del texto una vez e intersecar

    # MODIFICADORES QUE EL DESCOMPILADOR PUSO DONDE NO VALEN.
    #
    # `local editinline AudioComponent AC;` -- `editinline` describe una
    # PROPIEDAD que se edita en linea, y en una variable local el compilador lo
    # rechaza:
    #
    #     Specified type modifiers not allowed here
    #
    # Se quitan solo de los `local`. En un `var` si valen.
    lineas = texto.split(chr(10))
    tocadas = 0
    for k, l in enumerate(lineas):
        bajo = l.lstrip()
        if bajo.startswith("local ") and ("editinline" in bajo or "instanced" in bajo):
            for mod in ("editinline ", "editinlinenew ", "editinline", "instanced "):
                l = l.replace(mod, "")
            lineas[k] = l
            tocadas += 1
    if tocadas:
        avisos.append(f"{tocadas} `local` sin modificadores de propiedad")
        texto = chr(10).join(lineas)

    # LOS `const` QUE APUNTAN A OTRA CLASE.
    #
    # Va ANTES de los ARTEFACTOS y no es indiferente: aquel bucle sustituye por
    # expresion regular y no consulta nada. Este tiene que MIRAR el valor en la
    # clase que lo presta, asi que no cabe en `ARTEFACTOS` y va aparte.
    #
    # Si no se puede resolver, la linea SE DEJA y se avisa. Dejarla da un error
    # de sintaxis, que es feo pero es HONESTO; inventarse un valor daria un
    # numero equivocado que compila, y eso no se nota hasta que algo se comporta
    # mal en tiempo de ejecucion.
    resueltos, sin_resolver = 0, []
    for m in list(SOLO_EN_CONST.finditer(texto)):
        sangria, nombre, clase, miembro = m.groups()
        vals = CONSTS.get(clase.lower())
        valor = vals.get(miembro) if vals else None
        if valor is None:
            sin_resolver.append(f"{nombre} <- {clase}.{miembro}")
            continue
        texto = texto.replace(
            m.group(0), f"{sangria}const {nombre} = {valor};")
        resueltos += 1
    if resueltos:
        avisos.append(f"{resueltos} `const` resuelto(s) desde otra clase")
    if sin_resolver:
        avisos.append("**const SIN RESOLVER**: " + "; ".join(sin_resolver))

    # EL TAMANO DE LOS ARRAYS CUYO ENUM NO SIRVE PARA DIMENSIONAR.
    #
    # Sobre la tabla, y no sobre `[E<Algo>]` en general: de las 30 declaraciones
    # de esta forma que hay en el paquete, 25 compilan. Un patron que las tocara
    # todas cambiaria cosas que funcionan, y el tamano de un array de una clase
    # `native` es LAYOUT -- lo comprueba `native-class-size-check`.
    arreglados, sin_evidencia = [], []
    for m in list(ARRAY_POR_ENUM.finditer(texto)):
        sangria, clase_kw, medio, nombre, enum, fin = m.groups()
        if enum not in ENUMS_QUE_NO_DIMENSIONAN:
            continue
        tam = tamano_de_array(texto, m.end(), nombre)
        if tam is None:
            # SIN EVIDENCIA se pone el MINIMO LEGAL, y se avisa. Inventarse un
            # numero mas grande daria un array que compila y miente sobre el
            # layout; dejarlo sin arreglar daria un error de compilacion. El
            # minimo es lo unico que no afirma nada que no se sepa.
            tam = 2
            sin_evidencia.append(f"{enum}({nombre})")
        # EL NOMBRE VA EN EL REEMPLAZO, y estuvo fuera: la primera version
        # escribio `var UITexture [5];` -- sin `Images` -- porque el grupo del
        # nombre no se usaba. Una declaracion sin nombre es un error de
        # sintaxis, asi que el compilador se paro, y el recuento se quedo
        # clavado en 73 sin decir por que.
        texto = texto.replace(
            m.group(0), f"{sangria}{clase_kw}{medio} {nombre}[{tam}]{fin}")
        arreglados.append(f"{enum}->{tam}")
    if arreglados:
        avisos.append("tamano de array explicito: " + ", ".join(sorted(set(arreglados))))
    if sin_evidencia:
        avisos.append("**tamano SUPUESTO (minimo legal, sin defaults)**: "
                      + ", ".join(sin_evidencia))

    for pat, rep in ARTEFACTOS:
        texto, n = pat.subn(rep, texto)
        if n:
            avisos.append(f"{n} artefacto(s) de extraccion tratado(s)")

    # Cuantos artefactos siguen SIN comentar. Se cuentan de verdad en vez de
    # mirar si la cadena aparece: la cadena sigue apareciendo dentro del
    # comentario que acabamos de escribir, y eso daba un falso positivo en todas
    # las clases.
    sin_comentar = sum(
        1 for linea in texto.splitlines()
        if "Array type was not detected" in linea and not linea.lstrip().startswith("//")
    )
    if sin_comentar:
        avisos.append(f"OJO: {sin_comentar} 'Array type was not detected' SIN comentar")

    # =====================================================================
    # EL PAQUETE SE LLAMA `CrimeCraftStubs`, Y EL CODIGO DICE `CrimeCraft.`
    #
    # VA AL FINAL, y es deliberado: asi lo que cambie en la regeneracion es
    # atribuible a esta regla y a ninguna otra. Ninguna de las de arriba mira el
    # nombre del paquete --`DependsOn` emite NOMBRES DE CLASE, `recualifica()`
    # solo mira `var`/`local` y firmas, y `tramos_de_tipo()` no entra dentro de
    # un literal-- asi que el orden no cambia el resultado; pero puesto al
    # principio, cualquier interaccion futura seria invisible.
    #
    # El porque y las medidas, en `reescribe_paquete()`.
    # =====================================================================
    # LOS CASTS A `int` QUE SOBRAN. Ver `quita_casts_int()`.
    #
    # VA APARTE DEL PAQUETE y antes que el, para que el diff de una regeneracion
    # se pueda leer por reglas. No interfieren: una toca `CrimeCraft.` y la otra
    # `int(`.
    texto, n_casts, dejados = quita_casts_int(texto)
    if n_casts or dejados:
        CASTS_INT[clase or CLASE_ACTUAL] = (n_casts, dejados)

    # Y EL PRE-OPERADOR SIN PARENTESIS, que ademas era lo que tumbaba la
    # compilacion. Ver `parentiza_preoperador()`.
    texto, n_pre, dej_pre = parentiza_preoperador(texto)
    if n_pre or dej_pre:
        PREOPERADOR[clase or CLASE_ACTUAL] = (n_pre, dej_pre)

    # Y EL `goto` DE `foreach`, que ademas era lo que disparaba la asercion.
    # Ver `arregla_goto_foreach()`.
    texto, n_gf, d_gf = arregla_goto_foreach(texto)
    if n_gf:
        GOTO_FOREACH[CLASE_ACTUAL] = (n_gf, d_gf)

    texto, n_paquete = reescribe_paquete(texto)
    if n_paquete:
        # `CLASE_ACTUAL`, **NO `clase`**. Y no es un detalle: `clase` YA NO ES el
        # nombre de esta clase cuando se llega aqui.
        #
        # En la resolucion de `const` prestados (mas arriba) hay
        #
        #     sangria, nombre, clase, miembro = m.groups()
        #
        # que REASIGNA el parametro: a partir de ahi `clase` es "la clase DE LA
        # QUE SE TOMA PRESTADO el valor". No rompia nada porque todos los usos
        # legitimos estan ANTES -- hasta que se añade una regla al final, que es
        # justo lo que es esto.
        #
        # Costo encontrarlo: el sintoma era que 2 de las 268 clases se
        # contabilizaban con el nombre de otra, y `clase` es una CELDA (la lee
        # `lo_usa_un_ancestro`), asi que STORE_DEREF en vez de STORE_FAST. La
        # pista de la celda llevaba a buscar un `nonlocal` que no existe: el
        # reenlazado es un DESEMPAQUETADO DE TUPLA, y ahi no hay `nonlocal` que
        # valga.
        #
        # `CLASE_ACTUAL` se fija al principio y no se toca despues: es el unico
        # nombre que sigue siendo el de la clase al llegar al final.
        PAQUETE_REESCRITO[CLASE_ACTUAL] = n_paquete

    return texto, avisos


def toma_rutas(argv):
    """Saca `--origen` y `--sdk` de `argv` y rehace lo que colgaba de ellas.

    POR QUE ASI Y NO CON argparse
    -----------------------------
    El programa **ya lee `sys.argv` a mano** en varios sitios (`--dry-run`, y una
    lista de clases como posicional). Meterle argparse entero seria tocar lo que
    funciona. Aqui solo se **retiran los dos argumentos nuevos** y se recalculan
    las tres constantes que derivaban de ellos.

    Y las dos rutas eran el unico atajo a ESTE arbol: sin ellas, `ORIGEN` apunta a
    una carpeta que en otro repo no existe -- y el programa ya lo dice y sale con
    1, que es la conducta correcta (mejor un error que un cero silencioso).
    """
    global ORIGEN, SDK, DATOS, LISTA_CLASES, DESTINO, PAQUETE_NUEVO, PAQUETE_VIEJO
    for clave in ("--origen", "--sdk", "--datos"):
        for i, a in enumerate(argv):
            if a == clave and i + 1 < len(argv):
                valor = argv[i + 1]
                del argv[i:i + 2]
                if clave == "--origen":
                    ORIGEN = valor
                elif clave == "--sdk":
                    SDK = valor
                else:
                    DATOS = valor
                break
    # `LISTA_CLASES` se DERIVA en el nivel del modulo, asi que se recalcula aqui.
    # Olvidarlo deja la constante apuntando al sitio viejo: el cambio de `--datos`
    # no llega, y el error que sale es un `FileNotFoundError` de un fichero que
    # SI existe -- en otro directorio.
    LISTA_CLASES = os.path.join(DATOS, "clases-del-mapa.txt")
    DESTINO = os.path.join(SDK, "CrimeCraftStubs", "Classes")
    PAQUETE_NUEVO = os.path.basename(os.path.dirname(DESTINO))
    PAQUETE_VIEJO = os.path.basename(ORIGEN)


def main():
    toma_rutas(sys.argv)
    simular = "--dry-run" in sys.argv
    if not os.path.isdir(ORIGEN):
        print(f"no existe {ORIGEN}")
        return 1

    # `sdk` significa, en todo el programa, "el motor ya tiene esto". Se le
    # suman los nombres nativos, porque `tipos_del_sdk()` solo ve `.uc` y las
    # clases `noexport` no tienen. Ver `nombres_del_motor()`.
    sdk = tipos_del_sdk() | nombres_del_motor() | SOMBREAN_AL_MOTOR
    dueno = duenos()
    # Un tipo que falta puede no ser un fichero: se traduce a quien lo declara.
    nombrados, sin_dueno = [], []
    for t in TIPOS_QUE_FALTA:
        if t in dueno:
            nombrados.append(dueno[t])
        else:
            sin_dueno.append(t)
    # Una lista distinta se puede pasar por linea de ordenes. Ver lee_clases().
    otra = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    base = sorted(set(lee_clases(otra) + nombrados))

    # NADA QUE EL SDK YA DECLARE SE STUBEA.
    #
    # La clausura ya evitaba anadir superclases que el SDK tuviera, pero el
    # conjunto BASE --lo que importan los mapas-- no se filtraba, y por ahi se
    # colaron dos: `Interface` y `SeqCond_IsAlive`. Un stub con el nombre de una
    # clase que ya existe no la sustituye: la SOMBREA, y el motor se queda con la
    # equivocada.
    #
    # El sintoma fue preciso: `CrimeCraftStubs.CCDoTarget's superclass must be
    # Core.Interface, not CrimeCraftStubs.Interface`. `CCDoTarget` extendia del
    # `Interface` del SDK, y el paquete habia traido otro con el mismo nombre.
    choca = [c for c in base if c in sdk]
    if choca:
        print(f"fuera por chocar con el motor: {', '.join(choca)}")
        base = [c for c in base if c not in sdk]
    if sin_dueno:
        print(f'tipos sin declaracion en la exportacion: {sin_dueno}')

    # `disponibles` es lo que la clausura PUEDE anadir, y excluye las clases que
    # UE Explorer exporto como simple referencia. Se distinguen por su forma:
    # son declaraciones adelantadas sueltas. `ByteProperty`, `Class`, `UIButton`,
    # `UIScene` -- medio millar -- salieron asi, y son de Core y Engine, no de
    # CrimeCraft. Incluirlas habria declarado un segundo `ByteProperty` en el
    # paquete. Las tres de RECONSTRUIDAS son la excepcion: si son de CrimeCraft.
    disponibles = set()
    for f in os.listdir(ORIGEN):
        if not f.endswith(".uc"):
            continue
        nombre = f[:-3]
        t = io.open(os.path.join(ORIGEN, f), encoding="utf-8", errors="replace").read()
        # LA DISTINCION, Y ANTES NO ESTABA.
        #
        # Una declaracion adelantada suelta puede ser dos cosas MUY distintas:
        #   - una clase AJENA que el paquete importa --`ByteProperty`, `Class`,
        #     `UIButton`--, de la que UE Explorer dejo una referencia. Meterla
        #     seria declarar un segundo `ByteProperty` en el paquete.
        #   - una clase DEL JUEGO cuyo cuerpo no se recupero, y que el guion usa
        #     de verdad: `UIComp_DrawString`, `UIScreenObject`, `UIImage`.
        #
        # El discriminante es SI EL SDK LA DECLARA YA. Si la declara, es ajena
        # y sobra; si no, es un hueco y hay que reconstruirla.
        #
        # Antes se excluian TODAS, y por eso las del segundo tipo no se generaban
        # nunca: el compilador las nombraba, el cierre no las traia, y la lista de
        # reconstruidas no servia de nada porque el fichero no se escribia.
        if (SOLO_ADELANTADA.match(t.lstrip(chr(0xFEFF)))
                and nombre not in RECONSTRUIDAS
                and nombre in sdk):
            continue
        disponibles.add(nombre)
    print(f"con definicion propia:       {len(disponibles)}")

    CLASES, sin_fuente = clausura(base, sdk, disponibles, dueno)
    print(f"tipos que el motor ya tiene: {len(sdk)}")
    print(f"importadas por los mapas:   {len(base)}")
    print(f"tras cerrar las superclases: {len(CLASES)}")
    if sin_fuente:
        print(f"sin fuente extraida:         {len(sin_fuente)} -> {', '.join(sin_fuente)}")
    print()

    if not simular:
        os.makedirs(DESTINO, exist_ok=True)

    # EL DESTINO REFLEJA LA LISTA, no se le suma. Con la lista vieja de 19 aqui
    # quedaban ficheros de clases que la lista nueva ya no pide --CCClubSitableLogic
    # entre ellas--, y se compilaban igual: el compilador lee la CARPETA, no la
    # lista. Un stub obsoleto no es inocuo, porque arrastra sus propios tipos sin
    # resolver y hace fallar la compilacion por una clase que nadie importa.
    obsoletos = []
    if os.path.isdir(DESTINO):
        for f in sorted(os.listdir(DESTINO)):
            if f.endswith(".uc") and f[:-3] not in CLASES:
                obsoletos.append(f)
                if not simular:
                    os.remove(os.path.join(DESTINO, f))

    # SOLO las de ESTE paquete. Las del SDK ya estan compiladas y no hacen
    # falta en DependsOn; y un nombre de PAQUETE --`Engine`, `Core`-- no es
    # una clase: el compilador lo rechaza con 'Unparsed class'.
    CLASES_VALIDAS.clear()
    CLASES_VALIDAS.update(CLASES)
    # Y CCStubTipos, QUE NO ESTA EN `CLASES`. Se escribe aparte, fuera del bucle,
    # porque no viene de la exportacion. Sin anadirla aqui, la recualificacion
    # la nombra --`CCStubTipos.EItemType`-- pero `DependsOn` la IGNORA, porque
    # su filtro es `in CLASES_VALIDAS`. El compilador lo dijo asi:
    #     Unrecognized type 'EItemType' within 'CCStubTipos'
    CLASES_VALIDAS.add(CLASE_TIPOS_PERDIDOS)
    DUENOS.clear()
    DUENOS.update({k: v for k, v in dueno.items() if k not in CLASES})

    # Los `const` de TODA la exportacion, no solo de las clases del cierre: una
    # clase puede pedir prestado el valor de otra que no se stubea, y el valor
    # esta igual. `CCInstanceController` lo hace con `YakaLayer`, que si entra;
    # pero el mapa se construye entero porque el coste es el mismo.
    CONSTS.clear()
    CONSTS.update(consts())
    PAQUETE_REESCRITO.clear()
    CASTS_INT.clear()
    PREOPERADOR.clear()
    GOTO_FOREACH.clear()

    # Quien hereda de quien, para no declarar dependencia de un ancestro: el
    # compilador lo trata como error y aborta el arbol. Ver PADRES.
    PADRES.clear()
    PADRES.update(padres())

    # Quien es interfaz, leido del fuente. Ver ES_INTERFAZ.
    ES_INTERFAZ.clear()
    ES_INTERFAZ.update(interfaces_declaradas())

    # Y LAS INTERFACES TAMPOCO, con su motivo: una interfaz `native` solo la
    # pueden implementar clases `native`, y las de aqui no lo son. Pero quitarle
    # el `native` a la interfaz NO BASTA -- sus `native function` de dentro
    # pasan a ser ilegales:
    #
    #     Only functions of native classes can be declared native
    #
    # Asi que van por el MISMO camino que las clases: se les quita el `native` a
    # la declaracion y a sus funciones. Se supo midiendo: quitar solo el de la
    # interfaz subio el recuento de 51 a 52.
    NO_PUEDEN_SER_NATIVAS.update(ES_INTERFAZ)

    # Y quien no puede ser `native`, por la misma regla que antes habia que
    # descubrir compilando. Ver no_pueden_ser_nativas().
    # NO SE DERIVA. Ver el comentario de NO_PUEDEN_SER_NATIVAS: se intento, se
    # midio, y sale PEOR. Se queda la lista corta y medida.
    #
    # NO_PUEDEN_SER_NATIVAS.clear()
    # NO_PUEDEN_SER_NATIVAS.update(no_pueden_ser_nativas())
    print(f"interfaces declaradas o heredadas: {len(ES_INTERFAZ)}")

    # TIPOS PERDIDOS CUYA FORMA SE SABE POR LOS `defaultproperties`.
    #
    # Solo los que el paquete USA de verdad: hay 97 tipos con forma deducible en
    # la exportacion, y meterlos todos llenaria `CCStubTipos` de structs que
    # nadie nombra -- y alguno podria chocar con un nombre que ya existe.
    #
    # Se miran los textos de las clases que se van a escribir, que es donde
    # salen las referencias.
    formas = formas_de_los_defaults()
    dichos = set()
    for clase in CLASES:
        ruta = os.path.join(ORIGEN, clase + ".uc")
        if os.path.isfile(ruta):
            dichos |= set(re.findall(r"\b([A-Z]\w+)\b",
                                     io.open(ruta, encoding="utf-8",
                                             errors="replace").read()))
    # Y LOS QUE SOLO TIENE EL MOTOR DEL JUEGO, con sus miembros y su orden.
    DE_QUE_STRUCT.clear(); DE_QUE_STRUCT.update(de_que_struct())
    tj, mj, sin_tipar = tipos_del_juego()
    # Y LOS NOMBRES QUE SOLO ESTAN EN LAS TABLAS, NO EN NINGUN `.uc`.
    #
    # `dichos` se construye leyendo los TEXTOS de las clases, que es donde
    # salen las referencias. Pero hay tipos que solo nombra el `FPropertyTag`:
    # `TextAutoScaleValue` no aparece en ningun `.uc` exportado y si es miembro
    # de `UICombinedStyleData`. Sin anadirlo, `UICombinedStyleData` se declaraba
    # con un tipo que no existe, y eso **aborta `CCStubTipos` entero** -- con lo
    # que TODO lo que va detras en el fichero deja de existir, y salen trece
    # `Unrecognized type ... within 'CCStubTipos'` que parecen trece problemas
    # y son uno.
    #
    # Medido: sin esto, 17 -> 20. Con esto, los trece de golpe.
    #
    # Y SE CIERRA **DESDE LO QUE EL PAQUETE YA USA**, NO DESDE EL CATALOGO
    # ENTERO. La primera version metia todos los nombres del catalogo y con
    # ellos entro el universo de structs de Beast -- lightmass, que no tiene
    # nada que ver con la UI --: 90 tipos declarados y `CCStubTipos` abortado
    # por `BeastMaterialInstancePropertiesOverrides`, con 20 errores `within`
    # encima. **27 errores frente a 17.**
    #
    # La cascada se para donde tiene que pararse: en lo que este paquete
    # necesita de verdad, siguiendo la tabla miembro a miembro.
    por_dentro = {}
    for (contenedor, miembro), destino in DE_QUE_STRUCT.items():
        por_dentro.setdefault(contenedor, []).append((miembro, destino))
    cola = list(dichos)
    while cola:
        t = cola.pop()
        for _miembro, destino in por_dentro.get(t, ()):
            if destino not in dichos:
                dichos.add(destino)
                cola.append(destino)
        for _nombre, tipo in mj.get(t, ()):
            base = tipo.split("<")[-1].rstrip(">")
            if base not in dichos:
                dichos.add(base)
                cola.append(base)
    TIPO_DEL_JUEGO.clear(); TIPO_DEL_JUEGO.update(tj)
    MIEMBROS_DEL_JUEGO.clear(); MIEMBROS_DEL_JUEGO.update(mj)
    del_juego, no_tipables, candidatos = [], set(), set()
    for t in sorted(dichos):
        if (t in sdk or t in disponibles or t in CLASES or t in dueno
                or t in TIPOS_PERDIDOS or t not in TIPO_DEL_JUEGO):
            continue
        # DE UN ENUM SE SABE QUE EXISTE, PERO NO SUS MIEMBROS.
        #
        # Los ENUMERADORES no son exportaciones: van dentro del enum, y la tabla
        # de exportaciones no los lista. Asi que declararlo desde el catalogo da
        # un enum VACIO:
        #
        #     Enumeration must contain at least one enumerator
        #
        # Y ademas rompe los arrays dimensionados por el --`CellImage[EGridCellState]`
        # pasa a `Bad or missing array size`-- porque el tamano sale del numero de
        # miembros.
        #
        # Los enums se siguen sacando de `MIEMBROS_PERDIDOS`, que se dedujo de los
        # USOS (`CIT_`, `CH_`). MEDIDO: tomarlos del catalogo sube el recuento de
        # 21 a 29.
        if TIPO_DEL_JUEGO[t] == "Enum":
            continue
        if any(d == t for d, _ in sin_tipar):
            no_tipables.add(t)
            continue
        candidatos.add(t)

    # Y EL CIERRE: UN TIPO SOLO SE DECLARA SI **TODO** LO QUE NECESITA SE DECLARA.
    #
    # No es simetria: es que `CCStubTipos` es UN SOLO FICHERO y **un tipo sin
    # resolver ABORTA LA CLASE ENTERA**. Todo lo que va detras en ese fichero
    # deja de existir, y el compilador lo cuenta como un `Unrecognized type ...
    # within 'CCStubTipos'` por cada uso. Medido: con 90 tipos declarados y un
    # punado sin resolver, 20 errores `within` que parecen veinte problemas y
    # son uno.
    #
    # Por eso la regla no es «este tipo se puede declarar», es «este tipo y toda
    # su cadena». Se aplica hasta que no cambie nada.
    #
    # Es la misma regla que ya estaba escrita -- «si un miembro no se sabe
    # tipar, no se declara el tipo entero, a medias mentiria sobre el layout» --
    # un paso mas alla.
    primitivos = set(PROPIEDAD_A_TIPO.values()) | {"byte", "int", "float", "bool",
                                                   "name", "string", "Object"}
    while True:
        fuera = set()
        for t in candidatos:
            for _nombre, tipo in MIEMBROS_DEL_JUEGO.get(t, []):
                base = tipo.split("<")[-1].rstrip(">")
                # `TIPOS_PERDIDOS` cuenta como declarado: esos van a
                # `CCStubTipos` igual, y algunos -- `UIScreenValue_Extent` --
                # ya estaban ahi antes de este turno.
                if (base in primitivos or base in sdk or base in CLASES
                        or base in disponibles or base in candidatos
                        or base in TIPOS_PERDIDOS):
                    continue
                fuera.add(t)
                break
        if not fuera:
            break
        candidatos -= fuera
        for t in sorted(fuera):
            no_tipables.add(t)

    # Y UN TIPO ALOJADO A MANO QUE SEA STRUCT: sus miembros, del LITERAL.
    #
    # El catalogo no basta cuando un miembro es `StructProperty` -- el tipo va en
    # el `FPropertyTag` -- y para `SkelControlDestLocation` la tabla no lo tiene,
    # porque su `Default__` no lo serializa. Pero el guion SI escribe el valor:
    #
    #     IKLerpingLocation=(Type=EDT_World, SocketName="None",
    #                        Translation=(X=0,Y=0,Z=0), Rotation=(Pitch=0,...))
    #
    # `formas_de_los_defaults()` ya sabe leer eso -- un literal da los miembros,
    # su orden y el tipo de cada valor -- y aqui se conecta. **Es una medida, no
    # una suposicion**: el descompilador escribio el valor, y el valor dice el
    # tipo.
    # UN TIPO ALOJADO A MANO QUE SEA STRUCT: sus miembros, de DOS FUENTES.
    #
    # El LITERAL de los defaults da **los miembros y su ORDEN** -- es lo unico
    # que los da completos -- y el CATALOGO da el tipo de los que tiene. Se
    # combinan asi:
    #
    #   el tipo lo pone el CATALOGO si lo tiene, y si no lo que diga el literal
    #
    # Y ese orden importa. Para `SkelControlDestLocation` el literal da
    # `SocketName="None"`, que tipa como `string`, y el catalogo dice
    # `NameProperty`: **`name`**. Si ganara el literal, el layout saldria mal --
    # un `string` es un puntero y un `name` son 8 bytes.
    #
    # Y si tras las dos fuentes queda un hueco, NO SE DECLARA: es la regla de
    # siempre, a medias mentiria sobre el layout.
    for _cualificado, corto in list(TIPOS_PERDIDOS.items()):
        if corto in STRUCTS_PERDIDOS or corto not in formas:
            continue
        conocidos = dict(MIEMBROS_DEL_JUEGO.get(corto, []))
        miembros_forma, completo = [], True
        for nombre_m, tv in formas[corto]:
            tv = conocidos.get(nombre_m) or tv
            if not tv:
                completo = False
                break
            miembros_forma.append(f"var {tv} {nombre_m};")
        if not completo or not miembros_forma:
            print(f"   {corto}: NO se declara -- el literal deja un miembro sin "
                  "tipo y el catalogo tampoco lo tiene")
            continue
        STRUCTS_PERDIDOS[corto] = miembros_forma
        TIPOS_PERDIDOS[corto] = corto
        print(f"   {corto} (struct, {len(miembros_forma)} miembros: orden del "
              "literal, tipos del catalogo donde los tiene)")

    for t in sorted(candidatos):
        TIPOS_PERDIDOS[t] = t
        STRUCTS_PERDIDOS[t] = [f"var {tv} {m};" for m, tv in MIEMBROS_DEL_JUEGO.get(t, [])]
        del_juego.append((t, f"ScriptStruct, {len(STRUCTS_PERDIDOS[t])} miembros"))
    if del_juego:
        print(f"tipos del motor del juego declarados: {len(del_juego)}")
        for t, q in del_juego:
            print(f"   {t} ({q})")
    if no_tipables:
        print(f"NO se declaran, les falta el tipo de un miembro: {sorted(no_tipables)}")

    automaticos = []
    for t in sorted(dichos & set(formas)):
        # `t in dueno` es el filtro que faltaba, y sin el salian 85 en vez de 3:
        # un tipo ANIDADO --`struct native AbilityInfo` dentro de su clase-- no
        # tiene fichero propio, asi que no esta en `disponibles` ni en `CLASES`,
        # y parecia perdido. Declararlo ademas en `CCStubTipos` seria declarar
        # DOS tipos con el mismo nombre.
        if (t in sdk or t in disponibles or t in CLASES
                or t in dueno or t in TIPOS_PERDIDOS):
            continue
        # UNA FORMA CON HUECO NO SE DECLARA AQUI. `formas` ahora guarda el
        # miembro sin tipo en vez de tirar el struct entero -- para no perder el
        # ORDEN, que es lo unico que da el literal -- asi que hay que mirarlo.
        # Sin esta guarda saldria `var None m;`, que compila y MIENTE.
        if any(tv is None for _m, tv in formas[t]):
            continue
        TIPOS_PERDIDOS[t] = t
        STRUCTS_PERDIDOS[t] = [f"var {tv} {m};" for m, tv in formas[t]]
        automaticos.append(t)
    if automaticos:
        print(f"tipos perdidos con forma leida de los defaults: {len(automaticos)}")
        for t in automaticos:
            print(f"   {t} ({len(STRUCTS_PERDIDOS[t])} miembros, en su orden)")

    escritos, faltan, con_avisos = 0, [], []
    for clase in CLASES:
        ruta = os.path.join(ORIGEN, clase + ".uc")
        if not os.path.isfile(ruta):
            faltan.append(clase)
            print(f"  FALTA FUENTE  {clase}")
            continue
        texto = io.open(ruta, encoding="utf-8", errors="replace").read()
        adaptado, avisos = adapta(texto, clase)
        lineas = adaptado.count("\n") + 1
        # Solo se imprime lo que tiene algo que decir. Con 241 clases, una linea
        # por clase tapa justo lo que hay que mirar: las que avisan.
        if avisos:
            con_avisos.append(f"  {clase:<30} {lineas:>6}  {'; '.join(avisos)}")
        if not simular:
            with io.open(os.path.join(DESTINO, clase + ".uc"), "w", encoding="utf-8") as f:
                f.write(CABECERA)
                f.write(adaptado)
        escritos += 1

    if CASTS_INT:
        quitados = sum(c for c, _ in CASTS_INT.values())
        motivos = {}
        for _, d in CASTS_INT.values():
            for k, v in d.items():
                motivos[k] = motivos.get(k, 0) + v
        print(f"casts a `int` quitados: {quitados} en "
              f"{sum(1 for c, _ in CASTS_INT.values() if c)} clases")
        for k, v in sorted(motivos.items(), key=lambda x: -x[1]):
            print(f"   DEJADOS por {k}: {v}")
        print()

    if PREOPERADOR:
        quitados = sum(c for c, _ in PREOPERADOR.values())
        motivos = {}
        for _, d in PREOPERADOR.values():
            for k, v in d.items():
                motivos[k] = motivos.get(k, 0) + v
        print(f"pre-operadores parentizados: {quitados}")
        for k, v in sorted(motivos.items(), key=lambda x: -x[1]):
            print(f"   DEJADOS por {k}: {v}")
        print()

    if GOTO_FOREACH:
        tot = sum(c for c, _ in GOTO_FOREACH.values())
        d = collections.Counter()
        for _, dd in GOTO_FOREACH.values():
            d.update(dd)
        print(f"`goto` de `foreach` reescritos: {tot} en {len(GOTO_FOREACH)} clases "
              f"({dict(d)})")
        print()

    if PAQUETE_REESCRITO:
        print(f"paquete {PAQUETE_VIEJO}. -> {PAQUETE_NUEVO}. en "
              f"{sum(PAQUETE_REESCRITO.values())} referencias de "
              f"{len(PAQUETE_REESCRITO)} clases")
        print()

    if con_avisos:
        print("Clases con algo que senalar:")
        for l in con_avisos:
            print(l)
        print()

    # La clase que aloja los tipos perdidos. Se escribe DESPUES del bucle y fuera
    # de la lista, para que no se le aplique ninguna transformacion: no viene de
    # la exportacion, la escribimos nosotros.
    if not simular:
        lineas = ["// GENERADO POR tools/generate-stubs.py -- NO EDITAR A MANO.",
                  "//",
                  "// Aloja los tipos que el guion del juego referencia y que no existen",
                  "// ni en el SDK ni en la exportacion, porque eran del motor del juego,",
                  "// que es de otra version. Ver TIPOS_PERDIDOS en el generador: ahi esta",
                  "// por que, y ahi esta dicho que el ORDEN de los miembros es una",
                  "// suposicion y que pueden faltar miembros que el guion no use.",
                  "",
                  f"class {CLASE_TIPOS_PERDIDOS} extends Object;", ""]
        # DOS CLASES DE COSA, Y NO ES LO MISMO.
        #
        # `TIPOS_PERDIDOS` sabia escribir SOLO `enum`, y eso dejaba fuera a los
        # tipos perdidos que eran STRUCT. No es un detalle de forma: un enum es
        # un byte y un struct es lo que midan sus miembros, asi que declarar uno
        # por otro acierta que compila y MIENTE sobre el layout.
        #
        # Paso con `UIScreenValue_Extent`, que el guion usa en seis clases y que
        # en el motor del juego era un struct.
        # Y EL ORDEN NO ES ALFABETICO: **ES EL DE DEPENDENCIAS**.
        #
        # UnrealScript exige que un tipo este declarado ANTES de usarse, y
        # dentro de una clase eso es el orden del fichero. Con orden alfabetico
        # `UICombinedStyleData` salia antes que `UIImageAdjustmentData`, y el
        # compilador:
        #
        #     CCStubTipos.uc(131) : Error, Unrecognized type 'UIImageAdjustmentData'
        #
        # ...que era el que **abortaba la clase entera** y producia los trece
        # `within 'CCStubTipos'` de debajo.
        #
        # Los enums salen primeros solos: no tienen miembros y por tanto no
        # dependen de nadie.
        #
        # >>> ESO ERA UNA SUPOSICION, Y ES FALSA EN CUANTO UN NOMBRE ES PREFIJO
        # >>> DE OTRO. Lo dijo `PlacingItemInfo` y `PlacingItemInfo_State`: los
        # dos salen "libres" -- el struct no declara al enum como dependencia
        # porque el catalogo lo tiene tipado como `byte`-- y el desempate es
        # ALFABETICO, donde el struct corto gana. Salia el struct primero y el
        # enum despues, justo al reves de como se usan.
        #
        # Y LO DE ARRIBA LO GARANTIZABA EL CATALOGO, QUE NO ES LO QUE SE EMITE.
        # `MIEMBROS_DEL_JUEGO` es una aproximacion -- tiene los miembros que la
        # tabla de exportaciones deja ver, y `CurrState` no es uno de ellos--,
        # mientras que `STRUCTS_PERDIDOS` es **el texto que va al fichero**. Se
        # leen los DOS: el del catalogo no puede perder ninguna dependencia que
        # ya funcionaba, y el emitido anade las que faltaban. Es la misma regla
        # que se aplica en `coinciden()`: una sola verdad, no dos copias.
        def tipos_que_usa(nombre):
            fuera = {t.split("<")[-1].rstrip(">")
                     for _m, t in MIEMBROS_DEL_JUEGO.get(nombre, [])}
            for linea in STRUCTS_PERDIDOS.get(nombre, []):
                # `class<X>` tambien: `TakeHitInfo` lo lleva. Con solo
                # `array<` el tipo se leia como `class`, que no es un tipo y
                # por tanto no casaba con nada -- silenciosamente, que es la
                # forma de fallar de esta funcion.
                m = re.match(r"var\s+(?:array<|class<)?([\w.]+)>?\s+\w+;", linea)
                if m:
                    fuera.add(m.group(1).split(".")[-1])
            return fuera

        def orden_declaracion(nombres):
            quedan, salida, ciclo = set(nombres), [], False
            while quedan:
                libres = [n for n in quedan if not (tipos_que_usa(n) & quedan)]
                if not libres:
                    # Un ciclo de structs no se puede declarar en UnrealScript.
                    # Se emiten en orden alfabetico y **se dice**, en vez de
                    # dejar que el compilador lo diga por su cuenta mas tarde.
                    libres, ciclo = sorted(quedan), True
                for n in sorted(libres):
                    salida.append(n)
                    quedan.discard(n)
            return salida, ciclo

        en_orden, hubo_ciclo = orden_declaracion(set(TIPOS_PERDIDOS.values()))
        if hubo_ciclo:
            print("  AVISO: hay un CICLO entre structs de CCStubTipos; "
                  "se emiten en orden alfabetico")
        for nombre in en_orden:
            if nombre in STRUCTS_PERDIDOS:
                lineas.append(f"struct {nombre}")
                lineas.append("{")
                for m in STRUCTS_PERDIDOS[nombre]:
                    lineas.append(f"\t{m}")
                lineas.append("};")
                lineas.append("")
                continue
            lineas.append(f"enum {nombre}")
            lineas.append("{")
            miembros = MIEMBROS_PERDIDOS.get(nombre, [])
            for i, m in enumerate(miembros):
                coma = "" if i == len(miembros) - 1 else ","
                lineas.append(f"\t{m}{coma}")
            lineas.append("};")
            lineas.append("")
        with io.open(os.path.join(DESTINO, CLASE_TIPOS_PERDIDOS + ".uc"), "w",
                     encoding="utf-8") as f:
            f.write("\n".join(lineas))
        print(f"  {CLASE_TIPOS_PERDIDOS}: {len(TIPOS_PERDIDOS)} tipo(s) perdido(s) alojado(s)")

    print(f"{escritos} de {len(CLASES)} escritos en {DESTINO}")
    if obsoletos:
        print(f"{len(obsoletos)} obsoletos {'que se quitarian' if simular else 'retirados'}: "
              f"{', '.join(x[:-3] for x in obsoletos)}")
    if faltan:
        print(f"sin fuente extraida: {', '.join(faltan)}")
    if simular:
        print("(simulacion: no se ha escrito nada)")

    print("""
PASO SIGUIENTE, que este script NO hace:

  1. Anadir a `DemoGame/Config/DefaultEngine.ini`, en [UnrealEd.EditorEngine]:
         +EditPackages=CrimeCraftStubs
     La carpeta ya existe, que es lo que hacia falta: `EditPackages=DemoGame`
     esta desactivado justo porque la suya no existe.

  2. Compilar. El compilador de guion es EL JUEZ: dira que tipos no resuelve y
     que layouts nativos no cuadran. Este script solo comprueba que los `.uc`
     esten bien formados, no que el motor los acepte.

  3. Los tipos que falten de verdad —`YakaLayer.ECharacterClass`, un enum— hay
     que suplirlos a mano. Es el unico hueco genuino del cierre.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
