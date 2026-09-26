import json

from mimikr.cli import evaluate
from mimikr.config import Config


class FakeClient:
    """Reply with a fixed text, and embed each text as its length."""

    def __init__(self):
        self.models: list[str] = []
        self.embedding_models: list[str] = []

    def complete(self, messages, model, temperature):
        self.models.append(model)
        return "ok sure"

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
    [saved] = (tmp_path / "data" / "evals").glob("sam-default-model-*.json")
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
