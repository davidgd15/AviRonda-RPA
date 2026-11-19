# AviRonda RPA - automação de alertas para aviários

Robô em Python que processa leituras simuladas de sensores por zona, valida os dados, aplica limites de temperatura e CO₂ e envia avisos confirmados por e-mail usando OneDrive for Business e Power Automate. A demonstração ajuda a localizar zonas de risco; não representa operação de uma granja real.

## Integrantes

| Integrante | RM |
|---|---|
| Fernando Popolili Lameira Pires | RM99919 |
| Lucas Palamartschuk de Toledo | RM97913 |
| Augusto Fisco Milreu | RM98245 |
| David Guilherme Barchin Denunci | RM98603 |
| Matheus Zanardi | RM98832 |

## Problema e benefício

Um ponto fixo de medição pode não mostrar diferenças entre zonas do galpão. O AviRonda organiza leituras de uma ronda por zonas e aponta onde as condições ultrapassaram limites definidos. A automação pode ajudar o produtor a agir mais cedo, contribuindo para o bem-estar animal e para a continuidade da produção de alimentos. Leituras desta entrega são simuladas.

## Arquitetura

```text
Arquivos JSON Lines em data/entrada
          ↓
Robô Python: validação → deduplicação → limites → confirmação por zona
          ↓
JSON de alertas + CSV + dashboard/relatório HTML + logs
          ↓
OneDrive for Business / AviRonda-saida/alertas
          ↓
Power Automate: gatilho → obter conteúdo → analisar JSON → verificar avisos
          ├─ sem avisos: Fim sem envio
          └─ com avisos: um e-mail por aviso (Office 365 Outlook)
```

O diagrama BPMN está em [`docs/AviRonda_BPMN.png`](docs/AviRonda_BPMN.png) e o arquivo editável em [`docs/AviRonda_BPMN.drawio`](docs/AviRonda_BPMN.drawio). O pacote exportado do fluxo está em `power-automate/`.

## Tecnologias

- Python 3.11, JSON Lines, CSV e HTML.
- pytest para testes automatizados.
- OneDrive for Business e Power Automate para disparo por arquivo e notificação.
- Office 365 Outlook no conector de e-mail exportado.

## Regras principais

- Campos obrigatórios: `galpao_id`, `zona`, `ts` e `idade_lote_dias`.
- Leituras plausíveis: temperatura de -10 a 50 °C e CO₂ de 300 a 10.000 ppm.
- Temperatura-alvo começa em 32 °C e cai 0,2 °C por dia até 23 °C; desvios acima de 1,5 °C são atenção e acima de 3 °C são críticos.
- CO₂ acima de 2.500 ppm é atenção e acima de 3.000 ppm é crítico.
- Um alerta exige duas leituras consecutivas acima do limite na mesma zona, dentro da janela configurada de 150 minutos. Sem confirmação, gera observação.
- Leituras duplicadas pela chave galpão + zona + timestamp são descartadas.

Os limites são parâmetros iniciais de demonstração e precisam de validação especializada antes de qualquer uso operacional.

## Como executar

No PowerShell, a partir da raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

As leituras de exemplo (simuladas, geradas pelo pipeline de dados do grupo) estão em `data/amostras/`. A pasta `data/entrada/` não vem no clone, então crie-a e copie as amostras para ela antes de rodar:

```powershell
New-Item -ItemType Directory -Force data\entrada
copy data\amostras\*.json data\entrada\
python -m src.main
```

Com as duas amostras, o terminal deve mostrar `2 processado(s), 0 com erro`, `alertas gravados: 4 aviso(s)` e `csv atualizado: 139 leitura(s) no total`. O robô move os arquivos processados para `data/processados/` (e os inválidos para `data/erros/`), então, para repetir a execução, copie as amostras de novo.

Para reproduzir os testes automatizados:

```powershell
python -m pytest
```

O robô grava `saida/alertas/alertas_AAAAMMDD_HHMMSS.json`, `saida/alertas.json`, `saida/leituras_validas.csv`, `saida/dashboard.html`, `saida/relatorio_diario.html` e logs em `logs/` (um exemplo está em `logs/amostra_execucao.txt`). Defina `AVIRONDA_PASTA_SAIDA` para gravar as saídas em outra pasta, como a pasta do OneDrive que o Power Automate observa.

## Power Automate e evidências

O fluxo `AviRonda - Enviar alertas` observa a pasta `AviRonda-saida/alertas`, não inclui subpastas, analisa o JSON e envia ao destinatário FIAP `RM98603@fiap.com.br`. A definição exportada contém repetição fixa de 3 tentativas, intervalo `PT1M`, e ação `Registrar_falha` após falha ou timeout. O teste forçado de falha foi intencionalmente pulado; a existência dessa configuração não significa que a falha foi testada em execução. O teste com arquivo sem avisos e o envio bem-sucedido estão documentados nas capturas.

Capturas: [`assets/`](assets/). Histórico: [`pa_08_historico_sucesso.png`](pa_08_historico_sucesso.png), [`pa_08_historico_vazio.png`](pa_08_historico_vazio.png). E-mail recebido: [`pa_09_email_recebido.png`](pa_09_email_recebido.png). Relatório técnico: [`docs/Relatorio_Tecnico_AviRonda_RPA.pdf`](docs/Relatorio_Tecnico_AviRonda_RPA.pdf).

## ODS conectados

ODS 2 (fome zero e agricultura sustentável), ODS 9 (indústria, inovação e infraestrutura) e ODS 13 (ação contra a mudança global do clima). A explicação está no relatório técnico.

## Segurança, LGPD e limites

As amostras são simuladas e este repositório não deve conter credenciais ou dados pessoais reais. A conexão cloud é mantida pelo Power Automate. A evidência exportada mostra conexão Office 365 Outlook `AviRonda - Outlook FIAP`.

## Escopo e links

- Repositório público deste projeto: [davidgd15/AviRonda-RPA](https://github.com/davidgd15/AviRonda-RPA).
- Vídeo demonstrativo: link ainda pendente de gravação/publicação.
- Integração com MVP/Databricks: fora do escopo desta entrega RPA, conforme decisão da equipe. O projeto Big Data é relacionado, mas separado: [Fernando-Popolili/BigData-GS](https://github.com/Fernando-Popolili/BigData-GS).

## Relatório

Consulte [`docs/Relatorio_Tecnico_AviRonda_RPA.pdf`](docs/Relatorio_Tecnico_AviRonda_RPA.pdf) para processo, regras, exceções, auditoria, testes e evidências visuais.
