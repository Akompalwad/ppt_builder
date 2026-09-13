"""Generate a presentation through one compact, slide-scoped request at a time."""
from __future__ import annotations

from app.llm.gateway import LLMGateway
from app.config import get_settings
from app.schemas.presentation import CreatePresentationRequest, LayoutType, PresentationSpec, SlideSpec


class SlideContentAgent:
    """Keeps each provider completion small enough to avoid deck-wide timeouts."""

    @staticmethod
    def _deck_context(request: CreatePresentationRequest, brief) -> tuple[str, str]:
        """Return stable deck grounding without replaying the full user prompt.

        The brief interpreter has already extracted slide-level contracts.  A
        per-slide model call needs only a concise statement of the deck's
        subject, not the instructions, data, and layout requirements for all
        other slides.  This materially lowers token use and prevents one
        slide's requirements from bleeding into another.
        """
        declared_title=(getattr(brief, "deck_title", None) or "").strip()
        source=declared_title or request.topic
        source=" ".join(source.split())
        # Stop before an explicit slide contract when no deck title was
        # supplied.  Preserve a normal sentence for open-ended prompts.
        source=source.split("Slide 1:", 1)[0].strip()
        source=source[:220].rstrip(" ,;:-")
        deck_title=declared_title or source or "Presentation"
        return deck_title, source

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
            if directive.nested_bullets or (
                directive.native_diagram
                and directive.layout_type == LayoutType.architecture_layers
                and bool((element.body or "").strip())
            ):
                # Nested technical statements came directly from the user.
                # Architecture layer service names are source data as well,
                # not optional model copy. Both must survive even if the
                # provider emits a simplified or generic element list.
                preserved.append(merged)
                continue
            if element.type == "metric" and element.value:
                # An explicit metric has two immutable visible fields: the
                # numeric value and its descriptive heading.  Models often
                # echo the numeric value as body copy, producing a second
                # callout below the label.  Keep optional body copy empty
                # unless the user supplied it themselves.
                preserved.append(merged)
                continue
            for field in ("body", "subtext", "value", "label"):
                if candidate.get(field):
                    merged[field]=candidate[field]
            preserved.append(merged)
        return preserved

    @staticmethod
    def _preserve_named_requirements(requirements: list[str], generated: dict) -> list[dict]:
        """Keep named concepts from a prose constraint even if the model drifts."""
        returned={
            (item.get("heading") or item.get("label") or "").strip().lower(): item
            for item in generated.get("elements", []) if isinstance(item, dict)
        }
        preserved=[]
        for requirement in requirements:
            candidate=returned.get(requirement.lower(), {})
            preserved.append({
                "type":candidate.get("type", "card"), "heading":requirement,
                # Models may enrich a protected label. If they cannot, an
                # empty body is safer than exposing an internal instruction
                # as visible slide copy.
                "body":candidate.get("body") or candidate.get("subtext") or "",
            })
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
            purpose=fallback.purpose or f"Key considerations for {title}."
            repairs.append("purpose")
        elements=payload.get("elements")
        if not isinstance(elements, list):
            elements=[item.model_dump() for item in fallback.elements]
            repairs.append("elements")
        visual_spec=payload.get("visual_spec")
        if not isinstance(visual_spec, dict):
            visual_spec={}
            repairs.append("visual_spec")
        merged_visual_spec={**slide.visual_spec, **visual_spec}
        # These fields describe user-mandated rendering behaviour, not a
        # creative preference the provider may override. In particular, a
        # native architecture must never silently become a stock-image slide.
        if directive and directive.native_diagram:
            merged_visual_spec["native_diagram"]=True
            merged_visual_spec["image_required"]=False
        if directive and directive.table_data:
            merged_visual_spec["table_data"]=directive.table_data
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
            "visual_spec":merged_visual_spec,
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
            constraint=brief.constraint_for_slide(number) if brief else None
            if directive:
                placeholders.append(directive.seed())
            else:
                placeholders.append(SlideSpec(
                    slide_number=number, title=request.topic, purpose="Develop this story beat.",
                    layout_type=constraint.layout_type if constraint and constraint.layout_type else LayoutType.feature_grid,
                    visual_spec={
                        "constraint_requirements":constraint.requirements,
                        "constraint_layout":constraint.layout_type.value if constraint and constraint.layout_type else None,
                        "constraint_story_stage":constraint.story_stage,
                        "constraint_story_intent":constraint.story_intent,
                        "constraint_preferred_recipe":constraint.preferred_recipe,
                    } if constraint else {},
                    metadata={"content_contract_locked":bool(constraint)},
                ))
        deck_title, deck_focus=self._deck_context(request, brief)
        spec=PresentationSpec(
            title=deck_title, topic=request.topic, target_audience=request.audience,
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
            constraint=brief.constraint_for_slide(slide.slide_number) if brief else None
            locked_contract=(f'''This is an explicit user-authored contract. Preserve its exact title, subtitle, layout, and every required item. Expand each item with accurate, concise technical explanation; do not omit, rename, or replace it.
Required title: {directive.title}
Required subtitle: {directive.subtitle or "none"}
Required layout: {directive.layout_type.value}
Required items: {directive.requirements}
Chart data supplied by the user: {directive.chart_data or "none"}
Table data supplied by the user: {directive.table_data or "none"}
Required number of visible elements: {directive.exact_element_count or "normal"}
Additional rendering contract: {directive.content_instruction or "none"}
Requested visual direction: {directive.visual_instruction or "none"}
''' if directive else "")
            prose_contract=(f'''This is a non-negotiable prose constraint for this slide. Meet it without exposing this instruction in visible text.
Required layout: {constraint.layout_type.value if constraint and constraint.layout_type else "model choice"}
Required content: {constraint.requirements if constraint else "none"}
Required element count: {constraint.exact_element_count if constraint and constraint.exact_element_count else "normal"}
Narrative position: {constraint.story_stage if constraint else "model choice"}
Narrative instruction: {constraint.story_intent if constraint else "none"}
''' if constraint else "")
            element_count_rule=(
                f"Use exactly {directive.exact_element_count} elements for this slide." if directive and directive.exact_element_count else
                f"Use exactly {constraint.exact_element_count} elements for this slide." if constraint and constraint.exact_element_count else
                "Use zero or one element for the title slide, and 2–3 elements for other slides (four only for a true comparison)."
            )
            prompt=f'''Create exactly one PowerPoint slide as one JSON object.
Deck title: {deck_title}
Deck focus: {deck_focus}
Audience: {request.audience}
Tone: {request.tone}
Language: {request.language}
Theme: {theme_name}
Slide {slide.slide_number} of {request.slide_count}
Story role: {beat.stage}
Story intent: {beat.intent}
Preferred composition: {beat.preferred_recipe}
{locked_contract}
{prose_contract}
Visual asset rule: {"Set image_required to true for this cover and provide a precise Unsplash stock_query." if slide.slide_number == 1 else "Set image_required to true only when a real photograph materially improves this slide; otherwise use false."}

Return one valid JSON object only. It must include title, subtitle, layout_type, purpose, elements, and visual_spec. Each element must include type, heading, and body. visual_spec must include icon_concept, image_required, image_prompt, and stock_query.

Valid layouts: title_slide, section_slide, step_workflow, feature_grid, architecture_layers, comparison, timeline, process_flow, dashboard, two_column, key_metrics, summary, content_with_visual.
{element_count_rule} Keep headings under 42 characters and bodies under 120 characters. Story role and story intent are private planning instructions: never repeat or paraphrase them in title, subtitle, purpose, headings, or body copy. Purpose must state a complete, concrete audience-facing insight, never an instruction such as "Set the decision context". Do not infer, mention, or fulfill instructions belonging to any other slide.'''
            max_tokens=get_settings().gemini_max_output_tokens if provider == "gemini" else 1200
            generated=gateway.generate_json(prompt, max_tokens=max_tokens, temperature=.1)
            if directive and (directive.elements or directive.requirements) and isinstance(generated, dict):
                generated["elements"]=self._preserve_contract_elements(directive, generated)
            elif constraint and constraint.requirements and constraint.exact_element_count == len(constraint.requirements) and isinstance(generated, dict):
                generated["elements"]=self._preserve_named_requirements(constraint.requirements, generated)
            # The Storyline and Design agents own layout selection. Models
            # occasionally echo the JSON-schema placeholder ("...") for this
            # field, which should never invalidate otherwise usable content.
            spec.slides[slide.slide_number-1]=SlideSpec.model_validate(
                self._complete_slide_payload(slide, directive, generated)
            )
        return spec
