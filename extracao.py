import requests
import json
import time
import logging
# Importação para criar o Excel
import openpyxl 
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth

def scrape_pypi_package_names(base_search_url, max_pages_to_scrape):
    """
    Passo 1: Faz o scraping do PyPI usando Selenium com stealth para obter nomes de pacotes e datas.
    """
    all_package_data = []
    seen_package_names = set() 
    driver = None
    
    try:
        logging.info("Configurando o WebDriver do Selenium...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # User-Agent de um navegador real
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
        logging.info("WebDriver configurado com 'stealth'.")

        logging.info(f"Iniciando scraping em: {base_search_url}")
        
        for page_num in range(1, max_pages_to_scrape + 1):
            url = f"{base_search_url}&page={page_num}"
            logging.info(f"Navegando para a página {page_num}...")
            
            driver.get(url)
            time.sleep(5) # Espera para carregamento completo
            
            # --- DIAGNÓSTICO ---
            page_title = driver.title
            logging.info(f"Título da página carregada: '{page_title}'")
            
            page_html = driver.page_source
            soup = BeautifulSoup(page_html, 'html.parser')
            
            # --- SELETOR CORRIGIDO ---
            packages_on_page = soup.select("a.package-snippet")
            
            if not packages_on_page:
                error_msg = f"Nenhum pacote encontrado na página {page_num}."
                logging.error(error_msg)
                
                debug_filename = f"pagina_falha_{page_num}.html"
                with open(debug_filename, "w", encoding="utf-8") as f:
                    f.write(page_html)
                logging.info(f"HTML completo salvo em '{debug_filename}' para análise.")
                
                lower_html = page_html.lower()
                if "captcha" in lower_html:
                    raise Exception("⛔ DETECÇÃO DE BOT: O PyPI apresentou um CAPTCHA.")
                elif "cloudflare" in lower_html:
                    raise Exception("⛔ DETECÇÃO DE BOT: Bloqueio do Cloudflare identificado.")
                elif "search results" not in lower_html and "results for" not in lower_html:
                    raise Exception(f"⚠️ LAYOUT DESCONHECIDO: A página carregou, mas não parece uma página de busca válida. Verifique '{debug_filename}'.")
                else:
                    raise Exception(f"⚠️ ERRO DE SELETOR: A página parece correta, mas o seletor 'a.package-snippet' não encontrou nada. O PyPI pode ter mudado o CSS.")
                
            count = 0
            for pkg_snippet in packages_on_page:
                try:
                    # --- SELETORES CORRIGIDOS ---
                    name_tag = pkg_snippet.select_one("span.package-snippet__name")
                    date_tag = pkg_snippet.select_one("span.package-snippet__created time")
                    
                    if name_tag and date_tag:
                        package_name = name_tag.get_text().strip()
                        last_modified = date_tag.get_text().strip()
                        
                        if package_name and package_name not in seen_package_names:
                            all_package_data.append({
                                'name': package_name,
                                'last_modified': last_modified
                            })
                            seen_package_names.add(package_name)
                            count += 1
                    else:
                        logging.warning("Encontrou container de pacote, mas faltou nome ou data.")
                except Exception as inner_e:
                    logging.error(f"Erro ao processar um item específico na lista: {inner_e}")
            
            logging.info(f"Página {page_num} raspada com sucesso: {count} novos pacotes.")
            
    except Exception as e:
        logging.exception(f"❌ O SCRAPING FALHOU: {e}")
        raise e
        
    finally:
        if driver:
            driver.quit()
            logging.info("Navegador (Selenium) fechado.")
            
    return all_package_data

def buscar_estatisticas_do_pacote(stats_api_url):
    """
    Passo 2: Busca as estatísticas de um pacote específico na API pypistats.org.
    """
    logging.info(f"Buscando dados de: {stats_api_url}")
    
    try:
        response = requests.get(stats_api_url, timeout=10)
        response.raise_for_status()
        
        try:
            data = response.json()
            logging.info(f"  ✅ Sucesso! Dados de '{data.get('package', 'N/A')}' coletados.")
            return data
        except json.JSONDecodeError:
            logging.warning(f"  ⚠️ Resposta não é JSON para {stats_api_url}")
            return None

    except requests.exceptions.HTTPError as err:
        status = err.response.status_code
        logging.error(f"  ❌ Erro HTTP {status} ao buscar {stats_api_url}: {err.response.text.strip()}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"  ❌ Erro de Requisição ao buscar {stats_api_url}: {e}")
        return None

# --- Configuração Principal ---
PYPI_SEARCH_URL = "https://pypi.org/search/?q=AES&o=&c=Topic+%3A%3A+Security"
MAX_PAGES_TO_SCRAPE = 13
BASE_PYPISTATS_URL = "https://pypistats.org"
# Alterado para Excel
NOME_ARQUIVO_SAIDA = "estatisticas_pacotes_raspados.xlsx"

# Configuração global do logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("--- PASSO 1: INICIANDO WEB SCRAPING NO PYPI (COM SELENIUM) ---")

try:
    scraped_packages = scrape_pypi_package_names(PYPI_SEARCH_URL, MAX_PAGES_TO_SCRAPE)

    if not scraped_packages:
        logging.warning("Nenhum pacote encontrado no scraping. Encerrando execução.")
    else:
        logging.info(f"--- Scraping concluído. {len(scraped_packages)} pacotes únicos encontrados. ---")
        
        logging.info("\n--- PASSO 2: BUSCANDO ESTATÍSTICAS E PREPARANDO DADOS ---")
        
        final_data_list = []
        
        for package_info in scraped_packages:
            package_name = package_info['name']
            last_modified_date = package_info['last_modified']
            
            # Garante que o nome esteja em minúsculas para a API
            package_name_lower = package_name.lower()
            
            logging.info(f"Processando: '{package_name}'")
            
            stats_url = f"{BASE_PYPISTATS_URL}/api/packages/{package_name_lower}/recent"
            
            # Faz a requisição
            dados_pacote_api = buscar_estatisticas_do_pacote(stats_url)
            
            pypi_link = f"https://pypi.org/project/{package_name}/"
            
            # Monta o objeto completo para processamento
            pacote_consolidado = {
                "metadados_scraper": {
                    "nome_biblioteca": package_name,
                    "link_pypi": pypi_link,
                    "data_ultima_modificacao": last_modified_date
                },
                "resposta_api_stats": dados_pacote_api
            }
            
            final_data_list.append(pacote_consolidado)
            
            time.sleep(0.5) # Pausa entre requisições da API

        # Passo 3: Salvar em Excel (.xlsx)
        try:
            logging.info(f"\n--- PASSO 3: SALVANDO DADOS EM {NOME_ARQUIVO_SAIDA} ---")
            
            # Cria um novo Workbook do Excel
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Estatísticas PyPI"
            
            # Define os cabeçalhos
            headers = ["Nome Biblioteca", "Link PyPI", "Downloads (Mês)", "Data Último Lançamento"]
            ws.append(headers)
            
            # Itera sobre os dados e preenche as linhas
            for item in final_data_list:
                meta = item.get('metadados_scraper', {})
                stats_response = item.get('resposta_api_stats')
                
                nome = meta.get('nome_biblioteca', 'N/A')
                link = meta.get('link_pypi', 'N/A')
                data_lancamento = meta.get('data_ultima_modificacao', 'N/A')
                
                # Extrai downloads mensais com segurança (pode ser None se a API falhou)
                downloads_mensais = 0
                if stats_response and 'data' in stats_response:
                    downloads_mensais = stats_response['data'].get('last_month', 0)
                
                # Adiciona a linha na planilha
                ws.append([nome, link, downloads_mensais, data_lancamento])
            
            # Salva o arquivo
            wb.save(NOME_ARQUIVO_SAIDA)
            
            logging.info(f"--- Processo concluído ---")
            logging.info(f"🔥 Dados de {len(final_data_list)} pacotes salvos em '{NOME_ARQUIVO_SAIDA}'")

        except Exception as e:
            logging.exception(f"\n❌ Erro ao salvar o arquivo Excel final: {e}")

except Exception as main_e:
    logging.critical(f"O programa foi interrompido devido a um erro crítico: {main_e}")