import sys

import pytest
from mcp import StdioServerParameters

from agent_lab_api.artifacts import ToolFailure
from agent_lab_api.image_mcp import ImageMCP
from agent_lab_api.image_provider import commons_images


@pytest.fixture(autouse=True)
async def verify_owned_subprocess_shutdown(monkeypatch):
    import mcp.client.stdio as stdio

    original = stdio._create_platform_compatible_process
    processes = []

    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", spawn)
    yield
    assert all(process.returncode is not None for process in processes)


async def test_real_stdio_discovery_invocation_and_shutdown():
    adapter = ImageMCP()
    definitions = await adapter.discover()
    assert [tool.name for tool in definitions] == ["searchImages"]
    assert definitions[0].parameters["properties"]["query"]["type"] == "string"
    result = await adapter.search("coffee")
    assert result.provider == "離線示範" and len(result.images) == 1
    assert result.images[0].artist and result.images[0].license_url.startswith("https://")


async def test_server_dependency_failure_is_not_empty_images():
    with pytest.raises(ToolFailure, match="dependency_failure"):
        await ImageMCP("error-fixture").search("coffee")


async def test_server_domain_timeout_survives_mcp_boundary():
    with pytest.raises(ToolFailure, match="tool_timeout"):
        await ImageMCP("typed-timeout-fixture").search("coffee")


async def test_server_timeout_is_typed_and_session_closes():
    adapter = ImageMCP("timeout-fixture", call_deadline=0.2)
    with pytest.raises(ToolFailure, match="tool_timeout"):
        await adapter.search("coffee")
    # A separate session still works after the hanging subprocess is shut down.
    result = await ImageMCP().search("coffee")
    assert len(result.images) == 1


async def test_server_stops_before_handshake_is_dependency_failure():
    parameters = StdioServerParameters(command=sys.executable, args=["-c", "pass"], env={})
    with pytest.raises(ToolFailure, match="dependency_failure"):
        await ImageMCP(parameters=parameters).search("coffee")


async def test_wrong_discovered_schema_rejected():
    from types import SimpleNamespace

    client = SimpleNamespace()

    async def wrong():
        tool = SimpleNamespace(
            name="searchImages",
            description="test",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "number"}},
                "required": ["query"],
            },
        )
        return SimpleNamespace(tools=[tool], next_cursor=None)

    client.list_tools = wrong
    with pytest.raises(ToolFailure, match="dependency_failure"):
        await ImageMCP().definitions(client)


async def test_empty_query_rejected_against_actual_server_schema():
    with pytest.raises(ToolFailure, match="invalid_arguments"):
        await ImageMCP().search("")


def test_commons_parses_attribution_and_filters_non_images():
    data = {
        "query": {
            "pages": {
                "1": {
                    "title": "File:coffee.jpg",
                    "index": 1,
                    "imageinfo": [
                        {
                            "mime": "image/jpeg",
                            "thumburl": "https://upload.wikimedia.org/example.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:coffee.jpg",
                            "extmetadata": {
                                "Artist": {"value": "<a>Photographer</a>"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "LicenseUrl": {
                                    "value": "https://creativecommons.org/licenses/by-sa/4.0/"
                                },
                            },
                        }
                    ],
                }
            }
        }
    }
    result = commons_images(data)
    assert result.images[0].artist == "Photographer"
    assert result.images[0].license == "CC BY-SA 4.0"
    data["query"]["pages"]["1"]["imageinfo"][0]["mime"] = "application/pdf"
    assert commons_images(data).images == []
    assert commons_images({"batchcomplete": ""}).images == []
    with pytest.raises(ToolFailure, match="dependency_failure"):
        commons_images({"error": {"code": "blocked"}})
