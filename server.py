from flask import Flask, request, Response, jsonify
import requests
import re
import time

app = Flask(__name__)

# =========================
# CONFIG
# =========================
CACHE = {}
CACHE_TTL = 90

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*"
}

STREAM_EXT = (".m3u8", ".mpd", ".ts", ".m4s", ".mp4", ".mkv")
KEYWORDS = ("manifest", "playlist", "master", "hls", "dash", "live", "index")

TIMEOUT = 8


# =========================
# CHANNELS
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
    item = CACHE.get(url)
    if not item:
        return None

    stream, ts = item
    if time.time() - ts < CACHE_TTL:
        return stream

    return None


def cache_set(url, stream):
    CACHE[url] = (stream, time.time())


# =========================
# STREAM DETECTOR
# =========================
def detect_stream(url):
    try:
        time.sleep(0.2)

        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        html = r.text

        # direct links
        links = re.findall(r'https?://[^\s"\'<>]+', html)

        for l in links:
            low = l.lower()
            if any(x in low for x in STREAM_EXT):
                return l

        # m3u8 / mpd direct
        m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        if m3u8:
            return m3u8[0]

        mpd = re.findall(r'https?://[^\s"\'<>]+\.mpd[^\s"\'<>]*', html)
        if mpd:
            return mpd[0]

        # iframe fallback
        iframes = re.findall(r'src="(http[^"]+)"', html)

        for i in iframes:
            try:
                r2 = requests.get(i, headers=HEADERS, timeout=TIMEOUT)
                h2 = r2.text

                m3 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', h2)
                if m3:
                    return m3[0]

                mp = re.findall(r'https?://[^\s"\'<>]+\.mpd[^\s"\'<>]*', h2)
                if mp:
                    return mp[0]

            except:
                pass

    except:
        return None

    return None


# =========================
# RESOLVER
# =========================
def resolve_sources(sources, retries=5, delay=2):
    for i in range(retries):

        for url in sources:

            cached = cache_get(url)
            if cached:
                return cached

            stream = detect_stream(url)

            if stream:
                cache_set(url, stream)
                return stream

        time.sleep(delay + i * 0.5)

    return None


# =========================
# API
# =========================
@app.route("/play/<name>")
def play(name):

    if name not in CHANNELS:
        return jsonify({"error": "not found"}), 404

    stream = resolve_sources(CHANNELS[name])

    if not stream:
        return jsonify({"error": "stream not found"}), 404

    return jsonify({"stream": stream})


@app.route("/playlist.m3u")
def playlist():
    base = request.host_url.rstrip("/")
    out = "#EXTM3U\n"

    for name in CHANNELS:
        out += f"#EXTINF:-1,{name}\n"
        out += f"{base}/play/{name}\n"

    return Response(out, mimetype="text/plain")


@app.route("/")
def home():
    return "STREAM SERVER RUNNING"
