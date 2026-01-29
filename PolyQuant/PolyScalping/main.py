import asyncio
import os
from bot import ScalpingBot
from config import config

async def main():
    # Force dry run
    os.environ["TRADING_ENABLED"] = "False"
    config.trading_enabled = False
    
    bot = ScalpingBot()
    
    print("--------------------------------")
    print("Starting PolyScalping Bot (Dry Run)")
    print(f"Tracking Assets: BTC, ETH, SOL, XRP")
    print(f"Strategies: Entry < {config.entry_price}")
    print(f"Risk: TP Spread {config.unwind_profit_spread*100}%, SL Spread {config.stop_loss_spread*100}%")
    print("--------------------------------")
    
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
