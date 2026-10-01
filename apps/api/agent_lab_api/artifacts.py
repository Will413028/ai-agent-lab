import re
from pathlib import Path
from uuid import UUID, uuid4

from .tool_models import Artifact

MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


class ToolFailure(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(code)


def safe_name(name: str) -> str:
    if (
        not name
        or len(name) > 120
        or name.startswith(".")
        or any(c in name for c in ("/", "\\", "\x00"))
        or any(ord(c) < 32 for c in name)
        or re.search(r"(?i)(^|[._-])(env|secret|credentials?|token|id_rsa)([._-]|$)", name)
    ):
        raise ToolFailure("invalid_path", "檔名不可包含路徑、隱藏檔或憑證名稱。")
    return name


class ArtifactStore:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parents[3] / "artifacts" / "workspaces"

    def directory(self, workspace_id: UUID, *, create: bool = False) -> Path:
        if self.root.is_symlink():
            raise ToolFailure("invalid_path", "工作目錄不可使用 symbolic link。")
        path = self.root / str(workspace_id)
        if path.is_symlink():
            raise ToolFailure("invalid_path", "工作目錄不可使用 symbolic link。")
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.is_dir():
            raise ToolFailure("workspace_missing", "找不到工作區。")
        return path

    def create(self) -> UUID:
        workspace_id = uuid4()
        self.directory(workspace_id, create=True)
        return workspace_id

    def put(self, workspace_id: UUID, name: str, content: bytes, media_type: str) -> Artifact:
        safe_name(name)
        if len(content) > MAX_ARTIFACT_BYTES:
            raise ToolFailure("size_limit", "產物超過 8 MiB 上限。")
        directory = self.directory(workspace_id)
        artifact = Artifact(
            id=uuid4(),
            workspace_id=workspace_id,
            name=name,
            media_type=media_type,
            size=len(content),
        )
        target = directory / str(artifact.id)
        # Exclusive creation never follows an existing symlink or overwrites another artifact.
        with target.open("xb") as stream:
            stream.write(content)
        metadata = directory / f"{artifact.id}.json"
        with metadata.open("x", encoding="utf-8") as stream:
            stream.write(artifact.model_dump_json())
        return artifact

    def get(self, workspace_id: UUID, artifact_id: UUID) -> tuple[Artifact, Path]:
        directory = self.directory(workspace_id)
        metadata = directory / f"{artifact_id}.json"
        target = directory / str(artifact_id)
        if metadata.is_symlink() or target.is_symlink():
            raise ToolFailure("invalid_path", "產物不可使用 symbolic link。")
        try:
            artifact = Artifact.model_validate_json(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError) as failure:
            raise ToolFailure("artifact_missing", "找不到產物。") from failure
        if (
            artifact.workspace_id != workspace_id
            or artifact.id != artifact_id
            or not target.is_file()
        ):
            raise ToolFailure("artifact_missing", "找不到產物。")
        return artifact, target

    def list(self, workspace_id: UUID) -> list[Artifact]:
        directory = self.directory(workspace_id)
        results = []
        for metadata in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime_ns):
            if metadata.is_symlink():
                raise ToolFailure("invalid_path", "產物不可使用 symbolic link。")
            try:
                identity = UUID(metadata.stem)
            except ValueError:
                continue
            artifact, _ = self.get(workspace_id, identity)
            results.append(artifact)
        return results

    def read_named(self, workspace_id: UUID, name: str) -> str:
        safe_name(name)
        matches = [a for a in self.list(workspace_id) if a.name == name]
        if not matches:
            raise ToolFailure("artifact_missing", "找不到工作區內的檔案。")
        _, path = self.get(workspace_id, matches[-1].id)
        if path.stat().st_size > 256 * 1024:
            raise ToolFailure("size_limit", "文字讀取超過 256 KiB 上限。")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as failure:
            raise ToolFailure("invalid_file", "檔案不是 UTF-8 文字。") from failure
