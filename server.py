from flask import Flask, request, Response, jsonify
import requests
import re
import time

app = Flask(__name__)

# =========================
# CONFIG
# =========================
CACHE = {}
CACHE_TTL = 90  # lehce delší cache = méně failů

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Connection": "keep-alive"
}

STREAM_EXT = (".m3u8", ".mpd", ".ts", ".m4s", ".mp4")
KEYWORDS = ("manifest", "playlist", "master", "hls", "dash", "live", "chunklist", "index")

TIMEOUT = 8


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
# STREAM DETECTOR (IMPROVED)
# =========================
def detect_stream(url):
    try:
        time.sleep(0.2)  # 🔥 jemný delay = méně bloků

        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        html = r.text

        # 1) direct URL scan (lepší regex)
        links = re.findall(r'https?://[^\s"\'<>]+', html)

        for l in links:
            low = l.lower()
            if any(ext in low for ext in STREAM_EXT):
                return l

        # 2) m3u8/mpd inline detection (silnější)
        m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        if m3u8:
            return m3u8[0]

        mpd = re.findall(r'https?://[^\s"\'<>]+\.mpd[^\s"\'<>]*', html)
        if mpd:
            return mpd[0]

        # 3) iframe fallback (hlubší scan)
        iframes = re.findall(r'src="(http[^"]+)"', html)

        for i in iframes:
            try:
                time.sleep(0.2)

                r2 = requests.get(i, headers=HEADERS, timeout=TIMEOUT)
                h2 = r2.text

                m3 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', h2)
                if m3:
                    return m3[0]

                mp = re.findall(r'https?://[^\s"\'<>]+\.mpd[^\s"\'<>]*', h2)
                if mp:
                    return mp[0]

            except:
                continue

    except:
        pass

    return None


# =========================
# SLOW + SMART RESOLVER
# =========================
def resolve_sources(sources, retries=6, delay=2):

    for attempt in range(retries):

        for url in sources:

            # cache first
            cached = cache_get(url)
            if cached:
                return cached

            stream = detect_stream(url)

            if stream:
                cache_set(url, stream)
                return stream

        # 🔥 postupné zpomalování (lepší než fixní delay)
        time.sleep(delay + attempt * 0.5)

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
        return jsonify({
            "error": "stream not found",
            "hint": "all sources failed"
        }), 404

    return jsonify({
        "stream": stream
    })


# =========================
# M3U PLAYLIST (VLC)
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
    return "MAX STABLE STREAM RESOLVER RUNNING"
