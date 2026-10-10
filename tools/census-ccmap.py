#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EL CENSO DE LOS .ccmap: que sabemos leer de cada mapa -- y que NO.

QUE MIDE, CON QUE DEFINICIONES
------------------------------
Una fila por mapa, ordenados de LIVIANO A PESADO por `bytes` (ese ES el orden de
trabajo; `City05_HQ` va marcado en la columna `pivote`). Las columnas:

    bytes, exports, imports      del paquete, por `cc-studytools/tools/package.py`
    clases                       clases DISTINTAS usadas por las exportaciones
    clases_conocidas             de esas, cuantas resuelve NUESTRO SDK
    clases_desconocidas          el resto
    pct_clases                   100*clases_conocidas/clases
    pct_objetos                  100*(exportaciones con clase resuelta)/exports
    pct_bytes                    100*(tam de esas exportaciones)/(tam de todas)
    imports_faltantes            importaciones a objetos que nuestro SDK no tiene
    capa1_ok / capa1_detalle     las CUATRO comprobaciones de `package.py`
    entendido_pct                == pct_bytes (redondeado a 1 decimal)
    restante_pct                 100 - entendido_pct
    capa3                        el literal "NO MEDIDO" en TODAS las filas
    pivote                       "SI" solo en City05_HQ

LO QUE ESTE CSV **NO** DICE, Y HAY QUE DECIRLO
----------------------------------------------
**`entendido_pct` es la CAPA 2.** Dice «sabemos con que CLASE leerlo», no
«sabemos leerlo». La capa 3 -- el contenido de cada exportacion -- **no esta
medida para ningun mapa**, y por eso la columna va con el literal `NO MEDIDO`:
para que nadie lea la cabecera como si fuera entera.

COMO RESUELVE, SIN INVENTAR UN SEGUNDO LECTOR
---------------------------------------------
Usa `package.py` (el lector que se autovalida) y `census-imports.py` (la
resolucion por CADENA DE OUTER completa, no por subcadena: `BoneAtom` aparece
153 veces en nuestro `Engine.u` pero como `Core.BoneAtom`). Aqui no hay lector
nuevo: un segundo instrumento seria un segundo sitio donde mentir.

    ci < 0   importacion -> `camino_import`; resoluble si su RAIZ esta en el
             indice de proveedores Y el camino completo esta en sus exportaciones
    ci > 0   exportacion local -> la clase esta en el propio fichero: resoluble
    ci == 0  UCLASS_INDEX: la exportacion ES una `UClass`: resoluble

EL CONTROL, Y POR QUE ESTA EN PANTALLA
--------------------------------------
El mismo censo se corre **con los paquetes del JUEGO como proveedores**. Eso es
el **ruido de fondo por construccion** (el noexport: `Core.Class` y compania no
se exportan en ningun paquete, se resuelven nativamente). Se imprime el par de
numeros: lo nuestro y el control. Si el control saliera PEOR que lo nuestro,
seria una senal de que el indice nuestro esta mal -- y el informe lo dice en vez
de esconderlo.

Uso:
    python tools/census-ccmap.py                 # el censo entero -> docs/ccmap-censo.csv
    python tools/census-ccmap.py --sin-control   # sin cargar los 40 paquetes del juego
    python tools/census-ccmap.py --limite 8      # corrida parcial (NO escribe el CSV)
    python tools/census-ccmap.py --raiz <dir>    # OTRO corpus de mapas
    python tools/census-ccmap.py --pivote <mapa> # otra columna pivote

LA RAIZ Y EL PIVOTE, y por que dejaron de estar cableados
---------------------------------------------------------
Los dos apuntaban a este proyecto -- la carpeta del juego, y `City05_HQ` como el
mapa que marca la fila de referencia. En un repo publicado la carpeta no existe, y
el recorrido **no falla: devuelve cero mapas y un censo vacio, que se lee como un
dato.** Por eso los dos son argumentos Y hay una comprobacion que aborta.

El DEFECTO sigue siendo el de siempre, asi que las corridas de este proyecto no
cambian ni un byte. **Un valor por defecto no es un fork.**

Y la extension NO se parametriza, a proposito: esto es EL CENSO DE LOS MAPAS.
`census-corpus.py` es el que recorre los tres tipos y reusa esta misma metrica --
parametrizar aqui la extension dejaria dos recorridos donde hay uno.
"""
import argparse
import csv
import glob
import hashlib
import importlib.util
import os
import sys
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.normpath(os.path.join(AQUI, ".."))
sys.path.insert(0, AQUI)

from package import lee_paquete, camino_import, camino_export  # noqa: E402


def carga_censo_imports():
    """Carga `tools/census-imports.py` POR RUTA.

    El guion del nombre no es un identificador valido, asi que `import
    censo-imports` no existe. Se carga el fichero de verdad -- no una copia --
    para que la resolucion sea exactamente la del instrumento que ya existe.
    """
    ruta = os.path.join(AQUI, "census-imports.py")
    spec = importlib.util.spec_from_file_location("censo_imports", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CI = carga_censo_imports()

CENSO = os.path.join(RAIZ, "CrimeCraft", "CrimeCraftGame", "CookedPC")
SALIDA = os.path.join(RAIZ, "docs", "ccmap-censo.csv")
PIVOTE = "City05_HQ"

# The project this was extracted from expects 220 maps. **If the measured count
# disagrees, the tool SHOUTS -- it does not adjust the number to make it fit.**
ESPERADOS = 220

CABECERA = ["orden", "mapa", "ruta", "bytes", "exports", "imports", "clases",
            "clases_conocidas", "clases_desconocidas", "pct_clases",
            "pct_objetos", "pct_bytes", "imports_faltantes", "capa1_ok",
            "capa1_detalle", "entendido_pct", "restante_pct", "capa3", "pivote"]


# --------------------------------------------------------------------------
#  Recoleccion del corpus y de los proveedores
# --------------------------------------------------------------------------

def recorre_ccmap(raiz):
    """Todos los `.ccmap` bajo `raiz`, recursivo."""
    fuera = []
    for base, dirs, ficheros in os.walk(raiz):
        dirs.sort()
        for f in ficheros:
            if f.lower().endswith(".ccmap"):
                fuera.append(os.path.join(base, f))
    return fuera


def rel(ruta):
    return os.path.relpath(ruta, RAIZ).replace(os.sep, "/")


def md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def proveedores(carpeta, patrones=("*.u", "*.upk", "*.ccpk")):
    """Los paquetes de `carpeta`, mas la auditoria de la CARGA.

    La carga la hace `censo_imports.carga_proveedores` (no se copia). Lo que se
    anade aqui es el CONTEO: cuantos ficheros se miraron, cuantos entraron y
    cuantos traian `problemas`. `carga_proveedores` se traga las excepciones en
    silencio, y un proveedor que no entra encoge el indice sin decirlo.
    """
    candidatos = []
    for pat in patrones:
        candidatos += glob.glob(os.path.join(carpeta, pat))
    prov = CI.carga_proveedores(carpeta, patrones)
    con_problemas = sorted(k for k, v in prov.items() if v["problemas"])
    return prov, sorted(candidatos), con_problemas


# --------------------------------------------------------------------------
#  La clase de una exportacion, y si resuelve
# --------------------------------------------------------------------------

def clave_de_clase(p, exp):
    """(clave, propia). `propia` = la clase esta en el PROPIO fichero.

    Las claves son caminos completos (`Engine.ReachSpec`), que es lo unico
    contra lo que se puede resolver sin que la subcadena mienta. Las que no se
    pueden nombrar llevan un numero de indice, para NO fundir en una sola
    varias clases distintas que no sabemos nombrar.
    """
    ci = exp["ci"]
    if ci == 0:
        return "Class (UCLASS_INDEX=0)", True
    if ci > 0:
        k = ci - 1
        if k < len(p["exports"]):
            return camino_export(p, k) or "<export local #%d>" % k, True
        return "<ClassIndex fuera de rango #%d>" % ci, False
    k = -ci - 1
    if k >= len(p["imports"]):
        return "<import fuera de rango #%d>" % k, False
    c = camino_import(p, k)
    if c is None:
        return "<import sin camino #%d>" % k, False
    return c, False


def resuelve(clave, propia, idx):
    if propia:
        return True
    raiz = clave.split(".")[0]
    return raiz in idx and clave in idx[raiz]


def mide(exports, claves, idx):
    """Una pasada: objetos y bytes cuya clase resuelve `idx`, y el mapa de clases."""
    objetos = bytes_ok = bytes_tot = 0
    vistos = {}
    for exp, (clave, propia) in zip(exports, claves):
        ok = resuelve(clave, propia, idx)
        bytes_tot += exp["tam"]
        if ok:
            objetos += 1
            bytes_ok += exp["tam"]
        vistos[clave] = ok
    conocidas = sum(1 for v in vistos.values() if v)
    return {"objetos": objetos, "bytes_ok": bytes_ok, "bytes_tot": bytes_tot,
            "clases": len(vistos), "conocidas": conocidas,
            "desconocidas": len(vistos) - conocidas, "vistos": vistos}


def pct(parte, total):
    return 100.0 * parte / total if total else 0.0


# --------------------------------------------------------------------------
#  El censo de UN mapa
# --------------------------------------------------------------------------

def censo_mapa(ruta, idx_n, idx_c, pivote=PIVOTE):
    """Devuelve (fila, extras). `fila` es el dict de columnas del CSV.

    Si el fichero revienta al leerlo, la fila sale igual con `capa1_ok=NO` y el
    motivo en `capa1_detalle`: un mapa roto es un DATO, no una fila que borrar.
    """
    n_rel = rel(ruta)
    try:
        p = lee_paquete(ruta)
    except Exception as exc:
        texto = "EXCEPCION: %s" % exc
        fila = {"mapa": os.path.splitext(os.path.basename(ruta))[0], "ruta": n_rel,
                "bytes": os.path.getsize(ruta), "exports": 0, "imports": 0,
                "clases": 0, "clases_conocidas": 0, "clases_desconocidas": 0,
                "pct_clases": 0.0, "pct_objetos": 0.0, "pct_bytes": 0.0,
                "imports_faltantes": 0, "capa1_ok": "NO",
                "capa1_detalle": " ".join(texto.replace(",", " ").split()),
                "entendido_pct": 0.0, "restante_pct": 100.0, "capa3": "NO MEDIDO",
                "pivote": "SI" if os.path.splitext(os.path.basename(ruta))[0] == pivote else ""}
        return fila, {"excepcion": texto, "a_n": None, "a_c": None, "raices": Counter(),
                      "sin_camino": 0, "faltan_n": [], "faltan_c": [], "holgura": 0}

    claves = [clave_de_clase(p, e) for e in p["exports"]]
    a_n = mide(p["exports"], claves, idx_n)
    a_c = mide(p["exports"], claves, idx_c) if idx_c is not None else None

    faltan_n, raices, sin_camino, _total = CI.censo(p, idx_n)
    faltan_c = []
    if idx_c is not None:
        faltan_c, _, _, _ = CI.censo(p, idx_c)

    problemas = [" ".join(x.replace(",", " ").split()) for x in p["problemas"]]
    e_pct = round(pct(a_n["bytes_ok"], a_n["bytes_tot"]), 1)
    fila = {
        "mapa": p["nombre"], "ruta": n_rel, "bytes": p["bytes"],
        "exports": len(p["exports"]), "imports": len(p["imports"]),
        "clases": a_n["clases"], "clases_conocidas": a_n["conocidas"],
        "clases_desconocidas": a_n["desconocidas"],
        "pct_clases": round(pct(a_n["conocidas"], a_n["clases"]), 1),
        "pct_objetos": round(pct(a_n["objetos"], len(p["exports"])), 1),
        "pct_bytes": e_pct,
        "imports_faltantes": len(faltan_n),
        "capa1_ok": "si" if not problemas else "NO",
        "capa1_detalle": "; ".join(problemas),
        "entendido_pct": e_pct, "restante_pct": round(100.0 - e_pct, 1),
        "capa3": "NO MEDIDO", "pivote": "SI" if p["nombre"] == pivote else "",
    }
    # La holgura = bytes del fichero - suma de SerialSize = cabecera + tablas +
    # depends (los datos empiezan en el primer `off`). NO es un error: los
    # exports son contiguos y acaban en el ultimo byte (lo comprueba la capa 1).
    # Importa porque el denominador de `pct_bytes` es la SUMA, no el fichero.
    suma = sum(x["tam"] for x in p["exports"])
    extras = {"excepcion": None, "a_n": a_n, "a_c": a_c, "raices": raices,
              "sin_camino": sin_camino, "faltan_n": faltan_n, "faltan_c": faltan_c,
              "holgura": p["bytes"] - suma}
    return fila, extras


# --------------------------------------------------------------------------
#  Presentacion
# --------------------------------------------------------------------------

def muestra_corpus(rutas, revisa=None):
    """Cuadra el recuento del corpus contra el numero que dice el plan.

    `revisa` es el directorio donde se buscan mapas QUE NO esten bajo la raiz del
    censo -- el cruce que encontro los dos duplicados en `DemoGame/Content/`.

    **Y ese cruce dejaba de comprobar en silencio al mover el guion**, porque
    escaneaba `RAIZ`, que ahora es la carpeta de la herramienta y no tiene ni un
    `.ccmap`. Y como el aviso vivia dentro de un `if fuera:`, el cero NO SE
    IMPRIMIA: no se veia "0 encontrados", no se veia nada. **Un chequeo que deja
    de encontrar cosas y no lo dice es un chequeo que se cree hecho.**
    """
    if revisa is None:
        revisa = RAIZ
    print("  RECUENTO DEL CORPUS")
    print("    .ccmap bajo la raiz del censo : %d" % len(rutas))
    if len(rutas) != ESPERADOS:
        print("    ESPERADOS (plan, 29.2)        : %d   <-- NO COINCIDE" % ESPERADOS)
    # Los .ccmap del repo que NO estan bajo la raiz del censo.
    dentro = set(os.path.normcase(os.path.abspath(r)) for r in rutas)
    tam_dentro = {}
    for r in rutas:
        tam_dentro.setdefault(os.path.getsize(r), []).append(r)
    fuera = []
    for base, dirs, ficheros in os.walk(revisa):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for f in ficheros:
            if f.lower().endswith(".ccmap"):
                r = os.path.join(base, f)
                if os.path.normcase(os.path.abspath(r)) not in dentro:
                    fuera.append(r)
    # SE IMPRIME SIEMPRE, aunque sea cero. Un cero visible es un dato; un cero
    # que no se imprime es un chequeo que parece no haber hecho falta.
    print("    .ccmap FUERA de la raiz del censo, en %s: %d"
          % (rel(revisa), len(fuera)))
    if fuera:
        for r in sorted(fuera):
            h = md5(r)
            gemelos = [x for x in tam_dentro.get(os.path.getsize(r), []) if md5(x) == h]
            nota = ("DUPLICADO exacto de %s" % rel(gemelos[0])) if gemelos else "no duplicado"
            print("      %-58s %10d B  %s" % (rel(r), os.path.getsize(r), nota))
    print()


def muestra_proveedor(nombre, prov, candidatos, malos):
    print("  %-10s: %d paquetes cargados de %d ficheros candidatos  (%s)"
          % (nombre, len(prov), len(candidatos), rel(CI.NUESTROS) if nombre == "nuestros" else rel(CI.DEL_JUEGO)))
    if len(candidatos) != len(prov):
        no_entraron = []
        for c in candidatos:
            if os.path.splitext(os.path.basename(c))[0] not in prov:
                no_entraron.append(rel(c))
        print("     !!! %d candidato(s) NO entraron (carga_proveedores se traga la excepcion): %s"
              % (len(no_entraron), ", ".join(no_entraron[:6])))
    if malos:
        print("     !!! con problemas de formato (entran igual, envenenanan el indice): %s"
              % ", ".join(malos))
    else:
        print("     los %d cierran sus cuatro comprobaciones" % len(prov))


def linea_muestra(f, campos):
    print("    " + "  ".join("%s=%s" % (c, f[c]) for c in campos))


def fila_completa(f):
    return "  ".join("%s=%s" % (c, f[c]) for c in CABECERA)


# --------------------------------------------------------------------------
#  main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limite", type=int, default=0,
                    help="corrida parcial de los N mas livianos; NO escribe el CSV")
    ap.add_argument("--sin-control", action="store_true",
                    help="no carga los paquetes del juego (ahorra ~15 s)")
    # La RAIZ y el PIVOTE estaban cableados a este proyecto. En un repo publicado
    # la raiz no existe, y el recorrido NO falla: devuelve cero mapas y un censo
    # vacio, que se lee como un dato.
    ap.add_argument("--raiz", default=CENSO,
                    help="raiz del corpus de mapas (por defecto, la del juego)")
    ap.add_argument("--pivote", default=PIVOTE,
                    help="mapa que marca la columna `pivote` (por defecto City05_HQ)")
    # EL SDK CONTRA EL QUE SE MIDE -- ver el comentario largo en census-corpus.py.
    # Sin esto el censo mide contra nada y devuelve cifras con la forma de un dato.
    ap.add_argument("--nuestros", default=CI.NUESTROS,
                    help="carpeta de paquetes que construimos (el SDK)")
    ap.add_argument("--control", default=CI.DEL_JUEGO,
                    help="carpeta de paquetes del juego, para el control")
    ap.add_argument("--revisa", default=RAIZ,
                    help="donde buscar mapas FUERA de la raiz del censo (un cruce)")
    args = ap.parse_args()
    CI.NUESTROS, CI.DEL_JUEGO = args.nuestros, args.control

    if not os.path.isdir(args.raiz):
        print("ERROR: la raiz del corpus no existe: %s" % args.raiz)
        print("       (--raiz <dir>  para indicar otra)")
        return 2

    print("=" * 78)
    print("  CENSO DE LOS .ccmap  --  capa 1 + capa 2  (capa 3: NO MEDIDA)")
    print("=" * 78)

    rutas = sorted(recorre_ccmap(args.raiz), key=lambda r: (os.path.getsize(r), os.path.normcase(r)))
    if not rutas:
        print("ERROR: cero .ccmap bajo %s" % args.raiz)
        print("       no es un censo de cero: es que no estan ahi")
        return 2
    muestra_corpus(rutas, args.revisa)
    if args.limite:
        rutas = rutas[:args.limite]
        print("  !! CORRIDA PARCIAL: %d mapas (no se escribe el CSV)\n" % len(rutas))

    prov_n, cand_n, malos_n = proveedores(CI.NUESTROS)
    idx_n = CI.indice(prov_n)
    muestra_proveedor("nuestros", prov_n, cand_n, malos_n)

    idx_c = None
    if not args.sin_control:
        prov_c, cand_c, malos_c = proveedores(CI.DEL_JUEGO)
        idx_c = CI.indice(prov_c)
        muestra_proveedor("el juego", prov_c, cand_c, malos_c)
    else:
        print("  el juego  : NO CARGADO (--sin-control): sin control diferencial")
    print()

    filas, stats = [], {
        "no_ok": 0, "excepciones": [], "sin_camino": 0, "holgura": 0, "holgura_max": 0,
        "res_global": {}, "falta_nos": Counter(), "falta_juego": Counter(),
        "raices_ajenas": Counter(), "mapas_ajenas": Counter(),
        "tot": Counter(), "dispares": [], "control_peor": [], "sin_camino_claves": 0,
    }

    for i, r in enumerate(rutas):
        fila, ex = censo_mapa(r, idx_n, idx_c, pivote=args.pivote)
        filas.append(fila)
        if fila["capa1_ok"] != "si":
            stats["no_ok"] += 1
        if ex["excepcion"]:
            stats["excepciones"].append((rel(r), ex["excepcion"]))
            continue
        stats["holgura_max"] = max(stats["holgura_max"], ex["holgura"])
        stats["holgura"] += ex["holgura"]
        stats["sin_camino"] += ex["sin_camino"]
        a_n, a_c = ex["a_n"], ex["a_c"]
        stats["tot"]["objetos"] += a_n["objetos"]
        stats["tot"]["exports"] += fila["exports"]
        stats["tot"]["bytes_ok"] += a_n["bytes_ok"]
        stats["tot"]["bytes"] += a_n["bytes_tot"]
        stats["sin_camino_claves"] += sum(1 for k in a_n["vistos"] if k.startswith("<"))
        for clave, ok_n in a_n["vistos"].items():
            par = stats["res_global"].setdefault(clave, [False, False])
            par[0] = par[0] or ok_n
            if not ok_n:
                stats["falta_nos"][clave] += 1
            if a_c is not None:
                ok_c = a_c["vistos"].get(clave, False)
                par[1] = par[1] or ok_c
                if not ok_c:
                    stats["falta_juego"][clave] += 1
        if a_c is not None:
            stats["tot"]["objetos_c"] += a_c["objetos"]
            stats["tot"]["bytes_ok_c"] += a_c["bytes_ok"]
            stats["tot"]["bytes_c"] += a_c["bytes_tot"]
            stats["tot"]["faltantes_c"] += len(ex["faltan_c"])
            dif_cl = a_n["conocidas"] - a_c["conocidas"]
            dif_pt = fila["pct_bytes"] - round(pct(a_c["bytes_ok"], a_c["bytes_tot"]), 1)
            if dif_cl > 0 or dif_pt > 0:
                stats["control_peor"].append((fila["mapa"], dif_cl, dif_pt))
            elif dif_cl < 0 or dif_pt < 0:
                stats["dispares"].append((fila["mapa"], dif_cl, dif_pt))
        stats["tot"]["faltantes"] += len(ex["faltan_n"])
        for raiz, n in ex["raices"].items():
            if raiz not in idx_n:
                stats["raices_ajenas"][raiz] += n
                stats["mapas_ajenas"][raiz] += 1
        if (i + 1) % 50 == 0:
            print("  ... %d/%d" % (i + 1, len(rutas)))

    filas.sort(key=lambda f: (f["bytes"], os.path.normcase(f["ruta"])))
    for i, f in enumerate(filas):
        f["orden"] = i + 1

    if not args.limite:
        with open(SALIDA, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(CABECERA)
            for f in filas:
                w.writerow([f.get(c, "") for c in CABECERA])

    # ---------------- resumen ----------------
    print()
    print("=" * 78)
    print("  RESUMEN")
    print("=" * 78)
    n_ok = sum(1 for f in filas if f["capa1_ok"] == "si")
    print("  filas            : %d" % len(filas))
    print("  capa1_ok = si    : %d/%d" % (n_ok, len(filas)))
    if stats["no_ok"]:
        print("     !!! %d fila(s) con capa1_ok=NO:" % stats["no_ok"])
        for f in filas:
            if f["capa1_ok"] != "si":
                print("        %-28s %s" % (f["mapa"], f["capa1_detalle"]))
    for nombre, lista in (("EXCEPCION al leer", stats["excepciones"]),):
        for mapa, texto in lista:
            print("     !!! %s: %s" % (mapa, texto))
    if stats["holgura"]:
        print("     (holgura cabecera+tablas: %d B en total, max %d B en un mapa -- el"
              % (stats["holgura"], stats["holgura_max"]))
        print("      denominador de pct_bytes es la suma de SerialSize, no el fichero)")

    dups = [m for m, n in Counter(f["mapa"] for f in filas).items() if n > 1]
    if dups:
        print("     !! nombres de mapa repetidos (el pivote y los cortes van por nombre): %s"
              % ", ".join(dups))
    if stats["sin_camino"]:
        print("     !! importaciones sin camino a paquete (outer = export local): %d" % stats["sin_camino"])
    if stats["sin_camino_claves"]:
        print("     !! clases que no se pudieron NOMBRAR (clave con <...>): %d usos" % stats["sin_camino_claves"])

    # capa 2, agregada sobre el corpus
    rg = stats["res_global"]
    conoc_n = sum(1 for v in rg.values() if v[0])
    print()
    print("  CAPA 2 -- resolucion de clases")
    print("    clases distintas (union del corpus) : %d" % len(rg))
    print("      las resuelve NUESTRO SDK          : %d  (%.1f %%)"
          % (conoc_n, pct(conoc_n, len(rg))))
    if idx_c is not None:
        conoc_c = sum(1 for v in rg.values() if v[1])
        print("      las resuelve EL JUEGO (control)   : %d  (%.1f %%)"
              % (conoc_c, pct(conoc_c, len(rg))))
    t = stats["tot"]
    print("    exportaciones : %d de %d con clase resuelta (%.1f %%)"
          % (t["objetos"], t["exports"], pct(t["objetos"], t["exports"])))
    print("    bytes         : %d de %d (%.1f %%)"
          % (t["bytes_ok"], t["bytes"], pct(t["bytes_ok"], t["bytes"])))

    print()
    print("  IMPORTACIONES")
    print("    imports_faltantes (suma de la columna) : %d" % t["faltantes"])
    print("      -- solo cuenta raices que SI tenemos; una raiz que no tenemos no entra")
    if stats["raices_ajenas"]:
        print("    importaciones cuya RAIZ no tenemos    : %d  (en %d raices distintas)"
              % (sum(stats["raices_ajenas"].values()), len(stats["raices_ajenas"])))
        for k, v in stats["raices_ajenas"].most_common(8):
            print("       %-34s %6d  (%d mapas)" % (k, v, stats["mapas_ajenas"][k]))

    if idx_c is not None:
        print()
        print("  CONTROL DIFERENCIAL -- los paquetes del JUEGO como proveedores")
        print("    exportaciones : %d de %d (%.1f %%)   [nuestro: %.1f %%]"
              % (t["objetos_c"], t["exports"], pct(t["objetos_c"], t["exports"]),
                 pct(t["objetos"], t["exports"])))
        print("    bytes         : %d de %d (%.1f %%)   [nuestro: %.1f %%]"
              % (t["bytes_ok_c"], t["bytes_c"], pct(t["bytes_ok_c"], t["bytes_c"]),
                 pct(t["bytes_ok"], t["bytes"])))
        print("    imports_faltantes (ruido de fondo por construccion) : %d" % t["faltantes_c"])
        print("    capturamos el %.1f %% de los OBJETOS y el %.1f %% de los BYTES que el"
              % (pct(t["objetos"], t["objetos_c"]), pct(t["bytes_ok"], t["bytes_ok_c"])))
        print("    juego resuelve consigo mismo -- ese es el techo medido, no el 100 %")
        print("    mapas donde el JUEGO resuelve MENOS clases que nosotros : %d"
              % len(stats["control_peor"]))
        if stats["control_peor"]:
            print("       <-- el juego deberia resolver al menos tanto como nosotros; si sale")
            print("           alto, mirar el mapa antes de creer el indice nuestro.")
            for m, dc, dp in stats["control_peor"][:10]:
                print("          %-28s clases %+d  pct_bytes %+.1f" % (m, dc, dp))
        print("    mapas donde el juego resuelve MAS clases que nosotros : %d (lo esperado)"
              % len(stats["dispares"]))
        if stats["dispares"]:
            for m, dc, dp in stats["dispares"][:5]:
                print("          %-28s clases %+d  pct_bytes %+.1f" % (m, dc, dp))
        brecha = {k: v for k, v in stats["falta_nos"].items() if k not in stats["falta_juego"]}
        ruido = {k: v for k, v in stats["falta_juego"].items()}
        print("    clases que NO resuelve ninguno (noexport, ruido) : %d" % len(ruido))
        print("    clase que SI resuelve el juego y NO nosotros (brecha real) : %d" % len(brecha))
        if brecha:
            print("       top por numero de mapas:")
            for k, v in sorted(brecha.items(), key=lambda kv: -kv[1])[:12]:
                print("          %-44s %d mapas" % (k, v))
        if ruido:
            print("       ruido (ni el juego los resuelve), top:")
            for k, v in sorted(ruido.items(), key=lambda kv: -kv[1])[:8]:
                print("          %-44s %d mapas" % (k, v))

    # ---------------- muestras ----------------
    campos = ["orden", "mapa", "bytes", "exports", "imports", "clases",
              "clases_conocidas", "pct_clases", "pct_objetos", "pct_bytes",
              "imports_faltantes", "capa1_ok", "capa3", "pivote"]
    print()
    print("  LAS 5 MAS LIVIANAS")
    for f in filas[:5]:
        linea_muestra(f, campos)
    print("  LAS 5 MAS PESADAS")
    for f in filas[-5:]:
        linea_muestra(f, campos)
    piv = [f for f in filas if f["pivote"] == "SI"]
    print("  PIVOTE")
    if not piv:
        print("     !!! %s NO APARECE: la columna pivote saldria vacia en las %d filas"
              % (args.pivote, len(filas)))
    for f in piv:
        print("    " + fila_completa(f))

    if not args.limite:
        print()
        print("  ESCRITO: %s  (%d filas + cabecera)" % (rel(SALIDA), len(filas)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
