CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE agent_lab.embedding_profile (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    model text NOT NULL,
    version text NOT NULL,
    dimension integer NOT NULL CHECK (dimension BETWEEN 1 AND 4096)
);

CREATE TABLE agent_lab.documents (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    relationship_status text NOT NULL CHECK (relationship_status IN ('general','single','dating','married')),
    digest text NOT NULL,
    markdown text NOT NULL,
    embedding_model text NOT NULL,
    embedding_version text NOT NULL,
    embedding_dimension integer NOT NULL,
    chunk_version text NOT NULL,
    chunk_count integer NOT NULL CHECK (chunk_count > 0),
    keywords jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (digest, relationship_status)
);

CREATE TABLE agent_lab.chunks (
    id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES agent_lab.documents(id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    content text NOT NULL,
    dimension integer NOT NULL,
    embedding vector NOT NULL CHECK (vector_dims(embedding) = dimension),
    UNIQUE (document_id, ordinal)
);
CREATE INDEX chunks_document ON agent_lab.chunks(document_id);

CREATE TABLE agent_lab.retrievals (
    turn_id uuid PRIMARY KEY REFERENCES agent_lab.turns(id) ON DELETE CASCADE,
    result jsonb NOT NULL
);
