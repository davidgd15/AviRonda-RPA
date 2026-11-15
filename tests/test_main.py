import json
import logging
from datetime import datetime, timedelta

import pytest

from src import main as main_mod
from src.log import configurar_log
from src.main import executar

INICIO = datetime(2026, 11, 4, 0, 5)


def leit(ronda, zona=3, temp=27.0):
    return {
        "ronda_id": f"R{ronda}", "galpao_id": "G-SDE-01", "lote_id": "G-SDE-01-L01",
        "idade_lote_dias": 21, "zona": zona,
        "ts": (INICIO + timedelta(hours=2 * ronda)).isoformat(timespec="seconds"),
        "temp_c": temp, "umid_pct": 70.0, "co2_ppm": 1800, "nh3_ppm": None,
        "sensor": "SCD40", "origem": "simulado",
    }


def arquivo_bom(pasta, nome="carrinho_ok.json"):
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / nome
    arq.write_text("\n".join(json.dumps(leit(i)) for i in range(4)) + "\n", encoding="utf-8")
    return arq


@pytest.fixture
def pastas(tmp_path):
    return {
        "pasta_entrada": tmp_path / "entrada",
        "pasta_processados": tmp_path / "processados",
        "pasta_erros": tmp_path / "erros",
    }


@pytest.fixture(autouse=True)
def limpar_log():
    yield
    logger = logging.getLogger("avironda")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()


def test_pasta_vazia_nao_falha(pastas):
    saida = executar(**pastas)
    assert saida == {"resultados": [], "erros": []}
    assert pastas["pasta_entrada"].exists()


def test_arquivo_bom_vai_para_processados(pastas):
    arquivo_bom(pastas["pasta_entrada"])
    saida = executar(**pastas)
    assert len(saida["resultados"]) == 1 and saida["erros"] == []
    assert not list(pastas["pasta_entrada"].glob("*.json"))
    assert (pastas["pasta_processados"] / "carrinho_ok.json").exists()


def test_arquivo_invalido_vai_para_erros_e_nao_para_os_demais(pastas):
    arquivo_bom(pastas["pasta_entrada"], "a_bom.json")
    (pastas["pasta_entrada"] / "b_vazio.json").write_text("", encoding="utf-8")
    arquivo_bom(pastas["pasta_entrada"], "c_bom.json")
    saida = executar(**pastas)
    assert len(saida["resultados"]) == 2
    assert [e["arquivo"] for e in saida["erros"]] == ["b_vazio.json"]
    assert saida["erros"][0]["tipo"] == "erro_arquivo"
    assert (pastas["pasta_erros"] / "b_vazio.json").exists()


def test_erro_nao_expoe_caminho_completo(pastas):
    pastas["pasta_entrada"].mkdir(parents=True)
    (pastas["pasta_entrada"] / "vazio.json").write_text("", encoding="utf-8")
    saida = executar(**pastas)
    assert "\\" not in saida["erros"][0]["motivo"] and "/" not in saida["erros"][0]["motivo"]


def test_nome_repetido_nao_sobrescreve(pastas):
    arquivo_bom(pastas["pasta_entrada"])
    executar(**pastas)
    arquivo_bom(pastas["pasta_entrada"])  # mesmo nome de novo
    executar(**pastas)
    assert len(list(pastas["pasta_processados"].glob("*.json"))) == 2


def test_falha_inesperada_e_registrada_e_arquivo_vai_para_erros(pastas, monkeypatch):
    arquivo_bom(pastas["pasta_entrada"])

    def quebrado(caminho, cfg):
        raise RuntimeError("bug simulado")

    monkeypatch.setattr(main_mod, "processar_arquivo", quebrado)
    saida = executar(**pastas)
    assert saida["resultados"] == []
    assert saida["erros"][0]["motivo"] == "falha inesperada (RuntimeError)"
    assert (pastas["pasta_erros"] / "carrinho_ok.json").exists()


def test_log_grava_em_arquivo(tmp_path):
    arquivo = configurar_log(tmp_path / "logs")
    logging.getLogger("avironda").info("mensagem de teste")
    conteudo = arquivo.read_text(encoding="utf-8")
    assert "mensagem de teste" in conteudo and "INFO" in conteudo


def test_log_nao_duplica_linhas_ao_ser_configurado_duas_vezes(tmp_path):
    configurar_log(tmp_path / "logs")
    arquivo = configurar_log(tmp_path / "logs")
    logging.getLogger("avironda").info("uma vez so")
    assert arquivo.read_text(encoding="utf-8").count("uma vez so") == 1