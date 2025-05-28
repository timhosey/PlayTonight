from fuzzywuzzy import process
from fastapi import FastAPI, Request
from pydantic import BaseModel
import mysql.connector
import os
from dotenv import load_dotenv
import random
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

load_dotenv()

cached_tags = set()
cached_genres = set()

app = FastAPI(
    title="PlayTonight Game Recommender",
    version="1.0.0",
    description="Tool server for recommending Steam games from your library."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to just ["http://your-openwebui-ip"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def load_tag_genre_cache():
    global cached_tags, cached_genres
    print("🚀 Loading tags and genres from DB...")
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor()

    cursor.execute("SELECT tags, genres FROM games WHERE tags != '' AND genres != ''")
    rows = cursor.fetchall()
    tag_set = set()
    genre_set = set()

    for tags, genres in rows:
        if tags:
            tag_set.update(tag.strip().lower() for tag in tags.split(","))
        if genres:
            genre_set.update(genre.strip().lower() for genre in genres.split(","))

    cached_tags = tag_set
    cached_genres = genre_set

    print(f"✅ Loaded {len(cached_tags)} unique tags and {len(cached_genres)} unique genres.")
    cursor.close()
    conn.close()

# DB config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'playtonight')

# LLM request format
class ChatRequest(BaseModel):
    messages: list

class RecommendRequest(BaseModel):
    query: Optional[str] = "random"
    limit: Optional[int] = 1

class RefineRequest(BaseModel):
    text: str

class RefinedQuery(BaseModel):
    query: str

@app.post("/refine", response_model=RefinedQuery)
async def refine_query(body: RefineRequest):
    text = body.text.lower()
    all_keywords = list(cached_tags.union(cached_genres))
    best_matches = process.extract(text, all_keywords, limit=10)
    keywords = [match for match, score in best_matches if score > 80]

    print(f"🛠️ Refine request: text='{text}' → tags={keywords}")
    return {"query": " ".join(keywords) if keywords else "random"}


@app.post("/recommend")
async def recommend_game(body: Optional[RecommendRequest] = None):
    query = (body.query if body and body.query else "random").lower()
    limit = body.limit if body and body.limit and body.limit > 0 else 1
    print(f"🔍 Incoming request: query='{query}', limit={limit}")

    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)

    if query and query != "random":
        like = f"%{query}%"
        cursor.execute(
            f"SELECT * FROM games WHERE (name LIKE %s OR tags LIKE %s OR genres LIKE %s) AND tags != '' AND genres != '' ORDER BY RAND() LIMIT {limit}",
            (like, like, like)
        )
    else:
        cursor.execute(f"SELECT * FROM games WHERE tags != '' AND genres != '' ORDER BY RAND() LIMIT {limit}")

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return [{
        "name": row["name"],
        "genres": row["genres"],
        "tags": row["tags"],
        "debug": {
            "query": query,
            "limit": limit
        }
    } for row in results]

@app.get("/context")
async def get_context(limit: int = 5):
    print(f"📥 Requesting context summary for {limit} games")

    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM games WHERE tags != '' AND genres != '' ORDER BY RAND() LIMIT %s", (limit,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return {
        "summary": [f"{row['name']} — Genres: {row['genres']}, Tags: {row['tags']}" for row in results],
        "note": "Use this context to inform your game recommendation decisions."
    }

@app.get("/session_memory")
async def get_session_memory():
    print("🧠 Returning placeholder session memory")
    return {
        "user_preferences": [],
        "recent_queries": [],
        "note": "Session memory is currently stubbed. Extend this to persist preferences or history."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_api:app", host="0.0.0.0", port=8000, reload=True)