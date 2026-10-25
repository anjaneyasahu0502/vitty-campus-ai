import json
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
import chromadb

# 1. Load environment variables
load_dotenv()

# 2. Initialize Gemini Client & ChromaDB Vector Store
client = genai.Client()
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_FILE = DATA_DIR / "vit_info.txt"
TICKETS_FILE = DATA_DIR / "maintenance_tickets.json"
chroma_client = chromadb.PersistentClient(path=str(BASE_DIR / "chroma_db"))
collection = chroma_client.get_or_create_collection(name="vit_chennai_data_gemini")

def get_embedding(text: str) -> list[float]:
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text
    )
    return response.embeddings[0].values

def load_knowledge_base():
    if KNOWLEDGE_FILE.exists():
        with KNOWLEDGE_FILE.open("r", encoding="utf-8") as f:
            text = f.read()
        
        chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        for idx, chunk in enumerate(chunks):
            embedding = get_embedding(chunk)
            collection.upsert(
                ids=[f"doc_{idx}"],
                documents=[chunk],
                embeddings=[embedding]
            )
        print("✅ Knowledge Base Loaded into Vector DB!")

load_knowledge_base()

# --- AGENT TOOL DEFINITION ---
def file_maintenance_ticket(block_name: str, room_number: str, issue_description: str) -> str:
    """
    Files a hostel maintenance complaint ticket for a student.
    
    Args:
        block_name: The hostel block (e.g., 'MH A Block', 'LH B Block').
        room_number: The student's room number (e.g., '304', 'A-102').
        issue_description: Detailed summary of the maintenance problem (e.g., 'AC not cooling', 'Plumbing leak').
    """
    if not all(
        isinstance(value, str) and value.strip()
        for value in (block_name, room_number, issue_description)
    ):
        return "ERROR: Block name, room number, and issue description are required."

    ticket_key = f"{block_name.strip()}|{room_number.strip()}|{issue_description.strip()}"
    ticket_id = f"VITM-{hashlib.sha256(ticket_key.encode('utf-8')).hexdigest()[:8].upper()}"
    
    # Save ticket locally to a JSON file (simulating a backend database)
    ticket_data = {
        "ticket_id": ticket_id,
        "block": block_name,
        "room": room_number,
        "issue": issue_description,
        "status": "Submitted to Warden/Maintenance Office"
    }
    
    existing_tickets = []
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TICKETS_FILE.exists():
        with TICKETS_FILE.open("r", encoding="utf-8") as f:
            try:
                existing_tickets = json.load(f)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON in {TICKETS_FILE}; ticket was not filed.")
                
    existing_tickets.append(ticket_data)
    with TICKETS_FILE.open("w", encoding="utf-8") as f:
        json.dump(existing_tickets, f, indent=4)
        
    return f"SUCCESS: Ticket #{ticket_id} logged for Room {room_number} ({block_name}). Issue: '{issue_description}'."

# Map tool functions for execution
tools_dict = {
    "file_maintenance_ticket": file_maintenance_ticket
}

SYSTEM_INSTRUCTION = """
You are "VITTy", the official AI assistant for students at VIT Chennai.

Your Responsibilities:
1. Grounded QA: Answer general hostel/campus queries accurately using [RETRIEVED CONTEXT].
2. Agent Action (Maintenance Filing): When a student requests to log a complaint, fix an issue, or file a maintenance ticket:
   - Ask for missing details (Block Name, Room Number, and Issue Description).
   - Once all details are collected, call the `file_maintenance_ticket` function.
   - Confirm to the student once the ticket is generated.

Rules:
1. Stay polite, helpful, and concise.
2. If context does not contain general info, politely indicate missing records.
"""

def chat_with_bot():
    print("\n--- 🤖 Welcome to VITTy (RAG + Maintenance Agent) ---")
    print("Type 'exit' or 'quit' to end.\n")

    # Maintain conversation session
    chat = client.chats.create(
        model="gemini-3.8-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
            tools=[file_maintenance_ticket]  # Expose function tool to Gemini
        )
    )

    while True:
        user_input = input("You: ")
        if user_input.lower().strip() in ["exit", "quit"]:
            print("\nVITTy: Goodbye! Have a great day at VIT Chennai!")
            break

        if not user_input.strip():
            continue

        try:
            # 1. Retrieve RAG Context
            query_embedding = get_embedding(user_input)
            results = collection.query(query_embeddings=[query_embedding], n_results=2)
            retrieved_chunks = results["documents"][0] if results["documents"] else []
            context = "\n---\n".join(retrieved_chunks)

            augmented_prompt = f"[RETRIEVED CONTEXT]:\n{context}\n\n[USER MESSAGE]:\n{user_input}"

            # 2. Send message to Chat API
            response = chat.send_message(augmented_prompt)

            # 3. Check if Gemini invoked a Function Tool
            if response.function_calls:
                for call in response.function_calls:
                    func_name = call.name
                    func_args = call.args
                    
                    if func_name in tools_dict:
                        print(f"\n⚙️ [Agent executing tool: {func_name} with args {func_args}]...")
                        tool_result = tools_dict[func_name](**func_args)
                        
                        tool_response = types.Content(
                            role="tool",
                            parts=[
                                types.Part.from_function_response(
                                    name=func_name,
                                    response={"output": tool_result},
                                )
                            ],
                        )
                        follow_up = chat.send_message(tool_response)
                        print(f"\nVITTy: {follow_up.text}\n")
                    else:
                        raise ValueError(f"Gemini requested unknown tool: {func_name}")
            else:
                print(f"\nVITTy: {response.text}\n")

        except Exception as e:
            print(f"\n[Error]: {e}\n")

if __name__ == "__main__":
    chat_with_bot()