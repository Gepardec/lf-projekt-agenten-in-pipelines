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

def send_gchat_message(webhook_url, text, thread_key=None):
    """Hilfsfunktion zum Senden von Nachrichten an Google Chat."""
    payload = {"text": text}
    data = json.dumps(payload).encode("utf-8")
    url = webhook_url
    if thread_key:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD&threadKey={thread_key}"
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except Exception as e:
        print(f"Error sending to Google Chat: {e}")
        return False

def call_junie(prompt_text, env_dict, timeout=600):
    """Führt junie CLI sicher aus und nutzt automatisch den lokalen Fallback-Pfad."""
    try:
        result = subprocess.run(
            ["junie"], input=prompt_text, capture_output=True, text=True, check=True, timeout=timeout, env=env_dict
        )
        return result.stdout
    except FileNotFoundError:
        # Fallback path if 'junie' is not in global PATH
        fallback_path = os.path.expanduser("~/.local/bin/junie")
        result = subprocess.run(
            [fallback_path], input=prompt_text, capture_output=True, text=True, check=True, timeout=timeout, env=env_dict
        )
        return result.stdout

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
        with open("prompt_summarizer.md", "r", encoding="utf-8") as pf:
            global_prompt = pf.read().strip() 
    except FileNotFoundError:
        raise RuntimeError("Error: 'prompt_summarizer.md' not found.")
        
    # Variable, um zu tracken, ob heute überhaupt Updates gefunden wurden
    any_updates_found = False
    run_thread_key = f"releases-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    # 4. Process feeds
    for item in inventory:
        feed_url = item.get("feed_url")
        if not feed_url:
            continue
            
        print(f"Processing feed: {feed_url}")

        # Get project name from inventory
        project_name = item.get("name", "Unknown Project")

        # Inject watermark date and project name into prompt
        last_run = watermarks.get(feed_url, "2000-01-01T00:00:00Z")
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        prompt_with_vars = global_prompt.replace("{{LAST_RUN_DATE}}", last_run).replace("{{PROJECT_NAME}}", project_name)

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
        combined_prompt = f"{prompt_with_vars}\n\nHere is the feed content:\n\n{feed_content}"

        # Call junie with the combined prompt
        try:
            cli_output = call_junie(combined_prompt, process_env, timeout=600)
        except subprocess.CalledProcessError as e:
            print(f"junie error for {feed_url}: {e.stderr}")
            continue
        except Exception as ex:
            print(f"Unexpected error executing junie for {feed_url}. Moving to next project. Error: {ex}")
            continue

        # 5. Clean output and evaluate empty state
        clean_output = clean_ansi(cli_output).strip()

        if "NO_NEW_RELEASES" in clean_output:
            print(f"No new releases for {feed_url} since {last_run}. Skipping webhook.")
            continue

        expected_header = f"📦 *{project_name}*"
        if expected_header not in clean_output:
            print(f"Invalid format (Header '{expected_header}' missing) for {feed_url}. Assuming agent logs. Skipping.")
            continue

        # VORDERER CUT: Wir nehmen alles ab dem LETZTEN Vorkommen des Headers. 
        # Das ignoriert sämtliches "Gedankenlesen" oder Zitate des Agenten davor komplett.
        clean_output = expected_header + clean_output.rsplit(expected_header, 1)[-1]
    
        # AGGRESSIVER HINTERER CUT: Entfernt den Bash-Echo und Agenten-Log-Müll NACH dem Content
        lines = clean_output.split('\n')
        clean_lines = []
        for line in lines:
            stripped_line = line.strip()
            # Erweitert um "!" für Agenten-Kommandos (wie "! Running: git log")
            if stripped_line == "EOF" or stripped_line.startswith("●") or stripped_line.startswith("|") or stripped_line.startswith("!") or "TASK RESULT" in stripped_line:
                break
            clean_lines.append(line)
            
        clean_output = "\n".join(clean_lines).strip()
            
        clean_output = "\n".join(clean_lines).strip()

        # Fallback-Cut, falls es doch noch Reste gibt
        if "\n###" in clean_output:
            clean_output = clean_output.split("\n###")[0].strip()
            
        if not clean_output:
            print(f"Empty output for {feed_url}. Skipping webhook.")
            continue
        
        # 6. Sende Begrüßung (nur beim allerersten Update des Tages)
        if not any_updates_found:
            send_gchat_message(webhook_url, "*Guten Morgen!* Hier sind die Release-Updates für diese Woche:", thread_key=run_thread_key)
            any_updates_found = True
            time.sleep(1)

        # 7. Sende Release-Update an Google Chat
        if send_gchat_message(webhook_url, clean_output, thread_key=run_thread_key):
            print(f"Successfully sent {feed_url} to Google Chat.")
            watermarks[feed_url] = current_time
        
        time.sleep(2)

    # 8. Spruch der Woche (nur generieren und senden, wenn es Updates gab)
    if any_updates_found:
        print("Generating daily quote...")
        cache_buster_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        quote_prompt = f"""Heute ist der {cache_buster_time}. 

Du bist ein zynischer, aber meditativer Senior DevOps Engineer, der die täglichen Schmerzen der IT mit absurder, pseudo-philosophischer Motivation erträgt.

Generiere exakt EINEN neuen, einzigartigen Einzeiler im Stil eines Kalenderspruchs für das Tech-Team.

THEMEN-VIELFALT (SEHR WICHTIG):
Wähle für den heutigen Spruch ein völlig zufälliges, spezifisches Thema aus dem breiten IT-Alltag. 
Nutze NICHT immer nur Git, Pipelines oder Kubernetes! 
Gute alternative Themen: Legacy-Code, DNS-Caching-Probleme, fehlende Dokumentation, Jira-Ticket-Höllen, Zeitzonen-Bugs, Regex-Verzweiflung, Friday-Deployments, endlose Scrum-Meetings, veraltete NPM-Pakete, "Works on my machine"-Ausreden, unlesbare Fehlermeldungen, DB-Queries die Tage laufen oder Projektverantwortliche im Urlaub.

STRUKTUR-VIELFALT:
Das Grundprinzip ist: [IT-Problem] trifft auf [esoterische/buddhistische Erleuchtung].
Aber variiere unbedingt den Satzbau! Nutze NICHT immer das Muster "X ist kein Y, sondern Z". 
Erlaube dir auch rhetorische Fragen, kurze philosophische Thesen, Haikus oder meditative Aufforderungen.

ABSOLUTES TABU (STRIKTE REGEL): 
Mache NIEMALS Witze über Security-Themen, Datenlecks, offene S3-Buckets, Passwörter, Hacks oder Compliance. Das ist streng verboten!

Hier sind drei Beispiele für den Vibe (kopiere diese NICHT, sondern erfinde einen völlig neuen):
- "Wer die fehlende Dokumentation des Legacy-Codes akzeptiert, liest den Quelltext nicht mit den Augen, sondern mit der Seele."
- "Ein Regex, den du am nächsten Tag nicht mehr verstehst, ist keine technische Schuld, sondern ein Mantra der Vergänglichkeit."
- "Warum weinen wir über DNS-Propagierung, wenn doch die Zeit selbst nur eine flüchtige Illusion im globalen Netzwerk ist?"

WICHTIG (STRIKTE REGEL):
Du musst deinen generierten Spruch ZWINGEND zwischen <quote> und </quote> XML-Tags setzen! Schreibe absolut keinen anderen Text außerhalb dieser Tags!"""        
        try:
            # Timeout auf 180 Sekunden
            quote_output = call_junie(quote_prompt, process_env, timeout=180)
            raw_quote = clean_ansi(quote_output).strip()
            
            # Extrahiere EXAKT das, was zwischen <quote> und </quote> steht
            if "<quote>" in raw_quote and "</quote>" in raw_quote:
                raw_quote = raw_quote.split("<quote>")[1].split("</quote>")[0].strip()
            else:
                # Fallback, falls die KI die Tags doch vergisst
                raw_quote = "Der Pipeline-Runner ist ausgefallen, aber zumindest wärmt das Feuer der Fehlermeldungen unsere agilen Herzen."
                
            if raw_quote:
                # Sicherstellen, dass der KI-Satz mit einem Punkt endet, falls er fehlt
                if not raw_quote.endswith((".", "!", "?")):
                    raw_quote += "."
                    
                # Hartes Formatting durch Python
                final_quote_msg = f"Spruch der Woche: {raw_quote} Viel Glück!"
                send_gchat_message(webhook_url, final_quote_msg, thread_key=run_thread_key)
        except Exception as e:
            print(f"Failed to generate quote: {e}")

    # 9. Save updated watermarks to disk
    with open(watermarks_file, "w", encoding="utf-8") as f:
        json.dump(watermarks, f, indent=2)

if __name__ == "__main__":
    main()