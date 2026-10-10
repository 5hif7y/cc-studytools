#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LA LISTA DE MODIFICADORES DE UNREALSCRIPT, EN UN SOLO SITIO.

POR QUE EXISTE ESTE FICHERO
---------------------------
Estaba copiada en TRES sitios, y ya habian divergido:

    generate-stubs.py     31   <- la buena
    analiza-tipos.py    24   le faltaban editconst, globalconfig, init,
                              noclear, optional, out, retval
    mide-deriva.py      11   orientada a parametros

Y una lista corta no es un detalle: `tipo_de_var()` y `tipo_de()` se quedan con
**el primer identificador que no reconocen**, asi que un modificador que falte
**se convierte en el tipo**. Medido el 30/9 sobre `analiza-tipos.py`: de las
**123** entradas de su lista «SIN DECLARAR EN NINGUN SITIO», **11 no son tipos**
-- 4 modificadores (`editconst`, `globalconfig`, `init`, `noclear`) y 7
primitivos del lenguaje (`Vector`, `Rotator`, `Color`...). Y esa es justo la
lista que decide que falta.

La lista larga es la SEGURA para los tres: cuanto mas se reconozca como
modificador, menos veces se confunde con un tipo. El comentario de
`generate-stubs.py` tiene la procedencia de las cinco ultimas, medidas una a una.

NO lleva `Vector`, `Rotator` ni los demas primitivos a proposito: esos NO son
modificadores. Van en `PRIMITIVOS`, aparte, porque un primitivo si es un tipo y
lo que hay que hacer con el es lo contrario -- no buscarlo en ningun catalogo.
"""

MODIFICADORES = {
    "transient", "native", "const", "config", "localized", "input", "export",
    "editoronly", "private", "protected", "public", "repnotify", "databinding",
    "instanced", "editinline", "editinlinenew", "deprecated", "noexport",
    "notplaceable", "singular", "abstract", "atomic", "pointer", "coerce",
    # Las cinco que se midieron en vez de ir anadiendo de una en una, y las dos
    # de parametro:
    "init", "editconst", "noclear", "retval", "globalconfig",
    "optional", "out",
}

# Los tipos que el lenguaje ya trae. Un miembro de estos NO hay que buscarlo en
# ningun catalogo: existe siempre, y decir que "no esta declarado en ninguna
# parte" es un falso positivo.
PRIMITIVOS = {
    "byte", "int", "float", "bool", "string", "name",
    "Vector", "Vector2D", "Vector4", "Rotator", "Color", "LinearColor",
    "Quat", "Matrix", "Plane", "Box", "Range", "Interval",
    "Object", "Class", "Interface", "Pointer",
}
