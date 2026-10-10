import re
import sys

_ESCAPE = re.compile(
    r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\r\n|.)",
    re.DOTALL,
)
_CODE_POINT_ESCAPES = ("u", "x")
_CHARACTER_ESCAPES = {
    "0": "\0",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\n": "",
    "\r": "",
    "\r\n": "",
    "\u2028": "",
    "\u2029": "",
}


def decoded_javascript_string(written: str) -> str | None:
    body = written[1:-1]

    if written.startswith("`") and "${" in body:
        return None

    code_units = _ESCAPE.sub(_unescaped, body).encode(
        "utf-16-le", "surrogatepass"
    )

    return code_units.decode("utf-16-le", "surrogatepass")


def _unescaped(escape: re.Match[str]) -> str:
    sequence = escape.group(1)

    if len(sequence) > 1 and sequence.startswith(_CODE_POINT_ESCAPES):
        code_point = int(sequence[1:].strip("{}"), 16)

        if code_point > sys.maxunicode:
            return escape.group()

        return chr(code_point)

    return _CHARACTER_ESCAPES.get(sequence, sequence)
