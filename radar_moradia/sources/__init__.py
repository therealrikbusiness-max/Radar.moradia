"""Registro das fontes. Para adicionar uma fonte: crie o módulo, registre aqui
e configure em config.yaml (seção `fontes`)."""
from .chavesnamao import ChavesNaMaoMCP
from .vrsync_feed import VRSyncFeed

REGISTRY = {
    "chavesnamao": ChavesNaMaoMCP,
    "vrsync": VRSyncFeed,
}
