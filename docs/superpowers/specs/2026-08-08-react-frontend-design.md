# React Frontend — Design Spec

## Problem

Exam Partner currently ships a server-rendered Jinja2 + HTMX frontend. It works, but it is visually unstyled and cannot express the approved product design. The user approved a specific visual direction (see "Visual Direction" below) that requires a real component-based frontend.

This spec covers replacing the Jinja2/HTMX frontend with a React single-page application, and adding the JSON API layer that SPA requires. **No RAG, extraction, embedding, or retrieval behavior changes.** The backend's domain logic is already built and tested; this work adds an API surface over it and a new frontend on top.

## Approved visual direction

Monochrome, document-first. Reference points: NotebookLM (numbered sources, inline citations) and Profound (hairline data tables, monospace metadata labels).

- **White paper canvas; near-black is the only accent.** Buttons, avatar, logo mark, and active navigation are solid black. There is no brand hue.
- **Warm-biased neutrals** (`#FAF9F7`, `#E7E5E1`) so greys read as paper rather than generic slate.
- **Status color is the only color**, desaturated, and appears only as a 5px dot plus a small monospace label — never as a filled badge.
- **Two typefaces with distinct jobs:** Instrument Sans for anything read as prose; IBM Plex Mono for data — filenames, counts, timestamps, section labels, citation numbers.
- **Hairline borders (1px), small radii (6–8px), no decorative shadows** except a single soft shadow on popover menus.
- Both light and dark themes are required.

The approved mockup is the visual contract: https://claude.ai/code/artifact/4bdb815a-4f06-4abb-b8ff-f71169df65b3

## Screens

1. **Log in** — centered single column, no split marketing panel, no decorative graphics.
2. **Sign up** — same layout as log in.
3. **Subjects** — a data table (Subject / Documents / Last asked / Status), not a card grid.
4. **Subject detail** — two panes: a numbered Sources rail on the left, chat on the right.

Chat answers render as prose with inline numbered citation chips that map to the numbered source list, plus a source footer beneath each grounded answer. "Not found in your material" and general-AI answers are marked with a left rule and a monospace label rather than colored buttons.

## Architecture

- **Frontend:** React 18 + TypeScript, built with Vite. React Router for routing. TanStack Query for server state (it gives document-status polling and cache invalidation for free, which this app genuinely needs). Plain CSS with custom properties for design tokens — no CSS framework, because the design is specific and a utility framework would fight it.
- **Backend:** the existing FastAPI app gains a JSON API under `/api/*`. Domain functions (`create_subject`, `process_document`, `answer_question`, …) are reused unchanged; only the route layer is new.
- **Session:** unchanged mechanism — a signed cookie via Starlette's `SessionMiddleware`, holding `user_id`. The SPA calls `GET /api/auth/me` on load to restore the session, and every request sends credentials. Cookie settings become explicit (14-day lifetime, `httponly`, `samesite=lax`, `secure` off in dev and on in production).
- **Dev topology:** Vite's dev server proxies `/api` to FastAPI, so the browser only ever talks to one origin. This avoids CORS entirely and makes cookies behave exactly as they will in production.
- **Production topology:** `npm run build` emits `frontend/dist`; FastAPI serves those static assets and returns `index.html` for any non-`/api` path so client-side routing works on refresh.

## API contract

All endpoints are session-authenticated and scoped to the logged-in user. Unauthenticated requests to `/api/*` return `401` with a JSON body — never an HTML redirect.

```
POST   /api/auth/signup            {email, password}  -> 201 {user}      | 400 {detail}
POST   /api/auth/login             {email, password}  -> 200 {user}      | 401 {detail}
POST   /api/auth/logout                               -> 204
GET    /api/auth/me                                   -> 200 {user}      | 401

GET    /api/subjects                                  -> 200 {subjects: [SubjectSummary]}
POST   /api/subjects               {name}             -> 201 {subject}   | 400
GET    /api/subjects/{id}                             -> 200 {subject}   | 404
PATCH  /api/subjects/{id}          {name}             -> 200 {subject}   | 404
DELETE /api/subjects/{id}                             -> 204

GET    /api/subjects/{id}/documents                   -> 200 {documents: [Document]}
POST   /api/subjects/{id}/documents   (multipart)     -> 202 {document}  | 400
DELETE /api/subjects/{id}/documents/{doc_id}          -> 204

GET    /api/subjects/{id}/messages                    -> 200 {messages: [Message]}
POST   /api/subjects/{id}/messages         {question} -> 200 {message}
POST   /api/subjects/{id}/messages/general {question} -> 200 {message}
```

`SubjectSummary` carries the counts the subjects table displays: `document_count`, `processing_count`, `failed_count`, and `last_asked_at`. Computing these per subject is a new backend concern; the current `list_subjects` returns only name and creation time.

## Changes required in existing backend code

Three gaps surfaced while specifying this, each a real defect for the new UI:

1. **The global 401 handler redirects to `/login` with a 303.** Added for the HTML frontend, it would make `GET /api/auth/me` return an HTML page instead of a 401, breaking session bootstrap. The handler must skip paths under `/api/`.
2. **Chat messages do not persist `found`.** The "not found → offer a general answer" state is currently inferred in a Jinja template from `response_mode == "rag" and not citations`. Reloading history in the SPA needs the flag stored explicitly. New messages persist `found`; messages written before this change are read with the same inferred fallback so old history still renders correctly.
3. **Documents cannot be deleted.** The Sources rail offers deletion, so a delete endpoint is needed — and it must remove the document's chunks from the vector store, not just the document record, or deleted material would still be retrievable in answers.

## Data flow

**Session bootstrap.** On mount, the app calls `GET /api/auth/me`. While it is in flight the app renders nothing (no flash of the login screen). A `200` populates auth context; a `401` sends the user to `/login`. Any later `401` from any request clears auth context and redirects to `/login`.

**Uploading.** The file posts to `POST /api/subjects/{id}/documents`, which returns `202` immediately with status `processing` — the backend continues extraction, chunking, and embedding in a background task. The Sources rail polls `GET /api/subjects/{id}/documents` every 3 seconds while any document is `processing`, and stops polling once all are settled.

**Asking.** A question posts to `POST /api/subjects/{id}/messages`. The response carries `answer`, `citations`, `response_mode`, and `found`. When `found` is false the UI renders the "Not in your material" block with a button that posts the same question to `/messages/general`, which returns a message tagged `response_mode: "general"` with no citations.

**Citation numbering.** Citation chips are numbered per message: the message's citation list is deduplicated by `filename + source_label`, and the resulting order assigns `[1]`, `[2]`, … The numbers shown in the Sources rail are independent — they index that subject's document list. This is a deliberate choice; a single global numbering across a whole conversation would renumber earlier answers whenever a document was added.

## Components

- **Design tokens** — one CSS file holding the approved palette, type scale, radii, and both themes. Every other stylesheet reads from it and never hardcodes a color.
- **Primitives** — `Button`, `Input`/`Field`, `StatusDot`, `MonoLabel`, `Card`. Small, presentational, no data fetching.
- **Auth** — `AuthProvider` (context + session bootstrap), `useAuth`, `ProtectedRoute`, `LoginPage`, `SignupPage`.
- **Subjects** — `SubjectsPage`, `SubjectsTable`, `NewSubjectDialog`.
- **Subject detail** — `SubjectDetailPage`, `SourcesPanel` (dropzone + document list + polling), `ChatPanel` (thread + composer), `ChatMessage` (renders grounded / not-found / general variants).
- **API client** — a single `lib/api.ts` wrapper that always sends credentials, parses JSON, and converts a `401` into a typed error the auth layer can catch. Nothing else in the app calls `fetch` directly.

## Error handling

- **Invalid credentials / duplicate email** — the API returns `400`/`401` with a `detail` string; the form renders it inline beneath the field.
- **Session expiry mid-use** — any `401` clears auth context and redirects to `/login`; the user is not left staring at a broken screen.
- **Upload rejected or processing failed** — the document row shows `Failed` with the backend's reason and offers deletion. Existing backend retry-with-backoff for Gemini and Atlas is unchanged.
- **Network failure** — TanStack Query surfaces the error; lists show a retry affordance rather than an empty state that looks like "no data."
- **Asking with no ready documents** — the composer explains that material must finish indexing first, instead of posting a question that can only fail to match.

## Testing

- **Backend** — pytest, as today, against `mongomock` with Gemini mocked. Each new API endpoint gets tests for its success shape, its auth requirement (`401` as JSON, not a redirect), and its user-scoping (one user cannot read another's data).
- **Frontend** — Vitest + React Testing Library, with MSW mocking the API. Cover the pieces where logic actually lives: session bootstrap and redirect, the citation-numbering function, the document-polling stop condition, and the not-found → general-answer flow. Presentational primitives are not unit tested.
- **Manual** — the full flow against the real backend: sign up, create a subject, upload a PDF and a handwritten photo, ask a grounded question, ask an unanswerable one and take the general fallback, refresh mid-session to confirm the session restores, log out, and confirm a second user sees none of the first user's data.

## Out of scope

- Any change to RAG, extraction, chunking, embedding, or retrieval behavior.
- Deployment and hosting (still local-only).
- Real-time streaming of answers (answers arrive whole).
- Reranking after vector search (already deferred in the original spec).
- Account settings. The session menu offers only the signed-in email and Log out — a settings entry that did nothing would be worse than its absence.
- Subject rename in the UI — the API supports it, the UI does not expose it yet.
