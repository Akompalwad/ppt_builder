"""A small, reusable catalog of editorial presentation compositions.

The catalog gives the design agent an explicit vocabulary beyond "put cards on
the slide".  Recipes are renderer-neutral design intent; the PPTX renderer and
web preview both consume the chosen layout type and visual metadata.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.presentation import LayoutType


@dataclass(frozen=True)
class LayoutRecipe:
    name: str
    layout: LayoutType
    composition: str
    shape_language: str
    visual_priority: str
    transition: str
    motion_sequence: tuple[str, ...]


RECIPES: dict[str, LayoutRecipe] = {
    "cover": LayoutRecipe("cover", LayoutType.title_slide, "editorial cover", "large type with a focal visual", "single focal idea", "fade", ("Reveal title", "Reveal subtitle", "Reveal focal visual")),
    "split": LayoutRecipe("split", LayoutType.two_column, "split decision", "paired elevated surfaces", "choice", "push", ("Reveal first path", "Reveal second path", "Reveal decision rule")),
    "compare": LayoutRecipe("compare", LayoutType.comparison, "comparison matrix", "stacked contrast rows", "contrast", "wipe", ("Reveal decision lenses", "Reveal comparison rows")),
    "evidence": LayoutRecipe("evidence", LayoutType.key_metrics, "evidence strip", "vertical accent rules", "evidence", "fade", ("Reveal lead evidence", "Reveal supporting evidence")),
    "flow": LayoutRecipe("flow", LayoutType.process_flow, "numbered progression", "steps and connectors", "sequence", "push", ("Reveal first step", "Build remaining steps in order")),
    "layers": LayoutRecipe("layers", LayoutType.architecture_layers, "layered system", "nested horizontal layers", "hierarchy", "wipe", ("Reveal foundation", "Build layers upward")),
    "insight": LayoutRecipe("insight", LayoutType.content_with_visual, "asymmetric insight", "focal claim with support panels", "one focal claim", "fade", ("Reveal focal claim", "Reveal supporting points")),
    "grid": LayoutRecipe("grid", LayoutType.feature_grid, "editorial insight grid", "balanced insight cards", "key ideas", "push", ("Reveal insights in reading order",)),
    "close": LayoutRecipe("close", LayoutType.summary, "decision close", "lead recommendation and actions", "recommendation", "fade", ("Reveal recommendation", "Reveal next actions")),
    "section": LayoutRecipe("section", LayoutType.section_slide, "section interlude", "large label with minimal ornament", "transition", "wipe", ("Reveal section label",)),
}
