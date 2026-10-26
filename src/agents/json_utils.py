"""Forgiving extraction of a JSON array of objects from LLM text."""
import json
import re

_ARRAY_START = re.compile(r"\[\s*\{")


def extract_json_objects(text: str) -> list[dict]:
    """Return the objects of the first JSON array in `text`.

    Tolerates markdown fences and chatty preambles, and salvages the complete objects
    when the output was cut off mid-array (e.g. by the max-token cap).
    """
    match = _ARRAY_START.search(text)
    if not match:
        return []
    decoder = json.JSONDecoder()
    objects: list[dict] = []
    i = match.start() + 1
    while i < len(text):
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i >= len(text) or text[i] != "{":
            break
        try:
            obj, i = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            break  # truncated final object: keep what we have
        if isinstance(obj, dict):
            objects.append(obj)
    return objects
