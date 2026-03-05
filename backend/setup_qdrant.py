import json
import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from qdrant_client import QdrantClient

from dotenv import load_dotenv

load_dotenv()

qdrant_client = QdrantClient(
    url=os.environ.get("QDRANT_URL"),
    api_key=os.environ.get("QDRANT_API_KEY"),
)

print(qdrant_client.get_collections())

def load_data(filepath):
    """Loads the product data from JSON."""
    with open(filepath, 'r') as f:
        return json.load(f)

def setup_qdrant():
    """Initializes Qdrant client, creates collection, and loads data."""
    print("Loading embedding model (all-mpnet-base-v2)...")
    model = SentenceTransformer('all-mpnet-base-v2')

    print("Connecting to cloud Qdrant database...")
    # Use the global qdrant_client instance defined above
    client = qdrant_client
    collection_name = "partselect_parts"

    # all-mpnet-base-v2 embeddings are 768 dimensions
    vector_size = model.get_sentence_embedding_dimension()

    # Recreate collection to ensure clean state for the case study
    if client.collection_exists(collection_name):
        print(f"Collection '{collection_name}' already exists. Recreating it.")
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
    )

    parts_data = load_data("products.json")
    points = []

    print("Generating embeddings and preparing points for Qdrant...")
    for idx, part in enumerate(parts_data):
        # We want to embed a string that contains all the rich information about the part
        # to ensure the similarity search can find it based on descriptions, compatibility, or symptoms.
        text_to_embed = f"Part Number: {part['part_number']}. Title: {part['title']}. Description: {part['description']}. Compatibility: {part['compatibility_text']}. Troubleshooting & QnA: {part['troubleshooting_text']}."

        vector = model.encode(text_to_embed).tolist()

        # Store metadata to retrieve later during RAG
        payload = {
            "part_number": part["part_number"],
            "title": part["title"],
            "description": part["description"],
            "compatibility": part["compatibility_text"],
            "troubleshooting": part["troubleshooting_text"],
            "installation_video": part.get("installation_video", ""),
            "url": part["url"]
        }

        point = PointStruct(id=idx, vector=vector, payload=payload)
        points.append(point)

    print(f"Uploading {len(points)} points to Qdrant collection '{collection_name}'...")
    client.upsert(
        collection_name=collection_name,
        points=points
    )

    print("Qdrant database setup complete!")
    print(f"Collection '{collection_name}' has been successfully populated.")

if __name__ == "__main__":
    setup_qdrant()
