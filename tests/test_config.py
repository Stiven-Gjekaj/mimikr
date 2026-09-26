from pathlib import Path

from mimikr.config import Config, embedding_base_url, load_config


def test_uses_the_defaults_when_nothing_is_set(tmp_path):
    assert load_config(tmp_path / "missing.toml", environ={}) == Config()


def test_the_file_sets_values_and_the_environment_overrides_them(tmp_path):
    path = tmp_path / "mimikr.toml"
    path.write_text('model = "from-file"\ntemperature = 0.9\nidentities_dir = "people"\n', encoding="utf-8")
    config = load_config(path, environ={"MIMIKR_MODEL": "from-env", "MIMIKR_TEMPERATURE": "0.2"})
    assert config.model == "from-env"
    assert config.temperature == 0.2
    assert config.identities_dir == Path("people")


def test_the_file_sets_the_embedding_model(tmp_path):
    path = tmp_path / "mimikr.toml"
    path.write_text('embedding_model = "mxbai-embed-large"\n', encoding="utf-8")
    assert load_config(path, environ={}).embedding_model == "mxbai-embed-large"


def test_the_embeddings_use_the_chat_server_when_no_embedding_url_is_set():
    assert embedding_base_url(Config(base_url="http://chat/v1")) == "http://chat/v1"
    assert embedding_base_url(Config(base_url="http://chat/v1", embedding_url="http://embed/v1")) == "http://embed/v1"
