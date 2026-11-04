import json

from radar_moradia import pipeline
from radar_moradia.dedup import mark_duplicates
from radar_moradia.models import Listing
from radar_moradia.normalize import normalize
from radar_moradia.scoring import score
from radar_moradia.sources.base import Source, SourceResult
from radar_moradia.storage import Store


def L(**kw):
    base = dict(fonte="t", id_fonte="1", url="https://x/1", titulo="Kitnet no Centro",
                bairro="Centro", municipio="Paulínia", aluguel=800)
    base.update(kw)
    return normalize(Listing(**base))


def test_categorias(cfg):
    assert score(L(aluguel=850), cfg).categoria == "prioridade"
    assert score(L(aluguel=1000), cfg).categoria == "elegivel"
    # condomínio empurra o total acima do teto
    assert score(L(aluguel=1000, condominio=200), cfg).categoria != "elegivel"
    assert score(L(aluguel=2000), cfg).categoria == "descartado"


def test_excepcional_separado(cfg):
    top = L(aluguel=1250, titulo="Kitnet mobiliada individual", descricao=(
        "Kitnet mobiliada com geladeira e fogão. Água, luz e internet inclusas. Sem fiador."))
    assert score(top, cfg).categoria == "excepcional"
    comum = L(aluguel=1250)
    assert score(comum, cfg).categoria == "descartado"


def test_regiao_e_tipo(cfg):
    assert score(L(bairro="Barão Geraldo", municipio="Campinas"), cfg).regiao == "Barão Geraldo"
    assert score(L(bairro="Cidade Universitária", municipio="Campinas"), cfg).regiao == "Barão Geraldo"
    assert score(L(bairro="Centro", municipio="Campinas"), cfg).categoria == "descartado"
    assert score(L(bairro="Jardim Ypê", municipio="Paulínia"), cfg).categoria == "prioridade"
    assert score(L(bairro="Centro", municipio="Sumaré"), cfg).categoria == "descartado"
    assert score(L(titulo="Sala para alugar, 30 m²"), cfg).categoria == "descartado"
    assert score(L(titulo="Casa com 3 quartos", quartos=3), cfg).categoria == "descartado"


def test_compartilhado_penaliza(cfg):
    a = score(L(), cfg).pontuacao
    b = score(L(descricao="Quarto em casa, banheiro compartilhado"), cfg).pontuacao
    assert b < a


def test_status_ciclo(tmp_path):
    st = Store(tmp_path / "db.sqlite")
    assert st.upsert(L(uid="u1"), "t1").status == "novo"
    assert st.upsert(L(uid="u1"), "t2").status == "repetido"
    assert st.upsert(L(uid="u1", aluguel=750), "t3").status == "atualizado"
    gone = st.mark_unavailable("t", set(), "t4")
    assert [g.uid for g in gone] == ["u1"] and st.get("u1").status == "indisponivel"
    assert st.upsert(L(uid="u1", aluguel=750), "t5").status == "atualizado"  # reapareceu
    assert st.get("u1").primeira_vez == "t1"
    st.close()


def test_upsert_preserva_detalhes_conhecidos(tmp_path):
    st = Store(tmp_path / "db.sqlite")
    st.upsert(L(uid="u1", telefone="19997950079"), "t1")
    again = st.upsert(L(uid="u1"), "t2")
    assert again.telefone == "19997950079" and again.status == "repetido"
    st.close()


def test_duplicatas():
    a = L(uid="a", telefone="19997950079", primeira_vez="1")
    b = L(uid="b", id_fonte="2", fonte="outra", telefone="19997950079", primeira_vez="2")
    c = L(uid="c", id_fonte="3", aluguel=1500)
    mark_duplicates([a, b, c])
    assert a.duplicata_de is None and b.duplicata_de == "a" and c.duplicata_de is None


class FakeSource(Source):
    nome = "fake"
    payload: list = []
    ok = True

    def fetch(self):
        return SourceResult(fonte=self.nome, listings=[Listing(**d) for d in self.payload],
                            ok=self.ok, ids_vistos={d["id_fonte"] for d in self.payload},
                            cobertura_completa=self.ok)


class Boom(Source):
    nome = "boom"

    def fetch(self):
        raise RuntimeError("explodiu")


def test_pipeline_fim_a_fim(tmp_path, cfg, monkeypatch):
    FakeSource.payload = [
        dict(fonte="fake", id_fonte="1", url="https://x/1", titulo="Kitnet mobiliada",
             bairro="Centro", municipio="Paulínia", aluguel=800,
             descricao="Água e luz inclusas. WhatsApp (19) 99795-0079"),
        dict(fonte="fake", id_fonte="2", url="https://x/2", titulo="Sala comercial",
             bairro="Centro", municipio="Paulínia", aluguel=900),
    ]
    monkeypatch.setitem(pipeline.REGISTRY, "fake", FakeSource)
    monkeypatch.setitem(pipeline.REGISTRY, "boom", Boom)
    cfg["fontes"] = {"fake": {"ativa": True, "modulo": "fake"},
                     "boom": {"ativa": True, "modulo": "boom"}}
    out = tmp_path / "rep"
    r1 = pipeline.run(cfg, str(tmp_path / "db.sqlite"), str(out))
    assert r1["prioridade"] == 1
    assert {f["fonte"]: f["ok"] for f in r1["fontes"]} == {"fake": True, "boom": False}
    js = json.loads((out / "relatorio.json").read_text())
    p = js["prioridade"][0]
    assert p["whatsapp_link"] == "https://wa.me/5519997950079"
    assert p["status"] == "novo" and set(p["contas_incluidas"]) == {"agua", "luz"}
    md = (out / "relatorio.md").read_text()
    assert "Kitnet mobiliada" in md and "Sala comercial" not in md
    assert "boom | falhou" in md

    # 2ª execução: anúncio 1 sumiu da fonte (coleta completa) => indisponível
    FakeSource.payload = FakeSource.payload[1:]
    pipeline.run(cfg, str(tmp_path / "db.sqlite"), str(out))
    js = json.loads((out / "relatorio.json").read_text())
    assert js["prioridade"] == [] and js["indisponiveis"][0]["id_fonte"] == "1"


def test_pipeline_falha_nao_marca_indisponivel(tmp_path, cfg, monkeypatch):
    FakeSource.payload = [dict(fonte="fake", id_fonte="1", url="https://x/1", titulo="Kitnet",
                               bairro="Centro", municipio="Paulínia", aluguel=800)]
    FakeSource.ok = True
    monkeypatch.setitem(pipeline.REGISTRY, "fake", FakeSource)
    cfg["fontes"] = {"fake": {"ativa": True, "modulo": "fake"}}
    db = str(tmp_path / "db.sqlite")
    pipeline.run(cfg, db, str(tmp_path))
    FakeSource.payload, FakeSource.ok = [], False
    pipeline.run(cfg, db, str(tmp_path))
    FakeSource.ok = True
    st = Store(db)
    assert st.get(pipeline.make_uid("fake", "1")).status != "indisponivel"
    st.close()
