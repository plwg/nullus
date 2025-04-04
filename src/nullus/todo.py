import argparse
from datetime import datetime
from pathlib import Path

import polars as pl

DATA_PATH = Path("~/.config/nullus/").expanduser()
TASKS_FILE = "task.csv"

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
    try:
        tasks = pl.scan_csv(DATA_PATH / TASKS_FILE, schema_overrides=SCHEMA)
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
        ).lazy()
    return tasks


def save_tasks(tasks):
    DATA_PATH.mkdir(parents=True, exist_ok=True)

    tasks.collect().write_csv(DATA_PATH / TASKS_FILE)


def add_task(new_tasks):
    tasks = load_tasks()

    num_new_tasks = len(new_tasks)

    new_tasks = pl.DataFrame(
        {
            "id": [None] * num_new_tasks,
            "status": ["TODO"] * num_new_tasks,
            "desc": [t.capitalize() for t in new_tasks],
            "scheduled": [None] * num_new_tasks,
            "deadline": [None] * num_new_tasks,
            "created": [datetime.now()] * num_new_tasks,
            "is_visible": [True] * num_new_tasks,
            "is_pin": [False] * num_new_tasks,
            "done_date": [None] * num_new_tasks,
        },
        schema_overrides=SCHEMA,
    ).lazy()

    tasks = pl.concat([tasks, new_tasks])

    tasks = reindex(tasks)

    save_tasks(tasks)

    list_tasks()


def pin_task(task_ids):
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

    list_tasks()


def toggle_delete(task_ids):
    tasks = load_tasks()

    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids), pl.col("is_visible"))
        .then(pl.lit(False))
        .when(pl.col("id").is_in(task_ids), ~(pl.col("is_visible")))
        .then(pl.lit(True))
        .otherwise(pl.col("is_visible"))
        .alias("is_visible"),
    )

    tasks = reindex(tasks)

    save_tasks(tasks)

    list_tasks()


def toggle_done(task_ids):
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

    list_tasks()


def schedule_task(date, task_ids):
    tasks = load_tasks()
    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids))
        .then(pl.lit(date).cast(pl.Date))
        .otherwise(pl.col("scheduled"))
        .alias("scheduled"),
    )

    save_tasks(tasks)

    list_tasks()


def update_task(task_id, new_desc):
    tasks = load_tasks()
    tasks = tasks.with_columns(
        pl.when(pl.col("id") == task_id)
        .then(pl.lit(new_desc))
        .otherwise(pl.col("desc"))
        .alias("desc"),
    )

    save_tasks(tasks)

    list_tasks()


def set_deadline(date, task_ids):
    tasks = load_tasks()
    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids))
        .then(pl.lit(date).cast(pl.Date))
        .otherwise(pl.col("deadline"))
        .alias("deadline"),
    )

    save_tasks(tasks)

    list_tasks()


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
    tasks = load_tasks()
    tasks = tasks.with_columns(
        pl.when(pl.col("status") == "DONE")
        .then(pl.lit(False))
        .otherwise(pl.col("is_visible"))
        .alias("is_visible"),
    )

    tasks = reindex(tasks)

    save_tasks(tasks)

    list_tasks()


def purge(task_ids):
    tasks = load_tasks()
    tasks = tasks.filter(~pl.col("id").is_in(task_ids))
    tasks = reindex(tasks)
    save_tasks(tasks)

    list_tasks()


def dump_tasks(regex=None):
    task_to_print = load_tasks().collect()

    if regex:
        regex = regex.lower()

        task_to_print = task_to_print.filter(
            pl.concat_str(pl.all().cast(pl.String), ignore_nulls=True)
            .str.to_lowercase()
            .str.contains(regex),
        )

    with pl.Config(
        tbl_rows=-1,
        tbl_cols=-1,
        tbl_hide_column_data_types=True,
        set_tbl_hide_dataframe_shape=True,
        set_fmt_str_lengths=80,
    ):
        print(task_to_print)


def list_tasks(regex=None):
    """List all tasks or filter by regex."""
    tasks = load_tasks()

    task_to_print = tasks.filter(pl.col("is_visible")).collect()

    if regex:
        regex = regex.lower()

        task_to_print = task_to_print.filter(
            pl.concat_str(pl.all().cast(pl.String), ignore_nulls=True)
            .str.to_lowercase()
            .str.contains(regex),
        )

    if not task_to_print.is_empty():
        with pl.Config(
            tbl_rows=-1,
            tbl_cols=-1,
            tbl_hide_column_data_types=True,
            set_tbl_hide_dataframe_shape=True,
            set_fmt_str_lengths=80,
        ):
            if any(task_to_print["is_pin"]):
                task_to_print = task_to_print.with_columns(
                    pl.when(pl.col("is_pin"))
                    .then(pl.lit("*"))
                    .otherwise(pl.lit(""))
                    .alias("pin"),
                )

                sort_cols = ["is_pin", "status", "scheduled", "deadline"]
                sort_order = [True, True, True, True]
                show_cols = ["pin", "id", "status", "desc"]

            else:
                sort_cols = ["status", "scheduled", "deadline"]
                sort_order = [True, True, True]
                show_cols = ["id", "status", "desc"]

            task_to_print = task_to_print.with_columns(
                pl.all().cast(pl.String).fill_null("")
            )

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
        help="list active task(s) matching a regex; list all if regex is left empty",
    )

    group.add_argument(
        "-a",
        "--add",
        nargs="+",
        metavar="TASK",
        help="add task(s) and reassign task id(s)",
    )

    group.add_argument(
        "-u",
        "--update",
        nargs=2,
        metavar=("TASK_ID", "DESC"),
        help="update task description",
    )

    group.add_argument(
        "-d",
        "--done",
        nargs="+",
        metavar="TASK_ID",
        type=int,
        help="toggle task(s) between todo and done and reassign task id(s)",
    )

    group.add_argument(
        "-s",
        "--schedule",
        nargs="+",
        metavar=("DATE", "TASK_ID"),
        help="schedule task(s) to a specific DATE (YYYY-MM-DD)",
    )

    group.add_argument(
        "--deadline",
        nargs="+",
        metavar=("DATE", "TASK_ID"),
        help="give task(s) a deadline (YYYY-MM-DD)",
    )

    group.add_argument(
        "-p",
        "--pin",
        nargs="+",
        metavar="TASK_ID",
        type=int,
        help="pin task(s)",
    )

    group.add_argument(
        "--delete",
        nargs="+",
        metavar="TASK_ID",
        type=int,
        help="toggle tasks visibility and reassign task id(s)",
    )

    group.add_argument(
        "--prune",
        action="store_true",
        help="set done task(s) visibility to false and reassign task id(s)",
    )

    group.add_argument(
        "--purge",
        nargs="+",
        metavar="TASK_ID",
        type=int,
        help="remove task(s) from storage",
    )

    group.add_argument(
        "--dump",
        action="store_true",
        help="list active and inactive tasks",
    )

    group.add_argument(
        "--dumpr",
        nargs=1,
        metavar="REGEX",
        help="list active and inactive tasks matching a regex",
    )

    args = parser.parse_args()

    if not any(vars(args).values()):
        list_tasks()

    if args.list:
        list_tasks(args.list)

    if args.add:
        add_task(args.add)

    if args.update:
        task_id, new_desc = args.update
        task_id = int(task_id)
        update_task(task_id, new_desc)

    if args.pin:
        pin_task(args.pin)

    if args.done:
        toggle_done(args.done)

    if args.schedule:
        date, *task_ids = args.schedule
        task_ids = list(map(int, task_ids))
        schedule_task(date, task_ids)

    if args.deadline:
        date, *task_ids = args.deadline
        task_ids = list(map(int, task_ids))
        set_deadline(date, task_ids)

    if args.prune:
        prune_done()

    if args.dump:
        dump_tasks()

    if args.dumpr:
        dump_tasks(args.dumpr[0])

    if args.delete:
        toggle_delete(args.delete)

    if args.purge:
        task_ids = list(map(int, args.purge))
        purge(task_ids)

    return


if __name__ == "__main__":
    main()
