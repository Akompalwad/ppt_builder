import base64
import html
import os, time, uuid, httpx, streamlit as st
from datetime import datetime, timedelta, timezone
import streamlit.components.v1 as components
from app.schemas.presentation import PresentationSpec
from app.rendering.web_renderer import render_slide_html
st.set_page_config(page_title="SlideWeaver",page_icon="▣",layout="wide")
API=os.getenv("API_URL","http://localhost:8000")
PUBLIC_API_URL=os.getenv("PUBLIC_API_URL", API).rstrip("/")
PROJECT_GITHUB_URL="https://github.com/Akompalwad/ppt_builder"
GITHUB_PROFILE_URL="https://github.com/Akompalwad"
SESSION_COOKIE_NAME="slideweaver_session"
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
  [data-testid="stAppViewContainer"] [data-testid="stButton"] > button[kind="primary"]:disabled {
    opacity:1 !important;
    color:#f5f7fa !important;
    border:1px solid rgba(255,255,255,.76) !important;
    background:linear-gradient(135deg, #050505, #202020) !important;
    box-shadow:none !important;
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
    width: 100%;
    min-height: 2.6rem;
    box-sizing: border-box;
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
  .sidebar-logout-form { margin:.25rem 0 .8rem; }
  .sidebar-logout-form button {
    width:100%; min-height:2.6rem; box-sizing:border-box; cursor:pointer;
    border:1px solid rgba(70, 232, 211, .40); border-radius:.65rem;
    background:linear-gradient(110deg, rgba(31, 82, 103, .50), rgba(32, 43, 92, .54));
    color:#e8ffff; font:inherit; font-weight:600;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.08), 0 8px 22px rgba(0,0,0,.18);
  }
  .sidebar-logout-form button:hover { border-color:#38f5d0; box-shadow:0 0 0 2px rgba(56,245,208,.13), 0 10px 26px rgba(0,0,0,.27); transform:translateY(-1px); }
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
  .library-thumb { width:3.1rem; height:4rem; display:grid; place-items:center; border-radius:.55rem; color:#f7fbff; font-size:1.15rem; font-weight:850; letter-spacing:.04em; background:linear-gradient(145deg, var(--deck-accent), #111b31); border:1px solid rgba(255,255,255,.20); box-shadow:0 8px 18px rgba(0,0,0,.22); }
  .library-meta { color:#93a9bd; font-size:.78rem; line-height:1.45; }
  .library-status { display:inline-block; margin-right:.4rem; padding:.1rem .42rem; border-radius:99px; color:#aaf3d8; font-size:.67rem; font-weight:800; letter-spacing:.05em; text-transform:uppercase; background:rgba(74,222,128,.12); border:1px solid rgba(74,222,128,.28); }
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
    overview_tab, history_tab, presentations_tab, feedback_tab=st.tabs(["Overview", "Sign-in history", "Presentations & files", "Feedback & storage"])
    with overview_tab:
        left, middle, right=st.columns(3)
        left.metric("Active users", snapshot.get("active_users", 0))
        middle.metric("Testing limit", snapshot.get("max_active_users", 0))
        right.metric("Session window", f"{snapshot.get('session_ttl_minutes', 0)} min")
        actions_left, actions_right=st.columns(2)
        if actions_left.button("↻  Refresh activity", key="admin_refresh", use_container_width=True):
            st.rerun()
        if actions_right.button("Clean expired generated files", key="admin_cleanup_expired", use_container_width=True):
            try:
                cleaned=httpx.post(f"{API}/api/admin/cleanup-expired-files", headers=ACCESS_HEADERS, timeout=20)
                cleaned.raise_for_status()
                st.success(f"Removed {cleaned.json().get('removed', 0)} expired presentation folder(s).")
            except httpx.HTTPError:
                st.error("Expired-file cleanup could not be completed.")
        users=snapshot.get("users", [])
        if not users:
            st.info("No active Google sessions right now.")
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
    with history_tab:
        st.caption("Successful Google sign-ins and explicit sign-outs. This history starts when the feature is deployed.")
        filter_left, filter_right=st.columns([2, 1])
        selected_login_date=filter_left.date_input(
            "Calendar date (UTC)", value=None, key="admin_login_history_date",
            help="Leave blank to view sign-in activity from all dates.",
        )
        login_page_size=filter_right.selectbox("Rows per page", [10, 25, 50], index=0, key="admin_login_history_page_size")
        filter_value=selected_login_date.isoformat() if selected_login_date else ""
        if st.session_state.get("admin_login_history_filter") != (filter_value, login_page_size):
            st.session_state.admin_login_history_filter=(filter_value, login_page_size)
            st.session_state.admin_login_history_page=1
        login_page=st.session_state.get("admin_login_history_page", 1)
        try:
            history_response=httpx.get(
                f"{API}/api/admin/login-history",
                params={"page":login_page, "page_size":login_page_size, **({"on_date":filter_value} if filter_value else {})},
                headers=ACCESS_HEADERS,
                timeout=8,
            )
            history_response.raise_for_status()
            history_payload=history_response.json()
            history=history_payload.get("events", [])
        except (httpx.HTTPError, ValueError):
            history_payload={"page":1, "total_pages":1, "total":0}
            history=[]
            st.warning("Sign-in history is temporarily unavailable.")
        if not history:
            st.info("No sign-in events have been recorded yet.")
        for event in history:
            symbol="↗" if event.get("event") == "sign_in" else "↙"
            left, right=st.columns([3, 1])
            left.markdown(f"{symbol} **{event.get('email', 'Unknown user')}** · {str(event.get('event', '')).replace('_', ' ').title()}")
            right.caption(relative_time(event.get("created_at")))
        current_page=int(history_payload.get("page", 1))
        total_pages=int(history_payload.get("total_pages", 1))
        previous, indicator, following=st.columns([1, 2, 1])
        if previous.button("← Previous", key="admin_login_history_previous", disabled=current_page <= 1, use_container_width=True):
            st.session_state.admin_login_history_page=current_page - 1
            st.rerun()
        indicator.caption(f"Page {current_page} of {total_pages} · {history_payload.get('total', 0)} event(s)")
        if following.button("Next →", key="admin_login_history_next", disabled=current_page >= total_pages, use_container_width=True):
            st.session_state.admin_login_history_page=current_page + 1
            st.rerun()
    with presentations_tab:
        st.caption("Deck titles, requesting accounts, and the current generated PPTX location on this server.")
        presentation_page_size=st.selectbox("Rows per page", [10, 25, 50], index=0, key="admin_presentation_page_size")
        if st.session_state.get("admin_presentation_history_page_size") != presentation_page_size:
            st.session_state.admin_presentation_history_page_size=presentation_page_size
            st.session_state.admin_presentation_history_page=1
        presentation_page=st.session_state.get("admin_presentation_history_page", 1)
        try:
            presentation_response=httpx.get(
                f"{API}/api/admin/presentations",
                params={"page":presentation_page, "page_size":presentation_page_size},
                headers=ACCESS_HEADERS,
                timeout=8,
            )
            presentation_response.raise_for_status()
            presentation_payload=presentation_response.json()
            presentations=presentation_payload.get("presentations", [])
        except (httpx.HTTPError, ValueError):
            presentation_payload={"page":1, "total_pages":1, "total":0}
            presentations=[]
            st.warning("Presentation file history is temporarily unavailable.")
        if not presentations:
            st.info("No presentations have been requested yet.")
        for presentation in presentations:
            title=html.escape(str(presentation.get("title") or "Untitled presentation"))
            with st.expander(f"{title} · {str(presentation.get('status') or 'unknown').title()}"):
                st.markdown(f"**Requested by:** {presentation.get('requester_name') or 'Unknown'} · `{presentation.get('requester_email') or 'Unknown'}`")
                st.caption(f"Created {relative_time(presentation.get('created_at'))} · updated {relative_time(presentation.get('updated_at'))}")
                if presentation.get("version"):
                    st.caption(f"Version {presentation['version']} · server file: `{presentation.get('server_filename')}`")
                    st.code(presentation.get("server_path") or "", language=None)
                    if presentation.get("file_exists"):
                        st.success("PPTX file is present on the server.")
                    else:
                        st.warning("No current PPTX file is present. It may have expired or generation did not complete.")
                else:
                    st.caption("No generated PPTX version exists yet.")
        current_presentation_page=int(presentation_payload.get("page", 1))
        presentation_total_pages=int(presentation_payload.get("total_pages", 1))
        previous, indicator, following=st.columns([1, 2, 1])
        if previous.button("← Previous", key="admin_presentation_previous", disabled=current_presentation_page <= 1, use_container_width=True):
            st.session_state.admin_presentation_history_page=current_presentation_page - 1
            st.rerun()
        indicator.caption(f"Page {current_presentation_page} of {presentation_total_pages} · {presentation_payload.get('total', 0)} presentation(s)")
        if following.button("Next →", key="admin_presentation_next", disabled=current_presentation_page >= presentation_total_pages, use_container_width=True):
            st.session_state.admin_presentation_history_page=current_presentation_page + 1
            st.rerun()
    with feedback_tab:
        feedback=snapshot.get("feedback", [])
        purge_days=st.selectbox("Delete feedback older than", [7, 30, 90, 180, 365], index=1, format_func=lambda days: f"{days} days", key="feedback_purge_days")
        if st.button("Delete feedback older than selected age", key="admin_purge_feedback", use_container_width=True):
            try:
                purged=httpx.post(f"{API}/api/admin/feedback/purge", params={"older_than_days":purge_days}, headers=ACCESS_HEADERS, timeout=15)
                purged.raise_for_status()
                st.success(f"Deleted {purged.json().get('removed', 0)} old feedback report(s).")
                st.rerun()
            except httpx.HTTPError:
                st.error("Old feedback could not be deleted.")
        st.subheader(f"Recent feedback ({len(feedback)})")
        if not feedback:
            st.caption("No feedback has been submitted yet.")
        for report in feedback:
            label=f"{str(report.get('category', 'feedback')).title()} · {relative_time(report.get('created_at'))}"
            with st.expander(label):
                st.write(report.get("message") or "")
                if prompt:=report.get("prompt"):
                    st.markdown("**Prompt**")
                    st.code(prompt, language=None)
                if error_details:=report.get("error_details"):
                    st.markdown("**Error details**")
                    st.code(error_details, language=None)
                if reply_to:=report.get("reply_to"):
                    st.caption(f"Reply address: {reply_to}")
                if report.get("has_screenshot"):
                    try:
                        image=httpx.get(f"{API}/api/admin/feedback/{report['id']}/screenshot", headers=ACCESS_HEADERS, timeout=10)
                        image.raise_for_status()
                        st.image(image.content, caption="Submitted screenshot", use_container_width=True)
                    except httpx.HTTPError:
                        st.warning("The submitted screenshot is no longer available.")
                if st.button("Delete this feedback", key=f"admin_delete_feedback_{report['id']}"):
                    try:
                        deletion=httpx.delete(f"{API}/api/admin/feedback/{report['id']}", headers=ACCESS_HEADERS, timeout=10)
                        deletion.raise_for_status()
                        st.rerun()
                    except httpx.HTTPError:
                        st.error("This feedback could not be deleted.")

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
    # Streamlit session state is intentionally ephemeral: a browser refresh
    # creates a new session. The browser receives this HttpOnly cookie during
    # the Google callback, so restore its existing authenticated API session.
    try:
        saved_session_id=st.context.cookies.get(SESSION_COOKIE_NAME)
    except Exception:
        saved_session_id=None
    st.session_state.access_session_id=saved_session_id if saved_session_id else uuid.uuid4().hex
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
          <a class="signin-google" href="{sign_in_url}" target="_top"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M21.35 12.22c0-.71-.06-1.39-.18-2.04H12v3.86h5.24a4.48 4.48 0 0 1-1.94 2.94v2.5h3.14c1.84-1.7 2.91-4.2 2.91-7.26Z"/><path fill="#34A853" d="M12 21.73c2.62 0 4.82-.87 6.38-2.35l-3.14-2.5c-.87.58-1.99.92-3.24.92-2.49 0-4.6-1.68-5.36-3.94H3.4v2.58A9.63 9.63 0 0 0 12 21.73Z"/><path fill="#FBBC05" d="M6.64 13.86A5.8 5.8 0 0 1 6.34 12c0-.64.11-1.26.3-1.86V7.56H3.4A9.7 9.7 0 0 0 2.37 12c0 1.56.37 3.04 1.03 4.44l3.24-2.58Z"/><path fill="#EA4335" d="M12 6.2c1.43 0 2.7.49 3.7 1.45l2.78-2.78C16.82 3.31 14.62 2.27 12 2.27A9.63 9.63 0 0 0 3.4 7.56l3.24 2.58C7.4 7.88 9.51 6.2 12 6.2Z"/></svg>Continue with Google</a>
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
        return f"Expires in {days}d {hours}h"
    if hours:
        return f"Expires in {hours}h {minutes}m"
    return f"Expires in {minutes}m"


def library_display_title(item: dict) -> str:
    """Avoid presenting a generic creation request as the deck title."""
    title=" ".join(str(item.get("title") or "").split()).strip(" .")
    generic=title.lower()
    if not title or generic.startswith(("i would like to create", "create a presentation", "create presentation")):
        count=item.get("slide_count") or ""
        return f"{count}-slide presentation" if count else "Untitled presentation"
    return title


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
    st.caption("Your completed decks. Generated files expire automatically, but each deck remains listed here.")
    groups={"Today":[], "Yesterday":[], "Earlier":[]}
    today=datetime.now(timezone.utc).date()
    for item in completed:
        try:
            updated=datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
            updated_date=(updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc)).date()
        except (KeyError, ValueError):
            updated_date=None
        group="Today" if updated_date == today else "Yesterday" if updated_date == today - timedelta(days=1) else "Earlier"
        groups[group].append(item)
    for group, items in groups.items():
        if not items:
            continue
        st.markdown(f"#### {group}")
        for item in items:
            title=library_display_title(item)
            slide_count=item.get("slide_count") or "—"
            theme=item.get("theme") or "Custom theme"
            accent=str(item.get("accent_color") or "#2b6cb0")
            initials="".join(word[:1] for word in title.split()[:2]).upper() or "SW"
            with st.container(border=True):
                thumbnail, details, action=st.columns([0.72, 3.2, 0.85], vertical_alignment="center")
                thumbnail.markdown(f'<div class="library-thumb" style="--deck-accent:{html.escape(accent, quote=True)}">{html.escape(initials)}</div>', unsafe_allow_html=True)
                details.markdown(f"**{html.escape(title)}**")
                details.markdown(
                    f'<div class="library-meta"><span class="library-status">Ready</span>{slide_count} slides · {html.escape(str(theme))}<br>'
                    f'Updated {relative_time(item.get("updated_at"))} · {html.escape(retention_countdown(item.get("file_expires_at")))}</div>',
                    unsafe_allow_html=True,
                )
                if action.button("Open", key=f"open_library_{item['id']}", use_container_width=True):
                    # Fetch through the owner-authorized presentation endpoint
                    # rather than putting prompts into the history-list API.
                    try:
                        opened=httpx.get(f"{API}/api/presentations/{item['id']}", headers=ACCESS_HEADERS, timeout=5)
                        opened.raise_for_status()
                        original_prompt=opened.json().get("topic")
                        if isinstance(original_prompt, str) and original_prompt.strip():
                            st.session_state.topic_input=original_prompt
                    except (httpx.HTTPError, ValueError):
                        st.warning("The deck opened, but its original prompt could not be restored.")
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
# A refresh creates a new Streamlit session, while a generation continues in
# FastAPI's worker. Reattach the newest unfinished job for this signed-in user
# so the live agent pipeline and queue status immediately return.
if "job" not in st.session_state:
    try:
        active_job_response=httpx.get(f"{API}/api/presentations/active-job", headers=ACCESS_HEADERS, timeout=5)
        if active_job_response.status_code == 200:
            active_job=active_job_response.json()
            st.session_state.job={"presentation_id":active_job["presentation_id"], "job_id":active_job["id"], "status":active_job.get("status")}
    except (httpx.HTTPError, KeyError, ValueError):
        pass
with st.sidebar:
    st.markdown("""<div class="sidebar-console"><div class="label">AI PRESENTATION STUDIO</div><div class="name">SLIDEWEAVER</div><div class="status"><span class="dot"></span>SYSTEM READY</div></div>""", unsafe_allow_html=True)
    if auth_info.get("authenticated"):
        st.caption(f"Signed in · {auth_info.get('email')}")
        # This request is browser-originated (rather than server-side httpx),
        # allowing the API to delete the HttpOnly cookie as part of sign-out.
        browser_logout_url=html.escape(f"{PUBLIC_API_URL}/api/auth/logout/browser", quote=True)
        st.markdown(f'''<form class="sidebar-logout-form" action="{browser_logout_url}" method="post" target="_top">
          <button type="submit">Sign out</button>
        </form>''', unsafe_allow_html=True)
    # Local Ollama remains an opt-in server-side contingency only. Users choose
    # between the two supported cloud agent sources.
    provider=st.selectbox("Provider",["Gemini","NVIDIA"])
    theme=st.selectbox("Theme",["Auto","Cyber Dark","Minimalist White","Corporate Blue"])
    count=st.number_input("Number of slides *", min_value=3, max_value=10, value=None, step=1, help="Required. Enter an integer from 3 to 10.")
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
topic=st.text_area("Describe the presentation you want to create",placeholder="e.g. A board-ready AI-agent strategy", key="topic_input")
missing_generation_inputs=[]
if not topic.strip():
    missing_generation_inputs.append("a presentation prompt")
if count is None:
    missing_generation_inputs.append("the required number of slides in the sidebar")
current_job=st.session_state.get("job") or {}
job_in_progress=str(current_job.get("status") or "").upper() in {"QUEUED", "RUNNING"}
if job_in_progress:
    generate_help="A presentation is currently queued or generating. Wait for it to finish before starting another one."
elif missing_generation_inputs:
    generate_help="Enter " + " and ".join(missing_generation_inputs) + " to generate a presentation."
else:
    generate_help="Generate an editable PowerPoint presentation."
if st.button("Generate presentation",type="primary",disabled=bool(missing_generation_inputs) or job_in_progress,help=generate_help):
    try:
        if provider in {"NVIDIA", "Gemini"}:
            provider_id=provider.lower()
            check=httpx.get(f"{API}/api/llm/status",params={"provider":provider_id},headers=ACCESS_HEADERS,timeout=45)
            if check.status_code != 200:
                st.error(f"{provider} is unavailable or the selected model is not enabled. No job was started.")
                st.stop()
        r=httpx.post(f"{API}/api/presentations",json={"topic":topic,"slide_count":int(count),"theme":theme,"provider":provider.lower(),"audience":audience,"tone":tone,"include_external_images":include_images},headers=ACCESS_HEADERS,timeout=10); r.raise_for_status(); st.session_state.job={**r.json(), "status":"QUEUED"}
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
        job["status"]=status.get("status")
        st.session_state.job=job
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
