"""The exit test of P2: the real replies get the best score, and the replies
of a different person get a worse one."""

import pytest

from mimikr.evaluate import EvaluationError, run_evaluation
from mimikr.identity import Identity
from mimikr.style import build_profile
from mimikr.transcript import Message
from test_evaluate import WordEmbedder


def sam() -> Identity:
    """An identity that sends two short lowercase messages in each turn."""
    transcript = []
    for n in range(30):
        transcript.append(Message("June", f"June asks question {n}?"))
        transcript.append(Message("Sam", f"sam answer {n} about topic{n}"))
        transcript.append(Message("Sam", f"and more on topic{n}"))
    return Identity(
        id="sam", display_name="Sam", personality="A line cook.", speaker="Sam",
        transcript=transcript, style=build_profile(transcript, "Sam"),
    )


class Oracle:
    """Reply with the real reply of the case. It reads it from the transcript."""

    def __init__(self, identity: Identity):
        self.transcript = identity.transcript
        self.requests: list[list[dict]] = []

    def complete(self, messages, model, temperature):
        self.requests.append(messages)
        last = messages[-1]["content"].splitlines()[-1].removeprefix("June: ")
        index = next(i for i, m in enumerate(self.transcript) if m.text == last)
        return f"{self.transcript[index + 1].text}\n{self.transcript[index + 2].text}"


class Stranger:
    """Reply as a different person: one long, formal message."""

    def complete(self, messages, model, temperature):
        return "Good evening. I am afraid that I cannot answer that question today, but I will try tomorrow."


def test_the_real_replies_get_the_best_score():
    identity = sam()
    report = run_evaluation(identity, Oracle(identity), model="m", temperature=0.5, embed=WordEmbedder())
    assert report.style.score == pytest.approx(1.0)
    assert report.meaning.score == pytest.approx(1.0)
    assert len(report.results) == 6


def test_the_replies_of_a_different_person_get_a_worse_score():
    report = run_evaluation(sam(), Stranger(), model="m", temperature=0.5, embed=WordEmbedder())
    assert report.style.score < 0.6
    assert report.meaning.score < report.meaning.baseline


def test_no_request_holds_the_reply_that_it_asks_for():
    identity = sam()
    oracle = Oracle(identity)
    report = run_evaluation(identity, oracle, model="m", temperature=0.5)
    for request, result in zip(oracle.requests, report.results):
        text = "\n".join(message["content"] for message in request)
        assert not any(real in text for real in result.real)


def test_the_model_knows_only_the_training_part():
    identity = sam()
    oracle = Oracle(identity)
    report = run_evaluation(identity, oracle, model="m", temperature=0.5)
    # 24 turns of three messages, and the question before the first test turn.
    assert report.training_messages == 24 * 3 + 1
    last_test_reply = report.results[-1].real[0]
    assert last_test_reply not in oracle.requests[0][0]["content"]


def test_max_cases_keeps_the_last_cases():
    identity = sam()
    report = run_evaluation(identity, Oracle(identity), model="m", temperature=0.5, max_cases=2)
    assert [result.real[0] for result in report.results] == ["sam answer 28 about topic28", "sam answer 29 about topic29"]


def test_an_identity_with_no_chat_cannot_be_scored():
    identity = Identity(id="june", display_name="June", personality="A teacher.")
    with pytest.raises(EvaluationError, match="no chat.md"):
        run_evaluation(identity, Stranger(), model="m", temperature=0.5)


def test_similar_examples_hold_no_test_reply(monkeypatch):
    monkeypatch.setattr("mimikr.prompt.EXAMPLE_BUDGET", 200)
    identity = sam()
    oracle = Oracle(identity)
    report = run_evaluation(identity, oracle, model="m", temperature=0.5,
                            examples="similar", example_embed=WordEmbedder())
    assert report.examples == "similar"
    for request, result in zip(oracle.requests, report.results):
        text = "\n".join(message["content"] for message in request)
        assert not any(real in text for real in result.real)


def test_similar_examples_match_the_question_of_the_case(monkeypatch):
    monkeypatch.setattr("mimikr.prompt.EXAMPLE_BUDGET", 60)
    lines = [("June", "want noodles for lunch"), ("Sam", "noodles always"),
             ("June", "did you watch the match"), ("Sam", "we lost again"),
             ("June", "how was the shift"), ("Sam", "chaos"),
             ("June", "noodles again tonight"), ("Sam", "obviously")]
    transcript = [Message(speaker, text) for speaker, text in lines]
    identity = Identity(id="sam", display_name="Sam", personality="A cook.", speaker="Sam",
                        transcript=transcript, style=build_profile(transcript, "Sam"))
    completer = Stranger()
    completer.requests = []
    completer.complete = lambda messages, model, temperature: completer.requests.append(messages) or "ok"
    run_evaluation(identity, completer, model="m", temperature=0.5, test_fraction=0.25,
                   examples="similar", example_embed=WordEmbedder())
    system = completer.requests[0][0]["content"]
    assert "Sam: noodles always" in system
    assert "we lost again" not in system and "chaos" not in system


def test_similar_examples_need_an_embedder():
    with pytest.raises(EvaluationError, match="need an embedding model"):
        run_evaluation(sam(), Stranger(), model="m", temperature=0.5, examples="similar")
