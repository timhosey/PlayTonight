from fastapi import FastAPI, Request
from pydantic import BaseModel
import mysql.connector
import os
from dotenv import load_dotenv
import random
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

load_dotenv()

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

def build_filters_from_query(query: str):
    filters = []
    params = []

    if "short" in query or "finish in a night" in query:
        filters.append("tags LIKE %s")
        params.append("%short%")

    if "co-op" in query or "coop" in query:
        filters.append("tags LIKE %s")
        params.append("%co-op%")

    if "not multiplayer" in query or "singleplayer only" in query:
        filters.append("tags NOT LIKE %s")
        params.append("%multiplayer%")

    if "rpg" in query:
        filters.append("genres LIKE %s")
        params.append("%rpg%")

    return filters, params

@app.post("/recommend")
async def recommend_game(body: Optional[RecommendRequest] = None):
    query = (body.query if body and body.query else "random").lower()

    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)

    filters, params = build_filters_from_query(query)

    if filters:
        where_clause = " AND ".join(filters)
        sql = f"SELECT * FROM games WHERE {where_clause} ORDER BY RAND() LIMIT 1"
        cursor.execute(sql, params)
    else:
        cursor.execute("SELECT * FROM games ORDER BY RAND() LIMIT 1")

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result:
        return {
            "name": result["name"],
            "genres": result["genres"],
            "tags": result["tags"]
        }
    else:
        return {
            "name": None,
            "genres": None,
            "tags": None
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_api:app", host="0.0.0.0", port=8000, reload=True)