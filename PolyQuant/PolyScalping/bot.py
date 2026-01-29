import asyncio
import time
from typing import Dict, List, Optional, Set
from loguru import logger
from datetime import datetime
import traceback

from config import config
from utils import current_timestamp, format_pct, format_price, truncate
from models import Market, Position, ActiveOrder, OrderSide
from clients import PolymarketClient
import json

from tracker import MarketDataStreamer
from strategy_logic import PolyScalpingStrategy


class ScalpingBot:
    def __init__(self):
        self.client = PolymarketClient()
        self.tracker = MarketDataStreamer()
        self.strategy = PolyScalpingStrategy()
        self.active_markets: Dict[str, Market] = {}


        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, ActiveOrder] = {} # order_id -> Order
        self.daily_pnl = 0.0
        self.wallet_balance = 0.0
        self.is_running = False
        self.processing_markets: Set[str] = set()
        self.last_sync_time = 0

    async def start(self):
        """Start services."""
        self.is_running = True
        logger.info("Starting PolyScalping Bot...")
        
        # Start tracker
        self.tracker.add_callback(self.on_price_update)
        await self.tracker.start()

        if not config.trading_enabled:
            logger.warning("TRADING IS DISABLED (Dry Run Mode)")

    async def run_loop(self):
        """Main periodic loop."""
        await self.start()
        
        while self.is_running:
            try:
                # 1. Sync Positions & Balance (every 30s)
                if time.time() - self.last_sync_time > 30:
                    await self.sync_positions()
                    self.last_sync_time = time.time()

                # 2. Scan for markets
                await self.scan_markets()
                
                # 3. Global risk check
                self.check_global_risk()

                # Sleep to prevent tight loop
                await asyncio.sleep(5)

            except Exception as e:
                logger.exception(f"Error in main loop: {e}")
                await asyncio.sleep(5)
        
        await self.tracker.stop()

        
        await self.tracker.stop()


    async def scan_markets(self):
        """Find relevant 15m markets."""
        # Clean up old markets
        now = current_timestamp()
        expired = []
        for mid, m in self.active_markets.items():
            # If expired > 10m ago, remove
            end_time = datetime.fromisoformat(m.end_date_iso.replace("Z", "+00:00")).timestamp()
            if now > end_time + 600:
                expired.append(mid)
        
        for mid in expired:
            if mid in self.positions and self.positions[mid].total_exposure > 0.1:
                logger.warning(f"Keeping expired market {mid} due to active position")
            else:
                del self.active_markets[mid]

        # Don't scan if we have max markets
        if len(self.active_markets) >= config.max_concurrent_markets:
            return

        # Fetch new
        # Fetch new using Search API for better 15m discovery
        assets = ["BTC", "ETH", "SOL", "XRP"]
        query = "15m up down"
        candidates = await self.client.search_markets(query, limit=50)
        logger.debug(f"Search found {len(candidates)} candidates for {query}")
        
        for c in candidates:
            if len(self.active_markets) >= config.max_concurrent_markets:
                break
                
            # Filter for asset name and "15m"
            slug = c.get("slug", "").lower()
            question = c.get("question", "").lower()
            
            # Identify which asset this is
            asset_found = None
            for a in assets:
                if a.lower() in slug or a.lower() in question:
                    asset_found = a
                    break
            
            if not asset_found:
                continue
            
            # Check for binary outcomes (UP/DOWN usually is)
            clob_ids = json.loads(c.get("clobTokenIds", "[]"))
            if not clob_ids and "tokens" in c:
                    clob_ids = [t["id"] for t in c["tokens"]]
            
            if len(clob_ids) < 2:
                continue

            # Check expiry
            end_date = c.get("endDate")
            if not end_date:
                continue
            
            try:
                end_ts = datetime.fromisoformat(end_date.replace("Z", "+00:00")).timestamp()
                if end_ts < now:
                    continue 
                if end_ts - now < (config.min_time_to_expiry_minutes * 60):
                    continue
                    
                mid = c["id"]
                if mid not in self.active_markets:
                    logger.info(f"Found new market: {question} ({mid})")
                    m = Market(
                        id=mid,
                        question=c.get("question"),
                        condition_id=c.get("conditionId"),
                        slug=c.get("slug"),
                        end_date_iso=end_date,
                        tokens=clob_ids,
                        outcomes=json.loads(c.get("outcomes", "[]"))
                    )
                    self.active_markets[mid] = m
                    found_markets.append(m)
            except Exception as e:
                logger.error(f"Error parsing market {c.get('id')}: {e}")
        
        # Sync simple subscription
        
        # Sync simple subscription
        # We need to subscribe tracker to all active markets
        for mid, m in self.active_markets.items():
            await self.tracker.subscribe(mid, m.tokens)

    async def on_price_update(self, token_id: str, ob):
        """Event driven callback from tracker."""
        target_market = None
        for m in self.active_markets.values():
            if token_id in m.tokens:
                target_market = m
                break
        
        if not target_market:
            return

        # Check Lock
        if target_market.id in self.processing_markets:
            return

        # Run Strategy immediately
        # Lock
        self.processing_markets.add(target_market.id)
        try:
            await self.execute_strategy_cycle(target_market)
        finally:
            if target_market.id in self.processing_markets:
                self.processing_markets.remove(target_market.id)

    async def sync_positions(self):
        """Reconcile local state with Polymarket Data API."""
        if not config.polymarket_wallet_address:
            return

        logger.info("Syncing positions & balances...")
        
        # 1. Sync Balance
        bal = await self.client.get_usdc_balance()
        if bal > 0:
            self.wallet_balance = bal
            
        # 2. Sync Positions
        real_positions = await self.client.get_user_positions(config.polymarket_wallet_address)
        # Process real positions to update self.positions
        # real_positions is a list of dicts with 'conditionId', 'token_id', 'size', etc.
        
        # Create a map of conditionId -> pos data
        for rp in real_positions:
            cid = rp.get("conditionId")
            size = float(rp.get("size", 0))
            tid = rp.get("assetId") # Data API uses 'assetId' for token id
            avg_price = float(rp.get("avg_price", 0))
            
            # Find which market this belongs to
            target_mid = None
            for mid, m in self.active_markets.items():
                if m.condition_id == cid:
                    target_mid = mid
                    break
            
            if target_mid:
                if target_mid not in self.positions:
                    self.positions[target_mid] = Position(market_id=target_mid)
                
                pos = self.positions[target_mid]
                m = self.active_markets[target_mid]
                
                if tid == m.tokens[0]:
                    pos.shares_yes = size
                    pos.avg_price_yes = avg_price
                elif tid == m.tokens[1]:
                    pos.shares_no = size
                    pos.avg_price_no = avg_price
        
        logger.info(f"Sync complete. Balance: {self.wallet_balance} USDC")

    async def execute_strategy_cycle(self, market: Market):
        # 1. Get Positions (Optimistic from self.positions)
        pos = self.positions.get(market.id)
        if not pos:
            pos = Position(market_id=market.id)
            self.positions[market.id] = pos
            
        # 2. Get Prices from Tracker (Instant)
        bb_yes, ba_yes = self.tracker.get_price(market.tokens[0])
        bb_no, ba_no = self.tracker.get_price(market.tokens[1])
        
        # 3. Update Market object check (for visual reference only)
        market.best_bid_yes = bb_yes
        market.best_ask_yes = ba_yes
        market.best_bid_no = bb_no
        market.best_ask_no = ba_no
        
        # 4. Check Strategy
        signal = self.strategy.check_market(
            token_yes=market.tokens[0],
            token_no=market.tokens[1],
            ask_yes=ba_yes,
            ask_no=ba_no,
            pos_yes=pos.shares_yes,
            pos_no=pos.shares_no,
            avg_price_yes=pos.avg_price_yes,
            avg_price_no=pos.avg_price_no
        )
        
        if signal:
            logger.info(f"⚡ SIGNAL: {signal.reason} | {signal.action} {signal.size} of {signal.token_id}")
            side = OrderSide.BUY if signal.action == "BUY" else OrderSide.SELL
            await self.place_limit_order(market, signal.token_id, signal.price, signal.size, side)

    async def manage_market(self, market: Market):
        """Core logic for a single market."""
        # Deprecated: Strategy runs on events.
        # But maybe we keep this for periodic tasks like position synchronization or heartbeat?
        pass





    async def place_limit_order(self, market: Market, token: str, price: float, size: float, side: OrderSide) -> bool:
        """Wrapper to place order and track it."""
        resp = await self.client.place_order(token, price, size, side)
        if resp and isinstance(resp, dict):
            # Track order
            oid = resp.get("orderID") or "sim-" + str(current_timestamp())
            self.orders[oid] = ActiveOrder(
                order_id=oid,
                market_id=market.id,
                token_id=token,
                side=side,
                price=price,
                size=size,
                timestamp=current_timestamp()
            )
            # Optimistically update position?
            # Ideally we wait for fill.
            # For this prototype, let's NOT update position until we confirm fill (or assume fill if simulating).
            # But the user logic above "manage_market" relies on 'pos' being updated.
            # Hack for Prototype: If 'simulated', update position immediately.
            if resp.get("status") == "simulated":
                self.update_position_simulated(market.id, token, price, size, side, market)
            return True
        return False
    
    def update_position_simulated(self, market_id, token, price, size, side, market):
        """Mock position update for simulation/dry-run."""
        if market_id not in self.positions:
            self.positions[market_id] = Position(market_id=market_id)
        pos = self.positions[market_id]
        
        is_yes = (token == market.tokens[0])
        
        if not pos.first_fill_timestamp:
            pos.first_fill_timestamp = current_timestamp()
            
        if is_yes:
            # Update weighted avg
            total_val = (pos.shares_yes * pos.avg_price_yes) + (size * price)
            pos.shares_yes += size
            pos.avg_price_yes = total_val / pos.shares_yes
            logger.info(f"SIMULATED FILL: YES | New Size: {pos.shares_yes} | Avg: {pos.avg_price_yes}")
        else:
            total_val = (pos.shares_no * pos.avg_price_no) + (size * price)
            pos.shares_no += size
            pos.avg_price_no = total_val / pos.shares_no
            logger.info(f"SIMULATED FILL: NO | New Size: {pos.shares_no} | Avg: {pos.avg_price_no}")

    async def cancer_open_entries(self, market_id: str):
        """Cancel non-exit orders."""
        # scan self.orders for this market
        to_cancel = []
        for oid, order in self.orders.items():
            if order.market_id == market_id:
                # logic to distinguish entry vs exit?
                # For now assume all are cancelable except maybe explicitly marked unwinds.
                to_cancel.append(oid)
        
        for oid in to_cancel:
            await self.client.cancel_order(oid)
            del self.orders[oid]

    def has_order_at_level(self, market_id, token_id, price) -> bool:
        for order in self.orders.values():
            if order.market_id == market_id and order.token_id == token_id:
                if abs(order.price - price) < 0.001:
                    return True
        return False

    def check_global_risk(self):
        """Kill switch."""
        if self.daily_pnl < -config.daily_loss_limit_usdc:
            logger.critical("DAILY LOSS LIMIT REACHED. STOPPING BOT.")
            self.is_running = False

    async def run(self):
        try:
            await self.run_loop()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
