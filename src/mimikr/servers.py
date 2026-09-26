"""Check that the model servers in the settings answer. The settings page calls this."""

from collections.abc import Callable

from mimikr.config import Config, embedding_base_url
from mimikr.llm import ChatClient, LLMError


def check_servers(config: Config, client: Callable[[str, str], ChatClient] = ChatClient) -> list[tuple[bool, str]]:
    """Return one line for each server: whether it works, and what the check found."""
    lines: list[tuple[bool, str]] = []
    try:
        models = client(config.base_url, config.api_key).list_models()
        found = ", ".join(models[:5]) + (f", and {len(models) - 5} more" if len(models) > 5 else "")
        lines.append((True, f"Chat server: {len(models)} {'model' if len(models) == 1 else 'models'} ({found or 'none'})."))
        if models and config.model not in models:
            lines.append((False, f"The chat model {config.model!r} is not in the list of the server."))
    except LLMError as error:
        lines.append((False, f"Chat server: {error}."))
    try:
        [vector] = client(embedding_base_url(config), config.api_key).embed(["test"], config.embedding_model)
        lines.append((True, f"Embedding server: {len(vector)} dimensions from {config.embedding_model!r}."))
    except LLMError as error:
        lines.append((False, f"Embedding server: {error}."))
    return lines
