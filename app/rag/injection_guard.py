from dataclasses import dataclass


@dataclass(frozen=True)
class InjectionAssessment:
    suspicious: bool
    matched_categories: tuple[str, ...]


def assess_injection_risk(text: str) -> InjectionAssessment:
    lowered = text.lower()
    categories: list[str] = []
    if "ignore previous instructions" in lowered or "forget previous instructions" in lowered:
        categories.append("instruction_override")
    if "system prompt" in lowered:
        categories.append("system_prompt_request")
    if "run shell" in lowered or "execute command" in lowered or "bash" in lowered:
        categories.append("tool_execution")
    if "reveal secrets" in lowered or "api key" in lowered or "password" in lowered:
        categories.append("secret_exfiltration")
    return InjectionAssessment(suspicious=bool(categories), matched_categories=tuple(categories))
