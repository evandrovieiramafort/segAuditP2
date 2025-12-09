import logging
import sys
import os
import argparse
import shutil

# Importação dos módulos
import extracao
import installer_bibliotecas
import installer_falhas
import orquestrador

# --- CONFIGURAÇÃO DE CONTROLE ---
# True = faz o download de tudo de novo.
# False = pula direto pra auditoria; só usar caso os arquivos já tenham sido baixados.
BAIXAR_NOVAMENTE = True
# --------------------------------

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(module)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline_auditoria.log", encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)


def main():
    parser = argparse.ArgumentParser(description="Pipeline Centralizado de Auditoria NIST")
    parser.add_argument("--coletar", action="store_true", help="Força nova coleta de dados do PyPI.")
    args = parser.parse_args()

    # --- CONFIGURAÇÃO CENTRAL DE CAMINHOS ---
    BASE_DIR = os.getcwd()
    DIR_DOCS = os.path.join(BASE_DIR, "docs")
    DIR_DOWNLOADS = os.path.join(BASE_DIR, "downloads_pypi")
    DIR_DOWNLOADS_FALHAS = os.path.join(BASE_DIR, "downloads_pypi_falhas")
    DIR_VENVS = os.path.join(BASE_DIR, "audit_venvs")

    ARQUIVO_EXCEL_STATS = os.path.join(DIR_DOCS, "stats.xlsx")
    ARQUIVO_TEMP_FALHAS = os.path.join(BASE_DIR, "temp_falhas.json")
    ARQUIVO_RELATORIO_FINAL = os.path.join(BASE_DIR, "relatorio_auditoria_nist.xlsx")

    ARQUIVO_RUNNER = os.path.join(BASE_DIR, "runner.py")
    ARQUIVO_VETORES = os.path.join(BASE_DIR, "vetores_nist.json")

    # Garante que pastas existem
    for pasta in [DIR_DOCS, DIR_DOWNLOADS, DIR_DOWNLOADS_FALHAS, DIR_VENVS]:
        if not os.path.exists(pasta):
            os.makedirs(pasta)

    logging.info("=== INICIANDO PIPELINE CENTRALIZADO ===")
    logging.info(f"MODO DE OPERAÇÃO: {'BAIXAR TUDO' if BAIXAR_NOVAMENTE else 'AUDITAR SOMENTE (Downloads pulados)'}")

    # ---------------------------------------------------------
    # ETAPA 1: COLETA (SCRAPING)
    # ---------------------------------------------------------
    if args.coletar:
        logging.info("\n>>> ETAPA 1: Executando Coleta (Scraping)...")
        try:
            extracao.executar_scraping(caminho_saida=ARQUIVO_EXCEL_STATS)
        except Exception as e:
            logging.critical(f"Falha na coleta: {e}")
            return
    else:
        logging.info("\n>>> ETAPA 1: Coleta pulada (usando arquivo existente).")

    if not os.path.exists(ARQUIVO_EXCEL_STATS):
        logging.error(f"ERRO CRÍTICO: Arquivo de estatísticas não encontrado em: {ARQUIVO_EXCEL_STATS}")
        logging.error("Execute com --coletar na primeira vez.")
        return

    # ---------------------------------------------------------
    # ETAPA 2: DOWNLOADS (CONTROLADA PELA VARIÁVEL)
    # ---------------------------------------------------------
    if BAIXAR_NOVAMENTE:
        logging.info("\n>>> ETAPA 2: Gerenciando Downloads...")
        try:
            # Chama o instalador principal
            installer_bibliotecas.baixar_pacotes(
                caminho_excel=ARQUIVO_EXCEL_STATS,
                pasta_destino=DIR_DOWNLOADS,
                arquivo_falhas_temp=ARQUIVO_TEMP_FALHAS
            )

            # Chama a recuperação de falhas
            installer_falhas.recuperar_falhas(
                arquivo_falhas_temp=ARQUIVO_TEMP_FALHAS,
                pasta_destino=DIR_DOWNLOADS_FALHAS
            )
        except Exception as e:
            logging.error(f"Erro durante downloads: {e}")
    else:
        logging.info("\n>>> ETAPA 2: Downloads pulados (Variável BAIXAR_NOVAMENTE = False).")
        logging.info(f"Usando arquivos já existentes em '{DIR_DOWNLOADS}' e '{DIR_DOWNLOADS_FALHAS}'.")

    # ---------------------------------------------------------
    # ETAPA 3: AUDITORIA E TESTES
    # ---------------------------------------------------------
    logging.info("\n>>> ETAPA 3: Executando Auditoria e Testes NIST...")

    if not os.path.exists(ARQUIVO_RUNNER) or not os.path.exists(ARQUIVO_VETORES):
        logging.critical("Faltando 'runner.py' ou 'vetores_nist.json' na raiz.")
        return

    try:
        orquestrador.executar_auditoria(
            arquivo_referencia=ARQUIVO_EXCEL_STATS,
            dirs_downloads=[DIR_DOWNLOADS, DIR_DOWNLOADS_FALHAS],
            dir_venvs=DIR_VENVS,
            arquivo_runner=ARQUIVO_RUNNER,
            arquivo_vetores=ARQUIVO_VETORES,
            arquivo_saida_relatorio=ARQUIVO_RELATORIO_FINAL
        )
    except Exception as e:
        logging.critical(f"Erro fatal na auditoria: {e}")

    logging.info("\n=== PIPELINE FINALIZADO COM SUCESSO ===")
    logging.info(f"Relatório disponível em: {ARQUIVO_RELATORIO_FINAL}")


if __name__ == "__main__":
    main()