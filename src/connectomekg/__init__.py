"""connectomekg -- connectomes as KGModule knowledge graphs.

The first corpus is the FlyWire FAFB v783 adult fly brain. The reader schema is
dataset-neutral so hemibrain, MaleCNS and other connectomes plug in later.
"""

from connectomekg.module import ConnectomeKG

__all__ = ["ConnectomeKG"]
__version__ = "0.2.0"
