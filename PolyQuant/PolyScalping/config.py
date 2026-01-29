"""
Configuration management for PolyScalping Bot.
"""
import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Config(BaseSettings):
    """Configuration class for the scalping bot."""
    
    # API Configuration
    # API Credentials
    polymarket_private_key: str = Field(..., env="POLYMARKET_PRIVATE_KEY")
    polymarket_api_key: str = Field(default="", env="POLYMARKET_API_KEY")
    polymarket_api_secret: str = Field(default="", env="POLYMARKET_API_SECRET")
    polymarket_api_passphrase: str = Field(default="", env="POLYMARKET_API_PASSPHRASE")
    use_proxy: bool = Field(default=True, env="USE_PROXY")
    polymarket_wallet_address: str = Field(..., env="POLYMARKET_WALLET_ADDRESS")
    
    # Trading Configuration
    trading_enabled: bool = Field(default=False, env="TRADING_ENABLED")
    max_concurrent_markets: int = Field(default=2, env="MAX_CONCURRENT_MARKETS")
    daily_loss_limit_usdc: float = Field(default=50.0, env="DAILY_LOSS_LIMIT_USDC")
    
    # Timing
    dca_cutoff_minutes: int = 5
    min_time_to_expiry_minutes: int = 5

    # Strategy Parameters
    shares_per_clip: float = 10.0
    
    # Grid Levels
    entry_price_1: float = 0.35
    entry_price_2: float = 0.30
    entry_price_3: float = 0.25
    
    # Exit Rules
    unwind_profit_spread: float = 0.02 # 2% captured spread
    stop_loss_spread: float = -0.10 # -10% negative spread


    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # API Endpoints
    polymarket_base_url: str = "https://clob.polymarket.com"
    polymarket_base_url: str = "https://clob.polymarket.com"
    polymarket_data_url: str = "https://gamma-api.polymarket.com"
    polymarket_data_api_url: str = "https://data-api.polymarket.com"
    polymarket_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore" 

# Global config instance
try:
    config = Config()
except Exception as e:
    print(f"Warning: Error loading config (expected during setup without .env): {e}")
    # Create a dummy config to allow imports
    class DummyConfig:
        polymarket_api_key = ""
        polymarket_private_key = ""
        polymarket_wallet_address = ""
        trading_enabled = False
        log_level = "INFO"
        shares_per_clip = 10.0
        entry_price_1 = 0.35
        entry_price_2 = 0.30
        entry_price_3 = 0.25
        unwind_profit_spread = 0.02
        stop_loss_spread = -0.10

        max_concurrent_markets = 2
        daily_loss_limit_usdc = 50.0
        polymarket_base_url = "https://clob.polymarket.com"
        polymarket_data_url = "https://gamma-api.polymarket.com"
    config = DummyConfig()
