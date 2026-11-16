"""The legacy forge is the parity oracle: prove it loads and sees the full database."""


def test_oracle_loads_whole_database(all_serials):
    assert len(all_serials) == 9875


def test_oracle_roundtrips(legacy, all_serials):
    assert all(legacy.codec.encode(legacy.codec.decode(s)) == s for s in all_serials[:500])
