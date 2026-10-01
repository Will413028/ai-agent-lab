import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "../../../../contracts/chat-event.schema.json";
import type { ChatEvent } from "./chat-event.generated";

export type Scenario = "normal" | "slow" | "rate_limit" | "quota" | "timeout" | "dependency_failure";
const ajv = new Ajv();
// Pydantic's OpenAPI discriminator mapping is annotation; oneOf validates each variant.
ajv.addKeyword({ keyword: "discriminator", valid: true });
addFormats(ajv);
const validEvent = ajv.compile<ChatEvent>(schema);
const MAX_FRAME = 64 * 1024;
const protocolError = () => new Error("回覆格式不正確或串流提早結束，請重新嘗試。");

type Frame = { event: string; id: string; data: string };

export async function* frames(body: ReadableStream<Uint8Array>, maxFrame = MAX_FRAME): AsyncGenerator<Frame> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "";
  let event = "";
  let id = "";
  let data: string[] = [];
  let size = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      while (true) {
        const match = /\r\n|\r|\n/.exec(buffer);
        if (!match || (match[0] === "\r" && match.index === buffer.length - 1 && !chunk.done)) break;
        const line = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        size += line.length + match[0].length;
        if (size > maxFrame) throw protocolError();
        if (line === "") {
          if (data.length) yield { event, id, data: data.join("\n") };
          event = "";
          id = "";
          data = [];
          size = 0;
        } else if (!line.startsWith(":")) {
          const separator = line.indexOf(":");
          const field = separator < 0 ? line : line.slice(0, separator);
          const value = separator < 0 ? "" : line.slice(separator + 1).replace(/^ /, "");
          if (field === "event") event = value;
          if (field === "id") id = value;
          if (field === "data") data.push(value);
          if (size > maxFrame) throw protocolError();
        }
      }
      if (buffer.length + size > maxFrame) throw protocolError();
      if (chunk.done) {
        if (buffer || data.length || event || id) throw protocolError();
        break;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function* readChatEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  let requestId: string | undefined;
  let sequence = 0;
  let terminal = false;
  for await (const frame of frames(body)) {
    let value: unknown;
    try { value = JSON.parse(frame.data); } catch { throw protocolError(); }
    if (!validEvent(value) || frame.event !== value.type || terminal) throw protocolError();
    requestId ??= value.request_id;
    if (requestId !== value.request_id || value.sequence !== sequence || frame.id !== `${requestId}:${sequence}`) throw protocolError();
    sequence += 1;
    terminal = value.type === "done" || value.type === "error";
    yield value;
  }
  if (!terminal) throw protocolError();
}

export async function streamChat(
  request: { message: string; scenario: Scenario },
  signal: AbortSignal,
  onEvent: (event: ChatEvent) => void,
  conversationId?: string,
  retrieval?: { relationship_status: string | null; threshold: number; top_k: number },
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(conversationId ? `/api/conversations/${encodeURIComponent(conversationId)}/${retrieval ? "rag" : "chat"}` : "/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ ...request, ...retrieval }), signal,
    });
  } catch (failure) {
    if (signal.aborted) throw failure;
    throw new Error("無法連接服務，請確認服務已啟動後再試。");
  }
  if (!response.ok) {
    if (conversationId) {
      const body = await response.json().catch(() => null);
      if (typeof body?.detail?.message === "string") throw new Error(body.detail.message);
    }
    throw new Error(response.status === 422 ? "訊息格式不正確，請檢查後再試。" : "服務暫時無法使用，請稍後再試。");
  }
  if (!response.headers.get("content-type")?.startsWith("text/event-stream") || !response.body) throw protocolError();
  for await (const event of readChatEvents(response.body)) onEvent(event);
}
