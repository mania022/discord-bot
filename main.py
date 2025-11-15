from flask import Flask
from threading import Thread
import os
import discord
from discord import app_commands
import aiohttp
import asyncio
import random
import json
import time
import traceback
from ytmusicapi import YTMusic
import base64

# === Web server for uptime ===
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    thread = Thread(target=run_web)
    thread.start()

# === Config ===
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
SPOTIFY_CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]

CHANNELS = {
    "andrenavarroII": "UCv5OAW45h67CJEY6kJLyisg",
    "Musicforemptyrooms": "UCY8_y20lxQhhBe8GZl5A9rw",
    "herbietrees": "UCHPsRhxHbzQEwzdsJrx9bhg",
    "selvatican": "UCyvDDgWNL0gPlXCFQtofZLg",
    "VinyleArcheologie": "UCKydEBEvAU5zkN8o1snt62A",
}

CACHE_FILE = "video_cache.json"
ytmusic = YTMusic()

# === Helper to split long text ===
def split_long_text(text, limit=2000):
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)
    return chunks

# === Discord Bot ===
class SampleBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.videos_cache = []

    async def setup_hook(self):
        # Global command sync (works in DMs)
        await self.tree.sync()
        print("✅ Commands synced globally! Usable in DMs and servers.")

bot = SampleBot()

@bot.event
async def on_ready():
    print(f"🎶 Logged in as {bot.user}")

# === Cache Helpers ===
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

# === YouTube Fetch ===
async def fetch_channel_uploads(session, channel_id):
    try:
        channel_api = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={YOUTUBE_API_KEY}"
        async with session.get(channel_api) as resp:
            channel_data = await resp.json()
        uploads_playlist = channel_data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        videos = []
        next_page = None
        while True:
            url = (
                f"https://www.googleapis.com/youtube/v3/playlistItems"
                f"?part=snippet&maxResults=50&playlistId={uploads_playlist}&key={YOUTUBE_API_KEY}"
            )
            if next_page:
                url += f"&pageToken={next_page}"

            async with session.get(url) as resp:
                data = await resp.json()

            if "items" not in data:
                break

            videos.extend(data["items"])
            next_page = data.get("nextPageToken")
            if not next_page:
                break

        return videos
    except:
        return []

async def fetch_all_channels():
    async with aiohttp.ClientSession() as session:
        all_videos = []
        for name, channel_id in CHANNELS.items():
            vids = await fetch_channel_uploads(session, channel_id)
            all_videos.extend(vids)
            await asyncio.sleep(0.5)
        return all_videos

# === /turnon ===
@bot.tree.command(name="turnon", description="Fetch all YouTube channel videos")
async def turnon(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        videos = await fetch_all_channels()
        if not videos:
            return await interaction.followup.send("No videos found.")

        bot.videos_cache = videos
        save_cache({"time": time.time(), "videos": videos})
        await interaction.followup.send(f"✅ Cached {len(videos)} videos!")
    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send("❌ Error fetching videos.")

# === /sample ===
@bot.tree.command(name="sample", description="Send a random video")
async def sample(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    if not bot.videos_cache:
        cache = load_cache()
        if "videos" in cache:
            bot.videos_cache = cache["videos"]

    if not bot.videos_cache:
        return await interaction.followup.send("Run /turnon first.")

    video = random.choice(bot.videos_cache)
    snippet = video.get("snippet", {})
    video_id = snippet.get("resourceId", {}).get("videoId")

    if not video_id:
        return await interaction.followup.send("Invalid video in cache.")

    title = snippet.get("title")
    channel = snippet.get("videoOwnerChannelTitle")
    url = f"https://www.youtube.com/watch?v={video_id}"
    thumb = snippet.get("thumbnails", {}).get("high", {}).get("url")

    embed = discord.Embed(
        title=title,
        description=f"By **{channel}**",
        color=discord.Color.red()
    )
    if thumb:
        embed.set_thumbnail(url=thumb)

    await interaction.followup.send(embed=embed)

# === Spotify Helpers ===
async def get_spotify_token():
    auth = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    b64 = base64.b64encode(auth.encode()).decode()
    headers = {"Authorization": f"Basic {b64}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials"}

    async with aiohttp.ClientSession() as s:
        async with s.post("https://accounts.spotify.com/api/token", headers=headers, data=data) as r:
            tok = await r.json()
            return tok.get("access_token")

def get_artist_id_from_url(url):
    try:
        return url.split("artist/")[1].split("?")[0]
    except:
        return None

async def fetch_artist_albums(token, artist_id):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?include_groups=album,single,ep&limit=50"

    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return (await r.json()).get("items", [])

async def fetch_album_tracks(token, album_id):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"

    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return (await r.json()).get("items", [])

# === /discography_spotify ===
@bot.tree.command(name="discography_spotify", description="Spotify discography with album covers")
async def discography_spotify(interaction: discord.Interaction, artist_url: str):
    await interaction.response.defer(thinking=True)
    try:
        artist_id = get_artist_id_from_url(artist_url)
        if not artist_id:
            return await interaction.followup.send("❌ Invalid Spotify artist URL.")

        token = await get_spotify_token()
        albums = await fetch_artist_albums(token, artist_id)
        albums.sort(key=lambda a: a.get("release_date", "0"), reverse=True)

        for album in albums:
            album_name = album.get("name", "Unknown Album")
            release_year = album.get("release_date", "????")[:4]
            cover_url = album.get("images", [{}])[0].get("url")
            album_id = album.get("id")

            tracks = await fetch_album_tracks(token, album_id)
            tracklist = "\n".join([f"{i+1}. {t.get('name','Unknown')}" for i, t in enumerate(tracks)])

            embed = discord.Embed(title=f"{album_name} ({release_year})", color=discord.Color.green())
            if cover_url:
                embed.set_image(url=cover_url)
            await interaction.followup.send(embed=embed)

            for chunk in split_long_text(tracklist):
                await interaction.followup.send(f"```{chunk}```")

    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send("❌ Error fetching Spotify discography.")

# === /discography_ytmusic ===
@bot.tree.command(name="discography_ytmusic", description="YouTube Music discography with album covers")
async def discography_ytmusic(interaction: discord.Interaction, artist_name: str):
    await interaction.response.defer(thinking=True)
    try:
        albums = ytmusic.search(artist_name, filter="albums")
        if not albums:
            return await interaction.followup.send("❌ No albums found on YouTube Music.")

        for album in albums:
            album_title = album.get("title", "Unknown Album")
            browse_id = album.get("browseId")
            album_data = ytmusic.get_album(browse_id)

            tracks = album_data.get("tracks", [])
            cover_url = album_data.get("thumbnails", [{}])[-1].get("url")

            tracklist_text = "\n".join([f"{i+1}. {t.get('title','Unknown')}" for i, t in enumerate(tracks)])

            embed = discord.Embed(title=album_title, color=discord.Color.blue())
            if cover_url:
                embed.set_image(url=cover_url)
            await interaction.followup.send(embed=embed)

            for chunk in split_long_text(tracklist_text):
                await interaction.followup.send(f"```{chunk}```")

    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send("❌ Error fetching YouTube Music discography.")

# === Start bot ===
keep_alive()
bot.run(DISCORD_TOKEN)
