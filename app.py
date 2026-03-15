import requests
import random
import os
import time
from colorama import Fore, Style, init
import cloudscraper

init(autoreset=True)

CREDENTIALS_FILE = "credentials"
API_KEY = "bekorcfmGwGMw9Nh"

USER_AGENT = "xkom_prod/1.133.2"
scraper = cloudscraper.create_scraper(browser={'custom': USER_AGENT})


def load_credentials():
    try:
        credentials = {}
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    credentials[key.strip()] = value.strip()

        if 'email' not in credentials or 'haslo' not in credentials:
            raise ValueError("The credentials file must contain 'email' and 'haslo'.")

        return (
            credentials.get('email'),
            credentials.get('haslo'),
            credentials.get('webhook_url'),
            credentials.get('user_id_to_ping')
        )

    except FileNotFoundError:
        print(f"{Fore.RED}[!] Error: File '{CREDENTIALS_FILE}' not found.")
        print(f"{Fore.YELLOW}    Create it in the same folder as the script and fill in your credentials.")
        return None, None, None, None
    except Exception as e:
        print(f"{Fore.RED}[!] Error while loading credentials from file: {e}")
        return None, None, None, None


def send_to_discord(webhook_url, item_details, user_id_to_ping):
    if not webhook_url:
        return

    print(f"{Fore.BLUE}[*] Sending notification to Discord...")

    is_legendary = item_details.get('rarity', '').lower() == 'legendarna'
    ping_message = ""

    if is_legendary:
        ping_message = "@everyone"
        if user_id_to_ping:
            ping_message += f" <@{user_id_to_ping}>"

    embed = {
        "title": "🎁 New item drawn from x-kom Box!",
        "color": 0xFFD700 if is_legendary else 0x2ECC71,
        "fields": [
            {"name": "Item", "value": f"**{item_details.get('name', 'N/A')}**", "inline": False},
            {"name": "Catalog Price", "value": f"{item_details.get('catalog_price', 'N/A')} PLN", "inline": True},
            {"name": "Box Price", "value": f"{item_details.get('box_price', 'N/A')} PLN", "inline": True},
            {"name": "Rarity",
             "value": f"**✨ {item_details.get('rarity', 'N/A')} ✨**" if is_legendary else item_details.get('rarity',
                                                                                                           'N/A'),
             "inline": True},
        ],
        "thumbnail": {"url": item_details.get('image_url', '')},
        "footer": {"text": "X-kom Box Opener"}
    }

    payload = {"embeds": [embed]}
    if ping_message:
        payload["content"] = ping_message

    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        print(f"{Fore.GREEN}[+] Notification sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}[-] Failed to send notification to Discord: {e}")


def get_access_token(login, password):
    print(f"{Fore.YELLOW}[*] Attempting to log in to account: {login}...")
    token_url = "https://auth.x-kom.pl/xkom/Token"
    token_headers = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT}
    token_data = {
        "grant_type": "password", "username": login, "password": password,
        "client_id": "android", "scope": "api_v1 offline_access"
    }
    try:
        response = scraper.post(token_url, headers=token_headers, data=token_data)
        response.raise_for_status()
        token_json = response.json()
        if "access_token" in token_json:
            print(f"{Fore.GREEN}[+] Successfully logged in!")
            return token_json["access_token"]
        else:
            print(f"{Fore.RED}[-] Login error: {token_json.get('error_description', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"{Fore.RED}[-] A network error occurred during login: {e}")
        return None


def grant_required_consents(access_token):
    print(f"{Fore.YELLOW}[*] Attempting to accept the consent for personalized offers...")
    consent_url = "https://mobileapi.x-kom.pl/api/v1/xkom/Account/Consents"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8",
               "User-Agent": USER_AGENT, "x-api-key": API_KEY}
    data = {"ConsentOrigin": "nw_xkom_unbox", "ConsentValues": [{"Code": "offer_adaptin", "IsSelected": True}]}
    try:
        response = scraper.put(consent_url, headers=headers, json=data)
        response.raise_for_status()
        print(f"{Fore.GREEN}[+] Consent successfully accepted.")
        return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            print(
                f"{Fore.YELLOW}[!] Received 400 Bad Request. The consent might already be granted or API payload changed. Proceeding...")
            return True
        print(f"{Fore.RED}[-] HTTP Error while accepting consent: {e}")
        return False
    except Exception as e:
        print(f"{Fore.RED}[-] Error while accepting consent: {e}")
        return False


def open_box(box_id, access_token, webhook_url, user_id_to_ping):
    print(f"\n{Fore.CYAN}[>>] Opening box number {box_id}...")
    roll_url = f"https://mobileapi.x-kom.pl/api/v1/xkom/Box/{box_id}/Items"
    headers = {"Authorization": f"Bearer {access_token}", "X-API-Key": API_KEY, "User-Agent": USER_AGENT}

    try:
        roll_response = scraper.put(roll_url, headers=headers)
        roll_response.raise_for_status()
        roll_data = roll_response.json()
        items = roll_data.get("Items", [])

        if not items:
            print(f"{Fore.YELLOW}[!] Box {box_id} is empty or has already been opened.")
            return

        selected_item = random.choice(items)
        stop_url = f"https://mobileapi.x-kom.pl/api/v1/xkom/Box/{box_id}/Stop?boxRotatorItemIndex={selected_item['BoxRotatorItemResourceId']}&rotatorSpeed={random.uniform(0.6, 1.1):.6f}"
        stop_headers = {**headers, "box-rotator-resource-id": roll_data.get("BoxRotatorResourceId"),
                        "Content-Type": "application/x-www-form-urlencoded"}

        stop_response = scraper.post(stop_url, headers=stop_headers)
        stop_response.raise_for_status()
        stop_data = stop_response.json()

        item = stop_data.get("Item", {})
        item_details = {
            "name": item.get("Name", "Unknown item"),
            "catalog_price": item.get("CatalogPrice", "N/A"),
            "box_price": stop_data.get("BoxPrice", "N/A"),
            "rarity": stop_data.get("BoxRarity", {}).get("Name", "N/A"),
            "image_url": item.get("Photo", {}).get("Url", "")
        }

        print(f"{Fore.GREEN}[+] Drawn item: {item_details['name']}")
        print(f"  - Rarity: {item_details['rarity']}")
        print(f"  - Catalog Price: {item_details['catalog_price']} PLN")
        print(f"  - Box Price: {item_details['box_price']} PLN")

        send_to_discord(webhook_url, item_details, user_id_to_ping)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409:
            print(f"{Fore.YELLOW}[!] Box {box_id} has been opened before.")
        else:
            print(f"{Fore.RED}[-] HTTP error while opening box {box_id}: {e.response.status_code}")
    except Exception as e:
        print(f"{Fore.RED}[-] An unexpected error occurred with box {box_id}: {e}")


def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(Style.BRIGHT + Fore.MAGENTA + "--- X-KOM BOX OPENER ---")

    xkom_login, xkom_password, webhook_url, user_id_to_ping = load_credentials()
    if not (xkom_login and xkom_password):
        return

    access_token = get_access_token(xkom_login, xkom_password)
    if access_token:
        grant_required_consents(access_token)

        for box_id in [1, 2, 3]:
            open_box(box_id, access_token, webhook_url, user_id_to_ping)
            time.sleep(2)

    print(f"\n{Fore.MAGENTA}--- Script finished ---")


if __name__ == "__main__":
    main()