import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "../../../../contracts/conversation.schema.json";
import type { Conversation, ConversationDetail, SavedReport } from "./conversation.generated";

const ajv = new Ajv();
addFormats(ajv);
function validator<T>(name: string) {
  return ajv.compile<T>({ $defs: schema.$defs, $ref: `#/$defs/${name}` });
}
const conversation = validator<Conversation>("Conversation");
const detail = validator<ConversationDetail>("ConversationDetail");
const report = validator<SavedReport>("SavedReport");

async function request(url: string, options: RequestInit = {}): Promise<unknown> {
  let response: Response;
  try { response = await fetch(url, { ...options, headers: { "Content-Type": "application/json" } }); }
  catch (error) {
    if (options.signal?.aborted) throw error;
    throw new Error("無法連接服務，請確認服務已啟動。");
  }
  if (!response.ok) {
    let message = "操作失敗，請稍後再試。";
    try {
      const body = await response.json();
      if (typeof body.detail?.message === "string") message = body.detail.message;
    } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function checked<T>(value: unknown, validate: (value: unknown) => value is T): T {
  if (!validate(value)) throw new Error("服務回傳格式不正確，請重新嘗試。");
  return value;
}
export const conversations = {
  async list(): Promise<Conversation[]> {
    const rows = await request("/api/conversations");
    if (!Array.isArray(rows)) throw new Error("對話列表格式不正確。");
    return rows.map(row => checked(row, conversation));
  },
  async create(title: string, signal?: AbortSignal): Promise<Conversation> {
    return checked(await request("/api/conversations", { method: "POST", body: JSON.stringify({ title }), signal }), conversation);
  },
  async get(id: string): Promise<ConversationDetail> {
    return checked(await request(`/api/conversations/${encodeURIComponent(id)}`), detail);
  },
  async remove(id: string): Promise<void> {
    await request(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
  async reports(id: string): Promise<SavedReport[]> {
    const rows = await request(`/api/conversations/${encodeURIComponent(id)}/reports`);
    if (!Array.isArray(rows)) throw new Error("報告列表格式不正確。");
    return rows.map(row => checked(row, report));
  },
  async report(id: string): Promise<SavedReport> {
    return checked(await request(`/api/conversations/${encodeURIComponent(id)}/reports`, { method: "POST" }), report);
  },
};
