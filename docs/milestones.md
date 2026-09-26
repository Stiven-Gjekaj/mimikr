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

### One model: Mistral Nemo 12B Instruct

The user chose to download no model other than Mistral Nemo 12B Instruct, at
Q4_K_M, and nomic-embed-text for the embeddings. P4 thus compares the modes and
the examples, and not models.

Mistral Nemo won the choice before any score. It holds the voice of a character
well, it fits in 16 GB at Q4_K_M, and the transcripts are English only.

- **A bake-off of Llama 3.1 8B, Qwen3 8B and Mistral Nemo** lost. The user
  chose not to download them.
- **A base model for the continuation mode** lost, for the same reason. The
  continuation mode runs on the instruct model. It then has part of the voice
  of an assistant, and the score measures how much.

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

### A style sheet of our own, from a few colors

The window draws its own look, in light and dark, from one set of color tokens
in `theme.py`. The system theme chooses light or dark, unless the settings
choose one. The accent is a named color or any `#rrggbb` color. The text on the
accent is white or near black, whichever has more contrast.

A test checks the contrast of the text and of the muted text against the
background in both palettes. Each is 4.5 or more, which WCAG AA asks for.

- **The native look of each system** lost. Qt draws native controls well, but a
  chat window needs round bubbles, avatars and a composer that native controls
  do not have. A mix of native controls and drawn bubbles looked like two
  programs.
- **A QML interface** lost. It makes animation easy, but it is a second
  language and a second way to test. The widgets of Qt do the job.

### Settings in the window

The settings page writes `mimikr.toml`, the same file that a person can edit.
A change of the look shows at once, and **Revert** takes it back. A change of
the servers takes effect at **Save**, when the window makes new clients.

**Test connection** checks the values in the fields, before the save. It asks
the chat server for `/v1/models`, and the embedding server for one embedding,
because those two requests show that each server answers with the model that
mimikr will ask for.

The folders of the identities and of the rooms are not on the page. A change
of them needs a new start, and a person who moves the data can edit the file.

### Pictures in data, and not in the identity

A picture that the user chooses goes to `data/avatars/`, as a PNG of 256 by 256
pixels. The window never writes into the directory of an identity, because
[CONTRIBUTING.md](../CONTRIBUTING.md) says that the Software reads those files
only. A person can still put `avatar.png` into that directory by hand, and the
picture in `data` has priority.

- **A path to the picture in identity.toml** lost. The window would then write
  into identity.toml, and a picture outside the project could move and break it.
- **The original image, as it is** lost. A photo can be large, and each avatar
  in each message would read it again. A copy of 256 pixels is small and fast.

### An export that says who wrote it

An export is plain text in the form of `chat.md`. It is easy to paste into any
application, and mimikr can read it again.

The first lines say that a language model wrote the messages of the
identities. They are not an option, because [TERMS.md](../TERMS.md) section 5
asks that nobody shows the output as a message of the real person, and an
export is the easiest way to do that by accident.

- **HTML and PDF** lost. They look better, but a person who shares a chat
  pastes text, and plain text needs no viewer.
- **An export with no header** lost, for the reason above.

### A budget for the room

The prompt holds the most recent messages of the room that fit in 12000
characters, about 3000 tokens. A note says that earlier messages are not shown.
With the examples and the reply, the prompt fits a context of 8192 tokens, and
the local servers get `-c 8192`.

Before this, the prompt held the whole room. A long room would pass the
context of the model, and the server would cut the prompt or refuse it.

- **A summary of the older messages** lost for now. It costs one more call to
  the model for each reply, and a small model can put facts into a summary that
  the room never had.

### Keep the clear habits of the person

With 5 messages or more in the transcript, a reply loses what the person almost
never does: a capital at the start (90 percent or more start small), a period at
the end (5 percent or less end with one), and emoji (none). "I", "I'm" and
words in capitals keep their capitals, and "..." stays.

The setting is on by default. It changes only what the transcript shows to be a
habit, and the style score measures the result.

- **Only the instructions in the prompt** lost. A small model often forgets
  "do not end with a period" by the second sentence.

### The next speaker

A member whose name is in the last message speaks next. Otherwise a random
member speaks, but never the member that spoke last. `turn_taking = "rotate"`
keeps the order of the room.

- **A weight for how much each person talks** lost. The size of a transcript
  says how much of a chat the user exported, and not how much the person talks.

### The menu of a message

Copy, edit, delete, write again, and like. **Write again** removes the whole last
turn of the identity, and not only one message, because the turn was one reply.

A liked reply becomes an example in the later prompts of that identity, with
the message before it, in a budget of 1500 characters. The budget is small on
purpose: the model wrote a liked reply, and too many of them teach the model to
copy itself instead of the person.

### Realistic timing

With the setting on, the text does not show while the model writes, and each
message comes after about the time that a person takes to write it: 0.6 seconds
and 35 milliseconds for each character, 5 seconds at most. The time that the
model took counts. The setting is on by default, because the window is for
conversation. Stop works during a wait.

### Search

Search looks for the text in the names of the rooms, the names of the members,
and the messages, with no case. It reads the room files each time.

- **An index for search** lost. One person has some hundreds of rooms at most,
  and a loop over the files is fast enough.

### An identity editor that writes the files

The editor writes `personality.md`, `identity.toml` and `chat.md`, but only when
the user saves or imports. An import asks which name in the chat is the person,
and asks before it writes over a `chat.md` that exists. It reads the exports of
WhatsApp, Telegram Desktop and DiscordChatExporter, and plain `chat.md` files.

The rule "the Software reads the files of an identity only" changed to "the
Software writes them only for an action of the user". The editor is the reason:
a person who has no terminal must still make an identity.

### llama.cpp from the window

The settings page starts one `llama-server` for the chat model and one for the
embedding model, on 127.0.0.1 only, with a context of 8192 tokens by default.
The output goes to `data/logs/`. mimikr stops the servers when the window
closes. On this Mac, the nomic server answered 13.8 seconds after the start.

### The macOS application

PyInstaller builds `mimikr.app`. The application keeps its settings, identities
and rooms in `~/Documents/mimikr`, because a program that starts from the Dock
has `/` as its working directory. `MIMIKR_HOME` changes the place.

The Qt libraries in the application ask for macOS 13 or later, as their
`LC_BUILD_VERSION` says, so the cask asks for Ventura. The build is for Apple
silicon only.

A tag starts `release.yml`. It builds the application, starts it from the zip,
and opens a draft release. `scripts/homebrew-cask.sh` writes the cask for the
tap, and a person puts it into the tap after reading the draft.

- **Briefcase** lost. It is a good tool, but PyInstaller is the more common one
  for PySide6, and it needs no change to the layout of the project.
- **A signed and notarized application** lost for now. It needs a paid Apple
  certificate. The README says how to take the quarantine mark off.

### CI on three systems

`ci.yml` runs the tests and `mimikr check` on macOS, Linux and Windows. The
window tests need no screen. Linux needs the libraries that Qt loads.

### P4: the score chose the continue mode

The score ran on 26 September 2026 with Mistral Nemo 12B Instruct at Q4_K_M, on
llama.cpp with a context of 8192, and nomic-embed-text v1.5 for the meaning.
Each score holds the last 20 test replies of one person. The five identities
are real people, so the transcripts are not in the repository.

| Mode | Examples | Scores | Style, mean | Style, range | Meaning | Random real reply |
| :-- | :-- | --: | --: | :-- | --: | --: |
| continue | recent | 6 | **0.92** | 0.90 to 0.94 | 0.46 | 0.44 |
| continue | similar | 3 | 0.89 | 0.87 to 0.92 | 0.45 | 0.45 |
| chat | recent | 7 | 0.71 | 0.60 to 0.77 | 0.45 | 0.44 |
| chat | similar | 3 | 0.71 | 0.63 to 0.77 | 0.44 | 0.45 |

What the table says:

- **The continue mode wins on style for each of the five people**, by 0.16 to
  0.33. It is also faster: 63 to 107 seconds for 20 replies, against 226 to 323
  seconds in the chat mode.
- **Similar examples do not help.** Their style is equal or a little lower. In
  the continue mode they take three to five times longer (320 to 344 seconds),
  and in the chat mode a little longer (307 to 321 seconds).
- **The meaning score does not separate the configurations.** Each is within
  0.03 of the score of a random real reply of the same person. What somebody
  says next in a casual chat is mostly not predictable, so the style score is
  the useful one here.

The limits of the run:

- The similar examples have scores for three people only. For the other two,
  the embedding server refused messages longer than its batch of 512 tokens.
  mimikr now cuts a text before it embeds it, and the server that mimikr starts
  has a batch of 2048.
- The second run of each score was stopped after five scores, because the
  first five agreed with the first run to 0.03. Three scores thus have two runs,
  and the others have one.

The decision: `mode = "continue"` is the default. `examples = "recent"` stays
the default.

### Less repetition

The room with the five identities showed the model repeat itself: the same
stock reply three times, and emoji in almost each message. Three changes act on
it, and `mimikr eval` now measures it.

- **Avoid repeats** drops a message that the identity sent in its last six
  messages, or earlier in the same reply. A person does not send the same
  "bet" three times in a row.
- **The emoji of a message** stay at the habit of the person: at most the
  number of emoji that the person puts in 9 of 10 messages with emoji.
- **The frequency and presence penalties** go to the server from the settings.
  They are standard options of the OpenAI API. They are 0 by default, because
  no score has measured another value yet.
- **Repeats** in the report of `mimikr eval` is the share of replies that
  repeat an earlier reply, for the real person and for the model.

### The topic of a room, and the lore of a group

The room also showed the identities cheer for a chapter that they knew nothing
about. A room now has a topic, and the group has `identities/lore.md`, with the
facts that the whole group knows. Both go into the prompt in both modes. The
lore has a budget of 3000 characters.

- **Facts that a model learns from the transcript** lost. A small model mixes
  up the facts of a long transcript, and the person knows the facts better.

### Replies to a message

A message of the user can reply to another message. The prompt shows the
quote, and the author of the quoted message answers first. The identities do
not reply to a message by themselves: a model that points at the wrong message
is worse than a model that points at none.

### Windows and Linux

The release builds the application on macOS, Windows and Linux, with
PyInstaller, and each build must pass `scripts/smoke-test-app.py`: `check`
reads the example identities, and the window runs for 10 seconds. Windows and
Linux get a folder in a zip or a tar.gz, and not an installer.

- **An installer, a Flatpak or an AppImage** lost for now. Each is a second
  way to pack the application, and a folder works on each system.

### What mimikr does not do

These ideas lost, because they are not what the application is for:

- **A game of real or fake**, where a person guesses which reply is real. It
  is a test of the bots, and not a way to talk to them.
- **GIFs and images in the bubbles.** An identity cannot choose a picture that
  it has never seen, and a link that a model makes up shows nothing, or shows
  something that nobody chose.
- **Voice.** mimikr is a chat of text, as the transcripts are.
