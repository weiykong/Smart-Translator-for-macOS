"""Tests for the OllamaClient class."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from smart_translator.app import OllamaClient


class TestOllamaClient:
    """Test suite for OllamaClient."""

    def test_init(self):
        """Test client initialization."""
        client = OllamaClient("http://localhost:11434")
        assert client.base_url == "http://localhost:11434"
        assert client.session is not None

    def test_update_base_url_strips_trailing_slash(self):
        """Test that base URL trailing slashes are removed."""
        client = OllamaClient("http://localhost:11434/")
        assert client.base_url == "http://localhost:11434"

    def test_update_base_url(self):
        """Test updating base URL."""
        client = OllamaClient("http://localhost:11434")
        client.update_base_url("http://remote-server:11434/")
        assert client.base_url == "http://remote-server:11434"

    @patch('requests.Session')
    def test_check_connection_success(self, mock_session_class):
        """Test successful connection check."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")
        result = client.check_connection()

        assert result is True
        mock_session.get.assert_called_once_with(
            "http://localhost:11434/api/tags",
            timeout=(1.5, 3)
        )

    @patch('requests.Session')
    def test_check_connection_failure(self, mock_session_class):
        """Test failed connection check."""
        mock_session = Mock()
        mock_session.get.side_effect = Exception("Connection refused")
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")
        result = client.check_connection()

        assert result is False

    @patch('requests.Session')
    def test_fetch_models_success(self, mock_session_class):
        """Test successful model fetching."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2"},
                {"name": "mistral"},
                {"name": "gemma:7b"}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")
        models = client.fetch_models()

        assert models == ["llama3.2", "mistral", "gemma:7b"]
        mock_session.get.assert_called_once_with(
            "http://localhost:11434/api/tags",
            timeout=(2, 5)
        )

    @patch('requests.Session')
    def test_fetch_models_empty(self, mock_session_class):
        """Test fetching when no models available."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"models": []}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")
        models = client.fetch_models()

        assert models == []

    @patch('requests.Session')
    def test_fetch_models_failure(self, mock_session_class):
        """Test failed model fetching."""
        mock_session = Mock()
        mock_session.get.side_effect = Exception("API error")
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")
        models = client.fetch_models()

        assert models is None

    @patch('requests.Session')
    def test_generate_success(self, mock_session_class):
        """Test successful text generation."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"response": "Translated text here"}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")
        result = client.generate("llama3.2", "Translate this text")

        assert result == "Translated text here"
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://localhost:11434/api/generate"
        assert call_args[1]["json"]["model"] == "llama3.2"
        assert call_args[1]["json"]["prompt"] == "Translate this text"
        assert call_args[1]["json"]["stream"] is False

    @patch('requests.Session')
    def test_generate_empty_response(self, mock_session_class):
        """Test generation with empty response."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"response": ""}
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")
        result = client.generate("llama3.2", "Some prompt")

        assert result == ""

    @patch('requests.Session')
    def test_generate_failure(self, mock_session_class):
        """Test failed generation raises exception."""
        mock_session = Mock()
        mock_session.post.side_effect = Exception("Generation failed")
        mock_session_class.return_value = mock_session

        client = OllamaClient("http://localhost:11434")

        with pytest.raises(Exception):
            client.generate("llama3.2", "Some prompt")
