import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("extract_schema", Path(__file__).with_name("extract-schema.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExtractSchemaTest(unittest.TestCase):
    def test_quoted_semicolon_and_escaped_quotes(self):
        ddl = "CREATE TABLE `t` (`v` text COMMENT 'a; b\\\'c') ENGINE=InnoDB COMMENT='x; y';"
        result = module.extract_schema(ddl + "\nINSERT INTO `t` VALUES ('private');\n")
        self.assertIn(ddl, result)
        self.assertNotIn("private", result)
        self.assertNotIn("INSERT", result)

    def test_duplicate_and_unterminated_are_rejected(self):
        ddl = "CREATE TABLE `t` (`id` int) ENGINE=InnoDB;"
        for source in (ddl + "\n" + ddl, "CREATE TABLE `t` (`v` text) ENGINE=InnoDB COMMENT='missing;"):
            with self.assertRaises(ValueError):
                module.extract_schema(source)

    def test_upstream_contains_only_69_empty_table_definitions(self):
        source = Path(__file__).resolve().parents[1] / "db/teachingopen2.8.sql"
        result = module.extract_schema(source.read_text(encoding="utf-8"))
        self.assertEqual(result.count("\nCREATE TABLE "), 69)
        self.assertNotIn("INSERT INTO", result)
        self.assertNotIn("DROP TABLE", result)


if __name__ == "__main__":
    unittest.main()
