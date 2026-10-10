# cc-studytools

**Tools and format specifications for reading Unreal Engine 3 packages — with a focus
on the ones CrimeCraft shipped, which are UE3 build `576 / licensee 5` (Vogster).**

Everything here **only reads**. Nothing in this repository patches, rewrites or
repackages a game executable.

---

## What this is

Two things, and they are separate on purpose:

| | |
| --- | --- |
| **`docs/`** | **Format specifications** — the byte-level layout of a UE3 package, how to walk its tables, and what is still unknown. Written so that someone with a hex editor and no tooling can follow along |
| **`tools/`** | **Instrumentation** — one small tool per question, each with its own manual |

**It is not** a game mod, a general-purpose unpacker, or a fork of anything. The tools
exist because a specific question needed answering, and each one says in its own header
**what question it answers and what it cannot see**.

---

## Why the documents are in English

They are meant to be read by anyone working with UE3 packages, not only by whoever
wrote them. **The prose is English; the identifiers, the field names and the byte
offsets are the engine's own** and are not translated anywhere.

---

## The one rule that matters

> **Every number in these documents was measured against a real file, and the document
> says which file.**

Where something is *not* known, it is written down as unknown **rather than guessed
at** — see `docs/UE3-PACKAGE-FORMAT.md` § *Open questions*. A plausible number that
nobody checked is worse than an admitted gap: it gets built on.

The specifications also carry **arithmetic self-checks** — identities that must hold
across *every* file in the corpus, so that a reader can falsify the whole document in
one command instead of trusting it.

---

## Start here

| If you want to… | read |
| --- | --- |
| **write a loader for these packages** | **read [`docs/UE3-PACKAGE-FORMAT.md`](docs/UE3-PACKAGE-FORMAT.md) § *If you are writing a loader* FIRST** — it says what is finished and what is not, so the gap is a known quantity |
| understand the container layout | the same file, § 1–4 |
| know which offsets are still unverified | the same file, § *Open questions* |
| know what a `.ccmap` is | the same file, § *Map packages* |
| **build an editor for this content** | **[`docs/CC-EDITOR-BASE.md`](docs/CC-EDITOR-BASE.md)** — the starting condition, what exists, and what is missing. **Marked incomplete on purpose** |
| work on the stub generator | **[`docs/GENERATE-STUBS-NOTES.md`](docs/GENERATE-STUBS-NOTES.md)** — the reasoning behind `generate-stubs.py`, whose code now carries no comments |
| use a tool | **[`docs/TOOLS.md`](docs/TOOLS.md)** |

> **The short version, so it is not a surprise later: the container is specified well
> enough to write a reader for it today. A *map* loader also needs the property boundary
> rule — which is **open** and holds for about three quarters of a map's exports — and the
> mesh and texture formats, which are **not written down anywhere yet.**

---

## The corpus

The numbers in the specs were measured across **550 packages**:

| extension | count | what |
| --- | ---: | --- |
| `.u` | 12 | code packages (`Engine`, `Core`, the game's own) |
| `.ccmap` | 218 | maps |
| `.ccpk` | 320 | content packages |

**They are not distributed here.** They are someone else's game data, and they can be
obtained from the game itself.

---

## Credits

The package reading is independent — it does not link against the engine. It was
written after the engine's own loader was measured to desynchronise on some cooked
packages, and the decision is documented in `docs/UE3-PACKAGE-FORMAT.md`.

`kismet-analyzer` by Truman Kilen ([trumank](https://github.com/trumank)) is the UE4
original this work descends from; the port to UE3 is a separate repository.
