"""
Check USDC balance and allowance on Polymarket
"""
import asyncio
from loguru import logger
from clients import PolymarketClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

async def check_balance():
    """Check current balance and allowance"""
    async with PolymarketClient() as client:
        if not client.clob_client:
            logger.error("No CLOB client available")
            return

        try:
            # Check COLLATERAL (USDC) balance and allowance
            logger.info("Checking USDC balance and allowance...")
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)

            result = await asyncio.to_thread(
                client.clob_client.get_balance_allowance,
                params
            )

            logger.info(f"Result: {result}")

            if result:
                # Balance is in raw units (USDC has 6 decimals)
                balance_raw = int(result.get("balance", "0"))
                balance_usdc = balance_raw / 1_000_000  # Convert to USDC

                logger.info(f"USDC Balance: ${balance_usdc:.2f}")

                # Allowances is a dict of exchange -> allowance
                allowances = result.get("allowances", {})

                if allowances:
                    logger.info(f"Allowances for {len(allowances)} exchanges:")
                    for exchange, allowance_raw in allowances.items():
                        # Allowance also in raw units
                        allowance_usdc = int(allowance_raw) / 1_000_000
                        logger.info(f"  {exchange}: ${allowance_usdc:,.2f}")

                        # Check if this is one of the expected exchanges
                        if exchange == "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E":
                            logger.info(f"    → CTF Exchange")
                        elif exchange == "0xC5d563A36AE78145C45a50134d48A1215220f80a":
                            logger.info(f"    → Neg Risk CTF Exchange")
                        elif exchange == "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296":
                            logger.info(f"    → Neg Risk Adapter")
                else:
                    logger.warning("⚠️ No allowances found!")

                # Check if sufficient
                if balance_usdc < 10:
                    logger.warning(f"⚠️ Low balance: ${balance_usdc:.2f} - need at least $10 for a trade")
                else:
                    logger.success(f"✓ Balance OK: ${balance_usdc:.2f}")

                if not allowances:
                    logger.error("❌ No allowances set - need to approve!")
                    logger.info("Run: python3.11 setup_allowance.py")
                else:
                    # Check if all expected exchanges are approved
                    expected = [
                        "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
                        "0xC5d563A36AE78145C45a50134d48A1215220f80a",
                        "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
                    ]
                    missing = [e for e in expected if e not in allowances]
                    if missing:
                        logger.warning(f"⚠️ Missing allowances for {len(missing)} exchanges")
                    else:
                        logger.success("✓ All exchanges approved!")

        except Exception as e:
            logger.exception(f"Error checking balance: {e}")

if __name__ == "__main__":
    asyncio.run(check_balance())
