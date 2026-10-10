# Building an editor for CrimeCraft content — working base

> [!warning] **INCOMPLETE, AND DELIBERATELY SO.**
> **The investigation this document depends on has not been finished.** What is here is
> what has been *measured*; every "unknown" below is **work to do, not a gap in the
> writing**. It is published because a half-answer with its edges marked is worth more to
> the next developer than a blank page — **and a plausible answer nobody checked is worth
> less than either.**
>
> The same applies to `UE3-PACKAGE-FORMAT.md` § *If you are writing a loader*: it says
> what is finished and what is not, for exactly this reason.

---

## 1 · The honest starting condition, as three numbers

**How much of the game's data can we currently read**, measured in bytes, by export class,
across the whole corpus (9/10):

| corpus | files | mean readable |
| --- | ---: | ---: |
| `.u` — code packages | 12 | **50.1 %** |
| `.ccmap` — maps | 218 | **64.2 %** |
| `.ccpk` — content packages | 320 | **72.0 %** |

**And what that number does *not* mean.** It measures **classes resolved** — *"we know which
class to read this export with"* — **not content understood.** A `.ccpk` at 72 % is not "72 %
of it is interpreted". Conflating the two is the single most damaging misreading of these
figures, and it is written into every tool that produces them.

**The figures rise as classes are restored.** They carry their date for that reason.

## 2 · Why an editor, and why not the one that ships

`CrimeCraft.exe editor` **does not open an editor** — verified, not assumed.

The route actually taken is: **reconstruct the SDK from the game's own packages**, build it
with a modern toolchain, and let *that* engine open the content.

**And that route has a publishing problem with a clean answer.** The reconstructed SDK
**contains proprietary code** and cannot be shared. **An editor distilled down to only what
is needed to open and display content can be** — which is the whole point of this document.

## 3 · What exists today

Everything in this repository. The pieces an editor would actually build on:

| need | tool | state |
| --- | --- | --- |
| read the package container | `package.py` | **verified on 550 of 550 files** |
| walk names, imports, exports | `package.py` | done, with the `Outer`/`Class` conventions |
| read an object's tagged properties | `probe-properties.py` | **reads the tags; the boundary rule is open — see the format spec § 8** |
| find the world, the level and its actors | — | **documented, measured on four maps**: actors are exports whose `Outer` is the level |
| read a material's expression tree | `decode-material.py` | walks it and self-validates |
| walk mesh chunks and index grids | `walk-chunks.py`, `export-grid.py` | **they walk; they do not specify.** A format document does not exist |

## 4 · What an editor needs that is not here

**Listed so the gap is a known quantity.** A developer should be able to read this and
decide, in an afternoon, whether to start.

1. **The property boundary rule.** A quarter of a map's exports cannot be bounded exactly.
   **Everything downstream inherits that uncertainty**, which is why it comes first.
2. **What each property means** — that one named `Location` is a position, in what units.
3. **Coordinate conventions** — axis, handedness, scale. **Nothing is written down.**
4. **Mesh formats** — vertices, indices, LOD chunks. Two tools *walk* them; that is not a
   specification.
5. **Texture formats**, mipmaps, UVs.
6. **A renderer path.** Nothing here draws anything.

## 5 · The order, and it is a dependency order

```
  boundary rule  ──▶  property values  ──▶  assets  ──▶  a viewer
       (1)                  (2)             (3)          (4)
```

**Nothing downstream is safe while (1) is open.** An editor built before it would place
actors at wrong offsets for a quarter of the map and appear to work.

**But (4) is where the visible result is, and it is reachable earlier than it looks:** a
viewer that places actors and reads their transforms **already shows a level**, without a
single mesh or texture. That is the milestone worth aiming at first.

## 6 · What this document is missing

**Stated rather than left to be discovered:**

- **No worked example.** Nothing here takes one map, one actor, and shows the bytes.
- **No measured cost.** How long each of (1)–(4) would take is not estimated, because the
  investigation that would justify an estimate has not been done.
- **No rendering advice.** Which engine, which coordinate conversion, which units — all
  open. **Godot, Unity and a custom engine differ here and nothing above is engine-specific
  except by accident.**
- **No coverage of the 177 maps never exercised.** The behaviour of maps has been measured
  on **41 of 218**; the *container* on all of them. **The two numbers are different
  questions and must not be combined.**

---

> **The rule this repository runs on, and it applies here too:** every number above was
> measured against a real file. Where something is unknown it is written as unknown.
> **A plausible number nobody checked gets built on.**
