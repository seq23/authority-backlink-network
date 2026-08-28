# Editorial independence: what was built, and what the owner has to do

Companion to [`EXTERNAL-AUTHORITY-PLAN.md`](EXTERNAL-AUTHORITY-PLAN.md), which
is the plan for earning citations. This document covers the governance and
identity work that shipped, and the steps only the owner can perform.

**The line this work holds.** `README.md` forbids "fake rankings, fake reviews,
fake independence, comment spam, PBNs, or doorway pages." Nothing here invents a
person. There is no fictitious editor, no persona, no fabricated byline,
credential, headshot, quote or testimonial — and no invented corporate paperwork
either: no registration number, incorporation date, address, phone number or
award appears anywhere, because none was supplied.

**The byline is an organisation, and it is per publication.** Each publication is
written and edited by its own editorial company, named after the publication:

| Publication | Byline |
|---|---|
| Founder Operator Library | Founder Operator Library Editorial Desk |
| Memphis Vendor Library | Memphis Vendor Library Editorial Desk |
| Professional Resource Library | Professional Resource Library Editorial Desk |

Each is a subsidiary of Spry Labs. Those two statements — a per-publication
editorial company, and the Spry Labs parent — are the *only* corporate facts
asserted on these sites. Nothing else about the entities is claimed.

This replaces a shared personal byline. One person's name appeared 647 times
across 607 pages spanning all three publications, which was the weakest
ownership signal in the network: three genuinely independent publications do not
share a sole author. Worse, it disagreed with the machine-readable metadata —
552 pages carried `"author": {"@type": "Organization"}` in JSON-LD while the
visible attribution named a person. Both now come from one expression,
`scripts/byline.py: entity_for()`, so they cannot disagree again.

No `Person` node is emitted anywhere in the build, and no page names a member of
staff. Accountability sits with the editorial company, reachable at the
editorial and corrections addresses in every footer.

Independence here does not mean pretending the group is unrelated to itself. The
mastheads state that the three editorial companies are commonly owned, and that
they are commonly owned with several of the projects the publications cite. It
means the publications have their own identity, their own contact surface,
published standards, a working corrections route, and disclosed conflicts — the
things that make a property answerable rather than anonymous.

---

## 1. Three distinct visual identities

All three sites previously served a **byte-identical** `styles.css`. They now
share component class names and design-token names and share no values, so the
same page rendered under each reads as a different publication.

| | Founder Operator Library | Memphis Vendor Library | Professional Resource Library |
|---|---|---|---|
| **Concept** | the operator's manual | the city magazine | the reference work |
| **Type** | grotesque sans; monospace metadata | old-style serif headlines; humanist sans body | tight sans headings; **serif body for reading** |
| **Palette** | ink `#0f1720`, signal blue `#1d4ed8` | cream `#fdfaf4`, clay `#a33f24`, river `#2c6675` | white, navy `#1c3f6e` |
| **Geometry** | 3px radius, left rules | 14px radius, soft shadows, double rules | **0 radius, no shadows** — strict rectangles |
| **Masthead** | dark reversed bar, bracket wordmark | centred italic serif over a double rule | light bar under a heavy navy rule |
| **Favicon** | blue brackets on ink, rounded square | clay italic *M* in a circle | navy bar + rules, square |

The restraint on Professional Resource Library is deliberate and is itself the
identity: a page about immigration paperwork should not be styled like a party
guide.

**No webfont is loaded.** The three voices come from system font stacks, colour
and geometry. A Google Fonts request would be a third-party dependency and a
privacy disclosure on publications that promise neither, and it would slow every
page for a cosmetic gain.

Both themes are handled — each stylesheet defines its full light palette on
`:root` and redefines only the tokens under `prefers-color-scheme: dark`.

One related fix: `generate_cluster_articles.py` was injecting an inline
`<style>` block with the *old shared* palette hardcoded into it
(`#e5dac8`, `#f2ece1`). Inline styles outrank the linked sheet, so 46 pages
would have dragged founder-publication colours onto the other two sites. That
block is gone; `.ct` tables now inherit each site's own tokens, and
`install_editorial_chrome.py` strips any copy that comes back.

---

## 2. The contact surface

`editor@`, `corrections@` and `pitch@` on each of the three domains, using
**free Cloudflare Email Routing**. Addresses are configured in
`data/editorial.json` (`contact_prefixes`) and rendered into the masthead,
corrections page, contributors page and the footer of every page.

> **Do this before anything in the authority plan.** A corrections address
> printed on 608 pages that bounces is worse than no address at all.

### 2.1 What is free and what is not — read this first

Verified against Cloudflare's docs on 2026-08-27. The docs moved: Email Routing
now lives under **Cloudflare Email Service**.

| | Free (Workers Free plan) |
|---|---|
| **Inbound** — receiving and forwarding | ✅ **Unlimited.** *"Email Routing is available on both the Workers Free and Workers Paid plans."* |
| Routing rules per domain | 200 |
| Verified destination addresses per account | 200 (shared account-wide) |
| Max inbound message size | 25 MiB |
| Catch-all | ✅ supported |
| **Outbound** — sending, including replies | ❌ **"Not available."** *"Sending to arbitrary recipients requires the Workers Paid plan."* |

**The catch, stated plainly:** Cloudflare Email Routing is inbound-only. It
forwards mail *to* you; it cannot send mail *as* you to a stranger. Cloudflare's
newer Email Sending product does have an SMTP endpoint
(`smtp.mx.cloudflare.net:465`), but outbound is **plan-gated off** on the free
tier — the only free sends are to addresses already verified in your own
account, which cannot reach a reporter or a reader.

So receiving is genuinely $0 and unlimited. **Replying as `editor@` is the part
that needs a decision.**

### 2.2 Steps — inbound (do this now, ~20 minutes for all three domains)

Repeat for each of `founderoperatorlibrary.com`, `memphisvendorlibrary.com`,
`professionalresourcelibrary.com`.

1. The domain must already use Cloudflare's nameservers. All three do.
2. Cloudflare dashboard → select the zone → **Compute (Workers) → Email Service
   → Email Routing** → **Get started / Onboard domain**.
3. Let Cloudflare add the DNS records itself ("Add records and onboard"). It
   creates:

   ```
   MX   @                            route1.mx.cloudflare.net
   MX   @                            route2.mx.cloudflare.net
   MX   @                            route3.mx.cloudflare.net
   TXT  @                            "v=spf1 include:_spf.mx.cloudflare.net ~all"
   TXT  cf2024-1._domainkey          "v=DKIM1; h=sha256; k=rsa; p=<key>"
   ```

   **MX priorities are assigned automatically by Cloudflare** — the docs give no
   numbers, so read them off your own DNS tab rather than typing values in.

4. **Destination addresses** → add the Gmail address you actually read. Cloudflare
   emails it a verification link. **Click it.** Until you do, every rule pointing
   at that address stays disabled: *"all routing rules are automatically disabled
   until the destination address is validated."*
5. **Routing Rules** → create three custom addresses per domain, each forwarding
   to that destination:
   - `editor@<domain>`
   - `corrections@<domain>`
   - `pitch@<domain>`
6. Optionally enable **catch-all** to the same destination, so a misspelled
   address still reaches you.
7. **DMARC.** Cloudflare does not add one. While these domains only *receive*:

   ```
   TXT  _dmarc    "v=DMARC1; p=reject; rua=mailto:<your address>"
   ```

   `p=reject` is safe for a non-sending domain because forwarding does not put
   your domain in the `From:` header — Cloudflare rewrites only the envelope
   sender. (This follows from RFC 7489 semantics; neither Cloudflare nor Google
   publishes an explicit "parked domain → p=reject" recipe, so treat it as
   standard practice rather than a vendor instruction.)
8. Test each of the nine addresses by emailing them from an outside account.

Two useful behaviours: subaddressing works (`editor+press@…` matches the
`editor@` rule), and if two rules share a pattern only the first one listed
processes mail.

### 2.3 Replying as `editor@` — and a deadline you need to know about

⚠️ **Google is removing "Send mail as" for third-party addresses in January
2027.** Verbatim from Google's support documentation:

> "**Important:** Starting January 2027, Gmail will no longer support the 'Send
> as' feature for third-party email addresses… This change does not affect
> Google Workspace aliases or other Gmail addresses you own."

Google's published timeline: Q3 2026 notification, Q3–Q4 2026 transition (new
configuration may already be restricted), **January 2027 removal**. Gmailify and
POP fetching for third-party accounts go at the same time.

That is roughly four months from today. It means **the $0 send-as route has a
stated expiry**, and a setup guide that omits this would be setting the owner up
to lose her editorial address mid-flight.

**Option A — do nothing about outbound (recommended to start).**
Receive at `editor@`, reply from `hello@westpeek.ventures` with a signature line
saying so. This is $0, permanent, and entirely honest — plenty of small
publications route mail this way. It costs a little polish and nothing else.

**Option B — SMTP2GO free + Gmail "Send mail as" (works now, expires Jan 2027).**
SMTP2GO's free tier is 1,000 emails/month, 200/day, and it is the only free relay
whose terms actually permit person-to-person mail: *"your recipient must be
either someone with whom you have a personal or professional relationship."*
Mailjet, Brevo and Resend all restrict their free tiers to professional/bulk or
opt-in-only use; ImprovMX's free tier cannot send at all; Postmark's free tier is
100/month.

Sequence matters: **set up Cloudflare routing first**, because SMTP2GO refuses
signups from public-domain addresses and you will need an address on your own
domain.

🚨 **The one thing that will break your mail:** Cloudflare has already put
`v=spf1 include:_spf.mx.cloudflare.net ~all` on your apex. Adding a relay's SPF
as a **second** TXT record silently breaks all authentication — RFC 7208 says
more than one SPF record produces `permerror`. You must **edit the existing
record**:

```
v=spf1 include:_spf.mx.cloudflare.net include:spf.smtp2go.com ~all
```

Add the relay's DKIM on its own selector, and leave Cloudflare's `cf2024-1`
selector alone. If you start sending, move DMARC from `p=reject` to `p=none`
first and tighten it once reports look clean.

**Option C — Zoho Mail free.** A real two-way mailbox, 5 users, 1 domain, free
"forever". The caveats are real: web-only access (no IMAP/POP), available *"only
in selected data centers"* with no published list, and **forwarding and routing
are paid-only**, so you cannot pipe it into Gmail. It is also mutually exclusive
with §2.2 — you cannot point apex MX at both Cloudflare and Zoho. Its free-tier
SMTP status could not be verified (Zoho's own docs contradict each other), so
test with a throwaway domain before committing.

**Recommendation:** do §2.2 now and run Option A. Revisit outbound only if
replying as `editor@` turns out to matter, and if it does, know that Option B
buys you until January 2027 and Option C is the only $0 route that survives it.

---

## 3. Published editorial policy

Twelve pages, four per publication, generated by
`scripts/build_editorial_pages.py` from `data/editorial.json`:

| Route | What it says |
|---|---|
| `/masthead` | Names the publication's own editorial company as publisher, and states the Spry Labs subsidiary relationship and the common ownership across the group. Records that no individual staff member is named. Lists every affiliated project in a table. States what the publication will not do. |
| `/editorial-standards` | Per-publication sourcing standard, the AI-use disclosure, conflict-of-interest statement, and what is never published. |
| `/corrections` | The corrections address, what qualifies, what does not, the five-step process, and the log. |
| `/contributors` | Byline policy, contributor requirements, and how to pitch. |

**The conflict-of-interest table is derived, not written.** It is built at build
time from `data/brands.json` → `approved_publications`, so it cannot drift away
from the affiliations the link registry actually permits. Add a brand to a
publication's lane and it appears on that masthead on the next build.

### The AI-use disclosure is the honest one

This is the part most likely to be softened later, so it is worth being explicit
about why it reads as it does. These publications generate most pages
automatically. Claiming every page is hand-written and hand-reviewed would be
false. The published text says:

> "Most pages on this site are drafted by an automated system from a structured
> brief, then checked by an automated editorial review before they publish. A
> person sets the briefs and the standards; a person does not read every page
> before it goes live."

and then states what the system does, and what no page contains — no invented
quotes, no generated statistics or prices, no automated output presented as
first-hand experience, and no reviews or rankings at all *"so none can be
fabricated."*

That is a stronger position than a vague "human oversight" claim, because it is
checkable. **If the production process changes, change this text.** It lives in
`data/editorial.json` under `ai_use`.

---

## 4. Disclosure as an asset

`scripts/install_editorial_chrome.py` puts a visible `.affiliate-disclosure`
block on every page that actually cites an affiliated destination — placed next
to the citation, not in the small print. It names the specific projects cited on
that specific page:

> **Why this page links where it does**
> This page cites **A Player Mode**, which is owned by the same person who
> publishes Founder Operator Library. That is a genuine conflict of interest, and
> it is why you are reading it here rather than discovering it somewhere else.
> The citation carries `rel="sponsored nofollow"`, so it sends no ranking signal
> to the destination. Nothing on this page is ranked, scored, or paid for, and no
> mention here can be bought. If the affiliated resource is not the right fit for
> you, the rest of the page still answers the question without it — that is the
> test every page here has to pass.

Every page also gets a governance footer with the masthead, standards,
corrections and contributors routes plus the editorial address, so the
corrections route is one click from anywhere on the site.

**Existing disclosures were not weakened.** The strings in
`data/publications.json` are untouched, all 571 affiliated links still carry
`rel="sponsored nofollow"`, and the "Affiliation disclosed" text that
`hostile_review.py` requires is still on every page.

---

## 5. The byline system — shipped empty

- `data/contributors.json` — the registry. **`contributors: []`.** Its header
  documents the schema and says, at length, not to populate it with anyone who
  has not actually agreed and actually written something.
- `/contributors` on each site — byline policy plus an honest empty state.
- Author pages and `Person` JSON-LD with `sameAs` — generated automatically the
  moment a real contributor is added.

### Adding a real contributor

⚠️ **`sameAs` domains must be allowlisted first.** `hostile_review.py` locks
outbound domains to the brand registry, the three publication domains,
`schema.org` and `clarity.ms`, and it scans the **entire raw file including
JSON-LD**. A `sameAs` pointing at LinkedIn or a personal site will HARD_FAIL the
build.

`build_editorial_pages.py` refuses to write such a page and tells you exactly
which host is unregistered, so this fails at build time with a clear message
rather than in CI. To add one, register the contributor's profile domain in the
external-source allowlist before adding them to `contributors.json`.

### Contributor recruitment brief

Ready to send. Fill the bracketed parts; do not embellish them.

> **Subject: Would you write one piece for Memphis Vendor Library?**
>
> Hi [name] — I publish Memphis Vendor Library, a resource site about hosting and
> event vendors in Memphis. I'm looking for a small number of working vendors to
> write one piece each under their own byline, and I'd like to ask you.
>
> Straight about what it is: I own the publication, and I also own [Porch &
> Party], which the site sometimes cites. That's disclosed on every page and on
> our masthead. The site publishes no rankings, no awards and no paid placement —
> nothing on it can be bought.
>
> What I'm asking for: one piece, 800–1,200 words, on something you actually know
> that clients consistently get wrong. [Specific example for this person.] Your
> name on it, your author page, and a link to your own site or profile.
>
> What I'm not asking for: you don't have to mention or link to anything of mine.
> A piece that cites none of my projects is completely fine. There's no payment in
> either direction — I'm not paying for it and you're not paying to appear.
>
> You keep the copyright and can have it taken down if you ever want it gone. If
> we get something wrong in your piece, we publish a correction.
>
> Our standards are at [domain]/editorial-standards and the byline policy is at
> [domain]/contributors. If you're interested, reply and I'll send the specific
> question I'd want you to answer.
>
> — [Publication] Editorial Desk, [domain]/masthead

Why this works: it discloses the conflict first, it asks for expertise rather
than a link, and it explicitly releases them from any obligation to mention the
owner's projects. A vendor who says yes to that is a real contributor.

---

## 6. Separate analytics projects

**Finding: this was already correct for these three, contrary to the initial
assumption.** `data/clarity_projects.json` already maps each publication domain
to a **distinct** Clarity project:

| Publication | Project |
|---|---|
| founderoperatorlibrary.com | `y7l4zlnpql` |
| memphisvendorlibrary.com | `y7l5cj8s28` |
| professionalresourcelibrary.com | `y7l5omyh1t` |

The shared project mentioned in the brief (`y7l3djg8o6`, carrying both
`porchandparty901.com` and `partyandporch.com`) **does not appear in this repo at
all** — that is a different property's problem. The injected tag already resolves
by hostname and each page carries a map naming only its own domain, so no cross-
reporting is possible.

**What was missing was anything preventing the next publication from being added
with a placeholder or a copied id** — and `data/city-publications.json` is
designed to grow. New:
`scripts/validators/validate_analytics_separation.py`, wired into
`validation/plan.json` as **HARD_FAIL** in all three profiles. It checks that
every publication has a project, that no two share one, that none looks like a
placeholder, and that no page's map names another publication's domain. Tested
against both failure modes.

**If a new publication needs a Clarity project** (the owner must do this — it
requires an account):

1. clarity.microsoft.com → sign in → **New project**.
2. Name it after the publication; set the site URL to that domain; **one project
   per domain**.
3. **Settings → Overview** → copy the project ID (a short lowercase string).
4. Add it to `data/clarity_projects.json` under `projects`, keyed by the bare
   domain (no `www.`).
5. `npm run validate:analytics-separation` — it fails if the id is a placeholder,
   blank, or a duplicate of a sibling's.

---

## 7. A separate publishing entity

Structural options only. **Nothing here is legal advice, no filing fees are
quoted because they change and could not be verified, and the specifics need a
Tennessee attorney or CPA.** What follows is the shape of the decision.

**Why it is legitimate.** Media groups routinely hold editorial properties in an
entity separate from commercial operations — it separates liability, makes the
editorial budget legible, and lets the publications outlive any one commercial
venture. It is legitimate **precisely because ownership is disclosed**. Separate
entities with disclosed ownership is a media group. Separate entities with
concealed ownership is the thing `README.md` forbids. Build the first.

**The realistic options:**

1. **Do nothing.** Publications sit under the existing structure, ownership
   disclosed on every masthead. Costs nothing. Loses nothing editorially — the
   masthead already does the work an entity name would do.
2. **A DBA / assumed name.** Register a trade name (e.g. "West Peek Editorial")
   under the existing entity. Cheap, fast, gives the publications a name of their
   own on mastheads and contracts. **No liability separation.**
3. **A separate LLC.** A distinct publishing entity holding the three domains,
   with its own bank account and its own books, disclosing its member. Real
   separation, real ongoing cost: formation, registered agent, separate filings,
   separate returns, and the discipline not to commingle funds — which is what
   actually destroys the separation in practice.

**What to weigh.** Option 3 only means anything if it is maintained. An LLC whose
expenses run through a personal card provides no separation while costing money
every year. If the goal is editorial credibility, **Option 1 plus the masthead
that now exists delivers most of it at zero cost**, and Option 2 is a cheap
upgrade. Option 3 is worth it when there is revenue or liability to separate.

**Verify before acting:** current Tennessee LLC formation and annual report
fees, registered-agent requirements, whether a DBA is filed at state or county
level, and the tax treatment of moving domains between entities.

A separate Cloudflare account is a related decision with the same logic and a
real risk window; the runbook is in
[`CLOUDFLARE-ACCOUNT-SEPARATION.md`](CLOUDFLARE-ACCOUNT-SEPARATION.md), which
recommends deferring it.

### An honest note on what separation does not buy

Separate entities, separate Cloudflare accounts and separate analytics do **not**
meaningfully conceal common ownership, and should not be pursued for that reason.
What remains visible regardless: shared page templates and build configuration,
exclusive cross-linking into a single portfolio, correlated publishing cadence,
and whois. Anyone motivated enough to check will connect them in minutes.

The durable version of independence is the one the rest of this document builds:
**genuinely separate editorial identities, openly disclosed, with published
standards and a working corrections route.** That is defensible under scrutiny.
Concealment is not, and it fails at exactly the moment it matters.

---

## 8. What runs when

`scripts/build_editorial_pages.py`, `scripts/build_robots.py` and
`scripts/install_editorial_chrome.py` are **idempotent** and are wired into
`.github/workflows/authority-v4-autopilot.yml` immediately after
`build_site_navigation.py`.

They run last on purpose. There is no shared page shell in this repository —
five generators each inline their own `<!doctype html>` string, and three more
mutate pages afterwards. Rather than making the same edit in five places and
watching it drift, the installer re-applies the governance chrome over whatever
any generator produced. Same pattern as the existing `install_clarity.js`.

```bash
npm run editorial:build              # all three, in order
npm run validate:analytics-separation
npm run validate:changed
```

**Two markup constraints that must not be broken:**
`build_demand_shape_pages.py` and `deterministic_build.py` lift the header and
footer out of `index.html` with `re.compile(r"<header>.*?</header>")` and the
footer equivalent. **Both tags must stay bare, with no attributes** — adding a
`class` or `id` makes those scripts exit. The stylesheets therefore style
`header` and `footer` by element selector, and idempotency is detected by
comparing rendered content rather than by a marker attribute.

---

## 9. Known issue, not introduced here

`tests/test_recovery_agency_contract.py` fails (**STRONG_WARNING, non-blocking,
does not block release**). It fails on `main` too.

Two causes, both pre-existing:
1. It reads `sites/founder-operator/agency/index.html`, deliberately deleted in
   commit `7e48923` — and which `validate_published_tree_purity.py` now
   HARD_FAILs on if it ever returns. **The test contradicts the repo's current
   design.**
2. It asserts `agency.runtime_operators == package.json scripts`. That was
   already drifting (`cadence:template-share`, `validate:published-tree-purity`)
   before this branch; the five `editorial:*` / `validate:analytics-separation`
   scripts added here extend the list.

Regenerating `data/agency-dashboard.json` would fix cause 2 but not cause 1, so
the test fails either way. It needs a decision about whether that assertion
should be retired now that the operator dashboard is deliberately unpublished —
which is an operator-dashboard question, not an editorial one, and was left
alone rather than papered over.
