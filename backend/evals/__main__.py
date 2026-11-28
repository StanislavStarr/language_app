import argparse
import asyncio
import sys

from app.integrations.ai.provider import AIError

from evals.runner import SUITE_NAMES, run_with_settings


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        message = "must be at least 1"
        raise argparse.ArgumentTypeError(message)
    return number


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evals")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run an eval suite against the real API (costs money)")
    run.add_argument("suite", choices=SUITE_NAMES)
    run.add_argument("--limit", type=positive_int, default=None, help="use only the first N cases")
    return parser.parse_args(arguments)


def main() -> None:
    arguments = parse_arguments(sys.argv[1:])
    try:
        path = asyncio.run(run_with_settings(arguments.suite, arguments.limit))
    except AIError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(2) from error
    sys.stdout.write(f"report: {path}\n")


if __name__ == "__main__":
    main()
