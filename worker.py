import os
import json
import subprocess
import urllib.request
import time

def load_env_file(filepath=".env"):
    """
    Loads environment variables from a file if it exists.
    Does not override already existing environment variables (e.g. from CI).
    """
    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Ignore empty lines and comments
            if not line or line.startswith("#"):
                continue
                
            # Split on the first '='
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Only set if not already present in the environment
                if key not in os.environ:
                    os.environ[key] = value

def main():
    # 0. Load local .env file if it exists (for local development)
    load_env_file()

    # 1. Read environment variables (Webhook & API Token)
    webhook_url = os.environ.get("GOOGLE_CHAT_WEBHOOK")
    if not webhook_url:
        raise ValueError("Error: GOOGLE_CHAT_WEBHOOK environment variable is missing.")
        
    junie_api_token = os.environ.get("JUNIE_API_TOKEN")
    if not junie_api_token:
        raise ValueError("Error: JUNIE_API_TOKEN environment variable is missing.")

    # 2. Load inventory
    with open("inventory.json", "r", encoding="utf-8") as f:
        inventory = json.load(f)

    # Prepare environment for the subprocess (merges current env with the token)
    process_env = os.environ.copy()
    process_env["JUNIE_API_TOKEN"] = junie_api_token
    try:
        with open("prompt.md", "r", encoding="utf-8") as pf:
            # .strip() entfernt versehentliche Leerzeilen am Anfang/Ende
            global_prompt = pf.read().strip() 
    except FileNotFoundError:
        raise RuntimeError("Error: 'prompt.md' not found.")
    # 3. Process feeds
    for item in inventory.get("feeds", []):
        feed_url = item.get("feed_url")
        #custom_prompt = item.get("prompt")
        
        custom_prompt=global_prompt
        print(f"Processing feed: {feed_url}")

        # Call junie-cli
        try:
            result = subprocess.run(
                ["junie-cli", "--feed", feed_url, "--prompt", custom_prompt],
                capture_output=True,
                text=True,
                check=True,
                env=process_env
            )
            cli_output = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"junie-cli error for {feed_url}: {e.stderr}")
            continue
        except FileNotFoundError:
            raise RuntimeError("Error: 'junie-cli' was not found on the system.")

        # 4. Build payload for Google Chat
        payload = {"text": cli_output}
        data = json.dumps(payload).encode("utf-8")

        # 5. Send to Google Chat
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

        # 6. Short pause to respect API rate limits
        time.sleep(2)

if __name__ == "__main__":
    main()