# Case study: the in-house pipeline behind tanda

tanda is the clean, general rewrite of a set of shell scripts I run every day to contribute
fixes to open-source AI tooling. This page describes that in-house system: how it is built,
the rules it runs under, and what the numbers say. It describes the design only; the scripts
themselves stay private.

**Result so far (24 November 2026):** 1,737 pull requests merged by maintainers across 405
repositories since August 2026, 310 of them in repositories with over 10k stars. The full list
is in the [Merge Log](https://portfolio-alexgonzalez33.vercel.app).

## Roles

One run is a *tanda*: a batch with a target number of new pull requests. Every role is a
coding-agent session with its own prompt and model, and they coordinate only through a shared
queue with a file lock.

```mermaid
flowchart LR
  subgraph Phase0[Before the run]
    F[Follow-up report<br/>reviews, CI, mail on open PRs]
  end
  S1[Scouts<br/>find bugs in current main] -->|TODO| Q[(Shared queue)]
  SG[Follow-up scout<br/>our open PRs] -->|followup rows| Q
  Q -->|claim| FX[Fixers<br/>reproduce, fix, test]
  FX -->|BUILT + test command| Q
  Q -->|claim| RV[Reviewers<br/>stronger model, re-run the test]
  RV -->|READY| P[Publish queue]
  RV -->|FIX / DROPPED| Q
  RV -->|HOLD| H[Human]
  M[Moderator] -. watches, closes the run .- Q
  F --> M
```

| Role | Model tier | What it may do |
| --- | --- | --- |
| Scout (×2) | mid | Search for real bugs; add rows to the queue. No code, no writes to GitHub. |
| Follow-up scout | mid | Turn maintainer reviews, conflicts and red CI on our open PRs into rows. |
| Fixer (×2–3) | mid | Reproduce the bug in an isolated worktree, fix it, record the exact test command that went red to green. |
| Reviewer (×1–3) | high | Re-run that test on the fix and on `main`, check value, diff size, duplicates and the PR text; set READY, FIX, DROPPED or HOLD. |

The number of sessions follows the run's target. A run aimed at five new PRs or fewer starts two
scouts, two fixers and one reviewer; a run with 13 sessions for a five-PR target was more
than the work needed.
| Moderator | high | Watch the run, unblock stuck rows, write the closing report. |
| Follow-up owner | mid | Own every open PR until it is merged or closed. |

## Queue states

`TODO → CLAIMED → BUILT → REVIEW → READY → PUBLISHED`, with `FIX` (back to a fixer with a
concrete note), `DROPPED`, `PLAN` (a reviewer writes a five-line plan before anyone codes) and
`HOLD` (a human decides). A row cannot reach `BUILT` without the test command that proved the
fix, and roles may only set the states their prompt allows.

## Rules the agents work under

These are policy decisions, each made after looking at what earlier runs produced:

- **Only work maintainers want.** New rows come from issues the team opened, labelled or
  confirmed, or from regressions users hit in current `main`; speculative clean-ups are dropped.
- **Maintained projects first.** New work goes to repositories with an active team behind them
  and to those that already merge this kind of fix. Follow-ups on PRs already open continue
  anywhere until they are merged or closed.
- **Volume caps.** A ceiling of open PRs per repository, lower where a maintainer asked for it,
  and some organisations frozen entirely. Maintainers notice volume before quality.
- **AI policies are respected.** Repositories whose contribution guide rejects AI-assisted
  work are skipped. PR descriptions disclose AI involvement in neutral wording, and on repos
  with a CLA no co-author trailer is added.
- **The reviewer is independent and strict.** It runs on a stronger model than the fixer and
  re-runs the fixer's test itself; a fix without a test that fails on `main` goes back.
- **Mechanical follow-ups skip the reviewer.** Lint, CI and literal changes a maintainer
  requested go straight to READY after a diff check, so reviewer time goes to new logic.

## Measuring it

Each closed run appends a row of metrics: duration, rows by type, rows dropped at triage, new
PRs and follow-ups published, merges, 30-day merge rate, open PRs, sessions, requests, average
context per request, and model cost at API prices.

Over 35 runs between 25 October and 1 November 2026:

| Metric | Value |
| --- | --- |
| New pull requests published | 446 |
| Follow-ups published | 130 |
| 30-day merge rate | 87–89% |
| Model cost per published PR (API prices) | about $2.50–4 |

Decisions the metrics drove:

- **Triage before build.** Building a fix and then dropping it was the most expensive mistake,
  so candidates are verified before a fixer touches them.
- **Reviewers moved to a cheaper model.** A side-by-side test showed nearly the same verdicts
  at about 2.5× lower cost.
- **A third reviewer.** The bottleneck was finished fixes waiting for review, not fixing.
- **Context discipline.** Prompts tell each role exactly which slice of the shared notes to
  read, because average context per request was the main cost driver.

## What changed after the first month

The pipeline kept running while I measured it. These are the changes since the numbers above,
each one a reaction to something the metrics or the maintainers showed.

- **Repositories are ordered by how they respond.** A repository with more than three times as
  many open PRs of mine as merges in the last 30 days goes behind the others when a fixer claims
  work. The trigger was one project with eight of my PRs open and two merged.
- **The run knows when it is out of work.** When every scout has finished, the queue has no
  candidates left and new plus in-progress PRs are still under the target, the run exits with a
  specific code instead of waiting for work that will not come.
- **Dry scout passes pause the run.** Three scout passes in a row that add nothing put the
  scouts to sleep for 30 minutes, so an empty search space costs time instead of tokens.
- **Headless roles start light.** Fixers, reviewers, scouts and the mail and watch roles run
  non-interactively and now start without the memory index, connectors or skills they never
  use (the reviewer keeps its skills), with a prompt cache of five minutes and a cap in dollars
  per queue row. In a test the fixed prefix of a session went from 34,465 to 10,709 tokens.
- **The moderator compacts less often.** Its auto-compaction threshold went from 100k to 200k
  tokens, because at 100k it compacted about every four requests. The run now warns when the moderator's context passes 220k tokens per request.
- **Cost is read from the transcripts, at real prices.** A day on 21 November came to about
  $2.30 per published PR once cache reads and writes are priced as they are billed. That is the
  number the light start is meant to bring down.

## What tanda keeps from this

The queue, the role verdicts, the review gate, the hold-for-a-human default and the
`oss-contrib` example all come from this system. What stays out of tanda is the
project-specific part: the company registry, the per-repo state and the prompts tuned to my
own targets.
