<div align="center">
  <a href="../README.md"><b>mimikr</b></a>
</div>

# Milestones

The code of each phase is built. No real model has run the score yet, so the
defaults below are choices, and not results.
[The roadmap](roadmap.md) says what is still open.
This file holds the decisions that shape the work, and the reason for each.
It also holds the options that lost, because the reason a choice lost is the
part that a later reader needs.

---

## The rule that decides everything else

**Nothing leaves the computer.**

An identity holds the private messages of a real person.
mimikr sends them to one place: the model server in `base_url`.
The default address is on the same computer.
The program has no account, no telemetry, and no update check.

The rule also decides the model API.
A local model server is the only kind of server that the default can name.

---

## The decisions

### Python

The model servers, the tokenizers and the embedding libraries all have a
Python interface first.
The work of this project is in the prompt, and a prompt changes many times a
day. Python makes each change short.

- **Rust** lost. It gives one fast binary, but the slow part is the model, and
  not the program. A change to the prompt costs a compile.
- **TypeScript** lost. It is good for a web interface, and the interface is not
  a web page.

### Any server with the OpenAI chat API

Ollama, LM Studio, the llama.cpp server, vLLM and many others give the same
`/v1/chat/completions` endpoint.
One client with one setting, `base_url`, works with all of them.

- **Only Ollama** lost. It is the simplest to start, but it ties the user to
  one server.
- **llama.cpp in the process** lost. It needs no server, but it adds a large
  native dependency, and each new model format needs a new build.

### A native window with PySide6

The user asked for a native program and not a web page.
PySide6 is the Qt library for Python, from the Qt Company.
It draws native controls on macOS, on Windows and on Linux, and its licence is
the LGPL version 3.

- **A web interface in the browser** lost. The first version had one, with
  FastAPI and a WebSocket. It needed a server, a port and a browser for a
  program that one person uses on one computer.
- **Tkinter** lost. It comes with Python, but its controls do not look native
  and it has no good text layout for chat bubbles.
- **PyQt6** lost. It is the same Qt, but its licence is the GPL.
- **wxPython, Kivy and Flet** lost. Each is smaller, and each has fewer controls
  or a less native look than Qt.

### `Name: message` lines

A person can write the format by hand.
Each chat application can export to it with a short script.

- **A heading for each speaker** lost. It shows long messages well, but
  hand-written chats are mostly short lines.
- **The raw exports** lost for now. Each application has its own format, and
  each format changes. An importer for each export comes later, and it writes
  `Name: message` lines.

### English transcripts only

The transcripts are in English, and mimikr supports no other language.
The style profile, the prompt, and the choice of model assume English.

- **Support for other languages** lost. It makes each measurement of the style
  depend on the language, and it takes away the models that are strong in
  English only. No user needs it.

### Rooms

A conversation is a room.
A room holds the user and one or more identities.
The name is "room" and not "chat", because identities also talk to each other
in a room.
`Next speaker` lets the members talk in turn.

### A measured style profile

`style.py` counts things in the transcript: the length of a message, capitals,
periods, emoji, repeated short replies, and messages in a row.
Then it writes each result as one plain instruction.

A model copies the style of examples, but a small local model copies it badly.
A plain instruction such as "Do not put a period at the end of a message" helps
a small model more than ten examples do.
The two go into the prompt together.

- **Examples only** lost, for the reason above.
- **A model that writes the profile** lost for now. It costs one call to the
  model for each identity, and a count gives the same facts with no model.

### The most recent examples, in a budget

The prompt holds the most recent part of the transcript that fits in 6000
characters.
Recent messages show how the person writes now.

### Similar examples, and recent examples until a score says otherwise

`examples = "similar"` cuts the transcript into exchanges: one turn of the
person and up to three messages before it. An embedding model turns the
messages before each turn into a vector. For a new message, the prompt holds
the exchanges whose vectors are nearest, in the order of the transcript.

The default stays `recent`. Similar examples are the better idea, but no score
proves it yet, and they need a second model. P4 decides the default.

The embeddings stay in `data/index/`. The key of the file is a hash of the
transcript and of the name of the embedding model, so a change to either one
makes the embeddings again.

In `mimikr eval`, the index holds the training part only. Otherwise a test
reply could come back as an example, and the score would measure a copy.

- **Examples chosen by a model** lost. It costs one call to the chat model for
  each reply, and an embedding costs a small part of that.
- **A vector database** lost. One person has a few thousand exchanges at most,
  and a JSON file and a loop find the nearest ones in no measurable time.

### Two modes: chat and continue

An instruct model learned to be a helpful assistant, and the prompt fights that
voice in each reply. A base model learned only to continue text. Give it a chat
log that ends with `Sam:`, and it writes as Sam, because that is the most
likely next line.

`mode = "continue"` sends such a log to `/v1/completions`. The stop sequences
are the names of the other people, so the model stops at the end of the turn of
the person. The reply is also cut at the name of another person, because some
servers do not honor stop sequences.

Each identity can set its own mode, because the mode goes with the model.

`writer.py` writes the reply for a room and for `mimikr eval`. Thus a score
measures the same prompt that a room sends.

- **Only the chat mode** lost. It gives no way to test the idea above.
- **A chat template on a base model** lost. A base model has no template, and a
  made-up template is one more thing that can go wrong.

### llama.cpp as the local server

The user chose llama.cpp. It serves one model on each server, so the chat model
and the embedding model need two addresses. `embedding_url` holds the second
address. When it is empty, the embeddings go to `base_url`, which suits
Ollama and LM Studio.

The first test found that nomic-embed-text gives 0.79 for two texts about the
same thing, and 0.41 for two texts that are not related. An unrelated reply
does not score 0, and that is why the meaning score reports a baseline.

### Importers for three applications

`mimikr import` reads WhatsApp, Telegram Desktop and DiscordChatExporter. Each
reader gives messages, and one writer turns them into `chat.md` lines. The
command does not write over a file without `--force`, because a `chat.md` can
hold edits that exist nowhere else.

- **iMessage** lost. The Messages application has no export. A program that
  reads its database needs Full Disk Access, and then it can read each message
  of each person on the computer. That is much more than one conversation.
  A person who has an export from another tool can turn it into
  `Name: message` lines.
- **Media and deleted messages** lost. They have no text to learn a style from.

### Live replies

The client asks the server to stream the reply. The window shows the text so
far in a grey bubble, and replaces it with the real messages at the end. The
grey bubble is not a message, and nothing saves it.

- **Only the complete reply** lost. A local model on a laptop can take ten
  seconds or more, and a window that shows nothing for that time looks broken.

### Automatic rooms, and one Stop button

**Auto** lets the members talk in turn for a number of messages. **Stop** ends
any work: an automatic room, a round of replies, or one reply. A stop during a
reply takes effect at the next piece of text, and the part that the model
wrote goes away. A reply is whole or it does not exist.

- **Keep the part of a stopped reply** lost. Half a message is a message that
  the person never wrote, and the next reply then continues from it.

### A model call that blocks, in a worker thread

The model client blocks. The window starts a thread for each turn, and the
thread sends each new message to the window through a Qt signal.

- **asyncio with qasync** lost. It joins the event loop of Qt and the event loop
  of asyncio, and that adds a dependency for one call at a time.

### Many short messages from one reply

Many people send three short messages and not one long one.
If the transcript shows that, the prompt asks for one message on each line,
and the program makes one message from each line.
