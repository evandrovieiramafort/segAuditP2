import logging
import sys
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(module)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pipeline_auditoria.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    parser = argparse.ArgumentParser(description="Pipeline de Auditoria de Criptografia NIST")

    parser.add_argument(
        "--coletar",
        action="store_true",
        help="Força a execução do Coletor (Scraping do PyPI). Requer arquivo 'coletor_stats_pypi.py'."
    )

    parser.add_argument(
        "--pular-download",
        action="store_true",
        help="Pula a etapa de verificação/download de pacotes."
    )

    args = parser.parse_args()

    executar_download = not args.pular_download
    executar_coleta = args.coletar

    logging.info("=== INICIANDO PIPELINE DE AUDITORIA DE CRIPTOGRAFIA ===")
    logging.info(f"Configuração: Coleta={executar_coleta}, Download={executar_download}")

    if executar_coleta:
        logging.info("\n>>> ETAPA 1: Coletando nomes de pacotes do PyPI (FLAG ATIVADA)...")
        try:
            import coletor_stats_pypi
            coletor_stats_pypi.main_execution()
        except ImportError:
            logging.error("ERRO: Arquivo 'coletor_stats_pypi.py' não encontrado. Salve o código do coletor na pasta.")
            return
        except Exception as e:
            logging.exception(f"Falha na Etapa 1: {e}")
            return
    else:
        logging.info("\n>>> ETAPA 1: Pulada (Flag --coletar não detectada). Usando dados locais (docs/stats.xlsx).")

    if executar_download:
        logging.info("\n>>> ETAPA 2: Verificando downloads...")
        try:
            import installer_bibliotecas
            import installer_falhas

            logging.info(">>> Executando instalador principal...")
            installer_bibliotecas.baixar_pacotes_do_excel()

            logging.info(">>> Executando tentativa de recuperação de falhas...")
            installer_falhas.retry_downloads()

        except ImportError as e:
            logging.error(f"ERRO CRÍTICO: Arquivo de instalação não encontrado: {e}")
            logging.error("Verifique se 'installer_bibliotecas.py' e 'installer_falhas.py' estão na pasta.")
            return
        except Exception as e:
            logging.error(f"Falha na Etapa 2: {e}")
    else:
        logging.info("\n>>> ETAPA 2: Downloads pulados pelo usuário.")

    logging.info("\n>>> ETAPA 3: Executando Auditoria NIST em ambientes isolados...")
    try:
        import orquestrador
        orquestrador.auditar_pacotes()
    except ImportError as e:
        logging.error(f"ERRO CRÍTICO: Arquivo 'orquestrador.py' não encontrado: {e}")
    except Exception as e:
        logging.exception(f"Falha crítica na Etapa 3: {e}")

    logging.info("\n=== PIPELINE FINALIZADO ===")
    logging.info("Verifique o relatório final: relatorio_auditoria_nist.xlsx")

if __name__ == "__main__":
    main()