#!/usr/bin/env python3
"""
RECORRE `Chunks` DE UN FStaticLODModel Y SE AUTOVALIDA.

LA COMPROBACION QUE SE VALIDA SOLA
----------------------------------
`FSkelMeshChunk` serializa, en este orden (identico en el 867 y en Batman-576,
`UnSkeletalMesh.h`):

    BaseVertexIndex   UINT
    RigidVertices     TArray<FRigidSkinVertex>   -> 4 + N*33
    SoftVertices      TArray<FSoftSkinVertex>    -> 4 + N*40
    BoneMap           TArray<WORD>               -> 4 + N*2
    NumRigidVertices  INT          <-- el CONTEO, DESPUES de los arrays
    NumSoftVertices   INT          <-- idem
    MaxBoneInfluences INT

**`NumRigidVertices` viene DESPUES de `RigidVertices`.** Asi que si el recorrido
es correcto tiene que valer lo mismo que el contador del array. Si no coinciden,
**el desvio esta en ese chunk, y se sabe cual** -- no hay que adivinar.

Y los tamanos de elemento son IMPARES, que es lo que importa aqui:
  `FRigidSkinVertex` = 12 + 12 + 8 + 1 = 33   <- IMPAR
  `FSoftSkinVertex`  = 12 + 12 + 8 + 8 = 40
Asi que **un chunk con un numero impar de vertices rigidos cambia la paridad de
todo lo que venga detras**. Ver docs/tarea-relevo-576.md §13.

Uso:  python tools/walk-chunks.py <paquete> <indice-export> --desde <rel>
      python tools/walk-chunks.py .../Characters_Male_combocloth.ccpk 82 --desde 100032
"""
import struct
import sys

MAX_INFLUENCES = 4
MAX_TEXCOORDS = 4
T_RIGIDO = 12 + 12 + 4 * 2 + 1          # FVector + 3 FPackedNormal + UVs[0] + Bone
T_SUAVE = 12 + 12 + 4 * 2 + 4 * 2       # + InfluenceBones[4] + InfluenceWeights[4]


def i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def u32(d, p):
    return struct.unpack_from("<I", d, p)[0]


def lee_encabezado(d):
    p = 16 + i32(d, 12)
    e = {}
    p += 4
    e["NameCount"] = i32(d, p); p += 4
    e["NameOffset"] = i32(d, p); p += 4
    e["ExportCount"] = i32(d, p); p += 4
    e["ExportOffset"] = i32(d, p); p += 4
    return e


def exports(d, off, cuenta):
    fuera, p = [], off
    for _ in range(cuenta):
        fuera.append({"nombre": i32(d, p + 12),
                      "tamano": i32(d, p + 32),
                      "offset": i32(d, p + 36)})
        # Paso VARIABLE: el registro mide 68 + 4N, con N = i32(p+44). Con `p += 68`
        # fijo se camina por registros desplazados desde el primer registro largo
        # -- y los valores desplazados PARECEN buenos. Corregido el 5/10.
        # El lector de referencia, con las cuatro comprobaciones que no se pueden
        # falsear, es `cc-studytools/tools/package.py`.
        p += 68 + 4 * i32(d, p + 44)
    return fuera


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    ruta, k = sys.argv[1], int(sys.argv[2])
    desde = int(sys.argv[sys.argv.index("--desde") + 1]) if "--desde" in sys.argv else 0
    if "--desde" not in sys.argv:
        print("hace falta --desde: la posicion donde empieza `Chunks` (la da [PARIDAD])")
        return 2

    d = open(ruta, "rb").read()
    e = lee_encabezado(d)
    x = exports(d, e["ExportOffset"], e["ExportCount"])[k]
    base = x["offset"]
    p = base + desde
    fin = base + x["tamano"]

    print("export %d  offset=%d  tamano=%d" % (k, base, x["tamano"]))
    print("elementos: rigido=%d B  suave=%d B" % (T_RIGIDO, T_SUAVE))
    print()

    n = i32(d, p); print("chunks declarados: %d  (en +%d)" % (n, p - base)); p += 4
    if not (0 <= n <= 4096):
        print("  ** el contador de chunks es absurdo: el desvio es ANTES de +%d" % desde)
        return 1

    for c in range(n):
        if p + 4 > fin:
            print("chunk %d: se sale del export" % c); return 1
        bvi = u32(d, p); p += 4
        rel_r = p - base
        nr = i32(d, p); p += 4
        if not (0 <= nr <= 1 << 20):
            print("chunk %d: contador de RigidVertices absurdo (%d) en +%d" % (c, nr, rel_r)); return 1
        p += nr * T_RIGIDO
        rel_s = p - base
        ns = i32(d, p); p += 4
        if not (0 <= ns <= 1 << 20):
            print("chunk %d: contador de SoftVertices absurdo (%d) en +%d" % (c, ns, rel_s)); return 1
        p += ns * T_SUAVE
        nb = i32(d, p); p += 4
        if not (0 <= nb <= 4096):
            print("chunk %d: contador de BoneMap absurdo (%d) en +%d" % (c, nb, p - base - 4)); return 1
        p += nb * 2
        rel_n = p - base
        cr = i32(d, p); p += 4
        cs = i32(d, p); p += 4
        mx = i32(d, p); p += 4

        # ESTA es la comprobacion: los conteos van DESPUES de los arrays.
        ok = (cr == nr and cs == ns)
        print("chunk %d  +%-8d base=%-7d  rigidos=%d/%d  suaves=%d/%d  huesos=%d  maxinf=%d  %s"
              % (c, rel_n - 12 - 4 * 0, bvi, nr, cr, ns, cs, nb, mx, "OK" if ok else "** NO CUADRA **"))
        if not ok:
            print("      ^ el chunk %d desincroniza: los conteos van despues de los arrays" % c)
            print("      vuelca los bytes en +%d con el modo `hex` de probe-properties.py" % rel_n)
            return 1
        if mx < 0 or mx > 8:
            print("chunk %d: MaxBoneInfluences absurdo (%d)" % (c, mx)); return 1

    print()
    print("fin de Chunks en +%d  (posicion %d)" % (p - base, p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
