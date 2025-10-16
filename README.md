# TaskList

> A powerful command-line task manager with Trello integration, offline support, sub-tasks, and more.

[![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)](https://github.com/RichardLitt/standard-readme)

## Table of Contents

- [Background](#background)
- [Features](#features)
- [Install](#install)
- [Configuration](#configuration)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Background

TaskList is a simple and efficient command-line tool designed to help you manage your tasks seamlessly. It integrates with Trello, allowing you to sync your tasks with a Trello board. When you're offline, TaskList stores your tasks locally in a SQLite database and uploads them the next time you're online.

## Features

-   **Trello Integration:** Sync your tasks with a Trello board.
-   **Offline Mode:** Tasks are saved locally when you're offline and uploaded automatically later.
-   **Task Metadata:** Add due dates, priorities, and categories to your tasks.
-   **Sub-tasks:** Break down complex tasks into smaller, manageable sub-tasks.
-   **Filtering and Sorting:** Easily find the tasks you're looking for with powerful filtering and sorting options.
-   **Interactive Management:** Edit and view tasks directly from the command line.

## Install

This project uses Python and `pip`.

1.  Ensure you have Python 3.8+ installed.
2.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd tasklist
    ```
3.  Install the package in editable mode:
    ```bash
    pip install -e .
    ```
    This will install the `tasklist` command and all necessary dependencies.

## Configuration

First, you need to configure your Trello credentials. Run the interactive configuration command:

```bash
tasklist configure
```

This will prompt you for your Trello API key, token, board ID, and a default list ID.

### Security Recommendation

For enhanced security, it is highly recommended to use environment variables to store your Trello credentials. The application will automatically use them if they are present.

-   `TRELLO_API_KEY`: Your Trello API key.
-   `TRELLO_API_TOKEN`: Your Trello API token.

### Default Settings

The `configure` command will also prompt you to set a default priority and category for new tasks. These will be saved in a `[defaults]` section in your `config.ini` file and can be changed at any time.

## Usage

The `tasklist` commands are divided into three groups based on how they function:

1.  **Task Creation (Online/Offline):** These commands are for adding new tasks. They are "smart" and will try to connect to Trello first, but will save your tasks locally if you're offline.
2.  **Managing Pending Tasks (Offline):** These commands work on your local database of tasks that have not yet been uploaded to Trello. They do not require a network connection.
3.  **Managing Trello Tasks (Online):** These commands interact directly with your Trello board and require a network connection.

### Task Creation (Online/Offline)

-   **`tasklist add "My new task"`**: Adds a new task. If you are online, it's sent directly to Trello; otherwise, it's saved as a pending task.
    -   `--due-date YYYY-MM-DD`: The due date for the task.
    -   `--priority`: A number from 1 (low) to 3 (high).
    -   `--category`: The category of the task.
    -   `--list-name`: The name of the Trello list to add the task to (if online).

-   **`tasklist import <file-path>`**: Import tasks from a text file, adding them one by one using the same logic as the `add` command.

-   **`tasklist sub add <parent-task-number> "Sub-task description"`**: Add a sub-task to an existing **pending task**. This works online or offline, similar to the `add` command.

### Managing Pending Tasks (Offline)

-   **`tasklist list`**: List your pending tasks.
    -   `--verbose`: Show detailed information.
    -   `--category "Work"`: Filter by category.
    -   `--priority 3`: Filter by priority.
    -   `--sort-by priority`: Sort by `priority` or `due_date`.

-   **`tasklist edit <task-number>`**: Edit a pending task.
    -   `--description "New description"`
    -   `--priority 2`

-   **`tasklist view <task-number>`**: View all details of a single pending task.

-   **`tasklist remove <task-number>`**: Remove a pending offline task.

-   **`tasklist sub list <parent-task-number>`**: List all sub-tasks for a parent task from the local database.


### Managing Trello Tasks (Online)

-   **`tasklist show`**: Show tasks from your default Trello list.
    -   `--list-name "In Progress"`: Show tasks from a specific list by name.
    -   `--all`: Show tasks from all lists on your board.
    -   `--lists`: Show all lists on your board with their IDs.

-   **`tasklist done <task-number>`**: Mark a task on Trello as done (archives it). By default, this command acts on your default list.
    -   `--list-name "In Progress"`: Specify a different list to archive a task from.

-   **`tasklist upload`**: Manually upload all pending offline tasks to Trello.

### Generating Reports

You can generate several reports to get insights into your Trello data.

-   **`tasklist reports --all`**: Run all available reports.
-   **`tasklist reports lists`**: Show a bar chart of cards per list.
-   **`tasklist reports keywords`**: Show the top 10 keywords from your Trello cards.
-   **`tasklist reports sentiment`**: Show a weekly sentiment analysis of your Trello cards.
-   **`tasklist reports activity`**: Show a chart of task activity over time (not yet implemented).

### Searching for Tasks

You can search for tasks in both your local pending list and on your Trello board.

-   **`tasklist search "my query"`**: Search for tasks. By default, it searches both local and Trello tasks.
    -   `--local`: Search only your local pending tasks.
    -   `--remote`: Search only your Trello board.


## Contributing

Contributions are welcome! Please open an issue to discuss any changes or submit a pull request.
Thanks to Gemini for the huge help on documentation and picking up on test cases I missed. 

## License

This project is licensed under the MIT License.
