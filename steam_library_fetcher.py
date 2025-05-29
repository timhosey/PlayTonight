from dotenv import load_dotenv
import os
import requests
import time
from bs4 import BeautifulSoup
import mysql.connector
from howlongtobeatpy import HowLongToBeat

load_dotenv()

STEAM_API_KEY = os.getenv('STEAM_WEB_API_KEY')
STEAM_ID = os.getenv('STEAM_ID_64')

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASS = os.getenv('DB_PASS', '')
DB_NAME = os.getenv('DB_NAME', 'playtonight')

def get_game_details_from_steamspy(app_id):
    try:
        url = f"https://steamspy.com/api.php?request=appdetails&appid={app_id}"
        response = requests.get(url, timeout=10)
        print(f"🔎 SteamSpy status for {app_id}: {response.status_code}")
        if response.status_code != 200:
            return None
        data = response.json()
        tags = list(data.get("tags", {}).keys())
        genres = data.get("genre", "").split(", ") if data.get("genre") else []
        print(f"✅ SteamSpy returned {len(tags)} tags and {len(genres)} genres for {app_id}")
        return {"tags": tags, "genres": genres}
    except Exception as e:
        print(f"💥 SteamSpy failed for {app_id}: {e}")
        return None

def save_game_to_db(app_id, name, tags, genres, playtime_minutes=0):
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO games (app_id, name, tags, genres, playtime_forever)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name=VALUES(name),
                tags=VALUES(tags),
                genres=VALUES(genres),
                playtime_forever=VALUES(playtime_forever)
        """, (app_id, name, ','.join(tags), ','.join(genres), playtime_minutes))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_game_details(app_id):
    print(f"🔍 Getting game details for app {app_id}...")

    steamspy_data = get_game_details_from_steamspy(app_id)
    if steamspy_data and (steamspy_data["tags"] or steamspy_data["genres"]):
        return steamspy_data

    print(f"🔁 Falling back to Steam page scrape for app {app_id}")
    url = f"https://store.steampowered.com/app/{app_id}/"
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"📥 Status for {app_id}: {response.status_code}")
        if response.status_code != 200:
            print(f"⚠️ Failed to fetch {app_id} - status {response.status_code}")
            return {"tags": [], "genres": []}

        soup = BeautifulSoup(response.text, 'html.parser')
        tags = [tag.text.strip() for tag in soup.select('.glance_tags.popular_tags a')]
        genres = [g.text.strip() for g in soup.select('div.details_block a[href*="genre"]')]

        print(f"✅ Steam scrape found {len(tags)} tags and {len(genres)} genres for {app_id}")
        return {"tags": tags, "genres": genres}
    except Exception as e:
        print(f"💥 Error scraping {app_id}: {e}")
        return {"tags": [], "genres": []}

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

def get_existing_app_ids():
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )
    cursor = conn.cursor()
    cursor.execute("SELECT app_id, playtime_forever, tags, genres FROM games")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row[0]: (row[1], row[2], row[3]) for row in rows}

def get_estimated_playtime_minutes(game_name):
    try:
        results = HowLongToBeat().search(game_name)
        if results:
            game = results[0]
            if game.main_story:
                return int(float(game.main_story) * 60)
    except Exception as e:
        print(f"💥 HLTB failed for {game_name}: {e}")
    return 0

def main():
    games = get_owned_games(STEAM_API_KEY, STEAM_ID)
    print(f"🎮 You own {len(games)} games!\n")

    existing_games = get_existing_app_ids()
    completed = sum(1 for v in existing_games.values() if v[0] > 0)
    incomplete = sum(1 for v in existing_games.values() if v[0] == 0)
    print(f"📁 Skipping {completed} games already in DB with playtime, {incomplete} have no recorded playtime")

    for game in games:
        app_id = game['appid']
        name = game.get('name', 'Unknown')

        if app_id in existing_games:
            playtime, tags, genres = existing_games[app_id]
            if playtime > 0:
                continue  # Skip fully populated entries
            if tags and genres:
                estimated_time = get_estimated_playtime_minutes(name)
                estimated_time_hours = round(estimated_time / 60, 1)
                save_game_to_db(app_id, name, tags.split(','), genres.split(','), estimated_time)
                print(f"🕒 Updated playtime for {name} ({app_id}) only ({estimated_time} min ≈ {estimated_time_hours} hrs)")
                print()
                continue

        details = get_game_details(app_id)
        estimated_time = get_estimated_playtime_minutes(name)
        estimated_time_hours = round(estimated_time / 60, 1)
        save_game_to_db(app_id, name, details['tags'], details['genres'], estimated_time)
        print(f"✅ Saved {name} ({app_id}) to DB ({estimated_time} min ≈ {estimated_time_hours} hrs)")
        print()
        time.sleep(2)  # Respect SteamSpy servers 💖

if __name__ == '__main__':
    main()