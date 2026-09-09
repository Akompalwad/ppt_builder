"""Interpret structured user briefs before content and design agents run.

The interpreter is intentionally deterministic.  It extracts explicit slide
contracts from a prompt even when an external model is unavailable, so a
provider outage cannot turn a carefully authored brief into generic slides.
"""
from __future__ import annotations

import re
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
    "summary": LayoutType.summary,
    "timeline": LayoutType.timeline,
}


class BriefSlide(BaseModel):
    slide_number: int
    title: str
    subtitle: str | None = None
    layout_type: LayoutType
    requirements: list[str] = Field(default_factory=list)

    def seed(self) -> SlideSpec:
        elements=[]
        for item in self.requirements:
            heading, separator, detail=item.partition(" (")
            body=detail.rstrip("). ") if separator else f"Explain {heading.strip()} in practical terms."
            elements.append(SlideElement(type="card", heading=heading.strip(), body=body))
        purpose=(f"Explain {self.title} through the requested technical details."
                 if elements else f"Introduce {self.title}.")
        return SlideSpec(
            slide_number=self.slide_number, title=self.title, subtitle=self.subtitle,
            purpose=purpose, layout_type=self.layout_type, elements=elements,
            visual_spec={"brief_locked": True, "brief_requirements": self.requirements},
            metadata={"brief_layout_locked": True},
        )


class PresentationBrief(BaseModel):
    slides: list[BriefSlide] = Field(default_factory=list)

    @property
    def is_structured(self) -> bool:
        return bool(self.slides)

    def by_number(self, number: int) -> BriefSlide | None:
        return next((slide for slide in self.slides if slide.slide_number == number), None)


class BriefInterpreterAgent:
    """Extract `Slide N:` contracts and their requested content from a prompt."""

    @staticmethod
    def _lines_after(section: str, marker: str) -> list[str]:
        match=re.search(rf"(?im)^\s*{re.escape(marker)}\s*:\s*(.*)$", section)
        if not match:
            return []
        tail=section[match.end():]
        # Stop at the next labelled field, while retaining ordinary plain-text
        # item lines such as "Alert Ingestion (...)".
        tail=re.split(r"(?im)^\s*(?:Title|Subtitle|Layout|Topic Areas|Steps to cover|Tiers to cover|Key Outcomes)\s*:", tail, maxsplit=1)[0]
        first=match.group(1).strip()
        lines=([first] if first else []) + [line.strip(" -•\t") for line in tail.splitlines() if line.strip()]
        return [line for line in lines if line and not line.lower().startswith(("ensure ", "please "))]

    def interpret(self, prompt: str, requested_count: int) -> PresentationBrief:
        sections=list(re.finditer(r"(?im)^\s*slide\s+(\d+)\s*:\s*([^\n]+)", prompt))
        slides=[]
        for index, match in enumerate(sections):
            number=int(match.group(1))
            if number < 1 or number > requested_count:
                continue
            section=prompt[match.end():sections[index+1].start() if index+1 < len(sections) else len(prompt)]
            layout_text=(self._lines_after(section, "Layout") or [match.group(2).strip()])[0].lower()
            layout=next((value for phrase, value in _LAYOUTS.items() if phrase in layout_text), LayoutType.feature_grid)
            title=(self._lines_after(section, "Title") or [match.group(2).strip()])[0]
            subtitle_values=self._lines_after(section, "Subtitle")
            requirements=[]
            for marker in ("Topic Areas", "Steps to cover", "Tiers to cover", "Key Outcomes"):
                requirements.extend(self._lines_after(section, marker))
            slides.append(BriefSlide(slide_number=number, title=title, subtitle=subtitle_values[0] if subtitle_values else None, layout_type=layout, requirements=requirements))
        return PresentationBrief(slides=slides)
