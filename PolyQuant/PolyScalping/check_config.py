#!/usr/bin/env python3
"""
Quick config verification script
"""
from config import config

print("=" * 60)
print("CONFIG VERIFICATION")
print("=" * 60)
print(f"TRADING_ENABLED: {config.trading_enabled}")
print(f"Type: {type(config.trading_enabled)}")
print(f"Wallet Address: {config.polymarket_wallet_address}")
print(f"Max Concurrent Markets: {config.max_concurrent_markets}")
print(f"Shares Per Clip: {config.shares_per_clip}")
print("=" * 60)

if config.trading_enabled:
    print("✅ LIVE TRADING ACTIVE")
else:
    print("❌ DRY RUN MODE - Orders will NOT execute")
print("=" * 60)
