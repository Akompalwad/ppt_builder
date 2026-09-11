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
    table_data: dict | None = None
    exact_element_count: int | None = None
    content_instruction: str | None = None
    contact_matrix: bool = False
    nested_bullets: bool = False
    variable_rows: bool = False
    visual_instruction: str | None = None

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
            visual_spec={
                "brief_locked": True, "brief_requirements": self.requirements,
                **({"chart_data":self.chart_data} if self.chart_data else {}),
                **({"table_data":self.table_data} if self.table_data else {}),
                **({"content_instruction":self.content_instruction} if self.content_instruction else {}),
                **({"contact_matrix":True} if self.contact_matrix else {}),
                **({"nested_bullets":True} if self.nested_bullets else {}),
                **({"variable_rows":True} if self.variable_rows else {}),
                **({"brief_visual_instruction":self.visual_instruction} if self.visual_instruction else {}),
            },
            metadata={"brief_layout_locked": True, "requested_element_count":self.exact_element_count},
        )

class SlideConstraint(BaseModel):
    """A partial contract from prose that does not name every slide."""
    slide_number: int
    layout_type: LayoutType | None = None
    requirements: list[str] = Field(default_factory=list)
    exact_element_count: int | None = None
    story_stage: str | None = None
    story_intent: str | None = None
    preferred_recipe: str | None = None


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
        matches=[constraint for constraint in self.constraints if constraint.slide_number == number]
        if not matches:
            return None
        # A prose brief can independently specify a layout, named content, and
        # a narrative role for the same slide. Merge those partial contracts.
        return SlideConstraint(
            slide_number=number,
            layout_type=next((item.layout_type for item in matches if item.layout_type), None),
            requirements=[requirement for item in matches for requirement in item.requirements],
            exact_element_count=next((item.exact_element_count for item in matches if item.exact_element_count is not None), None),
            story_stage=next((item.story_stage for item in matches if item.story_stage), None),
            story_intent=next((item.story_intent for item in matches if item.story_intent), None),
            preferred_recipe=next((item.preferred_recipe for item in matches if item.preferred_recipe), None),
        )


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
        # Prompts pasted from chat often place all contracts in one long
        # paragraph.  A word boundary recognises both that form and normal
        # Markdown line breaks.
        numbers=[int(number) for number in re.findall(r"(?i)\bslide\s+(\d+)\s*:", normalized)]
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

    @staticmethod
    def _bracket_values(value: str) -> list[str]:
        """Read a user-authored ``[a, b, c]`` row without treating it as prose."""
        values=[item.strip().strip('"') for item in value.split(",") if item.strip()]
        # Markdown-style table rows often contain a formatted number such as
        # ``1,200ms`` without CSV quoting.  Stitch that one value back
        # together so it stays in its intended cell.
        index=0
        while index+1 < len(values):
            if re.fullmatch(r"\d{1,3}", values[index]) and re.match(r"\d{3}(?:\.\d+)?(?:ms|s|%|k|m|b)?\b", values[index+1], re.I):
                values[index:index+2]=[values[index]+","+values[index+1]]
            else:
                index+=1
        return values

    def _structured_slide_details(self, section: str, number: int) -> dict:
        """Extract hard layout/data contracts from a numbered free-form section.

        This intentionally understands simple human-written patterns, rather
        than requiring the user to provide JSON.  It gives tables and long
        roadmaps their own semantic payload before any LLM is called.
        """
        result: dict={"requirements":[], "elements":[], "table_data":None,
                      "exact_element_count":None, "content_instruction":None, "contact_matrix":False,
                      "nested_bullets":False, "variable_rows":False}
        # Nested lists are often pasted as a single line. Split only at
        # camel-case boundaries, then recover title-case parent headings and
        # preserve all intervening source sentences as their children.
        tier_count=re.search(r"\b(\d+)\s+(?:main\s+)?(?:architectural\s+tiers?|core\s+operational\s+divisions?|strategic\s+pillars?)\b", section, re.I)
        if tier_count:
            source=section[tier_count.end():]
            if ":" in source:
                source=source.split(":", 1)[1]
            normalized_source=re.sub(r"(?<=[.!?])(?=[A-Z])", "\n", source)
            normalized_source=re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", "\n", normalized_source)
            lines=[line.strip() for line in normalized_source.splitlines() if line.strip()]
            heading_pattern=re.compile(r"(?:[A-Z][A-Za-z0-9-]*|&)(?:\s+(?:[A-Z][A-Za-z0-9-]*|&)){1,6}$")
            architecture_indexes=[index for index,line in enumerate(lines) if re.search(r"(?:Layer|Matrix|Engine)\.?$", line)]
            heading_indexes=(architecture_indexes if len(architecture_indexes) >= int(tier_count.group(1)) else
                             [index for index,line in enumerate(lines) if heading_pattern.fullmatch(line.rstrip("."))])
            tiers=[]
            for position, line_index in enumerate(heading_indexes[:int(tier_count.group(1))]):
                next_index=heading_indexes[position+1] if position+1 < len(heading_indexes) else len(lines)
                detail=" ".join(lines[line_index+1:next_index])
                detail=re.sub(r"(?<=[.!?])(?=[A-Z])", " ", detail)
                detail=re.sub(r"\s+", " ", detail).strip()
                if detail and detail[-1] not in ".!?":
                    detail += "."
                if lines[line_index]:
                    tiers.append(SlideElement(type="tier", heading=lines[line_index].rstrip("."), body=detail))
            if len(tiers)==int(tier_count.group(1)):
                result["elements"]=tiers
                result["exact_element_count"]=len(tiers)
                result["nested_bullets"]=True
                result["content_instruction"]="Render each architectural tier with its own heading and two indented technical sub-bullets. Preserve the tier order."
                return result

        nodes=re.findall(r"\b(Node\s+[A-Z])\s*:\s*([^.(]+)\.\s*\(([^)]+)\)", section, re.I)
        if nodes:
            # Parenthetical phrases such as "(Extremely long phrase)" are
            # layout-test annotations, never visible slide copy.  Keep the
            # requested node label intact and let the model add a concise,
            # grounded explanation when one is useful.
            result["elements"]=[SlideElement(type="row", heading=f"{node.upper()}: {label.strip()}", body="") for node,label,_note in nodes]
            result["exact_element_count"]=len(nodes)
            result["variable_rows"]=True
            result["content_instruction"]="Render every supplied node label as an aligned row. Adapt each row to its content; do not show prompt annotations or discard long labels. Add one concise technical function only when it is grounded in the deck focus."
            return result
        table_headers=re.search(r"\bcolumns?\s*:\s*\[([^\]]+)\]", section, re.I | re.S)
        table_rows=re.findall(r"\brow\s*\d+\s*:\s*\[([^\]]+)\]", section, re.I | re.S)
        if table_headers and table_rows:
            headers=self._bracket_values(table_headers.group(1))
            rows=[self._bracket_values(row) for row in table_rows]
            if headers and all(len(row)==len(headers) for row in rows):
                result["table_data"]={"headers":headers, "rows":rows}
                result["content_instruction"]="Render the supplied data as a native editable table. Do not replace it with cards or generic comparison copy."
                return result

        steps=[]
        for match in re.finditer(r"\b(?:step|phase)\s*(\d+)\s*:\s*(.+?)(?=(?:[.,]|\n)\s*(?:(?:step|phase)\s*\d+\s*:|test\b)|$)", section, re.I | re.S):
            name=re.sub(r"\s+", " ", match.group(2)).strip(" .")
            if name:
                steps.append((int(match.group(1)), name))
        if steps:
            steps=[name for _,name in sorted(steps)]
            result["requirements"]=steps
            result["exact_element_count"]=len(steps)
            result["content_instruction"]="Render every requested roadmap phase in reading order. Keep the horizontal sequence inside the slide."
            return result

        metrics=re.findall(r"(?:^|\s)[\"“]?([+$-]?\d[\d,.]*(?:%|[xX])?|\$[\d,.]+[KMB]?)[\"”]?\s*\(\s*Label\s*:\s*([^)]+)\)", section, re.I)
        if metrics:
            result["elements"]=[SlideElement(type="metric", heading=label.strip(), value=value, body="") for value,label in metrics]
            result["exact_element_count"]=len(metrics)
            result["content_instruction"]="Show every supplied value as a large metric with its exact label."
            return result

        count_match=re.search(r"\b(\d+)\s+(?:distinct|separate)[^.\n]*(?:bullet|pain point|item|metric)", section, re.I)
        if count_match:
            result["exact_element_count"]=int(count_match.group(1))
        pillar_match=re.search(r"\b(\d+)\s+pillars?\b", section, re.I)
        if pillar_match:
            result["exact_element_count"]=int(pillar_match.group(1))
            result["content_instruction"]="Create indexed pillars in order, each with a complete technical description."
        quadrant_match=re.search(r"\b(?:2x2|four)\s+(?:grid|quadrant|boxes?)\b", section, re.I)
        if quadrant_match:
            result["exact_element_count"]=4
            result["content_instruction"]="Render four equally sized, distinct quadrant boxes that use the full slide canvas."
        if re.search(r"\bon-?call matrix\b", section, re.I):
            result["contact_matrix"]=True
            result["content_instruction"]="Create an On-Call Matrix with distinct escalation fields. Preserve each generated contact value in its own aligned cell; never use duplicate generic headings."
        return result

    def interpret_slide_adjustment(self, instruction: str) -> dict | None:
        """Extract an explicit one-slide layout edit without requiring Slide N.

        Slide editing receives a fragment rather than a full deck brief.  This
        parser deliberately reuses the same protected nested-data grammar as
        deck creation, then honours an orientation override such as
        ``horizontal layout`` before the renderer sees the instruction.
        """
        details=self._structured_slide_details(instruction, 1)
        if not details["nested_bullets"]:
            return None
        horizontal=bool(re.search(r"\b(?:horiz[oa]ntal|left[- ]to[- ]right|across)\b", instruction, re.I))
        return {
            "layout_type":LayoutType.feature_grid if horizontal else LayoutType.architecture_layers,
            "elements":details["elements"],
            "exact_element_count":details["exact_element_count"],
            "visual_spec":{
                "nested_bullets":True,
                "horizontal_nested":horizontal,
                "content_instruction":details["content_instruction"],
            },
        }

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
        deck_title_match=re.search(r"\b(?:presentation|deck)\s+titled\s+[\"“]([^\"”]+)[\"”]", normalized, re.I)
        declared_deck_title=deck_title_match.group(1).strip() if deck_title_match else None
        sections=list(re.finditer(r"(?i)\bslide\s+(\d+)\s*:\s*", normalized))
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
            section_label=section.strip().split(".", 1)[0].strip()
            layout_text=(self._lines_after(section, "Layout") or [section_label])[0].lower()
            layout=next((value for phrase, value in _LAYOUTS.items() if phrase in layout_text), LayoutType.feature_grid)
            explicit_title=re.search(r"\b(?:main\s+)?title\s*(?:must\s+be(?:\s+a\s+long\s+phrase)?\s*)?\:\s*[\"“]([^\"”]+)[\"”]", section, re.I | re.S)
            title=(self._lines_after(section, "Title") or [explicit_title.group(1).strip() if explicit_title else section_label])[0]
            if number == 1 and not explicit_title and section_label.casefold() in {"title slide", "cover slide", "title"} and declared_deck_title:
                title=declared_deck_title
            subtitle_values=self._lines_after(section, "Subtitle")
            visual_match=re.search(r"\b(?:use|show|feature)\s+([^.!]*\bbackground[^.!]*)", section, re.I)
            visual_instruction=visual_match.group(1).strip() if visual_match else None
            requirements=[]
            for marker in ("Topic Areas", "Steps to cover", "Tiers to cover", "Key Outcomes"):
                requirements.extend(self._lines_after(section, marker))
            details=self._structured_slide_details(section, number)
            requirements=details["requirements"] or requirements
            # A table is semantically a comparison, even when the user calls
            # it a markdown table.  The native renderer checks table_data
            # first and therefore never turns it into generic comparison rows.
            if details["table_data"]:
                layout=LayoutType.comparison
            elif details["nested_bullets"]:
                layout=LayoutType.architecture_layers
            elif details["elements"] and all(item.type == "row" for item in details["elements"]):
                layout=LayoutType.comparison
            elif details["elements"] and re.search(r"\bmetric", section, re.I):
                layout=LayoutType.key_metrics
            elif re.search(r"\b(?:split-screen|two[- ]column|2[- ]column)\b", section, re.I):
                layout=LayoutType.two_column
            elif details["requirements"] and re.search(r"\broadmap|\bsequence|\bstep\b|\bphase\b", section, re.I):
                layout=LayoutType.step_workflow
            slides.append(BriefSlide(
                slide_number=number, title=title, subtitle=subtitle_values[0] if subtitle_values else None,
                layout_type=layout, requirements=requirements, elements=details["elements"],
                table_data=details["table_data"], exact_element_count=details["exact_element_count"],
                content_instruction=details["content_instruction"], contact_matrix=details["contact_matrix"], nested_bullets=details["nested_bullets"], variable_rows=details["variable_rows"], visual_instruction=visual_instruction,
            ))
        if slides:
            return PresentationBrief(slides=slides, deck_title=declared_deck_title)

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
        if constraints:
            concept_slide=next((item.slide_number for item in constraints if item.exact_element_count and len(item.requirements) == item.exact_element_count), None)
            for number in range(1,count+1):
                if number == 1:
                    stage, intent, recipe="opening", "Frame the topic and explain why the audience should care.", "cover"
                elif number == 2:
                    stage, intent, recipe="historical timeline", "Begin the requested journey with the earliest historical milestones.", "flow"
                elif concept_slide and number < concept_slide:
                    stage, intent, recipe="progress to present", "Continue the history toward the present before introducing the core concepts.", "flow"
                elif number == concept_slide:
                    stage, intent, recipe="concept foundations", "Teach each named concept with a visible subheading and concise explanation.", "grid"
                elif number == count:
                    stage, intent, recipe="industry impact", "Close with the required distinct future applications or industries.", "grid"
                elif number == count-1:
                    stage, intent, recipe="future trajectory", "Bridge from current capability to the practical future implications.", "evidence"
                else:
                    stage, intent, recipe="current state", "Explain the present state of the field before discussing future impact.", "layers"
                constraints.append(SlideConstraint(
                    slide_number=number, story_stage=stage, story_intent=intent, preferred_recipe=recipe,
                ))
        return PresentationBrief(constraints=constraints, requested_slide_count=count) if constraints else PresentationBrief()
