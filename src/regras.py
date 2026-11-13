"""Regras de negocio do robo AviRonda.

Sao funcoes simples, sem ler arquivos: recebem uma leitura (dict) e a
configuracao de limites (dict) e devolvem uma resposta. Assim ficam faceis
de testar e de explicar no relatorio.
"""

CAMPOS_OBRIGATORIOS = ("galpao_id", "zona", "ts", "idade_lote_dias")
SEVERIDADE = {"ok": 0, "atencao": 1, "critico": 2}


def _e_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def temperatura_alvo(idade_dias, cfg):
    """Temperatura-alvo (C) para a idade do lote: cai com a idade ate um minimo."""
    t = cfg["temperatura"]
    return max(t["alvo_minimo_c"], t["alvo_inicial_c"] - t["queda_por_dia_c"] * (idade_dias - 1))


def validar_leitura(leitura, cfg):
    """Passa a leitura pelos dois filtros do fluxograma.

    Devolve (aprovada, motivo). Motivos possiveis:
      campo_invalido, sensor_parado, temperatura_fora_da_faixa, co2_fora_da_faixa
    """
    for campo in CAMPOS_OBRIGATORIOS:
        if leitura.get(campo) is None:
            return False, "campo_invalido"
    if not isinstance(leitura["idade_lote_dias"], int) or leitura["idade_lote_dias"] < 1:
        return False, "campo_invalido"

    temp, co2 = leitura.get("temp_c"), leitura.get("co2_ppm")
    if temp is None or co2 is None:
        return False, "sensor_parado"
    if not _e_numero(temp) or not _e_numero(co2):
        return False, "campo_invalido"

    faixa = cfg["faixas_plausiveis"]
    if not faixa["temperatura_c"]["min"] <= temp <= faixa["temperatura_c"]["max"]:
        return False, "temperatura_fora_da_faixa"
    if not faixa["co2_ppm"]["min"] <= co2 <= faixa["co2_ppm"]["max"]:
        return False, "co2_fora_da_faixa"
    return True, None


def classificar(leitura, cfg):
    """Classifica uma leitura JA VALIDADA como ok, atencao ou critico.

    A severidade final e a pior entre temperatura e CO2.
    """
    t = cfg["temperatura"]
    alvo = temperatura_alvo(leitura["idade_lote_dias"], cfg)
    desvio = leitura["temp_c"] - alvo

    if desvio > t["critico_acima_do_alvo_c"]:
        nivel_temp = "critico"
    elif desvio > t["atencao_acima_do_alvo_c"]:
        nivel_temp = "atencao"
    else:
        nivel_temp = "ok"

    co2 = leitura["co2_ppm"]
    if co2 > cfg["co2_ppm"]["critico"]:
        nivel_co2 = "critico"
    elif co2 > cfg["co2_ppm"]["atencao"]:
        nivel_co2 = "atencao"
    else:
        nivel_co2 = "ok"

    motivos = []
    if nivel_temp != "ok":
        motivos.append("temperatura")
    if nivel_co2 != "ok":
        motivos.append("co2")
    status = max(nivel_temp, nivel_co2, key=lambda n: SEVERIDADE[n])

    return {
        "status": status,
        "motivos": motivos,
        "temp_alvo_c": round(alvo, 1),
        "desvio_c": round(desvio, 1),
    }