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

    def continue_text(self, prompt: str, model: str, temperature: float, stop: list[str],
                      max_tokens: int = 200) -> str:
        """Continue a text with the completions API. A base model uses this API."""
        payload = {"model": model, "prompt": prompt, "temperature": temperature,
                   "stop": stop, "max_tokens": max_tokens}
        try:
            response = self._client.post("completions", json=payload)
        except httpx.HTTPError as error:
            raise LLMError(f"cannot reach the model server at {self._client.base_url}: {error}") from error
        if response.status_code != 200:
            raise LLMError(f"the model server returned {response.status_code}: {response.text[:300]}")
        try:
            return response.json()["choices"][0]["text"] or ""
        except (ValueError, KeyError, IndexError) as error:
            raise LLMError(f"the model server returned an unknown answer: {response.text[:300]}") from error

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Return one embedding for each text, in the same order."""
        try:
            response = self._client.post("embeddings", json={"model": model, "input": texts})
        except httpx.HTTPError as error:
            raise LLMError(f"cannot reach the model server at {self._client.base_url}: {error}") from error
        if response.status_code != 200:
            raise LLMError(
                f"the model server returned {response.status_code} for the embedding model {model!r}:"
                f" {response.text[:300]}"
            )
        try:
            items = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in items]
        except (ValueError, KeyError, TypeError) as error:
            raise LLMError(f"the model server returned an unknown answer: {response.text[:300]}") from error
        if len(vectors) != len(texts):
            raise LLMError(f"the model server returned {len(vectors)} embeddings for {len(texts)} texts")
        return vectors

    def close(self) -> None:
        self._client.close()
