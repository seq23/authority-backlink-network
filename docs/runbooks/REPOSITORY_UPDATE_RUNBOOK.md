# Authority Network Repository Update Runbook

## Repo identity

- Repo name: `authority-network`
- Expected branch: `main`
- GitHub remote slug: `authority-network`
- Update mode: `snapshot`
- Deploy model: Cloudflare Pages Git integration. The updater does not deploy directly to Cloudflare.

## Updater

Use the verified local updater discovered by the rapid diagnostic command:

`$HOME/repo-tools/active/update_repo_from_zip_generic_v3_1.sh`

Do not guess an alternate path. Run the diagnostic command from the Master Operating Contract if the path changes.

## Required baseline ZIP naming

`authority-network-main_BASELINE_MM-DD-YY_<sha>.zip`

## Exact updater command template

```bash
bash "$HOME/repo-tools/active/update_repo_from_zip_generic_v3_1.sh" "$HOME/Downloads/authority-network-main_BASELINE_MM-DD-YY_SHA.zip" "$HOME/Documents/GitHub/authority-network" snapshot authority-network
```

Replace only the ZIP filename with the downloaded baseline ZIP name.

## What the updater does

1. Requires a clean Git working tree.
2. Verifies repo basename, remote slug, and branch.
3. Tests ZIP integrity and archive safety.
4. Creates a local pre-update safety tag.
5. Runs rsync dry-run and deletion safeguard.
6. Applies the snapshot while excluding runtime/local files.
7. Installs dependencies when a lockfile exists.
8. Runs `npm run release:prepush:local` from `_repo_update_contract.json`.
9. Commits and pushes only if validation passes.
10. Creates and pushes safety tags.

## Expected success signals

- `Updater version:` printed
- `Detected ZIP root:` printed
- `Created local safety tag:` printed
- `Release execution environment: local` printed
- `DONE` printed
- `Evidence:` path printed

## Failure handling

If validation fails, do not manually commit or push. Repair the source baseline ZIP, redeliver a full replacement baseline, and rerun the updater from the start.
