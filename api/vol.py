"""Vercel serverless function: GET /api/vol

Daily history (1y) for the two volatility gauges the notes track:
  ^VIX  — equity volatility
  ^MOVE — ICE BofA MOVE, Treasury volatility (Yahoo's name field for this
          symbol is wrong, but the series matches the published MOVE index)
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
SERIES = {"vix": "%5EVIX", "move": "%5EMOVE"}


def fetch(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        res = json.load(r)["chart"]["result"][0]
    points = [[ts * 1000, round(c, 2)] for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
    closes = [p[1] for p in points]
    return {
        "points": points,
        "last": closes[-1],
        "prev": closes[-2] if len(closes) > 1 else closes[-1],
        "week_ago": closes[-6] if len(closes) > 5 else closes[0],
        "low": min(closes),
        "high": max(closes),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body, status = {k: fetch(s) for k, s in SERIES.items()}, 200
        except Exception as e:
            body, status = {"error": str(e)}, 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 200:
            self.send_header("Cache-Control", "s-maxage=900, stale-while-revalidate=300")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
