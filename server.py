from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import requests
import re
import os

app = Flask(__name__)

# =========================
# Stream přípony
# =========================
STREAM_EXTENSIONS = (
    ".m3u8",
    ".mpd",
    ".ts",
    ".m4s",
    ".mp4",
    ".mkv",
    ".webm",
    ".f4m",
    ".ism",
    ".isml"
)

# =========================
# Klíčová slova
# =========================
STREAM_KEYWORDS = (
    "manifest",
    "playlist",
    "master",
    "index.mpd",
    "index.m3u8",
    "live",
    "dash",
    "hls"
)


# =========================
# HTML SCRAPER
# =========================
def detect_html(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, timeout=10)

        urls = re.findall(r'https?://[^\s"\'<>]+', r.text)

        for u in urls:
            test = u.lower()

            if (
                any(ext in test for ext in STREAM_EXTENSIONS)
                or any(word in test for word in STREAM_KEYWORDS)
            ):
                return u

        return None

    except Exception:
        return None


# =========================
# PLAYWRIGHT
# =========================
def detect_playwright(url):

    found = []

    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ]
            )

            page = browser.new_page()

            def on_response(resp):

                test = resp.url.lower()

                if (
                    any(ext in test for ext in STREAM_EXTENSIONS)
                    or any(word in test for word in STREAM_KEYWORDS)
                ):
                    if resp.url not in found:
                        found.append(resp.url)

            page.on("response", on_response)

            page.goto(
                url,
                wait_until="networkidle",
                timeout=30000
            )

            page.wait_for_timeout(5000)

            browser.close()

    except Exception:
        return []

    return found


# =========================
# API
# =========================
@app.route("/find")
def find():

    url = request.args.get("url")

    if not url:
        return jsonify({"error": "missing url"}), 400

    stream = detect_html(url)

    if stream:
        return jsonify({
            "stream": stream,
            "source": "html"
        })

    streams = detect_playwright(url)

    if streams:
        return jsonify({
            "stream": streams[0],
            "source": "playwright"
        })

    return jsonify({
        "stream": None
    })


# =========================
# START
# =========================
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
