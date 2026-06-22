# AdSathi — AI Ad Creation & Launch Harness for Bangladesh

> Working product name: **AdSathi** ("ad companion"). A ChatGPT-style assistant where Bangladeshi
> businesses describe what they want to sell, get AI-generated ad images and bilingual (Bangla +
> English) captions, and launch Meta (Facebook/Instagram) ad campaigns automatically — all from a
> single chat.
>
> Video creative is intentionally **out of scope** for v1 and slotted for a later phase.

---

## 1. Vision

Most small and medium Bangladeshi businesses can't afford an agency and find Meta Ads Manager
intimidating and English-heavy. AdSathi collapses the whole funnel — creative + copy + campaign
setup + launch — into a chat conversation in the language they're comfortable with.

A shop owner types *"আমি শীতের জ্যাকেট বিক্রি করি, ঢাকায় ১৮-৩৫ বয়সীদের কাছে ৫০০ টাকা বাজেটে অ্যাড চালাতে চাই"*
("I sell winter jackets, want to run an ad to 18–35 year olds in Dhaka with a 500 taka budget") and
the assistant walks them through generating the image, writing the caption, choosing targeting, and
pressing launch.

### Who it's for
- D2C / Facebook-commerce sellers ("F-commerce") — the largest BD segment.
- Small retail shops, restaurants, salons, clinics, coaching centers.
- Freelance marketers and micro-agencies managing several clients.

---

## 2. End-to-end user flow

1. **Onboarding** — user signs up, connects their Facebook Business account / ad account (OAuth),
   selects the Facebook Page to advertise from.
2. **Brief** — in chat, the user describes the product, audience, budget, and goal in Bangla,
   English, or mixed ("Banglish"). The assistant asks only for what's missing.
3. **Creative generation** — assistant generates ad image option(s) and 2–3 bilingual caption
   variants. User can regenerate, tweak tone, or edit text inline.
4. **Campaign config** — assistant proposes objective, audience (location/age/gender/interests),
   placements, budget, and schedule, shown as an editable summary card.
5. **Review & launch** — user confirms; the backend creates the campaign → ad set → creative → ad
   via the Meta Marketing API. The ad starts in PAUSED state for a final human confirmation, then
   activates.
6. **Monitor** — a live dashboard pulls performance (reach, spend, results, CPR) and the assistant
   can suggest optimizations.

---

## 3. System architecture

```
                 +------------------------------------------------+
   Browser  ---> |  Chat Web App (ChatGPT-style UI)               |
   (Bangla/      |  - conversation thread + asset/preview panel   |
    English)     |  - campaign summary cards, launch button       |
                 +----------------+-------------------------------+
                                  | HTTPS / JSON (SSE for streaming)
                 +----------------v-------------------------------+
                 |  Backend API (orchestrator)                    |
                 |                                                |
                 |  - Conversation orchestrator (LLM + tools)     |
                 |  - Caption service  (bilingual copywriting)    |
                 |  - Image service    (provider-agnostic)        |
                 |  - Meta Ads service (campaign/adset/creative)  |
                 |  - Auth, accounts, billing/credits, jobs       |
                 +---+-----------+--------------+-----------------+
                     |           |              |
            +--------v--+  +-----v------+  +----v-------------+
            | LLM API   |  | Image gen  |  | Meta Marketing   |
            | (Claude)  |  | API        |  | Graph API        |
            +-----------+  +------------+  +------------------+
                     |
            +--------v-------------------------------+
            | Postgres (users, accounts, campaigns,  |
            | assets, credits) + object storage (S3) |
            +----------------------------------------+
```

The **orchestrator** is the heart: it interprets the chat, decides which "tool" to call
(`generate_caption`, `generate_image`, `propose_campaign`, `launch_campaign`, `get_insights`), runs
it, and streams the result back. This mirrors the prototype in this repo.

---

## 4. Recommended tech stack

For production, a single TypeScript codebase keeps the team small and the chat UX tight:

- **Frontend:** Next.js (React) + Tailwind. Chat thread on the left, live asset/preview panel on
  the right. Streaming via Server-Sent Events.
- **Backend:** Next.js API routes or a dedicated Node/NestJS service for orchestration. (The
  prototype in this repo uses **Python + FastAPI** because it boots instantly without a build step
  and is easy to read — the architecture maps 1:1 if you prefer to keep Python.)
- **Database:** Postgres (managed — Supabase/Neon/RDS). **Object storage:** S3 / Cloudflare R2 for
  generated images.
- **Queue/jobs:** a lightweight queue (BullMQ/Redis or Celery) for image generation and launch jobs
  so the chat stays responsive.
- **AI providers (pluggable):**
  - *Copy / conversation:* Claude (strong Bangla) or GPT-class models.
  - *Images:* a text-to-image API. Important caveat below on **Bangla text inside images.**
- **Hosting:** Vercel/Render/Fly for app; managed Postgres; CDN for assets.

> **Bangla-text-on-image caveat:** most diffusion image models render Bengali script poorly. The
> robust approach is to generate a clean *background/product image* with AI, then **composite the
> Bangla headline as a real text layer** (server-side with Pillow / node-canvas + a good Bengali
> font such as Noto Sans Bengali or Hind Siliguri). The prototype's image service is structured for
> exactly this two-step approach.

---

## 5. Meta Marketing API integration (the hard part)

Meta uses a strict three-tier hierarchy that the harness must build in order:

1. **Campaign** — objective (e.g. `OUTCOME_TRAFFIC`, `OUTCOME_SALES`, `OUTCOME_ENGAGEMENT`).
2. **Ad Set** — targeting (geo, age, gender, interests), placements, budget, schedule, bid.
3. **Ad Creative** — the image + caption + link + Page identity.
4. **Ad** — ties the creative to the ad set; this is what runs.

### Access & approvals (must-do before real launches)
- Create a **Meta App** and a **Business Manager**.
- Permissions needed: `ads_management`, `ads_read`, `business_management`, `pages_show_list`,
  `pages_read_engagement`.
- **Standard Access** works for assets you own (good for building/testing on your own ad account).
- **Advanced Access** is required to operate on *customers'* ad accounts in production. That gate
  requires **App Review** + **Business Verification**. Budget several weeks for this.
- Use **System User tokens** for server-to-server calls (they don't expire like user tokens).
- Pin the Graph API version; Meta deprecates old versions (e.g. legacy Advantage Shopping / App
  campaign APIs are being retired in the v25 era), so plan version upgrades.

### Safety rails built into the harness
- Always create ads in **PAUSED** status, surface a final human confirmation, then activate.
- Enforce per-account daily spend caps independent of Meta's own caps.
- Validate budget >= Meta's minimum for the chosen currency before submitting.
- Store every Meta API request/response for auditing and dispute handling.

---

## 6. Bangladesh-specific realities (this makes or breaks the product)

**Payments are the #1 friction.** Bangladeshi cards frequently fail for Meta due to low
international transaction limits, BIN blocks, and Bangladesh Bank foreign-currency controls. Plan
for one or more of:

- **Agency remittance model (recommended for v1).** Per a Bangladesh Bank Foreign Exchange Policy
  Department circular dated **17 June 2025**, local advertisers can pay for foreign-media ads
  *through a local advertising agency* without separate central-bank approval, subject to
  documentation (agreements, invoices, tax/VAT deduction, proof of tax payment, and an undertaking
  to return any excess remittance). This means AdSathi can operate as the licensed agency: users
  pay you in **BDT** (bKash/Nagad/card/bank), and you fund the ad spend on an agency ad account.
- **Agency ad accounts.** Running clients under an agency / Business Manager structure also reduces
  the random account bans that are common for fresh BD ad accounts.
- **Virtual dollar cards** as a fallback for users who want to use their own ad account.

**Tax/VAT:** Bangladesh applies VAT on digital ad services; build VAT handling and proper invoicing
into the billing module from day one.

**Account bans** are common in BD (billing issues, aggressive review). Mitigate with the agency
account structure, gradual spend ramp-up, and pre-launch policy checks on creatives.

**Localization:** full Bangla UI, BDT pricing, Bengali fonts, and culturally relevant creative
prompts (festivals like Eid / Pohela Boishakh, local payment logos, etc.).

---

## 7. Monetization

- **Credits / subscription** for content generation (per image / per caption batch).
- **Ad-spend markup or service fee** under the agency remittance model (e.g. a % of managed spend),
  which is also the cleanest way to handle the BDT->USD remittance legally.
- Tiered plans: free trial -> starter -> pro (multi-client for micro-agencies).

---

## 8. Roadmap

**Phase 0 — Prototype (this repo).** Chat orchestrator, bilingual caption generation, image
generation adapter (with Bangla-text compositing), Meta Ads service in **dry-run** mode. Runs
without any API keys so the flow is testable today.

**Phase 1 — MVP (~4–6 weeks).** Real AI providers wired in; Facebook OAuth + page/ad-account
connect; real campaign launch on *your own* ad account (Standard Access); Postgres + auth + asset
storage; basic insights dashboard; BDT credit billing.

**Phase 2 — Scale & compliance (~4–8 weeks).** App Review + Business Verification for Advanced
Access; agency remittance billing + VAT invoicing; multi-client management; spend caps, audit log,
policy pre-checks; Bangla UI polish.

**Phase 3 — Optimization & video.** AI optimization suggestions and auto-budget reallocation;
A/B creative testing; then **video ad generation** (the originally deferred piece).

---

## 9. Key risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Meta App Review / Business Verification delays | Build & demo on your own ad account first (Standard Access); start verification early. |
| BDT->USD payment friction & regulations | Operate under the 17 Jun 2025 agency remittance model; proper invoicing/VAT; virtual-card fallback. |
| Account bans | Agency BM structure, gradual ramp, pre-launch creative policy checks. |
| Bangla text garbled in AI images | Two-step pipeline: AI background + real Bengali text layer composited server-side. |
| Spend / launch mistakes | PAUSED-by-default, human confirmation, hard spend caps, full audit trail. |
| AI cost runaway | Credit metering, caching, cheaper models for routine copy. |

---

## 10. What's in this repo right now

- `PLAN.md` — this document.
- `backend/` — runnable **FastAPI** prototype: chat orchestrator + caption / image / Meta-ads
  services, all working in dry-run so you can test the full flow with no API keys.
- `frontend/index.html` — a ChatGPT-style chat UI that talks to the backend.
- `README.md` — how to run it.

See `README.md` to start the prototype.
