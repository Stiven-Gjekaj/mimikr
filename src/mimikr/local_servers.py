"""Start and stop llama.cpp servers for mimikr.

llama.cpp serves one model on each server, so mimikr starts one server for the
chat model and one for the embedding model. The output of each server goes to
`<data_dir>/logs/`. mimikr stops the servers that it started when it closes.
"""

import shutil
import subprocess
import time
from pathlib import Path

import httpx

# Places where Homebrew puts llama-server, for a program that has no PATH of a shell.
KNOWN_PLACES = ("/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server")


class ServerError(RuntimeError):
    pass


def find_llama_server() -> str:
    """Return the path of llama-server, or an empty text if it is not found."""
    found = shutil.which("llama-server")
    if found:
        return found
    return next((place for place in KNOWN_PLACES if Path(place).is_file()), "")


class LocalServer:
    def __init__(self, name: str, executable: str, model: str, port: int, alias: str,
                 log_dir: Path, context: int = 8192, embeddings: bool = False):
        self.name = name
        self.executable = executable
        self.model = model
        self.port = port
        self.alias = alias
        self.log_path = log_dir / f"{name}.log"
        self.context = context
        self.embeddings = embeddings
        self.process: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def command(self) -> list[str]:
        command = [self.executable, "-m", self.model, "--port", str(self.port), "--host", "127.0.0.1",
                   "--alias", self.alias, "-c", str(self.context)]
        if self.embeddings:
            # A batch of 2048 tokens takes a long message whole. The default of
            # 512 refuses it.
            command += ["--embeddings", "-b", "2048", "-ub", "2048"]
        return command

    def start(self) -> None:
        if self.running():
            return
        if not self.executable or not Path(self.executable).is_file():
            raise ServerError(f"llama-server is not at {self.executable!r}. Install llama.cpp, or set the path")
        if not Path(self.model).is_file():
            raise ServerError(f"the model file {self.model!r} of the {self.name} server does not exist")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen(self.command(), stdout=log, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL)
        finally:
            log.close()

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def ready(self) -> bool:
        try:
            # trust_env=False: the server is on this computer, so no proxy of the
            # system or of the environment may take the request.
            return httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=1.0, trust_env=False).status_code == 200
        except httpx.HTTPError:
            return False

    def wait_until_ready(self, timeout: float = 120.0) -> None:
        """Wait until the server answers. A large model takes some seconds to load."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.running():
                raise ServerError(f"the {self.name} server stopped. Read {self.log_path}: {self.last_log_line()}")
            if self.ready():
                return
            time.sleep(0.25)
        raise ServerError(f"the {self.name} server did not answer in {timeout:.0f} seconds. "
                          f"Read {self.log_path}: {self.last_log_line()}")

    def last_log_line(self) -> str:
        try:
            lines = [line for line in self.log_path.read_text(encoding="utf-8", errors="replace").splitlines() if line]
        except OSError:
            return ""
        return lines[-1] if lines else ""

    def stop(self, timeout: float = 5.0) -> None:
        if not self.running():
            self.process = None
            return
        self.process.terminate()
        try:
            self.process.wait(timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout)
        self.process = None
