import re


_STANDALONE_CITATION_PATTERN = re.compile(r"(?<!\!)\[(\d+)\](?!\()")
_PUNCTUATION = ",.;:!?"


def _iter_non_code_matches(answer: str):
    offset = 0
    parts = answer.split("```")
    for index, part in enumerate(parts):
        if index % 2 == 0:
            for match in _STANDALONE_CITATION_PATTERN.finditer(part):
                yield offset + match.start(), offset + match.end(), match
        offset += len(part)
        if index < len(parts) - 1:
            offset += 3


def extract_citation_numbers(answer: str) -> set[int]:
    return {int(match.group(1)) for _, _, match in _iter_non_code_matches(answer) if int(match.group(1)) > 0}


def _normalize_non_code_segment(text: str) -> str:
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text


def _preserve_multiline_formatting(text: str) -> str:
    parts = text.split("```")
    for index in range(0, len(parts), 2):
        parts[index] = _normalize_non_code_segment(parts[index])
    return "```".join(parts)


def normalize_citations(answer: str, max_source_number: int) -> tuple[str, int, bool]:
    removed = 0
    citations_present = False

    normalized_parts: list[str] = []
    last_end = 0

    for start, end, match in _iter_non_code_matches(answer):
        normalized_parts.append(answer[last_end:start])
        number = int(match.group(1))
        if 1 <= number <= max_source_number:
            citations_present = True
            normalized_parts.append(match.group(0))
        else:
            removed += 1
            next_char = answer[end : end + 1]
            if next_char and next_char[0] in _PUNCTUATION and normalized_parts:
                normalized_parts[-1] = normalized_parts[-1].rstrip(" \t")
        last_end = end

    normalized_parts.append(answer[last_end:])
    normalized = "".join(normalized_parts)
    normalized = _preserve_multiline_formatting(normalized).strip()
    return normalized, removed, citations_present
