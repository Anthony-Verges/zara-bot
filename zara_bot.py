#!/usr/bin/env python3
import os, time, random, logging, requests
from playwright.sync_api import sync_playwright

# ── CONFIG ──────────────────────────────────────────────────────────────────
# URL          = "https://www.zara.com/fr/fr/combinaison-bustier-a-pois-p03584250.html?v1=528590483"
URL = "https://www.zara.com/fr/fr/robe-midi-rayures-et-n-uds-p02298088.html?v1=521598970&utm_campaign=productShare&utm_medium=mobile_sharing_iOS&utm_source=red_social_movil"
NTFY_TOPIC   = "zara-estelle-combinaison-2024"
TARGET_SIZES = ["XS"]   # tailles à surveiller
INTERVAL     = 300                       # secondes entre chaque vérif
# ────────────────────────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s | %(message)s", datefmt="%d/%m %H:%M:%S", level=logging.INFO)
log = logging.getLogger(__name__)


def notify(title, body):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode(),
            headers={"Title": title, "Priority": "urgent", "Tags": "shopping_bags", "Click": URL},
            timeout=10,
        )
        log.info(f"Notif envoyée : {title}")
    except Exception as e:
        log.error(f"Notif échouée : {e}")


def check(pw):
    browser = pw.chromium.launch(
        headless=False,  # Playwright n'ajoute pas --headless, on utilise le nouveau mode ci-dessous
        args=[
            "--headless=new",  # Nouveau mode headless Chrome 112+, indétectable
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--window-size=1280,800",
        ],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="fr-FR",
        timezone_id="Europe/Paris",
        viewport={"width": 1280, "height": 800},
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR', 'fr', 'en']});
        window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
    """)
    page = ctx.new_page()

    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(random.randint(3000, 5000))

        # Fermer cookies si présents
        for sel in ["#onetrust-accept-btn-handler", "button[id*='accept-all']"]:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(1000)
                break

        # Supprimer la modale de géolocalisation via JS (serveurs GitHub hors France)
        removed = page.evaluate("""() => {
            const modal = document.querySelector('.geolocation-modal');
            const backdrop = document.querySelector('.zds-backdrop');
            if (modal) modal.remove();
            if (backdrop) backdrop.remove();
            return !!modal;
        }""")
        if removed:
            log.info("Modale géoloc supprimée via JS.")
            page.wait_for_timeout(500)

        # Cliquer sur "Ajouter" pour faire apparaître le sélecteur de tailles
        try:
            page.wait_for_selector("button[data-qa-action='add-to-cart']", timeout=15_000)
            page.click("button[data-qa-action='add-to-cart']")
            page.wait_for_timeout(random.randint(2000, 3000))
        except Exception as e:
            log.warning(f"Bouton Ajouter introuvable : {e}")
            return []

        # Lire les tailles disponibles
        # Indispo = classe contient "size-selector-sizes__size--disabled" ou "size-selector-sizes-size--unavailable"
        available = []
        for li in page.query_selector_all("li[class*='size-selector-sizes__size']"):
            cls = li.get_attribute("class") or ""
            if "size-selector-sizes__size--disabled" in cls or "size-selector-sizes-size--unavailable" in cls:
                continue
            text = li.inner_text().strip().split("\n")[0].split("|")[0].strip()
            if text:
                available.append(text)

        return available

    finally:
        browser.close()


def main():
    # En local : boucle toutes les 5 min
    # Sur GitHub Actions (RUN_ONCE=1) : vérifie une fois et quitte
    run_once = os.environ.get("RUN_ONCE") == "1"

    if not run_once:
        log.info(f"Bot démarré — surveillance : {TARGET_SIZES} — toutes les {INTERVAL // 60} min")
        notify("Bot Zara démarré", f"Surveillance de {', '.join(TARGET_SIZES)} toutes les {INTERVAL // 60} min.")

    with sync_playwright() as pw:
        while True:
            try:
                all_available = check(pw)
                matches = [s for s in all_available if s.upper() in [t.upper() for t in TARGET_SIZES]]
                log.info(f"Dispos : {all_available} — correspondances : {matches}")

                if matches:
                    notify(
                        "DISPO sur Zara !",
                        f"Taille(s) disponible(s) : {', '.join(matches)}\nFonce !\n{URL}",
                    )
                    break

            except Exception as e:
                log.error(f"Erreur : {e}")

            if run_once:
                break

            wait = INTERVAL + random.randint(-20, 20)
            log.info(f"Prochaine vérif dans ~{wait // 60} min")
            time.sleep(wait)


if __name__ == "__main__":
    main()
