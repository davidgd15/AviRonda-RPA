"""Ponto de entrada do robo: processa todos os arquivos novos de data/entrada/.

Uso (na raiz do projeto, com a .venv ativa):
    python -m src.main

Cada arquivo processado com sucesso vai para data/processados/; os que derem
erro vao para data/erros/. Um arquivo com problema nunca interrompe os demais.
"""
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from src.config import RAIZ, carregar_limites
from src.log import configurar_log
from src.robo import ArquivoInvalido, processar_arquivo

log = logging.getLogger("avironda")


def _mover(arquivo, pasta_destino):
    """Move o arquivo sem sobrescrever outro de mesmo nome."""
    pasta_destino.mkdir(parents=True, exist_ok=True)
    destino = pasta_destino / arquivo.name
    if destino.exists():
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = pasta_destino / f"{arquivo.stem}_{carimbo}{arquivo.suffix}"
    shutil.move(str(arquivo), str(destino))
    return destino


def executar(pasta_entrada=None, pasta_processados=None, pasta_erros=None, cfg=None):
    entrada = Path(pasta_entrada) if pasta_entrada else RAIZ / "data" / "entrada"
    processados = Path(pasta_processados) if pasta_processados else RAIZ / "data" / "processados"
    erros_dir = Path(pasta_erros) if pasta_erros else RAIZ / "data" / "erros"
    cfg = cfg or carregar_limites()

    entrada.mkdir(parents=True, exist_ok=True)
    arquivos = sorted(entrada.glob("*.json"))
    log.info("inicio da execucao: %d arquivo(s) novo(s) em %s", len(arquivos), entrada.name)

    resultados, erros = [], []
    for arquivo in arquivos:
        try:
            resultado = processar_arquivo(arquivo, cfg)
        except ArquivoInvalido as erro:
            log.error("arquivo invalido, movido para erros: %s", erro)
            erros.append({"tipo": "erro_arquivo", "arquivo": arquivo.name, "motivo": str(erro)})
            _mover(arquivo, erros_dir)
            continue
        except Exception as erro:  # nenhuma falha silenciosa: registra e segue para o proximo
            log.exception("falha inesperada ao processar %s", arquivo.name)
            erros.append({
                "tipo": "erro_arquivo", "arquivo": arquivo.name,
                "motivo": f"falha inesperada ({type(erro).__name__})",
            })
            _mover(arquivo, erros_dir)
            continue

        resultados.append(resultado)
        _mover(arquivo, processados)

    log.info("fim da execucao: %d processado(s), %d com erro", len(resultados), len(erros))
    return {"resultados": resultados, "erros": erros}


def main():
    configurar_log()
    saida = executar()
    return 0 if not saida["erros"] else 2


if __name__ == "__main__":
    sys.exit(main())