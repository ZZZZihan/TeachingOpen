#!/usr/bin/env python3
"""Extract upstream table definitions without importing users or business data."""
import argparse
from pathlib import Path
import re


def extract_schema(source: str) -> str:
    tables = []
    for match in re.finditer(r"^CREATE TABLE `([A-Za-z0-9_]+)` \(", source, re.MULTILINE):
        quote = None
        pos = match.end()
        while pos < len(source):
            char = source[pos]
            if quote:
                if char == "\\":
                    pos += 2
                    continue
                if char == quote:
                    if pos + 1 < len(source) and source[pos + 1] == quote:
                        pos += 2
                        continue
                    quote = None
            elif char in "'\"`":
                quote = char
            elif char == ";":
                tables.append((match.group(1), source[match.start():pos + 1]))
                break
            pos += 1
        else:
            raise ValueError(f"Unterminated table definition: {match.group(1)}")
    if not tables or len({name for name, _ in tables}) != len(tables):
        raise ValueError("Missing or duplicate table definitions")
    statements = ["SET NAMES utf8mb4;", "SET FOREIGN_KEY_CHECKS=0;"]
    statements.extend(definition for _, definition in tables)
    statements.append("SET FOREIGN_KEY_CHECKS=1;")
    return "\n\n".join(statements) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "db/teachingopen2.8.sql")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    schema = extract_schema(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Do not silently replace an existing schema or any runtime data.
    with args.output.open("x", encoding="utf-8") as out:
        out.write(schema)
    print(f"Extracted {len(re.findall(r'^CREATE TABLE', schema, re.MULTILINE))} empty tables into {args.output}")
