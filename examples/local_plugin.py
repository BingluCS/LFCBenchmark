"""Demo of explicit local registration: lfcbench --plugin examples.local_plugin list."""
from lfcbench import register_compressor
from lfcbench.compressors import IdentityCompressor


@register_compressor("local.identity")
class LocalIdentity(IdentityCompressor):
    pass
