from fastapi import Request


def direct_action_disabled(request: Request, settings) -> tuple[bool, int | None]:
    path = request.url.path
    if request.method == "POST" and path == "/vector-index/rebuild":
        return not settings.direct_vector_mutations_enabled, None
    if request.method == "POST" and path.startswith("/documents/") and path.endswith("/index"):
        value = path.split("/")[2]
        return not settings.direct_vector_mutations_enabled, int(value) if value.isdigit() else None
    if request.method == "DELETE" and path.startswith("/documents/"):
        value = path.split("/")[2]
        return not settings.direct_document_delete_enabled, int(value) if value.isdigit() else None
    return False, None
