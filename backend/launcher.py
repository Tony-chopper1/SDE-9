"""
SDK-9 AI Voice Co-Pilot - Backend Service Launcher
Deliverable #4: Service launcher to orchestrate startup configurations.
Owner: Apeksha KT (feature/backend-fastapi - Task W5)
"""

import argparse
import os
import sys
from typing import Any, Dict, Optional

import uvicorn
from dotenv import load_dotenv


def load_config() -> Dict[str, Any]:
    """
    Load service configuration from environment variables and defaults.
    """
    load_dotenv()

    environment = os.getenv("ENVIRONMENT", "development").lower()
    is_dev = environment == "development"

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload_env = os.getenv("RELOAD")
    reload = (
        reload_env.lower() in ("true", "1", "yes")
        if reload_env is not None
        else is_dev
    )
    mock_mode = os.getenv("MOCK_MODE", "true").lower() in ("true", "1", "yes")
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    return {
        "host": host,
        "port": port,
        "environment": environment,
        "reload": reload,
        "mock_mode": mock_mode,
        "log_level": log_level,
        "app_import": "backend.main:app",
    }


def parse_arguments(args: Optional[list[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments for service startup.
    """
    parser = argparse.ArgumentParser(
        description="SDK-9 Voicebot Backend Gateway Launcher"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host address to bind to (e.g. 0.0.0.0, 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port number to listen on (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        dest="reload",
        action="store_true",
        default=None,
        help="Enable auto-reload on code changes",
    )
    parser.add_argument(
        "--no-reload",
        dest="reload",
        action="store_false",
        help="Disable auto-reload",
    )
    parser.add_argument(
        "--env",
        dest="environment",
        type=str,
        default=None,
        help="Target environment (development, staging, production)",
    )
    parser.add_argument(
        "--mock-mode",
        dest="mock_mode",
        action="store_true",
        default=None,
        help="Force mock mode enabled",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Logging level (critical, error, warning, info, debug, trace)",
    )

    return parser.parse_args(args)


def get_launcher_config(args: Optional[list[str]] = None) -> Dict[str, Any]:
    """
    Merge base configuration with command-line overrides.
    """
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

    return config


def run_server(config: Optional[Dict[str, Any]] = None) -> None:
    """
    Orchestrate configuration and launch the Uvicorn ASGI server.
    """
    if config is None:
        config = get_launcher_config(sys.argv[1:])

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
