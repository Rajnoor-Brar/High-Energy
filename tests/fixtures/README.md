# tests/fixtures

`configs/`: the run TOMLs and cards the tests load, frozen from the repository's `configs/` at commit
`59f71da` (2026-10-03). The tests set `$HEKIT_CONFIGS` to this folder (tests/conftest.py), so
`PhotoProduction/eic` and every base card resolve here, never under the user's `configs/`, which the
user edits freely. A test failure therefore means the code changed, not a config.

Change a fixture only together with the test that needs the change. Never sync it from `configs/` wholesale.

`PhotoProduction/photo_zs.cmnd` was never committed under `configs/` (InProcZeus and zeus_seedSweep use it), so its
fixture is the working-tree copy of 2026-10-03.

One change from the commit: `PhotoProduction/zeus_validation.toml`'s `pdf` values carry `LHAPDF6:`, as V40 requires
(the committed file predates V40; the user's working copy has the same fix).
