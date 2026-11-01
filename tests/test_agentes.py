"""Canonicalizacao de nomes de agente regulado.

O HHI e quadratico na participacao: um agente de 20% contribui 400 pontos;
partido em dois de 10%, contribui 200. Rotulo duplicado derruba o indice quase
pela metade sem mudar um metro cubico de volume, e nenhuma trava de volume
pega. Estes testes travam os dois lados do risco:

- fundir de menos (duplicata passa) e fundir DEMAIS (dois agentes distintos
  viram um), sendo o segundo o erro que nos mesmos inventariamos.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import agentes  # noqa: E402

# Caso real do data.js: mesma marca, duas pessoas juridicas. NAO pode fundir.
ARAPETRO = ["ARAPETRO DISTRIBUIDORA DE COMBUSTIVEIS LTDA",
            "ARAPETRO DISTRIBUIDORA DE PETRÓLEO LTDA."]


def cubo(*pares, mes="2026-08"):
    """(agente, volume) -> cubo agregado com uma linha por agente."""
    return {(mes, comp, "SP", "TRR", "Diesel B"): vol for comp, vol in pares}


# --- normalizacao tipografica (automatica, segura) --------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("  VIBRA ENERGIA S.A.  ", "VIBRA ENERGIA S.A."),
    ("VIBRA  ENERGIA", "VIBRA ENERGIA"),
    ("VIBRA\tENERGIA", "VIBRA ENERGIA"),
])
def test_normalizar_tira_ruido_de_espaco(entrada, esperado):
    assert agentes.normalizar(entrada) == esperado


def test_normalizar_nao_mexe_em_acento_nem_caixa():
    """Tirar acento ou mudar caixa aproximaria nomes que a ANP trata como
    agentes diferentes. A normalizacao automatica nao pode fazer isso."""
    nome = "ATLÂNTICA PRODUTOS DE PETRÓLEO LTDA."
    assert agentes.normalizar(nome) == nome


def test_normalizar_funde_so_grafias_identicas():
    agg = cubo(("VIBRA  ENERGIA", 10.0), ("VIBRA ENERGIA", 5.0))
    novo, fusoes = agentes.aplicar(agg, {})
    assert novo[("2026-08", "VIBRA ENERGIA", "SP", "TRR", "Diesel B")] == pytest.approx(15.0)
    assert list(fusoes) == ["VIBRA ENERGIA"]


# --- deteccao (reporta, nao aplica) -----------------------------------------

def test_detecta_variante_por_sufixo_societario():
    grupos = agentes.detectar_variantes(["POSTO X LTDA", "POSTO X S.A.", "POSTO Y"])
    assert list(grupos) == ["POSTO X"]
    assert grupos["POSTO X"] == ["POSTO X LTDA", "POSTO X S.A."]


def test_deteccao_nao_altera_os_dados():
    """Candidato nao e alias. Sem entrada no mapa, nada funde."""
    agg = cubo(("POSTO X LTDA", 10.0), ("POSTO X S.A.", 10.0))
    novo, fusoes = agentes.aplicar(agg, {})
    assert fusoes == {}
    assert len({k[1] for k in novo}) == 2


def test_arapetro_nao_e_fundido_automaticamente():
    """Mesma marca, CNPJs distintos — o caso real que condena regra por
    semelhanca."""
    agg = cubo((ARAPETRO[0], 10.0), (ARAPETRO[1], 10.0))
    novo, _ = agentes.aplicar(agg, {})
    assert len({k[1] for k in novo}) == 2
    # e a deteccao tambem nao os agrupa: as raizes diferem
    assert agentes.detectar_variantes(ARAPETRO) == {}


# --- mapa de aliases (fusao explicita) --------------------------------------

def mapa(tmp_path, de, motivos=None):
    p = tmp_path / "aliases.json"
    p.write_text(json.dumps({"de": de,
                             "motivos": motivos if motivos is not None
                             else {k: "teste" for k in de}}), encoding="utf-8")
    return p


def test_alias_funde_e_soma(tmp_path):
    p = mapa(tmp_path, {"POSTO X LTDA": "POSTO X S.A."})
    agg = cubo(("POSTO X LTDA", 10.0), ("POSTO X S.A.", 6.0))
    novo, fusoes = agentes.aplicar(agg, agentes.carregar_aliases(p))
    assert novo[("2026-08", "POSTO X S.A.", "SP", "TRR", "Diesel B")] == pytest.approx(16.0)
    assert fusoes == {"POSTO X S.A.": ["POSTO X LTDA"]}


def test_alias_sem_motivo_derruba(tmp_path):
    """Alias sem motivo registrado e decisao sem rastro."""
    p = mapa(tmp_path, {"A": "B"}, motivos={})
    with pytest.raises(RuntimeError, match="motivo"):
        agentes.carregar_aliases(p)


def test_alias_em_cadeia_derruba(tmp_path):
    """A->B e B->C dependem da ordem de aplicacao: ambiguo, logo proibido."""
    p = mapa(tmp_path, {"A": "B", "B": "C"})
    with pytest.raises(RuntimeError, match="cadeia"):
        agentes.carregar_aliases(p)


def test_alias_para_si_mesmo_derruba(tmp_path):
    p = mapa(tmp_path, {"A": "A"})
    with pytest.raises(RuntimeError, match="si mesmo"):
        agentes.carregar_aliases(p)


def test_alias_com_destino_inexistente_derruba(tmp_path):
    """Erro de digitacao no mapa falharia em silencio: a fusao simplesmente
    nao aconteceria e ninguem perceberia."""
    p = mapa(tmp_path, {"POSTO X LTDA": "POSTO X S.A"})   # falta o ponto final
    agg = cubo(("POSTO X LTDA", 10.0), ("POSTO X S.A.", 6.0))
    with pytest.raises(RuntimeError, match="nao aparece nos dados"):
        agentes.aplicar(agg, agentes.carregar_aliases(p))


def test_fusao_excessiva_derruba(tmp_path):
    """Mapa que funde 10% dos agentes nao e limpeza de grafia."""
    de = {f"AGENTE {i:03d}": "CANONICO" for i in range(40)}
    p = mapa(tmp_path, de)
    agg = cubo(("CANONICO", 1.0), *[(f"AGENTE {i:03d}", 1.0) for i in range(40)])
    with pytest.raises(RuntimeError, match="acima do limite"):
        agentes.aplicar(agg, agentes.carregar_aliases(p))


def test_mapa_ausente_nao_quebra(tmp_path):
    assert agentes.carregar_aliases(tmp_path / "nao_existe.json") == {}


# --- efeito no HHI, que e o motivo de tudo isto -----------------------------

def test_hhi_duplicata_derruba_o_indice():
    """Um agente de 50% partido em dois de 25% custa 1.250 pontos de HHI."""
    inteiro = cubo(("GRANDE", 50.0), ("OUTRO A", 25.0), ("OUTRO B", 25.0))
    partido = cubo(("GRANDE LTDA", 25.0), ("GRANDE S.A.", 25.0),
                   ("OUTRO A", 25.0), ("OUTRO B", 25.0))
    h_inteiro = agentes.hhi_do_mes(inteiro, "2026-08")
    h_partido = agentes.hhi_do_mes(partido, "2026-08")
    assert h_inteiro == pytest.approx(3750.0)
    assert h_partido == pytest.approx(2500.0)
    assert h_inteiro - h_partido == pytest.approx(1250.0)


def test_hhi_de_mes_vazio_e_zero():
    assert agentes.hhi_do_mes({}, "2026-08") == 0.0


# --- o mapa que esta no repositorio -----------------------------------------

def test_mapa_do_repo_e_valido():
    """O arquivo versionado tem de passar nas proprias travas."""
    caminho = os.path.join(os.path.dirname(__file__), "..", "scripts",
                           "aliases_agentes.json")
    agentes.carregar_aliases(caminho)   # nao levanta


def test_todo_candidato_real_esta_declarado():
    """Varredura no artefato: todo candidato detectado tem de estar declarado.

    Em `de` (fundir) ou em `revisados` (olhado e nao fundido, com motivo).
    Candidato NOVO quebra a CI de proposito: e assim que se descobre no dia,
    e nao meses depois, que a serie de um agente esta partida em duas grafias.

    Foi este teste que apontou os quatro candidatos quando a serie passou de
    2017-2026 para 2007-2026 -- inclusive a armadilha do ALE/ALESAT.
    """
    base = os.path.join(os.path.dirname(__file__), "..")
    import data_js
    d = data_js.carregar(os.path.join(base, "data.js"))
    if d is None:                              # pragma: no cover
        pytest.skip("sem artefato de dados no repositorio")

    mapa = os.path.join(base, "scripts", "aliases_agentes.json")
    declarados = set(agentes.carregar_revisados(mapa))
    for variante, canonico in agentes.carregar_aliases(mapa).items():
        declarados.add(agentes.raiz_comparavel(canonico))

    nao_declarados = sorted(set(agentes.detectar_variantes(d["comps"])) - declarados)
    assert not nao_declarados, (
        f"{len(nao_declarados)} candidato(s) a alias sem decisao registrada: "
        f"{nao_declarados}. Olhe as janelas de cada grafia e registre em "
        "scripts/aliases_agentes.json, em 'de' (fundir) ou 'revisados' (nao fundir).")


def test_revisados_tem_motivo_de_verdade():
    """Motivo de uma linha nao e motivo: tem de dizer o que foi medido."""
    mapa = os.path.join(os.path.dirname(__file__), "..", "scripts",
                        "aliases_agentes.json")
    for raiz, motivo in agentes.carregar_revisados(mapa).items():
        assert len(motivo) > 80, f"{raiz}: motivo curto demais"
