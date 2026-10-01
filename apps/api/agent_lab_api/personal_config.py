"""Consume an explicitly selected local credential file without shell evaluation or output."""

import os
import stat
from pathlib import Path

from .cloudflare import CloudflareSettings


def load_personal_config(path: Path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("個人設定尚未就緒。")
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("個人設定檔必須由目前使用者持有，且權限為600。")
    accepted = {"CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"}
    values = {}
    for line in path.read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name in accepted:
            if name in values or not value or value != value.strip():
                raise RuntimeError("個人設定格式不符合契約。")
            values[name] = value
    if set(values) != accepted:
        raise RuntimeError("個人設定尚未就緒。")
    CloudflareSettings.from_environment({**os.environ, **values})
    os.environ.update(values)
