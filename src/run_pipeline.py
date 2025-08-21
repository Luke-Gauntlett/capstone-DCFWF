import pandas as pd
from src.extract.extract import main as extract_main
from src.transform.transform import main as transform_main
from src.load.load import main as load_main

def run_pipeline():
    print("--- Starting Data Pipeline ---")

    try:
        raw_data = extract_main()
    except Exception as e:
        print(f"Extraction failed: {e}")
        return

    try:
        clean_data = transform_main(raw_data)
    except Exception as e:
        print(f"Transformation failed: {e}")
        return
        
    try:
        load_main(clean_data)
    except Exception as e:
        print(f"Loading failed: {e}")
        return

    print("--- Pipeline Finished ---")

if __name__ == "__main__":
    run_pipeline()