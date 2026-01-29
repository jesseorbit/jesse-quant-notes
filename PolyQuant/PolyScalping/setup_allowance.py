"""
USDC Allowance 설정 스크립트

Polymarket에서 거래하기 전에 실행해야 하는 일회성 스크립트입니다.
USDC와 Conditional Token에 대한 allowance를 Polymarket 컨트랙트에 승인합니다.

사용법:
    python setup_allowance.py

주의:
    - Polygon 네트워크에서 가스비로 약간의 POL (MATIC)이 필요합니다 (보통 < $0.01)
    - 이 스크립트는 한 번만 실행하면 됩니다
    - 실행 전에 .env 파일에 POLYMARKET_PRIVATE_KEY와 POLYMARKET_WALLET_ADDRESS가 설정되어 있어야 합니다
"""

from web3 import Web3
try:
    from web3.middleware import ExtraDataToPOAMiddleware
except ImportError:
    # Web3.py v7+ doesn't need this middleware
    ExtraDataToPOAMiddleware = None
from loguru import logger
from config import config

# Polygon RPC (여러 옵션 시도)
RPC_URLS = [
    "https://polygon-rpc.com",
    "https://rpc-mainnet.matic.network",
    "https://rpc-mainnet.maticvigil.com",
    "https://1rpc.io/matic"
]
CHAIN_ID = 137

# 컨트랙트 주소
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e on Polygon
CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # Conditional Token Framework

# Polymarket Exchange 주소들 (모두 승인 필요)
EXCHANGES = [
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",  # CTF Exchange
    "0xC5d563A36AE78145C45a50134d48A1215220f80a",  # Neg Risk CTF Exchange
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",  # Neg Risk Adapter
]

# ABI
ERC20_APPROVE_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

ERC1155_SET_APPROVAL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "bool", "name": "approved", "type": "bool"}
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


def setup_allowances():
    """USDC와 CTF allowance 설정"""

    # .env에서 설정 읽기
    private_key = config.polymarket_private_key
    wallet_address = config.polymarket_wallet_address

    if not private_key or not wallet_address:
        logger.error("❌ .env 파일에 POLYMARKET_PRIVATE_KEY와 POLYMARKET_WALLET_ADDRESS를 설정해주세요")
        return False

    logger.info("🔧 Polymarket Allowance 설정을 시작합니다...")
    logger.info(f"지갑 주소: {wallet_address}")
    logger.info(f"체인: Polygon (ID: {CHAIN_ID})")

    # Web3 초기화 (여러 RPC 시도)
    web3 = None
    for rpc_url in RPC_URLS:
        try:
            logger.info(f"RPC 연결 시도: {rpc_url}")
            _web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
            if ExtraDataToPOAMiddleware:
                _web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

            if _web3.is_connected():
                web3 = _web3
                logger.success(f"✓ Polygon RPC 연결 성공: {rpc_url}")
                break
            else:
                logger.warning(f"RPC 응답 없음: {rpc_url}")
        except Exception as e:
            logger.warning(f"RPC 연결 실패: {rpc_url} - {e}")
            continue

    if not web3:
        logger.error("❌ 모든 Polygon RPC 연결 실패")
        return False

    # 가스비 확인 (POL 잔액)
    balance_wei = web3.eth.get_balance(web3.to_checksum_address(wallet_address))
    balance_pol = web3.from_wei(balance_wei, 'ether')
    logger.info(f"POL 잔액: {balance_pol:.4f} POL")

    if balance_pol < 0.001:
        logger.warning("⚠️ POL 잔액이 부족할 수 있습니다. 가스비로 최소 0.001 POL이 필요합니다.")

    # 컨트랙트 초기화
    usdc = web3.eth.contract(
        address=web3.to_checksum_address(USDC_ADDRESS),
        abi=ERC20_APPROVE_ABI
    )
    ctf = web3.eth.contract(
        address=web3.to_checksum_address(CTF_ADDRESS),
        abi=ERC1155_SET_APPROVAL_ABI
    )

    # Nonce 가져오기
    nonce = web3.eth.get_transaction_count(web3.to_checksum_address(wallet_address))
    logger.info(f"현재 Nonce: {nonce}")

    total_txs = 0

    # 각 Exchange에 대해 USDC와 CTF 승인
    for i, exchange in enumerate(EXCHANGES, 1):
        exchange_name = [
            "CTF Exchange",
            "Neg Risk CTF Exchange",
            "Neg Risk Adapter"
        ][i-1]

        logger.info(f"\n[{i}/3] {exchange_name} 승인 중...")
        logger.info(f"  주소: {exchange}")

        try:
            # 1. USDC Approval
            logger.info("  📝 USDC Approval 트랜잭션 생성 중...")
            # MAX_INT 처리 (Web3.py 버전에 따라 다름)
            try:
                from web3.constants import MAX_INT
                max_approval = int(MAX_INT, 0)
            except:
                max_approval = 2**256 - 1  # 최대값

            raw_tx = usdc.functions.approve(
                exchange,
                max_approval  # 최대 금액 승인
            ).build_transaction({
                "chainId": CHAIN_ID,
                "from": wallet_address,
                "nonce": nonce,
                "gas": 100000,  # 가스 리미트
                "maxFeePerGas": web3.eth.gas_price * 2,  # 가스 가격
                "maxPriorityFeePerGas": web3.to_wei(30, 'gwei')
            })

            logger.info("  🔐 트랜잭션 서명 중...")
            signed_tx = web3.eth.account.sign_transaction(raw_tx, private_key=private_key)

            logger.info("  📤 USDC Approval 전송 중...")
            tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            logger.info(f"  TX Hash: {tx_hash.hex()}")

            logger.info("  ⏳ 트랜잭션 확인 대기 중...")
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)

            if receipt['status'] == 1:
                logger.success(f"  ✓ USDC Approval 성공!")
                total_txs += 1
            else:
                logger.error(f"  ❌ USDC Approval 실패")
                return False

            nonce += 1

            # 2. CTF Approval
            logger.info("  📝 CTF Approval 트랜잭션 생성 중...")
            raw_tx = ctf.functions.setApprovalForAll(
                exchange,
                True
            ).build_transaction({
                "chainId": CHAIN_ID,
                "from": wallet_address,
                "nonce": nonce,
                "gas": 100000,
                "maxFeePerGas": web3.eth.gas_price * 2,
                "maxPriorityFeePerGas": web3.to_wei(30, 'gwei')
            })

            logger.info("  🔐 트랜잭션 서명 중...")
            signed_tx = web3.eth.account.sign_transaction(raw_tx, private_key=private_key)

            logger.info("  📤 CTF Approval 전송 중...")
            tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            logger.info(f"  TX Hash: {tx_hash.hex()}")

            logger.info("  ⏳ 트랜잭션 확인 대기 중...")
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)

            if receipt['status'] == 1:
                logger.success(f"  ✓ CTF Approval 성공!")
                total_txs += 1
            else:
                logger.error(f"  ❌ CTF Approval 실패")
                return False

            nonce += 1

        except Exception as e:
            logger.error(f"  ❌ 에러 발생: {e}")
            return False

    logger.success(f"\n🎉 모든 Allowance 설정 완료!")
    logger.success(f"총 {total_txs}개 트랜잭션 성공")
    logger.success(f"이제 Polymarket에서 거래할 수 있습니다!")

    return True


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Polymarket USDC Allowance 설정 스크립트")
    logger.info("=" * 60)

    success = setup_allowances()

    if success:
        logger.info("\n다음 단계:")
        logger.info("1. 봇을 실행하세요: python btc_web_server.py")
        logger.info("2. 웹 UI에서 마켓을 추가하면 자동으로 거래가 시작됩니다")
    else:
        logger.error("\n문제가 발생했습니다. 위의 에러 메시지를 확인해주세요.")
        logger.error("도움이 필요하면 다음을 확인하세요:")
        logger.error("- .env 파일에 올바른 PRIVATE_KEY와 WALLET_ADDRESS가 있는지")
        logger.error("- 지갑에 충분한 POL (가스비)이 있는지 (최소 0.001 POL)")
