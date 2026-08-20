-- AuditSys AI — Supabase schema
-- Run against a Supabase Postgres project (pgvector extension required).

create extension if not exists vector;
create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- documents
-- ---------------------------------------------------------------------------
create table if not exists documents (
    id uuid primary key default gen_random_uuid(),
    filename text not null,
    entity text,
    doc_date date,
    content_hash text not null,
    page_count int not null default 0,
    chunk_count int not null default 0,
    status text not null default 'processing', -- processing | indexed | failed | deleted
    uploaded_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists documents_status_idx on documents (status);
create unique index if not exists documents_content_hash_idx on documents (content_hash);

-- ---------------------------------------------------------------------------
-- document_chunks
-- ---------------------------------------------------------------------------
create table if not exists document_chunks (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents (id) on delete cascade,
    chunk_index int not null,
    content text not null,
    embedding vector(3072), -- text-embedding-3-large
    page_number int,
    token_count int,
    created_at timestamptz not null default now()
);

create index if not exists document_chunks_document_id_idx on document_chunks (document_id);
create index if not exists document_chunks_embedding_idx
    on document_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- ---------------------------------------------------------------------------
-- audit_log (append-only)
-- ---------------------------------------------------------------------------
create table if not exists audit_log (
    id uuid primary key default gen_random_uuid(),
    session_id text not null,
    user_id text,
    query text not null,
    answer text,
    citations jsonb not null default '[]'::jsonb,
    confidence_score numeric,
    prompt_version text,
    model_name text,
    trace_id text,
    status text not null default 'answered', -- answered | pending_review | rejected
    review_item_id uuid,
    pii_detected boolean not null default false,
    validation_passed boolean not null default true,
    validation_errors jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists audit_log_session_id_idx on audit_log (session_id);
create index if not exists audit_log_created_at_idx on audit_log (created_at desc);
create index if not exists audit_log_status_idx on audit_log (status);

-- ---------------------------------------------------------------------------
-- review_queue (HITL)
-- ---------------------------------------------------------------------------
create table if not exists review_queue (
    id uuid primary key default gen_random_uuid(),
    session_id text not null,
    user_id text,
    query text not null,
    draft_answer text not null,
    citations jsonb not null default '[]'::jsonb,
    confidence_score numeric,
    status text not null default 'pending', -- pending | approved | rejected | overridden
    reviewer_id text,
    reviewed_at timestamptz,
    reviewer_action text, -- approve | reject | override
    override_answer text,
    reviewer_notes text,
    created_at timestamptz not null default now()
);

create index if not exists review_queue_status_idx on review_queue (status);
create index if not exists review_queue_session_id_idx on review_queue (session_id);

-- ---------------------------------------------------------------------------
-- eval_results
-- ---------------------------------------------------------------------------
create table if not exists eval_results (
    id uuid primary key default gen_random_uuid(),
    run_id text not null,
    dataset_name text not null default 'financial_qa_v1',
    faithfulness numeric,
    answer_relevancy numeric,
    context_recall numeric,
    context_precision numeric,
    per_question jsonb not null default '[]'::jsonb,
    status text not null default 'completed', -- running | completed | failed
    created_at timestamptz not null default now()
);

create index if not exists eval_results_run_id_idx on eval_results (run_id);

-- ---------------------------------------------------------------------------
-- document_schema_registry — tracks extracted-field schemas per document type
-- ---------------------------------------------------------------------------
create table if not exists document_schema_registry (
    id uuid primary key default gen_random_uuid(),
    document_type text not null,
    schema_version text not null,
    field_definitions jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create unique index if not exists document_schema_registry_type_version_idx
    on document_schema_registry (document_type, schema_version);

-- ---------------------------------------------------------------------------
-- financial_metrics_view — placeholder, populated once metric extraction ships
-- ---------------------------------------------------------------------------
create or replace view financial_metrics_view as
select
    d.id as document_id,
    d.filename,
    d.entity,
    d.doc_date,
    null::text as metric_name,
    null::numeric as metric_value,
    null::text as unit
from documents d
where false; -- empty placeholder until metric extraction is implemented

-- ---------------------------------------------------------------------------
-- match_document_chunks — pgvector similarity search RPC
-- ---------------------------------------------------------------------------
create or replace function match_document_chunks (
    query_embedding vector(3072),
    match_count int default 6,
    filter_document_ids uuid[] default null
)
returns table (
    id uuid,
    document_id uuid,
    content text,
    page_number int,
    similarity float
)
language sql stable
as $$
    select
        c.id,
        c.document_id,
        c.content,
        c.page_number,
        1 - (c.embedding <=> query_embedding) as similarity
    from document_chunks c
    join documents d on d.id = c.document_id
    where d.status = 'indexed'
        and (filter_document_ids is null or c.document_id = any (filter_document_ids))
    order by c.embedding <=> query_embedding
    limit match_count;
$$;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table documents enable row level security;
alter table document_chunks enable row level security;
alter table audit_log enable row level security;
alter table review_queue enable row level security;
alter table eval_results enable row level security;
alter table document_schema_registry enable row level security;

-- Service role (backend) has full access; the API server always connects
-- with the Supabase service key, never a browser-exposed anon key.
create policy service_role_all_documents on documents
    for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
create policy service_role_all_document_chunks on document_chunks
    for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
create policy service_role_all_review_queue on review_queue
    for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
create policy service_role_all_eval_results on eval_results
    for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
create policy service_role_all_document_schema_registry on document_schema_registry
    for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');

-- audit_log is append-only: service role may insert/select, nobody may
-- update or delete rows (including the service role) to preserve the
-- integrity of the audit trail.
create policy service_role_insert_audit_log on audit_log
    for insert with check (auth.role() = 'service_role');
create policy service_role_select_audit_log on audit_log
    for select using (auth.role() = 'service_role');
