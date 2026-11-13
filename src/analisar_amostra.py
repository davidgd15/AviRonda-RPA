"""Analisa um arquivo de leituras do carrinho (JSON Lines) antes de construirmos o robo.

Uso (na raiz do projeto, com a .venv ativa):
    python src/analisar_amostra.py data/entrada/carrinho_G-SDE-01_2026-11-04.json
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carregar_limites():
    with open(RAIZ / "config" / "limites.json", encoding="utf-8") as f:
        return json.load(f)


def temperatura_alvo(idade_dias, cfg):
    t = cfg["temperatura"]
    return max(t["alvo_minimo_c"], t["alvo_inicial_c"] - t["queda_por_dia_c"] * (idade_dias - 1))


def classificar(leitura, cfg):
    """Devolve 'ok', 'atencao' ou 'critico' para uma leitura ja validada."""
    t = cfg["temperatura"]
    alvo = temperatura_alvo(leitura["idade_lote_dias"], cfg)
    desvio = leitura["temp_c"] - alvo
    if desvio > t["critico_acima_do_alvo_c"] or leitura["co2_ppm"] > cfg["co2_ppm"]["critico"]:
        return "critico"
    if desvio > t["atencao_acima_do_alvo_c"] or leitura["co2_ppm"] > cfg["co2_ppm"]["atencao"]:
        return "atencao"
    return "ok"


def main(caminho):
    cfg = carregar_limites()
    faixa = cfg["faixas_plausiveis"]
    janela = timedelta(minutes=cfg["janela_confirmacao_min"])

    total = invalidas = temp_nula = temp_fora = co2_fora = duplicadas = 0
    vistos = set()
    validas = []

    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            total += 1
            try:
                r = json.loads(linha)
                r["ts_dt"] = datetime.fromisoformat(r["ts"])
                chave = (r["galpao_id"], r["zona"], r["ts"])
                r["idade_lote_dias"] = int(r["idade_lote_dias"])
            except (ValueError, KeyError, TypeError):
                invalidas += 1
                continue
            temp, co2 = r.get("temp_c"), r.get("co2_ppm")
            if temp is None:
                temp_nula += 1
                continue
            if not (faixa["temperatura_c"]["min"] <= temp <= faixa["temperatura_c"]["max"]):
                temp_fora += 1
                continue
            if co2 is None or not (faixa["co2_ppm"]["min"] <= co2 <= faixa["co2_ppm"]["max"]):
                co2_fora += 1
                continue
            if chave in vistos:
                duplicadas += 1
                continue
            vistos.add(chave)
            validas.append(r)

    # Classificacao e teste de confirmacao pela proxima leitura da mesma zona
    por_zona = defaultdict(list)
    for r in validas:
        r["status"] = classificar(r, cfg)
        por_zona[(r["galpao_id"], r["zona"])].append(r)

    contagem = defaultdict(int)
    acima = confirmadas = sem_proxima = nao_confirmadas = 0
    for leituras in por_zona.values():
        leituras.sort(key=lambda x: x["ts_dt"])
        for i, r in enumerate(leituras):
            contagem[r["status"]] += 1
            if r["status"] == "ok":
                continue
            acima += 1
            prox = leituras[i + 1] if i + 1 < len(leituras) else None
            if prox is None or prox["ts_dt"] - r["ts_dt"] > janela:
                sem_proxima += 1
            elif prox["status"] != "ok":
                confirmadas += 1
            else:
                nao_confirmadas += 1

    print(f"Arquivo: {caminho}")
    print(f"Linhas lidas: {total}")
    print(f"  JSON invalido / campo faltando: {invalidas}")
    print(f"  temperatura nula (sensor parado): {temp_nula}")
    print(f"  temperatura fora da faixa: {temp_fora}")
    print(f"  CO2 nulo ou fora da faixa: {co2_fora}")
    print(f"  duplicadas: {duplicadas}")
    print(f"Leituras validas: {len(validas)}")
    print(f"  ok: {contagem['ok']} | atencao: {contagem['atencao']} | critico: {contagem['critico']}")
    print(f"Acima do limite (atencao ou critico): {acima}")
    print(f"  confirmadas na ronda seguinte: {confirmadas}")
    print(f"  NAO confirmadas (voltou ao normal): {nao_confirmadas}")
    print(f"  sem leitura seguinte na janela: {sem_proxima}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python src/analisar_amostra.py <arquivo.json>")
        sys.exit(1)
    main(sys.argv[1])