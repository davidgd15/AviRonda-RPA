"""Saidas do robo: alertas.json (Power Automate e MVP), CSV e paginas HTML.

Cada saida e gravada de forma independente: se uma falhar (por exemplo, o CSV
aberto no Excel), as outras continuam e a falha fica registrada no log.
"""
import csv
import html
import json
import logging
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from src.config import RAIZ
from src.regras import SEVERIDADE

log = logging.getLogger("avironda")

POSICOES = {1: "entrada de ar", 2: "meio", 3: "meio", 4: "meio", 5: "meio", 6: "exaustor"}
ROTULO = {"critico": "crítico", "atencao": "atenção", "observacao": "observação", "normal": "normal"}
CAMPOS_CSV = [
    "galpao_id", "zona", "ts", "lote_id", "idade_lote_dias", "temp_c", "umid_pct",
    "co2_ppm", "status", "temp_alvo_c", "desvio_c", "arquivo_origem",
]
esc = html.escape


def _hora(ts):
    return ts[11:16] if ts and len(ts) >= 16 else "-"


# --------------------------------------------------------------------------
# Avisos (um e-mail por galpao, um por falha de sensor, um por arquivo invalido)
# --------------------------------------------------------------------------
def _tabela(cabecalho, linhas):
    cab = "".join(f"<th>{c}</th>" for c in cabecalho)
    corpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in linha) + "</tr>" for linha in linhas)
    return (f'<table border="1" cellpadding="6" cellspacing="0" '
            f'style="border-collapse:collapse"><tr>{cab}</tr>{corpo}</table>')


_RODAPE = "<p><small>Mensagem automática do robô AviRonda (dados simulados na demonstração).</small></p>"


def _aviso_alerta(galpao, data, arquivo, alertas):
    alertas = sorted(alertas, key=lambda a: (a["zona"], a["inicio"]))
    zonas = sorted({a["zona"] for a in alertas})  # uma zona pode ter mais de um episodio
    severidade = max((a["severidade"] for a in alertas), key=lambda s: SEVERIDADE[s])
    linhas = [
        [f"Zona {a['zona']} ({POSICOES.get(a['zona'], '-')})", ROTULO[a["severidade"]],
         f"{_hora(a['inicio'])} a {_hora(a['fim'])}",
         f"{a['temp_max_c']} °C (alvo {a['temp_alvo_c']} °C)", f"{a['co2_max_ppm']} ppm"]
        for a in alertas
    ]
    corpo = (
        f"<p>O robô AviRonda confirmou alerta no galpão <b>{esc(str(galpao))}</b> em {esc(data)}.</p>"
        + _tabela(["Zona", "Severidade", "Horário", "Temperatura máxima", "CO₂ máximo"], linhas)
        + "<p>Alerta confirmado = duas rondas seguidas acima do limite na mesma zona. "
          "Confira as zonas listadas.</p>" + _RODAPE
    )
    return {
        "id": f"zona_em_alerta-{galpao}-{data}",
        "tipo": "zona_em_alerta", "severidade": severidade,
        "galpao_id": galpao, "data": data, "arquivo": arquivo,
        "zonas": zonas,
        "assunto": f"[AviRonda] {galpao}: {len(zonas)} zona(s) em alerta ({ROTULO[severidade]}) - {data}",
        "corpo_html": corpo,
    }


def _aviso_sensor(galpao, data, arquivo, falhas):
    por_zona = defaultdict(list)
    for f in falhas:
        por_zona[f.get("zona")].append(f.get("ts"))
    linhas = [
        [f"Zona {z}", str(len(ts)), ", ".join(_hora(t) for t in sorted(t for t in ts if t))]
        for z, ts in sorted(por_zona.items(), key=lambda kv: str(kv[0]))
    ]
    corpo = (
        f"<p>O galpão <b>{esc(str(galpao))}</b> teve leituras sem dados em {esc(data)}. "
        "Verifique o sensor do carrinho nas zonas abaixo.</p>"
        + _tabela(["Zona", "Leituras sem dados", "Horários"], linhas) + _RODAPE
    )
    return {
        "id": f"falha_sensor-{galpao}-{data}",
        "tipo": "falha_sensor", "severidade": "aviso",
        "galpao_id": galpao, "data": data, "arquivo": arquivo,
        "zonas": sorted(z for z in por_zona if z is not None),
        "assunto": f"[AviRonda] {galpao}: falha de sensor em {len(por_zona)} zona(s) - {data}",
        "corpo_html": corpo,
    }


def _aviso_erro(erro):
    nome = erro.get("arquivo", "?")
    corpo = (f"<p>O robô AviRonda não conseguiu processar o arquivo <b>{esc(nome)}</b>.</p>"
             f"<p>Motivo: {esc(erro.get('motivo', '-'))}.</p>"
             "<p>O arquivo foi movido para a pasta de erros.</p>" + _RODAPE)
    return {
        "id": f"erro_arquivo-{nome}",
        "tipo": "erro_arquivo", "severidade": "erro",
        "galpao_id": None, "data": None, "arquivo": nome, "zonas": [],
        "assunto": f"[AviRonda] Arquivo inválido: {nome}",
        "corpo_html": corpo,
    }


def montar_avisos(resultados, erros):
    avisos = []
    for res in resultados:
        data = res.get("data_referencia") or "sem data"
        alertas = defaultdict(list)
        for a in res["alertas"]:
            alertas[a["galpao_id"]].append(a)
        for galpao, lista in sorted(alertas.items()):
            avisos.append(_aviso_alerta(galpao, data, res["arquivo"], lista))
        sensores = defaultdict(list)
        for f in res["falhas_sensor"]:
            sensores[f.get("galpao_id")].append(f)
        for galpao, lista in sorted(sensores.items(), key=lambda kv: str(kv[0])):
            avisos.append(_aviso_sensor(galpao, data, res["arquivo"], lista))
    for erro in erros:
        avisos.append(_aviso_erro(erro))
    return avisos


def montar_documento(saida, agora):
    """Monta o conteudo de alertas.json. Os 'avisos' sao o que o Power Automate envia."""
    resultados, erros = saida["resultados"], saida["erros"]
    avisos = montar_avisos(resultados, erros)
    return {
        "versao": 1,
        "gerado_em": agora.isoformat(timespec="seconds"),
        "resumo": {
            "arquivos_processados": len(resultados),
            "arquivos_com_erro": len(erros),
            "avisos": len(avisos),
            "alertas": sum(r["resumo"]["alertas"] for r in resultados),
            "observacoes": sum(r["resumo"]["observacoes"] for r in resultados),
            "falhas_sensor": sum(r["resumo"]["falhas_sensor"] for r in resultados),
        },
        "avisos": avisos,
        "arquivos": [
            {
                "arquivo": r["arquivo"], "data_referencia": r.get("data_referencia"),
                "resumo": r["resumo"], "alertas": r["alertas"],
                "observacoes": r["observacoes"], "falhas_sensor": r["falhas_sensor"],
                "zonas": r["zonas"],
            }
            for r in resultados
        ],
        "erros_arquivo": erros,
    }


# --------------------------------------------------------------------------
# CSV cumulativo (rodar de novo nao duplica: a chave e galpao + zona + ts)
# --------------------------------------------------------------------------
def gravar_csv(resultados, caminho):
    caminho = Path(caminho)
    existentes = {}
    if caminho.exists():
        try:
            with open(caminho, newline="", encoding="utf-8") as f:
                for linha in csv.DictReader(f):
                    existentes[(linha["galpao_id"], linha["zona"], linha["ts"])] = linha
        except (KeyError, csv.Error, UnicodeDecodeError):
            log.warning("csv anterior ilegivel, sera recriado")
            existentes = {}
    for res in resultados:
        for leitura in res["leituras"]:
            linha = {**leitura, "arquivo_origem": res["arquivo"]}
            linha = {k: ("" if v is None else v) for k, v in linha.items()}
            existentes[(str(leitura["galpao_id"]), str(leitura["zona"]), leitura["ts"])] = linha
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        escritor.writeheader()
        for chave in sorted(existentes, key=lambda k: (k[0], k[2], k[1])):
            escritor.writerow(existentes[chave])
    return len(existentes)


# --------------------------------------------------------------------------
# Paginas HTML (dashboard com atualizacao automatica e relatorio estatico)
# --------------------------------------------------------------------------
CSS = """
:root{--fundo:#f6f7f9;--texto:#1b1f24;--card:#fff;--borda:#c3c9d2;--critico:#b3261e;--atencao:#8a5a00;--obs:#0b57d0;--ok:#1b6e3c}
@media (prefers-color-scheme: dark){:root{--fundo:#12151a;--texto:#eef1f5;--card:#1c2128;--borda:#4a5361;--critico:#ff8a80;--atencao:#ffcc66;--obs:#8ab4ff;--ok:#7fd6a0}}
body{margin:0;font-family:system-ui,"Segoe UI",Arial,sans-serif;background:var(--fundo);color:var(--texto);line-height:1.5}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:1.5rem;margin:.2rem 0}h2{font-size:1.2rem;margin-top:2rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.kpi{background:var(--card);border:1px solid var(--borda);border-radius:10px;padding:12px}
.kpi b{display:block;font-size:1.8rem}
.zonas{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;list-style:none;padding:0}
.zona{background:var(--card);border:3px solid var(--borda);border-radius:10px;padding:10px}
.zona.critico{border-color:var(--critico)}.zona.atencao{border-color:var(--atencao)}
.zona.observacao{border-color:var(--obs)}.zona.normal{border-color:var(--ok)}
.estado{font-weight:700}
.estado.critico{color:var(--critico)}.estado.atencao{color:var(--atencao)}
.estado.observacao{color:var(--obs)}.estado.normal{color:var(--ok)}
.tabela{overflow-x:auto}
table{width:100%;border-collapse:collapse;background:var(--card)}
th,td{border:1px solid var(--borda);padding:6px 8px;text-align:left}
.erro{border:3px solid var(--critico);background:var(--card);border-radius:10px;padding:10px}
.rodape{margin-top:2rem;font-size:.9rem}
"""


def _estado_do_dia(res, galpao, zona):
    alertas = [a for a in res["alertas"] if a["galpao_id"] == galpao and a["zona"] == zona]
    if alertas:
        pior = max(alertas, key=lambda a: SEVERIDADE[a["severidade"]])
        return pior["severidade"], f"{_hora(alertas[0]['inicio'])} a {_hora(alertas[-1]['fim'])}"
    if any(o["galpao_id"] == galpao and o["zona"] == zona for o in res["observacoes"]):
        return "observacao", ""
    return "normal", ""


def _secao_arquivo(res):
    titulo = f"{esc(res.get('data_referencia') or 'sem data')} · {esc(res['arquivo'])}"
    cartoes = []
    for z in res["zonas"].values():
        estado, janela = _estado_do_dia(res, z["galpao_id"], z["zona"])
        detalhe = f"<br>Das {janela}" if janela else ""
        cartoes.append(
            f'<li class="zona {estado}"><b>{esc(str(z["galpao_id"]))} · zona {z["zona"]}</b><br>'
            f'{POSICOES.get(z["zona"], "-")}<br>'
            f'<span class="estado {estado}">{ROTULO[estado]}</span>{detalhe}</li>'
        )
    if res["alertas"]:
        linhas = "".join(
            f"<tr><td>{esc(str(a['galpao_id']))} · zona {a['zona']}</td>"
            f"<td>{ROTULO[a['severidade']]}</td>"
            f"<td>{_hora(a['inicio'])} a {_hora(a['fim'])}</td>"
            f"<td>{a['leituras_acima_do_limite']}</td>"
            f"<td>{a['temp_max_c']} °C (alvo {a['temp_alvo_c']} °C)</td>"
            f"<td>{a['co2_max_ppm']} ppm</td></tr>"
            for a in res["alertas"]
        )
        tabela = (
            '<div class="tabela"><table><caption>Alertas confirmados</caption><thead><tr>'
            '<th scope="col">Zona</th><th scope="col">Severidade</th><th scope="col">Horário</th>'
            '<th scope="col">Leituras acima do limite</th><th scope="col">Temperatura máxima</th>'
            '<th scope="col">CO₂ máximo</th></tr></thead><tbody>' + linhas + "</tbody></table></div>"
        )
    else:
        tabela = "<p>Nenhum alerta confirmado neste arquivo.</p>"
    return (f"<section><h2>{titulo}</h2><ul class=\"zonas\">{''.join(cartoes)}</ul>{tabela}</section>")


def renderizar_html(saida, agora, atualizar=True):
    resultados, erros = saida["resultados"], saida["erros"]
    refresh = '<meta http-equiv="refresh" content="60">' if atualizar else ""
    titulo = "AviRonda – Painel do robô" if atualizar else "AviRonda – Relatório diário do robô"
    kpis = [
        ("Arquivos processados", len(resultados)),
        ("Alertas confirmados", sum(r["resumo"]["alertas"] for r in resultados)),
        ("Observações", sum(r["resumo"]["observacoes"] for r in resultados)),
        ("Falhas de sensor", sum(r["resumo"]["falhas_sensor"] for r in resultados)),
        ("Arquivos com erro", len(erros)),
    ]
    kpi_html = "".join(f'<div class="kpi"><b>{n}</b>{rotulo}</div>' for rotulo, n in kpis)
    erros_html = ""
    if erros:
        itens = "".join(
            f"<li><b>{esc(e['arquivo'])}</b>: {esc(e['motivo'])}</li>" for e in erros
        )
        erros_html = f'<section class="erro"><h2>Arquivos com erro</h2><ul>{itens}</ul></section>'
    nota = ("Esta página se atualiza sozinha a cada 60 segundos. " if atualizar else "")
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{refresh}<title>{titulo}</title><style>{CSS}</style></head><body><main>"
        f"<h1>{titulo}</h1>"
        f"<p>Gerado em {agora.strftime('%d/%m/%Y %H:%M:%S')}. {nota}"
        "Zona normal, em observação ou em alerta confirmado.</p>"
        f'<div class="kpis" role="list">{kpi_html}</div>'
        + erros_html + "".join(_secao_arquivo(r) for r in resultados)
        + '<p class="rodape">Dados do carrinho simulados para a demonstração. '
          "Alerta confirmado = duas rondas seguidas acima do limite na mesma zona.</p>"
        "</main></body></html>"
    )


# --------------------------------------------------------------------------
# Gravacao (cada saida e independente das outras)
# --------------------------------------------------------------------------
def gravar_saidas(saida, pasta_saida=None, agora=None):
    """Grava todas as saidas. Devolve {'gravados': [...], 'falhas': [...]} ou None."""
    if not saida["resultados"] and not saida["erros"]:
        log.info("nada a gravar: nenhum arquivo processado")
        return None

    agora = agora or datetime.now()
    pasta = Path(pasta_saida) if pasta_saida else RAIZ / "saida"
    carimbo = agora.strftime("%Y%m%d_%H%M%S")
    gravados, falhas = [], []

    def tentar(nome, funcao):
        try:
            funcao()
            gravados.append(nome)
        except Exception as erro:  # uma saida com problema nao derruba as outras
            log.exception("nao foi possivel gravar %s", nome)
            falhas.append({"saida": nome, "motivo": type(erro).__name__})

    def gravar_alertas():
        documento = montar_documento(saida, agora)
        texto = json.dumps(documento, ensure_ascii=False, indent=2)
        (pasta / "alertas").mkdir(parents=True, exist_ok=True)
        # copia unica por execucao: e ela que dispara o Power Automate
        (pasta / "alertas" / f"alertas_{carimbo}.json").write_text(texto, encoding="utf-8")
        # copia "ultimo": caminho fixo para o MVP e para o painel
        (pasta / "alertas.json").write_text(texto, encoding="utf-8")
        log.info("alertas gravados: %d aviso(s)", documento["resumo"]["avisos"])

    def gravar_csv_saida():
        total = gravar_csv(saida["resultados"], pasta / "leituras_validas.csv")
        log.info("csv atualizado: %d leitura(s) no total", total)

    def gravar_paginas():
        (pasta / "dashboard.html").write_text(renderizar_html(saida, agora, True), encoding="utf-8")
        (pasta / "relatorio_diario.html").write_text(renderizar_html(saida, agora, False), encoding="utf-8")

    pasta.mkdir(parents=True, exist_ok=True)
    tentar("alertas.json", gravar_alertas)
    tentar("leituras_validas.csv", gravar_csv_saida)
    tentar("dashboard.html e relatorio_diario.html", gravar_paginas)
    log.info("saidas: %d gravada(s), %d com falha", len(gravados), len(falhas))
    return {"gravados": gravados, "falhas": falhas}