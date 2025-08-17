# wa_web_prep.py — WhatsApp Web (préparation uniquement, bouton "+" -> Document)
import os, time
from typing import List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class WhatsAppPrep:
    def __init__(self, profile_dir: str = "wa_profile", headless: bool = False, timeout: int = 60):
        self.profile_dir = os.path.abspath(profile_dir)
        self.headless = headless
        self.timeout = timeout
        self._driver: Optional[webdriver.Chrome] = None

    def _build_options(self, profile_path: str) -> webdriver.ChromeOptions:
        opts = webdriver.ChromeOptions()
        opts.add_argument(f"--user-data-dir={profile_path}")
        opts.add_argument("--disable-notifications")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("detach", True)
        if self.headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1400,900")
        return opts

    def _get_driver(self) -> webdriver.Chrome:
        if self._driver:
            return self._driver

        service = ChromeService(ChromeDriverManager().install())

        try:
            opts = self._build_options(self.profile_dir)
            self._driver = webdriver.Chrome(service=service, options=opts)
        except SessionNotCreatedException:
            print("\n[INFO] Le profil Chrome est déjà utilisé (fenêtre ouverte).")
            choice = input("Ferme toutes les fenêtres Chrome puis tape 'o' pour réessayer, "
                           "ou tape 't' pour utiliser un profil temporaire (QR requis) : ").strip().lower()
            if choice == "o":
                time.sleep(2)
                opts = self._build_options(self.profile_dir)
                self._driver = webdriver.Chrome(service=service, options=opts)
            else:
                temp_profile = os.path.abspath(self.profile_dir + "_temp")
                os.makedirs(temp_profile, exist_ok=True)
                opts = self._build_options(temp_profile)
                self._driver = webdriver.Chrome(service=service, options=opts)
                print("[INFO] Profil temporaire utilisé. Tu devras scanner le QR cette fois.")

        self._driver.set_window_size(1400, 900)
        try:
            self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            })
        except Exception:
            pass
        return self._driver

    # --------- Ouverture chat ---------
    def open_chat(self, e164_phone: str):
        d = self._get_driver()
        d.get(f"https://web.whatsapp.com/send?phone={e164_phone.replace('+','')}&type=phone_number&app_absent=0")
        WebDriverWait(d, 300).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "footer div[contenteditable='true']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true'][role='textbox']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true'][data-tab='10']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "header [data-testid='conversation-info-header']")),
            )
        )
        time.sleep(0.8)

    # --------- Zone de saisie message ---------
    def _find_input_box(self):
        d = self._get_driver()
        selectors = [
            "footer div[contenteditable='true']",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true'][data-tab='10']",
        ]
        for sel in selectors:
            try:
                return WebDriverWait(d, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            except Exception:
                continue
        raise RuntimeError("Zone de saisie WhatsApp introuvable.")

    def type_message(self, text: str):
        box = self._find_input_box()
        box.click()
        first = True
        for line in text.split("\n"):
            if not first:
                box.send_keys(Keys.SHIFT, Keys.ENTER)  # retour à la ligne sans envoyer
            box.send_keys(line)
            first = False

    # --------- Menu attachement (bouton + / Joindre) ---------
    def _open_attach_menu(self) -> bool:
        d = self._get_driver()

        # Sélecteurs précis vus dans ton HTML
        precise_selectors = [
            "button[title='Joindre'] span[data-icon='plus-rounded']",
            "button[title='Joindre']",
            "span[data-icon='plus-rounded']",
        ]
        for sel in precise_selectors:
            try:
                btn = WebDriverWait(d, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                if btn.tag_name.lower() != "button":
                    try:
                        btn = btn.find_element(By.XPATH, "./ancestor::button")
                    except Exception:
                        pass
                btn.click()
                time.sleep(0.2)
                return True
            except Exception:
                continue

        # Fallbacks
        fallback_selectors = [
            "button[aria-label*='Joindre']",
            "div[aria-label*='Joindre']",
            "div[aria-label*='Ajouter']",
            "button[aria-label*='Attach']",
            "div[aria-label*='Attach']",
            "button span[data-icon='attach-menu']",
            "span[data-icon='clip']",
        ]
        for sel in fallback_selectors:
            try:
                btn = WebDriverWait(d, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                btn.click()
                time.sleep(0.2)
                return True
            except Exception:
                continue

        # Fallback XPath par title
        xpath_alternatives = [
            "//button[@title='Joindre']",
            "//div[@role='button' and @title='Joindre']",
        ]
        for xp in xpath_alternatives:
            try:
                btn = WebDriverWait(d, 6).until(EC.element_to_be_clickable((By.XPATH, xp)))
                btn.click()
                time.sleep(0.2)
                return True
            except Exception:
                continue

        print("Menu d'attachement introuvable (bouton + / Joindre).")
        return False

    # --------- Clic "Document" et upload via input[type=file] interne ---------
    def _click_document_and_upload(self, file_path: str) -> bool:
        d = self._get_driver()
        full = os.path.abspath(file_path)

        try:
            # Trouver le <li role='button'> Document (ou icône document-filled-refreshed) contenant un input file
            li = WebDriverWait(d, 8).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//li[@role='button'][.//span[contains(text(),'Document')] or .//span[@data-icon='document-filled-refreshed']]"
                ))
            )
            file_input = li.find_element(By.CSS_SELECTOR, "input[type='file']")
            file_input.send_keys(full)
            time.sleep(1.5)  # laisser l'aperçu se préparer
            return True
        except Exception as e:
            print("Impossible d'utiliser l'option 'Document' pour ce fichier :", full, "-", e)
            return False

    def _visible_file_inputs(self):
        d = self._get_driver()
        return [i for i in d.find_elements(By.CSS_SELECTOR, "input[type='file']") if i.is_displayed()]

    # --------- Attacher une ou plusieurs PDF ---------
    def attach_pdfs(self, pdf_paths: List[str]):
        d = self._get_driver()
        for path in pdf_paths:
            full = os.path.abspath(path)
            if not os.path.exists(full):
                print("Fichier introuvable, on saute :", full)
                continue

            if not self._open_attach_menu():
                print("Menu d'attachement introuvable. On saute l'attache pour ce fichier :", full)
                continue

            if not self._click_document_and_upload(full):
                # fallback ultime : si un input[type=file] global est visible, on essaye
                try:
                    vis = self._visible_file_inputs()
                    if vis:
                        vis[-1].send_keys(full)
                        time.sleep(1.5)
                except Exception:
                    print("Echec d'attache pour", full)

            # Attente non bloquante d'un aperçu/document chargé
            try:
                WebDriverWait(d, 10).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='dialog']")),
                        EC.presence_of_element_located((By.CSS_SELECTOR, "span[data-icon='document']")),
                        EC.presence_of_element_located((By.XPATH, "//div[contains(@aria-label,'Document')]")),
                    )
                )
            except Exception:
                pass

    # --------- Pipeline complet (sans envoi auto) ---------
    def prepare_only(self, e164_phone: str, message: str, pdf_paths: List[str]):
        self.open_chat(e164_phone)
        self.type_message(message)
        if pdf_paths:
            self.attach_pdfs(pdf_paths)
        print("WhatsApp prêt : texte saisi" + (f" + {len(pdf_paths)} PDF" if pdf_paths else " (aucune PJ)"))
        print("Vérifie puis clique sur Envoyer manuellement.")
