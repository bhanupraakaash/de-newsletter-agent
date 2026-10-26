import pytest
from pydantic import ValidationError

from src.config import Settings, load_settings


def test_defaults_are_sensible():
    s = Settings()
    assert s.max_articles_to_claude == 20
    assert s.max_selected_articles == 10


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("MAX_ARTICLES_TO_CLAUDE", "12")
    assert load_settings().max_articles_to_claude == 12


def test_invalid_limit_is_rejected():
    with pytest.raises(ValidationError):
        Settings(max_articles_to_claude=0)
