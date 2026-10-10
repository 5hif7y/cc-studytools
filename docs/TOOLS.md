# Tools — index and manuals

**One tool per question.** This file is the index; each tool's own header carries the
long version.

---

## How to read this

Not every tool needs the same treatment, and pretending otherwise wastes the reader's
time:

| | | |
| --- | --- | --- |
| **LIVE** | you would run it again | a full manual |
| **CLOSED** | it answered its question, once, and the answer is recorded | **one line**: what it answered |
| **PROJECT** | about *this repository*, not about UE3 or the game | one line; not for redistribution |

**A manual on a closed tool is a document that will never be updated and will be
believed anyway.** The answer was what mattered; the tool was the means.

---

## About the paths in the examples

Every `$ ` example below is written **from the root of a checkout of this
repository** — that is why the tool paths read `tools/…`. **This repository ships no
game data** — see `.gitignore` — so every corpus path is passed as an argument, and
the examples show exactly which flags that takes.

### The markers, and why they are markers

**No example names the project these tools were extracted from.** Where a path would be
*that* project's, the example uses a marker you substitute:

| marker | stands for |
| --- | --- |
| `<GAME>` | the game's install, where its `.ccmap` and `.ccpk` live |
| `<SDK>` | **your** reconstructed SDK's compiled packages |
| `<SRC>` | **your** SDK's source tree |
| `<LOG>` | a run log from **your** engine |
| `<EXPORT>` | the `.uc` files **you** exported out of the game's packages |
| `<DATA>` | the catalogues **you** generated (`generate-game-catalog.py` writes one) |

**This is not a gap — it is the point.** A reader of this repository has the game. **They
do not have anyone else's reconstruction**, and an example that named one would be an
example they cannot run.

> **The examples are not decoration: they are run — and they run both ways.** The project
> these tools came from keeps `tools/verifica-manuales.py`, which **substitutes these
> markers with real paths and then executes every `$ ` line**, comparing the result
> against a stored baseline. So an example that stops working **fails a check** instead of
> quietly misleading someone — which is how the `package.py` entry above was caught
> claiming a command line that does not exist.
>
> **Markers plus substitution is what makes the examples publishable *and* verified.**
> Concrete paths would make them unrunnable for a reader; no paths at all would make them
> unrunnable for the check.

---

## The distinction that decides where a tool lives

| | | |
| --- | --- | --- |
| **(A) about CrimeCraft's content** | `generate-stubs.py` exists to stub *the game's own classes* | **specific** |
| **(B) generic, defaulting to CrimeCraft** | `package.py` reads **any** UE3 package | **generic — the default becomes a parameter** |

**⇒ (B) is the tempting mistake: forking it into two copies.** This codebase already
paid for that — **six copies of the export-table reader drifted apart**, three with a
different stride, and **41.7 % of one package's records were read wrong, silently.**

> **A parameter is not a fork.**

---

## ⚠️ What this index documents, and what this repository actually contains

**These are not the same number, and the difference matters to a reader.**

| | |
| --- | ---: |
| tools described in this file | **47** |
| tools present in `tools/` of this repository | **24** |

**The other 22 are real, and they live in the project these tools were extracted from.**
They are documented here because they are part of the same method, and **because a reader
should know they exist** — but **you cannot run them from a checkout of this repository.**

**Where each group lives, and why:**

| group | why it is not here |
| --- | --- |
| **the record of a finished investigation** — `analiza-tipos`, `comprueba-cobertura`, `identifica-operadores`, `lista-miembros-perdidos`, `mide-anidamiento`, `mide-arrays`, `mide-cast-int`, `mide-deriva`, `mide-firmas`, `mide-goto-foreach`, `mide-paquete-crimecraft`, `mide-sombreados`, `mide-tipo-del-cast`, `mide-within`, `alinea-paridad`, `alinea-traza`, `verifica-diff-paquete` | each answered one question **about that project's reconstruction**, and the answer is the artifact — see the CLOSED table below. **They are history, not instruments** |
| **about that repository's own organisation** — `mide-especificidad`, `audita-rutas` | they audit *a repository's* tools. Here they would examine this one; there they examine that one. **Neither is useful without the other** |
| **they need the reconstructed SDK** — `compila-stubs.sh`, `cdb-compila-stubs.sh` | **outside that project there is nothing to compile.** They edit its ini files, run its engine and kill its processes |
| **bound to that project's build** — `mira-errores`, `porta-defaultproperties` | `mira-errores` reads a compiler log that project produces; `porta-defaultproperties` **writes into its SDK tree**. Both are usable — **neither belongs to a published reader** |

> **And the same is true of `tools/verifica-manuales.py`**, which this file names in the
> section on examples: **it lives in the enclosing project**, not here. It is what runs
> every `$ ` line below. A reader of this repository has the *examples*; the *check that
> they still work* is the project's.

**Nothing above is a promise.** Where a tool is named in this file and is not in `tools/`,
**it is listed here rather than left to be discovered by a `ls`.**

---

# LIVE tools

## `package.py` — **(B) the package reader**

**Answers:** *what is in this UE3 package, and do its tables agree with themselves?*

**Run:** *(it is a **library**, not a command — importing it is the way in. See below.)*

**Generic.** It takes a path; it has no default. **It is the base of everything else
here** — the tool that had to be extracted first, and it now lives at
`cc-studytools/tools/package.py`.

**Where the callers find it:** every tool that uses it puts this folder on `sys.path`
explicitly. **Not a copy** — a copy would be two readers, and this codebase already paid
for that. `modifiers.py` lives here too, for the same reason.

> [!warning] **This manual used to give a command line that does not exist:**
> `python -I tools/package.py <file>`. `package.py` has **no `__main__` and no argument
> parser.** Running that command **succeeds, exits 0, and prints nothing** — a silent
> empty result, which is the failure this whole directory keeps warning about.
> It was caught by `tools/verifica-manuales.py`, whose whole job is to *follow the manual
> and see if it reproduces the run.*

**Runnable example** — the self-check on the smallest map in the corpus (7,392 B):

```console
$ python -I -c "import sys; sys.path.insert(0,'cc-studytools/tools'); import package; p=package.lee_paquete('CrimeCraft/CrimeCraftGame/CookedPC/Maps/transient_map.ccmap'); print(p['nombre'], p['bytes'], len(p['exports']), p['problemas'] or 'tablas OK')"
transient_map 7392 11 tablas OK
```

**Cannot see:** what is *inside* each object — that is per-class and lives in the
class's own serializer. It reads the container, not the contents.

**Falsifies itself:** the four identities in `UE3-PACKAGE-FORMAT.md` § 3. On a
malformed file it reports the broken check rather than returning plausible numbers.

---

## `census-corpus.py` — **(B)**

**Answers:** *what fraction of each package can we read — measured in bytes, by export
class?*

**Run:** `python -I cc-studytools/tools/census-corpus.py --tipo u|ccmap|ccpk`

**Runnable example** (`--limite` measures only the first N of each kind and **writes no
CSV**, which is what makes it safe to run as a check):

```console
$ python -I cc-studytools/tools/census-corpus.py --tipo ccmap --raiz <GAME> --nuestros <SDK> --limite 5
```

**Generic.** `--tipo` picks the extension and `--raiz` the corpus. **The defaults are
this project's**, which is all that is CrimeCraft's about it.

**And the reason `--raiz` is not merely a convenience:** with the root hardcoded, a
published copy points at a folder that does not exist — and the walk **does not fail**.
It returns **zero files and an empty census, which reads as a result.** So the root is an
argument *and* there is a check that aborts. **A silent zero is worse than an error.**

**Cannot see:** it measures **classes resolved, not content understood.** 100 % means
*we know what class each export is* — it does **not** mean the file can be interpreted
or that a map would load. Conflating the two is the single most damaging misreading of
this number.

**Ships a date in every row**, because the figure rises as classes are added and an
undated percentage is a stale figure waiting to be misread.

---

## `census-imports.py` — **(B)**

**Answers:** *what does this package import, and which of those do we not have?*

**Run:** `python -I cc-studytools/tools/census-imports.py [package]`

**Runnable example:**

```console
$ python -I cc-studytools/tools/census-imports.py --sin-control --tope 5 --nuestros <SDK> --control <GAME> --consumidor <GAME>/CrimeCraft.u
```

**Resolves by full `outer` chain, never by substring.** Substring matching was measured
to lie: a struct appeared 153 times but under a *different* path, and the substring
search said "found" and was wrong.

**Cannot see:** an import that resolves is not an import that is *correct* — only that
a name exists at that path.

---

## `audit-package-coverage.py` — **(B)**

**Answers:** *how much of each package is readable, broken down by export class?*

**Cannot see:** an export whose class **resolves** is not an export that can be
**interpreted**. This measures *which classes are known*, not *what the data means* — the
same conflation the census warns about, and it does the same damage here.

**And a record that does not line up is not summed.** The export stride is `68 + 4·N`, and a
shifted read still looks like a number; the totals are therefore of the records it could
read, **not of the package**.

**Run:** `python -I cc-studytools/tools/audit-package-coverage.py <root-or-file> [--top N] [--solo .ext]`

**Runnable example** (a single file, so it is fast — the root also works and walks it):

```console
$ python -I cc-studytools/tools/audit-package-coverage.py CrimeCraft/CrimeCraftGame/CookedPC/Core.u
```

**Why it is separate from the census:** the census gives one number per file; this
gives the **per-class breakdown**, which is what says *what* is missing rather than
*how much*.

---

## `walk-tags.py` — **(B)**

**Answers:** *does this object's tagged-property stream close exactly at the end of its
export?*

**Cannot see:** it says whether the stream **closes**, not what the properties **mean** —
for that, `probe-properties.py`.

**And two different failures look alike:** a stream that lands **short**, and an export that
genuinely **has no** tagged properties, both fail to reach the end. The tool prints the
distance so the two can be told apart — **it does not decide for you.**

**Run:** `python -I cc-studytools/tools/walk-tags.py <package> <offset>`

**Runnable example** — offset `2496` is the first export of the smallest map, so it is
stable:

```console
$ python -I cc-studytools/tools/walk-tags.py CrimeCraft/CrimeCraftGame/CookedPC/Maps/transient_map.ccmap 2496
```

**The check it performs:** a tagged stream ends with a `NAME_None` tag. **If walking it
lands exactly on the export's end, the read is right** — and that is checkable per
object, which is what makes it usable as evidence.

---

## `probe-header.py` · `probe-name-table.py` — **(B)**

**Answer:** *what does this one table actually contain?* — a header, a name table.

**Cannot see:** **one table, with no cross-check.** It prints what is there and never asks
whether it agrees with the rest of the file — **a header whose offsets point nowhere prints
just as cleanly.** For the four identities that make a read falsifiable, `package.py`.

**Run:** `python -I tools/<name> <package>`

**Runnable example** (both probes take one package and print one table):

```console
$ python -I cc-studytools/tools/probe-header.py CrimeCraft/CrimeCraftGame/CookedPC/Maps/transient_map.ccmap
$ python -I cc-studytools/tools/probe-name-table.py CrimeCraft/CrimeCraftGame/CookedPC/Maps/transient_map.ccmap
```

**Why they exist as separate probes:** when a reader and a document disagree, the way to
settle it is to look at the bytes with the smallest possible tool, so there is less
between the reader and the file.

---

## `dumping-export.py` — **(B)**

**Answers:** *what are the raw bytes of this export?*

**Run:** `python -I cc-studytools/tools/dumping-export.py <package> <substring-of-name> [--todos] [--contexto N]`

**Why it exists.** `package.py` says **where** each object is (`SerialOffset`, `SerialSize`)
and `probe-properties.py` knows how to **read** a tagged-property stream. In between was
missing the simplest and most often needed thing: **seeing the bytes.**

**And it exists for a measured reason.** The comparison of `UIDynamicFieldProvider` between
the game and our build **matched field by field** — and the engine still said:

```
Serial size mismatch: Got 12, Expected 16
```

**A `Got`/`Expected` does not say *which* field is missing.** It says four bytes are
missing and nothing more. To find out which, you look at the bytes the package really
carries.

**`Got` and `Expected`, read from the code and not assumed** (`UnLinker.cpp:3930`, string
in `Core.int:64`):

| | | |
| --- | --- | --- |
| `Got` | `Tell() − Export.SerialOffset` | what **we** consumed while reading |
| `Expected` | `Export.SerialSize` | what the **package** declares |

**So `Got < Expected` means we read *too little*** — the opposite of how it was read on
8/10, and that inversion was in every document until it was checked.

**Cannot see:** it does not interpret. It prints the bytes grouped, in hex and decimal,
and stops there.

**Runnable example:**

```console
$ python -I cc-studytools/tools/dumping-export.py CrimeCraft/CrimeCraftGame/CookedPC/Packages/UIScene_FrontEnd.ccpk UIDynamicFieldProvider
```

> **And this manual's example corrects the tool's own header**, which said
> `UIDynamicFieldProvider_2`. **That name does not exist in the package** — 30 matches
> without the suffix, **0** with it. Caught by `tools/verifica-manuales.py`, same family as
> `package.py`'s command line that was never a command line.

---

## `decode-material.py` — **(B)**

**Answers:** *what does this material's uniform-expression tree look like, byte by byte?*

**Cannot see — two things, and one of them is live:**

- It knows **only the 22 types in its own table**, and **that table lags
  `MaterialShared.cpp`**. Measured: it still lacks
  `FMaterialUniformExpressionTransformRange` — **the type added to the C++ on 9/10**. When it
  meets it the walk stops and says so. That is a gap, **not a wrong answer**, and the
  distinction is the whole reason the tool is trustworthy.
- It reads **bytes, not meaning**. It says what the tree **is**; it never says what the
  expression **computes**.

**Run:** `python -I cc-studytools/tools/decode-material.py <package.ccpk> <pos> [--n N]`

**Why it exists.** The engine kills a material load at `MaterialShared.cpp:1122`
`check(Type)` when the package carries an `FMaterialUniformExpression` **whose type is not
registered**. The `[MAT-EXPR]` probe in that same file prints **the name, the package and
the position**; this takes that position and **walks the chain** — which is what says how
many bytes each thing occupies.

**How it can walk without the engine — two measured facts:**

1. **`Ar.Tell()` *is* the file offset** in these `.ccpk`. Verified against the file's own
   bytes at position `59954` of `lobby_textures_banners_01.ccpk`. **So nothing has to be
   reconstructed and nothing has to be run.**
2. **An expression serialises as `[FName of the type][that type's data]`**
   (`MaterialShared.cpp:1104`). The table of "that type's data" comes from our own
   `MaterialShared.cpp`, which holds the 22 types the engine registers.

**Self-validating, and that is what makes it usable:** every step reads an `FName` that
**must** be a type in the table. If the walk desynchronises, the name is not in the table
and **the program says so** instead of returning a plausible tree.

> **A walk that cannot fail proves nothing.**

**Runnable example** — `59954` is the position the tool's own header measured:

```console
$ python -I cc-studytools/tools/decode-material.py CrimeCraft/CrimeCraftGame/CookedPC/Packages/Lobby/lobby_textures_banners_01.ccpk 59954
FMaterialUniformExpressionSine  (112 B, pos 59954..60066)
```

> [!important] **And this example exits with `1`, on purpose.**
> It is **the self-validation firing**, not a broken manual. Walking the siblings, the
> tool reaches one whose type is not in its table and says so:
>
> ```
> ** HERMANO 5 SE DESINCRONIZO en 60166: tipo 'FMaterialUniformExpressionTransformRange'
>    (indice 71) NO esta en la tabla, en offset 60174
> ```
>
> **So the exit code is part of the answer.** A reader who expects `0` will think the tool
> failed, and it is the tool doing the one thing that makes it worth trusting.
>
> **And the name it reports is a finding in itself:** `FMaterialUniformExpressionTransformRange`
> is **the type that was the material wall** — the one added to `MaterialShared.cpp` on 9/10.
> **This tool's table has not been updated since**, so the two have diverged: the C++ knows
> the type and the walker does not. That is a live gap, written here rather than left to be
> rediscovered.

---

## `class-in-package.py` — **(B)**

**Answers:** *what is inside this class — read from the package, not from a decompile?*

**Run:** `python -I cc-studytools/tools/class-in-package.py <package> <ClassName> [--hondo N]`

**Why it exists.** The project restores classes the game's `Engine.u` has and ours does
not: you write the `.uc` and rebuild. **To write the `.uc` you have to know what is
inside.** And a decompile is not always available — **UELib does not export classes with no
body**, so `noexport` classes, and those whose members are all native, **have no `.uc`**.
The **package** always has them.

**The rule that has to be understood.** In UE3 **a class's members are exports whose
`Outer` is the class.** Nothing has to be deserialised to see the list — it is enough to
look at who points at whom. And `ClassIndex` says which class each member is:

| `ClassIndex` | means |
| --- | --- |
| `== 0` | the member **is** a `UClass` |
| `> 0` | an export (1-based) — e.g. a `StructProperty` |
| `< 0` | an import (1-based) — **its `ObjectName` is the class** |

**Cannot see:** it does **not** deduce the **exact type** of a `StructProperty` or an
`ObjectProperty` — that lives in the property's data, not in the table. For that,
`probe-properties.py`. What this gives is the **shape**: how many members, of which kind,
in what order — which is what is needed to know **what** has to be restored.

**Runnable example** — `DiffObjectData` is one of the classes with no `.uc` to read:

```console
$ python -I cc-studytools/tools/class-in-package.py CrimeCraft/CrimeCraftGame/CookedPC/Engine.u DiffObjectData
```

---

## `walk-chunks.py` — **(B)**

**Answers:** *does this `FStaticLODModel`'s chunk array close — and if not, **in which chunk**
does it drift?*

**Cannot see:** it says **where** the walk stops matching, not **why**. And it stops at the
**first** chunk whose counts disagree — the chunks after it are never examined, so
*"N chunks bad"* is not a count of bad chunks. It is the count of one place to look.

**Run:** `python -I cc-studytools/tools/walk-chunks.py <package> <export-index> --desde <rel>`

**The check validates itself.** `FSkelMeshChunk` serialises, in this order:

```
BaseVertexIndex     UINT
RigidVertices       TArray<FRigidSkinVertex>   ->  4 + N*33
SoftVertices        TArray<FSoftSkinVertex>    ->  4 + N*40
BoneMap             TArray<WORD>               ->  4 + N*2
NumRigidVertices    INT     <-- the COUNT, AFTER the arrays
NumSoftVertices     INT     <-- likewise
MaxBoneInfluences   INT
```

**The counts come *after* the arrays.** So if the walk is correct each count **must** equal
its array's. If they disagree, **the drift is in that chunk — and you know which one.** No
guessing.

**And the element sizes are odd, which is what matters here:** `FRigidSkinVertex` is
`12 + 12 + 8 + 1 = 33`. So **a chunk with an odd number of rigid vertices flips the parity
of everything after it.**

**Runnable example** — and it **exits `1`**, which is the answer, not a failure:

```console
$ python -I cc-studytools/tools/walk-chunks.py CrimeCraft/CrimeCraftGame/CookedPC/Packages/Characters_Male_combocloth.ccpk 82 --desde 100032
export 82  offset=9130843  tamano=2285698
elementos: rigido=33 B  suave=40 B
chunks declarados: 8065  (en +100032)
  ** el contador de chunks es absurdo: el desvio es ANTES de +100032
```

> **`exit 1` means it found a desync and says where.** A tool of this kind that always
> returned `0` would be telling you it walked a stream that had already gone wrong.
> **Same shape as `decode-material.py`: the exit code is part of the answer.**

---

## `export-grid.py` — **(B)**

**Answers:** *is this export's data on an **even** or an **odd** byte grid?*

**Cannot see:** parity **eliminates a family of causes; it does not name one.** Knowing the
misalignment came from *before* the index buffer does not say **which** byte was read or
missed — only that the fault is upstream of there.

**And it counts, it does not prove.** A run of `u16` inside the plausible vertex-index band
can occur by chance, so what is read is the **contrast between the two grids**, not the size
of either.

**Run:** `python -I cc-studytools/tools/export-grid.py <package> <export-index> [--desde N] [--hasta N]`

**Why this is worth a tool.** On 5/10 it was closed, byte by byte, why the editor crashes
opening `EntryLevel.ccmap`: at **+8253** of export **82** the engine read `0x5B0FE30D`, took
it for a `TArray<short>` count, and asked for `1,527,767,821 × 2` bytes at once.

But `0x5B0FE30D` is not a count — **it is the inside of the index buffer.** The indices are
`WORD` and live on the **even** grid. **And +8253 is odd.**

> A `TArray<WORD>` starts even and measures an even number of bytes, so it **ends even**.
> Ending on odd means the misalignment **did not come from the index buffer — it came from
> before it, and it was odd.**

**That eliminates the entire "read one count too many" family and leaves exactly one:
someone read a byte that was not there, or failed to read one that was.**

**Runnable example** — the same export `82` as `walk-chunks.py`, so the two read together:

```console
$ python -I cc-studytools/tools/export-grid.py CrimeCraft/CrimeCraftGame/CookedPC/Packages/Characters_Male_combocloth.ccpk 82
=== rejilla PAR   rachas=0  u16 totales=0 ===
=== rejilla IMPAR   rachas=58  u16 totales=7655 ===
```

**And this example is the finding:** the index runs are **not on the even grid at all** —
58 runs on the odd one. That *is* the misalignment, measured rather than argued.

> **Choose the fixture carefully: a map's export 0 gives `rachas=0` on both grids** — a real
> answer that exercises nothing, and one that reads like a clean result. **A test case that
> cannot distinguish the two outcomes is not a test case.**

---

## `probe-prefix.py` — **(B)**

**Answers:** *what is the 4-byte integer that opens each export's data?*

**Run:** `python -I cc-studytools/tools/probe-prefix.py <package>`

**The state of the question, measured.** The header and the three tables are measured and
verified by closure; the property stream is identified. **But the first tag starts at `+4`,
not at `+0`, always** — and the four bytes in front belong to no tag.

The hint being chased: in exports 3, 4 and 5 the prefix is `2, 3, 4` — index minus one. In
1349, 1362 and 1364 it is `190, 203, 205` — index minus 1159. It advances one by one in both
runs, with a **different constant**. Two very different explanations fit:

| | |
| --- | --- |
| **(a)** | a counter that only counts *some* exports, and skips when one does not count |
| **(b)** | something that merely correlates with the index in those runs |

**The difference matters, and it is settled by looking at the whole package:** if (a), the
`i − prefix` column will be constant in runs; if (b), it will not.

**Cannot see — and this is why it is still open:** it does **not** settle (a) versus (b). It
prints the column so it can be read.

> **And this paragraph used to point at a section that did not contain it.** It said the
> prefix *"stands among the open questions of `UE3-PACKAGE-FORMAT.md` § 8"* — **and § 8
> listed five unknowns, none of them this one.** A cross-reference to an absence reads as a
> citation and is worth nothing. **§ 8 now carries it**, where it belonged: it is the
> boundary rule `probe-properties.py` needs and cannot yet meet.

**Runnable example:**

```console
$ python -I cc-studytools/tools/probe-prefix.py CrimeCraft/CrimeCraftGame/CookedPC/Maps/transient_map.ccmap
```

---

## `probe-tables.py` — **(B), and its question is now answered**

**Answers:** *what are the layouts of the import and export tables?* — **answered, and now
written up in `UE3-PACKAGE-FORMAT.md` § 4.** Kept because the measurement is the artifact.

**Cannot see:** it reports the two quotients that **bound** the tables; it does **not**
validate each record. **A table of the right total size can still be read with the wrong
stride** — which is exactly what happened, and why `package.py` checks per-record closure
instead of a total.

**Run:** `python -I cc-studytools/tools/probe-tables.py <package>`

**The hard fact that bounded it came from the header itself** — two quotients with no room
to argue:

```
ImportOffset .. ExportOffset      55,776 B / 1,992 imports  =  28.0
TotalHeaderSize - DependsOffset  742,636   = 185,659 x 4    ->  4 B per export
```

The second anchors the end of the export table; the first fixes the import size with no
ambiguity.

**And it had to be measured, not read:** `FObjectExport::Serialize` in the SDK **cannot be
the source — this branch of UE3 no longer keeps the version gates of that era.**

**Runnable example:**

```console
$ python -I cc-studytools/tools/probe-tables.py CrimeCraft/CrimeCraftGame/CookedPC/Maps/transient_map.ccmap
```

---

## `probe-properties.py` — **(B)**

**Answers:** *does "skip the 4-byte prefix and read tags" reproduce **every** export's data
exactly — and what struct is this property?*

**Run:** four modes, and each answers a different question:

**The four modes, as templates** — *not* runnable as written, and deliberately **not**
marked with `$ ` for that reason:

```text
python -I cc-studytools/tools/probe-properties.py <package>                # the count, by type
python -I cc-studytools/tools/probe-properties.py <package> - <index>      # one export's tag trace
python -I cc-studytools/tools/probe-properties.py <package> - tag <Prop>   # which struct is <Prop>
```

> **`$ ` marks a case the checker will RUN; `<package>` does not run.** Writing a template
> with `$ ` makes the checker execute a literal `<package>`, get an error, and record it as
> a result — **three of this manual's four entries did exactly that** before it was fixed.

**The test that decides — and what it currently answers, which is *not* "yes".**

**You do not need to know what the prefix *is* to know whether the rule is right.** The tag
stream always ends with a `NAME_None` tag, and each export's data is bounded by its
`SerialOffset` and `SerialSize`. So the criterion is:

> if you skip 4, read tags until `NAME_None`, and land **exactly** on the export's end, the
> rule is right. And it has to hold for **every** export, because each one is an independent
> checkpoint — a rule that only usually works is not a rule.

> [!danger] **And the criterion is NOT met. Measured on `EntryLevel.ccmap` (1,711 exports):**
> ```
> cierran exactas ............. 1280
> fallan ......................  431
> NO concluyente: fallan 431. El prefijo no es simplemente 4 bytes,
> o hay mas de un formato de exportacion.
> ```
> **1,280 close; 431 do not** — about three quarters. **That last line is the tool's own
> verdict, and it is the honest state of this question.**
>
> **An earlier version of this manual presented the criterion as if it had been satisfied**
> — *"it is demanded of all 1,711 exports at once … that is what makes the claim worth
> something"*, written as though the demand had been met. **It had not.** The criterion was
> written down as a *requirement* in the tool's own header; a manual then repeated it as a
> *result*. The two are one word apart and the difference is the whole finding.

**What this means, stated plainly:** the tag stream **is** read correctly — the property
types come out, `StructProperty` 1,714 · `IntProperty` 1,535 · `ArrayProperty` 413 … — but
**"skip 4 and it closes" holds for roughly three quarters of a map's exports and not the
rest.** So the corpus is readable *through* the tag stream for most objects, and the
boundary rule that would make it exact is **still open**.

**`FPropertyTag`** (`UnPropertyTag.h:58`):

```
FName Name   (8)   FName Type  (8)   INT Size  (4)   INT ArrayIndex (4)
[FName StructName]  only if Type == StructProperty
[BYTE  BoolVal]     only if Type == BoolProperty
[FName EnumName]    only if Type == ByteProperty
... then Size bytes of the value
```

**Cannot see:** what the prefix **is**. The rule it validates is *"a prefix of 4 exists"*,
not *"the prefix means X"* — that is still open, and `probe-prefix.py` is the one chasing it.

**A trap worth keeping, because it cost two zeros:** the `tag` mode searches the **whole
tree** with a **word boundary**, and both were paid for. Searching only the **first level**
returned `0` for `Scaling`, which lives inside `RenderParameters` — **a zero that looked
like "not present".**

**Runnable example:**

```console
$ python -I cc-studytools/tools/probe-properties.py CrimeCraft/CrimeCraftGame/CookedPC/Maps/transient_map.ccmap
```

---

## `mira-errores.py` — **(B)**

**Answers:** *what is the compiler complaining about, next to the line that causes it?*

**Run:** `python -I tools/mira-errores.py <log>`

**Runnable example.** It prints `no hay errores que leer` on today's log — **and that is
the right answer, not a broken example**: the run it came from finished cleanly. The
example still works as a regression check, because a broken invocation would print a
traceback instead of that sentence.

```console
$ python -I tools/mira-errores.py <LOG>
```

**Cannot see:** it shows the error the compiler *reports*, which is frequently not where
the cause is. A parse error nine lines later is the classic case.

---

## The four PowerShell tools over the game's own packages — **(B)**

**These are the ones that look most CrimeCraft-specific and are the least.** Each takes
the package as a parameter; what is CrimeCraft's is **only the default**, and a default
is already the parameter's fallback. Nothing here needs forking — see the note at the
end of this block.

**They all load `Eliot.UELib.dll` by reflection**, and it is **not distributed here** — it
is a third-party dependency with its own licence. How to get it is below, and **so are two
different licences**, because they are two different projects.

### Getting `Eliot.UELib.dll`

| | repository | licence | what it is |
| --- | --- | --- | --- |
| **UELib** | [`EliotVU/Unreal-Library`](https://github.com/EliotVU/Unreal-Library) | **MIT** | **the library — this is what produces `Eliot.UELib.dll`** |
| UE Explorer | [`UE-Explorer/UE-Explorer`](https://github.com/UE-Explorer/UE-Explorer) | **GPL-3.0** | the WinForms GUI, which these tools use **only as the DLL's carrier** |

> **The split is not a detail.** The piece these tools depend on — UELib — is **MIT**. The
> GPL-3.0 covers the GUI, which is not needed and not called. Anyone reading the DLL's
> origin and seeing one licence for both would draw the wrong conclusion about what they
> may do with it.

UELib targets **.NET Framework 4.8** and is also published as the NuGet package
`Eliot.UELib`. UE Explorer links UELib **as a git submodule**, so building its solution
builds the DLL along with it.

**Where the scripts look**, in order, both relative to the workspace root (that is,
`$PSScriptRoot\..`):

1. `ue-explorer-1.6.2-net48-portable\ue-explorer\Eliot.UELib.dll` — the portable tree
2. `UE-Explorer\UE Explorer\bin\Release\Eliot.UELib.dll` — a local build's output

`extract_uscript.ps1`, `generate-native-table.ps1`, `probe-native-flags.ps1` and
`inspect-function.ps1` **break** without it, and they say so by failing to find the file
rather than by explaining.

> [!note] And one thing these tools depend on is a **defect of UELib's**
> It classifies operators testing `IsPost()` **first**, with a weak test, so every prefix
> comes out as a postfix — the measurement is in `generate-native-table.ps1`'s own comment.
> **A reimplementation gets to fix that at the source instead of working around it**,
> which is one of the reasons one is planned.

### `extract_uscript.ps1`

**Answers:** *what did this cooked package's UnrealScript say?*

**Run:** `.\extract_uscript.ps1 -Paquete <path.u> [-Salida <dir>] [-Filtro <text>]`

A cooked package carries no `.uc` source — but it carries **bytecode**, and bytecode
keeps the structure: class names, inheritance, variables, enums, states and function
bodies. UELib rebuilds the source from that. **Only reads.**

**Cannot see:** **the original comments** — they never reach the bytecode. The source
that comes out is functionally equivalent and is **not** what Vogster wrote. And
`native` classes come out as **declarations only**, because their bodies are in C++ and
were never in the package.

**The `-Tabla` default is the game's `.NTL`** — that is the whole of its CrimeCraft tie.

### `generate-native-table.ps1`

**Answers:** *what are the native token numbers of **this** engine build?*

**Run:** `.\generate-native-table.ps1 [-Paquetes <path.u>] [-Salida <file.NTL>] [-SoloListar]`

**The direct route, not a deduction.** UELib names native calls from a per-engine-build
table, and it does not ship CrimeCraft's — so every native comes out as
`__NFUN_<index>__`. But **the table does not have to be guessed or found elsewhere: the
game's `.u` files carry it inside.** Every `UFunction` marked `Native` keeps its
`NativeToken` in the export table. This is what UELib itself does
(`UC_NativeGenerator.cs:64-75`). **Only reads.**

**Output format** (`.NTL`, from UELib `NativesTablePackage.cs`): `uint32` signature
`0x2C8D14F1` · `int32` count · per entry: `string Name` · `byte OperPrecedence` ·
`byte Type` · `int32 ByteToken`, where `Type` is `1=Function 2=Operator 3=PreOperator
4=PostOperator`.

**Cannot see — and this one is measured, not hypothetical:** it inherits **UELib's**
operator classification, which is wrong:

```csharp
if (function.IsPost())      Type = PostOperator;   // IsOperator() && prec == 0
else if (function.IsPre())  Type = PreOperator;    // ...this branch never runs
```

`IsPost()` is tested **first** and its test is **weak** — `prec == 0` is true for
prefixes too. Measured in the game's own package:

```
129  !   prec=0   …PreOperator…   IsPre=True  IsPost=True
165  ++  prec=0   (no PreOperator)  IsPre=False IsPost=True
```

`!` **does** carry `PreOperator`, and `IsPost()` wins anyway; the decompiler then paints
the operator **behind** its operand — it emitted `bBlockRotation!`.

**Corrected here, in the generator** (`cc-studytools/tools/generate-native-table.ps1:112-114`): `IsPre()`
is tested first. **9 prefixes rescued.** The lines above are the measurement, quoted in
the script's own comment.

> **And it is not our table's defect, it is UELib's** —
> `NativesTableList_DukeNukemForever2011.NTL` ships `!` as `PostOperator` for exactly
> this reason. Every `.NTL` UELib ships carries it.

### `probe-native-flags.ps1`

**Answers:** ***does the game's package really mark `PreOperator`?*** — the check that
decides whether the fix above is ours to make or is blocked upstream.

**Cannot see:** it reads the flags the **package declares**. It does **not** run the
decompiler. So it tells you what the **data** says — which is what makes the fix available —
and not what UELib **does** with it. **That gap between the two is the entire point** of the
distinction above.

**Run:** `.\probe-native-flags.ps1 [-Tokens 129,165,160] [-Paquete <path.u>]`

**What it answered: yes.** So the correction belongs on our side — we are the ones who
write the `.NTL` — and it is a one-line ordering change, not a toolchain problem.

**Why it is worth keeping rather than deleting now that it has answered:** the finding is
a property **of UELib**, not of this build. Point it at a **different licensee build** and
the question is live again.

### `inspect-function.ps1`

**Answers:** *when the compiler complains about something in the SDK — does the game say
it too?*

**Run:** `.\inspect-function.ps1 -Clase Weapon [-Funcion SetPendingFire] [-Paquete <path.u>]`

**Why the question is worth a tool.** Our SDK is engine **10897**; the game is **4701**.
Every complaint about the SDK has two explanations and they are **opposite**:

| | | |
| --- | --- | --- |
| **(a)** | the game says it too | **the stub is wrong** |
| **(b)** | the game does not | it is an SDK **drift**, and aligning with the game is **restoring fidelity**, not breaking anything |

This reads the export table and says which. **Only reads.**

**Cannot see:** declarations, not behaviour. **And the package holding a class is not
always the obvious one** — `Weapon` is in `Engine.u`, the game's own classes are in
`CrimeCraft.u`. If `-Paquete` is omitted it searches a list **and prints where it found
it**, because *"not there"* and *"not searched"* are different answers.

> **On all four.** The tempting move is to fork each into a "CrimeCraft version" and a
> "generic version". **That is the mistake this codebase already paid for** — six copies
> of the export-table reader drifted apart, three with a different stride, and **41.7 %
> of one package's records were read wrong, silently.** Here the parameter already exists;
> what is CrimeCraft's is the default. **A default is not a fork.**

---

## `mide-especificidad.py` · `audita-rutas.py` — **PROJECT**

**Answer:** *which tools are game-specific?* / *which tools break if moved?*

**Run:** `python -I tools/<name>`

**Runnable example:**

```console
$ python -I tools/mide-especificidad.py --lado CRIMECRAFT
```

**Not for redistribution** — they are about this repository's own organisation.

**Both were wrong on their first attempt, the same way:** the specificity classifier
stripped comments **and strings** — deleting exactly the path literals it was looking for
— and reported 13 false "generic". The path auditor knew only `__file__` and declared
three PowerShell scripts fragile that had been correct from the start.

> **An instrument that deletes the thing it is looking for returns a zero that looks
> like a finding.**

**And the specificity one has now been wrong three times, in two directions:**

| | said | was |
| --- | --- | --- |
| 1st | strips comments **and strings** | **13 false "generic"** — it deleted the literals it was looking for |
| 2nd | strips **only** comments | ✅ — but **a docstring is also a string**, so 6 tools that merely *mention* CrimeCraft in their headers came out "specific" |
| 3rd | splits by location, for **names** | ❌ still counted a **path** inside a docstring as wired |
| 4th | splits by location, for **both searches** | ✅ **59 / 11 / 23** |

**And what it still cannot see, which is written into the tool:** it measures the **shape**
of the literal, not its **role**. `audit-package-coverage.py:276` matches because of a
`print("… Medido en CrimeCraft.u: …")` — **a note to the reader, not a path that gets
opened.** Distinguishing "a path that is used" from "a path that is named" means following
the data flow, and a counter does not follow anything. **So its output is a list to look
at, not a verdict.**

---

## `porta-defaultproperties.py` — **(A), but generic in shape**

**Answers:** *what `DefaultProperties` block is this class missing?*

**Run:** `python -I tools/porta-defaultproperties.py --lista | <class> … | --todas`

**Runnable example** (`--lista` only **reports**; the other two forms **write into the
SDK tree**, which is why the safe one is the one that goes here):

```console
$ python -I tools/porta-defaultproperties.py --lista
```

**Why it exists:** the game's script **export drops `DefaultProperties` blocks** for a
whole family of classes. Without them the CDO has no subobjects, and the engine reports
one `ObjectArchetype` failure **per instance**.

**Handles the preprocessor trap:** `` `if ``/`` `else ``/`` `endif `` can wrap **only the
opening line** of a block, with the body shared. Copying it verbatim yields
`Unexpected preprocessor macro 'Else'` **pointing at a different line.**

**Cannot see:** it does **not** verify the values are the game's. They are Epic's. Where
the game's cooker changed a default, the wrong value is silently carried.

---

# CLOSED tools — what they answered

**Kept for the record.** Each answered one question during a specific investigation;
the answer is the artifact, not the tool.

| tool | answered |
| --- | --- |
| `analiza-tipos.py` | how every type the game's script references classifies |
| `comprueba-cobertura.py` | whether a class is analysed **for real** — by planting a probe in it |
| `identifica-operadores.py` | the `__NFUN_NNN__` native-operator table |
| `lista-miembros-perdidos.py` | which members the compiler cannot find, and where |
| `mide-anidamiento.py` | parenthesis nesting in the stubs |
| `mide-arrays.py` | the real size of an array declared `[EEnum]` |
| `mide-cast-int.py` | how many `int(...)` casts exist, and in which form |
| `mide-deriva.py` | every stub signature that disagrees with its SDK parent |
| `mide-firmas.py` | stub signature **beside** its SDK parent's, for eyeballing |
| `mide-goto-foreach.py` | `goto` and its label in `foreach` — **the measurement that detects the real problem** |
| `mide-paquete-crimecraft.py` | where `CrimeCraft.` appears in the stubs |
| `mide-sombreados.py` | the classes that **shadow** the engine, and why that explains the largest error family |
| `mide-tipo-del-cast.py` | what is inside `int(...)`, in the compiler's own naming |
| `mide-within.py` | for each `Unrecognized type 'X' within 'Y'`, whether `Y` has its own errors |
| `verifica-diff-paquete.py` | that the rewrite rule changes `CrimeCraft.` as intended |
| `alinea-paridad.py` · `alinea-traza.py` | aligning a measured trace against the game's own bytes |

---

# Group (A) — about the game's content

**Six tools, and they have no meaning without the game.** Each is a step of one chain:
*the map imports classes the engine does not have → declare them as stubs → compile the
stubs → measure how far that got.*

```
u3pack tipos  ──▶ generate-game-catalog.py ──▶ generate-stubs.py ──▶ compila-stubs.sh
   (external)          (filter)                 (declare)          (verdict)
                                                      │                 │
                                                progress.py        cdb-…  (when it crashes)
                                                      │
                                              census-ccmap.py  (what is still unreadable)
```

**⇒ Where this chain goes in a move: all six together or none.** Handing someone
`generate-stubs.py` without `generate-game-catalog.py` hands them a tool whose input they
cannot produce.

---

## `generate-stubs.py` — **(A) the head of the chain**

**Answers:** *which `.uc` files must exist so the engine can deserialise what the map
saved?*

**Run:** `python cc-studytools/tools/generate-stubs.py [--dry-run]`

**Runnable example** (`--dry-run` **reports without writing**, which is why it is the one
that goes here):

```console
$ python cc-studytools/tools/generate-stubs.py --dry-run --origen <EXPORT> --sdk <SRC> --datos <DATA>
```

**Why stubs and not the game's own package.** The map imports `CrimeCraft` classes
(`CCEntryPawn`, `SeqVar_CCBoolStates`, `PositionPreset`…) the engine cannot find. Loading
the game's `CrimeCraft.u` does not work: it was **cooked at engine build 4701** and our
SDK is **10897** — it desynchronises. So the chosen route is **stubs**: declare the classes
so the engine can *deserialise* what the map stored, without reproducing behaviour.

**The vehicle already existed** and is documented in `DefaultEngine.ini`:
`EditPackagesInPath` + `+EditPackages=<Package>`, which requires
`Development/Src/<Package>/Classes` to exist. The engine compiles those `.uc` into
`DemoGame/Script/<Package>.u`. **The folder is what decides, not the line** — which is
exactly why `EditPackages=DemoGame` is switched off: its source folder does not exist.

**The transformation is short and mechanical:** strip `native` from the class declaration
(a stub has no C++ half); mark the **extraction artefacts** that are not valid
UnrealScript (`Components=/* Array type was not detected. */`, flag comments like
`/*0x20000000-0x00000000*/`, and the `// Reference:` / `// TemplateOwner*` /
`// Archetype:` lines); and **withdraw** stubs for classes the list no longer asks for —
the compiler reads the **folder**, so an obsolete stub compiles anyway and drags in its
own unresolved types.

**Cannot see — and this is a correction of its own docstring.** It used to claim it
"checks that every referenced type resolves". **It did not.** `tipos_del_sdk()` was
computed and used only to print its size. This was discovered while investigating why the
compiler found unresolved types the class list already contained.

**Not implemented on purpose:** the script compiler does that check properly, reaches the
package in ten seconds, and names the exact type and line. Reimplementing it approximately
would only add a source of false positives needing its own debugging.

**Does not decide anything about what it does not understand — it reports it.** A
generator that silently repairs the artefacts it cannot parse produces stubs that compile
and do not do what they appear to.

**And the package name is derived from the folder, not written** — so renaming the package
follows the rewrite rule on its own.

---

## `generate-game-catalog.py` — **(A) the filter before it**

**Answers:** *which of the game package's 185,659 exports matter for the stubs?*

**Run:**
```bash
u3pack tipos <package>.u > raw.txt
python cc-studytools/tools/generate-game-catalog.py raw.txt tools/tipos-crimecraft.txt
```

`u3pack tipos` dumps **one line per export**, and almost all of the 185,659 in
`CrimeCraft.u` are functions, constants and string buffers that the generator **never
looks at**. Versioning the whole dump is 16 MB to store what fits in less than half.

**The filter is not an opinion:** it is exactly the kinds `tipos_del_juego()` consumes —
`ScriptStruct`/`Enum` (the *kind* of a type), the property kinds (the *type* of a member),
and `StructProperty`/`ArrayProperty`, which **cannot** be typed from the export table
(the struct's name lives in the `FPropertyTag`) and therefore **block** the declaration of
the whole type. Those are **kept on purpose: they are the list of what is missing.**

**Cannot see — because it does not sort.** Export order **is** declaration order, and a
struct's member order **is** its layout. A `sort -u` destroys that **silently**, and it
did, once.

**Falsifies itself:** its kind sets must equal `generate-stubs.py`'s. It checks, and
**fails** if they differ.

---

## `compila-stubs.sh` — **(A) the verdict**

**Answers:** *does the stub package compile?*

**Run:** `bash tools/compila-stubs.sh`

**Why it is a script and not a command line.** The loop is five steps and **three of them
exist for traps that each cost a full round:**

| # | step | the trap it exists for |
| --- | --- | --- |
| 1 | enable `+EditPackages` in `DefaultEngine.ini` | it is commented out on purpose |
| 2 | **delete** `DemoEngine.ini`'s copy | the engine persists its runtime config **there**, and commenting the line in `DefaultEngine.ini` switches **nothing** off by itself |
| 3 | **delete the log** | a reading loop matches the **previous** "Warning/Error Summary" and accepts a stale result as today's |
| 4 | `make -unattended -auto` | |
| 5 | `taskkill` | the process **does not terminate on its own** after compiling, and the shell's `kill` does not kill it — processes accumulate |

It leaves the line commented again, so the editor's startup is unchanged.

**Cannot see:** it reports the compiler's verdict and nothing about *why* — for that, the
code is in `mira-errores.py`.

**`trap` and a ceiling, both — and the reason is on the record.** On 30/9 the `until` had
no ceiling, the engine exited before writing the summary, the script hung, it was killed —
and **both `.ini` files were left switched on**: the editor then starts up wanting to
compile the stubs, which is the one thing this script exists to prevent.

---

## `cdb-compila-stubs.sh` — **(A) the same loop, under the debugger**

**Answers:** *where does the compile crash?*

**Run:** `bash tools/cdb-compila-stubs.sh`

Same six steps, same traps, **step 4 replaced by `cdb`** — because the crash is a
`SIGSEGV` with **no `Critical:` and no `.dmp`**, and the log is cut mid-line. That leaves
diagnosis to guessing: you read the compiler's messages and conjecture which one it cannot
format. Under the debugger there is no conjecture — the faulting address, the module and
the stack are all there.

**Cannot see:** `cdb.exe` is a hardcoded path into the Windows Kits. Without the SDK
debuggers installed, it does not run — and it will say so by not finding the file, not by
explaining.

---

## `progress.py` — **(A) the fraction**

**Answers:** *how much of this is done — as a fraction, not as a sign of movement?*

**Run:** `python cc-studytools/tools/progress.py [--guardar] [<other.log>]`

**Runnable example** (`--guardar` appends a row to the CSV; without it, nothing is written):

```console
$ python cc-studytools/tools/progress.py <LOG> --nuestros <SDK> --juego <GAME> --consumidor <GAME>/CrimeCraft.u --csv docs/progreso.csv
```

**Why it exists.** For a week, the only way to answer "how far along are we?" was to watch
whether `[SZ]` was rising. **`[SZ]` rises — and it is not a fraction.** Movement is not
progress, and with a rising counter you cannot tell whether the path converges.

It gives the three figures that do: classes touched / classes the package declares;
objects still missing (the offline census); and the **delta since the last run**.

**How it measures the fraction, and why this way.** The `[SZ]` probe prints one line per
serialised struct with its name. Counting the **distinct** `CrimeCraft.<Class>` that
appear and dividing by the classes the package declares gives the fraction.

**Two earlier measures were used, both bad, and the reasons are worth keeping:**

1. **`bcstart` / file size** — looks natural, since `bcstart` is a position in the file.
   **But `bcstart` decreases within each class**: members are laid out in reverse in the
   file, so the sequence rises and falls. Measured: of 16,580 reads, **15,499 decrease.**
   As a fraction it is worthless.
2. **The last object in the log** — it is not the maximum. Loading stops at the **first**
   failure, so the last `[SZ]` may sit behind the furthest point reached.

**Cannot see:** the run stops at the first failure, so **every class beyond that point is
invisible**. The fraction is a **floor, not the truth** — and the census says which
classes are missing **by name**, which is what keeps the two from being confused.

---

## `census-ccmap.py` — **(A) the map-by-map census**

**Answers:** *for each map, what fraction can we read — and what is **not** measured?*

**Run:** `python cc-studytools/tools/census-ccmap.py [--raiz <dir>] [--pivote <map>] [--sin-control] [--limite N]`

**Runnable example** — `--limite` reads only the N lightest maps and **writes no CSV**:

```console
$ python -I cc-studytools/tools/census-ccmap.py --raiz <GAME> --nuestros <SDK> --revisa . --limite 3 --sin-control
```

One row per map, ordered **lightest → heaviest by bytes** — that **is** the work order —
with `City05_HQ` marked in the `pivote` column.

**It does not invent a second reader.** It uses `package.py` (the self-validating one) and
`census-imports.py` (resolution by **full `outer` chain**, not by substring: `BoneAtom`
appears 153 times in our `Engine.u`, but as `Core.BoneAtom`). **A second instrument would
be a second place to lie.**

**Resolution rules:** `ci < 0` → an import, resolvable if its **root** is in the provider
index *and* the full path is among its exports; `ci > 0` → a local export, its class is in
the file itself; `ci == 0` → `UCLASS_INDEX`, the export **is** a `UClass`.

**Cannot see — and this is the misreading that does the damage:** `entendido_pct` is
**layer 2**. It says *"we know which class to read it with"*, **not** *"we can read it"*.
Layer 3 — the content of each export — **is not measured for any map**, and the column
carries the literal **`NO MEDIDO`** in every row so that nobody reads the header as whole.

**The control is on screen, and that is deliberate.** The same census is run with **the
game's own packages as providers**. That is the **by-construction background noise** (the
`noexport` classes — `Core.Class` and friends are exported by no package, they resolve
natively). Both numbers are printed. **If the control came out *worse* than ours, our
index is wrong** — and the report says so instead of hiding it.

**Two parameters it takes, and one it deliberately does not.**

`--raiz` and `--pivote` were hardcoded to this project. Both are now arguments whose
**defaults are unchanged**, and both are checked: pointing `--raiz` at something that does
not exist aborts with exit 2 rather than producing an empty census. **The walk not failing
is the danger** — zero maps reads as a measurement.

**The extension is *not* parameterised, on purpose.** This is *the map census*.
`census-corpus.py` is the one that walks all three kinds and **reuses this same metric** —
adding `--extension` here would leave **two walks where there is one**, which is the
duplicate-reader failure this codebase already paid for.

---

## What every manual must say

1. **The question it answers** — one sentence, in the tool's own terms.
2. **How to run it**, with a real example.
3. **What it cannot see.** *This is the section that matters* — a tool whose limits are
   unwritten gets believed past them.
4. **The check that falsifies it**, ideally against a case whose answer is known.
