import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text, Table, MetaData
from src.utils.utils import get_db_engine
import os
from dotenv import load_dotenv

def main(clean_data):
    # stop if no new orders
    if clean_data.empty:
        print("No data to load")
        return

    # load creds
    load_dotenv()
    db_schema = os.getenv("DB_SCHEMA")
    table_name = f"{db_schema}.luke_customer_orders"

    #connect to db
    engine = get_db_engine()

    # make table if first run
    with engine.begin() as conn:
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            order_id BIGINT PRIMARY KEY,
            date_created TIMESTAMP,
            date_modified TIMESTAMP,
            date_paid TIMESTAMP,
            status VARCHAR(50),
            order_day INT,
            customer_id BIGINT,
            customer_identifier VARCHAR(64),
            is_guest BOOLEAN,
            order_total FLOAT,
            shipping_total FLOAT,
            total_tax FLOAT,
            discount_total FLOAT,
            total_items INT,
            distinct_items INT,
            latitude FLOAT,
            longitude FLOAT,
            payment_method VARCHAR(50),
            device_type VARCHAR(50),
            item_details JSONB,
            coupon_details JSONB,
            attribution_source VARCHAR(100),
            campaign_source VARCHAR(100),
            campaign_medium VARCHAR(100),
            referrer_url VARCHAR(2048)
        );
        """
        conn.execute(text(create_table_sql))

    data_to_insert = clean_data.to_dict(orient="records")

    metadata = MetaData()
    table = Table("luke_customer_orders", metadata, schema=db_schema, autoload_with=engine)

    # chunk the data for first run or its too big
    def chunked(seq, size):
        for i in range(0, len(seq), size):
            yield seq[i:i + size]

    rows_per_batch = 200

    # insert data into table if customer id already exists overwrite all the columns
    with engine.begin() as conn:
        for batch in chunked(data_to_insert, rows_per_batch):
            insert_stmt = insert(table).values(batch)
            upsert_sql = insert_stmt.on_conflict_do_update(
                index_elements=[table.columns["order_id"]],
                set_={
                    "date_created": insert_stmt.excluded.date_created,
                    "date_modified": insert_stmt.excluded.date_modified,
                    "date_paid": insert_stmt.excluded.date_paid,
                    "status": insert_stmt.excluded.status,
                    "order_day": insert_stmt.excluded.order_day,
                    "customer_id": insert_stmt.excluded.customer_id,
                    "customer_identifier": insert_stmt.excluded.customer_identifier,
                    "is_guest": insert_stmt.excluded.is_guest,
                    "order_total": insert_stmt.excluded.order_total,
                    "shipping_total": insert_stmt.excluded.shipping_total,
                    "total_tax": insert_stmt.excluded.total_tax,
                    "discount_total": insert_stmt.excluded.discount_total,
                    "total_items": insert_stmt.excluded.total_items,
                    "distinct_items": insert_stmt.excluded.distinct_items,
                    "latitude": insert_stmt.excluded.latitude,
                    "longitude": insert_stmt.excluded.longitude,
                    "payment_method": insert_stmt.excluded.payment_method,
                    "device_type": insert_stmt.excluded.device_type,
                    "item_details": text("excluded.item_details::jsonb"),
                    "coupon_details": text("excluded.coupon_details::jsonb"),
                    "attribution_source": insert_stmt.excluded.attribution_source,
                    "campaign_source": insert_stmt.excluded.campaign_source,
                    "campaign_medium": insert_stmt.excluded.campaign_medium,
                    "referrer_url": insert_stmt.excluded.referrer_url,
                })
            conn.execute(upsert_sql)

    print("Data uploaded")
