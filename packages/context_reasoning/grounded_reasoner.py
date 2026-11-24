# """Grounded Reasoner for Week 3.
# Implements evidence‑backed reasoning using Observation objects.
# Returns ReasoningResult with source_references and a fallback "no evidence" response.
# """

from __future__ import annotations

import time
from typing import List, Optional

from packages.context_reasoning.models import (
    Observation,
    ReasoningRequest,
    ReasoningResult,
    SourceReference,
)


class GroundedReasoner:
    """Simple rule‑based reasoner that searches observations for relevance.

    It looks for keyword overlap between the user query and Observation.content.
    If one or more observations match, it builds a response citing their sources.
    Otherwise it returns an intent ``NO_EVIDENCE`` with a polite fallback.
    """

    def __init__(self, min_match_ratio: float = 0.3) -> None:
        self.min_match_ratio = min_match_ratio

    def _relevance(self, query: str, obs: Observation) -> float:
        """Very naive relevance: fraction of query words present in observation content."""
        if not query or not obs.content:
            return 0.0
        query_terms = set(word.lower() for word in query.split())
        content_terms = set(word.lower() for word in obs.content.split())
        if not query_terms:
            return 0.0
        return len(query_terms & content_terms) / len(query_terms)

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        query = (request.query or "").strip()
        observations: List[Observation] = request.observations or []
        steps: List[str] = [f"GroundedReasoner received query: '{query}'"]

        if not query:
            steps.append("Empty query – returning idle response.")
            return ReasoningResult(
                intent="IDLE",
                requires_tool=False,
                direct_response="I'm listening. How can I help?",
                confidence=1.0,
                reasoning_steps=steps,
                source_references=[],
                metadata={},
            )

        # Compute relevance for each observation
        relevant: List[Observation] = []
        for obs in observations:
            rel = self._relevance(query, obs)
            if rel >= self.min_match_ratio:
                relevant.append(obs)
                steps.append(f"Observation {obs.observation_id} matched (rel={rel:.2f})")

        if not relevant:
            steps.append("No relevant observations found – returning NO_EVIDENCE.")
            return ReasoningResult(
                intent="NO_EVIDENCE",
                requires_tool=False,
                direct_response="I have no evidence to answer that.",
                confidence=0.9,
                reasoning_steps=steps,
                source_references=[],
                metadata={},
            )

        # Build a simple answer citing sources
        citations = []
        answer_parts = []
        for obs in relevant:
            src = obs.source
            citations.append(f"[{src.source_type.upper()}:{src.source_id}]")
            answer_parts.append(obs.content.strip())
        answer = " ".join(answer_parts)
        citation_str = " ".join(citations)
        full_response = f"{answer} {citation_str}".strip()

        steps.append("Constructed grounded answer with citations.")
        return ReasoningResult(
            intent="GROUND_TRUTH",
            requires_tool=False,
            direct_response=full_response,
            confidence=0.95,
            reasoning_steps=steps,
            source_references=[obs.source for obs in relevant],
            metadata={},
        )
