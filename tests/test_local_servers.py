import socket
import stat
import sys
from pathlib import Path

import pytest

from mimikr.local_servers import LocalServer, ServerError

FAKE = Path(__file__).with_name("fake_llama_server.py")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def fake_executable(tmp_path, extra: str = "") -> str:
    """Write a small program that starts the fake server, as llama-server would start."""
    if sys.platform == "win32":
        path = tmp_path / "llama-server.bat"
        path.write_text(f'@"{sys.executable}" "{FAKE}" %* {extra}\n', encoding="utf-8")
    else:
        path = tmp_path / "llama-server"
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@" {extra}\n', encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def model_file(tmp_path) -> str:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"GGUF")
    return str(path)


def test_the_command_has_the_model_the_port_the_alias_and_the_context(tmp_path):
    server = LocalServer("embedding", "/bin/llama-server", "/m.gguf", 8081, "nomic", tmp_path, 4096, embeddings=True)
    assert server.command() == ["/bin/llama-server", "-m", "/m.gguf", "--port", "8081", "--host", "127.0.0.1",
                                "--alias", "nomic", "-c", "4096", "--embeddings", "-b", "2048", "-ub", "2048"]


def test_start_wait_and_stop_a_server(tmp_path):
    server = LocalServer("chat", fake_executable(tmp_path), model_file(tmp_path), free_port(), "mistral", tmp_path)
    server.start()
    try:
        server.wait_until_ready(timeout=15)
        assert server.running() and server.ready()
    finally:
        server.stop()
    assert not server.running()
    assert "as mistral" in server.log_path.read_text(encoding="utf-8")


def test_a_server_that_stops_reports_the_last_line_of_its_log(tmp_path):
    server = LocalServer("chat", fake_executable(tmp_path, "--fail"), model_file(tmp_path), free_port(), "m", tmp_path)
    server.start()
    with pytest.raises(ServerError, match="the model file is broken"):
        server.wait_until_ready(timeout=15)


def test_a_missing_program_or_model_is_an_error_before_the_start(tmp_path):
    with pytest.raises(ServerError, match="llama-server is not at"):
        LocalServer("chat", str(tmp_path / "none"), model_file(tmp_path), 1, "m", tmp_path).start()
    with pytest.raises(ServerError, match="does not exist"):
        LocalServer("chat", fake_executable(tmp_path), str(tmp_path / "none.gguf"), 1, "m", tmp_path).start()
