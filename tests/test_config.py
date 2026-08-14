"""Tests for configuration and default data functions."""

import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from smart_translator.app import (
    build_default_config,
    build_default_use_cases,
)


class TestBuildDefaultUseCases:
    """Test suite for build_default_use_cases function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        use_cases = build_default_use_cases()
        assert isinstance(use_cases, list)

    def test_has_expected_count(self):
        """Test that we have the expected number of default use cases."""
        use_cases = build_default_use_cases()
        # We expect at least 8 use cases
        assert len(use_cases) >= 8

    def test_use_case_structure(self):
        """Test that each use case has required fields."""
        use_cases = build_default_use_cases()
        required_fields = {"name", "emoji", "description"}

        for use_case in use_cases:
            assert isinstance(use_case, dict)
            # Check required fields exist
            for field in required_fields:
                assert field in use_case, f"Missing field '{field}' in use case {use_case.get('name')}"

    def test_token_saver_safe_exists(self):
        """Test that Token Saver (Safe) use case exists with correct structure."""
        use_cases = build_default_use_cases()
        token_saver_safe = next(
            (uc for uc in use_cases if uc["name"] == "Token Saver (Safe)"),
            None
        )
        assert token_saver_safe is not None
        assert token_saver_safe["processor"] == "deterministic"
        assert token_saver_safe["profile"] == "token_saver_safe"

    def test_all_use_cases_have_emoji(self):
        """Test that all use cases have an emoji."""
        use_cases = build_default_use_cases()
        for use_case in use_cases:
            assert "emoji" in use_case
            assert isinstance(use_case["emoji"], str)
            assert len(use_case["emoji"]) > 0

    def test_debug_helper_exists(self):
        """Test that Debug Helper use case exists."""
        use_cases = build_default_use_cases()
        debug_helper = next(
            (uc for uc in use_cases if uc["name"] == "Debug Helper"),
            None
        )
        assert debug_helper is not None
        assert "prompt" in debug_helper
        assert "{text}" in debug_helper["prompt"]


class TestBuildDefaultConfig:
    """Test suite for build_default_config function."""

    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        config = build_default_config()
        assert isinstance(config, dict)

    def test_has_required_keys(self):
        """Test that config has all required keys."""
        config = build_default_config()
        required_keys = {"ollama_url", "targets", "prompts", "use_cases"}

        for key in required_keys:
            assert key in config, f"Missing required key '{key}'"

    def test_ollama_url_default(self):
        """Test that default Ollama URL is correct."""
        config = build_default_config()
        assert config["ollama_url"] == "http://localhost:11434"

    def test_targets_structure(self):
        """Test that targets have correct structure."""
        config = build_default_config()
        targets = config["targets"]

        assert isinstance(targets, list)
        assert len(targets) >= 3  # At least Chinese, French, English

        for target in targets:
            assert "name" in target
            assert "emoji" in target

    def test_prompts_structure(self):
        """Test that prompts have correct structure."""
        config = build_default_config()
        prompts = config["prompts"]

        assert isinstance(prompts, dict)
        assert "correct" in prompts
        assert "translate" in prompts

        # Check prompts contain placeholder
        assert "{text}" in prompts["correct"]
        assert "{text}" in prompts["translate"]
        assert "{action}" in prompts["translate"]

    def test_use_cases_from_builder(self):
        """Test that use_cases come from build_default_use_cases."""
        config = build_default_config()
        use_cases = config["use_cases"]

        assert isinstance(use_cases, list)
        assert len(use_cases) > 0

        # Verify structure matches what build_default_use_cases returns
        first_use_case = use_cases[0]
        assert "name" in first_use_case
        assert "emoji" in first_use_case
        assert "description" in first_use_case
