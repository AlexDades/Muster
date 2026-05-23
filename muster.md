# Muster — AI-Powered HR Policy Assistant

## What It Is

Muster is a SaaS product sold to corporations. It connects to a company's HR inbox (Gmail via IMAP/SMTP), reads internal policy documents (PDFs, DOCX), and automatically drafts or sends replies to employee questions — with citations to the relevant policy sections. It also includes **Veridas**, an in-dashboard chat assistant backed by the same RAG pipeline.

---

## Core Features

- Autonomous email replies in under 60 seconds
- Optional human-review mode (drafts only, no auto-send)
- Full audit trail: every response logged with source material
- Auto re-indexing when policy documents are updated
- Source citations in every reply so employees can verify
- In-browser chat assistant (Veridas) using the same RAG pipeline
- Onboarding policy sequences: scheduled drip emails to new employees (Phase 9)
- Policy versioning with update notifications (Phase 10)
- Role-based access (admin, reviewer, read-only)

---

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11 (Docker) / 3.9.6 (local dev) |
| AI model | Claude (Anthropic API) — claude-sonnet-4-6 |
| Document parsing | `pypdf` (PDF), `python-docx` (DOCX) |
| Vector store | ChromaDB (local, `/data/chroma_db` in production) |
| Embeddings | `all-MiniLM-L6-v2` via `sentence-transformers` (local, no API cost) |
| Email (primary) | Gmail IMAP (read) + SMTP (send) via App Password |
| Email (secondary) | Microsoft Graph API — OAuth stub present, not primary |
| Web framework | FastAPI (async, background tasks, slowapi rate limiting) |
| Database | SQLite (`/data/muster.db` in production) |
| Auth | API key → JWT (HS256); `MUSTER_API_KEY` env var sets the key |
| Deployment | Railway — `Dockerfile` + `railway.toml`; `/data` volume for persistence |
| Tunneling | ngrok auto-starts on `NGROK_AUTH_TOKEN` being set |

---

## Architecture

```
[Employee Email]
      |
      v
[Gmail Inbox]  ← IMAP (imaplib, stdlib only)
      |
      v
[Background Poller — asyncio task, every POLL_INTERVAL_SECONDS]
  - filters by ALLOWED_SENDERS allowlist (if set)
  - skips acknowledgments (<120 chars, no ?, matches gratitude regex)
  - extracts question text
      |
      v
[Retrieval Engine]
  - query embedded with all-MiniLM-L6-v2
  - top-K chunks retrieved from ChromaDB
      |
      v
[Response Generator]
  - Claude API called with: system prompt + policy chunks + question
  - secondary validation agent checks correctness
  - response includes cited policy sections
      |
      v
[Review Gate]
  - human_review_mode=True  → save draft, expose via /drafts for HR approval
  - human_review_mode=False → send automatically via Gmail SMTP
      |
      v
[Audit Logger]
  - logs: question, retrieved chunks, response, sender, timestamp, review status
      |
      v
[Gmail SMTP Send]  ← smtplib STARTTLS, stdlib only
```

---

## Implementation Plan

### Phase 1 — Document Indexing Engine  ✓ Complete
- Parse PDF and DOCX policy documents
- Chunk into passages (~500 tokens, 50-token overlap)
- Embed with `all-MiniLM-L6-v2`, store in ChromaDB
- Support add, update, delete

### Phase 2 — Retrieval + Answer Generation  ✓ Complete
- Accept plain-text question, retrieve top-K chunks
- Call Claude API with retrieved context
- Return answer with source citations
- Secondary validation agent: returns `{valid, confidence, issues, reasoning}`

### Phase 3 — Email Ingestion  ✓ Complete
- MockInbox for offline testing (local SQLite/JSON)
- GmailInbox for production (IMAP read, SMTP send)
- Poller extracts and feeds questions into Phase 2 pipeline

### Phase 4 — Response Delivery + Review Mode  ✓ Complete
- `human_review_mode` flag controls draft vs. auto-send
- DraftStore: approve (with optional edit) / reject
- Dispatcher handles both paths

### Phase 5 — Audit Trail + API Layer  ✓ Complete
- FastAPI routers: documents, drafts, audit, settings, inbox, auth
- SQLite audit table: question, answer, sources, sender, timestamp, status, reviewer

### Phase 6 — Security Hardening  ✓ Complete
- Input validation on all endpoints
- Rate limiting via `slowapi` (200 req/min default)
- JWT middleware (`require_auth` dependency)
- Security response headers middleware (X-Frame-Options, CSP, etc.)
- Secrets via `.env`, never committed

### Phase 7 — Gmail Integration  ✓ Complete
- `GmailInbox` class: IMAP read + SMTP send, stdlib only
- App Password authentication (`GMAIL_APP_PASSWORD`)
- Sender allowlist filtering (`ALLOWED_SENDERS`)
- Acknowledgment detection (skip short thank-you replies)
- Poller wired to `GmailInbox` when `GMAIL_USE_INBOX=true`

### Phase 8 — Veridas Chat Assistant  ✓ Complete
- In-browser chat widget in the dashboard
- Same RAG pipeline as email path; separate `CHAT_SYSTEM_PROMPT`
- In-memory session history: last 10 Q&A pairs per session, thread-safe
- `POST /chat/message`, `DELETE /chat/{session_id}`

### Phase 9 — Onboarding Policy Sequences  ✓ Complete
HR creates named sequences of policy documents, each with a day offset from a start date. Employees are enrolled with a start date. A background job checks daily and sends the scheduled document emails via Gmail SMTP.

**Data model:**
- `sequences` table: `id`, `name`, `description`
- `sequence_steps` table: `id`, `sequence_id`, `doc_id`, `day_offset`, `email_subject`, `email_body_template`
- `enrollments` table: `id`, `sequence_id`, `employee_email`, `start_date`, `status` (active/cancelled)
- `deliveries` table: `id`, `enrollment_id`, `step_id`, `scheduled_date`, `sent_at`, `status`

**New modules:**
- `app/onboarding/store.py` — CRUD for sequences, steps, enrollments, deliveries
- `app/email_utils.py` — shared `send_email(to, subject, body)` utility wrapping Gmail SMTP
- `app/api/onboarding.py` — FastAPI router

### Phase 10 — Policy Versioning & Update Alerts  ✓ Complete
SQLite tracks a version number per document. When a new file is uploaded with the same name, the version increments. HR can then send a notification email to a list of recipients informing them of the update.

**Data model:**
- `document_versions` table: `id`, `doc_id`, `version`, `filename`, `uploaded_at`, `notes`

**New modules:**
- `app/versioning/store.py` — version tracking queries

---

## Deployment

### Railway
- `Dockerfile`: Python 3.11-slim, embeds `all-MiniLM-L6-v2` at build time
- `railway.toml`: `builder = "dockerfile"`, `healthcheckPath = "/health"`
- Mount a Railway volume at `/data`; the app auto-detects `/data` and uses it for ChromaDB, SQLite, and uploaded docs
- `PORT` env var is respected (`CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`)

### Local dev
```bash
cd Muster
source venv/bin/activate
uvicorn app.main:app --reload
```
- Dashboard: `http://localhost:8000/`
- API docs: `http://localhost:8000/docs`

### ngrok tunnel
Set `NGROK_AUTH_TOKEN` in `.env`. On startup, a tunnel is opened and `settings.public_base_url` is updated to the ngrok URL. Policy document links in email replies and chat sources use this URL automatically. Leave `NGROK_AUTH_TOKEN` empty in production (Railway sets `PUBLIC_BASE_URL` instead).

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for answer generation |
| `MUSTER_API_KEY` | — | API key for dashboard login (e.g. `AlexDades` in `.env`) |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `JWT_EXPIRY_HOURS` | `8` | Token lifetime |
| `GMAIL_ADDRESS` | — | Gmail address used for send/receive |
| `GMAIL_APP_PASSWORD` | — | Google App Password (spaces ignored) |
| `GMAIL_USE_INBOX` | `false` | Enable live Gmail polling |
| `ALLOWED_SENDERS` | `` | Comma-separated allowlist; empty = allow all |
| `POLL_INTERVAL_SECONDS` | `60` | Background poller cadence |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Base URL for document links in replies |
| `NGROK_AUTH_TOKEN` | — | If set, auto-starts ngrok tunnel on startup |
| `CHROMA_DB_PATH` | `/data/chroma_db` or `./chroma_db` | ChromaDB directory |
| `DB_PATH` | `/data/muster.db` or `./muster.db` | SQLite database path |
| `UPLOADED_DOCS_DIR` | `/data/uploaded_docs` or `./uploaded_docs` | Uploaded file storage |
| `CHUNK_SIZE` | `500` | Token chunk size for document splitting |
| `CHUNK_OVERLAP` | `50` | Overlap between adjacent chunks |
| `ALLOWED_ORIGINS` | `http://localhost:8000` | CORS origins |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/auth/token` | Exchange API key for JWT |
| GET | `/documents` | List indexed documents |
| POST | `/documents` | Upload PDF/DOCX and index it |
| DELETE | `/documents/{doc_id}` | Remove from index |
| GET | `/documents/{doc_id}/versions` | Get version history |
| POST | `/documents/{doc_id}/notify` | Send update notification emails |
| POST | `/inbox/process` | Manually trigger inbox processing |
| GET | `/drafts` | List pending review drafts |
| POST | `/drafts/{id}/approve` | Approve draft (optionally with edited answer) |
| POST | `/drafts/{id}/reject` | Reject draft |
| POST | `/chat/message` | Send message to Veridas, get answer + sources |
| DELETE | `/chat/{session_id}` | Clear chat session |
| GET | `/onboarding/sequences` | List sequences |
| POST | `/onboarding/sequences` | Create sequence |
| DELETE | `/onboarding/sequences/{id}` | Delete sequence |
| GET | `/onboarding/sequences/{id}/steps` | List steps in a sequence |
| POST | `/onboarding/sequences/{id}/steps` | Add step to sequence |
| DELETE | `/onboarding/sequences/{id}/steps/{step_id}` | Remove step |
| GET | `/onboarding/enrollments` | List enrollments |
| POST | `/onboarding/enrollments` | Enroll employee in sequence |
| DELETE | `/onboarding/enrollments/{id}` | Cancel enrollment |
| GET | `/audit` | Paginated audit log (filter by status, sender) |
| GET | `/settings` | Get runtime settings |
| PATCH | `/settings` | Update settings (`human_review_mode`, `n_results`) |
| GET | `/health` | Health check + `public_base_url` |

### Settings response fields
`human_review_mode`, `n_results`, `gmail_connected`, `gmail_address` (masked, e.g. `ada***@gmail.com`), `allowed_senders`, `poll_interval_seconds`

---

## UI / Design

### Overview
Single-page application at `app/static/index.html`. Served by FastAPI. Mobile-responsive with hamburger sidebar. Auth state stored in `localStorage` (JWT). Full-screen chat layout when Veridas is active.

### Design tokens
```css
--primary:        rgb(72,91,200)    /* blue-purple — nav active, icons, toggles */
--primary-dark:   rgb(55,72,170)
--primary-light:  rgb(200,210,245)
--primary-xlight: rgb(235,238,252)
--accent:         #f59e0b           /* amber — primary CTA buttons */
--bg:             #fff
--bg-soft:        #f8fafc
--bg-muted:       #f1f5f9
--border:         #e2e8f0
--fg:             #0f172a
--fg-muted:       #475569
--fg-subtle:      #94a3b8
--r:              10px
```

### Font
`Plus Jakarta Sans` via Google Fonts. Weights: 400, 500, 600, 700.

### Logo
SVG cloud mark (three overlapping circles + rounded rect) with horizontal document lines, followed by "Muster" text at `font-weight:600`.

### Key patterns
- **Primary buttons** (`btn-primary`): `--primary` background, white text
- **Accent buttons** (`btn-accent`): amber (`--accent`), white text
- **Sidebar:** white (`--bg`) with right border; active item uses `--primary` background tint
- **Cards:** white background, `1px solid var(--border)`, `border-radius:var(--r)`
- **Chips/badges:** pill shape, color variants: `chip-primary`, `chip-amber`, `chip-blue`, `chip-red`, `chip-gray`
- **Modals:** custom confirm/reject dialogs (no browser `confirm()`)
- **Skeleton loaders:** shown while data fetches
- **Page transitions:** CSS fade between sections
- **Upload progress:** XHR with progress bar
- **Audit log:** click row to expand full detail drill-down

### Chat (Veridas) UI
- User bubbles: right-aligned, `--primary` background
- Assistant bubbles: left-aligned, white with border, "M" avatar
- Typing indicator: bouncing dots during API call
- Source chips below each assistant message, link to `/files/{filename}`
- "New conversation" button calls `DELETE /chat/{session_id}`
- Send on Enter; Shift+Enter for newline

---

## Key Implementation Details

- **Python compatibility:** Local venv is 3.9.6 — use `from __future__ import annotations` for union type hints (`str | Path` not native until 3.10)
- **Circular imports:** `app/delivery/__init__.py` and `app/email_ingestion/__init__.py` are intentionally empty; `TYPE_CHECKING` guard used in `draft_store.py` for the `Email` annotation
- **Prompt caching:** `cache_control: ephemeral` on system prompt in both generator and validator
- **API cost optimisation:** validation agent uses `claude-haiku-4-5` (not Sonnet); email reply `max_tokens` capped at 600; classifier (`is_policy_question`) uses Haiku with `max_tokens=5`
- **Validation agent:** separate Claude call returns `{valid, confidence, issues, reasoning}`; handles markdown-fenced JSON and unparseable responses
- **Acknowledgment detection:** `len(body.strip()) < 120 and "?" not in body and gratitude_regex.match(body)` — matched emails are marked read and skipped
- **GmailInbox:** stdlib only (`imaplib`, `smtplib`); App Password spaces stripped automatically; STARTTLS for SMTP; threading headers set for proper email threading

---

## Build Status (as of 2026-05-23)

Phases 1–10 complete.

| Phase | Description | Unit tests | Integration tests |
|---|---|---|---|
| 1 | Document indexing | 21 | — |
| 2 | Retrieval + answer generation + validation | 35 | 12 |
| 3 | Email ingestion (mock + Gmail) | 55 | — |
| 4 | Review mode + draft store | 28 | 4 |
| 5 | Audit trail + FastAPI REST API | 34 | — |
| 6 | Security (JWT, rate limiting, headers) | 21 | — |
| 7 | Gmail integration | 25 | — |
| 8 | Veridas chat assistant | 24 | — |
| 9 | Onboarding policy sequences | — | — |
| 10 | Policy versioning + update alerts | — | — |
| **Total** | | **243** | **16** |

---

## Directory Structure

```
Muster/
├── muster.md               # this file — project spec
├── logAlex.md              # development log
├── index-alex.html         # muster.team marketing site (reference)
├── Dockerfile              # Railway build
├── railway.toml            # Railway deploy config
├── .dockerignore
├── .env                    # local secrets (gitignored)
├── .env.example            # env var template
├── requirements.txt
├── pytest.ini
├── ask.py                  # CLI Q&A against indexed docs
├── email_demo.py           # CLI email simulation
├── review.py               # CLI HR reviewer tool
├── eval_qa.py              # evaluation harness
├── app/
│   ├── main.py             # FastAPI entry point, lifespan, routers, poller
│   ├── config.py           # Settings from env vars
│   ├── dependencies.py     # FastAPI dependency injection
│   ├── email_utils.py      # shared send_email() utility (Phase 9+)
│   ├── indexer/            # Phase 1: parser, chunker, vector store, pipeline
│   ├── retrieval/          # Phase 2: retriever, generator, validator, pipeline
│   ├── email_ingestion/    # Phase 3: Email model, MockInbox, parser, poller
│   ├── delivery/           # Phase 4: draft store, dispatcher
│   ├── audit/              # Phase 5: append-only audit log store
│   ├── auth/               # Phase 6: JWT middleware
│   ├── gmail/              # Phase 7: GmailInbox (IMAP read + SMTP send)
│   ├── ms365/              # OAuth stub for Microsoft 365 (not primary)
│   ├── onboarding/         # Phase 9: store.py (sequences, enrollments, deliveries)
│   ├── versioning/         # Phase 10: store.py (version tracking)
│   ├── api/
│   │   ├── documents.py
│   │   ├── drafts.py
│   │   ├── audit.py
│   │   ├── settings_api.py
│   │   ├── inbox.py
│   │   ├── chat.py         # Phase 8: Veridas chat
│   │   ├── auth_api.py
│   │   └── onboarding.py   # Phase 9: onboarding router
│   └── static/
│       └── index.html      # SPA dashboard
├── tests/
│   ├── conftest.py
│   ├── test_indexer.py     # 21 tests
│   ├── test_retrieval.py   # 35 tests (+ 12 integration)
│   ├── test_email.py       # 30 tests (+ 4 integration)
│   ├── test_delivery.py    # 28 tests (+ 4 integration)
│   ├── test_api.py         # 34 tests
│   ├── test_gmail.py       # 25 tests
│   ├── test_ms365.py       # 24 tests
│   └── test_security.py    # 21 tests
├── sample_docs/            # 10 mock HR policy documents (5 PDF, 5 DOCX)
├── sample_emails/          # seed script for mock inbox
├── uploaded_docs/          # documents uploaded via API (gitignored)
└── chroma_db/              # ChromaDB vector store (gitignored)
```

---

## Business Context

### Positioning
- Vertical SaaS sold directly to HR managers at SMBs (50–500 employees)
- Core pitch: employees ask policy questions by email → Muster answers in under 60 seconds with citations
- Secondary pitch: Veridas chat widget embedded in existing HR portals (sold separately as a lighter entry point)

### Pricing (proposed)
- £199/month flat for up to 200 employees — low enough for HR manager to approve without CFO sign-off
- Alternative: £2–4 per employee per month (scales with company size, industry standard for HR SaaS)
- API costs at current usage: ~£0.015–0.020 per email processed; £10–15/month per client at 500 interactions
- Railway hosting: ~£5–10/month at small scale

### Enterprise Upgrade Path (when client #2 appears)
In this order — do not build ahead of demand:
1. **Multi-tenancy** — isolated ChromaDB collection + SQLite DB per client. This is the single most important change; everything else builds on it.
2. **Audit trail UI** — log every Q&A for compliance ("what did we tell John about paternity leave?")
3. **Security hardening** — per-tenant API keys, RBAC, SSO/SAML
4. **Infrastructure** — migrate SQLite → Postgres for concurrent multi-tenant writes; Sentry for error monitoring
5. **Enterprise features** — white-labeling, usage analytics dashboard, Veridas widget embed

---

## Planned Next Features (People Section — Onboarding Module)

Research conducted May 2026. Competitive analysis against BambooHR, Rippling, Workday, HiBob, Trainual, Zavvy, Leapsome, Xoralia, AirMason.

### Planned Phase 11 — Onboarding Timeline Preview
**Status:** Not started  
**Competitive position:** Mild differentiator. Competitors (Workday, Zavvy) show admin-only live views but not a pre-enrolment preview.  
**What it is:** Before clicking "Enrol", HR sees a visual day-by-day timeline of exactly what will be sent and when. Spots gaps ("nothing in week 3") or overloading ("three emails in one day") before it's too late.  
**Why first:** Pure frontend, zero backend changes, lowest risk.  
**Implementation:** Derive from existing sequence steps data (`GET /onboarding/sequences/{id}/steps`). Render a timeline card per step sorted by `day_offset`. No new API endpoints needed.  
**New nav item:** People → Timeline Preview

---

### Planned Phase 12 — Role-Based Templates
**Status:** Not started  
**Competitive position:** Table stakes — BambooHR, Rippling, Trainual, Zavvy all have it. Muster's differentiator is AI doc-matching: pre-populate a role template by analysing which uploaded policies are relevant to that role.  
**What it is:** Pre-built sequence templates by department (Engineering, Sales, Operations, etc.). HR picks a template, customises it, and enrolls. Much faster than building from scratch.  
**Implementation:** New SQLite table `sequence_templates(id, name, role, description, steps_json)`. New API endpoints `GET/POST /onboarding/templates`. Seed with 3–5 default templates. AI layer: on template creation, Claude scans uploaded docs and suggests which to include.  
**New nav item:** People → Templates

---

### Planned Phase 13 — AI Sequence Advisor
**Status:** Not started  
**Competitive position:** Strong first-mover. No competitor takes uploaded policy documents as input and generates a recommended day-by-day schedule from them.  
**What it is:** HR clicks "Generate recommendation" → Claude analyses all uploaded policy documents and suggests a structured onboarding schedule: which documents to send, in what order, with recommended day offsets and rationale. HR approves or edits rather than building from scratch.  
**Why it matters:** Every competitor assumes HR already knows what the sequence should be. Muster inverts this.  
**Implementation:** New `POST /onboarding/sequences/recommend` endpoint. Claude call with system prompt + list of all uploaded doc titles/summaries + instruction to produce a JSON sequence plan. Result rendered as an editable draft sequence in the UI.  
**New nav item:** People → AI Advisor  
**Risk:** New Claude API call (cost + latency). Run on demand only, not automatically.

---

### Planned Phase 14 — Employee Progress Tracker
**Status:** Not started  
**Competitive position:** Progress tracking is table stakes (BambooHR, Rippling, Trainual, HiBob all have it). The lightweight in-email "I've read this ✓" confirmation link is less common and more elegant than forcing employees to log into an HR portal.  
**What it is:** HR dashboard shows each enrolled employee's journey — steps sent, steps upcoming, and whether the employee clicked the confirmation link. Each onboarding email includes a one-click "I've read this ✓" link.  
**Differentiator angle:** Add a Claude-generated 2-question micro-quiz per document delivered in the same email. No competitor does comprehension-checking today.  
**Implementation:**  
- Add `confirmed_at` column to `enrollment_deliveries` table  
- New `GET /onboarding/confirm/{token}` public endpoint (no auth) that marks delivery confirmed  
- Generate a signed token per delivery; embed in outgoing email  
- New UI page showing per-employee progress grid  
**New nav item:** People → Progress Tracker  
**Risk:** Touches live onboarding poller and email sending logic — test thoroughly before shipping.

---

### Planned Phase 15 — Smart Email Summaries (Biggest Differentiator)
**Status:** Not started  
**Competitive position:** Strong moat — no named competitor does this. BambooHR "Ask BambooHR" is reactive (employee asks). Muster is proactive (AI reads the doc and sends the brief).  
**What it is:** Each onboarding step email includes a Claude-generated 3-bullet plain-English summary of the key points from that policy document — written in a friendly tone, addressed to the employee by name. New hires get something readable alongside the full document link.  
**Why it's the moat:** Muster already has the document indexed at upload time. Generating a summary is a near-zero-cost extension. Competitors would have to rebuild their document ingestion pipeline to replicate it.  
**Core pitch:** "Every HR tool sends new hires a PDF and hopes for the best. Muster sends them a human-readable brief, written by AI from your actual policy, in the same email."  
**Implementation:**  
- At document upload time (or on first sequence step use), generate and cache a 3-bullet summary via Claude (`claude-haiku-4-5` to keep cost low)  
- Store in new `document_summaries(doc_id, summary_text, generated_at)` SQLite table  
- Inject summary into outgoing onboarding step emails above the document link  
- UI: show cached summary in document list; "Regenerate" button  
**New nav item:** People → Smart Emails (settings/preview page)  
**Risk:** Highest risk — touches document upload pipeline AND live onboarding email sending. Implement last.

---

### Implementation Order (safest to riskiest)
| Phase | Feature | Risk | New backend? | Estimated effort |
|---|---|---|---|---|
| 11 | Timeline Preview | Low | No | 1 session |
| 12 | Role Templates | Low | Simple CRUD | 1–2 sessions |
| 13 | AI Advisor | Medium | 1 Claude endpoint | 1 session |
| 14 | Progress Tracker | Medium | DB column + token endpoint | 2 sessions |
| 15 | Smart Email Summaries | High | Touches upload + poller | 2–3 sessions |

### Nav structure when complete (People section)
```
People
├── Onboarding        (Phase 9 — complete)
├── Timeline Preview  (Phase 11)
├── Templates         (Phase 12)
├── AI Advisor        (Phase 13)
├── Progress Tracker  (Phase 14)
└── Smart Emails      (Phase 15)
```

---

## Open Questions

1. Multi-tenancy: one ChromaDB collection per client, or namespace within shared DB?
2. Pricing enforcement: usage metering per reply?
3. Chunking: currently fixed-size (500 words, 50-word overlap); consider semantic chunking by section headers
4. People nav: flat list of 6 items, or collapsible group?
5. Smart Email Summaries: generate at upload time (stored, instant) or at send time (fresh per employee)?
6. Progress Tracker: simple click confirmation, or add Claude-generated micro-quiz for comprehension checking?
