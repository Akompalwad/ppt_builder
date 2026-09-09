from __future__ import annotations
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator


class HighlightState(str, Enum): default="default"; active="active"; warning="warning"; success="success"; muted="muted"
class LayoutType(str, Enum):
    title_slide="title_slide"; section_slide="section_slide"; step_workflow="step_workflow"; feature_grid="feature_grid"; architecture_layers="architecture_layers"; comparison="comparison"; timeline="timeline"; process_flow="process_flow"; dashboard="dashboard"; two_column="two_column"; key_metrics="key_metrics"; summary="summary"; content_with_visual="content_with_visual"

class DesignSystem(BaseModel):
    name: str = "Cyber Dark"; background_color: str = "#070E17"; surface_color: str = "#102131"; primary_color: str = "#00F2C3"; secondary_color: str = "#2B6CB0"; accent_color: str = "#FF8C00"; warning_color: str = "#FF8C00"; success_color: str = "#00F2C3"; header_color: str = "#FFE600"; text_primary: str = "#F4F8FB"; text_secondary: str = "#B7C6D5"; muted_text: str = "#7890A3"; font_heading: str = "Arial"; font_body: str = "Arial"; border_radius: int = 12; spacing: int = 16; title_size: int = 30; subtitle_size: int = 16; body_size: int = 14; icon_style: str = "outline"; image_style: str = "rounded"; card_style: str = "subtle"; line_style: str = "solid"; shadow_style: str = "none"

class SlideElement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4())); type: str = "text"; heading: str | None = None; subtext: str | None = None; body: str | None = None; icon: str | None = None; image_asset_id: str | None = None; value: str | None = None; label: str | None = None; highlight_state: HighlightState = HighlightState.default; style: dict[str, Any] = Field(default_factory=dict); position: dict[str, float] = Field(default_factory=dict)

class SlideSpec(BaseModel):
    slide_number: int = Field(ge=1); title: str; subtitle: str | None = None; layout_type: LayoutType; purpose: str; speaker_notes: str = ""; elements: list[SlideElement] = Field(default_factory=list); visual_spec: dict[str, Any] = Field(default_factory=dict); metadata: dict[str, Any] = Field(default_factory=dict)

class PresentationSpec(BaseModel):
    id: UUID = Field(default_factory=uuid4); title: str; subtitle: str | None = None; topic: str; objective: str = "Inform and persuade"; target_audience: str = "General audience"; language: str = "English"; theme: str = "Cyber Dark"; slides: list[SlideSpec]; metadata: dict[str, Any] = Field(default_factory=dict); design_system: DesignSystem = Field(default_factory=DesignSystem)
    @field_validator("slides")
    @classmethod
    def ordered(cls, slides: list[SlideSpec]) -> list[SlideSpec]:
        if not slides: raise ValueError("A presentation needs at least one slide")
        if [s.slide_number for s in slides] != list(range(1, len(slides)+1)): raise ValueError("Slide numbers must be consecutive")
        return slides

class CreatePresentationRequest(BaseModel):
    # Detailed JSON slide contracts are intentionally accepted.  The bound
    # prevents accidental/unbounded payloads without rejecting a normal
    # five-to-ten-slide technical brief.
    topic: str = Field(min_length=3, max_length=16000); slide_count: int = Field(default=6, ge=3, le=10); theme: str = "Auto"; provider: str | None = None; model: str | None = None; audience: str = "General audience"; tone: str = "Professional"; language: str = "English"; email_notification: bool = False; include_external_images: bool = True
