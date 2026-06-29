from flask import Flask, request, jsonify, Response, send_from_directory
import threading
import time
import uuid
import os
import subprocess
import requests
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# =========================
# STORAGE
# =========================
CHANNELS = {}  # name -> [url1, url2, url3]
STREAM_POOL = {}  # active ffmpeg processes
CACHE = {}

OUTPUT_DIR = "streams"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHECK_INTERVAL = 10


# =========================
# ADD CHANNEL (3 SOURCES)
# =========================
@app.route("/add")
def add():
    name = request.args.get("name")
    urls = request.args.getlist("url")

    if not name or len(urls) == 0:
        return jsonify({"error": "name + urls required"}), 400

    # max 3 fallback sources
    CHANNELS[name] = urls[:3]

    return jsonify({"ok": True, "count": len(CHANNELS)})


# =========================
# NETWORK SNIFFER (Playwright)
# =========================
def sniff(url):
    found = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            def on_response(resp):
                u = resp.url.lower()
                if ".m3u8" in u or ".mpd" in u:
                    found.append(resp.url)

            page.on("response", on_response)
            page.goto(url, timeout=20000)
            page.wait_for_timeout(4000)

            browser.close()

    except:
        pass

    return found


# =========================
# RESOLVER (3 SOURCE FALLBACK)
# =========================
def resolve(urls):
    for url in urls:

        # 1) direct sniff
        streams = sniff(url)
        if streams:
            return streams[0]

        # 2) direct m3u8/mpd check
        try:
            r = requests.get(url, timeout=8)
            if ".m3u8" in r.text:
                return url
        except:
            pass

    return None


# =========================
# FFMPEG START (PERSISTENT)
# =========================
def ffmpeg_worker(stream_id, url):
    out_path = os.path.join(OUTPUT_DIR, stream_id)
    os.makedirs(out_path, exist_ok=True)

    output = os.path.join(out_path, "index.m3u8")

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

        output
    ]

    proc = subprocess.Popen(cmd)

    STREAM_POOL[stream_id] = {
        "proc": proc,
        "url": url,
        "last_ok": time.time()
    }


# =========================
# WATCHDOG (AUTO HEAL 24/7)
# =========================
def watchdog():
    while True:
        time.sleep(CHECK_INTERVAL)

        for sid in list(STREAM_POOL.keys()):
            info = STREAM_POOL[sid]
            proc = info["proc"]

            # restart dead ffmpeg
            if proc.poll() is not None:
                print("RESTART:", sid)

                ffmpeg_worker(sid, info["url"])
                del STREAM_POOL[sid]


threading.Thread(target=watchdog, daemon=True).start()


# =========================
# PLAY CHANNEL
# =========================
@app.route("/play/<name>")
def play(name):

    if name not in CHANNELS:
        return "not found", 404

    urls = CHANNELS[name]

    stream = resolve(urls)

    if not stream:
        return jsonify({"error": "no stream found"}), 404

    sid = str(uuid.uuid4())

    threading.Thread(
        target=ffmpeg_worker,
        args=(sid, stream)
    ).start()

    return jsonify({
        "stream": f"/hls/{sid}/index.m3u8"
    })


# =========================
# IPTV PLAYLIST (PHONE READY)
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
# HLS SERVER
# =========================
@app.route("/hls/<sid>/<file>")
def hls(sid, file):
    return send_from_directory(os.path.join(OUTPUT_DIR, sid), file)


# =========================
@app.route("/")
def home():
    return "REAL IPTV ENGINE RUNNING"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
