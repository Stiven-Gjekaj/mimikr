import json

from mimikr.cli import evaluate, import_export, scores
from mimikr.config import Config


class FakeClient:
    """Reply with a fixed text, and embed each text as its length."""

    def __init__(self):
        self.models: list[str] = []
        self.embedding_models: list[str] = []

    def complete(self, messages, model, temperature):
        self.models.append(model)
        return "ok sure"

    def continue_text(self, prompt, model, temperature, stop):
        self.models.append(model)
        return " ok sure"

    def embed(self, texts, model):
        self.embedding_models.append(model)
        return [[float(len(text)), 1.0] for text in texts]


def make_config(tmp_path, settings: str | None = None) -> Config:
    directory = tmp_path / "identities" / "sam"
    directory.mkdir(parents=True)
    (directory / "personality.md").write_text("A line cook.", encoding="utf-8")
    lines = []
    for n in range(10):
        lines += [f"June: question {n}", f"Sam: answer {n}"]
    (directory / "chat.md").write_text("\n".join(lines), encoding="utf-8")
    if settings:
        (directory / "identity.toml").write_text(settings, encoding="utf-8")
    return Config(identities_dir=tmp_path / "identities", data_dir=tmp_path / "data",
                  model="default-model", embedding_model="embedder")


def test_eval_prints_the_scores_and_saves_the_report(tmp_path, capsys):
    client = FakeClient()
    assert evaluate(make_config(tmp_path), "sam", cases=None, model=None, meaning=True, show=True,
                    client=client) == 0
    out = capsys.readouterr().out
    assert "sam, model default-model" in out
    assert "2 test replies" in out
    assert "Warning: a score from fewer than 10 test replies is not reliable." in out
    assert "style    " in out and "meaning  " in out
    assert "  real:  answer 9" in out and "  model: ok sure" in out
    [saved] = (tmp_path / "data" / "evals").glob("sam-default-model-chat-recent-*.json")
    report = json.loads(saved.read_text(encoding="utf-8"))
    assert [result["real"] for result in report["results"]] == [["answer 8"], ["answer 9"]]
    assert client.embedding_models == ["embedder"]


def test_the_model_option_has_priority_over_the_identity_and_the_settings(tmp_path, capsys):
    client = FakeClient()
    config = make_config(tmp_path, settings='model = "identity-model"\n')
    evaluate(config, "sam", cases=1, model="option-model", meaning=False, show=False, client=client)
    assert client.models == ["option-model"]
    evaluate(config, "sam", cases=1, model=None, meaning=False, show=False, client=client)
    assert client.models[-1] == "identity-model"


def test_no_meaning_calls_no_embedding_model(tmp_path, capsys):
    client = FakeClient()
    evaluate(make_config(tmp_path), "sam", cases=None, model=None, meaning=False, show=False, client=client)
    assert client.embedding_models == []
    assert "meaning  not measured" in capsys.readouterr().out


def test_an_unknown_identity_is_an_error(tmp_path, capsys):
    assert evaluate(make_config(tmp_path), "zed", None, None, True, False, client=FakeClient()) == 1
    assert "no identity is named 'zed'" in capsys.readouterr().err


def test_one_case_is_one_test_reply(tmp_path, capsys):
    evaluate(make_config(tmp_path), "sam", cases=1, model=None, meaning=False, show=False, client=FakeClient())
    assert "1 test reply," in capsys.readouterr().out


def test_an_error_before_the_first_case_has_no_blank_line(tmp_path, capsys):
    (tmp_path / "identities" / "june").mkdir(parents=True)
    (tmp_path / "identities" / "june" / "personality.md").write_text("A teacher.", encoding="utf-8")
    config = make_config(tmp_path)
    assert evaluate(config, "june", None, None, False, False, client=FakeClient()) == 1
    assert capsys.readouterr().err.startswith("mimikr: the identity 'june' has no chat.md")


def test_eval_can_embed_with_a_second_client(tmp_path, capsys):
    chat, embedder = FakeClient(), FakeClient()
    evaluate(make_config(tmp_path), "sam", None, None, True, False, client=chat, embed_client=embedder)
    assert chat.embedding_models == [] and embedder.embedding_models == ["embedder"]


def test_the_examples_option_has_priority_over_the_setting(tmp_path, capsys):
    client = FakeClient()
    config = make_config(tmp_path)
    evaluate(config, "sam", None, None, False, False, client=client, examples="similar")
    out = capsys.readouterr().out
    assert "similar examples" in out
    # The similar examples need the embedding model, even with no meaning score.
    assert client.embedding_models
    evaluate(config, "sam", None, None, False, False, client=FakeClient())
    assert "recent examples" in capsys.readouterr().out


def test_the_mode_option_is_in_the_report_and_the_file_name(tmp_path, capsys):
    evaluate(make_config(tmp_path), "sam", None, None, False, False, client=FakeClient(), mode="continue")
    assert "continue mode" in capsys.readouterr().out
    assert list((tmp_path / "data" / "evals").glob("sam-default-model-continue-recent-*.json"))


def save_report(directory, name, identity, model, style, meaning):
    directory.mkdir(parents=True, exist_ok=True)
    report = {"identity": identity, "model": model, "mode": "chat", "examples": "recent",
              "results": [{}] * 12, "style": {"score": style},
              "meaning": None if meaning is None else {"score": meaning, "baseline": 0.3}}
    (directory / name).write_text(json.dumps(report), encoding="utf-8")


def test_scores_sorts_by_meaning_and_puts_reports_with_no_meaning_last(tmp_path, capsys):
    config = make_config(tmp_path)
    evals = tmp_path / "data" / "evals"
    save_report(evals, "a.json", "sam", "small", 0.9, 0.40)
    save_report(evals, "b.json", "sam", "large", 0.7, 0.55)
    save_report(evals, "c.json", "sam", "nomeaning", 0.95, None)
    save_report(evals, "d.json", "june", "other", 0.5, 0.9)
    assert scores(config, "sam") == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[1] for line in lines[1:]] == ["large", "small", "nomeaning"]
    assert lines[1].split()[-2:] == ["0.55", "0.30"]
    assert lines[3].split()[-2:] == ["-", "-"]


def test_scores_skips_a_damaged_file(tmp_path, capsys):
    config = make_config(tmp_path)
    evals = tmp_path / "data" / "evals"
    save_report(evals, "a.json", "sam", "small", 0.9, 0.4)
    (evals / "bad.json").write_text("{", encoding="utf-8")
    assert scores(config, None) == 0
    captured = capsys.readouterr()
    assert "skip bad.json" in captured.err and "small" in captured.out


def test_scores_with_no_reports_says_what_to_do(tmp_path, capsys):
    assert scores(make_config(tmp_path), None) == 1
    assert "Run `mimikr eval <identity>` first." in capsys.readouterr().out


WHATSAPP = "\ufeff1/1/24, 10:00 AM - June: noodles?\n1/1/24, 10:01 AM - Sam: say less\n1/1/24, 10:02 AM - Sam: 1pm\n"


def test_import_writes_the_transcript_and_counts_the_speakers(tmp_path, capsys):
    source = tmp_path / "chat.txt"
    source.write_text(WHATSAPP, encoding="utf-8")
    output = tmp_path / "identities" / "sam" / "chat.md"
    assert import_export("whatsapp", source, output, force=False) == 0
    assert output.read_text(encoding="utf-8") == (
        "[1/1/24 10:00 AM] June: noodles?\n[1/1/24 10:01 AM] Sam: say less\n[1/1/24 10:02 AM] Sam: 1pm\n"
    )
    assert "3 messages from Sam (2), June (1)" in capsys.readouterr().err


def test_import_does_not_write_over_a_file(tmp_path, capsys):
    source = tmp_path / "chat.txt"
    source.write_text(WHATSAPP, encoding="utf-8")
    output = tmp_path / "chat.md"
    output.write_text("Sam: keep me\n", encoding="utf-8")
    assert import_export("whatsapp", source, output, force=False) == 1
    assert output.read_text(encoding="utf-8") == "Sam: keep me\n"
    assert "Use --force" in capsys.readouterr().err
    assert import_export("whatsapp", source, output, force=True) == 0
    assert "say less" in output.read_text(encoding="utf-8")


def test_import_with_no_output_writes_to_the_standard_output(tmp_path, capsys):
    source = tmp_path / "chat.txt"
    source.write_text(WHATSAPP, encoding="utf-8")
    assert import_export("whatsapp", source, None, force=False) == 0
    assert capsys.readouterr().out.startswith("[1/1/24 10:00 AM] June: noodles?")


def test_import_reports_a_wrong_format(tmp_path, capsys):
    source = tmp_path / "chat.txt"
    source.write_text(WHATSAPP, encoding="utf-8")
    assert import_export("telegram", source, None, force=False) == 1
    assert "not the JSON export of Telegram Desktop" in capsys.readouterr().err
