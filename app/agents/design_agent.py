"""Design Director: turns a linear outline into an intentional visual sequence."""
from __future__ import annotations
from typing import Literal
import re
from pydantic import BaseModel, Field
from app.agents.layout_catalog import RECIPES, LayoutRecipe
from app.schemas.presentation import DesignSystem, LayoutType, PresentationSpec
from app.llm.gateway import LLMGateway
from app.config import get_settings

class DesignDecision(BaseModel):
    slide_number: int
    layout: LayoutType
    composition: str
    shape_language: str
    visual_priority: str
    native_transition: str
    motion_sequence: list[str] = Field(default_factory=list)
    visual_direction: str = ""
    visual_variant: str = ""
    background_treatment: str = ""

class DesignPlan(BaseModel):
    decisions: list[DesignDecision]
    source: str = "deterministic"
    palette_source: str = "deterministic"
    animation_note: str = "PowerPoint exports a capped, story-aware sequence of native entrance animations for meaningful text components."

class _DesignChoice(BaseModel):
    slide_number: int
    recipe: Literal["cover", "split", "compare", "evidence", "flow", "layers", "insight", "grid", "close", "section"]
    visual_direction: str = Field(max_length=160)
    visual_variant: Literal["editorial_cover", "chevron_flow", "cycle_loop", "layer_stack", "isometric_stack", "comparison_table", "split_decision", "metric_dashboard", "data_chart", "editorial_insight", "image_story", "summary_blueprint", "section_break"] = "editorial_insight"
    background_treatment: Literal["halo", "blueprint", "diagonal", "spotlight", "clean"] = "clean"

class _DesignResponse(BaseModel):
    slides: list[_DesignChoice]
    theme_tokens: dict[str, str] | None = None


_PALETTE_FIELDS=(
    "background_color", "surface_color", "primary_color", "secondary_color",
    "accent_color", "header_color", "text_primary", "text_secondary", "muted_text",
)


def _rgb(hex_value: str) -> tuple[float, float, float]:
    value=hex_value.lstrip("#")
    return tuple(int(value[index:index+2], 16) / 255 for index in (0, 2, 4))


def _luminance(hex_value: str) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
    red, green, blue=(channel(value) for value in _rgb(hex_value))
    return .2126 * red + .7152 * green + .0722 * blue


def _contrast(first: str, second: str) -> float:
    light, dark=sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


def validated_palette(tokens: object, base: DesignSystem) -> DesignSystem | None:
    """Accept only complete, readable LLM-selected renderer colour tokens."""
    if not isinstance(tokens, dict) or set(tokens) != set(_PALETTE_FIELDS):
        return None
    normalized={}
    for field in _PALETTE_FIELDS:
        value=tokens.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            return None
        normalized[field]=value.upper()
    # Body text needs a real reading contrast, while headings receive an even
    # stricter guard. This rejects visually attractive but unusable palettes.
    if _contrast(normalized["text_primary"], normalized["background_color"]) < 4.5:
        return None
    if _contrast(normalized["header_color"], normalized["background_color"]) < 4.5:
        return None
    if _contrast(normalized["text_secondary"], normalized["background_color"]) < 3.2:
        return None
    if len(set(normalized.values())) < 5:
        return None
    return DesignSystem(**{**base.model_dump(), **normalized, "name":"Prompt Brand Palette"})

class DesignDirectorAgent:
    """Selects a varied, topic-aware visual composition for every slide.

    It is deliberately deterministic: a regeneration of the same outline has a
    coherent story, while adjacent slides are prevented from sharing the same
    silhouette unless their content genuinely requires it.
    """

    @staticmethod
    def _recipe_for(text: str) -> LayoutRecipe:
        if any(word in text for word in ("compare", "trade-off", "versus", "criteria", "difference")):
            return RECIPES["compare"]
        if any(word in text for word in ("choose", "operating model", "decision", "recommend")):
            return RECIPES["split"]
        if any(word in text for word in ("process", "migration", "timeline", "roadmap", "how it works", "journey")):
            return RECIPES["flow"]
        if any(word in text for word in ("architecture", "platform", "layers", "system", "stack")):
            return RECIPES["layers"]
        if any(word in text for word in ("scale", "cost", "impact", "results", "metrics", "evidence", "outcome")):
            return RECIPES["evidence"]
        if any(word in text for word in ("challenge", "problem", "principle", "insight", "why")):
            return RECIPES["insight"]
        return RECIPES["grid"]

    @staticmethod
    def _recipe_for_explicit_layout(layout: LayoutType) -> LayoutRecipe:
        """Translate a locked user layout into its matching composition.

        A prompt asking for a Feature Grid must not be silently rendered as a
        metrics dashboard just because its content contains numbers.
        """
        mapping={
            LayoutType.title_slide:"cover", LayoutType.section_slide:"section",
            LayoutType.feature_grid:"grid", LayoutType.step_workflow:"flow",
            LayoutType.process_flow:"flow", LayoutType.architecture_layers:"layers",
            LayoutType.comparison:"compare", LayoutType.two_column:"split",
            LayoutType.key_metrics:"evidence", LayoutType.dashboard:"evidence",
            LayoutType.summary:"close", LayoutType.timeline:"flow",
            LayoutType.content_with_visual:"insight",
        }
        return RECIPES[mapping[layout]]

    @staticmethod
    def _default_variant(recipe: LayoutRecipe) -> str:
        return {
            "cover":"editorial_cover", "split":"split_decision", "compare":"comparison_table",
            "evidence":"metric_dashboard", "flow":"chevron_flow", "layers":"layer_stack",
            "insight":"editorial_insight", "grid":"editorial_insight", "close":"summary_blueprint",
            "section":"section_break",
        }[recipe.name]

    @staticmethod
    def _default_background(recipe: LayoutRecipe) -> str:
        return {
            "cover":"halo", "split":"diagonal", "compare":"clean", "evidence":"spotlight",
            "flow":"diagonal", "layers":"blueprint", "insight":"halo", "grid":"clean",
            "close":"spotlight", "section":"halo",
        }[recipe.name]

    def _model_choices(self, spec: PresentationSpec, provider: str | None, model: str | None) -> tuple[dict[int, _DesignChoice], dict[str, str] | None]:
        """Ask a dedicated design planner for composition only, never copy."""
        if provider not in {"gemini", "nvidia", "ollama"}:
            return {}, None
        slides="\n".join(
            f"{slide.slide_number}. stage={slide.visual_spec.get('story_stage', 'content')}; title={slide.title}; purpose={slide.purpose}"
            for slide in spec.slides
        )
        prompt=f'''You are the Design Director for an editable PowerPoint deck. Choose a composition for each slide without changing any wording or facts.
Topic: {spec.topic}
Slides:
{slides}

Return JSON only: {{"slides":[{{"slide_number":1,"recipe":"...","visual_direction":"...","visual_variant":"...","background_treatment":"..."}}],"theme_tokens":{{"background_color":"#......","surface_color":"#......","primary_color":"#......","secondary_color":"#......","accent_color":"#......","header_color":"#......","text_primary":"#......","text_secondary":"#......","muted_text":"#......"}}}}.
Allowed recipes: cover, split, compare, evidence, flow, layers, insight, grid, close, section.
Allowed visual variants: editorial_cover, chevron_flow, cycle_loop, layer_stack, isometric_stack, comparison_table, split_decision, metric_dashboard, data_chart, editorial_insight, image_story, summary_blueprint, section_break.
Allowed background treatments: halo, blueprint, diagonal, spotlight, clean.
Rules: slide 1 must use cover; the final slide must use close. Vary adjacent recipes and preserve the narrative role of each slide. Prefer compare for direct criteria, flow for a sequence, layers for a system, evidence for quantified proof, split for a decision, and insight for a single strong claim. Use cycle_loop only for repeated feedback; use isometric_stack only for a true architecture hierarchy. Use data_chart only when the slide already includes explicit, comparable source data. Keep background treatments subtle and vary them only when they reinforce the visual role. visual_direction is a short instruction for an editable native visual, not a list of boxes.

If the prompt contains explicit brand colours, palette names, or a named colour scheme, return exactly the nine theme_tokens as six-digit hex values matching that instruction. Otherwise return theme_tokens as null. Prefer dark text on light backgrounds and light text on dark backgrounds.'''
        try:
            max_tokens=min(700, get_settings().gemini_max_output_tokens) if provider=="gemini" else 700
            response=_DesignResponse.model_validate(
                LLMGateway.from_settings(provider, model).generate_json(prompt, max_tokens=max_tokens, temperature=.2)
            )
        except Exception:
            # Composition enhancement is optional: never downgrade a
            # successfully generated deck because this single request fails.
            return {}, None
        choices={choice.slide_number: choice for choice in response.slides}
        return (choices, response.theme_tokens) if set(choices) == set(range(1, len(spec.slides)+1)) else ({}, response.theme_tokens)

    def apply(self, spec: PresentationSpec, *, provider: str | None = None, model: str | None = None, allow_prompt_palette: bool = False) -> DesignPlan:
        choices, proposed_palette=self._model_choices(spec, provider, model)
        applied_palette=validated_palette(proposed_palette, spec.design_system) if allow_prompt_palette else None
        if applied_palette:
            spec.design_system=applied_palette
        decisions=[]; previous_composition: str | None=None
        for index, slide in enumerate(spec.slides):
            title=(slide.title+" "+slide.purpose).lower()
            constraint_layout=slide.visual_spec.get("constraint_layout")
            if slide.metadata.get("brief_layout_locked") or constraint_layout:
                recipe=self._recipe_for_explicit_layout(slide.layout_type)
            elif index==0:
                recipe=RECIPES["cover"]
            elif index==len(spec.slides)-1:
                recipe=RECIPES["close"]
            else:
                # A Storyline Agent recommendation wins for generated decks;
                # semantic analysis remains the safe fallback for edited specs.
                preferred=slide.visual_spec.get("preferred_recipe")
                recipe=RECIPES.get(preferred) if preferred else self._recipe_for(title)
                if recipe is None:
                    recipe=self._recipe_for(title)

            choice=choices.get(slide.slide_number)
            if choice and index not in {0, len(spec.slides)-1} and not constraint_layout:
                recipe=RECIPES[choice.recipe]

            # A sequence of generic grids is the usual cause of a template-like
            # deck. Switch the later duplicate into an asymmetric editorial slide.
            if not (slide.metadata.get("brief_layout_locked") or constraint_layout) and recipe.composition==previous_composition and recipe.name in {"grid", "insight"}:
                recipe=RECIPES["insight"] if recipe.name=="grid" else RECIPES["grid"]

            # Explicit layout requests in a detailed user brief are a contract,
            # not a suggestion for the visual agent to overwrite.
            resolved_layout=slide.layout_type if (slide.metadata.get("brief_layout_locked") or constraint_layout) else recipe.layout
            slide.layout_type=resolved_layout
            selected_variant=choice.visual_variant if choice else self._default_variant(recipe)
            # A user who explicitly asks for an architecture, pipeline, or
            # workflow diagram is asking for real PowerPoint geometry.  Keep
            # it on the native renderer path rather than selecting a visual
            # variant that may favour a decorative composition or an image.
            if slide.visual_spec.get("native_diagram"):
                selected_variant="native_diagram"
            # A chart is chosen from supplied data, never from model-invented
            # values. The renderer validates the structure before drawing it.
            if slide.visual_spec.get("chart_data"):
                selected_variant="data_chart"
            slide.visual_spec.update({
                "composition":recipe.composition,
                "shape_language":recipe.shape_language,
                "visual_priority":recipe.visual_priority,
                "transition":recipe.transition,
                "motion_sequence":list(recipe.motion_sequence),
                "visual_direction":choice.visual_direction if choice else recipe.visual_priority,
                "visual_variant":selected_variant,
                "background_treatment":choice.background_treatment if choice else self._default_background(recipe),
            })
            decisions.append(DesignDecision(
                slide_number=slide.slide_number, layout=resolved_layout,
                composition=recipe.composition, shape_language=recipe.shape_language,
                visual_priority=recipe.visual_priority, native_transition=recipe.transition,
                motion_sequence=list(recipe.motion_sequence),
                visual_direction=choice.visual_direction if choice else recipe.visual_priority,
                visual_variant=selected_variant,
                background_treatment=choice.background_treatment if choice else self._default_background(recipe),
            ))
            previous_composition=recipe.composition
        return DesignPlan(
            decisions=decisions, source="model" if choices else "deterministic",
            palette_source="model" if applied_palette else "deterministic",
        )
