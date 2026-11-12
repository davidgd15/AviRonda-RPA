# PDD – Automação de Alertas do AviRonda

## 1. Objetivo
Substituir a conferência manual das leituras do carrinho por um fluxo
automático que valida os dados, aplica as regras do lote e avisa o granjeiro.

## 2. Início do processo
Chegada de um novo arquivo de leituras em `data/entrada/` (ou execução
agendada).

## 3. Entradas
- Leituras do carrinho: zona, ponto, data/hora, lote, temperatura,
  umidade, CO2 (amônia opcional).
- Configuração de limites por idade do lote (`config/limites.json`).

## 4. Etapas
1. Verificar se o arquivo existe e se o formato é válido.
2. Ler as leituras.
3. Para cada leitura (loop):
   a. Validar campos obrigatórios e faixa plausível.
   b. Descartar duplicadas.
   c. Calcular o ITU.
   d. Buscar os limites conforme a idade do lote.
   e. Comparar com os limites (decisão).
   f. Se acima do limite, verificar a remedição de confirmação.
4. Consolidar por zona (normal / observação / crítica).
5. Gerar `alertas.json`, relatório diário e dashboard HTML.
6. Power Automate envia o e-mail pelo Outlook.
7. Registrar o resumo no log.

## 5. Regras de decisão
- Leitura fora da faixa física plausível -> descartar e registrar.
- Leitura duplicada (mesma zona, ponto e hora) -> descartar e registrar.
- Acima do limite SEM confirmação -> aguardar.
- Acima do limite COM confirmação -> zona crítica e alerta.

## 6. Exceções
| Situação | Tratamento |
|---|---|
| Arquivo ausente | Log de erro + aviso |
| JSON/CSV inválido | Log de erro + move para `data/erros/` |
| Leitura absurda | Descarta, loga, não gera alarme falso |
| Duplicado | Descarta e loga |
| Sensor parado | Aviso de falha de sensor |
| Falha no envio do e-mail | Registra e tenta novamente |

## 7. Saídas
- `saida/alertas.json`
- `saida/leituras_validas.csv`
- `saida/relatorio_diario.html`
- `saida/dashboard.html`
- `logs/robo_AAAA-MM-DD.log`

## 8. Segurança e LGPD
Sem credenciais no código; ID do produtor tratado com hash; logs sem
dados sensíveis.