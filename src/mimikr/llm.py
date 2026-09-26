"""A client for an OpenAI-compatible chat API.

Ollama, LM Studio and the llama.cpp server all give this API.
The client blocks. The GUI calls it from a worker thread.
"""

import json
from collections.abc import Iterator

import httpx


class LLMError(RuntimeError):
    pass


# The largest text, in estimated tokens, that goes to an embedding model. A
# llama.cpp server refuses a text that is longer than its batch, which is 512
# tokens by default.
EMBED_TOKENS = 480


def clip_for_embedding(text: str, budget: int = EMBED_TOKENS) -> str:
    """Cut a text so that it fits the batch of an embedding server.

    The estimate is high on purpose: a character of plain ASCII costs a third of
    a token, and any other character, such as an emoji, costs three tokens.
    """
    used = 0.0
    for index, character in enumerate(text):
        used += 1 / 3 if ord(character) < 128 else 3
        if used > budget:
            return text[:index]
    return text


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

    def _stream(self, path: str, payload: dict, piece) -> Iterator[str]:
        """Send a request with stream on, and give each piece of text as it arrives.

        The server sends server-sent events: lines that start with "data: ",
        and "data: [DONE]" at the end.
        """
        try:
            with self._client.stream("POST", path, json={**payload, "stream": True}) as response:
                if response.status_code != 200:
                    response.read()
                    raise LLMError(f"the model server returned {response.status_code}: {response.text[:300]}")
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        text = piece(json.loads(data)["choices"][0])
                    except (ValueError, KeyError, IndexError, TypeError) as error:
                        raise LLMError(f"the model server sent an unknown event: {data[:300]}") from error
                    if text:
                        yield text
        except httpx.HTTPError as error:
            raise LLMError(f"cannot reach the model server at {self._client.base_url}: {error}") from error

    def stream_complete(self, messages: list[dict], model: str, temperature: float) -> Iterator[str]:
        payload = {"model": model, "messages": messages, "temperature": temperature}
        return self._stream("chat/completions", payload, lambda choice: (choice.get("delta") or {}).get("content"))

    def stream_continue(self, prompt: str, model: str, temperature: float, stop: list[str],
                        max_tokens: int = 200) -> Iterator[str]:
        payload = {"model": model, "prompt": prompt, "temperature": temperature, "stop": stop,
                   "max_tokens": max_tokens}
        return self._stream("completions", payload, lambda choice: choice.get("text"))

    def list_models(self) -> list[str]:
        """Return the names of the models that the server gives."""
        try:
            response = self._client.get("models", timeout=5.0)
        except httpx.HTTPError as error:
            raise LLMError(f"cannot reach the model server at {self._client.base_url}: {error}") from error
        if response.status_code != 200:
            raise LLMError(f"the model server returned {response.status_code}: {response.text[:300]}")
        try:
            return [str(item["id"]) for item in response.json()["data"]]
        except (ValueError, KeyError, TypeError) as error:
            raise LLMError(f"the model server returned an unknown answer: {response.text[:300]}") from error

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Return one embedding for each text, in the same order."""
        try:
            response = self._client.post(
                "embeddings", json={"model": model, "input": [clip_for_embedding(text) for text in texts]})
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
