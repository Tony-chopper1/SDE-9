import pytest
from packages.context_reasoning.grounded_reasoner import GroundedReasoner

def test_redaction_of_email():
    input_text = "Contact me at user@example.com for details."
    result = GroundedReasoner.process(input_text)
    # Ensure email addresses are redacted in the processed text
    assert "user@example.com" not in result.processed_text
    assert "<redacted>" in result.processed_text
