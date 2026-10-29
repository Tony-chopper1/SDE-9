from typing import Dict


class VersionedPromptManager:
    """
    Manages version-controlled prompt templates with placeholder replacement.
    """
    def __init__(self):
        self._prompts: Dict[str, str] = {
            "v1.0": (
                "You are AI Voice Co-Pilot. Active app: {app_name}. "
                "Visible screen content: {snippet}. User says: '{query}'."
            )
        }

    def render_prompt(self, version: str, app_name: str, snippet: str, query: str) -> str:
        template = self._prompts.get(version)
        if not template:
            raise ValueError(f"Prompt version {version} not registered.")
        return template.format(app_name=app_name, snippet=snippet, query=query)
