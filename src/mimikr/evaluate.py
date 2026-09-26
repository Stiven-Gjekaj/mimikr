"""Measure how near the replies of the model are to the replies of the person.

The evaluation keeps the last turns of the person apart from the transcript.
The model sees the conversation up to each of those turns, and writes a reply.
Then the evaluation compares the reply of the model with the real reply.

The identity that the model uses knows only the part of the transcript before
the first test turn. Thus the model cannot copy a real reply from its prompt.
"""

from dataclasses import dataclass

from mimikr.style import StyleProfile, build_profile
from mimikr.transcript import Message

# The maximum number of messages before a test turn that the model sees.
CONTEXT_SIZE = 20


class EvaluationError(ValueError):
    pass


@dataclass
class Case:
    context: list[Message]
    reply: list[Message]


def turn_starts(messages: list[Message], speaker: str) -> list[int]:
    """Return the index of the first message of each turn of the speaker."""
    return [
        index
        for index, message in enumerate(messages)
        if message.speaker == speaker and (index == 0 or messages[index - 1].speaker != speaker)
    ]


def split_cases(
    messages: list[Message], speaker: str, test_fraction: float = 0.2, context_size: int = CONTEXT_SIZE
) -> tuple[list[Message], list[Case]]:
    """Split a transcript into the training messages and the test cases.

    Each test case is one turn of the speaker: one or more messages in a row.
    The training messages end before the first test turn.
    """
    starts = turn_starts(messages, speaker)
    if len(starts) < 2:
        raise EvaluationError(f"the transcript needs two or more turns of {speaker!r}, and has {len(starts)}")
    # Keep one turn or more for the training, so that the identity has a style.
    count = min(len(starts) - 1, max(1, round(len(starts) * test_fraction)))
    training = messages[: starts[-count]]

    cases = []
    for start in starts[-count:]:
        end = start
        while end < len(messages) and messages[end].speaker == speaker:
            end += 1
        cases.append(Case(context=messages[max(0, start - context_size) : start], reply=messages[start:end]))
    return training, cases


# The parts of the style profile that the score compares.
# The rate of questions is not here, because it depends on the conversation
# more than on the person.
STYLE_FEATURES = (
    "median_words",
    "lowercase_start",
    "ends_with_period",
    "exclamation_rate",
    "emoji_rate",
    "messages_per_turn",
)


@dataclass
class StyleScore:
    score: float
    # For each feature: the value of the real replies and of the replies of the model.
    features: dict[str, tuple[float, float]]


def profile_of_turns(turns: list[list[str]]) -> StyleProfile:
    """Measure the style of a list of turns. Each turn is a list of messages."""
    messages = []
    for turn in turns:
        messages.append(Message("other", "."))
        messages += [Message("self", text) for text in turn]
    return build_profile(messages, "self")


def feature_difference(name: str, real: float, generated: float) -> float:
    """Return a difference from 0 (the same) to 1 (as far apart as possible)."""
    if name in ("median_words", "messages_per_turn"):
        top = max(real, generated)
        return abs(real - generated) / top if top else 0.0
    return abs(real - generated)


def score_style(real_turns: list[list[str]], generated_turns: list[list[str]]) -> StyleScore:
    """Compare the style of all real turns with the style of all generated turns.

    One message tells little about a style, so the score compares the two sets
    of turns, and not each pair. A score of 1 means the same style.
    """
    real = profile_of_turns(real_turns)
    generated = profile_of_turns(generated_turns)
    features = {name: (getattr(real, name), getattr(generated, name)) for name in STYLE_FEATURES}
    differences = [feature_difference(name, *values) for name, values in features.items()]
    return StyleScore(score=1 - sum(differences) / len(differences), features=features)
