"""Design Director: turns a linear outline into an intentional visual sequence."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from app.agents.layout_catalog import RECIPES, LayoutRecipe
from app.schemas.presentation import LayoutType, PresentationSpec
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
    animation_note: str = "PowerPoint slide transitions are exported. Element reveal sequences remain a design brief for the current renderer."

class _DesignChoice(BaseModel):
    slide_number: int
    recipe: Literal["cover", "split", "compare", "evidence", "flow", "layers", "insight", "grid", "close", "section"]
    visual_direction: str = Field(max_length=160)
    visual_variant: Literal["editorial_cover", "chevron_flow", "cycle_loop", "layer_stack", "isometric_stack", "comparison_table", "split_decision", "metric_dashboard", "editorial_insight", "image_story", "summary_blueprint", "section_break"] = "editorial_insight"
    background_treatment: Literal["halo", "blueprint", "diagonal", "spotlight", "clean"] = "clean"

class _DesignResponse(BaseModel):
    slides: list[_DesignChoice]

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

    def _model_choices(self, spec: PresentationSpec, provider: str | None, model: str | None) -> dict[int, _DesignChoice]:
        """Ask a dedicated design planner for composition only, never copy."""
        if provider not in {"gemini", "nvidia", "ollama"}:
            return {}
        slides="\n".join(
            f"{slide.slide_number}. stage={slide.visual_spec.get('story_stage', 'content')}; title={slide.title}; purpose={slide.purpose}"
            for slide in spec.slides
        )
        prompt=f'''You are the Design Director for an editable PowerPoint deck. Choose a composition for each slide without changing any wording or facts.
Topic: {spec.topic}
Slides:
{slides}

Return JSON only: {{"slides":[{{"slide_number":1,"recipe":"...","visual_direction":"...","visual_variant":"...","background_treatment":"..."}}]}}.
Allowed recipes: cover, split, compare, evidence, flow, layers, insight, grid, close, section.
Allowed visual variants: editorial_cover, chevron_flow, cycle_loop, layer_stack, isometric_stack, comparison_table, split_decision, metric_dashboard, editorial_insight, image_story, summary_blueprint, section_break.
Allowed background treatments: halo, blueprint, diagonal, spotlight, clean.
Rules: slide 1 must use cover; the final slide must use close. Vary adjacent recipes. Prefer compare for direct criteria, flow for a sequence, layers for a system, evidence for quantified proof, split for a decision, and insight for a single strong claim. Use cycle_loop only for repeated feedback; use isometric_stack only for a true architecture hierarchy. Keep background treatments subtle and vary them only when they reinforce the visual role. visual_direction is a short instruction for an editable native visual, not a list of boxes.'''
        try:
            max_tokens=min(700, get_settings().gemini_max_output_tokens) if provider=="gemini" else 700
            response=_DesignResponse.model_validate(
                LLMGateway.from_settings(provider, model).generate_json(prompt, max_tokens=max_tokens, temperature=.2)
            )
        except Exception:
            # Composition enhancement is optional: never downgrade a
            # successfully generated deck because this single request fails.
            return {}
        choices={choice.slide_number: choice for choice in response.slides}
        return choices if set(choices) == set(range(1, len(spec.slides)+1)) else {}

    def apply(self, spec: PresentationSpec, *, provider: str | None = None, model: str | None = None) -> DesignPlan:
        choices=self._model_choices(spec, provider, model)
        decisions=[]; previous_composition: str | None=None
        for index, slide in enumerate(spec.slides):
            title=(slide.title+" "+slide.purpose).lower()
            if index==0:
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
            if choice and index not in {0, len(spec.slides)-1}:
                recipe=RECIPES[choice.recipe]

            # A sequence of generic grids is the usual cause of a template-like
            # deck. Switch the later duplicate into an asymmetric editorial slide.
            if recipe.composition==previous_composition and recipe.name in {"grid", "insight"}:
                recipe=RECIPES["insight"] if recipe.name=="grid" else RECIPES["grid"]

            slide.layout_type=recipe.layout
            slide.visual_spec.update({
                "composition":recipe.composition,
                "shape_language":recipe.shape_language,
                "visual_priority":recipe.visual_priority,
                "transition":recipe.transition,
                "motion_sequence":list(recipe.motion_sequence),
                "visual_direction":choice.visual_direction if choice else recipe.visual_priority,
                "visual_variant":choice.visual_variant if choice else self._default_variant(recipe),
                "background_treatment":choice.background_treatment if choice else self._default_background(recipe),
            })
            decisions.append(DesignDecision(
                slide_number=slide.slide_number, layout=recipe.layout,
                composition=recipe.composition, shape_language=recipe.shape_language,
                visual_priority=recipe.visual_priority, native_transition=recipe.transition,
                motion_sequence=list(recipe.motion_sequence),
                visual_direction=choice.visual_direction if choice else recipe.visual_priority,
                visual_variant=choice.visual_variant if choice else self._default_variant(recipe),
                background_treatment=choice.background_treatment if choice else self._default_background(recipe),
            ))
            previous_composition=recipe.composition
        return DesignPlan(decisions=decisions, source="model" if choices else "deterministic")
