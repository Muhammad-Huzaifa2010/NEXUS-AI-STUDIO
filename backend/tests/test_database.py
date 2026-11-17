import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
