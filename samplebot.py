from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    thread = Thread(target=run_web)
    thread.start()


import discord
from discord import app_commands
import aiohttp
import asyncio
import random
import json
import os
import time
import traceback
from ytmusicapi import YTMusic
import base64

# === CONFIGURATION / INSERT YOUR INFO HERE ===

# Discord Bot Token
DISCORD_TOKEN = "MTQzODIxNDMzMDE2MzI2NTYxNw.GRyGAi.CABe4dwRg8aQjXXh3N8onRQ26VV8cYXintNMzk"  # e.g. "MzI1NjYxNDM1Njk4ODU2.XYZabc..."

# YouTube Data API Key
YOUTUBE_API_KEY = "AIzaSyC6pDqBKUc7Ijs_OgRPR1aLudckx98uqYs"  # e.g. "AIzaSyA...XYZ"

# Spotify API Credentials
SPOTIFY_CLIENT_ID = "ee87103105f04f46bc418be3255df3b6"  # from https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_SECRET = "7d907399609641f3b93d8950b7653d7a"  # from the same dashboard

# Discord server (guild) ID where commands are synced
GUILD_ID = 1429281076190117912  # replace with your server's ID

CHANNELS = {
    "andrenavarroII": "UCv5OAW45h67CJEY6kJLyisg",
    "Musicforemptyrooms": "UCY8_y20lxQhhBe8GZl5A9rw",
    "herbietrees": "UCHPsRhxHbzQEwzdsJrx9bhg",
    "selvatican": "UCyvDDgWNL0gPlXCFQtofZLg",
    "VinyleArcheologie": "UCKydEBEvAU5zkN8o1snt62A",
}

CACHE_FILE = "video_cache.json"
CACHE_EXPIRY = 60 * 60 * 6  # 6 hours

ytmusic = YTMusic()

# === Helper to split long messages ===
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

# === BOT SETUP ===
class SampleBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.videos_cache = []

    async def setup_hook(self):
        await self.tree.sync()
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            await self.tree.sync(guild=guild)
            print(f"✅ Commands synced in guild {GUILD_ID}")

bot = SampleBot()

@bot.event
async def on_ready():
    print(f"🎶 Logged in as {bot.user}")

# === Cache Helpers ===
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

# === YouTube Fetching ===
async def fetch_channel_uploads(session, channel_id):
    try:
        channel_api = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={YOUTUBE_API_KEY}"
        async with session.get(channel_api) as resp:
            channel_data = await resp.json()

        uploads_playlist = channel_data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        videos = []
        next_page = None
        while True:
            playlist_api = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={uploads_playlist}&key={YOUTUBE_API_KEY}"
            if next_page:
                playlist_api += f"&pageToken={next_page}"
            async with session.get(playlist_api) as resp:
                data = await resp.json()
            if "items" not in data:
                break
            videos.extend(data["items"])
            next_page = data.get("nextPageToken")
            if not next_page:
                break
        return videos
    except Exception as e:
        print(f"⚠️ Error fetching channel {channel_id}: {e}")
        return []

async def fetch_all_channels():
    async with aiohttp.ClientSession() as session:
        all_videos = []
        for name, channel_id in CHANNELS.items():
            print(f"📡 Fetching videos from {name}...")
            videos = await fetch_channel_uploads(session, channel_id)
            print(f"✅ Found {len(videos)} videos from {name}")
            all_videos.extend(videos)
            await asyncio.sleep(0.5)
        return all_videos

# === Commands: /turnon & /sample ===
@bot.tree.command(name="turnon", description="⚡ Fetch YouTube videos from all configured channels")
async def turnon(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        videos = await fetch_all_channels()
        if not videos:
            await interaction.followup.send("⚠️ Couldn’t fetch any videos.")
            return
        bot.videos_cache = videos
        save_cache({"timestamp": time.time(), "videos": videos})
        await interaction.followup.send(f"✅ Cached {len(videos)} total videos from all channels!")
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching videos: {e}")
        traceback.print_exc()

@bot.tree.command(name="sample", description="🎧 Send a random video from the fetched list")
async def sample(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        if not bot.videos_cache:
            cache = load_cache()
            if "videos" in cache:
                bot.videos_cache = cache["videos"]
        if not bot.videos_cache:
            await interaction.followup.send("⚠️ You need to run `/turnon` first!")
            return
        video = random.choice(bot.videos_cache)
        snippet = video.get("snippet", {})
        video_id = snippet.get("resourceId", {}).get("videoId") or snippet.get("id", None)
        if not video_id:
            await interaction.followup.send("⚠️ Could not find a valid video ID in this entry.")
            return
        title = snippet.get("title", "Unknown Title")
        channel_name = snippet.get("videoOwnerChannelTitle", "Unknown Channel")
        url = f"https://www.youtube.com/watch?v={video_id}"
        thumbnail = snippet.get("thumbnails", {}).get("high", {}).get("url")
        embed = discord.Embed(
            title=title,
            description=f"👤 **{channel_name}**\n🎥 [Watch on YouTube]({url})",
            color=discord.Color.red()
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ An internal error occurred: {type(e).__name__}")
        traceback.print_exc()

# === Spotify Helpers ===
async def get_spotify_token():
    auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Authorization": f"Basic {b64_auth}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials"}
    async with aiohttp.ClientSession() as session:
        async with session.post("https://accounts.spotify.com/api/token", headers=headers, data=data) as resp:
            token_data = await resp.json()
            return token_data.get("access_token")

async def get_artist_id_from_url(url: str):
    try:
        return url.split("artist/")[1].split("?")[0]
    except:
        return None

async def fetch_artist_albums(token, artist_id):
    # include albums, singles, eps, compilations
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?limit=50&include_groups=album,single,appears_on,compilation"
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

async def fetch_album_tracks(token, album_id):
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

# === /discography_spotify (scrolling messages, no links, includes singles & eps) ===
@bot.tree.command(name="discography_spotify", description="Spotify discography (albums, singles, EPs, compilations)")
async def discography_spotify(interaction: discord.Interaction, artist_url: str):
    await interaction.response.defer(thinking=True)
    try:
        artist_id = await get_artist_id_from_url(artist_url)
        if not artist_id:
            await interaction.followup.send("❌ Invalid Spotify artist URL.")
            return

        token = await get_spotify_token()
        albums_data = await fetch_artist_albums(token, artist_id)
        albums = albums_data.get("items", [])
        albums.sort(key=lambda a: a.get("release_date", "0"), reverse=True)
        if not albums:
            await interaction.followup.send("❌ No releases found for this artist.")
            return

        for album in albums:
            album_name = album["name"]
            release_year = album.get("release_date", "????")[:4]
            album_type = album.get("album_type", "album").capitalize()
            album_id = album["id"]

            tracks_data = await fetch_album_tracks(token, album_id)
            tracks = tracks_data.get("items", [])

            tracklist_text = ""
            for idx, track in enumerate(tracks, start=1):
                track_name = track["name"]
                tracklist_text += f"{idx}. {track_name}\n"

            await interaction.followup.send(f"📀 **{album_name} ({release_year}) [{album_type}])**")
            for chunk in split_long_text(tracklist_text):
                await interaction.followup.send(f"```{chunk}```")

    except Exception as e:
        await interaction.followup.send("❌ Error fetching Spotify discography.")
        traceback.print_exc()

# === /discography_ytmusic (scrolling messages, no links) ===
@bot.tree.command(name="discography_ytmusic", description="YouTube Music discography (album + tracklist only)")
async def discography_ytmusic(interaction: discord.Interaction, artist_name: str):
    await interaction.response.defer(thinking=True)
    try:
        search_results = ytmusic.search(artist_name, filter="albums")
        if not search_results:
            await interaction.followup.send("❌ No albums found on YouTube Music.")
            return

        for album in search_results:
            album_title = album.get("title", "Unknown Album")
            album_id = album.get("browseId")
            album_tracks = ytmusic.get_album(album_id).get("tracks", [])

            tracklist_text = ""
            for idx, track in enumerate(album_tracks, start=1):
                track_title = track.get("title", "Unknown Track")
                tracklist_text += f"{idx}. {track_title}\n"

            await interaction.followup.send(f"📀 **{album_title}**")
            for chunk in split_long_text(tracklist_text):
                await interaction.followup.send(f"```{chunk}```")

    except Exception as e:
        await interaction.followup.send("❌ Error fetching YouTube Music discography.")
        traceback.print_exc()

# === Run Bot ===
bot.run(DISCORD_TOKEN)
