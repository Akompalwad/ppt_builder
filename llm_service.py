from __future__ import annotations

import json
import re
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from openai import OpenAI
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
)


def _sanitize_title(v: Any) -> str:
    """Clean newlines and ensure titles are concise (3-7 words)."""
    if not isinstance(v, str):
        v = str(v)
    cleaned = " ".join(v.strip().split())
    cleaned = re.sub(
        r"^(Create a presentation on|Create a ppt on|Generate a deck for|Act as|Write a)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    if len(cleaned) > 80:
        words = cleaned.split()
        return " ".join(words[:6]).title() + " Deck"
    return cleaned.title() if cleaned else "Executive Overview Deck"


SanitizedTitle = Annotated[str, BeforeValidator(_sanitize_title)]


class LayoutType(str, Enum):
    title_slide = "title_slide"
    step_workflow = "step_workflow"
    feature_grid = "feature_grid"
    architecture_layers = "architecture_layers"


class HighlightState(str, Enum):
    default = "default"
    active = "active"
    warning = "warning"


class SlideElement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=80)
    heading: str = Field(min_length=1, max_length=140)
    subtext: str = Field(default="", max_length=500)
    highlight_state: HighlightState = HighlightState.default


class SlideSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slide_number: int = Field(ge=1)
    title: SanitizedTitle = Field(default="Slide Title")
    subtitle: str = Field(default="", max_length=300)
    layout_type: LayoutType
    elements: List[SlideElement] = Field(
        default_factory=list,
        max_length=12,
    )


class PresentationSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: SanitizedTitle = Field(default="Executive Deck")
    slides: List[SlideSpec] = Field(min_length=1, max_length=10)

    @field_validator("slides")
    @classmethod
    def normalize_slide_numbers(cls, value: List[SlideSpec]) -> List[SlideSpec]:
        for index, slide in enumerate(value, start=1):
            slide.slide_number = index
        return value


UNIVERSAL_SYSTEM_PROMPT = """
You are a expert presentation architect capable of breaking down ANY topic (business, tech, science, finance, history, health, etc.).

TASK:
1. Analyze the user's prompt context fully.
2. Summarize the core idea into a concise 3-6 word main presentation title.
3. Generate detailed, accurate slide content based strictly on the user's input topic.
4. Output STRICT JSON adhering to the exact schema provided. DO NOT use markdown backticks or commentary.

JSON Schema:
{
  "title": "Short Main Title",
  "slides": [
    {
      "slide_number": 1,
      "title": "Main Presentation Title",
      "subtitle": "Informative single-sentence executive context",
      "layout_type": "title_slide",
      "elements": []
    },
    {
      "slide_number": 2,
      "title": "Topic-Specific Structural Section",
      "subtitle": "Detailed summary phrase matching input topic context",
      "layout_type": "feature_grid | step_workflow | architecture_layers",
      "elements": [
        {
          "id": "e1",
          "heading": "Specific Topic Detail 1",
          "subtext": "Comprehensive explanation of this specific point derived from context.",
          "highlight_state": "active | default | warning"
        }
      ]
    }
  ]
}

Layout Guidelines:
- Slide 1 MUST be layout_type: "title_slide".
- Use "step_workflow" for lifecycles, processes, timelines, or sequential workflows.
- Use "architecture_layers" for structured levels, stacks, frameworks, or tiered concepts.
- Use "feature_grid" for feature breakdowns, core pillars, metrics, or comparisons.
"""


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    starts = [i for i, c in enumerate(cleaned) if c == "{"]
    for start in starts:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(cleaned)):
            c = cleaned[i]
            if in_string:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_string = False
                continue
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError("Failed to parse valid JSON from model execution response.")


def _universal_dynamic_fallback(prompt: str, slide_count: int) -> PresentationSpec:
    """Dynamic fallback parser that extracts key phrases directly from ANY input prompt."""
    deck_title = _sanitize_title(prompt)
    
    # Extract non-empty lines or key phrases from the raw prompt
    prompt_lines = [line.strip() for line in prompt.splitlines() if len(line.strip()) > 3]
    topic_keywords = prompt_lines if prompt_lines else ["Overview", "Framework", "Operations", "Strategy"]

    section_templates = [
        ("Executive Overview", "High-level summary and core strategic direction", LayoutType.feature_grid),
        ("Core Components & Pillars", "Key functional domains and operational elements", LayoutType.architecture_layers),
        ("Execution & Lifecycle Workflow", "Step-by-step processing and operational roadmap", LayoutType.step_workflow),
        ("Strategic Impact & Takeaways", "Key capabilities, value drivers, and next steps", LayoutType.feature_grid),
    ]

    slides = [
        SlideSpec(
            slide_number=1,
            title=deck_title,
            subtitle="Executive Presentation Overview",
            layout_type=LayoutType.title_slide,
            elements=[],
        )
    ]

    for i in range(1, slide_count):
        idx = (i - 1) % len(section_templates)
        section_title, section_sub, layout = section_templates[idx]
        
        # Inject user keywords directly into element descriptions dynamically
        elements = []
        for k in range(3):
            phrase = topic_keywords[k % len(topic_keywords)] if topic_keywords else f"Pillar {k+1}"
            elements.append(
                SlideElement(
                    id=f"e_{i}_{k}",
                    heading=f"Focus Area: {phrase[:35]}",
                    subtext=f"Strategic implementation focus on {phrase} addressing requirements outlined in brief.",
                    highlight_state=HighlightState.active if k == 0 else HighlightState.default
                )
            )

        slides.append(
            SlideSpec(
                slide_number=i + 1,
                title=f"{section_title} - Part {i}" if i > 4 else section_title,
                subtitle=section_sub,
                layout_type=layout,
                elements=elements,
            )
        )

    return PresentationSpec(title=deck_title, slides=slides[:slide_count])


class LLMService:
    def __init__(
        self,
        provider: str = "NVIDIA",
        architect_model: Optional[str] = None,
        model: Optional[str] = None,
        writer_model: Optional[str] = None,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        api_key: Optional[str] = None,
        timeout: float = 9800.0,
    ) -> None:
        self.provider = provider
        self.architect_model = architect_model or model or "meta/llama-3.1-70b-instruct"
        self.writer_model = writer_model or self.architect_model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "ollama"
        self.timeout = timeout

    def _client(self) -> OpenAI:
        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=2,
        )

    def generate(self, topic: str, slide_count: int) -> tuple[PresentationSpec, bool, str]:
        try:
            client = self._client()
            user_message = (
                f"Target Slide Count: {slide_count}\n"
                f"Input Presentation Topic Brief:\n\"\"\"\n{topic}\n\"\"\""
            )

            completion = client.chat.completions.create(
                model=self.architect_model,
                messages=[
                    {"role": "system", "content": UNIVERSAL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                max_tokens=max(2000, slide_count * 550),
                response_format={"type": "json_object"},
            )

            raw_content = completion.choices[0].message.content or ""
            payload = _extract_json(raw_content)
            presentation = PresentationSpec.model_validate(payload)
            return presentation, False, f"Generated dynamically with {self.architect_model}."

        except Exception as exc:
            msg = f"API Execution Error ({exc})."

        fallback = _universal_dynamic_fallback(topic, slide_count)
        return fallback, True, f"{msg} Generated dynamic fallback deck."