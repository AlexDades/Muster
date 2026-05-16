# Muster — AI-Powered HR Policy Assistant

## What It Is

Muster is a SaaS product sold to corporations. It connects to a company's shared HR inbox (Microsoft 365 / Outlook), reads internal policy documents (PDFs, Word docs, SharePoint libraries), and automatically drafts or sends replies to employee questions — with citations to the relevant policy sections. It targets HR teams that spend too much time answering repetitive questions about benefits, PTO, expenses, etc.

---

## Core Features

- Autonomous email replies in under 60 seconds
- Optional human-review mode (drafts only, no auto-send)
- Full audit trail: every response logged with source material
- Auto re-indexing when policy documents are updated
- Source citations in every reply so employees can verify
- GDPR-compliant, data residency options, SSO, exportable audit logs
- Role-based access (admin, reviewer, read-only)

---

## Tech Stack Decisions

- **Language:** Python (strong ecosystem for AI, document parsing, email integration)
- **AI model:** Claude (Anthropic API) — claude-sonnet-4-6 as default, upgradeable
- **Document parsing:** `pypdf` for PDFs, `python-docx` for Word, SharePoint via Microsoft Graph API
- **Vector store / retrieval:** ChromaDB (local, open-source, easy to swap for Pinecone/Weaviate in prod)
- **Email integration:** Microsoft Graph API (mock first, real OAuth later)
- **Web framework (API layer):** FastAPI — async, fast, great for background tasks
- **Database (audit + metadata):** SQLite for dev, PostgreSQL for production
- **Auth:** OAuth 2.0 (Microsoft Entra ID / Azure AD) for M365, JWT for internal API
- **Security:** All secrets via environment variables, no hardcoded credentials, input sanitization, HTTPS only

---

## Architecture Overview

```
[Employee Email]
      |
      v
[Outlook Shared Inbox]  <-- Microsoft Graph API (mocked initially)
      |
      v
[Email Ingestion Service]
  - polls inbox every N seconds
  - extracts question text and metadata (sender, timestamp, thread ID)
      |
      v
[Retrieval Engine]
  - query is embedded (Claude or sentence-transformers)
  - top-K relevant policy chunks retrieved from vector store
      |
      v
[Response Generator]
  - Claude API called with: system prompt + policy chunks + employee question
   - A secondary agent checks the corectness of the response
  - response includes cited policy sections
      |
      v
[Review Gate]
  - if human_review_mode=True: save draft, notify HR reviewer via email. human reviewer receives the potential reply via email. Human reviewer has 2 options, they either reply with the same email body, or do any changes then reply with the email body
  - if human_review_mode=False: send automatically
      |
      v
[Audit Logger]
  - logs: question, retrieved chunks, response, sender, timestamp, review status
      |
      v
[Email Send Service]
  - sends reply via Microsoft Graph API (mocked initially)
```

---

## Implementation Plan (One Piece at a Time)

### Phase 1 — Document Indexing Engine
- Create 10 mock policy documents in PDF and DOCX formats
- Parse policy documents (PDF, DOCX)
- Chunk documents into passages (~500 tokens, with overlap)
- Embed chunks and store in ChromaDB
- Support adding, updating, and deleting documents
- Test: ingest sample HR policy docs, verify retrieval quality

### Phase 2 — Retrieval + Answer Generation
- Accept a plain-text question
- Retrieve top-K relevant chunks from vector store
- Call Claude API with retrieved context + question
- Return answer with source citations
- Test: ask policy questions, verify accuracy and citation correctness

### Phase 3 — Email Ingestion (Mocked)
- Mock an Outlook inbox (local JSON or SQLite with fake emails)
- Poll mock inbox, extract questions
- Feed into Phase 2 pipeline
- Test: end-to-end from fake email to generated answer

### Phase 4 — Response Delivery + Review Mode
- Implement human_review_mode flag
- If True: save draft response to DB, expose via API for HR to approve/edit/reject
- If False: mark as auto-sent (mock send)
- Test: both modes, verify audit trail completeness

### Phase 5 — Audit Trail + API Layer
- FastAPI endpoints: upload docs, view audit log, manage settings, approve drafts
- SQLite audit table: question, answer, sources, sender, timestamp, status, reviewer
- Test: API contract, audit log integrity

### Phase 6 — Security Hardening
- Input validation and sanitization on all endpoints
- Rate limiting
- Auth middleware (JWT for API, OAuth stub for M365)
- Secrets management (.env, never committed)
- Test: basic penetration checks, auth bypass attempts

### Phase 7 — Real Microsoft 365 Integration
- Register Azure AD app, implement OAuth 2.0 flow
- Replace mock inbox with real Graph API calls
- Replace mock send with real Graph API send
- Test: with dev M365 tenant

---

## Security Considerations

- No policy document content stored in plaintext beyond the vector embeddings
- All API keys and secrets in environment variables (`.env`, gitignored)
- Audit logs are append-only
- Email content treated as sensitive PII — not logged beyond necessary metadata
- GDPR: data residency configurable, retention policies enforced
- Role separation: admins manage docs/settings, reviewers approve drafts, employees have no system access

---

## UI / Design Guidelines

**All interfaces built for Muster must match the design of `index-alex.html`** (the muster.team marketing site). This is non-negotiable — the product interface and the marketing site must feel like one cohesive brand.

### Design tokens (use these exactly)
```css
--green: #00a86e           /* primary brand color — nav active, icons, toggles, chips */
--green-dark: #008a5a
--green-deep: #075c3d
--accent: #f59e0b          /* amber — primary CTA buttons (NOT green) */
--green-light: #d8f3e4
--green-mid: #9cdcb9
--green-xlight: #ecfaf2    /* icon backgrounds, hover states */
--bg: #fff
--bg-soft: #f8fafc         /* page background */
--bg-muted: #f1f5f9
--border: #e2e8f0
--border-strong: #cbd5e1
--fg: #0f172a
--fg-muted: #475569
--fg-subtle: #94a3b8
--r: 10px                  /* standard border radius */
```

### Font
`system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif` — no external font imports.

### Key patterns
- **Logo:** pulsing green dot + "Muster" text (`font-weight:600`), animated with `@keyframes pulse`
- **Primary buttons:** amber (`--accent: #f59e0b`), hover `#d97706`
- **Secondary buttons:** transparent with `--border`, hover `--bg-muted`
- **Cards:** `background:var(--bg)`, `border:1px solid var(--border)`, `border-radius:var(--r)`, `box-shadow:var(--shadow-sm)`
- **Card icons:** `36×36px`, `border-radius:8px`, `background:var(--green-xlight)`, SVG in `--green`
- **Chips/badges:** pill shape, color variants: `chip-green`, `chip-amber`, `chip-blue`, `chip-red`, `chip-gray`
- **Section labels:** `font-size:10–11px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; color:var(--green)`
- **Sidebar (dashboard):** white (`--bg`) with right border, green active state, not dark navy
- **Dark mode:** supported via `@media(prefers-color-scheme:dark)` with the inverted palette from `index-alex.html`
- **Topbar:** white, 56px height, bottom border, matches the marketing site nav height

### Reference file
`index-alex.html` (in the Muster project root) is the single source of truth for colors, typography, spacing, and component patterns.

---

## Build Status (as of 2026-05-08)

All phases 1–5 are complete and tested.

| Phase | Description | Unit tests | Integration tests |
|---|---|---|---|
| 1 | Document indexing (parse, chunk, embed, store) | 21 | — |
| 2 | Retrieval + Claude answer generation + validation agent | 23 | 12 |
| 3 | Mock email inbox + poller + email parser | 26 | 4 |
| 4 | Review mode + draft store + dispatcher + reviewer CLI | 24 | 4 |
| 5 | Audit trail + FastAPI REST API (5 routers, 11 endpoints) | 34 | — |
| **Total** | | **128** | **20** |

All 128 unit tests pass without an API key. All 20 integration tests pass with `ANTHROPIC_API_KEY`.

### Key implementation details
- **Python version:** 3.9.6 — use `from __future__ import annotations` for union type hints (`str | Path` is not native)
- **Circular import fix:** `app/delivery/__init__.py` and `app/email_ingestion/__init__.py` are intentionally empty; `TYPE_CHECKING` guard used in `draft_store.py` for the `Email` annotation
- **Embedding model:** `all-MiniLM-L6-v2` via `sentence-transformers` (local, no API cost)
- **ChromaDB path:** `./chroma_db/` (configurable via `CHROMA_DB_PATH` env var)
- **SQLite path:** `./muster.db` (configurable via `DB_PATH` env var)
- **Prompt caching:** `cache_control: ephemeral` on system prompt in both generator and validator to reduce API costs on repeated calls
- **Secondary validation agent:** separate Claude call returns `{valid, confidence, issues, reasoning}` JSON; handles markdown-fenced JSON and unparseable responses gracefully

### Running the server
```bash
cd Muster
source venv/bin/activate
uvicorn app.main:app --reload
```
- Dashboard UI: `http://localhost:8000/`
- API docs: `http://localhost:8000/docs`

### Key API endpoints
| Method | Path | Description |
|---|---|---|
| GET | `/documents` | List indexed documents |
| POST | `/documents` | Upload PDF/DOCX and index it |
| DELETE | `/documents/{doc_id}` | Remove from index |
| POST | `/inbox/process` | Process all unread mock inbox emails |
| GET | `/drafts` | List pending drafts |
| POST | `/drafts/{id}/approve` | Approve draft (optionally with edited answer) |
| POST | `/drafts/{id}/reject` | Reject draft |
| GET | `/audit` | Paginated audit log (filter by status, sender) |
| GET | `/settings` | Get runtime settings |
| PATCH | `/settings` | Update settings (human_review_mode, n_results) |
| GET | `/health` | Health check |

---

## Directory Structure (Actual)

```
Muster/
├── muster.md               # this file — project spec + design guidelines
├── logAlex.md              # development audit log (what was built, when, test results)
├── index-alex.html         # muster.team marketing site — SOURCE OF TRUTH for UI design
├── .env.example            # environment variable template
├── requirements.txt
├── ask.py                  # interactive CLI Q&A against indexed docs
├── email_demo.py           # interactive CLI email simulation
├── review.py               # interactive CLI for HR reviewers
├── app/
│   ├── main.py             # FastAPI entry point (5 routers)
│   ├── config.py           # settings from env vars
│   ├── dependencies.py     # FastAPI dependency injection (shared resources)
│   ├── indexer/            # Phase 1: parser, chunker, vector store, pipeline
│   ├── retrieval/          # Phase 2: retriever, generator, validator, pipeline
│   ├── email_ingestion/    # Phase 3: Email model, mock inbox, parser, poller
│   ├── delivery/           # Phase 4: draft store, dispatcher
│   ├── audit/              # Phase 5: append-only audit log store
│   ├── api/                # Phase 5: FastAPI routers (documents, drafts, audit, settings, inbox)
│   ├── static/
│   │   └── index.html      # SPA dashboard — must match index-alex.html design
│   └── auth/               # Phase 6: JWT + OAuth (not yet built)
├── tests/
│   ├── test_indexer.py     # 21 tests
│   ├── test_retrieval.py   # 35 tests (23 unit + 12 integration)
│   ├── test_email.py       # 30 tests (26 unit + 4 integration)
│   ├── test_delivery.py    # 28 tests (24 unit + 4 integration)
│   └── test_api.py         # 34 tests
├── sample_docs/            # 10 mock HR policy documents (5 PDF, 5 DOCX)
├── sample_emails/          # seed script for mock inbox
├── uploaded_docs/          # documents uploaded via the API (gitignored)
└── chroma_db/              # ChromaDB vector store (gitignored)
```

---

## Phase 8 — Chatbot Interface

### What It Is
A live chat widget embedded in the Muster dashboard that lets employees (or HR admins testing the system) ask policy questions directly in the browser — no email required. Uses the same RAG pipeline as the email path.

### Architecture
```
[Browser chat UI]
      |  POST /chat/message {session_id, message}
      v
[Chat API router — app/api/chat.py]
  - retrieves session history from in-memory store
  - calls retrieve() to get relevant policy chunks
  - calls generate_chat_answer() with message + chunks + history
  - appends turn to session history (capped at last 10 Q&A pairs)
      |
      v
[generate_chat_answer() — app/retrieval/generator.py]
  - separate CHAT_SYSTEM_PROMPT (no email formatting constraints)
  - passes full conversation history to Claude as messages array
  - returns answer + extracted source citations
      |
      v
[Browser renders response]
  - markdown rendered client-side (bold, bullets, citations)
  - sources shown as clickable chips linking to /files/{filename}
  - typing indicator while waiting
```

### API Endpoints Added
| Method | Path | Description |
|---|---|---|
| POST | `/chat/message` | Send a message, get an answer (with session history) |
| DELETE | `/chat/{session_id}` | Clear a session (new conversation) |

### Session Model
- Sessions are keyed by a UUID generated client-side
- History stored in-memory (dict) — resets on server restart, appropriate for demo
- Last 10 Q&A pairs (20 messages) retained per session to keep context window manageable
- Thread-safe via `threading.Lock`

### Auth
Same JWT auth as the rest of the dashboard. Users log in with the API key before accessing the chat.

### UI Design
- New "Chat" nav section in the sidebar
- Full-height chat layout (overrides content padding when active)
- User bubbles: right-aligned, green background
- Assistant bubbles: left-aligned, white with border, "M" avatar
- Typing indicator (bouncing dots) during API call
- Source chips below each assistant message — clickable links to policy files
- "New conversation" button resets session
- Send on Enter, Shift+Enter for newline

### Publishing for Testing
- ngrok tunnel starts automatically when `NGROK_AUTH_TOKEN` is set in `.env`
- Share the ngrok URL; recipients log in with the API key
- All policy document links in replies and chat sources use the ngrok public URL

## Remaining Phases

### Phase 6 — Security Hardening
- Input validation and sanitization on all endpoints
- Rate limiting (e.g. slowapi)
- Auth middleware (JWT for API, OAuth stub for M365)
- Secrets management (already done: .env, never committed)
- Test: basic penetration checks, auth bypass attempts

### Phase 7 — Real Microsoft 365 Integration
- Register Azure AD app, implement OAuth 2.0 flow
- Replace mock inbox with real Graph API calls (Microsoft Graph)
- Replace mock send with real Graph API send
- SharePoint document auto-sync
- Test: with dev M365 tenant

---

## Key Open Questions

1. Multi-tenancy: one ChromaDB collection per client, or namespace within shared DB?
2. Pricing enforcement: usage metering per reply?
3. Deployment target: Docker + cloud (AWS/GCP/Azure), or managed PaaS?
4. Chunking: currently fixed-size (500 words, 50-word overlap); consider semantic chunking by section headers for better retrieval quality
