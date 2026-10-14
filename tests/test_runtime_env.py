from __future__ import annotations

import os

from evidex.runtime import Settings, load_env_file, make_provider

KEYS = ["EVIDEX_LLM_API_KEY", "EVIDEX_LLM_MODEL", "EVIDEX_LLM_BASE_URL", "EVIDEX_DEMO"]


def _clean(monkeypatch):
    # Work on a private copy so values loaded from .env never leak into other tests.
    monkeypatch.setattr(os, "environ", os.environ.copy())
    for key in [*KEYS, "EVIDEX_ENV_FILE", "EVIDEX_CROSSREF_MAILTO"]:
        monkeypatch.delenv(key, raising=False)


def test_env_file_configures_live_llm(tmp_path, monkeypatch):
    _clean(monkeypatch)
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "EVIDEX_LLM_API_KEY='sk-test'\n"
        'export EVIDEX_LLM_MODEL="my-model"  \n'
        "EVIDEX_LLM_BASE_URL=https://llm.example/v1  # inline comment\n"
        "not a valid line\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    assert settings.llm_key == "sk-test"
    assert settings.llm_model == "my-model"
    assert settings.llm_base_url == "https://llm.example/v1"
    assert not settings.demo
    provider = make_provider(settings)
    assert provider.name == "openai-compatible" and not provider.fixture_mode
    assert provider.llm.model == "my-model"
    assert provider.llm.base_url == "https://llm.example/v1"
    provider.close()


def test_real_environment_overrides_env_file(tmp_path, monkeypatch):
    _clean(monkeypatch)
    (tmp_path / ".env").write_text("EVIDEX_LLM_MODEL=from-file\nEVIDEX_LLM_API_KEY=k\n")
    monkeypatch.setenv("EVIDEX_LLM_MODEL", "from-shell")
    monkeypatch.chdir(tmp_path)
    assert Settings.from_env().llm_model == "from-shell"


def test_missing_env_file_is_fine_and_custom_path_works(tmp_path, monkeypatch):
    _clean(monkeypatch)
    monkeypatch.chdir(tmp_path)
    assert load_env_file() is None
    custom = tmp_path / "custom.env"
    custom.write_text("EVIDEX_LLM_API_KEY=abc\n")
    monkeypatch.setenv("EVIDEX_ENV_FILE", str(custom))
    assert load_env_file() == custom
    assert os.environ["EVIDEX_LLM_API_KEY"] == "abc"


def test_demo_flag_in_env_file_selects_fixtures(tmp_path, monkeypatch):
    _clean(monkeypatch)
    (tmp_path / ".env").write_text("EVIDEX_DEMO=1\nEVIDEX_LLM_API_KEY=k\n")
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    assert settings.demo
    assert make_provider(settings).fixture_mode
