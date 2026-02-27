import re


def parse_reflection_score(response_text: str) -> tuple[int, str]:
    score = 7
    critique = response_text
    score_match = re.search(r"Score:\s*(\d+)", response_text)
    if score_match:
        score = min(10, max(1, int(score_match.group(1))))
    critique_match = re.search(r"Critique:\s*(.*)", response_text, re.DOTALL)
    if critique_match:
        critique = critique_match.group(1).strip()
    return score, critique


def is_quality_sufficient(score: int, threshold: int = 7) -> bool:
    return score >= threshold
