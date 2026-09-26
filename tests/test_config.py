from pathlib import Path

from mimikr.config import Config, load_config


def test_uses_the_defaults_when_nothing_is_set(tmp_path):
    assert load_config(tmp_path / "missing.toml", environ={}) == Config()


def test_the_file_sets_values_and_the_environment_overrides_them(tmp_path):
    path = tmp_path / "mimikr.toml"
    path.write_text('model = "from-file"\ntemperature = 0.9\nidentities_dir = "people"\n', encoding="utf-8")
    config = load_config(path, environ={"MIMIKR_MODEL": "from-env", "MIMIKR_TEMPERATURE": "0.2"})
    assert config.model == "from-env"
    assert config.temperature == 0.2
    assert config.identities_dir == Path("people")
