"""`serve` listens on loopback only unless --allow-remote is given. Needs no game data."""
import argparse

import pytest

from bl4forge.cli._commands import cmd_serve
from bl4forge.cli._core import CliError
from bl4forge.cli._parser import build_parser


def test_default_host_is_loopback():
    args = build_parser().parse_args(["serve"])
    assert args.host == "127.0.0.1" and args.allow_remote is False


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.10", "::", "example.invalid"])
def test_non_loopback_host_is_refused_without_flag(host):
    args = argparse.Namespace(host=host, port=0, open=False, quiet=True, allow_remote=False)
    with pytest.raises(CliError) as ex:
        cmd_serve(None, args)
    assert "--allow-remote" in ex.value.message
