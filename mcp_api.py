from fastapi import FastAPI, Request
from pydantic import BaseModel
import mysql.connector
import os
from dotenv import load_dotenv
import random

load_dotenv()

app = FastAPI()

# DB config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'playtonight')

# LLM request format
class ChatRequest(BaseModel):
    messages: list

@app.post("/v1/chat/completions")
async def chat_with_mcp(request: ChatRequest):
    query = request.messages[-1]['content'].lower()

    # Connect to DB
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor(dictionary=True)

    if "random" in query:
        cursor.execute("SELECT * FROM games ORDER BY RAND() LIMIT 1")
    else:
        like = f"%{query}%"
        cursor.execute("SELECT * FROM games WHERE name LIKE %s OR tags LIKE %s OR genres LIKE %s ORDER BY RAND() LIMIT 1", (like, like, like))

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result:
        content = f"🎮 Try **{result['name']}**!\nGenres: {result['genres']}\nTags: {result['tags']}"
    else:
        content = "Aww, I couldn’t find anything that matches that vibe, nya~ 🥺"

    return {
        "id": "chatcmpl-playtonight-001",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }