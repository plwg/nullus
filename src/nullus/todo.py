import argparse
from datetime import datetime
from pathlib import Path

import polars as pl

TASKS_FILE = Path("~/data/task.csv").expanduser()

SCHEMA = {
    "id": pl.Int64,
    "status": pl.Enum(["DONE", "TODO"]),
    "desc": pl.String,
    "scheduled": pl.Date,
    "deadline": pl.Date,
    "created": pl.Datetime,
    "is_visible": pl.Boolean,
    "is_pin": pl.Boolean,
    "done_date": pl.Date,
}


def load_tasks():
    """Load tasks from the text file."""
    try:
        tasks = pl.read_csv(TASKS_FILE, schema_overrides=SCHEMA)
    except (FileNotFoundError, pl.exceptions.NoDataError):
        tasks = pl.DataFrame(
            {
                "id": [],
                "status": [],
                "desc": [],
                "scheduled": [],
                "deadline": [],
                "created": [],
                "is_visible": [],
                "is_pin": [],
                "done_date": [],
            },
            schema_overrides=SCHEMA,
        )
    return tasks


def save_tasks(tasks):
    """Save tasks back to the text file."""
    tasks.write_csv(TASKS_FILE)


def add_task(task):
    """Add a task to the tasks list."""
    tasks = load_tasks()

    if not tasks.is_empty():
        task_id = tasks["id"].max() + 1

    else:
        task_id = 1

    task = pl.DataFrame(
        {
            "id": [task_id],
            "status": ["TODO"],
            "desc": [task],
            "scheduled": [None],
            "deadline": [None],
            "created": [datetime.now()],
            "is_visible": [True],
            "is_pin": [False],
            "done_date": [None],
        },
        schema_overrides=SCHEMA,
    )

    tasks = pl.concat([tasks, task])

    tasks = reindex(tasks)

    save_tasks(tasks)


def pin_task(task_ids):
    """Pin tasks by their IDs."""
    tasks = load_tasks()

    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids), pl.col("is_pin"))
        .then(pl.lit(False))
        .when(pl.col("id").is_in(task_ids), ~(pl.col("is_pin")))
        .then(pl.lit(True))
        .otherwise(pl.col("is_pin"))
        .alias("is_pin"),
    )

    save_tasks(tasks)


def mark_done(task_ids):
    """Mark tasks as done by their IDs."""
    tasks = load_tasks()

    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids), pl.col("status") == "DONE")
        .then(pl.lit(None))
        .when(pl.col("id").is_in(task_ids), ~(pl.col("status") == "DONE"))
        .then(pl.lit(datetime.now().date()))
        .otherwise(pl.col("done_date"))
        .alias("done_date"),
    )

    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids), pl.col("status") == "DONE")
        .then(pl.lit("TODO"))
        .when(pl.col("id").is_in(task_ids), ~(pl.col("status") == "DONE"))
        .then(pl.lit("DONE"))
        .otherwise(pl.col("status"))
        .alias("status"),
    )

    tasks = tasks.with_columns(
        pl.when(~(pl.col("status") == "DONE"))
        .then(pl.lit(True))
        .otherwise(pl.col("is_visible"))
        .alias("is_visible"),
    )

    save_tasks(tasks)


def schedule_task(date, task_ids):
    """Schedule tasks for a specific date."""
    tasks = load_tasks()
    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids))
        .then(pl.lit(date).cast(pl.Date))
        .otherwise(pl.col("scheduled"))
        .alias("scheduled"),
    )
    save_tasks(tasks)


def set_deadline(date, task_ids):
    """Assign a deadline to tasks."""
    tasks = load_tasks()
    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids))
        .then(pl.lit(date).cast(pl.Date))
        .otherwise(pl.col("deadline"))
        .alias("deadline"),
    )
    save_tasks(tasks)


def reindex(tasks):
    tasks = (
        tasks.sort(
            ["is_visible", "is_pin", "status", "scheduled", "deadline"],
            descending=[True, True, True, False, False],
        )
        .drop("id")
        .with_row_index("id", offset=1)
    )

    return tasks


def prune_done():
    """Prune all done tasks and reassign task IDs."""
    tasks = load_tasks()
    tasks = tasks.with_columns(
        pl.when(pl.col("status") == "DONE")
        .then(pl.lit(False))
        .otherwise(pl.col("is_visible"))
        .alias("is_visible"),
    )

    tasks = reindex(tasks)

    save_tasks(tasks)


def dump_tasks():
    tasks = load_tasks()

    with pl.Config(tbl_rows=-1, tbl_cols=-1):
        print(tasks)


def list_tasks(regex=None):
    """List all tasks or filter by regex."""
    tasks = load_tasks()

    task_to_print = tasks.filter(pl.col("is_visible"))

    if regex:
        regex = regex.lower()

        task_to_print = task_to_print.filter(
            pl.concat_str(pl.all().cast(pl.String), ignore_nulls=True)
            .str.to_lowercase()
            .str.contains(regex),
        )

    if not task_to_print.is_empty():
        with pl.Config(
            tbl_hide_column_data_types=True, set_tbl_hide_dataframe_shape=True,
        ):
            if any(task_to_print["is_pin"]):
                task_to_print = task_to_print.with_columns(
                    pl.when(pl.col("is_pin"))
                    .then(pl.lit("*"))
                    .otherwise(pl.lit(""))
                    .alias("pin"),
                )

                sort_cols = ["is_pin", "status", "scheduled", "deadline"]
                sort_order = [True, True, False, False]
                show_cols = ["pin", "id", "status", "desc"]

            else:
                sort_cols = ["status", "scheduled", "deadline"]
                sort_order = [True, False, False]
                show_cols = ["id", "status", "desc"]

            if any(task_to_print["scheduled"]):
                show_cols.append("scheduled")

            if any(task_to_print["deadline"]):
                show_cols.append("deadline")

            task_to_print = (
                task_to_print.sort(
                    sort_cols,
                    descending=sort_order,
                )
                .select(show_cols)
                .with_columns(pl.all().fill_null(""))
            )

            print(task_to_print)

    else:
        print("No active tasks found.")


def main():
    parser = argparse.ArgumentParser(description="CLI To-Do List")
    group = parser.add_mutually_exclusive_group()

    # Argument definitions
    group.add_argument(
        "-l",
        "--list",
        nargs="?",
        metavar="REGEX",
        help="List active task(s) matching a regex; list all if regex is left empty",
    )

    group.add_argument(
        "-p", "--pin", nargs="+", metavar="TASK_ID", type=int, help="Pin task(s)",
    )

    group.add_argument("-a", "--add", nargs="+", metavar="TASK", help="Add task(s)")

    group.add_argument(
        "-d",
        "--done",
        nargs="+",
        metavar="TASK_ID",
        type=int,
        help="Mark task(s) as done",
    )

    group.add_argument(
        "-s",
        "--schedule",
        nargs="+",
        metavar=("DATE", "TASK_ID"),
        help="Schedule task(s) to a specific DATE (YYYY-MM-DD)",
    )

    group.add_argument(
        "--deadline",
        nargs="+",
        metavar=("DATE", "TASK_ID"),
        help="Give task(s) a deadline (YYYY-MM-DD)",
    )

    group.add_argument(
        "--prune",
        action="store_true",
        help="Prune done task(s) and reassign task id(s)",
    )

    group.add_argument(
        "--dump",
        action="store_true",
        help="List active and inactive tasks matching a regex; list all if regex is left empty",
    )

    args = parser.parse_args()

    if not any(vars(args).values()):
        list_tasks()

    if args.list:
        list_tasks(args.list)

    if args.add:
        for task in args.add:
            add_task(task)

    if args.pin:
        pin_task(args.pin)

    if args.done:
        mark_done(args.done)

    if args.schedule:
        date, *task_ids = args.schedule
        task_ids = list(map(int, task_ids))  # Convert IDs to integers
        schedule_task(date, task_ids)

    if args.deadline:
        date, *task_ids = args.deadline
        task_ids = list(map(int, task_ids))  # Convert IDs to integers
        set_deadline(date, task_ids)

    if args.prune:
        prune_done()

    if args.dump:
        dump_tasks()


if __name__ == "__main__":
    main()
