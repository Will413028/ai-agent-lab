import { describe, expect, it } from "vitest";
import { readRunEvents } from "../src/lib/runs";

const id = "00000000-0000-4000-8000-000000000001";
const started = { version: 1, run_id: id, sequence: 0, data: { type: "started", workspace_id: id, provider: "fake" } };
const done = { version: 1, run_id: id, sequence: 1, data: { type: "done", status: "succeeded", answer: "完成", usage: { source: "unknown", input_tokens: null, output_tokens: null }, code: null } };
function body(events: unknown[]) {
  const bytes = new TextEncoder().encode(events.map(event => `event: run\ndata: ${JSON.stringify(event)}\n\n`).join(""));
  return new ReadableStream<Uint8Array>({ start(controller) { for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.subarray(i, i + 7)); controller.close(); } });
}
async function read(events: unknown[]) { const rows = []; for await (const event of readRunEvents(body(events))) rows.push(event); return rows; }
describe("run contract", () => {
  it("reads chunked UTF-8 and terminal status", async () => { expect(await read([started, done])).toEqual([started, done]); });
  it("rejects missing terminal, wrong sequence, mismatched run and raw reasoning", async () => {
    for (const events of [[started], [started, { ...done, sequence: 2 }], [started, { ...done, run_id: "00000000-0000-4000-8000-000000000002" }], [started, { ...done, reasoning: "hidden" }]]) await expect(read(events)).rejects.toThrow();
  });
});
