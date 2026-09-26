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


def test_embed_sends_the_texts_and_keeps_their_order():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        # A server can return the items in any order. The index says which text each one is.
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ]})

    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(handler))
    assert client.embed(["a", "b"], model="e") == [[1.0, 0.0], [0.0, 1.0]]
    assert seen["url"] == "http://model.test/v1/embeddings"
    assert seen["body"] == {"model": "e", "input": ["a", "b"]}


def test_embed_names_the_model_when_the_server_refuses_it():
    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(
        lambda request: httpx.Response(404, text="model not found")))
    with pytest.raises(LLMError, match="embedding model 'e'"):
        client.embed(["a"], model="e")


def test_embed_refuses_a_wrong_number_of_embeddings():
    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})))
    with pytest.raises(LLMError, match="1 embeddings for 2 texts"):
        client.embed(["a", "b"], model="e")


def test_continue_text_sends_the_prompt_and_the_stop_sequences():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"text": " lol ok"}]})

    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(handler))
    assert client.continue_text("June: hi\nSam:", model="base", temperature=0.9, stop=["\nJune:"]) == " lol ok"
    assert seen["url"] == "http://model.test/v1/completions"
    assert seen["body"] == {"model": "base", "prompt": "June: hi\nSam:", "temperature": 0.9,
                            "stop": ["\nJune:"], "max_tokens": 200}


def test_continue_text_reports_an_error_status():
    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(
        lambda request: httpx.Response(500, text="boom")))
    with pytest.raises(LLMError, match="500: boom"):
        client.continue_text("x", model="m", temperature=0.5, stop=[])


def sse(*events: str) -> bytes:
    return "".join(f"data: {event}\n\n" for event in events).encode()


def test_stream_complete_gives_each_piece_of_the_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse(
            '{"choices":[{"delta":{"role":"assistant"}}]}',
            '{"choices":[{"delta":{"content":"lol "}}]}',
            '{"choices":[{"delta":{"content":"ok"}}]}',
            "[DONE]",
        ), headers={"content-type": "text/event-stream"})

    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(handler))
    assert list(client.stream_complete([{"role": "user", "content": "hi"}], "m", 0.5)) == ["lol ", "ok"]
    assert seen["body"]["stream"] is True


def test_stream_continue_reads_the_text_of_each_event():
    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=sse('{"choices":[{"text":" say"}]}',
                                                        '{"choices":[{"text":" less"}]}', "[DONE]"))))
    assert "".join(client.stream_continue("Sam:", "m", 0.5, stop=[])) == " say less"


def test_a_stream_error_status_becomes_an_llm_error():
    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(
        lambda request: httpx.Response(503, text="loading model")))
    with pytest.raises(LLMError, match="503: loading model"):
        list(client.stream_complete([], "m", 0.5))


def test_an_unknown_stream_event_becomes_an_llm_error():
    client = ChatClient("http://model.test/v1", "k", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=sse("{not json"))))
    with pytest.raises(LLMError, match="unknown event"):
        list(client.stream_complete([], "m", 0.5))
