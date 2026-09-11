import os, time, uuid, httpx, streamlit as st
from datetime import datetime, timezone
import streamlit.components.v1 as components
from app.schemas.presentation import PresentationSpec
from app.rendering.web_renderer import render_slide_html
st.set_page_config(page_title="SlideWeaver",page_icon="▣",layout="wide")
API=os.getenv("API_URL","http://localhost:8000")
PROJECT_GITHUB_URL="https://github.com/Akompalwad/ppt_builder"
GITHUB_PROFILE_URL="https://github.com/Akompalwad"
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] {
    background:
      radial-gradient(circle at 77% 3%, rgba(82, 87, 255, .18), transparent 25%),
      radial-gradient(circle at 33% 18%, rgba(35, 234, 199, .12), transparent 26%),
      linear-gradient(145deg, #070b14 0%, #0a1222 48%, #07111b 100%);
    color: #dce9f5;
  }
  [data-testid="stHeader"] { background: transparent; }
  [data-testid="stMainBlockContainer"] {
    max-width: 1380px;
    padding-top: 2.4rem;
    background-image: linear-gradient(rgba(103, 224, 211, .025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(103, 224, 211, .025) 1px, transparent 1px);
    background-size: 32px 32px;
  }
  [data-testid="stAppViewContainer"] h1,
  [data-testid="stAppViewContainer"] h2,
  [data-testid="stAppViewContainer"] h3 { color: #effaff; }
  [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] p,
  [data-testid="stAppViewContainer"] label { color: #b8cbe0; }
  [data-testid="stAppViewContainer"] [data-testid="stTextArea"] textarea,
  [data-testid="stAppViewContainer"] [data-testid="stTextInput"] input {
    background: rgba(7, 20, 35, .78);
    color: #effaff;
    border-color: rgba(77, 224, 207, .34);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
  }
  [data-testid="stAppViewContainer"] [data-testid="stButton"] > button[kind="primary"] {
    border: 1px solid rgba(74, 242, 209, .76);
    background: linear-gradient(105deg, #137a81, #3149ad);
    box-shadow: 0 9px 28px rgba(23, 196, 192, .23);
  }
  [data-testid="stAppViewContainer"] [data-testid="stExpander"],
  [data-testid="stAppViewContainer"] [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(12, 27, 45, .56);
    border-color: rgba(90, 221, 209, .20);
  }
  [data-testid="stSidebar"] {
    background:
      radial-gradient(circle at 14% 0%, rgba(45, 225, 202, .20), transparent 27%),
      radial-gradient(circle at 90% 18%, rgba(104, 87, 255, .19), transparent 29%),
      linear-gradient(160deg, #07111f 0%, #0b1728 51%, #07101d 100%);
    border-right: 1px solid rgba(94, 224, 210, .20);
  }
  [data-testid="stSidebar"] > div:first-child {
    background-image: linear-gradient(rgba(103, 224, 211, .035) 1px, transparent 1px),
      linear-gradient(90deg, rgba(103, 224, 211, .035) 1px, transparent 1px);
    background-size: 24px 24px;
  }
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
  [data-testid="stSidebar"] label { color: #c5d6e9; }
  [data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div,
  [data-testid="stSidebar"] [data-testid="stTextInput"] input,
  [data-testid="stSidebar"] [data-testid="stSlider"] {
    border-color: rgba(77, 224, 207, .35) !important;
  }
  [data-testid="stSidebar"] [data-testid="stButton"] > button,
  [data-testid="stSidebar"] [data-testid="stLinkButton"] a {
    min-height: 2.6rem;
    border: 1px solid rgba(70, 232, 211, .40) !important;
    border-radius: .65rem !important;
    background: linear-gradient(110deg, rgba(31, 82, 103, .50), rgba(32, 43, 92, .54)) !important;
    color: #e8ffff !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.08), 0 8px 22px rgba(0,0,0,.18);
    transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
  }
  [data-testid="stSidebar"] [data-testid="stButton"] > button:hover,
  [data-testid="stSidebar"] [data-testid="stLinkButton"] a:hover {
    border-color: #38f5d0 !important;
    box-shadow: 0 0 0 2px rgba(56,245,208,.13), 0 10px 26px rgba(0,0,0,.27);
    transform: translateY(-1px);
  }
  [data-testid="stSidebar"] hr { border-color: rgba(93, 225, 208, .24); }
  .sidebar-console {
    margin: -.55rem 0 1.3rem;
    padding: 1rem;
    border: 1px solid rgba(78, 234, 212, .30);
    border-radius: .82rem;
    background: linear-gradient(135deg, rgba(16, 44, 63, .78), rgba(17, 21, 59, .72));
    box-shadow: 0 14px 34px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.08);
  }
  .sidebar-console .label { color: #63f4d7; font-size: .68rem; font-weight: 800; letter-spacing: .16em; }
  .sidebar-console .name { margin-top: .25rem; color: #f4fbff; font-size: 1.28rem; font-weight: 750; letter-spacing: -.03em; }
  .sidebar-console .status { margin-top: .55rem; color: #abc3d8; font-size: .72rem; }
  .sidebar-console .dot { display:inline-block; width:.48rem; height:.48rem; margin-right:.42rem; border-radius:50%; background:#39f3c5; box-shadow:0 0 12px #39f3c5; }
</style>
""", unsafe_allow_html=True)

@st.dialog("About SlideWeaver")
def about_slideweaver():
    st.subheader("SlideWeaver")
    st.write("An AI-assisted workspace for creating polished, editable PowerPoint presentations.")
    st.markdown(f"**Developer:** [Ajay Kompalwad]({GITHUB_PROFILE_URL})")
    st.link_button("Open developer profile", GITHUB_PROFILE_URL, use_container_width=True)
    st.link_button("Open project repository", PROJECT_GITHUB_URL, use_container_width=True)

st.title("SlideWeaver")
st.caption("Professional, editable presentations — generated asynchronously.")
st.caption("Testing mode: presentation history is tied to this browser session until Google sign-in is enabled.")
if "access_session_id" not in st.session_state:
    st.session_state.access_session_id=uuid.uuid4().hex
ACCESS_HEADERS={"X-SlideWeaver-Session":st.session_state.access_session_id}

def retention_countdown(expires_at: str | None) -> str:
    """Human-readable remaining retention time for the presentation library."""
    if not expires_at:
        return "Expiry unavailable"
    try:
        expires=datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires=expires.replace(tzinfo=timezone.utc)
        remaining=int((expires-datetime.now(timezone.utc)).total_seconds())
    except ValueError:
        return "Expiry unavailable"
    if remaining <= 0:
        return "Expired"
    days, remainder=divmod(remaining, 86400)
    hours, remainder=divmod(remainder, 3600)
    minutes=max(1, remainder // 60)
    if days:
        return f"T− {days}d {hours}h"
    if hours:
        return f"T− {hours}h {minutes}m"
    return f"T− {minutes}m"

@st.dialog("My presentations")
def presentation_library(history: list[dict]):
    completed=[item for item in history if item.get("status")=="COMPLETED"]
    if not completed:
        st.info("Completed decks will appear here.")
        return
    st.caption("Files are removed automatically when their retention time reaches zero.")
    for item in completed:
        with st.container(border=True):
            left, right=st.columns([4, 1])
            left.markdown(f"**{item['title']}**")
            left.caption(f"Updated {item['updated_at'][:10]} · {retention_countdown(item.get('file_expires_at'))}")
            if right.button("Open", key=f"open_library_{item['id']}", use_container_width=True):
                st.session_state.job={"presentation_id":item["id"]}
                st.rerun()
try:
    access=httpx.post(f"{API}/api/access/claim",headers=ACCESS_HEADERS,timeout=5)
    if access.status_code == 429:
        st.error("Login after sometime — user limit is exceeded at this time.")
        st.stop()
    access.raise_for_status()
except httpx.HTTPError:
    st.error("Could not verify testing access. Start the API and try again.")
    st.stop()
with st.sidebar:
    st.markdown("""<div class="sidebar-console"><div class="label">AI PRESENTATION STUDIO</div><div class="name">SLIDEWEAVER</div><div class="status"><span class="dot"></span>SYSTEM READY</div></div>""", unsafe_allow_html=True)
    # Local Ollama remains an opt-in server-side contingency only. Users choose
    # between the two supported cloud agent sources.
    provider=st.selectbox("Provider",["Gemini","NVIDIA"])
    theme=st.selectbox("Theme",["Auto","Cyber Dark","Minimalist White","Corporate Blue"]); count=st.slider("Slides",3,10,6)
    audience=st.text_input("Audience","General audience"); tone=st.selectbox("Tone",["Professional","Executive","Educational","Persuasive"])
    include_images=st.checkbox("Use topic-specific Unsplash visuals",value=True,help="Uses Unsplash when configured; at most three visuals per deck. Native editable visuals remain the fallback.")
    if include_images:
        try:
            image_status=httpx.get(f"{API}/api/llm/image-status",headers=ACCESS_HEADERS,timeout=5).json()
            if image_status.get("ready"):
                st.caption(f"Visual source: {image_status['provider'].title()} ready")
            else:
                st.warning(image_status.get("message", "Topic-specific visuals are unavailable."))
        except (httpx.HTTPError, ValueError):
            st.caption("Visual source status is temporarily unavailable.")
    st.divider()
    history=None
    completed=[]
    try:
        history_response=httpx.get(f"{API}/api/presentations",headers=ACCESS_HEADERS,timeout=5,follow_redirects=True)
        history_response.raise_for_status()
        history=history_response.json()
        if not isinstance(history, list):
            raise ValueError("Presentation history response was not a list")
        completed=[item for item in history if item["status"]=="COMPLETED"]
        if completed:
            st.caption(f"{len(completed)} saved deck{'s' if len(completed) != 1 else ''} · files expire automatically")
    except (httpx.HTTPError, ValueError):
        st.caption("Presentation history is temporarily unavailable.")
    with st.container(key="sidebar-action-rail", gap=6):
        if history is not None:
            if st.button(f"📚  My presentations ({len(completed)})", use_container_width=True):
                presentation_library(history)
        else:
            st.button("📚  My presentations", use_container_width=True, disabled=True)
        if st.button("ⓘ  About SlideWeaver", use_container_width=True):
            about_slideweaver()
        st.markdown(
            f'''<a href="{GITHUB_PROFILE_URL}" target="_blank" rel="noopener noreferrer"
            aria-label="GitHub profile: Akompalwad"
            style="display:flex;align-items:center;justify-content:center;gap:8px;width:100%;padding:.62rem .75rem;
            border:1px solid rgba(70,232,211,.40);border-radius:.65rem;color:#e8ffff;text-decoration:none;font-weight:600;
            background:linear-gradient(110deg,rgba(31,82,103,.50),rgba(32,43,92,.54));box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 8px 22px rgba(0,0,0,.18);">
            <img src="https://github.githubassets.com/favicons/favicon.svg" alt="GitHub" width="18" height="18">Akompalwad</a>''',
            unsafe_allow_html=True,
        )
topic=st.text_area("Describe the presentation you want to create",placeholder="e.g. A board-ready AI-agent strategy")
if st.button("Generate presentation",type="primary",disabled=not topic.strip()):
    try:
        if provider in {"NVIDIA", "Gemini"}:
            provider_id=provider.lower()
            check=httpx.get(f"{API}/api/llm/status",params={"provider":provider_id},headers=ACCESS_HEADERS,timeout=45)
            if check.status_code != 200:
                st.error(f"{provider} is unavailable or the selected model is not enabled. No job was started.")
                st.stop()
        r=httpx.post(f"{API}/api/presentations",json={"topic":topic,"slide_count":count,"theme":theme,"provider":provider.lower(),"audience":audience,"tone":tone,"include_external_images":include_images},headers=ACCESS_HEADERS,timeout=10); r.raise_for_status(); st.session_state.job=r.json()
    except httpx.HTTPStatusError as exc:
        # A validation error (for example a malformed structured brief) is a
        # reachable API returning useful feedback, not a connectivity failure.
        try:
            detail=exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail=exc.response.text
        st.error(f"The API rejected this request: {detail}")
    except httpx.HTTPError:
        st.error("Could not reach the API. Check that the SlideWeaver API service is running.")
if job:=st.session_state.get("job"):
    if job.get("job_id"):
        st.info(f"Generation job: {job['job_id']}")
        st.button("Refresh job status", key="refresh_job")
    try:
        if job.get("job_id"):
            status=httpx.get(f"{API}/api/jobs/{job['job_id']}",headers=ACCESS_HEADERS,timeout=5).json()
        else:
            opened=httpx.get(f"{API}/api/presentations/{job['presentation_id']}",headers=ACCESS_HEADERS,timeout=5).json()
            status={"status":opened["status"],"progress":100 if opened["status"]=="COMPLETED" else 0,"current_stage":opened["status"]}
        st.progress(status["progress"],text=status["current_stage"])
        if status["status"] in {"QUEUED", "RUNNING"}:
            st.caption(f"Active work: {status['current_stage']}")
        if status["status"] == "QUEUED" and (queue:=status.get("queue")):
            ahead=queue.get("jobs_ahead",0)
            depth=queue.get("queue_depth",0)
            st.info(f"Queued: {ahead} job{'s' if ahead != 1 else ''} ahead · queue depth {depth}")
        if status["status"]=="COMPLETED":
            deck=httpx.get(f"{API}/api/presentations/{job['presentation_id']}",headers=ACCESS_HEADERS).json(); st.success("Presentation ready")
            generation_metadata=deck["spec"].get("metadata",{})
            generation_provider=generation_metadata.get("generation_provider")
            if generation_provider == "fallback":
                reason=deck["spec"].get("metadata",{}).get("provider_fallback_reason","unknown provider error")
                source=generation_metadata.get("provider_fallback_from","The selected provider").replace("_"," ").title()
                st.warning(f"{source} failed during generation; this deck was built with the deterministic fallback. Reason: {reason}")
            elif generation_provider in {"nvidia", "gemini"}:
                st.caption(f"Generated with {generation_provider.title()} ({generation_metadata.get('generation_model')}).")
            elif generation_provider in {"ollama", "ollama_fallback"}:
                st.caption("The selected cloud source was unavailable; the server completed the deck using its configured contingency.")
            if expires_at:=deck["spec"].get("metadata",{}).get("file_expires_at"): st.caption(f"Generated files expire: {expires_at}")
            preview_spec=PresentationSpec.model_validate(deck["spec"])
            preview_key=f"preview_slide_{job['presentation_id']}"
            if preview_key not in st.session_state: st.session_state[preview_key]=1
            st.caption("Live slide preview")
            buttons=st.columns(len(preview_spec.slides))
            for number, column in enumerate(buttons, start=1):
                if column.button(f"{number:02d}",key=f"{preview_key}_{number}",use_container_width=True): st.session_state[preview_key]=number
            selected=st.session_state[preview_key]
            st.caption(f"Slide {selected}: {preview_spec.slides[selected-1].title}")
            components.html(render_slide_html(preview_spec,selected),height=630,scrolling=False)
            st.subheader(f"Edit slide {selected}")
            edit_job_key=f"slide_edit_job_{job['presentation_id']}"
            completed_notice_key=f"slide_edit_notice_{job['presentation_id']}"
            if notice:=st.session_state.pop(completed_notice_key,None):
                st.success(notice)
            pending_edit=st.session_state.get(edit_job_key)
            if pending_edit:
                try:
                    edit_job=httpx.get(f"{API}/api/jobs/{pending_edit['job_id']}",headers=ACCESS_HEADERS,timeout=5).json()
                    if edit_job["status"] == "COMPLETED":
                        st.session_state.pop(edit_job_key,None)
                        st.session_state[preview_key]=pending_edit["slide_number"]
                        st.session_state[completed_notice_key]=f"Slide {pending_edit['slide_number']} updated. The live preview and editable PPTX now use the new version."
                        st.rerun()
                    if edit_job["status"] == "FAILED":
                        st.session_state.pop(edit_job_key,None)
                        st.error(edit_job.get("error_message") or "The slide adjustment could not be applied.")
                    else:
                        st.info(f"Editing slide {pending_edit['slide_number']}: {edit_job['current_stage']}")
                        st.progress(edit_job["progress"], text=edit_job["current_stage"])
                        if edit_job["status"] == "QUEUED" and (queue:=edit_job.get("queue")):
                            ahead=queue.get("jobs_ahead",0)
                            depth=queue.get("queue_depth",0)
                            st.caption(f"Queued: {ahead} job{'s' if ahead != 1 else ''} ahead · queue depth {depth}")
                        st.caption("The existing preview remains available until the updated version is ready.")
                        time.sleep(2)
                        st.rerun()
                except (httpx.HTTPError, KeyError, ValueError):
                    st.warning("Checking the slide edit status…")
            slide_instruction=st.text_area(
                "Describe the correction or adjustment",
                placeholder="Example: Shorten the title, make the comparison clearer, and use an architecture diagram.",
                key=f"slide_instruction_{job['presentation_id']}_{selected}",
            )
            if st.button("Apply slide adjustment",type="primary",disabled=bool(pending_edit) or not slide_instruction.strip(),key=f"edit_{job['presentation_id']}_{selected}"):
                try:
                    edit=httpx.post(
                        f"{API}/api/presentations/{job['presentation_id']}/slides/{selected}/edit",
                        params={"instruction":slide_instruction.strip()},headers=ACCESS_HEADERS,timeout=10,
                    )
                    edit.raise_for_status()
                    st.session_state[edit_job_key]={"job_id":edit.json()["job_id"],"slide_number":selected}
                    st.rerun()
                except httpx.HTTPStatusError as exc:
                    detail=exc.response.text[:300] or f"HTTP {exc.response.status_code}"
                    st.error(f"The slide adjustment was rejected: {detail}")
                except httpx.HTTPError as exc:
                    st.error(f"Could not reach the API while applying the adjustment: {exc}")
            trace=deck["spec"].get("metadata",{}).get("agent_trace",[])
            if trace:
                st.subheader("Agent run details")
                for item in trace:
                    with st.expander(f"{item['agent']} · {item['status']}"):
                        st.write(item["summary"])
                        st.json(item["output"])
            else:
                st.info("This presentation was generated before agent tracing was enabled. Generate a new deck to see agent output.")
            assets=deck["spec"].get("metadata",{}).get("asset_generation",[])
            if assets:
                st.subheader("Visual asset status")
                for asset in assets:
                    if asset.get("status") == "generated":
                        st.success(f"Slide {asset['slide_number']}: {asset.get('source','visual')} asset generated")
                    else:
                        st.warning(f"Visual generation skipped: {asset.get('reason','unknown reason')}")
            for slide in deck["spec"]["slides"]:
                with st.expander(f"{slide['slide_number']}. {slide['title']}"):
                    st.write(slide["purpose"])
                    for item in slide["elements"]: st.markdown(f"- **{item.get('heading') or 'Insight'}** — {item.get('body') or ''}")
            st.link_button("Download editable PPTX",f"{API}/api/presentations/{job['presentation_id']}/download?slideweaver_session={st.session_state.access_session_id}")
        elif status["status"] in {"QUEUED", "RUNNING"}:
            st.caption("Generation is running. This page refreshes automatically every two seconds; you may also leave and return later.")
            time.sleep(2)
            st.rerun()
    except (httpx.HTTPError, KeyError, ValueError): st.warning("Waiting for job status…")
