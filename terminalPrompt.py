import json
import requests
from web3 import Web3

PULSECHAIN_API_BASE_URL = 'https://scan.v4.testnet.pulsechain.com/api'


def download_abi(contract_address):
    print('Downloading ABI from Pulse Scan')
    url = f'{PULSECHAIN_API_BASE_URL}?module=contract&action=getabi&address={contract_address}'
    response = requests.get(url)
    data = response.json()
    abi = data['result']
    return json.loads(abi)


def call_function_through_proxy(proxy_address, proxy_abi, function_name, web3, *args):
    proxy_contract = web3.eth.contract(address=proxy_address, abi=proxy_abi)
    function = proxy_contract.get_function_by_name(function_name)
    if args:
        result = function(*args).call()
    else:
        result = function().call()
    return result

def get_implementation_address(proxy_address, proxy_abi, web3):
    proxy_contract = web3.eth.contract(address=proxy_address, abi=proxy_abi)
    implementation_address = proxy_contract.functions.implementation().call()
    return implementation_address




def main():
    infura_url = 'https://rpc.v4.testnet.pulsechain.com'
    web3 = Web3(Web3.HTTPProvider(infura_url))
    print('Connected to RPC endpoint')

    proxy_address = '0x6B08a50865aDeCe6e3869D9AfbB316d0a0436B6c'
    proxy_abi = download_abi(proxy_address)

    implementation_address = get_implementation_address(proxy_address, proxy_abi, web3)
    print(f'Implementation address: {implementation_address}')
    implementation_abi = download_abi(implementation_address)

    while True:
        print("\nSelect a function:")
        print("1. Get bridged token address")
        print("2. Get native token address")
        print("3. Get mediator contract on the other side")
        print("4. Exit")

        choice = int(input("Enter your choice (1, 2, 3, 4, or 5): "))

        if choice == 1:
            token_address = input("Enter the token address: ")
            token_address = web3.toChecksumAddress(token_address)
            bridged_token_address = call_function_through_proxy(proxy_address, implementation_abi, "bridgedTokenAddress", web3, token_address)
            print(f"Bridged token address: {bridged_token_address}")
        elif choice == 2:
            token_address = input("Enter the token address: ")
            token_address = web3.toChecksumAddress(token_address)
            native_token_address = call_function_through_proxy(proxy_address, implementation_abi, "nativeTokenAddress", web3, token_address)
            print(f"Native token address: {native_token_address}")
        elif choice == 3:
            mediator_contract_on_other_side = call_function_through_proxy(proxy_address, implementation_abi, "mediatorContractOnOtherSide", web3)
            print(f"Mediator contract on the other side: {mediator_contract_on_other_side}")
        elif choice == 4:
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")


if __name__ == '__main__':
    main()
