import os
import json
import subprocess
import urllib.request
import urllib.error
import time
import datetime
import re

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

def clean_ansi(text):
    """Entfernt Terminal-Farbcodes aus dem Output, damit das Chat-Layout nicht kaputt geht."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def main():
    # 0. Load local .env file
    load_env_file()

    # 1. Read environment variables
    webhook_url = os.environ.get("GOOGLE_CHAT_WEBHOOK")
    if not webhook_url:
        raise ValueError("Error: GOOGLE_CHAT_WEBHOOK environment variable is missing.")
        
    junie_api_key = os.environ.get("JUNIE_API_KEY")
    if not junie_api_key:
        raise ValueError("Error: JUNIE_API_KEY environment variable is missing.")

    process_env = os.environ.copy()
    process_env["JUNIE_API_KEY"] = junie_api_key

    # 2. Load inventory and watermarks
    with open("inventory.json", "r", encoding="utf-8") as f:
        inventory = json.load(f)

    watermarks_file = "watermarks.json"
    if os.path.exists(watermarks_file):
        with open(watermarks_file, "r", encoding="utf-8") as f:
            watermarks = json.load(f)
    else:
        watermarks = {}
    
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

        # Inject watermark date into prompt
        last_run = watermarks.get(feed_url, "2000-01-01T00:00:00Z")
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        prompt_with_date = global_prompt.replace("{{LAST_RUN_DATE}}", last_run)

        # Fetch the feed content using Python
        try:
            req = urllib.request.Request(
                feed_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Python Feed Reader)'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                feed_content = response.read().decode("utf-8")
                
                # Truncate content to save LLM context window/tokens
                max_chars = 80000
                if len(feed_content) > max_chars:
                    feed_content = feed_content[:max_chars] + "\n\n... [FEED TRUNCATED]"
        except Exception as e:
            print(f"Error fetching feed from {feed_url}: {e}")
            continue

        # Combine instructions and feed data
        combined_prompt = f"{prompt_with_date}\n\nHere is the feed content:\n\n{feed_content}"

        # Call junie with the combined prompt via standard input (STDIN)
        try:
            result = subprocess.run(
                ["junie"],
                input=combined_prompt,
                capture_output=True,
                text=True,
                check=True,
                timeout=600,
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
                    [fallback_path],
                    input=combined_prompt,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=600,
                    env=process_env
                )
                cli_output = result.stdout.strip()
            except Exception as ex:
                raise RuntimeError(f"Error: 'junie' was not found on the system. {ex}")
        except subprocess.TimeoutExpired:
            print(f"Timeout error for {feed_url}: junie processing exceeded 600 seconds.")
            continue

        # 5. Clean output and evaluate empty state
        clean_output = clean_ansi(cli_output).strip()

        if "NO_NEW_RELEASES" in clean_output:
            print(f"No new releases for {feed_url} since {last_run}. Skipping webhook.")
            continue
            
        if not clean_output:
            print(f"Empty output for {feed_url}. Skipping webhook.")
            continue

        # 6. Build payload for Google Chat
        payload = {"text": clean_output}
        data = json.dumps(payload).encode("utf-8")

        # 7. Send to Google Chat
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                print(f"Successfully sent {feed_url} to Google Chat. Status: {response.status}")
                # Update watermark ONLY on successful transmission
                watermarks[feed_url] = current_time
        except Exception as e:
            print(f"Error during webhook call: {e}")

        time.sleep(2)

    # 8. Save updated watermarks to disk
    with open(watermarks_file, "w", encoding="utf-8") as f:
        json.dump(watermarks, f, indent=2)

if __name__ == "__main__":
    main()