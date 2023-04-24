import requests
import csv
import os
import json
from time import sleep
from web3 import Web3
import asyncio
from tqdm.asyncio import tqdm

GRAPHQL_API_URL = "https://url.to.graphql.here" # Uses custom implementation of graphql. Code needs to be modified in order to talk to the offiial pulsechain graphql server
TOKENS_CSV_FILE = "tokens.csv"
INFURA_URL = "https://rpc.v4.testnet.pulsechain.com"
PULSECHAIN_API_BASE_URL = "https://scan.v4.testnet.pulsechain.com/api"
BRIDGE_PROXY_ADDRESS = "0x6B08a50865aDeCe6e3869D9AfbB316d0a0436B6c"

def run_query(query):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    response = requests.post(GRAPHQL_API_URL, json={"query": query}, headers=headers)

    if response.status_code == 200:
        return response.json()["data"]
    else:
        raise Exception(f"Failed to run query: {response.text}")

def fetch_tokens(skip=0):
    query = f"""
    query MyQuery {{
      tokens(orderBy: totalTransactions, orderDirection: desc, first: 1000, skip: {skip}) {{
        id
        name
        symbol
      }}
    }}
    """
    return run_query(query)["tokens"]

def load_existing_tokens(file_path):
    tokens = {}

    if os.path.exists(file_path):
        with open(file_path, mode="r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                tokens[row["id"]] = row

    return tokens

def save_tokens_to_csv(file_path, tokens):
    with open(file_path, mode="w", newline="") as file:
        fieldnames = ["id", "symbol", "name", "is_bridged_in", "is_bridged_out", "native_address", "bridged_address"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for token in tokens.values():
            writer.writerow(token)


def download_abi(contract_address):
    print("Downloading ABI from Pulse Scan")
    url = f"{PULSECHAIN_API_BASE_URL}?module=contract&action=getabi&address={contract_address}"
    response = requests.get(url)
    data = response.json()
    abi = data["result"]
    return json.loads(abi)

def call_function_through_proxy(proxy_address, proxy_abi, function_name, web3, *args):
    proxy_contract = web3.eth.contract(address=proxy_address, abi=proxy_abi)
    function = proxy_contract.get_function_by_name(function_name)
    try:
        if args:
            result = function(*args).call()
        else:
            result = function().call()
        return result
    except ValueError:
        return None


def get_implementation_address(proxy_address, proxy_abi, web3):
    proxy_contract = web3.eth.contract(address=proxy_address, abi=proxy_abi)
    implementation_address = proxy_contract.functions.implementation().call()
    return implementation_address

def update_token_bridge_info(token, web3, proxy_address, implementation_abi):
    token_address = web3.toChecksumAddress(token["id"])
    bridged_token_address = call_function_through_proxy(proxy_address, implementation_abi, "bridgedTokenAddress", web3, token_address)
    native_token_address = call_function_through_proxy(proxy_address, implementation_abi, "nativeTokenAddress", web3, token_address)

    if bridged_token_address != "0x0000000000000000000000000000000000000000":
        token["is_bridged_out"] = True
        token["bridged_address"] = bridged_token_address

    if native_token_address != "0x0000000000000000000000000000000000000000":
        token["is_bridged_in"] = True
        token["native_address"] = native_token_address

    return token


async def update_tokens_async(token, web3, proxy_address, implementation_abi, tokens_with_bridge_info):
    if token["id"] not in tokens_with_bridge_info:
        new_token = {
            "id": token["id"],
            "symbol": token["symbol"],
            "name": token["name"],
            "is_bridged_in": False,
            "is_bridged_out": False,
            "native_address": "",
            "bridged_address": ""
        }
        updated_token = await asyncio.to_thread(update_token_bridge_info, new_token, web3, proxy_address, implementation_abi)
        return updated_token
    return None


async def main():
    web3 = Web3(Web3.HTTPProvider(INFURA_URL))
    print("Connected to RPC endpoint")

    proxy_abi = download_abi(BRIDGE_PROXY_ADDRESS)
    implementation_address = get_implementation_address(BRIDGE_PROXY_ADDRESS, proxy_abi, web3)
    print(f"Implementation address: {implementation_address}")
    implementation_abi = download_abi(implementation_address)

    print("Fetching tokens from GraphQL API...")
    tokens = []
    skip = 0
    while True:
        fetched_tokens = fetch_tokens(skip)
        if not fetched_tokens:
            break
        tokens.extend(fetched_tokens)
        skip += len(fetched_tokens)

    if not os.path.exists(TOKENS_CSV_FILE):
        print("Tokens CSV file not found. Building a new tokens database.")
        tokens_with_bridge_info = {}
    else:
        print(f"Reading tokens from {TOKENS_CSV_FILE}")
        tokens_with_bridge_info = load_existing_tokens(TOKENS_CSV_FILE)

    save_tokens_to_csv(TOKENS_CSV_FILE, tokens_with_bridge_info)
    print(f"Saved {len(tokens_with_bridge_info)} tokens to {TOKENS_CSV_FILE}")

    new_tokens = []

    print("Checking tokens for bridged parameters...")
    tasks = []
    for token in tokens:
        tasks.append(update_tokens_async(token, web3, BRIDGE_PROXY_ADDRESS, implementation_abi, tokens_with_bridge_info))

    for updated_token in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
        result = await updated_token
        if result:
            new_tokens.append(result)
            tokens_with_bridge_info[result["id"]] = result

    if new_tokens:
        save_tokens_to_csv(TOKENS_CSV_FILE, tokens_with_bridge_info)
        print(f"Added {len(new_tokens)} new tokens to {TOKENS_CSV_FILE}")
    else:
        print("No new tokens found")


if __name__ == "__main__":
    asyncio.run(main())
