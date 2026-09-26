from pathlib import Path

from mimikr.config import Config, app_home, config_file, embedding_base_url, load_config, save_config


def test_uses_the_defaults_when_nothing_is_set(tmp_path):
    from dataclasses import replace

    expected = replace(Config(), identities_dir=tmp_path / "identities", data_dir=tmp_path / "data")
    assert load_config(tmp_path / "missing.toml", environ={}) == expected


def test_the_file_sets_values_and_the_environment_overrides_them(tmp_path):
    path = tmp_path / "mimikr.toml"
    path.write_text('model = "from-file"\ntemperature = 0.9\nidentities_dir = "people"\n', encoding="utf-8")
    config = load_config(path, environ={"MIMIKR_MODEL": "from-env", "MIMIKR_TEMPERATURE": "0.2"})
    assert config.model == "from-env"
    assert config.temperature == 0.2
    # A relative folder is relative to the directory of the file.
    assert config.identities_dir == tmp_path / "people"


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
                    accent="#ff8800", identities_dir=tmp_path / "people", data_dir=tmp_path / "rooms",
                    mode="continue")
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


def test_the_home_is_mimikr_home_then_documents_in_the_app_then_the_working_directory(tmp_path, monkeypatch):
    import sys

    assert app_home({"MIMIKR_HOME": str(tmp_path)}) == tmp_path
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert app_home({}) == Path.home() / "Documents" / "mimikr"
    monkeypatch.delattr(sys, "frozen")
    monkeypatch.chdir(tmp_path)
    assert app_home({}) == tmp_path


def test_the_settings_file_and_the_folders_are_in_the_home(tmp_path):
    environ = {"MIMIKR_HOME": str(tmp_path)}
    (tmp_path / "mimikr.toml").write_text('model = "from-home"\n', encoding="utf-8")
    config = load_config(environ=environ)
    assert config_file(environ) == tmp_path / "mimikr.toml"
    assert (config.model, config.identities_dir, config.data_dir) == (
        "from-home", tmp_path / "identities", tmp_path / "data")


def test_an_absolute_folder_stays(tmp_path):
    path = tmp_path / "mimikr.toml"
    path.write_text(f'data_dir = "{(tmp_path / "elsewhere").as_posix()}"\n', encoding="utf-8")
    assert load_config(path, environ={}).data_dir == tmp_path / "elsewhere"


def test_save_makes_the_directory_of_the_file(tmp_path):
    path = tmp_path / "new" / "mimikr.toml"
    save_config(Config(), path)
    assert path.is_file()
