# scripts/test_postcodes_api.py
# Minimal diagnostics for https://api.postcodes.io
# Usage:
#   python scripts/test_postcodes_api.py
#   python scripts/test_postcodes_api.py --postcodes "SW1A 1AA,EC1A 1BB"
#   python scripts/test_postcodes_api.py --timeout 20 --batch-size 50

import argparse, sys, time, json
import requests

DEFAULT_POSTCODES = [
    "SW1A 1AA",  # London
    "EC1A 1BB",  # London
    "EH1 1AA",   # Edinburgh
    "CF10 1AA",  # Cardiff
    "BT1 1AA",   # Belfast
    "G1 1AA",    # Glasgow
    "M1 1AA",    # Manchester
    "B1 1AA",    # Birmingham
    "LS1 1AA",   # Leeds
    "BS1 1AA",   # Bristol
]

BASE_SINGLE = "https://api.postcodes.io/postcodes"
BASE_BATCH  = "https://api.postcodes.io/postcodes"   # POST with {"postcodes": [...]}

def norm_pc(s: str) -> str:
    return " ".join(str(s).strip().upper().replace("\xa0", " ").split())

def headers_info(h):
    out = []
    for k in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        if k in h:
            out.append(f"{k}={h[k]}")
    return "; ".join(out) if out else "(no ratelimit headers)"

def test_single(postcodes, timeout) -> bool:
    print("\n== Single GET checks ==")
    ok = True
    sess = requests.Session()
    for pc in postcodes[:min(5, len(postcodes))]:
        url = f"{BASE_SINGLE}/{requests.utils.quote(pc)}"
        t0 = time.time()
        try:
            r = sess.get(url, timeout=timeout)
            ms = int((time.time() - t0) * 1000)
            print(f"GET {pc} -> HTTP {r.status_code} in {ms} ms | {headers_info(r.headers)}")
            if r.status_code != 200:
                print(f"  Body: {r.text[:200]}")
                ok = False
                continue
            data = r.json()
            if data.get("status") != 200 or data.get("result") is None:
                print(f"  Unexpected payload: {json.dumps(data)[:200]}")
                ok = False
            else:
                lat = data["result"]["latitude"]; lon = data["result"]["longitude"]
                print(f"  lat/lon: {lat}, {lon}")
        except requests.RequestException as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            ok = False
    return ok

def test_batch(postcodes, timeout, batch_size) -> bool:
    print("\n== Batch POST check ==")
    pcs = [norm_pc(p) for p in postcodes]
    pcs = pcs[:batch_size] if batch_size else pcs
    payload = {"postcodes": pcs}
    t0 = time.time()
    try:
        r = requests.post(BASE_BATCH, json=payload, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        print(f"POST {len(pcs)} postcodes -> HTTP {r.status_code} in {ms} ms | {headers_info(r.headers)}")
        if r.status_code != 200:
            print(f"  Body: {r.text[:400]}")
            return False
        data = r.json()
        if data.get("status") != 200 or "result" not in data:
            print(f"  Unexpected payload: {json.dumps(data)[:400]}")
            return False
        results = data["result"]
        resolved = sum(1 for item in results if item.get("result"))
        unresolved = len(results) - resolved
        print(f"  Resolved: {resolved} | Unresolved: {unresolved} (of {len(results)})")
        # Show a couple of examples
        for item in results[:3]:
            q = item.get("query")
            res = item.get("result")
            if res:
                print(f"   ✓ {q}: ({res['latitude']}, {res['longitude']})")
            else:
                print(f"   ✗ {q}: not found")
        return True
    except requests.RequestException as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return False

def main():
    ap = argparse.ArgumentParser(description="Test api.postcodes.io connectivity & responses")
    ap.add_argument("--postcodes", type=str, default="", help="Comma-separated list to test")
    ap.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds (default 30)")
    ap.add_argument("--batch-size", type=int, default=100, help="Batch size for POST (default 100)")
    args = ap.parse_args()

    if args.postcodes:
        postcodes = [norm_pc(x) for x in args.postcodes.split(",") if x.strip()]
    else:
        postcodes = [norm_pc(x) for x in DEFAULT_POSTCODES]

    # Quick connectivity probe
    try:
        ping = requests.get("https://api.postcodes.io/health", timeout=args.timeout)
        print(f"Health: HTTP {ping.status_code} | {ping.text.strip()[:200]}")
        if ping.status_code >= 400:
            print("(!) Health check failed; service might be down or blocked.")
    except requests.RequestException as e:
        print(f"Health: ERROR {type(e).__name__}: {e}")
        print("Your network/DNS/TLS may be blocking the API.")
        sys.exit(2)

    ok1 = test_single(postcodes, args.timeout)
    ok2 = test_batch(postcodes, args.timeout, args.batch_size)

    # Exit codes:
    # 0 = all good; 1 = API reachable but problems in responses; 2 = connectivity error
    if ok1 and ok2:
        print("\nResult: OK")
        sys.exit(0)
    else:
        print("\nResult: API reachable but issues detected.")
        sys.exit(1)

if __name__ == "__main__":
    main()
