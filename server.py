from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import requests
import re
import os

app = Flask(__name__)

# =========================
# STREAM PATTERNS
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

STREAM_KEYWORDS = (
    "manifest",
    "playlist",
    "master",
    "index.mpd",
    "index.m3u8",
    "live",
    "dash",
    "hls",
    "chunk",
    "segment"
)


# =========================
# HTML SCRAPER
# =========================
def detect_html(url):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        html = r.text

        urls = re.findall(r'https?://[^\s"\'<>]+', html)

        for u in urls:
            test = u.lower()

            if (
                any(ext in test for ext in STREAM_EXTENSIONS)
                or any(word in test for word in STREAM_KEYWORDS)
            ):
                return u

        return None

    except:
        return None


# =========================
# PLAYWRIGHT SCRAPER (HEAVY MODE)
# =========================
def detect_playwright(url):
    found = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )

            page = browser.new_page()

            # -------------------------
            # REQUEST INTERCEPT (XHR + fetch)
            # -------------------------
            def on_request(req):
                u = req.url.lower()

                if (
                    any(ext in u for ext in STREAM_EXTENSIONS)
                    or any(word in u for word in STREAM_KEYWORDS)
                ):
                    if req.url not in found:
                        found.append(req.url)

            # -------------------------
            # RESPONSE INTERCEPT
            # -------------------------
            def on_response(resp):
                u = resp.url.lower()

                if (
                    any(ext in u for ext in STREAM_EXTENSIONS)
                    or any(word in u for word in STREAM_KEYWORDS)
                ):
                    if resp.url not in found:
                        found.append(resp.url)

            page.on("request", on_request)
            page.on("response", on_response)

            # -------------------------
            # LOAD PAGE
            # -------------------------
            page.goto(url, timeout=30000, wait_until="networkidle")

            page.wait_for_timeout(4000)

            # -------------------------
            # HTML CONTENT SCAN
            # -------------------------
            html = page.content()

            urls = re.findall(r'https?://[^\s"\'<>]+', html)

            for u in urls:
                test = u.lower()

                if (
                    any(ext in test for ext in STREAM_EXTENSIONS)
                    or any(word in test for word in STREAM_KEYWORDS)
                ):
                    if u not in found:
                        found.append(u)

            # -------------------------
            # SCRIPT SCAN
            # -------------------------
            scripts = page.locator("script").all()

            for s in scripts:
                try:
                    txt = s.inner_text()
                    urls = re.findall(r'https?://[^\s"\'<>]+', txt)

                    for u in urls:
                        test = u.lower()

                        if (
                            any(ext in test for ext in STREAM_EXTENSIONS)
                            or any(word in test for word in STREAM_KEYWORDS)
                        ):
                            if u not in found:
                                found.append(u)
                except:
                    pass

            # -------------------------
            # IFRAMES
            # -------------------------
            for frame in page.frames:
                try:
                    fhtml = frame.content()

                    urls = re.findall(r'https?://[^\s"\'<>]+', fhtml)

                    for u in urls:
                        test = u.lower()

                        if (
                            any(ext in test for ext in STREAM_EXTENSIONS)
                            or any(word in test for word in STREAM_KEYWORDS)
                        ):
                            if u not in found:
                                found.append(u)

                except:
                    pass

            browser.close()

    except Exception:
        return []

    return found


# =========================
# API ENDPOINT
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
            "source": "playwright",
            "count": len(streams)
        })

    return jsonify({
        "stream": None
    })


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
