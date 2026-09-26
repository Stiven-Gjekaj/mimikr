import json

import httpx

from mimikr.config import Config
from mimikr.llm import ChatClient
from mimikr.servers import check_servers


def factory(handler):
    """Make clients that send each request to the handler, as a server would get them."""
    return lambda base_url, api_key: ChatClient(base_url, api_key, transport=httpx.MockTransport(handler))


def working(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "mistral-nemo"}, {"id": "other"}]})
    size = 768 if request.url.host == "embed" else 4
    assert json.loads(request.content)["model"] == "nomic-embed-text"
    return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1] * size}]})


def test_both_servers_answer():
    config = Config(base_url="http://chat/v1", embedding_url="http://embed/v1", model="mistral-nemo")
    assert check_servers(config, factory(working)) == [
        (True, "Chat server: 2 models (mistral-nemo, other)."),
        (True, "Embedding server: 768 dimensions from 'nomic-embed-text'."),
    ]


def test_a_model_that_the_server_does_not_have_is_reported():
    config = Config(base_url="http://chat/v1", embedding_url="http://embed/v1", model="llama3.1")
    lines = check_servers(config, factory(working))
    assert (False, "The chat model 'llama3.1' is not in the list of the server.") in lines


def test_a_server_that_does_not_answer_is_reported():
    def refused(request):
        raise httpx.ConnectError("refused")

    lines = check_servers(Config(base_url="http://chat/v1"), factory(refused))
    assert [ok for ok, _ in lines] == [False, False]
    assert lines[0][1].startswith("Chat server: cannot reach the model server at http://chat/v1/")
