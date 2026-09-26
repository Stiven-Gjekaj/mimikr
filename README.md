<div align="center">

![mimikr](assets/wordmark.svg)

### A chatbot that writes like a person you know

_A short description, a transcript, and a model on your own computer._

![Python](https://img.shields.io/badge/python-a78bfa?style=for-the-badge&logo=python&logoColor=07090f)
![Qt](https://img.shields.io/badge/pyside6-60a5fa?style=for-the-badge&logo=qt&logoColor=07090f)
![macOS](https://img.shields.io/badge/macos-34d399?style=for-the-badge&logo=apple&logoColor=07090f)
![Windows](https://img.shields.io/badge/windows-34d399?style=for-the-badge&logo=windows&logoColor=07090f)
![Linux](https://img.shields.io/badge/linux-a3e635?style=for-the-badge&logo=linux&logoColor=07090f)
[![MIT licence](https://img.shields.io/badge/mit_licence-d9f99d?style=for-the-badge&logoColor=07090f)](LICENSE)

![Phase](https://img.shields.io/badge/phase-P2_built-34d399?style=flat-square&labelColor=07090f)
![Local](https://img.shields.io/badge/data-stays_local-a78bfa?style=flat-square&labelColor=07090f)

<p align="center">
  <a href="#overview"><b>Overview</b></a> |
  <a href="#start"><b>Start</b></a> |
  <a href="#make-an-identity"><b>Identities</b></a> |
  <a href="#rooms"><b>Rooms</b></a> |
  <a href="#score-an-identity"><b>Score</b></a> |
  <a href="#how-a-reply-is-made"><b>How it works</b></a> |
  <a href="docs/roadmap.md"><b>Roadmap</b></a>
</p>

<a href="https://ko-fi.com/stivengjekaj"><img src="https://img.shields.io/badge/Ko--fi-Support_this_project-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support this project on Ko-fi"/></a>

</div>

---

> [!NOTE]
> **Phases P1 and P2 are built.**
> The window, the rooms, the identity files and the style profile work.
> `mimikr eval` scores the replies of a model against the real replies.
> The tests prove both with a fake model. No real model has run the score yet.
> [docs/roadmap.md](docs/roadmap.md) says what comes next, and
> [docs/milestones.md](docs/milestones.md) holds each decision and the reason
> for it.

---

## Overview

**mimikr** writes chat messages in the style of a person.
You give it two files for each person: a short description and a transcript of
the messages of that person.
mimikr measures how the person writes, and tells a language model on your
computer to write in the same way.

You talk to the identities in rooms.
A room holds you and one or more identities, and the identities can also talk
to each other.

<table>
<tr>
<td width="50%" valign="top">

### What it does

- **Reads a transcript** in plain `Name: message` lines.
- **Measures the style**: length, capitals, periods, emoji, stock replies,
  and messages in a row.
- **Writes like the person**, with a real sample of their messages in the
  prompt.
- **Sends short messages in a row** when the person does.
- **Holds rooms** with one or more identities.

</td>
<td width="50%" valign="top">

### How it behaves

- It runs on your computer. The data goes to your model server only.
- It works with Ollama, LM Studio, llama.cpp, and each other server with the
  OpenAI chat API.
- It reads the files of an identity again for each reply, so an edit takes
  effect at once.
- It never changes the files of an identity.
- A native window, on macOS, Windows and Linux.

</td>
</tr>
</table>

---

## Start

You need Python 3.11 or later, [uv](https://docs.astral.sh/uv/), and a local
model server.
With [Ollama](https://ollama.com):

```bash
ollama pull llama3.1
```

Then start mimikr from the root of the repository:

```bash
uv sync
uv run mimikr
```

To try the two invented examples:

```bash
MIMIKR_IDENTITIES_DIR=examples/identities uv run mimikr
```

---

## Make an identity

Make one directory for each identity in `identities/`:

```
identities/
  alex/
    personality.md    necessary: a short description of the person
    chat.md           optional: a transcript of their messages
    identity.toml     optional: the settings of this identity
```

`chat.md` holds one message on each line:

```
[2025-03-02 23:41] June: are you still awake
Alex: unfortunately
Alex: just got home
  and the kitchen was chaos
```

- The time in brackets is optional.
- A line that starts with a space continues the previous message.
- A line that starts with `#` is a comment.

`identity.toml` changes the defaults:

```toml
display_name = "Alex"
speaker = "alex_99"     # the name of the person in chat.md
model = "qwen2.5"       # a different model for this identity
temperature = 0.7
```

If `speaker` is not set, mimikr uses the display name.
If `display_name` is not set, mimikr uses the name of the directory.

This command shows what mimikr found in each identity:

```bash
uv run mimikr check
```

```
june (June)
  chat.md: none
sam (Sam)
  chat.md: 11 messages from 'Sam'
  - A usual message has about 3 words.
  - Start most messages with a lowercase letter.
  - Do not put a period at the end of a message.
  - Do not use emoji.
  - Send about 2 short messages in a row, not one long message. Put each message on its own line.
```

---

## Rooms

- Click **New room**, and select the members.
- Write a message and press Enter. Each member replies one time, in order.
- Click **Next speaker** to let the next member write. Click it again and the
  identities talk to each other.

mimikr keeps each room as a JSON file in `data/rooms/`.

---

## Score an identity

`mimikr eval` tells how near the replies of a model are to the real replies of
the person:

```bash
uv run mimikr eval sam --show
```

1. It keeps the last 20 percent of the turns of the person apart from the
   transcript.
2. The identity learns its style from the part before those turns only, so the
   model cannot copy a real reply from its prompt.
3. The model sees the conversation up to each test turn, and writes a reply.
4. The **style** score compares the style of all model replies with the style
   of all real replies. 1 is the same style.
5. The **meaning** score compares each model reply with its real reply through
   an embedding model. The report also gives the score of two different real
   replies. A model that scores near that number does no better than a random
   reply of the person.

This report shows its shape only. A stand-in server wrote the reply, and no
real model did:

```
sam, model llama3.1, temperature 0.8
1 test reply, 15 training messages
Warning: a score from fewer than 10 test replies is not reliable.

style    0.86
  feature                 real   model
  median_words            2.00    3.00
  lowercase_start         1.00    1.00
  ends_with_period        0.00    0.00
  exclamation_rate        0.00    0.00
  emoji_rate              0.00    0.00
  messages_per_turn       1.00    2.00
```

The meaning score needs an embedding model on the model server:

```bash
ollama pull nomic-embed-text
```

`--model` tries a different model, `--cases N` scores only the last N test
replies, and `--no-meaning` skips the embedding model.
Each report goes to `data/evals/` as JSON, so you can compare models later.
The model writes different replies each time, so run a score two times before
you trust a small difference.

---

## How a reply is made

```mermaid
flowchart LR
    A[personality.md] --> P[the prompt]
    B[chat.md] --> S[style profile] --> P
    B --> E[recent examples] --> P
    R[the room] --> P
    P --> M[(model server)]
    M --> X[split into messages] --> R
```

1. mimikr reads the files of the identity again.
2. The prompt holds the description, the style as plain instructions, and the
   most recent part of the transcript that fits the budget.
3. The messages of the identity go to the model as its own. The messages of
   each other member go with the name first.
4. mimikr removes a name that the model puts before its reply. If the person
   sends short messages in a row, each line becomes one message.

---

## Settings

Put the settings in `mimikr.toml` in the working directory, or set the
environment variables. The environment variables have priority.

| Key | Variable | Default |
| :-- | :-- | :-- |
| `base_url` | `MIMIKR_BASE_URL` | `http://localhost:11434/v1` (Ollama) |
| `api_key` | `MIMIKR_API_KEY` | `local` |
| `model` | `MIMIKR_MODEL` | `llama3.1` |
| `temperature` | `MIMIKR_TEMPERATURE` | `0.8` |
| `embedding_model` | `MIMIKR_EMBEDDING_MODEL` | `nomic-embed-text` |
| `identities_dir` | `MIMIKR_IDENTITIES_DIR` | `identities` |
| `data_dir` | `MIMIKR_DATA_DIR` | `data` |

LM Studio uses `http://localhost:1234/v1`.

---

## Real people

> [!WARNING]
> **An identity holds the private messages of a real person.**
> Get the consent of that person first.
> What mimikr writes is not a message from that person, so do not show it as
> one.
> Read [TERMS.md](TERMS.md) sections 4 and 5 before you make an identity.

`identities/`, `data/` and `mimikr.toml` are in `.gitignore`, so they stay out
of the repository.

---

## Project documents

| Document | What it holds |
| :-- | :-- |
| [docs/roadmap.md](docs/roadmap.md) | The order of the work, and the exit test for each phase |
| [docs/milestones.md](docs/milestones.md) | Each decision, the reason for it, and the options that lost |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to take part, and the rule that no real person goes into the repository |
| [AGENTS.md](AGENTS.md) | The rules for anybody who changes this repository, human or agent |
| [SECURITY.md](SECURITY.md) | The threat model, and how to report a vulnerability privately |
| [TERMS.md](TERMS.md) | What you agree to when you make an identity of a real person |
| [SUPPORT.md](SUPPORT.md) | Where to ask a question |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Applies to everybody who takes part |

---

## Tests

```bash
uv run pytest
```

No test calls a real model. The window tests use the Qt `offscreen` platform,
so they open no window.

---

## Licence

MIT. See [LICENSE](LICENSE) and [TERMS.md](TERMS.md).

<div align="center">
<sub>mimikr imitates people. Ask them first.</sub>
</div>
