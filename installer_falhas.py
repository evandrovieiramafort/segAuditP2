import subprocess
import os
import logging
import json

PASTA_DESTINO = "downloads_pypi_falhas"
ARQUIVO_TEMP_FALHAS = "temp_falhas.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def retry_downloads():
    if not os.path.exists(PASTA_DESTINO):
        os.makedirs(PASTA_DESTINO)
        logging.info(f"Pasta '{PASTA_DESTINO}' criada para as tentativas.")

    bibliotecas_falhas = []

    if os.path.exists(ARQUIVO_TEMP_FALHAS):
        try:
            with open(ARQUIVO_TEMP_FALHAS, "r") as f:
                bibliotecas_falhas = json.load(f)
            logging.info(f"Carregada lista dinâmica de falhas com {len(bibliotecas_falhas)} itens.")
        except Exception as e:
            logging.error(f"Erro ao ler arquivo temporário de falhas: {e}")
    else:
        logging.info("Nenhum arquivo de falhas anteriores encontrado. Nada a recuperar.")


    if not bibliotecas_falhas:
        logging.info("A lista de falhas está vazia ou inacessível. Tudo certo!")
        return

    total_falhas = len(bibliotecas_falhas)
    logging.info(f"Iniciando tentativa de recuperação para {total_falhas} pacotes...")

    sucessos = 0
    falhas = 0

    for i, package in enumerate(bibliotecas_falhas, 1):
        logging.info(f"[{i}/{total_falhas}] 🔄 Tentando baixar fonte de: {package}...")

        comando = [
            "pip", "download", package,
            "-d", PASTA_DESTINO,
            "--no-binary", ":all:",
            "--no-deps"
        ]

        try:
            processo = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=180
            )

            if processo.returncode == 0:
                logging.info(f"✅ SUCESSO (Fonte): {package}")
                sucessos += 1
            else:
                logging.warning(f"❌ AINDA FALHOU: {package}")
                erro_limpo = "Erro desconhecido"
                if processo.stderr:
                    linhas_erro = [L for L in processo.stderr.strip().split('\n') if L.strip()]
                    if linhas_erro:
                        erro_limpo = linhas_erro[-1]

                logging.error(f"   Detalhe: {erro_limpo}")
                falhas += 1

        except subprocess.TimeoutExpired:
            logging.error(f"⏰ Timeout (3min) esgotado ao tentar baixar {package}")
            falhas += 1
        except Exception as e:
            logging.error(f"💥 Erro crítico (Exceção Python): {e}")
            falhas += 1

    if os.path.exists(ARQUIVO_TEMP_FALHAS):
        try:
            os.remove(ARQUIVO_TEMP_FALHAS)
        except:
            pass

    logging.info("-" * 30)
    logging.info(f"Recuperação concluída. Recuperados: {sucessos} | Perdidos: {falhas}")
    logging.info(f"Verifique a pasta: {os.path.abspath(PASTA_DESTINO)}")


if __name__ == "__main__":
    retry_downloads()