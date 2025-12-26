#!/usr/bin/env python3
"""
FastAPI Web Server for Arbitrage Scanner

Provides a web interface to view arbitrage opportunities in real-time.
"""

import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

# Load environment variables
load_dotenv()
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from models import ArbitrageOpportunity, StandardMarket
from services import PolymarketCollector, KalshiCollector, OpinionCollector
from matcher import MarketMatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Arbitrage Scanner", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache for results
cache = {
    "opportunities": [],
    "last_update": None,
    "poly_count": 0,
    "kalshi_count": 0,
    "opinion_count": 0,
}


def format_maturity(end_date: datetime = None) -> str:
    """Format time to maturity (e.g. 2d10h)."""
    if not end_date:
        return "N/A"
    
    try:
        # Ensure timezone aware
        now = datetime.now(end_date.tzinfo)
        diff = end_date - now
        
        if diff.total_seconds() < 0:
            return "Expired"
            
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        
        if days > 0:
            return f"{days}d{hours}h"
        elif hours > 0:
            return f"{hours}h{minutes}m"
        else:
            return f"{minutes}m"
    except Exception:
        return "Err"


async def scan_markets():
    """Scan markets for arbitrage opportunities."""
    import os
    enable_opinion = bool(os.getenv("OPINION_API_KEY"))
    
    logger.info("Starting market scan...")
    
    # Collect data in parallel
    poly_collector = PolymarketCollector()
    kalshi_collector = KalshiCollector()
    
    tasks = [
        asyncio.to_thread(poly_collector.fetch_active_markets, None),
        asyncio.to_thread(kalshi_collector.fetch_active_markets, limit=None) # Note: Limit arg handled inside class
    ]
    
    if enable_opinion:
        opinion_collector = OpinionCollector()
        tasks.append(asyncio.to_thread(opinion_collector.fetch_active_markets, None))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results safely
    poly_markets = results[0] if not isinstance(results[0], Exception) else []
    if isinstance(results[0], Exception):
        logger.error(f"Polymarket fetch failed: {results[0]}")

    kalshi_markets = results[1] if not isinstance(results[1], Exception) else []
    if isinstance(results[1], Exception):
        logger.error(f"Kalshi fetch failed: {results[1]}")

    opinion_markets = []
    if enable_opinion:
        if isinstance(results[2], Exception):
            logger.error(f"Opinion fetch failed: {results[2]}")
        else:
            opinion_markets = results[2]
            
    # Update cache counts (even if empty/failed, set to 0)
    cache["poly_count"] = len(poly_markets)
    cache["kalshi_count"] = len(kalshi_markets)
    cache["opinion_count"] = len(opinion_markets)
    
    # Match and find arbitrage
    matcher = MarketMatcher(similarity_threshold=90.0, min_common_keywords=2)
    all_opportunities = []
    
    # Polymarket vs Kalshi
    if poly_markets and kalshi_markets:
        matches = matcher.find_matches(poly_markets, kalshi_markets)
        if matches:
            opportunities = matcher.calculate_arbitrage(matches, min_margin=0.02, max_cost=0.98)
            all_opportunities.extend(opportunities)
    
    # Polymarket vs Opinion
    if poly_markets and opinion_markets:
        matches = matcher.find_matches(poly_markets, opinion_markets)
        if matches:
            opportunities = matcher.calculate_arbitrage(matches, min_margin=0.02, max_cost=0.98)
            all_opportunities.extend(opportunities)
    
    # Kalshi vs Opinion
    if kalshi_markets and opinion_markets:
        matches = matcher.find_matches(kalshi_markets, opinion_markets)
        if matches:
            opportunities = matcher.calculate_arbitrage(matches, min_margin=0.02, max_cost=0.98)
            all_opportunities.extend(opportunities)
    
    # Sort by ROI
    all_opportunities.sort(key=lambda x: x.roi_percent, reverse=True)
    
    # Update cache
    cache["opportunities"] = all_opportunities
    cache["last_update"] = datetime.now()
    
    logger.info(f"Scan complete: {len(all_opportunities)} opportunities found")
    
    return all_opportunities


# Global lock for cache updates
cache_lock = asyncio.Lock()

async def background_scanner():
    """Background task to scan markets periodically."""
    while True:
        try:
            logger.info("Starting background market scan...")
            opportunities = await scan_markets()
            
            async with cache_lock:
                # Cache is updated inside scan_markets, but we ensure thread safety here if we were doing more
                pass
                
            logger.info(f"Background scan finished. sleeping for 60s...")
        except Exception as e:
            logger.error(f"Error in background scan: {e}")
            
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    """Start background tasks on server startup."""
    asyncio.create_task(background_scanner())  # Runs every 300s (5m)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Prediction Market Arbitrage Scanner</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            .header {
                background: white;
                border-radius: 16px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            h1 {
                color: #667eea;
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-top: 20px;
            }
            .stat-card {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }
            .stat-label { font-size: 0.9em; color: #666; }
            .stat-value { font-size: 1.8em; font-weight: bold; color: #333; margin-top: 5px; }
            .opportunities {
                display: grid;
                gap: 20px;
            }
            .opportunity {
                background: white;
                border-radius: 12px;
                padding: 25px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            .opportunity:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            }
            .roi {
                font-size: 2em;
                font-weight: bold;
                color: #10b981;
                margin-bottom: 15px;
            }
            .market-pair {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-top: 15px;
            }
            .market {
                padding: 15px;
                background: #f8f9fa;
                border-radius: 8px;
            }
            .platform {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 0.85em;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .poly { background: #667eea; color: white; }
            .kalshi { background: #10b981; color: white; }
            .opinion { background: #f59e0b; color: white; }
            .price { font-size: 1.2em; margin: 10px 0; }
            .profit { color: #10b981; font-weight: bold; }
            .button {
                background: #667eea;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 1em;
                cursor: pointer;
                transition: background 0.2s;
                margin-right: 10px;
            }
            .button:hover { background: #5568d3; }
            .button-secondary {
                background: #94a3b8;
            }
            .button-secondary:hover { background: #64748b; }
            
            .loading-bar {
                display: none;
                margin: 20px 0;
                padding: 15px;
                background: #ebf8ff;
                border: 1px solid #90cdf4;
                color: #2b6cb0;
                border-radius: 8px;
                text-align: center;
            }
            
            .no-results {
                text-align: center;
                padding: 60px;
                background: white;
                border-radius: 12px;
                color: #666;
            }
            .strategy-container {
                display: flex;
                align-items: center;
                gap: 15px;
                background: #f1f5f9;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }
            .step {
                display: flex;
                align-items: center;
                gap: 10px;
                background: white;
                padding: 8px 16px;
                border-radius: 6px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .step-action {
                font-weight: bold;
                color: #64748b;
                font-size: 0.9em;
            }
            .step-side {
                font-weight: 800;
                padding: 2px 8px;
                border-radius: 4px;
            }
            .side-YES { color: #059669; background: #d1fae5; }
            .side-NO { color: #dc2626; background: #fee2e2; }
            
            .step-price { font-family: monospace; font-weight: bold; font-size: 1.1em; color: #334155; }
            .operator { font-weight: bold; color: #94a3b8; font-size: 1.2em; }
            
            .profit-box {
                background: #ecfdf5;
                border: 1px solid #10b981;
                color: #047857;
            }
            
            .disclaimer {
                margin-top: 30px;
                padding: 20px;
                background: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.8);
                border-radius: 8px;
                font-size: 0.85em;
                line-height: 1.5;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Prediction Market Arbitrage Scanner</h1>
                <p style="color: #666; margin-top: 10px;">Real-time arbitrage opportunities across Polymarket, Kalshi, and Opinion Labs.</p>
                
                <div class="stats" id="stats">
                    <div class="stat-card">
                        <div class="stat-label">Polymarket Markets</div>
                        <div class="stat-value" id="poly-count">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Kalshi Markets</div>
                        <div class="stat-value" id="kalshi-count">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Opinion Markets</div>
                        <div class="stat-value" id="opinion-count">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Opportunities</div>
                        <div class="stat-value" id="opp-count">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Last Update</div>
                        <div class="stat-value" style="font-size: 1.2em;" id="last-update">-</div>
                    </div>
                </div>
                
                <div class="loading-bar" id="loading-bar">
                    ⏳ Scanning markets in progress... usually takes 30-60 seconds. Previous data is shown below.
                </div>
                
                <div style="margin-top: 20px;">
                    <button class="button" onclick="loadData()">🔄 Refresh Data</button>
                    <button class="button button-secondary" onclick="forceScan()">⚡ Force Scan (Slow)</button>
                </div>
            </div>
            
            <div id="results"></div>
            
            <div class="disclaimer">
                <strong>Disclaimer:</strong> This tool is for informational purposes only. Prediction markets are volatile and risky. 
                Arbitrage opportunities may disappear quickly due to slippage, fees, or market movement. 
                The developers are not responsible for any financial losses incurred from using this tool. 
                Always verify prices and liquidity on the respective platforms before trading.
                Data is updated automatically every 5 minutes.
            </div>
        </div>
        
        <script>
            function setLoadingState(loading) {
                const buttons = document.querySelectorAll('.button');
                buttons.forEach(btn => {
                    btn.disabled = loading;
                    btn.style.opacity = loading ? '0.6' : '1';
                    btn.style.cursor = loading ? 'not-allowed' : 'pointer';
                });
            }

            async function loadData() {
                // Just load the cached data
                setLoadingState(true);
                // Don't wipe results on simple refresh, just flicker or show loading state if needed
                // document.getElementById('results').innerHTML = '<div class="loading">⏳ Loading data...</div>';
                
                try {
                    const response = await fetch('/scan');
                    const data = await response.json();
                    renderData(data);
                } catch (error) {
                    console.error("Fetch error:", error);
                    // Only show error if we have no results yet
                   if (!document.getElementById('results').children.length) {
                        document.getElementById('results').innerHTML = '<div class="no-results">❌ Error: ' + error.message + '</div>';
                   }
                } finally {
                    setLoadingState(false);
                }
            }

            async function forceScan() {
                // Trigger a real scan
                if (!confirm("This will trigger a full market scan which can take 30-60 seconds. Continue?")) return;
                
                setLoadingState(true);
                document.getElementById('loading-bar').style.display = 'block';
                // Do NOT wipe results - keep showing old data
                
                try {
                    const response = await fetch('/force-refresh', { method: 'POST' });
                    if (response.status === 429) {
                        throw new Error("Scan already in progress. Please wait.");
                    }
                    if (!response.ok) {
                        throw new Error("Server error: " + response.statusText);
                    }
                    const data = await response.json();
                    renderData(data);
                } catch (error) {
                    alert('Scan failed: ' + error.message);
                } finally {
                    setLoadingState(false);
                    document.getElementById('loading-bar').style.display = 'none';
                }
            }
            
            function renderData(data) {
                document.getElementById('poly-count').textContent = data.poly_count.toLocaleString();
                document.getElementById('kalshi-count').textContent = data.kalshi_count.toLocaleString();
                document.getElementById('opinion-count').textContent = data.opinion_count.toLocaleString();
                document.getElementById('opp-count').textContent = data.opportunities.length;
                
                // Format date nicely
                if (data.last_update) {
                    const date = new Date(data.last_update);
                    document.getElementById('last-update').textContent = date.toLocaleTimeString();
                } else {
                    document.getElementById('last-update').textContent = "Never";
                }
                
                displayOpportunities(data.opportunities);
            }
            
            function displayOpportunities(opportunities) {
                const resultsDiv = document.getElementById('results');
                
                if (opportunities.length === 0) {
                    resultsDiv.innerHTML = '<div class="no-results"><h2>No arbitrage opportunities found</h2><p style="margin-top: 10px;">Markets are efficiently priced right now.</p></div>';
                    return;
                }
                
                resultsDiv.innerHTML = '<div class="opportunities">' + opportunities.map((opp, i) => {
                    // Determine prices for display based on side
                    const polyPrice = opp.poly_side === 'YES' ? opp.poly_market.price_yes : opp.poly_market.price_no;
                    const opinionPrice = opp.opinion_side === 'YES' ? opp.opinion_market.price_yes : opp.opinion_market.price_no;
                    
                    return `
                    <div class="opportunity">
                        <div class="roi">ROI: ${opp.roi_percent.toFixed(2)}%</div>
                        
                        <div class="strategy-container">
                            <div class="step">
                                <span class="step-action">BUY</span>
                                <span class="step-side side-${opp.poly_side}">${opp.poly_side}</span>
                                <span class="platform ${opp.poly_market.platform.toLowerCase()}" style="margin: 0;">${opp.poly_market.platform}</span>
                                <span class="step-price">$${polyPrice.toFixed(2)}</span>
                            </div>
                            
                            <div class="operator">+</div>
                            
                            <div class="step">
                                <span class="step-action">BUY</span>
                                <span class="step-side side-${opp.opinion_side}">${opp.opinion_side}</span>
                                <span class="platform ${opp.opinion_market.platform.toLowerCase()}" style="margin: 0;">${opp.opinion_market.platform}</span>
                                <span class="step-price">$${opinionPrice.toFixed(2)}</span>
                            </div>
                            
                            <div class="operator">→</div>
                            
                            <div class="step profit-box">
                                <span style="font-weight: bold; font-size: 0.9em;">PROFIT</span>
                                <span class="step-price" style="color: inherit;">$${opp.profit_margin.toFixed(2)}</span>
                            </div>
                        </div>

                        <div style="color: #666; margin-bottom: 15px; font-size: 0.9em;">
                            Match Score: ${opp.similarity_score.toFixed(1)}/100 | 
                            Total Cost: $${opp.total_cost.toFixed(4)}
                        </div>
                        <div class="market-pair">
                            <div class="market">
                                <span class="platform ${opp.poly_market.platform.toLowerCase()}">${opp.poly_market.platform}</span>
                                <span style="font-size: 0.8em; color: #666; margin-left: 8px;">⏳ ${opp.poly_market.maturity}</span>
                                <div style="margin-top: 10px; font-weight: 500;">${opp.poly_market.title.substring(0, 80)}...</div>
                                <div class="price">YES: $${opp.poly_market.price_yes.toFixed(3)} | NO: $${opp.poly_market.price_no.toFixed(3)}</div>
                                <a href="${opp.poly_market.url}" target="_blank" style="color: #667eea; text-decoration: none;">View Market →</a>
                            </div>
                            <div class="market">
                                <span class="platform ${opp.opinion_market.platform.toLowerCase()}">${opp.opinion_market.platform}</span>
                                <span style="font-size: 0.8em; color: #666; margin-left: 8px;">⏳ ${opp.opinion_market.maturity}</span>
                                <div style="margin-top: 10px; font-weight: 500;">${opp.opinion_market.title.substring(0, 80)}...</div>
                                <div class="price">YES: $${opp.opinion_market.price_yes.toFixed(3)} | NO: $${opp.opinion_market.price_no.toFixed(3)}</div>
                                <a href="${opp.opinion_market.url}" target="_blank" style="color: #667eea; text-decoration: none;">View Market →</a>
                            </div>
                        </div>
                    </div>
                `}).join('') + '</div>';
            }
            
            // Auto-load on load (from cache)
            loadData();
            
            // Auto-refresh every 20 seconds
            setInterval(() => {
                // background refresh only if we aren't currently loading manually
                 const btn = document.querySelector('.button');
                 if (!btn.disabled) {
                     loadData();
                 }
            }, 20000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/scan")
async def scan():
    """Return cached opportunities immediately."""
    return format_response()


@app.post("/force-refresh")
async def force_refresh():
    """Trigger a manual scan and return results."""
    # Use lock to prevent multiple concurrent forced scans
    if cache_lock.locked():
        raise HTTPException(status_code=429, detail="Scan already in progress")
        
    await scan_markets()
    return format_response()


def format_response():
    """Format the current cache into JSON response."""
    opportunities = cache["opportunities"]
    
    return {
        "opportunities": [
            {
                "roi_percent": opp.roi_percent,
                "profit_margin": opp.profit_margin,
                "total_cost": opp.total_cost,
                "similarity_score": opp.similarity_score,
                "strategy": opp.strategy,
                "poly_side": opp.poly_side,
                "opinion_side": opp.opinion_side,
                "poly_market": {
                    "platform": opp.poly_market.platform,
                    "title": opp.poly_market.title,
                    "price_yes": opp.poly_market.price_yes,
                    "price_no": opp.poly_market.price_no,
                    "url": opp.poly_market.url,
                    "maturity": format_maturity(opp.poly_market.end_date),
                },
                "opinion_market": {
                    "platform": opp.opinion_market.platform,
                    "title": opp.opinion_market.title,
                    "price_yes": opp.opinion_market.price_yes,
                    "price_no": opp.opinion_market.price_no,
                    "url": opp.opinion_market.url,
                    "maturity": format_maturity(opp.opinion_market.end_date),
                },
            }
            for opp in opportunities
        ],
        "poly_count": cache["poly_count"],
        "kalshi_count": cache["kalshi_count"],
        "opinion_count": cache["opinion_count"],
        "last_update": cache["last_update"].isoformat() if cache["last_update"] else None,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 to be accessible via tunnel
    uvicorn.run(app, host="0.0.0.0", port=8000)
