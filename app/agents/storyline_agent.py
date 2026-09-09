"""Narrative planning before visual layout selection.

This agent assigns each slide a job in the story.  The Design Director then
turns that job into a composition, so a deck does not become a repeated series
of visually identical cards or two-column choices.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.presentation import PresentationSpec


class StoryBeat(BaseModel):
    slide_number: int
    stage: str
    intent: str
    preferred_recipe: str


class StorylinePlan(BaseModel):
    arc: str
    beats: list[StoryBeat]


class StorylineAgent:
    def _arc_for(self, topic: str) -> tuple[str, list[tuple[str, str, str]]]:
        text=topic.lower()
        # A topic should determine the *argument* of a deck, not merely its
        # nouns.  These archetypes deliberately use different story grammar so
        # a security operating model never reads like an investment comparison.
        if any(word in text for word in ("threat", "security", "soc", "incident", "vulnerability", "mitigation", "attack")):
            return "security operations arc", [
                ("risk landscape", "Make the threat, exposure, and operational stakes tangible.", "insight"),
                ("response lifecycle", "Show how signals move from detection through containment and learning.", "flow"),
                ("control plane", "Explain the agents, data, and human controls that govern safe response.", "layers"),
                ("operating guardrails", "Surface escalation, auditability, and decision rights.", "split"),
                ("outcome", "Connect the operating model to response quality and resilience.", "evidence"),
            ]
        if any(word in text for word in ("investment", "depository", "nsdl", "cdsl", "portfolio", "wealth", "stock", "share", "fund")):
            return "investor decision arc", [
                ("decision frame", "Clarify what the investor is choosing and what does not change.", "insight"),
                ("market foundation", "Explain the market structure and the parties involved.", "layers"),
                ("decision lenses", "Compare the options on the few criteria an investor can act on.", "compare"),
                ("investor scenarios", "Map common investor needs to the appropriate practical path.", "split"),
                ("takeaway", "Land on the broker-first selection rule and next action.", "evidence"),
            ]
        if any(word in text for word in ("vs", "versus", "compare", "comparison", "trade-off")):
            return "comparison decision arc", [
                ("context", "Set the decision context and stakes.", "insight"),
                ("operating model", "Explain the systems and constraints behind each option.", "layers"),
                ("trade-offs", "Make the alternatives comparable using a shared lens.", "compare"),
                ("proof", "Show the evidence, costs, or outcomes that matter.", "evidence"),
                ("action", "Turn the analysis into a practical selection rule.", "split"),
            ]
        if any(word in text for word in ("roadmap", "migration", "process", "workflow", "plan", "launch")):
            return "execution arc", [
                ("context", "Frame the outcome and the starting condition.", "insight"),
                ("system", "Show the components that make execution possible.", "layers"),
                ("journey", "Walk through the sequence of work.", "flow"),
                ("proof", "Define how success will be measured.", "evidence"),
                ("action", "End with the next owned action.", "split"),
            ]
        return "insight-to-action arc", [
            ("context", "Frame why this topic matters now.", "insight"),
            ("mechanism", "Explain the core components or operating model.", "layers"),
            ("options", "Contrast viable approaches and their implications.", "compare"),
            ("evidence", "Show the signal, impact, or metric to watch.", "evidence"),
            ("action", "Close with a practical decision or next step.", "split"),
        ]

    def apply(self, spec: PresentationSpec) -> StorylinePlan:
        arc, pattern=self._arc_for(spec.topic)
        beats: list[StoryBeat]=[]
        middle=spec.slides[1:-1]
        for index, slide in enumerate(spec.slides):
            if index == 0:
                stage, intent, recipe="opening", "Introduce the central question.", "cover"
            elif index == len(spec.slides)-1:
                stage, intent, recipe="close", "Land on a memorable recommendation.", "close"
            else:
                # Spread the five narrative jobs across however many middle
                # slides were requested, without adjacent repeated recipes.
                middle_index=index-1
                pattern_index=int(middle_index * len(pattern) / max(1, len(middle)))
                stage, intent, recipe=pattern[min(pattern_index, len(pattern)-1)]
            slide.visual_spec.update({"story_stage":stage, "story_intent":intent, "preferred_recipe":recipe})
            beats.append(StoryBeat(slide_number=slide.slide_number, stage=stage, intent=intent, preferred_recipe=recipe))
        return StorylinePlan(arc=arc, beats=beats)
