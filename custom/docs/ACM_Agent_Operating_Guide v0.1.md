# ACM Agent Operating Guide v0.1

**Status:** Dogfooding (Sprints 1–4 — through Context / ACM-005)  
**Audience:** AI coding agents (Cursor, Codex, Claude Code, and others)  
**Purpose:** Operate the **current** ACM CLI and workspace safely and accurately in real projects.

This guide is derived from the v0.1 implementation and tests. When in doubt, prefer live `acm --help` output and repository behavior over Product Spec or Implementation Plan.

**Not yet in the CLI (later sprints):** `acm context build`, handoff, `acm history`, `acm knowledge show`.

---

## 0. Role and boundaries

**ACM is for:** durable task state, session handoffs (checkpoints), searchable lessons, repository indexing, and task-scoped **context snapshots** under `.acm/context/` (inspect via `acm context show` / `export` when a snapshot exists).

**ACM is not for:** replacing Git, running tests, editing source code, or storing secrets.

| Source of truth | Use it for |
|-----------------|------------|
| `.acm/` task and knowledge records | Declared task status, objectives, checkpoints, recorded lessons |
| Git working tree | Actual code, diffs, and verification you can run |
| Checkpoint front matter | Git revision/branch/dirty flag **at checkpoint write time** (may be stale later) |
| Context snapshot (`context-manifest.json`) | File selection and inlined bytes **at build time** (may be stale later) |

**Use ACM when it adds value** (multi-session work, explicit handoff, shared task list, reusable lessons). Do **not** create a task, checkpoint, or knowledge item for every trivial edit.

**Never without authorization:** `acm init`, changing `.acm/config.yaml`, editing product/architecture docs, or initializing ACM in a repo that does not already have a workspace.

---

## 1. Operating principles

1. **ACM data is authoritative** for recorded tasks and knowledge **as stored**—not for whether code matches intent.
2. **The repository is authoritative** for code and for test/build results you claim as verified.
3. **Never claim verification** unless you actually ran the check and recorded it under verified fields (checkpoint) or stated it plainly to the user.
4. **Preserve unrelated user changes** in the repo and in `.acm/`.
5. **Do not silently expand task scope**; negotiate scope with the user and update the task when appropriate.
6. **Never store secrets** in ACM (tokens, keys, credentials). Context selection excludes many secret paths; do not bypass that by pasting secrets into checkpoints or knowledge bodies.
7. **Do not hand-edit** `.acm/` internals (YAML, checkpoints, locks, counters) to bypass validation or locking.
8. **Command syntax** comes from the installed binary: run `acm --help` and subcommand help before assuming flags exist.

---

## 2. Capability snapshot (v0.1)

### 2.1 Available CLI (verified)

Top-level commands: `completion`, `context`, `help`, `init`, `knowledge`, `repo`, `task`, `version`.

**Global flags (all commands):**

- `--json` — structured JSON on stdout for supported commands  
- `--log-level` — `error`, `warn`, `info`, or `debug` (default `warn`); diagnostics go to stderr  

**Task:** `new`, `list`, `show`, `update`, `checkpoint`, `resume`, `close`  
**Knowledge:** `add`, `search`, `verify`, `deprecate`  
**Context:** `show`, `export` (read existing snapshots only — no `build` subcommand)  
**Repo:** `scan`, `status`, `tree`  
**Init:** `init` (authorized users only)

### 2.2 Implemented in code, not exposed as CLI

| Capability | Application API | Agent implication |
|------------|-----------------|-------------------|
| Context snapshot **build** | `app.BuildContextSnapshot` | **No** `acm context build`. A snapshot appears only after assembly runs (API/tests/tooling—not via agent CLI today). Until then, use `repo status`, direct file reads, and `task show`. |
| Knowledge show | — | **No** `acm knowledge show`. Use `search` (lessons only), or read `.acm/knowledge/<type>/<ID>/`. |
| Task field updates | partial via `task update` | Scope, constraints, acceptance criteria, `knowledge_refs`, and `description.md` are **not** CLI-updatable. |
| Handoff packages | (Sprint 5) | **No** `acm handoff` commands. |
| History query | (Sprint 6) | **No** `acm history`. Mutations may still print stderr: `history is enabled but no event was written`. |

### 2.3 Planned / documented elsewhere but not in this build

Product Spec names commands that are **not** registered after Sprint 4: `acm context build` (`--file`, `--path`, `--keyword`), `acm knowledge show`, `acm handoff create|show`, `acm history`. Treat those documents as **direction**, not current behavior.

---

## 3. Session bootstrap

### 3.1 Discover environment

From the project directory:

```bash
which acm
acm version
git rev-parse --show-toplevel
```

Confirm the Git top-level. ACM commands discover the repository from the current working directory (or empty `startDir` = cwd). Bare Git repositories are **not** supported.

### 3.2 Detect workspace

An initialized workspace is a `.acm/` directory at the **repository root** (not inside a subdirectory). Most commands call Git discovery, then resolve `.acm` at the repo top-level.

If `.acm/` is missing, commands fail with a workspace-missing error (exit code **2**). **Do not run `acm init` unless the user explicitly asks.**

Sanity checks (read-only):

```bash
acm task list
acm repo status
```

If these succeed, the workspace is usable.

### 3.3 Learn exact syntax

```bash
acm --help
acm task --help
acm knowledge --help
acm context --help
acm repo --help
```

Re-run help after upgrading `acm` (e.g. Sprint 4 adds the `context` group).

### 3.4 JSON mode (optional)

For machine parsing, pass `--json` on the same command (e.g. `acm --json task list`). Errors emit JSON with a stable `code` when `--json` is set. See §11 for exit codes.

---

## 4. Understand the project and current task

### 4.1 List and select a task

```bash
acm task list
acm task list --status active
```

Inspect one task:

```bash
acm task show ACM-0001
```

Human output includes: `id`, `title`, `status`, `priority`, timestamps, `objective`, `scope`, `constraints`, `files`, `knowledge_refs`, `acceptance_criteria`, `latest_checkpoint`.

**Note:** New tasks created via CLI start with empty `scope`, `constraints`, and `acceptance_criteria`. There is **no CLI** to maintain those fields in v0.1—use `objective`, checkpoints, and user communication for acceptance tracking unless richer task YAML already exists from another tool.

### 4.2 Create a task (when authorized)

```bash
acm task new "Short title" \
  --objective "Measurable outcome" \
  --status active \
  --priority high \
  --file path/relative/to/repo.go
```

Rules:

- **Title** is the single positional argument (required).
- **Default status:** `draft`. **Allowed initial statuses:** `draft`, `planned`, `active`.
- **Default priority:** `medium`. Allowed: `low`, `medium`, `high`.
- **`--objective` is required** when initial status is `planned` or `active`.
- **`--file`** may be repeated; paths must be repository-relative.

IDs are allocated as `ACM-0001`, `ACM-0002`, …

Before creating a task: check `acm task list` for overlap; avoid duplicate tasks for the same work.

### 4.3 Task lifecycle (status transitions)

Valid transitions (from implementation):

| From | To |
|------|-----|
| `draft` | `planned`, `active`, `archived` |
| `planned` | `draft`, `active`, `archived` |
| `active` | `blocked`, `completed`, `archived` |
| `blocked` | `active`, `archived` |
| `completed` | `archived` |
| `archived` | *(none)* |

Update status:

```bash
acm task update ACM-0001 --status blocked
```

`acm task close ACM-0001` is equivalent to archiving via status `archived` (it refuses if already archived).

Do not bump status to `completed` or `archived` to “look done” without meeting the user’s intent.

### 4.4 Other task updates

```bash
acm task update ACM-0001 --title "Revised title"
acm task update ACM-0001 --objective "Updated objective"
acm task update ACM-0001 --priority low
acm task update ACM-0001 --file pkg/a.go --file pkg/b.go
acm task update ACM-0001 --clear-files
```

At least one flag is required. `--clear-files` cannot be combined with `--file`.

---

## 5. Prepare context

### 5.1 Repository inspection (CLI)

**Live Git state** (trust this over old checkpoints when resuming):

```bash
acm repo status
```

**Persisted file tree** (from last index build—not live Git):

```bash
acm repo tree
```

**Rebuild index** after large tree changes or when tree seems wrong (mutates `.acm/repository/`):

```bash
acm repo scan
```

`repo tree` prints plain text only (no JSON schema in v0.1). Use it for orientation; use direct file reads and `repo status` for accuracy.

### 5.2 Task-associated files

Attach paths relevant to the task:

```bash
acm task update ACM-0001 --file internal/foo/bar.go
```

These paths feed **context selection** when a snapshot is built (see §5.3). They are also visible in `task show`.

### 5.3 Context snapshots (Sprint 4)

**Build (no CLI yet):** Snapshot assembly is implemented (`app.BuildContextSnapshot`) but **`acm context build` is not registered**. Agents cannot rebuild context from the CLI alone. Prepare with `task update --file …` and live repo reads; use an existing snapshot when present.

**Inspect manifest (read-only, does not write):**

```bash
acm context show ACM-0001
acm --json context show ACM-0001
```

Human `show` prints manifest metadata: `task_id`, `built_at`, Git `revision` / `branch` / `detached` / `dirty`, limits, `estimated_tokens: null`, plus `selected_files`, `knowledge_refs`, and `excluded_files` (with reasons). It does **not** print inlined file bodies.

JSON `show` returns `{ "ok": true, "manifest": … }` with the full `context-manifest.json` document.

**Export inlined bundle (read-only):**

```bash
acm context export ACM-0001
```

Writes existing `context.md` bytes to stdout (Markdown with inlined sources). No extra output path; does not modify `.acm/context/`.

**Missing snapshot:** `context show` and `context export` return `not_found` (exit **2**) when `.acm/context/<TASK-ID>/` does not exist. They do not create a directory or snapshot.

**On-disk layout** (same artifacts `show` / `export` read):

| File | Purpose |
|------|---------|
| `context-manifest.json` | Selection, exclusions, limits, `built_at`, Git revision/branch/dirty at build |
| `context.md` | Human-readable bundle with inlined file bodies (`export` prints this) |
| `selected-files.txt` | Newline-separated paths included |

Agents may still read these files directly if CLI is unavailable; prefer CLI so validation runs before display.

**Stale context:** Compare manifest Git fields from `context show` with `acm repo status`. If they differ, prefer live repo reads. `context.md` includes a fixed notice when the tree was dirty at build time.

**Checkpoint link:** Checkpoints may record `context_manifest: .acm/context/<TASK-ID>/context-manifest.json` when that file existed at checkpoint time; otherwise `null`.

### 5.4 Context selection semantics (when snapshots are built)

Selection merges, in order: **manual** paths, **task** `files`, optional **path** queries, optional **keyword** queries—then deduplicates.

**Explicit (manual) selection:** Missing, symlink, or invalid paths **fail the build** (no partial snapshot publish on that failure).

**Implicit (task / path / keyword):** Inaccessible paths are **omitted** and listed in `excluded_files` with reasons such as `inaccessible`, `excluded`, `symlink`, `secret`, `over_file_limit`, `over_byte_limit`, `not_regular`.

Default limits (from workspace config): **40 files**, **500000** bytes total—configurable in `.acm/config.yaml` (do not change without authorization).

### 5.5 Knowledge search (lessons only)

```bash
acm knowledge search "authentication middleware"
```

Search is case-insensitive substring match over **lesson** title, summary, tags, and body. It does **not** search skills or decisions.

For `SKL-*` or `DEC-*` items, use IDs returned from `knowledge add` or read `.acm/knowledge/skills/` and `.acm/knowledge/decisions/` directly.

---

## 6. Implement

1. Confirm task scope via `acm task show` or `acm task resume` (if resuming).
2. Align with live repo: `acm repo status`; inspect diffs and files with normal editor tools.
3. Search lessons before rediscovering prior art: `acm knowledge search "…"`.
4. Stay within task scope; keep unrelated user edits intact.
5. Use `acm task update` for status (`blocked` when stuck) and file associations as the codebase focus shifts.

ACM does not run builds or tests for you.

---

## 7. Verify

1. Run the tests or checks the user cares about; capture **exact commands and outcomes**.
2. Distinguish **reported** vs **verified** in checkpoints (see §8).
3. Do not mark acceptance criteria in task YAML via CLI—they are display-only unless maintained outside this CLI.

---

## 8. Preserve progress (checkpoints)

### 8.1 When to checkpoint

Checkpoint when ending a meaningful stretch of work, switching tasks, or handing off—**not** after every file touch.

**Required flag:** `--next` (non-empty).

```bash
acm task checkpoint ACM-0001 \
  --next "Wire OAuth callback tests and update task status" \
  --remaining-work "Callback handler lacks error paths" \
  --implementation-state "Added route skeleton only" \
  --known-issues "Flaky test in pkg/auth on CI" \
  --blockers "Need client id from user" \
  --files-modified internal/auth/oauth.go \
  --tests-executed "go test ./internal/auth/..." \
  --test-results "all pass" \
  --reported-completed "OAuth route registered" \
  --verified-completed "go test ./internal/auth/... pass" \
  --reported-tests "unit tests green" \
  --verified-tests "go test ./internal/auth/... pass"
```

Repeatable array flags: `--files-modified`, `--tests-executed`, `--test-results`, `--reported-completed`, `--reported-tests`, `--verified-completed`, `--verified-tests`.

Body sections (`--remaining-work`, `--implementation-state`, etc.) are free text. Only `--next` is validated as required.

### 8.2 Checkpoint behavior

- Writes `checkpoint.md` in the task directory; previous `checkpoint.md` is archived under `checkpoints/<timestamp>.md`.
- Embeds **current** Git revision, branch, detached/dirty flags.
- Records `task_status` at write time.

### 8.3 Resume safely

```bash
acm task resume ACM-0001
```

Resume output includes the full task plus the latest checkpoint. Watch for:

- **`checkpoint: missing`** — no checkpoint yet; rely on task fields and repo state.
- **`status_mismatch`** — task status changed after the checkpoint; **trust current task status** and treat checkpoint `task_status` as historical.

Then:

1. Run `acm repo status` and reconcile with checkpoint `git.*` fields.
2. Run `acm context show TASK-ID` (or `context export`) if a snapshot exists; reconcile with `repo status` (§5.3).
3. Execute the checkpoint `next_action` or agree a new one with the user.

---

## 9. Handoff or complete

### 9.1 Complete vs archive

- Set status to `completed` when work meets the agreed objective:

  ```bash
  acm task update ACM-0001 --status completed
  ```

- **Archive** when the task should leave the active set (including cancelled work):

  ```bash
  acm task close ACM-0001
  ```

Closing only sets `archived`; it does not run tests or prove correctness.

### 9.2 Final checkpoint

Optional but useful before archive: one honest checkpoint with verified test lines populated.

---

## 10. Knowledge and feedback

### 10.1 Create knowledge

```bash
acm knowledge add \
  --title "Lesson title" \
  --summary "One-line takeaway" \
  --type lesson \
  --tag auth --tag testing \
  --evidence docs/DECISIONS.md \
  --content-file /path/to/body.md
```

- **`--title` and `--summary` are required.**
- **`--type`:** `lesson` (default), `skill`, or `decision` (help text may say “lessons only”; all three work in the current implementation).
- New items start as **`candidate`**.
- `--content-file` is optional; body may be empty.

IDs: `LSN-0001`, `SKL-0001`, `DEC-0001`, …

### 10.2 Verify and deprecate

```bash
acm knowledge verify LSN-0001
acm knowledge deprecate LSN-0001 --reason "Superseded by DEC-0002"
```

Knowledge status transitions:

| From | To |
|------|-----|
| `candidate` | `verified`, `deprecated` |
| `verified` | `deprecated` |
| `deprecated` | *(none)* |

**Verify** may require at least one `--evidence` on the item when `knowledge.require_evidence_for_verification` is true (default **true** in default config). Add evidence at create time or do not verify until evidence exists.

Deprecated items remain in search results with status `deprecated`.

### 10.3 Dogfooding feedback (for humans maintaining ACM)

When friction appears, record **concrete** notes for the user or maintainers:

- Commands or flags you expected but `acm --help` did not show  
- Confusing errors, lock contention, or stderr history warnings  
- Missing CLI for `context build`, knowledge show, handoff, or rich task fields  
- Places ACM overhead exceeded value  

Classify issues as: documentation, CLI usability, or missing product capability—before proposing code changes.

### 10.4 Session summary to the user

After substantial work, report briefly:

**Task** (id, title, status) · **Repo** (branch, dirty) · **Implemented** · **Tests run and results** · **Checkpoint** (yes/no) · **Knowledge** (ids created) · **Remaining** · **Next action**

---

## 11. Error handling and integrity

| Situation | Agent behavior |
|-----------|----------------|
| Command failed | Read message and exit code; do not blindly retry mutations. |
| Exit **1** | Usage, validation, invalid transition, schema issues—fix arguments. |
| Exit **2** | Missing workspace, not found, lock busy—often environmental. |
| Exit **3** | Path/symlink/secret safety—fix paths or selections. |
| Exit **4** | Internal error—report; do not corrupt data retrying. |
| Lock busy | Another ACM process holds `.acm/.lock`; wait or ask user. **Never delete `.lock`.** |
| Invalid transition | Use §4.3 / §10.2 tables; do not patch YAML by hand. |
| Workspace incompatible | Layout or schema mismatch—escalate; do not guess repairs. |

Mutation commands may print to stderr: `history is enabled but no event was written`. That is expected in v0.1; stdout JSON/human output is still authoritative for the operation result.

---

## 12. Quick command reference

```bash
# Workspace (read-only discovery)
acm version
acm task list [--status STATUS]
acm task show TASK-ID
acm task resume TASK-ID
acm repo status
acm repo tree
acm knowledge search QUERY
acm context show TASK-ID
acm context export TASK-ID

# Tasks (mutating — use when authorized)
acm task new TITLE [--objective ...] [--status draft|planned|active] [--priority low|medium|high] [--file PATH...]
acm task update TASK-ID [--title ...] [--objective ...] [--status ...] [--priority ...] [--file PATH... | --clear-files]
acm task checkpoint TASK-ID --next "..." [optional sections and arrays]
acm task update TASK-ID --status completed
acm task close TASK-ID

# Knowledge (mutating)
acm knowledge add --title T --summary S [--type lesson|skill|decision] [--tag ...] [--evidence ...] [--content-file PATH]
acm knowledge verify KNOWLEDGE-ID
acm knowledge deprecate KNOWLEDGE-ID --reason "..."

# Repository index (mutating)
acm repo scan

# Init — user authorization only
acm init [--repo PATH] [--update-gitignore]
```

---

## 13. Workflow map

```text
1. Bootstrap     → which acm, version, git root, .acm present, --help
2. Understand    → task list/show or resume; repo status
3. Prepare       → knowledge search; task --file; context show/export if snapshot exists
4. Implement     → edit repo; task update status/files as needed
5. Verify        → run tests; record verified vs reported
6. Preserve      → task checkpoint when handing off
7. Complete      → status completed or task close
8. Knowledge     → knowledge add; verify when evidenced and stable
```

**Remember:** The implementation and installed `acm` binary are the authority. Refresh this guide when dogfooding reveals drift.
