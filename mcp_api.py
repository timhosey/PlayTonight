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

    if query and query != "random":
        like = f"%{query}%"
        cursor.execute(
            "SELECT * FROM games WHERE name LIKE %s OR tags LIKE %s OR genres LIKE %s ORDER BY RAND() LIMIT 1",
            (like, like, like)
        )
    else:
        cursor.execute("SELECT * FROM games ORDER BY RAND() LIMIT 1")

    result = cursor.fetchone()
    attempts = 0
    while result and not result["tags"] and not result["genres"] and attempts < 5:
        print(f"⚠️ Skipping app {result['name']} due to missing metadata...")
        if query and query != "random":
            cursor.execute(
                "SELECT * FROM games WHERE name LIKE %s OR tags LIKE %s OR genres LIKE %s ORDER BY RAND() LIMIT 1",
                (like, like, like)
            )
        else:
            cursor.execute("SELECT * FROM games ORDER BY RAND() LIMIT 1")
        result = cursor.fetchone()
        attempts += 1
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