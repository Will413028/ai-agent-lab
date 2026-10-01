import asyncio
import io
import tarfile
from uuid import UUID, uuid4

from .artifacts import MAX_ARTIFACT_BYTES, ArtifactStore, ToolFailure, safe_name

TERMINAL_IMAGE = "python:3.14.7-slim-bookworm"
MAX_OUTPUT = 65536


async def docker_process(
    *args: str, input_data: bytes | None = None, deadline: int = 30, execution: bool = False
) -> tuple[bytes, int, bool]:
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT if execution else asyncio.subprocess.PIPE,
        )
    except OSError as failure:
        raise ToolFailure("dependency_failure", "Docker 執行環境無法使用。") from failure
    output, errors = bytearray(), bytearray()
    total = 0

    async def read(stream, target, *, command_output=False):
        nonlocal total
        while part := await stream.read(16384):
            if command_output:
                total += len(part)
                target.extend(part[: max(0, MAX_OUTPUT - len(target))])
                if total > MAX_ARTIFACT_BYTES:
                    raise ToolFailure("size_limit", "Terminal 輸出超過上限。")
            else:
                target.extend(part)
                if len(target) > MAX_ARTIFACT_BYTES:
                    raise ToolFailure("size_limit", "Docker 回傳超過大小上限。")

    async def communicate():
        readers = [read(process.stdout, output, command_output=execution)]
        if not execution:
            readers.append(read(process.stderr, errors))
        if input_data is not None:
            process.stdin.write(input_data)
            await process.stdin.drain()
            process.stdin.close()
        await asyncio.gather(*readers)
        await process.wait()

    try:
        async with asyncio.timeout(deadline):
            await communicate()
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    # Never forward Docker daemon diagnostics, which may include host paths.
    if process.returncode == 125 or (process.returncode and not execution):
        raise ToolFailure("dependency_failure", "容器操作失敗，請確認 Docker 可用。")
    return bytes(output), process.returncode, total > MAX_OUTPUT


async def docker(*args: str, **kwargs) -> bytes:
    output, _, _ = await docker_process(*args, **kwargs)
    return output


def input_archive(store: ArtifactStore, workspace_id: UUID) -> bytes:
    content = io.BytesIO()
    total = 0
    latest = {a.name: a for a in store.list(workspace_id)}
    with tarfile.open(fileobj=content, mode="w") as archive:
        for name, artifact in latest.items():
            safe_name(name)
            total += artifact.size
            if total > MAX_ARTIFACT_BYTES:
                raise ToolFailure("size_limit", "工作區輸入超過 8 MiB。")
            _, path = store.get(workspace_id, artifact.id)
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.uid, entry.gid = artifact.size, 0o644, 65534, 65534
            with path.open("rb") as stream:
                archive.addfile(entry, stream)
    return content.getvalue()


def output_archive(store: ArtifactStore, workspace_id: UUID, content: bytes):
    files = []
    total = 0
    with tarfile.open(fileobj=io.BytesIO(content), mode="r") as archive:
        for item in archive:
            if item.isdir() and item.name.rstrip("/") in ("workspace", "."):
                continue
            name = item.name.removeprefix("workspace/").removeprefix("./")
            safe_name(name)
            if not item.isfile() or item.size > MAX_ARTIFACT_BYTES or len(files) >= 32:
                raise ToolFailure("invalid_file", "容器產物僅接受最多 32 個一般檔案。")
            total += item.size
            if total > MAX_ARTIFACT_BYTES:
                raise ToolFailure("size_limit", "容器產物超過 8 MiB。")
            stream = archive.extractfile(item)
            files.append((name, stream.read(MAX_ARTIFACT_BYTES + 1)))
    # Validate everything before publishing; never extract a path onto the host.
    return [store.put(workspace_id, name, data, "application/octet-stream") for name, data in files]


class DockerTerminal:
    async def execute(self, command: str, workspace_id: UUID, store: ArtifactStore):
        name = "ai-agent-lab-tool-" + uuid4().hex
        created = False
        try:
            archive = input_archive(store, workspace_id)
            await docker(
                "create",
                "--name",
                name,
                "--label",
                "ai-agent-lab.owner=terminal",
                "--network",
                "none",
                "--read-only",
                "--user",
                "65534:65534",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--cpus",
                "0.5",
                "--memory",
                "128m",
                "--memory-swap",
                "128m",
                "--pids-limit",
                "64",
                "--ulimit",
                "fsize=8388608:8388608",
                "--tmpfs",
                "/workspace:rw,noexec,nosuid,size=16m,uid=65534,gid=65534",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--workdir",
                "/workspace",
                TERMINAL_IMAGE,
                "sleep",
                "infinity",
            )
            created = True
            await docker("start", name)
            await docker(
                "exec", "-i", name, "tar", "-xf", "-", "-C", "/workspace", input_data=archive
            )
            output, code, truncated = await docker_process(
                "exec",
                name,
                "/bin/sh",
                "-c",
                command,
                deadline=20,
                execution=True,
            )
            raw = await docker(
                "exec", name, "tar", "-cf", "-", "-C", "/workspace", ".", deadline=10
            )
            artifacts = output_archive(store, workspace_id, raw)
            if code:
                raise ToolFailure("terminal_failed", "Terminal command 回傳失敗；不會重試。")
            return {
                "output": output.decode("utf-8", errors="replace"),
                "exit_code": code,
                "truncated": truncated,
                "artifacts": [a.model_dump(mode="json") for a in artifacts],
            }
        except TimeoutError as failure:
            raise ToolFailure("tool_timeout", "Terminal 執行逾時。") from failure
        finally:

            async def remove_owned():
                try:
                    await docker("rm", "-f", name, deadline=15)
                except ToolFailure:
                    if created:
                        raise

            cleanup = asyncio.create_task(remove_owned())
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await asyncio.shield(cleanup)
                raise
