"""The command line of mimikr.

- `mimikr` or `mimikr gui`: open the window.
- `mimikr check`: load each identity and show what the program found.
- `mimikr eval <identity>`: score how near the replies of the model are to the
  real replies of the person.
"""

import argparse
import json
import re
import sys
from datetime import datetime

from mimikr.config import Config, embedding_base_url, load_config
from mimikr.evaluate import STYLE_FEATURES, EvaluationError, Report, run_evaluation
from mimikr.identity import list_identities
from mimikr.llm import ChatClient, LLMError


def check(config) -> int:
    identities, errors = list_identities(config.identities_dir)
    if not identities and not errors:
        print(f"No identities found in {config.identities_dir}/.")
        print("Make a directory for each identity, with a personality.md file in it.")
        return 1
    for identity in identities.values():
        print(f"{identity.id} ({identity.display_name})")
        if identity.speaker:
            print(f"  chat.md: {identity.style.message_count} messages from '{identity.speaker}'")
            for line in identity.style.describe():
                print(f"  - {line}")
        else:
            print("  chat.md: none")
    for name, error in errors.items():
        print(f"{name}: ERROR: {error}")
    return 1 if errors else 0


# Below this number of test replies, the report warns that the score is not reliable.
FEW_CASES = 10


def print_report(report: Report, show: bool) -> None:
    print(f"{report.identity}, model {report.model}, temperature {report.temperature}, {report.mode} mode, {report.examples} examples")
    count = len(report.results)
    print(f"{count} test {'reply' if count == 1 else 'replies'}, {report.training_messages} training messages")
    if count < FEW_CASES:
        print(f"Warning: a score from fewer than {FEW_CASES} test replies is not reliable.")
    print()
    print(f"style    {report.style.score:.2f}")
    print(f"  {'feature':<20}{'real':>8}{'model':>8}")
    for name in STYLE_FEATURES:
        real, generated = report.style.features[name]
        print(f"  {name:<20}{real:>8.2f}{generated:>8.2f}")
    if report.meaning is None:
        print("meaning  not measured")
    else:
        baseline = "none" if report.meaning.baseline is None else f"{report.meaning.baseline:.2f}"
        print(f"meaning  {report.meaning.score:.2f}   (two different real replies: {baseline})")
    if show:
        for result in report.results:
            print()
            for line in result.context:
                print(f"  {line}")
            print(f"  real:  {' / '.join(result.real)}")
            print(f"  model: {' / '.join(result.generated) or '(no reply)'}")


def evaluate(config: Config, name: str, cases: int | None, model: str | None, meaning: bool,
             show: bool, client=None, embed_client=None, examples: str | None = None,
             mode: str | None = None) -> int:
    identities, errors = list_identities(config.identities_dir)
    if name not in identities:
        print(f"mimikr: {errors.get(name) or f'no identity is named {name!r}'}", file=sys.stderr)
        return 1
    identity = identities[name]
    client = client or ChatClient(config.base_url, config.api_key)
    if embed_client is None:
        embed_url = embedding_base_url(config)
        embed_client = client if embed_url == config.base_url else ChatClient(embed_url, config.api_key)
    model = model or identity.model or config.model
    temperature = identity.temperature if identity.temperature is not None else config.temperature

    def embed(texts: list[str]) -> list[list[float]]:
        return embed_client.embed(texts, config.embedding_model)

    started = False

    def progress(number: int, total: int) -> None:
        nonlocal started
        started = True
        print(f"\rcase {number} of {total}", end="", file=sys.stderr, flush=True)

    try:
        report = run_evaluation(identity, client, model, temperature, embed=embed if meaning else None,
                                max_cases=cases, progress=progress, examples=examples or config.examples,
                                example_embed=embed, mode=mode or identity.mode or config.mode)
    except (EvaluationError, LLMError) as error:
        print(f"{chr(10) if started else ''}mimikr: {error}", file=sys.stderr)
        return 1
    print(file=sys.stderr)
    print_report(report, show)

    directory = config.data_dir / "evals"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = re.sub(r"[^A-Za-z0-9._-]", "_", f"{model}-{report.mode}-{report.examples}")
    path = directory / f"{identity.id}-{label}-{stamp}.json"
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved to {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mimikr")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="open the window (the default)")
    commands.add_parser("check", help="load the identities and show the results")
    eval_parser = commands.add_parser("eval", help="score the replies of the model against the real replies")
    eval_parser.add_argument("identity")
    eval_parser.add_argument("--cases", type=int, help="score only the last N test replies")
    eval_parser.add_argument("--model", help="use this model and not the one in the settings")
    eval_parser.add_argument("--mode", choices=("chat", "continue"),
                             help="how the model writes, in place of the setting")
    eval_parser.add_argument("--examples", choices=("recent", "similar"),
                             help="how the prompt chooses examples, in place of the setting")
    eval_parser.add_argument("--no-meaning", action="store_true", help="do not use the embedding model")
    eval_parser.add_argument("--show", action="store_true", help="show each real reply and each reply of the model")
    arguments = parser.parse_args(argv)

    config = load_config()
    if arguments.command == "check":
        return check(config)
    if arguments.command == "eval":
        return evaluate(config, arguments.identity, arguments.cases, arguments.model,
                        meaning=not arguments.no_meaning, show=arguments.show, examples=arguments.examples,
                        mode=arguments.mode)
    from mimikr.gui import run

    return run(config)


if __name__ == "__main__":
    sys.exit(main())
