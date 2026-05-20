#!/usr/bin/env node
/**
 * HEP Contrast — theme build script
 *
 * Reads palette.toml, where every entry is [light_value, dark_value].
 * Emits:
 *   themes/hep-contrast-light.json
 *   themes/hep-contrast-dark.json
 *
 * Usage:  node build.js
 */

"use strict";
const fs   = require("fs");
const path = require("path");

// ═══════════════════════════════════════════════════════════════════════════════
// TOML PARSER — handles exactly the subset used by palette.toml:
//   [section]
//   key = ["value1", "value2"]   (pairs only)
//   # comments (ignored)
// ═══════════════════════════════════════════════════════════════════════════════
function parsePalette(src) {
  const result = {};
  let section = "_";
  for (const raw of src.split("\n")) {
    const line = raw.replace(/#.*$/, "").trim(); // strip inline comments
    if (!line) continue;
    const sec = line.match(/^\[([^\]]+)\]$/);
    if (sec) { section = sec[1]; result[section] = {}; continue; }
    const pair = line.match(/^(\w+)\s*=\s*\[\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\]/);
    if (pair) result[section][pair[1]] = [pair[2], pair[3]];
  }
  return result;
}

// Flatten all sections into a single {key: value} object, picking index idx.
function flatten(raw, idx) {
  const C = {};
  for (const section of Object.values(raw)) {
    for (const [key, pair] of Object.entries(section)) {
      C[key] = pair[idx];
    }
  }
  return C;
}

// ═══════════════════════════════════════════════════════════════════════════════
// THEME DEFINITION — parameterised by C (a flat palette object)
// ═══════════════════════════════════════════════════════════════════════════════
function buildTheme(C, type) {
  return {
    name: type === "light" ? "HEP Contrast" : "HEP Contrast Dark",
    type,

    colors: {
      // ── Editor core ──────────────────────────────────────────────────────
      "editor.background":                          C.bgEditor,
      "editor.foreground":                          C.fg,
      "editorLineNumber.foreground":                C.fgFaint,
      "editorLineNumber.activeForeground":          C.fg2,
      "editor.lineHighlightBackground":             C.bgLine,
      "editor.lineHighlightBorder":                 C.borderSubtle,
      "editor.selectionBackground":                 C.selection,
      "editor.selectionHighlightBackground":        C.selectionHi,
      "editor.wordHighlightBackground":             C.wordHi,
      "editor.wordHighlightStrongBackground":       C.wordHiStrong,
      "editor.findMatchBackground":                 C.findMatch,
      "editor.findMatchHighlightBackground":        C.findMatchHi,
      "editor.rangeHighlightBackground":            C.rangeHi,
      "editorCursor.foreground":                    C.fg,
      "editorWhitespace.foreground":                C.fgWhisper,
      "editorIndentGuide.background":               C.borderSubtle,
      "editorIndentGuide.activeBackground":         C.fgFainter,
      "editorRuler.foreground":                     C.borderFaint,

      // ── Bracket pair ─────────────────────────────────────────────────────
      "editorBracketHighlight.foreground1":         C.bracket1,
      "editorBracketHighlight.foreground2":         C.bracket2,
      "editorBracketHighlight.foreground3":         C.bracket3,
      "editorBracketHighlight.foreground4":         C.bracket4,
      "editorBracketHighlight.unexpectedBracket.foreground": C.accentRedDark,
      "editorBracketPairGuide.activeBackground1":   C.bracketGuide1,
      "editorBracketPairGuide.activeBackground2":   C.bracketGuide2,
      "editorBracketPairGuide.activeBackground3":   C.bracketGuide3,

      // ── Gutter / diff ────────────────────────────────────────────────────
      "editorGutter.addedBackground":               C.accentBlue,
      "editorGutter.modifiedBackground":            C.accentAmber,
      "editorGutter.deletedBackground":             C.accentOrange,
      "diffEditor.insertedTextBackground":          C.diffAdded55,
      "diffEditor.removedTextBackground":           C.diffRemoved55,
      "diffEditor.insertedLineBackground":          C.diffAddedLine,
      "diffEditor.removedLineBackground":           C.diffRemovedLine,

      // ── Errors / warnings / info ─────────────────────────────────────────
      "editorError.foreground":                     C.accentRedDark,
      "editorWarning.foreground":                   C.accentWarn,
      "editorInfo.foreground":                      C.accentBlue,
      "editorHint.foreground":                      C.numbers,
      "editorError.background":                     type === "light" ? "#FFF0F0" : "#3B1B1B",
      "editorWarning.background":                   type === "light" ? "#FFFBEE" : "#2E2800",

      // ── Sidebar ──────────────────────────────────────────────────────────
      "sideBar.background":                         C.bgSidebar,
      "sideBar.foreground":                         C.fg3,
      "sideBar.border":                             C.border,
      "sideBarTitle.foreground":                    C.fg4,
      "sideBarSectionHeader.background":            C.bgSection,
      "sideBarSectionHeader.foreground":            C.fg4,
      "sideBarSectionHeader.border":                C.borderLight,
      "tree.indentGuidesStroke":                    C.fgAlmostGone,

      // ── Git decorations ──────────────────────────────────────────────────
      "gitDecoration.addedResourceForeground":      C.gitAdded,
      "gitDecoration.modifiedResourceForeground":   C.gitModified,
      "gitDecoration.deletedResourceForeground":    C.gitDeleted,
      "gitDecoration.untrackedResourceForeground":  C.gitUntracked,
      "gitDecoration.ignoredResourceForeground":    C.gitIgnored,
      "gitDecoration.conflictingResourceForeground":C.gitConflict,
      "gitDecoration.stageModifiedResourceForeground": C.gitModified,

      // ── Activity bar ─────────────────────────────────────────────────────
      "activityBar.background":                     C.bgActivity,
      "activityBar.foreground":                     C.fg2,
      "activityBar.inactiveForeground":             C.fgSubtle,
      "activityBar.border":                         C.border,
      "activityBarBadge.background":                C.accentBlue,
      "activityBarBadge.foreground":                C.bg,

      // ── Status bar ───────────────────────────────────────────────────────
      "statusBar.background":                       C.statusBg,
      "statusBar.foreground":                       C.statusFg,
      "statusBar.border":                           C.fgAlmostGone,
      "statusBar.noFolderBackground":               C.fgMid,
      "statusBar.debuggingBackground":              C.statusDebugBg,
      "statusBarItem.hoverBackground":              C.listHover,
      "statusBarItem.remoteBackground":             C.statusRemoteBg,
      "statusBarItem.remoteForeground":             C.statusRemoteFg,
      "statusBarItem.errorBackground":              C.accentRedDark,
      "statusBarItem.warningBackground":            C.accentWarn,

      // ── Title bar ────────────────────────────────────────────────────────
      "titleBar.activeBackground":                  C.bgTitle,
      "titleBar.activeForeground":                  C.fg2,
      "titleBar.inactiveBackground":                C.bgTitleInact,
      "titleBar.inactiveForeground":                C.fgSubtle,
      "titleBar.border":                            C.border,

      // ── Tabs ─────────────────────────────────────────────────────────────
      "tab.activeBackground":                       C.bg,
      "tab.activeForeground":                       C.fg,
      "tab.activeBorderTop":                        C.accentAmber,
      "tab.inactiveBackground":                     C.bgSection,
      "tab.inactiveForeground":                     C.fgLight,
      "tab.border":                                 C.border,
      "tab.hoverBackground":                        C.bgSidebar,
      "tab.unfocusedActiveBackground":              C.bgTitleInact,
      "tab.unfocusedActiveForeground":              C.fgMid,
      "editorGroupHeader.tabsBackground":           C.bgSection,

      // ── Panel ────────────────────────────────────────────────────────────
      "panel.background":                           C.bgPanel,
      "panel.border":                               C.border,
      "panelTitle.activeForeground":                C.accentBlue,
      "panelTitle.activeBorder":                    C.accentBlue,
      "panelTitle.inactiveForeground":              C.fgSubtle,

      // ── Integrated terminal ──────────────────────────────────────────────
      "terminal.background":                        C.bg,
      "terminal.foreground":                        C.fg,
      "terminal.selectionBackground":               C.selection,
      "terminalCursor.foreground":                  C.fg,
      "terminal.ansiBlack":                         C.ansiBlack,
      "terminal.ansiRed":                           C.ansiRed,
      "terminal.ansiGreen":                         C.ansiGreen,
      "terminal.ansiYellow":                        C.ansiYellow,
      "terminal.ansiBlue":                          C.ansiBlue,
      "terminal.ansiMagenta":                       C.ansiMagenta,
      "terminal.ansiCyan":                          C.ansiCyan,
      "terminal.ansiWhite":                         C.ansiWhite,
      "terminal.ansiBrightBlack":                   C.ansiBrightBlack,
      "terminal.ansiBrightRed":                     C.ansiBrightRed,
      "terminal.ansiBrightGreen":                   C.ansiBrightGreen,
      "terminal.ansiBrightYellow":                  C.ansiBrightYellow,
      "terminal.ansiBrightBlue":                    C.ansiBrightBlue,
      "terminal.ansiBrightMagenta":                 C.ansiBrightMagenta,
      "terminal.ansiBrightCyan":                    C.ansiBrightCyan,
      "terminal.ansiBrightWhite":                   C.ansiBrightWhite,

      // ── Input / widgets ──────────────────────────────────────────────────
      "input.background":                           C.bg,
      "input.foreground":                           C.fg,
      "input.border":                               C.fgFainter,
      "input.placeholderForeground":                C.fgFaint,
      "inputOption.activeBorder":                   C.accentBlue,
      "inputOption.activeBackground":               C.listActive,
      "focusBorder":                                C.accentBlue,
      "widget.shadow":                              C.shadowColor,

      // ── Lists ────────────────────────────────────────────────────────────
      "dropdown.background":                        C.bg,
      "dropdown.border":                            C.fgAlmostGone,
      "list.activeSelectionBackground":             C.listActive,
      "list.activeSelectionForeground":             C.fg,
      "list.inactiveSelectionBackground":           C.borderSubtle,
      "list.hoverBackground":                       C.listHover,
      "list.focusBackground":                       C.listFocus,
      "list.highlightForeground":                   C.accentBlue,

      // ── Scrollbar ────────────────────────────────────────────────────────
      "scrollbarSlider.background":                 C.scrollbarBg,
      "scrollbarSlider.hoverBackground":            C.scrollbarHover,
      "scrollbarSlider.activeBackground":           C.scrollbarActive,

      // ── Minimap ──────────────────────────────────────────────────────────
      "minimap.findMatchHighlight":                 C.findMatch,
      "minimap.selectionHighlight":                 C.selection,
      "minimap.errorHighlight":                     C.errorBg66,
      "minimap.warningHighlight":                   C.warnBg66,
      "minimapGutter.addedBackground":              C.accentBlue,
      "minimapGutter.modifiedBackground":           C.gitModified,
      "minimapGutter.deletedBackground":            C.gitDeleted,

      // ── Notifications ────────────────────────────────────────────────────
      "notificationCenter.border":                  C.border,
      "notifications.background":                   C.bg,
      "notifications.border":                       C.border,
      "notificationsErrorIcon.foreground":          C.accentRedDark,
      "notificationsWarningIcon.foreground":        C.accentWarn,
      "notificationsInfoIcon.foreground":           C.accentBlue,

      // ── Peek view ────────────────────────────────────────────────────────
      "peekView.border":                            C.peekBorder,
      "peekViewEditor.background":                  C.peekEditor,
      "peekViewEditor.matchHighlightBackground":    C.findMatch55,
      "peekViewResult.background":                  C.peekResult,
      "peekViewResult.matchHighlightBackground":    C.selection,
      "peekViewResult.selectionBackground":         C.listActive,
      "peekViewTitle.background":                   C.peekTitle,
      "peekViewTitleLabel.foreground":              C.fg,
      "peekViewTitleDescription.foreground":        C.fg4,

      // ── Breadcrumb ───────────────────────────────────────────────────────
      "breadcrumb.foreground":                      C.fgLight,
      "breadcrumb.focusForeground":                 C.accentBlue,
      "breadcrumb.activeSelectionForeground":       C.fg,
      "breadcrumbPicker.background":                C.bg,

      // ── Buttons ──────────────────────────────────────────────────────────
      "button.background":                          C.accentBlue,
      "button.foreground":                          C.bg,
      "button.hoverBackground":                     C.accentBlueDark,
      "button.secondaryBackground":                 C.borderSubtle,
      "button.secondaryForeground":                 C.fg2,

      // ── Debug ────────────────────────────────────────────────────────────
      "debugToolBar.background":                    C.bg,
      "debugIcon.breakpointForeground":             C.accentRedDark,
      "debugIcon.breakpointDisabledForeground":     C.fgFainter,
      "editor.stackFrameHighlightBackground":       C.rangeHi,
      "editor.focusedStackFrameHighlightBackground":C.diffAddedLine,

      // ── Misc ─────────────────────────────────────────────────────────────
      "badge.background":                           C.accentBlue,
      "badge.foreground":                           C.bg,
      "progressBar.background":                     C.accentBlue,
      "charts.red":                                 C.accentRedDark,
      "charts.blue":                                C.accentBlue,
      "charts.green":                               C.gitAdded,
      "charts.yellow":                              C.accentWarn,
      "charts.orange":                              C.chartsOrange,
      "charts.purple":                              C.namespaces,
      "extensionButton.prominentBackground":        C.accentBlue,
      "extensionButton.prominentForeground":        C.bg,
    },

    // ═══════════════════════════════════════════════════════════════════════
    // TOKEN COLORS (TextMate scopes — language-agnostic fallback)
    // ═══════════════════════════════════════════════════════════════════════
    tokenColors: [

      // ── Base ─────────────────────────────────────────────────────────────
      { name: "Base text",
        scope: ["source", "text"],
        settings: { foreground: C.fg } },

      // ── Comments ─────────────────────────────────────────────────────────
      { name: "Comments",
        scope: ["comment", "punctuation.definition.comment"],
        settings: { foreground: C.fgComment, fontStyle: "italic" } },
      { name: "Doc comment tags",
        scope: [
          "comment.block.documentation storage.type.class.jsdoc",
          "comment.block.doxygen keyword",
          "comment.line.double-slash.doxygen keyword",
          "storage.type.class.jsdoc",
        ],
        settings: { foreground: C.docCommentTag, fontStyle: "italic bold" } },
      { name: "Doc comment parameter names",
        scope: "comment.block.doxygen variable",
        settings: { foreground: C.parameters, fontStyle: "italic" } },

      // ── Keywords ─────────────────────────────────────────────────────────
      { name: "Control-flow keywords",
        scope: [
          "keyword.control", "keyword.control.flow",
          "keyword.control.conditional", "keyword.control.loop",
          "keyword.control.return", "keyword.control.exception",
        ],
        settings: { foreground: C.types, fontStyle: "bold" } },
      { name: "Other keywords",
        scope: ["keyword", "keyword.other", "storage.modifier", "storage.type.modifier"],
        settings: { foreground: C.types } },
      { name: "C++ storage types (int, double, void, auto, …)",
        scope: ["storage.type", "storage.type.primitive", "storage.type.built-in", "keyword.type"],
        settings: { foreground: C.types, fontStyle: "bold" } },
      { name: "C++ new / delete / sizeof / this",
        scope: [
          "keyword.operator.new", "keyword.operator.delete",
          "keyword.operator.sizeof", "variable.language.this", "variable.language.self",
        ],
        settings: { foreground: C.types, fontStyle: "bold" } },
      { name: "Python self / cls",
        scope: ["variable.parameter.function.language.special"],
        settings: { foreground: C.types, fontStyle: "bold italic" } },
      { name: "import / from / as",
        scope: [
          "keyword.control.import", "keyword.control.from-import",
          "keyword.other.import", "keyword.other.use",
        ],
        settings: { foreground: C.types, fontStyle: "bold" } },

      // ── Preprocessor ─────────────────────────────────────────────────────
      { name: "Preprocessor directive",
        scope: [
          "keyword.control.directive", "keyword.control.directive.include",
          "keyword.control.directive.define", "keyword.control.directive.pragma",
          "keyword.control.directive.conditional", "meta.preprocessor keyword",
          "meta.preprocessor.include keyword",
        ],
        settings: { foreground: C.preprocessor, fontStyle: "bold" } },
      { name: "Macro names",
        scope: ["entity.name.function.preprocessor", "meta.preprocessor.macro entity.name.function"],
        settings: { foreground: C.preprocessor } },
      { name: "Preprocessor include path",
        scope: ["meta.preprocessor.include string", "string.quoted.other.lt-gt.include"],
        settings: { foreground: C.strings } },

      // ── Types / classes ───────────────────────────────────────────────────
      { name: "Class / struct / enum names",
        scope: [
          "entity.name.type", "entity.name.type.class", "entity.name.type.struct",
          "entity.name.type.enum", "entity.name.type.template",
          "entity.name.class", "support.class",
        ],
        settings: { foreground: C.types, fontStyle: "bold" } },
      { name: "Inherited / used type",
        scope: ["entity.other.inherited-class", "entity.name.type.base-class"],
        settings: { foreground: C.types, fontStyle: "bold italic" } },
      { name: "Python decorators",
        scope: ["meta.decorator", "entity.name.function.decorator", "punctuation.definition.decorator"],
        settings: { foreground: C.types, fontStyle: "bold italic" } },
      { name: "Template type parameters",
        scope: ["storage.type.template", "entity.name.type.template-parameter"],
        settings: { foreground: C.types } },

      // ── Namespaces ────────────────────────────────────────────────────────
      { name: "Namespace names",
        scope: ["entity.name.namespace", "entity.name.type.namespace"],
        settings: { foreground: C.namespaces } },
      { name: "Scope resolution ::",
        scope: ["punctuation.separator.scope-resolution", "punctuation.accessor.double-colon"],
        settings: { foreground: C.namespaces } },

      // ── Functions ─────────────────────────────────────────────────────────
      { name: "Function / method definition",
        scope: ["entity.name.function", "entity.name.function.member", "entity.name.function.definition"],
        settings: { foreground: C.functions, fontStyle: "bold" } },
      { name: "Function call",
        scope: [
          "meta.function-call entity.name.function",
          "meta.function-call.generic entity.name.function",
        ],
        settings: { foreground: C.functions } },
      { name: "Support functions",
        scope: ["support.function", "support.function.builtin", "support.function.std"],
        settings: { foreground: C.functions } },
      { name: "Lambda",
        scope: ["meta.lambda", "storage.type.lambda", "punctuation.definition.lambda"],
        settings: { foreground: C.functions, fontStyle: "italic" } },

      // ── Variables ─────────────────────────────────────────────────────────
      { name: "Function parameters",
        scope: ["variable.parameter", "meta.function.parameter variable"],
        settings: { foreground: C.parameters } },
      { name: "Member variables",
        scope: ["variable.other.member", "variable.other.property", "variable.other.object.property"],
        settings: { foreground: C.fg3 } },
      { name: "Local / other variables",
        scope: ["variable", "variable.other", "variable.other.local", "variable.other.readwrite"],
        settings: { foreground: C.fg } },
      { name: "Constants (ALL_CAPS / constexpr)",
        scope: ["variable.other.constant", "entity.name.variable.constant", "support.constant"],
        settings: { foreground: C.numbers, fontStyle: "bold" } },
      { name: "Python builtins",
        scope: "support.function.builtin.python",
        settings: { foreground: C.types } },

      // ── Strings ───────────────────────────────────────────────────────────
      { name: "Strings",
        scope: ["string", "string.quoted", "string.quoted.double", "string.quoted.single", "string.template"],
        settings: { foreground: C.strings } },
      { name: "Raw / byte strings",
        scope: ["string.quoted.raw", "string.quoted.other", "string.other"],
        settings: { foreground: C.strings, fontStyle: "italic" } },
      { name: "Escape sequences",
        scope: ["constant.character.escape", "constant.other.placeholder"],
        settings: { foreground: C.preprocessor, fontStyle: "bold" } },

      // ── Numbers ───────────────────────────────────────────────────────────
      { name: "Numbers",
        scope: [
          "constant.numeric", "constant.numeric.integer", "constant.numeric.float",
          "constant.numeric.hex", "constant.numeric.octal", "constant.numeric.binary",
        ],
        settings: { foreground: C.numbers, fontStyle: "bold" } },
      { name: "Boolean / null / nullptr / None",
        scope: ["constant.language", "constant.language.boolean", "constant.language.null", "constant.language.nullptr"],
        settings: { foreground: C.types, fontStyle: "bold italic" } },

      // ── Operators ─────────────────────────────────────────────────────────
      { name: "Operators",
        scope: [
          "keyword.operator", "keyword.operator.arithmetic", "keyword.operator.assignment",
          "keyword.operator.comparison", "keyword.operator.logical", "keyword.operator.bitwise",
          "keyword.operator.increment", "keyword.operator.decrement",
          "keyword.operator.pointer", "keyword.operator.address",
        ],
        settings: { foreground: C.operators, fontStyle: "bold" } },
      { name: "Arrow / member access",
        scope: ["punctuation.accessor", "punctuation.separator.dot-access", "punctuation.accessor.arrow"],
        settings: { foreground: C.operators } },

      // ── Punctuation ───────────────────────────────────────────────────────
      { name: "Brackets / parens / braces",
        scope: [
          "punctuation.section", "punctuation.section.block", "punctuation.section.parens",
          "punctuation.definition.bracket", "meta.brace.round", "meta.brace.square", "meta.brace.curly",
        ],
        settings: { foreground: C.fg4 } },
      { name: "Semicolons / commas",
        scope: ["punctuation.terminator", "punctuation.separator.comma", "punctuation.separator.colon"],
        settings: { foreground: C.fgMid } },
      { name: "Template angle brackets",
        scope: ["punctuation.section.angle-brackets", "punctuation.definition.typeparameters"],
        settings: { foreground: C.types } },

      // ── C++ specifics ─────────────────────────────────────────────────────
      { name: "C++ cast keywords",
        scope: ["keyword.operator.cast", "keyword.operator.word", "keyword.operator.expression"],
        settings: { foreground: C.types, fontStyle: "bold" } },
      { name: "C++ override / final / virtual / inline / constexpr",
        scope: [
          "storage.modifier.override", "storage.modifier.final", "storage.modifier.virtual",
          "storage.modifier.inline", "storage.modifier.constexpr", "storage.modifier.explicit",
        ],
        settings: { foreground: C.types, fontStyle: "italic" } },
      { name: "Pointer / reference declarators",
        scope: ["storage.modifier.pointer", "storage.modifier.reference"],
        settings: { foreground: C.fg4, fontStyle: "bold" } },

      // ── Python specifics ──────────────────────────────────────────────────
      { name: "Python f-string braces",
        scope: ["punctuation.definition.template-expression", "meta.fstring punctuation.definition.string"],
        settings: { foreground: C.preprocessor } },
      { name: "Python magic methods",
        scope: ["support.function.magic", "meta.function.python entity.name.function.magic"],
        settings: { foreground: C.functions, fontStyle: "bold italic" } },
      { name: "Python type hints",
        scope: ["meta.function.annotation", "meta.function.annotation.return"],
        settings: { foreground: C.types } },

      // ── Markdown ──────────────────────────────────────────────────────────
      { name: "Markdown headings",
        scope: ["markup.heading", "entity.name.section.markdown", "heading.1 entity.name", "heading.2 entity.name"],
        settings: { foreground: C.accentBlue, fontStyle: "bold" } },
      { name: "Markdown bold",
        scope: "markup.bold",
        settings: { foreground: C.fg, fontStyle: "bold" } },
      { name: "Markdown italic",
        scope: "markup.italic",
        settings: { foreground: C.fg, fontStyle: "italic" } },
      { name: "Markdown inline code",
        scope: "markup.inline.raw",
        settings: { foreground: C.types } },
      { name: "Markdown links",
        scope: ["markup.underline.link", "string.other.link"],
        settings: { foreground: C.accentBlue } },

      // ── CMake ─────────────────────────────────────────────────────────────
      { name: "CMake commands",
        scope: "keyword.cmake",
        settings: { foreground: C.functions, fontStyle: "bold" } },
      { name: "CMake variables",
        scope: ["variable.other.cmake", "variable.cmake"],
        settings: { foreground: C.numbers } },

      // ── Shell / Bash ──────────────────────────────────────────────────────
      { name: "Shell built-in commands",
        scope: "support.function.builtin.shell",
        settings: { foreground: C.types, fontStyle: "bold" } },
      { name: "Shell variable expansion",
        scope: ["variable.other.normal.shell", "punctuation.definition.variable.shell"],
        settings: { foreground: C.preprocessor } },

      // ── JSON / YAML / TOML ────────────────────────────────────────────────
      { name: "JSON / YAML / TOML booleans",
        scope: ["constant.language.json", "constant.language.yaml", "constant.language.toml"],
        settings: { foreground: C.accentBlue, fontStyle: "bold" } },
      { name: "TOML / YAML keys",
        scope: [
          "support.type.property-name", "entity.name.tag.yaml",
          "keyword.key.group.toml", "meta.mapping.key string",
        ],
        settings: { foreground: C.accentBlue, fontStyle: "bold" } },
      { name: "TOML section headers",
        scope: ["entity.name.section.group-title.toml", "punctuation.definition.table.toml"],
        settings: { foreground: C.types, fontStyle: "bold" } },
      { name: "YAML anchors / aliases",
        scope: ["entity.name.type.anchor.yaml", "variable.other.alias.yaml"],
        settings: { foreground: C.namespaces } },
      { name: "JSON keys",
        scope: "support.type.property-name.json",
        settings: { foreground: C.accentBlue, fontStyle: "bold" } },

      // ── CMND custom language ──────────────────────────────────────────────
      { name: "CMND namespace",
        scope: "entity.name.namespace.cmnd",
        settings: { foreground: C.namespaces } },
      { name: "CMND namespace separator",
        scope: "punctuation.separator.namespace.cmnd",
        settings: { foreground: C.operators } },
      { name: "CMND parameter",
        scope: "variable.parameter.cmnd",
        settings: { foreground: C.types } },
      { name: "CMND assignment operator",
        scope: "keyword.operator.assignment.cmnd",
        settings: { foreground: C.operators } },
      { name: "CMND value — boolean (on/off/true/false)",
        scope: "constant.language.boolean.cmnd",
        settings: { foreground: C.types, fontStyle: "bold italic" } },
      { name: "CMND value — numeric (int, float, PDG ID)",
        scope: "constant.numeric.cmnd",
        settings: { foreground: C.numbers, fontStyle: "bold" } },
      { name: "CMND value — string",
        scope: "string.unquoted.cmnd",
        settings: { foreground: C.strings } },
      { name: "CMND disabled command (commented-out setting)",
        scope: "comment.line.exclamation.disabled.cmnd",
        settings: { foreground: C.fgComment, fontStyle: "italic" } },

      // ── Invalid ───────────────────────────────────────────────────────────
      { name: "Invalid / deprecated",
        scope: ["invalid", "invalid.deprecated"],
        settings: { foreground: C.accentRedDark, fontStyle: "underline" } },
    ],

    // ═══════════════════════════════════════════════════════════════════════
    // SEMANTIC TOKEN COLORS (LSP — clangd / pylsp)
    // ═══════════════════════════════════════════════════════════════════════
    semanticHighlighting: true,
    semanticTokenColors: {
      "namespace":              { foreground: C.namespaces },
      "namespace.declaration":  { foreground: C.namespaces },
      "class":                  { foreground: C.types, bold: true },
      "struct":                 { foreground: C.types, bold: true },
      "enum":                   { foreground: C.types, bold: true },
      "enumMember":             { foreground: C.enumMember, bold: true },
      "type":                   { foreground: C.types },
      "typeParameter":          { foreground: C.types, italic: true },
      "interface":              { foreground: C.types, italic: true },
      "function":               { foreground: C.functions },
      "function.declaration":   { foreground: C.functions, bold: true },
      "method":                 { foreground: C.functions },
      "method.declaration":     { foreground: C.functions, bold: true },
      "event":                  { foreground: C.functions },
      "variable":               { foreground: C.variables },
      "variable.static":        { foreground: C.numbers },
      "parameter":              { foreground: C.parameters },
      "property":               { foreground: C.variables },
      "property.static":        { foreground: C.numbers },
      "selfParameter":          { foreground: C.types, bold: true, italic: true },
      "clsParameter":           { foreground: C.types, bold: true, italic: true },
      "macro":                  { foreground: C.preprocessor, bold: true },
      "keyword":                { foreground: C.types },
      "decorator":              { foreground: C.types, italic: true },
      "string":                 { foreground: C.strings },
      "number":                 { foreground: C.numbers, bold: true },
      "operator":               { foreground: C.operators },
      "comment":                { foreground: C.fgComment, italic: true },
    },
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════
const raw   = parsePalette(fs.readFileSync(path.join(__dirname, "palette.toml"), "utf8"));
const light = flatten(raw, 0);
const dark  = flatten(raw, 1);

const outDir = path.join(__dirname, "themes");
fs.mkdirSync(outDir, { recursive: true });

for (const [C, label, file] of [
  [light, "light", "hep-contrast-light.json"],
  [dark,  "dark",  "hep-contrast-dark.json" ],
]) {
  const outPath = path.join(outDir, file);
  fs.writeFileSync(outPath, JSON.stringify(buildTheme(C, label), null, 2));
  console.log(`Built → ${outPath}`);
}
