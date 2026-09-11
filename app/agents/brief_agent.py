"""Interpret structured user briefs before content and design agents run.

The interpreter is intentionally deterministic.  It extracts explicit slide
contracts from a prompt even when an external model is unavailable, so a
provider outage cannot turn a carefully authored brief into generic slides.
"""
from __future__ import annotations

import re
import json
from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.presentation import LayoutType, SlideElement, SlideSpec


_LAYOUTS={
    "title slide": LayoutType.title_slide,
    "feature grid": LayoutType.feature_grid,
    "step workflow": LayoutType.step_workflow,
    "architecture layers": LayoutType.architecture_layers,
    "process flow": LayoutType.process_flow,
    "comparison": LayoutType.comparison,
    "two column": LayoutType.two_column,
    "key metrics": LayoutType.key_metrics,
    "dashboard": LayoutType.dashboard,
    "summary": LayoutType.summary,
    "timeline": LayoutType.timeline,
}


class BriefSlide(BaseModel):
    slide_number: int
    title: str
    subtitle: str | None = None
    layout_type: LayoutType
    requirements: list[str] = Field(default_factory=list)
    elements: list[SlideElement] = Field(default_factory=list)
    chart_data: dict | None = None

    def seed(self) -> SlideSpec:
        elements=[element.model_copy(deep=True) for element in self.elements]
        if not elements:
            for item in self.requirements:
                heading, separator, detail=item.partition(" (")
                body=detail.rstrip("). ") if separator else f"Explain {heading.strip()} in practical terms."
                elements.append(SlideElement(type="card", heading=heading.strip(), body=body))
        purpose=(f"Explain {self.title} through the requested technical details."
                 if elements else f"Introduce {self.title}.")
        return SlideSpec(
            slide_number=self.slide_number, title=self.title, subtitle=self.subtitle,
            purpose=purpose, layout_type=self.layout_type, elements=elements,
            visual_spec={"brief_locked": True, "brief_requirements": self.requirements, **({"chart_data":self.chart_data} if self.chart_data else {})},
            metadata={"brief_layout_locked": True},
        )

class SlideConstraint(BaseModel):
    """A partial contract from prose that does not name every slide."""
    slide_number: int
    layout_type: LayoutType | None = None
    requirements: list[str] = Field(default_factory=list)
    exact_element_count: int | None = None


class PresentationBrief(BaseModel):
    slides: list[BriefSlide] = Field(default_factory=list)
    constraints: list[SlideConstraint] = Field(default_factory=list)
    deck_title: str | None = None
    requested_slide_count: int | None = None

    @property
    def is_structured(self) -> bool:
        return bool(self.slides or self.constraints)

    def by_number(self, number: int) -> BriefSlide | None:
        return next((slide for slide in self.slides if slide.slide_number == number), None)

    def constraint_for_slide(self, number: int) -> SlideConstraint | None:
        return next((constraint for constraint in self.constraints if constraint.slide_number == number), None)


class PromptClassification(BaseModel):
    mode: Literal["structured", "open_ended"]
    reason: str
    detected_slide_numbers: list[int] = Field(default_factory=list)


class BriefInterpreterAgent:
    """Extract `Slide N:` contracts and their requested content from a prompt."""

    @staticmethod
    def _normalize_markdown(prompt: str) -> str:
        """Make ordinary Markdown briefs look like the plain-text contract grammar."""
        lines=[]
        for raw in prompt.splitlines():
            line=raw.strip().replace("**", "").replace("__", "")
            line=re.sub(r"^(?:[-*•]\s*)", "", line)
            lines.append(line)
        return "\n".join(lines)

    def classify(self, prompt: str) -> PromptClassification:
        normalized=self._normalize_markdown(prompt)
        numbers=[int(number) for number in re.findall(r"(?im)^\s*slide\s+(\d+)\s*:", normalized)]
        fields=re.findall(r"(?im)^\s*(?:title|subtitle|layout|topic areas|steps to cover|tiers to cover|key outcomes)\s*:", normalized)
        if '"slides"' in prompt and '"slide_number"' in prompt:
            return PromptClassification(
                mode="structured",
                reason="Detected an embedded JSON slide specification with explicit slide numbers and layouts.",
                detected_slide_numbers=[int(number) for number in re.findall(r'"slide_number"\s*:\s*(\d+)', prompt)],
            )
        if numbers and (fields or len(numbers) >= 2):
            return PromptClassification(
                mode="structured",
                reason="Detected numbered slide contracts with explicit title, layout, or content requirements.",
                detected_slide_numbers=numbers,
            )
        constraint_count=re.search(r"\b(?:exactly|spanning)\s+(\d+)\s+slides?\b", normalized, re.I)
        has_narrative_constraints=bool(re.search(r"\b(?:timeline|finish\s+with|concepts?\s*\(|must\s+include)\b", normalized, re.I))
        if constraint_count and has_narrative_constraints:
            return PromptClassification(
                mode="structured",
                reason="Detected an exact slide count with narrative and content constraints.",
                detected_slide_numbers=list(range(1, int(constraint_count.group(1))+1)),
            )
        return PromptClassification(
            mode="open_ended",
            reason="No complete slide-by-slide contract was supplied; the storyline and design agents may plan the deck.",
        )

    @staticmethod
    def _embedded_json(prompt: str) -> dict | None:
        """Find the first balanced JSON object that declares a slides array."""
        start=prompt.find("{")
        while start >= 0:
            depth=0; in_string=False; escaped=False
            for end, char in enumerate(prompt[start:], start=start):
                if in_string:
                    if escaped: escaped=False
                    elif char == "\\": escaped=True
                    elif char == '"': in_string=False
                    continue
                if char == '"': in_string=True
                elif char == "{": depth+=1
                elif char == "}":
                    depth-=1
                    if depth == 0:
                        try:
                            candidate=json.loads(prompt[start:end+1])
                            if isinstance(candidate, dict) and isinstance(candidate.get("slides"), list):
                                return candidate
                        except json.JSONDecodeError:
                            pass
                        break
            start=prompt.find("{", start+1)
        return None

    @staticmethod
    def _lines_after(section: str, marker: str) -> list[str]:
        match=re.search(rf"(?im)^\s*{re.escape(marker)}\s*:\s*(.*)$", section)
        if not match:
            return []
        tail=section[match.end():]
        # Stop at the next labelled field, while retaining ordinary plain-text
        # item lines such as "Alert Ingestion (...)".
        tail=re.split(r"(?im)^\s*(?:Title|Subtitle|Layout|Topic Areas|Steps to cover|Tiers to cover|Key Outcomes)\s*:", tail, maxsplit=1)[0]
        first=re.sub(r"^\d+[.)]\s*", "", match.group(1).strip())
        lines=([first] if first else []) + [re.sub(r"^\d+[.)]\s*", "", line.strip(" -•\t")) for line in tail.splitlines() if line.strip()]
        return [line for line in lines if line and not line.lower().startswith(("ensure ", "please "))]

    def interpret(self, prompt: str, requested_count: int) -> PresentationBrief:
        if self.classify(prompt).mode != "structured":
            return PresentationBrief()
        payload=self._embedded_json(prompt)
        if payload:
            slides=[]
            for raw in payload.get("slides", []):
                try:
                    number=int(raw["slide_number"])
                    layout=LayoutType(raw["layout_type"])
                except (KeyError, TypeError, ValueError):
                    continue
                raw_elements=[]
                for element in raw.get("elements", []):
                    if not isinstance(element, dict):
                        continue
                    raw_elements.append(SlideElement.model_validate({
                        **element, "type":element.get("type", "card"),
                        "body":element.get("body") or element.get("subtext"),
                    }))
                requirements=[item.heading or item.label or "" for item in raw_elements if item.heading or item.label]
                slides.append(BriefSlide(
                    slide_number=number, title=str(raw.get("title") or f"Slide {number}"),
                    subtitle=raw.get("subtitle"), layout_type=layout,
                    requirements=requirements, elements=raw_elements,
                    chart_data=raw.get("chart_data") or (raw.get("visual_spec") or {}).get("chart_data"),
                ))
            if slides:
                return PresentationBrief(slides=slides, deck_title=payload.get("title"))
        normalized=self._normalize_markdown(prompt)
        sections=list(re.finditer(r"(?im)^\s*slide\s+(\d+)\s*:\s*([^\n]+)", normalized))
        slides=[]
        for index, match in enumerate(sections):
            number=int(match.group(1))
            # The numbered contract, not the Streamlit slider's default,
            # determines deck length. This lets a user paste a complete
            # ten-slide brief while the sidebar still shows its six-slide
            # default. Keep the public API's documented maximum of ten.
            if number < 1 or number > 10:
                continue
            section=normalized[match.end():sections[index+1].start() if index+1 < len(sections) else len(normalized)]
            layout_text=(self._lines_after(section, "Layout") or [match.group(2).strip()])[0].lower()
            layout=next((value for phrase, value in _LAYOUTS.items() if phrase in layout_text), LayoutType.feature_grid)
            title=(self._lines_after(section, "Title") or [match.group(2).strip()])[0]
            subtitle_values=self._lines_after(section, "Subtitle")
            requirements=[]
            for marker in ("Topic Areas", "Steps to cover", "Tiers to cover", "Key Outcomes"):
                requirements.extend(self._lines_after(section, marker))
            slides.append(BriefSlide(slide_number=number, title=title, subtitle=subtitle_values[0] if subtitle_values else None, layout_type=layout, requirements=requirements))
        if slides:
            return PresentationBrief(slides=slides)

        # Some strong briefs describe a sequence in prose rather than naming
        # every "Slide N". Convert only the hard placement/content constraints
        # into a partial contract and leave the remaining story to the model.
        count_match=re.search(r"\b(?:exactly|spanning)\s+(\d+)\s+slides?\b", normalized, re.I)
        if not count_match:
            return PresentationBrief()
        count=int(count_match.group(1))
        if not 3 <= count <= 10:
            return PresentationBrief()
        constraints=[]
        timeline=re.search(r"(?:timeline|historical timeline)\s*\(([^)]+)\)", normalized, re.I)
        if timeline:
            constraints.append(SlideConstraint(
                slide_number=2, layout_type=LayoutType.timeline,
                requirements=[f"Historical timeline covering {timeline.group(1).strip()}"],
            ))
        concepts=re.search(r"(\d+)\s+(?:complex\s+)?concepts?\s*\(([^)]+)\)", normalized, re.I)
        if concepts:
            names=[name.strip() for name in concepts.group(2).split(",") if name.strip()]
            if names:
                constraints.append(SlideConstraint(
                    slide_number=max(3,count-3), layout_type=LayoutType.feature_grid,
                    requirements=names, exact_element_count=min(int(concepts.group(1)),len(names)),
                ))
        future=re.search(r"finish\s+with\s+(?:a\s+slide\s+)?(?:detailing|showing)\s+(\d+)\s+distinct\s+([^.!\n]+)", normalized, re.I)
        if future:
            constraints.append(SlideConstraint(
                slide_number=count, layout_type=LayoutType.feature_grid,
                requirements=[future.group(2).strip()], exact_element_count=int(future.group(1)),
            ))
        return PresentationBrief(constraints=constraints, requested_slide_count=count) if constraints else PresentationBrief()
