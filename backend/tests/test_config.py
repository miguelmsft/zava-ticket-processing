"""
Tests for application configuration (app.config).

Covers:
  • Default values
  • Property derivation (cors_origins_list, is_development)
  • Environment variable override
  • get_settings caching
"""

import os
from unittest.mock import patch

import pytest

from app.config import Settings, get_settings


class TestSettings:
    def test_defaults(self):
        import os
        from unittest.mock import patch as _patch
        # Temporarily clear env vars that conftest sets so we test true defaults
        clean_env = {k: v for k, v in os.environ.items() if k.upper() not in (
            "APP_ENV", "LOG_LEVEL", "COSMOS_ENDPOINT", "COSMOS_KEY",
            "COSMOS_DATABASE", "BLOB_CONNECTION_STRING",
            "CONTENT_UNDERSTANDING_ENDPOINT", "CONTENT_UNDERSTANDING_KEY",
            "AI_PROJECT_ENDPOINT", "STAGE_B_FUNCTION_URL", "STAGE_C_FUNCTION_URL",
            "CORS_ORIGINS",
        )}
        with _patch.dict(os.environ, clean_env, clear=True):
            s = Settings(
                _env_file=None,  # type: ignore  # don't read .env
            )
        assert s.app_env == "development"
        assert s.cosmos_database == "zava-ticket-processing"
        assert s.blob_container_name == "invoices"
        assert s.model_deployment_name == "gpt-4o"

    def test_cors_origins_list_single(self):
        s = Settings(cors_origins="http://localhost:3000", _env_file=None)  # type: ignore
        assert s.cors_origins_list == ["http://localhost:3000"]

    def test_cors_origins_list_multiple(self):
        s = Settings(cors_origins="http://a.com, http://b.com , http://c.com", _env_file=None)  # type: ignore
        assert len(s.cors_origins_list) == 3
        assert s.cors_origins_list[1] == "http://b.com"

    def test_cors_origins_list_empty(self):
        s = Settings(cors_origins="", _env_file=None)  # type: ignore
        assert s.cors_origins_list == []

    def test_is_development_true(self):
        s = Settings(app_env="development", _env_file=None)  # type: ignore
        assert s.is_development is True

    def test_is_development_false(self):
        s = Settings(app_env="production", _env_file=None)  # type: ignore
        assert s.is_development is False

    def test_cosmos_emulator_default(self):
        s = Settings(_env_file=None)  # type: ignore
        assert s.cosmos_use_emulator is False


class TestGetSettings:
    def test_returns_settings_instance(self, mock_settings):
        assert isinstance(mock_settings, Settings)

    def test_caching(self):
        """get_settings should return the same object on repeated calls."""
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        get_settings.cache_clear()

    def test_env_override(self):
        """Environment variables should override defaults."""
        get_settings.cache_clear()
        with patch.dict(os.environ, {"APP_ENV": "staging", "LOG_LEVEL": "DEBUG"}):
            get_settings.cache_clear()
            s = get_settings()
            assert s.app_env == "staging"
            assert s.log_level == "DEBUG"
        get_settings.cache_clear()
