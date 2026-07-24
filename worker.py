import os
import json
import subprocess
import urllib.request
import urllib.error
import time

def load_env_file(filepath=".env"):
    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key not in os.environ:
                    os.environ[key] = value

def main():
    # 0. Load local .env file
    load_env_file()

    # 1. Read environment variables
    webhook_url = os.environ.get("GOOGLE_CHAT_WEBHOOK")
    if not webhook_url:
        raise ValueError("Error: GOOGLE_CHAT_WEBHOOK environment variable is missing.")
        
    junie_api_token = os.environ.get("JUNIE_API_TOKEN")
    if not junie_api_token:
        raise ValueError("Error: JUNIE_API_TOKEN environment variable is missing.")

    # 2. Load inventory
    with open("inventory.json", "r", encoding="utf-8") as f:
        inventory = json.load(f)

    process_env = os.environ.copy()
    process_env["JUNIE_API_TOKEN"] = junie_api_token
    
    # 3. Load global prompt
    try:
        with open("prompt.md", "r", encoding="utf-8") as pf:
            global_prompt = pf.read().strip() 
    except FileNotFoundError:
        raise RuntimeError("Error: 'prompt.md' not found.")
        
    # 4. Process feeds
    for item in inventory:
        feed_url = item.get("feed_url")
        if not feed_url:
            continue
            
        print(f"Processing feed: {feed_url}")

        # Fetch the feed content using Python
        try:
            req = urllib.request.Request(
                feed_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Python Feed Reader)'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                feed_content = response.read().decode("utf-8")
        except Exception as e:
            print(f"Error fetching feed from {feed_url}: {e}")
            continue

        # Combine instructions and feed data
        combined_prompt = f"{global_prompt}\n\nHere is the feed content:\n\n{feed_content}"

        # Call junie with the combined prompt
        try:
            result = subprocess.run(
                ["junie", "--prompt", combined_prompt],
                capture_output=True,
                text=True,
                check=True,
                env=process_env
            )
            cli_output = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"junie error for {feed_url}: {e.stderr}")
            continue
        except FileNotFoundError:
            # Fallback path if 'junie' is not in global PATH
            try:
                fallback_path = os.path.expanduser("~/.local/bin/junie")
                result = subprocess.run(
                    [fallback_path, "--prompt", combined_prompt],
                    capture_output=True,
                    text=True,
                    check=True,
                    env=process_env
                )
                cli_output = result.stdout.strip()
            except Exception as ex:
                raise RuntimeError(f"Error: 'junie' was not found on the system. {ex}")

        # 5. Build payload for Google Chat
        payload = {"text": cli_output}
        data = json.dumps(payload).encode("utf-8")

        # 6. Send to Google Chat
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                print(f"Successfully sent. HTTP Status: {response.status}")
        except Exception as e:
            print(f"Error during webhook call: {e}")

        time.sleep(2)

if __name__ == "__main__":
    main()
