# AuditSys AI v2 scope

## Product boundary

AuditSys AI v2 is an evidence-grounded audit operations workspace. It helps
authorized audit teams upload evidence, locate relevant passages, obtain cited
draft answers, and route weak or high-risk findings to a reviewer.

It does not reach autonomous audit conclusions, enforce policy, alter external
finance or ERP systems, provide broad document collaboration, or attempt to
support every file format. The initial ingestion release accepts PDF and XLSX
only.

## First implementation milestone

The v2 foundation introduces these durable concepts:

- organizations and member roles;
- documents and extracted evidence chunks;
- cited query records;
- review items and append-only decisions;
- append-only audit events;
- a private `audit-evidence` Storage bucket.

The FastAPI service is the sole data-access layer. Browser clients receive no
database or Storage table grants, and all production routes must authenticate a
user and resolve their organization membership before accessing data.

## Delivery order

1. Apply the versioned Supabase migration and configure server-only secrets.
2. Add verified Supabase Auth to FastAPI, including organization membership
   checks and role enforcement.
3. Ship PDF/XLSX upload, extraction, chunking, and embedding jobs.
4. Replace the query stub with retrieval, citations, and a confidence gate.
5. Implement reviewer decisions and evaluation regressions.

## Completion criteria for v2

- A user can only access records for organizations they belong to.
- Every displayed answer contains source metadata or is explicitly withheld.
- Low-confidence answers create review work rather than a final conclusion.
- Upload, query, and review actions produce immutable audit events.
- Automated tests cover tenant isolation, file validation, and approval flow.
