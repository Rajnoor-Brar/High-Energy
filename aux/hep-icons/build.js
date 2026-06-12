#!/usr/bin/env node
// build.js — Merge Material Icon Theme base with HEP additions
// Reads MIT's dist/material-icons.json, re-roots icon paths from ./../icons/
// to ./icons/ (our extension root), then injects HEP icon definitions and
// file/folder name mappings on top.  Writes hep-icons.json.
//
// Run:  node build.js
// Requires: MIT extension installed at MIT_ROOT below (auto-detected from
//           ~/.vscode/extensions/).

const fs   = require("fs");
const path = require("path");
const os   = require("os");

// ── Locate MIT ─────────────────────────────────────────────────────────────
const extDir = path.join(os.homedir(), ".vscode", "extensions");
const mitDir = fs.readdirSync(extDir)
  .filter(d => d.startsWith("pkief.material-icon-theme-"))
  .sort()
  .pop();

if (!mitDir) {
  console.error("Material Icon Theme not found in ~/.vscode/extensions/. Install it first.");
  process.exit(1);
}

const MIT_JSON = path.join(extDir, mitDir, "dist", "material-icons.json");
console.log(`Using MIT: ${mitDir}`);

// ── Load MIT base ──────────────────────────────────────────────────────────
const base = JSON.parse(fs.readFileSync(MIT_JSON, "utf8"));

// Fix all icon paths:  ./../icons/X  →  ./icons/X
function fixPath(p) {
  return p.replace(/^\.\/\.\.\/icons\//, "./icons/");
}

function fixDefs(defs) {
  if (!defs) return defs;
  const out = {};
  for (const [k, v] of Object.entries(defs)) {
    out[k] = { iconPath: fixPath(v.iconPath) };
  }
  return out;
}

function fixThemeLayer(layer) {
  if (!layer) return layer;
  const out = {};
  if (layer.iconDefinitions) out.iconDefinitions = fixDefs(layer.iconDefinitions);
  // Copy everything else unchanged (fileExtensions, folderNames, etc. in light/hc use id refs, not paths)
  for (const [k, v] of Object.entries(layer)) {
    if (k !== "iconDefinitions") out[k] = v;
  }
  return out;
}

// ── HEP icon definitions ───────────────────────────────────────────────────
const HEP_DEFS = {
  "_hep_root":             { iconPath: "./icons/root.svg" },
  "_hep_cmnd":             { iconPath: "./icons/cmnd.svg" },
  "_hep_lhe":              { iconPath: "./icons/lhe.svg" },
  "_hep_hepmc":            { iconPath: "./icons/hepmc.svg" },
  "_hep_dec":              { iconPath: "./icons/dec.svg" },
  "_hep_folder_paint":     { iconPath: "./icons/folder-paint.svg" },
  "_hep_folder_paint_o":   { iconPath: "./icons/folder-paint-open.svg" },
  "_hep_folder_monitor":   { iconPath: "./icons/folder-monitor.svg" },
  "_hep_folder_monitor_o": { iconPath: "./icons/folder-monitor-open.svg" },
  "_hep_folder_record":    { iconPath: "./icons/folder-record.svg" },
  "_hep_folder_record_o":  { iconPath: "./icons/folder-record-open.svg" },
  "_hep_folder_probe":     { iconPath: "./icons/folder-probe.svg" },
  "_hep_folder_probe_o":   { iconPath: "./icons/folder-probe-open.svg" },
};

// ── HEP file extension overrides/additions ─────────────────────────────────
// MIT already covers: .py, .cpp, .h, .json, .yaml, .toml, .md, .ipynb, ...
// We add HEP-specific formats and override a few (e.g. .mac → console, not g4mac yet)
const HEP_FILE_EXTS = {
  // ── HEP native formats ──────────────────────────────────────────────
  "root":    "_hep_root",
  "cmnd":    "_hep_cmnd",
  "lhe":     "_hep_lhe",
  "hepmc":   "_hep_hepmc",
  "hepmc2":  "_hep_hepmc",
  "hepmc3":  "_hep_hepmc",
  "dec":     "_hep_dec",
  // ── These map to existing MIT icons (name-only additions) ───────────
  // .yoda → table/histogram (MIT table icon)
  "yoda":    "table",
  // .spc .slha → table (structured text columns)
  "spc":     "table",
  "slha":    "table",
  // .gdml → xml (it IS xml)
  "gdml":    "xml",
  // .pwhg → shares LHE scattering concept; use lhe icon for now
  "pwhg":    "_hep_lhe",
  // .mac (Geant4 macros) → console/shell
  "mac":     "console",
  // ── ML / data science ──────────────────────────────────────────────
  // .safetensors → database (nearest match until we author dedicated icon)
  "safetensors": "database",
  // .keras, .tflite → database until V1 icons
  "keras":   "database",
  "tflite":  "database",
  // .ckpt → already covered by MIT's 'checkpoint' or 'database'; force database
  "ckpt":    "database",
  // .npy .npz → already in MIT as numpy? If not, database
  "npy":     "database",
  "npz":     "database",
  // .h5 .hdf5 → database
  "h5":      "database",
  "hdf5":    "database",
  // .arrow .joblib → database
  "arrow":   "database",
  "joblib":  "pkl",
  // .pb (TF SavedModel protobuf)
  "pb":      "database",
  // ROOT macro on macOS (.C is case-sensitive; .C isn't in MIT's fileExtensions)
  "C":       "cpp",
};

// ── HEP file name additions ────────────────────────────────────────────────
const HEP_FILE_NAMES = {
  "CMakeLists.txt": "cmake",
};

// ── HEP folder name additions ──────────────────────────────────────────────
const HEP_FOLDER_NAMES = {
  // Project subsystem folders
  "paint":   "_hep_folder_paint",
  "monitor": "_hep_folder_monitor",
  "record":  "_hep_folder_record",
  "probe":   "_hep_folder_probe",
  // Physics / HEP domain folders → MIT's atom icon
  "physics": "folder-atom",
  "Physics": "folder-atom",
  // Simulation → MIT already has folder-simulation; make lowercase too
  "simulation":  "folder-simulations",
  "simulations": "folder-simulations",
  // Analysis, results, experiments
  "analysis":    "folder-benchmark",
  "analyses":    "folder-benchmark",
  "results":     "folder-benchmark",
  "result":      "folder-benchmark",
  "experiments": "folder-benchmark",
  "experiment":  "folder-benchmark",
  // Datasets (ML + HEP data folders)
  "datasets":  "folder-database",
  "dataset":   "folder-database",
  "raw":       "folder-database",
  "processed": "folder-database",
  "interim":   "folder-database",
  // Plots/figures → images
  "plots":     "folder-images",
  "plot":      "folder-images",
  // Filter/preprocessing
  "preprocessing":  "folder-filter",
  "preprocess":     "folder-filter",
  // Toolbox folders
  "aux":            "folder-tools",
  // ML workflow folders (V1 will get dedicated icons)
  "weights":     "folder-resource",
  "weight":      "folder-resource",
  "training":    "folder-class",
  "train":       "folder-class",
  "checkpoints": "folder-archive",
  "checkpoint":  "folder-archive",
  "root_macros": "folder-script",
  "macros":      "folder-script",
  "macro":       "folder-script",
};

const HEP_FOLDER_NAMES_EXPANDED = {};
for (const [k, v] of Object.entries(HEP_FOLDER_NAMES)) {
  // MIT uses a naming convention: folder-X → folder-X-open
  // For our custom icons, map to the _open variant
  const openMap = {
    "_hep_folder_paint":   "_hep_folder_paint_o",
    "_hep_folder_monitor": "_hep_folder_monitor_o",
    "_hep_folder_record":  "_hep_folder_record_o",
    "_hep_folder_probe":   "_hep_folder_probe_o",
  };
  // For MIT icons: folderExpanded is stored separately in MIT's JSON;
  // we don't need to add open variants here — MIT handles it.
  // Only add for our custom HEP icons.
  if (openMap[v]) {
    HEP_FOLDER_NAMES_EXPANDED[k] = openMap[v];
  }
}

// ── Merge ──────────────────────────────────────────────────────────────────
const merged = {
  ...base,
  iconDefinitions:      { ...fixDefs(base.iconDefinitions), ...HEP_DEFS },
  fileExtensions:       { ...base.fileExtensions,           ...HEP_FILE_EXTS },
  fileNames:            { ...base.fileNames,                ...HEP_FILE_NAMES },
  folderNames:          { ...base.folderNames,              ...HEP_FOLDER_NAMES },
  folderNamesExpanded:  { ...base.folderNamesExpanded,      ...HEP_FOLDER_NAMES_EXPANDED },
  // Fix paths in light + highContrast override layers too
  light:         fixThemeLayer(base.light),
  highContrast:  fixThemeLayer(base.highContrast),
};

const OUT = path.join(__dirname, "hep-icons.json");
fs.writeFileSync(OUT, JSON.stringify(merged, null, 2));

const stats = fs.statSync(OUT);
console.log(`Written: hep-icons.json  (${(stats.size / 1024).toFixed(1)} KB)`);
console.log(`  iconDefinitions: ${Object.keys(merged.iconDefinitions).length}`);
console.log(`  fileExtensions:  ${Object.keys(merged.fileExtensions).length}`);
console.log(`  fileNames:       ${Object.keys(merged.fileNames).length}`);
console.log(`  folderNames:     ${Object.keys(merged.folderNames).length}`);
console.log(`  HEP additions:   ${Object.keys(HEP_DEFS).length} defs, ${Object.keys(HEP_FILE_EXTS).length} exts, ${Object.keys(HEP_FOLDER_NAMES).length} folders`);
