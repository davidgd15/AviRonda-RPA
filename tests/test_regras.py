import pytest

from src.config import carregar_limites
from src.regras import classificar, temperatura_alvo, validar_leitura


@pytest.fixture
def cfg():
    return carregar_limites()


def leitura(**kw):
    base = {
        "galpao_id": "G-SDE-01", "zona": 3, "ts": "2026-11-04T10:00:00",
        "idade_lote_dias": 21, "temp_c": 27.0, "co2_ppm": 1800,
    }
    base.update(kw)
    return base


# ---- temperatura-alvo por idade ----
def test_alvo_dia_1(cfg):
    assert temperatura_alvo(1, cfg) == 32.0


def test_alvo_dia_21(cfg):
    assert temperatura_alvo(21, cfg) == pytest.approx(28.0)


def test_alvo_nunca_abaixo_do_minimo(cfg):
    assert temperatura_alvo(60, cfg) == 23.0


# ---- validacao (fluxo: sensor enviou? plausivel?) ----
def test_leitura_valida(cfg):
    assert validar_leitura(leitura(), cfg) == (True, None)


def test_sensor_parado_temperatura_nula(cfg):
    assert validar_leitura(leitura(temp_c=None), cfg) == (False, "sensor_parado")


def test_sensor_parado_co2_nulo(cfg):
    assert validar_leitura(leitura(co2_ppm=None), cfg) == (False, "sensor_parado")


def test_temperatura_absurda(cfg):
    assert validar_leitura(leitura(temp_c=99.0), cfg) == (False, "temperatura_fora_da_faixa")


def test_co2_absurdo(cfg):
    assert validar_leitura(leitura(co2_ppm=99999), cfg) == (False, "co2_fora_da_faixa")


def test_campo_obrigatorio_ausente(cfg):
    l = leitura()
    del l["zona"]
    assert validar_leitura(l, cfg) == (False, "campo_invalido")


def test_tipo_invalido(cfg):
    assert validar_leitura(leitura(temp_c="quente"), cfg) == (False, "campo_invalido")


# ---- classificacao (decisao) ----
def test_ok_dentro_do_alvo(cfg):
    assert classificar(leitura(temp_c=28.0), cfg)["status"] == "ok"


def test_ok_no_limite_exato_da_atencao(cfg):
    # alvo 28.0 + 1.5 = 29.5: so passa se for MAIOR
    assert classificar(leitura(temp_c=29.5), cfg)["status"] == "ok"


def test_atencao_por_temperatura(cfg):
    r = classificar(leitura(temp_c=30.0), cfg)
    assert r["status"] == "atencao" and r["motivos"] == ["temperatura"]


def test_critico_por_temperatura(cfg):
    r = classificar(leitura(temp_c=31.5), cfg)
    assert r["status"] == "critico" and r["desvio_c"] == 3.5


def test_atencao_por_co2(cfg):
    r = classificar(leitura(co2_ppm=2600), cfg)
    assert r["status"] == "atencao" and r["motivos"] == ["co2"]


def test_critico_por_co2(cfg):
    assert classificar(leitura(co2_ppm=3100), cfg)["status"] == "critico"


def test_pior_severidade_vence(cfg):
    r = classificar(leitura(temp_c=30.0, co2_ppm=3200), cfg)
    assert r["status"] == "critico" and r["motivos"] == ["temperatura", "co2"]