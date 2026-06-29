from flask import Flask, request, jsonify, Response, send_from_directory
import requests
import re
import time
import threading
import subprocess
import uuid
import os

app = Flask(__name__)

# =========================
# CONFIG
# =========================
OUTPUT_DIR = "streams"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CACHE = {}          # url -> (stream, timestamp)
CACHE_TTL = 60

POOL = {}           # ffmpeg processes

CHECK_INTERVAL = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

STREAM_EXT = (".m3u8", ".mpd", ".ts", ".m4s", ".mp4")
KEYWORDS = ("manifest", "playlist", "master", "hls", "dash", "live")


# =========================
# 3-STREAM CHANNELS (fallback engine)
# =========================
CHANNELS = {
    "test": [
        "https://example.com/source1",
        "https://example.com/source2",
        "https://example.com/source3"
    ]
}


# =========================
# REAL STREAM SNIFFER V2 (LIGHT)
# =========================
def sniff_stream(url):
    """
    Pomalejší, ale výrazně úspěšnější než rychlé regexy
    """

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        html = r.text

        # 1) direct links
        links = re.findall(r'https?://[^\s"\'<>]+', html)

        for l in links:
            low = l.lower()
            if any(x in low for x in STREAM_EXT):
                return l

        # 2) iframe recursion (1 level)
        iframes = re.findall(r'src="(http[^"]+)"', html)

        for i in iframes:
            try:
                r2 = requests.get(i, headers=HEADERS, timeout=10)
                h2 = r2.text

                match = re.findall(r'https?://[^\s"\'<>]+\.m3u8', h2)
                if match:
                    return match[0]

                match2 = re.findall(r'https?://[^\s"\'<>]+\.mpd', h2)
                if match2:
                    return match2[0]

            except:
                pass

    except:
        pass

    return None


# =========================
# SLOW RETRY RESOLVER (IMPORTANT FIX)
# =========================
def resolve_with_retry(urls, retries=4, delay=2):
    for _ in range(retries):

        for u in urls:

            # cache hit
            if u in CACHE:
                stream, ts = CACHE[u]
                if time.time() - ts < CACHE_TTL:
                    return stream

            stream = sniff_stream(u)

            if stream:
                CACHE[u] = (stream, time.time())
                return stream

        time.sleep(delay)

    return None


# =========================
# FFMPEG PIPE (PERSISTENT)
# =========================
def ffmpeg_start(stream_id, url):
    out_dir = os.path.join(OUTPUT_DIR, stream_id)
    os.makedirs(out_dir, exist_ok=True)

    out = os.path.join(out_dir, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-re",
        "-i", url,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",
        "-c:a", "aac",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "6",
        "-hls_flags", "delete_segments+append_list",
        out
    ]

    proc = subprocess.Popen(cmd)

    POOL[stream_id] = {
        "proc": proc,
        "url": url,
        "last_ok": time.time()
    }


# =========================
# WATCHDOG (AUTO RESTART)
# =========================
def watchdog():
    while True:
        time.sleep(CHECK_INTERVAL)

        for sid in list(POOL.keys()):
            proc = POOL[sid]["proc"]

            if proc.poll() is not None:
                print("[RESTART]", sid)

                ffmpeg_start(sid, POOL[sid]["url"])
                del POOL[sid]


threading.Thread(target=watchdog, daemon=True).start()


# =========================
# PLAY ENDPOINT
# =========================
@app.route("/play/<name>")
def play(name):

    if name not in CHANNELS:
        return "not found", 404

    urls = CHANNELS[name]

    stream = resolve_with_retry(urls)

    if not stream:
        return jsonify({"error": "stream not found"}), 404

    sid = str(uuid.uuid4())

    ffmpeg_start(sid, stream)

    return jsonify({
        "stream": f"/hls/{sid}/index.m3u8"
    })


# =========================
# HLS SERVER
# =========================
@app.route("/hls/<sid>/<file>")
def hls(sid, file):
    return send_from_directory(os.path.join(OUTPUT_DIR, sid), file)


# =========================
# PLAYLIST (VLC ONLY)
# =========================
@app.route("/playlist.m3u")
def playlist():
    base = request.host_url.rstrip("/")
    out = "#EXTM3U\n"

    for name in CHANNELS:
        out += f"#EXTINF:-1,{name}\n"
        out += f"{base}/play/{name}\n"

    return Response(out, mimetype="text/plain")


# =========================
@app.route("/")
def home():
    return "REAL STREAM SNIFFER V2 RUNNING"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
