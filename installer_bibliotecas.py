import openpyxl
import subprocess
import os
import logging
import json

def baixar_pacotes(caminho_excel, pasta_destino, arquivo_falhas_temp):
    """
    Baixa pacotes listados no Excel para a pasta destino.
    """
    if not os.path.exists(caminho_excel):
        logging.error(f"Excel não encontrado: {caminho_excel}")
        return

    logging.info(f"Lendo {caminho_excel}...")
    try:
        wb = openpyxl.load_workbook(caminho_excel)
        ws = wb.active
    except Exception as e:
        logging.error(f"Erro ao abrir Excel: {e}")
        return

    lista_pacotes = [row[0] for row in ws.iter_rows(min_row=2, values_only=True) if row[0]]
    lista_de_falhas = []

    logging.info(f"Iniciando download de {len(lista_pacotes)} pacotes para '{pasta_destino}'...")

    for i, package_name in enumerate(lista_pacotes, 1):
        logging.info(f"[{i}/{len(lista_pacotes)}] Baixando: {package_name}")
        try:
            proc = subprocess.run(
                ["pip", "download", package_name, "-d", pasta_destino],
                capture_output=True, text=True, timeout=120
            )
            if proc.returncode != 0:
                logging.warning(f"Falha ao baixar {package_name}")
                lista_de_falhas.append(package_name)
        except Exception as e:
            logging.error(f"Erro crítico em {package_name}: {e}")
            lista_de_falhas.append(package_name)

    # Salva falhas para o retry
    try:
        with open(arquivo_falhas_temp, "w") as f:
            json.dump(lista_de_falhas, f)
    except Exception as e:
        logging.error(f"Erro ao salvar log de falhas: {e}")