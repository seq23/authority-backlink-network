# LinkedIn and X Credential Automation Decision

## Finding

ChatGPT/OpenAI app connections can authorize ChatGPT to use an app's exposed actions. They do not provide the repository with raw OAuth access tokens, API keys, client secrets, or token secrets, and the connected-app permission does not expand the underlying access grant.

Therefore the Authority Network cannot safely extract LinkedIn or X credentials from the user's OpenAI connection and copy them into GitHub secrets.

## Supported architecture

1. Create/approve the LinkedIn developer application and X developer project with posting permissions.
2. Complete each provider's OAuth flow once through a controlled credential broker or operator setup.
3. Store the resulting credentials directly in GitHub Actions secrets or a server-side secret vault.
4. The repo reads credentials only at workflow runtime.
5. Add a token-health preflight and expiry/rotation alerts.
6. Never write raw credentials to repo files, reports, ChatGPT messages, or generated artifacts.

## Where credentials live ("the vault")

There is no separate vault repository or directory in this portfolio, and inventing one would
add a second place for a credential to rot. The vault for this repository is **GitHub Actions
repository secrets** — `Settings → Secrets and variables → Actions → Secrets` — which is
option 3 above and the only store any workflow here reads from. This section is the registry:
a secret that is not named below is not wired to anything.

## Current required secret names

- `LINKEDIN_ACCESS_TOKEN`
- `LINKEDIN_AUTHOR_URN`
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`
- `BUFFER_ACCESS_TOKEN` — **the one that is actually in use for X.** X's own API is
  pay-per-use and unfunded, so the six names above post nothing today; this token delivers
  the same X posts through Buffer's free queue instead. Read only at workflow runtime by
  `scripts/lib/buffer_route.py`, sent as `Authorization: Bearer` to
  `https://api.buffer.com/graphql`, and passed through a redactor before any response can
  reach a log or a report. Registered here on 2026-08-29; the value has never been written
  to a repository file. `scripts/validators/validate_buffer_route.py` blocks the release if
  it ever appears in a log, a report, the drafts sheet or a commit.

## Automation options

### GitHub secret bootstrap

A local/operator bootstrap can accept secrets from environment variables and set encrypted GitHub repository secrets. This removes manual web-form entry but still requires the real provider credentials to exist outside ChatGPT.

### OAuth broker

A small Cloudflare Worker can run provider OAuth, store refreshable credentials in encrypted server-side storage, and expose only posting actions to GitHub Actions. This is the best long-term option if provider tokens expire or rotate.

### Custom OpenAI/MCP app

A custom app could expose a `post_to_linkedin` or `post_to_x` action from the same broker. It would allow ChatGPT to request posting but still would not reveal provider secrets to the model or repository.

## Not possible

- extracting raw provider tokens from existing OpenAI app connections;
- converting a normal LinkedIn login into LinkedIn API posting credentials automatically;
- bypassing LinkedIn/X developer-app approval or provider permissions;
- committing secrets into the ZIP.
