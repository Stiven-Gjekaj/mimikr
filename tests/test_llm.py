import json

import httpx
import pytest

from mimikr.llm import ChatClient, LLMError


def test_sends_an_openai_request_and_reads_the_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hey"}}]})

    client = ChatClient("http://model.test/v1/", "key", transport=httpx.MockTransport(handler))
    reply = client.complete([{"role": "user", "content": "hi"}], model="m", temperature=0.5)
    assert reply == "hey"
    assert seen["url"] == "http://model.test/v1/chat/completions"
    assert seen["auth"] == "Bearer key"
    assert seen["body"] == {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0.5}


def test_an_error_status_becomes_an_llm_error():
    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(
        lambda request: httpx.Response(404, text="model not found")))
    with pytest.raises(LLMError, match="404: model not found"):
        client.complete([], model="m", temperature=0.5)


def test_a_connection_fault_becomes_an_llm_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError, match="cannot reach"):
        client.complete([], model="m", temperature=0.5)
