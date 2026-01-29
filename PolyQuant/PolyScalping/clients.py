import asyncio
import aiohttp
import json
import time
from typing import List, Dict, Optional, Any
from loguru import logger

from loguru import logger

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, ApiCreds, BalanceAllowanceParams, AssetType
    from py_clob_client.order_builder.constants import BUY, SELL
except ImportError:
    logger.warning("py-clob-client not found. Using Mock client.")
    class ClobClient:
        def __init__(self, **kwargs): pass
        def set_api_creds(self, creds): pass
        def create_or_derive_api_creds(self): return None
        def update_balance_allowance(self): pass
        def get_balance_allowance(self, params): return {"balance": "100.0", "allowance": "1000.0"}
        def get_order_book(self, token_id): return None
        def create_and_post_order(self, args): return {"orderID": "mock-id", "status": "simulated"}
        def cancel(self, order_id): return True
        def cancel_all(self): return True
    
    class ApiCreds:
        def __init__(self, **kwargs): pass

    class OrderArgs:
        def __init__(self, **kwargs): pass

    class BalanceAllowanceParams:
        def __init__(self, **kwargs): pass

    class AssetType:
        COLLATERAL = "collateral"
        CONDITIONAL = "conditional"

    BUY = "buy"
    SELL = "sell"

from config import config
from models import Market, OrderSide

ASSET_TO_TAG_ID = {
    "BTC": "235",
    "ETH": "1002", 
    "SOL": "11060",
    "XRP": "21" # Fallback
}


class PolymarketClient:
    """
    Unified client for Polymarket data (Gamma) and trading (CLOB).
    """
    def __init__(self):
        self.clob_client: Optional[ClobClient] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self._init_clob_client()
        
    def _init_clob_client(self):
        """Initialize the CLOB client with EOA or Proxy mode."""
        try:
            key = config.polymarket_private_key
            if not key:
                logger.warning("No private key found. Trading will be disabled.")
                return

            # Determine Signature Type
            # 0 = EOA (Direct Key)
            # 1 = Gnosis Safe
            # 2 = Polymarket Proxy (Standard for MetaMask users on Polymarket)
            sig_type = 2 if config.use_proxy else 0

            # For Proxy mode, specify funder address
            if sig_type == 2:
                self.clob_client = ClobClient(
                    host=config.polymarket_base_url,
                    key=key,
                    chain_id=137,
                    signature_type=sig_type,
                    funder=config.polymarket_wallet_address,  # Funder/Proxy address
                )
                logger.info(f"Initialized Proxy mode with funder: {config.polymarket_wallet_address}")
            else:
                self.clob_client = ClobClient(
                    host=config.polymarket_base_url,
                    key=key,
                    chain_id=137,
                    signature_type=sig_type,
                )
                logger.info(f"Initialized EOA mode")
            
            # Set API Credentials
            # Always derive credentials from private key (more reliable than explicit keys)
            # Explicit keys from .env often become invalid/expired
            try:
                logger.info("Deriving API credentials from private key...")
                creds = self.clob_client.create_or_derive_api_creds()
                self.clob_client.set_api_creds(creds)
                logger.info(f"✓ Successfully derived API credentials (signature_type={sig_type})")
            except Exception as e:
                logger.error(f"Failed to derive L2 creds: {e}")
                # Fallback to explicit keys if derivation fails
                if config.polymarket_api_key and config.polymarket_api_secret and config.polymarket_api_passphrase:
                    logger.warning("Falling back to explicit API credentials from .env")
                    creds = ApiCreds(
                        api_key=config.polymarket_api_key,
                        api_secret=config.polymarket_api_secret,
                        api_passphrase=config.polymarket_api_passphrase,
                    )
                    self.clob_client.set_api_creds(creds)
                    logger.info("Using explicitly configured API credentials.")
                else:
                    raise
                
            # Update on-chain balance/allowance check (sync)
            try:
                # BalanceAllowanceParams가 필요함
                from py_clob_client.clob_types import BalanceAllowanceParams
                params = BalanceAllowanceParams(
                    asset_type="COLLATERAL"  # USDC
                )
                self.clob_client.update_balance_allowance(params)
                logger.info("Balance and allowance updated.")
            except Exception as e:
                logger.warning(f"Could not update balance/allowance: {e}")

        except Exception as e:
            logger.exception(f"Failed to initialize ClobClient: {e}")
            self.clob_client = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json"}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_active_markets(self, asset: str = "BTC", limit: int = 50, order: str = "volume24hr", ascending: bool = False) -> List[Dict]:
        """
        Fetch active markets for a given asset.
        """
        tag_id = ASSET_TO_TAG_ID.get(asset.upper(), "")
        url = f"{config.polymarket_data_url}/markets"
        
        params = {

            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": order, 
            "ascending": str(ascending).lower(),
            "tag_id": tag_id
        }
        
        if params.get("tag_id") == "":
            del params["tag_id"]
        
        # NOTE: Gamma API is loose. We grab a bunch and filter in logic.
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data can be list or dict with 'data' key
                    if isinstance(data, dict):
                        return data.get("data", [])
                    return data
                else:
                    logger.error(f"Failed to fetch markets: {resp.status}")
                    return []

    async def search_markets(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Search for markets using the Gamma Markets API.
        Example: search_markets("15m")
        """
        url = f"{config.polymarket_data_url}/markets"
        params = {
            "q": query,
            "active": "true",
            "closed": "false",
            "limit": limit
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data is likely a list
                    return data if isinstance(data, list) else data.get("data", [])
                else:
                    logger.error(f"Search failed: {resp.status}")
                    return []

    async def get_user_positions(self, address: str) -> List[Dict]:
        """
        Fetch all user positions from the Data API.
        """
        url = f"{config.polymarket_data_api_url}/positions"
        params = {"user": address}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Failed to fetch positions: {resp.status}")
                    return []

    async def get_usdc_balance(self) -> float:
        """
        Fetch USDC balance of the configured wallet.
        """
        if not self.clob_client:
            return 0.0
        
        try:
            # Requires BalanceAllowanceParams
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            # get_balance_allowance is synchronous in the client usually, 
            # but let's check if it's async in this version.
            # Most py-clob-client methods are synchronous wrappers around requests.
            resp = await asyncio.to_thread(
                self.clob_client.get_balance_allowance,
                params
            )
            if resp:
                b = resp.get("balance", "0")
                return float(b)
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    async def get_orderbook(self, token_id: str):
        """Fetch orderbook for a token."""
        # Prefer CLOB client if available for speed/accuracy? 
        # Actually CLOB client is sync HTTP usually.
        # Let's use Gamma for read if we want async non-blocking easily, 
        # or wrap CLOB call. Wrapper is better for consistency.
        if self.clob_client:
            try:
                return await asyncio.to_thread(self.clob_client.get_order_book, token_id)
            except Exception as e:
                logger.error(f"Error fetching orderbook from CLOB: {e}")
                return None
        return None

    async def place_order(
        self, 
        token_id: str, 
        price: float, 
        size: float, 
        side: OrderSide, 
        post_only: bool = False
    ):
        """Place a limit order."""
        if not config.trading_enabled:
            logger.warning("Trading DISABLED. Order simulated.")
            return {"status": "simulated", "orderID": "sim-123"}
            
        if not self.clob_client:
            logger.error("No ClobClient available.")
            return None

        # DEBUG
        logger.error(f"DEBUG: side type={type(side)}, value={side}, repr={repr(side)}")
        logger.error(f"DEBUG: OrderSide.BUY={OrderSide.BUY}, side==OrderSide.BUY={side == OrderSide.BUY}")

        side_const = BUY if side == OrderSide.BUY else SELL
        logger.error(f"DEBUG: side_const={side_const}, BUY={BUY}, SELL={SELL}")
        
        # Create OrderArgs
        # Note: 'post_only' might not be directly in OrderArgs in some versions, 
        # specify in create_and_post_order or check version. 
        # Py-clob-client uses OrderArgs.
        
        args = OrderArgs(
            price=price,
            size=size,
            side=side_const,
            token_id=token_id,
        )
        
        try:
            # Debug: Log the order details
            logger.info(f"Placing order: token_id={token_id}, price={price}, size={size}, side={side_const}")

            resp = await asyncio.to_thread(
                self.clob_client.create_and_post_order,
                args
            )
            logger.info(f"Order response: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            # Try to get more details from the exception
            if hasattr(e, 'error_message'):
                logger.error(f"Error details: {e.error_message}")
            if hasattr(e, 'status_code'):
                logger.error(f"Status code: {e.status_code}")
            return None

    async def cancel_order(self, order_id: str):
        """Cancel an order."""
        if not config.trading_enabled:
            return True
        
        if not self.clob_client:
            return False
            
        try:
            await asyncio.to_thread(self.clob_client.cancel, order_id)
            return True
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            return False

    async def cancel_all(self):
        """Cancel all open orders."""
        if not config.trading_enabled or not self.clob_client:
            return
        try:
            await asyncio.to_thread(self.clob_client.cancel_all)
        except Exception as e:
            logger.error(f"Cancel all failed: {e}")
