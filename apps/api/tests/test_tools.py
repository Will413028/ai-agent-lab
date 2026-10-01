import io
import json
import socket
import tarfile

import pytest
from pypdf import PdfReader

from agent_lab_api.artifacts import ArtifactStore, ToolFailure
from agent_lab_api.network import PinnedResolver, public_addresses, public_ip
from agent_lab_api.terminal import output_archive
from agent_lab_api.tool_models import ToolCall
from agent_lab_api.tools import ToolRegistry, tool_message
from agent_lab_api.web_tools import parse_search


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(ArtifactStore(tmp_path / "workspaces"))


async def invoke(registry, workspace, name, arguments, call_id="call-1"):
    return await registry.invoke(ToolCall(id=call_id, name=name, arguments=arguments), workspace)


async def test_write_read_download_and_call_identity(registry):
    workspace = registry.store.create()
    written = await invoke(
        registry, workspace, "writeFile", {"fileName": "筆記.md", "content": "中文學習"}
    )
    assert written.status == "success" and written.tool_call_id == "call-1"
    read = await invoke(registry, workspace, "readFile", {"fileName": "筆記.md"}, "call-2")
    assert read.data == {"content": "中文學習"}
    assert tool_message(read)["tool_call_id"] == "call-2"
    assert json.loads(tool_message(read)["content"])["status"] == "success"
    other = registry.store.create()
    missing = await invoke(registry, other, "readFile", {"fileName": "筆記.md"})
    assert missing.status == "error" and missing.code == "artifact_missing"


@pytest.mark.parametrize("name", ["../x", "/tmp/x", "a\\b", ".env", "credentials.json", "x\x00y"])
async def test_rejects_traversal_and_secret_names(registry, name):
    result = await invoke(
        registry, registry.store.create(), "writeFile", {"fileName": name, "content": "x"}
    )
    assert result.status == "error" and result.code == "invalid_path"
    assert not registry.store.list(next(registry.store.root.iterdir()).name)


async def test_schema_and_unknown_tool_failures_are_explicit(registry):
    workspace = registry.store.create()
    for name, args, code in [
        ("unknown", {}, "unknown_tool"),
        ("writeFile", {"fileName": "x", "content": "x", "extra": 1}, "invalid_arguments"),
    ]:
        result = await invoke(registry, workspace, name, args)
        assert result.status == "error" and result.code == code
    assert len(registry.definitions()) == 8
    assert len({d.name for d in registry.definitions()}) == 8


async def test_side_effect_error_is_not_retried(registry):
    calls = []

    async def failing(args, workspace):
        calls.append(workspace)
        registry.store.put(workspace, "partial.txt", b"already happened", "text/plain")
        raise ToolFailure("tool_failure", "副作用後失敗")

    from agent_lab_api.tools import WriteArgs

    registry.register("partial", "test", WriteArgs, failing, True)
    result = await invoke(
        registry, registry.store.create(), "partial", {"fileName": "x", "content": "x"}
    )
    assert result.status == "error" and len(calls) == 1
    assert len(registry.store.list(calls[0])) == 1


async def test_pdf_contains_extractable_chinese_and_no_markup(registry):
    result = await invoke(
        registry,
        registry.store.create(),
        "generatePDF",
        {
            "fileName": "學習.pdf",
            "content": "# 中文學習\n工具呼叫保留 ID。\n<script>不能執行</script>",
        },
    )
    assert result.status == "success"
    from agent_lab_api.tool_models import Artifact

    artifact = Artifact.model_validate(result.data["artifact"])
    _, path = registry.store.get(artifact.workspace_id, artifact.id)
    reader = PdfReader(path)
    assert len(reader.pages) >= 1
    text = "".join(page.extract_text() for page in reader.pages)
    assert "中文學習" in text and "工具呼叫保留 ID" in text and "<script>" in text
    fonts = reader.pages[0]["/Resources"]["/Font"]
    assert any(
        "/FontFile2" in font.get_object().get("/FontDescriptor", {}) for font in fonts.values()
    )


async def test_fixture_search_scrape_and_download(registry):
    workspace = registry.store.create()
    search = await invoke(registry, workspace, "searchWeb", {"query": "agent"})
    assert 0 < len(search.data["results"]) <= 5
    scrape = await invoke(
        registry, workspace, "scrapeWebPage", {"url": "https://example.com/learning"}
    )
    assert scrape.data["untrusted"] is True and "Understand tool calls" in scrape.data["content"]
    download = await invoke(
        registry,
        workspace,
        "downloadResource",
        {"url": "https://example.com/learning", "fileName": "page.html"},
    )
    assert download.status == "success" and download.data["artifact"]["size"] > 0


def test_artifact_symlinks_and_isolation(tmp_path):
    store = ArtifactStore(tmp_path / "workspaces")
    workspace = store.create()
    artifact = store.put(workspace, "x.txt", b"safe", "text/plain")
    _, path = store.get(workspace, artifact.id)
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(ToolFailure, match="invalid_path"):
        store.get(workspace, artifact.id)
    other = store.create()
    with pytest.raises(ToolFailure, match="artifact_missing"):
        store.get(other, artifact.id)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::",
    ],
)
def test_private_and_translation_addresses_blocked(address):
    assert not public_ip(address)


async def test_dns_mixed_private_blocks_before_connection(monkeypatch):
    import asyncio

    async def addresses(*args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443))
            for ip in ["1.1.1.1", "127.0.0.1"]
        ]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    with pytest.raises(ToolFailure, match="network_blocked"):
        await public_addresses("https://example.com")


async def test_connection_resolver_is_pinned_and_rejects_other_host():
    resolver = PinnedResolver("example.com", ["1.1.1.1"])
    resolved = await resolver.resolve("example.com", 443)
    assert resolved[0]["host"] == "1.1.1.1"
    with pytest.raises(ToolFailure, match="network_blocked"):
        await resolver.resolve("localhost", 443)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/a",
        "http://user:pass@example.com",
        "http://example.com:8080",
        "https://example.com\\@localhost",
    ],
)
async def test_url_guard_rejects_unsupported_urls(url):
    with pytest.raises(ToolFailure, match="invalid_url"):
        await public_addresses(url)


def test_search_challenge_is_not_empty_and_small_results_are_valid():
    with pytest.raises(ToolFailure, match="dependency_failure"):
        parse_search('<form id="challenge-form"></form>')
    assert parse_search('<div class="no-results"></div>') == []
    result = parse_search('<a class="result__a" href="https://example.com">Example</a>')
    assert len(result) == 1 and result[0]["url"] == "https://example.com"


@pytest.mark.parametrize("name,kind", [("../escape", "file"), ("workspace/x", "symlink")])
def test_container_archive_never_extracts_unsafe_files(tmp_path, name, kind):
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w") as archive:
        item = tarfile.TarInfo(name)
        if kind == "symlink":
            item.type = tarfile.SYMTYPE
            item.linkname = "/etc/passwd"
        archive.addfile(item)
    store = ArtifactStore(tmp_path / "workspaces")
    workspace = store.create()
    with pytest.raises(ToolFailure):
        output_archive(store, workspace, content.getvalue())
    assert store.list(workspace) == []
