import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "../../../../contracts/tools.schema.json";
import type { Artifact, ToolCall, ToolDefinition, ToolResult, Workspace } from "./tools.generated";

export type { Artifact, ToolCall, ToolDefinition, ToolResult };
const ajv = new Ajv(); addFormats(ajv); ajv.addSchema(schema, "tools");
const artifact = ajv.compile<Artifact>({ $ref: "tools#/$defs/Artifact" });
const result = ajv.compile<ToolResult>({ $ref: "tools#/$defs/ToolResult" });
const definition = ajv.compile<ToolDefinition>({ $ref: "tools#/$defs/ToolDefinition" });
const workspace = ajv.compile<Workspace>({ $ref: "tools#/$defs/Workspace" });

async function request(path: string, body?: unknown): Promise<unknown> {
  let response: Response;
  try { response = await fetch(path, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  catch { throw new Error("無法連接工具服務。"); }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail?.message === "string" ? data.detail.message : "工具操作失敗。");
  return data;
}
function checked<T>(value: unknown, validate: (value: unknown) => value is T): T {
  if (!validate(value)) throw new Error("工具回傳格式不正確。");
  return value;
}
function list<T>(value: unknown, validate: (value: unknown) => value is T): T[] {
  if (!Array.isArray(value)) throw new Error("工具列表格式不正確。");
  return value.map(item => checked(item, validate));
}
export const tools = {
  async definitions() { return list(await request("/api/tools"), definition); },
  async createWorkspace() { return checked(await request("/api/workspaces", {}), workspace); },
  async artifacts(id: string) { return list(await request(`/api/workspaces/${encodeURIComponent(id)}/artifacts`), artifact); },
  async invoke(workspaceId: string, calls: ToolCall[]) { return list(await request("/api/tools/invoke", { workspace_id: workspaceId, calls }), result); },
  download(artifact: Artifact) { return `/api/workspaces/${encodeURIComponent(artifact.workspace_id)}/artifacts/${encodeURIComponent(artifact.id)}`; },
};
