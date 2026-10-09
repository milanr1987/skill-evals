# Skill Eval Bench

Local regression tests for Claude Code skills.

Skill Eval Bench takes a skill, wraps it in a minimal plugin and runs Claude Code's built-in `claude plugin eval` against it. Each test case runs **with the skill and without it**, so you see two things: whether the skill still does its job, and whether it actually helps compared to plain Claude.

## What it does

- **Wraps skills as plugins.** Copies each skill into `suites/<name>/skills/` and adds a plugin manifest, so `claude plugin eval` can load it. Your original skill folder is never modified.
- **Rewrites absolute paths.** A skill that writes to a fixed location (for example a memory folder) gets those paths replaced with relative ones, so tests run in a temporary folder instead of touching your real files.
- **Protects real files.** Files you list under `[protect]` are hashed before and after each run. If any of them changed, the run is marked `INVALID`.
- **Tracks token usage.** Reads token counts from every run's trace and stops starting new suites once a token budget is spent.
- **Writes a daily report.** A Markdown report per day: pass rate per case, with-skill vs. without-skill difference, tokens used, and regressions compared to the previous report.

## Requirements

- **Python 3.12 or newer.** No third-party packages.
- **Claude Code 2.1.269 or newer**, with `claude` on your `PATH`. Check with `claude --version`.
- **Bash.** Test cases can use a `scaffold.sh` script to create starting files. On Windows, install [Git for Windows](https://git-scm.com/download/win), which includes Git Bash.
- A logged-in Claude Code account. Test runs use your normal Claude Code usage (subscription quota or API billing, depending on how you are logged in).

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/milanr1987/skill-evals.git
   cd skill-evals
   ```

2. Check that Python and Claude Code are the right versions:

   ```bash
   python --version     # 3.12+
   claude --version     # 2.1.269+
   ```

3. Run the tool's own tests. They do not call Claude and cost nothing:

   ```bash
   python -m unittest discover -s tests -v
   ```

4. Create your own config. `skills.toml` ships with only the demo suite `_probe`. Copy it to `skills.local.toml` (git-ignored) and add suites that point to skills on your machine (see [Configuration](#configuration)):

   ```bash
   cp skills.toml skills.local.toml
   ```

   When `skills.local.toml` exists, `run.py` uses it instead of `skills.toml`.

5. Copy the skills into their suites and check that everything resolves:

   ```bash
   python run.py sync
   ```

   Each suite prints `ok` with the hash of its `SKILL.md`, or an error explaining what is wrong (missing `SKILL.md`, a leftover absolute path).

6. Run the included probe suite as a first real test:

   ```bash
   python run.py test _probe --runs 1
   ```

## Usage

All commands run from inside the `skill-evals/` folder.

### `sync`: prepare suites (no model calls)

```bash
python run.py sync              # all suites
python run.py sync my-skill     # one suite
```

### `test`: run evals (uses Claude usage)

```bash
python run.py test my-skill                 # one suite
python run.py test                          # all suites tagged "regression"
python run.py test --tag delta              # all suites with another tag
python run.py test my-skill --runs 1        # fewer repetitions per case (default: 3)
python run.py test --token-budget 2000000   # stop starting suites after this many tokens
```

`test` runs `sync` first, so the copy is always current. At the end it prints each suite's status and token count:

| Status | Meaning |
|---|---|
| `ok` | The eval finished and produced results. |
| `invalid` | A protected file changed during the run. Treat the results as untrusted and check what the skill wrote. |
| `not-run` | Skipped: token budget spent, sync failed, or no JSON output from `claude plugin eval`. The reason is printed next to it. |

The exit code is `1` if any suite is `invalid`, `2` if `claude` is missing or too old, otherwise `0`.

### `report`: build the daily report

```bash
python run.py report                     # today
python run.py report --date 2026-10-07   # a specific day
```

The report is written to `results/<date>.md`. Raw output for each suite goes to `results/raw/<date>-<suite>.json`, `.log`, `.tokens.json` and `.meta.json`.

## How a test run works

For each suite, `python run.py test` does the following:

1. **Sync.** Copies the skill(s) from `source` into `suites/<name>/skills/` and applies `path_map` replacements.
2. **Scaffold.** For each case, joins the suite's `_fixture.sh` and the case's optional `extra.sh` into `scaffold.sh`. Claude Code runs it in a temporary folder before the case starts.
3. **Snapshot.** Hashes every protected file.
4. **Eval.** Runs:

   ```
   claude plugin eval suites/<name> --no-publish --trust-plugin --scaffold --keep-temp \
     --ablation <ablation> --runs <N> --max-cost-usd <limit> --json results/raw/<date>-<name>.json \
     [--allow-tools ...]
   ```

5. **Check.** Hashes the protected files again. Any change marks the suite `invalid`.
6. **Count tokens.** Reads input, output and cache tokens from each run's `trace.jsonl`, then deletes the temporary run folders.
7. **Report.** Builds the Markdown report for the day.

## Configuration

Suites are defined in `skills.local.toml` (your own, git-ignored) or, if that file does not exist, in `skills.toml`. Each top-level table except `[protect]` is one suite. Relative paths resolve against the folder that holds the config file.

```toml
# Files and folders that tests must never change.
[protect]
files = ['/home/me/notes/memory.md']
dirs  = ['/home/me/notes/topics']

[my-skill]
source = '/home/me/.claude/skills/my-skill'   # folder containing SKILL.md
tags = ["regression"]                         # selected by `run.py test --tag`
allow_tools = ["Write", "Edit", "Bash"]       # tools the eval may give the model
token_budget = 1000000                        # this suite's share of the default budget
max_cost_usd = 5                              # passed to claude plugin eval
# ablation = "none"                           # run only with the skill, no comparison

# Optional: replace absolute paths inside the copied skill.
[my-skill.path_map]
'/home/me/notes/' = "notes/"

# Several skills in one suite, e.g. to compare overlapping skills.
[design-skills]
sources = [
  '/home/me/.claude/skills/design-review',
  'plugin:frontend-design@claude-plugins-official/frontend-design',
]
tags = ["delta"]
```

Use single quotes for Windows paths so backslashes are kept as-is.

`plugin:<plugin-id>/<skill>` sources are looked up in `installed_plugins.json` under `CLAUDE_CONFIG_DIR`, or `~/.claude` if that variable is not set.

## Writing test cases

A suite folder looks like this:

```
suites/my-skill/
  _fixture.sh                 # optional: starting files shared by all cases
  evals/
    saves-new-entry/
      case.yaml
      extra.sh                # optional: extra setup for this case only
  skills/                     # generated by sync, do not edit
```

Example `case.yaml`:

```yaml
schema_version: "1.1"
name: saves-new-entry
tags: [happy]
runs: 1
execution:
  max_turns: 8
  allowed_tools: [Read, Write, Edit, Glob, Grep, Skill]
  prompt: |
    Save this post to notes: Agents need evals. Skills drift without tests.
context:
  scaffold_script: scaffold.sh
graders:
  - name: new-entry-added
    type: regex
    pattern: '^## POST 2 '
    flags: m
    target: { source: file, path: notes.md }
  - name: old-entry-kept
    type: regex
    pattern: '^## POST 1 '
    flags: m
    target: { source: file, path: notes.md }
```

The report groups cases by the first matching tag:

| Tag | Use it for |
|---|---|
| `happy` | The normal task the skill is built for. |
| `edge` | Unusual input the skill should still handle. |
| `near-miss` | A prompt that looks related but should **not** trigger the skill. |
| `gate` | A required step or order, such as checking for duplicates before writing. |
| `held-out` | Cases you do not tune the skill against, to catch overfitting. |

Grader types:

| Type | Checks |
|---|---|
| `regex` | A pattern in the final answer or in a file (`target: { source: file, path: ... }`). |
| `llm` | A model judges the agent's final reply against your `criteria` text. It takes no `target`: to judge a file, ask the agent to print it in its reply and check the real file with a `regex` grader. |
| `tool_used` | How often a tool was used. `tool: Skill` with `max: 0` asserts the skill did not fire. |
| `tool_order` | One tool was used before another, e.g. `before: { tool: Grep }`, `after: { tool: Edit }`. |

The `suites/_probe/` folder has one working example of each grader type.

After adding cases:

```bash
python run.py sync my-skill
python run.py test my-skill --runs 1
python run.py report
```

## Recommended: a `/skill-evals` skill for Claude Code

You can use the bench from a terminal only. We recommend also adding a small Claude Code skill, so you can run and read tests from inside a Claude Code session.

### Why

- **Approval before spending.** A test run uses your Claude usage. The skill estimates the tokens first and waits for your "yes" before it starts.
- **Reports in plain language.** Claude reads `results/<date>.md` and the raw logs, then tells you which cases fail, why, and what regressed. You do not have to open the files.
- **Cleanup hints.** Skills whose with-skill vs. without-skill difference stays near zero are listed as candidates to remove.
- **Read-only.** The skill only runs commands and reads results. It never edits your skills, `skills.toml` or test cases.
- **Safety first.** If a suite is `invalid`, the skill reports that before anything else and does not interpret that suite's results.

### What you need

One file: `.claude/skills/skill-evals/SKILL.md`. Put it inside the cloned `skill-evals/` folder, so it loads when you start Claude Code there. To have it in every project, put it in `~/.claude/skills/skill-evals/SKILL.md` instead and write the full path to your `skill-evals/` folder in the file.

### How to add it

1. From inside the cloned `skill-evals/` folder:

   ```bash
   mkdir -p .claude/skills/skill-evals
   ```

2. Create `.claude/skills/skill-evals/SKILL.md` with this content:

   ````markdown
   ---
   name: skill-evals
   description: Use when the user types /skill-evals, or asks to test, check or measure their Claude skills ("test my skills", "does this skill still work", "which skill doesn't help", "show the skill test report"). Covers the local skill-evals/ tool. Not for unit tests of ordinary code.
   ---

   # skill-evals

   The local tool in `skill-evals/` tests Claude skills through `claude plugin eval`, with and without the skill. Always run commands from inside `skill-evals/`.

   ## Arguments

   | User types | Action |
   |---|---|
   | `/skill-evals` | **Status**, no usage |
   | `/skill-evals test <suite>` or `test all` | **Test**, uses Claude usage |
   | `/skill-evals report` | **Report**, no usage |

   ## Status

   1. Run `python run.py sync` to check that every skill copies cleanly.
   2. For each suite in `skills.toml`, count cases: `suites/<suite>/evals/*/case.yaml`.
   3. Read the newest `results/*.md` if one exists: number of regressions, PARTIAL and INVALID.
   4. Answer with a table (suite | cases | last status) and one sentence on the next step.

   ## Test

   1. The suite must exist in `skills.toml` and have at least one `case.yaml`. Do not run a suite with 0 cases; say that cases must be written first.
   2. Estimate tokens: cases × runs × arms (2, or 1 if the suite has `ablation = "none"`) × tokens per run. Tokens per run = the average from the latest report for that suite; if there is none, use 50,000 as a rough first guess.
   3. Gate: write "Running <suite>: N runs, estimated ~X tokens. OK?" and wait for "yes" in a new message. Approval for another suite or an earlier run is not approval for this one. Use `--runs 1` unless the user asks for more.
   4. Run `python run.py test <suite> --runs <n>` (for "all": no suite name).
   5. Continue with **Report** for today's date.

   ## Report

   Read `results/<date>.md` (the newest one if no date is given). Answer in this order:
   1. One sentence: passing / failing / regressions.
   2. Failing or regressed cases, with the reason from `results/raw/<date>-<suite>.log` when it is visible.
   3. Skills with an average difference ≤ 0.05 are candidates for removal (suggestion only).
   4. Total tokens from the report header.

   ## Rules

   - Report usage in tokens.
   - Never change source skills, `skills.toml` or test cases. Only run and read.
   - INVALID means a protected file changed: report it first and do not interpret that suite's results.
   ````

3. Start a new Claude Code session in the project (skills load at session start) and type `/skill-evals`. You should get the status table.

### When to run it

| Situation | What to run |
|---|---|
| You edited a skill | `/skill-evals test <that-suite>` |
| A new Claude model or Claude Code version came out | `/skill-evals test all`, then compare with the previous report |
| A skill fired when it should not have, or did not fire | Add a `near-miss` or `happy` case, then `/skill-evals test <suite>` |
| You have several skills that overlap (e.g. design skills) | `/skill-evals test <delta-suite>` and check which one adds the least |
| Regular check (e.g. once a week) | `/skill-evals` for status, `/skill-evals report` for the latest results |

### How to use it

```
/skill-evals                  # status: suites, case counts, last result
/skill-evals test my-skill    # estimate, ask for approval, run, report
/skill-evals test all         # same for every "regression" suite
/skill-evals report           # explain the latest report
```

Plain requests work too, for example "test my save-post skill" or "what did the last skill test show?".

## Safety

- `--no-publish` is always passed, so nothing is uploaded.
- `sync` fails if the copied skill still contains a path into your home folder, so a test cannot write to your real files through a path you forgot to add to `path_map`.
- Protected files are hashed before and after every suite. A change marks the run `invalid`.
- `max_cost_usd` caps each eval and `token_budget` caps the whole run.

## Project layout

```
run.py         CLI entry point: sync | test | report
skills.toml    default config (demo suite only); your own goes in skills.local.toml
bench/         config loading, sync, protection, eval call, token accounting, report
suites/        one wrapper plugin per suite, with test cases under evals/
probe/         small demo skill used by the _probe suite
tests/         unit tests for the tool (no Claude calls)
results/       daily reports; raw/ holds per-run output and is git-ignored
```
