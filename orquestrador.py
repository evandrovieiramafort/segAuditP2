import os
import subprocess
import sys
import shutil
import json
import logging
import openpyxl
from pathlib import Path

ARQUIVO_REFERENCIA = os.path.join("docs", "stats.xlsx")
DIR_DOWNLOADS = "downloads_pypi"
DIR_DOWNLOADS_FALHAS = "downloads_pypi_falhas"
DIR_VENVS = "audit_venvs"
ARQUIVO_REPORT = "relatorio_auditoria_nist.xlsx"
RUNNER_SCRIPT = "runner.py"
DATA_FILE = "vetores_nist.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


def setup_excel_and_get_headers():
    try:
        with open(DATA_FILE, "r") as f:
            vectors = json.load(f)
            # Extrai IDs usando a nova chave "id_teste"
            test_headers = [v["id_teste"] for v in vectors]
    except:
        test_headers = ["TESTES_NAO_CARREGADOS"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Auditoria NIST"

    static_headers_pre = ["Ranking", "Biblioteca", "Arquivo Usado", "Downloads (Mês)", "Status Instalação"]
    static_headers_pos = ["Tempo Enc (ms)", "Tempo Dec (ms)", "Score Final"]

    ws.append(static_headers_pre + test_headers + static_headers_pos)
    return wb, ws, test_headers


def encontrar_arquivo_instalacao(nome_biblioteca):
    nome_norm = nome_biblioteca.lower().replace('-', '_')
    dirs_to_search = [DIR_DOWNLOADS, DIR_DOWNLOADS_FALHAS]
    for d in dirs_to_search:
        if not os.path.exists(d): continue
        for f in os.listdir(d):
            f_lower = f.lower()
            if f_lower.startswith(f"{nome_norm}-") or \
                    f_lower.startswith(f"{nome_norm}_") or \
                    f_lower.startswith(f"{nome_norm}."):
                return os.path.join(d, f)
            if f_lower == nome_norm:
                return os.path.join(d, f)
    return None


def criar_venv(path):
    if os.path.exists(path): shutil.rmtree(path)
    subprocess.run([sys.executable, "-m", "venv", path], check=True)


def get_venv_python(venv_path):
    return os.path.join(venv_path, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(venv_path, "bin",
                                                                                                 "python")


def get_venv_pip(venv_path):
    return os.path.join(venv_path, "Scripts", "pip.exe") if os.name == 'nt' else os.path.join(venv_path, "bin", "pip")


def calcular_ranking_final(audit_results, test_headers):
    total_libs = len(audit_results)

    # Score Base (Absoluto)
    for item in audit_results:
        score = 0
        if item["status"] == "SUCESSO":
            score += 1

        for t_id in test_headers:
            if item["tests"].get(t_id) == "PASS":
                score += 1

        item["temp_score"] = score

    # Ranking de Downloads
    sorted_by_down = sorted(audit_results, key=lambda x: x["downloads"], reverse=True)
    for rank, item in enumerate(sorted_by_down):
        points = total_libs - rank
        item["temp_score"] += points

    # Ranking de Tempo Enc
    valid_enc = [x for x in audit_results if x["enc_time"] > 0]
    sorted_enc = sorted(valid_enc, key=lambda x: x["enc_time"])
    for rank, item in enumerate(sorted_enc):
        points = total_libs - rank
        item["temp_score"] += points

    # Ranking de Tempo Dec
    valid_dec = [x for x in audit_results if x["dec_time"] > 0]
    sorted_dec = sorted(valid_dec, key=lambda x: x["dec_time"])
    for rank, item in enumerate(sorted_dec):
        points = total_libs - rank
        item["temp_score"] += points

    final_ranking = sorted(audit_results, key=lambda x: x["temp_score"], reverse=True)
    return final_ranking


def auditar_pacotes():
    if not os.path.exists(RUNNER_SCRIPT) or not os.path.exists(DATA_FILE) or not os.path.exists(ARQUIVO_REFERENCIA):
        logging.error("Arquivos essenciais não encontrados.")
        return

    wb, ws, test_headers = setup_excel_and_get_headers()

    logging.info(f"Lendo dados de referência: {ARQUIVO_REFERENCIA}")
    bibliotecas_map = {}
    try:
        wb_ref = openpyxl.load_workbook(ARQUIVO_REFERENCIA)
        ws_ref = wb_ref.active
        for row in ws_ref.iter_rows(min_row=2, values_only=True):
            if row[0]:
                try:
                    downloads = int(row[2]) if row[2] else 0
                except:
                    downloads = 0
                bibliotecas_map[row[0]] = downloads
    except Exception as e:
        logging.error(f"Erro ao ler Excel: {e}")
        return

    bibliotecas_alvo = list(bibliotecas_map.keys())
    logging.info(f"Auditando {len(bibliotecas_alvo)} pacotes...")

    if not os.path.exists(DIR_VENVS): os.makedirs(DIR_VENVS)

    audit_data_list = []

    for i, nome_lib in enumerate(bibliotecas_alvo):
        logging.info(f"[{i + 1}/{len(bibliotecas_alvo)}] Auditando: {nome_lib}...")

        downloads_count = bibliotecas_map.get(nome_lib, 0)
        arquivo_path = encontrar_arquivo_instalacao(nome_lib)

        lib_data = {
            "lib": nome_lib,
            "file": os.path.basename(arquivo_path) if arquivo_path else "NÃO ENCONTRADO",
            "downloads": downloads_count,
            "status": "DOWNLOAD FALHOU" if not arquivo_path else "FALHA INSTALAÇÃO",
            "tests": {k: "-" for k in test_headers},
            "enc_time": 0,
            "dec_time": 0,
            "temp_score": 0
        }

        if not arquivo_path:
            audit_data_list.append(lib_data)
            continue

        venv_path = os.path.join(DIR_VENVS, f"venv_{nome_lib}")
        criar_venv(venv_path)
        pip_cmd = get_venv_pip(venv_path)
        python_cmd = get_venv_python(venv_path)

        subprocess.run([pip_cmd, "install", "cryptography"], capture_output=True)

        try:
            proc = subprocess.run([pip_cmd, "install", arquivo_path], capture_output=True, text=True, timeout=120)

            if proc.returncode == 0:
                lib_data["status"] = "SUCESSO"
                nome_import = nome_lib.replace('-', '_')

                try:
                    proc_test = subprocess.run(
                        [python_cmd, RUNNER_SCRIPT, nome_import],
                        capture_output=True, text=True, timeout=60, cwd=os.getcwd()
                    )

                    if proc_test.returncode == 0:
                        try:
                            res = json.loads(proc_test.stdout)
                            for t_id in test_headers:
                                lib_data["tests"][t_id] = res.get(t_id, "N/A")

                            lib_data["enc_time"] = res.get("enc_time", 0)
                            lib_data["dec_time"] = res.get("dec_time", 0)

                        except:
                            lib_data["status"] = "ERRO JSON"
                    else:
                        lib_data["status"] = "ERRO RUNNER"
                except subprocess.TimeoutExpired:
                    lib_data["status"] = "TIMEOUT TESTE"

        except subprocess.TimeoutExpired:
            lib_data["status"] = "TIMEOUT INSTALAÇÃO"

        audit_data_list.append(lib_data)
        try:
            shutil.rmtree(venv_path)
        except:
            pass

    logging.info("Calculando Ranking Competitivo...")
    ranked_list = calcular_ranking_final(audit_data_list, test_headers)

    for rank, item in enumerate(ranked_list, 1):
        row = [
            rank,
            item["lib"],
            item["file"],
            item["downloads"],
            item["status"]
        ]

        for t_id in test_headers:
            row.append(item["tests"].get(t_id, "-"))

        row.append(item["enc_time"])
        row.append(item["dec_time"])
        row.append(item["temp_score"])

        ws.append(row)

    wb.save(ARQUIVO_REPORT)
    logging.info(f"Auditoria finalizada! Relatório salvo em: {ARQUIVO_REPORT}")


if __name__ == "__main__":
    auditar_pacotes()