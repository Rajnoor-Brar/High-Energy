# HEP Contrast — VSCode Theme

High-contrast **light and dark** themes built for long sessions with C++ and Python in a physics / scientific computing context. Every color decision prioritizes unambiguous role differentiation over decoration.

---

## Install

### Option A — Load from folder (dev / local)
```
Extensions sidebar → ··· → Install from VSIX...
```
Or, for instant live-reload during editing:
```
F5  (with this folder open — launches Extension Development Host)
```

### Option B — VSIX package
```bash
npm install -g @vscode/vsce
cd hep-contrast-theme
node build.js         # regenerate themes/hep-contrast-light.json + themes/hep-contrast-dark.json from palette.toml
vsce package          # produces hep-contrast-2.0.0.vsix
code --install-extension hep-contrast-2.0.0.vsix
```

Then: **Cmd/Ctrl+K → Cmd/Ctrl+T** → select **HEP Contrast Light** or **HEP Contrast Dark**.

---

## Palette

All colors live in **`palette.toml`** as `[light, dark]` pairs. Edit there, run `node build.js`, done — both themes regenerate from the single source of truth.

| Role                        | Light          | Dark       |
|-----------------------------|----------------|------------|
| Background                  | `#FFFFFF`      | `#1E1E1E`  |
| Base text                   | `#0A0A0A`      | `#D4D4D4`  |
| Keywords / control flow     | `#D71868`      | `#FF79C6`  |
| Types / classes / structs   | `#D71868`      | `#FF79C6`  |
| Functions / methods         | `#0055CC`      | `#6BB5FF`  |
| Strings                     | `#E60026`      | `#F07178`  |
| Numbers / constants         | `#CC332A`      | `#F78C6C`  |
| Preprocessor / macros       | `#D75C1E`      | `#FFAB40`  |
| Namespaces                  | `#883DA4`      | `#C792EA`  |
| Variables                   | `#224C98`      | `#82AAFF`  |
| Parameters                  | `#2072AF`      | `#89DDFF`  |
| Operators / punctuation     | `#E28512`      | `#FFCB6B`  |
| Comments                    | `#777777`      | `#676E95`  |

---

## Features

- **Semantic highlighting** enabled — requires clangd (C++) or pylsp/pyright (Python) for full effect. Token-level colors are the fallback.
- **Full 16-color ANSI terminal palette** — calibrated for white background; all 8 bright variants are distinctly darker than typical to maintain contrast.
- **Bracket pair colorization** — blue / red / teal / amber cycling.
- **Git gutter decorations** — green add, blue modify, red delete.
- **CMake, Shell, TOML, YAML, JSON, Markdown** all covered.
- **Debug / diff / peek view** colors consistent with the palette.

---

## Recommended Settings

Add to your `settings.json` for the best experience:

```jsonc
{
  "editor.semanticHighlighting.enabled": true,
  "editor.bracketPairColorization.enabled": true,
  "editor.guides.bracketPairs": "active",
  "editor.fontFamily": "'JetBrains Mono', 'Fira Code', monospace",
  "editor.fontLigatures": true,
  "editor.fontSize": 13,
  "editor.lineHeight": 1.6,
  "editor.renderWhitespace": "boundary"
}
```

---

## Customization

All colors are defined in **`palette.toml`** as `key = [light_value, dark_value]` pairs, grouped into named sections (`[syntax]`, `[bg_ramp]`, `[ansi]`, etc.).

To change something:
1. Edit the hex value(s) in `palette.toml`
2. Run `node build.js`
3. VS Code picks up the change immediately if you're in Extension Development Host (F5)

The theme-building logic lives in `build.js`, which has three sections:
- **`buildTheme` → `colors`** — editor chrome, sidebar, terminal (ANSI 16), status bar, diff, peek
- **`buildTheme` → `tokenColors`** — TextMate grammar scopes (language-agnostic fallback)
- **`buildTheme` → `semanticTokenColors`** — LSP semantic tokens (clangd / pylsp)
