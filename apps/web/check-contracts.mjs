import { readFile } from "node:fs/promises";
import path from "node:path";
import { compileFromFile } from "json-schema-to-typescript";

const root = path.resolve(import.meta.dirname, "../..");
for (const name of ["chat-event", "conversation", "rag", "tools", "images", "runs"]) {
  const generated = await compileFromFile(path.join(root, `contracts/${name}.schema.json`));
  const current = await readFile(path.join(import.meta.dirname, `src/lib/${name}.generated.ts`), "utf8");
  if (generated !== current) throw new Error("API 型別已過期，請執行 make contracts。");
}
console.log("事件與 REST 型別符合 canonical schemas。");
