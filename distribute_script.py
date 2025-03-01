import os
import requests
import time
from web3 import Web3

# 1. Ethereum RPC URL (e.g., Infura, local node, etc.)
ETH_RPC_URL = os.environ.get("ETH_RPC_URL", "https://sepolia.infura.io/v3/XXXXXX")
# 2. Private key of the operational wallet for distribution
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "0xyourprivatekey")

# 3. Extract wallet address (from_address)
#   Using web3.eth.account.privateKeyToAccount
web3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
account = web3.eth.account.from_key(PRIVATE_KEY)

def fetch_records(cid, start_date=None, end_date=None):
    """
    Call get_records_cid API to fetch revenue-related records for a specific cid
    """
    url = f"http://localhost:8000/api/get-records/cid/{cid}"
    params = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch records: {resp.text}")
    data = resp.json()
    return data["records"]  # [{cid, blockchain_address, provider_wallet, creator_wallet, price, timestamp}, ...]

def distribute_earnings(records):
    """
    Analyze each transaction in the given list of records
    and distribute earnings to creator and provider.
    """
    # Example distribution: creator 70%, provider 30%
    # If price is in string format, convert to float
    for rec in records:
        creator_wallet = rec["creator_wallet"]
        provider_wallet = rec["provider_wallet"]
        price_wei = web3.to_wei(float(rec["price"]), 'ether')

        creator_amount = int(price_wei * 0.7)
        provider_amount = price_wei - creator_amount

        # 1) Send to creator
        send_transaction(creator_wallet, creator_amount)
        # 2) Send to provider
        send_transaction(provider_wallet, provider_amount)

        print(f"[OK] Distribution completed: cid={rec['cid']} time={rec['timestamp']}")
        # Optionally mark 'distributed' in DB or log record
        time.sleep(1)  # Wait 1 second between transactions as an example

def send_transaction(to_address, amount_wei):
    """
    Send Ether transaction using web3.py
    """
    nonce = web3.eth.get_transaction_count(account.address)
    tx = {
        'nonce': nonce,
        'to': to_address,
        'value': amount_wei,
        'gas': 21000,
        'gasPrice': web3.to_wei('5', 'gwei'),
    }
    signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Transaction completed: to={to_address} amount(wei)={amount_wei} txhash={receipt.transactionHash.hex()}")

if __name__ == "__main__":
    # Test CID
    test_cid = "0x43659dACc5DF5284006df3a504562D6172063999"
    # Example date range
    start_date = "2023-07-01"
    end_date   = "2023-07-31"

    # 1) Fetch records
    records = fetch_records(test_cid, start_date, end_date)
    # 2) Distribute earnings
    distribute_earnings(records)
