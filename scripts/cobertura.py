"""Janela comparavel da serie: onde a FONTE passa a cobrir cada produto.

O PROBLEMA, medido no artefato de 2026-11-05 (mil m3 por ano):

    ano    Diesel B   Etanol Hidr.   Gasolina C   Oleo Comb.
    2007        403          7.254       19.940        5.285
    2008        582         12.840       25.416        5.204
    2009        483         16.833       26.202        5.093
    2010     32.821         15.471       31.249        4.967   <- degrau

O diesel nao cresceu 68 vezes em um ano: o arquivo historico da ANP so passa a
trazer vendas de diesel em 2010. Ate 2009 o diesel esta praticamente AUSENTE da
fonte, e o diesel e metade do mercado. Consequencias de desenhar 2007-2026 como
uma serie unica:

- o total mensal mais que dobra em jan/2010 e o grafico mostra um mercado
  triplicando, que e artefato de cobertura, nao demanda;
- a variacao a/a de cada mes de 2010 fica em +100% ou mais, contra uma base
  que nao existia;
- o HHI de 2007-2009 e calculado SEM as distribuidoras de diesel, o que muda
  quem sao os grandes: e um indice de outro mercado com o mesmo nome.

Nada disso aparece numa trava de volume: os numeros de 2007-2009 estao certos
para o que a fonte traz. O que esta errado e compara-los com 2010 em diante.

A REGRA, por produto e so sobre meses fechados: existe degrau em `i` quando os
12 meses que terminam em `i` somam menos que 10% dos 12 meses seguintes. O
primeiro mes comparavel do produto e `i+1`; o da serie e o mais tardio entre os
produtos. Dois cuidados deliberados:

- a comparacao e entre janelas VIZINHAS, nunca contra o maximo da serie. O Oleo
  Comb. cai de 5.285 (2007) para 1.083 (2025) -- queda secular real, de 80%, que
  contra o maximo seria acusada como falta de cobertura e truncaria a serie;
- o degrau tem de estar no INICIO (primeiro quarto da serie). Um degrau no meio
  nao e entrada de cobertura: e sumico de produto, troca de layout ou falha de
  coleta, e ai a rotina para e alguem olha, em vez de o painel esconder 15 anos
  de historico sozinho.
"""

JANELA = 12
# 10% e folgado de proposito: o degrau real do diesel e de 1,5% (483 contra
# 32.821). Um limite apertado pegaria oscilacao de safra; este so dispara
# quando o produto esta praticamente ausente.
RAZAO_DEGRAU = 0.10
# Fracao da serie em que um degrau ainda e "entrada de cobertura".
FRACAO_INICIAL = 0.25


def volume_por_produto(agg, parciais=()) -> dict:
    """{produto: {mes: volume}}, so com meses fechados."""
    fora = set(parciais)
    out: dict[str, dict[str, float]] = {}
    for (mes, _comp, _uf, _mkt, prod), q in agg.items():
        if mes in fora:
            continue
        out.setdefault(prod, {})[mes] = out.setdefault(prod, {}).get(mes, 0.0) + q
    return out


def _degrau(serie: list[float]) -> tuple[int, float, float] | None:
    """Ultimo indice i tal que os 12 meses ate i somam < 10% dos 12 seguintes."""
    n = len(serie)
    achado = None
    limite = int(n * FRACAO_INICIAL)
    for i in range(JANELA - 1, n - JANELA):
        antes = sum(serie[i - JANELA + 1:i + 1])
        depois = sum(serie[i + 1:i + 1 + JANELA])
        if depois > 0 and antes < depois * RAZAO_DEGRAU:
            achado = (i, antes, depois)
    if achado is None:
        return None
    if achado[0] >= limite:
        raise RuntimeError(
            f"degrau de cobertura em posicao {achado[0]} de {n} meses, fora do "
            f"primeiro quarto da serie ({achado[1]:,.0f} -> {achado[2]:,.0f} mil "
            "m3 em 12 meses). Isso nao e entrada de cobertura: e produto que "
            "sumiu, layout trocado ou coleta falhada. Artefato NAO foi alterado."
        )
    return achado


def analisar(agg, months: list[str], parciais=()) -> dict:
    """Janela comparavel por produto e da serie inteira.

    `inicio_comparavel` e o mes a partir do qual TODO produto esta coberto --
    o unico ponto em que somar os quatro produtos e legitimo.
    """
    fechados = [m for m in months if m not in set(parciais)]
    por_produto = volume_por_produto(agg, parciais)
    detalhe: dict[str, dict] = {}
    for prod in sorted(por_produto):
        serie = [por_produto[prod].get(m, 0.0) for m in fechados]
        d = _degrau(serie)
        if d is None:
            detalhe[prod] = {"inicio": fechados[0] if fechados else None}
            continue
        i, antes, depois = d
        detalhe[prod] = {
            "inicio": fechados[i + 1],
            "antes_12m": round(antes, 1),
            "depois_12m": round(depois, 1),
            "razao": round(antes / depois, 4) if depois else None,
        }
    inicios = [v["inicio"] for v in detalhe.values() if v["inicio"]]
    return {
        "por_produto": detalhe,
        "inicio_comparavel": max(inicios) if inicios else None,
    }


def conferir_contra_anterior(cobertura: dict, anterior) -> None:
    """Trava: a janela comparavel nao pode encurtar de uma rodada para a outra.

    Encurtar significa que a fonte PERDEU cobertura de um produto em anos que
    ja estavam cobertos -- arquivo truncado, membro faltando no zip. Alargar
    (inicio mais antigo) e bem-vindo e passa.
    """
    if not anterior:
        return
    antes = (anterior.get("cobertura") or {}).get("inicio_comparavel")
    agora = cobertura.get("inicio_comparavel")
    if antes and agora and agora > antes:
        raise RuntimeError(
            f"regressao de cobertura: a serie comparavel comecava em {antes} e "
            f"agora comecaria em {agora}. Algum produto perdeu cobertura em anos "
            "que ja estavam cobertos. Artefato NAO foi alterado."
        )
