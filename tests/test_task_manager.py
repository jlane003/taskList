import unittest
import sqlite3
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from tasklist.task_manager import TaskList


class TestTaskList(unittest.TestCase):

    def setUp(self):
        """Set up a temporary in-memory database and a mock config for each test."""
        self.temp_dir = tempfile.mkdtemp()
        # Patch appdirs to use a temporary directory for testing
        patcher = patch("appdirs.user_data_dir")
        self.mock_user_data_dir = patcher.start()
        self.mock_user_data_dir.return_value = self.temp_dir
        self.addCleanup(patcher.stop)

        # Mock configparser to avoid needing a real config file
        self.mock_config = {
            "trello": {
                "api_key": "test_api_key",
                "token": "test_token",
                "board_id": "test_board_id",
                "list_id": "test_list_id",
            },
            "defaults": {"priority": "1", "category": "General"},
        }

        # Patch configparser.ConfigParser to return our mock config
        patcher = patch("configparser.ConfigParser")
        self.mock_config_parser = patcher.start()
        self.mock_config_parser.return_value.read.return_value = True
        self.mock_config_parser.return_value.__getitem__.side_effect = (
            self.mock_config.__getitem__
        )
        self.mock_config_parser.return_value.__contains__.side_effect = (
            self.mock_config.__contains__
        )
        # Create a mock for the 'defaults' section
        defaults_section_mock = MagicMock()
        defaults_section_mock.getint.side_effect = lambda key, fallback: int(
            self.mock_config["defaults"].get(key, fallback)
        )
        defaults_section_mock.get.side_effect = lambda key, fallback: self.mock_config[
            "defaults"
        ].get(
            key, fallback
        )
        self.mock_config_parser.return_value.__getitem__.side_effect = (
            lambda section: {
                "trello": self.mock_config["trello"],
                "defaults": defaults_section_mock,
            }[section]
        )
        self.addCleanup(patcher.stop)

        # Initialize TaskList with a path, though it's not used due to the mock
        self.task_list = TaskList("dummy_config.ini")

    def tearDown(self):
        """Clean up the temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_add_task_offline(self):
        """Test that a task is saved locally when the network is offline."""
        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("Test task offline", "2025-12-31", 3, "Work")

            # Verify the task was saved to the in-memory database
            with sqlite3.connect(self.task_list.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM pending_tasks")
                tasks = cursor.fetchall()
                self.assertEqual(len(tasks), 1)
                task = dict(tasks[0])
                self.assertEqual(task["description"], "Test task offline")
                self.assertEqual(task["due_date"], "2025-12-31")
                self.assertEqual(task["priority"], 3)
                self.assertEqual(task["category"], "Work")

    @patch("tasklist.task_manager.requests.post")
    def test_add_task_online_success(self, mock_post):
        """Test that a task is uploaded directly when the network is online."""
        mock_post.return_value.status_code = 200

        with patch.object(self.task_list, "check_network", return_value=True):
            self.task_list.add("Test task online", "2025-12-31", 3, "Work")

            # Verify the task was NOT saved locally
            self.assertFalse(self.task_list.has_pending_tasks())
            # Verify that the upload method was called with the correct data
            mock_post.assert_called_once_with(
                self.task_list.trello_url,
                data={
                    "key": "test_api_key",
                    "token": "test_token",
                    "idList": "test_list_id",
                    "name": "Test task online",
                    "desc": "Priority: 3\nCategory: Work",
                    "due": "2025-12-31",
                },
                timeout=10,
            )

    @patch("tasklist.task_manager.requests.post")
    def test_upload_all_tasks_success(self, mock_post):
        """Test uploading all pending tasks successfully."""
        mock_post.return_value.status_code = 200

        # First, add some tasks while "offline"
        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("Task 1", "2025-01-01", 1, "Personal")
            self.task_list.add("Task 2", "2025-01-02", 2, "Work")

        self.assertTrue(self.task_list.has_pending_tasks())

        # Now, go "online" and upload
        with patch.object(self.task_list, "check_network", return_value=True):
            self.task_list.upload()

        # Verify that the local task list is now empty
        self.assertFalse(self.task_list.has_pending_tasks())
        self.assertEqual(mock_post.call_count, 2)
        # Check the data for the first call
        mock_post.assert_any_call(
            self.task_list.trello_url,
            data={
                "key": "test_api_key",
                "token": "test_token",
                "idList": "test_list_id",
                "name": "Task 1",
                "desc": "Priority: 1\nCategory: Personal",
                "due": "2025-01-01",
            },
            timeout=10,
        )
        # Check the data for the second call
        mock_post.assert_any_call(
            self.task_list.trello_url,
            data={
                "key": "test_api_key",
                "token": "test_token",
                "idList": "test_list_id",
                "name": "Task 2",
                "desc": "Priority: 2\nCategory: Work",
                "due": "2025-01-02",
            },
            timeout=10,
        )

    @patch("tasklist.task_manager.requests.post")
    def test_upload_partial_failure(self, mock_post):
        """Test that if one task fails to upload, subsequent tasks are not attempted."""
        # Simulate failure on the second task
        mock_post.side_effect = [
            MagicMock(status_code=200),  # First task succeeds
            MagicMock(status_code=500),  # Second task fails
        ]

        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("Task 1", "2025-01-01", 1, "Personal")
            self.task_list.add("Task 2", "2025-01-02", 2, "Work")

        with patch.object(self.task_list, "check_network", return_value=True):
            self.task_list.upload()

        # Verify that the first task was cleared but the second remains
        remaining_tasks = self.task_list._load_tasks()
        self.assertEqual(len(remaining_tasks), 1)
        self.assertEqual(remaining_tasks[0]["description"], "Task 2")
        self.assertEqual(mock_post.call_count, 2)

    @patch("tasklist.task_manager.requests.get")
    def test_get_trello_tasks_success(self, mock_get):
        """Test fetching Trello tasks successfully."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"id": "1", "name": "Trello Task 1"},
            {"id": "2", "name": "Trello Task 2"},
        ]

        tasks = self.task_list.get_trello_tasks()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["name"], "Trello Task 1")

    @patch("tasklist.task_manager.requests.get")
    def test_get_trello_tasks_failure(self, mock_get):
        """Test fetching Trello tasks with an API failure."""
        mock_get.return_value.status_code = 401
        tasks = self.task_list.get_trello_tasks()
        self.assertEqual(len(tasks), 0)

    @patch("tasklist.task_manager.requests.put")
    def test_archive_task_success(self, mock_put):
        """Test archiving a Trello task successfully."""
        mock_put.return_value.status_code = 200
        result = self.task_list.archive_task("task_id_1")
        self.assertTrue(result)

    @patch("tasklist.task_manager.requests.put")
    def test_archive_task_failure(self, mock_put):
        """Test archiving a Trello task with an API failure."""
        mock_put.return_value.status_code = 404
        result = self.task_list.archive_task("task_id_1")
        self.assertFalse(result)

    def test_delete_pending_task(self):
        """Test deleting a pending task from the local database."""
        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("Task to be deleted")

        self.assertTrue(self.task_list.has_pending_tasks())
        self.task_list.delete_pending_task("Task to be deleted")
        self.assertFalse(self.task_list.has_pending_tasks())

    def test_get_pending_tasks(self):
        """Test retrieving all pending tasks."""
        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("Pending Task 1", "2025-12-01", 1, "Home")
            self.task_list.add("Pending Task 2", "2025-12-02", 2, "Work")

        pending_tasks = self.task_list.get_pending_tasks()
        self.assertEqual(len(pending_tasks), 2)
        self.assertEqual(pending_tasks[0]["description"], "Pending Task 1")
        self.assertEqual(pending_tasks[0]["due_date"], "2025-12-01")
        self.assertEqual(pending_tasks[0]["priority"], 1)
        self.assertEqual(pending_tasks[0]["category"], "Home")

    def test_edit_pending_task(self):
        """Test editing a pending task in the local database."""
        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("Original task", "2025-01-01", 1, "Initial")

        tasks = self.task_list.get_pending_tasks()
        self.assertEqual(len(tasks), 1)
        task_id = tasks[0]["id"]

        # Edit the task
        self.task_list.edit_pending_task(
            task_id, description="Updated task", priority=3
        )

        # Verify the changes
        edited_tasks = self.task_list.get_pending_tasks()
        self.assertEqual(len(edited_tasks), 1)
        edited_task = edited_tasks[0]
        self.assertEqual(edited_task["description"], "Updated task")
        self.assertEqual(edited_task["due_date"], "2025-01-01")  # Should be unchanged
        self.assertEqual(edited_task["priority"], 3)
        self.assertEqual(edited_task["category"], "Initial")  # Should be unchanged

    def test_add_and_get_sub_task(self):
        """Test adding and retrieving a sub-task."""
        with patch.object(self.task_list, "check_network", return_value=False):
            # Add parent task
            self.task_list.add("Parent task")
            parent_tasks = self.task_list.get_pending_tasks()
            self.assertEqual(len(parent_tasks), 1)
            parent_id = parent_tasks[0]["id"]

            # Add sub-task
            self.task_list.add("Sub-task", parent_id=parent_id)

            # Verify sub-task is not in the main list
            self.assertEqual(len(self.task_list.get_pending_tasks()), 1)

            # Verify sub-task is retrievable
            sub_tasks = self.task_list.get_sub_tasks(parent_id)
            self.assertEqual(len(sub_tasks), 1)
            self.assertEqual(sub_tasks[0]["description"], "Sub-task")
            self.assertEqual(sub_tasks[0]["parent_id"], parent_id)

            # Verify has_sub_tasks
            self.assertTrue(self.task_list.has_sub_tasks(parent_id))
            self.assertFalse(self.task_list.has_sub_tasks(sub_tasks[0]["id"]))

    def test_get_pending_tasks_filtered_and_sorted(self):
        """Test filtering and sorting of pending tasks."""
        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("Task A", priority=3, category="Work")
            self.task_list.add("Task B", priority=1, category="Home")
            self.task_list.add("Task C", priority=2, category="Work")

        # Test filtering by category
        work_tasks = self.task_list.get_pending_tasks(category="Work")
        self.assertEqual(len(work_tasks), 2)
        self.assertTrue(all(t["category"] == "Work" for t in work_tasks))

        # Test filtering by priority
        high_priority_tasks = self.task_list.get_pending_tasks(priority=3)
        self.assertEqual(len(high_priority_tasks), 1)
        self.assertEqual(high_priority_tasks[0]["description"], "Task A")

        # Test sorting by priority
        sorted_tasks = self.task_list.get_pending_tasks(sort_by="priority")
        self.assertEqual(len(sorted_tasks), 3)
        self.assertEqual(sorted_tasks[0]["description"], "Task B")  # Priority 1
        self.assertEqual(sorted_tasks[1].get("description"), "Task C")  # Priority 2
        self.assertEqual(sorted_tasks[2].get("description"), "Task A")  # Priority 3

    def test_load_defaults_from_config(self):
        """Test that default priority and category are loaded from config."""
        # Override the default mock config for this specific test
        self.mock_config["defaults"] = {"priority": "2", "category": "Work"}

        # Re-initialize TaskList to pick up the new config
        task_list_with_defaults = TaskList("dummy_config.ini")
        self.assertEqual(task_list_with_defaults.default_priority, 2)
        self.assertEqual(task_list_with_defaults.default_category, "Work")

    def test_search_pending_tasks(self):
        """Test searching for pending tasks in the local database."""
        with patch.object(self.task_list, "check_network", return_value=False):
            self.task_list.add("First task to search for")
            self.task_list.add("Second task that is different")

        results = self.task_list.search_pending_tasks("First task")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["description"], "First task to search for")

        no_results = self.task_list.search_pending_tasks("non-existent")
        self.assertEqual(len(no_results), 0)

    @patch("tasklist.task_manager.requests.get")
    def test_search_trello_cards(self, mock_get):
        """Test searching for cards on Trello."""
        mock_search_response = MagicMock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = {
            "cards": [
                {
                    "id": "card1",
                    "name": "Found Trello Card 1",
                    "idBoard": "board1",
                    "idList": "list1",
                }
            ]
        }

        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.json.return_value = {"name": "List 1"}

        mock_board_response = MagicMock()
        mock_board_response.status_code = 200
        mock_board_response.json.return_value = {"name": "Board 1"}

        mock_all_cards_response = MagicMock()
        mock_all_cards_response.status_code = 200
        mock_all_cards_response.json.return_value = [
            {"id": "other_card_1", "name": "Some other card"},
            {"id": "card1", "name": "Found Trello Card 1"},
            {"id": "other_card_2", "name": "Another card"},
        ]

        # The order of side_effect matters: search, list info, board info, all cards in list
        mock_get.side_effect = [
            mock_search_response,
            mock_list_response,
            mock_board_response,
            mock_all_cards_response,
        ]

        results = self.task_list.search_trello_cards("Found")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Found Trello Card 1")
        self.assertEqual(results[0]["list_name"], "List 1")
        self.assertEqual(results[0]["board_name"], "Board 1")
        self.assertEqual(results[0]["card_number"], 2)  # It's the 2nd card in the list


if __name__ == "__main__":
    unittest.main()
