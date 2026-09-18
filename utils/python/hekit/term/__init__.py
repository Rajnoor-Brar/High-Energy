"""The terminal: one view model, two renderers (06 §1–2).

`model.RunView` holds what a run looks like; `dashboard` draws it live with rich, `plain` writes lines
for logs and pipes, and `hep watch` rebuilds the same view from a `status.jsonl`.
"""

from .model import PointView, RunView, StageView, from_journal  # noqa: F401
