import re


_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def extract_citation_numbers(answer: str) -> set[int]:
    return {int(match.group(1)) for match in _CITATION_PATTERN.finditer(answer) if int(match.group(1)) > 0}


def normalize_citations(answer: str, max_source_number: int) -> tuple[str, int, bool]:
    removed = 0
    citations_present = False

    def replace(match: re.Match[str]) -> str:
        nonlocal removed, citations_present
        number = int(match.group(1))
        if 1 <= number <= max_source_number:
            citations_present = True
            return match.group(0)
        removed += 1
        return ""

    normalized = _CITATION_PATTERN.sub(replace, answer)
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    return normalized, removed, citations_present
