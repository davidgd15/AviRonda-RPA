import csv
import json
from datetime import datetime, timedelta
from html.parser import HTMLParser

import pytest

from src.config import carregar_limites
from src.robo import processar_arquivo
from src.saidas import gravar_csv, gravar_saidas, montar_avisos, montar_documento, renderizar_html

INICIO = datetime(2026, 11, 4, 0, 5)
AGORA = datetime(2026, 11, 15, 16, 41, 39)


def leit(ronda, zona=3, temp=27.0, **kw):
    r = {
        "ronda_id": f"R{ronda}", "galpao_id": "G-SDE-01", "lote_id": "G-SDE-01-L01",
        "idade_lote_dias": 21, "zona": zona,
        "ts": (INICIO + timedelta(hours=2 * ronda)).isoformat(timespec="seconds"),
        "temp_c": temp, "umid_pct": 70.0, "co2_ppm": 1800, "nh3_ppm": None,
        "sensor": "SCD40", "origem": "simulado",
    }
    r.update(kw)
    return r


def processar(tmp_path, leituras, nome="carrinho_teste.json"):
    arq = tmp_path / nome
    arq.write_text("\n".join(json.dumps(l) for l in leituras) + "\n", encoding="utf-8")
    return processar_arquivo(arq, carregar_limites())


def dois_alertas():
    return [leit(0, 1), leit(1, 1, temp=30.0), leit(2, 1, temp=30.0),
            leit(0, 2), leit(1, 2, temp=31.5), leit(2, 2, temp=31.5)]


# ---- avisos ----
def test_um_aviso_por_galpao_agrupando_zonas(tmp_path):
    res = processar(tmp_path, dois_alertas())
    avisos = montar_avisos([res], [])
    assert len(avisos) == 1
    a = avisos[0]
    assert a["tipo"] == "zona_em_alerta" and a["zonas"] == [1, 2]
    assert a["severidade"] == "critico"
    assert "G-SDE-01" in a["assunto"] and "2 zona(s)" in a["assunto"] and "2026-11-04" in a["assunto"]
    assert "Zona 1" in a["corpo_html"] and "Zona 2" in a["corpo_html"]


def test_zona_com_dois_episodios_conta_uma_vez(tmp_path):
    # zona 3: acima nas rondas 1-2, normal na 3, acima de novo nas rondas 5-6
    leituras = [leit(0), leit(1, temp=30.0), leit(2, temp=30.0), leit(3),
                leit(4), leit(5, temp=30.0), leit(6, temp=30.0), leit(7)]
    res = processar(tmp_path, leituras)
    assert res["resumo"]["alertas"] == 2
    aviso = montar_avisos([res], [])[0]
    assert aviso["zonas"] == [3] and "1 zona(s)" in aviso["assunto"]


def test_sem_alerta_nao_gera_aviso(tmp_path):
    res = processar(tmp_path, [leit(i) for i in range(4)])
    assert montar_avisos([res], []) == []


def test_aviso_de_falha_de_sensor(tmp_path):
    res = processar(tmp_path, [leit(0), leit(1, temp=None), leit(2, zona=5, temp=None)])
    avisos = montar_avisos([res], [])
    assert [a["tipo"] for a in avisos] == ["falha_sensor"]
    assert avisos[0]["zonas"] == [3, 5]


def test_aviso_de_arquivo_invalido():
    erro = {"tipo": "erro_arquivo", "arquivo": "x.json", "motivo": "arquivo vazio ou sem JSON valido: x.json"}
    avisos = montar_avisos([], [erro])
    assert avisos[0]["tipo"] == "erro_arquivo" and "x.json" in avisos[0]["assunto"]


def test_documento_e_serializavel_e_tem_contrato(tmp_path):
    res = processar(tmp_path, dois_alertas())
    doc = montar_documento({"resultados": [res], "erros": []}, AGORA)
    texto = json.dumps(doc, ensure_ascii=False)
    lido = json.loads(texto)
    assert lido["versao"] == 1 and lido["gerado_em"] == "2026-11-15T16:41:39"
    assert lido["resumo"]["avisos"] == 1 and lido["resumo"]["alertas"] == 2
    assert lido["avisos"][0]["assunto"] and lido["avisos"][0]["corpo_html"]


# ---- csv ----
def test_csv_cumulativo_nao_duplica(tmp_path):
    res = processar(tmp_path, dois_alertas())
    caminho = tmp_path / "leituras.csv"
    assert gravar_csv([res], caminho) == 6
    assert gravar_csv([res], caminho) == 6  # rodar de novo nao muda nada
    with open(caminho, newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert len(linhas) == 6 and linhas[0]["arquivo_origem"] == "carrinho_teste.json"


def test_csv_ilegivel_e_recriado(tmp_path):
    res = processar(tmp_path, dois_alertas())
    caminho = tmp_path / "leituras.csv"
    caminho.write_text("coluna_errada\nxxx\n", encoding="utf-8")
    assert gravar_csv([res], caminho) == 6


# ---- html ----
class _Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_dashboard_atualiza_sozinho_e_relatorio_nao(tmp_path):
    res = processar(tmp_path, dois_alertas())
    saida = {"resultados": [res], "erros": []}
    painel = renderizar_html(saida, AGORA, True)
    relatorio = renderizar_html(saida, AGORA, False)
    assert 'http-equiv="refresh"' in painel and 'http-equiv="refresh"' not in relatorio
    assert 'lang="pt-BR"' in painel and "crítico" in painel
    parser = _Parser()
    parser.feed(painel)
    assert any(t == "table" for t, _ in parser.tags)


def test_html_escapa_conteudo_perigoso():
    erro = {"tipo": "erro_arquivo", "arquivo": "<script>alert(1)</script>.json", "motivo": "x"}
    pagina = renderizar_html({"resultados": [], "erros": [erro]}, AGORA, True)
    assert "<script>" not in pagina and "&lt;script&gt;" in pagina


# ---- gravacao ----
def test_gravar_saidas_cria_todos_os_arquivos(tmp_path):
    res = processar(tmp_path, dois_alertas())
    pasta = tmp_path / "saida"
    resultado = gravar_saidas({"resultados": [res], "erros": []}, pasta, AGORA)
    assert resultado["falhas"] == []
    assert (pasta / "alertas.json").exists()
    assert (pasta / "alertas" / "alertas_20261115_164139.json").exists()
    assert (pasta / "leituras_validas.csv").exists()
    assert (pasta / "dashboard.html").exists() and (pasta / "relatorio_diario.html").exists()
    doc = json.loads((pasta / "alertas.json").read_text(encoding="utf-8"))
    assert doc["resumo"]["avisos"] == 1


def test_nada_a_gravar_quando_nao_ha_arquivos(tmp_path):
    pasta = tmp_path / "saida"
    assert gravar_saidas({"resultados": [], "erros": []}, pasta, AGORA) is None
    assert not pasta.exists()


def test_falha_em_uma_saida_nao_derruba_as_outras(tmp_path):
    res = processar(tmp_path, dois_alertas())
    pasta = tmp_path / "saida"
    pasta.mkdir()
    (pasta / "leituras_validas.csv").mkdir()  # impede gravar o CSV (arquivo e uma pasta)
    resultado = gravar_saidas({"resultados": [res], "erros": []}, pasta, AGORA)
    assert [f["saida"] for f in resultado["falhas"]] == ["leituras_validas.csv"]
    assert (pasta / "alertas.json").exists() and (pasta / "dashboard.html").exists()