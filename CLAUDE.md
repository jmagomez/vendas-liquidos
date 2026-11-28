# CLAUDE.md — vendas-liquidos

Painel das vendas mensais de combustíveis líquidos da ANP. **ETL em Python**
(`scripts/`, `tests/`) + **painel em Vite/React/TypeScript** (`web/`), publicado
no GitHub Pages. Converse em **português do Brasil**.

A série tem 237 meses e 725 mil combinações de mês × agente × UF × mercado ×
produto. Ela roda sozinha duas vezes por mês e é lida como se fosse verdade:
**o pior desfecho possível aqui não é a rotina falhar, é ela publicar número
errado sem avisar ninguém.** Tudo abaixo existe por causa disso.

## Comandos

```bash
# ETL (raiz) — tudo offline, nada baixa da ANP
python -m pytest                     # 166 testes
ruff check .

python scripts/update_dashboard.py   # rodada REAL: baixa ~227 MB da ANP

# Painel
cd web
npm ci                               # ci, não install — ver "Dependências"
npm run typecheck && npm test && npm run build   # 36 testes
```

## A rotina

`update-dashboard.yml` roda **dias 5 e 28, 12:00 UTC** (9h de Brasília), e
também sob demanda. Duas passadas de propósito: **a ANP não fecha o mês
anterior no dia 5** — ela fecha o mês M na segunda metade de M+1, medido no
histórico deste repositório (18/jul/2026 o arquivo não trazia junho; 30/jul já
trazia). A do dia 28 é a que costuma pegar o mês consolidado; a do dia 5
recolhe revisões e serve de rede.

**28 e não 30**: 29, 30 e 31 não existem em todo mês, e um cron nesses dias
simplesmente não dispara em fevereiro.

O resumo do e-mail sai de `scripts/resumo_email.py`, que escreve pares
`chave=valor` para o `$GITHUB_OUTPUT` (valor multilinha quebraria o formato).
**Pegadinha:** o workflow lê o secret `MAIL_PASSWORD_ANP`, não
`MAIL_PASSWORD`. Com o secret ausente a rotina roda e avisa, não falha.

| workflow | quando | escreve? |
|---|---|---|
| `update-dashboard.yml` | dias 5 e 28 + manual | **sim** — commita `data.js` e `data/` |
| `painel.yml` | push em `web/**` + manual | **sim** — commita `painel/` pelo bot |
| `ci.yml` | push/PR | não — pytest e ruff |
| `painel-ci.yml` | push/PR em `web/**` e `data/**` | não — tsc, vitest, build |
| `diagnostico-zip.yml` | só manual | não — lê o zip da ANP e relata |
| `vendorizar.yml` | só manual | sim — gera `vendor/chart.umd.js` |

**Quando desconfiar da fonte, rode o `diagnostico-zip.yml` antes de mexer no
ETL.** Ele lista membros, cabeçalhos e faixa de meses sem tocar em nada, e tem
um passo final que falha se qualquer arquivo versionado mudou. Foi ele que
descobriu que o histórico da ANP tinha virado três membros.

## Arquivos gerados — nunca edite à mão

| | |
|---|---|
| `data.js` | carregador de 3 KB (já foi 13,9 MB de JSON) |
| `data/meta.json` | dimensões, marcas de qualidade, proveniência |
| `data/cubo.bin.gz` | 725 mil linhas, colunar, 2,1 MB |
| `data/cubo-mes-*.json` | marginais (mês × dimensão), 229 KB |
| `painel/` | bundle do Vite, commitado pelo `painel.yml` |

"Consertar" um valor no artefato é o erro mais caro que existe neste
repositório: o número volta errado na rodada seguinte e, no intervalo, ninguém
sabe que ele foi editado. Corrija o ETL e regere.

## Invariantes

1. **Quantidade é inteiro com `ESCALA = 10000`** (mil m³ com 4 casas). Ler sem
   dividir dá um número 10.000× maior, sem erro nenhum.
2. **O passo das linhas vem de `campos`, dentro do próprio arquivo**
   (`data_js.campos_de`). Arquivo sem a marca é o formato legado de 5 campos;
   assumir 6 soma as colunas erradas em silêncio.
3. **Mês em `parciais` sai de tudo**: média, acumulado, média móvel, variação
   a/a, ranking, HHI, manchete do e-mail. A referência pública é
   `ultimo_completo`.
4. **Fora de `cobertura.inicio_comparavel` a série não é comparável.** A fonte
   só traz diesel a partir de mar/2010, e diesel é metade do mercado. Somar
   2007-2009 com 2010+ mostra um mercado triplicando por artefato de cobertura.
5. **Nunca invente número.** Falta de dado é `n/d` ou o valor anterior
   preservado — nunca interpolação, projeção ou média "para preencher". Isso
   vale para o teor de anidro antes de out/2011, para a MM12 com menos de 12
   meses fechados e para qualquer célula vazia do cruzamento.
6. **Agregação existe só em Python.** O painel consome cubos e deriva
   indicadores de apresentação; reimplementar soma em TypeScript cria duas
   verdades que um dia divergem. **Este invariante vale para `web/`, e o
   `index.html` da raiz é a exceção que ainda não foi paga** — ver abaixo.
7. **Fusão de agente só pelo mapa versionado**, com motivo escrito
   (`scripts/aliases_agentes.json`). O HHI é quadrático na participação: um
   rótulo duplicado derruba o índice quase pela metade sem mudar um metro
   cúbico, e nenhuma trava de volume pega isso. Semelhança de nome **não** é
   evidência — ARAPETRO são duas pessoas jurídicas com a mesma marca.
8. **Escrita de artefato é atômica** (`tmp` + `os.replace`). Um runner
   interrompido no meio de um `write_text` deixa JSON inválido e, pior, a
   próxima rodada sem base de comparação.

## As oito travas

Em `update_dashboard.py`, `leitura.py`, `membros.py` e `cobertura.py`: encoding
detectado (não assumido), mojibake, cabeçalho conferido por nome, validação por
linha, mês da ponta não consolidado, regressão de meses/combinações/volume,
janela comparável por produto, rótulo do arquivo contra o conteúdo. Todas
abortam **antes** de escrever, e o workflow dispara e-mail de falha.

> **Trava que dispara é hipótese sobre a origem, não bug nosso.**
>
> Vá olhar o arquivo da ANP primeiro. **Não afrouxe limiar para a rotina
> passar.** O run #17 caiu em `achado 'MÃªs'` porque a ANP trocou o encoding
> para UTF-8; relaxar a conferência teria gravado `RaÃ­zen` ao lado de `Raízen`
> e destruído ranking e HHI em silêncio. Mudar um limiar exige, no PR: o trecho
> do arquivo da ANP que motivou, e um teste que falha antes e passa depois.
>
> O contrário também é verdade: o run #18 caiu por **falso positivo** meu —
> a trava de mojibake acusava qualquer `Ã`, que é letra legítima em
> `DISTRIBUIÇÃO` e `ATLÂNTICA`. Trava que acusa dado bom também é defeito.

## O que a ANP já fez, e o código já viu

- **trocou o encoding** do CSV sem avisar (run #17);
- **encurtou o arquivo** de 116 para 33 meses, movendo o resto para membros
  históricos do mesmo zip (run #19) — daí `membros.py`;
- **publica um arquivo cujo nome mente**: `Historico_2007_a_2017.csv` termina
  em 2016-12. Por isso 2017 é herdado do artefato anterior e **não é mais
  reproduzível a partir do zip de hoje**;
- **derruba a conexão** por minutos a fio (runs #24 e #25) — daí o orçamento de
  25 min no retry;
- **lista o mês corrente** assim que o primeiro agente declara: em 2026-09-05,
  agosto apareceu com 0,6% de um mês normal.

Nenhuma dessas foi anunciada. Assuma que a próxima também não será.

## Painel

`web/src/` é plano de propósito, não tem camada de framework: `dados.ts`
(carga), `financeiro.ts` (série, MM12, a/a, HHI), `setor.ts` (ciclo Otto em
base energética, CR4), `cruzamento.ts` (cubo completo + CSV), `App.tsx` e dois
componentes sob demanda.

- **O boot carrega 229 KB de cubos marginais.** O cubo completo (2,1 MB) só
  entra quando o usuário pede cruzamento ou concentração por UF. Não mova isso
  para o caminho crítico.
- **Indicador financeiro nasce em `financeiro.ts` ou `setor.ts`, com teste.**
  Não calcule dentro do componente.
- **`web/src/artefato.test.ts` é o canário**: lê o `data/` versionado e
  reconcilia a soma do cubo completo, mês a mês, com os quatro marginais. É o
  que pega o Python que escreve e o TypeScript que lê discordando sobre largura
  de coluna, ordem de campo ou escala — divergência que passa nos dois lados
  isoladamente e só apareceria como número errado na tela.
- Toda leitura de concentração repete na tela que **agente regulado ≠ grupo
  econômico** (o HHI publicado é piso) e que a UF é a de **destino declarado**.

## O painel antigo (`index.html`)

São 1.087 linhas de JavaScript à mão, servidas na **raiz** do GitHub Pages; o
painel novo fica em `/painel/`. Os dois leem o mesmo `data/` — uma fonte, não
duas.

**Ele reimplementa a regra de mês não consolidado em JavaScript.** Hoje essa
regra existe em dois lugares, Python e JS, e é o tipo de duplicação que um dia
diverge em silêncio: o invariante 6 descreve para onde o repositório vai, não
onde ele está. Mudou a regra em `update_dashboard.py`? Confira o `index.html`
também, ou aposente-o.

Ele carrega o Chart.js de `vendor/chart.umd.js` e só então tenta o CDN — o
painel é aberto de dentro de rede corporativa, onde CDN costuma estar
bloqueado, e antes disso um CDN inacessível devolvia página em branco sem uma
linha de erro. Abrir o arquivo direto do disco não funciona: o navegador
bloqueia o `data.js` por `file://`, e a página diz isso em vez de ficar branca.

## Convenções

- **Comentário e identificador em português sem acento** (ASCII); **mensagem de
  erro e texto de tela com acento**. `cabecalho` na variável, "cabeçalho da ANP
  não confere" no `raise`.
- **Nome de teste descreve o comportamento, em português**:
  `test_mes_antigo_encolhendo_nao_sobrescreve`. O docstring diz **por que o
  teste existe**, de preferência citando o incidente.
- **Constante de regra de negócio em maiúscula, no topo do módulo, com o
  comentário do porquê daquele número** — `FATOR_PARCIAL = 0.60`,
  `QUEDA_MAX_MES_FECHADO = 0.10`, `MAX_MESES_HERDADOS = 12`, `ORCAMENTO`. Número
  mágico no meio da função é a forma mais fácil de um limiar virar folclore.
- Python **3.12** (o CI usa 3.12; `datetime.UTC` exige 3.11+). Ruff com
  `line-length 100` e `select = ["E", "F", "I", "UP", "B"]`, em `pyproject.toml`.

## Dependências

`npm ci`, nunca `npm install`: falha quando o lock e o `package.json`
discordam, em vez de consertar em silêncio e testar uma árvore que não é a
versionada. O dependabot vigia `pip`, `github-actions` e o `npm` de `/web`.

## Fluxo de trabalho

- **Mudança entra por pull request**, com CI verde (`ci.yml` roda pytest e
  ruff; `painel-ci.yml` roda tsc, vitest e build). Não commite direto na `main`.
- **Arquivos em `.github/workflows/` não podem ser escritos pelo GitHub App**
  usado aqui (falta o escopo `workflow`): edite pelo editor web do GitHub.
- Teste novo explica **por que existe**, de preferência citando o incidente que
  o motivou. A suíte deste repositório é um registro de falhas reais, não um
  exercício de cobertura.

## Convenções comuns a todos os pipelines

@CONVENCOES-COMUNS.md

Esse arquivo é uma cópia sincronizada de
https://github.com/jmagomez/convencoes-claude. Não edite a cópia daqui: a
próxima sincronização a sobrescreve sem avisar. Mude a fonte, e o workflow
"Sincronizar convenções" traz a mudança de volta.
