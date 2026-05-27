import argparse
import os
from pathlib import Path

from .scraper import run


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="canvas-download",
        description="Download all files from your Canvas LMS courses.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("CANVAS_URL"),
        help="Canvas instance URL (e.g. https://canvas.example.edu). "
        "Can also be set via the CANVAS_URL environment variable.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("downloads"),
        help="Directory to save downloaded files (default: ./downloads)",
    )
    args = parser.parse_args()

    if not args.url:
        parser.error("Canvas URL is required. Pass --url or set CANVAS_URL.")

    base_url = args.url.rstrip("/")
    run(base_url, args.output)
