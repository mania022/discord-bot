import aiohttp
import base64
import traceback
from discord import app_commands
import discord

# === Spotify Helpers ===
async def get_spotify_token(client_id, client_secret):
    """Get Spotify access token using Client Credentials Flow (public data only)."""
    auth_str = f"{client_id}:{client_secret}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}

    async with aiohttp.ClientSession() as session:
        async with session.post("https://accounts.spotify.com/api/token", headers=headers, data=data) as resp:
            resp_json = await resp.json()
            return resp_json.get("access_token")


def get_artist_id_from_url(url: str):
    """Extract Spotify artist ID from full Spotify URL."""
    try:
        return url.split("artist/")[1].split("?")[0]
    except:
        return None


async def fetch_artist_albums(token, artist_id):
    """Fetch all public albums, singles, and EPs of an artist."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/artists/{artist_id}/albums?include_groups=album,single,ep&limit=50"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            return data.get("items", [])


async def fetch_album_tracks(token, album_id):
    """Fetch tracklist of a Spotify album."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            return data.get("items", [])


# === Discord command ===
@bot.tree.command(name="discography_spotify", description="Full Spotify discography with album covers")
async def discography_spotify(interaction: discord.Interaction, artist_url: str):
    await interaction.response.defer(thinking=True)

    try:
        artist_id = get_artist_id_from_url(artist_url)
        if not artist_id:
            return await interaction.followup.send("❌ Invalid Spotify artist URL.")

        token = await get_spotify_token(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        albums = await fetch_artist_albums(token, artist_id)

        if not albums:
            return await interaction.followup.send("❌ No releases found for this artist.")

        # Sort by release date descending
        albums.sort(key=lambda a: a["release_date"], reverse=True)

        for album in albums:
            album_name = album.get("name", "Unknown Album")
            release_year = album.get("release_date", "????")[:4]
            cover_url = album.get("images", [{}])[0].get("url")
            album_id = album.get("id")

            # Get tracklist
            tracks = await fetch_album_tracks(token, album_id)
            tracklist_text = "\n".join([f"{i+1}. {t.get('name', 'Unknown Track')}" for i, t in enumerate(tracks)])

            # Send album cover first
            embed = discord.Embed(
                title=f"{album_name} ({release_year})",
                color=discord.Color.green()
            )
            if cover_url:
                embed.set_image(url=cover_url)

            await interaction.followup.send(embed=embed)

            # Send tracklist in code blocks (split if too long)
            for chunk in split_long_text(tracklist_text):
                await interaction.followup.send(f"```{chunk}```")

    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send("❌ Error fetching Spotify discography.")
