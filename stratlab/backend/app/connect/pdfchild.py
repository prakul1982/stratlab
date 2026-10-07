"""Runs in a child process only (pdfsandbox.py starts it): reads one statement PDF with casparser and prints the result as
one JSON line. It imports nothing from the app and sees none of the server's environment, so a PDF that tries to use
all the memory, or all the time, stops this process and nothing else.

stdin: a first line {"pw": "<password>"}, then the PDF's bytes. stdout: {"ok": "<casparser's JSON>"} or {"err": "<kind>"}."""
import io
import json
import sys


def main() -> None:
    pw = json.loads(sys.stdin.buffer.readline() or b"{}").get("pw") or ""
    data = sys.stdin.buffer.read()
    try:
        import casparser
        from casparser.exceptions import CASParseError, IncorrectPasswordError
        res = {"ok": casparser.read_cas_pdf(io.BytesIO(data), pw, output="json")}
    except MemoryError:
        res = {"err": "limit"}
    except Exception as e:                                  # the class name only: a message can carry the file's text
        name = type(e).__name__
        res = {"err": "password" if name == "IncorrectPasswordError" else "parse" if name == "CASParseError" else "other"}
    sys.stdout.write(json.dumps(res))


if __name__ == "__main__":
    main()
