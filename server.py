from flask import Flask, request, Response, jsonify
import requests
import re
import time

app = Flask(__name__)

# =========================
# CONFIG
# =========================
CACHE = {}
CACHE_TTL = 60  # cache 60s

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

STREAM_EXT = (".m3u8", ".mpd")
KEYWORDS = ("manifest", "playlist", "master", "hls", "dash", "live")

# =========================
# CHANNELS (3 SOURCES EACH)
# =========================
CHANNELS = {
    "test": [
        "https://example.com/source1",
        "https://example.com/source2",
        "https://example.com/source3"
    ]
}


# =========================
# CACHE
# =========================
def cache_get(url):
    if url in CACHE:
        stream, ts = CACHE[url]
        if time.time() - ts < CACHE_TTL:
            return stream
    return None


def cache_set(url, stream):
    CACHE[url] = (stream, time.time())


# =========================
# STREAM DETECTOR (LIGHT SNIFFER V2)
# =========================
def detect_stream(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        html = r.text

        # 1) direct links
        links = re.findall(r'https?://[^\s"\'<>]+', html)

        for l in links:
            low = l.lower()
            if any(ext in low for ext in STREAM_EXT):
                return l

        # 2) iframe follow (1 level)
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
# SLOW RESOLVER (retry + delay)
# =========================
def resolve_sources(sources, retries=4, delay=2):

    for _ in range(retries):

        for url in sources:

            cached = cache_get(url)
            if cached:
                return cached

            stream = detect_stream(url)

            if stream:
                cache_set(url, stream)
                return stream

        time.sleep(delay)

    return None


# =========================
# PLAY ENDPOINT (VLC FRIENDLY)
# =========================
@app.route("/play/<name>")
def play(name):

    if name not in CHANNELS:
        return "not found", 404

    sources = CHANNELS[name]

    stream = resolve_sources(sources)

    if not stream:
        return jsonify({"error": "stream not found"}), 404

    # VLC dostane rovnou stream URL
    return jsonify({
        "stream": stream
    })


# =========================
# M3U PLAYLIST (for VLC)
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
    return "REAL STREAM SNIFFER V2 (NO FFMPEG) RUNNING"
