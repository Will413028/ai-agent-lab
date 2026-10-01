"""Build a metadata-only source ledger; never read source or credential contents."""

import argparse
import json
import subprocess
from pathlib import Path

PIN = "6d4608c58b442d470fffc7a5e0b2aedb0e9478c8"


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def destination(path: str) -> tuple[str, str, str]:
    if path.endswith((".yml", ".yaml")) or path.endswith("mcp-servers.json") or path.endswith("TestApiKey.java"):
        return "replace-without-reading", "S1", "Only metadata inspected; define fresh server settings without copying credential payloads."
    if "demo/invoke/" in path or ".mvn/" in path or path.endswith(("mvnw", "mvnw.cmd", "pom.xml")):
        return "omit", "S7", "D1: Java/SDK/Ollama tutorial variants and Java tooling are outside functional parity."
    if "demo/rag/" in path:
        return "omit", "S7", "D1: standalone multi-query tutorial; retain query rewrite in R07, not each tutorial variant."
    if "RagCloudAdvisor" in path:
        return "replace", "S3", "D1: replace Alibaba cloud knowledge base with local RAG."
    if "/src/test/" in path:
        return "rewrite", "S7", "Rebuild behavioral coverage with deterministic tests; opt-in live eval remains separate."
    if path.startswith("yu-image-search-mcp-server/"):
        return "rewrite", "S5", "Python MCP server/client; deployment settings redefined, image provider remains D4."
    if path.startswith("yu-ai-agent-frontend/"):
        if path.endswith(("HelloWorld.vue", "vite.svg", "vue.svg", "package-lock.json", "vite.config.js")):
            return "omit", "S1", "Replace Vue/Vite starter artifacts with Next.js tooling and visuals."
        return "rewrite", "S1", "Next.js navigation, chat UI and fetch-based SSE; feature UI expands in S2-S6."
    if "/tools/" in path:
        return "rewrite", "S4", "Typed Python tools and bounded artifacts; terminal policy remains D3."
    if "/agent/" in path:
        return "rewrite", "S6", "D6a: composition-based run state and ReAct loop, not Java inheritance."
    if "/rag/" in path or "/resources/document/" in path:
        return "rewrite", "S3", "D2: PostgreSQL/pgvector; author new equivalent learning corpus instead of copying prose."
    if "/chatmemory/" in path or "/app/" in path:
        return "rewrite", "S2", "Database-backed conversations and typed reports; RAG/tools/MCP methods connect in S3-S5."
    if "/advisor/" in path:
        return "rewrite", "S7", "Redacted call summaries; re-reading is an opt-in experiment."
    if "/controller/" in path:
        return "rewrite", "S1", "FastAPI endpoints and explicit SSE event contract."
    return "replace", "S1", "Fresh Python/Next.js scaffolding, bootstrap and local settings; no Java deployment compatibility required."


def discover(root: Path) -> dict:
    revision = git(root, "rev-parse", "HEAD").decode().strip()
    if revision != PIN:
        raise ValueError("Source revision differs from the approved inventory pin")
    paths = git(root, "ls-files", "-z").decode().split("\0")[:-1]
    files = []
    for path in sorted(paths):
        action, phase, reason = destination(path)
        files.append({"path": path, "action": action, "phase": phase, "reason": reason})
    return {"repository": "https://github.com/liyupi/yu-ai-agent", "revision": revision,
            "command": "git -C <absolute-reference-checkout> ls-files -z",
            "contents_read": False, "files": files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = discover(args.source.resolve())
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"Mapped {len(data['files'])} tracked paths at {PIN}; no file contents read.")


if __name__ == "__main__":
    main()
