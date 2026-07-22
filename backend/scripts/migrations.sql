-- =============================================================================
-- AuditSys AI — Supabase Database Migrations
-- =============================================================================
-- Requires: pgvector extension enabled in Supabase project settings
-- Run via Supabase SQL Editor or supabase db push
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- TABLE: documents
-- Stores metadata for uploaded PDF documents
-- =============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'indexed', 'deleted')),
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL,
    uploaded_by TEXT NOT NULL DEFAULT 'system',
    entity TEXT,
    doc_date TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_status ON documents (status) WHERE status != 'deleted';
CREATE INDEX idx_documents_uploaded_by ON documents (uploaded_by);
CREATE INDEX idx_documents_uploaded_at ON documents (uploaded_at DESC);

-- =============================================================================
-- TABLE: document_chunks
-- Stores chunked text with vector embeddings for semantic search
-- =============================================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(3072),  -- text-embedding-3-large outputs 3072 dimensions
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chunks_document_id ON document_chunks (document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- =============================================================================
-- TABLE: audit_log
-- Append-only audit trail for all query interactions
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    answer TEXT,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence_score FLOAT NOT NULL DEFAULT 0.0,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'answered'
        CHECK (status IN ('answered', 'pending_review', 'rejected', 'overridden')),
    review_item_id UUID,
    pii_detected BOOLEAN NOT NULL DEFAULT false,
    validation_passed BOOLEAN NOT NULL DEFAULT true,
    validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit log is append-only: no UPDATE or DELETE triggers
CREATE INDEX idx_audit_log_session_id ON audit_log (session_id);
CREATE INDEX idx_audit_log_user_id ON audit_log (user_id);
CREATE INDEX idx_audit_log_status ON audit_log (status);
CREATE INDEX idx_audit_log_created_at ON audit_log (created_at DESC);
CREATE INDEX idx_audit_log_confidence ON audit_log (confidence_score);
CREATE INDEX idx_audit_log_pii ON audit_log (pii_detected) WHERE pii_detected = true;

-- =============================================================================
-- TABLE: review_queue
-- Human-in-the-Loop compliance review items
-- =============================================================================
CREATE TABLE IF NOT EXISTS review_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    draft_answer TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence_score FLOAT NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'overridden')),
    reviewer_id TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewer_action TEXT
        CHECK (reviewer_action IN ('approve', 'reject', 'override')),
    override_answer TEXT,
    reviewer_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_review_queue_status ON review_queue (status);
CREATE INDEX idx_review_queue_session_id ON review_queue (session_id);
CREATE INDEX idx_review_queue_created_at ON review_queue (created_at DESC);

-- =============================================================================
-- TABLE: eval_results
-- Stores RAGAS evaluation run results
-- =============================================================================
CREATE TABLE IF NOT EXISTS eval_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    dataset_size INTEGER,
    created_by TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX idx_eval_results_status ON eval_results (status);
CREATE INDEX idx_eval_results_started_at ON eval_results (started_at DESC);

-- =============================================================================
-- TABLE: document_schema_registry
-- Registry for tracking document schema versions
-- =============================================================================
CREATE TABLE IF NOT EXISTS document_schema_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schema_name TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 1,
    schema_definition JSONB NOT NULL DEFAULT '{}'::jsonb,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- VIEW: financial_metrics_view
-- Placeholder view for financial metrics aggregation
-- =============================================================================
CREATE OR REPLACE VIEW financial_metrics_view AS
SELECT
    date_trunc('day', created_at) AS metric_date,
    COUNT(*) AS total_queries,
    COUNT(*) FILTER (WHERE status = 'answered') AS answered_queries,
    COUNT(*) FILTER (WHERE status = 'pending_review') AS pending_queries,
    COUNT(*) FILTER (WHERE status = 'rejected') AS rejected_queries,
    AVG(confidence_score) AS avg_confidence,
    COUNT(*) FILTER (WHERE pii_detected = true) AS pii_flagged_count
FROM audit_log
GROUP BY date_trunc('day', created_at)
ORDER BY metric_date DESC;

-- =============================================================================
-- FUNCTION: match_document_chunks
-- pgvector RPC for semantic similarity search
-- =============================================================================
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding vector(3072),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INTEGER DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    chunk_index INTEGER,
    content TEXT,
    token_count INTEGER,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.chunk_index,
        dc.content,
        dc.token_count,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    INNER JOIN documents d ON d.id = dc.document_id
    WHERE d.status = 'indexed'
        AND 1 - (dc.embedding <=> query_embedding) > match_threshold
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- =============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- =============================================================================

-- Enable RLS on all tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE eval_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_schema_registry ENABLE ROW LEVEL SECURITY;

-- Documents: users can read their own, service role can do all
CREATE POLICY "Users can view their own documents"
    ON documents FOR SELECT
    USING (auth.uid()::text = uploaded_by OR auth.role() = 'service_role');

CREATE POLICY "Service role full access to documents"
    ON documents FOR ALL
    USING (auth.role() = 'service_role');

-- Document chunks: inherit access from parent document
CREATE POLICY "Users can view chunks of their documents"
    ON document_chunks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM documents d
            WHERE d.id = document_chunks.document_id
                AND (d.uploaded_by = auth.uid()::text OR auth.role() = 'service_role')
        )
    );

CREATE POLICY "Service role full access to chunks"
    ON document_chunks FOR ALL
    USING (auth.role() = 'service_role');

-- Audit log: append-only for service role, read for users' own entries
CREATE POLICY "Users can view their own audit entries"
    ON audit_log FOR SELECT
    USING (auth.uid()::text = user_id OR auth.role() = 'service_role');

CREATE POLICY "Service role can insert audit entries"
    ON audit_log FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

-- Prevent updates and deletes on audit_log (append-only)
CREATE POLICY "No updates on audit log"
    ON audit_log FOR UPDATE
    USING (false);

CREATE POLICY "No deletes on audit log"
    ON audit_log FOR DELETE
    USING (false);

-- Review queue: reviewers and service role can access
CREATE POLICY "Users can view their own review items"
    ON review_queue FOR SELECT
    USING (auth.uid()::text = user_id OR auth.role() = 'service_role');

CREATE POLICY "Service role full access to review queue"
    ON review_queue FOR ALL
    USING (auth.role() = 'service_role');

-- Eval results: read for all authenticated, write for service role
CREATE POLICY "Authenticated users can view eval results"
    ON eval_results FOR SELECT
    USING (auth.role() IN ('authenticated', 'service_role'));

CREATE POLICY "Service role full access to eval results"
    ON eval_results FOR ALL
    USING (auth.role() = 'service_role');

-- Schema registry: read for all, write for service role
CREATE POLICY "Authenticated users can view schema registry"
    ON document_schema_registry FOR SELECT
    USING (auth.role() IN ('authenticated', 'service_role'));

CREATE POLICY "Service role full access to schema registry"
    ON document_schema_registry FOR ALL
    USING (auth.role() = 'service_role');

-- =============================================================================
-- TRIGGERS: updated_at auto-update
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER set_schema_registry_updated_at
    BEFORE UPDATE ON document_schema_registry
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
