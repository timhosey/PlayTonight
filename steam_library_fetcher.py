from dotenv import load_dotenv
import os
import requests
import time
from bs4 import BeautifulSoup
import mysql.connector

load_dotenv()

STEAM_API_KEY = os.getenv('STEAM_WEB_API_KEY')
STEAM_ID = os.getenv('STEAM_ID_64')

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'playtonight')
def save_game_to_db(app_id, name, tags, genres):
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO games (app_id, name, tags, genres)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name=VALUES(name),
                tags=VALUES(tags),
                genres=VALUES(genres)
        """, (app_id, name, ','.join(tags), ','.join(genres)))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_owned_games(api_key, steam_id):
    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
    params = {
        'key': api_key,
        'steamid': steam_id,
        'include_appinfo': 1,
        'include_played_free_games': 1,
        'format': 'json'
    }
    print("📦 Fetching owned games from Steam...")
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()['response'].get('games', [])

def get_game_details(app_id):
    url = f"https://store.steampowered.com/app/{app_id}/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    print(f"🔍 Scraping tags/genres for app {app_id}...")
    try:
        page = requests.get(url, headers=headers, timeout=10)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, 'html.parser')

        tags = [tag.text.strip() for tag in soup.select('.glance_tags.popular_tags a')]
        genres = [genre.text.strip() for genre in soup.select('div.details_block a[href*="genre"]')]

        return {'tags': tags, 'genres': genres}
    except Exception as e:
        print(f"⚠️ Error fetching {app_id}: {e}")
        return {'tags': [], 'genres': []}

def get_existing_app_ids():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor()
    cursor.execute("SELECT app_id FROM games")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return set(row[0] for row in rows)

def main():
    games = get_owned_games(STEAM_API_KEY, STEAM_ID)
    print(f"🎮 You own {len(games)} games!\n")

    existing_ids = get_existing_app_ids()
    print(f"📁 Skipping {len(existing_ids)} already in DB")

    for game in games:
        app_id = game['appid']
        if app_id in existing_ids:
            continue  # Skip if already in DB

        name = game.get('name', 'Unknown')
        details = get_game_details(app_id)
        save_game_to_db(app_id, name, details['tags'], details['genres'])
        print(f"✅ Saved {name} ({app_id}) to DB")
        print()
        time.sleep(2)  # Respect Steam servers 💖

if __name__ == '__main__':
    main()