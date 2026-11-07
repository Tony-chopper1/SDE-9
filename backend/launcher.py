
"""
SDK-9 AI Voice Co-Pilot - Backend Service Launcher
Deliverable #4: Validated startup configuration.
"""

import argparse
import os
import sys
from typing import Any, Optional

import uvicorn
from dotenv import load_dotenv


VALID_ENVIRONMENTS = {"development", "staging", "production","test"}
VALID_LOG_LEVELS = {
    "critical", "error", "warning", "info", "debug", "trace"
}


def parse_bool(value: str, name: str) -> bool:
    value = value.strip().lower()

    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False

    raise ValueError(f"{name} must be true or false")


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if config["environment"] not in VALID_ENVIRONMENTS:
        raise ValueError("Invalid ENVIRONMENT")

    if not isinstance(config["port"], int) or not 1 <= config["port"] <= 65535:
        raise ValueError("PORT must be between 1 and 65535")

    if not config["host"].strip():
        raise ValueError("HOST cannot be empty")

    if config["log_level"] not in VALID_LOG_LEVELS:
        raise ValueError("Invalid LOG_LEVEL")

    if not isinstance(config["mock_mode"], bool):
        raise ValueError("MOCK_MODE must be a boolean")

    if not isinstance(config["reload"], bool):
        raise ValueError("RELOAD must be a boolean")

    return config


def load_config() -> dict[str, Any]:
    load_dotenv()

    environment = os.getenv("ENVIRONMENT", "development").lower()
    is_dev = environment == "development"

    port_value = os.getenv("PORT", "8000")
    try:
        port = int(port_value)
    except ValueError as exc:
        raise ValueError("PORT must be a valid integer") from exc

    reload_value = os.getenv("RELOAD")
    reload_enabled = (
        parse_bool(reload_value, "RELOAD")
        if reload_value is not None
        else is_dev
    )

    config = {
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": port,
        "environment": environment,
        "reload": reload_enabled,
        "mock_mode": parse_bool(
            os.getenv("MOCK_MODE", "true"), "MOCK_MODE"
        ),
        "log_level": os.getenv("LOG_LEVEL", "info").lower(),
        "app_import": "backend.main:app",
    }

    return validate_config(config)


def parse_arguments(args: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SDK-9 Voicebot Backend Gateway Launcher"
    )
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", dest="reload", action="store_true", default=None)
    parser.add_argument("--no-reload", dest="reload", action="store_false")
    parser.add_argument("--env", dest="environment", type=str, default=None)
    parser.add_argument("--mock-mode", dest="mock_mode", action="store_true", default=None)
    parser.add_argument("--log-level", type=str, default=None)

    return parser.parse_args(args)


def get_launcher_config(args: Optional[list[str]] = None) -> dict[str, Any]:
    config = load_config()
    cli_args = parse_arguments(args)

    if cli_args.host is not None:
        config["host"] = cli_args.host
    if cli_args.port is not None:
        config["port"] = cli_args.port
    if cli_args.environment is not None:
        config["environment"] = cli_args.environment.lower()
    if cli_args.reload is not None:
        config["reload"] = cli_args.reload
    if cli_args.mock_mode is not None:
        config["mock_mode"] = cli_args.mock_mode
    if cli_args.log_level is not None:
        config["log_level"] = cli_args.log_level.lower()

    return validate_config(config)


def run_server(config: Optional[dict[str, Any]] = None) -> None:
    if config is None:
        config = get_launcher_config(sys.argv[1:])
    else:
        config = validate_config(config)

    print("=" * 60)
    print("  SDK-9 AI Voice Co-Pilot - Backend Gateway")
    print(f"  Environment  : {config['environment']}")
    print(f"  Mock Mode    : {config['mock_mode']}")
    print(f"  Host / Port  : {config['host']}:{config['port']}")
    print(f"  Auto Reload  : {config['reload']}")
    print(f"  API Docs     : http://{config['host']}:{config['port']}/docs")
    print("=" * 60)

    uvicorn.run(
        config["app_import"],
        host=config["host"],
        port=config["port"],
        reload=config["reload"],
        log_level=config["log_level"],
    )


if __name__ == "__main__":
    run_server()
