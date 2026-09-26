# Lambda

Λ → p π⁻ reconstruction from Pythia events, measured twice on the same events.

| File | What |
|---|---|
| `Reconstruction.hh` | the physics, shared by both paths: every (p, π⁻) pair, the mass window (and an optional cos θ* cut), and the greedy one-to-one matching |
| `Lambda.cc` | a plain program built with `utils/Module.hh`: HepMC3 in, `lambda.root` out (densities, `Lambda/<set>_<property>`) |
| `Rivet/Lamriv.cc` | the same as a Rivet analysis: `lamriv.yoda`, options `MASSTOL`, `COSTHETATOL`, `RESERVED`, … |

```bash
hep build
```

```bash
hep run Lambda/lambda              # one run at 7 TeV: lambda.root, lamriv.yoda, lamriv.root
```

```bash
hep run Lambda/lambda masswindow   # the mass window swept through both paths
```

`configs/Lambda/lambda.toml` holds the cuts: the module's under `[tools.lambda.config]`, and
Lamriv's as options. A quantity with `target = ["lamriv/Lamriv", "lambda"]` sets both at once.
`configs/Lambda/lambda.cmnd` holds the physics (Angantyr Ne-20 on Ne-20, and Λ decaying to p π⁻).

**The two paths agree** to the precision YODA writes (7 significant digits), on the same events,
because App_Pythia fans out to both (`tests/integration/test_modules_p4.py`).

On Ne–Ne events the selected set is bounded by the protons (`reserved_protons` = 2 is pp's 2 × Z,
kept from v1), so it hardly moves with the window: the validated set is what measures the cut.
