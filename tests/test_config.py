import os
from pathlib import Path
import unittest

from deep_stock_analysis.config import PipelineConfig, load_dotenv


class ConfigTests(unittest.TestCase):
    def test_load_dotenv_reads_values_without_overriding_shell(self):
        env_path = Path("/private/tmp/deep-stock-test.env")
        env_path.write_text(
            "\n".join(
                [
                    "POLYGON_API_KEY=from-file",
                    "FMP_API_KEY='quoted-fmp'",
                    "MAX_WORKERS=7",
                    "SHORTLIST_MIN_SCORE=61",
                ]
            )
        )
        original_polygon = os.environ.get("POLYGON_API_KEY")
        try:
            os.environ["POLYGON_API_KEY"] = "from-shell"
            os.environ.pop("FMP_API_KEY", None)
            os.environ.pop("MAX_WORKERS", None)
            os.environ.pop("SHORTLIST_MIN_SCORE", None)

            load_dotenv(env_path)

            self.assertEqual(os.environ["POLYGON_API_KEY"], "from-shell")
            self.assertEqual(os.environ["FMP_API_KEY"], "quoted-fmp")
            self.assertEqual(os.environ["MAX_WORKERS"], "7")
        finally:
            if original_polygon is None:
                os.environ.pop("POLYGON_API_KEY", None)
            else:
                os.environ["POLYGON_API_KEY"] = original_polygon
            os.environ.pop("FMP_API_KEY", None)
            os.environ.pop("MAX_WORKERS", None)
            os.environ.pop("SHORTLIST_MIN_SCORE", None)
            env_path.unlink(missing_ok=True)

    def test_config_uses_dotenv_defaults(self):
        env_path = Path(".env")
        original_text = env_path.read_text() if env_path.exists() else None
        try:
            env_path.write_text("POLYGON_API_KEY=polygon\nFMP_API_KEY=fmp\nROIC_API_KEY=roic\nMAX_WORKERS=3\n")
            os.environ.pop("POLYGON_API_KEY", None)
            os.environ.pop("FMP_API_KEY", None)
            os.environ.pop("ROIC_API_KEY", None)
            os.environ.pop("MAX_WORKERS", None)

            config = PipelineConfig.from_env()

            self.assertEqual(config.polygon_api_key, "polygon")
            self.assertEqual(config.fmp_api_key, "fmp")
            self.assertEqual(config.roic_api_key, "roic")
            self.assertEqual(config.max_workers, 3)
        finally:
            if original_text is None:
                env_path.unlink(missing_ok=True)
            else:
                env_path.write_text(original_text)
            os.environ.pop("POLYGON_API_KEY", None)
            os.environ.pop("FMP_API_KEY", None)
            os.environ.pop("ROIC_API_KEY", None)
            os.environ.pop("MAX_WORKERS", None)


if __name__ == "__main__":
    unittest.main()
