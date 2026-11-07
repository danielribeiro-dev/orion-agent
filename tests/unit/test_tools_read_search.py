"""v0.5.0 Sprint 4 — read_file avançado, edit_file replace_all, glob e grep."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from orion.runtime.tools.edit_file import EditFileTool
from orion.runtime.tools.glob import GlobTool
from orion.runtime.tools.grep import GrepTool
from orion.runtime.tools.read_file import ReadFileTool

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082"
)


class TestReadFile:
    async def test_numbered_with_offset_and_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_text("".join(f"l{i}\n" for i in range(1, 11)))
        r = await ReadFileTool().run(path=str(f), offset=3, limit=2)
        assert r.output == "     3→l3\n     4→l4\n"
        assert r.metadata["returned_lines"] == 2

    async def test_default_cap_announces_continuation(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        f.write_text("x\n" * 2500)
        r = await ReadFileTool().run(path=str(f))
        assert r.metadata["truncated"] is True
        assert "offset=2001" in r.output

    async def test_long_lines_are_clipped(self, tmp_path: Path) -> None:
        f = tmp_path / "w.txt"
        f.write_text("y" * 5000 + "\n")
        r = await ReadFileTool().run(path=str(f))
        assert "line truncated" in r.output
        assert len(r.output) < 2200

    async def test_binary_is_refused(self, tmp_path: Path) -> None:
        f = tmp_path / "b.bin"
        f.write_bytes(b"\x00\x01\x02")
        assert not (await ReadFileTool().run(path=str(f))).success

    async def test_offset_past_end(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_text("one\n")
        r = await ReadFileTool().run(path=str(f), offset=50)
        assert "beyond the end" in r.output

    async def test_image_is_attached_as_block_source(self, tmp_path: Path) -> None:
        f = tmp_path / "p.png"
        f.write_bytes(PNG)
        r = await ReadFileTool().run(path=str(f))
        assert r.success
        assert r.metadata["image"]["media_type"] == "image/png"
        assert r.metadata["image"]["data"]

    async def test_image_too_large(self, tmp_path: Path) -> None:
        f = tmp_path / "huge.png"
        f.write_bytes(b"0" * (5 * 1024 * 1024 + 1))
        r = await ReadFileTool().run(path=str(f))
        assert not r.success and "limit" in r.error

    @pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext ausente")
    async def test_pdf_text_and_page_validation(self, tmp_path: Path) -> None:
        pdf = tmp_path / "d.pdf"
        pdf.write_bytes(_minimal_pdf("Ola ORION"))
        r = await ReadFileTool().run(path=str(pdf))
        assert r.success and "Ola ORION" in r.output
        assert not (await ReadFileTool().run(path=str(pdf), pages="5-1")).success
        assert not (await ReadFileTool().run(path=str(pdf), pages="abc")).success


def _minimal_pdf(text: str) -> bytes:
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET"
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        content = body if body else f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
        out += f"{i} 0 obj\n{content}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


class TestEditReplaceAll:
    async def test_replace_all(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("foo foo foo")
        r = await EditFileTool().run(path=str(f), target="foo", replacement="bar", replace_all=True)
        assert r.success and f.read_text() == "bar bar bar"
        assert r.metadata["occurrences_found"] == 3

    async def test_ambiguous_still_rejected_without_flag(self, tmp_path: Path) -> None:
        f = tmp_path / "a.py"
        f.write_text("foo foo")
        r = await EditFileTool().run(path=str(f), target="foo", replacement="x")
        assert not r.success and f.read_text() == "foo foo"


class TestGlob:
    async def test_sorted_by_mtime_and_ignores_noise(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        old, new = tmp_path / "src" / "old.py", tmp_path / "src" / "new.py"
        old.write_text("1")
        new.write_text("2")
        os.utime(old, (1, 1))
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "x.py").write_text("3")
        r = await GlobTool().run(pattern="**/*.py", path=str(tmp_path))
        assert r.output.splitlines() == [str(Path("src/new.py")), str(Path("src/old.py"))]

    async def test_limit_and_empty_and_invalid(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("x")
        r = await GlobTool().run(pattern="*.txt", path=str(tmp_path), limit=2)
        assert r.metadata["truncated"] and "3 more" in r.output
        assert (await GlobTool().run(pattern="*.zzz", path=str(tmp_path))).output == "(no matches)"
        assert not (await GlobTool().run(pattern="../*", path=str(tmp_path))).success
        assert not (await GlobTool().run(pattern="*", path=str(tmp_path / "nope"))).success


@pytest.fixture(params=["ripgrep", "python"])
def grep(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> GrepTool:
    if request.param == "python":
        monkeypatch.setattr(shutil, "which", lambda _name: None)
    elif shutil.which("rg") is None:
        pytest.skip("rg ausente")
    return GrepTool()


class TestGrep:
    @pytest.fixture()
    def tree(self, tmp_path: Path) -> Path:
        (tmp_path / "a.py").write_text("alpha\nBeta\ngamma\n")
        (tmp_path / "b.txt").write_text("alpha again\n")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "c.py").write_text("alpha\n")
        return tmp_path

    async def test_files_with_matches_and_glob(self, grep: GrepTool, tree: Path) -> None:
        r = await grep.run(pattern="alpha", path=str(tree), glob="*.py")
        names = {Path(line).name for line in r.output.splitlines()}
        assert names == {"a.py"} or names == {"a.py", "c.py"}  # rg respeita .gitignore, não node_modules
        assert "b.txt" not in names

    async def test_content_with_context_and_case(self, grep: GrepTool, tree: Path) -> None:
        r = await grep.run(
            pattern="beta", path=str(tree / "a.py"), output_mode="content",
            case_insensitive=True, context=1,
        )
        text = r.output
        assert "Beta" in text and "alpha" in text and "gamma" in text

    async def test_count_and_no_match_and_head_limit(self, grep: GrepTool, tree: Path) -> None:
        r = await grep.run(pattern="a", path=str(tree / "a.py"), output_mode="count")
        assert r.success and r.output.strip()
        assert (await grep.run(pattern="zzzzz", path=str(tree))).output == "(no matches)"
        big = tree / "big.txt"
        big.write_text("hit\n" * 50)
        r = await grep.run(pattern="hit", path=str(big), output_mode="content", head_limit=5)
        assert r.metadata["truncated"] and "more lines omitted" in r.output

    async def test_invalid_regex_and_missing_path(self, grep: GrepTool, tmp_path: Path) -> None:
        assert not (await grep.run(pattern="(", path=str(tmp_path))).success
        assert not (await grep.run(pattern="x", path=str(tmp_path / "nope"))).success
        assert not (await grep.run(pattern="")).success
