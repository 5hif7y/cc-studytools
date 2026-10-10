# The UE3 package format — `.u`, `.upk`, `.ccmap`, `.ccpk`

**Byte-level layout of an Unreal Engine 3 package, as measured on a real corpus of
550 files.** Every number below was read from a file, not from documentation or from
the engine's source.

> **Scope.** This describes the **container**: the header, the three tables, and how to
> find where each object's data begins and ends. It does **not** describe what is
> inside each object — that is per-class and lives in each class's own serializer.

---

## 1. The three rules that make this readable without the engine

A package is **header + tables + the data of each export**, and **the tables say where
everything is**. That gives four identities that hold on every well-formed file, and
they are what makes an independent reader checkable:

1. the **name table** ends exactly at `ImportOffset`
2. the **import table** ends exactly at `ExportOffset` — 28 bytes per entry
3. the **export table** ends exactly at `DependsOffset` — `68 + 4·N` per entry
4. the **last export** ends exactly at the last byte of the file

**If any of the four fails, the reader is wrong — not the file.** Check them before
believing any field read from a package.

---

## 2. Header — `FPackageFileSummary`

Layout is **identical** in `.u`, `.upk`, `.ccmap` and `.ccpk`. Measured on
`EntryLevel.ccmap` (23,023,618 bytes).

| Offset | Size | Field | Value seen | Meaning |
| --- | --- | --- | --- | --- |
| `0x00` | 4 | `Tag` | `0x9E2A83C1` | `PACKAGE_FILE_TAG` — bytes on disk `c1 83 2a 9e` |
| `0x04` | 4 | `FileVersion` | `0x00050240` | `(licensee << 16) \| epic` → **epic 576, licensee 5** |
| `0x08` | 4 | `TotalHeaderSize` | 175,688 | end of the `DependsMap` |
| `0x0C` | 4 | `FolderName` length | 5 | **includes the NUL** |
| `0x10` | 5 | `FolderName` | `"None\0"` | no folder in the Generic Browser |
| **`0x15`** | 4 | `PackageFlags` | `0x008A0009` | **not 4-byte aligned** |
| `0x19` | 4 | `NameCount` | 1,511 | |
| `0x1D` | 4 | `NameOffset` | 134 | |
| `0x21` | 4 | `ExportCount` | 1,711 | |
| `0x25` | 4 | `ExportOffset` | 52,368 | |
| `0x29` | 4 | `ImportCount` | 309 | |
| `0x2D` | 4 | `ImportOffset` | 43,716 | |
| `0x31` | 4 | `DependsOffset` | 168,844 | |
| `0x35` | 16 | `Guid` | | package GUID |
| `0x45` | 4 | `Generations.Num` | 1 | |
| `0x49` | 12 | `Generations[0]` | `(1711, 1511, 328)` | `(ExportCount, NameCount, NetObjectCount)` |
| `0x55` | 4 | `EngineVersion` | **4701** | the build that cooked it — **not** the SDK's constant |
| `0x59` | 4 | `CookedContentVersion` | 87 | |
| `0x5D` | 4 | `CompressionFlags` | **`0x00000000`** | **no compression** |
| `0x61` | 4 | `CompressedChunks.Num` | 0 | |
| `0x65` | 4 | `PackageSource` | `0x39F9CA95` | varies per package |
| `0x69` | 4 | `AdditionalPackagesToCook.Num` | 1 | |
| `0x6D` | 4+21 | `FString` | `"EntryLevel_oceanside\0"` | sublevel loaded with this map |
| — | — | **end** | **`== NameOffset`** | exact validation |

**Watch two traps:**

- **`PackageFlags` sits at `0x15`, not at a 4-byte boundary.** Assuming alignment
  shifts everything after it.
- **`FolderName`'s length includes the terminating NUL.** Off by one shifts the flags.

---

## 3. The three arithmetic checks

These are what let a reader falsify itself instead of being trusted.

### 3.1 `TotalHeaderSize − DependsOffset == 4 × ExportCount`

The `DependsMap` is a `TArray<TArray<INT>>` with one **empty** array per export —
hence exactly 4 bytes per export.

| file | `TotalHeaderSize` | `DependsOffset` | difference | `ExportCount` | ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Core.u` | 113,544 | 108,220 | 5,324 | 1,331 | **4.000** ✅ |
| `EditorMaterials.ccpk` | 30,065 | 28,929 | 1,136 | 284 | **4.000** ✅ |
| `EntryLevel.ccmap` | 175,688 | 168,844 | 6,844 | 1,711 | **4.000** ✅ |
| `arena01.ccmap` | 904,694 | 858,382 | 46,312 | 11,578 | **4.000** ✅ |

### 3.2 The table ends land exactly on the next table's offset

See § 1. All four identities hold across the corpus.

### 3.3 The last export ends at the last byte

**Together these mean a wrong read cannot stay plausible**: it breaks an identity.

---

## 4. The tables

**On-disk order: names → imports → exports → depends.** All three tables are at the
offsets in the header, and each is a flat array.

### 4.1 Names

```
INT32  length          //                       bytes, NUL excluded by some writers
BYTE[] characters      // ANSI, NUL-terminated
QWORD  flags           // 8 bytes, always present in this version
```

The **8 trailing flag bytes per name are still not established**. A reader must carry
them through unchanged — see § *Open questions*.

### 4.2 Imports — 28 bytes each

```
FName  ClassPackage    // 8
FName  ClassName       // 8
INT32  OuterIndex      // 4
FName  ObjectName      // 8
```

**`OuterIndex` convention, and it is the same in both tables:**

| value | means |
| --- | --- |
| `> 0` | **export**, 1-based |
| `< 0` | **import**, 1-based — zero-based index is `-n − 1` |
| `== 0` | the package / the root |

**Getting this backwards is silent**: assuming negative meant *export* produced 99.95 %
of imports unresolved in one measurement — a number that looks like data and is an
artefact.

### 4.3 Exports — **variable stride**, `68 + 4·N`

```
INT32  ClassIndex       // 4
INT32  SuperIndex       // 4
INT32  OuterIndex       // 4
FName  ObjectName       // 8
INT32  ArchetypeIndex   // 4
QWORD  ObjectFlags      // 8
INT32  SerialSize       // 4
INT32  SerialOffset     // 4
INT32  ExportFlags      // 4
INT32  GenerationNetObjectCount   // 4 (+ 4·N following)
GUID   PackageGuid      // 16
INT32  PackageFlags     // 4
```

> [!danger] **The stride is `68 + 4·N`, not 68.**
> Five separate tools in one project read this table with a **fixed** stride of 68 and
> got **41.7 % of records in one package and 53.1 % in another** wrong — **silently**,
> because a shifted value still looks like a number.
>
> **A format assumption shared by several tools is audited by none of them.**

`ClassIndex` needs two rules of its own:

- `> 0` → export, 1-based
- `< 0` → import; **use the import's `ObjectName`, not its `ClassName`**
- `== 0` → the export **is** a `UClass`

Reading `ClassName` for an import put **1,711 of 1,711** exports in one package — and
**95.09 %** of an entire 10.57 GB corpus — into a single wrong bucket.

---

## 5. Map packages — what makes a `.ccmap` a map

Three facts, all measured:

1. **The map contains an object literally named `TheWorld`**, of class `World`, with
   `Outer` = `None`. **That is the string the engine looks for.**
2. **`PackageFlags` carries `PKG_ContainsMap`** (`0x008A0009` includes it) — this is
   the **reliable** discriminator, better than the extension.
3. **The extension `.ccmap` is configuration, not code**: it comes from `[URL] MapExt`
   in an ini file. The same container read as `.u` is still a package.

**A `.ccpk` is the same container with content instead of a world.** There is no
format difference between `.ccmap`, `.ccpk` and `.u` — **only in what they are used
for** and in which objects they happen to hold.

**4. How a map's objects are arranged under the World.** Measured on four maps spanning
11 to 11,578 exports:

```
<map>.TheWorld                              class World, Outer = the package
<map>.TheWorld.PersistentLevel              the level
<map>.TheWorld.PersistentLevel.<Actor>      actors: exports whose Outer IS the level
<map>.TheWorld.PersistentLevel.Model        level geometry, likewise
```

**All four maps have `TheWorld` and a `PersistentLevel`, and their actors are ordinary
exports whose `Outer` is the level** — so **the full name path, which § 4 already tells you
how to resolve, is enough to find them.** No extra format is involved.

> **And this is where the reading stops being sufficient.** The level also holds its own
> **serialised** data, and the tag stream that would walk it is the one with the open
> boundary rule in § 8. **See the section below before planning a loader.**

---

## 6. Compression

**Measured: none of the corpus is compressed.** `CompressionFlags = 0` and
`CompressedChunks.Num = 0` in every file checked.

> **This is a property of *this* corpus, not of the format.** A reader that assumes it
> globally will break on the first compressed package it meets, and the failure will
> look like a corrupt table rather than a missing code path.

---

## 7. Version marks — `576` does not identify an engine

**A package carries TWO marks**, `FileVersion` decomposes into `(licensee << 16) | epic`,
and **two different engines share `576`**:

| build | epic | licensee | who |
| --- | ---: | ---: | --- |
| Vogster | 576 | **5** | the authors of CrimeCraft |
| Batman: Arkham Asylum | 576 | **21** | a different engine entirely |

**No `Ar.Ver()` gate catches this difference.** It cost a full measurement round: the
struct `BoneAtom` is **40 bytes under Vogster and 32 under Batman**.

> **The rule that follows: the package being read is what decides. If the code does not
> match it, the code is what changes.**

---

## 8. Open questions

**Listed rather than guessed**, because a plausible number nobody checked gets built on:

| unknown | what is known |
| --- | --- |
| the **8 trailing bytes of each name entry** | present in every file, size constant; carried through unchanged |
| **two integers per export** whose meaning is not established | likewise carried through |
| **the 4-byte prefix that opens each export's data** — *is it really 4?* | **it is 4 for most exports and not for all.** Measured on `EntryLevel.ccmap` (1,711 exports): skipping 4 and reading tags until `NAME_None` **closes exactly on 1,280 and fails on 431**. So the prefix is **not simply 4 bytes, or there is more than one export format** — the tool's own words. **This is the boundary rule a reader of a package needs, and it is not settled.** `probe-prefix.py` · `probe-properties.py` |
| the **literal value of `MapExt`** | not present in any readable ini in the installation; the *mechanism* is established (§ 5) |
| what `PackageSource` encodes | varies per package |
| why the engine's own loader **desynchronises** on some cooked packages | the reason an independent reader exists |

---

## 9. If you are writing a loader — read this first

**This document describes the container. A loader needs the contents, and they are not
here.** The list below says exactly where the boundary is, so the gap is a known quantity
rather than a surprise three weeks in.

| what a `.ccmap` loader needs | where it stands |
| --- | --- |
| the header, the three tables, and each object's offset and size | ✅ **this document**, verified on **550 of 550** files |
| resolving names, imports and exports, with the `Outer` / `Class` conventions | ✅ **this document** § 4 |
| finding the world and the level, and finding actors under the level | ✅ **this document** § 5 |
| the layout of a tagged property (`FPropertyTag`), and that a value is `Size` bytes | ✅ **`TOOLS.md`**, `probe-properties.py` — *not in this document* |
| **the boundary rule that says where an object's data ends** | ⚠️ **OPEN** — § 8. Holds for ~**three quarters** of a map's exports, not all |
| **what each property *means*** (that one named `Location` is a position, in what units) | ❌ **not documented anywhere** |
| **coordinate conventions** — axis, handedness, scale | ❌ **not documented anywhere** |
| **mesh formats** — vertices, indices, the LOD/chunk layout | ❌ **not documented anywhere.** `TOOLS.md` has two tools that *walk* them (`walk-chunks.py`, `export-grid.py`), which is not a specification |
| **texture formats**, mipmaps, UVs | ❌ **not documented anywhere** |
| compression | ✅ declared — but as **"none in *this* corpus"**, which is a property of the corpus, not the format (§ 6) |

**So, plainly: the container is specified well enough to write a reader for it today. A
*map* loader also needs the property boundary rule and the asset formats, and neither is
finished.**

**Work in this order, and the order is not preference — it is what unblocks what:**

1. **Settle the 4-byte boundary rule** (§ 8). Nothing downstream is safe while a quarter of
   a map's exports cannot be bounded; every later reading inherits that uncertainty.
2. **Write the tagged-property value format down** — the tag layout exists in `TOOLS.md`;
   what is missing is what each type's value *is*.
3. **Only then the assets** — meshes and textures. They are the largest part by bytes and
   the least urgent, because a loader that can place actors and read their transforms
   already shows a level.

> **And one warning that the rest of this repository earned the hard way.** Every number
> above was measured against a real file, and where something is unknown it is written down
> as unknown. **A plausible number nobody checked gets built on** — which is why the
> boundary rule in § 8 is written as *"1,280 close and 431 do not"* rather than as *"the
> prefix is 4 bytes"*. The second reads better and would have been wrong.

---

## 10. How to verify any of this

The identities in § 3 are the whole point: **they can be checked on every file in the
corpus in one pass**, and they fail loudly. A reader that reproduces them is not being
taken on faith, and a document whose numbers break them is falsified by the same
command.
