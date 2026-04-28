# Bot Instructions

## Plan Approval

- During planning, do not solicit go-ahead or ask to proceed; transition to
  implementation only when the user explicitly triggers it (e.g. "Implement the plan").
- Save the plan progressively to `bots/current_plan.md` during planning, to
  avoid loss on context reset.
- Future roadmaps and intent notes go in `bots/intent.md`.
- Run `/compact` after a major implementation triggered by "Implement the plan".

## Context

### Directory Layout

| Path        | Purpose                                                                     |
| ----------- | --------------------------------------------------------------------------- |
| `aux/`      | VSCode extensions and tooling for HEP UX                                    |
| `bots/`     | Bot configuration, plans (`current_plan.md`, `intent.md`), and `lessons.md` |
| `configs/`  | User configs for programs                                                   |
| `datasets/` | Third-party datasets downloaded from the internet                           |
| `docs/`     | Markdown files: file maps, documentation                                    |
| `modules/`  | Project-specific objects and functions                                      |
| `outputs/`  | Processed datasets                                                          |
| `results/`  | Presentable outputs (images, PDFs)                                          |
| `utils/`    | Core logic not tied to a specific module                                    |

- For any module or utility `Foo`, its submodules reside in `Foo/`.
- `BOT.md` contains directives for bots and agents (BOTs).
- Additional rules given explicitly by the user may be appended to their dedicated file.
- Bots may record frequent issues, pitfalls, and observed code style conventions
  in `bots/lessons.md`. This file is consulted at lower priority than explicit
  instructions in `BOT.md` or user messages, only when context is otherwise
  insufficient.

## Code Design

Modules and utils are collectively called **Namespaces**. Each has a corresponding
submodule directory (e.g. `Foo/` for namespace `Foo`).

- `Namespace.hh` exposes only the primary functions that define the namespace's mission.
- Supporting logic is distributed to submodules, for example:
  - **Types** — type definitions
  - **Type Methods** — member/free functions on those types
  - **Type Interfacing** — initialisation, import/export
  - **Workers** — task-specific logic
  - **Helpers** — internal utilities
- Submodules should preferably:
  - build linearly on each other (minimise circular dependencies)
  - be self-sufficient with minimal includes, even of sibling submodules
  - expose a minimal interface to other namespaces — typically `Types.hh` is
    sufficient for cross-namespace communication
  - avoid sub-namespacing unless it meaningfully improves readability

## Testing

- When running tests, redirect output paths from `outputs/` to `outputs/test/`.
- Restore to `outputs/` only after tests pass or are explicitly abandoned by the user.
- If a test run is interrupted or fails, do not restore paths automatically —
  report the state to the user and wait for instruction.
- Do not modify source or output paths permanently without user confirmation.