import os
import logging
import requests
import appdirs
from typing import List
import configparser
import sqlite3

# Define app constants for appdirs
APP_NAME = "tasklist"
APP_AUTHOR = "TaskList"


class TaskList:
    """
    Manage tasks locally and with Trello integration.

    Configuration is loaded from an external file.

    Attributes:
        api_key (str): Trello API key.
        token (str): Trello API token.
        list_id (str): Trello list ID.
        db_path (str): Path to the SQLite database file.
        trello_url (str): Trello API endpoint for card creation.
    """

    def __init__(self, config_path: str):
        """
        Initialize TaskList from configuration file.

        This method loads Trello API credentials from the [trello] section
        and default task attributes from the optional [defaults] section.

        Args:
            config_path (str): Path to the INI config file.
        """
        config = configparser.ConfigParser()
        try:
            loaded = config.read(os.path.expanduser(config_path))
        except configparser.Error as e:
            raise ValueError(f"Error parsing config file at {config_path}: {e}")

        if not loaded:
            raise FileNotFoundError(f"Could not read config file at {config_path}")

        try:
            trello_config = config["trello"]
            self.api_key = os.environ.get("TRELLO_API_KEY") or trello_config.get(
                "api_key"
            )
            self.token = os.environ.get("TRELLO_API_TOKEN") or trello_config.get(
                "token"
            )
            self.board_id = trello_config["board_id"]
            self.list_id = trello_config["list_id"]
        except KeyError:
            raise ValueError(
                f"Config file at {config_path} is missing a required key in the [trello] section "
                "(api_key, token, board_id, or list_id). "
                "Please run 'tasklist configure' to update it."
            )

        # Load defaults
        self.default_priority = 1
        self.default_category = "General"
        if "defaults" in config:
            priority_str = config["defaults"].get("priority", "1")
            if priority_str:
                self.default_priority = int(priority_str)
            else:
                self.default_priority = 1
            self.default_category = config["defaults"].get("category", "General")

        # Determine the appropriate data directory using appdirs
        data_dir = appdirs.user_data_dir(APP_NAME, APP_AUTHOR)
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "tasks.db")

        self.trello_url = "https://api.trello.com/1/cards"
        self.logger = logging.getLogger(__name__)
        self._init_db()

    def _init_db(self):
        """Create the tasks table if it doesn't exist and add new columns if they are missing."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL UNIQUE,
                    due_date TEXT,
                    priority INTEGER DEFAULT 1,
                    category TEXT DEFAULT 'General',
                    parent_id INTEGER REFERENCES pending_tasks(id)
                )
            """
            )
            # Add columns if they don't exist, for backward compatibility
            try:
                cursor.execute("ALTER TABLE pending_tasks ADD COLUMN due_date TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute(
                    "ALTER TABLE pending_tasks ADD COLUMN priority INTEGER DEFAULT 1"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute(
                    "ALTER TABLE pending_tasks ADD COLUMN category TEXT DEFAULT 'General'"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute(
                    "ALTER TABLE pending_tasks ADD COLUMN parent_id INTEGER REFERENCES pending_tasks(id)"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()

    def check_network(self) -> bool:
        """
        Check if Trello API is reachable to validate credentials.

        Returns:
            bool: True if reachable and authorized, False otherwise.
        """
        try:
            response = requests.get(
                "https://api.trello.com/1/members/me",
                params={"key": self.api_key, "token": self.token},
                timeout=5,
            )
            if response.status_code == 200:
                self.logger.debug("Connected to Trello API")
                return True
            else:
                self.logger.warning(
                    f"Trello API connection failed with status {response.status_code}"
                )
                return False
        except requests.RequestException as e:
            self.logger.warning(f"Network error while connecting to Trello: {e}")
            return False

    def add(
        self,
        task: str,
        due_date: str = None,
        priority: int = 1,
        category: str = "General",
        parent_id: int = None,
        force_upload: bool = False,
        list_id: str = None,
    ) -> None:
        """
        Add a new task to Trello if online or save locally if offline.

        Args:
            task (str): Task description to add.
            due_date (str, optional): Due date for the task. Defaults to None.
            priority (int, optional): Priority of the task. Defaults to 1.
            category (str, optional): Category of the task. Defaults to "General".
            parent_id (int, optional): The ID of the parent task. Defaults to None.
            force_upload (bool): If True, uploads pending tasks first.
            list_id (str, optional): The ID of the Trello list to add the task to.
        """
        if not task.strip():
            self.logger.error("Empty task description, nothing to add.")
            return

        if force_upload and self.has_pending_tasks():
            self.upload()

        if self.check_network():
            if not self._upload_task(
                task, due_date, priority, category, parent_id, list_id
            ):
                self.logger.info("Failed to upload task, saving locally.")
                self._save_task_locally(task, due_date, priority, category, parent_id)
        else:
            self.logger.info("Offline mode: saving task locally.")
            self._save_task_locally(task, due_date, priority, category, parent_id)

    def upload(self) -> None:
        """
        Upload all pending tasks saved locally to Trello.

        Creates a backup before uploading. Clears local storage on success.
        """
        if not self.has_pending_tasks():
            self.logger.info("No tasks to upload.")
            return

        try:
            tasks = self._load_tasks()
        except Exception as e:
            self.logger.error(f"Error loading tasks from DB: {e}")
            return

        uploaded_tasks = []
        for task in tasks:
            if self._upload_task(
                task["description"],
                task["due_date"],
                task["priority"],
                task["category"],
                task["parent_id"],
            ):
                uploaded_tasks.append(task)
            else:
                self.logger.error(
                    f"Failed to upload task: {task['description']}. Upload aborted."
                )
                self._clear_tasks(uploaded_tasks)
                return

        self._clear_tasks(uploaded_tasks)
        self.logger.info("All tasks uploaded successfully and local cache cleared.")

    def get_pending_tasks(
        self, sort_by: str = None, category: str = None, priority: int = None
    ) -> List[dict]:
        """
        Return a list of all top-level pending tasks from the local database,
        with optional sorting and filtering.

        Args:
            sort_by (str, optional): Field to sort by ('priority' or 'due_date').
            category (str, optional): Category to filter by.
            priority (int, optional): Priority to filter by.

        Returns:
            List[dict]: A list of tasks.
        """
        query = "SELECT id, description, due_date, priority, category, parent_id FROM pending_tasks WHERE parent_id IS NULL"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if priority:
            query += " AND priority = ?"
            params.append(priority)

        if sort_by in ["priority", "due_date"]:
            query += f" ORDER BY {sort_by}"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_sub_tasks(self, parent_id: int) -> List[dict]:
        """Return a list of all sub-tasks for a given parent task."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, description, due_date, priority, category, parent_id FROM pending_tasks WHERE parent_id = ?",
                (parent_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def has_sub_tasks(self, task_id: int) -> bool:
        """Check if a task has any sub-tasks."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(id) FROM pending_tasks WHERE parent_id = ?", (task_id,)
            )
            count = cursor.fetchone()[0]
            return count > 0

    def search_pending_tasks(self, query: str) -> List[dict]:
        """Search for pending tasks with descriptions matching the query."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pending_tasks WHERE description LIKE ?", (f"%{query}%",)
            )
            return [dict(row) for row in cursor.fetchall()]

    def search_trello_cards(self, query: str) -> List[dict]:
        """Search for cards on the Trello board matching the query."""
        url = "https://api.trello.com/1/search"
        params = {
            "key": self.api_key,
            "token": self.token,
            "query": query,
            "idBoards": self.board_id,
            "card_fields": "name,idBoard,idList",
            "modelTypes": "cards",
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                self.logger.error(f"Trello API error {response.status_code}")
                return []

            results = response.json()
            cards_data = results.get("cards", [])
            if not cards_data:
                return []

            # Group cards by list ID to fetch list and board info efficiently
            lists_info = {}
            boards_info = {}
            cards_by_list = {}
            for card in cards_data:
                if card["idList"] not in cards_by_list:
                    cards_by_list[card["idList"]] = []
                cards_by_list[card["idList"]].append(card)

            # Fetch details for each list and board
            for list_id in cards_by_list:
                if list_id not in lists_info:
                    list_url = f"https://api.trello.com/1/lists/{list_id}"
                    list_response = requests.get(list_url, params={"key": self.api_key, "token": self.token})
                    if list_response.status_code == 200:
                        lists_info[list_id] = list_response.json()

            board_id = cards_data[0]["idBoard"]
            if board_id not in boards_info:
                board_url = f"https://api.trello.com/1/boards/{board_id}"
                board_response = requests.get(board_url, params={"key": self.api_key, "token": self.token})
                if board_response.status_code == 200:
                    boards_info[board_id] = board_response.json()

            # Fetch all cards for each list to determine the card number
            final_cards = []
            for list_id, found_cards in cards_by_list.items():
                all_cards_in_list_url = f"https://api.trello.com/1/lists/{list_id}/cards"
                all_cards_response = requests.get(all_cards_in_list_url, params={"key": self.api_key, "token": self.token})
                if all_cards_response.status_code == 200:
                    all_cards_data = all_cards_response.json()
                    card_id_to_number = {card["id"]: i + 1 for i, card in enumerate(all_cards_data)}

                    for card in found_cards:
                        final_cards.append(
                            {
                                "id": card["id"],
                                "name": card["name"],
                                "list_name": lists_info.get(list_id, {}).get("name", "Unknown List"),
                                "board_name": boards_info.get(card["idBoard"], {}).get("name", "Unknown Board"),
                                "card_number": card_id_to_number.get(card["id"], -1),
                            }
                        )
            return final_cards
        except requests.RequestException as e:
            self.logger.error(f"Trello API request error: {e}")
            return []

    def get_board_lists(self) -> List[dict]:
        """Fetch all lists from the configured Trello board."""
        url = f"https://api.trello.com/1/boards/{self.board_id}/lists"
        params = {"key": self.api_key, "token": self.token}
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                lists = response.json()
                return [{"id": lst["id"], "name": lst["name"]} for lst in lists]
            self.logger.error(f"Trello API error {response.status_code}")
            return []
        except requests.RequestException as e:
            self.logger.error(f"Trello API request error: {e}")
            return []

    def get_all_cards_on_board(self) -> List[dict]:
        """Fetch all cards from the configured Trello board."""
        url = f"https://api.trello.com/1/boards/{self.board_id}/cards"
        params = {"key": self.api_key, "token": self.token}
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            self.logger.error(f"Trello API error {response.status_code}")
            return []
        except requests.RequestException as e:
            self.logger.error(f"Trello API request error: {e}")
            return []

    def get_board_actions(self) -> List[dict]:
        """Fetch create and complete actions from the configured Trello board."""
        url = f"https://api.trello.com/1/boards/{self.board_id}/actions"
        params = {
            "key": self.api_key,
            "token": self.token,
            "filter": "createCard,updateCard",
            "limit": 1000,  # Fetch up to 1000 recent actions
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            self.logger.error(f"Trello API error {response.status_code}")
            return []
        except requests.RequestException as e:
            self.logger.error(f"Trello API request error: {e}")
            return []

    def get_trello_tasks(self, list_id: str = None) -> List[dict]:
        """Fetch all cards from a specific Trello list."""
        target_list_id = list_id if list_id else self.list_id
        url = f"https://api.trello.com/1/lists/{target_list_id}/cards"
        params = {"key": self.api_key, "token": self.token}
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                cards = response.json()
                # We only need the id and name for now
                return [{"id": card["id"], "name": card["name"]} for card in cards]
            self.logger.error(f"Trello API error {response.status_code}")
            return []
        except requests.RequestException as e:
            self.logger.error(f"Trello API request error: {e}")
            return []

    def archive_task(self, task_id: str) -> bool:
        """Archive a specific task on Trello by its card ID."""
        url = f"https://api.trello.com/1/cards/{task_id}"
        params = {"key": self.api_key, "token": self.token, "closed": "true"}
        try:
            response = requests.put(url, params=params, timeout=10)
            if response.status_code == 200:
                self.logger.info(f"Successfully archived task {task_id}")
                return True
            self.logger.error(f"Trello API error {response.status_code}")
            return False
        except requests.RequestException as e:
            self.logger.error(f"Trello API request error: {e}")
            return False

    def delete_pending_task(self, task_description: str) -> bool:
        """Delete a specific pending task from the local database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM pending_tasks WHERE description = ?",
                    (task_description,),
                )
                conn.commit()
                # rowcount will be 1 if a task was deleted, 0 otherwise
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self.logger.error(f"Error deleting pending task: {e}")
            return False

    def edit_pending_task(
        self,
        task_id: int,
        description: str = None,
        due_date: str = None,
        priority: int = None,
        category: str = None,
    ) -> bool:
        """Edit a specific pending task in the local database."""
        fields_to_update = []
        params = []

        if description is not None:
            fields_to_update.append("description = ?")
            params.append(description)
        if due_date is not None:
            fields_to_update.append("due_date = ?")
            params.append(due_date)
        if priority is not None:
            fields_to_update.append("priority = ?")
            params.append(priority)
        if category is not None:
            fields_to_update.append("category = ?")
            params.append(category)

        if not fields_to_update:
            self.logger.info("No fields provided to update.")
            return False

        params.append(task_id)
        query = f"UPDATE pending_tasks SET {', '.join(fields_to_update)} WHERE id = ?"

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            self.logger.error(f"Error editing pending task: {e}")
            return False

    def has_pending_tasks(self) -> bool:
        """Check for any tasks in the local database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(id) FROM pending_tasks")
            count = cursor.fetchone()[0]
            return count > 0

    def _load_tasks(self) -> List[dict]:
        """Load all tasks from the local database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, description, due_date, priority, category, parent_id FROM pending_tasks"
            )
            return [dict(row) for row in cursor.fetchall()]

    def _upload_task(
        self,
        task: str,
        due_date: str,
        priority: int,
        category: str,
        parent_id: int,
        list_id: str = None,
    ) -> bool:
        """Send a single task to Trello as a card."""
        try:
            desc = f"Priority: {priority}\nCategory: {category}"
            if parent_id:
                desc += f"\nSub-task of: {parent_id}"
            payload = {
                "key": self.api_key,
                "token": self.token,
                "idList": list_id if list_id else self.list_id,
                "name": task,
                "desc": desc,
            }
            if due_date:
                payload["due"] = due_date

            response = requests.post(
                self.trello_url,
                data=payload,
                timeout=10,
            )
            if response.status_code in (200, 201):
                self.logger.info(f"Successfully uploaded task: {task}")
                return True
            self.logger.error(f"Trello API error {response.status_code}")
            return False
        except requests.RequestException as e:
            self.logger.error(f"Trello upload error: {e}")
            raise ConnectionError(
                "Could not connect to Trello. Please check your network connection."
            )
        return False

    def _save_task_locally(
        self, task: str, due_date: str, priority: int, category: str, parent_id: int
    ) -> None:
        """Append a task to the local database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Use INSERT OR IGNORE to avoid duplicate tasks
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO pending_tasks (description, due_date, priority, category, parent_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (task, due_date, priority, category, parent_id),
                )
                conn.commit()
            self.logger.info(f"Task saved locally: {task}")
        except sqlite3.Error as e:
            self.logger.error(f"Error saving task locally: {e}")

    def _clear_tasks(self, tasks_to_clear: List[dict]) -> None:
        """Remove specific tasks from the local database."""
        if not tasks_to_clear:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Create a placeholder string like (?, ?, ?) for the query
                task_ids = [task["id"] for task in tasks_to_clear]
                placeholders = ", ".join("?" for _ in task_ids)
                query = f"DELETE FROM pending_tasks WHERE id IN ({placeholders})"
                cursor.execute(query, task_ids)
                conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"Error clearing tasks: {e}")
