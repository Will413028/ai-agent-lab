import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "../../../../contracts/runs.schema.json";
import { frames } from "./chat";
import type { Run, RunEvent, RunRequest } from "./runs.generated";

export type { Run, RunEvent };
const ajv = new Ajv();
ajv.addKeyword({ keyword: "discriminator", valid: true });
addFormats(ajv); ajv.addSchema(schema, "runs");
const validateRun = ajv.compile<Run>({ $ref: "runs#/$defs/Run" });
const validateEvent = ajv.compile<RunEvent>({ $ref: "runs#/$defs/RunEvent" });
const invalid = () => new Error("任務串流格式不正確或提前結束。");

export async function* readRunEvents(body: ReadableStream<Uint8Array>) {
  let runId: string | undefined;
  let sequence = 0;
  let done = false;
  for await (const frame of frames(body, 1024 * 1024)) {
    let value: unknown;
    try { value = JSON.parse(frame.data); } catch { throw invalid(); }
    if (!validateEvent(value) || frame.event !== "run" || value.version !== 1 || !value.data.type || done) throw invalid();
    runId ??= value.run_id;
    if (value.run_id !== runId || value.sequence !== sequence || (sequence === 0 && value.data.type !== "started")) throw invalid();
    sequence++;
    done = value.data.type === "done";
    yield value;
  }
  if (!done) throw invalid();
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, init);
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail?.message ?? "任務操作失敗。");
  return data;
}
export const runs = {
  async list(conversationId: string): Promise<Run[]> {
    const rows = await request(`/api/conversations/${encodeURIComponent(conversationId)}/runs`);
    if (!Array.isArray(rows) || !rows.every(row => validateRun(row))) throw invalid();
    return rows;
  },
  async get(conversationId: string, runId: string): Promise<Run> {
    const row = await request(`/api/conversations/${encodeURIComponent(conversationId)}/runs/${encodeURIComponent(runId)}`);
    if (!validateRun(row)) throw invalid();
    return row;
  },
  async cancel(conversationId: string, runId: string) {
    await request(`/api/conversations/${encodeURIComponent(conversationId)}/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
  },
  async stream(conversationId: string, body: RunRequest, signal: AbortSignal, onEvent: (event: RunEvent) => void) {
    const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/runs/stream`, {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body), signal,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.detail?.message ?? "無法啟動任務。");
    }
    if (!response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) throw invalid();
    for await (const event of readRunEvents(response.body)) onEvent(event);
  },
};
