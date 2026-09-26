"""A client for an OpenAI-compatible chat API.

Ollama, LM Studio and the llama.cpp server all give this API.
The client blocks. The GUI calls it from a worker thread.
"""

import httpx


class LLMError(RuntimeError):
    pass


class ChatClient:
    def __init__(self, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(300.0, connect=5.0),
            transport=transport,
        )

    def complete(self, messages: list[dict], model: str, temperature: float) -> str:
        try:
            response = self._client.post(
                "chat/completions",
                json={"model": model, "messages": messages, "temperature": temperature},
            )
        except httpx.HTTPError as error:
            raise LLMError(f"cannot reach the model server at {self._client.base_url}: {error}") from error
        if response.status_code != 200:
            raise LLMError(f"the model server returned {response.status_code}: {response.text[:300]}")
        try:
            return response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError) as error:
            raise LLMError(f"the model server returned an unknown answer: {response.text[:300]}") from error

    def close(self) -> None:
        self._client.close()
