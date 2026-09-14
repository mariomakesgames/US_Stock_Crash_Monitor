"""Vercel serverless function: GET /api/market?ticker=VOO

Returns ~2y of daily OHLC for the ticker plus the latest 10Y Treasury yield (^TNX),
fetched from Yahoo Finance's chart endpoint. Stdlib only, so the bundle stays tiny.
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ALLOWED = {"VOO", "QQQ"}
UA = {"User-Agent": "Mozilla/5.0"}


def fetch_chart(symbol, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as r:
        return json.load(r)["chart"]["result"][0]


def get_market(ticker):
    res = fetch_chart(ticker, "2y")
    q = res["indicators"]["quote"][0]
    rows = [
        {"t": ts, "o": o, "h": h, "l": l, "c": c}
        for ts, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
        if None not in (o, h, l, c)
    ]
    try:
        tnx = fetch_chart("%5ETNX", "5d")
        closes = [c for c in tnx["indicators"]["quote"][0]["close"] if c is not None]
        us_10y = closes[-1] if closes else 4.0
    except Exception:
        us_10y = 4.0
    return {"ticker": ticker, "rows": rows, "us10y": us_10y}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ticker = parse_qs(urlparse(self.path).query).get("ticker", ["VOO"])[0].upper()
        if ticker not in ALLOWED:
            ticker = "VOO"
        try:
            body, status = get_market(ticker), 200
        except Exception as e:
            body, status = {"error": str(e)}, 502
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 200:
            self.send_header("Cache-Control", "s-maxage=3600, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(data)
