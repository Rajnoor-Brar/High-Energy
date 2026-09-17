# Paint Review

Updated: 2026-05-16.

Audit of `utils/Paint/` (8 files, ~1300 LOC), the `_Paint.cc` driver, the
`configs/defaults/Paint.toml` default, and `tests/test_paint.cc`. Paint is
offline-only — invoked from `_Paint.exe` and the paint test, not from the
reconstruction pipeline.

Severity levels:

- **P0** — silent miscompare or undefined behaviour
- **P1** — surprising default, missed config, or visible UX bug
- **P2** — code-quality / maintainability concern

---

## P0 — Correctness Issues

### P0.1 `style.hasMaximum` is value-driven, not key-driven

In `Paint/Style.hh::mergeStyle`:

```cpp
if (detail::hasKey(table, "minimum")) {
    detail::readValue(table, "minimum", style.minimum);
    style.hasMinimum = true;
}
if (detail::hasKey(table, "maximum")) {
    detail::readValue(table, "maximum", style.maximum);
    style.hasMaximum = std::abs(style.maximum) > 0.0;
}
```

`hasMinimum` is set whenever the key exists; `hasMaximum` is set only when the
parsed value is non-zero. A user who legitimately wants `maximum = 0.0` (a
valid ceiling for histograms with negative weights) gets `hasMaximum = false`
and ROOT auto-scales instead. Asymmetric with `minimum`, and the magic
zero-check is undocumented.

**Fix:** set `hasMaximum = true` whenever the key is present, matching
`hasMinimum`. Provide an explicit `auto_maximum = true` opt-out if needed.

### P0.2 `source_search` silently overrides explicit `mode = "single"`

In `Paint/Resolve.hh::resolveSources`:

```cpp
if (paths.size() > 1 && result.mode != Mode::Overlay) {
    result.mode = Mode::Grid;
}
```

If a user sets `mode = "single"` with `source_search`, and the search returns
>1 objects, the mode is silently promoted to grid. Either:

- the user's explicit `mode = "single"` should win (and `finaliseLayout` will
  reject because >1 sources), or
- the promotion should be allowed only when `mode` was not set (default).

The current code conflates "not specified" with "specified as single".

**Fix:** track whether `mode` was set explicitly, and only auto-promote when
unset.

### P0.3 Color offsets overflow silently for large values

In `Paint/Style.hh::parseColor`:

```cpp
return static_cast<Color_t>(it->second + offset);
```

`Color_t` is `Short_t` (16-bit). `kViolet + 1000` wraps to a negative value
without warning. Real configs use small offsets (≤ 10), but a typo could put
the colour at an arbitrary palette index.

**Fix:** clamp or validate the result; throw on overflow rather than wrap.

### P0.4 Overlay stats boxes overwrite each other

In `Paint/Render.hh::drawOverlay`:

```cpp
for (...) {
    ...
    applyStatsBox(source, &canvas);
}
```

`applyStatsBox` calls `hist->FindObject("stats")` on each histogram. In
overlay mode, all histograms share one pad and ROOT only displays one stats
box; each iteration repositions and restyles the *same* box, so only the last
source's stats are visible. Multiple stats boxes in an overlay need explicit
TPaveStats creation per source with offset coordinates.

**Fix:** in overlay mode, either disable stats entirely or stack stats boxes
with computed offsets.

### P0.5 `renderPlan` permanently sets ROOT to batch mode

```cpp
inline void renderPlan(RenderPlan& plan) {
    gROOT->SetBatch(kTRUE);
    ...
}
```

This is a global side effect that persists for the rest of the process. If
Paint is ever invoked from a longer-lived process that subsequently wants
interactive ROOT, plotting silently breaks.

**Fix:** save the previous batch state and restore on scope exit (RAII).

### P0.6 `TImage` leaks on exception in `savePng`

```cpp
TImage* image = TImage::Create();
...
image->FromPad(...);
image->WriteImage(...);
delete image;
```

`FromPad` or `WriteImage` can throw or exit on ROOT errors. The `delete` is
skipped. Leaks one TImage per failed save.

**Fix:** `std::unique_ptr<TImage>` with a custom deleter, or guard with
try/catch.

---

## P1 — UX / Default Issues

### P1.1 Silent fallback to `kBlack` on unknown colours

`Paint::parseColor` returns `kBlack` for:

- empty strings;
- malformed offsets (catch-all `catch (...)`);
- unknown named colours.

A typo (`kRedd`, `kRed_5`) becomes a black line with no error. For an offline
plotting tool, surfacing a clear error message at config load is more useful
than silently producing a wrong plot.

**Fix:** throw on unrecognised colour token; let the driver report and exit.

### P1.2 `detail::readValue` silently ignores type mismatches

```cpp
template <typename T>
inline void readValue(const toml::table& table, const std::string& key, T& out) {
    const toml::node_view<const toml::node> node = table[key];
    if (!node) return;
    if (auto value = node.value<T>()) out = *value;
}
```

If a user writes `line_width = "thick"` (string instead of int), the cast
fails silently and the default is kept. No diagnostic, no log, no error.

**Fix:** throw on type mismatch with the key name and expected type.

### P1.3 `source_search` cannot style sources differently

`source_search` returns N matched objects but applies the *same* style to all
of them. In overlay mode this means every histogram is the same colour.
Useless for the common case "overlay the same hist across N directories".

**Fix:** allow `[[paint.<name>.style_by_path]]` overrides keyed by full path,
or accept a per-result colour palette (vector of colours cycled across
matched sources).

### P1.4 `source_search` is exact-name-only

`searchDirectory` matches `name == needle`. No prefix, suffix, glob, or regex
support. `"Hist*"` matches nothing; the name "search" is misleading.

**Fix:** support `*` glob (or a `source_search_regex` alternative key). Make
the matching style explicit in the doc.

### P1.5 No support for TProfile / TF1 / THStack / TMultiGraph

`ObjectKind` is `{Hist1D, Hist2D, Graph}`. `inferKind` throws for anything
else. TProfile inherits from TH1 — would currently be misclassified as
`Hist1D` and drawn as a histogram (likely "fine" visually but stats and
options are wrong).

**Fix:** add `Profile` kind explicitly; throw cleanly for unsupported types
(TF1, THStack, TMultiGraph) with a message pointing to the unsupported list.

### P1.6 `assertExpectedKind` accepts inconsistent type tokens

```cpp
if ((expected == "TH1" || expected == "H1") && actual == ObjectKind::Hist1D) return;
if ((expected == "TH2" || expected == "H2") && actual == ObjectKind::Hist2D) return;
if ((expected == "TGraph" || expected == "Graph") && actual == ObjectKind::Graph) return;
```

Two forms accepted per kind, both undocumented. The TOML key is
`source_type`; users have no way to know which form is canonical. Pick one
and reject the other.

**Fix:** accept only the `T*` ROOT class names (`TH1`, `TH2`, `TGraph`,
`TProfile`).

### P1.7 No way to opt out of inheriting `configs/defaults/Paint.toml`

`Book.hh::readDefaultStylePath` falls back to `"configs/defaults/Paint.toml"`
if no `default_style` key is set. There is no syntax to say "don't inherit
any default". For unit tests that want a fully self-contained config, this
forces a real defaults file to exist.

**Fix:** support `default_style = ""` (or `false`) to skip the default
inheritance.

### P1.8 `output_name` cannot be set from a visual preset

`applyVisualPreset` calls `mergeDirectRenderSettings(..., inheritOutputName=false)`
but the per-result `mergeResultVisual` passes `inheritOutputName=true`. This
means a preset can supply `mode`, `formats`, `mutate_input`, `title`, but not
`output_name`. Asymmetric and undocumented.

**Fix:** either explain the asymmetry in the TOML doc, or treat
`output_name` the same as other settings (overridden per result by default).

### P1.9 `applyStatsBox` overwrites `fill_style` to solid (1001) regardless of config

```cpp
stats->SetFillColor(0);
stats->SetFillStyle(1001);
```

The `stats.fill_style` field doesn't exist in `StatsSpec` — but more
importantly, the stats box is force-set to solid white. A user who wants a
transparent stats overlay has no escape.

**Fix:** add `stats.fill_color` and `stats.fill_style` fields and respect
them; default to current values.

### P1.10 `legend->AddEntry(..., "lpf")` hardcoded

The legend marker style ("line", "point", "fill") is fixed at `"lpf"`
regardless of how the source is actually drawn. A pure-line graph gets a
filled box in the legend.

**Fix:** derive the legend type from the source's draw option / kind, or
let the user override per source via `legend_type`.

### P1.11 Default formats list silently strips unrecognised entries

`Save.hh::saveCanvas` throws on unsupported format — good. But the
recognised set is `{png, pdf, svg, root}`. Common alternatives:
`jpg`/`jpeg`, `eps`, `C`, `tex` (all natively supported by TCanvas::Print).

**Fix:** route all non-PNG formats through `canvas.Print()` and remove the
hardcoded whitelist; let ROOT report unknown formats.

### P1.12 `mutate_input` is a footgun

`mutate_input = true` makes Paint write style fields onto the live TObject
in the open ROOT file. The intent is to skip a clone for memory savings, but
since the file is opened READ-only it shouldn't actually mutate on disk —
yet the in-memory object is now styled, and if the same path is rendered
twice in the same plan, the second render inherits styles from the first.

**Fix:** either remove the flag (the clone cost is negligible for offline
plotting), or document it loudly and add a guard that prevents reusing the
same path twice in one plan.

---

## P2 — Code Quality / Maintainability

### P2.1 Cross-file use of `detail::` namespace

`detail::mergeAxis`, `detail::mergeCanvas`, etc. defined in `Style.hh` are
called from `Resolve.hh::mergeSubsectionUse`. `detail::` should mean
"private to the file"; once it's used across files it's just a name prefix.
Either lift the merge helpers into the public Paint namespace, or stop
using `detail::` to imply privacy.

### P2.2 Preset resolution duplicated in `applyVisualPreset` and `applySourcePreset`

The two functions do the same recursive `use` walk with cycle detection.
Only difference: one passes a `RenderResult`, the other passes a `Style`.
They can be unified with a small template or callback.

### P2.3 `inferKind`'s `dynamic_cast` chain is not extensible

Adding a new ObjectKind requires editing `inferKind`, `assertExpectedKind`,
`apply*` overloads in Apply.hh, `applyToSource`/`drawSource`/`setSourceTitle`
in Render.hh, `defaultDrawOption` in Render.hh, and the kind name in
Types.hh's `objectKindName`. ~6 sites for one new type.

Consider a registry-based approach: one struct per kind containing the
dynamic_cast, apply, and draw callbacks.

### P2.4 `Paint.hh` header doc comment violates REVIEW 4.1

REVIEW.md item 4.1 says module-level doc blocks should not live in `.hh`
files. `Paint.hh` opens with an 18-line ASCII-bordered comment listing every
submodule. Move to a Paint section in `Architecture.md` and trim the header
to a one-liner.

### P2.5 `modeName` and `objectKindName` swallow invalid enums

```cpp
inline std::string modeName(Mode mode) {
    switch (mode) { ... }
    return "single";   // fallback if mode is corrupted
}
```

A corrupted enum value silently maps to `"single"`. Better: `throw
std::runtime_error` or `__builtin_unreachable()` so the bug surfaces.

### P2.6 `searchDirectory` does no recursion-depth cap

A pathological ROOT file with circular TDirectory references could spin
forever. Unlikely with normal Writer output, but a depth cap (or visited set)
is cheap insurance.

### P2.7 `detachFromDirectory` only knows TH1

A TProfile clone (or any TDirectory-resident object that isn't TH1) won't be
detached. The current code only clones TH1/TH2/TGraph and won't reach the
problem, but the helper's name implies it works for any TObject.

**Fix:** rename to `detachHistFromDirectory` to make the intent explicit.

### P2.8 `printPlan` output omits resolved styles

The dry-run printer lists path, kind, and ROOT class but not which line
colour / draw option / preset path produced the final style. For debugging a
preset chain, the dry-run is currently useless.

**Fix:** add resolved colour codes and preset chain to the dry-run output
(behind a `--verbose` flag if it gets noisy).

### P2.9 No const-correctness on `Illustrator::render`

`render()` mutates `plan_` (calls into `renderPlan` which takes
`RenderPlan&`). That's fine, but `dryRun(...) const` claims to be const yet
`printPlan(plan_, os)` reads the same mutable state. Either drop `const` on
`dryRun` or take `RenderPlan` by const ref in `printPlan`.

### P2.10 Magic strings throughout

`"configs/defaults/Paint.toml"`, `"results"`, `"png"`, `"HIST"`, `"COLZ"`,
`"APL"`, `"lpf"`, `"stats"` (the ROOT internal name), `"title"`,
`"__paint"` suffix. Some are conventional ROOT names (`"stats"`, `"title"`)
and have to stay; others (`"results"`, `"png"`) belong in named constants at
the top of the file or in `Paint/Types.hh`.

---

## Test Gaps

`tests/test_paint.cc` covers the happy path well but is missing:

| Gap | Reason it matters |
|---|---|
| Preset cycle detection | A `use = "A"`, `use = "B"`, `use = "A"` cycle should throw — currently untested |
| `mutate_input = true` | Footgun path not exercised |
| PDF / SVG / ROOT save | Only PNG is verified |
| `image_scale > 1` | Scaling logic untested |
| `default_style = ""` opt-out | After P1.7 fix, needs a test |
| Unknown colour throw | After P1.1 fix |
| Type-mismatch throw | After P1.2 fix |
| Overlay stats boxes | After P0.4 fix, verify all sources' stats visible |
| TProfile rendering | After P1.5 fix |
| Source-style cycle detection | `applySourcePreset` cycle path untested |
| `output_name` override | Currently no assertion on output filename customisation |

---

## Recommendations Summary

Highest-leverage cleanups (do these before anything else):

1. Fix P0.1, P0.2, P0.4, P0.5, P0.6 — these are correctness bugs that
   produce wrong plots or leak resources.
2. Resolve silent-failure paths (P1.1, P1.2): every config parse error
   should surface, not get swallowed.
3. Address P1.3 / P1.4: `source_search` is currently only useful for the
   one-result-per-search case; the more interesting "overlay across
   directories" case is broken.
4. Unify preset resolution (P2.2) and the kind dispatch (P2.3) before
   adding TProfile/THStack support — otherwise the new types compound the
   existing duplication.
5. Remove the header doc block (P2.4) and align with REVIEW 4.1.

Out of scope for this audit but worth flagging:

- No ratio / pull / residual plot support (CMS-style mass + ratio).
- No multi-file input (`root_file` is single-valued).
- No log file or verbosity flag — failures must surface as exceptions.
