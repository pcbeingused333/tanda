# Roadmap: small improvements

Concrete, small changes that would make the public version easier to use without changing its
philosophy. That philosophy: zero dependencies, agents report only through the CLI, HOLD by
default, no idle token burn, a human publishes. Each item is meant to fit in one small PR with
a test.

## CLI UX

| # | Change | Why |
|---|---|---|
| 1 | `tanda --version` | Not there today. Makes bug reports easier. |
| 2 | `tanda check`: validate `tanda.toml` | Catch at load time: a claimed state that no role or `initial_state` ever produces, a missing prompt file, `working` reused by two roles, a verdict with no claimant that isn't `DONE`/`DROPPED`/`HOLD`/an `extra_state`, or an agent binary not on `PATH` (`shutil.which`). |
| 3 | `tanda init --list` and `tanda init <ex> <dir>` | You can't discover examples today without reading the source. |
| 4 | `tanda run --dry-run` | Print each role's rendered prompt and command line without starting agents. |
| 5 | `tanda list --group owner/repo`, `--json` | Easier scripting and triage. |
| 6 | `tanda reset <id>` (human only) | Move a stuck `working` item back to its claim state, with an event. |

## Error messages

| # | Today | Better |
|---|---|---|
| 7 | `tanda: builder can only set BUILT DROPPED HOLD` | Add the item and a hint: `tanda: role builder cannot set READY on #12 (allowed: BUILT DROPPED HOLD)` |
| 8 | Agent binary missing: written only to the log, then the item goes to HOLD | Also print it on the console once per role and fail fast before the run starts (with #2). |
| 9 | The UI's `/api/set` accepts any state string | Validate it against `cfg.states` the way the CLI does, and return 400 with the valid list. |
| 10 | `tanda ui --host 0.0.0.0` starts silently | Print a warning that the dashboard has no authentication. |

## Observability

| # | Change | Why |
|---|---|---|
| 11 | `tanda report`: per-run summary from `events` | Throughput by state, verdicts per role, FIX loop count per item, HOLD reasons, median time in state. Everything needed is already in the DB. |
| 12 | Store `run_id` on events | Tie each verdict to the agent invocation and log that produced it. |
| 13 | Optional usage capture | If an agent prints usage JSON (for example `claude -p --output-format json`), parse tokens and cost into `runs`. Opt-in per agent, no dependency. |
| 14 | `max_cost_per_item` (with #13) | A per-item cap, which the in-house system already has. Over the cap, the item goes to HOLD. |
| 15 | UI: show `fields` and the reviewer's note on the card | Faster triage of `READY` and `HOLD`. |

## Robustness

| # | Change | Why |
|---|---|---|
| 16 | `tanda stop` also terminates running `once` roles | A documented known gap. |
| 17 | Pass long prompts through a file or stdin (opt-in `{prompt_file}` placeholder) | Avoids OS argument-length limits, especially on Windows. |
| 18 | On startup, put orphaned `working` items (from a crashed run) into HOLD | Today they stay in `working` and block the "drained" condition. |

## CI and packaging

| # | Change |
|---|---|
| 19 | GitHub Actions: `python -m unittest` on 3.11, 3.12 and 3.13 × ubuntu, macos and windows |
| 20 | A test per example: `tanda init <ex>` loads and passes `tanda check` |
| 21 | Publish to PyPI so `pip install tanda` / `pipx install tanda` works, if the name is free |
| 22 | A short screencast GIF of the hello demo in the README |

## Examples

| # | Example | Notes |
|---|---|---|
| 23 | `bug-bash`: one local repo, no GitHub | The scout reads `TODO`/`FIXME` and failing tests, builders fix in worktrees, the reviewer gates. The smallest realistic demo. |
| 24 | `docs-fix`: broken links and stale snippets | Cheap models, low risk. Good for trying the opencode and codex presets. |
| 25 | `oss-contrib`: add the optional `prompts/triage.md` | The toml refers to it, but the file isn't shipped. |
| 26 | `hello`: let the fake agent sometimes exit without a verdict | Shows the automatic HOLD path in the demo. |
