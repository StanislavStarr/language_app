import argparse
import gzip
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError
from wordfreq import top_n_list, word_frequency

from scripts.wiktextract_stats import Collected, Entry, collect_entry
from scripts.wiktextract_summary import summarize

DEFAULT_INPUT = Path("data/kaikki/kaikki.org-dictionary-English.jsonl")
DEFAULT_OUTPUT = Path("data/kaikki/exploration-stats.json")
TOP_NS = (30_000, 60_000, 100_000)
PROGRESS_EVERY = 200_000
ENGLISH_MARKER = '"lang_code": "en"'


def open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def read_lines(path: Path, max_lines: int | None) -> Iterator[str]:
    with open_text(path) as source:
        for index, line in enumerate(source):
            if max_lines is not None and index >= max_lines:
                return
            yield line


def build_ranks(top_n: int) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for rank, word in enumerate(top_n_list("en", top_n), start=1):
        ranks.setdefault(word.lower(), rank)
    return ranks


def explore(path: Path, max_lines: int | None = None, progress: bool = False) -> Collected:
    collected = Collected(ranks=build_ranks(max(TOP_NS)))
    for line in read_lines(path, max_lines):
        if ENGLISH_MARKER not in line:
            collected.entries += 1
            collected.other_language_entries += 1
            continue
        try:
            entry = Entry.model_validate_json(line)
        except ValidationError:
            collected.invalid_entries += 1
            continue
        collect_entry(collected, entry)
        if progress and collected.entries % PROGRESS_EVERY == 0:
            sys.stderr.write(f"{collected.entries} entries read\n")
    return collected


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure Wiktextract coverage for lexicon import")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-lines", type=int, default=None)
    arguments = parser.parse_args()
    collected = explore(arguments.input, arguments.max_lines, progress=True)
    frequencies = {word: word_frequency(word, "en") for word in collected.ranks}
    summary = summarize(collected, TOP_NS, frequencies)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.stdout.write(f"written {arguments.output}\n")


if __name__ == "__main__":
    main()
