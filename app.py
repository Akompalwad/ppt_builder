import os, time, uuid, httpx, streamlit as st
import streamlit.components.v1 as components
from app.schemas.presentation import PresentationSpec
from app.rendering.web_renderer import render_slide_html
st.set_page_config(page_title="SlideWeaver",page_icon="▣",layout="wide")
API=os.getenv("API_URL","http://localhost:8000")
st.title("SlideWeaver"); st.caption("Professional, editable presentations — generated asynchronously.")
st.caption("Testing mode: presentation history is tied to this browser session until Google sign-in is enabled.")
if "access_session_id" not in st.session_state:
    st.session_state.access_session_id=uuid.uuid4().hex
ACCESS_HEADERS={"X-SlideWeaver-Session":st.session_state.access_session_id}
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
    st.subheader("My presentations")
    try:
        history_response=httpx.get(f"{API}/api/presentations",headers=ACCESS_HEADERS,timeout=5,follow_redirects=True)
        history_response.raise_for_status()
        history=history_response.json()
        if not isinstance(history, list):
            raise ValueError("Presentation history response was not a list")
        completed=[item for item in history if item["status"]=="COMPLETED"]
        if completed:
            labels={f"{item['title']} · {item['updated_at'][:10]}":item["id"] for item in completed}
            chosen=st.selectbox("Open a previous deck",[""]+list(labels),label_visibility="collapsed")
            if chosen and st.button("Open selected presentation",use_container_width=True):
                st.session_state.job={"presentation_id":labels[chosen]}
                st.rerun()
        else:
            st.caption("Completed decks will appear here.")
    except (httpx.HTTPError, ValueError):
        st.caption("Presentation history is temporarily unavailable.")
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
            slide_instruction=st.text_area(
                "Describe the correction or adjustment",
                placeholder="Example: Shorten the title, make the comparison clearer, and use an architecture diagram.",
                key=f"slide_instruction_{job['presentation_id']}_{selected}",
            )
            if st.button("Apply slide adjustment",type="primary",disabled=not slide_instruction.strip(),key=f"edit_{job['presentation_id']}_{selected}"):
                try:
                    with st.status(f"Slide {selected}: processing adjustment…", expanded=True) as edit_status:
                        st.write("Updating content, applying layout QA, and rebuilding the editable PPTX.")
                        edit=httpx.post(
                            f"{API}/api/presentations/{job['presentation_id']}/slides/{selected}/edit",
                            # An AI-backed edit can take longer than the former
                            # 30-second client deadline, then still complete on
                            # the server. Keep the request open through provider
                            # generation and PPTX rendering.
                            params={"instruction":slide_instruction.strip()},headers=ACCESS_HEADERS,timeout=180,
                        )
                        edit.raise_for_status()
                        edit_status.update(label=f"Slide {selected}: completed", state="complete", expanded=False)
                    st.success(f"Slide {selected} updated. The preview and PPTX now use version {edit.json()['version_number']}.")
                    st.rerun()
                except httpx.TimeoutException:
                    st.warning("The adjustment is still being processed. Refresh this deck in a moment; do not submit it again yet.")
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
