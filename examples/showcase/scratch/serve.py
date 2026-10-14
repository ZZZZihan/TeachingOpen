"""Local verification only: serve the unmodified project Scratch player and files."""
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import argparse

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parents[2] / "web" / "public"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def translate_path(self, path):
        clean = unquote(urlsplit(path).path)
        if clean.startswith("/showcase/"):
            target = (ROOT / clean[len("/showcase/"):]).resolve()
            if target.is_relative_to(ROOT):
                return str(target)
            return str(ROOT / ".not-found")
        return super().translate_path(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18146)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
