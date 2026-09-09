from app.schemas.presentation import CreatePresentationRequest
from app.agents.orchestrator import PresentationOrchestrator
from app.rendering.pptx_builder import build_presentation
from app.agents.qa_agent import PresentationQAAgent, summarize_point
from app.schemas.presentation import LayoutType, PresentationSpec, SlideSpec
from app.agents.design_agent import DesignDirectorAgent
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
