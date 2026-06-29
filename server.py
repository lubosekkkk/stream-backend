from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import re
import requests

app = Flask(__name__)
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

def detect_html(url):
    try:
        r = requests.get(url, timeout=10)
        urls = re.findall(r'https?://[^\s"\'<>]+', r.text)

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

for u in urls:
    url = u.lower()

    if (
        any(ext in url for ext in STREAM_EXTENSIONS)
        or any(keyword in url for keyword in STREAM_KEYWORDS)
    ):
        return u

        return None

    except:
        return None


def detect_playwright(url):
    found = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            page = browser.new_page()

   def on_response(resp):
    url = resp.url.lower()

    if (
        any(ext in url for ext in STREAM_EXTENSIONS)
        or any(keyword in url for keyword in STREAM_KEYWORDS)
    ):
        found.append(resp.url)
                except:
                    pass

            page.on("response", on_response)
            page.goto(url, timeout=20000)
            page.wait_for_timeout(5000)

            browser.close()
    except Exception:
        return []

    return found

@app.route("/find")
def find():
    url = request.args.get("url")

    stream = detect_html(url)
    if stream:
        return jsonify({"stream": stream})

    streams = detect_playwright(url)
    if streams:
        return jsonify({"stream": streams[0]})

    return jsonify({"stream": None})

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
