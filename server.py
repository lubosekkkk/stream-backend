from flask import Flask, request, jsonify, redirect, send_from_directory
import requests
import re
import time
import uuid
import os
import threading
import subprocess
from urllib.parse import urljoin

app = Flask(__name__)

# =========================
# CONFIG
# =========================
CACHE = {}
CACHE_TTL = 60  # seconds

OUTPUT_DIR = "streams"
os.makedirs(OUTPUT_DIR, exist_ok=True)

STREAM_EXTENSIONS = (
    ".m3u8", ".mpd", ".ts", ".m4s", ".mp4",
    ".mkv", ".webm", ".f4m", ".ism", ".isml"
)

KEYWORDS = (
    "manifest", "playlist", "master",
    "index.mpd", "index.m3u8",
    "live", "dash", "hls"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

# =========================
# CACHE
# =========================
def cache_get(url):
    item = CACHE.get(url)
    if not item:
        return None

    value, ts = item
    if time.time() - ts < CACHE_TTL:
        return value

    return None


def cache_set(url, value):
    CACHE[url] = (value, time.time())


# =========================
# STREAM DETECTION (HTML)
# =========================
def detect_html(url):
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
# GOOGLE SITES / EMBED BOOST (iframe + scripts fallback)
# =========================
def deep_scan(html, base_url=None):
    found = []

    urls = re.findall(r'https?://[^\s"\'<>]+', html)

    for u in urls:
        t = u.lower()
        if any(x in t for x in STREAM_EXTENSIONS) or any(k in t for k in KEYWORDS):
            found.append(u)

    # relative URLs (Google Sites často)
    if base_url:
        rels = re.findall(r'src="(.*?)"', html)
        for r in rels:
            absu = urljoin(base_url, r)
            found.append(absu)

    return found


# =========================
# RESOLVER WITH RETRY
# =========================
def resolve(url, retries=3):
    cached = cache_get(url)
    if cached:
        return cached

    last = None

    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            html = r.text

            # 1. direct scan
            stream = detect_html(url)
            if stream:
                cache_set(url, stream)
                return stream

            # 2. deep scan
            found = deep_scan(html, url)

            if found:
                cache_set(url, found[0])
                return found[0]

        except Exception as e:
            last = e
            time.sleep(0.5 * (i + 1))

    return None


# =========================
# FFMPEG PROXY WORKER
# =========================
def ffmpeg_worker(stream_id, input_url):
    path = os.path.join(OUTPUT_DIR, stream_id)
    os.makedirs(path, exist_ok=True)

    output = os.path.join(path, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-re",
        "-i", input_url,
        "-c:v", "copy",
        "-c:a", "copy",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "6",
        "-hls_flags", "delete_segments",
        output
    ]

    subprocess.Popen(cmd)


# =========================
# MAIN API
# =========================
@app.route("/find")
def find():
    url = request.args.get("url")

    if not url:
        return jsonify({"error": "missing url"}), 400

    stream = resolve(url)

    if not stream:
        return jsonify({"stream": None})

    # direct HLS
    if ".m3u8" in stream:
        return jsonify({
            "stream": stream,
            "type": "direct"
        })

    # ffmpeg fallback
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
# SERVE HLS
# =========================
@app.route("/hls/<sid>/<file>")
def hls(sid, file):
    return send_from_directory(os.path.join(OUTPUT_DIR, sid), file)


# =========================
@app.route("/")
def home():
    return "ULTRA IPTV resolver + FFmpeg proxy running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
