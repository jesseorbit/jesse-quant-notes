#!/usr/bin/env python3
"""
FastAPI Web Server for Arbitrage Scanner

Provides a web interface to view arbitrage opportunities in real-time.
"""

import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from models import ArbitrageOpportunity, StandardMarket
from services import KalshiCollector, PolymarketCollector
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
}


async def scan_markets():
    """Scan markets for arbitrage opportunities."""
    logger.info("Starting market scan...")

    # Collect data
    poly_collector = PolymarketCollector()
    kalshi_collector = KalshiCollector()
    
    poly_markets = await asyncio.get_event_loop().run_in_executor(
        None, poly_collector.fetch_active_markets, None
    )
    
    kalshi_markets = await asyncio.get_event_loop().run_in_executor(
        None, kalshi_collector.fetch_active_markets, None
    )
    
    # Update cache counts
    cache["poly_count"] = len(poly_markets)
    cache["kalshi_count"] = len(kalshi_markets)
    
    # Match and find arbitrage
    matcher = MarketMatcher(similarity_threshold=85.0, min_common_keywords=2)
    all_opportunities = []
    
    # Polymarket vs Kalshi
    if poly_markets and kalshi_markets:
        matches = matcher.find_matches(poly_markets, kalshi_markets)
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


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Arbitrage Scanner</title>
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
            .kalshi { background: #f59e0b; color: white; }
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
            }
            .button:hover { background: #5568d3; }
            .loading {
                text-align: center;
                padding: 40px;
                color: white;
                font-size: 1.2em;
            }
            .no-results {
                text-align: center;
                padding: 60px;
                background: white;
                border-radius: 12px;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Arbitrage Scanner</h1>
                <p style="color: #666; margin-top: 10px;">Real-time prediction market arbitrage opportunities</p>
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
                        <div class="stat-label">Opportunities</div>
                        <div class="stat-value" id="opp-count">-</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Last Update</div>
                        <div class="stat-value" style="font-size: 1.2em;" id="last-update">-</div>
                    </div>
                </div>
                <button class="button" onclick="scanMarkets()" style="margin-top: 20px;">🔄 Scan Markets</button>
            </div>
            
            <div id="results"></div>
        </div>
        
        <script>
            async function scanMarkets() {
                document.getElementById('results').innerHTML = '<div class="loading">⏳ Scanning markets...</div>';
                
                try {
                    const response = await fetch('/scan');
                    const data = await response.json();
                    
                    document.getElementById('poly-count').textContent = data.poly_count.toLocaleString();
                    document.getElementById('kalshi-count').textContent = data.kalshi_count.toLocaleString();
                    document.getElementById('opp-count').textContent = data.opportunities.length;
                    document.getElementById('last-update').textContent = new Date(data.last_update).toLocaleTimeString();
                    
                    displayOpportunities(data.opportunities);
                } catch (error) {
                    document.getElementById('results').innerHTML = '<div class="no-results">❌ Error: ' + error.message + '</div>';
                }
            }
            
            function displayOpportunities(opportunities) {
                const resultsDiv = document.getElementById('results');
                
                if (opportunities.length === 0) {
                    resultsDiv.innerHTML = '<div class="no-results"><h2>No arbitrage opportunities found</h2><p style="margin-top: 10px;">Markets are efficiently priced right now.</p></div>';
                    return;
                }
                
                resultsDiv.innerHTML = '<div class="opportunities">' + opportunities.map((opp, i) => `
                    <div class="opportunity">
                        <div class="roi">ROI: ${opp.roi_percent.toFixed(2)}%</div>
                        <div style="color: #666; margin-bottom: 15px;">
                            Match Score: ${opp.similarity_score.toFixed(1)}/100 | 
                            Profit: <span class="profit">$${opp.profit_margin.toFixed(4)}</span> | 
                            Cost: $${opp.total_cost.toFixed(4)}
                        </div>
                        <div class="market-pair">
                            <div class="market">
                                <span class="platform ${opp.poly_market.platform.toLowerCase()}">${opp.poly_market.platform}</span>
                                <div style="margin-top: 10px; font-weight: 500;">${opp.poly_market.title.substring(0, 80)}...</div>
                                <div class="price">YES: $${opp.poly_market.price_yes.toFixed(3)} | NO: $${opp.poly_market.price_no.toFixed(3)}</div>
                                <a href="${opp.poly_market.url}" target="_blank" style="color: #667eea; text-decoration: none;">View Market →</a>
                            </div>
                            <div class="market">
                                <span class="platform ${opp.counter_market.platform.toLowerCase()}">${opp.counter_market.platform}</span>
                                <div style="margin-top: 10px; font-weight: 500;">${opp.counter_market.title.substring(0, 80)}...</div>
                                <div class="price">YES: $${opp.counter_market.price_yes.toFixed(3)} | NO: $${opp.counter_market.price_no.toFixed(3)}</div>
                                <a href="${opp.counter_market.url}" target="_blank" style="color: #667eea; text-decoration: none;">View Market →</a>
                            </div>
                        </div>
                    </div>
                `).join('') + '</div>';
            }
            
            // Auto-scan on load
            scanMarkets();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/scan")
async def scan():
    """Scan markets and return opportunities."""
    opportunities = await scan_markets()
    
    return {
        "opportunities": [
            {
                "roi_percent": opp.roi_percent,
                "profit_margin": opp.profit_margin,
                "total_cost": opp.total_cost,
                "similarity_score": opp.similarity_score,
                "poly_market": {
                    "platform": opp.poly_market.platform,
                    "title": opp.poly_market.title,
                    "price_yes": opp.poly_market.price_yes,
                    "price_no": opp.poly_market.price_no,
                    "url": opp.poly_market.url,
                },
                "counter_market": {
                    "platform": opp.counter_market.platform,
                    "title": opp.counter_market.title,
                    "price_yes": opp.counter_market.price_yes,
                    "price_no": opp.counter_market.price_no,
                    "url": opp.counter_market.url,
                },
            }
            for opp in opportunities
        ],
        "poly_count": cache["poly_count"],
        "kalshi_count": cache["kalshi_count"],
        "last_update": cache["last_update"].isoformat() if cache["last_update"] else None,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
