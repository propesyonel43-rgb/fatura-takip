import requests
import database
import threading
import urllib.parse

def _send_whatsapp_sync(phone, message, apikey):
    if not phone or not apikey:
        return False
    
    phone = str(phone).strip()
    if phone.startswith('0'):
        phone = '90' + phone[1:]
    elif phone.startswith('+'):
        phone = phone[1:]
    elif not phone.startswith('90'):
        phone = '90' + phone

    encoded_msg = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_msg}&apikey={apikey}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"WhatsApp API Error: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"WhatsApp Error: {e}")
        return False

def send_whatsapp(phone, message, apikey):
    thread = threading.Thread(target=_send_whatsapp_sync, args=(phone, message, apikey))
    thread.daemon = True
    thread.start()
    return True

def notify_all(message):
    users = database.get_all_users()
    for user in users:
        if user.get("phone_number") and user.get("whatsapp_apikey"):
            send_whatsapp(user["phone_number"], message, user["whatsapp_apikey"])
