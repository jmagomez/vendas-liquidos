"""Testes das travas de integridade acrescentadas depois do episódio de ago/2026.

Em 2026-09-05 a rotina gravou `2026-08` com 71 mil m³ vindos de 3 distribuidoras
— 0,6% de um mês normal, sem Vibra, Ipiranga ou Raízen. Não era dado ruim: era o
mês corrente ainda em formação no arquivo da ANP. As travas de então defendiam o
histórico contra ENCOLHER; um mês novo incompleto ADICIONA linhas, e passava.

Estes testes travam as três defesas novas: cabeçalho conferido por nome, mês da
ponta classificado como não consolidado, e mês já fechado que não pode encolher.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import data_js  # noqa: E402
import update_dashboard as ud  # noqa: E402
from test_agregar import CAB_ANP, csv_bytes, linha  # noqa: E402

# --- cabeçalho conferido por nome, não só por contagem ----------------------

def test_cabecalho_generico_derruba():
    """15 colunas com nomes que não são os da ANP: layout desconhecido."""
    generico = ";".join(f"c{i}" for i in range(15))
    with pytest.raises(RuntimeError, match="cabeçalho"):
        ud.agregar(csv_bytes(linha(), cabecalho=generico))


def test_colunas_numericas_trocadas_derrubam():
    """Ano e mês trocados passariam por TODA a validação por linha — os dois são
    inteiros pequenos e plausíveis. Só o nome da coluna denuncia a troca."""
    trocado = list(CAB_ANP)
    trocado[0], trocado[1] = trocado[1], trocado[0]
    with pytest.raises(RuntimeError, match="cabeçalho"):
        ud.agregar(csv_bytes(linha(), cabecalho=";".join(trocado)))


def test_acento_no_cabecalho_nao_derruba():
    """'(mil m³)' em vez de '(mil m3)' é cosmético; não pode parar a rotina."""
    com_acento = list(CAB_ANP)
    com_acento[11] = "Quantidade de Produto (mil m³)"
    com_acento[1] = "Mês"
    agg = ud.agregar(csv_bytes(linha(qtd="10,0"), cabecalho=";".join(com_acento)))
    assert sum(agg.values()) == pytest.approx(10.0)


# --- mês da ponta ainda não consolidado -------------------------------------

def serie(meses_cheios=15, comps_cheio=100, vol_cheio=10.0, ponta=None):
    """Monta um agg sintético: N meses cheios e, opcionalmente, uma ponta magra.

    `ponta` = (n_comps, volume_por_comp) do mês seguinte ao último cheio.
    """
    agg = {}
    for m in range(1, meses_cheios + 1):
        ym = f"2025-{m:02d}" if m <= 12 else f"2026-{m - 12:02d}"
        for c in range(comps_cheio):
            agg[(ym, f"COMP{c}", "SP", "TRR", "Diesel B")] = vol_cheio
    if ponta:
        n, v = ponta
        m = meses_cheios + 1
        ym = f"2025-{m:02d}" if m <= 12 else f"2026-{m - 12:02d}"
        for c in range(n):
            agg[(ym, f"COMP{c}", "SP", "TRR", "Diesel B")] = v
    return agg


def test_mes_completo_nao_e_marcado():
    assert ud.classificar_meses(serie()) == []


def test_stub_da_anp_e_marcado():
    """O caso real: 3 agentes contra ~150, 0,6% do volume."""
    agg = serie(ponta=(3, 2.0))
    assert ud.classificar_meses(agg) == ["2026-04"]


def test_queda_de_volume_sozinha_marca():
    """Todos os agentes declararam, mas com uma fração do volume."""
    agg = serie(ponta=(100, 1.0))       # 100 agentes, 10% do volume
    assert ud.classificar_meses(agg) == ["2026-04"]


def test_queda_de_agentes_sozinha_marca():
    """Volume quase normal concentrado em poucos agentes: declaração parcial."""
    agg = serie(ponta=(20, 45.0))       # 20 agentes (13%), 90% do volume
    assert ud.classificar_meses(agg) == ["2026-04"]


def test_variacao_normal_nao_marca():
    """Um mês 25% abaixo da mediana é sazonalidade, não mês incompleto."""
    agg = serie(ponta=(100, 7.5))
    assert ud.classificar_meses(agg) == []


def test_colapso_no_meio_da_serie_nao_e_reclassificado():
    """Greve, choque regulatório: dado de verdade no meio da série. A varredura
    só olha a ponta e tem de parar no primeiro mês fechado."""
    agg = serie(meses_cheios=15)
    for c in range(100):
        agg[("2025-06", f"COMP{c}", "SP", "TRR", "Diesel B")] = 0.5
    assert ud.classificar_meses(agg) == []


def test_muitos_meses_parciais_derrubam():
    """Se a ponta inteira está magra, o problema não é a ponta: é o arquivo."""
    agg = serie(meses_cheios=13)
    for m in range(2, 7):                      # 2026-02 a 2026-06, todos magros
        for c in range(2):
            agg[(f"2026-{m:02d}", f"COMP{c}", "SP", "TRR", "Diesel B")] = 1.0
    with pytest.raises(RuntimeError, match="arquivo da ANP inteiro"):
        ud.classificar_meses(agg)


def test_historico_curto_nao_julga():
    """Com dois meses de base não dá para dizer o que é normal."""
    assert ud.classificar_meses(serie(meses_cheios=2, ponta=(1, 0.1))) == []


def test_data_js_grava_parciais_e_ultimo_completo():
    d = ud.gerar_data_js(serie(ponta=(3, 2.0)))
    assert d["parciais"] == ["2026-04"]
    assert d["ultimo_completo"] == "2026-03"
    # o mês parcial CONTINUA no arquivo: marcado, não apagado — quem audita
    # precisa conseguir ver o que a ANP publicou.
    assert "2026-04" in d["months"]


# --- mês já fechado não pode encolher ---------------------------------------

def _arquivo(meses, volumes, parciais=None):
    """data.js mínimo: um mês por volume, uma linha cada."""
    rows = []
    for i, v in enumerate(volumes):
        rows.extend([i, 0, 0, 0, 0, round(v * data_js.ESCALA)])
    return {"months": list(meses), "comps": ["A"], "ufs": ["SP"], "mkts": ["TRR"],
            "prods": ["Diesel B"], "campos": ud.CAMPOS, "rows": rows,
            "parciais": parciais or []}


def test_mes_fechado_encolhendo_derruba():
    """A ANP republicar um mês antigo pela metade: as contagens de meses e de
    combinações não veem isso — só a comparação mês a mês vê."""
    antes = _arquivo(["2026-01", "2026-02", "2026-03"], [100, 100, 100])
    agora = _arquivo(["2026-01", "2026-02", "2026-03"], [100, 50, 100])
    with pytest.raises(RuntimeError, match="encolheram"):
        ud.conferir_contra_anterior(agora, antes)


def test_revisao_pequena_da_anp_passa():
    """Revisões reais são da ordem de 0,1% (2026-06 foi de 11.507 p/ 11.515)."""
    antes = _arquivo(["2026-01", "2026-02"], [100, 100])
    agora = _arquivo(["2026-01", "2026-02"], [100, 99.9])
    ud.conferir_contra_anterior(agora, antes)   # não levanta


def test_mes_consolidado_voltando_a_parcial_derruba():
    antes = _arquivo(["2026-01", "2026-02"], [100, 100])
    agora = _arquivo(["2026-01", "2026-02"], [100, 100], parciais=["2026-01"])
    with pytest.raises(RuntimeError, match="voltaram a ficar incompletos"):
        ud.conferir_contra_anterior(agora, antes)


def test_mes_sumindo_derruba():
    antes = _arquivo(["2026-01", "2026-02", "2026-03"], [100, 100, 100])
    agora = _arquivo(["2026-01", "2026-03", "2026-04"], [100, 100, 100])
    with pytest.raises(RuntimeError, match="sumiu"):
        ud.conferir_contra_anterior(agora, antes)


def test_ponta_parcial_do_arquivo_antigo_fica_de_fora():
    """Num data.js gerado antes da marca `parciais` não dá para saber se a ponta
    já estava incompleta. Comparar contra ela inventaria uma falha: o arquivo
    novo, com o mês agora consolidado, ficaria MAIOR — mas se a ANP tiver
    corrigido para baixo, a queda seria falso positivo."""
    antes = {"months": ["2026-01", "2026-02"], "campos": ud.CAMPOS,
             "rows": [0, 0, 0, 0, 0, 1000000, 1, 0, 0, 0, 0, 1000]}   # ponta magra
    agora = _arquivo(["2026-01", "2026-02", "2026-03"], [100, 100, 100])
    ud.conferir_contra_anterior(agora, antes)   # não levanta


def test_mes_parcial_nao_bloqueia_proxima_rodada():
    """2026-08 marcado hoje; amanhã a ANP consolida. Não pode travar."""
    antes = _arquivo(["2026-06", "2026-07", "2026-08"], [100, 100, 0.6],
                     parciais=["2026-08"])
    agora = _arquivo(["2026-06", "2026-07", "2026-08"], [100, 100, 101])
    ud.conferir_contra_anterior(agora, antes)   # não levanta
