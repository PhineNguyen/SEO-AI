"""Structural verification tests for TASK-001 repository initialization.

Uses only Python standard library modules so it can run prior to installing
third-party packages in TASK-002.
"""

import importlib
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestProjectStructure(unittest.TestCase):
    """Verify repository directory layout, package imports, config templates, and docs."""

    def test_backend_packages_exist_and_importable(self) -> None:
        required_packages = [
            "app",
            "app.api",
            "app.api.v1",
            "app.agents",
            "app.agents.nodes",
            "app.agents.prompts",
            "app.connectors",
            "app.services",
            "app.models",
            "app.schemas",
            "app.repositories",
            "app.database",
            "app.workers",
            "app.utils",
            "tests",
        ]
        for package_name in required_packages:
            package_init = BACKEND_DIR / Path(*package_name.split(".")) / "__init__.py"
            self.assertTrue(package_init.is_file(), f"Missing {package_init}")
            module = importlib.import_module(package_name)
            self.assertIsNotNone(module.__doc__, f"Missing module docstring in {package_name}")

        self.assertTrue((BACKEND_DIR / "alembic" / "versions").is_dir())
        self.assertTrue((BACKEND_DIR / "tests" / "fixtures").is_dir())
        for manifest in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements-ml.txt"):
            self.assertTrue((BACKEND_DIR / manifest).is_file(), f"Missing backend/{manifest}")

    def test_frontend_structure_and_package_json(self) -> None:
        required_dirs = [
            FRONTEND_DIR / "src" / "pages",
            FRONTEND_DIR / "src" / "components",
            FRONTEND_DIR / "src" / "features" / "projects",
            FRONTEND_DIR / "src" / "features" / "research",
            FRONTEND_DIR / "src" / "features" / "keyword-review",
            FRONTEND_DIR / "src" / "features" / "clustering-review",
            FRONTEND_DIR / "src" / "features" / "content-brief",
            FRONTEND_DIR / "src" / "services",
        ]
        for directory in required_dirs:
            self.assertTrue(directory.is_dir(), f"Missing frontend directory {directory}")

        package_json_path = FRONTEND_DIR / "package.json"
        self.assertTrue(package_json_path.is_file(), "Missing frontend/package.json")
        package_data = json.loads(package_json_path.read_text(encoding="utf-8"))
        dependencies = package_data.get("dependencies", {})
        self.assertIn("@mui/material", dependencies)
        self.assertIn("@mui/x-data-grid", dependencies)
        self.assertIn("react", dependencies)

    def test_env_example_keys_and_no_real_secrets(self) -> None:
        env_example_path = REPO_ROOT / ".env.example"
        self.assertTrue(env_example_path.is_file(), "Missing .env.example")
        content = env_example_path.read_text(encoding="utf-8")

        required_keys = [
            "APP_NAME",
            "DATABASE_URL",
            "REDIS_URL",
            "CELERY_BROKER_URL",
            "JWT_SECRET_KEY",
            "OAUTH_TOKEN_ENCRYPTION_KEY",
            "OPENAI_API_KEY",
            "EMBEDDING_PROVIDER",
            "OPENAI_EMBEDDING_MODEL",
            "DATAFORSEO_LOGIN",
            "DATAFORSEO_PASSWORD",
            "SEMRUSH_API_KEY",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "VITE_API_BASE_URL",
        ]
        defined_keys = {
            line.split("=", 1)[0].strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#") and "=" in line
        }
        for key in required_keys:
            self.assertIn(key, defined_keys, f"Missing key {key} in .env.example")

        forbidden_secret_patterns = [
            r"sk-proj-[A-Za-z0-9_-]{10,}",
            r"sk-live-[A-Za-z0-9_-]{10,}",
            r"AIza[0-9A-Za-z_-]{20,}",
        ]
        for pattern in forbidden_secret_patterns:
            self.assertIsNone(
                re.search(pattern, content),
                f"Potential real secret pattern detected in .env.example: {pattern}",
            )

    def test_core_documentation_exists_and_non_empty(self) -> None:
        required_docs = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "PROJECT_STATUS.md",
            REPO_ROOT / "TASKS.md",
            REPO_ROOT / "CHANGELOG.md",
            REPO_ROOT / "docs" / "ARCHITECTURE.md",
            REPO_ROOT / "docs" / "DATABASE.md",
        ]
        for doc_path in required_docs:
            self.assertTrue(doc_path.is_file(), f"Missing documentation file {doc_path}")
            self.assertGreater(doc_path.stat().st_size, 100, f"Documentation file too small: {doc_path}")

    def test_gitignore_protects_secrets(self) -> None:
        gitignore_path = REPO_ROOT / ".gitignore"
        self.assertTrue(gitignore_path.is_file(), "Missing .gitignore")
        lines = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()}
        self.assertIn(".env", lines)
        self.assertIn("__pycache__/", lines)
        self.assertIn("frontend/node_modules/", lines)


if __name__ == "__main__":
    unittest.main()
