# Muster — Development & Audit Log

**Project:** Muster HR Policy Assistant  
**Author:** Alexandru Dades  
**Start date:** 2026-05-08  
**Purpose:** Automated AI-powered email assistant that answers employee HR policy questions using company policy documents.

---

## Phase 1 — Document Indexing Engine

**Date:** 2026-05-08

### 1.1 Project scaffold
Created the base directory structure (`app/`, `tests/`, `sample_docs/`), `requirements.txt`, `.env.example`, and Python virtual environment. All secrets are loaded from environment variables — no credentials are hardcoded anywhere in the codebase.

### 1.2 Document parser (`app/indexer/parser.py`)
Implemented parsing of PDF files using `pypdf` and DOCX files using `python-docx`. Unsupported file types raise a `ValueError` rather than silently failing.

### 1.3 Text chunker (`app/indexer/chunker.py`)
Splits parsed document text into overlapping word-based chunks (default: 500 words per chunk, 50-word overlap). Chunk size and overlap are configurable via environment variables.

### 1.4 Vector store (`app/indexer/store.py`)
Implemented `PolicyStore`, a ChromaDB-backed vector store using the `all-MiniLM-L6-v2` sentence-transformers embedding model. Supports add, update, delete, and semantic query operations. Documents cannot exceed the collection — edge cases (empty collection, fewer items than requested) are handled safely.

### 1.5 Indexing pipeline (`app/indexer/pipeline.py`)
Orchestrates parse → chunk → store. Accepts a file path and an optional `PolicyStore` instance (injectable for testing).

### 1.6 Mock policy documents (`sample_docs/generate_docs.py`)
Generated 10 realistic HR policy documents (5 PDF, 5 DOCX) covering: PTO & vacation, expense reimbursement, remote work, code of conduct, health & benefits, performance reviews, onboarding, data privacy & security, parental leave, and travel policy.

### 1.7 Tests (`tests/test_indexer.py`)
21 unit tests covering: PDF parsing, DOCX parsing, unsupported file type rejection, chunking size and overlap correctness, empty input handling, store add/query/delete/update, metadata integrity, and full pipeline indexing and removal.

**Test result:** 21/21 passed

---

## Phase 2 — Retrieval and Answer Generation

**Date:** 2026-05-08

### 2.1 Retriever (`app/retrieval/retriever.py`)
Thin wrapper over `PolicyStore.query()` that accepts a plain-text question and returns the top-K most semantically relevant document chunks.

### 2.2 Answer generator (`app/retrieval/generator.py`)
Calls the Claude API (`claude-sonnet-4-6`) with the retrieved policy chunks as context and the employee question. The system prompt instructs Claude to answer strictly from the provided documents and to include inline source citations in the format `[Source: filename]`. Prompt caching (`cache_control: ephemeral`) is applied to the system prompt to reduce API costs on repeated calls.

### 2.3 Validator — secondary agent (`app/retrieval/validator.py`)
A second Claude API call that acts as a quality assurance agent. It receives the question, the retrieved context, and the generated answer, and returns a structured JSON assessment: `valid` (bool), `confidence` (0–1), `issues` (list), and `reasoning`. This is the secondary correctness-checking agent described in the architecture. Handles markdown-wrapped JSON responses and unparseable responses gracefully.

### 2.4 Retrieval pipeline (`app/retrieval/pipeline.py`)
Orchestrates retriever → generator → validator into a single `answer_question()` call. Returns question, answer, sources, validation result, and chunk count.

### 2.5 Interactive CLI (`ask.py`)
Command-line tool for direct interactive Q&A against the indexed documents. Indexes documents on first run and persists the index to `chroma_db/`. Displays answer, cited sources, and validation status per question.

### 2.6 Tests (`tests/test_retrieval.py`)
23 unit tests (Claude mocked) and 12 integration tests (real Claude API) covering: retrieval delegation and structure, citation extraction and deduplication, context formatting, empty chunk handling, prompt construction verification, cache_control usage, JSON parsing (including markdown-fenced), unparseable validator handling, pipeline key structure, and 12 specific policy questions verified against expected facts.

**Test result:** 23/23 unit passed; 12/12 integration passed

---

## Phase 3 — Email Ingestion (Mocked)

**Date:** 2026-05-08

### 3.1 Email model (`app/email_ingestion/models.py`)
`Email` dataclass with fields: `id`, `message_id`, `sender`, `subject`, `body`, `received_at`, `status`, `reply_body`, `replied_at`.

### 3.2 Mock inbox (`app/email_ingestion/mock_inbox.py`)
SQLite-backed mock Outlook inbox (`MockInbox` class). Supports: add email, get unread, get all, mark replied, mark failed, count by status. Duplicate `message_id` entries are silently ignored (idempotent ingestion). Designed to be a drop-in replacement for a real Microsoft Graph API inbox in Phase 7.

### 3.3 Email parser (`app/email_ingestion/parser.py`)
Strips quoted reply chains (`>` prefixed lines) and common reply separators (`On ... wrote:`, `-----Original Message-----`) from email bodies, returning only the clean employee question.

### 3.4 Poller (`app/email_ingestion/poller.py`)
Fetches all unread emails from the inbox, extracts the question from each, runs the full retrieval pipeline, and dispatches the result. Failed emails are marked with status `failed` and logged with the error message rather than crashing the poller.

### 3.5 Sample emails (`sample_emails/seed_inbox.py`)
Seeds the mock inbox with 10 realistic HR question emails from different senders, covering: vacation days, expense reimbursement, remote work, parental leave, password policy, business travel, performance reviews, health benefits enrollment, sick leave, and a reply-chain email (to test quoted text stripping).

### 3.6 Email simulation CLI (`email_demo.py`)
Interactive CLI that simulates the full email flow: enter sender address, subject, and body → email is added to the mock inbox → poller processes it → formatted reply is displayed with sources and validation score.

### 3.7 Tests (`tests/test_email.py`)
26 unit tests and 4 integration tests covering: inbox CRUD, duplicate handling, field preservation, reply/fail status updates, quoted text stripping, reply separator stripping, poller processing, skip-already-replied logic, multi-email batches, failure handling, reply formatting, and 4 end-to-end integration flows.

**Test result:** 26/26 unit passed; 4/4 integration passed

---

## Phase 4 — Response Delivery and Review Mode

**Date:** 2026-05-08

### 4.1 Draft store (`app/delivery/draft_store.py`)
SQLite-backed `DraftStore` that saves generated answers as reviewable drafts before sending. Each draft records: `email_id`, `sender`, `subject`, `question`, `proposed_answer`, `sources`, `validation`, `status` (`pending` / `approved` / `edited` / `rejected`), `final_answer`, `reviewer_note`, `created_at`, `reviewed_at`.

### 4.2 Dispatcher (`app/delivery/dispatcher.py`)
Routes each processed email through the review gate:
- `human_review_mode=False`: reply is formatted and written to the inbox immediately (`status: sent`)
- `human_review_mode=True`: answer is saved as a pending draft (`status: pending_review`); inbox is not updated until a reviewer approves

`send_approved_draft()` handles the approve flow: marks draft as `approved` or `edited`, formats the reply with an HR-reviewed footer, and updates the inbox.

### 4.3 Poller updated
Poller refactored to accept `human_review_mode` and `draft_store` parameters and delegate delivery to the dispatcher.

### 4.4 Reviewer CLI (`review.py`)
Interactive CLI for HR reviewers: displays each pending draft with the original question, proposed answer, sources, and validation score. Reviewer can `[A]pprove`, `[E]dit`, `[R]eject`, or `[S]kip` each draft. Edited answers replace the proposed answer in the final reply. Rejected drafts are logged with a reviewer note but not sent.

### 4.5 Tests (`tests/test_delivery.py`)
24 unit tests covering: draft store CRUD, approve/edit/reject status transitions, reviewed_at timestamps, dispatcher auto-send vs review-mode routing, missing draft_store raises `ValueError`, approved reply footer content, full poller-to-approve and poller-to-edit-to-reply flows, and 4 integration tests for full lifecycle validation.

**Test result:** 24/24 unit passed; 4/4 integration passed

---

## Phase 5 — Audit Trail and API Layer

**Date:** 2026-05-08

### 5.1 Audit store (`app/audit/audit_log.py`)
Append-only SQLite audit log (`AuditStore`). Records every email processed: `timestamp`, `email_id`, `draft_id`, `sender`, `subject`, `question`, `answer`, `final_answer`, `sources`, `validation`, `status`, `reviewer`, `error`. Supports filtered queries by `status` and `sender`, pagination, and lookup by ID. Count method supports same filters as query for accurate totals.

### 5.2 FastAPI application (`app/main.py`)
FastAPI app with five routers mounted. Auto-generates interactive Swagger UI at `/docs` and OpenAPI schema at `/openapi.json`.

### 5.3 Documents API (`app/api/documents.py`)
- `GET /documents` — list all indexed documents with doc_id and filename
- `POST /documents` — upload a PDF or DOCX file; file is saved to `uploaded_docs/` and indexed; unsupported file types return HTTP 400
- `DELETE /documents/{doc_id}` — remove a document from the vector index

### 5.4 Inbox API (`app/api/inbox.py`)
- `POST /inbox/process` — processes all unread mock inbox emails through the pipeline; respects `human_review_mode` from runtime settings; writes one audit entry per email processed

### 5.5 Drafts API (`app/api/drafts.py`)
- `GET /drafts` — list pending drafts
- `GET /drafts/{id}` — get a specific draft
- `POST /drafts/{id}/approve` — approve as-is or with an edited answer and optional reviewer name; returns HTTP 409 if already reviewed
- `POST /drafts/{id}/reject` — reject with optional note; returns HTTP 409 if already reviewed

### 5.6 Audit API (`app/api/audit.py`)
- `GET /audit` — paginated audit log with optional `status` and `sender` filters; returns total count and entries
- `GET /audit/{id}` — single audit entry by ID; returns HTTP 404 if not found

### 5.7 Settings API (`app/api/settings_api.py`)
- `GET /settings` — returns current runtime settings (`human_review_mode`, `n_results`)
- `PATCH /settings` — update settings; `n_results` is clamped to 1–20

### 5.8 Dependency injection (`app/dependencies.py`)
All shared resources (PolicyStore, DraftStore, AuditStore, MockInbox, Anthropic client, RuntimeSettings) are provided via FastAPI dependency functions. Tests override these with `app.dependency_overrides` to inject isolated temp-path instances without touching the real database or ChromaDB.

### 5.9 Circular import resolution
Removed eager re-exports from `app/delivery/__init__.py` and `app/email_ingestion/__init__.py` that were creating import cycles. Used `TYPE_CHECKING` guard in `draft_store.py` for the `Email` type annotation to break the remaining runtime cycle.

### 5.10 Tests (`tests/test_api.py`)
34 API tests using FastAPI `TestClient` with fully mocked dependencies (no real Claude calls, no shared state between tests). Covers: health check, document upload/list/delete, settings get/patch/clamp, inbox processing in both modes, draft list/get/approve/edit/reject/409-conflicts, audit list/filter/paginate/get-by-id/404.

**Test result:** 34/34 passed

---

---

## Phase 6 — Security Hardening

**Date:** 2026-05-08

### 6.1 JWT authentication (`app/auth/jwt_auth.py`)
Implemented API key → JWT exchange flow. Client POSTs their API key to `POST /auth/token`; server verifies it with `hmac.compare_digest` (constant-time, no timing attack) and returns a short-lived JWT signed with HS256. All subsequent requests must include `Authorization: Bearer <token>`. Token expiry is configurable via `JWT_EXPIRY_HOURS` env var (default: 8 hours).

### 6.2 Auth API router (`app/api/auth_api.py`)
`POST /auth/token` — accepts `{api_key}`, returns `{access_token, token_type}`. Rate-limited to 10/minute per IP. Public endpoint (no auth required to reach it).

### 6.3 Protected routes
All five data routers (documents, drafts, audit, settings, inbox) now require a valid JWT via `dependencies=[Depends(require_auth)]` in `app/main.py`. `/health`, `/`, `/static/*`, `/docs`, `/auth/token` remain public.

### 6.4 Rate limiting (`slowapi`)
- `POST /auth/token`: 10 requests/minute per IP (brute-force protection)
- `POST /inbox/process`: 10 requests/minute per IP (expensive operation)
- `POST /documents`: 20 requests/minute per IP
- Global default: 200 requests/minute per IP on all routes

### 6.5 Security headers middleware (`app/main.py`)
Every response now includes:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`

### 6.6 CORS middleware
Origins restricted to `ALLOWED_ORIGINS` env var (default: `http://localhost:8000`). Comma-separated for multiple origins.

### 6.7 File upload hardening (`app/api/documents.py`)
Added 20 MB file size limit. Requests with files exceeding this return HTTP 413.

### 6.8 New config variables (`app/config.py`, `.env.example`)
`MUSTER_API_KEY`, `JWT_SECRET`, `JWT_EXPIRY_HOURS`, `ALLOWED_ORIGINS`.

### 6.9 SPA login screen (`app/static/index.html`)
Dashboard now shows a login overlay on load if no token is in `sessionStorage`. User enters their API key, the SPA exchanges it for a JWT via `POST /auth/token`, and stores it. All subsequent `fetch()` calls include `Authorization: Bearer <token>`. 401 responses (expired token) automatically show the login screen again. Sign-out button clears the token.

### 6.10 Tests (`tests/test_security.py`)
24 unit tests covering: JWT creation/structure/expiry, wrong-secret rejection, malformed token rejection, missing token rejection, valid token acceptance, auth endpoint (valid/invalid/empty/unconfigured key, returned token validity), unauthenticated 401 on all protected endpoints, public endpoints accessibility, and all 5 security headers on both public and protected routes.

Also: `tests/conftest.py` now includes an `autouse` fixture that disables all rate limiters between tests to prevent in-memory counter accumulation from causing false failures.

**Test result:** 24/24 passed (new). All 129 unit tests pass.

---

---

## Phase 7 — Real Microsoft 365 Integration

**Date:** 2026-05-10

### 7.1 Graph API client (`app/ms365/graph_client.py`)
Authenticated wrapper around Microsoft Graph API using MSAL client-credentials flow (app-only, for shared mailboxes). Methods: `get_messages(unread_only, top)`, `send_reply(message_id, reply_text)`, `mark_as_read(message_id)`. Automatically strips HTML tags and decodes entities from message bodies (Graph returns HTML content). Reply is sent as a proper thread reply (createReply → send draft) to preserve conversation threading.

### 7.2 Graph inbox adapter (`app/ms365/graph_inbox.py`)
`GraphInbox` — drop-in replacement for `MockInbox` that satisfies the same interface. The poller and dispatcher work with no changes. Graph message IDs are used as the email `id` field. `mark_failed` marks messages as read so they aren't re-processed.

### 7.3 OAuth 2.0 stub (`app/ms365/oauth.py`)
Three endpoints (all auth-protected):
- `GET /ms365/authorize` — redirects admin to Microsoft's consent page
- `GET /ms365/callback` — receives the authorization code (token exchange is the next step when Azure app registration is finalized)
- `GET /ms365/status` — shows current M365 configuration state

### 7.4 Inbox dependency injection (`app/dependencies.py`)
`get_inbox()` returns `GraphInbox` when `MS365_USE_REAL_INBOX=true`, otherwise `MockInbox`. Zero code changes needed in the poller or any other layer — the abstraction is transparent.

### 7.5 New config variables
`MS365_TENANT_ID`, `MS365_CLIENT_ID`, `MS365_CLIENT_SECRET`, `MS365_MAILBOX`, `MS365_REDIRECT_URI`, `MS365_USE_REAL_INBOX`.

### 7.6 Tests (`tests/test_ms365.py`)
22 unit tests (all mocked — no Azure credentials required) covering: MSAL token acquisition (success + failure), Graph API `get_messages` call structure and URL, HTML stripping from message bodies, `send_reply` two-step flow (createReply + send), `mark_as_read` PATCH, all `GraphInbox` methods, OAuth authorize redirect URL, OAuth callback (code + error + missing), dependency injection switching logic. Plus 2 integration tests (skip without M365 credentials).

**Test result:** 22/22 unit tests passed

---

## Summary

| Phase | Description | Tests |
|---|---|---|
| 1 | Document indexing (parse, chunk, embed, store) | 21 |
| 2 | Retrieval + Claude answer generation + validation agent | 35 |
| 3 | Mock email inbox + poller + email parser | 30 |
| 4 | Review mode + draft store + dispatcher + reviewer CLI | 28 |
| 5 | Audit trail + FastAPI REST API (5 routers, 11 endpoints) | 34 |
| 6 | Security hardening (JWT auth, rate limiting, security headers, CORS, login UI) | 24 |
| 7 | Microsoft 365 integration (Graph API, GraphInbox, OAuth stub) | 22 |
| **Total** | | **194** |

**All 174 unit tests pass without API keys.**  
**All 20 integration tests pass with a valid `ANTHROPIC_API_KEY`.**  
**2 additional M365 integration tests available with Azure AD credentials.**

---

## Security notes

- All secrets (API keys, credentials) are loaded from `.env` and never committed to version control (`.env` is gitignored)
- No credentials are hardcoded anywhere in the codebase
- File uploads are validated by extension (PDF/DOCX only) and size (20 MB max) before processing
- Audit log is append-only; entries are never deleted
- Email content is treated as PII — only necessary metadata is stored in the audit log
- Draft approval returns HTTP 409 if a draft has already been reviewed, preventing double-processing
- Input to ChromaDB and SQLite is passed via parameterised queries — no string interpolation in SQL
- All audit `UPDATE` operations use an allowlist of permitted field names to prevent arbitrary column injection
- API key comparison uses `hmac.compare_digest` (constant-time) to prevent timing attacks
- JWT tokens signed with HS256, expire in 8 hours, verified on every protected request
- Rate limiting applied per-IP on sensitive endpoints to prevent brute-force and abuse
- Security headers set on every HTTP response (nosniff, deny framing, XSS protection, referrer policy)
