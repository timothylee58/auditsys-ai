create extension if not exists pgcrypto;
create extension if not exists vector;

create type public.member_role as enum ('admin', 'auditor', 'reviewer');
create type public.document_status as enum ('uploaded', 'processing', 'indexed', 'needs_review', 'failed');
create type public.review_status as enum ('open', 'in_review', 'approved', 'rejected', 'escalated');
create type public.review_severity as enum ('low', 'medium', 'high', 'critical');

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 200),
  created_at timestamptz not null default now()
);

create table public.organization_members (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role public.member_role not null default 'auditor',
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 512),
  media_type text not null check (media_type in (
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  )),
  storage_path text not null unique,
  content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 26214400),
  status public.document_status not null default 'uploaded',
  risk_score smallint check (risk_score between 0 and 100),
  uploaded_by uuid not null references auth.users(id),
  uploaded_at timestamptz not null default now(),
  indexed_at timestamptz,
  unique (organization_id, content_sha256)
);

create index documents_organization_uploaded_idx on public.documents (organization_id, uploaded_at desc);

create table public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  sequence_no integer not null check (sequence_no >= 0),
  page_number integer check (page_number > 0),
  content text not null check (char_length(content) > 0),
  embedding vector,
  created_at timestamptz not null default now(),
  unique (document_id, sequence_no)
);

create table public.audit_queries (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  question text not null check (char_length(question) between 3 and 2000),
  answer text,
  confidence numeric(4, 3) check (confidence between 0 and 1),
  flagged_for_review boolean not null default false,
  requested_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table public.query_sources (
  query_id uuid not null references public.audit_queries(id) on delete cascade,
  document_chunk_id uuid not null references public.document_chunks(id) on delete restrict,
  relevance_score numeric(5, 4) check (relevance_score between 0 and 1),
  primary key (query_id, document_chunk_id)
);

create table public.review_items (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  query_id uuid references public.audit_queries(id) on delete set null,
  title text not null check (char_length(title) between 1 and 500),
  severity public.review_severity not null,
  status public.review_status not null default 'open',
  assignee_id uuid references auth.users(id) on delete set null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index review_items_queue_idx on public.review_items (organization_id, status, severity, created_at desc);

create table public.review_decisions (
  id uuid primary key default gen_random_uuid(),
  review_item_id uuid not null references public.review_items(id) on delete cascade,
  decision public.review_status not null check (decision in ('approved', 'rejected', 'escalated')),
  rationale text not null check (char_length(rationale) between 1 and 4000),
  decided_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table public.audit_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  actor_id uuid references auth.users(id) on delete set null,
  action text not null check (char_length(action) between 1 and 100),
  target_type text not null check (char_length(target_type) between 1 and 100),
  target_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index audit_events_organization_created_idx on public.audit_events (organization_id, created_at desc);

create or replace function public.prevent_audit_event_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'audit events are immutable';
end;
$$;

create trigger audit_events_immutable
before update or delete on public.audit_events
for each row execute function public.prevent_audit_event_mutation();

alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.documents enable row level security;
alter table public.document_chunks enable row level security;
alter table public.audit_queries enable row level security;
alter table public.query_sources enable row level security;
alter table public.review_items enable row level security;
alter table public.review_decisions enable row level security;
alter table public.audit_events enable row level security;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'audit-evidence',
  'audit-evidence',
  false,
  26214400,
  array[
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ]
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
