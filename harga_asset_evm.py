import os
import requests
from web3 import Web3

# =========================================================
# CONFIGURATION
# =========================================================

# Ubah CHAIN_ID untuk memilih jaringan
CHAIN_ID = 8453

# Kosongkan untuk native token.
# Isi alamat kontrak untuk memeriksa token ERC-20.
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS") or None

COINGECKO_URL = "https://api.coingecko.com/api/v3"
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"

TIMEOUT = 20

# coin_id:
# CoinGecko ID untuk native token.
#
# platform_id:
# CoinGecko asset platform ID untuk token ERC-20.
# Isi None jika jaringan belum dipetakan.

CHAINS = {
    # Ethereum
    1: {
        "name": "Ethereum Mainnet",
        "rpc": "https://ethereum-rpc.publicnode.com",
        "native_symbol": "ETH",
        "coin_id": "ethereum",
        "platform_id": "ethereum",
    },
    11155111: {
        "name": "Ethereum Sepolia",
        "rpc": "https://ethereum-sepolia-rpc.publicnode.com",
        "native_symbol": "ETH",
        "coin_id": None,
        "platform_id": "ethereum",
    },
    # Base
    8453: {
        "name": "Base Mainnet",
        "rpc": "https://mainnet.base.org",
        "native_symbol": "ETH",
        "coin_id": "ethereum",
        "platform_id": "base",
    },
    84532: {
        "name": "Base Sepolia",
        "rpc": "https://sepolia.base.org",
        "native_symbol": "ETH",
        "coin_id": None,
        "platform_id": "base",
    },
    # BNB Smart Chain
    56: {
        "name": "BNB Smart Chain",
        "rpc": "https://bsc-dataseed.binance.org",
        "native_symbol": "BNB",
        "coin_id": "binancecoin",
        "platform_id": "binance-smart-chain",
    },
    # Polygon PoS
    137: {
        "name": "Polygon PoS",
        "rpc": "https://polygon.drpc.org",
        "native_symbol": "POL",
        "coin_id": "polygon-ecosystem-token",
        "platform_id": "polygon-pos",
    },
    # Arbitrum One
    42161: {
        "name": "Arbitrum One",
        "rpc": "https://arb1.arbitrum.io/rpc",
        "native_symbol": "ETH",
        "coin_id": "ethereum",
        "platform_id": "arbitrum-one",
    },
    # Optimism
    10: {
        "name": "Optimism",
        "rpc": "https://mainnet.optimism.io",
        "native_symbol": "ETH",
        "coin_id": "ethereum",
        "platform_id": "optimistic-ethereum",
    },
    # Avalanche C-Chain
    43114: {
        "name": "Avalanche C-Chain",
        "rpc": "https://api.avax.network/ext/bc/C/rpc",
        "native_symbol": "AVAX",
        "coin_id": "avalanche-2",
        "platform_id": "avalanche",
    },
    # BOT Chain
    677: {
        "name": "BOT Chain Mainnet",
        "rpc": "https://rpc.botchain.ai",
        "native_symbol": "BOT",
        "coin_id": "bot",
        "platform_id": None,
    },
    # Monad
    143: {
        "name": "Monad Mainnet",
        "rpc": "https://rpc.monad.xyz",
        "native_symbol": "MON",
        "coin_id": "monad",
        "platform_id": "monad",
    },
}


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()
session.headers.update(
    {
        "accept": "application/json",
        "user-agent": "EVM-Token-Price-Checker/1.0",
    }
)


def get_json(url, params=None):
    response = session.get(
        url,
        params=params,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


# =========================================================
# CONNECT TO EVM
# =========================================================


def connect_chain():
    if CHAIN_ID not in CHAINS:
        raise ValueError(
            f"Chain ID {CHAIN_ID} belum terdaftar. "
            "Tambahkan konfigurasi ke dictionary CHAINS."
        )

    config = CHAINS[CHAIN_ID]
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))

    if not w3.is_connected():
        raise ConnectionError(
            f"Gagal terhubung ke {config['name']}. "
            "Periksa RPC atau coba endpoint lain."
        )

    actual_chain_id = w3.eth.chain_id

    if actual_chain_id != CHAIN_ID:
        raise ValueError(
            f"Chain ID mismatch: konfigurasi={CHAIN_ID}, " f"RPC={actual_chain_id}"
        )

    return w3, config


# =========================================================
# READ TOKEN SYMBOL AND DECIMALS
# =========================================================

ERC20_ABI = [
    {
        "type": "function",
        "name": "symbol",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
    {
        "type": "function",
        "name": "decimals",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]


def get_token_info(w3, config):
    if CONTRACT_ADDRESS is None:
        return {
            "symbol": config["native_symbol"],
            "decimals": 18,
            "type": "Native Token",
        }

    address = Web3.to_checksum_address(CONTRACT_ADDRESS)

    contract = w3.eth.contract(
        address=address,
        abi=ERC20_ABI,
    )

    try:
        symbol = contract.functions.symbol().call()
        decimals = contract.functions.decimals().call()
    except Exception as exc:
        raise RuntimeError(
            "Gagal membaca symbol/decimals ERC-20. "
            "Pastikan alamat kontrak benar dan token "
            "mengimplementasikan fungsi standar ERC-20."
        ) from exc

    return {
        "symbol": symbol,
        "decimals": decimals,
        "type": "ERC-20",
    }


# =========================================================
# GET TOKEN PRICE FROM COINGECKO
# =========================================================


def get_price_usd(config):
    # Native token: gunakan CoinGecko coin ID.
    if CONTRACT_ADDRESS is None:
        coin_id = config.get("coin_id")

        if not coin_id:
            raise ValueError(
                "Native token ini tidak memiliki CoinGecko "
                "coin ID yang dikonfigurasi. Testnet biasanya "
                "tidak mempunyai harga pasar."
            )

        data = get_json(
            f"{COINGECKO_URL}/simple/price",
            params={
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            },
        )

        coin = data.get(coin_id)

        if not coin or coin.get("usd") is None:
            raise ValueError(f"Harga {coin_id} tidak ditemukan di CoinGecko.")

        return {
            "price_usd": coin["usd"],
            "change_24h": coin.get("usd_24h_change"),
            "updated_at": coin.get("last_updated_at"),
        }

    # ERC-20: gunakan platform ID + alamat kontrak.
    platform_id = config.get("platform_id")

    if not platform_id:
        raise ValueError(
            "Platform ID CoinGecko untuk jaringan ini "
            "belum dikonfigurasi. Tambahkan platform_id "
            "yang benar ke CHAINS."
        )

    address = Web3.to_checksum_address(CONTRACT_ADDRESS)

    data = get_json(
        f"{COINGECKO_URL}/simple/token_price/{platform_id}",
        params={
            "contract_addresses": address,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        },
    )

    token_data = data.get(address.lower())

    if not token_data:
        token_data = data.get(address)

    if not token_data or token_data.get("usd") is None:
        raise ValueError(
            "Harga ERC-20 tidak ditemukan. Token mungkin "
            "belum terdaftar, belum didukung CoinGecko, "
            "atau alamat kontrak/platform ID tidak sesuai."
        )

    return {
        "price_usd": token_data["usd"],
        "change_24h": token_data.get("usd_24h_change"),
        "updated_at": token_data.get("last_updated_at"),
    }


# =========================================================
# USD TO IDR
# =========================================================


def get_usd_to_idr():
    data = get_json(
        FRANKFURTER_URL,
        params={
            "base": "USD",
            "symbols": "IDR",
        },
    )

    rate = data.get("rates", {}).get("IDR")

    if rate is None:
        raise ValueError("Kurs USD/IDR tidak ditemukan.")

    return rate


# =========================================================
# MAIN
# =========================================================


def main():
    w3, config = connect_chain()
    token = get_token_info(w3, config)
    price = get_price_usd(config)
    usd_to_idr = get_usd_to_idr()

    price_usd = price["price_usd"]
    price_idr = price_usd * usd_to_idr

    print("=" * 52)
    print("             EVM TOKEN PRICE CHECKER")
    print("=" * 52)
    print(f"Network       : {config['name']}")
    print(f"Chain ID      : {CHAIN_ID}")
    print(f"Token Type    : {token['type']}")
    print(f"Symbol        : {token['symbol']}")
    print(f"Decimals      : {token['decimals']}")

    if CONTRACT_ADDRESS:
        print(f"Contract      : {CONTRACT_ADDRESS}")

    print("-" * 52)
    print(f"Price USD     : ${price_usd:,.10f}")
    print(f"USD/IDR       : Rp{usd_to_idr:,.2f}")
    print(f"Price IDR     : Rp{price_idr:,.2f}")

    change = price.get("change_24h")
    if change is not None:
        print(f"Change 24h    : {change:+.2f}%")

    timestamp = price.get("updated_at")
    if timestamp:
        from datetime import datetime, timezone

        updated = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        )
        print(f"Price Updated : {updated.isoformat()}")

    print("=" * 52)


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print(f"HTTP/API Error: {exc}")
    except (ValueError, RuntimeError, ConnectionError) as exc:
        print(f"Error: {exc}")
    except Exception as exc:
        print(f"Unexpected Error: {exc}")
