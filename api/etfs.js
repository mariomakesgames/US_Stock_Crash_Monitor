// GET /api/etfs — US ETF heat map data.
// Sized by AUM, colored by estimated net flow = Δ shares outstanding × current price.
// Yahoo only exposes the *current* share count, so we keep one snapshot per trading
// day in Vercel Blob (written by the daily cron or the first visit of the day);
// flows accrue from the first snapshot onward.
import { list, put } from "@vercel/blob";

export const GROUPS = {
  "BROAD EQUITY": ["SPY", "IVV", "VOO", "VTI", "QQQ", "IWM", "DIA", "RSP", "MDY", "VUG", "VTV", "SCHD"],
  SECTOR: ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH"],
  INTERNATIONAL: ["EFA", "EEM", "VEA", "VWO", "IEFA", "IEMG", "FXI", "EWJ", "INDA"],
  COMMODITIES: ["GLD", "IAU", "SLV", "USO", "DBC"],
  BONDS: ["TLT", "IEF", "SHY", "AGG", "BND", "LQD", "HYG", "TIP", "BIL", "SGOV"],
};
const SYMBOLS = Object.values(GROUPS).flat();
const HISTORY_PATH = "etf-shares-history.json";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36";
const PERIODS = { "1D": null, "1W": 7, "1M": 30, "3M": 91, YTD: "ytd", "1Y": 365 };

async function yahooQuotes() {
  // Yahoo's quote API needs a session cookie + matching crumb.
  const fc = await fetch("https://fc.yahoo.com", { headers: { "User-Agent": UA }, redirect: "manual" });
  const cookie = fc.headers.getSetCookie().map(c => c.split(";")[0]).join("; ");
  const headers = { "User-Agent": UA, Cookie: cookie };
  const crumb = await (await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb", { headers })).text();
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${SYMBOLS.join(",")}&crumb=${encodeURIComponent(crumb)}`;
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`Yahoo quote HTTP ${r.status}`);
  const out = {};
  for (const q of (await r.json()).quoteResponse.result) {
    out[q.symbol] = {
      name: q.longName || q.shortName || q.symbol,
      price: q.regularMarketPrice,
      shares: q.sharesOutstanding ?? null,
      aum: q.netAssets ?? (q.sharesOutstanding && q.regularMarketPrice ? q.sharesOutstanding * q.regularMarketPrice : null),
      time: q.regularMarketTime,
    };
  }
  return out;
}

async function loadHistory() {
  const { blobs } = await list({ prefix: HISTORY_PATH });
  const blob = blobs.find(b => b.pathname === HISTORY_PATH);
  if (!blob) return [];
  const r = await fetch(`${blob.url}?v=${Date.parse(blob.uploadedAt)}`, { cache: "no-store" });
  return r.ok ? r.json() : [];
}

const nyDate = sec => new Date(sec * 1000).toLocaleDateString("en-CA", { timeZone: "America/New_York" });

// Latest snapshot dated on/before `date` (strictly before today for 1D).
function baseline(history, date, strict) {
  let best = null;
  for (const s of history) if (strict ? s.date < date : s.date <= date) best = s;
  return best ?? history[0];
}

function shiftDate(date, days) {
  const d = new Date(date + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export default async function handler(req, res) {
  try {
    const quotes = await yahooQuotes();
    let history = await loadHistory();

    const marketTime = Math.max(...Object.values(quotes).map(q => q.time || 0));
    const today = nyDate(marketTime);
    const snap = { date: today, shares: Object.fromEntries(Object.entries(quotes).map(([s, q]) => [s, q.shares])) };
    const last = history.at(-1);
    if (!last || last.date !== today || JSON.stringify(last.shares) !== JSON.stringify(snap.shares)) {
      history = [...history.filter(s => s.date !== today), snap].slice(-400);
      await put(HISTORY_PATH, JSON.stringify(history), {
        access: "public", addRandomSuffix: false, allowOverwrite: true, contentType: "application/json", cacheControlMaxAge: 60,
      });
    }

    const bases = Object.fromEntries(Object.entries(PERIODS).map(([p, n]) => {
      const target = n === null ? today : n === "ytd" ? `${today.slice(0, 4)}-01-01` : shiftDate(today, n);
      return [p, baseline(history, target, n === null)];
    }));

    const etfs = [];
    for (const [group, syms] of Object.entries(GROUPS)) {
      for (const sym of syms) {
        const q = quotes[sym];
        if (!q?.aum) continue;
        const flows = {};
        for (const [p, base] of Object.entries(bases)) {
          const prev = base?.shares?.[sym];
          flows[p] = prev && q.shares ? (q.shares - prev) * q.price : 0;
        }
        etfs.push({ symbol: sym, group, name: q.name, price: q.price, aum: q.aum, flows });
      }
    }

    res.setHeader("Cache-Control", "s-maxage=900, stale-while-revalidate=300");
    res.status(200).json({ since: history[0]?.date ?? today, asOf: today, snapshots: history.length, etfs });
  } catch (e) {
    res.status(502).json({ error: String(e?.message || e) });
  }
}
