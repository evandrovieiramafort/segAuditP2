import openpyxl
import subprocess
import os
import logging
import json

ARQUIVO_EXCEL = "docs/stats.xlsx"
PASTA_DESTINO = "downloads_pypi"
ARQUIVO_TEMP_FALHAS = "temp_falhas.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def baixar_pacotes_do_excel():
    if not os.path.exists(ARQUIVO_EXCEL):
        logging.error(f"Arquivo '{ARQUIVO_EXCEL}' não encontrado.")
        return

    if not os.path.exists(PASTA_DESTINO):
        os.makedirs(PASTA_DESTINO)
        logging.info(f"Pasta '{PASTA_DESTINO}' criada.")

    logging.info("Lendo lista de bibliotecas...")
    try:
        wb = openpyxl.load_workbook(ARQUIVO_EXCEL)
        ws = wb.active
    except Exception as e:
        logging.error(f"Erro ao abrir Excel: {e}")
        return

    lista_pacotes = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        package_name = row[0]
        if package_name:
            lista_pacotes.append(package_name)

    total_pacotes = len(lista_pacotes)
    logging.info(f"Total de pacotes encontrados: {total_pacotes}")

    sucessos = 0
    falhas = 0
    lista_de_falhas = []

    for i, package_name in enumerate(lista_pacotes, 1):
        logging.info(f"[{i}/{total_pacotes}] ⬇️ Baixando: {package_name}...")

        try:
            processo = subprocess.run(
                ["pip", "download", package_name, "-d", PASTA_DESTINO],
                capture_output=True,
                text=True,
                timeout=120
            )

            if processo.returncode == 0:
                logging.info(f"✅ Sucesso: {package_name}")
                sucessos += 1
            else:
                erro_curto = processo.stderr.strip().split('\n')[-1] if processo.stderr else "Erro desconhecido"
                logging.error(f"❌ Falha ao baixar {package_name}: {erro_curto}")
                falhas += 1
                lista_de_falhas.append(package_name)

        except subprocess.TimeoutExpired:
            logging.error(f"⏰ Timeout: O download de {package_name} demorou demais.")
            falhas += 1
            lista_de_falhas.append(package_name)
        except Exception as e:
            logging.error(f"💥 Erro crítico em {package_name}: {e}")
            falhas += 1
            lista_de_falhas.append(package_name)

    try:
        with open(ARQUIVO_TEMP_FALHAS, "w") as f:
            json.dump(lista_de_falhas, f)
        logging.info(f"Lista de falhas salva em '{ARQUIVO_TEMP_FALHAS}' para retentativa.")
    except Exception as e:
        logging.error(f"Erro ao salvar lista temporária de falhas: {e}")

    logging.info(f"\n--- RESUMO ---")
    logging.info(f"Arquivos salvos em: {os.path.abspath(PASTA_DESTINO)}")
    logging.info(f"Sucessos: {sucessos}")
    logging.info(f"Falhas: {falhas}")

if __name__ == "__main__":
    baixar_pacotes_do_excel()