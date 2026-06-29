from flask import Flask, request, jsonify, Response, send_from_directory
import requests
import re
import os
import uuid
import threading
import subprocess
import time

app = Flask(__name__)

# =========================
# STORAGE (DYNAMIC CHANNELS)
# =========================
CHANNELS = {}  # name -> source url
STREAMS = {}   # stream_id -> ffmpeg process info
CACHE = {}

OUTPUT_DIR = "streams"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHECK_INTERVAL = 15


# =========================
# HEADERS
# =========================
HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

STREAM_HINTS = (".m3u8", ".mpd", ".mp4", ".ts", ".m4s", ".mkv")
KEYWORDS = ("manifest", "playlist", "dash", "hls", "live")


# =========================
# ADD CHANNEL API (DYNAMIC)
# =========================
@app.route("/add")
def add_channel():
    name = request.args.get("name")
    url = request.args.get("url")

    if not name or not url:
        return jsonify({"error": "missing name or url"}), 400

    CHANNELS[name] = url

    return jsonify({"ok": True, "channels": len(CHANNELS)})


# =========================
# SIMPLE STREAM FINDER
# =========================
def find_stream(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        html = r.text

        urls = re.findall(r'https?://[^\s"\'<>]+', html)

        for u in urls:
            t = u.lower()
            if any(x in t for x in STREAM_HINTS) or any(k in t for k in KEYWORDS):
                return u

    except:
        return None

    return None


# =========================
# RESOLVE WITH RETRY
# =========================
def resolve(url):
    if url in CACHE:
        return CACHE[url]

    for _ in range(3):
        stream = find_stream(url)
        if stream:
            CACHE[url] = stream
            return stream
        time.sleep(0.5)

    return None


# =========================
# FFMPEG PROXY (HLS OUTPUT)
# =========================
def ffmpeg_worker(stream_id, url):
    out_dir = os.path.join(OUTPUT_DIR, stream_id)
    os.makedirs(out_dir, exist_ok=True)

    output = os.path.join(out_dir, "index.m3u8")

    cmd = [
        "ffmpeg",
        "-re",
        "-i", url,

        # stabilní TV output
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",

        "-c:a", "aac",

        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "6",
        "-hls_flags", "delete_segments+append_list",

        output
    ]

    proc = subprocess.Popen(cmd)

    STREAMS[stream_id] = {
        "proc": proc,
        "url": url,
        "last_ok": time.time()
    }


# =========================
# AUTO HEAL WATCHDOG (⚡ KEY FEATURE)
# =========================
def watchdog():
    while True:
        time.sleep(CHECK_INTERVAL)

        for sid in list(STREAMS.keys()):
            info = STREAMS[sid]
            proc = info["proc"]

            # restart když FFmpeg spadne
            if proc.poll() is not None:
                print("RESTART STREAM:", sid)

                new_id = sid
                ffmpeg_worker(new_id, info["url"])

                del STREAMS[sid]


threading.Thread(target=watchdog, daemon=True).start()


# =========================
# PLAY CHANNEL
# =========================
@app.route("/play/<name>")
def play(name):

    if name not in CHANNELS:
        return "not found", 404

    source = CHANNELS[name]

    stream = resolve(source)

    if not stream:
        return "no stream found", 404

    sid = str(uuid.uuid4())

    threading.Thread(
        target=ffmpeg_worker,
        args=(sid, stream)
    ).start()

    return jsonify({
        "url": f"/hls/{sid}/index.m3u8"
    })


# =========================
# M3U PLAYLIST (FOR IPTV APPS)
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
# SERVE HLS
# =========================
@app.route("/hls/<sid>/<file>")
def hls(sid, file):
    return send_from_directory(os.path.join(OUTPUT_DIR, sid), file)


# =========================
@app.route("/")
def home():
    return "DYNAMIC IPTV SERVER + AUTO HEAL RUNNING"


# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
