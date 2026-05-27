from canvas_course_downloads.scraper import sanitize, unique_path


class TestSanitize:
    def test_removes_special_characters(self):
        assert sanitize('file<>:"/\\|?*name') == "file_________name"

    def test_strips_whitespace(self):
        assert sanitize("  hello  ") == "hello"

    def test_preserves_normal_names(self):
        assert sanitize("lecture_notes.pdf") == "lecture_notes.pdf"

    def test_empty_string(self):
        assert sanitize("") == ""


class TestUniquePath:
    def test_returns_original_when_no_conflict(self, tmp_path):
        result = unique_path(tmp_path, "file.txt")
        assert result == tmp_path / "file.txt"

    def test_appends_suffix_on_conflict(self, tmp_path):
        (tmp_path / "file.txt").write_text("existing")
        result = unique_path(tmp_path, "file.txt")
        assert result == tmp_path / "file_2.txt"

    def test_increments_suffix(self, tmp_path):
        (tmp_path / "file.txt").write_text("existing")
        (tmp_path / "file_2.txt").write_text("existing")
        result = unique_path(tmp_path, "file.txt")
        assert result == tmp_path / "file_3.txt"

    def test_handles_no_extension(self, tmp_path):
        (tmp_path / "README").write_text("existing")
        result = unique_path(tmp_path, "README")
        assert result == tmp_path / "README_2"
