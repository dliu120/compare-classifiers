"""load_settings is the one function that handles credentials; these tests keep it honest
offline: environment first, then the env file, then the use-jev key file for Jev only."""

from __future__ import annotations

from pathlib import Path

import pytest

from bakeoff import config
from bakeoff.config import Settings, load_settings

ENV_VARS = [
    "TYPESAFE_API_KEY",
    "OPENAI_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_AUTH_TOKEN",
    "LIQUID_API_KEY",
    "FOUNDRY_ENDPOINT",
    "FOUNDRY_ACCESS_TOKEN",
    "FOUNDRY_DEPLOYMENT_NAME",
    "FOUNDRY_REQUESTS_PER_MINUTE",
    "AIPROXY_BASE_URL",
    "OPENAI_BASE_URL_DIRECT",
    "BAKEOFF_BUDGET_USD",
    "BAKEOFF_DATA_DIR",
    "BAKEOFF_RUNS_DIR",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "USE_JEV_KEY_FILE", tmp_path / "no-such-key-file")


def test_defaults_without_any_source() -> None:
    settings = load_settings(env_file=None)
    assert settings == Settings()
    assert settings.typesafe_api_key is None and settings.openai_api_key is None
    assert settings.aiproxy_base_url == "http://127.0.0.1:17688/v1"
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.budget_usd == 50.0
    assert settings.has("ownbuild") and not settings.has("jev") and not settings.has("nothing")


def test_environment_values_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-env")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-env")
    monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "cf-env")
    monkeypatch.setenv("LIQUID_API_KEY", "liquid-env")
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "https://resource.services.ai.azure.com/")
    monkeypatch.setenv("FOUNDRY_ACCESS_TOKEN", "foundry-env")
    monkeypatch.setenv("FOUNDRY_DEPLOYMENT_NAME", "decision-test")
    monkeypatch.setenv("FOUNDRY_REQUESTS_PER_MINUTE", "15")
    monkeypatch.setenv("AIPROXY_BASE_URL", "http://proxy:1/v1/")
    monkeypatch.setenv("OPENAI_BASE_URL_DIRECT", "https://direct.test/v1/")
    monkeypatch.setenv("BAKEOFF_BUDGET_USD", "2.5")
    monkeypatch.setenv("BAKEOFF_DATA_DIR", "/tmp/d")
    monkeypatch.setenv("BAKEOFF_RUNS_DIR", "/tmp/r")
    settings = load_settings(env_file=None)
    assert settings.typesafe_api_key == "ts-env" and settings.openai_api_key == "sk-env"
    assert settings.liquid_api_key == "liquid-env"
    assert settings.cloudflare_account_id == "acct-env"
    assert settings.cloudflare_auth_token == "cf-env"
    assert settings.aiproxy_base_url == "http://proxy:1/v1"  # trailing slash dropped
    assert settings.openai_base_url == "https://direct.test/v1"
    assert settings.budget_usd == 2.5
    assert (settings.data_dir, settings.runs_dir) == (Path("/tmp/d"), Path("/tmp/r"))
    assert all(settings.has(family) for family in ("jev", "cloudflare", "liquid"))
    assert settings.has("openai-decisions")
    assert settings.foundry_endpoint == "https://resource.services.ai.azure.com"
    assert settings.foundry_access_token == "foundry-env"
    assert settings.foundry_deployment_name == "decision-test"
    assert settings.foundry_requests_per_minute == 15
    assert settings.has("foundry")


def test_empty_strings_mean_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_AUTH_TOKEN", "")
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "")
    monkeypatch.setenv("FOUNDRY_ACCESS_TOKEN", "")
    settings = load_settings(env_file=None)
    assert settings.openai_api_key is None
    assert settings.cloudflare_auth_token is None and not settings.has("cloudflare")
    assert not settings.has("openai-decisions")
    assert settings.foundry_endpoint is None and settings.foundry_access_token is None
    assert not settings.has("foundry")


def test_env_file_fills_gaps_but_never_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-file\nLIQUID_API_KEY=liquid-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    settings = load_settings(env_file=env_file)
    assert settings.openai_api_key == "sk-env"  # the environment wins
    assert settings.liquid_api_key == "liquid-file"


def test_jev_key_falls_back_to_the_use_jev_file_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "api-key"
    key_file.write_text("  ts-from-file\n", encoding="utf-8")
    monkeypatch.setattr(config, "USE_JEV_KEY_FILE", key_file)
    settings = load_settings(env_file=None)
    assert settings.typesafe_api_key == "ts-from-file"
    assert settings.openai_api_key is None  # no other credential has a file fallback

    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-env")
    assert load_settings(env_file=None).typesafe_api_key == "ts-env"

    key_file.write_text("   \n", encoding="utf-8")
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert load_settings(env_file=None).typesafe_api_key is None  # a blank file is no key
    assert config._read_use_jev_key() is None
