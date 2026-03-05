import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
import os
import re
import json
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
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


def extract_ps_numbers(text):
    """Extract PS part numbers from user query."""
    return re.findall(r'PS\d{6,}', text, re.IGNORECASE)


def lookup_by_part_number(part_number):
    """Direct filter lookup in Qdrant by part number."""
    try:
        results = qdrant_client.scroll(
            collection_name="partselect_parts",
            scroll_filter=Filter(
                must=[FieldCondition(key="part_number", match=MatchValue(value=part_number))]
            ),
            limit=1,
            with_payload=True,
        )
        return results[0]  # returns list of points
    except Exception as e:
        print(f"Error in part number lookup: {e}")
        return []


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    user_query = request.message

    # 1. Check if user is asking about a specific part number
    ps_numbers = extract_ps_numbers(user_query)
    direct_matches = []
    for ps_num in ps_numbers:
        matches = lookup_by_part_number(ps_num.upper())
        direct_matches.extend(matches)

    # 2. Embed user query for semantic search
    query_vector = embedding_model.encode(user_query).tolist()

    # 3. Semantic search in Qdrant
    try:
        query_response = qdrant_client.query_points(
            collection_name="partselect_parts",
            query=query_vector,
            limit=10
        )
        search_results = query_response.points
    except Exception as e:
        print(f"Error searching Qdrant: {e}")
        search_results = []


    # 4. Compile context: direct matches first, then semantic matches (deduplicated)
    context_str = ""
    suggested_parts = []
    seen_part_numbers = set()

    def add_part_to_context(payload):
        """Helper to add a part's data to the context string and suggested parts."""
        nonlocal context_str
        part_number = payload.get('part_number', 'N/A')
        if part_number in seen_part_numbers:
            return
        seen_part_numbers.add(part_number)

        title = payload.get('title', '')
        desc = payload.get('description', '')
        price = payload.get('price', '')
        compat = payload.get('compatibility', '')
        trouble = payload.get('troubleshooting', '')
        qna = payload.get('qna', '')
        video = payload.get('installation_video', '')
        url = payload.get('url', '')

        context_str += f"---\nPart Number: {part_number}\nTitle: {title}\nDescription: {desc}\nPrice: {price}\nCompatibility: {compat}\nTroubleshooting: {trouble}\nQ&A: {qna}\nInstallation Video: {video}\nUrl: {url}\n"

        suggested_parts.append({
            "part_number": part_number,
            "title": title,
            "description": desc,
            "url": url
        })

    # Priority 1: Direct part number matches (exact filter lookup)
    for point in direct_matches:
        add_part_to_context(point.payload)

    # Priority 2: Semantic search results
    for hit in search_results:
        if hit.score > 0.15:
            add_part_to_context(hit.payload)

    # Limit suggested parts returned to frontend to top 3
    suggested_parts = suggested_parts[:3]

    # 4. Construct Prompt for Gemini
    full_prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context_str}\n\nUser Question: {user_query}\n\nAgent Response:"

    # 5. Call Gemini with retry for rate limits
    import time as _time
    reply_text = ""
    for attempt in range(3):
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=full_prompt,
            )
            reply_text = response.text
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = (attempt + 1) * 10  # 10s, 20s, 30s
                print(f"Gemini rate limit hit. Retrying in {wait}s (attempt {attempt+1}/3)...")
                _time.sleep(wait)
            else:
                print(f"Gemini Error: {e}")
                reply_text = f"I'm sorry, I'm having trouble processing your request right now. Please try again in a moment."
                break
    else:
        reply_text = "I'm sorry, the service is temporarily overloaded. Please try again in a few minutes."

    return ChatResponse(reply=reply_text, suggested_parts=suggested_parts)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
