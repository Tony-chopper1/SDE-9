"""
Unit Tests for Service Launcher
Deliverable #4: Tests for backend/launcher.py
"""

from unittest.mock import patch
from backend.launcher import (
    get_launcher_config,
    load_config,
    parse_arguments,
    run_server,
)


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("MOCK_MODE", raising=False)
    monkeypatch.delenv("RELOAD", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    config = load_config()
    assert config["host"] == "0.0.0.0"
    assert config["port"] == 8000
    assert config["environment"] == "development"
    assert config["reload"] is True
    assert config["mock_mode"] is True
    assert config["log_level"] == "info"
    assert config["app_import"] == "backend.main:app"


def test_load_config_custom_env(monkeypatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("RELOAD", "false")
    monkeypatch.setenv("LOG_LEVEL", "warning")

    config = load_config()
    assert config["host"] == "127.0.0.1"
    assert config["port"] == 9000
    assert config["environment"] == "production"
    assert config["reload"] is False
    assert config["mock_mode"] is False
    assert config["log_level"] == "warning"


def test_parse_arguments():
    args = parse_arguments(
        [
            "--host",
            "192.168.1.10",
            "--port",
            "8080",
            "--env",
            "staging",
            "--reload",
            "--mock-mode",
            "--log-level",
            "debug",
        ]
    )
    assert args.host == "192.168.1.10"
    assert args.port == 8080
    assert args.environment == "staging"
    assert args.reload is True
    assert args.mock_mode is True
    assert args.log_level == "debug"


def test_parse_arguments_no_reload():
    args = parse_arguments(["--no-reload"])
    assert args.reload is False


def test_get_launcher_config_with_cli_overrides():
    config = get_launcher_config(
        ["--host", "localhost", "--port", "5000", "--log-level", "error"]
    )
    assert config["host"] == "localhost"
    assert config["port"] == 5000
    assert config["log_level"] == "error"


@patch("uvicorn.run")
def test_run_server(mock_uvicorn_run):
    custom_config = {
        "host": "127.0.0.1",
        "port": 8888,
        "environment": "test",
        "reload": False,
        "mock_mode": True,
        "log_level": "info",
        "app_import": "backend.main:app",
    }
    run_server(custom_config)
    mock_uvicorn_run.assert_called_once_with(
        "backend.main:app",
        host="127.0.0.1",
        port=8888,
        reload=False,
        log_level="info",
    )
