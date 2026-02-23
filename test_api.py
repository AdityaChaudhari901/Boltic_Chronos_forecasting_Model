import requests
import sys

# Replace this with your actual Boltic deployment URL
URL = "http://localhost:8080" 

def test_health():
    print(f"Testing Health Check at {URL}/health...")
    try:
        r = requests.get(f"{URL}/health")
        print(f"Status: {r.status_code}")
        print(f"Response: {r.json()}")
    except Exception as e:
        print(f"Error: {e}")

def test_forecast(csv_path):
    print(f"\nTesting Forecast CSV at {URL}/forecast/csv...")
    try:
        files = {'file': open(csv_path, 'rb')}
        # Optional: prediction_length=14
        r = requests.post(f"{URL}/forecast/csv?prediction_length=7", files=files)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            import json
            print(json.dumps(r.json(), indent=2))
        else:
            print(f"Error: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        URL = sys.argv[1].rstrip("/")
    
    test_health()
    test_forecast("sample_test_data.csv")
