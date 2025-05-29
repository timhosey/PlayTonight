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
    min_playtime: Optional[int] = None
    max_playtime: Optional[int] = None

class RefineRequest(BaseModel):
    text: str

class RefinedQuery(BaseModel):
    query: str

@app.post("/refine")
async def refine_query(body: RefineRequest):
    text = body.text.lower()
    all_keywords = list(cached_tags.union(cached_genres))
    best_matches = process.extract(text, all_keywords, limit=10)
    keywords = [match for match, score in best_matches if score > 80]

    print(f"🛠️ Refine request: text='{text}' → tags={keywords}")

    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)

    if keywords:
        placeholders = ' OR '.join(["tags LIKE %s OR genres LIKE %s"] * len(keywords))
        values = []
        for keyword in keywords:
            kw = f"%{keyword}%"
            values.extend([kw, kw])
        sql = f"SELECT * FROM games WHERE ({placeholders}) AND tags != '' AND genres != '' ORDER BY RAND() LIMIT 5"
        cursor.execute(sql, values)
        games = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"results": games, "query": " ".join(keywords)}
    else:
        fallback_keywords = process.extract(text, all_keywords, limit=5)
        fallback_suggestions = [match for match, score in fallback_keywords if score > 60]
        print(f"⚠️ No strong match. Suggestions: {fallback_suggestions}")
        cursor.execute("SELECT * FROM games WHERE tags != '' AND genres != '' ORDER BY RAND() LIMIT 5")
        games = cursor.fetchall()
        cursor.close()
        conn.close()
        return {
            "results": games,
            "query": "random",
            "fallback_suggestions": fallback_suggestions,
            "note": "No confident tag/genre match found. Using fallback options for consideration."
        }


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

    playtime_conditions = []
    params = []

    if query and query != "random":
        like = f"%{query}%"
        base_sql = "SELECT * FROM games WHERE (name LIKE %s OR tags LIKE %s OR genres LIKE %s)"
        params.extend([like, like, like])
    else:
        base_sql = "SELECT * FROM games WHERE 1=1"

    if body and body.min_playtime is not None:
        playtime_conditions.append("playtime_forever >= %s")
        params.append(body.min_playtime)
    if body and body.max_playtime is not None:
        playtime_conditions.append("playtime_forever <= %s")
        params.append(body.max_playtime)

    playtime_sql = " AND ".join(playtime_conditions)
    final_sql = f"{base_sql} AND tags != '' AND genres != ''"
    if playtime_sql:
        final_sql += f" AND {playtime_sql}"
    final_sql += f" ORDER BY RAND() LIMIT {limit}"

    cursor.execute(final_sql, params)
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return [{
        "name": row["name"],
        "genres": row["genres"],
        "tags": row["tags"],
        "debug": {
            "query": query,
            "limit": limit,
            "min_playtime": body.min_playtime if body else None,
            "max_playtime": body.max_playtime if body else None
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