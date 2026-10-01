CREATE TABLE agent_lab.conversations (
    id uuid PRIMARY KEY,
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE agent_lab.turns (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES agent_lab.conversations(id) ON DELETE CASCADE,
    position integer NOT NULL CHECK (position > 0),
    question text NOT NULL CHECK (length(question) BETWEEN 1 AND 2000),
    answer text NOT NULL DEFAULT '' CHECK (length(answer) <= 16000),
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (conversation_id, position),
    CHECK ((status = 'running') = (finished_at IS NULL))
);
CREATE UNIQUE INDEX one_running_turn ON agent_lab.turns(conversation_id) WHERE status = 'running';
CREATE TABLE agent_lab.reports (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES agent_lab.conversations(id) ON DELETE CASCADE,
    source_position integer NOT NULL CHECK (source_position > 0),
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX reports_by_conversation ON agent_lab.reports(conversation_id, created_at DESC);
