import argparse
import asyncio

from mcp.server import MCPServer
from mcp_types import CallToolResult, TextContent

from .artifacts import ToolFailure
from .image_models import ImageSearchResult, ImageToolError
from .image_provider import CommonsImages, FixtureImages
from .tool_models import SearchQuery


def make_server(mode: str = "fixture") -> MCPServer:
    server = MCPServer("AI Agent Lab Images")
    provider = CommonsImages() if mode == "live" else FixtureImages()

    @server.tool()
    async def searchImages(
        query: SearchQuery,
    ) -> ImageSearchResult:
        """搜尋最多五张圖片，保留作者、來源與授權連結。"""
        if mode == "timeout-fixture":
            await asyncio.sleep(60)
        try:
            if mode in ("error-fixture", "typed-timeout-fixture"):
                raise ToolFailure(
                    "tool_timeout" if mode == "typed-timeout-fixture" else "dependency_failure",
                    "fixture",
                )
            return await provider.search(query)
        except ToolFailure as failure:
            error = ImageToolError(code=failure.code)
            return CallToolResult(
                is_error=True,
                structured_content=error.model_dump(),
                content=[TextContent(type="text", text=error.code)],
            )

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["fixture", "live", "timeout-fixture", "error-fixture", "typed-timeout-fixture"],
        default="fixture",
    )
    args = parser.parse_args()
    make_server(args.mode).run(transport="stdio")


if __name__ == "__main__":
    main()
