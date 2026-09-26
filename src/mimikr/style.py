"""Measure how a person writes, from the messages in a transcript."""

import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

from mimikr.transcript import Message

_EMOJI = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f2ff\U0001f900-\U0001f9ff]"
)
_WORD = re.compile(r"\S+")
# A message that is only a link, a mention, or the code of a custom emoji. It
# shows no words of the person, so it is not a stock reply.
_NOT_WORDS = re.compile(r"\s*(?:https?://\S+|@\S+|<a?:\w+:\d+>|:\w+:)\s*", re.IGNORECASE)


@dataclass
class StyleProfile:
    message_count: int = 0
    median_words: float = 0.0
    lowercase_start: float = 0.0
    ends_with_period: float = 0.0
    question_rate: float = 0.0
    exclamation_rate: float = 0.0
    emoji_rate: float = 0.0
    top_emoji: list[str] = field(default_factory=list)
    # The most emoji in one message, for 9 of 10 messages that have emoji.
    max_emoji: int = 0
    stock_replies: list[str] = field(default_factory=list)
    messages_per_turn: float = 1.0

    def describe(self) -> list[str]:
        """Return the profile as short instructions for the model."""
        if self.message_count == 0:
            return []
        lines = [f"A usual message has about {round(self.median_words)} words."]
        if self.lowercase_start >= 0.6:
            lines.append("Start most messages with a lowercase letter.")
        elif self.lowercase_start <= 0.2:
            lines.append("Start messages with a capital letter.")
        if self.ends_with_period <= 0.2:
            lines.append("Do not put a period at the end of a message.")
        elif self.ends_with_period >= 0.6:
            lines.append("End messages with a period.")
        if self.exclamation_rate >= 0.25:
            lines.append("Use exclamation marks often.")
        if self.emoji_rate >= 0.15 and self.top_emoji:
            lines.append(f"Use emoji often. Favorites: {' '.join(self.top_emoji)}")
        if self.emoji_rate >= 0.03 and self.max_emoji:
            lines.append(f"Put {self.max_emoji} emoji or fewer in one message.")
        elif self.emoji_rate < 0.03:
            lines.append("Do not use emoji.")
        if self.stock_replies:
            quoted = ", ".join(f'"{reply}"' for reply in self.stock_replies)
            lines.append(f"Short replies that this person uses again and again: {quoted}.")
        if self.messages_per_turn >= 1.5:
            lines.append(
                f"Send about {round(self.messages_per_turn)} short messages in a row, not one long message."
                " Put each message on its own line."
            )
        return lines


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _percentile_90(values: list[int]) -> int:
    if not values:
        return 0
    # The nearest rank: the smallest value that 90 percent of the values do not pass.
    ordered = sorted(values)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def build_profile(messages: list[Message], speaker: str) -> StyleProfile:
    texts = [message.text for message in messages if message.speaker == speaker]
    total = len(texts)
    if total == 0:
        return StyleProfile()

    emoji = Counter(symbol for text in texts for symbol in _EMOJI.findall(text))
    short = Counter(text.lower() for text in texts if len(_WORD.findall(text)) <= 3 and not _NOT_WORDS.fullmatch(text))

    # A turn is a run of messages from the speaker with no other speaker between them.
    turns: list[int] = []
    previous_speaker = None
    for message in messages:
        if message.speaker == speaker:
            if previous_speaker == speaker:
                turns[-1] += 1
            else:
                turns.append(1)
        previous_speaker = message.speaker

    letters = [text.lstrip()[0] for text in texts if text.lstrip()[:1].isalpha()]
    return StyleProfile(
        message_count=total,
        median_words=statistics.median(len(_WORD.findall(text)) for text in texts),
        lowercase_start=_rate(sum(letter.islower() for letter in letters), len(letters)),
        ends_with_period=_rate(sum(text.rstrip().endswith(".") for text in texts), total),
        question_rate=_rate(sum("?" in text for text in texts), total),
        exclamation_rate=_rate(sum("!" in text for text in texts), total),
        emoji_rate=_rate(sum(bool(_EMOJI.search(text)) for text in texts), total),
        top_emoji=[symbol for symbol, _ in emoji.most_common(5)],
        max_emoji=_percentile_90([len(_EMOJI.findall(text)) for text in texts if _EMOJI.search(text)]),
        stock_replies=[text for text, count in short.most_common(6) if count >= 2],
        messages_per_turn=statistics.mean(turns),
    )


# The style is enforced only with this number of messages or more, because a
# few messages do not show a habit.
ENFORCE_MINIMUM = 5
_FIRST_WORD = re.compile(r"^(\W*)(\w+)")


def _keep_emoji(text: str, limit: int) -> str:
    """Keep the first emoji of the text up to the limit, and remove the others."""
    count = 0

    def one(match: re.Match) -> str:
        nonlocal count
        count += 1
        return match.group(0) if count <= limit else ""

    return re.sub(r" {2,}", " ", _EMOJI.sub(one, text)).strip()


def enforce(profile: StyleProfile, texts: list[str]) -> list[str]:
    """Change the replies of the model where they break a clear habit of the person.

    - Almost no message starts with a capital: make the first letter small,
      except in "I", in "I'm", and in a word of capitals only, such as "NASA".
    - Almost no message ends with a period: remove one period at the end, and
      keep "..." as it is.
    - No message has an emoji: remove the emoji.
    - Otherwise: keep only as many emoji in a message as the person usually puts in one.
    """
    if profile.message_count < ENFORCE_MINIMUM:
        return texts
    result = []
    for text in texts:
        if profile.emoji_rate == 0:
            text = re.sub(r" {2,}", " ", _EMOJI.sub("", text)).strip()
        elif profile.max_emoji:
            text = _keep_emoji(text, profile.max_emoji)
        if profile.lowercase_start >= 0.9:
            match = _FIRST_WORD.match(text)
            if match:
                word = match[2]
                keep = word == "I" or (word.isupper() and len(word) > 1) or word.startswith("I'")
                if not keep:
                    text = match[1] + word[0].lower() + word[1:] + text[match.end():]
        if profile.ends_with_period <= 0.05 and text.endswith(".") and not text.endswith(".."):
            text = text[:-1]
        if text:
            result.append(text)
    return result


def _key(text: str) -> str:
    return " ".join(text.casefold().split())


def drop_repeats(texts: list[str], recent: list[str]) -> list[str]:
    """Remove a message that the identity sent in its recent messages, or earlier in the same reply.

    A person does not answer "bet" three times in a row, but a small model does.
    """
    seen = {_key(text) for text in recent}
    kept = []
    for text in texts:
        if _key(text) in seen:
            continue
        seen.add(_key(text))
        kept.append(text)
    return kept
