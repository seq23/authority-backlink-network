# Moving the three publication domains to a separate Cloudflare account

**Status: PLAN ONLY. Nothing here has been executed.** No Cloudflare resource
was created, moved or deleted, and the existing API token was not touched or
regenerated — other repositories depend on it.

**Scope:** `founderoperatorlibrary.com`, `memphisvendorlibrary.com`,
`professionalresourcelibrary.com`.

All quoted text is verbatim from `developers.cloudflare.com`, checked
2026-08-27. Everything I could not verify is marked. `community.cloudflare.com`
returned 403 to every request, so nothing here rests on forum posts.

---

## 0. Read this before anything else

**Two findings change the shape of this job.**

**Finding 1 — the obvious procedure is the wrong one.** The instinctive approach
is "delete the zone from the old account, add it to the new one." Cloudflare
documents the opposite, and the documented flow is much safer: **add the domain
to the new account first, then cut the nameservers, then let the old zone age
out by itself.** Delete-first throws away both the overlap window and the
rollback target. It is not Enterprise-gated.

**Finding 2 — Pages and DNS cannot be split, for apex domains.** Verbatim:

> "To deploy your Pages project to a custom apex domain, that custom domain must
> be a zone on the Cloudflare account you have created your Pages project on."
> — [pages/configuration/custom-domains](https://developers.cloudflare.com/pages/configuration/custom-domains/)

A Pages project in the new account **cannot** serve an apex domain whose zone
lives in the old one. So each domain moves as a single atomic unit: zone and
Pages project together, or not at all. There is no gradual migration.

**Honest recommendation before the mechanics:** weigh whether to do this at all.
See §9 — separate accounts buy real operational separation but almost no
concealment, and concealment is not the goal this work is pursuing anyway.

---

## 1. What actually happens, and what it costs

### DNS resolution barely breaks. Proxying does.

Cloudflare answers DNS on both the old and the new nameservers during the
overlap — that is the design.

| Zone state | DNS behaviour (verbatim) |
|---|---|
| **Pending** (new account) | "Cloudflare responds to DNS queries for pending zones on the assigned Cloudflare nameserver IPs, but your zone is still not active" |
| **Deleted** (old account) | "Cloudflare still responds to DNS queries for deleted zones on the assigned Cloudflare nameserver IPs (for non-deleted DNS records)" |
| **Purged** | "Cloudflare does not respond to DNS queries for purged zones and, unlike deleted zones, this status cannot be reverted." |

**The real outage is the Pending window**, and it is worse than a DNS blip:

> "While the domain in the new account is **Pending**, it cannot proxy traffic
> through Cloudflare and the origin IP addresses will be returned until the
> domain is marked as **Active**."

During that window: no WAF, no cache, no Cloudflare rules, **origin IPs publicly
exposed**, and no Cloudflare-terminated TLS. For a Pages-hosted site fronted by
Cloudflare, that means **HTTPS genuinely fails**, not merely degrades.

### The honest downtime estimate

**Budget up to ~48 hours of degraded or unproxied service. Most of it will
probably resolve within an hour, but do not promise that.**

The window is: registrar NS TTL at the TLD (commonly 24–48 h) + Cloudflare
activation re-check + Universal SSL issuance, which is **additive** because the
certificate clock starts at *activation*:

> "your domain should **automatically** receive its Universal SSL certificate
> within **15 minutes to 24 hours** of domain activation"

⚠️ **Could not verify** any Cloudflare figure for NS delegation propagation in
this specific flow. Cloudflare's "5–15 minutes" line refers to records *inside*
a zone, not a registrar delegation change — **do not cite it as the NS window.**

### Certificates

- "SSL/TLS certificates associated with your previous Cloudflare account will not
  be transferred to your new account."
- Cloudflare documents three ways to shrink the HTTPS gap, all verbatim:
  1. "Order an advanced certificate before proxying traffic to Cloudflare."
  2. "Upload a custom certificate prior to migrating and then delete the
     certificate after your Universal certificate is active."
  3. "Keep DNS records unproxied until your certificate is active."
- ⚠️ **CAA records can block re-issuance entirely.** Check for CAA on all three
  domains before cutover: "This can cause issues when adding a custom domain to
  your Pages project if you have CAA records that do not allow Cloudflare to
  issue a certificate for your custom domain."

### Nameservers will probably change

> "Cloudflare automatically assigns nameservers to a domain and these assignments
> cannot be changed."

and re-adding makes a change *more* likely: "The likelihood of your new zone
being assigned different nameserver names than your previously existing zones is
higher."

**Assume the pair changes.** "If their names are not **copied exactly**, your DNS
will not resolve correctly."

---

## 2. What breaks — the full list

### Account-scoped: does not move, must be rebuilt in the new account

| Thing | Applies here? |
|---|---|
| **Pages projects** | **Yes — all three.** "limit of 100 projects per account" |
| **API tokens** | **Yes.** Permissions are "segmented into three categories based on resource: Zone permissions, Account permissions, User permissions" |
| **Account ID** | **Yes — it changes by definition** |
| **Email Routing destination addresses** | **Yes.** "Destination addresses are shared at the account level" — a new account shares nothing |
| Bulk Redirects | Not currently used |
| Workers, KV, R2, D1 | Not used by this repo. Note their **data** has no documented cross-account copy — export/import if any exist |
| Zero Trust / Access | ⚠️ team name is org-level; whether apps and policies are account-scoped is **not documented** — treat as unverified |

### Zone-scoped: dies with the old zone

Page Rules, Cache Rules, WAF custom rules, Redirect Rules, all zone settings, and
all certificates. **Zone IDs also change**, because re-adding creates a new zone
object.

### Every automation that stops working

The token and account ID are the blast radius. Before touching anything, inventory:

- `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` — GitHub Actions secrets for
  this repo (named in `README.md`) **and in every other repo in the portfolio
  that deploys to Cloudflare.** This is the item most likely to be forgotten.
- Cloudflare Pages Git integration for all three projects — must be reconnected,
  and reconnection re-authorises the GitHub app against the new account.
- Any `wrangler.toml` / `wrangler.jsonc` `account_id`.
- Any bookmarked `dash.cloudflare.com/<account_id>/...` URL.
- Anything reading Cloudflare analytics via API.

> **Do not roll or regenerate the existing token as part of this.** It is shared
> with other repositories. Issue a *new* token in the new account and retire the
> old one only after every consumer has been migrated and verified.

### Email Routing — plan this deliberately

The setup in
[`EDITORIAL-INDEPENDENCE.md`](EDITORIAL-INDEPENDENCE.md#2-the-contact-surface)
does not survive a move on its own.

- Hard prerequisite: **"You must be using Cloudflare DNS to use Email Service."**
  Email Routing is dead for any window in which the zone is not active.
- Destination addresses are account-level, so **every destination must be re-added
  and re-verified in the new account** — each needs a click in a verification
  email. Rules pointing at unverified destinations stay disabled.
- Routing rules are per-domain and must be recreated.
- Onboarding re-adds MX, SPF and DKIM records.

**Do this before cutover, not after**, so rules go live the instant the zone
activates.

⚠️ **Could not verify** what happens to mail in flight during cutover — no
Cloudflare doc addresses zone moves. In practice a sending MTA queues and retries
for days when MX is unresolvable, but that is ordinary SMTP behaviour, not a
Cloudflare guarantee, and some senders bounce sooner.

---

## 3. The runbook

**Test the entire sequence on the least valuable domain first.** That is
`founderoperatorlibrary.com` on current traffic. It resolves the two open
unknowns (§5) at low cost. Do not batch all three.

### Phase 0 — before touching anything

1. **Record the current nameserver pair for each zone, exactly.** This is the
   only rollback target and it is unrecoverable once the old zone purges.
2. Export DNS records for each zone (Cloudflare's BIND export). Cloudflare warns
   that skipping this means "Cloudflare will import your proxied DNS records,
   which might cause your domain to experience a 1000 error."
3. Screenshot or export every zone setting you rely on: Page Rules, Cache Rules,
   Redirect Rules, WAF custom rules, SSL/TLS mode.
4. Record each Pages project's build config, environment variables and secrets
   **from your own source of truth** — secrets are write-only and cannot be read
   back out of the old project.
5. Check for **CAA records** on all three domains.
6. Check whether any domain is registered *at* Cloudflare Registrar. If so, use
   the self-service registrar inter-account transfer instead of this flow — but
   note "WHOIS contact information will be moved as is. **No other configuration
   will be moved.**" It also requires DNSSEC off, the domain registered more than
   10 days, action within 5 days, and it transfer-locks for 30 days afterwards.
7. **Turn DNSSEC off** on the domain being moved. Required, and it needs its own
   propagation time — do it well ahead.
8. Cancel any add-ons or paid subscriptions on the zone. Note: "Removing your
   domain cancels all active subscriptions on that domain, which will not be
   refunded per our billing policy."

### Phase 1 — stage the new account (no user-visible change)

9. Create the new Cloudflare account. **The owner must do this** — it requires a
   signup, a password and accepting terms. Neither I nor any agent can.
10. Add the domain to the new account "as if you were adding it for the first
    time." It will sit **Pending**. ⚠️ See §5 unknown #1 — this is the step where
    an "already hosting under a different account" error may appear.
11. Import the DNS records exported in step 2. Verify record-by-record.
12. Recreate the Pages project in the new account and connect it to this GitHub
    repo. Re-enter build config, environment variables and secrets.
13. Confirm the new project builds and serves correctly on its `*.pages.dev`
    URL. **This is the real go/no-go gate.** If the site is not right on
    `*.pages.dev`, stop — nothing after this point is reversible cheaply.
14. Pre-stage Email Routing: add and **verify** the destination addresses, and
    create the routing rules.
15. Consider a mitigation for the HTTPS gap (§1) — the simplest is to keep
    records unproxied until the certificate is active.

### Phase 2 — cutover (the visible window opens here)

16. At the registrar, replace the nameservers with the new pair. "Remove your
    existing authoritative nameservers. Add the nameservers provided by
    Cloudflare."
17. In the new account: **Overview → Re-check now.**
18. Wait for **Active**. The Universal SSL clock starts here (15 min – 24 h).
19. Attach the apex custom domain to the new Pages project. This only works now
    that the zone is in the same account (§0, Finding 2).
20. Re-proxy any records left unproxied in step 15, once the certificate is
    active.

### Phase 3 — verify before trusting

21. HTTPS resolves with a valid certificate on the apex and `www`.
22. All three sites serve, and `/404` returns an actual 404.
23. Email: send to `editor@`, `corrections@` and `pitch@` and confirm delivery.
24. Deploy from GitHub end to end with the **new** token and account ID.
25. `npm run validate:release` still passes.
26. Confirm the old zone shows **Moved Away** / **Deleted**, not Purged.

### Phase 4 — let it age out

27. Do nothing to the old zone. "After seven days in **Moved Away** status, the
    domain will be marked as **Deleted**. After seven days in the **Deleted**
    status, the domain will be permanently removed."
28. **Do not let it purge until the new setup has been verified for several
    days.** Purge is irreversible.
29. Only after everything is verified: retire the old API token, and only once no
    other repository still uses it.

---

## 4. Rollback

**There is a real rollback corridor of roughly 14 days** — 7 days in Deleted
before purge, following 7 in Moved Away. Purged zones "cannot be reverted",
explicitly contrasted with deleted zones ("unlike deleted zones").

**To roll back:** point the registrar's nameservers back at the *original* pair
recorded in Phase 0 step 1. The old zone answers DNS immediately once delegation
returns, because Cloudflare still serves deleted zones on their assigned
nameserver IPs.

**Rollback is not instant** — it costs the same NS propagation as the forward
move. And it is **lossy**: subscriptions cancelled on removal "will not be
refunded", and "If you add this domain back to Cloudflare later, you will need to
re-purchase all subscriptions."

**The rollback target is the one thing you cannot recover from the dashboard
after purge. Write the nameserver pair down somewhere outside Cloudflare.**

---

## 5. Open unknowns — resolve these on the test domain

1. **What exactly happens when you add a domain to account B while it is Active
   in account A.** Cloudflare's move-domain page names the error string
   `Cloudflare is already hosting under a different account` as a *reason people
   need to move*, but never says at which step it fires. The add-site docs never
   mention account conflicts. **This is the single biggest unknown in the plan.**
2. **Whether a Pages project in account B accepts a *subdomain* whose parent zone
   is Active in account A.** Apex is documented as impossible; subdomains are
   documented as not needing to be a Cloudflare zone at all, but the docs do not
   address "a zone in someone else's account."
3. **Whether Pages projects can be moved between accounts.** ⚠️ **No Cloudflare
   doc says they can, and none says they cannot.** Recreation is the safe
   planning assumption — but do not write "Cloudflare documents that Pages
   projects cannot be moved", because that sentence is unverified.
4. **Web Analytics scope.** Not documented as account- or zone-scoped. Assume the
   site token changes and history does not follow.

---

## 6. Cost

$0 in Cloudflare fees — the Free plan allows multiple accounts, and Pages and
Email Routing are free at this scale. The cost is **owner time (3–5 hours per
domain, done carefully) and the risk window in §1.**

---

## 7. Should this be done at all?

The honest answer is: **probably not yet, and not for the reason it is usually
considered.**

**What separate accounts genuinely buy:** clean billing separation, a blast
radius that stops at one account, credentials that can be handed to someone else
without granting access to the commercial properties, and a tidy asset boundary
if the publications are ever sold or moved into a separate entity. Those are real
and they are the good reasons.

**What they do not buy: concealment.** Separate accounts do not meaningfully hide
common ownership. What remains visible regardless:

- shared page templates and build configuration across all three sites,
- exclusive cross-linking into a single portfolio,
- correlated publishing cadence from one repository and one workflow,
- whois, and the same GitHub organisation deploying all three,
- and the affiliation disclosures on every page, which say so outright.

Anyone motivated to connect them will do it in minutes. So if the goal is to look
independent, this migration spends 10–15 hours and a real outage window to buy
almost nothing.

**The durable version of independence is the one the rest of this branch built:**
genuinely distinct editorial identities, a published masthead naming who is
responsible, real editorial standards, a working corrections route, and
affiliation disclosed as an asset rather than hidden. That holds up under
scrutiny. Infrastructure separation does not, and it fails at exactly the moment
someone is looking hard enough for it to matter.

**Suggested decision:** defer. Revisit if and when there is a separate legal
entity to hold the properties (see
[`EDITORIAL-INDEPENDENCE.md` §7](EDITORIAL-INDEPENDENCE.md#7-a-separate-publishing-entity)),
someone other than the owner needs Cloudflare access, or the publications are
being prepared for sale. Those are the situations where the operational benefits
justify the risk window. "Looking less connected" is not.
