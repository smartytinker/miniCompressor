from minicompressor.cli import main


def test_compress_then_decompress_round_trip(tmp_path, capsys):
    src = tmp_path / "input.txt"
    src.write_bytes(b"hello hello hello hello hello\n" * 50)

    rc = main([str(src)])
    assert rc == 0
    compressed = tmp_path / "input.txt.mc"
    assert compressed.exists()
    assert src.exists()  # original is kept

    out = capsys.readouterr().out
    assert "Compressed" in out
    assert "ratio" in out

    rc = main(["-d", str(compressed)])
    assert rc == 0
    restored = tmp_path / "input.txt"
    assert restored.read_bytes() == src.read_bytes()
    assert compressed.exists()  # .mc is kept


def test_explicit_output_path(tmp_path):
    src = tmp_path / "data.bin"
    src.write_bytes(b"some bytes to compress" * 10)
    out = tmp_path / "custom.mc"

    rc = main(["-o", str(out), str(src)])
    assert rc == 0
    assert out.exists()

    restored = tmp_path / "restored.bin"
    rc = main(["-d", "-o", str(restored), str(out)])
    assert rc == 0
    assert restored.read_bytes() == src.read_bytes()


def test_missing_file_errors(capsys):
    rc = main(["/no/such/file.txt"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no such file" in err


def test_decompress_without_mc_suffix_and_no_output_errors(tmp_path, capsys):
    src = tmp_path / "plain.txt"
    src.write_bytes(b"data")
    rc = main(["-d", str(src)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "error:" in err
