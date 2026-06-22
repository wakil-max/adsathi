# AdSathi — Go-Live Playbook

This is the checklist to take AdSathi from the working demo to a product you can charge
clients for. The **software is done**; the items below are accounts, approvals, and config
that are legally/operationally yours and can't be coded for you.

Work top to bottom. You can start onboarding clients in **demo mode** (DRY_RUN=true) on day
one to validate demand while the Meta approval (step 3) is in review.

---

## 0. Run it locally (5 minutes)

```bash
cd backend
python3 -m app.main           # no pip install needed — pure stdlib, DRY_RUN defaults to true
```

(To enable live mode later: `pip install -r requirements.txt`, copy `.env.example` to `.env`,
and fill in the keys below.) **To deploy on Vercel, see VERCEL.md.**

Open http://127.0.0.1:8000 — sign up, chat ("I sell jackets in Dhaka, 500tk/day"),
generate creative, top up credits (auto-confirms in demo), and launch (dry-run). Everything
works without a single API key.

## 1. Deploy to a server

Easiest path with Docker:

```bash
cp backend/.env.example backend/.env   # edit values (see steps below)
docker compose up -d --build
```

Put it behind a domain with HTTPS (Caddy/Nginx + Let's Encrypt, or a host like Render/
Railway/Fly/DigitalOcean App Platform). Set `BASE_URL` and `META_OAUTH_REDIRECT` to your
real `https://app.yourdomain.com`. HTTPS is **required** by Facebook Login.

For scale, swap the SQLite layer in `backend/app/db.py` for managed Postgres (the schema is
standard SQL) and move generated images to S3/Cloudflare R2.

## 2. AI keys (captions + images)

- **Captions:** create an Anthropic API key → set `ANTHROPIC_API_KEY`, `LLM_PROVIDER=anthropic`.
- **Images:** create an OpenAI API key → set `IMAGE_API_KEY`, `IMAGE_PROVIDER=openai`.
  - For best Bangla headlines on images, drop a `NotoSansBengali-Bold.ttf` font file next to
    the app; `services/images.py` composites the headline as a real text layer.

You can turn these on independently of Meta — captions/images will be real while launches
stay dry-run until step 3 is done.

## 3. Meta (the gate to running real ads) — start this FIRST, it takes time

1. Go to developers.facebook.com → **Create App** → type **Business**.
2. Add products: **Marketing API** and **Facebook Login**.
3. Facebook Login settings → Valid OAuth Redirect URIs → add
   `https://app.yourdomain.com/connect/facebook/callback`.
4. Copy **App ID** and **App Secret** → set `META_APP_ID`, `META_APP_SECRET`.
5. Create a **Business Manager** (business.facebook.com) and complete **Business
   Verification** (business documents — trade license etc.). Mandatory for `ads_management`
   Advanced Access.
6. Submit **App Review** for: `ads_management`, `ads_read`, `business_management`,
   `pages_show_list`, `pages_read_engagement`. Provide a screencast of the connect→generate→
   launch flow and a description like:

   > "AdSathi lets Bangladeshi small businesses connect their own Facebook Page and ad
   > account, generate ad creative, and create campaigns on their behalf. We use
   > ads_management to create campaigns/ad sets/ads, ads_read for performance, and the page
   > permissions to publish from the user's selected Page."

7. Until Advanced Access is granted you can only operate on **your own** ad account
   (Standard Access) — perfect for piloting with your own agency account.
8. For production server-to-server, generate a **System User token** in Business settings and
   use it as the agency fallback (`META_AGENCY_TOKEN`, `META_AGENCY_AD_ACCOUNT_ID`,
   `META_AGENCY_PAGE_ID`).
9. Set `DRY_RUN=false`.

## 4. Payments (collect BDT from clients)

1. Register a merchant account with **SSLCommerz** (sslcommerz.com) — supports bKash, Nagad,
   Rocket, and cards. (Or use a bKash/Nagad merchant directly; the adapter lives in
   `backend/app/billing.py`.)
2. Set `SSLCZ_STORE_ID`, `SSLCZ_STORE_PASS`, and `SSLCZ_SANDBOX=true` to test, then `false`
   to go live.
3. Add your real success/IPN URLs in the SSLCommerz panel (they're already wired:
   `/billing/callback`, `/billing/ipn`).

## 5. Bangladesh compliance — the agency remittance model

To pay Meta in USD on behalf of clients who pay you in BDT, the clean route (per Bangladesh
Bank's Foreign Exchange Policy Department circular dated **17 June 2025**) is to operate as a
**local advertising agency**:

- Have a valid **trade license** and the client **agreements + invoices**.
- Deduct applicable **tax/VAT** from gross collections and keep proof of payment.
- Provide the **undertaking** that excess/erroneous remittance is returned.
- Talk to your bank (an AD/authorized-dealer branch) about the remittance setup; a banking/CA
  advisor is worth it here.

Build VAT into your pricing. Consider funding an **agency ad account** (Business Manager) and
running clients under it to reduce the account bans common with fresh BD ad accounts. Ramp
spend gradually.

> This is operational/regulatory guidance, not legal advice — confirm specifics with your
> bank and an accountant.

## 6. Pre-launch checklist

- [ ] HTTPS domain live, `BASE_URL` + redirect URI set
- [ ] Meta App Review approved (or piloting on your own ad account)
- [ ] Business Verification complete
- [ ] System user token + agency ad account configured
- [ ] AI keys set, `IMAGE_PROVIDER=openai`, Bengali font present
- [ ] SSLCommerz live credentials, a real test payment completed
- [ ] `DRY_RUN=false`
- [ ] Trade license + client agreement template + VAT handling ready
- [ ] Spend caps reviewed in `services/meta_ads.py`; ads launch PAUSED by default

## 7. Suggested pricing to clients

- Sell **credits** (default 10 BDT/credit; ~3 credits per ad created). Tune in `.env`.
- Add a **management fee or % of ad spend** under the agency model — this is also how you
  legally handle the BDT→USD remittance.
- Tiers: free trial (20 credits) → starter → pro/agency (multi-client).
