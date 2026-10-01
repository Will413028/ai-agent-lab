import Ajv from "ajv";
import schema from "../../../../contracts/images.schema.json";
import type { ImageSearchResult } from "./images.generated";

const ajv = new Ajv(); ajv.addSchema(schema, "images");
const validate = ajv.compile<ImageSearchResult>({ $ref: "images#/$defs/ImageSearchResult" });
export async function searchImages(query: string): Promise<ImageSearchResult> {
  let response: Response;
  try { response = await fetch("/api/mcp/images/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query }) }); }
  catch { throw new Error("無法連接圖片服務。"); }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail?.message === "string" ? data.detail.message : "圖片搜尋失敗。");
  if (!validate(data)) throw new Error("圖片回傳格式不正確。");
  return data;
}
