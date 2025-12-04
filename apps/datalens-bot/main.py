import os
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
CHAT_ID = os.environ.get("TG_CHAT_ID")
DATALENS_URL = "https://datalens.ru/35o65aulrl0wo-kc-obshiy"

SCREENSHOT_PATH = Path("/app/data/datalens_dashboard.png")
COOKIES_PATH = Path("/app/data/yandex_cookies.json")
SELENIUM_HOST = os.environ.get("SELENIUM_HOST", "http://selenium-chrome:4444/wd/hub")


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def now_moscow():
    return datetime.now(timezone.utc) + timedelta(hours=3)


def save_cookies(driver):
    cookies = driver.get_cookies()
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIES_PATH, 'w') as f:
        json.dump(cookies, f)
    return len(cookies)


def load_cookies(driver):
    if not COOKIES_PATH.exists():
        return False
    try:
        with open(COOKIES_PATH, 'r') as f:
            cookies = json.load(f)

        # Группируем cookies по доменам
        domains = {}
        for cookie in cookies:
            domain = cookie.get('domain', '')
            if domain not in domains:
                domains[domain] = []
            domains[domain].append(cookie)

        # Загружаем cookies для каждого домена
        loaded = 0
        for domain, domain_cookies in domains.items():
            # Определяем URL для домена
            clean_domain = domain.lstrip('.')
            if 'yandex' in clean_domain:
                url = f"https://{clean_domain}"
            elif 'datalens' in clean_domain:
                url = f"https://{clean_domain}"
            else:
                continue

            try:
                driver.get(url)
                time.sleep(1)
                for cookie in domain_cookies:
                    cookie.pop('sameSite', None)
                    cookie.pop('expiry', None)
                    try:
                        driver.add_cookie(cookie)
                        loaded += 1
                    except:
                        pass
            except:
                pass

        log(f"Загружено {loaded} cookies")
        return True
    except Exception as e:
        log(f"Ошибка загрузки cookies: {e}")
        return False

def create_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    try:
        return webdriver.Remote(command_executor=SELENIUM_HOST, options=options)
    except Exception as e:
        log(f"Ошибка создания драйвера: {e}")
        return None


def first_run_mode():
    """Режим первого запуска — собирает cookies со всех доменов."""
    log("=== РЕЖИМ ПЕРВОГО ВХОДА ===")
    driver = create_driver()
    if not driver:
        return

    all_cookies = {}

    try:
        driver.get(DATALENS_URL)
        log("Страница открыта. Залогинься в Яндексе через VNC!")
        log("Cookies сохраняются каждые 3 секунды.")
        log("Когда закончишь — нажми Ctrl+C")

        while True:
            time.sleep(3)
            cookies = driver.get_cookies()

            for cookie in cookies:
                key = f"{cookie.get('domain', '')}_{cookie.get('name', '')}"
                all_cookies[key] = cookie

            # Сохраняем КАЖДЫЙ раз
            COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(COOKIES_PATH, 'w') as f:
                json.dump(list(all_cookies.values()), f)

            log(f"Сохранено {len(all_cookies)} cookies")

    except KeyboardInterrupt:
        log("Остановлено")
    finally:
        driver.quit()
        log(f"Готово. Итого {len(all_cookies)} cookies. Убери FIRST_RUN=true.")

def make_screenshot():
    driver = create_driver()
    if not driver:
        return False

    try:
        if COOKIES_PATH.exists():
            load_cookies(driver)

        log(f"Открываю {DATALENS_URL}")
        driver.get(DATALENS_URL)
        log("Жду 20 сек...")
        time.sleep(20)

        SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(SCREENSHOT_PATH))

        if SCREENSHOT_PATH.exists():
            log(f"Скриншот: {SCREENSHOT_PATH.stat().st_size} байт")
            return True
        return False
    except Exception as e:
        log(f"Ошибка: {e}")
        return False
    finally:
        driver.quit()


def crop_screenshot():
    try:
        if not SCREENSHOT_PATH.exists():
            return False
        img = Image.open(SCREENSHOT_PATH)
        w, h = img.size
        cropped = img.crop((0, int(h*0.25), w, int(h*0.55)))
        cropped.save(SCREENSHOT_PATH)
        log("Скриншот обрезан")
        return True
    except Exception as e:
        log(f"Ошибка кропа: {e}")
        return False


def send_telegram(text=None, photo_path=None):
    if not TG_BOT_TOKEN or not CHAT_ID:
        return False
    try:
        if photo_path and photo_path.exists():
            with open(photo_path, "rb") as f:
                r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                    data={"chat_id": CHAT_ID}, files={"photo": f}, timeout=30)
            return r.status_code == 200
        elif text:
            r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                data={"chat_id": CHAT_ID, "text": text}, timeout=30)
            return r.status_code == 200
    except:
        return False


def main():
    log("=== DATALENS BOT ===")

    if os.environ.get("FIRST_RUN", "").lower() == "true":
        first_run_mode()
        return

    log(f"Cookies: {COOKIES_PATH.exists()}")

    while True:
        now = now_moscow()
        next_run = (now + timedelta(hours=1)).replace(minute=10, second=0, microsecond=0)
        sleep_sec = (next_run - now).total_seconds()
        log(f"Сплю до {next_run.strftime('%H:%M')} МСК")
        time.sleep(sleep_sec)

        if now_moscow().hour < 9:
            continue

        log("=== Делаю отчет ===")
        if make_screenshot():
            crop_screenshot()
            send_telegram(photo_path=SCREENSHOT_PATH)
            send_telegram(text=f"Отчет за {now_moscow().hour}:00")
        else:
            send_telegram(text=f"Ошибка отчета за {now_moscow().hour}:00")


if __name__ == "__main__":
    main()