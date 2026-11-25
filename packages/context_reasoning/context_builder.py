"""
Bounded Context Builder for AI Voice Co-Pilot.

Assembles multimodal context for reasoning with strict token-budget limits,
recency prioritization, keyword-relevance ranking, and time-based stale filtering.
Ensures prompt payloads stay bounded and focused on the active user query.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from packages.context_reasoning.models import (
    ContextBuilderConfig,
    ContextItem,
    ConversationContext,
    ConversationTurn,
    ReasoningRequest,
    ScreenContext,
    WindowContext,
)


def approximate_tokens(text: str) -> int:
    """
    Estimate token count for a text string using standard ~4 characters/token heuristic.

    Args:
        text: Input string.

    Returns:
        Estimated number of tokens (minimum 1 for non-empty text).
    """
    if not text:
        return 0
    # Standard heuristic: 1 token ≈ 4 characters of alphanumeric/code text
    return max(1, (len(text) + 3) // 4)


class ContextBuilder:
    """
    Builds bounded, prioritized reasoning contexts for the AI Co-Pilot.

    Features:
    - Token-budget approximation with strict upper-bound enforcement.
    - Stale filtering based on item age and screen frame TTL.
    - Combined relevance and recency scoring to rank competing context items.
    - Bounded sliding dialogue history selection prioritizing recent turns.
    - Telemetry tracking retained vs. dropped items and token allocation.
    """

    def __init__(self, config: Optional[ContextBuilderConfig] = None) -> None:
        """
        Initialize the context builder.

        Args:
            config: Optional ContextBuilderConfig specifying limits and thresholds.
        """
        self.config = config or ContextBuilderConfig()

    def filter_stale_items(
        self,
        items: List[ContextItem],
        now: Optional[float] = None,
    ) -> List[ContextItem]:
        """
        Filter out context items whose age exceeds stale_threshold_seconds.

        Args:
            items: List of candidate ContextItem instances.
            now: Current timestamp (defaults to time.time()).

        Returns:
            List of fresh ContextItems.
        """
        current_time = now if now is not None else time.time()
        fresh_items: List[ContextItem] = []

        for item in items:
            age = current_time - item.timestamp
            if age <= self.config.stale_threshold_seconds:
                fresh_items.append(item)

        return fresh_items

    def is_screen_stale(
        self,
        screen: Optional[ScreenContext],
        now: Optional[float] = None,
    ) -> bool:
        """
        Check if a screen frame is older than screen_stale_seconds TTL.

        Args:
            screen: ScreenContext instance or None.
            now: Current timestamp (defaults to time.time()).

        Returns:
            True if screen is None or age exceeds TTL, False otherwise.
        """
        if screen is None:
            return True
        current_time = now if now is not None else time.time()
        age = current_time - screen.timestamp
        return age > self.config.screen_stale_seconds

    def score_relevance(self, query: str, text: str) -> float:
        """
        Compute term-frequency overlap score between query and target content.

        Args:
            query: User's search query or question.
            text: Context candidate string.

        Returns:
            Relevance score between 0.0 (no overlap) and 1.0 (strong overlap).
        """
        if not query or not text:
            return 0.0

        # Extract words ignoring common stop words
        stopwords: Set[str] = {
            "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
            "is", "it", "this", "that", "what", "how", "why", "can", "you", "me"
        }
        query_terms = [
            w.lower() for w in re.findall(r"\w+", query)
            if len(w) > 1 and w.lower() not in stopwords
        ]

        if not query_terms:
            return 0.1  # baseline non-zero for empty/stopword-only query

        text_lower = text.lower()
        matched = 0
        for term in query_terms:
            if term in text_lower:
                matched += 1

        score = matched / len(query_terms)
        return min(1.0, max(0.0, score))

    def score_recency(self, timestamp: float, now: Optional[float] = None) -> float:
        """
        Compute recency score with exponential-like decay based on age.

        Args:
            timestamp: Item creation timestamp.
            now: Current timestamp.

        Returns:
            Recency score between 0.0 and 1.0.
        """
        current_time = now if now is not None else time.time()
        age_seconds = max(0.0, current_time - timestamp)
        # Half-life of decay ~ 60 seconds
        return 1.0 / (1.0 + (age_seconds / 60.0))

    def rank_and_select_items(
        self,
        query: str,
        items: List[ContextItem],
        token_allowance: int,
        now: Optional[float] = None,
    ) -> Tuple[List[ContextItem], int]:
        """
        Rank context items by combined (relevance * 0.7 + recency * 0.3) and fit into budget.

        Args:
            query: User query string.
            items: Candidate ContextItem instances.
            token_allowance: Maximum tokens allotted to context items.
            now: Current timestamp.

        Returns:
            Tuple of (selected_items, total_tokens_used).
        """
        current_time = now if now is not None else time.time()
        scored_items: List[Tuple[float, ContextItem]] = []

        for item in items:
            rel = self.score_relevance(query, item.content)
            rec = self.score_recency(item.timestamp, current_time)
            # Trusted items receive a slight priority bonus
            trust_bonus = 0.15 if item.is_trusted else 0.0
            combined_score = (rel * 0.65) + (rec * 0.35) + trust_bonus

            if combined_score >= self.config.relevance_threshold or item.is_trusted:
                scored_items.append((combined_score, item))

        # Sort descending by score
        scored_items.sort(key=lambda x: x[0], reverse=True)

        selected: List[ContextItem] = []
        tokens_used = 0

        for score, item in scored_items:
            item_tokens = approximate_tokens(item.content)
            if tokens_used + item_tokens <= token_allowance:
                selected.append(item)
                tokens_used += item_tokens
            else:
                # If budget full, skip
                continue

        return selected, tokens_used

    def select_history_turns(
        self,
        history: List[ConversationTurn],
        token_allowance: int,
    ) -> Tuple[List[ConversationTurn], int]:
        """
        Select most recent conversation turns that fit within token allowance.

        Args:
            history: Complete chronological turn history.
            token_allowance: Maximum tokens for dialogue history.

        Returns:
            Tuple of (selected_turns_in_chronological_order, tokens_used).
        """
        if not history:
            return [], 0

        # Traverse backwards from most recent turn
        selected_reversed: List[ConversationTurn] = []
        tokens_used = 0

        for turn in reversed(history[-self.config.max_history_turns:]):
            turn_tokens = approximate_tokens(f"{turn.role}: {turn.content}")
            if tokens_used + turn_tokens <= token_allowance:
                selected_reversed.append(turn)
                tokens_used += turn_tokens
            else:
                break

        # Restore chronological order
        selected = list(reversed(selected_reversed))
        return selected, tokens_used

    def build_context(
        self,
        raw_context: ConversationContext,
        query: Optional[str] = None,
        prompt_version: str = "v1.0",
        now: Optional[float] = None,
    ) -> ReasoningRequest:
        """
        Assemble a bounded, stale-filtered, budget-constrained ReasoningRequest.

        Args:
            raw_context: Complete source ConversationContext snapshot.
            query: Query override (defaults to raw_context.user_query).
            prompt_version: Version of prompt template to target.
            now: Current timestamp.

        Returns:
            Optimized, bounded ReasoningRequest within token_budget.
        """
        current_time = now if now is not None else time.time()
        effective_query = (query or raw_context.user_query or "").strip()
        total_budget = self.config.token_budget

        # 1. Budget Allocations:
        # - Query & Basic Metadata: ~15%
        # - Active Window & Screen Snippet: ~35%
        # - Dialogue History: ~25%
        # - Context Items & Knowledge: ~25%
        query_tokens = approximate_tokens(effective_query)
        remaining_budget = max(32, total_budget - query_tokens)

        # 2. Stale Screen Frame Filtering
        screen_frame = raw_context.screen_context
        screen_to_include: Optional[ScreenContext] = None

        if screen_frame and not self.is_screen_stale(screen_frame, current_time):
            screen_tokens = approximate_tokens(screen_frame.visible_text or "")
            screen_allowance = int(remaining_budget * 0.35)
            if screen_tokens <= screen_allowance:
                screen_to_include = screen_frame
                remaining_budget -= screen_tokens

        # 3. Active Window Budgeting
        active_window = raw_context.active_window
        window_snippet = active_window.visible_snippet or ""
        snippet_tokens = approximate_tokens(window_snippet)
        window_allowance = int(remaining_budget * 0.40)

        if snippet_tokens > window_allowance and window_snippet:
            # Truncate visible snippet to fit window allowance
            char_limit = window_allowance * 4
            truncated_snippet = window_snippet[:char_limit] + "\n... [truncated to fit token budget]"
            active_window = WindowContext(
                app_name=active_window.app_name,
                window_title=active_window.window_title,
                app_type=active_window.app_type,
                visible_snippet=truncated_snippet,
                url=active_window.url,
                metadata=active_window.metadata,
            )
            remaining_budget -= approximate_tokens(truncated_snippet)
        else:
            remaining_budget -= snippet_tokens

        # 4. History Selection (recency prioritized)
        history_allowance = int(remaining_budget * 0.50)
        selected_history, history_tokens = self.select_history_turns(
            raw_context.history, history_allowance
        )
        remaining_budget -= history_tokens

        # 5. Stale Context Items Filtering & Relevance Selection
        fresh_items = self.filter_stale_items(raw_context.context_items, current_time)
        selected_items, items_tokens = self.rank_and_select_items(
            effective_query, fresh_items, remaining_budget, current_time
        )
        remaining_budget -= items_tokens

        # 6. Assemble Pruned Bounded ConversationContext
        bounded_context = ConversationContext(
            session_id=raw_context.session_id,
            active_window=active_window,
            history=selected_history,
            user_query=effective_query,
            screen_context=screen_to_include,
            context_items=selected_items,
            timestamp=current_time,
            metadata={
                "builder": "BoundedContextBuilder_v2",
                "token_budget": total_budget,
                "approximate_tokens_used": total_budget - remaining_budget,
                "history_turns_retained": len(selected_history),
                "items_retained": len(selected_items),
                "items_dropped": len(raw_context.context_items) - len(selected_items),
            },
        )

        # 7. Construct Final ReasoningRequest
        return ReasoningRequest(
            session_id=raw_context.session_id,
            query=effective_query,
            context=bounded_context,
            context_items=selected_items,
            screen_context=screen_to_include,
            prompt_version=prompt_version,
            temperature=0.0,
            timestamp=current_time,
            metadata=bounded_context.metadata,
        )
