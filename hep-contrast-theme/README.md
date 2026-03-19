# HEP Contrast — VSCode Theme

A high-contrast **light** theme built for long sessions with C++ and Python in a physics / scientific computing context. Every color decision prioritizes unambiguous role differentiation over decoration.

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
vsce package          # produces hep-contrast-1.0.0.vsix
code --install-extension hep-contrast-1.0.0.vsix
```

Then: **Cmd/Ctrl+K → Cmd/Ctrl+T** → select **HEP Contrast**.

---

## Palette

| Role                        | Color          | Hex       |
|-----------------------------|----------------|-----------|
| Background                  | White          | `#FFFFFF` |
| Base text                   | Near-black     | `#0A0A0A` |
| Keywords / control flow     | Green          | `#1A7F00` |
| Types / classes / structs   | Magenta        | `#BB0077` |
| Functions / methods         | Indigo         | `#4B44CC` |
| Strings                     | Red            | `#CC1100` |
| Numbers / constants         | Olive          | `#5A6600` |
| Preprocessor / macros       | Amber          | `#BB6600` |
| Namespaces                  | Bold blue      | `#0055CC` |
| Variables / parameters      | Deep blue      | `#003388` |
| Operators / punctuation     | Teal           | `#007755` |
| Comments                    | Mid gray       | `#777777` |

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

All colors live in `themes/hep-contrast.json`. The file is structured with clear section comments so you can tune individual roles without hunting through an undocumented blob.

Key sections:
- `colors` — editor chrome, sidebar, terminal, status bar, etc.
- `tokenColors` — TextMate grammar scopes (language-agnostic fallback)
- `semanticTokenColors` — LSP semantic tokens (clangd / pylsp)
