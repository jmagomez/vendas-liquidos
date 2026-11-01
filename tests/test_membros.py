"""Leitura multi-membro do liquidos.zip e heranca de lacuna interior.

Contexto (run #19, 2026-10-31): a ANP encurtou o Liquidos_Vendas_Atual.csv de
116 para 33 meses e moveu o historico para outros membros do MESMO zip. O
diagnostico mediu tres membros de vendas, dois detalhes dos quais estes testes
travam:

- o membro 2007-2016 tem 11 colunas e NAO tem cabecalho, com UF/mercado/
  quantidade deslocados um a esquerda. Le-lo com o layout novo daria numero
  errado em silencio;
- falta 2017 (as linhas por ano do membro somam exatamente o total do arquivo,
  710.832, sem sobrar nenhuma para 2017), e 2017 existe no data.js.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import membros as mod_membros  # noqa: E402
import update_dashboard as ud  # noqa: E402

# --- fixtures de CSV --------------------------------------------------------

CAB12 = ";".join([
    "Ano", "Mês", "Agente Regulado", "Código do Produto", "Nome do Produto",
    "Descrição do Produto", "Região Origem", "UF Origem", "Região Destinatário",
    "UF Destino", "Mercado Destinatário", "Quantidade de Produto (mil m³)",
])


def linha12(ano, mes, comp="DISTRIB A", prod="Diesel B", uf="SP",
            mkt="TRR", qtd="10,0"):
    c = [""] * 12
    c[0], c[1], c[2], c[4], c[9], c[10], c[11] = (
        str(ano), str(mes), comp, prod, uf, mkt, qtd)
    return ";".join(c)


def linha11(ano, mes, comp="DISTRIB A", prod="Diesel B", uf="SP",
            mkt="TRR", qtd="10,0"):
    """Layout antigo: 11 colunas, sem 'Descricao do Produto'."""
    c = [""] * 11
    c[0], c[1], c[2], c[4], c[8], c[9], c[10] = (
        str(ano), str(mes), comp, prod, uf, mkt, qtd)
    return ";".join(c)


def csv12(linhas, enc="utf-8"):
    return ("\n".join([CAB12, *linhas]) + "\n").encode(enc)


def csv11(linhas, enc="cp1252"):
    """Sem cabecalho, como o Liquidos_Vendas_Historico_2007_a_2017.csv."""
    return ("\n".join(linhas) + "\n").encode(enc)


# --- layout de 11 colunas ---------------------------------------------------

def test_membro_sem_cabecalho_usa_o_layout_de_11_colunas():
    """UF, mercado e quantidade estao deslocados: o resultado prova que foram
    lidos das colunas 8, 9 e 10, nao das 9, 10 e 11."""
    agg = ud.agregar(csv11([linha11(2016, 5, uf="RJ", mkt="REVENDEDOR",
                                    qtd="12,5")]))
    assert agg[("2016-05", "DISTRIB A", "RJ", "REVENDEDOR", "Diesel B")] == pytest.approx(12.5)


def test_primeira_linha_do_membro_sem_cabecalho_nao_e_perdida():
    agg = ud.agregar(csv11([linha11(2016, 5, qtd="1,0"),
                            linha11(2016, 5, qtd="2,0")]))
    assert agg[("2016-05", "DISTRIB A", "SP", "TRR", "Diesel B")] == pytest.approx(3.0)


def test_sem_cabecalho_com_numero_errado_de_colunas_derruba():
    ruim = ";".join(["2016", "5"] + [""] * 6)      # 8 colunas
    with pytest.raises(RuntimeError, match="sem cabecalho|colunas"):
        ud.agregar((ruim + "\n").encode("cp1252"))


def test_cabecalho_de_12_colunas_continua_no_layout_novo():
    agg = ud.agregar(csv12([linha12(2024, 1, uf="MG", mkt="TRR", qtd="4,0")]))
    assert agg[("2024-01", "DISTRIB A", "MG", "TRR", "Diesel B")] == pytest.approx(4.0)


# --- selecao de membros -----------------------------------------------------

@pytest.mark.parametrize("nome,esperado", [
    ("Liquidos_Vendas_Atual.csv", True),
    ("Liquidos_Vendas_Historico_2007_a_2017.csv", True),
    ("Liquidos_Vendas_Historico_2018_a_2023.csv", True),
    # Bases DIFERENTES, com outro grao e outras colunas. Misturar familias foi o
    # erro da primeira versao do relatorio de diagnostico.
    ("Liquidos_Entregas_Distribuidor_Atual.csv", False),
    ("Liquidos_Entregas_Historico.csv", False),
    ("Liquidos_Importacao_de_Distribuidores.csv", False),
    ("leiame.pdf", False),
])
def test_so_membros_de_vendas_entram(nome, esperado):
    assert mod_membros.e_membro_de_vendas(nome) is esperado


# --- agregacao conjunta -----------------------------------------------------

def test_membros_somam_sem_duplicar():
    stats: dict = {}
    agg = ud.agregar_membros([
        ("Liquidos_Vendas_Historico_2007_a_2017.csv",
         csv11([linha11(2016, 12, qtd="5,0")])),
        ("Liquidos_Vendas_Atual.csv",
         csv12([linha12(2024, 1, qtd="7,0")])),
    ], stats)
    assert agg[("2016-12", "DISTRIB A", "SP", "TRR", "Diesel B")] == pytest.approx(5.0)
    assert agg[("2024-01", "DISTRIB A", "SP", "TRR", "Diesel B")] == pytest.approx(7.0)
    assert stats["linhas"] == 2
    assert set(stats["cobertura"]) == {
        "Liquidos_Vendas_Historico_2007_a_2017.csv", "Liquidos_Vendas_Atual.csv"}


def test_membros_sobrepostos_derrubam():
    """Somar o mesmo mes de dois membros o DOBRA, e nenhuma trava de volume
    pegaria isso — o total so cresce."""
    with pytest.raises(RuntimeError, match="sobrepoem"):
        ud.agregar_membros([
            ("Liquidos_Vendas_Historico_2018_a_2023.csv",
             csv12([linha12(2023, 12, qtd="5,0")])),
            ("Liquidos_Vendas_Atual.csv",
             csv12([linha12(2023, 12, qtd="5,0")])),
        ])


def test_buraco_dentro_de_um_membro_derruba():
    """Buraco interno a um membro nao e reorganizacao da ANP: e arquivo
    incompleto."""
    with pytest.raises(RuntimeError, match="buraco"):
        ud.agregar_membros([
            ("Liquidos_Vendas_Atual.csv",
             csv12([linha12(2024, 1), linha12(2024, 3)])),
        ])


# --- heranca de lacuna interior --------------------------------------------

def anterior_com(meses, qtd=10.0):
    agg = {(m, "DISTRIB A", "SP", "TRR", "Diesel B"): qtd for m in meses}
    return ud.gerar_data_js(agg)


def test_lacuna_interior_e_herdada_e_marcada():
    """O caso de 2017: ausente de todos os membros, presente no data.js."""
    anterior = anterior_com(["2016-12", "2017-06", "2018-01"])
    agg = {("2016-12", "D", "SP", "TRR", "Diesel B"): 1.0,
           ("2018-01", "D", "SP", "TRR", "Diesel B"): 1.0}
    herdados = mod_membros.herdar_lacunas(agg, anterior)
    assert herdados == ["2017-06"]
    assert ("2017-06", "DISTRIB A", "SP", "TRR", "Diesel B") in agg


def test_fonte_completa_nao_herda_nada():
    """Se a ANP voltar a publicar 2017, a lacuna some e nada e herdado."""
    anterior = anterior_com(["2016-12", "2017-06", "2018-01"])
    agg = {(m, "D", "SP", "TRR", "Diesel B"): 1.0
           for m in ["2016-12", "2017-06", "2018-01"]}
    assert mod_membros.herdar_lacunas(agg, anterior) == []


def test_ponta_que_encolheu_nao_vira_heranca():
    """Truncamento corta a PONTA, e ponta nao e lacuna interior — tem de
    continuar caindo na trava de regressao, nao ser remendado."""
    anterior = anterior_com(["2024-01", "2024-02", "2024-03"])
    agg = {("2024-01", "D", "SP", "TRR", "Diesel B"): 1.0}
    assert mod_membros.herdar_lacunas(agg, anterior) == []


def test_lacuna_acima_do_teto_derruba():
    meses = [f"{2017 + i // 12}-{i % 12 + 1:02d}" for i in range(14)]
    anterior = anterior_com(["2016-12", *meses, "2019-01"])
    agg = {("2016-12", "D", "SP", "TRR", "Diesel B"): 1.0,
           ("2019-01", "D", "SP", "TRR", "Diesel B"): 1.0}
    with pytest.raises(RuntimeError, match="teto"):
        mod_membros.herdar_lacunas(agg, anterior)


def test_lacuna_que_cresce_derruba():
    """Lacuna nova e hipotese sobre a origem, nao coisa para remendar."""
    anterior = anterior_com(["2016-12", "2017-06", "2017-07", "2018-01"])
    anterior["herdados"] = ["2017-06"]
    agg = {("2016-12", "D", "SP", "TRR", "Diesel B"): 1.0,
           ("2018-01", "D", "SP", "TRR", "Diesel B"): 1.0}
    with pytest.raises(RuntimeError, match="CRESCEU"):
        mod_membros.herdar_lacunas(agg, anterior)


def test_lacuna_que_encolhe_passa():
    anterior = anterior_com(["2016-12", "2017-06", "2018-01"])
    anterior["herdados"] = ["2017-05", "2017-06"]
    agg = {("2016-12", "D", "SP", "TRR", "Diesel B"): 1.0,
           ("2018-01", "D", "SP", "TRR", "Diesel B"): 1.0}
    assert mod_membros.herdar_lacunas(agg, anterior) == ["2017-06"]


def test_sem_anterior_nao_herda():
    assert mod_membros.herdar_lacunas({("2024-01", "D", "S", "T", "P"): 1.0}, None) == []
