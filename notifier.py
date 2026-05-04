import requests
import database
import threading

def _send_sms_sync(phone, message):
    if not phone:
        return False
    phone = str(phone).strip()
    if phone.startswith('0'):
        phone = phone[1:]
    if not phone.startswith('+'):
        phone = '+90' + phone
    url = "https://api.sms-gate.app/3rdparty/v1/message"
    payload = {
        "message": message,
        "phoneNumbers": [phone]
    }
    try:
        response = requests.post(
            url,
            json=payload,
            auth=("VKLS8B", "oerazwrhuki_fr"),
            timeout=10
        )
        if response.status_code not in (200, 201, 202):
            print(f"SMS API Error: {response.status_code} - {response.text}")
        return response.status_code in (200, 201, 202)
    except Exception as e:
        print(f"SMS Error: {e}")
        return False

def send_sms(phone, message):
    # Arka planda çalıştır ki web sitesi donmasın
    thread = threading.Thread(target=_send_sms_sync, args=(phone, message))
    thread.daemon = True
    thread.start()
    return True # API sonucu beklenmeyeceği için varsayılan True döneriz

def notify_all(message):
    users = database.get_all_users()
    for user in users:
        if user.get("phone_number"):
            send_sms(user["phone_number"], message)
