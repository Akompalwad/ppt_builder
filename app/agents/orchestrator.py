from __future__ import annotations
from app.schemas.presentation import CreatePresentationRequest, DesignSystem, LayoutType, PresentationSpec, SlideElement, SlideSpec
from app.llm.gateway import LLMGateway
from app.agents.qa_agent import PresentationQAAgent, summarize_point
from app.agents.design_agent import DesignDirectorAgent
from app.agents.storyline_agent import StorylineAgent
from app.agents.slide_content_agent import SlideContentAgent
from app.agents.brief_agent import BriefInterpreterAgent
from app.config import get_settings
from datetime import datetime, timezone
import hashlib
import re

THEMES={
 "Cyber Dark": DesignSystem(),
 "Minimalist White": DesignSystem(name="Minimalist White",background_color="#FCFBF8",surface_color="#FFFFFF",primary_color="#8070A5",secondary_color="#B8ADC9",accent_color="#C77B45",header_color="#25242B",text_primary="#29272F",text_secondary="#67636F",muted_text="#918B99",card_style="flat",shadow_style="none"),
 "Corporate Blue": DesignSystem(name="Corporate Blue",background_color="#EAF2FB",surface_color="#FFFFFF",primary_color="#075FC4",secondary_color="#338CCB",accent_color="#F2A51A",header_color="#0B315B",text_primary="#102B4A",text_secondary="#466786",muted_text="#7390AA",card_style="elevated",shadow_style="soft"),
 "Security Signal": DesignSystem(name="Security Signal",background_color="#081117",surface_color="#10272C",primary_color="#20D3A2",secondary_color="#197C78",accent_color="#FFB703",header_color="#D9FFF1",text_primary="#F2FFFB",text_secondary="#B6D4CC",muted_text="#7CA69A"),
 "Investor Slate": DesignSystem(name="Investor Slate",background_color="#F4F7FB",surface_color="#FFFFFF",primary_color="#1B5FBF",secondary_color="#6B8FBE",accent_color="#E89B1F",header_color="#123257",text_primary="#172D46",text_secondary="#536A82",muted_text="#71869B"),
 "Aurora Tech": DesignSystem(name="Aurora Tech",background_color="#101024",surface_color="#20213C",primary_color="#A78BFA",secondary_color="#3B82F6",accent_color="#F6C945",header_color="#F4F0FF",text_primary="#FAF9FF",text_secondary="#C7C5E1",muted_text="#9390B5"),
}

def auto_theme_for_topic(topic: str) -> DesignSystem:
    """Choose a coherent but topic-appropriate visual system for Auto."""
    text=topic.lower()
    if any(word in text for word in ("threat", "security", "soc", "incident", "vulnerability", "attack")):
        return THEMES["Security Signal"]
    if any(word in text for word in ("investment", "depository", "nsdl", "cdsl", "portfolio", "wealth", "stock", "share", "fund")):
        return THEMES["Investor Slate"]
    if any(word in text for word in ("ai", "software", "platform", "cloud", "data", "technology", "automation")):
        return THEMES["Aurora Tech"]
    # Keep Auto varied for unrelated topics while deterministic across restarts.
    names=("Cyber Dark", "Minimalist White", "Corporate Blue")
    index=hashlib.sha256(topic.strip().lower().encode()).digest()[0] % len(names)
    return THEMES[names[index]]

def resolve_theme(theme_name: str, topic: str) -> DesignSystem:
    return auto_theme_for_topic(topic) if theme_name == "Auto" else THEMES.get(theme_name, THEMES["Cyber Dark"])

def trace(agent: str, status: str, summary: str, output: dict) -> dict:
    """Inspectable agent artifact; deliberately a concise result, not hidden reasoning."""
    return {"agent":agent,"status":status,"summary":summary,"output":output,"recorded_at":datetime.now(timezone.utc).isoformat()}

def _clean_model_copy(value: str, maximum: int) -> str:
    value=re.sub(r"\s+", " ", (value or "").replace("\\n", " ").replace("\n", " ")).strip()
    return value if len(value)<=maximum else summarize_point(value, max(6, maximum // 8))

def normalize_slide_copy(payload: dict) -> dict:
    """Defensive content editor: model text must be slide-sized before rendering."""
    payload["title"]=_clean_model_copy(payload.get("title",""),52)
    payload["subtitle"]=_clean_model_copy(payload.get("subtitle",""),110) if payload.get("subtitle") else None
    for slide in payload.get("slides",[]):
        slide["title"]=_clean_model_copy(slide.get("title",""),78)
        slide["subtitle"]=_clean_model_copy(slide.get("subtitle",""),100) if slide.get("subtitle") else None
        for element in slide.get("elements",[])[:4]:
            for field,limit in (("heading",42),("label",42),("body",180),("subtext",180)):
                if element.get(field): element[field]=_clean_model_copy(element[field],limit)
    return payload

class PresentationOrchestrator:
    """Deterministic pipeline; replace stages with provider-backed agents incrementally."""
    def generate(self, request: CreatePresentationRequest, progress=None) -> PresentationSpec:
        def stage(name, value):
            if progress: progress(name, value)
        stage("Brief Classification Agent — analyzing prompt structure", 8); topic=request.topic.strip(); title=_clean_model_copy(topic,52).rstrip(".")
        brief_agent=BriefInterpreterAgent()
        prompt_classification=brief_agent.classify(topic)
        brief=brief_agent.interpret(topic, request.slide_count)
        if brief.deck_title:
            title=_clean_model_copy(brief.deck_title,52).rstrip(".")
        # A structured prompt is a stronger instruction than the UI's default
        # slider.  It is especially important when the slider still says six
        # but the prompt explicitly defines "Slide 1" through "Slide 5".
        if brief.is_structured:
            requested_brief_count=max(slide.slide_number for slide in brief.slides)
            request=request.model_copy(update={"slide_count":requested_brief_count})
        selected_provider=(request.provider or "").lower()
        if selected_provider in {"nvidia", "gemini", "ollama"}:
            try:
                stage("Theme Agent — selecting a visual system", 18)
                resolved_theme=resolve_theme(request.theme, topic)
                prompt=f'''Create a professional {request.slide_count}-slide PowerPoint deck specification.
Topic: {topic}\nAudience: {request.audience}\nTone: {request.tone}\nLanguage: {request.language}\nTheme: {resolved_theme.name}
Return one JSON object with these top-level fields: title, subtitle, topic, objective, target_audience, language, theme, slides. The `theme` value must be exactly "{resolved_theme.name}". Each slide must contain slide_number, title, layout_type, purpose, elements, and visual_spec. Each element contains type, heading, and body. visual_spec contains icon_concept, image_required, image_prompt, and stock_query.
Valid layouts: title_slide, section_slide, step_workflow, feature_grid, architecture_layers, comparison, timeline, process_flow, dashboard, two_column, key_metrics, summary, content_with_visual. Include exactly {request.slide_count} consecutively numbered slides. Use 2–3 elements per content slide; use four only for a true comparison. Each heading must be under 42 characters and each body under 120 characters. Write takeaway-style titles that make a point, not generic section labels. Every slide needs an icon_concept. Request image_required only for the cover and at most two content slides where an image materially helps. image_prompt must describe the visual only: no text, logos, UI, or watermark. stock_query must be a concise 3–6 word Unsplash search query, with no brand names.'''
                # The previous fixed 6,000-token budget made a three-slide deck
                # unnecessarily slow and prone to timing out on reasoning models.
                token_budget=max(1800, min(4000, request.slide_count * 550 + 600))
                settings=get_settings()
                # A structured brief always uses one canonical model call per
                # slide: a full-deck call could silently omit its contracts.
                slide_by_slide=brief.is_structured or selected_provider in {"gemini", "ollama"} or settings.nvidia_slide_by_slide_enabled
                if slide_by_slide:
                    spec=SlideContentAgent().generate(request, resolved_theme.name, StorylineAgent(), provider=selected_provider, brief=brief, progress=stage)
                    spec.design_system=resolved_theme
                else:
                    stage("Content Agent — drafting presentation specification", 28)
                    generated=normalize_slide_copy(LLMGateway.from_settings(selected_provider,request.model).generate_json(prompt,max_tokens=token_budget))
                    generated["design_system"]=resolved_theme.model_dump()
                    spec=PresentationSpec.model_validate(generated)
                stage("Storyline Agent — assigning narrative roles", 70)
                storyline_plan=StorylineAgent().apply(spec)
                # The design pass owns only composition and visual direction;
                # slide wording remains the responsibility of the content and
                # QA stages.
                stage("Design Director Agent — selecting layouts and visuals", 78)
                design_plan=DesignDirectorAgent().apply(spec, provider=selected_provider, model=request.model)
                stage("Presentation QA Agent — checking copy and layout budgets", 87)
                qa_report=PresentationQAAgent().validate_and_recompose(spec)
                provider_label={"gemini":"Gemini", "nvidia":"NVIDIA", "ollama":"Ollama"}[selected_provider]
                spec.metadata["generation_provider"]=selected_provider
                spec.metadata["generation_model"]=request.model or "configured default"
                spec.metadata["agent_trace"]=[
                    trace("Brief Classification Agent", "completed", "Classified the request before generation routing.", prompt_classification.model_dump()),
                    trace(
                        "Slide Content Agent" if slide_by_slide else "Content & Storyline Agent",
                        "completed",
                        f"{provider_label} generated one validated canonical slide per request." if slide_by_slide else f"{provider_label} generated the validated canonical deck specification.",
                        {"slide_count":len(spec.slides),"title":spec.title,"provider":selected_provider,"requests":len(spec.slides) if slide_by_slide else 1},
                    ),
                    trace("Storyline Agent","completed","Assigned a narrative role to every slide before visual composition.",storyline_plan.model_dump()),
                    trace("Design Director Agent","completed","Selected slide silhouettes, visual priorities, and motion-ready reveal sequences.",design_plan.model_dump()),
                    trace("Theme Agent","completed","Applied deterministic renderer tokens for the selected theme.",{"theme":spec.design_system.name}),
                    trace("Visual Director","completed","Assigned native-shape visual treatments from each slide specification.",{"treatments":[s.visual_spec.get("treatment","native_shapes") for s in spec.slides]}),
                    trace("Presentation QA Agent","completed","Recomposed overlong copy into complete slide-sized points.",qa_report),
                ]
                stage("Slide Composer Agent — preparing editable slide specification",92); return spec
            except Exception as exc:
                # A provider outage must never prevent usable deck generation.
                # Store a bounded, credential-free diagnosis so the UI tells the
                # user whether this was configuration, access, timeout, or JSON.
                fallback_reason=str(exc)[:300] or type(exc).__name__
                if selected_provider != "ollama" and settings.ollama_fallback_enabled and settings.ollama_model:
                    try:
                        stage("LOCAL_FALLBACK", 55)
                        # Keep the local fallback slide-by-slide as well.
                        # Previously it was asked for a whole deck without the
                        # canonical schema, which made a valid Ollama JSON
                        # response fail later during Pydantic validation.
                        spec=SlideContentAgent().generate(
                            request,
                            resolved_theme.name,
                            StorylineAgent(),
                            provider="ollama",
                            brief=brief,
                            progress=stage,
                        )
                        spec.design_system=resolved_theme
                        stage("Storyline Agent — assigning narrative roles",70)
                        storyline_plan=StorylineAgent().apply(spec)
                        stage("Design Director Agent — selecting layouts and visuals",78)
                        design_plan=DesignDirectorAgent().apply(spec)
                        stage("Presentation QA Agent — checking copy and layout budgets",87)
                        qa_report=PresentationQAAgent().validate_and_recompose(spec)
                        spec.metadata["generation_provider"]="ollama_fallback"
                        spec.metadata["generation_model"]=settings.ollama_model
                        spec.metadata["provider_fallback_reason"]=fallback_reason
                        spec.metadata["agent_trace"]=[
                            trace("Brief Classification Agent", "completed", "Classified the request before generation routing.", prompt_classification.model_dump()),
                            trace(f"{selected_provider.title()} Content Agent", "fallback", f"{selected_provider.title()} did not produce a usable structured deck; local Ollama continued the job.", {"reason":fallback_reason}),
                            trace("Local Ollama Content Agent", "completed", "Generated one validated canonical slide per request locally.", {"model":settings.ollama_model, "slide_count":len(spec.slides), "ollama_requests":len(spec.slides)}),
                            trace("Storyline Agent", "completed", "Assigned a narrative role to every slide before visual composition.", storyline_plan.model_dump()),
                            trace("Design Director Agent", "completed", "Selected slide silhouettes and visual priorities.", design_plan.model_dump()),
                            trace("Presentation QA Agent", "completed", "Recomposed overlong copy into complete slide-sized points.", qa_report),
                        ]
                        stage("Slide Composer Agent — preparing editable slide specification",92); return spec
                    except Exception as ollama_exc:
                        fallback_reason=f"{selected_provider.title()}: {fallback_reason}; Ollama: {str(ollama_exc)[:180]}"
            else:
                fallback_reason=""
        else:
            fallback_reason=""
        stage("Content Validation Agent — preparing safe deterministic content", 28); stage("Storyline Agent — planning the narrative", 42)
        theme=resolve_theme(request.theme, topic)
        stage("Theme Agent — selecting a visual system", 55); stage("Design Director Agent — selecting layouts and visuals", 66)
        slides=[]
        if brief.is_structured:
            slides=[brief_slide.seed() for brief_slide in brief.slides]
            # Preserve a complete requested deck even when a provider fails.
            # Missing slide numbers receive the normal deterministic treatment.
            existing={slide.slide_number for slide in slides}
            for number in range(1, request.slide_count+1):
                if number not in existing:
                    slides.append(SlideSpec(slide_number=number,title=f"{title}: Key insight",purpose="Explain one decision-relevant idea.",layout_type=LayoutType.feature_grid))
            slides.sort(key=lambda slide: slide.slide_number)
        elif "kubernetes" in topic.lower() and "monolith" in topic.lower():
            slides=[
                SlideSpec(slide_number=1,title="Kubernetes vs Monolithic Architecture",subtitle="Choose based on change rate, operating maturity, and scale.",layout_type=LayoutType.title_slide,purpose="Frame the enterprise architecture decision.",visual_spec={"icon_concept":"architecture"}),
                SlideSpec(slide_number=2,title="Start with the operating model",layout_type=LayoutType.two_column,purpose="The right architecture reflects how the organization delivers software.",elements=[SlideElement(heading="Kubernetes fits",body="Independent services, frequent releases, and a platform team can justify the operating overhead."),SlideElement(heading="A monolith fits",body="A cohesive product, stable demand, and a small team benefit from a simpler operating model.")],visual_spec={"icon_concept":"team"}),
                SlideSpec(slide_number=3,title="The trade-off is speed versus complexity",layout_type=LayoutType.feature_grid,purpose="Compare the cost of change with the cost of operating the platform.",elements=[SlideElement(heading="Delivery speed",body="Kubernetes enables independent releases when services can evolve separately."),SlideElement(heading="Operating load",body="Clusters require observability, security, deployment, and incident capabilities."),SlideElement(heading="Scaling profile",body="Scale individual services only when demand patterns truly differ.")],visual_spec={"icon_concept":"scale"}),
                SlideSpec(slide_number=4,title="Kubernetes pays off at sustained scale",layout_type=LayoutType.feature_grid,purpose="Adopt it when organizational and technical conditions reinforce each other.",elements=[SlideElement(heading="Release cadence",body="Teams deploy multiple services often and need isolated delivery paths."),SlideElement(heading="Platform maturity",body="Engineers can own automation, observability, security, and reliability."),SlideElement(heading="Variable demand",body="Workloads need independent scaling or resilient multi-environment deployment.")],visual_spec={"icon_concept":"deploy"}),
                SlideSpec(slide_number=5,title="A monolith remains the efficient default",layout_type=LayoutType.feature_grid,purpose="Simplicity is an advantage when it matches the business context.",elements=[SlideElement(heading="One product core",body="Most changes touch the same domain model and release together."),SlideElement(heading="Small operations team",body="A focused team can ship safely without maintaining a platform layer."),SlideElement(heading="Predictable demand",body="The application scales as one unit without costly resource contention.")],visual_spec={"icon_concept":"system"}),
                SlideSpec(slide_number=6,title="Choose the simplest architecture that fits",layout_type=LayoutType.summary,purpose="Adopt Kubernetes only when its flexibility creates measurable business value.",elements=[SlideElement(heading="Choose Kubernetes",body="When service autonomy and scale outweigh platform cost."),SlideElement(heading="Choose monolith",body="When speed comes from a simpler codebase and operating model."),SlideElement(heading="Reassess deliberately",body="Use delivery friction and demand signals, not fashion, to trigger change.")],visual_spec={"icon_concept":"architecture"}),
            ][:request.slide_count]
            for number,slide in enumerate(slides, start=1): slide.slide_number=number
        else:
            layouts=[LayoutType.title_slide, LayoutType.feature_grid, LayoutType.two_column, LayoutType.feature_grid, LayoutType.key_metrics, LayoutType.summary]
            for number in range(1, request.slide_count+1):
                layout=layouts[min(number-1, len(layouts)-1)] if number != request.slide_count else LayoutType.summary
                if number==1: heading=title; purpose="Set context"; elements=[SlideElement(type="text", body=f"A {request.tone.lower()} briefing for {request.audience}.")]
                elif number==request.slide_count: heading="Key takeaways"; purpose="Close with action"; elements=[SlideElement(type="bullet",body=f"Focus investment and attention on the highest-value opportunities in {topic}."),SlideElement(type="bullet",body="Align stakeholders around the next practical decision."),SlideElement(type="bullet",body="Measure progress and refine the approach.")]
                else:
                    heading=f"{topic}: {['Context and opportunity','Core building blocks','How it works','Signals of success','Recommended approach'][min(number-2,4)]}"
                    purpose="Explain one decision-relevant idea"; elements=[SlideElement(type="card",heading="What matters",body=f"The most important consideration for {topic.lower()} in this context."),SlideElement(type="card",heading="Why now",body="A concise rationale grounded in audience needs and business outcomes."),SlideElement(type="card",heading="Practical implication",body="A clear action that can be tested, owned, and measured.")]
                slides.append(SlideSpec(slide_number=number,title=heading,layout_type=layout,purpose=purpose,elements=elements,visual_spec={"treatment":"native_shapes"}))
        stage("COMPOSING",82); spec=PresentationSpec(title=title,subtitle=f"{request.tone} presentation",topic=topic,target_audience=request.audience,language=request.language,theme=theme.name,slides=slides,design_system=theme)
        storyline_plan=StorylineAgent().apply(spec)
        design_plan=DesignDirectorAgent().apply(spec)
        stage("Presentation QA Agent — checking copy and layout budgets", 82)
        qa_report=PresentationQAAgent().validate_and_recompose(spec)
        spec.metadata["generation_provider"]="fallback" if fallback_reason else "deterministic"
        if fallback_reason:
            spec.metadata["provider_fallback_reason"]=fallback_reason
            spec.metadata["provider_fallback_from"]=selected_provider
        spec.metadata["agent_trace"]=[
            trace("Content Research Agent","completed","Extracted the topic, audience, and requested tone.",{"topic":topic,"audience":request.audience,"tone":request.tone}),
            trace("Brief Classification Agent", "completed", "Classified the request before generation routing.", prompt_classification.model_dump()),
            trace("Brief Interpreter Agent", "completed", "Converted explicit slide instructions into protected content and layout contracts.", {"structured":brief.is_structured, "locked_slides":[slide.slide_number for slide in brief.slides], "resolved_slide_count":request.slide_count}),
            trace("Content Validation Agent","completed","Applied concise, presentation-safe deterministic copy.",{"content_policy":"three concise decision-oriented points per content slide"}),
            trace("Storyline Agent","completed","Assigned a varied narrative arc before slide layouts were selected.",storyline_plan.model_dump()),
            trace("Theme Agent","completed","Resolved the selected theme into deterministic design tokens.",{"theme":theme.name,"primary_color":theme.primary_color}),
            trace("Design Director Agent","completed","Selected varied slide silhouettes and motion-ready reveal sequences.",design_plan.model_dump()),
            trace("Visual Director Agent","completed","Selected native editable PowerPoint shapes rather than flattened images.",{"treatment":"native_shapes"}),
            trace("Slide Composer Agent","completed","Composed canonical SlideSpec objects for PPTX and web preview.",{"titles":[s.title for s in slides]}),
            trace("Presentation QA Agent","completed","Recomposed copy and checked each layout against its readable-content budget.",qa_report),
        ]
        stage("Slide Composer Agent — preparing editable slide specification",92); return spec
    def edit_slide(self, spec: PresentationSpec, slide_number: int, instruction: str) -> PresentationSpec:
        copy=spec.model_copy(deep=True); slide=copy.slides[slide_number-1]; slide.metadata["last_edit_instruction"]=instruction
        provider=copy.metadata.get("generation_provider")
        configured_model=copy.metadata.get("generation_model")
        if provider in {"nvidia", "gemini", "ollama", "ollama_fallback"}:
            try:
                provider_name="ollama" if provider=="ollama_fallback" else provider
                model=None if configured_model in {None, "configured default"} else configured_model
                prompt=f'''Rewrite exactly one PowerPoint slide as valid JSON according to the requested adjustment.
Adjustment: {instruction}
Current slide JSON: {slide.model_dump_json()}
Return only a JSON object with title, subtitle, layout_type, purpose, elements, visual_spec, and metadata. Keep the same slide_number and preserve concise, readable content. Do not change any other slide.'''
                max_tokens=get_settings().gemini_max_output_tokens if provider_name=="gemini" else 1400
                generated=LLMGateway.from_settings(provider_name, model).generate_json(prompt, max_tokens=max_tokens, temperature=.1)
                replacement=SlideSpec.model_validate({
                    **generated,
                    "slide_number":slide.slide_number,
                    "visual_spec":{**slide.visual_spec, **(generated.get("visual_spec") or {})},
                    "metadata":{**slide.metadata, **(generated.get("metadata") or {}), "last_edit_instruction":instruction},
                })
                copy.slides[slide_number-1]=replacement
                copy.metadata["last_slide_edit_provider"]=provider_name
                return copy
            except Exception:
                # A single-slide editing failure must not discard a user's
                # requested deterministic adjustment.
                copy.metadata["last_slide_edit_provider"]="deterministic fallback"
        if "title" in instruction.lower(): slide.title=instruction.split(":",1)[-1].strip()[:100] or slide.title
        if any(x in instruction.lower() for x in ("visual", "diagram", "architecture")):
            slide.layout_type=LayoutType.architecture_layers; slide.visual_spec={"treatment":"layered_native_diagram"}
        if "simpl" in instruction.lower() or "short" in instruction.lower(): slide.elements=slide.elements[:2]
        return copy
