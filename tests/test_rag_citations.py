from app.rag.citation import extract_citation_numbers, normalize_citations


def test_extract_citation_numbers() -> None:
    assert extract_citation_numbers("A [1] B [2] C [0]") == {1, 2}


def test_normalize_citations_removes_invalid_markers() -> None:
    answer, removed, present = normalize_citations("A [1] B [9] C [abc]", 2)
    assert "[9]" not in answer
    assert removed == 1
    assert present is True


def test_markdown_link_and_image_label_are_not_citations() -> None:
    text = "Docs [1](https://example.com) and ![1](image.png) plus [2]"
    assert extract_citation_numbers(text) == {2}


def test_normalize_citations_preserves_markdown_links() -> None:
    answer, removed, present = normalize_citations("See [1](https://example.com) and [9].", 2)
    assert "[1](https://example.com)" in answer
    assert "[9]" not in answer
    assert removed == 1
    assert present is False


def test_normalize_citations_preserves_multiline_formatting() -> None:
    answer, removed, _ = normalize_citations("- first\n- second [9]\n\n```txt\nx = [9]\n```", 1)
    assert answer == "- first\n- second\n\n```txt\nx = [9]\n```"
    assert removed == 1
