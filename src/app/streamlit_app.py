"""Streamlit chat interface for the AI Newsletter Curator."""

import streamlit as st

from src.app.chat import NewsletterRAG
from src.storage.database import init_db

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Newsletter Curator",
    page_icon="📰",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
@st.cache_resource
def _init_db():
    init_db()


@st.cache_resource
def _get_rag() -> NewsletterRAG:
    return NewsletterRAG()


_init_db()
rag = _get_rag()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # list of {"role": str, "content": str}

if "sources" not in st.session_state:
    st.session_state.sources = {}  # turn_index → list[dict]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📰 AI Newsletter Curator")
    st.caption("Ask anything about your newsletter archive.")
    st.divider()

    n_results = st.slider(
        "Chunks to retrieve per query",
        min_value=4,
        max_value=20,
        value=8,
        help="More chunks = more context but potentially noisier answers.",
    )

    show_sources = st.toggle("Show sources", value=True)

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.sources = {}
        st.rerun()

    st.divider()
    st.caption(
        "Run ingestion to update your archive:\n"
        "```\npython scripts/run_ingestion.py --source all --days 7\n```"
    )


# ---------------------------------------------------------------------------
# Chat display
# ---------------------------------------------------------------------------
st.title("Ask your newsletter archive")

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Show sources beneath each assistant turn
        if show_sources and msg["role"] == "assistant" and i in st.session_state.sources:
            chunks = st.session_state.sources[i]
            if chunks:
                with st.expander("Sources", expanded=False):
                    seen: set[str] = set()
                    for chunk in chunks:
                        meta = chunk["metadata"]
                        chunk_type = meta.get("type", "email")
                        if chunk_type == "article":
                            label = meta.get("title") or meta.get("url", "Unknown article")
                            detail = meta.get("url", "")
                        else:
                            label = meta.get("subject", "Newsletter")
                            detail = meta.get("sender_email", "")

                        key = label + detail
                        if key in seen:
                            continue
                        seen.add(key)

                        if chunk_type == "article" and detail:
                            st.markdown(f"- [{label}]({detail})")
                        else:
                            st.markdown(f"- **{label}** — {detail}")


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
if prompt := st.chat_input("Ask about RAG architectures, recent LLM papers, AI tools…"):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Build conversation history (exclude current prompt, already appended)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
    ]

    # Retrieve and generate
    with st.chat_message("assistant"):
        with st.spinner("Searching your archive…"):
            try:
                answer, chunks = rag.answer(
                    query=prompt,
                    conversation_history=history,
                    n_results=n_results,
                )
            except Exception as exc:
                answer = f"Sorry, something went wrong: {exc}"
                chunks = []

        st.markdown(answer)

        turn_index = len(st.session_state.messages)  # index of the reply we're about to add
        st.session_state.sources[turn_index] = chunks

        if show_sources and chunks:
            with st.expander("Sources", expanded=False):
                seen: set[str] = set()
                for chunk in chunks:
                    meta = chunk["metadata"]
                    chunk_type = meta.get("type", "email")
                    if chunk_type == "article":
                        label = meta.get("title") or meta.get("url", "Unknown article")
                        detail = meta.get("url", "")
                    else:
                        label = meta.get("subject", "Newsletter")
                        detail = meta.get("sender_email", "")

                    key = label + detail
                    if key in seen:
                        continue
                    seen.add(key)

                    if chunk_type == "article" and detail:
                        st.markdown(f"- [{label}]({detail})")
                    else:
                        st.markdown(f"- **{label}** — {detail}")

    st.session_state.messages.append({"role": "assistant", "content": answer})
