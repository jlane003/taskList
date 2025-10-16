import os
import sys
import stat
import argparse
import configparser
import importlib.metadata
import appdirs
import requests
import datetime
from colorama import Fore, Style, init as colorama_init
from tasklist.task_manager import TaskList
from tasklist.logging_config import setup_logging
from . import reports

# Initialize colorama
colorama_init(autoreset=True)

# Define app constants for appdirs
APP_NAME = "tasklist"
APP_AUTHOR = "TaskList"


def get_priority_color(priority):
    """Return a color based on the task priority."""
    if priority == 3:
        return Fore.RED  # High
    elif priority == 2:
        return Fore.YELLOW  # Medium
    else:
        return Fore.GREEN  # Low (or default)


def validate_due_date(date_string):
    """Validate that the due date string is in YYYY-MM-DD format."""
    if date_string is None:
        return None
    try:
        datetime.datetime.strptime(date_string, "%Y-%m-%d")
        return date_string
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: '{date_string}'. Please use YYYY-MM-DD."
        )


def validate_priority(value):
    """Validate that the priority is an integer between 1 and 3."""
    try:
        priority = int(value)
        if priority not in [1, 2, 3]:
            raise argparse.ArgumentTypeError(
                f"Invalid priority: '{value}'. Must be 1 (low), 2 (medium), or 3 (high)."
            )
        return priority
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid priority: '{value}'. Must be an integer."
        )


def validate_task_number(value):
    """Validate that the task number is a valid integer."""
    try:
        if "." in value or "," in value:
            raise ValueError("Task number must be a whole number.")
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid task number: '{value}'. Must be a valid integer."
        )


def set_secure_config_permissions(path):
    """Sets secure permissions for the configuration file."""
    # On Windows, file permissions work differently, so we skip this check.
    if sys.platform == "win32":
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        print(f"Error setting permissions on {path}: {e}", file=sys.stderr)


def prompt_for_upload():
    """Prompts the user to upload pending tasks."""
    ans = input("Pending tasks exist. Upload them now? (y/n): ").strip().lower()
    return ans == "y"


def handle_add_command(args, task_list):
    """
    Handles the 'add' command, including due date, priority, and category.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    list_id = None
    if args.list_name:
        lists = task_list.get_board_lists()
        found_list = next(
            (lst for lst in lists if lst["name"].lower() == args.list_name.lower()),
            None,
        )

        if not found_list:
            print(f"Error: List '{args.list_name}' not found.", file=sys.stderr)
            sys.exit(1)
        list_id = found_list["id"]

    new_task = " ".join(args.task)
    force_upload = False
    # If there are pending tasks, ask the user if they want to upload them.
    if task_list.has_pending_tasks():
        print("Pending tasks exist:")
        for i, task in enumerate(task_list.get_pending_tasks(), 1):
            print(f"{i}. {task['description']}")
        force_upload = prompt_for_upload()
    # Add the new task. If force_upload is True, all pending tasks will be uploaded.
    task_list.add(
        new_task,
        due_date=args.due_date,
        priority=args.priority,
        category=args.category,
        force_upload=force_upload,
        list_id=list_id,
    )


def handle_upload_command(args, task_list):
    """
    Handles the 'upload' command, showing progress.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    if not task_list.has_pending_tasks():
        print("No tasks to upload.", file=sys.stderr)
        return

    tasks_to_upload = task_list._load_tasks()
    print(f"Found {len(tasks_to_upload)} tasks to upload.")
    for i, task in enumerate(tasks_to_upload, 1):
        print(
            f"Uploading task {i} of {len(tasks_to_upload)}: '{task['description']}'..."
        )
    task_list.upload()
    print("All tasks uploaded successfully.")


def handle_list_command(args, task_list):
    """
    Handles the 'list' command with filtering, sorting, and verbose output.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    tasks = task_list.get_pending_tasks(
        sort_by=args.sort_by, category=args.category, priority=args.priority
    )
    if not tasks:
        print("No pending tasks match your criteria.", file=sys.stderr)
        return
    print("Pending tasks:")
    for i, task in enumerate(tasks, 1):
        prefix = "[+] " if task_list.has_sub_tasks(task["id"]) else "    "
        priority_color = get_priority_color(task["priority"])
        if args.verbose:
            due_date_str = task["due_date"] if task["due_date"] else "N/A"
            print(f"{i}. {prefix}{task['description']}")
            print(f"   Due Date: {due_date_str}")
            print(f"   Priority: {priority_color}{task['priority']}{Style.RESET_ALL}")
            print(f"   Category: {task['category']}")
        else:
            print(
                f"{i}. {prefix}{priority_color}[P{task['priority']}] {Style.RESET_ALL}{task['description']}"
            )


def handle_show_command(args, task_list):
    """
    Handles the 'show' command to display tasks or lists from Trello.

    Can show tasks from the default list, a specific list by name, or all lists.
    Can also show all lists on the board with their IDs.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    if args.lists:
        lists = task_list.get_board_lists()
        if not lists:
            print("No lists found on your Trello board.", file=sys.stderr)
            return
        print("Trello Lists:")
        for lst in lists:
            print(f"  - Name: {lst['name']:<25} ID: {lst['id']}")
        return

    if args.all:
        lists = task_list.get_board_lists()
        if not lists:
            print("No lists found on your Trello board.", file=sys.stderr)
            return

        for lst in lists:
            print(f"\n--- List: {lst['name']} ---")
            tasks = task_list.get_trello_tasks(list_id=lst["id"])
            if not tasks:
                print("No tasks found in this list.")
            else:
                for i, task in enumerate(tasks, 1):
                    print(f"{i}. {task['name']}")

    elif args.list_name:
        lists = task_list.get_board_lists()
        found_list = next(
            (lst for lst in lists if lst["name"].lower() == args.list_name.lower()),
            None,
        )

        if not found_list:
            print(f"Error: List '{args.list_name}' not found.", file=sys.stderr)
            sys.exit(1)

        tasks = task_list.get_trello_tasks(list_id=found_list["id"])
        if not tasks:
            print(f"No tasks found in list '{args.list_name}'.", file=sys.stderr)
            return
        print(f"Tasks on Trello list '{args.list_name}':")
        for i, task in enumerate(tasks, 1):
            print(f"{i}. {task['name']}")

    else:
        tasks = task_list.get_trello_tasks()
        if not tasks:
            print("No tasks found on your default Trello list.", file=sys.stderr)
            return
        print("Tasks on default Trello list:")
        for i, task in enumerate(tasks, 1):
            print(f"{i}. {task['name']}")


def get_task_from_list_by_number(task_list: list, task_number: int):
    """
    Retrieves a task from a list by its 1-based number.

    Handles index validation and prints errors if the number is invalid.
    """
    if not task_list:
        print(
            "Error: There are no pending tasks to perform this action on.",
            file=sys.stderr,
        )
        return None
    try:
        task_index = int(task_number) - 1
        if not 0 <= task_index < len(task_list):
            print(
                "Error: Invalid task number. "
                f"Please enter a number between 1 and {len(task_list)}.",
                file=sys.stderr,
            )
            return None
        return task_list[task_index]
    except ValueError:
        print("Error: Please enter a valid number.", file=sys.stderr)
        return None


def handle_done_command(args, task_list):
    """
    Handles the 'done' command to archive a task on Trello.

    Can archive a task from the default list or a specific list by name.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    if args.list_name:
        lists = task_list.get_board_lists()
        found_list = next(
            (lst for lst in lists if lst["name"].lower() == args.list_name.lower()),
            None,
        )

        if not found_list:
            print(f"Error: List '{args.list_name}' not found.", file=sys.stderr)
            sys.exit(1)

        tasks = task_list.get_trello_tasks(list_id=found_list["id"])
        if not tasks:
            print(f"No tasks found in list '{args.list_name}'.", file=sys.stderr)
            return
    else:
        tasks = task_list.get_trello_tasks()
        if not tasks:
            print("No tasks found on your default Trello list.", file=sys.stderr)
            return

    task_to_archive = get_task_from_list_by_number(tasks, args.task_number)

    if not task_to_archive:
        return

    task_id = task_to_archive["id"]
    task_name = task_to_archive["name"]

    if task_list.archive_task(task_id):
        print(f"Task '{task_name}' marked as done.")
    else:
        print(f"Failed to mark task '{task_name}' as done.", file=sys.stderr)


def handle_remove_command(args, task_list):
    """
    Handles the 'remove' command for pending tasks with a confirmation prompt.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    tasks = task_list.get_pending_tasks()
    task_to_remove = get_task_from_list_by_number(tasks, args.task_number)

    if not task_to_remove:
        return

    confirm = (
        input(
            f"Are you sure you want to remove '{task_to_remove['description']}'? [y/N]: "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print("Removal cancelled.", file=sys.stderr)
        return

    if task_list.delete_pending_task(task_to_remove["description"]):
        print(f"Removed pending task: '{task_to_remove['description']}'")
    else:
        print(
            f"Failed to remove pending task: '{task_to_remove['description']}'",
            file=sys.stderr,
        )


def handle_edit_command(args, task_list):
    """
    Handles the 'edit' command for pending tasks.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    if not any([args.description, args.due_date, args.priority, args.category]):
        print("Error: Please provide at least one field to edit.", file=sys.stderr)
        print(
            "Usage: tasklist edit <task_number> [--description ...] [--due-date ...]",
            file=sys.stderr,
        )
        return

    tasks = task_list.get_pending_tasks()
    task_to_edit = get_task_from_list_by_number(tasks, args.task_number)

    if not task_to_edit:
        return

    if task_list.edit_pending_task(
        task_id=task_to_edit["id"],
        description=args.description,
        due_date=args.due_date,
        priority=args.priority,
        category=args.category,
    ):
        print(f"Successfully edited task {args.task_number}.")
    else:
        print(f"Failed to edit task {args.task_number}.", file=sys.stderr)


def handle_view_command(args, task_list):
    """
    Handles the 'view' command for a single pending task.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    tasks = task_list.get_pending_tasks()
    task_to_view = get_task_from_list_by_number(tasks, args.task_number)

    if not task_to_view:
        return

    print(f"Details for task {args.task_number}:")
    print(f"  Description: {task_to_view['description']}")
    due_date_str = task_to_view["due_date"] if task_to_view["due_date"] else "N/A"
    print(f"  Due Date:    {due_date_str}")
    print(f"  Priority:    {task_to_view['priority']}")
    print(f"  Category:    {task_to_view['category']}")


def handle_sub_add_command(args, task_list):
    """
    Handles the 'sub add' command to add a sub-task to a parent.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    tasks = task_list.get_pending_tasks()
    parent_task = get_task_from_list_by_number(tasks, args.parent_task_number)

    if not parent_task:
        return

    new_task = " ".join(args.task)
    task_list.add(
        new_task,
        due_date=args.due_date,
        priority=args.priority,
        category=args.category,
        parent_id=parent_task["id"],
    )
    print(f"Added sub-task to '{parent_task['description']}'.")


def handle_sub_list_command(args, task_list):
    """
    Handles the 'sub list' command to list sub-tasks for a parent.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    tasks = task_list.get_pending_tasks()
    parent_task = get_task_from_list_by_number(tasks, args.parent_task_number)

    if not parent_task:
        return

    sub_tasks = task_list.get_sub_tasks(parent_task["id"])

    if not sub_tasks:
        print(
            f"No sub-tasks found for '{parent_task['description']}'.", file=sys.stderr
        )
        return

    print(f"Sub-tasks for '{parent_task['description']}':")
    for i, task in enumerate(sub_tasks, 1):
        print(f"  {i}. {task['description']}")


def handle_sub_command(args, task_list):
    """
    Handles the main 'sub' command and delegates to sub-commands.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    if args.sub_command == "add":
        handle_sub_add_command(args, task_list)
    elif args.sub_command == "list":
        handle_sub_list_command(args, task_list)


def handle_import_command(args, task_list):
    """
    Handles the 'import' command, showing progress.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            print(f"Found {len(lines)} tasks to import from {args.file}.")
            for line in lines:
                task = line.strip()
                if task:
                    print(f"Importing task: '{task}'...")
                    task_list.add(task)
        print(f"Tasks from {args.file} imported successfully.")
    except FileNotFoundError:
        print(f"Error: File not found at {args.file}", file=sys.stderr)
        sys.exit(1)


def handle_search_command(args, task_list):
    """
    Handles the 'search' command for both local and remote tasks.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    query = " ".join(args.query)
    search_local = args.local or not args.remote
    search_remote = args.remote or not args.local

    if search_local:
        print("--- Searching Pending Tasks ---")
        local_results = task_list.search_pending_tasks(query)
        if not local_results:
            print("No matching pending tasks found.")
        else:
            for i, task in enumerate(local_results, 1):
                print(f"{i}. {task['description']}")

    if search_remote:
        print("\n--- Searching Trello Tasks ---")
        remote_results = task_list.search_trello_cards(query)
        if not remote_results:
            print("No matching Trello cards found.")
        else:
            for task in remote_results:
                print(
                    f"Board: {task['board_name']} | List: {task['list_name']} | #{task['card_number']} - {task['name']}"
                )


def handle_report_command(args, task_list):
    """
    Handles the 'report' command and delegates to sub-commands.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
        task_list (TaskList): An instance of the TaskList class.
    """
    run_all = args.all or not args.reports_command

    if run_all or args.reports_command == "lists":
        lists = task_list.get_board_lists()
        cards = task_list.get_all_cards_on_board()
        list_counts = {lst["name"]: 0 for lst in lists}
        for card in cards:
            for lst in lists:
                if card["idList"] == lst["id"]:
                    list_counts[lst["name"]] += 1
        print(reports.generate_bar_chart(list_counts, "Cards per List"))

    if run_all or args.reports_command == "keywords":
        cards = task_list.get_all_cards_on_board()
        keywords = reports.get_top_keywords(cards)
        print("\n--- Top 10 Keywords ---")
        for keyword, count in keywords:
            print(f"- {keyword}: {count}")

    if run_all or args.reports_command == "sentiment":
        cards = task_list.get_all_cards_on_board()
        sentiment = reports.analyze_sentiment_by_week(cards)
        print("\n--- Weekly Sentiment Analysis ---")
        for week, mood in sorted(sentiment.items()):
            print(f"- Week {week}: {mood}")

    if run_all or args.reports_command == "activity":
        actions = task_list.get_board_actions()
        # Assuming 'Done' is the name of your list for completed tasks.
        # This can be made configurable in the future.
        print(reports.generate_activity_chart(actions, done_list_name="Done"))


def validate_trello_credentials(api_key, token):
    """Validates Trello credentials by making a test API call."""
    url = "https://api.trello.com/1/members/me"
    params = {"key": api_key, "token": token}
    try:
        response = requests.get(url, params=params, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def handle_configure_command(args):
    """
    Handles the 'configure' command to set up Trello and default settings.

    Args:
        args (argparse.Namespace): The parsed command-line arguments.
    """
    print("Configuring tasklist...")
    api_key = input("Enter your Trello API key: ").strip()
    token = input("Enter your Trello API token: ").strip()
    board_id = input("Enter your Trello board ID: ").strip()
    list_id = input("Enter your Trello list ID for default tasks: ").strip()

    if not validate_trello_credentials(api_key, token):
        print("Error: Invalid Trello API key or token.", file=sys.stderr)
        sys.exit(1)

    while True:
        default_priority = input(
            "Enter a default priority (1-3, optional, press Enter to skip): "
        ).strip()
        if not default_priority:
            default_priority = "1"  # Default to 1 if skipped
            break
        try:
            priority_val = int(default_priority)
            if 1 <= priority_val <= 3:
                break
            else:
                print(
                    "Invalid priority. Please enter a number between 1 and 3.",
                    file=sys.stderr,
                )
        except ValueError:
            print("Invalid input. Please enter a number.", file=sys.stderr)

    default_category = input(
        "Enter a default category (optional, press Enter to skip): "
    ).strip()

    config = configparser.ConfigParser()
    config["trello"] = {
        "api_key": api_key,
        "token": token,
        "board_id": board_id,
        "list_id": list_id,
    }
    config["defaults"] = {
        "priority": default_priority,
        "category": default_category,
    }

    config_dir = os.path.dirname(args.config)
    os.makedirs(config_dir, exist_ok=True)

    with open(args.config, "w") as config_file:
        config.write(config_file)
        # Set secure permissions (not applicable on Windows)
        if sys.platform != "win32":
            os.chmod(args.config, stat.S_IRUSR | stat.S_IWUSR)

    print(f"Configuration saved to {args.config}")


def main():
    """
    Command line interface entry point for tasklist.
    """
    setup_logging()

    try:
        __version__ = importlib.metadata.version("tasklist")
    except importlib.metadata.PackageNotFoundError:
        __version__ = "0.0.0"  # Fallback for development mode

    # Determine the appropriate config directory using appdirs
    config_dir = appdirs.user_config_dir(APP_NAME, APP_AUTHOR)
    default_config_path = os.path.join(config_dir, "config.ini")

    parser = argparse.ArgumentParser(
        description="taskList CLI with Trello integration.",
        epilog="""
Command Groups:

  Task Creation (Online/Offline):
    add, import, sub add
    These commands add new tasks. They work online and offline.

  Pending Task Management (Offline):
    list, edit, view, remove, sub list
    Manage local tasks that have not been uploaded to Trello.

  Trello Board Interaction (Online):
    show, done, upload
    These commands interact directly with your Trello board.

  Reports:
    reports
    Generate reports based on your Trello data.

  Search:
    search
    Search for tasks both locally and on Trello.
""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=default_config_path,
        help=f"Path to configuration file (default: {default_config_path})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("task", nargs="+", help="Task description")
    add_parser.add_argument(
        "--due-date", type=validate_due_date, help="Due date for the task (YYYY-MM-DD)"
    )
    add_parser.add_argument(
        "--priority",
        type=validate_priority,
        help="Priority of the task (1=low, 2=medium, 3=high)",
    )
    add_parser.add_argument(
        "--category",
        help="Category of the task",
    )
    add_parser.add_argument(
        "--list-name", help="Name of the Trello list to add the task to"
    )

    subparsers.add_parser("upload", help="Upload pending tasks saved locally")
    list_parser = subparsers.add_parser("list", help="List all pending tasks")
    list_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed information for each task",
    )
    list_parser.add_argument("--category", help="Filter tasks by category")
    list_parser.add_argument(
        "--priority", type=validate_priority, help="Filter tasks by priority (1-3)"
    )
    list_parser.add_argument(
        "--sort-by",
        choices=["priority", "due_date"],
        help="Sort tasks by priority or due date",
    )
    show_parser = subparsers.add_parser(
        "show", help="Show tasks from your Trello list"
    )
    show_parser.add_argument(
        "--list-name", help="Name of the Trello list to show tasks from"
    )
    show_parser.add_argument(
        "--all", action="store_true", help="Show tasks from all lists on the board"
    )
    show_parser.add_argument(
        "--lists", action="store_true", help="Show all lists on the board with their IDs"
    )
    done_parser = subparsers.add_parser(
        "done", help="Mark a task on Trello as done (archives it)"
    )
    done_parser.add_argument(
        "task_number",
        type=validate_task_number,
        help="The number of the task to mark as done",
    )
    done_parser.add_argument(
        "--list-name", help="Name of the Trello list to archive a task from"
    )
    remove_parser = subparsers.add_parser(
        "remove", help="Remove a pending task from the local list"
    )
    remove_parser.add_argument(
        "task_number",
        type=validate_task_number,
        help="The number of the pending task to remove",
    )
    edit_parser = subparsers.add_parser("edit", help="Edit a pending task")
    edit_parser.add_argument(
        "task_number",
        type=validate_task_number,
        help="The number of the pending task to edit",
    )
    edit_parser.add_argument("--description", help="New description for the task")
    edit_parser.add_argument(
        "--due-date",
        type=validate_due_date,
        help="New due date for the task (YYYY-MM-DD)",
    )
    edit_parser.add_argument(
        "--priority",
        type=validate_priority,
        help="New priority for the task (1-3)",
    )
    edit_parser.add_argument("--category", help="New category for the task")

    view_parser = subparsers.add_parser(
        "view", help="View a single pending task in detail"
    )
    view_parser.add_argument(
        "task_number",
        type=validate_task_number,
        help="The number of the pending task to view",
    )

    sub_parser = subparsers.add_parser("sub", help="Manage sub-tasks")
    sub_subparsers = sub_parser.add_subparsers(dest="sub_command", required=True)

    sub_add_parser = sub_subparsers.add_parser(
        "add", help="Add a sub-task to a parent task"
    )
    sub_add_parser.add_argument(
        "parent_task_number",
        type=validate_task_number,
        help="The number of the parent task",
    )
    sub_add_parser.add_argument("task", nargs="+", help="Sub-task description")
    sub_add_parser.add_argument(
        "--due-date", type=validate_due_date, help="Due date for the sub-task"
    )
    sub_add_parser.add_argument(
        "--priority",
        type=validate_priority,
        help="Priority of the sub-task (1-3)",
    )
    sub_add_parser.add_argument(
        "--category",
        help="Category of the sub-task",
    )

    sub_list_parser = sub_subparsers.add_parser(
        "list", help="List sub-tasks for a parent task"
    )
    sub_list_parser.add_argument(
        "parent_task_number",
        type=validate_task_number,
        help="The number of the parent task",
    )

    search_parser = subparsers.add_parser("search", help="Search for tasks")
    search_parser.add_argument("query", nargs="+", help="The search query")
    search_parser.add_argument(
        "--local", action="store_true", help="Search only local pending tasks"
    )
    search_parser.add_argument(
        "--remote", action="store_true", help="Search only Trello tasks"
    )

    import_parser = subparsers.add_parser("import", help="Import tasks from a file")
    import_parser.add_argument("file", help="Path to the file to import tasks from")

    report_parser = subparsers.add_parser("reports", help="Generate reports")
    report_parser.add_argument(
        "--all", action="store_true", help="Run all reports"
    )
    report_subparsers = report_parser.add_subparsers(dest="reports_command")
    report_subparsers.add_parser("activity", help="Show a chart of task activity over time")
    report_subparsers.add_parser("keywords", help="Show the top 10 keywords from your Trello cards")
    report_subparsers.add_parser("lists", help="Show a bar chart of cards per list")
    report_subparsers.add_parser("sentiment", help="Show a weekly sentiment analysis of your Trello cards")

    subparsers.add_parser("configure", help="Create the configuration file.")

    args = parser.parse_args()

    # The configure command is special, it runs without a loaded TaskList
    if args.command == "configure":
        handle_configure_command(args)
        sys.exit(0)

    # For all other commands, we need to load the config and TaskList
    config_path = os.path.expanduser(args.config)
    set_secure_config_permissions(config_path)

    try:
        task_list = TaskList(config_path)
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}", file=sys.stderr)
        print("Please run 'tasklist configure' to create one.", file=sys.stderr)
        sys.exit(1)
    except configparser.Error as e:
        print(f"Error: Could not parse config file: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Set default priority and category for 'add' and 'sub add' commands if not provided
    if args.command == "add" or (args.command == "sub" and args.sub_command == "add"):
        if args.priority is None:
            args.priority = task_list.default_priority
        if args.category is None:
            args.category = task_list.default_category

    if args.command == "add":
        handle_add_command(args, task_list)
    elif args.command == "upload":
        handle_upload_command(args, task_list)
    elif args.command == "list":
        handle_list_command(args, task_list)
    elif args.command == "show":
        handle_show_command(args, task_list)
    elif args.command == "done":
        handle_done_command(args, task_list)
    elif args.command == "remove":
        handle_remove_command(args, task_list)
    elif args.command == "edit":
        handle_edit_command(args, task_list)
    elif args.command == "view":
        handle_view_command(args, task_list)
    elif args.command == "sub":
        handle_sub_command(args, task_list)
    elif args.command == "import":
        handle_import_command(args, task_list)
    elif args.command == "search":
        handle_search_command(args, task_list)
    elif args.command == "reports":
        handle_report_command(args, task_list)


if __name__ == "__main__":
    main()
