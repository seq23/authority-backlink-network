#!/usr/bin/env python3
"""Authored content for the demand-shape pages.

Kept separate from the renderer so the prose is reviewable as prose. Every
`sources` block names ids from data/external-sources.json, and every one of
those URLs was fetched and returned HTTP 200 before it was registered.

No figure appears here that this publication cannot attribute. Where the honest
answer is "the number depends and here is who publishes it", the page says that
instead of printing a range.
"""

PUBLISHED = "2026-08-27"

FOUNDER_PAGES = [
    {
        "lane": "founder",
        "shape": "cost",
        "slug": "virtual-event-production-cost-drivers.html",
        "published": PUBLISHED,
        "title": "What Actually Drives the Cost of a Virtual Event Production",
        "h1": "What Actually Drives the Cost of a Virtual Event Production",
        "eyebrow": "Cost structure, not a price list",
        "description": ("The eight variables that move a virtual event production quote, why "
                        "two bids for the same event differ, and what to put in writing before you sign."),
        "direct_answer": (
            "A virtual event production quote is driven by crew hours, not by audience size. "
            "The variables that move it most are how many live sources have to be switched, "
            "whether the show is rehearsed, whether presenters are in one room or many, how "
            "much is pre-recorded, and how long the crew is booked for. This page does not "
            "publish a price range, because a credible one would have to come from bids on "
            "your own scope."),
        "recommends": (
            "Ask for a quote broken out by crew role and hours rather than a single event "
            "price, and confirm in writing which of the eight cost drivers below your bid "
            "assumes."),
        "boundary": (
            "This is an educational page about how production quotes are structured. It does "
            "not price any specific event and does not rank vendors."),
        "sections": [
            {
                "type": "prose",
                "h2": "Why a single event price tells you almost nothing",
                "paras": [
                    "Two production companies can quote the same webinar and land far apart "
                    "without either being wrong. One assumed a single presenter on a laptop "
                    "and a producer watching the stream. The other assumed three remote "
                    "presenters, a rehearsal the day before, a backup encoder, and a "
                    "post-event edit. Both are honest quotes for different shows.",
                    "That is why the useful question is not what a virtual event costs but "
                    "which assumptions a given number contains. A quote broken out by role "
                    "and hour can be compared to another quote. A single figure cannot be "
                    "compared to anything, and it is the format most likely to produce a "
                    "change order later.",
                    "The cost drivers below are the ones that reliably move a bid. They are "
                    "listed in rough order of impact for a typical single-session corporate "
                    "broadcast, though the order shifts once a show runs multiple days.",
                ],
            },
            {
                "type": "table",
                "h2": "Eight cost drivers and what to confirm about each",
                "intro": ("For each driver, the middle column is what actually changes the "
                          "number, and the right column is the sentence worth getting in "
                          "writing before you sign."),
                "headers": ["Cost driver", "What moves the number", "Confirm in writing"],
                "rows": [
                    ["Crew size and roles",
                     "Each additional role is a separate person for the whole call, not a task",
                     "Which roles are staffed, and whether one person is covering two"],
                    ["Booked hours, not show length",
                     "Load-in, rehearsal, show, and strike are all billable time",
                     "The call time and the release time, not just the broadcast window"],
                    ["Number of live sources",
                     "Every live camera, screen share, or remote presenter is another feed to switch",
                     "How many simultaneous live sources the bid assumes"],
                    ["Rehearsal",
                     "A tech rehearsal is usually a second crew call on a different day",
                     "Whether a rehearsal is included or quoted separately"],
                    ["Presenter locations",
                     "Presenters in one room share a kit; presenters in five cities need five",
                     "How many locations, and who supplies equipment at each"],
                    ["Pre-recorded segments",
                     "Recording and editing happen before the event and are their own line",
                     "How many minutes of pre-recorded content and how many edit passes"],
                    ["Redundancy",
                     "A backup encoder or a second internet path is real hardware and real setup",
                     "What fails over if the primary path drops, and whether it is in the bid"],
                    ["Post-event deliverables",
                     "Captions, cutdowns, and platform re-uploads are work after the show ends",
                     "Exactly which files you receive, in what format, by what date"],
                ],
            },
            {
                "type": "list",
                "h2": "Questions that make two bids comparable",
                "ordered": True,
                "intro": ("Send the same list to every vendor. Differences in the answers "
                          "explain the differences in the numbers."),
                "items": [
                    "How many crew, in which roles, and for how many hours each?",
                    "Is rehearsal included, and is it a separate crew call?",
                    "How many live sources does this bid assume, and what happens if we add one?",
                    "What is the change-order rate if the show runs long?",
                    "What is the redundancy plan, and is the backup path staffed or automatic?",
                    "Who owns the recording, and what deliverables come with it?",
                    "Is travel, per diem, or shipping included, and for whom?",
                    "What is the cancellation and postponement policy, in days and percentages?",
                ],
            },
            {
                "type": "prose",
                "h2": "The staffing question underneath the quote",
                "paras": [
                    "A production company's own cost base is mostly people, and how those "
                    "people are engaged changes what the company must charge. A crew member "
                    "engaged as an employee carries payroll tax and benefit costs that a "
                    "contractor engagement does not, and the classification is not a matter "
                    "of preference. The Internal Revenue Service publishes the test that "
                    "determines which one applies.",
                    "This matters to a buyer for one practical reason: a bid that is far "
                    "below the others may be assuming a classification the vendor cannot "
                    "actually support, and that is a risk that eventually reaches the client "
                    "through cancelled crew or a renegotiated invoice. Asking how crew are "
                    "engaged is a fair question, and a serious vendor will answer it.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The outside references this page relies on:",
                "cites": [
                    {"id": "irs-contractor-or-employee",
                     "used_for": "The federal test for whether a worker is a contractor or an employee."},
                    {"id": "esta-tsp",
                     "used_for": "The ANSI-accredited standards programme covering entertainment "
                                 "rigging, power and staging, which governs the physical side of a hybrid show."},
                    {"id": "sba-manage-your-business",
                     "used_for": "Federal small-business guidance on ongoing compliance obligations."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated projects covering this subject in more depth:",
                "links": [
                    ("https://virtualagency-os.com/learn/virtual-event-production-cost",
                     "virtual event production cost guide",
                     "A longer breakdown of production cost structure."),
                    ("https://www.westpeekproductions.com/", "West Peek Productions",
                     "Virtual event production and executive broadcast planning."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about virtual event production cost",
                "qas": [
                    ("Does a bigger audience cost more?",
                     "Usually far less than people expect. Streaming platforms may charge per "
                     "viewer or per hour, but the production crew cost is the same whether 50 "
                     "or 5,000 people watch. Audience size changes the platform bill, not the "
                     "crew call."),
                    ("Why is rehearsal quoted separately?",
                     "Because it is a separate crew call on a separate day. A rehearsal that "
                     "runs two hours still occupies most of a working day for the crew once "
                     "setup and teardown are counted."),
                    ("Is a cheaper quote a worse quote?",
                     "Not necessarily, but it is usually a different scope. Before treating a "
                     "low bid as a saving, check whether it includes rehearsal, redundancy, "
                     "and post-event deliverables, which are the three things most often left out."),
                    ("Why does this page not list prices?",
                     "Because this publication has no basis for a credible range. Production "
                     "costs vary by market, crew availability, and scope, and a made-up range "
                     "would be worse than none. The honest route is to get two or three bids "
                     "broken out by role and hour."),
                ],
            },
        ],
    },
    {
        "lane": "founder",
        "shape": "checklist",
        "slug": "ai-delegation-risk-checklist.html",
        "published": PUBLISHED,
        "title": "An AI Delegation Checklist for Operators",
        "h1": "An AI Delegation Checklist for Operators",
        "eyebrow": "Checklist grounded in a published framework",
        "description": ("Before handing a recurring task to an AI system, work through these "
                        "checks on reversibility, review, disclosure and failure, mapped to the "
                        "NIST AI Risk Management Framework."),
        "direct_answer": (
            "Delegate a task to an AI system only after you can answer four things: how a "
            "wrong output would be noticed, who reviews it before it reaches anyone outside "
            "the team, how the decision is reversed, and whether the use has to be disclosed. "
            "If any of the four has no answer, the task is not ready to delegate yet."),
        "recommends": (
            "Run the checklist below against one recurring task before you automate it, and "
            "map your answers onto the NIST AI Risk Management Framework rather than an "
            "internal maturity model."),
        "boundary": (
            "This is a general operating checklist. It is not a compliance assessment, and it "
            "does not tell you whether a particular AI use is lawful in your jurisdiction or industry."),
        "sections": [
            {
                "type": "prose",
                "h2": "Why delegation, not adoption, is the unit of decision",
                "paras": [
                    "Most AI failures inside small teams are not model failures. They are "
                    "delegation failures: a task moved to a system without anyone deciding who "
                    "still owns the outcome. The tool worked exactly as designed and produced "
                    "something nobody checked.",
                    "That makes the recurring task, not the tool, the right unit to reason "
                    "about. A single model can be entirely appropriate for drafting an internal "
                    "summary and entirely inappropriate for answering a customer, and no "
                    "tool-level policy captures that difference.",
                    "There is a published, non-commercial framework for this. The National "
                    "Institute of Standards and Technology released the AI Risk Management "
                    "Framework 1.0 on 26 January 2023, developed through an open, "
                    "consensus-driven process, and intended for voluntary use. NIST also "
                    "publishes a companion Playbook. Using it has one practical advantage over "
                    "a vendor's maturity model: nobody selling you anything wrote it.",
                ],
            },
            {
                "type": "list",
                "h2": "The checklist",
                "ordered": True,
                "intro": ("Work through this for one task at a time. A task that fails any "
                          "single item is not blocked forever; it is blocked until that item "
                          "has an answer."),
                "items": [
                    "Name the task in one sentence, including who currently does it and how often.",
                    "Describe what a wrong output looks like. If you cannot describe it, you cannot detect it.",
                    "Say how a wrong output would be noticed, and by whom, before it causes harm.",
                    "Name the reviewer. A named person, not a role that nobody currently fills.",
                    "State the reversal path: how a wrong result gets undone, and how long that takes.",
                    "Decide whether the output leaves the team. Anything customer-facing needs a higher bar.",
                    "Check whether the use requires disclosure to a customer, a client, or a platform.",
                    "Confirm what data the system sees, and whether any of it belongs to someone else.",
                    "Write down the stop condition: what would make you take this task back.",
                    "Re-run this list when the task changes, not on a calendar.",
                ],
            },
            {
                "type": "table",
                "h2": "Four delegation tiers and what each requires",
                "intro": ("A useful shorthand once the checklist has been run once. The tier "
                          "is set by where the output goes, not by how sophisticated the tool is."),
                "headers": ["Tier", "Example task", "Review before release", "Disclosure question"],
                "rows": [
                    ["Draft only",
                     "Summarising an internal meeting for the team",
                     "Author reads it; no second reviewer needed",
                     "None, provided no external data is involved"],
                    ["Internal decision support",
                     "Ranking inbound leads for a human to work through",
                     "Reviewer spot-checks a sample each week",
                     "None externally, but record the method internally"],
                    ["Customer-facing with review",
                     "Drafting a reply that a person sends",
                     "Named person reads every output before it sends",
                     "Check platform and contract terms"],
                    ["Customer-facing autonomous",
                     "A system that replies without a person in the loop",
                     "Sampling plus a logged escalation path",
                     "Assume disclosure is required until confirmed otherwise"],
                ],
            },
            {
                "type": "prose",
                "h2": "The disclosure item is the one most often skipped",
                "paras": [
                    "Operators tend to treat disclosure as a legal question to resolve later. "
                    "In marketing contexts it is often already settled: the Federal Trade "
                    "Commission publishes guidance on endorsements and testimonials that "
                    "applies to how a message is presented regardless of how it was produced, "
                    "and a claim does not become exempt because a model drafted it.",
                    "The practical version of this item is short. If the output makes a claim "
                    "about a product, carries an endorsement, or presents itself as a person's "
                    "own view, read the FTC guidance before it ships rather than after.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The published frameworks and guidance behind this checklist:",
                "cites": [
                    {"id": "nist-ai-rmf",
                     "used_for": "AI RMF 1.0, released 26 January 2023 for voluntary use, and the companion Playbook."},
                    {"id": "nist-ai-rmf-development",
                     "used_for": "How the framework was developed, for checking that it is a real consensus standard."},
                    {"id": "ftc-endorsement-guides",
                     "used_for": "Federal guidance on endorsements and disclosure in marketing messages."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated projects covering operator decision-making:",
                "links": [
                    ("https://billionairehighperformancecoach.com/ai-coach-vs-human-coach.html",
                     "AI coach vs human coach comparison",
                     "Where an AI tool substitutes for a person and where it does not."),
                    ("https://virtualagency-os.com/learn/", "Virtual Agency OS learning library",
                     "Operating systems and delegation practice for small teams."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about delegating work to AI",
                "qas": [
                    ("Is the NIST AI RMF mandatory?",
                     "No. NIST states the framework is intended for voluntary use. Its value is "
                     "that it is a published, independently developed reference, which makes it "
                     "a better shared vocabulary than an internal scheme or a vendor's model."),
                    ("What if nobody on the team can review the output?",
                     "Then the task is not ready to delegate. A task with no competent reviewer "
                     "is a task where errors will be found by a customer, which is the most "
                     "expensive place to find them."),
                    ("How often should the checklist be re-run?",
                     "When the task changes, when the tool changes materially, or when a failure "
                     "occurs. A fixed calendar review tends to become a formality."),
                    ("Does disclosure mean labelling everything?",
                     "Not necessarily, and the answer depends on context and jurisdiction. The "
                     "checklist item is to establish the answer deliberately rather than by "
                     "default, starting with the FTC guidance where marketing claims are involved."),
                ],
            },
        ],
    },
    {
        "lane": "founder",
        "shape": "comparison",
        "slug": "contractor-vs-employee-lean-team-comparison.html",
        "published": PUBLISHED,
        "title": "Contractor or Employee: Comparing Two Ways to Staff a Lean Team",
        "h1": "Contractor or Employee: Comparing Two Ways to Staff a Lean Team",
        "eyebrow": "Comparison with the classification test named",
        "description": ("A side-by-side comparison of contractor and employee engagements for a "
                        "small operating team, and why the choice is a legal test rather than a preference."),
        "direct_answer": (
            "The contractor-or-employee decision is not a preference and not a cost optimisation. "
            "It is a classification determined by the degree of control and independence in the "
            "relationship, and the Internal Revenue Service publishes the test. The useful "
            "comparison is therefore not which is cheaper, but which one your actual working "
            "arrangement already is."),
        "recommends": (
            "Describe how the work is actually directed, then check that description against the "
            "IRS test before choosing an engagement type, rather than choosing the type first "
            "and describing the work to fit."),
        "boundary": (
            "This page compares two engagement models in general terms. It is not tax advice and "
            "does not determine the correct classification for any specific worker."),
        "sections": [
            {
                "type": "prose",
                "h2": "The comparison most founders start with is the wrong one",
                "paras": [
                    "The usual framing is a cost comparison: a contractor invoices a rate, an "
                    "employee costs the salary plus payroll taxes and benefits, so the "
                    "contractor looks cheaper. That comparison is real but it is downstream of "
                    "a question that is not optional.",
                    "Worker classification is determined by the facts of the working "
                    "relationship, not by what the parties agree to call it or what the "
                    "contract says. The Internal Revenue Service publishes guidance on the "
                    "distinction between an independent contractor and an employee, and it "
                    "turns on the degree of control the business exercises and the degree of "
                    "independence the worker retains.",
                    "So the honest sequence is: describe how the work is really directed, then "
                    "read the test, then price the arrangement that description implies. "
                    "Reversing that order is how small teams accumulate a liability that "
                    "surfaces years later.",
                ],
            },
            {
                "type": "table",
                "h2": "Side by side",
                "intro": ("Generalised differences between the two engagement models. The right "
                          "column is the question that usually settles which one you are "
                          "actually operating."),
                "headers": ["Dimension", "Contractor engagement", "Employee engagement",
                            "Question that decides it"],
                "rows": [
                    ["Direction of work",
                     "Contractor decides how and often when the work is done",
                     "Business directs how, when and in what sequence",
                     "Who decides the method, not just the outcome?"],
                    ["Tools and equipment",
                     "Typically supplied by the contractor",
                     "Typically supplied by the business",
                     "Whose equipment does the work run on?"],
                    ["Financial risk",
                     "Contractor can make a loss on an engagement",
                     "Employee is paid regardless of project outcome",
                     "Who absorbs a cost overrun?"],
                    ["Other clients",
                     "Usually free to work for others in the same period",
                     "Usually exclusive or restricted",
                     "Is the worker offering services to a wider market?"],
                    ["Duration",
                     "Scoped to a project or defined term",
                     "Continuing and open-ended",
                     "Does the relationship end when the project does?"],
                    ["Onboarding and training",
                     "Expected to arrive with the skill",
                     "Trained in the business's way of working",
                     "Are you teaching the method or buying the result?"],
                    ["Administrative load",
                     "Contract, invoices, and information reporting",
                     "Payroll, withholding, and ongoing compliance",
                     "Which obligations is the business actually able to run?"],
                ],
            },
            {
                "type": "list",
                "h2": "Signals that a contractor engagement has drifted",
                "intro": ("Drift is the common failure. The engagement started correctly and "
                          "the working relationship changed without the paperwork changing."),
                "items": [
                    "The person now attends internal meetings as a matter of course rather than by invitation.",
                    "Their hours are set by the business rather than by the deliverable.",
                    "They have been working exclusively for you for a long, open-ended period.",
                    "They use business-supplied equipment and accounts for everything.",
                    "You train them in your method rather than buying an outcome.",
                    "They manage or are managed by employees in the ordinary chain of command.",
                    "The original statement of work no longer describes what they do.",
                ],
            },
            {
                "type": "prose",
                "h2": "What to do with the answer",
                "paras": [
                    "If the description of the actual relationship matches an employee "
                    "engagement, the resolution is to change the engagement or change the "
                    "relationship, and both are legitimate. What is not legitimate is leaving "
                    "the mismatch in place because the paperwork is convenient.",
                    "The Small Business Administration publishes general guidance on launching "
                    "and running a business, including the ongoing compliance obligations that "
                    "an employee engagement brings. For anything specific to your facts or "
                    "your state, this is a question for a professional who can look at the "
                    "actual arrangement.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "Where the classification rules and compliance obligations are published:",
                "cites": [
                    {"id": "irs-contractor-or-employee",
                     "used_for": "The federal contractor-or-employee determination and the control test behind it."},
                    {"id": "sba-launch-your-business",
                     "used_for": "Choosing a business structure and the obligations each carries."},
                    {"id": "sba-manage-your-business",
                     "used_for": "Ongoing compliance obligations once people are engaged."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated projects covering lean team operations:",
                "links": [
                    ("https://www.aplayermode.com/", "A Player Mode",
                     "Standards and operating practice for small high-performing teams."),
                    ("https://virtualagency-os.com/learn/", "Virtual Agency OS learning library",
                     "Delegation, roles, and operating systems for lean teams."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about contractor and employee engagements",
                "qas": [
                    ("Can a contract simply state that someone is a contractor?",
                     "A contract records what the parties intend, but classification is "
                     "determined by the facts of the working relationship. A contract that "
                     "describes an arrangement different from the one actually operating does "
                     "not settle the question."),
                    ("Is a contractor always cheaper?",
                     "Not reliably. Contractor rates usually price in the costs the business is "
                     "not carrying, and misclassification carries a cost of its own. The "
                     "comparison only means something once the correct classification is established."),
                    ("What if the same person does both kinds of work?",
                     "That is a common and genuinely difficult situation, and it is one where "
                     "the general guidance stops being enough. It is worth professional advice "
                     "on the specific facts."),
                    ("Where is the actual test published?",
                     "The Internal Revenue Service publishes it, and the page is linked in the "
                     "sources section above. Read it against a written description of how the "
                     "work is really directed."),
                ],
            },
        ],
    },
    {
        "lane": "founder",
        "shape": "checklist",
        "slug": "event-production-safety-standards-questions.html",
        "published": PUBLISHED,
        "title": "What to Ask an Event Production Vendor About Safety Standards",
        "h1": "What to Ask an Event Production Vendor About Safety Standards",
        "eyebrow": "Checklist against an accredited standards programme",
        "description": ("The questions that separate a production vendor working to published "
                        "entertainment technology standards from one improvising, and where those "
                        "standards actually come from."),
        "direct_answer": (
            "Ask which published standards the vendor works to, who on the crew is responsible "
            "for rigging and power, and what the plan is when something fails. The entertainment "
            "technology industry has an ANSI-accredited standards programme, so a vendor who "
            "cannot name any standard is telling you something useful."),
        "recommends": (
            "Put the eight questions below to any vendor handling rigging, temporary power, or "
            "overhead load, and get the answers in the contract rather than in a phone call."),
        "boundary": (
            "This page lists questions a buyer can ask. It is not a safety inspection, does not "
            "certify any vendor, and does not substitute for the responsible competent person on site."),
        "sections": [
            {
                "type": "prose",
                "h2": "There is a real standards body, and most buyers have never heard of it",
                "paras": [
                    "Event production sits in an unusual position. It involves overhead loads, "
                    "temporary power distribution, and structures assembled in hours by crews "
                    "who may never have worked together, and yet the buyer is usually a "
                    "marketing or events team with no technical background.",
                    "The industry does have published standards. The Entertainment Services and "
                    "Technology Association runs the Technical Standards Program, which it "
                    "describes as the only ANSI-accredited standards programme dedicated to "
                    "entertainment technology. It is built by over 350 volunteer experts "
                    "drafting American National Standards covering areas including rigging and "
                    "power.",
                    "A buyer does not need to read those standards. A buyer needs to know they "
                    "exist, because it converts a vague question about safety into a specific "
                    "one that a competent vendor can answer immediately and an improvising one cannot.",
                ],
            },
            {
                "type": "list",
                "h2": "Eight questions to ask before signing",
                "ordered": True,
                "intro": "Ask all eight. The pattern of answers matters more than any single one.",
                "items": [
                    "Which published standards does your crew work to for rigging and temporary power?",
                    "Who on site is the named responsible person for overhead load, and what is their qualification?",
                    "Will anything be suspended above people, and if so what is the secondary retention?",
                    "Who performs the pre-show check, and is it recorded?",
                    "What is the plan if the venue's power is not what the site survey said?",
                    "Has a site survey been done, and may we see it?",
                    "What is the crew's maximum working day on this call, and who calls a halt?",
                    "Who holds the insurance, what does it cover, and may we see the certificate?",
                ],
            },
            {
                "type": "table",
                "h2": "How to read the answers",
                "intro": ("The distinction that matters is between a vendor who has a process "
                          "and a vendor who has confidence."),
                "headers": ["Question area", "A reassuring answer sounds like", "A concerning answer sounds like"],
                "rows": [
                    ["Standards",
                     "Names a specific standards programme or document and can say what it covers",
                     "\"Everything is to code\" with no code named"],
                    ["Named responsibility",
                     "Names a role and a person, and says what happens when that person is unavailable",
                     "\"The whole crew is experienced\""],
                    ["Overhead load",
                     "Describes secondary retention and what is and is not flown over people",
                     "Treats the question as unusual"],
                    ["Pre-show checks",
                     "Describes a written check that someone signs",
                     "Describes checks as continuous and informal"],
                    ["Power",
                     "Describes a site survey and a contingency if supply differs",
                     "Assumes the venue's information is correct"],
                    ["Stopping work",
                     "States plainly that any crew member can stop the job",
                     "Locates that authority only with the client or the schedule"],
                ],
            },
            {
                "type": "prose",
                "h2": "Why this matters even for a small show",
                "paras": [
                    "The instinct is that standards are for arenas and that a fifty-person "
                    "conference room does not need this conversation. The physical risks do "
                    "scale down, but two things do not: a small show is more likely to be "
                    "crewed by people who have not worked together, and more likely to be "
                    "scheduled with no margin.",
                    "Those are precisely the conditions where a written pre-show check and a "
                    "clear stop-work authority do the most work. They cost nothing to ask for "
                    "at contract stage and are close to impossible to introduce on the day.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The standards programme referenced above:",
                "cites": [
                    {"id": "esta-tsp",
                     "used_for": "The ANSI-accredited Technical Standards Program for entertainment "
                                 "technology, its scope and how it is developed."},
                    {"id": "sba-manage-your-business",
                     "used_for": "General compliance obligations for a business engaging vendors and crew."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated projects covering event production:",
                "links": [
                    ("https://www.westpeekproductions.com/", "West Peek Productions",
                     "Virtual event production and executive broadcast planning."),
                    ("https://virtualagency-os.com/learn/what-is-virtual-event-production",
                     "what virtual event production means",
                     "How production scope is defined before a vendor conversation."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about production safety standards",
                "qas": [
                    ("Is ESTA a regulator?",
                     "No. It is a standards-developing organisation. Its Technical Standards "
                     "Program is ANSI-accredited and produces American National Standards, but "
                     "enforcement of workplace safety rests with the relevant regulator and the "
                     "venue, not with ESTA."),
                    ("Do I need to read the standards myself?",
                     "No. The point of asking is to find out whether the vendor works to any "
                     "published standard at all, which is a question you can evaluate without "
                     "technical knowledge."),
                    ("What if the vendor cannot name a standard?",
                     "It is not automatically disqualifying, particularly for a small vendor, "
                     "but it makes the other questions more important, especially the ones about "
                     "named responsibility and stop-work authority."),
                    ("Does the venue not handle all of this?",
                     "Venues vary enormously. Some have in-house technical staff who control "
                     "rigging and power entirely; others hand over an empty room. Establishing "
                     "which one you have is part of the site survey question."),
                ],
            },
        ],
    },
]

MEMPHIS_PAGES = [
    {
        "lane": "memphis",
        "shape": "geo-cost",
        "slug": "memphis-event-vendor-quote-cost-drivers.html",
        "published": PUBLISHED,
        "title": "What Moves the Price of a Memphis Event Vendor Quote",
        "h1": "What Moves the Price of a Memphis Event Vendor Quote",
        "eyebrow": "Memphis cost structure, not a price list",
        "description": ("The local variables that change an event vendor quote in Memphis and "
                        "Shelby County, including tax, permits, delivery windows and seasonality."),
        "direct_answer": (
            "Two Memphis vendor quotes for the same party can differ because of things that "
            "have nothing to do with the decor: whether sales tax is shown separately, whether "
            "the setup needs a permit, how far the delivery is from the vendor's base, and what "
            "weekend of the year it is. This page names those local variables and points at the "
            "Tennessee and Shelby County authorities that publish the rules, rather than "
            "printing a price range."),
        "recommends": (
            "Ask every Memphis vendor for a written quote that separates labour, rental, "
            "delivery and tax, and confirm which party is responsible for any permit before "
            "comparing numbers."),
        "boundary": (
            "This is an educational page about local cost structure. It does not price any "
            "event, does not rank vendors, and is not tax advice."),
        "sections": [
            {
                "type": "prose",
                "h2": "Why the local variables matter more than people expect",
                "paras": [
                    "When two quotes for the same Memphis event land far apart, the gap is "
                    "usually not in the decor. It is in the parts of the quote that are easy "
                    "to leave implicit: whether the number includes tax, whether the crew is "
                    "coming back to strike, how far the van is driving, and whether the date "
                    "is one every vendor in the city is already booked for.",
                    "None of that is unique to Memphis, but the specific answers are local. "
                    "Sales and use tax is administered by the Tennessee Department of Revenue. "
                    "Food service is permitted and inspected by the Shelby County Health "
                    "Department. Anything involving public property, street closures, or "
                    "certain temporary structures is a City of Memphis question. A quote "
                    "silently assumes an answer to each of these.",
                    "The practical move is to make those assumptions explicit before comparing "
                    "numbers, which is what the table below is for.",
                ],
            },
            {
                "type": "table",
                "h2": "Local variables that change a Memphis quote",
                "intro": ("For each variable: what it changes, and who actually publishes the "
                          "answer. Confirm current requirements with the named authority."),
                "headers": ["Variable", "How it moves the quote", "Who publishes the answer"],
                "rows": [
                    ["Sales and use tax",
                     "A quote shown before tax is not comparable to one shown after it",
                     "Tennessee Department of Revenue"],
                    ["Food service permitting",
                     "A permitted, inspected food setup carries costs an unpermitted one does not",
                     "Shelby County Health Department"],
                    ["Public property or street use",
                     "Permits, timing restrictions and insurance requirements",
                     "City of Memphis"],
                    ["Delivery distance and access",
                     "Drive time, parking, stairs and lift access are all crew hours",
                     "The vendor, in writing, based on the specific address"],
                    ["Strike and collection",
                     "A second crew trip to remove rentals is a separate cost from setup",
                     "The vendor's contract terms"],
                    ["Date and season",
                     "Peak weekends compress supply of both crew and rental stock",
                     "The vendor's own booking calendar"],
                    ["Outdoor weather risk",
                     "A wet-weather contingency is either priced in or it is not",
                     "National Weather Service Memphis forecast office"],
                    ["Rental versus purchase",
                     "Rented stock returns; purchased stock is yours and is priced accordingly",
                     "The vendor's line-item breakdown"],
                ],
            },
            {
                "type": "list",
                "h2": "What to ask for so two quotes can be compared",
                "ordered": True,
                "intro": "Send the same request to each vendor and compare like with like.",
                "items": [
                    "A written quote separating labour, rental stock, delivery and tax.",
                    "Whether the figure shown includes Tennessee sales tax or excludes it.",
                    "Whether setup and strike are both included, and how many crew trips that is.",
                    "The delivery address assumed, and what changes if access is harder than expected.",
                    "Who is responsible for any permit, and whether the vendor has obtained it before.",
                    "The wet-weather plan for anything outdoors, and whether it costs extra.",
                    "The deposit, the balance date, and the cancellation terms in days and percentages.",
                    "What happens to rented items that are damaged, and who carries that risk.",
                ],
            },
            {
                "type": "prose",
                "h2": "A note on why no prices appear here",
                "paras": [
                    "It would be easy to publish a table of typical Memphis prices and it would "
                    "make this page more satisfying to read. It would also be invented. This "
                    "publication has not surveyed local vendor pricing, and a range presented "
                    "without that work would be a number with a confident format and no basis.",
                    "The useful substitute is the structure above. A reader who knows which "
                    "eight variables move the number, and who publishes the rules behind three "
                    "of them, can get real quotes and read them properly. That is worth more "
                    "than a range that may be wrong for their date, their address, and their guest count.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The authorities that publish the local rules referenced above:",
                "cites": [
                    {"id": "tn-sales-and-use-tax",
                     "used_for": "Tennessee sales and use tax, which decides whether a quote is shown before or after tax."},
                    {"id": "shelby-county-health",
                     "used_for": "The county authority that permits and inspects food service in Memphis."},
                    {"id": "memphis-city-government",
                     "used_for": "City requirements for events involving public property or street use."},
                    {"id": "nws-memphis",
                     "used_for": "The local forecast office, for the weather risk an outdoor date carries."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated local resources:",
                "links": [
                    ("https://porchandparty901.com/pricing.html", "Porch & Party pricing information",
                     "How one Memphis decor vendor structures its own pricing."),
                    ("https://porchandparty901.com/", "Porch & Party",
                     "Memphis event decor, porch styling and party setups."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about Memphis event vendor pricing",
                "qas": [
                    ("Why does one quote look so much cheaper?",
                     "Most often because it excludes something the other includes: tax, strike, "
                     "delivery beyond a certain radius, or a wet-weather contingency. Ask each "
                     "vendor to confirm which of those the number contains."),
                    ("Do I need a permit for a party at my own house?",
                     "Usually the question only arises when public property, a street, or food "
                     "service for the public is involved. The City of Memphis and the Shelby "
                     "County Health Department are the authorities that can confirm it for your "
                     "specific setup, and it is worth asking rather than assuming."),
                    ("Is sales tax charged on event decor services?",
                     "That depends on what is being supplied and how it is structured, which is "
                     "why this page points at the Tennessee Department of Revenue rather than "
                     "answering it. Ask the vendor to show tax as a separate line so you can see "
                     "how they have treated it."),
                    ("How far ahead should I book?",
                     "Vendors report that peak weekends go first, but this publication has no "
                     "survey data on Memphis lead times and will not invent one. Ask two or "
                     "three vendors directly what their calendar looks like for your date."),
                ],
            },
        ],
    },
    {
        "lane": "memphis",
        "shape": "checklist",
        "slug": "grazing-table-food-safety-checklist.html",
        "published": PUBLISHED,
        "title": "A Food Safety Checklist for a Grazing Table",
        "h1": "A Food Safety Checklist for a Grazing Table",
        "eyebrow": "Checklist grounded in the FDA Food Code",
        "description": ("A grazing table sits out for hours, which is exactly the condition food "
                        "safety rules exist for. What to plan, what to ask a caterer, and where the "
                        "actual rules come from."),
        "direct_answer": (
            "The risk in a grazing table is time and temperature: it is designed to sit out and "
            "be picked at, which is the opposite of how perishable food is meant to be held. The "
            "rules that govern this come from the FDA Food Code, which state and local "
            "jurisdictions adopt as the basis for their own food rules, and in Memphis the "
            "permitting and inspection authority is the Shelby County Health Department."),
        "recommends": (
            "Decide before the event which items are temperature-sensitive, plan how long the "
            "table will be out, and ask any caterer whether they hold a current permit from the "
            "county health department."),
        "boundary": (
            "This is general educational information about food safety planning. It is not a "
            "food safety certification, does not state the requirements for any specific event, "
            "and does not replace guidance from the county health department or a permitted caterer."),
        "sections": [
            {
                "type": "prose",
                "h2": "Why a grazing table is a harder food safety problem than a buffet",
                "paras": [
                    "A grazing table is styled to look abundant and untouched, and it is meant "
                    "to stay out for the length of the event. That is its appeal and it is also "
                    "the whole of the risk. A plated meal is served and cleared. A grazing table "
                    "is a perishable display with a multi-hour service window and no chafing dish.",
                    "This is not a fringe concern. The Food and Drug Administration publishes "
                    "the Food Code as a model that, in its own description, gives food control "
                    "jurisdictions at every level of government a scientifically sound technical "
                    "and legal basis for regulating retail and food service. Local, state, tribal "
                    "and federal regulators use it as the model for their own rules. Since the "
                    "2005 edition, full editions have been issued on a four-year interval, with "
                    "supplements published in between.",
                    "For a Memphis event, the authority that actually permits and inspects food "
                    "service is the Shelby County Health Department. A host planning a private "
                    "party at home is in a different position from a caterer serving the public, "
                    "and the department is the right place to confirm which situation applies.",
                ],
            },
            {
                "type": "table",
                "h2": "Sorting the table by risk before you style it",
                "intro": ("The styling decision and the safety decision are the same decision. "
                          "Group items this way when planning the layout."),
                "headers": ["Group", "Examples", "Planning implication"],
                "rows": [
                    ["Shelf-stable",
                     "Crackers, nuts, dried fruit, whole hard fruit",
                     "Can carry the visual bulk of the table for the full event"],
                    ["Cold and perishable",
                     "Soft cheese, cured meat, dips, cut fruit, anything dairy-based",
                     "Needs a held temperature and a defined time out; plan replenishment rather than volume"],
                    ["Hot and perishable",
                     "Anything served warm",
                     "Generally does not belong on an unheated grazing display at all"],
                    ["Allergen-relevant",
                     "Nuts, dairy, gluten, shellfish",
                     "Needs separation and labelling regardless of temperature"],
                    ["Garnish and non-food",
                     "Foliage, flowers, decorative props",
                     "Confirm nothing decorative is toxic or treated, and keep it off food surfaces"],
                ],
            },
            {
                "type": "list",
                "h2": "The checklist",
                "ordered": True,
                "intro": "Work through this while planning, not on the day.",
                "items": [
                    "Decide how long the table will actually be out, from set-down to clear.",
                    "Separate the menu into shelf-stable and perishable, and build the visual bulk from shelf-stable items.",
                    "Plan cold holding for perishable items rather than assuming room temperature is fine.",
                    "Use a thermometer rather than judging by touch; the FDA publishes guidance on cold holding and thermometers.",
                    "Plan replenishment in small batches instead of putting the full quantity out at once.",
                    "Keep a labelled record of allergens, and separate allergen items physically.",
                    "Agree who is watching the table during the event and who clears it.",
                    "Decide in advance what happens to leftovers, and do not return items to cold storage after a long hold.",
                    "If a caterer is supplying the food, confirm they hold a current county permit.",
                    "If the event is outdoors, check the forecast: heat compresses every timing above.",
                ],
            },
            {
                "type": "prose",
                "h2": "The outdoor variable",
                "paras": [
                    "An outdoor grazing table in a Memphis summer is a materially different "
                    "proposition from an indoor one, because ambient temperature shortens every "
                    "safe holding window and direct sun shortens it further. The National "
                    "Weather Service Memphis forecast office publishes the local forecast, and "
                    "NOAA publishes 30-year climate normals, which is the honest way to check "
                    "what a given month in Memphis typically looks like rather than relying on "
                    "an impression.",
                    "The practical adjustment is usually not cancelling the table. It is shade, "
                    "smaller batches, more frequent replenishment, and a shorter planned service "
                    "window than the same table would get indoors.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "Where the food safety rules and local requirements are published:",
                "cites": [
                    {"id": "fda-food-code",
                     "used_for": "The model code that state, local and tribal jurisdictions adopt as "
                                 "the basis for retail food safety rules."},
                    {"id": "fda-refrigerator-thermometers",
                     "used_for": "Cold holding and why a thermometer rather than judgement is the check."},
                    {"id": "shelby-county-health",
                     "used_for": "The Memphis-area authority that permits and inspects food service."},
                    {"id": "noaa-climate-normals",
                     "used_for": "30-year climate normals, for checking what a Memphis month typically looks like."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated local resources:",
                "links": [
                    ("https://porchandparty901.com/services/grazing-tables-memphis.html",
                     "grazing tables in Memphis",
                     "How one Memphis vendor builds and styles grazing tables."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about grazing table food safety",
                "qas": [
                    ("How long can a grazing table stay out?",
                     "That depends on the food, the holding temperature and the ambient "
                     "conditions, which is why this page points at the FDA Food Code and the "
                     "county health department rather than giving a single number. Plan the "
                     "service window deliberately and ask a permitted caterer for the specific answer."),
                    ("Does a home party need a permit?",
                     "Requirements differ between a private gathering and food served to the "
                     "public, and the Shelby County Health Department is the authority that can "
                     "confirm which applies. It is a short question to ask and a poor one to assume."),
                    ("Is the FDA Food Code law?",
                     "It is a model, not a law in itself. The FDA describes it as a model that "
                     "jurisdictions use to develop or update their own food safety rules, so the "
                     "binding rules are the ones your state and county have adopted."),
                    ("What about leftovers from the table?",
                     "Food that has been held at room temperature for a long service window is "
                     "in a different position from food that came straight from cold storage. "
                     "Decide the leftover policy before the event rather than at the end of it."),
                ],
            },
        ],
    },
    {
        "lane": "memphis",
        "shape": "geo",
        "slug": "memphis-outdoor-event-weather-planning.html",
        "published": PUBLISHED,
        "title": "Planning an Outdoor Memphis Event Around the Weather",
        "h1": "Planning an Outdoor Memphis Event Around the Weather",
        "eyebrow": "Memphis-specific planning",
        "description": ("How to use the National Weather Service Memphis forecast and NOAA climate "
                        "normals to choose a date, set a call time, and write a workable wet-weather plan."),
        "direct_answer": (
            "There are two different weather questions in an outdoor Memphis event and they need "
            "different sources. Choosing a month is a climate question, answered by NOAA's 30-year "
            "climate normals. Deciding what happens on the day is a forecast question, answered by "
            "the National Weather Service Memphis forecast office. Using a forecast to pick a date "
            "nine months out is the common mistake."),
        "recommends": (
            "Use NOAA climate normals to choose the month and time of day, use the NWS Memphis "
            "forecast in the final week, and write the wet-weather plan into the vendor contract "
            "rather than agreeing it verbally."),
        "boundary": (
            "This page explains which public weather sources answer which planning question. It "
            "does not forecast weather and is not a substitute for official warnings."),
        "sections": [
            {
                "type": "prose",
                "h2": "Two questions, two sources",
                "paras": [
                    "Almost every weather mistake in outdoor event planning comes from using the "
                    "wrong source for the question being asked. A forecast is a short-range "
                    "product. It cannot tell you whether a Saturday in nine months will be "
                    "pleasant, and no amount of refreshing it will make it able to.",
                    "The question of what a Memphis month is typically like is a climate "
                    "question, and NOAA's National Centers for Environmental Information "
                    "publishes U.S. Climate Normals, which are 30-year averages. That is the "
                    "right instrument for choosing a month, a time of day, and whether shade or "
                    "heat is the thing to design around.",
                    "The question of what will happen on your actual date is a forecast "
                    "question, and the National Weather Service operates a Memphis forecast "
                    "office that publishes it. That becomes useful in the final week, and it is "
                    "the source that issues watches and warnings.",
                ],
            },
            {
                "type": "table",
                "h2": "Which source answers which decision",
                "intro": "Match the decision to the instrument that can actually answer it.",
                "headers": ["Decision", "When you make it", "Source that answers it"],
                "rows": [
                    ["Which month to hold it in",
                     "Six to twelve months out",
                     "NOAA U.S. Climate Normals"],
                    ["What time of day to start",
                     "When the month is chosen",
                     "NOAA U.S. Climate Normals"],
                    ["Whether to budget for shade or heating",
                     "At the point of booking rentals",
                     "NOAA U.S. Climate Normals"],
                    ["Whether the wet-weather plan is likely to be used",
                     "Final week",
                     "NWS Memphis forecast"],
                    ["Whether to trigger the wet-weather plan",
                     "24 to 48 hours out, per the contract",
                     "NWS Memphis forecast"],
                    ["Whether to stop or evacuate",
                     "On the day",
                     "NWS Memphis watches and warnings"],
                ],
            },
            {
                "type": "list",
                "h2": "Writing a wet-weather plan a vendor can actually execute",
                "ordered": True,
                "intro": ("The failure mode is a plan that exists in conversation and not in the "
                          "contract. Each item below is a sentence that belongs in writing."),
                "items": [
                    "Name the decision-maker: one person who calls it, not a committee.",
                    "Name the deadline: the exact hour by which the call is made.",
                    "Name the trigger: what condition in the forecast causes the call.",
                    "Describe plan B concretely, including where it physically happens.",
                    "State what plan B costs and who pays for it.",
                    "State what happens to already-delivered rentals if plan B is triggered.",
                    "Confirm the vendor's crew is available for the plan B setup as well.",
                    "Agree what happens if the call is made and the weather then holds.",
                ],
            },
            {
                "type": "prose",
                "h2": "The heat variable people underestimate",
                "paras": [
                    "Rain gets the attention because it is dramatic and visible, but for a "
                    "Memphis outdoor event in the warmer months heat is often the bigger "
                    "operational problem. It affects guests, it affects crew working a load-in "
                    "in direct sun, and it shortens the safe service window for any perishable "
                    "food on the table.",
                    "Designing around it is mostly a matter of timing and shade, both of which "
                    "are decided months ahead using climate normals rather than in the final "
                    "week using a forecast. A start time chosen for the light is not always a "
                    "start time that works for the temperature, and that trade-off is easier to "
                    "make deliberately than to discover.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The public weather and climate sources referenced above:",
                "cites": [
                    {"id": "nws-memphis",
                     "used_for": "The local forecast office for the Memphis area, including watches and warnings."},
                    {"id": "noaa-climate-normals",
                     "used_for": "30-year U.S. Climate Normals, the right instrument for choosing a month and a time of day."},
                    {"id": "memphis-city-government",
                     "used_for": "City requirements for events on public property, which can interact with a weather postponement."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated local resources:",
                "links": [
                    ("https://porchandparty901.com/services/porch-decorating.html",
                     "Memphis porch decorating services",
                     "Covered and semi-covered setups that reduce weather exposure."),
                    ("https://porchandparty901.com/", "Porch & Party",
                     "Memphis event decor and seasonal styling."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about Memphis outdoor event weather",
                "qas": [
                    ("How far ahead is a forecast actually useful?",
                     "For an event decision, the final week is where it starts to carry weight, "
                     "and the final 48 hours is where most contracts set the trigger. Beyond "
                     "that range, climate normals are the more honest instrument."),
                    ("What are climate normals?",
                     "They are 30-year averages published by NOAA's National Centers for "
                     "Environmental Information. They describe what is typical for a place and "
                     "time of year, which is a different thing from a prediction about a specific date."),
                    ("Who should make the wet-weather call?",
                     "One named person, with the deadline written into the contract. The common "
                     "failure is not a wrong call; it is no call, made too late for the vendor to act on."),
                    ("Does this page tell me what the weather will be?",
                     "No. It tells you which official source answers which question. The forecast "
                     "itself comes from the National Weather Service, linked in the sources above."),
                ],
            },
        ],
    },
    {
        "lane": "memphis",
        "shape": "geo-comparison",
        "slug": "memphis-event-rental-vs-purchase-comparison.html",
        "published": PUBLISHED,
        "title": "Renting or Buying Event Decor in Memphis: A Comparison",
        "h1": "Renting or Buying Event Decor in Memphis: A Comparison",
        "eyebrow": "Comparison for local hosts",
        "description": ("When renting event decor makes sense in Memphis, when buying does, and the "
                        "local factors including storage, tax treatment and strike logistics that decide it."),
        "direct_answer": (
            "Rent when the item is bulky, used once, or needs a crew to install and remove. Buy "
            "when the item is small, will be reused within a year, and you have somewhere to keep "
            "it. The decision usually turns on strike and storage rather than on the sticker "
            "price, and in Memphis it also turns on how the vendor structures tax and delivery."),
        "recommends": (
            "Compare rental and purchase on total cost including delivery, strike, storage and "
            "damage risk, not on the headline price, and ask the vendor to show tax as a separate line."),
        "boundary": (
            "This page compares two approaches in general terms. It does not price any item, does "
            "not rank vendors, and is not tax advice."),
        "sections": [
            {
                "type": "prose",
                "h2": "The comparison people run, and the one that decides it",
                "paras": [
                    "The instinctive comparison is a rental fee against a purchase price, and it "
                    "usually makes buying look sensible: if renting something for one weekend "
                    "costs a meaningful fraction of owning it, ownership seems obviously better.",
                    "That comparison leaves out the three things that actually determine the "
                    "answer. Someone has to deliver the item and someone has to take it away, "
                    "which is crew time either way. Someone has to store it for the rest of the "
                    "year, which for anything large is a real cost even when it is invisible "
                    "because it is your own garage. And if it breaks, ownership means you "
                    "replace it, while a rental contract allocates that risk explicitly.",
                    "Once those are in the comparison, the answer separates cleanly by item type "
                    "rather than by philosophy, which is what the table below sets out.",
                ],
            },
            {
                "type": "table",
                "h2": "Where each option usually wins",
                "intro": ("Generalised guidance by item type. The right column is the question "
                          "that settles a borderline case."),
                "headers": ["Item type", "Usually rent", "Usually buy", "The deciding question"],
                "rows": [
                    ["Large structures such as tents and arches",
                     "Yes, installation and strike dominate the cost",
                     "Rarely, unless hosting many events a year",
                     "Can you install and remove it without a crew?"],
                    ["Tables, chairs and linens",
                     "Yes for one event at scale",
                     "Only for small, frequently repeated gatherings",
                     "How many times will you use it in twelve months?"],
                    ["Seasonal porch and door decor",
                     "Sometimes, for a styled one-off",
                     "Often, since it repeats every year and stores flat",
                     "Does it repeat annually and store in a box?"],
                    ["Serving pieces such as boards and stands",
                     "For a large one-off spread",
                     "Often, since they are small and reused",
                     "Will it earn its shelf space?"],
                    ["Lighting and power distribution",
                     "Yes, installation and safety matter more than ownership",
                     "Rarely",
                     "Is anyone qualified to install it safely?"],
                    ["Fresh florals and perishables",
                     "Not applicable; these are consumed",
                     "Not applicable; these are consumed",
                     "Plan replacement, not ownership"],
                ],
            },
            {
                "type": "list",
                "h2": "The costs to put on both sides of the comparison",
                "intro": "Compare these line by line rather than comparing headline numbers.",
                "items": [
                    "Delivery to the specific address, including access difficulty and parking.",
                    "Setup labour, and whether it is the same crew trip as delivery.",
                    "Strike and collection, which is usually a separate crew trip.",
                    "Storage for the rest of the year, including whether it needs to stay dry.",
                    "Damage and replacement risk, and who carries it under the contract.",
                    "Tennessee sales tax, shown as a separate line so both options are comparable.",
                    "Cleaning between uses, which for linens and serving pieces is not trivial.",
                    "Disposal at end of life for anything purchased.",
                ],
            },
            {
                "type": "prose",
                "h2": "Two local factors worth naming",
                "paras": [
                    "The first is tax treatment. A rental and a purchase are not necessarily "
                    "treated identically for Tennessee sales and use tax, and the practical "
                    "consequence is that a like-for-like comparison needs both quotes to show "
                    "tax as a separate line. The Tennessee Department of Revenue publishes the "
                    "rules; the vendor should be able to show how they have applied them.",
                    "The second is storage, which in a Memphis summer is not just a question of "
                    "space. Anything fabric, anything with adhesive, and anything that warps is "
                    "affected by where it spends the hot months. An uninsulated garage is "
                    "storage in the sense that the item is in it, and not always in the sense "
                    "that the item survives the year.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The authorities behind the local factors above:",
                "cites": [
                    {"id": "tn-sales-and-use-tax",
                     "used_for": "How Tennessee treats sales and use tax, which affects a rental-versus-purchase comparison."},
                    {"id": "noaa-climate-normals",
                     "used_for": "30-year climate normals, for what a Memphis storage environment is actually like across the year."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated local resources:",
                "links": [
                    ("https://porchandparty901.com/services/party-decor-memphis.html",
                     "party decor in Memphis",
                     "Styled setups where installation and strike are part of the service."),
                    ("https://porchandparty901.com/pricing.html", "Porch & Party pricing information",
                     "How one local vendor structures decor pricing."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about renting versus buying event decor",
                "qas": [
                    ("Is renting always more expensive over time?",
                     "Only if you ignore strike and storage. For anything large, the crew trips "
                     "to install and remove it are the dominant cost whether you own it or not, "
                     "and owning it adds a storage problem that renting does not."),
                    ("What is the threshold for buying?",
                     "There is no universal number, but the practical test is whether you will "
                     "use it more than a couple of times within a year and whether you have "
                     "somewhere to keep it that will not damage it."),
                    ("Who pays if a rented item is damaged?",
                     "That is set by the rental contract, and it is worth reading before the "
                     "event rather than after. Ask specifically what counts as damage and what "
                     "counts as normal wear."),
                    ("Why does tax matter to this decision?",
                     "Because a rental quote and a purchase quote may present tax differently, "
                     "which can make one look cheaper than it is. Asking for tax as a separate "
                     "line on both makes the comparison honest."),
                ],
            },
        ],
    },
]

PROFESSIONAL_PAGES = [
    {
        "lane": "professional",
        "shape": "checklist",
        "slug": "credit-report-dispute-letter-checklist.html",
        "published": PUBLISHED,
        "title": "What Belongs in a Credit Report Dispute Letter",
        "h1": "What Belongs in a Credit Report Dispute Letter",
        "eyebrow": "Checklist from federal consumer guidance",
        "description": ("The seven items federal consumer guidance says a mailed credit dispute "
                        "letter should contain, where to get your reports free, and who to send it to."),
        "direct_answer": (
            "The Consumer Financial Protection Bureau publishes what a mailed dispute letter "
            "should include: your full contact details, the report confirmation number if you "
            "have one, each error and its account number, a clear explanation of why it is "
            "wrong, a request that it be removed or corrected, a copy of the report portion with "
            "the items marked, and copies rather than originals of supporting documents. Dispute "
            "with both the credit reporting company and the company that supplied the information."),
        "recommends": (
            "Get your reports free from the official federal site first, then write one letter "
            "per bureau containing the seven items below, and keep proof of delivery."),
        "boundary": (
            "This page summarises published federal consumer guidance and links to it. It is "
            "educational only. It does not review anyone's credit report and cannot say what "
            "outcome a particular dispute will have."),
        "sections": [
            {
                "type": "prose",
                "h2": "Two places to dispute, not one",
                "paras": [
                    "The Consumer Financial Protection Bureau states that fixing an error "
                    "generally means contacting both the credit reporting company and the "
                    "company that provided the information. This is the part most often missed. "
                    "Disputing only with the bureau leaves the original furnisher still holding "
                    "the record it reported, and the same item can reappear.",
                    "The three nationwide credit reporting companies are Experian, Equifax and "
                    "TransUnion, and an error may appear on one report and not on the others. "
                    "That is why the guidance is to check all three rather than assuming they match.",
                    "If the error appears to be the result of identity theft, the CFPB directs "
                    "people to IdentityTheft.gov, the federal government's resource for "
                    "reporting and recovering from identity theft. That is a different process "
                    "from an ordinary dispute and it is worth using the right one.",
                ],
            },
            {
                "type": "list",
                "h2": "The seven items a mailed dispute letter should contain",
                "ordered": True,
                "intro": ("This list follows the Consumer Financial Protection Bureau's published "
                          "guidance on what a mailed dispute letter should include."),
                "items": [
                    "Your contact information, including complete name, address and telephone number.",
                    "The credit report confirmation number, if you have one.",
                    "Each error you want fixed, including the account number for any account being disputed.",
                    "A clear explanation of why you are disputing the information.",
                    "A request that the information be removed or corrected.",
                    "A copy of the portion of your credit report containing the disputed items, with those items circled or highlighted.",
                    "Copies, not originals, of documents that support your position.",
                ],
            },
            {
                "type": "table",
                "h2": "Getting the reports before you write anything",
                "intro": ("You cannot mark up a report you do not have. The Federal Trade "
                          "Commission publishes what is available free and where."),
                "headers": ["What", "What federal guidance says", "Where"],
                "rows": [
                    ["Annual free reports",
                     "You have the right to free copies from each of the three major bureaus once every 12 months",
                     "AnnualCreditReport.com"],
                    ["Weekly free reports",
                     "The three bureaus have permanently extended a programme allowing a free report from each weekly",
                     "AnnualCreditReport.com"],
                    ["Additional Equifax reports",
                     "Anyone in the U.S. can get 6 free Equifax reports per year through 2026, in addition to the above",
                     "The Equifax website, or by phone"],
                    ["Why it matters",
                     "Credit report information can affect borrowing cost, insurance, renting and some hiring decisions",
                     "Federal Trade Commission consumer guidance"],
                ],
            },
            {
                "type": "prose",
                "h2": "Sending it so you can prove you sent it",
                "paras": [
                    "The CFPB notes that you can choose to send a dispute letter by certified "
                    "mail and ask for a return receipt, so that you have a record the letter was "
                    "received. That record costs very little and is the difference between a "
                    "dispute you can evidence and one you can only describe.",
                    "Disputes can also be filed online or by phone with each of the three "
                    "nationwide companies. The CFPB page linked below lists the current routes "
                    "for each. Contact details and web addresses change, so use the agency page "
                    "rather than a number copied from anywhere else, including this one.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "Everything above is drawn from these federal consumer resources:",
                "cites": [
                    {"id": "cfpb-dispute-credit-report-error",
                     "used_for": "What a mailed dispute letter should include, and the instruction to dispute with both the bureau and the furnisher."},
                    {"id": "ftc-disputing-credit-report-errors",
                     "used_for": "Free report entitlements, including the weekly programme and the additional Equifax reports through 2026."},
                    {"id": "ftc-free-credit-reports",
                     "used_for": "Which credit reports are free and which sites charge."},
                    {"id": "annualcreditreport-official",
                     "used_for": "The site federal law directs consumers to for free reports from the three nationwide bureaus."},
                    {"id": "cfpb-credit-reports-and-scores",
                     "used_for": "What a credit report contains and who may see it."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": ("Affiliated document-preparation resources. Approval Prep is not a "
                          "credit-repair company: it helps people write their own truthful "
                          "documents and does not contact bureaus or creditors on anyone's behalf."),
                "links": [
                    ("https://approvalprep.com/credit-letter-kit", "create a credit dispute letter",
                     "A self-service kit for drafting your own dispute letter."),
                    ("https://approvalprep.com/not-a-credit-repair-company",
                     "what Approval Prep does and does not do",
                     "The service boundary, stated plainly."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about credit report disputes",
                "qas": [
                    ("Do I have to dispute with all three bureaus?",
                     "An error may appear on one report and not the others, so the practical "
                     "answer is to check all three and dispute with each one that carries the "
                     "error. Federal guidance also directs you to contact the company that "
                     "supplied the information, not only the bureau."),
                    ("Should I send originals of my documents?",
                     "No. The CFPB guidance is explicit that you should send copies, not "
                     "originals, of documents supporting your position."),
                    ("Is AnnualCreditReport.com the official site?",
                     "Yes. It is the site federal law directs consumers to for their free "
                     "reports from the three nationwide credit reporting companies, and the FTC "
                     "points people there."),
                    ("Can anyone guarantee an item will be removed?",
                     "No, and a claim that an accurate item can be removed on request should be "
                     "treated with suspicion. A dispute asks for information that is wrong to be "
                     "corrected or removed; it is not a mechanism for deleting accurate history."),
                ],
            },
        ],
    },
    {
        "lane": "professional",
        "shape": "cost",
        "slug": "uscis-medical-exam-what-it-costs-and-the-sealed-envelope.html",
        "published": PUBLISHED,
        "title": "The USCIS Medical Exam: What Sets the Cost and Why the Envelope Stays Sealed",
        "h1": "The USCIS Medical Exam: What Sets the Cost and Why the Envelope Stays Sealed",
        "eyebrow": "Cost structure and procedure, from the agency",
        "description": ("Who sets the fee for a Form I-693 immigration medical examination, why the "
                        "civil surgeon seals the envelope, and what changes when you file online."),
        "direct_answer": (
            "The examination fee is set by the civil surgeon, not by USCIS, which is why quotes "
            "differ between clinics in the same city. USCIS requires that the civil surgeon give "
            "you a completed Form I-693 signed and placed in a sealed envelope. If you file Form "
            "I-485 by mail, that envelope stays sealed and goes with your package. If you file "
            "online, USCIS instructs you to open it and upload the form, then keep the original "
            "and the envelope until a final decision is made."),
        "recommends": (
            "Confirm the clinician is a designated civil surgeon using the official USCIS "
            "locator before booking, and ask the clinic to itemise the examination fee separately "
            "from vaccinations and any laboratory work."),
        "boundary": (
            "This page describes published agency procedure and links to it. It is educational "
            "only, is not immigration or medical advice, and cannot tell any individual what "
            "their case requires."),
        "sections": [
            {
                "type": "prose",
                "h2": "Why two clinics quote different amounts",
                "paras": [
                    "The immigration medical examination is performed by a civil surgeon "
                    "designated for that purpose, and the fee for the examination is the "
                    "clinic's, not a government charge. That single fact explains most of the "
                    "confusion around cost: people expect a fixed federal price and find a range.",
                    "The examination fee is also not the whole bill. Vaccinations required to "
                    "complete the vaccination record are a separate cost, and how many you need "
                    "depends on what you can document having already received. Laboratory work "
                    "may be separate again. A clinic that quotes one number without saying which "
                    "of these it covers is not necessarily being evasive, but the quote cannot "
                    "be compared to another clinic's until it is broken out.",
                    "This publication does not publish a price range for the examination, "
                    "because it has not surveyed civil surgeon fees and a range invented for the "
                    "sake of completeness would be worse than none. Call two designated civil "
                    "surgeons and ask them to itemise.",
                ],
            },
            {
                "type": "table",
                "h2": "What to ask a clinic to itemise",
                "intro": ("Ask for each line separately. This is the only way two quotes become "
                          "comparable."),
                "headers": ["Line item", "Why it varies", "What to ask"],
                "rows": [
                    ["Examination fee",
                     "Set by the civil surgeon, not by USCIS",
                     "What is the fee for the examination alone?"],
                    ["Vaccinations",
                     "Depends on which you can document having already received",
                     "Which vaccinations will I need given my records, and what does each cost?"],
                    ["Laboratory work",
                     "May be billed by the clinic or by an outside laboratory",
                     "Is laboratory work included, and who bills me for it?"],
                    ["Follow-up visit",
                     "Sometimes required to complete the record",
                     "Is a second visit likely, and is it charged separately?"],
                    ["Records review",
                     "Bringing documentation can reduce what has to be repeated",
                     "What records should I bring so nothing is repeated unnecessarily?"],
                    ["Replacement form",
                     "If a form is lost or an envelope is opened improperly",
                     "What happens, and what does it cost, if the form has to be reissued?"],
                ],
            },
            {
                "type": "list",
                "h2": "The sealed envelope rule, step by step",
                "ordered": True,
                "intro": ("This is the procedural detail that most often goes wrong, and USCIS "
                          "publishes it directly."),
                "items": [
                    "The civil surgeon completes and signs Form I-693 and places it in a sealed envelope.",
                    "USCIS states you must submit Form I-693 when you file Form I-485.",
                    "If you file Form I-485 by mail, the envelope stays sealed and goes in the application package.",
                    "If you file Form I-485 online, USCIS instructs you to open the sealed envelope and upload the completed form with your package.",
                    "In the online case, keep the original form and the envelope until USCIS makes a final decision on the I-485.",
                    "USCIS may review the original, or ask you to submit it as evidence, including at an interview.",
                    "Confirm the clinician is a designated civil surgeon before the appointment, using the official locator.",
                ],
            },
            {
                "type": "prose",
                "h2": "Where the requirement itself comes from",
                "paras": [
                    "The examination is not a clinic policy or a USCIS preference. The "
                    "requirement sits in federal regulation, and the text is publicly readable "
                    "in the Electronic Code of Federal Regulations at 8 CFR part 232. Reading "
                    "the regulation is not necessary for most applicants, but knowing it exists "
                    "is useful when someone offers a shortcut around it.",
                    "Forms, editions and procedures change, sometimes between one filing and the "
                    "next. The USCIS page for Form I-693 is the authoritative place to check the "
                    "current edition and the current instructions, and it is linked below. "
                    "Nothing on this page should be relied on in place of it.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The agency and regulatory sources behind this page:",
                "cites": [
                    {"id": "uscis-i-693",
                     "used_for": "The sealed-envelope requirement, the online and mail filing difference, and the instruction to retain the original."},
                    {"id": "uscis-find-civil-surgeon",
                     "used_for": "The official way to confirm a clinician is a designated civil surgeon."},
                    {"id": "ecfr-8-232-1",
                     "used_for": "The federal regulation that establishes the examination requirement."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated educational resources on this subject:",
                "links": [
                    ("https://uscisexam.com/guides/costs-and-timeframes/",
                     "USCIS medical exam costs and timeframes",
                     "A longer educational guide to cost structure and timing."),
                    ("https://uscisexam.com/guides/", "USCIS medical exam guides",
                     "General preparation guides for the immigration medical examination."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about the immigration medical examination",
                "qas": [
                    ("Does USCIS set the price of the exam?",
                     "No. The examination fee is charged by the civil surgeon, which is why "
                     "clinics in the same city quote different amounts. Ask for the examination "
                     "fee separately from vaccinations and laboratory work."),
                    ("Can I open the sealed envelope?",
                     "It depends on how you file. USCIS instructs online filers to open the "
                     "envelope and upload the completed form, keeping the original and envelope "
                     "until a final decision. For a mailed Form I-485, the envelope goes in "
                     "sealed. Follow the current USCIS instructions for your filing method."),
                    ("How do I know a doctor is a civil surgeon?",
                     "Use the official USCIS civil surgeon locator. A clinic describing itself as "
                     "an immigration exam provider is not the same as being designated, and the "
                     "locator is the authoritative check."),
                    ("Why does this page not give a price?",
                     "Because this publication has not surveyed civil surgeon fees and will not "
                     "print a number it cannot support. The itemisation table above is designed "
                     "to get a real quote from two clinics instead."),
                ],
            },
        ],
    },
    {
        "lane": "professional",
        "shape": "comparison",
        "slug": "recovery-residence-levels-of-support-comparison.html",
        "published": PUBLISHED,
        "title": "Comparing Recovery Residences by Level of Support",
        "h1": "Comparing Recovery Residences by Level of Support",
        "eyebrow": "Comparison against a national standard",
        "description": ("Recovery residences are described by four levels of support under the NARR "
                        "Standard. What the levels framework is, what to ask, and where the national "
                        "helpline is."),
        "direct_answer": (
            "Recovery residences are not interchangeable, and the vocabulary for telling them "
            "apart already exists. The National Alliance for Recovery Residences publishes a "
            "national Standard that defines the spectrum of recovery-oriented housing and "
            "distinguishes four residence types, referred to as levels or levels of support. "
            "Asking which level a residence is certified at is a far better question than asking "
            "whether it is a good one."),
        "recommends": (
            "Ask which level of support a residence corresponds to and whether it is certified by "
            "a NARR affiliate, then compare residences within the same level rather than across levels."),
        "boundary": (
            "This page explains a published national framework and links to it. It is educational "
            "only, is not clinical or treatment advice, and does not evaluate, endorse or rank "
            "any residence."),
        "sections": [
            {
                "type": "prose",
                "h2": "Why families end up comparing things that are not comparable",
                "paras": [
                    "Families researching recovery housing usually start by comparing whatever "
                    "they can see: photographs, monthly cost, and how quickly someone answers "
                    "the phone. Those are all real, and none of them tells you what kind of "
                    "residence it is.",
                    "There is an established framework for that. The National Alliance for "
                    "Recovery Residences publishes the NARR Standard, which it describes as "
                    "defining the spectrum of recovery-oriented housing and services and "
                    "distinguishing four residence types referred to as levels, or levels of "
                    "support. The Standard was developed with input from regional and national "
                    "recovery housing organisations and from providers representing all four levels.",
                    "NARR describes the Standard as built on the lived experience of operators "
                    "and residents rather than the decisions of an external accreditation body, "
                    "and as grounded in the Social Model, a community-based approach built on "
                    "shared lived experience, support and structure. NARR also publishes a Code "
                    "of Ethics that owners, operators, staff and volunteers in affiliate "
                    "organisations are expected to follow.",
                ],
            },
            {
                "type": "table",
                "h2": "What to compare, and what the answer tells you",
                "intro": ("Ask each residence the same questions. Comparing two residences at "
                          "different levels of support tells you less than comparing two at the same level."),
                "headers": ["Question", "Why it matters", "Where the answer should come from"],
                "rows": [
                    ["Which level of support does this residence correspond to?",
                     "It places the residence on the published national spectrum",
                     "The residence, checkable against the NARR Standard"],
                    ["Is it certified, and by which NARR affiliate?",
                     "Certification is done through affiliate organisations rather than by the residence itself",
                     "The residence, and the state affiliate"],
                    ["Does it follow the NARR Code of Ethics?",
                     "NARR expects owners, operators, staff and volunteers in affiliates to adhere to it",
                     "The residence, in writing"],
                    ["What is the structure of a typical week?",
                     "It distinguishes levels far better than a description of the house does",
                     "The residence"],
                    ["What are the house rules and how are they enforced?",
                     "This is where most placements succeed or fail in the first month",
                     "The residence, in writing before moving in"],
                    ["What happens if someone returns to use?",
                     "The policy differs sharply between residences and should be known in advance",
                     "The residence, in writing"],
                    ["What is included in the fee and what is extra?",
                     "It makes two residences comparable on cost",
                     "The residence, itemised"],
                ],
            },
            {
                "type": "list",
                "h2": "How to run the comparison",
                "ordered": True,
                "intro": "A sequence that keeps the comparison honest.",
                "items": [
                    "Read the NARR Standard page first so the levels vocabulary is familiar before any call.",
                    "Ask each residence which level of support it corresponds to.",
                    "Group the shortlist by level, and compare within groups.",
                    "Ask each one about certification and which affiliate certified it.",
                    "Ask for house rules and the return-to-use policy in writing.",
                    "Ask what a typical week actually contains, hour by hour.",
                    "Ask what is included in the fee and what is billed separately.",
                    "Confirm what happens at the end of a stay and how transitions are supported.",
                ],
            },
            {
                "type": "prose",
                "h2": "If the immediate need is help rather than a comparison",
                "paras": [
                    "Research is the right activity when there is time for it. When there is "
                    "not, the Substance Abuse and Mental Health Services Administration operates "
                    "a National Helpline, a free and confidential federal service available "
                    "around the clock, and that is a better first call than any comparison exercise.",
                    "This publication is not a referral service and cannot assess anyone's "
                    "situation. It can point at the national standard that makes residences "
                    "comparable and at the federal helpline that exists for the moment when "
                    "comparison is not what is needed.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The national standard and federal service referenced above:",
                "cites": [
                    {"id": "narr-standards",
                     "used_for": "The NARR Standard, the four levels of support, the Social Model basis and the Code of Ethics."},
                    {"id": "samhsa-national-helpline",
                     "used_for": "The free, confidential federal helpline available around the clock."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated resources on recovery housing:",
                "links": [
                    ("https://www.diannesplacerecoveryservices.com/recovery-housing/",
                     "recovery housing information",
                     "Plain-language information about recovery housing."),
                    ("https://www.diannesplacerecoveryservices.com/answers/",
                     "plain-language recovery housing answers",
                     "Common questions from families and referrers."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask when comparing recovery residences",
                "qas": [
                    ("What are the levels of support?",
                     "The NARR Standard distinguishes four residence types, referred to as levels "
                     "or levels of support, which together define the spectrum of "
                     "recovery-oriented housing. NARR publishes the framework; the Standards page "
                     "is linked in the sources above."),
                    ("Is certification required?",
                     "Requirements differ by state, and certification is carried out through NARR "
                     "affiliate organisations. Asking which affiliate certified a residence, and "
                     "when, is a more useful question than asking whether it is certified in the abstract."),
                    ("Does this page recommend a residence?",
                     "No. This publication does not evaluate, endorse or rank residences. It "
                     "explains the published framework that lets a family run its own comparison."),
                    ("What if we need help right now?",
                     "SAMHSA operates a National Helpline that is free, confidential and "
                     "available at any hour. It is linked in the sources section above."),
                ],
            },
        ],
    },
    {
        "lane": "professional",
        "shape": "checklist",
        "slug": "lender-document-request-checklist.html",
        "published": PUBLISHED,
        "title": "Answering a Lender Document Request Without Restarting the File",
        "h1": "Answering a Lender Document Request Without Restarting the File",
        "eyebrow": "Checklist for loan applicants",
        "description": ("Why underwriters ask for the documents they ask for, how to answer a request "
                        "completely the first time, and which federal resources explain the underlying ratios."),
        "direct_answer": (
            "A lender document request is usually not suspicion; it is an underwriter reconciling "
            "your file against published requirements. Answer it completely the first time, in one "
            "package, with each document labelled to the item it answers. A partial answer restarts "
            "the clock, and every restart adds days."),
        "recommends": (
            "Answer the whole request in a single labelled package rather than sending documents as "
            "you find them, and use the federal explainers below to understand what the underwriter "
            "is calculating."),
        "boundary": (
            "This page explains general documentation practice and links to federal consumer "
            "resources. It is educational only and is not financial, lending or legal advice."),
        "sections": [
            {
                "type": "prose",
                "h2": "The request is a reconciliation, not an accusation",
                "paras": [
                    "Borrowers commonly read a document request as a sign the application is in "
                    "trouble. Usually it is the opposite: the file is being worked, and the "
                    "underwriter has found a gap between what the application says and what the "
                    "documents currently prove.",
                    "Lenders selling loans into the secondary market work to published "
                    "requirements. Fannie Mae, for example, publishes its Selling Guide, and the "
                    "documentation an underwriter asks for traces back to requirements of that "
                    "kind rather than to personal judgement. Knowing that changes the tone of the "
                    "response: the task is to close a specific gap, not to persuade anyone.",
                    "It also explains why requests can feel repetitive. A document that resolves "
                    "one requirement may raise a question against another, which is why a "
                    "deposit shown on a statement can generate a follow-up even though the "
                    "statement was what was asked for.",
                ],
            },
            {
                "type": "table",
                "h2": "What common requests are usually reconciling",
                "intro": ("Understanding the purpose of a request makes it much easier to answer "
                          "in one pass."),
                "headers": ["Request", "What the underwriter is reconciling", "What a complete answer includes"],
                "rows": [
                    ["Recent pay statements",
                     "That stated income matches documented income",
                     "Consecutive periods, unredacted, showing year-to-date figures"],
                    ["Full bank statements",
                     "That funds exist and where they came from",
                     "Every page, including pages that appear blank"],
                    ["Explanation of a large deposit",
                     "That the deposit is not undisclosed borrowing",
                     "A short factual note plus the document evidencing the source"],
                    ["Explanation of an employment gap",
                     "That income is stable and likely to continue",
                     "Dates, what happened, and what the current position is"],
                    ["Self-employment records",
                     "That business income is real and sustainable",
                     "The specific returns and statements named, for the exact periods named"],
                    ["Identity or address documents",
                     "That records across the file agree with each other",
                     "The document that reconciles the mismatch, not a restatement of it"],
                ],
            },
            {
                "type": "list",
                "h2": "The checklist for answering a request",
                "ordered": True,
                "intro": "Work through this before sending anything.",
                "items": [
                    "Read the whole request and list every distinct item before you start gathering.",
                    "Send one complete package rather than documents as you find them.",
                    "Label each file with the item number or wording it answers.",
                    "Include every page of any statement, including pages that look blank.",
                    "Keep explanations factual and short: what happened, when, and what is true now.",
                    "Never alter a document. Explain it instead.",
                    "If something does not exist, say so plainly and say what does exist in its place.",
                    "Keep a copy of exactly what you sent and when you sent it.",
                    "Ask the loan officer to confirm the package is complete before the clock restarts.",
                ],
            },
            {
                "type": "prose",
                "h2": "Understanding what is being calculated",
                "paras": [
                    "Two federal explainers do most of the work here. The Consumer Financial "
                    "Protection Bureau publishes an explanation of the debt-to-income ratio, "
                    "which is the calculation much of the income documentation feeds. It also "
                    "publishes a Loan Estimate explainer, covering the standardised disclosure "
                    "that makes two mortgage offers comparable line by line.",
                    "Neither of those will tell you what a specific underwriter will decide. What "
                    "they do is make the request legible, and a borrower who understands what is "
                    "being calculated tends to answer more completely and argue less, which is "
                    "the behaviour that actually shortens a file.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The federal and industry references behind this page:",
                "cites": [
                    {"id": "cfpb-debt-to-income-ratio",
                     "used_for": "What a debt-to-income ratio is and what the income documentation feeds."},
                    {"id": "cfpb-loan-estimate",
                     "used_for": "The standardised disclosure that makes two mortgage offers comparable."},
                    {"id": "cfpb-loan-options",
                     "used_for": "How loan types differ in what they require."},
                    {"id": "fannie-mae-selling-guide",
                     "used_for": "The published guide behind many of the documentation requirements an underwriter applies."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": ("Affiliated document-preparation resources. Approval Prep is not a "
                          "credit-repair company and does not contact lenders on anyone's behalf."),
                "links": [
                    ("https://approvalprep.com/mortgage-document-checklist",
                     "what to prepare for a mortgage review",
                     "A checklist of what a mortgage file typically requires."),
                    ("https://approvalprep.com/loan-prep-letter-kit", "create a loan explanation letter",
                     "A self-service kit for drafting your own explanation letter."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions people ask about lender document requests",
                "qas": [
                    ("Why do they want every page of a statement?",
                     "Because a missing page is an unverifiable gap, and an underwriter cannot "
                     "confirm what is not there. Pages that appear blank are still part of the "
                     "sequence and are usually required."),
                    ("Does a document request mean I am being declined?",
                     "Not by itself. A request generally means the file is being actively worked "
                     "and a specific gap has been identified between the application and the "
                     "supporting documents."),
                    ("Should I explain everything preemptively?",
                     "Answer what is asked, completely and factually. Volunteering long "
                     "narratives about matters not raised tends to generate further questions "
                     "without resolving the original one."),
                    ("What if a document genuinely does not exist?",
                     "Say so plainly and describe what does exist instead. Altering or "
                     "reconstructing a document is never the answer and creates a far worse problem."),
                ],
            },
        ],
    },
    {
        "lane": "professional",
        "shape": "comparison",
        "slug": "workplace-mental-health-training-vs-therapy.html",
        "published": PUBLISHED,
        "title": "Workplace Mental Health Training and Therapy Are Not the Same Purchase",
        "h1": "Workplace Mental Health Training and Therapy Are Not the Same Purchase",
        "eyebrow": "Comparison for employers scoping a programme",
        "description": ("What workplace wellbeing training can and cannot do, where clinical care and "
                        "legal rights begin, and which federal bodies publish the boundaries."),
        "direct_answer": (
            "Workplace mental health training is an education purchase aimed at managers and "
            "teams. Therapy is clinical care for an individual. Legal obligations toward an "
            "employee with a mental health condition are a third thing again, set by employment "
            "law rather than by either. Buying one while needing another is the most common and "
            "most expensive mistake in this area."),
        "recommends": (
            "Decide which of the three you are actually buying before writing a brief, and keep "
            "the training scope separate from clinical care and from your obligations as an employer."),
        "boundary": (
            "This page distinguishes categories of service and links to federal resources on "
            "workplace rights. It is educational only, is not legal or clinical advice, and does "
            "not assess any workplace or any individual."),
        "sections": [
            {
                "type": "prose",
                "h2": "Three different things, routinely conflated",
                "paras": [
                    "An organisation that has noticed a problem usually describes it as a "
                    "wellbeing problem and starts looking for a wellbeing supplier. That framing "
                    "collapses three separate things into one purchase order.",
                    "The first is education: training that helps managers notice, respond and "
                    "refer appropriately, and helps teams talk about workload without it becoming "
                    "a disciplinary conversation. This is what a training engagement can genuinely deliver.",
                    "The second is clinical care for an individual, which is a therapeutic "
                    "relationship between a licensed clinician and a person, not a service an "
                    "employer purchases on someone's behalf or has visibility into.",
                    "The third is legal obligation. The Equal Employment Opportunity Commission "
                    "publishes guidance on depression, PTSD and other mental health conditions in "
                    "the workplace and the legal rights that attach to them, along with a wider "
                    "set of disability-related resources. That is a compliance question, and no "
                    "training programme resolves it.",
                ],
            },
            {
                "type": "table",
                "h2": "Which purchase answers which problem",
                "intro": ("Match the problem you actually have to the category that can address "
                          "it. Most disappointing engagements are a mismatch in this table."),
                "headers": ["The problem", "What it needs", "What it is not"],
                "rows": [
                    ["Managers do not know how to respond when someone is struggling",
                     "Training and clear internal referral routes",
                     "Not therapy, and not a policy document alone"],
                    ["An individual needs clinical support",
                     "A licensed clinician, through an appropriate route",
                     "Not a training session, and not a manager's responsibility to provide"],
                    ["An employee has requested an accommodation",
                     "An employment law process, informed by EEOC guidance",
                     "Not a wellbeing programme decision"],
                    ["Workload is the actual cause",
                     "An operational change to how work is allocated",
                     "Not resilience training layered on an unchanged workload"],
                    ["Someone needs help outside working hours",
                     "A published external service such as the SAMHSA National Helpline",
                     "Not an internal channel that is unstaffed at night"],
                    ["Leadership wants to know if anything changed",
                     "Agreed measures set before the programme starts",
                     "Not attendance figures or satisfaction scores alone"],
                ],
            },
            {
                "type": "list",
                "h2": "Questions to settle before writing a brief",
                "ordered": True,
                "intro": "Answering these first prevents most scope failures.",
                "items": [
                    "Which of the three categories is this: education, clinical care, or a legal obligation?",
                    "Who is the audience: managers, a specific team, or the whole organisation?",
                    "What will be different afterwards, stated as an observable change?",
                    "What are the confidentiality boundaries, and who has told staff about them?",
                    "Where does an individual go for clinical support, and is that route published internally?",
                    "Is workload or job design a cause here, and is anyone empowered to change it?",
                    "How will you know whether it worked, and was that measure agreed beforehand?",
                    "Who handles an accommodation request, and do they know the applicable guidance?",
                ],
            },
            {
                "type": "prose",
                "h2": "The workload question underneath most requests",
                "paras": [
                    "The Occupational Safety and Health Administration publishes material on "
                    "workplace stress, which frames job stress as a workplace matter rather than "
                    "purely an individual one. That framing matters commercially as well as "
                    "ethically: where the cause is how work is designed and allocated, training "
                    "individuals to cope better is treating a structural problem as a personal one.",
                    "Good training providers say this out loud, and it is a reasonable thing to "
                    "ask a prospective provider directly. A provider who agrees that training "
                    "alone cannot fix a workload problem is describing their scope honestly, "
                    "which is a better signal than one who accepts the brief as written.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The federal resources that set the boundaries described above:",
                "cites": [
                    {"id": "eeoc-mental-health-rights",
                     "used_for": "Employee legal rights relating to mental health conditions in the workplace."},
                    {"id": "eeoc-disability-resources",
                     "used_for": "The agency's wider resource set on disability and accommodation."},
                    {"id": "osha-workplace-stress",
                     "used_for": "The workplace-safety framing of job stress, as distinct from clinical care."},
                    {"id": "samhsa-national-helpline",
                     "used_for": "A free, confidential federal helpline available at any hour."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated resources on workplace wellbeing:",
                "links": [
                    ("https://www.hicksconsulting.org/corporate-speaking/",
                     "workplace mental-health speaking programs",
                     "Education-focused workplace programmes."),
                    ("https://www.hicksconsulting.org/faq/", "Hicks Consulting FAQ",
                     "Service boundaries between training, coaching and therapy."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions employers ask when scoping a wellbeing programme",
                "qas": [
                    ("Can a training provider also provide therapy to our staff?",
                     "These are distinct services with distinct boundaries, and combining them "
                     "raises confidentiality and role questions that should be settled explicitly "
                     "before any engagement rather than assumed."),
                    ("Does training satisfy our legal obligations?",
                     "No. Obligations toward an employee with a mental health condition are set "
                     "by employment law. The EEOC publishes guidance on those rights, and a "
                     "training programme is not a substitute for following it."),
                    ("How do we measure whether it worked?",
                     "Agree the measure before the programme starts, and make it observable. "
                     "Attendance and satisfaction scores tell you the session happened, not that "
                     "anything changed."),
                    ("What if the real problem is workload?",
                     "Then training individuals to cope better will disappoint, and it is worth "
                     "saying so during scoping. OSHA's material on workplace stress treats job "
                     "stress as a workplace matter, which supports raising it directly."),
                ],
            },
        ],
    },
    {
        "lane": "professional",
        "shape": "checklist",
        "slug": "horse-boarding-agreement-preparation-checklist.html",
        "published": PUBLISHED,
        "title": "What to Settle Before Signing a Horse Boarding Agreement",
        "h1": "What to Settle Before Signing a Horse Boarding Agreement",
        "eyebrow": "Checklist for horse owners",
        "description": ("The terms that cause most boarding disputes, what to get in writing before "
                        "the horse arrives, and why equine liability rules differ by state."),
        "direct_answer": (
            "Most boarding disputes come from a small number of terms nobody wrote down: who "
            "calls the veterinarian and who pays, what happens when board is late, what notice "
            "either side must give, and who is responsible for the horse during turnout and "
            "transport. Settle those in writing before the horse arrives. Equine liability rules "
            "differ from state to state, so the applicable law is a local question."),
        "recommends": (
            "Get the eleven items below written into the agreement before move-in, and check what "
            "your own state's equine activity statute provides rather than assuming a general rule."),
        "boundary": (
            "This page is general educational information about boarding arrangements. It is not "
            "legal advice, does not interpret any state statute, and does not review any contract."),
        "sections": [
            {
                "type": "prose",
                "h2": "Boarding disputes are usually about silence, not disagreement",
                "paras": [
                    "The typical boarding dispute is not two parties who disagreed about a term. "
                    "It is two parties who never discussed it, each assuming the ordinary "
                    "practice they were used to, and discovering the mismatch during an "
                    "emergency, a late payment, or a departure.",
                    "That makes the drafting stage disproportionately valuable. Every item on "
                    "the checklist below is cheap to agree in advance and expensive to resolve "
                    "afterwards, and none of them requires the parties to anticipate anything "
                    "exotic. They are the ordinary events of keeping a horse somewhere else.",
                    "There is a second reason to be specific. Liability for equine activities is "
                    "governed substantially at state level, and provisions differ between states, "
                    "including requirements around posted warnings and contract language. The "
                    "American Horse Council is the national industry body and a starting point "
                    "for understanding that landscape, but the operative law is your state's.",
                ],
            },
            {
                "type": "table",
                "h2": "The terms that generate disputes",
                "intro": ("For each, the question that is usually left unasked and the form a "
                          "workable answer takes."),
                "headers": ["Term", "The unasked question", "What a workable clause states"],
                "rows": [
                    ["Veterinary emergencies",
                     "Who decides when the owner cannot be reached?",
                     "A named decision-maker, a spending limit, and a contact sequence"],
                    ["Routine care",
                     "What is included in board and what is billed?",
                     "An itemised list of what board covers"],
                    ["Farrier and dental",
                     "Who schedules and who pays?",
                     "Whether the barn arranges it and how it is invoiced"],
                    ["Feed changes",
                     "Who may change the feeding programme?",
                     "That changes require the owner's agreement, with an exception for veterinary direction"],
                    ["Turnout",
                     "How much, with whom, and in what weather?",
                     "The normal turnout routine and who may vary it"],
                    ["Late board",
                     "What happens, and after how long?",
                     "A stated grace period, any late fee, and the escalation sequence"],
                    ["Notice to leave",
                     "How much notice does either side give?",
                     "A period in days, in both directions"],
                    ["Transport",
                     "Who is responsible during transport?",
                     "Who may transport, insurance position, and authority to do so"],
                    ["Insurance",
                     "Who insures what?",
                     "What each party carries and what evidence is exchanged"],
                    ["Access hours",
                     "When may the owner come?",
                     "Stated hours and any restrictions"],
                    ["Records",
                     "Who keeps them and who can see them?",
                     "Where records are kept and how the owner obtains copies"],
                ],
            },
            {
                "type": "list",
                "h2": "Before the horse arrives",
                "ordered": True,
                "intro": "A sequence that surfaces mismatches while they are still cheap.",
                "items": [
                    "Visit at an ordinary time, not only by appointment.",
                    "Ask how veterinary emergencies have actually been handled in the past year.",
                    "Get the full fee schedule, including everything billed outside board.",
                    "Read the whole agreement, including anything referred to but attached separately.",
                    "Confirm the notice period in both directions.",
                    "Confirm who may handle, ride or transport the horse.",
                    "Exchange emergency contacts and confirm they are current.",
                    "Photograph the horse's condition and record identifying marks on arrival.",
                    "Check what your state's equine activity statute requires, including any posting or contract language.",
                    "Keep a copy of the signed agreement and every invoice from the start.",
                ],
            },
            {
                "type": "prose",
                "h2": "Why the state matters more than the general rule",
                "paras": [
                    "People often look for a single answer to what a boarding contract must "
                    "contain, and there is not one. Equine activity liability is addressed "
                    "largely through state statutes that vary in scope, in what they require to "
                    "be posted or included in a contract, and in what protection they provide.",
                    "This publication does not interpret any of them. The honest position is that "
                    "the applicable rules are the ones in the state where the horse is kept, that "
                    "the American Horse Council is a reasonable starting point for the national "
                    "picture, and that a contract with real money or a valuable animal behind it "
                    "is worth having reviewed by someone who practises in that state.",
                ],
            },
            {
                "type": "sources",
                "h2": "Sources",
                "intro": "The industry body referenced above:",
                "cites": [
                    {"id": "american-horse-council",
                     "used_for": "The national industry body, and a starting point for state-by-state equine activity statutes."},
                ],
            },
            {
                "type": "affiliated",
                "h2": "Related resources",
                "intro": "Affiliated equine legal education resources:",
                "links": [
                    ("https://horselegalguide.com/boarding/what-should-be-included-in-a-horse-boarding-agreement/",
                     "horse boarding agreement checklist",
                     "A longer educational guide to boarding agreement terms."),
                    ("https://horselegalguide.com/compare/contract-review-vs-diy-horse-agreement/",
                     "contract review versus a DIY horse agreement",
                     "When a review is worth the cost and when it is not."),
                ],
            },
            {
                "type": "faq",
                "h2": "Questions horse owners ask about boarding agreements",
                "qas": [
                    ("Is a verbal boarding arrangement enforceable?",
                     "That depends on the state and the circumstances, which is exactly why it is "
                     "a poor basis for an arrangement involving a valuable animal. A written "
                     "agreement removes the question."),
                    ("What is the single most important clause?",
                     "In practice, the veterinary emergency clause. It is the term most likely to "
                     "be needed urgently and the one where an unresolved question does the most damage."),
                    ("Do equine liability statutes mean a barn is never responsible?",
                     "No. These statutes vary by state in scope and effect, and none of them is a "
                     "blanket release. What they provide in a particular state is a question for "
                     "someone who practises there."),
                    ("Should I have the contract reviewed?",
                     "For a short-term arrangement with a modest horse, many owners do not. Where "
                     "the animal is valuable, the term is long, or the fees are substantial, a "
                     "review by a lawyer in the relevant state is a proportionate step."),
                ],
            },
        ],
    },
]

PAGES = FOUNDER_PAGES + MEMPHIS_PAGES + PROFESSIONAL_PAGES
