# Vendas de Combustíveis Líquidos — Dashboard ANP

Dashboard interativo com as vendas mensais de combustíveis líquidos por distribuidora (dados abertos da ANP), com filtros por companhia, estado (UF de destino) e tipo de consumidor, além de gráfico de participação por companhia.

**Dashboard:** https://jmagomez.github.io/vendas-liquidos/

## Estrutura

```
vendas-liquidos/
├── scripts/
│   └── update_dashboard.py   # baixa o CSV da ANP, agrega e gera data.js
├── data.js                   # dados agregados (mês × companhia × UF × mercado)
├── index.html                # dashboard (GitHub Pages)
└── .github/workflows/
    └── update-dashboard.yml  # rotina mensal (dia 5) + e-mail
```

## Rotina automática

Todo dia 5 de cada mês (9h de Brasília), o GitHub Actions baixa o
`Liquidos_Vendas_Atual.csv` da ANP, regenera o `data.js`, commita e envia
um resumo por e-mail com link para o dashboard.

Para o envio de e-mail funcionar, configure os secrets `MAIL_USERNAME` e
`MAIL_PASSWORD_ANP` (senha de app do Gmail) em Settings → Secrets and variables → Actions.
O workflow lê `MAIL_PASSWORD_ANP`, não `MAIL_PASSWORD` — o README apontava o nome errado.

## Integridade dos dados

A rotina falha alto em vez de gravar dados ruins:

- o CSV é lido por posição de coluna (a ANP não documenta um cabeçalho estável),
  então **cada linha é validada** — ano entre 2000 e 2100, mês entre 1 e 12 e
  volume numérico. Se mais de 1% das linhas não passar, a execução é
  interrompida: é o sintoma de que o layout da ANP mudou, e somar a coluna
  errada em silêncio seria pior do que não atualizar;
- antes de sobrescrever, o resultado é **comparado com o `data.js` atual**. Se o
  número de meses cair, ou as combinações caírem mais de 5%, o arquivo antigo
  fica intacto e a rotina falha. A ANP já publicou arquivo truncado, e sem essa
  checagem um download parcial apagaria anos de histórico terminando com sucesso.

Nos dois casos o `data.js` não é tocado e o workflow dispara o e-mail de falha.

## Fonte

[Dados abertos da ANP — vendas de derivados de petróleo](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos) · volumes em mil m³.
