#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials as ServiceCreds
from google.oauth2.credentials import Credentials as UserCreds
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

APP_TITLE = "HAVEN – Assistant (GUI)"
PERSIST_FILE = "factures_attachees.json"
DEFAULT_APP = "haven_app_v1_oauth.py"
DEFAULT_CREDS = "credentials.json"
DEFAULT_SHEET_ID = "1UGhydAjQvg6NfA1E-LL8HLebqP5XMrUzE4Hf3w8KUP0"
DEFAULT_TAB = "Clients"
DEFAULT_CMD_TEMPLATE = 'python "{app}" --csv "{csv}" --creds "{creds}" --sheet-id "{sheet_id}" --tab "{tab}"'

# Dossiers factures (modifiables dans l'UI)
DEFAULT_INVOICE_DIR = r"C:\Users\HAVEN\Desktop\Haven_assistant\facture"
DEFAULT_SENT_DIR    = r"C:\Users\HAVEN\Desktop\Haven_assistant\facture_envoye"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# -------- Multilingual messages (synchronisés avec haven_app) --------
MESSAGES = {
    "fr": "Bonjour M./Mme {nom},\n\nJ’espère que vous allez bien.\nVous trouverez ci-joint votre facture.\n\nN’hésitez pas à revenir vers moi pour toute question ou précision.\n\nBien cordialement,\nThéo",
    "en": "Hello Mr./Mrs. {nom},\n\nI hope you are doing well.\nPlease find attached your invoice.\n\nFeel free to reach out if you have any questions.\n\nBest regards,\nThéo",
    "de": "Guten Tag Herr/Frau {nom},\n\nIch hoffe, es geht Ihnen gut.\nAnbei finden Sie Ihre Rechnung.\n\nZögern Sie nicht, mich bei Fragen zu kontaktieren.\n\nMit freundlichen Grüßen,\nThéo",
    "es": "Hola Sr./Sra. {nom},\n\nEspero que se encuentre bien.\nAdjunto encontrará su factura.\n\nNo dude en contactarme si tiene alguna pregunta.\n\nAtentamente,\nThéo",
    "it": "Buongiorno Sig./Sig.ra {nom},\n\nSpero che stia bene.\nTroverà in allegato la sua fattura.\n\nNon esiti a contattarmi per qualsiasi domanda.\n\nCordiali saluti,\nThéo",
    "ru": "Здравствуйте, г-н/г-жа {nom},\n\nНадеюсь, у Вас всё хорошо.\nВо вложении Вы найдёте свой счёт.\n\nЕсли у Вас возникнут вопросы, пожалуйста, свяжитесь со мной.\n\nС уважением,\nThéo",
    "tr": "Merhaba Bay/Bayan {nom},\n\nUmarım iyisinizdir.\nFaturanızı ekte bulabilirsiniz.\n\nHerhangi bir sorunuz olursa bana ulaşmaktan çekinmeyin.\n\nSaygılarımla,\nThéo",
    "nl": "Beste meneer/mevrouw {nom},\n\nIk hoop dat het goed met u gaat.\nIn de bijlage vindt u uw factuur.\n\nNeem gerust contact met mij op als u vragen heeft.\n\nMet vriendelijke groet,\nThéo",
    "pl": "Dzień dobry Panie/Pani {nom},\n\nMam nadzieję, że u Pana/Pani wszystko w porządku.\nW załączniku znajduje się faktura.\n\nW razie pytań proszę się ze mną skontaktować.\n\nZ poważaniem,\nThéo",
    "el": "Καλημέρα κ. {nom},\n\nΕλπίζω να είστε καλά.\nΣυνημμένα θα βρείτε το τιμολόγιό σας.\n\nΜη διστάσετε να επικοινωνήσετε μαζί μου για οποιαδήποτε απορία.\n\nΜε εκτίμηση,\nThéo",
    "he": "שלום מר/גברת {nom},\n\nאני מקווה שהכול בסדר אצלך.\nמצורפת החשבונית שלך.\n\nאל תהסס לפנות אלי בכל שאלה.\n\nבברכה,\nThéo",
    "pt": "Olá Sr./Sra. {nom},\n\nEspero que esteja bem.\nSegue em anexo a sua fatura.\n\nFique à vontade para entrar em contato caso tenha alguma dúvida.\n\nAtenciosamente,\nThéo",
}

def build_multilang_message(lang: str, nom: str) -> str:
    lang = (lang or "en").lower().strip() or "en"
    template = MESSAGES.get(lang, MESSAGES["en"])
    return template.format(nom=nom or "")

# -------- Google auth --------
def google_auth(creds_path: str):
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"Fichier d'identifiants introuvable: {creds_path}")
    with open(creds_path, "r", encoding="utf-8") as f:
        head = f.read(128)
    is_service = '"type": "service_account"' in head
    if is_service:
        creds = ServiceCreds.from_service_account_file(creds_path, scopes=SCOPES)
        gc = gspread.authorize(creds)
        return gc
    creds = None
    token_path = "token_gui.json"
    if os.path.exists(token_path):
        try:
            creds = UserCreds.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as t:
            t.write(creds.to_json())
    gc = gspread.authorize(creds)
    return gc

# -------- Persistence for attached invoices --------
def load_persist_map(path=PERSIST_FILE):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_persist_map(data, path=PERSIST_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("WARN: cannot save persistence:", e)

def open_with_default_app(path: str):
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Ouverture", f"Impossible d'ouvrir le fichier:\n{e}")

# -------- GUI --------
class HavenGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x720")
        self.configure(padx=8, pady=8)

        # Top config frame
        cfg = ttk.LabelFrame(self, text="Configuration")
        cfg.pack(fill="x")

        self.app_path = tk.StringVar(value=DEFAULT_APP)
        self.creds_path = tk.StringVar(value=DEFAULT_CREDS)
        self.sheet_id = tk.StringVar(value=DEFAULT_SHEET_ID)
        self.tab_name = tk.StringVar(value=DEFAULT_TAB)
        self.cmd_template = tk.StringVar(value=DEFAULT_CMD_TEMPLATE)
        self.invoice_dir = tk.StringVar(value=DEFAULT_INVOICE_DIR)
        self.sent_dir = tk.StringVar(value=DEFAULT_SENT_DIR)

        row = 0
        ttk.Label(cfg, text="Script HAVEN:").grid(row=row, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.app_path, width=70).grid(row=row, column=1, sticky="we")
        ttk.Button(cfg, text="Parcourir", command=self.pick_app).grid(row=row, column=2, padx=4)
        row += 1
        ttk.Label(cfg, text="Credentials.json:").grid(row=row, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.creds_path, width=70).grid(row=row, column=1, sticky="we")
        ttk.Button(cfg, text="Parcourir", command=self.pick_creds).grid(row=row, column=2, padx=4)
        row += 1
        ttk.Label(cfg, text="Sheet ID:").grid(row=row, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.sheet_id, width=70).grid(row=row, column=1, sticky="we")
        ttk.Button(cfg, text="Charger depuis Google Sheets", command=self.load_clients).grid(row=row, column=2, padx=4)
        row += 1
        ttk.Label(cfg, text="Onglet:").grid(row=row, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.tab_name, width=30).grid(row=row, column=1, sticky="w")
        row += 1
        ttk.Label(cfg, text="Commande sous-processus:").grid(row=row, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.cmd_template, width=70).grid(row=row, column=1, sticky="we")
        ttk.Button(cfg, text="Par défaut", command=lambda: self.cmd_template.set(DEFAULT_CMD_TEMPLATE)).grid(row=row, column=2, padx=4)
        row += 1
        ttk.Label(cfg, text="Dossier factures:").grid(row=row, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.invoice_dir, width=70).grid(row=row, column=1, sticky="we")
        ttk.Button(cfg, text="Choisir", command=self.pick_invoice_dir).grid(row=row, column=2, padx=4)
        row += 1
        ttk.Label(cfg, text="Dossier factures envoyées:").grid(row=row, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.sent_dir, width=70).grid(row=row, column=1, sticky="we")
        ttk.Button(cfg, text="Choisir", command=self.pick_sent_dir).grid(row=row, column=2, padx=4)

        for i in range(3):
            cfg.columnconfigure(i, weight=1)

        # Split: left = clients, middle = preview, right = invoices
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, pady=(8, 0))

        # Left
        left = ttk.LabelFrame(main, text="Clients (sélection multiple)")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        cols = ("client_id", "client_nom", "tel", "lang")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="extended")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=150 if c != "client_nom" else 260, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="Tout sélectionner", command=self.select_all).pack(side="left")
        ttk.Button(btns, text="Tout désélectionner", command=self.unselect_all).pack(side="left", padx=6)
        ttk.Button(btns, text="Attacher facture (PDF)", command=self.attach_invoice).pack(side="left", padx=6)

        # Middle (preview)
        mid = ttk.LabelFrame(main, text="Prévisualisation du message")
        mid.pack(side="left", fill="both", expand=True)
        self.preview = tk.Text(mid, height=18, wrap="word")
        self.preview.pack(fill="both", expand=True, padx=4, pady=4)

        # Right (invoices viewer)
        right = ttk.LabelFrame(main, text="Factures")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        inv_top = ttk.Frame(right); inv_top.pack(fill="x")
        ttk.Button(inv_top, text="Rafraîchir", command=self.refresh_invoices).pack(side="left")
        ttk.Button(inv_top, text="Ouvrir", command=self.open_selected_invoice).pack(side="left", padx=6)
        ttk.Button(inv_top, text="Attacher au(x) client(s) sélectionné(s)", command=self.attach_from_browser).pack(side="left", padx=6)

        # Two lists
        lists = ttk.Panedwindow(right, orient="vertical")
        lists.pack(fill="both", expand=True, pady=(4,0))

        self.list_invoices = tk.Listbox(lists, height=10, selectmode="browse")
        self.list_sent = tk.Listbox(lists, height=10, selectmode="browse")
        lists.add(self._labeled(self.list_invoices, "Dossier factures"))
        lists.add(self._labeled(self.list_sent, "Dossier factures envoyées"))

        # Bottom actions + logs
        bottom = ttk.Frame(self)
        bottom.pack(fill="both", expand=False, pady=(8, 0))
        ttk.Button(bottom, text="Préparer WhatsApp (clients sélectionnés)", command=self.prepare_whatsapp).pack(side="left")
        ttk.Button(bottom, text="Quitter", command=self.destroy).pack(side="right")

        logbox = ttk.LabelFrame(self, text="Logs")
        logbox.pack(fill="both", expand=True, pady=(8, 0))
        self.log = tk.Text(logbox, height=10, wrap="word")
        self.log.pack(fill="both", expand=True)

        # Data
        self.df = pd.DataFrame(columns=["client_id","client_nom","tel","email","canal_pref","lang"])
        self.attached = self._safe_load_persist()
        self.refresh_invoices()

    def _labeled(self, widget, title):
        frame = ttk.Frame()
        ttk.Label(frame, text=title).pack(anchor="w")
        widget.pack(in_=frame, fill="both", expand=True)
        return frame

    def _safe_load_persist(self):
        m = load_persist_map()
        # Clean invalid paths
        dirty = []
        for k, v in m.items():
            if v and not os.path.exists(v):
                dirty.append(k)
        for k in dirty:
            m.pop(k, None)
        if dirty:
            save_persist_map(m)
        return m

    # ---- Config pickers ----
    def pick_app(self):
        f = filedialog.askopenfilename(filetypes=[("Python", "*.py"), ("All", "*.*")])
        if f:
            self.app_path.set(f)

    def pick_creds(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if f:
            self.creds_path.set(f)

    def pick_invoice_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.invoice_dir.set(d)
            self.refresh_invoices()

    def pick_sent_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.sent_dir.set(d)
            self.refresh_invoices()

    # ---- Load clients ----
    def load_clients(self):
        try:
            gc = google_auth(self.creds_path.get())
            sh = gc.open_by_key(self.sheet_id.get().strip())
            ws = sh.worksheet(self.tab_name.get().strip())
            rows = ws.get_all_values()
            if not rows:
                messagebox.showwarning("Google Sheets", "Onglet vide.")
                return
            header = rows[0]
            data = rows[1:]
            df = pd.DataFrame(data, columns=header)
            for c in ["client_id","client_nom","tel","email","canal_pref","lang"]:
                if c not in df.columns:
                    df[c] = ""
            self.df = df[["client_id","client_nom","tel","email","canal_pref","lang"]]
            # populate
            for i in self.tree.get_children():
                self.tree.delete(i)
            for _, r in self.df.iterrows():
                self.tree.insert("", "end", values=(r["client_id"], r["client_nom"], r["tel"], r["lang"]))
            self.log_write(f"Chargé {len(self.df)} clients depuis Google Sheets.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger les clients: {e}")

    # ---- Clients selection / preview ----
    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            self.preview.delete("1.0", tk.END)
            return
        item = self.tree.item(sel[0])
        cid, nom, tel, lang = item["values"]
        msg = build_multilang_message(lang, nom)
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, msg)

    def select_all(self):
        for iid in self.tree.get_children():
            self.tree.selection_add(iid)

    def unselect_all(self):
        self.tree.selection_remove(self.tree.selection())

    def attach_invoice(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Sélection", "Sélectionnez au moins un client.")
            return
        f = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not f:
            return
        for iid in sel:
            cid = self.tree.item(iid)["values"][0]
            self.attached[cid] = f
        save_persist_map(self.attached)
        self.log_write(f"Facture attachée à {len(sel)} client(s): {f}")

    # ---- Invoices browser ----
    def refresh_invoices(self):
        self.list_invoices.delete(0, tk.END)
        self.list_sent.delete(0, tk.END)
        inv = self.invoice_dir.get().strip()
        sent = self.sent_dir.get().strip()
        def list_pdfs(folder):
            if not folder or not os.path.isdir(folder):
                return []
            try:
                return sorted([str(Path(folder)/f) for f in os.listdir(folder) if f.lower().endswith(".pdf")])
            except Exception:
                return []
        for p in list_pdfs(inv):
            self.list_invoices.insert(tk.END, p)
        for p in list_pdfs(sent):
            self.list_sent.insert(tk.END, p)

    def open_selected_invoice(self):
        listbox = None
        if self.list_invoices.curselection():
            listbox = self.list_invoices
        elif self.list_sent.curselection():
            listbox = self.list_sent
        if not listbox:
            messagebox.showinfo("Ouvrir", "Sélectionnez une facture dans l'un des listes.")
            return
        path = listbox.get(listbox.curselection()[0])
        open_with_default_app(path)

    def attach_from_browser(self):
        sel_clients = self.tree.selection()
        if not sel_clients:
            messagebox.showwarning("Sélection", "Sélectionnez des clients à gauche.")
            return
        listbox = None
        if self.list_invoices.curselection():
            listbox = self.list_invoices
        elif self.list_sent.curselection():
            listbox = self.list_sent
        if not listbox:
            messagebox.showwarning("Sélection", "Sélectionnez une facture à droite.")
            return
        path = listbox.get(listbox.curselection()[0])
        for iid in sel_clients:
            cid = self.tree.item(iid)["values"][0]
            self.attached[cid] = path
        save_persist_map(self.attached)
        self.log_write(f"Facture '{os.path.basename(path)}' attachée à {len(sel_clients)} client(s).")

    # ---- Prepare WhatsApp via subprocess ----
    def prepare_whatsapp(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Sélection", "Sélectionnez au moins un client.")
            return
        selected_ids = [self.tree.item(i)["values"][0] for i in sel]
        sub = self.df[self.df["client_id"].isin(selected_ids)].copy()
        sub["invoice_path"] = sub["client_id"].map(self.attached).fillna("")
        out_csv = Path.cwd() / "clients_selectionnes.csv"
        try:
            sub.to_csv(out_csv, index=False, encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'écrire le CSV: {e}")
            return
        self.log_write(f"CSV créé: {out_csv} ({len(sub)} lignes)")

        app = self.app_path.get().strip() or DEFAULT_APP
        creds = self.creds_path.get().strip() or DEFAULT_CREDS
        sheet_id = self.sheet_id.get().strip()
        tab = self.tab_name.get().strip()
        tmpl = self.cmd_template.get().strip() or DEFAULT_CMD_TEMPLATE
        cmd = tmpl.format(app=app, csv=str(out_csv), creds=creds, sheet_id=sheet_id, tab=tab)

        threading.Thread(target=self.run_subprocess, args=(cmd,), daemon=True).start()

    def run_subprocess(self, cmd: str):
        self.log_write(f"Lancement: {cmd}")
        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                self.log_write(line.rstrip("\n"))
            proc.wait()
            rc = proc.returncode
            if rc == 0:
                self.log_write("✅ Terminé sans erreur.")
                messagebox.showinfo("Terminé", "Préparation WhatsApp terminée (clique manuellement sur Envoyer).")
            else:
                self.log_write(f"⚠️ Terminé avec code {rc}.")
                messagebox.showwarning("Avertissement", f"Processus terminé avec code {rc}. Consulte les logs.")
        except Exception as e:
            self.log_write(f"❌ Erreur: {e}")
            messagebox.showerror("Erreur", f"Impossible de lancer le processus:\n{e}")

    def log_write(self, text: str):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)


if __name__ == "__main__":
    try:
        app = HavenGUI()
        app.mainloop()
    except Exception as e:
        try:
            from tkinter import messagebox
            messagebox.showerror("Erreur critique", str(e))
        except Exception:
            print("Erreur critique:", e)
