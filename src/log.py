"""Configura o log do robo: um arquivo por dia em logs/ e a saida no terminal."""
import logging
from datetime import date
from pathlib import Path

from src.config import RAIZ


def configurar_log(pasta_logs=None, nivel=logging.INFO):
    """Liga o log do robo. Devolve o caminho do arquivo de log do dia."""
    pasta = Path(pasta_logs) if pasta_logs else RAIZ / "logs"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"robo_{date.today().isoformat()}.log"

    logger = logging.getLogger("avironda")
    logger.setLevel(nivel)
    logger.propagate = False
    for h in list(logger.handlers):  # evita linhas duplicadas se for chamado duas vezes
        logger.removeHandler(h)
        h.close()

    formato = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.FileHandler(arquivo, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(formato)
        logger.addHandler(handler)
    return arquivo