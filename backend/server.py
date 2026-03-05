import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
import os
import json
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("WARNING: GEMINI_API_KEY is not set in environment or .env file.")

# Set up Gemini
gemini_client = genai.Client(api_key=api_key)

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    suggested_parts: list = []

# Initialize Embedding Model & Qdrant Client globally to avoid reloading on every request
try:
    print("Starting server... loading embedding model")
    embedding_model = SentenceTransformer('all-mpnet-base-v2')
    # Using cloud qdrant database
    qdrant_client = QdrantClient(
        url=os.environ.get("QDRANT_URL"),
        api_key=os.environ.get("QDRANT_API_KEY"),
    )
except Exception as e:
    print(f"Error initializing models/db: {e}")

SYSTEM_PROMPT = """You are a helpful and expert customer support agent for PartSelect.com.
You ONLY answer questions about Refrigerator and Dishwasher appliances and their replacement parts.

CRITICAL INSTRUCTIONS:
1. DO NOT direct the user to go to the PartSelect.com website to check compatibility or find manuals. YOU MUST ANSWER THEIR QUESTION DIRECTLY IN THE CHAT using the provided context.
2. If the user asks about compatibility, explicitly state whether it is compatible or not based on the context. If the context says it fits, say "Yes, this part is compatible".
3. **If the user asks how to install a part or for troubleshooting advice, ALWAYS begin your response by directing them to their specific appliance's owner's manual or user guide first. Then, provide the general guidelines.**
4. When providing installation instructions or general guidelines, format them neatly as a bulleted or numbered list.
5. If there is an 'Installation Video' link in the context, you MUST provide that YouTube link in your response so the user can watch it.

Context is the absolute truth. Use it.
Tone: Professional, helpful, specific. Format your answers in markdown.
"""

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    user_query = request.message

    # 1. Embed user query
    query_vector = embedding_model.encode(user_query).tolist()

    # 2. Search Qdrant
    try:
        query_response = qdrant_client.query_points(
            collection_name="partselect_parts",
            query=query_vector,
            limit=5 # Fetch multiple to ensure we get a hit
        )
        search_results = query_response.points
    except Exception as e:
        print(f"Error searching Qdrant: {e}")
        search_results = []


    # 3. Compile context and extract matched parts for the frontend
    context_str = ""
    suggested_parts = []

    for hit in search_results:
        # Lower threshold to guarantee finding the contextual mock parts even for short queries
        if hit.score > 0.0:
            payload = hit.payload
            part_number = payload.get('part_number', 'N/A')
            title = payload.get('title', '')
            desc = payload.get('description', '')
            compat = payload.get('compatibility', '')
            trouble = payload.get('troubleshooting', '')
            video = payload.get('installation_video', '')
            url = payload.get('url', '')

            context_str += f"---\nPart Number: {part_number}\nTitle: {title}\nDescription: {desc}\nCompatibility: {compat}\nTroubleshooting: {trouble}\nInstallation Video: {video}\nUrl: {url}\n"

            suggested_parts.append({
                "part_number": part_number,
                "title": title,
                "description": desc,
                "url": url
            })

    # Limit suggested parts returned to frontend to top 2 to not overwhelm UI
    suggested_parts = suggested_parts[:2]

    # 4. Construct Prompt for Gemini
    full_prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context_str}\n\nUser Question: {user_query}\n\nAgent Response:"

    # 5. Call Gemini
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt,
        )
        reply_text = response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        reply_text = f"I'm sorry, I'm having trouble connecting to my brain right now. ({e})"

    return ChatResponse(reply=reply_text, suggested_parts=suggested_parts)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
