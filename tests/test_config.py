from pathlib import Path

from mimikr.config import Config, embedding_base_url, load_config, save_config


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


def test_the_examples_are_recent_by_default_and_the_environment_can_change_them(tmp_path):
    assert load_config(tmp_path / "missing.toml", environ={}).examples == "recent"
    assert load_config(tmp_path / "missing.toml", environ={"MIMIKR_EXAMPLES": "similar"}).examples == "similar"


def test_the_mode_is_chat_by_default():
    assert Config().mode == "chat"


def test_the_look_has_defaults_and_the_file_can_change_it(tmp_path):
    assert (Config().theme, Config().accent, Config().font_size) == ("system", "violet", 14)
    path = tmp_path / "mimikr.toml"
    path.write_text('theme = "dark"\naccent = "#ff8800"\nfont_size = 16\n', encoding="utf-8")
    config = load_config(path, environ={})
    assert (config.theme, config.accent, config.font_size) == ("dark", "#ff8800", 16)


def test_saved_settings_load_back_the_same(tmp_path):
    config = Config(base_url='http://host:8080/v1', model='mistral "nemo"', temperature=0.65, font_size=16,
                    accent="#ff8800", identities_dir=tmp_path / "people", mode="continue")
    path = tmp_path / "mimikr.toml"
    save_config(config, path)
    assert load_config(path, environ={}) == config


def test_saving_writes_over_the_old_file(tmp_path):
    path = tmp_path / "mimikr.toml"
    path.write_text('model = "old"\n', encoding="utf-8")
    save_config(Config(model="new"), path)
    assert load_config(path, environ={}).model == "new"
    assert not path.with_suffix(".tmp").exists()


def test_convert_reads_true_and_false_in_words_and_in_toml():
    from mimikr.config import convert

    assert convert(True, "false") is False and convert(False, "YES") is True
    assert convert(True, False) is False
    assert convert(0, "3") == 3 and convert(Path("a"), "b") == Path("b")


def test_a_true_or_false_setting_reads_the_words_of_the_file_and_of_the_environment(tmp_path):
    path = tmp_path / "mimikr.toml"
    path.write_text("enforce_style = false\n", encoding="utf-8")
    assert load_config(path, environ={}).enforce_style is False
    assert load_config(path, environ={"MIMIKR_ENFORCE_STYLE": "true"}).enforce_style is True
    assert load_config(tmp_path / "none.toml", environ={"MIMIKR_ENFORCE_STYLE": "false"}).enforce_style is False


def test_saved_true_or_false_is_valid_toml(tmp_path):
    path = tmp_path / "mimikr.toml"
    save_config(Config(enforce_style=False), path)
    assert "enforce_style = false" in path.read_text(encoding="utf-8")
    assert load_config(path, environ={}).enforce_style is False
