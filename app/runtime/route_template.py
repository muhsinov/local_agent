from fastapi import Request


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if template:
        return str(template)
    path = request.url.path
    if path.startswith("/documents/"):
        suffix = path[len("/documents/") :].split("/", 1)
        if suffix and suffix[0].isdigit():
            return "/documents/{document_id}" + (f"/{suffix[1]}" if len(suffix) > 1 and suffix[1] in {"text", "index"} else "")
    if path.startswith("/approvals/"):
        suffix = path[len("/approvals/") :].split("/", 1)
        return f"/approvals/{{approval_id}}" + (f"/{suffix[1]}" if len(suffix) > 1 else "")
    return path if path in {"/", "/chat", "/health", "/live", "/ready", "/vector-index/rebuild", "/vector-index/status", "/vector-search", "/documents/upload", "/session/bootstrap"} else "<local-route>"
