
-- ===========================================================================
-- Increment 003 — hash-chained audit log
-- ===========================================================================
-- One row per answered or refused question. Each row stores the previous
-- row's hash; entry_hash = sha256(prev_hash || E'\n' || canonical). See
-- app/audit/chain.py (the application computes the hashes; `canonical` is
-- the exact string that was hashed, kept beside the queryable jsonb payload
-- so verification never depends on Postgres JSON re-serialisation).
--
-- * prev_hash is UNIQUE: two concurrent writers cannot fork the chain; the
--   loser's insert fails with 23505 and the app re-reads the head and retries.
-- * seq is an identity column. Failed/retried inserts may leave gaps in seq;
--   gaps are normal. Integrity is the hash linkage, not seq continuity.
-- * UPDATE, DELETE and TRUNCATE are blocked for EVERY role (including the
--   service role, which bypasses RLS) by triggers, same as audit_log.
-- * The table records references and hashes, not raw document text.

create table if not exists audit_chain (
    seq bigint generated always as identity primary key,
    prev_hash text not null unique,
    entry_hash text not null unique,
    canonical text not null,
    payload jsonb not null,
    user_id text,
    created_at timestamptz not null default now(),
    constraint audit_chain_hash_format_chk check (
        prev_hash ~ '^[0-9a-f]{64}$' and entry_hash ~ '^[0-9a-f]{64}$'
    ),
    constraint audit_chain_not_self_linked_chk check (prev_hash <> entry_hash)
);

create index if not exists audit_chain_user_seq_idx on audit_chain (user_id, seq desc);

alter table audit_chain enable row level security;

drop policy if exists service_role_insert_audit_chain on audit_chain;
create policy service_role_insert_audit_chain on audit_chain
    for insert with check (auth.role() = 'service_role');

drop policy if exists service_role_select_audit_chain on audit_chain;
create policy service_role_select_audit_chain on audit_chain
    for select using (auth.role() = 'service_role');

create or replace function prevent_audit_chain_mutation()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception 'audit_chain is append-only: % is not permitted', tg_op;
end;
$$;

drop trigger if exists audit_chain_immutable on audit_chain;
create trigger audit_chain_immutable
before update or delete on audit_chain
for each row execute function prevent_audit_chain_mutation();

drop trigger if exists audit_chain_no_truncate on audit_chain;
create trigger audit_chain_no_truncate
before truncate on audit_chain
for each statement execute function prevent_audit_chain_mutation();
