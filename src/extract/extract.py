import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time
import os

# load .env website api credentials
load_dotenv()
key = os.getenv("WOOCOMMERCE_CONSUMER_KEY") or os.getenv("CONSUMER_KEY")
secret = os.getenv("WOOCOMMERCE_CONSUMER_SECRET") or os.getenv("CONSUMER_SECRET")

url = "https://dcfreshwaterfish.co.uk/wp-json/wc/v3"
last_extraction_file = "data/other/last_extraction_time.json"


def main():
    last_extraction = get_last_extraction_time()
    
    endpoints = [
        "orders",
        # "products",
        # "customers",
        # "coupons",
        # "products/categories",
        # "products/tags",
        # "products/reviews"
    ]
    
    all_raw_data = []

    for endpoint in endpoints:
        if last_extraction:
            print(f"\nFetching new data from {endpoint} since {last_extraction}")
        else:
            print(f"\nFetching all data from {endpoint}")
        
        data = request_data(endpoint, last_extraction)
        
        if data:
            all_raw_data.extend(data)
        else:
            print(f"No new data found for {endpoint}")
    
            
    # save current timestamp (minus 2 mins) if anything new came in
    if all_raw_data:
        extraction_time = (datetime.now() - timedelta(minutes=2)).isoformat()
        save_current_extraction_time(extraction_time)
        print("\nExtraction time updated")
    
    return all_raw_data


def get_last_extraction_time():
    try:
        with open(last_extraction_file, "r") as file:
            payload = json.load(file)
            return payload.get("last_extraction", "")
    except FileNotFoundError:
        return ""


def save_current_extraction_time(extraction_time: str):
    os.makedirs(os.path.dirname(last_extraction_file), exist_ok=True)
    with open(last_extraction_file, "w") as file:
        json.dump({"last_extraction": extraction_time}, file)


def request_data(endpoint, last_extraction):
    page = 1
    all_data = []
    params = {"per_page": 100, "page": page}
    
    if last_extraction != "":
        params["modified_after"] = last_extraction
    
    if endpoint == "orders":
        params["status"] = "any"    
    
    max_retries = 5
    current_retry = 0
    
    while True:
        try:
            if current_retry > 0:
                sleep_time = 2 ** current_retry
                print(f"\nRetrying {endpoint} page {page} in {sleep_time} seconds")
                time.sleep(sleep_time)
            
            result = requests.get(
                f"{url}/{endpoint}",
                auth=(key, secret),
                params=params,
                timeout=60
            )
            result.raise_for_status()
            current_retry = 0
        
        except requests.RequestException as e:
            if current_retry < max_retries:
                current_retry += 1
                print(f"\nError requesting data from {endpoint} page {page}: {e} Retrying")
                continue
            else:
                print(f"\nMax retries reached for {endpoint}. Stopping.")
                break
        
        data = result.json()
        
        if not data:
            break
        
        all_data.extend(data)
        page += 1
        params["page"] = page
    
    return all_data
