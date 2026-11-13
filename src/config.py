"""Carrega o arquivo de limites (config/limites.json)."""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carregar_limites(caminho=None):
    caminho = Path(caminho) if caminho else RAIZ / "config" / "limites.json"
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)