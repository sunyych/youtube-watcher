#!/usr/bin/env python3
"""
Read user feedback JSON from the feedback directory and run Cursor CLI to apply changes.

Usage:
  python scripts/apply_feedback.py [feedback_id]
  FEEDBACK_DIR=/path/to/feedback python scripts/apply_feedback.py

If feedback_id is omitted, processes all .json files in FEEDBACK_DIR (default: ./data/feedback).
Each feedback is passed to Cursor agent as a prompt to modify the project accordingly.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def get_feedback_dir() -> Path:
    return Path(os.environ.get("FEEDBACK_DIR", "./data/feedback")).resolve()


def load_feedback(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not load {path}: {e}", file=sys.stderr)
        return None


def build_prompt(data: dict, feedback_dir: Path) -> str:
    page = data.get("page", "")
    display = data.get("display_description") or ""
    comment = data.get("comment", "")
    screenshot_path = data.get("screenshot_path")
    username = data.get("username", "")
    created_at = data.get("created_at", "")

    lines = [
        "Apply the following user feedback to the project.",
        "",
        f"Page: {page}",
        f"User: {username}",
        f"Submitted: {created_at}",
        "",
    ]
    if display:
        lines.append(f"What they see: {display}")
        lines.append("")
    lines.append(f"Feedback / change request: {comment}")
    if screenshot_path:
        full_path = feedback_dir / screenshot_path
        if full_path.exists():
            lines.append("")
            lines.append(f"A screenshot was attached: {full_path}")
            lines.append("Refer to it if helpful for UI/context.")
    return "\n".join(lines)


def run_cursor_agent(prompt: str) -> bool:
    """Run Cursor CLI agent with the given prompt. Returns True on success."""
    cmd = ["cursor", "agent", "-p", "--force", prompt]
    try:
        result = subprocess.run(cmd, cwd=Path.cwd())
        return result.returncode == 0
    except FileNotFoundError:
        print("Error: 'cursor' CLI not found. Install Cursor and ensure 'cursor' is on PATH.", file=sys.stderr)
        return False


def main() -> int:
    feedback_dir = get_feedback_dir()
    if not feedback_dir.exists():
        print(f"Feedback directory does not exist: {feedback_dir}", file=sys.stderr)
        return 1

    feedback_id = sys.argv[1].strip() if len(sys.argv) > 1 else None

    if feedback_id:
        json_path = feedback_dir / f"{feedback_id}.json"
        if not json_path.exists():
            print(f"Feedback not found: {feedback_id}", file=sys.stderr)
            return 1
        files = [json_path]
    else:
        files = sorted(feedback_dir.glob("*.json"))

    if not files:
        print("No feedback JSON files found.", file=sys.stderr)
        return 0

    for json_path in files:
        data = load_feedback(json_path)
        if not data:
            continue
        prompt = build_prompt(data, feedback_dir)
        print(f"Applying feedback from {json_path.name}...", file=sys.stderr)
        if not run_cursor_agent(prompt):
            print(f"Cursor agent failed for {json_path.name}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
