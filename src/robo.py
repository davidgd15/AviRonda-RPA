"""Robo AviRonda: le um arquivo de leituras, aplica as regras e devolve o resultado.

Segue o fluxograma docs/AviRonda_BPMN.png (raia "Robo Python").

Uso (na raiz do projeto, com a .venv ativa):
    python -m src.robo data/entrada/carrinho_G-SDE-01_2026-11-04.json
"""
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from src.config import carregar_limites
from src.regras import SEVERIDADE, classificar, validar_leitura

log = logging.getLogger("avironda")


class ArquivoInvalido(Exception):
    """Arquivo ausente, ilegivel, vazio ou sem nenhuma linha em JSON valido."""


# --------------------------------------------------------------------------
# Etapa 1 e 2 do fluxograma: "Arquivo existe e e valido?" e "Ler leituras"
# --------------------------------------------------------------------------
def ler_leituras(caminho):
    """Le o arquivo JSON Lines. Devolve (leituras, linhas_quebradas).

    Uma linha quebrada e ignorada (e registrada); o arquivo so e considerado
    invalido se nao existir, nao puder ser lido ou nao tiver nenhuma linha valida.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ArquivoInvalido(f"arquivo nao encontrado: {caminho}")

    leituras, quebradas = [], 0
    try:
        with open(caminho, encoding="utf-8") as f:
            for numero, linha in enumerate(f, start=1):
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    obj = json.loads(linha)
                    if not isinstance(obj, dict):
                        raise ValueError("a linha nao e um objeto JSON")
                except ValueError:
                    quebradas += 1
                    log.warning("linha %d ignorada: JSON invalido", numero)
                    continue
                obj["_linha"] = numero
                leituras.append(obj)
    except (OSError, UnicodeDecodeError) as erro:
        raise ArquivoInvalido(f"arquivo ilegivel: {caminho} ({erro})") from erro

    if not leituras:
        raise ArquivoInvalido(f"arquivo vazio ou sem JSON valido: {caminho}")
    return leituras, quebradas


# --------------------------------------------------------------------------
# Funcoes auxiliares: agrupar leituras acima do limite e montar eventos
# --------------------------------------------------------------------------
def _corridas_acima_do_limite(leituras, janela):
    """Agrupa leituras consecutivas da mesma zona que estao acima do limite.

    Duas leituras acima do limite so ficam na mesma corrida se a diferenca de
    horario for de no maximo `janela`. Uma leitura normal encerra a corrida.
    """
    corridas, atual = [], []
    for r in leituras:
        acima = r["_class"]["status"] != "ok"
        if acima and atual and r["_ts"] - atual[-1]["_ts"] <= janela:
            atual.append(r)
        elif acima:
            if atual:
                corridas.append(atual)
            atual = [r]
        else:
            if atual:
                corridas.append(atual)
            atual = []
    if atual:
        corridas.append(atual)
    return corridas


def _montar_alerta(galpao, zona, corrida):
    pior = max(corrida, key=lambda r: SEVERIDADE[r["_class"]["status"]])
    return {
        "tipo": "zona_em_alerta",
        "severidade": pior["_class"]["status"],
        "galpao_id": galpao,
        "zona": zona,
        "lote_id": corrida[0].get("lote_id"),
        "idade_lote_dias": corrida[0]["idade_lote_dias"],
        "inicio": corrida[0]["ts"],
        "fim": corrida[-1]["ts"],
        "leituras_acima_do_limite": len(corrida),
        "motivos": sorted({m for r in corrida for m in r["_class"]["motivos"]}),
        "temp_max_c": max(r["temp_c"] for r in corrida),
        "co2_max_ppm": max(r["co2_ppm"] for r in corrida),
        "temp_alvo_c": corrida[0]["_class"]["temp_alvo_c"],
    }


def _montar_observacao(galpao, zona, r):
    return {
        "tipo": "observacao",
        "severidade": r["_class"]["status"],
        "galpao_id": galpao,
        "zona": zona,
        "ts": r["ts"],
        "temp_c": r["temp_c"],
        "co2_ppm": r["co2_ppm"],
        "motivos": r["_class"]["motivos"],
    }


# --------------------------------------------------------------------------
# Etapas 3 a 8 do fluxograma: loop, validacao, decisao, confirmacao, consolidacao
# --------------------------------------------------------------------------
def processar_leituras(brutas, cfg):
    janela = timedelta(minutes=cfg["janela_confirmacao_min"])
    descartes = Counter()
    descartadas, falhas_sensor = [], []
    vistos = set()
    validas = []

    for r in brutas:  # "Para cada leitura"
        ok, motivo = validar_leitura(r, cfg)  # "Sensor enviou leitura?" e "Leitura plausivel?"
        if ok:
            try:
                r["_ts"] = datetime.fromisoformat(r["ts"])
            except (TypeError, ValueError):
                ok, motivo = False, "campo_invalido"

        if not ok:
            evento = {
                "linha": r.get("_linha"), "motivo": motivo,
                "galpao_id": r.get("galpao_id"), "zona": r.get("zona"), "ts": r.get("ts"),
            }
            descartes[motivo] += 1
            descartadas.append(evento)
            if motivo == "sensor_parado":
                falhas_sensor.append(evento)
            log.warning("leitura descartada (%s): galpao=%s zona=%s ts=%s",
                        motivo, evento["galpao_id"], evento["zona"], evento["ts"])
            continue

        chave = (r["galpao_id"], r["zona"], r["ts"])  # "...e nao duplicada?"
        if chave in vistos:
            descartes["duplicada"] += 1
            descartadas.append({
                "linha": r.get("_linha"), "motivo": "duplicada",
                "galpao_id": r["galpao_id"], "zona": r["zona"], "ts": r["ts"],
            })
            log.warning("leitura descartada (duplicada): galpao=%s zona=%s ts=%s",
                        r["galpao_id"], r["zona"], r["ts"])
            continue
        vistos.add(chave)

        r["_class"] = classificar(r, cfg)  # "Calcular ... / Acima do limite?"
        validas.append(r)

    # Confirmacao: "Localizar proxima leitura do mesmo ponto" (feita por zona, apos o loop,
    # porque precisa olhar a leitura seguinte)
    por_zona = defaultdict(list)
    for r in validas:
        por_zona[(r["galpao_id"], r["zona"])].append(r)

    alertas, observacoes, zonas = [], [], {}
    for (galpao, zona), leituras in sorted(por_zona.items()):
        leituras.sort(key=lambda x: x["_ts"])
        corridas = _corridas_acima_do_limite(leituras, janela)

        for corrida in corridas:
            if len(corrida) >= 2:  # confirmada pela leitura seguinte -> alerta
                alertas.append(_montar_alerta(galpao, zona, corrida))
            else:  # acima do limite, mas sem confirmacao -> observacao
                observacoes.append(_montar_observacao(galpao, zona, corrida[0]))
                log.info("observacao: galpao=%s zona=%s ts=%s", galpao, zona, corrida[0]["ts"])

        # "Consolidar por zona": estado ao fim do arquivo
        if corridas and corridas[-1][-1] is leituras[-1]:
            estado = "alerta" if len(corridas[-1]) >= 2 else "observacao"
        else:
            estado = "normal"
        contagem = Counter(r["_class"]["status"] for r in leituras)
        zonas[f"{galpao}-Z{zona}"] = {
            "galpao_id": galpao, "zona": zona, "estado_final": estado,
            "leituras": len(leituras),
            "ok": contagem["ok"], "atencao": contagem["atencao"], "critico": contagem["critico"],
        }

    contagem_total = Counter(r["_class"]["status"] for r in validas)
    resumo = {
        "descartes": dict(descartes),
        "leituras_validas": len(validas),
        "ok": contagem_total["ok"],
        "atencao": contagem_total["atencao"],
        "critico": contagem_total["critico"],
        "alertas": len(alertas),
        "observacoes": len(observacoes),
        "falhas_sensor": len(falhas_sensor),
    }
    return {
        "resumo": resumo,
        "alertas": alertas,
        "observacoes": observacoes,
        "falhas_sensor": falhas_sensor,
        "descartadas": descartadas,
        "zonas": zonas,
    }


def processar_arquivo(caminho, cfg=None):
    """Executa o processo inteiro para um arquivo. Levanta ArquivoInvalido se for o caso."""
    cfg = cfg or carregar_limites()
    log.info("processando %s", caminho)
    brutas, quebradas = ler_leituras(caminho)
    resultado = processar_leituras(brutas, cfg)
    resultado["arquivo"] = str(caminho)
    resultado["resumo"]["linhas_json_invalido"] = quebradas
    resultado["resumo"]["linhas_lidas"] = len(brutas) + quebradas
    log.info("resumo: %s", resultado["resumo"])
    return resultado


# --------------------------------------------------------------------------
# Execucao pelo terminal
# --------------------------------------------------------------------------
def imprimir_resumo(res):
    r = res["resumo"]
    print(f"Arquivo: {res['arquivo']}")
    print(f"Linhas lidas: {r['linhas_lidas']} (JSON invalido: {r['linhas_json_invalido']})")
    print(f"Descartes: {r['descartes'] or 'nenhum'}")
    print(f"Leituras validas: {r['leituras_validas']} -> ok {r['ok']} | "
          f"atencao {r['atencao']} | critico {r['critico']}")
    print(f"Alertas (confirmados): {r['alertas']} | Observacoes (sem confirmacao): "
          f"{r['observacoes']} | Falhas de sensor: {r['falhas_sensor']}")
    print("Zonas (estado ao fim do arquivo):")
    for nome, z in res["zonas"].items():
        print(f"  {nome}: {z['estado_final']} | leituras {z['leituras']} "
              f"(ok {z['ok']}, atencao {z['atencao']}, critico {z['critico']})")
    if res["alertas"]:
        print("Alertas:")
        for a in res["alertas"]:
            print(f"  [{a['severidade']}] {a['galpao_id']} zona {a['zona']} | "
                  f"{a['inicio']} -> {a['fim']} | {a['leituras_acima_do_limite']} leituras | "
                  f"temp max {a['temp_max_c']} | co2 max {a['co2_max_ppm']} | "
                  f"motivos: {', '.join(a['motivos'])}")


def main(argv):
    if len(argv) != 2:
        print("Uso: python -m src.robo <arquivo.json>")
        return 1
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        resultado = processar_arquivo(argv[1])
    except ArquivoInvalido as erro:
        print(f"ARQUIVO INVALIDO: {erro}")
        return 2
    imprimir_resumo(resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))