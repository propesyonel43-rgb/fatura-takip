import os
import requests
import database
import threading


def _get_green_credentials():
    """Green API bilgileri: önce ortam değişkeni, yoksa config tablosu."""
    gid = os.environ.get("GREEN_API_ID") or database.get_config("green_api_id")
    token = os.environ.get("GREEN_API_TOKEN") or database.get_config("green_api_token")
    return gid, token


def _normalize_phone(phone):
    phone = str(phone).strip().replace(" ", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = "90" + phone[1:]
    elif not phone.startswith("90"):
        phone = "90" + phone
    return phone


def _send_whatsapp_sync(phone, message, apikey=None):
    """Green API üzerinden WhatsApp mesajı gönderir.
    apikey parametresi eski CallMeBot uyumluluğu için duruyor, kullanılmıyor."""
    gid, token = _get_green_credentials()
    if not phone or not gid or not token:
        print("[WhatsApp] Eksik bilgi: telefon veya Green API ayarları yok.")
        return False

    api_base = os.environ.get("GREEN_API_URL") or database.get_config("green_api_url") or "https://7107.api.greenapi.com"
    url = f"{api_base}/waInstance{gid}/sendMessage/{token}"
    payload = {
        "chatId": f"{_normalize_phone(phone)}@c.us",
        "message": message,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            print(f"WhatsApp API Error: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"WhatsApp Error: {e}")
        return False


def send_whatsapp(phone, message, apikey=None):
    thread = threading.Thread(target=_send_whatsapp_sync, args=(phone, message, apikey))
    thread.daemon = True
    thread.start()
    return True


def notify_all(message):
    users = database.get_all_users()
    for user in users:
        if user.get("phone_number"):
            send_whatsapp(user["phone_number"], message)
