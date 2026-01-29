import asyncio
import json
import time
from typing import Dict, List, Optional, Callable, Set
import aiohttp
from loguru import logger
from dataclasses import dataclass, field

from config import config

@dataclass
class OrderBook:
    market_id: str
    token_id: str
    # usage: price -> size
    _bids: Dict[float, float] = field(default_factory=dict)
    _asks: Dict[float, float] = field(default_factory=dict)
    last_updated: float = 0.0

    def update(self, bids: List[Dict], asks: List[Dict]):
        """Update levels from WS message."""
        # 🔍 DEBUG: Log before update
        old_best_bid = self.get_best_bid()
        old_best_ask = self.get_best_ask()

        self._update_side(self._bids, bids)
        self._update_side(self._asks, asks)
        self.last_updated = time.time()

        # 🔍 DEBUG: Log after update if prices changed
        new_best_bid = self.get_best_bid()
        new_best_ask = self.get_best_ask()
        if new_best_bid != old_best_bid or new_best_ask != old_best_ask:
            logger.debug(f"🔄 OrderBook {self.token_id[:16]}... prices changed: bid {old_best_bid:.4f}→{new_best_bid:.4f}, ask {old_best_ask:.4f}→{new_best_ask:.4f}")

    def _update_side(self, side_map: Dict[float, float], updates: List[Dict]):
        for u in updates:
            try:
                p = float(u.get('price', 0))
                s = float(u.get('size', 0))
                if s == 0:
                    if p in side_map:
                        del side_map[p]
                else:
                    side_map[p] = s
            except Exception:
                continue

    def get_best_bid(self) -> float:
        if not self._bids: return 0.0
        return max(self._bids.keys())

    def get_best_ask(self) -> float:
        if not self._asks: return 0.0
        return min(self._asks.keys())
    
    # Optional: Logic to clear if full snapshot implied? 
    # For now assuming updates are persistent or we receive deltas correctly.
    # If connection drops, we should clear.
    def clear(self):
        self._bids.clear()
        self._asks.clear()


class MarketDataStreamer:
    def __init__(self):
        self.ws_url = config.polymarket_ws_url
        self.subscribed_tokens: Set[str] = set()
        self.order_books: Dict[str, OrderBook] = {} # token_id -> OrderBook
        self.callbacks: List[Callable[[str, OrderBook], None]] = []
        self.running = False
        self.ws_task = None
        self.map_token_to_market: Dict[str, str] = {}
        self.msg_queue: asyncio.Queue = asyncio.Queue()
        self.last_msg_time = 0  # 마지막 메시지 수신 시간
        self.msg_count = 0  # 총 받은 메시지 수
        self.last_ping_time = 0  # 마지막 ping 전송 시간
        self.last_pong_time = 0  # 마지막 pong 수신 시간
        self.ping_count = 0  # 총 ping 전송 횟수
        self.pong_count = 0  # 총 pong 수신 횟수
        
    def add_callback(self, cb):
        self.callbacks.append(cb)

    async def subscribe(self, market_id: str, token_ids: List[str]):
        """Request subscription for these tokens."""
        logger.debug(f"📝 Subscribe called for market {market_id[:16]}... with {len(token_ids)} tokens")
        new_tokens = []
        for tid in token_ids:
            if tid not in self.subscribed_tokens:
                self.subscribed_tokens.add(tid)
                self.map_token_to_market[tid] = market_id
                self.order_books[tid] = OrderBook(market_id=market_id, token_id=tid)
                new_tokens.append(tid)
                logger.debug(f"   + Added token: {tid}")

        # Only if already running, send dynamic sub
        if self.running and new_tokens:
            logger.debug(f"📤 Sending subscribe message for {len(new_tokens)} new tokens")
            payload = {
                "operation": "subscribe",
                "assets_ids": new_tokens
            }
            # Put in queue for write loop
            try:
                self.msg_queue.put_nowait(payload)
                logger.info(f"Queued subscription for {len(new_tokens)} tokens")
            except Exception as e:
                logger.error(f"Failed to queue subscription: {e}")


    async def start(self):
        self.running = True
        self.ws_task = asyncio.create_task(self._ws_loop())

    async def stop(self):
        self.running = False
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass

    async def _ws_loop(self):
        logger.info(f"Connecting to WS: {self.ws_url}")
        reconnect_count = 0
        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        self.ws_url,
                        heartbeat=None,  # Disable auto heartbeat - Polymarket doesn't respond to WebSocket pings
                        timeout=aiohttp.ClientTimeout(total=None, sock_read=120)  # 120초 타임아웃
                    ) as ws:
                        if reconnect_count > 0:
                            logger.warning(f"WS Reconnected (attempt #{reconnect_count})")
                        else:
                            logger.info("WS Connected.")
                        reconnect_count += 1

                        # Reset ping/pong tracking
                        self.last_ping_time = time.time()
                        self.last_pong_time = time.time()

                        # Start sender task
                        sender_task = asyncio.create_task(self._write_loop(ws))

                        # Start health monitor task
                        health_task = asyncio.create_task(self._health_monitor(ws))

                        # CRITICAL: Send initial handshake message (required by Polymarket protocol)
                        init_payload = {
                            "assets_ids": [],
                            "type": "market"
                        }
                        await ws.send_json(init_payload)
                        logger.debug("Sent initial market handshake message")

                        # Subscribe to existing tokens immediately (if any)
                        if self.subscribed_tokens:
                            subscribe_payload = {
                                "operation": "subscribe",
                                "assets_ids": list(self.subscribed_tokens)
                            }
                            await ws.send_json(subscribe_payload)
                            logger.info(f"Re-subscribed to {len(self.subscribed_tokens)} tokens after reconnect")

                        try:
                            async for msg in ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    try:
                                        if not msg.data:
                                            continue
                                        data = json.loads(msg.data)
                                        # Track message reception
                                        self.last_msg_time = time.time()
                                        self.msg_count += 1
                                        await self._handle_msg(data)
                                    except Exception as e:
                                        logger.error(f"Error handling msg: {e} | Data: {msg.data}")
                                elif msg.type == aiohttp.WSMsgType.PING:
                                    # Server sent us a ping, aiohttp will auto-respond with pong
                                    logger.debug(f"⬅️  Received PING from server")
                                elif msg.type == aiohttp.WSMsgType.PONG:
                                    # Server responded to our ping
                                    self.last_pong_time = time.time()
                                    self.pong_count += 1
                                    pong_latency = self.last_pong_time - self.last_ping_time
                                    logger.debug(f"⬅️  Received PONG #{self.pong_count} (latency: {pong_latency*1000:.1f}ms)")
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    logger.warning("WS Closed by server")
                                    break
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    logger.error(f"WS Error: {ws.exception()}")
                                    break
                        finally:
                            sender_task.cancel()
                            health_task.cancel()
                            try:
                                await sender_task
                            except asyncio.CancelledError:
                                pass
                            try:
                                await health_task
                            except asyncio.CancelledError:
                                pass

            except Exception as e:
                # Exponential backoff: 2s, 4s, 8s, max 30s
                retry_delay = min(2 ** min(reconnect_count, 4), 30)
                logger.error(f"WS Connection failed: {e}. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)

    async def _write_loop(self, ws):
        """Monitor queue and send messages to WS."""
        try:
            while self.running and not ws.closed:
                # Wait for next message
                msg = await self.msg_queue.get()
                try:
                    await ws.send_json(msg)
                    logger.info(f"Sent dynamic subscription: {msg}")
                except Exception as e:
                    logger.error(f"Failed to send WS message: {e}")
                    # Put back? Or just assume retry on reconnect will handle it if we updated state.
                    # If we fail here, the connection is likely dead, so the main loop will restart.
                    pass
                finally:
                    self.msg_queue.task_done()
        except asyncio.CancelledError:
            pass

    async def _health_monitor(self, ws):
        """Monitor connection health based on message reception."""
        try:
            while self.running and not ws.closed:
                await asyncio.sleep(20)  # 20초마다 체크

                now = time.time()
                time_since_last_msg = now - self.last_msg_time if self.last_msg_time > 0 else 999

                # 120초 (2분) 동안 메시지가 없으면 연결 끊김으로 판단
                if time_since_last_msg > 120:
                    logger.error(f"❌ No messages for {time_since_last_msg:.0f}s - reconnecting...")
                    break  # Trigger reconnect

                # 60초 동안 메시지가 없으면 경고
                elif time_since_last_msg > 60:
                    logger.warning(f"⚠️  No messages for {time_since_last_msg:.0f}s (total: {self.msg_count})")

                # 정상 상태 로그
                elif self.msg_count > 0 and time_since_last_msg < 30 and self.msg_count % 500 == 0:
                    logger.debug(f"✓ WS healthy: {self.msg_count} msgs, last: {time_since_last_msg:.0f}s ago, tokens: {len(self.subscribed_tokens)}")

        except asyncio.CancelledError:
            pass

    async def _handle_msg(self, data):
        # Data is typically a List of updates.
        # [{"market":..., "asset_id":..., "bids":[], "asks":[]}, ...]
        if isinstance(data, list):
            for item in data:
                await self._process_item(item)
        elif isinstance(data, dict):
            await self._process_item(data)

    async def _process_item(self, item):
        # Track if we processed anything relevant
        has_relevant_data = False

        # 🔍 DEBUG: Log raw item structure every 50 messages
        if self.msg_count % 50 == 0:
            logger.debug(f"📦 Raw WS item: {str(item)[:500]}")

        # 방법 1: asset_id가 직접 있는 경우 (orderbook snapshot)
        asset_id = item.get("asset_id")
        if asset_id and asset_id in self.order_books:
            ob = self.order_books[asset_id]
            bids = item.get("bids", [])
            asks = item.get("asks", [])

            # 🔍 DEBUG: Log orderbook data
            if bids or asks:
                logger.debug(f"📊 Orderbook update for {asset_id[:16]}... | Bids: {len(bids)} | Asks: {len(asks)}")
                if bids:
                    logger.debug(f"   Best bid: {bids[0] if bids else 'none'}")
                if asks:
                    logger.debug(f"   Best ask: {asks[0] if asks else 'none'}")

                ob.update(bids, asks)
                has_relevant_data = True

                # 🔍 DEBUG: Log OrderBook state after update
                logger.debug(f"   After update: bid={ob.get_best_bid():.4f} ask={ob.get_best_ask():.4f}")

                # Trigger callbacks immediately for this asset
                for cb in self.callbacks:
                    try:
                        res = cb(asset_id, ob)
                        if asyncio.iscoroutine(res):
                            asyncio.create_task(res)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

        # 방법 2: price_changes가 있는 경우 (실시간 업데이트)
        price_changes = item.get("price_changes", [])
        if price_changes and self.msg_count % 50 == 0:
            logger.debug(f"💱 Price changes: {len(price_changes)} changes")

        # Process price_changes - these are incremental updates to the orderbook
        for change in price_changes:
            asset_id = change.get("asset_id")
            if not asset_id or asset_id not in self.order_books:
                continue

            ob = self.order_books[asset_id]
            side = change.get("side")  # "BUY" or "SELL"
            price = change.get("price")
            size = change.get("size")

            # 🔍 DEBUG: Log price change details (less frequently)
            if self.msg_count % 100 == 0:
                logger.debug(f"   Change: {asset_id[:16]}... {side} @ {price} x {size}")

            if price:
                has_relevant_data = True
                # SELL side = ask (someone wants to sell), BUY side = bid (someone wants to buy)
                if side == "SELL":
                    ob.update([], [{"price": price, "size": size}])  # Update asks
                elif side == "BUY":
                    ob.update([{"price": price, "size": size}], [])  # Update bids

                # Trigger callbacks for each change
                for cb in self.callbacks:
                    try:
                        res = cb(asset_id, ob)
                        if asyncio.iscoroutine(res):
                            asyncio.create_task(res)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

        # Log if we got a message but no relevant data
        if not has_relevant_data and self.msg_count % 100 == 0:
            logger.debug(f"Received message #{self.msg_count} with no relevant orderbook data")

        
    # Public method for bot to get current price instantly
    def get_price(self, token_id: str) -> (float, float):
        """Return (best_bid, best_ask)"""
        if token_id in self.order_books:
            ob = self.order_books[token_id]
            return ob.get_best_bid(), ob.get_best_ask()
        return 0.0, 0.0

    def get_status(self) -> dict:
        """Get WebSocket connection status"""
        now = time.time()
        time_since_last_msg = now - self.last_msg_time if self.last_msg_time > 0 else -1
        # Health is based purely on message reception (Polymarket doesn't respond to WebSocket pings)
        is_healthy = (time_since_last_msg < 60) if time_since_last_msg >= 0 else False
        return {
            "connected": self.running,
            "subscribed_tokens": len(self.subscribed_tokens),
            "total_messages": self.msg_count,
            "last_message_ago": time_since_last_msg,
            "is_healthy": is_healthy
        }

