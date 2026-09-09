"""Slide-fit QA that recomposes copy instead of clipping it."""
from __future__ import annotations
import re
from app.schemas.presentation import LayoutType, PresentationSpec

_PLANNING_COPY = (
    "set the decision context", "set context", "story intent", "develop this story beat",
    "frame the outcome", "frame why this topic", "introduce the central question",
    "land on a memorable recommendation", "explain the importance of choosing",
)
_TRAILING_CONNECTORS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "vs", "with"}


def comparison_cover_title(topic: str) -> str | None:
    """Derive a complete, neutral cover title from a comparison request.

    A cover must never depend on the model completing both halves of a
    comparison.  For example, a response of ``NSDL vs.`` is syntactically
    incomplete but can otherwise pass every text-length check.
    """
    text=re.sub(r"\s+", " ", (topic or "")).strip()
    # Use the first comparison sentence only.  Subsequent questions such as
    # "Which should I choose and why?" belong in the supporting copy.
    first=re.split(r"[.?!]", text, maxsplit=1)[0].strip()
    explicit_compare=bool(re.match(r"^(?:please\s+)?(?:compare|comparison\s+of)\s+", first, flags=re.I))
    first=re.sub(r"^(?:please\s+)?(?:compare|comparison\s+of)\s+", "", first, flags=re.I)
    # An ordinary request can contain "and" (for example, "product and
    # technical overview"). Treat it as comparison syntax only after an
    # explicit Compare/Comparison request.
    separator=r"(?:vs\.?|versus|and)" if explicit_compare else r"(?:vs\.?|versus)"
    match=re.match(rf"^(.+?)\s+{separator}\s+(.+?)$", first, flags=re.I)
    if not match:
        return None
    left, right=(part.strip(" ,:;-") for part in match.groups())
    # Prompts are often written as one sentence, for example "NSDL vs CDSL
    # which should I choose?".  Keep the compared entities on the cover and
    # leave the decision question for the subtitle instead of putting it in a
    # circle or an overlong title.
    right=re.split(r"\s+(?=(?:which|what|who|when|where|why|how)\b)", right, maxsplit=1, flags=re.I)[0].strip(" ,:;-")
    if not left or not right:
        return None
    return f"{left} vs. {right}"

def summarize_point(value: str, max_words: int) -> str:
    """Keep one complete relevant point; never emit an ellipsis-cut string."""
    text=re.sub(r"\s+", " ", (value or "").replace("\\n", " ").replace("\n", " ")).strip(" •")
    if not text: return ""
    sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    candidate=next((s for s in sentences if len(s.split())<=max_words), sentences[0] if sentences else text)
    if len(candidate.split())<=max_words: return candidate
    clauses=[c.strip() for c in re.split(r"[,;:]\s*", candidate) if c.strip()]
    kept=[]
    for clause in clauses:
        if len((" ".join(kept+[clause])).split())<=max_words: kept.append(clause)
    if kept: return ", ".join(kept).rstrip(". ")+"."
    words=candidate.split()[:max_words]
    # Never turn a long sentence into a visibly unfinished phrase such as
    # "the importance of choosing the.".  A later QA fallback can replace
    # generic planning language with an actual slide fact.
    while words and words[-1].lower().rstrip(".,:;?!") in _TRAILING_CONNECTORS:
        words.pop()
    return " ".join(words).rstrip(". ")+"." if words else ""

def _is_unusable_lead(value: str) -> bool:
    text=(value or "").strip().lower()
    if not text or any(phrase in text for phrase in _PLANNING_COPY):
        return True
    last=text.rstrip(".?! ").split(" ")[-1] if text else ""
    return last in _TRAILING_CONNECTORS

def _fact_based_lead(slide) -> str:
    """Use visible content, never private agent instructions, as a fallback lead."""
    for element in slide.elements:
        body=(element.body or element.subtext or element.value or "").strip()
        if body:
            return summarize_point(body, 13)
    heading=next((item.heading or item.label for item in slide.elements if item.heading or item.label), "")
    return summarize_point(heading or slide.title, 13)

class PresentationQAAgent:
    def validate_and_recompose(self, spec: PresentationSpec) -> dict:
        issues=[]
        for slide in spec.slides:
            if slide.layout_type == LayoutType.title_slide:
                # Preserve the complete comparison named in the user request;
                # it is the deck's essential promise, not optional filler.
                derived_title=comparison_cover_title(spec.topic)
                if derived_title:
                    if slide.title != derived_title:
                        issues.append(f"Slide {slide.slide_number}: restored complete comparison title")
                    slide.title=derived_title
                else:
                    slide.title=summarize_point(slide.title, 10)
            else:
                slide.title=summarize_point(slide.title, 8)
            if slide.subtitle: slide.subtitle=summarize_point(slide.subtitle,18)
            # Purpose is rendered as the lead statement in several layouts.
            # It must have its own budget, otherwise a model can place a
            # paragraph in a box intended for one or two lines.
            if slide.layout_type == LayoutType.summary:
                purpose_budget=8
            elif slide.visual_spec.get("image_path") or slide.layout_type == LayoutType.content_with_visual:
                purpose_budget=13
            else:
                purpose_budget=18
            slide.purpose=summarize_point(slide.purpose, purpose_budget)
            if _is_unusable_lead(slide.purpose):
                replacement=_fact_based_lead(slide)
                if replacement:
                    slide.purpose=replacement
                    issues.append(f"Slide {slide.slide_number}: replaced internal planning copy with a slide fact")
            locked=bool(slide.metadata.get("brief_layout_locked"))
            if not locked and slide.layout_type in {LayoutType.step_workflow,LayoutType.process_flow,LayoutType.timeline} and len(slide.elements)>3:
                slide.layout_type=LayoutType.feature_grid; issues.append(f"Slide {slide.slide_number}: converted dense flow to a readable grid")
            budget=16 if slide.layout_type in {LayoutType.feature_grid,LayoutType.comparison,LayoutType.two_column} else 13
            max_elements=2 if slide.layout_type==LayoutType.two_column else (4 if locked else 3)
            if len(slide.elements)>max_elements:
                slide.elements=slide.elements[:max_elements]; issues.append(f"Slide {slide.slide_number}: reduced to {max_elements} decision points")
            for element in slide.elements:
                if element.heading: element.heading=summarize_point(element.heading,6)
                if element.label: element.label=summarize_point(element.label,6)
                if element.body: element.body=summarize_point(element.body,budget)
                if element.subtext: element.subtext=summarize_point(element.subtext,budget)
        spec.title=summarize_point(spec.title,8)
        return {"passed":True,"score":100 if not issues else 92,"issues":issues,"policy":"Complete decision-relevant sentences replace clipped copy."}
