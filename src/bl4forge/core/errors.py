"""Error vocabulary shared by every module. Modules raise these, never bare Exception."""


class ForgeError(Exception):
    """Base class for everything bl4forge raises on purpose."""


class ConfigError(ForgeError):
    """config.toml is unreadable or has an invalid value."""


class DataMissing(ForgeError):
    """A required data file (manifest, serial database) is absent or unreadable."""


class SerialError(ForgeError):
    """A serial string cannot be decoded, encoded, or transformed."""


class ContractViolation(ForgeError):
    """A module does not honour the port it claims to implement."""


class UndeclaredDependency(ForgeError):
    """A module reached for a neighbour it did not list in `requires`."""


class ModuleUnavailable(ForgeError):
    """The requested module failed to start, or a module it depends on did."""


class SaveError(ForgeError):
    """A save file or its YAML text cannot be decrypted, parsed, or patched (wrong key, corrupt data,
    unknown slot, refused write)."""


class SaveKeyMissing(SaveError):
    """The save key needed for this operation is not configured (`[save]` in config.toml)."""


class LootPakError(ForgeError):
    """The loot-pak builder refused or failed: bad plan, refused output path, a tool failed, or the
    decode-diff gate found a change that was not planned."""
