# `generate-stubs.py` — the reasoning behind the code

> [!warning] **INCOMPLETE — this is a working base, not a finished document.**
> It records what has been **measured**; where something has not been investigated it
> says so rather than guessing. **A reader should treat every "unknown" below as work
> to do, not as a gap in the writing.** See the note at the end.

**This document is the English form of the comments that `generate-stubs.py` used to
carry** — 3,284 lines of them, written as the work happened. They are preserved verbatim
in `generate-stubs-commented.py` (Spanish), and distilled here.

**Read this before changing a rule in the tool.** Most of that file's constants are not
preferences. **They are measurements**, and the measurement is here.

---

## 1 · Why stubs at all

The maps import classes from the game's `CrimeCraft.u` that our engine does not have.
**Loading the game's own package does not work:** it was cooked at **engine build 4701**
and our SDK is **10897** — it desynchronises.

So the route is **stubs**: declare the classes so the engine can *deserialise* what the
map stored, without reproducing behaviour.

**The vehicle already existed.** `EditPackages` in the ini, plus a
`Development/Src/<Package>/Classes` folder, which the engine compiles into
`DemoGame/Script/<Package>.u`.

> **The folder is what decides, not the ini line.** That is why `EditPackages=DemoGame`
> is switched off — its source folder does not exist.

## 2 · What the transformation actually does

Three things, and each one exists because of something that went wrong without it:

| step | why it is needed |
| --- | --- |
| **strip `native`** from the class declaration | a stub has no C++ half; leaving `native` makes the compiler expect script, which is exactly what is being provided |
| **mark the extraction artefacts** that are not valid UnrealScript | e.g. `Components=/* Array type was not detected. */`, flag comments like `/*0x20000000-0x00000000*/`, and the `// Reference:` / `// TemplateOwner*` / `// Archetype:` lines |
| **withdraw** stubs for classes the list no longer asks for | **the compiler reads the folder, not the list** — an obsolete stub compiles anyway and drags in its own unresolved types |

**And the package name is derived from the folder, not written.** It used to be written in
one place while the reconstruction lived in another, with nothing tying the two together.

## 3 · What it does not do, and will not

**It does not check that every referenced type resolves.** The tool's own docstring claimed
it did. **It did not** — `tipos_del_sdk()` was computed and used only to print its size.
This was found while investigating why the compiler reported unresolved types the class
list already contained.

**It is not implemented on purpose:** the script compiler does that check properly, reaches
the package in ten seconds, and names the exact type and line. An approximate
reimplementation would only add false positives needing their own debugging.

**It decides nothing about what it does not understand — it reports it.** A generator that
silently repairs artefacts it cannot parse produces stubs that compile and do not do what
they appear to.

## 4 · The rules that are measurements

These are in `generate-stubs-commented.py` in full, with the counts that produced them.
The short form:

| rule | what it encodes |
| --- | --- |
| **nothing the SDK already declares is stubbed** | a stub with the name of an existing class does not replace it — **it shadows it**, and the engine keeps the wrong one. Two got through this way (`Interface`, `SeqCond_IsAlive`) |
| **the closure over superclasses runs before the filter** | a superclass the SDK already has must not be pulled in by closing over a stub's parents |
| **`{TMap<…>}` annotations are stripped by the game's export** | only visible by comparing against a reference build |
| **arrays dimensioned by an enum that cannot dimension them** | the compiler accepts the declaration and the sizes are wrong |
| **the two catalogues are two because they are two sources** | engine types and game types come from different packages, and are read in a fixed order |
| **the `StructProperty` name lives in the property tag, not the table** | so a struct whose member type is unknown **blocks** the declaration of the whole type — those are kept deliberately, as the list of what is missing |

## 5 · What is *not* established here

| unknown | what is known |
| --- | --- |
| **why some exported classes need no stub at all** | the counts are recorded (1,322 with their own definition, 4,596 the engine already has, 256 imported by the maps, 933 after closing superclasses) — **the reason each one falls in its bucket is not written down** |
| **whether the game's cooker changed any default value** | `defaultproperties` blocks are ported from a reference build, so **where the game's cooker changed one, the wrong value is carried, silently** |
| **the exact set of extraction artefacts** | the ones seen so far are listed; **the list is empirical, not derived from the exporter's grammar** |

---

## What this document is missing, stated plainly

**This is a first pass, written from the code's own recorded findings.** What it does not
yet have, and what a developer picking this up would want:

1. **A worked example** — one class, from its export in the package to the `.uc` on disk,
   with the artefact markings shown at each step.
2. **The counts per rule**, not just totals. The totals are here; the breakdown that would
   let someone check a change's effect is not.
3. **The failure modes in the compiler's own words** — what an over-eager strip looks like
   when it breaks, so the next person recognises it in ten minutes instead of an hour.

**They are missing because the investigation behind them has not been done**, not because
they were judged unimportant.
