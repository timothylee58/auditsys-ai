# FEAT-001: Integrate Enhanced Document Ingestion Pipeline

Status: completed

## Description
Integrate the user's enhanced document ingestion pipeline into the existing codebase.

## Review Fixes Applied
1. **Failure recovery** - Steps 4-5 (embed + store) wrapped in try/except; document marked "failed" on error with logging.
2. **Duplicate detection** - Fast path restored: checks for existing document with same content_hash + user_id in "ready" status; returns early with status="duplicate" without re-embedding.
3. **list_documents user scoping** - Added user_id parameter; query now filters by `.eq("user_id", user_id)`.
4. **soft_delete_document ownership check** - Added user_id parameter; verifies ownership before deletion; raises ValueError (404) or PermissionError (403).
5. **TODO: Unauthenticated user_id** - Comment added to routes noting auth middleware is out of scope.
6. **TODO: Embedding cache** - Comment added to service noting Redis caching could be restored.
7. **TODO: Async client reset** - Comment added to database.py about adding reset mechanism.

## v2 Review Fixes Applied
1. **_mark_document_failed chunk cleanup** - Now deletes partially-written chunks before marking the document as failed.
2. **list_documents async** - Converted from sync get_supabase() to async get_async_supabase().
3. **soft_delete_document async** - Converted from sync get_supabase() to async get_async_supabase().
4. **Orphan cleanup in _upsert_document_record** - Cleans up chunks from prior failed attempts (same content_hash + user_id) before upserting.
5. **Removed unused import** - get_supabase no longer imported since all functions use async client.

## Findings
- The fs_write and str_replace tools did not persist to the physical filesystem; had to use Python file I/O via bash.
- All 10 existing unit tests continue to pass after changes.
