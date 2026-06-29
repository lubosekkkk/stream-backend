from flask import Flask, request, jsonify, send_from_directory
import requests
import re
import os
import uuid
import threading
import subprocess
import time

app = Flask(__name__)

# =========================
# CACHE
# =========================
CACHE = {}
CACHE_TTL = 60

STREAM_EXTENSIONS = (
    ".m3u8", ".mpd", ".ts", ".mp4", ".mkv", ".m4s", ".webm"
)

KEYWORDS = (
    "manifest", "playlist", "master", "dash", "hls", "live", "index"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

OUTPUT_DIR = "streams"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# =========================
# CACHE
# =========================
def cache_get(url):
    if url in CACHE:
        val, t = CACHE[url]
        if time.time() - t < CACHE_TTL:
            return val
    return None


def cache_set(url, val):
    CACHE[url] = (val, time.time())


# =========================
# BASIC SCRAPER
# =========================
def detect_stream(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        html = r.text

        urls = re.findall(r'https?://[^\s"\'<>]+', html)

        for u in urls:
            t = u.lower()
            if any(x in t for x in STREAM_EXTENSIONS) or any(k in t for k in KEYWORDS):
                return u

    except:
        return None

    return None


# =========================
# RESOLVER + CACHE
# =========================
def resolve(url):
    cached = cache_get(url)
    if cached:
        return cached

    stream = detect_stream(url)

    if stream:
        cache_set(url, stream)
        return stream

    return None


# =========================
# 🔥 FFMPEG FIXED WORKER (IMPORTANT)
# =========================
def ffmpeg_worker(stream_id, input_url):

    path = os.path.join(OUTPUT_DIR, stream_id)
    os.makedirs(path, exist_ok=True)

    output = os.path.join(path, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-re",
        "-i", input_url,

        # 🔥 KLÍČOVÉ: musí se re-encode (COPY nefunguje u MPD)
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",

        "-c:a", "aac",
        "-b:a", "128k",

        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "6",
        "-hls_flags", "delete_segments+append_list+independent_segments",

        output
    ]

    # 🔥 důležité: permanentní proces
    subprocess.Popen(cmd)


# =========================
# API
# =========================
@app.route("/find")
def find():

    url = request.args.get("url")

    if not url:
        return jsonify({"error": "missing url"}), 400

    stream = resolve(url)

    if not stream:
        return jsonify({"stream": None})

    # ✔ pokud už je m3u8 → direct
    if ".m3u8" in stream:
        return jsonify({"stream": stream, "type": "direct"})

    # 🔥 jinak FFmpeg proxy
    stream_id = str(uuid.uuid4())

    t = threading.Thread(
        target=ffmpeg_worker,
        args=(stream_id, stream)
    )
    t.start()

    return jsonify({
        "stream": f"/hls/{stream_id}/index.m3u8",
        "type": "ffmpeg"
    })


# =========================
# SERVE HLS FILES
# =========================
@app.route("/hls/<sid>/<file>")
def hls(sid, file):
    return send_from_directory(os.path.join(OUTPUT_DIR, sid), file)


# =========================
@app.route("/")
def home():
    return "FFmpeg IPTV Proxy FIX running"


# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
