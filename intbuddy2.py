import os
os.environ["STREAMLIT_DISABLE_WATCHDOG_WARNINGS"] = "true"
os.environ["STREAMLIT_WATCH_MODE"] = "poll"
import streamlit as st
import asyncio
import os
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain.chains import ConversationalRetrievalChain
from data_preprocessor import clean_and_structure, json_to_documents
from code360 import fetch_all_interviews as fetch_interview_data
from prompt import get_prompt
from pdfgen import pdfgenerator  # Must return BytesIO or bytes PDF

# 🔐 Setup API key
os.environ["GOOGLE_API_KEY"] = "AIzaSyAfNUg3nn1UaW1uzjXypquW2RJfXreKkrU"

import os
import subprocess

# Download + unzip chromedriver manually (first run only)
CHROMEDRIVER_PATH = "/tmp/chromedriver"

if not os.path.exists(CHROMEDRIVER_PATH):
    print("⬇️ Downloading correct chromedriver...")
    subprocess.run([
        "wget",
        "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/120.0.6099.224/linux64/chromedriver-linux64.zip",
        "-O", "/tmp/chromedriver.zip"
    ])
    subprocess.run(["unzip", "/tmp/chromedriver.zip", "-d", "/tmp/"])
    subprocess.run(["chmod", "+x", "/tmp/chromedriver-linux64/chromedriver"])
    subprocess.run(["cp", "/tmp/chromedriver-linux64/chromedriver", CHROMEDRIVER_PATH])


import os

# 💣 Force overwrite any previously set WDM_CACHE_DIR
if 'WDM_CACHE_DIR' in os.environ:
    print("⚠️ Overwriting existing WDM_CACHE_DIR:", os.environ['WDM_CACHE_DIR'])

os.environ['WDM_CACHE_DIR'] = '/tmp/wdm'
print("✅ Final WDM_CACHE_DIR =", os.environ['WDM_CACHE_DIR'])



def debug_paths():
    chromium_path = "/usr/bin/chromium"
    chromedriver_path = "/usr/lib/chromium/chromedriver"

    st.write("✅ chromium exists:", os.path.exists(chromium_path))
    st.write("✅ chromedriver exists:", os.path.exists(chromedriver_path))

debug_paths()

# 🧠 Ensure event loop exists
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# 🧠 Cached LLM
@st.cache_resource
def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0.3,
        max_tokens=None,
        timeout=None,
        max_retries=2
    )

# 🧠 Cached embedding model
@st.cache_resource
def get_embeddings():
    return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-exp-03-07")

# 📦 Vectorstore + raw data loader
@st.cache_resource(show_spinner="Fetching and embedding interview data...")
def load_vectorstore(company: str, role: str, pages: int):
    df = fetch_interview_data(company, role, pages)
    raw_text = df['description'].str.cat(sep=' ')
    structured = clean_and_structure(raw_text)
    chunks = json_to_documents(structured)
    docs = [Document(page_content=chunk) for chunk in chunks]
    embeddings = get_embeddings()
    vectorstore = FAISS.from_documents(docs, embeddings)
    return vectorstore, df, structured

# 🎯 Page Title
st.markdown("""
    <div style="text-align: center;">
        <h1 style="margin-bottom: 0.2rem; font-size: 3 rem;">PrepGenie</h1>
        <p style="color: gray; font-size: 1.4rem;">A RAG-based chatbot for interview preparation</p>
    </div>
""", unsafe_allow_html=True)




with st.sidebar:
    st.title("About PrepGenie")
    st.markdown("""
**What This App Does**

- Scrapes recent interview experiences from platforms.
- Best suited for roles like SDE-1, SDE-2, and SDE Intern.
- Builds a Retrieval-Augmented Generation (RAG) chatbot that answers your queries contextually.

**How to Use**

1. Enter a company name and a role (e.g., Microsoft, SDE-2).
2. Choose the number of pages to scrape.
   - Each page contains approximately 5–6 interview experiences.
   - More pages = more information, but longer scraping time.
   - Scrapping 3 pages nearly takes 2 minutes
**Prompts You Can Ask**

- Provide me brief summary of interview round 1
- Give me topic-wise percentage distribution of questions asked in round 2
- Major mistakes that should be avoided during interview
- Tips for interview rounds
- Number of rounds

**Important Notes**

- To end the session, type: `exit`, `quit`, or `bye`
- Ask specific and clear questions for best results
- Give the long and detailed prompt for better output
    """)


company = st.text_input("Enter Company Name", "Microsoft")
role = st.text_input("Enter Role", "SDE-2")
pages = st.number_input("Number of Pages to Scrape", min_value=1, max_value=10, value=1)

#  Session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "qa_chain" not in st.session_state:
    st.session_state.qa_chain = None

#  Load VectorStore + Build QA Chain
if st.button("Load & Build Chatbot"):
    with st.spinner("Working...",show_time=True):
        vs, df, structured = load_vectorstore(company, role, pages)
        st.session_state.structured = structured

        custom_prompt = get_prompt()
        st.session_state.qa_chain = ConversationalRetrievalChain.from_llm(
            llm=get_llm(),
            retriever=vs.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True,
            combine_docs_chain_kwargs={"prompt": custom_prompt}
        )
        st.success(f"Chatbot ready with {len(df)} interview experiences ✅")

# 💬 Chat Interface
if st.session_state.qa_chain:
    if prompt := st.chat_input("Ask a question"):
        if prompt.lower().strip() in ["exit", "quit", "bye"]:
            st.success("🧹 Ending session. Cache and chat history cleared.")
            st.cache_resource.clear()
            st.session_state.clear()
            st.stop()

        with st.spinner("Thinking..."):
            result = st.session_state.qa_chain({
                "question": prompt,
                "chat_history": st.session_state.chat_history
            })
            answer = result["answer"]
            st.session_state.chat_history.append((prompt, answer))

            for user_q, bot_a in st.session_state.chat_history:
                st.chat_message("user").write(user_q)
                st.chat_message("assistant").write(bot_a)

    # 📄 PDF generation button
    # st.markdown("---")
    # if st.button("📄 Generate PDF from Interviews"):
    #     if "structured" in st.session_state:
    #         with st.spinner("Generating PDF..."):
    #             pdf_bytes = pdfgenerator(st.session_state.structured)
    #             st.success("PDF generated successfully! 📄")
    #             st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name="interview_data.pdf", mime="application/pdf")
    #     else:
    #         st.warning("Please load and build the chatbot first.")
