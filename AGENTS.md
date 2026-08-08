# Repo Agent Bootstrap

This repository is governed by the user's local Repo Operator system.

## Source of authority
1. Read repo-local authority first (`AGENTS.md`, `REPO_IDENTITY.md`, `*AUTHORITY*.md`, `*GOVERNANCE*.md`, `*RUNBOOK*.md`, `_repo_update_contract.json`, `_repo_validation_matrix.json`, `_repo_lifecycle_profile.json`).
2. Repo-local authority outranks global instructions where its hierarchy says so.
3. Global Repo Work OS and active tools live under `~/repo-tools/reference-authorities/repo-work-os` and `~/repo-tools/manifests/ACTIVE_SCRIPTS.md`.
4. Hallmark is the existing repo tool/authority under `~/repo-tools/reference-authorities/hallmark`; use the active Hallmark workflow for substantial architecture or production-readiness review. Do not recreate it.

## Terminal entry points
```bash
~/repo-tools/agent/repo-work <repo>
~/repo-tools/agent/repo-work --help
~/repo-tools/agent/repo-status
```
Full unattended lifecycle:
```bash
~/repo-tools/agent/repo-supervisor --engine <codex|claude|antigravity> --repo <repo-name> --worktree <exact-worktree-path> --task-file <task-file>
```
Parallel bake-off:
```bash
~/repo-tools/agent/repo-bakeoff --repo-path <canonical-repo-path> --baseline <SHA> --slug <task-slug> --task-file <task-file> --engines codex,claude,antigravity
```

## Operating law
- Lock exact repo, worktree, branch, baseline SHA, and remote before mutation.
- Unattended work runs only on isolated `work/*` branches/worktrees.
- Never substitute another repo or write to another canonical repo.
- Use a full-baseline ZIP as the governed handoff artifact when required.
- Local updater validation and exact-SHA GitHub checks must pass before merge eligibility.
- RED or UNPROVEN remains merge-blocked; merge to main/default is human-authorized only.
- Provider quota/rate-limit is BLOCKED/UNSCORED, not a model-quality failure.
- For material UI/UX/design-system work, use the Claude Design routing layer when it materially improves the result; not for backend-only work.
- Use existing tools and repo authority rather than inventing duplicate systems.
