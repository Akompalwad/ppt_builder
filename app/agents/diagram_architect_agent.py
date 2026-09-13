"""Plan native flow and architecture diagrams before visual composition.

The renderer should never infer relationships from a list of cards.  This
agent creates a small, serialisable diagram contract that both the web and
PowerPoint renderers can consume: nodes, directed edges, lane names and a
safe topology.  It is deliberately deterministic so diagram quality does not
depend on an additional provider call being available.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.presentation import PresentationSpec


class DiagramNode(BaseModel):
    id: str
    heading: str
    description: str = ""
    lane: str | None = None


class DiagramEdge(BaseModel):
    source: str
    target: str
    relationship: str = "flow"


class DiagramPlan(BaseModel):
    slide_number: int
    kind: str
    topology: str
    nodes: list[DiagramNode] = Field(default_factory=list)
    edges: list[DiagramEdge] = Field(default_factory=list)
    lanes: list[str] = Field(default_factory=list)
    cross_cutting_controls: list[str] = Field(default_factory=list)


class DiagramArchitectAgent:
    """Build an explicit, bounded topology for requested native diagrams."""

    @staticmethod
    def _controls(title: str) -> list[str]:
        text=title.lower()
        if "security" in text or "zero-trust" in text:
            return ["Identity & access", "Data protection", "Audit evidence"]
        if "reliability" in text or "resilience" in text:
            return ["Observability", "Recovery controls", "Operational runbooks"]
        if "azure" in text or "deployment" in text:
            return ["Security", "Governance", "Observability"]
        return []

    def apply(self, spec: PresentationSpec) -> list[DiagramPlan]:
        plans: list[DiagramPlan]=[]
        for slide in spec.slides:
            kind=slide.visual_spec.get("diagram_kind")
            if kind not in {"pipeline", "architecture_map", "reference_architecture"}:
                continue
            source=slide.elements[:10]
            nodes=[DiagramNode(
                id=f"s{slide.slide_number}-n{index + 1}",
                heading=(item.heading or item.label or f"Component {index + 1}"),
                description=(item.body or item.subtext or ""),
            ) for index, item in enumerate(source)]
            if not nodes:
                continue
            edges=[DiagramEdge(source=nodes[index].id, target=nodes[index + 1].id)
                   for index in range(len(nodes) - 1)]
            if kind == "pipeline":
                topology="linear" if len(nodes) <= 5 else "snake"
                lanes=["Flow of execution"]
            elif kind == "architecture_map":
                # A two-row snake keeps the row-transition vertical. It avoids
                # the long diagonal generated when a generic grid is connected
                # left-to-right in both rows.
                topology="linear" if len(nodes) <= 3 else "snake"
                lanes=["Request & orchestration", "Grounding & execution"] if len(nodes) > 3 else ["Architecture flow"]
            else:
                topology="layered"
                lanes=["Platform layers"]
            plan=DiagramPlan(
                slide_number=slide.slide_number, kind=kind, topology=topology,
                nodes=nodes, edges=edges, lanes=lanes,
                cross_cutting_controls=self._controls(slide.title),
            )
            slide.visual_spec["diagram_spec"]=plan.model_dump()
            plans.append(plan)
        return plans
