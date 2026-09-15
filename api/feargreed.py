"""Vercel serverless function: GET /api/feargreed

Proxies CNN's Fear & Greed Index (the browser can't call it directly: CORS + UA check)
and trims it to the current score, comparison points, 1y history and the 7 sub-indicators.
"""
import json
import urllib.request
from http.server import BaseHTTPRequestHandler

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
    "Referer": "https://edition.cnn.com/",
    "Accept": "application/json",
}
INDICATORS = ["market_momentum_sp500", "stock_price_strength", "stock_price_breadth", "put_call_options",
              "market_volatility_vix", "junk_bond_demand", "safe_haven_demand"]


def get_fear_greed():
    with urllib.request.urlopen(urllib.request.Request(URL, headers=HEADERS), timeout=15) as r:
        d = json.load(r)
    return {
        "now": d["fear_and_greed"],
        "history": [[p["x"], round(p["y"], 2)] for p in d["fear_and_greed_historical"]["data"]],
        "indicators": {k: {"score": d[k]["score"], "rating": d[k]["rating"]} for k in INDICATORS if k in d},
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body, status = get_fear_greed(), 200
        except Exception as e:
            body, status = {"error": str(e)}, 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 200:
            self.send_header("Cache-Control", "s-maxage=600, stale-while-revalidate=300")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
