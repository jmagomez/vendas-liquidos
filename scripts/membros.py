"""Leitura dos varios membros de vendas do liquidos.zip e costura de lacunas.

Ate out/2026 o Liquidos_Vendas_Atual.csv trazia a serie inteira (116 meses) e o
pipeline lia so ele. O run #19 (2026-10-31) mostrou que a ANP encurtou essa
janela para 33 meses, e a trava de regressao recusou trocar 116 meses por 33 --
corretamente.

O diagnostico (workflow "Diagnostico do zip da ANP") mediu o zip e achou TRES
membros da familia de vendas, cobrindo 225 meses:

    Liquidos_Vendas_Historico_2007_a_2017.csv   2007-01..2016-12  cp1252     11 col, SEM cabecalho
    Liquidos_Vendas_Historico_2018_a_2023.csv   2018-01..2023-12  utf-8-sig  12 col, com cabecalho
    Liquidos_Vendas_Atual.csv                   2024-01..2026-09  utf-8-sig  12 col, com cabecalho

Dois detalhes que este modulo existe para tratar:

1. O membro antigo tem OUTRO layout: 11 colunas, sem a "Descricao do Produto".
   UF Destino, Mercado e Quantidade estao em 8, 9 e 10 -- nao em 9, 10 e 11.
   Le-lo com as constantes do layout novo produziria numero errado em silencio,
   que e o desfecho que este repositorio inteiro existe para evitar.

2. Falta 2017. O arquivo chamado "2007_a_2017" termina em 2016-12 (as linhas
   por ano somam exatamente o total do arquivo, 710.832 -- nao sobra nenhuma
   linha para 2017) e o membro seguinte comeca em 2018-01. Os 12 meses de 2017
   existem no data.js e em nenhum membro de vendas do zip.

Dai a heranca de LACUNA INTERIOR: um mes que nenhum membro cobre, mas que fica
ENTRE as coberturas de dois membros, e herdado do artefato anterior e marcado
como tal. Nao e backfill generico -- se fosse, um download truncado seria
remendado em silencio e a trava de regressao perderia a serventia. As condicoes
sao deliberadamente estreitas e estao em `herdar_lacunas`.

Se a ANP voltar a publicar 2017, nada e herdado: a lacuna deixa de existir e o
mes passa a vir da fonte, revalidado como todos os outros.
"""
import re

# Membros da familia de vendas. O zip tambem traz Entregas (distribuidor,
# fornecedor, historico) e Importacao -- bases DIFERENTES, com outro grao e
# outras colunas. Misturar familias foi o erro da primeira versao do relatorio
# de diagnostico, que somou a cobertura de todas e concluiu que nao faltava
# nada.
PADRAO_MEMBRO_VENDAS = re.compile(r"liquidos_vendas_.*\.csv$", re.IGNORECASE)

# Layout do membro historico 2007-2016: 11 colunas, sem cabecalho e sem a
# coluna "Descricao do Produto" que o layout novo tem na posicao 5. Conferido
# contra a primeira linha real do arquivo:
#   2007;1;ABENGOA BIOENERGIA SAO JOAO LTDA;810101001;Etanol Hidratado;
#   SE;SP;NI;NI;CONSUMIDOR FINAL;1,981765
LAYOUT_11 = {"ano": 0, "mes": 1, "comp": 2, "prod": 4, "uf": 8, "mkt": 9, "qtd": 10}
N_COLUNAS_11 = 11

# Teto absoluto de meses herdados. 2017 sao 12. Um numero maior significa que a
# fonte encolheu de novo, e isso tem de parar a rotina e chamar um humano, nao
# ser remendado. O teto vale inclusive na primeira rodada, quando ainda nao ha
# com o que comparar.
MAX_MESES_HERDADOS = 12


def e_membro_de_vendas(nome: str) -> bool:
    return bool(PADRAO_MEMBRO_VENDAS.search(nome.rsplit("/", 1)[-1]))


def parece_cabecalho(campos) -> bool:
    """Cabecalho tem texto onde dado teria numero (a coluna 0 e o ano)."""
    if not campos:
        return False
    try:
        int(campos[0].strip().strip('"'))
    except ValueError:
        return True
    return False


def _ym(mes: str) -> tuple:
    a, m = mes.split("-")
    return int(a), int(m)


def _passo(ym: tuple) -> tuple:
    a, m = ym
    return (a + 1, 1) if m == 12 else (a, m + 1)


def meses_entre(inicio: str, fim: str) -> list:
    """Todos os meses de `inicio` a `fim`, inclusive."""
    atual, alvo, saida = _ym(inicio), _ym(fim), []
    while atual <= alvo:
        saida.append("%04d-%02d" % atual)
        atual = _passo(atual)
    return saida


def conferir_contiguidade(nome: str, meses) -> None:
    """Nenhum membro pode ter buraco DENTRO da propria faixa.

    Buraco interno a um membro nao e reorganizacao da ANP: e arquivo incompleto.
    O diagnostico de 2026-10-31 mediu os tres membros de vendas e os tres vieram
    contiguos.
    """
    meses = sorted(meses)
    if not meses:
        raise RuntimeError(f"membro {nome} nao produziu nenhum mes")
    faltando = [m for m in meses_entre(meses[0], meses[-1]) if m not in set(meses)]
    if faltando:
        raise RuntimeError(
            f"membro {nome} tem {len(faltando)} buraco(s) dentro da propria faixa "
            f"({meses[0]} a {meses[-1]}): {faltando[:6]}. Arquivo incompleto; "
            "data.js NAO foi alterado."
        )


def conferir_sem_sobreposicao(cobertura_por_membro: dict) -> None:
    """Dois membros nao podem trazer o mesmo mes.

    Se trouxerem, somar os dois DOBRA o mes -- e nenhuma trava de volume pega
    isso, porque o total so cresce. As faixas da ANP sao disjuntas por desenho
    (2007-2016, 2018-2023, 2024-); se deixarem de ser, a rotina para.
    """
    visto = {}
    conflitos = []
    for nome, meses in cobertura_por_membro.items():
        for m in meses:
            if m in visto:
                conflitos.append(f"{m}: {visto[m]} e {nome}")
            else:
                visto[m] = nome
    if conflitos:
        raise RuntimeError(
            f"membros do zip se sobrepoem em {len(conflitos)} mes(es) — somar os "
            f"dois dobraria o mes. data.js NAO foi alterado. {conflitos[:5]}"
        )


def lacunas_interiores(meses) -> list:
    """Meses ausentes ENTRE o primeiro e o ultimo mes coberto pelos membros.

    So o interior. Uma ponta que encolheu (inicio mais tarde, fim mais cedo) nao
    vira lacuna aqui, e por isso continua sendo tratada pela trava de regressao
    como truncamento -- que e o que normalmente e.
    """
    meses = set(meses)
    if not meses:
        return []
    ordenados = sorted(meses)
    return [m for m in meses_entre(ordenados[0], ordenados[-1]) if m not in meses]


def herdar_lacunas(agg, anterior, max_herdados: int = MAX_MESES_HERDADOS) -> list:
    """Copia do artefato anterior os meses de LACUNA INTERIOR, e so eles.

    Condicoes, todas obrigatorias:
      - o mes nao e coberto por nenhum membro do zip;
      - o mes fica ENTRE coberturas (lacuna interior), nao na ponta;
      - o mes existe no data.js anterior;
      - o conjunto herdado cabe no teto (`max_herdados`);
      - o conjunto herdado NAO cresceu em relacao a rodada anterior.

    Devolve a lista de meses herdados (vazia quando a fonte cobre tudo).
    Modifica `agg` no lugar.
    """
    if not anterior:
        return []
    import data_js

    lacunas = [m for m in lacunas_interiores({k[0] for k in agg})
               if m in set(anterior["months"])]
    if not lacunas:
        return []

    if len(lacunas) > max_herdados:
        raise RuntimeError(
            f"{len(lacunas)} meses faltam na fonte e precisariam ser herdados "
            f"({lacunas[0]} a {lacunas[-1]}), acima do teto de {max_herdados}. "
            "Isso nao e a lacuna conhecida de 2017 — e a fonte encolhendo. "
            "data.js NAO foi alterado."
        )

    herdados_antes = anterior.get("herdados")
    if herdados_antes is not None:
        novos = sorted(set(lacunas) - set(herdados_antes))
        if novos:
            raise RuntimeError(
                f"a lacuna da fonte CRESCEU: {len(novos)} mes(es) novo(s) "
                f"({novos[:6]}) alem dos ja conhecidos ({sorted(herdados_antes)[:6]}). "
                "Lacuna nova e hipotese sobre a origem, nao coisa para remendar. "
                "data.js NAO foi alterado."
            )

    campos = data_js.campos_de(anterior)
    if "prod" not in campos:
        raise RuntimeError(
            "o data.js anterior e do formato legado (sem produto na chave) e nao "
            "da para herdar meses dele sem inventar a dimensao de produto. "
            "Rode uma vez com a fonte cobrindo a serie inteira antes."
        )

    alvo = set(lacunas)
    for i_mes, c, u, k, p, q in data_js.iter_linhas(anterior):
        mes = anterior["months"][i_mes]
        if mes in alvo:
            # .get() em vez de += direto: `agg` e um defaultdict em producao,
            # mas nao exigir isso mantem a funcao testavel com um dict comum.
            chave = (mes, anterior["comps"][c], anterior["ufs"][u],
                     anterior["mkts"][k], anterior["prods"][p])
            agg[chave] = agg.get(chave, 0.0) + q
    return sorted(lacunas)
