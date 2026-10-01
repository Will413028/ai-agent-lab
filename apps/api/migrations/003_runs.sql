CREATE TABLE agent_lab.runs (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES agent_lab.conversations(id) ON DELETE CASCADE,
    turn_id uuid NOT NULL UNIQUE REFERENCES agent_lab.turns(id) ON DELETE CASCADE,
    workspace_id uuid NOT NULL,
    goal text NOT NULL CHECK (length(goal) BETWEEN 1 AND 2000),
    status text NOT NULL CHECK (status IN ('running','succeeded','failed','cancelled','limit')),
    max_steps integer NOT NULL CHECK (max_steps BETWEEN 1 AND 12),
    max_calls integer NOT NULL CHECK (max_calls BETWEEN 1 AND 24),
    answer text NOT NULL DEFAULT '' CHECK (length(answer) <= 16000),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    CHECK ((status = 'running') = (finished_at IS NULL))
);
CREATE INDEX runs_by_conversation ON agent_lab.runs(conversation_id, created_at);
CREATE TABLE agent_lab.run_events (
    run_id uuid NOT NULL REFERENCES agent_lab.runs(id) ON DELETE CASCADE,
    sequence integer NOT NULL CHECK (sequence >= 0),
    payload jsonb NOT NULL,
    PRIMARY KEY (run_id,sequence)
);
