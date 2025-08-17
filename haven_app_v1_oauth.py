import os
import re
import json
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -------------------------
# Utils
# -------------------------

def normalize_phone(phone: str, country_prefix: str = None) -> str:
    """Normalize phone number into E.164 format."""
    if not country_prefix:
        country_prefix = os.getenv("DEFAULT_COUNTRY_PREFIX", "+33")
    if not country_prefix.startswith("+"):
        country_prefix = "+" + country_prefix

    phone = re.sub(r'\D', '', phone)
    if phone.startswith("0"):
        phone = phone[1:]
    return country_prefix + phone


def build_message(client_name: str, lang: str) -> str:
    """Build message text depending on client language."""
    messages = {
        "fr": f"""Bonjour {client_name},
J’espère que vous allez bien.
Vous trouverez ci-joint votre facture.

N’hésitez pas à revenir vers moi pour toute question ou précision.

Bien cordialement,
Théo""",

        "en": f"""Hello {client_name},
I hope you are doing well.
Please find attached your invoice.

Feel free to reach out if you have any questions.

Best regards,
Théo""",

        "es": f"""Hola {client_name},
Espero que se encuentre bien.
Adjunto encontrará su factura.

No dude en contactarme si tiene alguna pregunta.

Saludos cordiales,
Théo""",

        "de": f"""Hallo {client_name},
Ich hoffe, es geht Ihnen gut.
Anbei finden Sie Ihre Rechnung.

Zögern Sie nicht, mich bei Fragen zu kontaktieren.

Mit freundlichen Grüßen,
Théo""",

        "it": f"""Ciao {client_name},
Spero che stia bene.
Troverà in allegato la sua fattura.

Non esiti a contattarmi per qualsiasi domanda.

Cordiali saluti,
Théo""",

        "ru": f"""Здравствуйте {client_name},
Надеюсь, у вас всё хорошо.
Во вложении вы найдете ваш счёт.

Пожалуйста, обращайтесь ко мне, если у вас есть вопросы.

С уважением,
Théo""",

        "nl": f"""Hallo {client_name},
Ik hoop dat alles goed met u gaat.
In de bijlage vindt u uw factuur.

Neem gerust contact met mij op als u vragen heeft.

Met vriendelijke groet,
Théo""",

        "pt": f"""Olá {client_name},
Espero que esteja bem.
Segue em anexo a sua fatura.

Sinta-se à vontade para entrar em contato caso tenha dúvidas.

Atenciosamente,
Théo""",

        "tr": f"""Merhaba {client_name},
Umarım iyisinizdir.
Faturanızı ekte bulabilirsiniz.

Herhangi bir sorunuz olursa bana ulaşmaktan çekinmeyin.

Saygılarımla,
Théo""",

        "el": f"""Γεια σας {client_name},
Ελπίζω να είστε καλά.
Σας επισυνάπτω το τιμολόγιό σας.

Μη διστάσετε να επικοινωνήσετε μαζί μου για οποιαδήποτε ερώτηση.

Με εκτίμηση,
Théo""",

        "he": f"""שלום {client_name},
אני מקווה שאתה מרגיש טוב.
מצורפת החשבונית שלך.

אל תהסס לפנות אלי בכל שאלה.

בברכה,
Théo"""
    }

    return messages.get(lang, messages["en"])


# -------------------------
# Google Sheets
# -------------------------

def get_clients(sheet_id: str, tab: str, creds_file: str):
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id).worksheet(tab)
    data = sheet.get_all_records()
    return sheet, data


def mark_sent(ws, row_indices):
    """Mark rows as sent using batch_update to reduce API calls."""
    requests = []
    for row in row_indices:
        requests.append({
            "range": f"F{row}",
            "values": [["SENT"]]
        })
    if requests:
        ws.batch_update([{"range": r["range"], "values": r["values"]} for r in requests])


# -------------------------
# Main Process (simplified placeholder)
# -------------------------

def process_invoices(sheet_id: str, tab: str, creds_file: str):
    ws, clients = get_clients(sheet_id, tab, creds_file)
    rows_to_update = []

    for idx, client in enumerate(clients, start=2):  # start=2 to skip header
        client_name = client.get("client_nom", "Client")
        lang = client.get("lang", "en")
        message = build_message(client_name, lang)
        print("Prepared message:")  # debug
        print(message)
        # Simuler un envoi réussi
        rows_to_update.append(idx)

    # Batch update une fois tous les clients traités
    mark_sent(ws, rows_to_update)


if __name__ == "__main__":
    SHEET_ID = os.getenv("SHEET_ID", "")
    TAB = os.getenv("TAB", "Clients")
    CREDS = os.getenv("CREDS", "credentials.json")
    process_invoices(SHEET_ID, TAB, CREDS)
