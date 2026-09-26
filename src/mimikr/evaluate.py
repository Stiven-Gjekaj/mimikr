"""Measure how near the replies of the model are to the replies of the person.

The evaluation keeps the last turns of the person apart from the transcript.
The model sees the conversation up to each of those turns, and writes a reply.
Then the evaluation compares the reply of the model with the real reply.

The identity that the model uses knows only the part of the transcript before
the first test turn. Thus the model cannot copy a real reply from its prompt.
"""

from dataclasses import dataclass

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
