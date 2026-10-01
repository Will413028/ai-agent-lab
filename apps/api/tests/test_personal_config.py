import os

import pytest

from agent_lab_api.personal_config import load_personal_config


def test_invalid_config_does_not_change_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    path = tmp_path / "config"
    path.write_text("CLOUDFLARE_ACCOUNT_ID=invalid\nCLOUDFLARE_API_TOKEN=fixture\n")
    path.chmod(0o600)
    with pytest.raises(RuntimeError):
        load_personal_config(path)
    assert "CLOUDFLARE_ACCOUNT_ID" not in os.environ
    assert "CLOUDFLARE_API_TOKEN" not in os.environ


def test_config_rejects_symlink_and_shared_permissions(tmp_path):
    path = tmp_path / "config"
    path.write_text("not consumed")
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        load_personal_config(path)
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(RuntimeError):
        load_personal_config(link)


def test_model_outside_free_allowlist_is_rejected(monkeypatch):
    from agent_lab_api.cloudflare import CloudflareSettings

    with pytest.raises(RuntimeError, match="allowlist"):
        CloudflareSettings.from_environment(
            {
                "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
                "CLOUDFLARE_API_TOKEN": "fixture",
                "AGENT_LAB_CHAT_MODEL": "unapproved",
            }
        )
