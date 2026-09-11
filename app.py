import base64
import html
import os, time, uuid, httpx, streamlit as st
from datetime import datetime, timezone
import streamlit.components.v1 as components
from app.schemas.presentation import PresentationSpec
from app.rendering.web_renderer import render_slide_html
st.set_page_config(page_title="SlideWeaver",page_icon="▣",layout="wide")
API=os.getenv("API_URL","http://localhost:8000")
PUBLIC_API_URL=os.getenv("PUBLIC_API_URL", API).rstrip("/")
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
  .agent-pipeline {
    margin: 1rem 0 .65rem;
    padding: .85rem .15rem .7rem;
    border-top: 1px solid rgba(118, 153, 188, .22);
    border-bottom: 1px solid rgba(118, 153, 188, .15);
  }
  .agent-pipeline__header, .agent-pipeline__footer { display:flex; justify-content:space-between; gap:1rem; align-items:center; }
  .agent-pipeline__eyebrow { color:#8ca3bc; font-size:.7rem; font-weight:750; letter-spacing:.11em; text-transform:uppercase; }
  .agent-pipeline__summary { color:#dce9f5; font-size:.88rem; font-weight:650; }
  .agent-pipeline__count { color:#8ca3bc; font-size:.76rem; white-space:nowrap; }
  .agent-pipeline__rail { display:grid; grid-template-columns:repeat(var(--agent-count), minmax(0, 1fr)); margin: .9rem .15rem .8rem; }
  .agent-pipeline__stage { position:relative; min-width:0; text-align:center; }
  .agent-pipeline__stage:not(:last-child)::after { content:""; position:absolute; top:7px; left:50%; width:100%; height:1px; background:rgba(122, 145, 171, .32); }
  .agent-pipeline__stage.done:not(:last-child)::after { background:#4ade80; }
  .agent-pipeline__dot { position:relative; z-index:1; display:block; width:14px; height:14px; margin:0 auto .4rem; border-radius:50%; border:2px solid #61728a; background:#101b2b; }
  .agent-pipeline__stage.done .agent-pipeline__dot { border-color:#4ade80; background:#4ade80; box-shadow:0 0 12px rgba(74,222,128,.5); }
  .agent-pipeline__stage.active .agent-pipeline__dot { border-color:#f7b955; background:#f7b955; box-shadow:0 0 0 4px rgba(247,185,85,.13),0 0 14px rgba(247,185,85,.42); }
  .agent-pipeline__stage.attention .agent-pipeline__dot { border-color:#ff6b6b; background:#ff6b6b; box-shadow:0 0 12px rgba(255,107,107,.48); }
  .agent-pipeline__label { color:#8496ac; font-size:.69rem; font-weight:700; letter-spacing:.01em; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .agent-pipeline__stage.done .agent-pipeline__label { color:#a8e9be; }
  .agent-pipeline__stage.active .agent-pipeline__label { color:#ffe1a3; }
  .agent-pipeline__stage.attention .agent-pipeline__label { color:#ffc0c0; }
  .agent-pipeline__current { color:#a9bed1; font-size:.78rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .agent-pipeline__state { display:inline-flex; align-items:center; gap:.38rem; color:#9fb5c9; font-size:.72rem; white-space:nowrap; }
  .agent-pipeline__state i { display:inline-block; width:.42rem; height:.42rem; border-radius:50%; background:#f7b955; box-shadow:0 0 8px rgba(247,185,85,.55); }
  .agent-pipeline__state.complete i { background:#4ade80; box-shadow:0 0 8px rgba(74,222,128,.55); }
  .agent-pipeline__state.failed i { background:#ff6b6b; box-shadow:0 0 8px rgba(255,107,107,.55); }
  .signin-shell { min-height:72vh; display:flex; align-items:center; justify-content:center; padding:2rem 1rem 4rem; }
  .signin-card { width:min(100%, 480px); padding:2.7rem 2.55rem 2.25rem; border:1px solid rgba(122, 238, 219, .25); border-radius:1.25rem; text-align:center; background:linear-gradient(145deg, rgba(15, 36, 57, .91), rgba(12, 18, 48, .91)); box-shadow:0 28px 80px rgba(0,0,0,.36), inset 0 1px 0 rgba(255,255,255,.08); }
  .signin-mark { width:3.3rem; height:3.3rem; margin:0 auto 1.35rem; display:grid; place-items:center; border-radius:1rem; color:#06111c; font-size:1.35rem; font-weight:900; background:linear-gradient(135deg, #4bf0cd, #6a82ff); box-shadow:0 0 0 6px rgba(73,235,210,.08), 0 10px 30px rgba(51,209,199,.26); }
  .signin-eyebrow { color:#62efd1; font-size:.7rem; font-weight:800; letter-spacing:.16em; text-transform:uppercase; }
  .signin-card h1 { margin:.55rem 0 .7rem; color:#f4fbff; font-size:2rem; letter-spacing:-.045em; }
  .signin-card p { margin:0 auto; max-width:350px; color:#b4c6d9; font-size:.98rem; line-height:1.55; }
  .signin-google { display:flex; align-items:center; justify-content:center; gap:.75rem; margin:1.8rem 0 1.2rem; padding:.82rem 1rem; border:1px solid rgba(224,235,248,.52); border-radius:.72rem; color:#eef6ff !important; text-decoration:none !important; font-weight:700; background:rgba(255,255,255,.08); box-shadow:inset 0 1px 0 rgba(255,255,255,.09), 0 10px 22px rgba(0,0,0,.18); transition:transform .16s ease, background .16s ease, border-color .16s ease; }
  .signin-google:hover { transform:translateY(-1px); background:rgba(255,255,255,.14); border-color:#fff; }
  .signin-google svg { width:20px; height:20px; flex:0 0 auto; }
  .signin-footnote { color:#829ab1 !important; font-size:.76rem !important; }
  @media (max-width: 640px) { .signin-shell { min-height:66vh; padding:1rem 0 3rem; } .signin-card { padding:2.25rem 1.45rem 1.85rem; border-radius:1rem; } }
</style>
""", unsafe_allow_html=True)

@st.dialog("About SlideWeaver")
def about_slideweaver():
    st.subheader("SlideWeaver")
    st.write("An AI-assisted workspace for creating polished, editable PowerPoint presentations.")
    st.markdown(f"**Developer:** [Ajay Kompalwad]({GITHUB_PROFILE_URL})")
    st.link_button("Open developer profile", GITHUB_PROFILE_URL, use_container_width=True)
    st.link_button("Open project repository", PROJECT_GITHUB_URL, use_container_width=True)


@st.dialog("Share feedback")
def share_feedback():
    st.caption("Help improve SlideWeaver by sharing the result, the prompt, and any error. Do not include API keys, passwords, or private data.")
    with st.form("share_feedback_form", clear_on_submit=True):
        category=st.selectbox("What are you reporting?", ["feedback", "error", "design", "other"], format_func=lambda value: value.replace("_", " ").title())
        message=st.text_area("What happened?", placeholder="Describe what you expected and what happened instead.")
        prompt=st.text_area("Prompt that led to this result (optional)", value=st.session_state.get("topic_input", ""))
        error_details=st.text_area("Error message or technical details (optional)", placeholder="Paste the visible error text here.")
        screenshot=st.file_uploader("Screenshot (optional, PNG or JPG, maximum 3 MB)", type=["png", "jpg", "jpeg"])
        reply_to=st.text_input("Email for a reply (optional)", placeholder="you@example.com")
        submitted=st.form_submit_button("Send feedback", type="primary", use_container_width=True)
    if not submitted:
        return
    if not message.strip():
        st.error("Please describe the feedback or issue.")
        return
    payload={
        "category":category, "message":message.strip(), "prompt":prompt.strip() or None,
        "error_details":error_details.strip() or None, "reply_to":reply_to.strip() or None,
    }
    if screenshot:
        screenshot_bytes=screenshot.getvalue()
        if len(screenshot_bytes) > 3 * 1024 * 1024:
            st.error("Please choose a screenshot smaller than 3 MB.")
            return
        mime_type=screenshot.type if screenshot.type in {"image/png", "image/jpeg"} else "image/jpeg"
        payload.update({
            "screenshot_name":screenshot.name, "screenshot_mime_type":mime_type,
            "screenshot_base64":base64.b64encode(screenshot_bytes).decode("ascii"),
        })
    try:
        response=httpx.post(f"{API}/api/feedback", json=payload, headers=ACCESS_HEADERS, timeout=15)
        response.raise_for_status()
        st.success("Feedback received — thank you.")
    except httpx.HTTPStatusError as exc:
        detail=exc.response.text[:240] or f"HTTP {exc.response.status_code}"
        st.error(f"Feedback could not be submitted: {detail}")
    except httpx.HTTPError:
        st.error("Could not reach the feedback service. Please try again shortly.")


@st.dialog("Admin activity")
def admin_activity():
    st.caption("Live sessions and operational activity. Presentation content and prompts are never shown here.")
    try:
        response=httpx.get(f"{API}/api/admin/activity", headers=ACCESS_HEADERS, timeout=8)
        response.raise_for_status()
        snapshot=response.json()
    except httpx.HTTPStatusError as exc:
        st.error("This account is not authorized to view admin activity." if exc.response.status_code == 403 else "Admin activity is temporarily unavailable.")
        return
    except (httpx.HTTPError, ValueError):
        st.error("Admin activity is temporarily unavailable.")
        return
    left, middle, right=st.columns(3)
    left.metric("Active users", snapshot.get("active_users", 0))
    middle.metric("Testing limit", snapshot.get("max_active_users", 0))
    right.metric("Session window", f"{snapshot.get('session_ttl_minutes', 0)} min")
    if st.button("↻  Refresh activity", use_container_width=True):
        st.rerun()
    users=snapshot.get("users", [])
    if not users:
        st.info("No active Google sessions right now.")
        return
    for user in users:
        with st.container(border=True):
            identity, activity=st.columns([1.1, 1])
            identity.markdown(f"**{user.get('name') or 'Unknown user'}**")
            identity.caption(user.get("email") or "")
            activity.markdown(f"**{user.get('presentations', 0)}** presentations")
            activity.caption(f"Last seen: {relative_time(user.get('last_seen_at'))}")
            if latest:=user.get("latest_presentation"):
                st.caption(f"Latest deck: {latest}")
            if stage:=user.get("current_stage"):
                status=(user.get("job_status") or "unknown").title()
                st.caption(f"Latest job · {status}: {stage}")

if auth_error:=st.query_params.get("auth_error"):
    st.error(str(auth_error))
    del st.query_params["auth_error"]
if oauth_ticket:=st.query_params.get("oauth_ticket"):
    try:
        exchange=httpx.post(f"{API}/api/auth/session", params={"ticket":str(oauth_ticket)}, timeout=10)
        exchange.raise_for_status()
        st.session_state.access_session_id=exchange.json()["session_id"]
        del st.query_params["oauth_ticket"]
        st.rerun()
    except (httpx.HTTPError, KeyError, ValueError):
        st.error("Your Google sign-in could not be completed. Please try again.")
        del st.query_params["oauth_ticket"]
if "access_session_id" not in st.session_state:
    st.session_state.access_session_id=uuid.uuid4().hex
ACCESS_HEADERS={"X-SlideWeaver-Session":st.session_state.access_session_id}
try:
    auth_response=httpx.get(f"{API}/api/auth/me", headers=ACCESS_HEADERS, timeout=5)
    auth_response.raise_for_status()
    auth_info=auth_response.json()
except (httpx.HTTPError, ValueError):
    st.error("Could not check sign-in status. Start the API and try again.")
    st.stop()
if auth_info.get("mode", "").lower() == "google":
    if not auth_info.get("configured"):
        st.error("Google sign-in is enabled but not configured on this server. Add the Google OAuth settings and restart the API.")
        st.stop()
    if not auth_info.get("authenticated"):
        sign_in_url=html.escape(f"{PUBLIC_API_URL}/api/auth/google/start", quote=True)
        st.markdown(f'''<main class="signin-shell"><section class="signin-card" aria-label="Sign in to SlideWeaver">
          <div class="signin-mark">S</div><div class="signin-eyebrow">AI presentation studio</div>
          <h1>Welcome to SlideWeaver</h1>
          <p>Create editable, polished presentations and return to every deck from your own workspace.</p>
          <a class="signin-google" href="{sign_in_url}"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M21.35 12.22c0-.71-.06-1.39-.18-2.04H12v3.86h5.24a4.48 4.48 0 0 1-1.94 2.94v2.5h3.14c1.84-1.7 2.91-4.2 2.91-7.26Z"/><path fill="#34A853" d="M12 21.73c2.62 0 4.82-.87 6.38-2.35l-3.14-2.5c-.87.58-1.99.92-3.24.92-2.49 0-4.6-1.68-5.36-3.94H3.4v2.58A9.63 9.63 0 0 0 12 21.73Z"/><path fill="#FBBC05" d="M6.64 13.86A5.8 5.8 0 0 1 6.34 12c0-.64.11-1.26.3-1.86V7.56H3.4A9.7 9.7 0 0 0 2.37 12c0 1.56.37 3.04 1.03 4.44l3.24-2.58Z"/><path fill="#EA4335" d="M12 6.2c1.43 0 2.7.49 3.7 1.45l2.78-2.78C16.82 3.31 14.62 2.27 12 2.27A9.63 9.63 0 0 0 3.4 7.56l3.24 2.58C7.4 7.88 9.51 6.2 12 6.2Z"/></svg>Continue with Google</a>
          <p class="signin-footnote">We use your verified Google identity only to secure your workspace and presentation history.</p>
        </section></main>''', unsafe_allow_html=True)
        st.stop()
    st.title("SlideWeaver")
    st.caption("Professional, editable presentations — generated asynchronously.")
    st.caption(f"Signed in as {auth_info.get('name') or auth_info.get('email')}")
else:
    st.title("SlideWeaver")
    st.caption("Professional, editable presentations — generated asynchronously.")
    st.caption("Testing mode: presentation history is tied to this browser session until Google sign-in is enabled.")

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


def relative_time(timestamp: str | None) -> str:
    if not timestamp:
        return "unknown"
    try:
        moment=datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment=moment.replace(tzinfo=timezone.utc)
        seconds=max(0, int((datetime.now(timezone.utc)-moment).total_seconds()))
    except ValueError:
        return "unknown"
    if seconds < 60:
        return "just now"
    minutes=seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours=minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _pipeline_stage_index(current_stage: str, stages: list[tuple[str, tuple[str, ...]]]) -> int:
    """Find the pipeline stage represented by a backend progress message."""
    stage=current_stage.lower()
    for index, (_, keywords) in enumerate(stages):
        if any(keyword in stage for keyword in keywords):
            return index
    return -1


def render_agent_pipeline(status: dict, *, is_slide_edit: bool=False) -> None:
    """Render a compact, accessible job pipeline from the API's live stage text."""
    stages=(
        [("Content", ("slide content", "rewriting", "composing")), ("Visuals", ("visual asset", "design director", "image")), ("QA", ("qa", "quality")), ("Export", ("renderer", "pptx", "updated"))]
        if is_slide_edit else
        [("Brief", ("brief", "classification", "interpreter")), ("Theme", ("theme",)), ("Content", ("slide content", "composing", "drafting")), ("Story", ("storyline",)), ("Visuals", ("design director", "visual asset", "image")), ("QA", ("qa", "quality")), ("Export", ("renderer", "pptx", "completed"))]
    )
    job_status=str(status.get("status", "QUEUED")).upper()
    current_stage=str(status.get("current_stage") or "Waiting to start")
    progress=int(status.get("progress") or 0)
    active_index=_pipeline_stage_index(current_stage, stages)
    if active_index < 0:
        active_index=min(len(stages)-1, max(0, round(progress / 100 * (len(stages)-1))))
    failed=job_status == "FAILED"
    completed=job_status == "COMPLETED"
    queued=job_status == "QUEUED"
    stage_classes=[]
    for index, _ in enumerate(stages):
        if completed or (not queued and index < active_index):
            stage_classes.append("done")
        elif failed and index == active_index:
            stage_classes.append("attention")
        elif not queued and index == active_index:
            stage_classes.append("active")
        else:
            stage_classes.append("waiting")
    completed_count=len(stages) if completed else sum(state == "done" for state in stage_classes)
    if completed:
        summary="Presentation ready" if not is_slide_edit else "Slide update ready"
        state_class="complete"
        state_label="Complete"
    elif failed:
        summary="Generation needs attention" if not is_slide_edit else "Slide update needs attention"
        state_class="failed"
        state_label="Failed"
    elif queued:
        summary="Queued for generation" if not is_slide_edit else "Queued for slide update"
        state_class=""
        state_label="Waiting"
    else:
        summary="Generating presentation" if not is_slide_edit else "Updating slide"
        state_class=""
        state_label="In progress"
    stages_html="".join(
        f'<div class="agent-pipeline__stage {stage_classes[index]}"><span class="agent-pipeline__dot"></span><span class="agent-pipeline__label">{html.escape(label)}</span></div>'
        for index, (label, _) in enumerate(stages)
    )
    queue=status.get("queue") or {}
    queue_note=""
    if queued:
        ahead=int(queue.get("jobs_ahead", 0))
        depth=int(queue.get("queue_depth", 0))
        queue_note=f" · {ahead} ahead / depth {depth}"
    detail=status.get("error_message") if failed else current_stage
    st.markdown(
        f'''<section class="agent-pipeline" style="--agent-count:{len(stages)}">
          <div class="agent-pipeline__header"><div><div class="agent-pipeline__eyebrow">Agent pipeline</div><div class="agent-pipeline__summary">{html.escape(summary)}</div></div><div class="agent-pipeline__count">{completed_count}/{len(stages)} complete</div></div>
          <div class="agent-pipeline__rail">{stages_html}</div>
          <div class="agent-pipeline__footer"><div class="agent-pipeline__current">{html.escape(str(detail or "Waiting to start"))}</div><span class="agent-pipeline__state {state_class}"><i></i>{state_label}{queue_note}</span></div>
        </section>''',
        unsafe_allow_html=True,
    )

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
    if auth_info.get("authenticated"):
        st.caption(f"Signed in · {auth_info.get('email')}")
        if st.button("Sign out", use_container_width=True):
            try:
                httpx.post(f"{API}/api/auth/logout", headers=ACCESS_HEADERS, timeout=5).raise_for_status()
            except httpx.HTTPError:
                pass
            st.session_state.pop("access_session_id", None)
            st.rerun()
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
        if st.button("✦  Share feedback", use_container_width=True):
            share_feedback()
        if auth_info.get("is_admin") and st.button("◈  Admin activity", use_container_width=True):
            admin_activity()
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
topic=st.text_area("Describe the presentation you want to create",placeholder="e.g. A board-ready AI-agent strategy", key="topic_input")
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
        render_agent_pipeline(status)
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
                        render_agent_pipeline(edit_job, is_slide_edit=True)
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
