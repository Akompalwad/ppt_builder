import zipfile

from app.schemas.presentation import CreatePresentationRequest
from app.agents.orchestrator import PresentationOrchestrator, auto_theme_for_topic
from app.agents.storyline_agent import StorylineAgent
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
