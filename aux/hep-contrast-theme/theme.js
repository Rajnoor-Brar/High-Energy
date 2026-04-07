#!/usr/bin/env node
/**
 * HEP Contrast — theme build script
 * Edit colors here, then run:  node build.js
 * Output:  themes/hep-contrast.json
 */

const fs = require("fs");
const path = require("path");

// ═══════════════════════════════════════════════════════════════════════
// PALETTE — edit these
// ═══════════════════════════════════════════════════════════════════════
const C = {
  // ── Syntax roles ──────────────────────────────────────────────────
  functions:      "#0055CC",   // bold blue
  types:          "#D71868",   // magenta  (also: keywords, decorators, self/cls)
  namespaces:     "#883DA4",   // purple
  variables:      "#224C98",   // deep blue  (also: parameters, properties)
  strings:        "#E60026",   // red
  operators:      "#E28512",   // amber-brown
  numbers:        "#CC332A",   // teal
  preprocessor:   "#D75C1E",   // amber
  parameters:     "#2072AF",   // medium blue

  fgComment:      "#777777",

  baseForeground: "#222222",
  baseBackground: "#f5f5f5",
  errors        : "#E00000",
  warnings      : "#ED9121",

    // ── Git ───────────────────────────────────────────────────────────
  gitAdded:       "#4F7703",
  gitModified:    "#E05915",
  gitDeleted:     "#BA160C",
  gitConflict:    "#F42A92",
  gitUntracked:   "#4682B4",
  gitIgnored:     "#777777",


  // ── Base text ─────────────────────────────────────────────────────
  fg:             "#0A0A0A",   // near-black
  fg2:            "#111111",
  fg3:            "#1A1A1A",
  fg4:            "#333333",   // (unused in syntax now — operators took this slot)
  fgMid:          "#555555",
  fgLight:        "#666666",
  fgSubtle:       "#888888",
  fgFaint:        "#AAAAAA",
  fgFainter:      "#BBBBBB",
  fgAlmostGone:   "#CCCCCC",
  fgWhisper:      "#DDDDDD",

  // ── Backgrounds ───────────────────────────────────────────────────
  bg:             "#FFFFFF",
  bgEditor:       "#FFFFFF",
  bgLine:         "#F3F3F3",
  bgSidebar:      "#F5F5F5",
  bgPanel:        "#FAFAFA",
  bgSection:      "#EBEBEB",
  bgActivity:     "#EFEFEF",
  bgTitle:        "#F0F0F0",
  bgTitleInact:   "#F8F8F8",
  bgInputFocus:   "#F8FBFF",
  bgPeekResult:   "#F0F4FF",

  // ── Accents / UI ──────────────────────────────────────────────────
  accentBlue:     "#0055CC",   // functions, focus borders, badges
  accentBlueDark: "#0044AA",
  accentAmber:    "#E6A117",   // modified files
  accentGreen:    "#337D27",   // untracked files
  accentOrange:   "#CF6F00",   // deleted files
  accentRed:      "#E60000",   // conflicts / errors
  accentRedDark:  "#CC0000",   // editor errors
  accentWarn:     "#886600",

  // ── Status bar ────────────────────────────────────────────────────
  statusBg:       "#DEDEDE",
  statusFg:       "#111111",
  statusDebugBg:  "#EEDAF2",
  statusRemoteBg: "#dbdaf2ff",
  statusRemoteFg: "#111111",

  // ── Selection / highlights ────────────────────────────────────────
  selection:      "#C8DCFF",
  selectionHi:    "#DDEEFF",
  wordHi:         "#E0EBF5",
  wordHiStrong:   "#B8D4F0",
  findMatch:      "#ffc400ff",
  findMatchHi:    "#ffdca0ff",
  rangeHi:        "#ffecccff",
  listFocus:      "#C8DCFF",
  listActive:     "#D0E4FF",
  listHover:      "#F2F2F2",

  // ── Borders / dividers ────────────────────────────────────────────
  border:         "#DCDCDC",
  borderLight:    "#D4D4D4",
  borderSubtle:   "#E8E8E8",
  borderFaint:    "#E0E0E0",

  // ── Diff ──────────────────────────────────────────────────────────
  diffAddedText:  "#CCFFCC55",
  diffRemovedText:"#FFCCCC55",
  diffAddedLine:  "#EEFFF0",
  diffRemovedLine:"#FFF0F0",

  // ── Peek view ─────────────────────────────────────────────────────
  peekBorder:     "#0055CC",
  peekEditor:     "#F8FBFF",
  peekResult:     "#F0F4FF",
  peekTitle:      "#D0E4FF",

  // ── Transparent overlays (hex8) ───────────────────────────────────
  shadowColor:        "#00000022",
  scrollbarBg:        "#00000018",
  scrollbarHover:     "#00000030",
  scrollbarActive:    "#0055CC44",
  warnBg66:           "#88660066",
  errorBg66:          "#E6000066",
  findMatch55:        "#FFD70055",
  diffAdded55:        "#CCFFCC55",
  diffRemoved55:      "#FFCCCC55",

  // ── Bracket pair ─────────────────────────────────────────────────
  bracket1:       "#0055CC",
  bracket2:       "#CF1196",
  bracket3:       "#007755",
  bracket4:       "#E59F2E",
  bracketGuide1:  "#D0E4FF",
  bracketGuide2:  "#FFD8CC",
  bracketGuide3:  "#C8F0E0",

  // ── Misc ──────────────────────────────────────────────────────────
  docCommentTag:  "#555577",
  enumMember:     "#007755",
  chartsOrange:   "#AA4400",
};

// ═══════════════════════════════════════════════════════════════════════
// THEME DEFINITION
// ═══════════════════════════════════════════════════════════════════════
const theme = {
  name: "HEP Contrast",
  type: "light",

  colors: {
    // ── Editor core ────────────────────────────────────────────────
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
    "editorCursor.foreground":                    "#000000",
    "editorWhitespace.foreground":                C.fgWhisper,
    "editorIndentGuide.background":               C.borderSubtle,
    "editorIndentGuide.activeBackground":         C.fgFainter,
    "editorRuler.foreground":                     C.borderFaint,

    // ── Bracket pair ───────────────────────────────────────────────
    "editorBracketHighlight.foreground1":         C.bracket1,
    "editorBracketHighlight.foreground2":         C.bracket2,
    "editorBracketHighlight.foreground3":         C.bracket3,
    "editorBracketHighlight.foreground4":         C.bracket4,
    "editorBracketHighlight.unexpectedBracket.foreground": C.accentRedDark,
    "editorBracketPairGuide.activeBackground1":   C.bracketGuide1,
    "editorBracketPairGuide.activeBackground2":   C.bracketGuide2,
    "editorBracketPairGuide.activeBackground3":   C.bracketGuide3,

    // ── Gutter / diff ──────────────────────────────────────────────
    "editorGutter.addedBackground":               C.accentBlue,
    "editorGutter.modifiedBackground":            C.accentAmber,
    "editorGutter.deletedBackground":             C.accentOrange,
    "diffEditor.insertedTextBackground":          C.diffAdded55,
    "diffEditor.removedTextBackground":           C.diffRemoved55,
    "diffEditor.insertedLineBackground":          C.diffAddedLine,
    "diffEditor.removedLineBackground":           C.diffRemovedLine,

    // ── Errors / warnings / info ───────────────────────────────────
    "editorError.foreground":                     C.accentRedDark,
    "editorWarning.foreground":                   C.accentWarn,
    "editorInfo.foreground":                      C.accentBlue,
    "editorHint.foreground":                      C.numbers,
    "editorError.background":                     "#FFF0F0",
    "editorWarning.background":                   "#FFFBEE",

    // ── Sidebar ────────────────────────────────────────────────────
    "sideBar.background":                         C.bgSidebar,
    "sideBar.foreground":                         C.fg3,
    "sideBar.border":                             C.border,
    "sideBarTitle.foreground":                    "#444444",
    "sideBarSectionHeader.background":            C.bgSection,
    "sideBarSectionHeader.foreground":            C.fg4,
    "sideBarSectionHeader.border":                C.borderLight,
    "tree.indentGuidesStroke":                    C.fgAlmostGone,

    // ── Git decorations ────────────────────────────────────────────
    "gitDecoration.addedResourceForeground":      C.gitAdded,
    "gitDecoration.modifiedResourceForeground":   C.gitModified,
    "gitDecoration.deletedResourceForeground":    C.gitDeleted,
    "gitDecoration.untrackedResourceForeground":  C.gitUntracked,
    "gitDecoration.ignoredResourceForeground":    C.gitIgnored,
    "gitDecoration.conflictingResourceForeground":C.gitConflict,
    "gitDecoration.stageModifiedResourceForeground": C.gitModified,

    // ── Activity bar ───────────────────────────────────────────────
    "activityBar.background":                     C.bgActivity,
    "activityBar.foreground":                     C.fg2,
    "activityBar.inactiveForeground":             C.fgSubtle,
    "activityBar.border":                         C.border,
    "activityBarBadge.background":                C.accentBlue,
    "activityBarBadge.foreground":                C.bg,

    // ── Status bar ─────────────────────────────────────────────────
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

    // ── Title bar ──────────────────────────────────────────────────
    "titleBar.activeBackground":                  C.bgTitle,
    "titleBar.activeForeground":                  C.fg2,
    "titleBar.inactiveBackground":                C.bgTitleInact,
    "titleBar.inactiveForeground":                C.fgSubtle,
    "titleBar.border":                            C.border,

    // ── Tabs ───────────────────────────────────────────────────────
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

    // ── Panel ──────────────────────────────────────────────────────
    "panel.background":                           C.bgPanel,
    "panel.border":                               C.border,
    "panelTitle.activeForeground":                C.accentBlue,
    "panelTitle.activeBorder":                    C.accentBlue,
    "panelTitle.inactiveForeground":              C.fgSubtle,
    "terminal.background":                        C.bg,
    "terminal.foreground":                        C.fg,
    "terminal.selectionBackground":               C.selection,
    "terminalCursor.foreground":                  "#000000",

    // ── Input / widgets ────────────────────────────────────────────
    "input.background":                           C.bg,
    "input.foreground":                           C.fg,
    "input.border":                               C.fgFainter,
    "input.placeholderForeground":                C.fgFaint,
    "inputOption.activeBorder":                   C.accentBlue,
    "inputOption.activeBackground":               C.listActive,
    "focusBorder":                                C.accentBlue,
    "widget.shadow":                              C.shadowColor,

    // ── Lists ──────────────────────────────────────────────────────
    "dropdown.background":                        C.bg,
    "dropdown.border":                            C.fgAlmostGone,
    "list.activeSelectionBackground":             C.listActive,
    "list.activeSelectionForeground":             C.fg,
    "list.inactiveSelectionBackground":           C.borderSubtle,
    "list.hoverBackground":                       C.listHover,
    "list.focusBackground":                       C.listFocus,
    "list.highlightForeground":                   C.accentBlue,

    // ── Scrollbar ──────────────────────────────────────────────────
    "scrollbarSlider.background":                 C.scrollbarBg,
    "scrollbarSlider.hoverBackground":            C.scrollbarHover,
    "scrollbarSlider.activeBackground":           C.scrollbarActive,

    // ── Minimap ────────────────────────────────────────────────────
    "minimap.findMatchHighlight":                 C.findMatch,
    "minimap.selectionHighlight":                 C.selection,
    "minimap.errorHighlight":                     C.errorBg66,
    "minimap.warningHighlight":                   C.warnBg66,
    "minimapGutter.addedBackground":              C.accentBlue,
    "minimapGutter.modifiedBackground":           C.gitModified,
    "minimapGutter.deletedBackground":            C.gitDeleted,

    // ── Notifications ──────────────────────────────────────────────
    "notificationCenter.border":                  C.border,
    "notifications.background":                   C.bg,
    "notifications.border":                       C.border,
    "notificationsErrorIcon.foreground":          C.accentRedDark,
    "notificationsWarningIcon.foreground":        C.accentWarn,
    "notificationsInfoIcon.foreground":           C.accentBlue,

    // ── Peek view ──────────────────────────────────────────────────
    "peekView.border":                            C.peekBorder,
    "peekViewEditor.background":                  C.peekEditor,
    "peekViewEditor.matchHighlightBackground":    C.findMatch55,
    "peekViewResult.background":                  C.peekResult,
    "peekViewResult.matchHighlightBackground":    C.selection,
    "peekViewResult.selectionBackground":         C.listActive,
    "peekViewTitle.background":                   C.peekTitle,
    "peekViewTitleLabel.foreground":              C.fg,
    "peekViewTitleDescription.foreground":        "#444444",

    // ── Breadcrumb ─────────────────────────────────────────────────
    "breadcrumb.foreground":                      C.fgLight,
    "breadcrumb.focusForeground":                 C.accentBlue,
    "breadcrumb.activeSelectionForeground":       C.fg,
    "breadcrumbPicker.background":                C.bg,

    // ── Buttons ────────────────────────────────────────────────────
    "button.background":                          C.accentBlue,
    "button.foreground":                          C.bg,
    "button.hoverBackground":                     C.accentBlueDark,
    "button.secondaryBackground":                 C.borderSubtle,
    "button.secondaryForeground":                 C.fg2,

    // ── Debug ──────────────────────────────────────────────────────
    "debugToolBar.background":                    C.bg,
    "debugIcon.breakpointForeground":             C.accentRedDark,
    "debugIcon.breakpointDisabledForeground":     C.fgFainter,
    "editor.stackFrameHighlightBackground":       C.rangeHi,
    "editor.focusedStackFrameHighlightBackground":"#CCFFCC",

    // ── Misc ───────────────────────────────────────────────────────
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
    "extensionBadge.remoteBackground":            C.gitAdded,
    "extensionBadge.remoteForeground":            C.bg,
  },

  // ═════════════════════════════════════════════════════════════════
  // TOKEN COLORS (TextMate scopes)
  // ═════════════════════════════════════════════════════════════════
  tokenColors: [

    // ── Base ──────────────────────────────────────────────────────
    {
      name: "Base text",
      scope: ["source", "text"],
      settings: { foreground: C.fg },
    },

    // ── Comments ──────────────────────────────────────────────────
    {
      name: "Comments",
      scope: ["comment", "punctuation.definition.comment"],
      settings: { foreground: C.fgComment, fontStyle: "italic" },
    },
    {
      name: "Doc comment tags",
      scope: [
        "comment.block.documentation storage.type.class.jsdoc",
        "comment.block.documentation entity.name.type",
        "storage.type.class.jsdoc",
        "comment.block.doxygen keyword",
        "comment.line.double-slash.doxygen keyword",
      ],
      settings: { foreground: C.docCommentTag, fontStyle: "italic bold" },
    },
    {
      name: "Doc comment parameter names",
      scope: "comment.block.doxygen variable",
      settings: { foreground: C.parameters, fontStyle: "italic" },
    },

    // ── Keywords ──────────────────────────────────────────────────
    {
      name: "Control-flow keywords",
      scope: [
        "keyword.control",
        "keyword.control.flow",
        "keyword.control.conditional",
        "keyword.control.loop",
        "keyword.control.return",
        "keyword.control.exception",
      ],
      settings: { foreground: C.types, fontStyle: "bold" },
    },
    {
      name: "Other keywords",
      scope: ["keyword", "keyword.other", "storage.modifier", "storage.type.modifier"],
      settings: { foreground: C.types },
    },
    {
      name: "C++ storage types (int, double, void, auto, ...)",
      scope: [
        "storage.type",
        "storage.type.primitive",
        "storage.type.built-in",
        "keyword.type",
      ],
      settings: { foreground: C.types, fontStyle: "bold" },
    },
    {
      name: "C++ new / delete / sizeof / this",
      scope: [
        "keyword.operator.new",
        "keyword.operator.delete",
        "keyword.operator.sizeof",
        "variable.language.this",
        "variable.language.self",
      ],
      settings: { foreground: C.types, fontStyle: "bold" },
    },
    {
      name: "Python self / cls",
      scope: ["variable.parameter.function.language.special"],
      settings: { foreground: C.types, fontStyle: "bold italic" },
    },
    {
      name: "import / from / as",
      scope: [
        "keyword.control.import",
        "keyword.control.from-import",
        "keyword.other.import",
        "keyword.other.use",
      ],
      settings: { foreground: C.types, fontStyle: "bold" },
    },

    // ── Preprocessor ──────────────────────────────────────────────
    {
      name: "Preprocessor directive",
      scope: [
        "keyword.control.directive",
        "keyword.control.directive.include",
        "keyword.control.directive.define",
        "keyword.control.directive.pragma",
        "keyword.control.directive.conditional",
        "keyword.control.directive.undef",
        "meta.preprocessor keyword",
        "meta.preprocessor.include keyword",
      ],
      settings: { foreground: C.preprocessor, fontStyle: "bold" },
    },
    {
      name: "Macro names",
      scope: [
        "entity.name.function.preprocessor",
        "meta.preprocessor.macro entity.name.function",
      ],
      settings: { foreground: C.preprocessor },
    },
    {
      name: "Preprocessor include path",
      scope: [
        "meta.preprocessor.include string",
        "string.quoted.other.lt-gt.include",
      ],
      settings: { foreground: C.strings },
    },

    // ── Types / Classes ───────────────────────────────────────────
    {
      name: "Class / struct / enum names",
      scope: [
        "entity.name.type",
        "entity.name.type.class",
        "entity.name.type.struct",
        "entity.name.type.enum",
        "entity.name.type.template",
        "entity.name.class",
        "support.class",
      ],
      settings: { foreground: C.types, fontStyle: "bold" },
    },
    {
      name: "Inherited / used type",
      scope: ["entity.other.inherited-class", "entity.name.type.base-class"],
      settings: { foreground: C.types, fontStyle: "bold italic" },
    },
    {
      name: "Python decorators",
      scope: [
        "meta.decorator",
        "entity.name.function.decorator",
        "punctuation.definition.decorator",
      ],
      settings: { foreground: C.types, fontStyle: "bold italic" },
    },
    {
      name: "Template type parameters",
      scope: ["storage.type.template", "entity.name.type.template-parameter"],
      settings: { foreground: C.types },
    },

    // ── Namespaces ────────────────────────────────────────────────
    {
      name: "Namespace names",
      scope: ["entity.name.namespace", "entity.name.type.namespace"],
      settings: { foreground: C.namespaces },
    },
    {
      name: "Scope resolution ::",
      scope: [
        "punctuation.separator.scope-resolution",
        "punctuation.accessor.double-colon",
      ],
      settings: { foreground: C.namespaces },
    },

    // ── Functions ─────────────────────────────────────────────────
    {
      name: "Function / method definition",
      scope: [
        "entity.name.function",
        "entity.name.function.member",
        "entity.name.function.definition",
      ],
      settings: { foreground: C.functions, fontStyle: "bold" },
    },
    {
      name: "Function call",
      scope: [
        "meta.function-call entity.name.function",
        "meta.function-call.generic entity.name.function",
      ],
      settings: { foreground: C.functions },
    },
    {
      name: "Support functions",
      scope: ["support.function", "support.function.builtin", "support.function.std"],
      settings: { foreground: C.functions },
    },
    {
      name: "Lambda",
      scope: ["meta.lambda", "storage.type.lambda", "punctuation.definition.lambda"],
      settings: { foreground: C.functions, fontStyle: "italic" },
    },

    // ── Variables ─────────────────────────────────────────────────
    {
      name: "Function parameters",
      scope: ["variable.parameter", "meta.function.parameter variable"],
      settings: { foreground: C.parameters },
    },
    {
      name: "Member variables",
      scope: [
        "variable.other.member",
        "variable.other.property",
        "variable.other.object.property",
      ],
      settings: { foreground: C.fg3 },
    },
    {
      name: "Local / other variables",
      scope: ["variable", "variable.other", "variable.other.local", "variable.other.readwrite"],
      settings: { foreground: C.fg },
    },
    {
      name: "Constants (ALL_CAPS / constexpr)",
      scope: ["variable.other.constant", "entity.name.variable.constant", "support.constant"],
      settings: { foreground: C.numbers, fontStyle: "bold" },
    },
    {
      name: "Python builtins",
      scope: "support.function.builtin.python",
      settings: { foreground: C.types },
    },

    // ── Strings ───────────────────────────────────────────────────
    {
      name: "Strings",
      scope: [
        "string",
        "string.quoted",
        "string.quoted.double",
        "string.quoted.single",
        "string.template",
      ],
      settings: { foreground: C.strings },
    },
    {
      name: "Raw / byte strings",
      scope: ["string.quoted.raw", "string.quoted.other", "string.other"],
      settings: { foreground: C.strings, fontStyle: "italic" },
    },
    {
      name: "Escape sequences",
      scope: ["constant.character.escape", "constant.other.placeholder"],
      settings: { foreground: C.preprocessor, fontStyle: "bold" },
    },
    {
      name: "Printf format specifiers",
      scope: ["constant.other.placeholder", "string.interpolated", "meta.interpolation"],
      settings: { foreground: C.preprocessor, fontStyle: "bold" },
    },

    // ── Numbers ───────────────────────────────────────────────────
    {
      name: "Numbers",
      scope: [
        "constant.numeric",
        "constant.numeric.integer",
        "constant.numeric.float",
        "constant.numeric.hex",
        "constant.numeric.octal",
        "constant.numeric.binary",
      ],
      settings: { foreground: C.numbers, fontStyle: "bold" },
    },
    {
      name: "Boolean / null / nullptr / None",
      scope: [
        "constant.language",
        "constant.language.boolean",
        "constant.language.null",
        "constant.language.nullptr",
      ],
      settings: { foreground: C.types, fontStyle: "bold italic" },
    },

    // ── Operators ─────────────────────────────────────────────────
    {
      name: "Operators",
      scope: [
        "keyword.operator",
        "keyword.operator.arithmetic",
        "keyword.operator.assignment",
        "keyword.operator.comparison",
        "keyword.operator.logical",
        "keyword.operator.bitwise",
        "keyword.operator.increment",
        "keyword.operator.decrement",
        "keyword.operator.pointer",
        "keyword.operator.address",
      ],
      settings: { foreground: C.operators, fontStyle: "bold" },
    },
    {
      name: "Arrow / member access",
      scope: [
        "punctuation.accessor",
        "punctuation.separator.dot-access",
        "punctuation.accessor.arrow",
      ],
      settings: { foreground: C.operators },
    },

    // ── Punctuation ───────────────────────────────────────────────
    {
      name: "Brackets / parens / braces",
      scope: [
        "punctuation.section",
        "punctuation.section.block",
        "punctuation.section.parens",
        "punctuation.definition.bracket",
        "meta.brace.round",
        "meta.brace.square",
        "meta.brace.curly",
      ],
      settings: { foreground: C.fg4 },
    },
    {
      name: "Semicolons / commas",
      scope: [
        "punctuation.terminator",
        "punctuation.separator.comma",
        "punctuation.separator.colon",
      ],
      settings: { foreground: C.fgMid },
    },
    {
      name: "Template angle brackets",
      scope: [
        "punctuation.section.angle-brackets",
        "punctuation.definition.typeparameters",
      ],
      settings: { foreground: C.types },
    },

    // ── C++ specifics ─────────────────────────────────────────────
    {
      name: "C++ cast keywords",
      scope: [
        "keyword.operator.cast",
        "keyword.operator.word",
        "keyword.operator.expression",
      ],
      settings: { foreground: C.types, fontStyle: "bold" },
    },
    {
      name: "C++ override / final / virtual / inline / constexpr",
      scope: [
        "storage.modifier.override",
        "storage.modifier.final",
        "storage.modifier.virtual",
        "storage.modifier.inline",
        "storage.modifier.constexpr",
        "storage.modifier.explicit",
      ],
      settings: { foreground: C.types, fontStyle: "italic" },
    },
    {
      name: "Pointer / reference declarators",
      scope: ["storage.modifier.pointer", "storage.modifier.reference"],
      settings: { foreground: C.fg4, fontStyle: "bold" },
    },

    // ── Python specifics ──────────────────────────────────────────
    {
      name: "Python f-string braces",
      scope: [
        "punctuation.definition.template-expression",
        "meta.fstring punctuation.definition.string",
      ],
      settings: { foreground: C.preprocessor },
    },
    {
      name: "Python magic methods",
      scope: [
        "support.function.magic",
        "meta.function.python entity.name.function.magic",
      ],
      settings: { foreground: C.functions, fontStyle: "bold italic" },
    },
    {
      name: "Python type hints",
      scope: ["meta.function.annotation", "meta.function.annotation.return"],
      settings: { foreground: C.types },
    },

    // ── Markdown ──────────────────────────────────────────────────
    {
      name: "Markdown headings",
      scope: [
        "markup.heading",
        "entity.name.section.markdown",
        "heading.1 entity.name",
        "heading.2 entity.name",
      ],
      settings: { foreground: C.accentBlue, fontStyle: "bold" },
    },
    {
      name: "Markdown bold",
      scope: "markup.bold",
      settings: { foreground: C.fg, fontStyle: "bold" },
    },
    {
      name: "Markdown italic",
      scope: "markup.italic",
      settings: { foreground: C.fg, fontStyle: "italic" },
    },
    {
      name: "Markdown inline code",
      scope: "markup.inline.raw",
      settings: { foreground: C.types },
    },
    {
      name: "Markdown links",
      scope: ["markup.underline.link", "string.other.link"],
      settings: { foreground: C.accentBlue },
    },

    // ── CMake ─────────────────────────────────────────────────────
    {
      name: "CMake commands",
      scope: "keyword.cmake",
      settings: { foreground: C.functions, fontStyle: "bold" },
    },
    {
      name: "CMake variables",
      scope: ["variable.other.cmake", "variable.cmake"],
      settings: { foreground: C.numbers },
    },

    // ── Shell / Bash ──────────────────────────────────────────────
    {
      name: "Shell built-in commands",
      scope: "support.function.builtin.shell",
      settings: { foreground: C.types, fontStyle: "bold" },
    },
    {
      name: "Shell variable expansion",
      scope: [
        "variable.other.normal.shell",
        "punctuation.definition.variable.shell",
      ],
      settings: { foreground: C.preprocessor },
    },
    {
      name: "Shell flags",
      scope: "string.unquoted.argument",
      settings: { foreground: C.fg },
    },

    // ── JSON / YAML / TOML ────────────────────────────────────────
    {
      name: "JSON / YAML / TOML keywords and booleans",
      scope: [
        "constant.language.json",
        "constant.language.yaml",
        "constant.language.toml",
      ],
      settings: { foreground: C.accentBlue, fontStyle: "bold" },
    },
    {
      name: "TOML / YAML keys",
      scope: [
        "support.type.property-name",
        "entity.name.tag.yaml",
        "keyword.key.group.toml",
        "meta.mapping.key string",
      ],
      settings: { foreground: C.accentBlue, fontStyle: "bold" },
    },
    {
      name: "TOML section headers",
      scope: [
        "entity.name.section.group-title.toml",
        "punctuation.definition.table.toml",
      ],
      settings: { foreground: C.types, fontStyle: "bold" },
    },
    {
      name: "YAML anchors / aliases",
      scope: [
        "entity.name.type.anchor.yaml",
        "variable.other.alias.yaml",
      ],
      settings: { foreground: C.namespaces },
    },
    {
      name: "JSON keys",
      scope: "support.type.property-name.json",
      settings: { foreground: C.accentBlue, fontStyle: "bold" },
    },

    // ── CMND custom language ──────────────────────────────────────
    {
      name: "CMND namespace",
      scope: "entity.name.namespace.cmnd",
      settings: { foreground: C.namespaces },
    },
    {
      name: "CMND namespace separator",
      scope: "punctuation.separator.namespace.cmnd",
      settings: { foreground: C.operators },
    },
    {
      name: "CMND parameter",
      scope: "variable.parameter.cmnd",
      settings: { foreground: C.types },
    },
    {
      name: "CMND assignment operator",
      scope: "keyword.operator.assignment.cmnd",
      settings: { foreground: C.operators },
    },
    {
      name: "CMND value string",
      scope: "string.unquoted.cmnd",
      settings: { foreground: C.strings },
    },

    // ── Invalid ───────────────────────────────────────────────────
    {
      name: "Invalid / deprecated",
      scope: ["invalid", "invalid.deprecated"],
      settings: { foreground: C.accentRedDark, fontStyle: "underline" },
    },
  ],

  // ═════════════════════════════════════════════════════════════════
  // SEMANTIC TOKEN COLORS (LSP — clangd / pylsp)
  // ═════════════════════════════════════════════════════════════════
  semanticHighlighting: true,
  semanticTokenColors: {
    // Namespaces — purple, unbold
    "namespace":                { foreground: C.namespaces },
    "namespace.declaration":    { foreground: C.namespaces },
    // Types — magenta
    "class":                    { foreground: C.types, bold: true },
    "struct":                   { foreground: C.types, bold: true },
    "enum":                     { foreground: C.types, bold: true },
    "enumMember":               { foreground: C.enumMember, bold: true },
    "type":                     { foreground: C.types },
    "typeParameter":            { foreground: C.types, italic: true },
    "interface":                { foreground: C.types, italic: true },
    // Functions — blue
    "function":                 { foreground: C.functions },
    "function.declaration":     { foreground: C.functions, bold: true },
    "method":                   { foreground: C.functions },
    "method.declaration":       { foreground: C.functions, bold: true },
    "event":                    { foreground: C.functions },
    // Variables — deep blue
    "variable":                 { foreground: C.variables },
    "variable.static":          { foreground: C.numbers },
    "parameter":                { foreground: C.parameters },
    "property":                 { foreground: C.variables },
    "property.static":          { foreground: C.numbers },
    // self/cls — keyword-colored, bold italic
    "selfParameter":            { foreground: C.types, bold: true, italic: true },
    "clsParameter":             { foreground: C.types, bold: true, italic: true },
    // Macros — amber
    "macro":                    { foreground: C.preprocessor, bold: true },
    // Keywords — same as types
    "keyword":                  { foreground: C.types },
    // Decorators
    "decorator":                { foreground: C.types, italic: true },
    // Literals
    "string":                   { foreground: C.strings },
    "number":                   { foreground: C.numbers, bold: true },
    // Operators
    "operator":                 { foreground: C.operators },
    // Comments
    "comment":                  { foreground: C.fgComment, italic: true },
  },
};

// ═══════════════════════════════════════════════════════════════════════
// OUTPUT
// ═══════════════════════════════════════════════════════════════════════
const outPath = path.join(__dirname, "themes", "hep-contrast.json");
fs.mkdirSync(path.join(__dirname, "themes"), { recursive: true });
fs.writeFileSync(outPath, JSON.stringify(theme, null, 2));
console.log(`Built → ${outPath}`);