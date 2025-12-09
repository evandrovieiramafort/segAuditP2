import requests
import time
import logging
import openpyxl
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth

# Configurações internas do scraper
PYPI_SEARCH_URL = "https://pypi.org/search/?q=AES&o=&c=Topic+%3A%3A+Security"
MAX_PAGES_TO_SCRAPE = 13
BASE_PYPISTATS_URL = "https://pypistats.org"


def scrape_pypi_package_names(base_search_url, max_pages):
    all_package_data = []
    seen_package_names = set()
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine", fix_hairline=True)

        for page_num in range(1, max_pages + 1):
            url = f"{base_search_url}&page={page_num}"
            driver.get(url)
            time.sleep(3)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            packages_on_page = soup.select("a.package-snippet")

            if not packages_on_page: break

            for pkg_snippet in packages_on_page:
                try:
                    name_tag = pkg_snippet.select_one("span.package-snippet__name")
                    date_tag = pkg_snippet.select_one("span.package-snippet__created time")
                    if name_tag:
                        package_name = name_tag.get_text().strip()
                        last_modified = date_tag.get_text().strip() if date_tag else "N/A"
                        if package_name and package_name not in seen_package_names:
                            all_package_data.append({'name': package_name, 'last_modified': last_modified})
                            seen_package_names.add(package_name)
                except:
                    continue
    except Exception as e:
        logging.error(f"Erro Selenium: {e}")
    finally:
        if driver: driver.quit()
    return all_package_data


def executar_scraping(caminho_saida):
    """
    Executa o processo completo de coleta e salva no caminho_saida especificado pelo main.
    """
    logging.info(f"Iniciando scraping... Destino: {caminho_saida}")
    packages = scrape_pypi_package_names(PYPI_SEARCH_URL, MAX_PAGES_TO_SCRAPE)

    if not packages:
        logging.warning("Nenhum pacote encontrado.")
        return

    final_data = []
    logging.info(f"Coletando estatísticas para {len(packages)} pacotes...")

    for pkg in packages:
        stats_url = f"{BASE_PYPISTATS_URL}/api/packages/{pkg['name'].lower()}/recent"
        downloads = 0
        try:
            resp = requests.get(stats_url, timeout=5)
            if resp.status_code == 200:
                downloads = resp.json().get('data', {}).get('last_month', 0)
        except:
            pass

        final_data.append([pkg['name'], f"https://pypi.org/project/{pkg['name']}/", downloads, pkg['last_modified']])
        time.sleep(0.1)

    # Salva o Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dados PyPI"
    ws.append(["Nome Biblioteca", "Link PyPI", "Downloads (Mês)", "Data Último Lançamento"])

    for row in final_data:
        ws.append(row)

    wb.save(caminho_saida)
    logging.info(f"Arquivo gerado com sucesso: {caminho_saida}")