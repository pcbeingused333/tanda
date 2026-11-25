# Contributing to tanda

Thanks for helping. tanda is small on purpose, and these rules keep it that way.

## Ground rules

- **No new runtime dependencies.** Standard library only, Python 3.11+. Dev-only tools need a good reason.
- **Small PRs.** One change per PR. If it touches the queue schema, the state model or role permissions, open an issue first.
- **Add a test with every behavior change.** For bug fixes, add a test that fails without the fix and passes with it. This is the bar tanda's own reviewer role uses.
- **Keep the philosophy:** agents report only through the CLI, HOLD for a human by default, no idle token burn, nothing writes to GitHub without a human.
- **Disclose AI involvement.** If a coding agent helped, say so in the PR description. That's expected and fine here.

## Dev setup

```bash
git clone https://github.com/pcbeingused333/tanda && cd tanda
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v     # ~20 s, runs the hello demo end to end
```

To try a change by hand:

```bash
mkdir /tmp/t && cd /tmp/t && tanda init hello && tanda run
```

## Where help is most useful

- Verifying the `opencode` and `codex` presets end to end, and documenting the permission flags each one needs
- New examples under `tanda/examples/` (see below)
- Clearer error messages, and the `tanda check` / `tanda report` commands in [docs/roadmap.md](docs/roadmap.md)
- Windows testing

## Adding an example

An example is a folder with `tanda.toml` and `prompts/*.md`. It gets copied by `tanda init <name>`. A good example:

- runs offline, or says clearly at the top of `tanda.toml` which CLI and keys it needs;
- gives every worker role `HOLD` among its verdicts;
- never lets an agent push, comment or open PRs;
- is covered by a test, if it can run with the fake agent.

## Reporting bugs

Include your `tanda.toml` (with secrets removed), the output of `tanda status`, and the relevant log from `.tanda/logs/`.
