import subprocess
import os
import logging
import json


def recuperar_falhas(arquivo_falhas_temp, pasta_destino):
    """
    Tenta baixar apenas o código fonte dos pacotes que falharam anteriormente
    e exibe um relatório final.
    """
    if not os.path.exists(arquivo_falhas_temp):
        return

    try:
        with open(arquivo_falhas_temp, "r") as f:
            bibliotecas_falhas = json.load(f)
    except:
        return

    if not bibliotecas_falhas:
        return

    logging.info(f"Tentando recuperar {len(bibliotecas_falhas)} falhas em '{pasta_destino}'...")

    if not os.path.exists(pasta_destino):
        os.makedirs(pasta_destino)

    recuperados = []
    perdidos = []

    for package in bibliotecas_falhas:
        logging.info(f"Tentando fonte (source-only): {package}")

        # Capturamos o retorno do processo
        proc = subprocess.run(
            ["pip", "download", package, "-d", pasta_destino, "--no-binary", ":all:", "--no-deps"],
            capture_output=True,
            timeout=180
        )

        # Se returncode for 0, o download funcionou
        if proc.returncode == 0:
            recuperados.append(package)
        else:
            perdidos.append(package)

    # Limpeza do arquivo temporário
    try:
        os.remove(arquivo_falhas_temp)
    except:
        pass

    # --- Relatório Final ---
    logging.info("-" * 40)
    logging.info("RELATÓRIO DE RECUPERAÇÃO DE FALHAS")
    logging.info("-" * 40)

    if recuperados:
        logging.info(f"✅ SUCESSO - Recuperados ({len(recuperados)}):")
        logging.info(f"   {', '.join(recuperados)}")
    else:
        logging.info("⚠️ Nenhum pacote foi recuperado nesta etapa.")

    if perdidos:
        logging.warning(f"❌ FALHA FINAL - Não foi possível baixar ({len(perdidos)}):")
        logging.warning(f"   {', '.join(perdidos)}")
    else:
        logging.info("✨ Todos os pacotes perdidos foram recuperados com sucesso!")

    logging.info("-" * 40)