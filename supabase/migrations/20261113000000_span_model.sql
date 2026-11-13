
-- ===========================================================================
-- Increment 002 — span model (audit-grade citations)
-- ===========================================================================
-- Every chunk becomes a citable span: (document id, version, page, character
-- range, content hash) plus a deterministic span_id. See app/cite/spans.py;
-- the span_id formula below MUST match span_id_for() there:
--     sha256(document_id|version|chunk_index|content_hash) hex, first 32 chars
-- Chunks ingested before this increment are backfilled with content_hash and
-- span_id. Their character offsets are unknown (NULL) until the document is
-- re-ingested; text and hash remain verifiable.
-- Deploy note: ship the app version that writes these columns before, or
-- together with, this migration — span_id/content_hash become NOT NULL.

alter table documents
    add column if not exists version int not null default 1;

alter table document_chunks
    add column if not exists span_id text,
    add column if not exists char_start int,
    add column if not exists char_end int,
    add column if not exists content_hash text;

update document_chunks
set content_hash = encode(sha256(convert_to(content, 'UTF8')), 'hex')
where content_hash is null;

update document_chunks c
set span_id = substr(
    encode(
        sha256(convert_to(
            c.document_id::text || '|' || d.version::text || '|' ||
            c.chunk_index::text || '|' || c.content_hash,
            'UTF8'
        )),
        'hex'
    ),
    1, 32
)
from documents d
where d.id = c.document_id and c.span_id is null;

alter table document_chunks
    alter column span_id set not null,
    alter column content_hash set not null;

create unique index if not exists document_chunks_span_id_idx
    on document_chunks (span_id);

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'document_chunks_span_range_chk'
    ) then
        alter table document_chunks
            add constraint document_chunks_span_range_chk
            check (
                (char_start is null and char_end is null)
                or (char_start is not null and char_end is not null
                    and char_start >= 0 and char_end > char_start)
            );
    end if;
end
$$;

-- match_document_chunks now also returns the span fields. The return type
-- changes, so the function must be dropped first (CREATE OR REPLACE cannot).
drop function if exists match_document_chunks (vector, int, uuid[], uuid, double precision);

create function match_document_chunks (
    query_embedding vector(3072),
    match_count int default 6,
    filter_document_ids uuid[] default null,
    user_id uuid default null,
    match_threshold float default 0.0
)
returns table (
    id uuid,
    document_id uuid,
    content text,
    page_number int,
    similarity float,
    text text,
    source text,
    page int,
    entity text,
    doc_date date,
    score float,
    span_id text,
    version int,
    char_start int,
    char_end int,
    content_hash text
)
language sql stable
set search_path = public, extensions
as $$
    select
        c.id,
        c.document_id,
        c.content,
        c.page_number,
        1 - (c.embedding::halfvec(3072) <=> query_embedding::halfvec(3072)) as similarity,
        c.content as text,
        d.filename as source,
        c.page_number as page,
        d.entity,
        d.doc_date,
        1 - (c.embedding::halfvec(3072) <=> query_embedding::halfvec(3072)) as score,
        c.span_id,
        d.version,
        c.char_start,
        c.char_end,
        c.content_hash
    from document_chunks c
    join documents d on d.id = c.document_id
    where d.status = 'indexed'
        and (filter_document_ids is null or c.document_id = any (filter_document_ids))
        and d.uploaded_by = match_document_chunks.user_id
        and (1 - (c.embedding::halfvec(3072) <=> query_embedding::halfvec(3072))) >= match_threshold
    order by c.embedding::halfvec(3072) <=> query_embedding::halfvec(3072)
    limit match_count;
$$;
