import { describe, expect, it } from "vitest";
import { readChatEvents } from "../src/lib/chat";

const requestId = "58f4b2f7-28a2-4b26-bf16-8ab70fa9978a";
const delta = { version: 1, request_id: requestId, sequence: 0, type: "delta", text: "你好🙂\n第二行" };
const done = { version: 1, request_id: requestId, sequence: 1, type: "done", usage: null };

function frame(value: typeof delta | typeof done | Record<string, unknown>, event = String(value.type)) {
  return `event: ${event}\nid: ${value.request_id}:${value.sequence}\ndata: ${JSON.stringify(value)}\n\n`;
}

function stream(text: string, split = 1): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({ start(controller) { for (let i = 0; i < bytes.length; i += split) controller.enqueue(bytes.slice(i, i + split)); controller.close(); } });
}

async function collect(text: string) {
  const events = [];
  for await (const event of readChatEvents(stream(text))) events.push(event);
  return events;
}

describe("SSE contract", () => {
  it("decodes fragmented UTF-8, newlines and complete terminal event", async () => {
    expect(await collect(frame(delta) + frame(done))).toEqual([delta, done]);
  });
  it("handles split CRLF and comments", async () => {
    expect(await collect((": heartbeat\n\n" + frame(delta) + frame(done)).replaceAll("\n", "\r\n"))).toEqual([delta, done]);
  });
  it("accepts a typed error terminal without a done", async () => {
    const failure = { version: 1, request_id: requestId, sequence: 0, type: "error", code: "quota_exhausted", message: "額度用完", retryable: false };
    expect(await collect(frame(failure))).toEqual([failure]);
  });
  it("accepts many small frames coalesced in one large network chunk", async () => {
    const events = Array.from({ length: 600 }, (_, sequence) => ({ ...delta, sequence }));
    const ending = { ...done, sequence: events.length };
    const text = events.map((event) => frame(event)).join("") + frame(ending);
    const received = [];
    for await (const event of readChatEvents(stream(text, text.length * 4))) received.push(event);
    expect(received).toEqual([...events, ending]);
  });
  it.each([
    ["wrong header", frame(delta, "changed") + frame(done)],
    ["wrong version", frame({ ...delta, version: 2 }) + frame(done)],
    ["missing done", frame(delta)],
    ["truncated frame", frame(delta) + frame(done).slice(0, -2)],
    ["sequence gap", frame(delta) + frame({ ...done, sequence: 2 })],
    ["request changed", frame(delta) + frame({ ...done, request_id: "1960f5d4-2c93-4fd7-a91d-d61e7ae3894d" })],
    ["duplicate terminal", frame(delta) + frame(done) + frame(done)],
    ["extra payload", frame({ ...delta, reasoning: "internal" }) + frame(done)],
    ["empty stream", ""],
    ["oversized frame", `data: ${"x".repeat(65537)}\n\n`],
  ])("rejects %s", async (_name, text) => {
    await expect(collect(text)).rejects.toThrow();
  });
});
