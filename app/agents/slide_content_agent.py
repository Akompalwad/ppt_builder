"""Generate a presentation through one short NVIDIA request per slide."""
from __future__ import annotations

from app.llm.gateway import LLMGateway
from app.config import get_settings
from app.schemas.presentation import CreatePresentationRequest, LayoutType, PresentationSpec, SlideSpec


class SlideContentAgent:
    """Keeps each NVIDIA completion small enough to avoid deck-wide timeouts."""

    @staticmethod
    def _preserve_contract_elements(directive, generated: dict) -> list[dict]:
        """Keep every explicitly requested item if a model returns a partial slide."""
        required=directive.seed().elements
        returned={
            (item.get("heading") or item.get("label") or "").strip().lower(): item
            for item in generated.get("elements", []) if isinstance(item, dict)
        }
        preserved=[]
        for element in required:
            key=(element.heading or element.label or "").strip().lower()
            candidate=returned.get(key, {})
            # IDs, headings, and the user's seed detail are authoritative;
            # the cloud agent may improve the explanatory copy only.
            merged=element.model_dump()
            for field in ("body", "subtext", "value", "label"):
                if candidate.get(field):
                    merged[field]=candidate[field]
            preserved.append(merged)
        return preserved

    @staticmethod
    def _complete_slide_payload(slide: SlideSpec, directive, generated: object) -> dict:
        """Repair partial provider output before strict SlideSpec validation.

        Some reasoning models intermittently return an element-like JSON object
        (for example ``{"type": "comparison_group", ...}``) despite the
        one-slide contract. The pipeline already knows the slide number,
        requested title, layout, and baseline purpose, so preserve those
        authoritative fields instead of discarding a whole deck.
        """
        payload=generated if isinstance(generated, dict) else {}
        fallback=directive.seed() if directive else slide
        repairs=[]
        title=directive.title if directive else payload.get("title")
        if not isinstance(title, str) or not title.strip():
            title=fallback.title
            repairs.append("title")
        purpose=payload.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            purpose=fallback.purpose or f"Explain {title} for the audience."
            repairs.append("purpose")
        elements=payload.get("elements")
        if not isinstance(elements, list):
            elements=[item.model_dump() for item in fallback.elements]
            repairs.append("elements")
        visual_spec=payload.get("visual_spec")
        if not isinstance(visual_spec, dict):
            visual_spec={}
            repairs.append("visual_spec")
        return {
            **payload,
            "slide_number":slide.slide_number,
            "title":title,
            "subtitle":directive.subtitle if directive else payload.get("subtitle"),
            "purpose":purpose,
            # Layout selection belongs to the storyline/design pipeline, not
            # an occasionally malformed content completion.
            "layout_type":directive.layout_type.value if directive else fallback.layout_type.value,
            "elements":elements,
            "visual_spec":{**slide.visual_spec, **visual_spec},
            "metadata":{
                **slide.metadata,
                "brief_layout_locked":bool(directive),
                **({"provider_response_repaired":repairs} if repairs else {}),
            },
        }

    def generate(
        self,
        request: CreatePresentationRequest,
        theme_name: str,
        storyline,
        *,
        provider: str = "nvidia",
        brief=None,
        progress=None,
    ) -> PresentationSpec:
        placeholders=[]
        for number in range(1, request.slide_count + 1):
            directive=brief.by_number(number) if brief else None
            placeholders.append(directive.seed() if directive else SlideSpec(slide_number=number, title=request.topic, purpose="Develop this story beat.", layout_type=LayoutType.feature_grid))
        spec=PresentationSpec(
            title=request.topic, topic=request.topic, target_audience=request.audience,
            language=request.language, theme=theme_name, slides=placeholders,
        )
        plan=storyline.apply(spec)
        # Both providers receive the exact same small, canonical slide
        # contract. This avoids asking a local fallback to invent an entire
        # deck schema in one long response.
        gateway=LLMGateway.from_settings(
            provider, request.model if provider in {"nvidia", "gemini"} else None
        )
        for slide, beat in zip(spec.slides, plan.beats, strict=True):
            if progress:
                progress(
                    f"Slide Content Agent — drafting slide {slide.slide_number}/{request.slide_count}: {beat.stage}",
                    25 + int((slide.slide_number - 1) / max(1, request.slide_count) * 42),
                )
            directive=brief.by_number(slide.slide_number) if brief else None
            locked_contract=(f'''This is an explicit user-authored contract. Preserve its exact title, subtitle, layout, and every required item. Expand each item with accurate, concise technical explanation; do not omit, rename, or replace it.
Required title: {directive.title}
Required subtitle: {directive.subtitle or "none"}
Required layout: {directive.layout_type.value}
Required items: {directive.requirements}
Chart data supplied by the user: {directive.chart_data or "none"}
''' if directive else "")
            prompt=f'''Create exactly one PowerPoint slide as one JSON object.
Topic: {request.topic}
Audience: {request.audience}
Tone: {request.tone}
Language: {request.language}
Theme: {theme_name}
Slide {slide.slide_number} of {request.slide_count}
Story role: {beat.stage}
Story intent: {beat.intent}
Preferred composition: {beat.preferred_recipe}
{locked_contract}
Visual asset rule: {"Set image_required to true for this cover and provide a precise Unsplash stock_query." if slide.slide_number == 1 else "Set image_required to true only when a real photograph materially improves this slide; otherwise use false."}

Return one valid JSON object only. It must include title, subtitle, layout_type, purpose, elements, and visual_spec. Each element must include type, heading, and body. visual_spec must include icon_concept, image_required, image_prompt, and stock_query.

Valid layouts: title_slide, section_slide, step_workflow, feature_grid, architecture_layers, comparison, timeline, process_flow, dashboard, two_column, key_metrics, summary, content_with_visual.
Use zero or one element for the title slide, and 2–3 elements for other slides (four only for comparisons). Keep headings under 42 characters and bodies under 120 characters. Story role and story intent are private planning instructions: never repeat or paraphrase them in title, subtitle, purpose, headings, or body copy. Purpose must state a complete, concrete audience-facing insight, never an instruction such as "Set the decision context".'''
            max_tokens=get_settings().gemini_max_output_tokens if provider == "gemini" else 1200
            generated=gateway.generate_json(prompt, max_tokens=max_tokens, temperature=.1)
            if directive and (directive.elements or directive.requirements) and isinstance(generated, dict):
                generated["elements"]=self._preserve_contract_elements(directive, generated)
            # The Storyline and Design agents own layout selection. Models
            # occasionally echo the JSON-schema placeholder ("...") for this
            # field, which should never invalidate otherwise usable content.
            spec.slides[slide.slide_number-1]=SlideSpec.model_validate(
                self._complete_slide_payload(slide, directive, generated)
            )
        return spec
