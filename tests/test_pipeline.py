"""Teste ponta a ponta do `main()`: download → agregação → travas → escrita.

Os outros arquivos testam cada peça isolada. Este exercita o caminho que
realmente rodou em 2026-09-05 e gravou um mês inexistente: baixar, agregar,
classificar, conferir contra o data.js anterior e escrever. Uma peça pode estar
certa sozinha e errada na composição — foi exatamente o que aconteceu, porque
`conferir_contra_anterior` estava correto para o que se propunha e mesmo assim
deixava passar a ponta incompleta.

O download é substituído por um CSV sintético; o resto é o código de produção.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import data_js  # noqa: E402
import resumo_email  # noqa: E402
import update_dashboard as ud  # noqa: E402
from test_agregar import CAB, linha  # noqa: E402


def csv_da_anp(meses_cheios=18, agentes=120, vol=100.0, ponta=None, encolher=None):
    """CSV no formato da ANP: N meses completos e, opcionalmente, uma ponta magra.

    `ponta`    = (n_agentes, volume_por_agente) do mês seguinte ao último cheio.
    `encolher` = (índice_do_mês, fator) para reduzir o volume de um mês do meio
                 sem mexer no número de linhas.
    """
    linhas = []

    def bloco(ano, mes, n, v):
        for a in range(n):
            linhas.append(linha(ano=ano, mes=mes, comp=f"DISTRIB {a:03d}",
                                uf="SP", mkt="TRR", prod="Diesel B",
                                qtd=f"{v:.2f}".replace(".", ",")))
            linhas.append(linha(ano=ano, mes=mes, comp=f"DISTRIB {a:03d}",
                                uf="SP", mkt="TRR", prod="Gasolina C",
                                qtd=f"{v / 2:.2f}".replace(".", ",")))

    for i in range(meses_cheios):
        fator = encolher[1] if encolher and encolher[0] == i else 1.0
        bloco(2025 + i // 12, i % 12 + 1, agentes, vol * fator)
    if ponta:
        i = meses_cheios
        bloco(2025 + i // 12, i % 12 + 1, ponta[0], ponta[1])
    return ("\n".join([CAB, *linhas]) + "\n").encode("latin-1")


@pytest.fixture
def rodar(tmp_path, monkeypatch):
    """Roda main() com um CSV sintético e o data.js apontando para tmp_path."""
    saida = tmp_path / "data.js"
    monkeypatch.setattr(ud, "OUT", saida)
    monkeypatch.setattr(resumo_email, "OUT", saida)

    def executar(conteudo):
        monkeypatch.setattr(ud, "baixar", lambda: conteudo)
        ud.main()
        return data_js.carregar(saida)

    executar.saida = saida
    return executar


def test_rodada_normal_grava_tudo(rodar):
    d = rodar(csv_da_anp())
    assert len(d["months"]) == 18
    assert d["parciais"] == []
    assert d["ultimo_completo"] == d["months"][-1]
    assert d["campos"] == ud.CAMPOS
    assert d["prods"] == ["Diesel B", "Gasolina C"]
    # 120 agentes x 2 produtos x 18 meses
    assert len(d["rows"]) // len(ud.CAMPOS) == 120 * 2 * 18


def test_proveniencia_identifica_o_arquivo(rodar):
    conteudo = csv_da_anp()
    d = rodar(conteudo)
    import hashlib
    assert d["fonte"]["sha256"] == hashlib.sha256(conteudo).hexdigest()[:16]
    assert d["fonte"]["bytes"] == len(conteudo)
    assert d["fonte"]["linhas"] == 120 * 2 * 18
    assert d["fonte"]["descartadas"] == 0


def test_ponta_incompleta_e_marcada_e_nao_contamina(rodar):
    """O caso de 2026-09-05, ponta a ponta."""
    d = rodar(csv_da_anp(ponta=(3, 2.0)))
    magro = d["months"][-1]
    assert d["parciais"] == [magro]
    assert d["ultimo_completo"] == d["months"][-2]
    # O mês continua no arquivo — marcado, não apagado.
    assert magro in d["months"]
    vol = data_js.volume_por_mes(d)
    assert vol[-1] < vol[-2] * 0.05
    # E a manchete do e-mail não é o mês magro.
    r = resumo_email.resumo(d)
    assert r["mes"] == d["months"][-2]
    assert magro in r["aviso_parcial"]


def test_segunda_rodada_com_o_mes_ja_consolidado(rodar):
    """A ANP fecha o mês na rodada seguinte: tem de destravar sozinho."""
    magro = rodar(csv_da_anp(ponta=(3, 2.0)))["months"][-1]
    d = rodar(csv_da_anp(meses_cheios=19))          # mesmo mês, agora cheio
    assert d["parciais"] == []
    assert d["ultimo_completo"] == magro
    assert resumo_email.resumo(d)["mes"] == magro


def test_arquivo_truncado_nao_sobrescreve(rodar):
    """Trava de regressão vista de fora: o data.js bom continua no disco."""
    bom = rodar(csv_da_anp(meses_cheios=18))
    with pytest.raises(RuntimeError, match="regressao"):
        rodar(csv_da_anp(meses_cheios=10))
    assert data_js.carregar(rodar.saida)["months"] == bom["months"]


def test_mes_antigo_encolhendo_nao_sobrescreve(rodar):
    """Contagem de meses e de combinações não mudam; só o volume de um mês cai.

    É o buraco que as travas de contagem deixavam: a ANP republicar o arquivo com
    um mês antigo pela metade passava por elas sem sinal nenhum.
    """
    bom = rodar(csv_da_anp(meses_cheios=18))
    with pytest.raises(RuntimeError, match="encolheram"):
        rodar(csv_da_anp(meses_cheios=18, encolher=(4, 0.5)))
    assert data_js.volume_por_mes(data_js.carregar(rodar.saida)) == \
        data_js.volume_por_mes(bom)


def test_revisao_pequena_da_anp_passa_ponta_a_ponta(rodar):
    """Revisão real (~0,1%) não pode travar a rotina."""
    rodar(csv_da_anp(meses_cheios=18))
    d = rodar(csv_da_anp(meses_cheios=18, encolher=(4, 0.999)))
    assert d["parciais"] == []


def test_layout_mudado_nao_sobrescreve(rodar):
    bom = rodar(csv_da_anp())
    trocado = csv_da_anp().decode("latin-1").replace("Ano;Mes", "Mes;Ano", 1)
    with pytest.raises(RuntimeError, match="cabeçalho"):
        rodar(trocado.encode("latin-1"))
    assert data_js.carregar(rodar.saida)["months"] == bom["months"]


def test_escrita_e_atomica_sem_deixar_temporario(rodar):
    rodar(csv_da_anp())
    assert rodar.saida.exists()
    assert not rodar.saida.with_name(rodar.saida.name + ".tmp").exists()


def test_data_js_gerado_e_relido_identico(rodar):
    """O contrato de leitura tem de reler exatamente o que a rotina escreveu."""
    d = rodar(csv_da_anp(ponta=(3, 2.0)))
    idx, passo = data_js.indices(d)
    assert passo == len(ud.CAMPOS)
    assert idx["qtd"] == len(ud.CAMPOS) - 1
    assert data_js.ultimo_mes_completo(d) == d["months"][-2]
    assert len(data_js.meses_completos(d)) == len(d["months"]) - 1
