import json
from datetime import datetime, timedelta

import pytest

from src.config import carregar_limites
from src.robo import ArquivoInvalido, processar_arquivo

INICIO = datetime(2026, 11, 4, 0, 5)


def leit(ronda, zona=3, temp=27.0, co2=1800, **kw):
    """Leitura da ronda N (uma ronda a cada 2 h). Idade 21 -> alvo 28.0 C."""
    r = {
        "ronda_id": f"R{ronda}", "galpao_id": "G-SDE-01", "lote_id": "G-SDE-01-L01",
        "idade_lote_dias": 21, "zona": zona,
        "ts": (INICIO + timedelta(hours=2 * ronda)).isoformat(timespec="seconds"),
        "temp_c": temp, "umid_pct": 70.0, "co2_ppm": co2, "nh3_ppm": None,
        "sensor": "SCD40", "origem": "simulado",
    }
    r.update(kw)
    return r


def escrever(tmp_path, leituras, extra=""):
    arq = tmp_path / "carrinho_teste.json"
    arq.write_text("\n".join(json.dumps(l) for l in leituras) + "\n" + extra, encoding="utf-8")
    return arq


@pytest.fixture
def cfg():
    return carregar_limites()


# ---- arquivo invalido ----
def test_arquivo_inexistente(tmp_path, cfg):
    with pytest.raises(ArquivoInvalido):
        processar_arquivo(tmp_path / "nao_existe.json", cfg)


def test_arquivo_vazio(tmp_path, cfg):
    arq = tmp_path / "vazio.json"
    arq.write_text("", encoding="utf-8")
    with pytest.raises(ArquivoInvalido):
        processar_arquivo(arq, cfg)


def test_arquivo_sem_json_valido(tmp_path, cfg):
    arq = tmp_path / "lixo.json"
    arq.write_text("isto nao e json\nnem isto\n", encoding="utf-8")
    with pytest.raises(ArquivoInvalido):
        processar_arquivo(arq, cfg)


# ---- excecoes por linha ----
def test_linha_quebrada_e_ignorada(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0), leit(1)], extra="{linha quebrada\n")
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["linhas_json_invalido"] == 1
    assert res["resumo"]["leituras_validas"] == 2


def test_duplicada_e_descartada(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0), leit(0), leit(1)])
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["descartes"] == {"duplicada": 1}
    assert res["resumo"]["leituras_validas"] == 2


def test_sensor_parado_registrado(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0), leit(1, temp=None)])
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["falhas_sensor"] == 1
    assert res["falhas_sensor"][0]["zona"] == 3


def test_valor_absurdo_descartado(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0, temp=99.0), leit(1, co2=99999), leit(2)])
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["descartes"] == {
        "temperatura_fora_da_faixa": 1, "co2_fora_da_faixa": 1,
    }
    assert res["resumo"]["alertas"] == 0


# ---- decisao e confirmacao ----
def test_tudo_normal(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(i) for i in range(6)])
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["alertas"] == 0 and res["resumo"]["observacoes"] == 0
    assert res["zonas"]["G-SDE-01-Z3"]["estado_final"] == "normal"


def test_pico_isolado_vira_observacao(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0), leit(1, temp=30.0), leit(2), leit(3)])
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["alertas"] == 0
    assert res["resumo"]["observacoes"] == 1
    assert res["zonas"]["G-SDE-01-Z3"]["estado_final"] == "normal"


def test_duas_leituras_seguidas_geram_um_alerta(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0), leit(1, temp=30.0), leit(2, temp=30.5), leit(3)])
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["alertas"] == 1
    assert res["alertas"][0]["leituras_acima_do_limite"] == 2


def test_episodio_longo_gera_um_unico_alerta(tmp_path, cfg):
    leituras = [leit(0)] + [leit(i, temp=30.0) for i in range(1, 6)] + [leit(6)]
    res = processar_arquivo(escrever(tmp_path, leituras), cfg)
    assert res["resumo"]["alertas"] == 1
    assert res["alertas"][0]["leituras_acima_do_limite"] == 5


def test_severidade_do_alerta_e_a_pior_do_episodio(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0, temp=30.0), leit(1, temp=31.5), leit(2)])
    res = processar_arquivo(arq, cfg)
    assert res["alertas"][0]["severidade"] == "critico"


def test_leitura_seguinte_fora_da_janela_nao_confirma(tmp_path, cfg):
    # ronda 1 e ronda 4 acima do limite, sem leitura valida no meio
    arq = escrever(tmp_path, [leit(1, temp=30.0), leit(4, temp=30.0)])
    res = processar_arquivo(arq, cfg)
    assert res["resumo"]["alertas"] == 0 and res["resumo"]["observacoes"] == 2


def test_estado_final_alerta_quando_episodio_continua(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0), leit(1, temp=30.0), leit(2, temp=30.0)])
    res = processar_arquivo(arq, cfg)
    assert res["zonas"]["G-SDE-01-Z3"]["estado_final"] == "alerta"


def test_estado_final_observacao_quando_ultima_leitura_e_isolada(tmp_path, cfg):
    arq = escrever(tmp_path, [leit(0), leit(1), leit(2, temp=30.0)])
    res = processar_arquivo(arq, cfg)
    assert res["zonas"]["G-SDE-01-Z3"]["estado_final"] == "observacao"


def test_zonas_sao_independentes(tmp_path, cfg):
    leituras = [leit(0, zona=1), leit(1, zona=1, temp=30.0),
                leit(0, zona=2), leit(1, zona=2, temp=30.0), leit(2, zona=2, temp=30.0)]
    res = processar_arquivo(escrever(tmp_path, leituras), cfg)
    assert res["resumo"]["alertas"] == 1 and res["alertas"][0]["zona"] == 2
    assert res["resumo"]["observacoes"] == 1