from app.rag.citation import extract_citation_numbers, normalize_citations


def test_extract_citation_numbers() -> None:
    assert extract_citation_numbers("A [1] B [2] C [0]") == {1, 2}


def test_normalize_citations_removes_invalid_markers() -> None:
    answer, removed, present = normalize_citations("A [1] B [9] C [abc]", 2)
    assert "[9]" not in answer
    assert removed == 1
    assert present is True
