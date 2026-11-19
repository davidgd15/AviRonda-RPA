# Resultados dos testes automatizados

## Como reproduzir

Na raiz do repositório, com a `.venv` ativa:

```powershell
pip install -r requirements.txt
python -m pytest -v
```

## Execução registrada

- Data e hora: 18/11/2026 20:35
- Ambiente: Windows, Python 3.11.4
- Resultado: 54 passed in 1.23s
- Saída completa: [`pytest_saida.txt`](pytest_saida.txt)

## Cenários cobertos

| Cenário | Arquivos | Exemplos de testes |
|---|---|---|
| Sucesso | `test_regras.py`, `test_robo.py`, `test_main.py`, `test_saidas.py` | leitura válida; arquivo sem alertas; arquivo bom vai para `data/processados`; todas as saídas são gravadas; CSV acumulado sem duplicar |
| Decisão | `test_regras.py`, `test_robo.py`, `test_saidas.py` | temperatura-alvo por idade; atenção e crítico por temperatura e CO₂; limite exato não alerta; duas leituras consecutivas geram um alerta; pico isolado vira observação; leitura fora da janela não confirma; um aviso por galpão |
| Falha | `test_regras.py`, `test_robo.py`, `test_main.py`, `test_saidas.py` | sensor parado; temperatura e CO₂ absurdos; campo ausente e tipo inválido; arquivo ausente, vazio ou sem JSON válido; linha quebrada; duplicata; erro inesperado no processamento; falha ao gravar uma saída |