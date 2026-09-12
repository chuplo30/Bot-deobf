import discord
from discord.ext import commands
import requests
import asyncio
import io
import os
from typing import Optional
from flask import Flask
from threading import Thread

TOKEN = os.environ.get("DISCORD_TOKEN")
LOADER = "<a:loader:1547584320544448542>"
RUBIS_EMOJI = "<:rubis:1546171167281254550>"
INLINE_LIMIT = 2000

DETECT_URL = "https://leakd.up.railway.app/detect"
OBF_URL = "https://8xms-obfuscator.netlify.app/api/obfuscate"

HEADER = """--[[ 
█░░░█ █▀█ █▄░█
▀▄▀▄▀ █▀█ █░▀█

   WAN DEOBFUSCATOR 
  
]]
"""

DEOBFUSCATORS = {
    "prometheus":    ("Prometheus",    "https://leakd.up.railway.app/prometheus"),
    "ironbrew2":     ("IronBrew2",     "https://leakd.up.railway.app/ironbrew2"),
    "moonsec":       ("MoonSec",       "https://leakd.up.railway.app/moonsec"),
    "ironveil":      ("IronVeil",      "https://leakd.up.railway.app/ironveil"),
    "hercules":      ("Hercules",      "https://leakd.up.railway.app/hercules"),
    "goofyscator":   ("Goofyscator",   "https://leakd.up.railway.app/goofyscator"),
    "clydedeobf":    ("Clyde",         "https://leakd.up.railway.app/clydedeobf"),
    "77fuscator":    ("77fuscator",    "https://leakd.up.railway.app/77fuscator"),
    "luaobfuscator": ("LuaObfuscator", "https://leakd.up.railway.app/luaobfuscator"),
}

NAME_TO_KEY = {label.lower(): key for key, (label, _) in DEOBFUSCATORS.items()}

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Bot is alive!"


def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

bot.remove_command("help")


@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")


def call_deobf_api(endpoint: str, content: bytes) -> dict:
    files = {"file": ("script.lua", content, "text/plain")}
    r = requests.post(endpoint, files=files, timeout=120)
    try:
        return r.json()
    except ValueError:
        return {"success": False, "error": f"API returned non-JSON (status {r.status_code})"}


def call_detect_api(content: bytes) -> dict:
    files = {"file": ("script.lua", content, "text/plain")}
    r = requests.post(DETECT_URL, files=files, timeout=60)
    try:
        return r.json()
    except ValueError:
        return {"success": False}


def call_obf_api(code: str) -> dict:
    try:
        r = requests.post(OBF_URL, json={"code": code}, timeout=180)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def upload_to_rubis(content: str, title: str = "WAN DEOBFUSCATOR") -> Optional[str]:
    url = "https://api.rubis.app/v2/scrap"
    params = {"public": "true", "accessKey": "true", "title": title}
    headers = {"accept": "application/json", "Content-Type": "text/plain"}
    try:
        response = requests.post(
            url, params=params, headers=headers,
            data=content.encode("utf-8"), timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        raw = data.get("raw")
        if isinstance(raw, str) and raw.startswith("http"):
            return raw
        scrap_id = data.get("scrapID")
        if scrap_id:
            return f"https://api.rubis.app/v2/scrap/{scrap_id}/raw"
    except Exception as e:
        print(f"[!] Rubis error: {e}")
    return None


def strip_comments(code: str) -> str:
    lines = code.split("\n")
    out = []
    for line in lines:
        if not out and line.strip().startswith("--"):
            continue
        out.append(line)
    return "\n".join(out).strip()


async def send_result(dest, label: str, filename: str, code: str, out_size, loading_msg=None):
    full_code = HEADER + code

    if loading_msg is not None:
        try:
            await loading_msg.edit(content=f"{LOADER} Uploading to Rubis...")
        except Exception:
            pass

    loop = asyncio.get_event_loop()
    try:
        rubis_url = await loop.run_in_executor(None, upload_to_rubis, full_code)
    except Exception:
        rubis_url = None

    header_line = f"{label} — {filename} ({out_size} KB, {len(code)} chars)"
    if rubis_url:
        header_line += f"\n{RUBIS_EMOJI}Rubis: [click]({rubis_url})"

    if loading_msg is not None:
        try:
            await loading_msg.delete()
        except Exception:
            pass

    inline_msg = f"{header_line}\n```lua\n{full_code}\n```"

    if len(full_code) <= INLINE_LIMIT and len(inline_msg) <= 2000:
        await dest.send(inline_msg)
        return

    buf = io.BytesIO(full_code.encode("utf-8"))
    await dest.send(header_line, file=discord.File(buf, filename="dumper.txt"))


async def get_attachment(ctx):
    if ctx.message.attachments:
        return ctx.message.attachments[0]
    if ctx.message.reference:
        try:
            ref_id = ctx.message.reference.message_id
            replied = await ctx.channel.fetch_message(ref_id)
            if replied.attachments:
                return replied.attachments[0]
        except Exception:
            pass
    return None


async def fetch_content(ctx, url: str = None):
    if url:
        loading = await ctx.send(f"{LOADER} Downloading file from URL...")
        try:
            loop = asyncio.get_event_loop()

            def download():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                }
                r = requests.get(url, timeout=60, headers=headers, allow_redirects=True)
                r.raise_for_status()
                return r.content

            content = await loop.run_in_executor(None, download)
            filename = url.split("/")[-1].split("?")[0] or "script.lua"
            if not filename.lower().endswith(".lua"):
                filename += ".lua"
            return content, filename, loading
        except requests.exceptions.RequestException as e:
            await loading.edit(content=f"Failed to download file: {e}")
            raise

    attachment = await get_attachment(ctx)
    if attachment:
        loading = await ctx.send(f"{LOADER} Reading attached file...")
        try:
            content = await attachment.read()
            return content, attachment.filename, loading
        except Exception as e:
            await loading.edit(content=f"Failed to read file: {e}")
            raise

    return None, None, None


class DeobfButton(discord.ui.Button):
    def __init__(self, key: str, label: str, endpoint: str, content: bytes,
                 filename: str, author_id: int, detected: bool = False):
        style = discord.ButtonStyle.success if detected else discord.ButtonStyle.secondary
        super().__init__(label=label, style=style)
        self.key = key
        self.endpoint = endpoint
        self.content = content
        self.filename = filename
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "This is not your command.", ephemeral=True
            )

        await interaction.response.send_message(f"{LOADER} Running {self.label}...")
        loading_msg = await interaction.original_response()

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, call_deobf_api, self.endpoint, self.content
            )

            if not result.get("success"):
                err = result.get("error", "Unknown error")
                return await loading_msg.edit(content=f"{self.label}: {err}")

            code = strip_comments(result.get("deobfuscated_code", ""))
            out_size = result.get("file", {}).get("output_size_kb", "?")

            if not code:
                return await loading_msg.edit(
                    content=f"{self.label}: API did not return any code."
                )

            await send_result(
                interaction.channel, self.label, self.filename,
                code, out_size, loading_msg=loading_msg
            )

            try:
                if self.view.message:
                    await self.view.message.delete()
            except Exception:
                pass

        except requests.exceptions.RequestException as e:
            await loading_msg.edit(content=f"API error {self.label}: {e}")
        except Exception as e:
            await loading_msg.edit(content=f"Error: {e}")


class DeobfView(discord.ui.View):
    def __init__(self, content: bytes, filename: str, author_id: int, detected_key: str = None):
        super().__init__(timeout=300)
        self.content = content
        self.filename = filename
        self.message = None
        self.detected_key = detected_key

        for i, (key, (label, endpoint)) in enumerate(DEOBFUSCATORS.items()):
            btn = DeobfButton(
                key, label, endpoint, content, filename, author_id,
                detected=(key == detected_key),
            )
            btn.row = i // 5
            self.add_item(btn)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="Selection timed out.", view=self)
            except Exception:
                pass


@bot.command(name="deobf", aliases=["deo"])
async def deobf(ctx, url: str = None, method: str = None):
    if url and url.lower() in DEOBFUSCATORS:
        attachment = await get_attachment(ctx)
        if attachment:
            method = url.lower()
            url = None

    content, filename, loading = await fetch_content(ctx, url)

    if not content:
        if loading is None:
            return await ctx.send(
                "Usage:\n"
                "• .deobf <url> — download from link\n"
                "• .deobf + attached file / reply file\n"
                "• .deobf <url> <type> — direct run\n"
                "• .deobf <type> + attached file / reply file\n\n"
                f"Supported types: {', '.join(DEOBFUSCATORS.keys())}"
            )
        return

    if method:
        method = method.lower()
        if method not in DEOBFUSCATORS:
            return await loading.edit(
                content=f"Unknown type {method}.\n"
                        f"Supported: {', '.join(DEOBFUSCATORS.keys())}"
            )

        label, endpoint = DEOBFUSCATORS[method]
        await loading.edit(content=f"{LOADER} Running {label}...")

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, call_deobf_api, endpoint, content)

            if not result.get("success"):
                err = result.get("error", "Unknown error")
                return await loading.edit(content=f"{label}: {err}")

            code = strip_comments(result.get("deobfuscated_code", ""))
            out_size = result.get("file", {}).get("output_size_kb", "?")

            if not code:
                return await loading.edit(content=f"{label}: API did not return any code.")

            await send_result(ctx, label, filename, code, out_size, loading_msg=loading)

        except requests.exceptions.RequestException as e:
            await loading.edit(content=f"API error: {e}")
        except Exception as e:
            await loading.edit(content=f"Error: {e}")
        return

    await loading.delete()

    view = DeobfView(content, filename, ctx.author.id, detected_key=None)
    view.message = await ctx.send(
        f"File: {filename}\n"
        f"Click a button to get the deobfuscated code (expires in 5 min):",
        view=view
    )


@bot.command(name="detect")
async def detect(ctx, url: str = None):
    content, filename, loading = await fetch_content(ctx, url)

    if not content:
        if loading is None:
            return await ctx.send(
                "Usage:\n"
                "• .detect <url> — detect from link\n"
                "• .detect + attached file / reply file"
            )
        return

    await loading.edit(content=f"{LOADER} Detecting obfuscator type...")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, call_detect_api, content)
    except Exception as e:
        return await loading.edit(content=f"Detection error: {e}")

    if not result.get("success"):
        return await loading.edit(content="This type of debug is not supported")

    top = result.get("top_result", {}) or {}
    detected_name = (top.get("name") or "").strip()
    confidence = top.get("confidence", "?")

    if not detected_name:
        return await loading.edit(content="This type of debug is not supported")

    detected_key = NAME_TO_KEY.get(detected_name.lower())
    supported = "(supported)" if detected_key else "(not supported)"

    await loading.edit(
        content=(
            f"File: {filename}\n"
            f"Detected: {detected_name} ({confidence}% confidence) {supported}"
        )
    )


@bot.command(name="obf")
async def obf(ctx, *, input_text: str = None):
    loading = None
    code = None
    filename = "script.lua"

    attachment = await get_attachment(ctx)

    if attachment:
        loading = await ctx.send(f"{LOADER} Reading attached file...")
        try:
            content = await attachment.read()
            code = content.decode("utf-8", errors="ignore")
            filename = attachment.filename
            if not filename.lower().endswith(".lua"):
                filename += ".lua"
        except Exception as e:
            return await loading.edit(content=f"Failed to read file: {e}")

    elif input_text and input_text.strip().startswith(("http://", "https://")):
        url = input_text.strip()
        loading = await ctx.send(f"{LOADER} Downloading file from URL...")
        try:
            loop = asyncio.get_event_loop()

            def download():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                }
                r = requests.get(url, timeout=60, headers=headers, allow_redirects=True)
                r.raise_for_status()
                return r.content

            content = await loop.run_in_executor(None, download)
            code = content.decode("utf-8", errors="ignore")
            filename = url.split("/")[-1].split("?")[0] or "script.lua"
            if not filename.lower().endswith(".lua"):
                filename += ".lua"
        except requests.exceptions.RequestException as e:
            return await loading.edit(content=f"Failed to download file: {e}")

    elif input_text and input_text.strip():
        code = input_text
        loading = await ctx.send(f"{LOADER} Obfuscating...")

    else:
        return await ctx.send(
            "Usage:\n"
            "• .obf <url> — download from link then obfuscate\n"
            "• .obf <code> — obfuscate inline code\n"
            "• .obf + attached file / reply file"
        )

    if not code or not code.strip():
        return await loading.edit(content="No code provided.")

    if loading is None:
        loading = await ctx.send(f"{LOADER} Obfuscating...")
    else:
        try:
            await loading.edit(content=f"{LOADER} Obfuscating...")
        except Exception:
            pass

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, call_obf_api, code)
    except Exception as e:
        return await loading.edit(content=f"Obfuscation error: {e}")

    if not result.get("ok"):
        err = result.get("error") or result.get("message") or "Unknown error"
        return await loading.edit(content=f"Obfuscation failed: {err}")

    obf_code = result.get("code", "")
    if not obf_code:
        return await loading.edit(content="API did not return any code.")

    meta = result.get("meta", {}) or {}
    out_kb = f"{len(obf_code) / 1024:.2f}"

    label = "8xms Obfuscator"
    if meta:
        frag = meta.get("fragments") or meta.get("fragment_count")
        if frag:
            label += f" ({frag} fragments)"

    await send_result(ctx, label, filename, obf_code, out_kb, loading_msg=loading)


if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
