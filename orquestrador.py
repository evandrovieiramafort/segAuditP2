import os
import subprocess
import sys
import shutil
import json
import logging
import openpyxl


def setup_excel_report(arquivo_vetores):
    try:
        with open(arquivo_vetores, "r", encoding='utf-8') as f:
            vectors = json.load(f)
            test_headers = [v["id_teste"] for v in vectors]
    except:
        test_headers = ["ERRO_LEITURA_VETORES"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Auditoria NIST"

    static_pre = ["Ranking", "Biblioteca", "Arquivo Usado", "Downloads (Mês)", "Status Instalação"]
    static_pos = ["Tempo Enc (ms)", "Tempo Dec (ms)", "Score Final"]
    ws.append(static_pre + test_headers + static_pos)
    return wb, ws, test_headers


def encontrar_arquivo(nome_lib, lista_diretorios):
    nome_norm = nome_lib.lower().replace('-', '_')
    for d in lista_diretorios:
        if not os.path.exists(d): continue
        for f in os.listdir(d):
            f_lower = f.lower()
            if f_lower.startswith(nome_norm) or f_lower == nome_norm:
                return os.path.join(d, f)
    return None


def criar_venv(path):
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
        except:
            pass
    subprocess.run([sys.executable, "-m", "venv", path], check=True)


def get_venv_bin(venv_path, bin_name):
    if os.name == 'nt':
        return os.path.join(venv_path, "Scripts", f"{bin_name}.exe")
    return os.path.join(venv_path, "bin", bin_name)


def executar_auditoria(arquivo_referencia, dirs_downloads, dir_venvs, arquivo_runner, arquivo_vetores,
                       arquivo_saida_relatorio):
    logging.info(f"Preparando relatório em: {arquivo_saida_relatorio}")
    wb, ws, test_headers = setup_excel_report(arquivo_vetores)

    bibliotecas_map = {}
    try:
        wb_ref = openpyxl.load_workbook(arquivo_referencia)
        ws_ref = wb_ref.active
        for row in ws_ref.iter_rows(min_row=2, values_only=True):
            if row[0]: bibliotecas_map[row[0]] = row[2] if row[2] else 0
    except Exception as e:
        logging.error(f"Erro ao ler referência: {e}")
        return

    libs_alvo = list(bibliotecas_map.keys())
    logging.info(f"Iniciando auditoria de {len(libs_alvo)} bibliotecas...")

    for i, nome_lib in enumerate(libs_alvo):
        logging.info(f"[{i + 1}/{len(libs_alvo)}] Processando: {nome_lib}...")

        arquivo_path = encontrar_arquivo(nome_lib, dirs_downloads)

        lib_data = {
            "lib": nome_lib,
            "file": os.path.basename(arquivo_path) if arquivo_path else "N/A",
            "downloads": bibliotecas_map.get(nome_lib, 0),
            "status": "ARQUIVO AUSENTE" if not arquivo_path else "FALHA INSTALAÇÃO",
            "tests": {k: "-" for k in test_headers},
            "enc": 0, "dec": 0
        }

        if arquivo_path:
            venv_path = os.path.join(dir_venvs, f"venv_{nome_lib}")
            try:
                criar_venv(venv_path)
                pip = get_venv_bin(venv_path, "pip")
                python = get_venv_bin(venv_path, "python")

                # Instala dependências básicas
                subprocess.run([pip, "install", "cryptography"], capture_output=True)

                # Instala lib alvo (TIMEOUT AUMENTADO + ENCODING FIX)
                proc_inst = subprocess.run(
                    [pip, "install", arquivo_path],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',  # Força UTF-8
                    errors='replace',  # Substitui caracteres bugados por '?'
                    timeout=120  # Aumentado para 120s
                )

                if proc_inst.returncode == 0:
                    lib_data["status"] = "SUCESSO"

                    # Roda o runner (ENCODING FIX)
                    proc_test = subprocess.run(
                        [python, arquivo_runner, nome_lib],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        timeout=40,
                        cwd=os.path.dirname(arquivo_runner)
                    )

                    if proc_test.returncode == 0:
                        try:
                            res = json.loads(proc_test.stdout)
                            if "error" in res:
                                erro_msg = res.get('error', 'Erro Genérico')
                                status_code = res.get('status', 'FAIL')
                                lib_data["status"] = f"FALHA ({status_code}): {erro_msg}"
                            else:
                                for t_id in test_headers:
                                    lib_data["tests"][t_id] = res.get(t_id, "FAIL")
                                lib_data["enc"] = res.get("enc_time", 0)
                                lib_data["dec"] = res.get("dec_time", 0)
                        except:
                            lib_data["status"] = "ERRO JSON (Saída inválida do Runner)"
                    else:
                        erro_runner = "Erro desconhecido"
                        if proc_test.stderr:
                            linhas_erro = [l for l in proc_test.stderr.strip().split('\n') if l.strip()]
                            if linhas_erro: erro_runner = linhas_erro[-1]

                        lib_data["status"] = f"CRASH RUNNER: {erro_runner}"
                else:
                    erro_pip = "Erro desconhecido"
                    if proc_inst.stderr:
                        linhas_erro = [l for l in proc_inst.stderr.strip().split('\n') if l.strip()]
                        if linhas_erro: erro_pip = linhas_erro[-1]

                    lib_data["status"] = f"ERRO INSTALL: {erro_pip}"

            except subprocess.TimeoutExpired:
                lib_data["status"] = "TIMEOUT (Instalação demorou > 120s)"
                logging.error(f"   ⌛ TIMEOUT na instalação")
            except Exception as e:
                logging.error(f"Erro venv: {e}")
                lib_data["status"] = f"EXCEÇÃO VENV: {str(e)}"
            finally:
                try:
                    shutil.rmtree(venv_path)
                except:
                    pass

        # --- LOG DETALHADO ---
        status = lib_data["status"]
        if status == "SUCESSO":
            logging.info(f"   ✅ SUCESSO! (Enc: {lib_data['enc']:.2f}ms)")
        elif "ARQUIVO AUSENTE" in status:
            logging.warning(f"   ⚠️  PULADO: Arquivo não baixado.")
        elif "NOT_FOUND" in status or "Implementation not found" in status:
            logging.warning(f"   ⛔ SEM CLASSE AES: Pacote instalado, mas sem AES visível.")
        elif "ERRO INSTALL" in status:
            logging.error(f"   ❌ {status}")
        elif "TIMEOUT" in status:
            logging.error(f"   ⌛ {status}")
        else:
            logging.error(f"   ❌ FALHA: {status}")

        row = [i + 1, lib_data["lib"], lib_data["file"], lib_data["downloads"], lib_data["status"]]
        for t_id in test_headers: row.append(lib_data["tests"].get(t_id, "-"))
        row.extend([lib_data["enc"], lib_data["dec"], 0])
        ws.append(row)

    wb.save(arquivo_saida_relatorio)
    logging.info(f"Relatório final salvo em: {arquivo_saida_relatorio}")