import pandas as pd
import json
import hashlib
import requests
from src.utils.utils import get_db_engine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main(raw_data):
    
    # Check if there is any new order data
    if not raw_data:
        print("No new data to transform")
        return pd.DataFrame()

    orders_data = pd.DataFrame(raw_data)
    
    # Change date columns to datetime
    for column in ["date_modified", "date_created", "date_paid"]:
        orders_data[column] = pd.to_datetime(orders_data[column], errors="coerce")

    # Sort the orders to get most recent
    orders_data.sort_values(by=["id", "date_modified"], ascending=[True, False], inplace=True)
    
    # Remove duplicate orders, keeping only the most recent 
    deduplicated_data = orders_data.drop_duplicates(subset="id", keep="first").copy()
    
    # Convert relevant JSON strings to numbers and change names
    deduplicated_data["order_id"] = pd.to_numeric(deduplicated_data["id"], errors="coerce").astype("Int64")
    deduplicated_data["order_total"] = pd.to_numeric(deduplicated_data["total"], errors="coerce")
    deduplicated_data["shipping_total"] = pd.to_numeric(deduplicated_data["shipping_total"], errors="coerce")
    deduplicated_data["discount_total"] = pd.to_numeric(deduplicated_data["discount_total"], errors="coerce")
    deduplicated_data["total_tax"] = pd.to_numeric(deduplicated_data["total_tax"], errors="coerce")
    
    # Create a customer_identifier from customer ID or a hashed email if they're a guest
    deduplicated_data["customer_identifier"] = deduplicated_data.apply(create_customer_identifier, axis=1)

    # Add latitude and longitude coordinates based on shipping postcode
    deduplicated_data = add_coordinates(deduplicated_data)
    
    # Add other useful columns
    deduplicated_data["is_guest"] = deduplicated_data["customer_id"].fillna(0).astype(int) == 0      # Mark if user was logged in or guest
    deduplicated_data["total_items"] = deduplicated_data["line_items"].apply(count_total_items)      # Count total items in order
    deduplicated_data["distinct_items"] = deduplicated_data["line_items"].apply(count_unique_items) # Count different items in order
    deduplicated_data["order_day"] = deduplicated_data["date_created"].dt.dayofweek                  # Day of the week
    
    # Simplify complicated columns
    deduplicated_data["item_details"] = deduplicated_data["line_items"].apply(simplify_line_items)
    deduplicated_data["coupon_details"] = deduplicated_data["coupon_lines"].apply(simplify_coupon)

    # Get the useful data from metadata
    meta_expanded = pd.DataFrame(
        deduplicated_data["meta_data"].apply(simplify_metadata).tolist(),
        index=deduplicated_data.index,
    )
    deduplicated_data = pd.concat([deduplicated_data, meta_expanded], axis=1)
    
    final_columns = [
        "order_id", "date_created", "date_modified", "date_paid", "status",
        "order_day", "customer_id", "customer_identifier", "is_guest", "order_total",
        "shipping_total", "total_tax", "discount_total", "total_items", "distinct_items",
        "latitude", "longitude", "payment_method_title", "device_type", "item_details",
        "coupon_details", "attribution_source", "campaign_source", "campaign_medium", "referrer_url",
    ]
    
    # Create a new DataFrame with only the useful columns
    processed_data = deduplicated_data[final_columns].copy()
    
    for col in ["item_details", "coupon_details"]:
        processed_data[col] = processed_data[col].apply(
            lambda v: json.loads(v) if isinstance(v, str) else v
        )
    
    # Rename column to match database schema
    processed_data.rename(columns={"payment_method_title": "payment_method"}, inplace=True)
    
    # Sort data from oldest to newest by creation date
    processed_data.sort_values(by="date_created", ascending=True, inplace=True)
    
    # Get rid of NaT error by converting to None
    processed_data["date_created"] = processed_data["date_created"].astype(object).where(pd.notnull(processed_data["date_created"]), None)
    processed_data["date_modified"] = processed_data["date_modified"].astype(object).where(pd.notnull(processed_data["date_modified"]), None)
    processed_data["date_paid"] = processed_data["date_paid"].astype(object).where(pd.notnull(processed_data["date_paid"]), None)
    
    print(f"Transformed {len(processed_data)} records.")
    return processed_data

################################################ customer identification ################################################

# create customer identifier from customer id or their hashed email if not logged in
def create_customer_identifier(order_row):
    
    customer_id_number = pd.to_numeric(order_row.get("customer_id", None), errors="coerce")
    
    if pd.notna(customer_id_number) and customer_id_number > 0:
        return str(int(customer_id_number))
    
    billing_email = order_row.get("billing", {}).get("email")
    
    if pd.notna(billing_email) and str(billing_email).strip():
        # Hash the email to anonomise
        return hashlib.sha256(str(billing_email).strip().lower().encode("utf-8")).hexdigest()
        
    return None

################################################ simplification ################################################
# keeps only the useful information from the ordered items
def simplify_line_items(line_items_list):
    if not isinstance(line_items_list, list):
        return [] 
    
    simple_items = []
    for item in line_items_list:
        try:
            quantity = int(item.get("quantity", 0))
            price = float(item.get("price", 0))
            total = price * quantity
            simple_items.append({
                "product_id": item.get("product_id"),
                "name": item.get("name"),
                "quantity": quantity,
                "total_price": round(total, 2),
            })
        except (TypeError, ValueError):
            continue
    return simple_items

# keeps only the useful information from the coupons
def simplify_coupon(coupon_lines):
    if not isinstance(coupon_lines, list):
        return []
        
    coupons = []
    for item in coupon_lines:
        if isinstance(item, dict):
            coupons.append({
                "code": item.get("code"),
                "discount_amount": float(item.get("discount", 0)),
            })
    return coupons

# keeps only the useful information from the meta data
def simplify_metadata(metadata_list):

    result = {
        "device_type": "Unknown",
        "attribution_source": None,
        "campaign_source": None,
        "campaign_medium": None,
        "referrer_url": None,
    }
    if not isinstance(metadata_list, list):
        return result

    for item in metadata_list:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        val = item.get("value")

        if key == "_wc_order_attribution_device_type" and val:
            result["device_type"] = val
            
        elif key == "_wc_order_attribution_source_type" and val:
            result["attribution_source"] = val
            
        elif key == "_wc_order_attribution_utm_source" and val:
            result["campaign_source"] = val
            
        elif key == "_wc_order_attribution_utm_medium" and val:
            result["campaign_medium"] = val
            
        elif key == "_wc_order_attribution_referrer" and val and not result["referrer_url"]:
            result["referrer_url"] = val
            
        elif key == "_wc_order_attribution_session_referrer" and val and not result["referrer_url"]:
            result["referrer_url"] = val

    return result


################################################ counts ################################################
# total num of items
def count_total_items(item_list):
    if isinstance(item_list, list):
        return sum(int(item.get("quantity", 0)) for item in item_list)
    return 0

# how many different items
def count_unique_items(item_list):
    if isinstance(item_list, list):
        unique_skus = {item.get("sku") for item in item_list if item.get("sku")}
        return len(unique_skus)
    return 0


################################################ postcode ################################################
# standard postcode format for api call
def format_postcode(value):
    if isinstance(value, dict):
        value = value.get("postcode")
    
    if value is None or pd.isna(value):
        return None
    return " ".join(str(value).strip().upper().split()) or None

# api request to get the coordinates for each postcode
def get_coordinates(postcodes):
    found_coordinates = {}
    
    if not isinstance(postcodes, (list, pd.Series)):
        return found_coordinates
    
    api_url = "https://api.postcodes.io/postcodes/"
    
    for start in range(0, len(postcodes), 100):
        batch = [postcode for postcode in postcodes[start : start + 100] if postcode]
        if not batch:
            continue
            
        try:
            response = requests.post(api_url, json={"postcodes": batch}, timeout=30)
            
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") == 200:
                for item in data.get("result", []):
                    requested_postcode = item.get("query")
                    if item.get("result"):
                        latitude = round(item["result"]["latitude"], 2)
                        longitude = round(item["result"]["longitude"], 2)
                        found_coordinates[requested_postcode] = (latitude, longitude)
                    else:
                        found_coordinates[requested_postcode] = (None, None)
            else:
                print(f"API returned status {data.get('status')} for a batch: {batch}")
                for postcode in batch:
                    found_coordinates[postcode] = (None, None)

        except requests.exceptions.RequestException as error:
            print(f"Error getting coordinates for a batch: {error}")
            for postcode in batch:
                found_coordinates[postcode] = (None, None)
                
    return found_coordinates

# add the lat and long columns to dataframe
def add_coordinates(orders_data):
    
    order_postcodes = orders_data["shipping"].apply(format_postcode)
    
    unique_postcodes = order_postcodes.unique()
    
    if len(unique_postcodes) > 0:
        print(f"Requesting coordinates for {len(unique_postcodes)} unique postcodes.")
        all_locations = get_coordinates(unique_postcodes)
    else:
        all_locations = {}

    coordinates_series = order_postcodes.apply(all_locations.get, args=((None, None),))
    
    orders_data["latitude"] = coordinates_series.apply(lambda x: x[0])
    orders_data["longitude"] = coordinates_series.apply(lambda x: x[1])
    
    return orders_data