import zipfile

from app.schemas.presentation import CreatePresentationRequest
from app.agents.orchestrator import PresentationOrchestrator, auto_theme_for_topic
from app.agents.storyline_agent import StorylineAgent
from app.agents.brief_agent import BriefInterpreterAgent
from app.agents.slide_content_agent import SlideContentAgent
from app.rendering.pptx_builder import build_presentation
from app.agents.qa_agent import PresentationQAAgent, summarize_point
from app.schemas.presentation import LayoutType, PresentationSpec, SlideSpec
from app.agents.design_agent import DesignDirectorAgent
from pptx import Presentation
def test_fallback_and_pptx(tmp_path):
    spec=PresentationOrchestrator().generate(CreatePresentationRequest(topic="AI adoption",slide_count=4))
    assert len(spec.slides)==4
    output=build_presentation(spec,tmp_path/"deck.pptx")
    assert output.exists() and output.stat().st_size>1000

def test_qa_keeps_complete_sentence_not_ellipsis():
    result=summarize_point("Clusters require observability, security, deployment, and incident capabilities for safe operation.", 8)
    assert result.endswith(".")
    assert "…" not in result

def test_design_director_assigns_a_cover_and_close():
    spec=PresentationOrchestrator().generate(CreatePresentationRequest(topic="Kubernetes versus monolithic architecture",slide_count=6))
    plan=DesignDirectorAgent().apply(spec)
    assert plan.decisions[0].layout.value == "title_slide"
    assert plan.decisions[-1].layout.value == "summary"

def test_design_director_records_a_visual_direction():
    spec=PresentationOrchestrator().generate(CreatePresentationRequest(topic="A product migration roadmap",slide_count=5))
    plan=DesignDirectorAgent().apply(spec)
    assert len(plan.decisions) == 5
    assert all(decision.visual_direction for decision in plan.decisions)
    assert all(decision.background_treatment for decision in plan.decisions)

def test_qa_restores_both_sides_of_a_comparison_cover():
    spec=PresentationSpec(
        title="Compare NSDL and CDSL", topic="Compare NSDL and CDSL. Which should I choose and why?",
        slides=[SlideSpec(slide_number=1, title="NSDL vs.", subtitle="A decision guide", purpose="Set the context", layout_type=LayoutType.title_slide)],
    )
    PresentationQAAgent().validate_and_recompose(spec)
    assert spec.slides[0].title == "NSDL vs. CDSL"

def test_qa_removes_unpunctuated_comparison_question_from_cover_title():
    spec=PresentationSpec(
        title="NSDL versus CDSL", topic="NSDL vs CDSL which should I choose and why",
        slides=[SlideSpec(slide_number=1, title="NSDL vs.", purpose="Choose a depository", layout_type=LayoutType.title_slide)],
    )
    PresentationQAAgent().validate_and_recompose(spec)
    assert spec.slides[0].title == "NSDL vs. CDSL"

def test_qa_does_not_turn_an_overview_request_into_a_fake_comparison():
    spec=PresentationSpec(
        title="DeckForge", topic="Create a 7-slide product and technical overview of DeckForge, an AI-powered PowerPoint generator.",
        slides=[SlideSpec(slide_number=1, title="DeckForge", purpose="Overview", layout_type=LayoutType.title_slide)],
    )
    PresentationQAAgent().validate_and_recompose(spec)
    assert spec.slides[0].title == "DeckForge"

def test_qa_replaces_private_story_instruction_with_slide_fact():
    spec=PresentationSpec(
        title="NSDL versus CDSL", topic="Compare NSDL and CDSL",
        slides=[SlideSpec(slide_number=1, title="Digital wealth", purpose="Set the decision context and stakes by explaining the importance of choosing the.", layout_type=LayoutType.content_with_visual, elements=[{"heading":"What is a depository?", "body":"A digital vault that holds shares and bonds."}])],
    )
    PresentationQAAgent().validate_and_recompose(spec)
    assert spec.slides[0].purpose == "A digital vault that holds shares and bonds."

def test_portable_gradient_background_and_long_metric_copy(tmp_path):
    spec=PresentationSpec(
        title="Cost comparison", topic="Compare costs",
        design_system={"name":"Corporate Blue", "background_color":"#FFFFFF", "surface_color":"#F7F9FC", "primary_color":"#2167C5", "secondary_color":"#6B96D0", "header_color":"#1A2D45", "text_primary":"#1A2D45", "text_secondary":"#536476", "muted_text":"#6D8092"},
        slides=[SlideSpec(
            slide_number=1, title="Cost and Efficiency Comparison", purpose="Compare practical costs", layout_type=LayoutType.key_metrics,
            visual_spec={"background_treatment":"halo"},
            elements=[
                {"heading":"NSDL: The Institutional Standard", "body":"Higher focus on institutional stability with robust security protocols for large-scale holdings."},
                {"heading":"CDSL: The Retail Favorite", "body":"Lower transaction costs and seamless digital integration for active individual traders."},
                {"heading":"Key Cost Driver", "body":"Broker and transaction charges determine the practical cost for most retail investors."},
            ],
        )],
    )
    output=build_presentation(spec,tmp_path/"portable-background.pptx")
    presentation=Presentation(output)
    text_boxes=[shape for shape in presentation.slides[0].shapes if shape.has_text_frame]
    heading=next(shape for shape in text_boxes if shape.text=="NSDL: The Institutional Standard")
    body=next(shape for shape in text_boxes if shape.text.startswith("Higher focus"))
    assert heading.top+heading.height < body.top
    with zipfile.ZipFile(output) as archive:
        assert b"a:gradFill" in archive.read("ppt/slides/slide1.xml")

def test_asymmetric_insight_uses_one_page_number_and_fits_card_body(tmp_path):
    spec=PresentationSpec(
        title="Depository choices", topic="Compare depositories",
        slides=[SlideSpec(
            slide_number=1, title="The Infrastructure of Your Wealth", purpose="Establish that the choice between NSDL and CDSL is the foundational decision.", layout_type=LayoutType.content_with_visual,
            elements=[
                {"heading":"The Regulatory Landscape", "body":"Two distinct central depositories manage your securities, ensuring safe electronic transfers."},
                {"heading":"Why the Choice Matters", "body":"Your choice affects broker compatibility and the platform experience."},
            ],
        )],
    )
    output=build_presentation(spec,tmp_path/"asymmetric.pptx")
    presentation=Presentation(output)
    text_boxes=[shape for shape in presentation.slides[0].shapes if shape.has_text_frame]
    page_numbers=[shape for shape in text_boxes if shape.text=="1"]
    body=next(shape for shape in text_boxes if shape.text.startswith("Two distinct"))
    assert len(page_numbers)==1
    assert body.top+body.height <= 3.67 * 914400

def test_storyline_uses_distinct_security_and_investor_arcs():
    def plan(topic):
        spec=PresentationSpec(title=topic, topic=topic, slides=[
            SlideSpec(slide_number=index, title=f"Slide {index}", purpose="A concrete point.", layout_type=LayoutType.feature_grid)
            for index in range(1, 7)
        ])
        return StorylineAgent().apply(spec)
    security=plan("Autonomous threat mitigation and SOC orchestration")
    investor=plan("NSDL vs CDSL: which depository should I choose?")
    assert security.arc == "security operations arc"
    assert investor.arc == "investor decision arc"
    assert [beat.preferred_recipe for beat in security.beats[1:-1]] != [beat.preferred_recipe for beat in investor.beats[1:-1]]

def test_auto_theme_is_topic_aware():
    assert auto_theme_for_topic("SOC incident response automation").name == "Security Signal"
    assert auto_theme_for_topic("NSDL versus CDSL investor choice").name == "Investor Slate"

def test_brief_interpreter_preserves_explicit_slide_contracts_in_fallback():
    prompt='''Agentic AI Alert Response Platform
Slide 1: Title Slide
Title: Autonomous Alert Triage Platform
Subtitle: Transforming SOC Operations with Agentic Incident Response
Slide 2: Core Capabilities
Layout: Feature Grid (4 items)
Topic Areas:
Autonomous Context Enrichment (correlating telemetry and indicators)
Dynamic Investigation Plans (building hypothesis-driven triage paths)
Human-in-the-Loop Safeguards (requiring analyst approval for high-risk actions)
Self-Healing Playbooks (updating detections from retrospectives)
Slide 3: Incident Response Pipeline
Layout: Step Workflow (4 sequential steps)
Steps to cover:
Alert Ingestion (streaming SIEM and EDR data)
Agent Triage (evaluating severity)
Action Execution (isolating endpoints)
Post-Mortem Audit (updating tickets)'''
    brief=BriefInterpreterAgent().interpret(prompt, 3)
    assert brief.is_structured and brief.by_number(2).layout_type == LayoutType.feature_grid
    assert len(brief.by_number(2).requirements) == 4
    # The UI can still be on its six-slide default; explicit Slide 1–3
    # instructions are the authoritative deck contract.
    spec=PresentationOrchestrator().generate(CreatePresentationRequest(topic=prompt, slide_count=6))
    assert len(spec.slides) == 3
    assert spec.slides[0].title == "Autonomous Alert Triage Platform"
    assert spec.slides[1].layout_type == LayoutType.feature_grid
    assert len(spec.slides[1].elements) == 4
    assert spec.slides[2].layout_type == LayoutType.step_workflow

def test_design_director_keeps_explicit_feature_grid_recipe():
    spec=PresentationSpec(title="Impact", topic="SOC impact", slides=[
        SlideSpec(slide_number=1, title="Cover", purpose="Start", layout_type=LayoutType.title_slide),
        SlideSpec(slide_number=2, title="Three metrics", purpose="Evidence", layout_type=LayoutType.feature_grid, metadata={"brief_layout_locked":True}),
        SlideSpec(slide_number=3, title="Locked metrics", purpose="End", layout_type=LayoutType.feature_grid, metadata={"brief_layout_locked":True}),
    ])
    DesignDirectorAgent().apply(spec)
    assert spec.slides[1].visual_spec["composition"] == "editorial insight grid"
    assert spec.slides[2].visual_spec["composition"] == "editorial insight grid"

def test_brief_classifier_distinguishes_structured_and_open_ended_prompts():
    agent=BriefInterpreterAgent()
    structured=agent.classify("Slide 1: Cover\nTitle: A platform\nSlide 2: Workflow\nLayout: Step Workflow")
    generic=agent.classify("Explain how an agentic AI security platform improves SOC operations.")
    assert structured.mode == "structured"
    assert structured.detected_slide_numbers == [1, 2]
    assert generic.mode == "open_ended"

def test_brief_interpreter_protects_embedded_json_slide_schema():
    prompt='''Use this JSON schema:
    {"title":"Agentic AI Alert Response Platform","slides":[
      {"slide_number":1,"title":"Autonomous Alert Triage Platform","subtitle":"Transforming SOC Operations","layout_type":"title_slide","elements":[]},
      {"slide_number":2,"title":"Platform Core Capabilities","layout_type":"feature_grid","elements":[
        {"id":"e1","heading":"Context Enrichment","subtext":"Correlate SIEM telemetry."},
        {"id":"e2","heading":"Investigation Plans","subtext":"Generate triage paths."},
        {"id":"e3","heading":"Approval Safeguards","subtext":"Gate high-risk actions."},
        {"id":"e4","heading":"Self-Healing Playbooks","subtext":"Learn from incidents."}]},
      {"slide_number":3,"title":"Response Pipeline","layout_type":"step_workflow","elements":[]},
      {"slide_number":4,"title":"Architecture Layers","layout_type":"architecture_layers","elements":[]},
      {"slide_number":5,"title":"Strategic SOC Impact","layout_type":"feature_grid","elements":[]}
    ]}'''
    agent=BriefInterpreterAgent()
    brief=agent.interpret(prompt, 6)
    assert agent.classify(prompt).mode == "structured"
    assert brief.deck_title == "Agentic AI Alert Response Platform"
    assert len(brief.slides) == 5
    assert brief.by_number(2).elements[0].body == "Correlate SIEM telemetry."
    spec=PresentationOrchestrator().generate(CreatePresentationRequest(topic=prompt, slide_count=6))
    assert len(spec.slides) == 5
    assert spec.title == "Agentic AI Alert Response Platform"
    assert len(spec.slides[1].elements) == 4

def test_slide_content_contract_restores_items_missing_from_model_response():
    brief=BriefInterpreterAgent().interpret('''{"slides":[{"slide_number":1,"title":"Capabilities","layout_type":"feature_grid","elements":[{"heading":"Context","subtext":"Correlate telemetry."},{"heading":"Containment","subtext":"Isolate endpoints."}]}]}''', 1)
    directive=brief.by_number(1)
    restored=SlideContentAgent._preserve_contract_elements(directive, {"elements":[{"heading":"Context","body":"Model-expanded context."}]})
    assert [item["heading"] for item in restored] == ["Context", "Containment"]
    assert restored[0]["body"] == "Model-expanded context."

def test_request_accepts_a_detailed_structured_brief():
    request=CreatePresentationRequest(topic="{" + '"slides":[],' * 700 + "}")
    assert len(request.topic) > 2_000
