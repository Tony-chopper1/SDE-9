"""
Interactive CLI Demonstration Tool for Context & Reasoning.

Provides a terminal interface to inspect active application context, render
versioned prompts, and run mock LLM reasoning decisions.

Usage:
    python -m packages.context_reasoning.cli
    python -m packages.context_reasoning.cli --simulate
"""
from __future__ import annotations

import argparse
import sys
import time

from packages.context_reasoning.context_manager import ContextManager
from packages.context_reasoning.prompt_manager import VersionedPromptManager
from packages.context_reasoning.mock_reasoning import MockReasoningService


def run_simulation() -> None:
    """Run an automated scenario walkthrough showcasing Context and Reasoning capabilities."""
    print("=" * 70)
    print("  SDK-9 AI Voice Co-Pilot: Context & Reasoning Demonstration")
    print("=" * 70)

    # 1. Initialize services
    session_id = "demo-session-001"
    cm = ContextManager(session_id=session_id, max_turns=10)
    pm = VersionedPromptManager(default_version="v1.0")
    reasoner = MockReasoningService()

    print(f"\n[1] Initialized ContextManager for session: '{session_id}'")
    print(f"    Available Prompt Versions: {pm.list_versions()}")

    # 2. Simulate Active Window Context
    print("\n[2] Updating Active OS Window to VS Code with an active snippet...")
    error_snippet = "def calculate_average(nums):\n    return sum(nums) / len(nums)  # ZeroDivisionError"
    cm.update_active_window(
        app_name="VS Code",
        window_title="math_utils.py - SDK-9",
        app_type="ide",
        visible_snippet=error_snippet,
    )
    print("    Active Window: VS Code | math_utils.py")
    print("    Visible Snippet:")
    for line in error_snippet.splitlines():
        print(f"      | {line}")

    # 3. Simulate Scenario A: Error Explanation
    query_a = "Why did I get a ZeroDivisionError here?"
    print(f"\n[3] Incoming User Voice Query: \"{query_a}\"")
    cm.add_turn("user", query_a)
    ctx_a = cm.update_user_query(query_a)

    print("\n    --> Running MockReasoningService:")
    result_a = reasoner.reason(ctx_a)
    print(f"    Intent:        {result_a.intent}")
    print(f"    Requires Tool: {result_a.requires_tool}")
    print(f"    Confidence:    {result_a.confidence * 100:.1f}%")
    print(f"    Response:      {result_a.direct_response}")
    print("    Reasoning Trace:")
    for step in result_a.reasoning_steps:
        print(f"      * {step}")
    cm.add_turn("assistant", result_a.direct_response or "")

    # 4. Simulate Scenario B: Tool Triggering (File Search)
    query_b = "Find all test files in the repository"
    print(f"\n[4] Incoming User Voice Query: \"{query_b}\"")
    cm.add_turn("user", query_b)
    ctx_b = cm.update_user_query(query_b)

    print("\n    --> Running MockReasoningService:")
    result_b = reasoner.reason(ctx_b)
    print(f"    Intent:        {result_b.intent}")
    print(f"    Requires Tool: {result_b.requires_tool}")
    print(f"    Planned Tool:  {result_b.planned_tool_name}")
    print(f"    Parameters:    {result_b.tool_parameters}")
    print(f"    Response:      {result_b.direct_response}")

    # 5. Render Versioned Prompt
    print("\n[5] Rendering Versioned Prompt Template ('v1.0'):")
    rendered = pm.render_prompt(
        version="v1.0",
        app_name=ctx_b.active_window.app_name,
        snippet=ctx_b.active_window.visible_snippet or "",
        query=ctx_b.user_query,
        history=cm.get_history_summary(),
    )
    print("-" * 50)
    print(rendered[:400] + "\n... [truncated for display] ...")
    print("-" * 50)

    print("\n[✔] Simulation complete. Context, history, and reasoning decisions verified.\n")


def run_interactive() -> None:
    """Run an interactive console REPL for testing arbitrary queries and window contexts."""
    session_id = f"interactive-{int(time.time())}"
    cm = ContextManager(session_id=session_id)
    pm = VersionedPromptManager()
    reasoner = MockReasoningService()

    print("=" * 60)
    print("  SDK-9 Context & Reasoning Interactive REPL")
    print("  Type 'quit' or 'exit' to stop.")
    print("  Type ':window <app_name>' to change active application.")
    print("=" * 60)

    while True:
        try:
            query = input("\n[User Query] > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit"):
            print("Session ended.")
            break

        if query.startswith(":window "):
            new_app = query.split(" ", 1)[1].strip()
            cm.update_active_window(app_name=new_app, window_title=f"{new_app} Window")
            print(f"[*] Updated active app to: {new_app}")
            continue

        cm.add_turn("user", query)
        ctx = cm.update_user_query(query)
        decision = reasoner.reason(ctx)

        print(f"\n[Reasoning Decision]")
        print(f"  Intent:        {decision.intent}")
        print(f"  Requires Tool: {decision.requires_tool}")
        if decision.requires_tool:
            print(f"  Tool Name:     {decision.planned_tool_name}")
            print(f"  Parameters:    {decision.tool_parameters}")
        print(f"  Confidence:    {decision.confidence * 100:.1f}%")
        print(f"  Response:      {decision.direct_response}")
        cm.add_turn("assistant", decision.direct_response or "")


def main() -> None:
    """Main CLI entrypoint parsing arguments."""
    parser = argparse.ArgumentParser(description="SDK-9 Context & Reasoning CLI Demo")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run non-interactive automated simulation walkthrough",
    )
    args = parser.parse_args()

    if args.simulate or not sys.stdin.isatty():
        run_simulation()
    else:
        run_interactive()


if __name__ == "__main__":
    main()
