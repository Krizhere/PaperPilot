
from dotenv import load_dotenv
load_dotenv()

import os
import tempfile
from langchain_community.document_loaders import PyPDFLoader, PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_community.vectorstores import Chroma
from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
import streamlit as st


# ---------------- Session State ----------------

if "document_uploaded" not in st.session_state:
    st.session_state.document_uploaded = False

if "agent" not in st.session_state:
    st.session_state.agent = None

if "vector_store" not in st.session_state:
    st.session_state.vector_store = None

if "messages" not in st.session_state:
    st.session_state.messages = []


# ---------------- Document Processing ----------------

def process_document(path):

    # Load PDFs from the directory
    loader = PyPDFDirectoryLoader(path)
    docs = loader.load()

    if not docs:
        raise ValueError("No readable PDF documents were found.")

    # Split documents into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    chunks = splitter.split_documents(docs)

    # Create embeddings
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # Create Chroma vector store
    vector_db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings
    )

    # Initialize Groq LLM
    llm = ChatGroq(
        model="openai/gpt-oss-20b"
    )

    # Retrieval tool
    @tool
    def retrieve_context(query: str) -> str:
        """Retrieve relevant passages from the uploaded PDF documents."""

        retrieved_docs = vector_db.similarity_search(
            query=query,
            k=3
        )

        if not retrieved_docs:
            return "No relevant information was found."

        context = "\n\n".join(
            doc.page_content for doc in retrieved_docs
        )

        return context

    system_prompt = """
    You are a helpful PDF question-answering assistant.

    Use the retrieve_context tool to find information from uploaded PDFs
    before answering questions about their contents.

    Answer using the retrieved information. If the answer is not present
    in the documents, clearly state that you could not find it.
    Do not invent facts or claim that the documents say something
    that was not retrieved.
    """

    memory = InMemorySaver()

    agent = create_agent(
        model=llm,
        tools=[retrieve_context],
        system_prompt=system_prompt,
        checkpointer=memory
    )

    st.session_state.vector_store = vector_db
    st.session_state.agent = agent
    st.session_state.document_uploaded = True


# ---------------- Upload UI ----------------

st.title("PaperPilot: PDF RAG Chatbot")

if not st.session_state.document_uploaded:

    uploaded_files = st.file_uploader(
        "Select PDF Files",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded_files and st.button("Process PDFs"):

        try:
            with st.spinner("Processing PDFs..."):

                # Temporary directory for this upload batch
                with tempfile.TemporaryDirectory() as temp_dir:

                    for file in uploaded_files:
                        file_path = os.path.join(
                            temp_dir, file.name
                        )

                        with open(file_path, "wb") as f:
                            f.write(file.getvalue())

                    process_document(temp_dir)

            st.success("PDFs processed successfully!")
            st.rerun()

        except Exception as e:
            st.error(f"Error processing PDFs: {e}")

            
## chat ui

if st.session_state.document_uploaded and st.session_state.agent:
    for message in st.session_state.messages:
        role = message.get("role")
        content = message.get("content")
        st.chat_message(role).markdown(content)


    query = st.chat_input("Ask anything related to uploaded documents....")
    if query:
        st.session_state.messages.append({"role":"user", "content":query})

        st.chat_message("user").markdown(query)
        response = st.session_state.agent.invoke(
            {"messages":[{"role":"user", "content":query}]},
            {"configurable":{"thread_id":1}}
        )

        answer = response["messages"][-1].content
        st.chat_message("ai").markdown(answer)
        st.session_state.messages.append({"role":"ai", "content":answer})
