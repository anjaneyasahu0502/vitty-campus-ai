import hashlib
import json
from pathlib import Path

import chromadb
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_FILE = DATA_DIR / "vit_info.txt"
TICKETS_FILE = DATA_DIR / "maintenance_tickets.json"
CHROMA_PATH = BASE_DIR / "chroma_db"
COLLECTION_NAME = "vit_chennai_data_gemini"
EMBEDDING_MODEL = "gemini-embedding-001"
CHAT_MODEL = "gemini-3.8-flash"

SYSTEM_INSTRUCTION = """
You are "VITTy", the official AI assistant for students at VIT Chennai.

Responsibilities:
1. Answer general hostel/campus questions accurately using [RETRIEVED CONTEXT].
2. When a student requests maintenance help, collect Block Name, Room Number,
   and Issue Description, then call `file_maintenance_ticket`.
3. Confirm the ticket ID after the tool succeeds.

Rules:
1. Stay polite, helpful, and concise.
2. If the context does not contain the answer, say that you do not have that
   information and suggest contacting the relevant official department.
"""


@st.cache_resource
def get_clients():
    client = genai.Client()
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

    if not KNOWLEDGE_FILE.exists():
        raise FileNotFoundError(f"Knowledge file not found: {KNOWLEDGE_FILE}")

    knowledge_text = KNOWLEDGE_FILE.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(knowledge_text.encode("utf-8")).hexdigest()
    chunks = [chunk.strip() for chunk in knowledge_text.split("\n\n") if chunk.strip()]

    collection_metadata = collection.metadata or {}
    if collection_metadata.get("source_hash") != source_hash:
        if collection.count():
            chroma_client.delete_collection(COLLECTION_NAME)
            collection = chroma_client.create_collection(name=COLLECTION_NAME)

        embeddings = embed_texts(client, chunks, "RETRIEVAL_DOCUMENT")
        collection.add(
            ids=[f"doc_{index}" for index in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
        )
        collection.modify(metadata={"source_hash": source_hash, "embedding_model": EMBEDDING_MODEL})

    return client, collection


def embed_texts(client, texts: list[str], task_type: str) -> list[list[float]]:
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type),
    )
    return [list(embedding.values) for embedding in response.embeddings]


def retrieve_context(client, collection, query: str) -> str:
    query_embedding = embed_texts(client, [query], "RETRIEVAL_QUERY")[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=2)
    documents = results.get("documents", [[]])[0]
    return "\n---\n".join(documents)


def file_maintenance_ticket(
    block_name: str, room_number: str, issue_description: str
) -> str:
    if not all(
        isinstance(value, str) and value.strip()
        for value in (block_name, room_number, issue_description)
    ):
        return "ERROR: Block name, room number, and issue description are required."

    block_name = block_name.strip()
    room_number = room_number.strip()
    issue_description = issue_description.strip()
    ticket_key = f"{block_name}|{room_number}|{issue_description}"
    ticket_id = f"VITM-{hashlib.sha256(ticket_key.encode('utf-8')).hexdigest()[:8].upper()}"
    ticket_data = {
        "ticket_id": ticket_id,
        "block": block_name,
        "room": room_number,
        "issue": issue_description,
        "status": "Submitted to Warden/Maintenance Office",
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing_tickets = []
    if TICKETS_FILE.exists():
        try:
            existing_tickets = json.loads(TICKETS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON in {TICKETS_FILE}; ticket was not filed.") from error

    existing_tickets.append(ticket_data)
    TICKETS_FILE.write_text(json.dumps(existing_tickets, indent=4), encoding="utf-8")
    return (
        f"SUCCESS: Ticket #{ticket_id} logged for Room {room_number} "
        f"({block_name}). Issue: '{issue_description}'."
    )


TOOLS = {"file_maintenance_ticket": file_maintenance_ticket}


def send_tool_response(chat, function_name: str, result: str):
    return chat.send_message(
        types.Content(
            role="tool",
            parts=[
                types.Part.from_function_response(
                    name=function_name,
                    response={"output": result},
                )
            ],
        )
    )


st.set_page_config(page_title="VITTy - VIT Chennai Assistant", page_icon="🤖")
st.title("🤖 VITTy: Campus AI Assistant")
st.caption("Official AI Assistant for VIT Chennai | RAG & Maintenance Agent")

try:
    client, collection = get_clients()
except Exception as error:
    st.error(f"Unable to initialize VITTy: {error}")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_session" not in st.session_state:
    st.session_state.chat_session = client.chats.create(
        model=CHAT_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            tools=list(TOOLS.values()),
        ),
    )

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_input := st.chat_input("Ask VITTy or report a hostel issue..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            context = retrieve_context(client, collection, user_input)
            prompt = f"[RETRIEVED CONTEXT]:\n{context}\n\n[USER MESSAGE]:\n{user_input}"
            response = st.session_state.chat_session.send_message(prompt)

            if response.function_calls:
                for call in response.function_calls:
                    if call.name not in TOOLS:
                        raise ValueError(f"Gemini requested unknown tool: {call.name}")
                    result = TOOLS[call.name](**call.args)
                    response = send_tool_response(
                        st.session_state.chat_session, call.name, result
                    )

            answer = response.text or "I could not generate a response."
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        except Exception as error:
            st.error(f"Unable to process your request: {error}")
