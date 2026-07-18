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
`MAIL_PASSWORD` (senha de app do Gmail) em Settings → Secrets and variables → Actions.

## Fonte

[Dados abertos da ANP — vendas de derivados de petróleo](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos) · volumes em mil m³.
