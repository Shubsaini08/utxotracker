#!/usr/bin/env python3
import argparse
import json
import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
from urllib3 import util
import requests
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Create a lock for thread-safe printing/output
print_lock = threading.Lock()

# ============================================================
# ADDRESS MODE FUNCTIONS (using multiple API endpoints)
# ============================================================

# Create 4 PoolManager instances with different headers (for rotation/fallback)
http1 = urllib3.PoolManager(
    timeout=util.Timeout(5),
    headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/110.0.0.0 Safari/537.36 Header1')
    }
)
http2 = urllib3.PoolManager(
    timeout=util.Timeout(5),
    headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/110.0.0.0 Safari/537.36 Header2')
    }
)
http3 = urllib3.PoolManager(
    timeout=util.Timeout(5),
    headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/110.0.0.0 Safari/537.36 Header3')
    }
)
http4 = urllib3.PoolManager(
    timeout=util.Timeout(5),
    headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/110.0.0.0 Safari/537.36 Header4')
    }
)
http_list = [http1, http2, http3, http4]

def fetch_with_rotating(url, max_attempts=4):
    """
    Attempt to fetch the URL using the available PoolManager instances.
    Returns the decoded data if successful; otherwise, returns None.
    """
    attempt = 0
    while attempt < max_attempts:
        http = random.choice(http_list)
        try:
            response = http.request('GET', url)
            if response.status == 200:
                return response.data
            else:
                with print_lock:
                    print(f"{Fore.YELLOW}API response code {response.status} for URL:{Style.RESET_ALL} {url}")
        except Exception as e:
            with print_lock:
                print(f"{Fore.RED}Error fetching URL {url}:{Style.RESET_ALL} {e}")
        attempt += 1
        time.sleep(0.5)  # delay before next attempt
    return None

def get_address_data(address):
    """
    Fetch detailed data for a Bitcoin address from multiple endpoints.
    Uses blockchain.info, blockcypher, and blockstream as examples.
    """
    endpoints = [
        ('blockchain_balance', f"https://blockchain.info/balance?active={address}"),
        ('blockchain_rawaddr', f"https://blockchain.info/rawaddr/{address}"),
        ('blockcypher', f"https://api.blockcypher.com/v1/btc/main/addrs/{address}"),
        ('blockstream', f"https://blockstream.info/api/address/{address}")
    ]
    results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_api = {executor.submit(fetch_with_rotating, url): name for name, url in endpoints}
        for future in as_completed(future_to_api):
            api_name = future_to_api[future]
            try:
                data = future.result()
                if data is not None:
                    results[api_name] = json.loads(data.decode('utf-8'))
                else:
                    results[api_name] = f"Error: No data received from {api_name}"
            except Exception as e:
                results[api_name] = f"Error: {str(e)}"
    return results

def fetch_transaction_detail(txid):
    """
    Fetch individual transaction details from blockchain.info.
    """
    url = f"https://blockchain.info/rawtx/{txid}?format=json"
    data = fetch_with_rotating(url)
    if data:
        try:
            return json.loads(data.decode('utf-8'))
        except Exception as e:
            return {"error": f"Failed to parse transaction data: {e}"}
    else:
        return {"error": "No data received"}

def get_transactions_details(txids):
    """
    Fetch transaction details concurrently for a list of txids.
    """
    tx_details = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_tx = {executor.submit(fetch_transaction_detail, txid): txid for txid in txids}
        for future in as_completed(future_to_tx):
            txid = future_to_tx[future]
            try:
                tx_details[txid] = future.result()
            except Exception as e:
                tx_details[txid] = {"error": str(e)}
    return tx_details

def display_address_results(address, results):
    """
    Display the fetched address data in a structured format.
    """
    header_line = "=" * 80
    print(header_line)
    print(f"{Fore.CYAN}Bitcoin Address Data for: {address}{Style.RESET_ALL}")
    print(header_line)
    for api_name, data in results.items():
        print(f"\n{Fore.MAGENTA}-- {api_name.upper()} DATA --{Style.RESET_ALL}")
        if isinstance(data, dict):
            print(json.dumps(data, indent=4))
        else:
            print(data)
    print(header_line)

def save_address_results(address, data):
    """
    Save address mode results to a file in utxdump/{address}.log.
    """
    directory = "utxdump"
    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, f"{address}.log")
    try:
        with open(file_path, "w") as f:
            f.write(json.dumps(data, indent=4))
        with print_lock:
            print(f"{Fore.GREEN}Data saved to {file_path}{Style.RESET_ALL}")
    except Exception as e:
        with print_lock:
            print(f"{Fore.RED}Failed to save file:{Style.RESET_ALL} {e}")

def address_mode(address, save_flag):
    """
    Mode to fetch address information and optionally detailed transaction info.
    """
    with print_lock:
        print(f"{Fore.GREEN}Fetching data for address: {address}{Style.RESET_ALL}")
    address_results = get_address_data(address)
    tx_details = {}
    # If blockchain_rawaddr data contains transactions, fetch their details.
    if ('blockchain_rawaddr' in address_results and 
        isinstance(address_results['blockchain_rawaddr'], dict) and
        address_results['blockchain_rawaddr'].get('txs')):
        tx_list = address_results['blockchain_rawaddr'].get('txs', [])
        txids = [tx.get('hash') for tx in tx_list if tx.get('hash')]
        if txids:
            with print_lock:
                print(f"{Fore.GREEN}Found {len(txids)} transactions. Fetching detailed info...{Style.RESET_ALL}")
            tx_details = get_transactions_details(txids)
    combined_results = {
        "address_info": address_results,
        "transaction_details": tx_details
    }
    display_address_results(address, combined_results)
    if save_flag:
        save_address_results(address, combined_results)

# ============================================================
# TRANSACTION DIGGING MODE FUNCTIONS (recursive tx analysis)
# ============================================================

# Global dictionary to track seen addresses and transaction IDs and their counts.
bittrack_dict = {'addresses': [], 'txids': []}

# For counting repeated appearances, we also use the same dict as counters.
# (e.g., bittrack_dict[txid] will hold count if already seen)

def get_tx(txid, network):
    """
    Fetch transaction details from mempool.space API (bitcoin or testnet).
    """
    time.sleep(0.05)
    url = ""
    if network == "bitcoin":
        url = "https://mempool.space/api/tx/" + txid
    elif network == "testnet":
        url = "https://mempool.space/testnet/api/tx/" + txid
    else:
        with print_lock:
            print(f"{Fore.RED}Unknown network: {network}{Style.RESET_ALL}")
        return None
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            with print_lock:
                print(f"{Fore.YELLOW}Non-200 response ({response.status_code}) for tx: {txid}{Style.RESET_ALL}")
    except Exception as e:
        with print_lock:
            print(f"{Fore.RED}An error occurred while fetching tx {txid}:{Style.RESET_ALL} {e}")
    return None

def dig_tx(txid, level, max_level, network):
    """
    Recursively dig into transaction inputs up to max_level.
    """
    if level >= max_level:
        return
    tx = get_tx(txid, network)
    if tx is None:
        with print_lock:
            print(f"{Fore.RED}Error retrieving transaction {txid}. Skipping.{Style.RESET_ALL}")
        return
    if tx.get('vin') is None:
        with print_lock:
            print(f"{Fore.RED}Malformed transaction data for {txid}. Skipping.{Style.RESET_ALL}")
        return
    vin_list = tx['vin']
    vout_list = tx.get('vout', [])
    with print_lock:
        print(f"Level {level} TX {txid} has {len(vin_list)} inputs and {len(vout_list)} outputs.")
        print("Inputs:")
    next_txids = []
    for vin in vin_list:
        input_txid = vin.get('txid')
        prevout = vin.get('prevout', {})
        address = prevout.get('scriptpubkey_address', 'N/A')
        value = prevout.get('value', 0)

        if input_txid and input_txid not in next_txids:
            next_txids.append(input_txid)

        # Track unique txids and addresses (and count occurrences)
        if input_txid:
            if input_txid not in bittrack_dict['txids']:
                bittrack_dict['txids'].append(input_txid)
            else:
                with print_lock:
                    print(f"Detected repeated TX id: {Fore.YELLOW}{input_txid}{Style.RESET_ALL}")
            # Count occurrences in the dictionary
            bittrack_dict[input_txid] = bittrack_dict.get(input_txid, 0) + 1

        if address:
            if address not in bittrack_dict['addresses']:
                bittrack_dict['addresses'].append(address)
            else:
                with print_lock:
                    print(f"Detected repeated address: {Fore.YELLOW}{address}{Style.RESET_ALL}")
            bittrack_dict[address] = bittrack_dict.get(address, 0) + 1

        # Display input info with highlighting if repeated
        txid_highlight = Fore.YELLOW + input_txid + Style.RESET_ALL if bittrack_dict.get(input_txid, 0) > 1 else input_txid
        address_highlight = Fore.YELLOW + address + Style.RESET_ALL if bittrack_dict.get(address, 0) > 1 else address
        with print_lock:
            print(f"{txid_highlight} {value} from {address_highlight}")
    # Recurse for each new transaction id found in inputs
    for next_tx in next_txids:
        dig_tx(next_tx, level + 1, max_level, network)

def display_tx_results():
    """
    Display summary counts for addresses and txids discovered.
    """
    with print_lock:
        print("\n" + "=" * 80)
        print(f"Total involved addresses: {len(bittrack_dict['addresses'])}")
        for addr in bittrack_dict['addresses']:
            count = bittrack_dict.get(addr, 0)
            if count > 1:
                print(f"{Fore.YELLOW}{addr}{Style.RESET_ALL} : {count}")
            else:
                print(f"{addr} : {count}")
        print(f"\nTotal involved txids: {len(bittrack_dict['txids'])}")
        for tx in bittrack_dict['txids']:
            count = bittrack_dict.get(tx, 0)
            if count > 1:
                print(f"{Fore.YELLOW}{tx}{Style.RESET_ALL} : {count}")
            else:
                print(f"{tx} : {count}")
        print("=" * 80)

def save_tx_results():
    """
    Save transaction digging mode results to utxdump/trxids.log.
    """
    directory = "utxdump"
    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, "trxids.log")
    try:
        with open(file_path, "w") as f:
            f.write(json.dumps(bittrack_dict, indent=4))
        with print_lock:
            print(f"{Fore.GREEN}Transaction results saved to {file_path}{Style.RESET_ALL}")
    except Exception as e:
        with print_lock:
            print(f"{Fore.RED}Failed to save transaction results:{Style.RESET_ALL} {e}")

def tx_mode(network, start_txid, max_level, save_flag):
    """
    Run the transaction digging mode.
    """
    with print_lock:
        print(f"{Fore.GREEN}Starting tx digging mode on network '{network}' for txid {start_txid} up to level {max_level}{Style.RESET_ALL}")
    dig_tx(start_txid, 0, max_level, network)
    display_tx_results()
    if save_flag:
        save_tx_results()

# ============================================================
# MAIN: Argument parsing and mode selection
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Advanced Bitcoin Data Explorer and Transaction Digger"
    )
    # Address mode argument
    parser.add_argument('-a', '--address', type=str,
                        help="Bitcoin address to query (address mode)")
    # Global save flag (works for both modes)
    parser.add_argument('-S', '--save', action='store_true',
                        help="Save the results to a file (in utxdump/ directory)")
    # Positional arguments for tx-digging mode (if -a is not used)
    parser.add_argument('network', nargs='?', default="bitcoin",
                        help="Network to use for tx digging (default: bitcoin)")
    parser.add_argument('txid', nargs='?', default=None,
                        help="Transaction ID to start digging")
    parser.add_argument('level', nargs='?', type=int, default=None,
                        help="Max recursion level for tx digging")

    args = parser.parse_args()

    # Decide mode based on arguments: if -a is provided, run address mode.
    if args.address:
        address_mode(args.address.strip(), args.save)
    elif args.txid and args.level is not None:
        tx_mode(args.network, args.txid, args.level, args.save)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()


