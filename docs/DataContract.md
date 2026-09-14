# Data Contract — output file format

Updated: 2026-06-12.

The rule that keeps this project multi-language ready:

> **Anything persisted to a ROOT output file must be readable by `uproot`
> (plain Python, no PyROOT, no C++ dictionaries).**

In practice that means flat `TTree`s of scalar POD branches, standard
histogram classes, and `TObjString`/`TParameter` metadata — never `std::variant`,
`std::map`, framework structs, or custom classes. The in-memory types
(`Probe::AuxValue`, `Probe::Event`, `RecordKey`) are deliberately *not*
serialized; they exist only between read and write.

## Output file layout (written by `Record::Writer`)

```
<prefix>[_<serial>][_<energy>GeV][_<events>].root
├── About/                      provenance, written by Record::Meta::writeAbout
│   ├── dataset/                name, experiment, data_type, run_period,
│   │                           campaign, file_uuid, parent_files  (TObjString)
│   ├── processing/             analysis_name, build_type, compiler,
│   │                           root_version, os_arch, config_snapshot
│   ├── events/                 n_events_total, n_events_processed,
│   │                           sum_weights, sum_weights_squared  (TParameter)
│   ├── physics/                generator, tune, pdf_set,
│   │                           center_of_mass_energy_gev, cross_section_pb,
│   │                           filter_efficiency
│   ├── objects/                selection_toml (the [lambda] config snapshot)
│   ├── integrity/              git SHA, dirty flag, config file SHA-256s
│   └── notes/                  description, known_issues, contact
├── <Collection> trees          one per declared particle collection,
│   │                           e.g. Protons, Pions:
│   │                             event_index (Int/Long64)
│   │                             Energy, pX, pY, pZ (Double)   ← GeV
│   └── ...
├── <Object> directories        histograms: TH1D / TH2D / TProfile
└── <explicit trees>            user-declared flat trees of POD branches
```

## Conventions

- **Units:** GeV everywhere (natural units, c = 1); angles in radians.
  See the convention block in `utils/Physics.hh`.
- **Branch types:** `Double_t`, `Float_t`, `Int_t`, `UInt_t`, `Long64_t`,
  `ULong64_t`, `Bool_t` only. Fixed- or counter-sized arrays of those are
  fine (`nX` + `X[nX]` NanoAOD style); jagged object branches are not.
- **Event linkage:** per-candidate rows carry `event_index`, ascending within
  a tree. Readers (`Probe`, future `Ingest`) rely on monotonicity for
  partitioned parallel reads — don't write out-of-order indices.
- **Metadata:** every file must carry `About/integrity` (git SHA + config
  hashes) so any plot or ML artifact can be traced to the exact code and
  config that produced it.

## Python side

```python
import uproot

f = uproot.open("Lambda_Gen_7000GeV_1k.root")
protons = f["Protons"].arrays(library="np")     # or library="pd"
mass_hist = f["Validated/Validated_Mass_Invariant_Hist"]
git_sha = f["About/integrity/git_sha"]          # TObjString
```

A future `py/check_contract.py` (planned, Phase 5) will assert this contract
mechanically as part of `tests/run_all.sh`.

## Enforcement

There is no automatic gate yet — when adding a new branch or object to
`Record`, check it against this file. If you find yourself wanting to persist
a variant/map/struct, flatten it into POD columns instead.
