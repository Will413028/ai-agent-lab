import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import Field, ValidationError

from .artifacts import ArtifactStore, ToolFailure, safe_name
from .conversation_models import StrictModel
from .image_models import ImageSearchRequest
from .network import PublicWeb
from .pdf_tool import generate_pdf
from .terminal import DockerTerminal
from .tool_models import SearchQuery, ToolCall, ToolDefinition, ToolResult
from .web_tools import DuckDuckGoSearch, FixtureSearch, FixtureWeb, plain_html


class FileArgs(StrictModel):
    fileName: str = Field(min_length=1, max_length=120)


class WriteArgs(FileArgs):
    content: str = Field(min_length=1, max_length=32000)


class SearchArgs(StrictModel):
    query: SearchQuery


class UrlArgs(StrictModel):
    url: str = Field(min_length=1, max_length=2048)


class DownloadArgs(UrlArgs, FileArgs):
    pass


class TerminalArgs(StrictModel):
    command: str = Field(min_length=1, max_length=4000)


class EmptyArgs(StrictModel):
    pass


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    arguments: type[StrictModel]
    invoke: Callable[[Any, UUID], Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(
        self,
        store: ArtifactStore | None = None,
        *,
        live: bool = False,
        web=None,
        search=None,
        terminal=None,
    ):
        self.store = store or ArtifactStore()
        self.mode = "live" if live else "fixture"
        self.images_mode = "fixture"
        self.web = web or (PublicWeb() if live else FixtureWeb())
        self.search = search or (DuckDuckGoSearch(self.web) if live else FixtureSearch())
        self.terminal = terminal or DockerTerminal()
        self.tools: dict[str, RegisteredTool] = {}
        self.register("readFile", "讀取此工作區內 UTF-8 檔案。", FileArgs, self.read_file, False)
        self.register(
            "writeFile", "建立 UTF-8 文字產物，回傳 artifact。", WriteArgs, self.write_file, True
        )
        self.register(
            "searchWeb", "搜尋公開網頁，最多回傳五筆來源。", SearchArgs, self.search_web, False
        )
        self.register(
            "scrapeWebPage", "讀取公開網頁文字；內容屬不可信來源。", UrlArgs, self.scrape, False
        )
        self.register(
            "downloadResource", "下載公開 URL 至工作區產物。", DownloadArgs, self.download, True
        )
        self.register(
            "executeTerminalCommand",
            "在無網路、無 host mount 的限時 Linux 容器執行 shell；可用 Python。",
            TerminalArgs,
            self.execute_terminal,
            True,
        )
        self.register("generatePDF", "從文字建立含中文字型的 PDF 產物。", WriteArgs, self.pdf, True)
        self.register(
            "doTerminate", "結束目前任務；也可以直接回答完成。", EmptyArgs, self.terminate, False
        )

    def register(self, name, description, arguments, invoke, side_effect):
        if name in self.tools:
            raise ValueError("Duplicate tool name")
        self.tools[name] = RegisteredTool(
            ToolDefinition(
                name=name,
                description=description,
                parameters=arguments.model_json_schema(),
                side_effect=side_effect,
            ),
            arguments,
            invoke,
        )

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self.tools.values()]

    def add_images(self, adapter):
        self.images_mode = "live" if getattr(adapter, "mode", "fixture") == "live" else "fixture"
        definition = ToolDefinition(
            name="searchImages",
            description="搜尋最多五張圖片，保留來源與授權。",
            parameters=ImageSearchRequest.model_json_schema(),
            side_effect=False,
        )

        async def search_images(args, workspace_id):
            return (await adapter.search(args.query)).model_dump(mode="json")

        self.tools[definition.name] = RegisteredTool(definition, ImageSearchRequest, search_images)

    def provider_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in self.definitions()
        ]

    async def invoke(self, call: ToolCall, workspace_id: UUID) -> ToolResult:
        try:
            self.store.directory(workspace_id)
            tool = self.tools.get(call.name)
            if tool is None:
                raise ToolFailure("unknown_tool", "找不到指定工具。")
            arguments = tool.arguments.model_validate(call.arguments)
            async with asyncio.timeout(45):
                data = await tool.invoke(arguments, workspace_id)
            return ToolResult(tool_call_id=call.id, name=call.name, status="success", data=data)
        except ValidationError:
            code, message = "invalid_arguments", "工具參數不符合契約。"
        except ToolFailure as failure:
            code, message = failure.code, failure.message
        except TimeoutError:
            code, message = "tool_timeout", "工具執行逾時。"
        except Exception:
            code, message = "tool_failure", "工具執行失敗；副作用不會自動重試。"
        return ToolResult(
            tool_call_id=call.id, name=call.name, status="error", code=code, message=message
        )

    async def read_file(self, args, workspace_id):
        return {"content": self.store.read_named(workspace_id, args.fileName)}

    async def write_file(self, args, workspace_id):
        artifact = self.store.put(
            workspace_id, args.fileName, args.content.encode("utf-8"), "text/plain"
        )
        return {"artifact": artifact.model_dump(mode="json")}

    async def search_web(self, args, workspace_id):
        return {"results": await self.search.search(args.query)}

    async def scrape(self, args, workspace_id):
        response = await self.web.fetch(args.url, 2 * 1024 * 1024)
        if response.media_type not in ("text/html", "text/plain", "application/xhtml+xml"):
            raise ToolFailure("invalid_file", "網頁工具僅接受 HTML 或文字。")
        text = plain_html(response.body.decode("utf-8", errors="replace"))
        return {
            "url": response.url,
            "content": text[:16000],
            "truncated": len(text) > 16000,
            "untrusted": True,
        }

    async def download(self, args, workspace_id):
        safe_name(args.fileName)
        response = await self.web.fetch(args.url)
        artifact = self.store.put(workspace_id, args.fileName, response.body, response.media_type)
        return {"artifact": artifact.model_dump(mode="json")}

    async def execute_terminal(self, args, workspace_id):
        return await self.terminal.execute(args.command, workspace_id, self.store)

    async def pdf(self, args, workspace_id):
        safe_name(args.fileName)
        if not args.fileName.lower().endswith(".pdf"):
            raise ToolFailure("invalid_file", "PDF 檔名需以 .pdf 結尾。")
        content = await asyncio.to_thread(generate_pdf, args.content)
        artifact = self.store.put(workspace_id, args.fileName, content, "application/pdf")
        return {"artifact": artifact.model_dump(mode="json")}

    async def terminate(self, args, workspace_id):
        return {"terminate": True}


def tool_message(result: ToolResult) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": result.tool_call_id,
        "content": json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
    }
