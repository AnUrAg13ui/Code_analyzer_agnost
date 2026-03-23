import streamlit as st
import requests
from typing import Any, Dict, List

st.set_page_config(page_title="AI Code Analyzer Test UI", layout="wide")

API_BASE = st.sidebar.text_input("API Base URL", value="http://127.0.0.1:8000")
owner = st.sidebar.text_input("Owner", value="")
repo = st.sidebar.text_input("Repo", value="")
pr_str = st.sidebar.text_input("PR Number", value="")

if not owner or not repo or not pr_str:
    st.sidebar.warning("Fill owner/repo/pr_number first")

run_action = st.sidebar.selectbox("Action", ["manual_trigger", "debug_analyze"])

if st.sidebar.button("Run"):
    try:
        pr_number = int(pr_str)
    except ValueError:
        st.error("PR Number must be an integer")
        st.stop()

    if run_action == "manual_trigger":
        st.info("Triggering background analysis via /analyze")
        response = requests.post(
            f"{API_BASE}/analyze",
            params={"owner": owner, "repo": repo, "pr_number": pr_number},
            timeout=120,
        )
        st.write("Status code:", response.status_code)
        st.json(response.json())

    else:
        st.info("Running synchronous debug analysis via /debug/analyze")
        response = requests.post(
            f"{API_BASE}/debug/analyze",
            params={"owner": owner, "repo": repo, "pr_number": pr_number},
            timeout=120,
        )
        st.write("Status code:", response.status_code)
        debug_data = response.json()
        st.session_state["debug_data"] = debug_data
        st.json(debug_data)

if "debug_data" in st.session_state:
    data = st.session_state["debug_data"]

    st.header("PR inputs")
    st.write(f"{data.get('owner')}/{data.get('repo')} PR #{data.get('pr_number')}")
    st.metric("Avg Confidence", f"{data.get('avg_confidence', 0.0)*100:.1f}%")
    st.metric("Findings", len(data.get("all_findings", [])))

    st.header("Context data loaded into agents")
    with st.expander("PR context", expanded=False):
        st.json(data.get("pr_context", {}))

    with st.expander("File contexts (first 5)", expanded=True):
        file_contexts = data.get("file_contexts", [])
        st.write(f"{len(file_contexts)} files")
        for f in file_contexts[:5]:
            st.markdown(f"**{f.get('file_path')}**")
            st.json(f)

    with st.expander("Memory context text", expanded=False):
        st.text_area("Memory prompt text", value=data.get("memory_context_text", ""), height=300)

    with st.expander("Agent results : Simulated pt1", expanded=True):
        agent_results = data.get("agent_results", {})
        for agent_name, agent_block in agent_results.items():
            st.subheader(agent_name)
            st.write("Summary:", agent_block.get("summary"))
            st.write("Confidence:", agent_block.get("confidence"))
            findings = agent_block.get("findings", [])
            st.write(f"Findings: {len(findings)}")
            if findings:
                st.json(findings[:10])

            debug_context = agent_block.get("debug_context", [])
            if debug_context:
                st.write(f"Agent context entries: {len(debug_context)}")
                for idx, ctx in enumerate(debug_context[:5], start=1):
                    st.markdown(f"**Context #{idx}**")
                    st.write("File:", ctx.get("file_path"))
                    st.write("Prompt snippet:", (ctx.get("prompt", "")[:500] + "...") if ctx.get("prompt") else "")
                    if ctx.get("memory_context") is not None:
                        st.write("Memory context included")
                if len(debug_context) > 5:
                    st.write(f"... plus {len(debug_context)-5} more contexts")
                with st.expander("Show full debug context JSON"):
                    st.json(debug_context)

    with st.expander("Agent initial file contexts (QA checklist)", expanded=False):
        initial_contexts = data.get("agent_initial_file_contexts", {})
        for agent_name, context_list in initial_contexts.items():
            st.subheader(agent_name)
            st.write(f"Files sent to agent: {len(context_list)}")
            for item in context_list[:5]:
                st.markdown(f"- {item.get('file_path', '(unknown file)')}")
            if len(context_list) > 5:
                st.write(f"... + {len(context_list)-5} more")
            with st.expander(f"Full {agent_name} file_contexts JSON"):
                st.json(context_list)

    with st.expander("All findings details", expanded=False):
        findings = data.get("all_findings", [])
        st.write(f"Total findings: {len(findings)}")
        for f in findings[:25]:
            st.markdown(f"**{f.get('file_path')}** — {f.get('issue_type')} {f.get('severity')}")
            st.write(f.get("description"))
            st.write("---")
