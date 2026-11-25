import unittest
from unittest.mock import AsyncMock, patch

from app import database


class DatabaseOptionalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_database()

    async def test_database_is_optional_for_local_development(self):
        with patch.object(database.settings, "database_url", ""):
            await database.init_database()
        self.assertFalse(database.persistence_enabled())
        self.assertFalse(await database.database_is_ready())
        self.assertEqual(await database.list_tasks(), [])
        self.assertIsNone(await database.save_task("test request", {"response": "test"}))

    async def test_unavailable_database_does_not_prevent_app_startup(self):
        with (
            patch.object(database.settings, "database_url", "postgresql://unavailable"),
            patch.object(database.asyncpg, "create_pool", new=AsyncMock(
                side_effect=OSError("database unavailable")
            )),
            self.assertLogs("app.database", level="ERROR"),
        ):
            await database.init_database()

        self.assertFalse(database.persistence_enabled())
        self.assertFalse(await database.database_is_ready())


if __name__ == "__main__":
    unittest.main()
