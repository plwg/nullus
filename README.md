# NULLUS - Python task management in the CLI

## Usage

`uv` is recommended:

```bash
pip install uv
uv tool install nullus
nu
```

Detailed options:

```
usage: nu [-h] [-l [REGEX] | -a TASK [TASK ...] | -t TASK_IDS [TAGS ...] | -u TASK_ID DESC | -p TASK_ID [TASK_ID ...] | -d TASK_ID [TASK_ID ...] | -s DATE [TASK_ID ...] | --deadline DATE [TASK_ID ...] | --delete TASK_ID [TASK_ID ...] | --prune | --purge TASK_ID [TASK_ID ...] | --dump |
          --dumpr REGEX]

CLI To-Do List

options:
  -h, --help            show this help message and exit
  -l [REGEX], --list [REGEX]
                        list active task(s) matching a regex; list all if regex is left empty
  -a TASK [TASK ...], --add TASK [TASK ...]
                        add task(s) and reassign task id(s)
  -t TASK_IDS [TAGS ...], --tag TASK_IDS [TAGS ...]
                        add/remove tag(s) to tasks(s)
  -u TASK_ID DESC, --update TASK_ID DESC
                        update task description
  -p TASK_ID [TASK_ID ...], --pin TASK_ID [TASK_ID ...]
                        pin task(s)
  -d TASK_ID [TASK_ID ...], --done TASK_ID [TASK_ID ...]
                        toggle task(s) between todo and done and reassign task id(s)
  -s DATE [TASK_ID ...], --schedule DATE [TASK_ID ...]
                        schedule task(s) to a specific DATE (YYYY-MM-DD)
  --deadline DATE [TASK_ID ...]
                        give task(s) a deadline (YYYY-MM-DD)
  --delete TASK_ID [TASK_ID ...]
                        toggle tasks visibility and reassign task id(s)
  --prune               set done task(s) visibility to false and reassign task id(s)
  --purge TASK_ID [TASK_ID ...]
                        remove task(s) from storage
  --dump                list active and inactive tasks
  --dumpr REGEX         list active and inactive tasks matching a regex
```

## Notes

The tasks are saved to a sqlite3 database file located at `~/.config/nullus/task.db`. The file is created if it doesn't already exist. Ensure that the script has permission to write to that location to avoid any runtime errors.

## License

This project is licensed under the MIT License. For more details, see the LICENSE file in the repository.