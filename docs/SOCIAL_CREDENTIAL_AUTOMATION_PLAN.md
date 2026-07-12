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

## Current required secret names

- `LINKEDIN_ACCESS_TOKEN`
- `LINKEDIN_AUTHOR_URN`
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

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
