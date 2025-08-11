from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import cast

import polars as pl

SCHEMA = {
    "id": pl.Int64,
    "perma_id": pl.String,
    "status": pl.String,
    "desc": pl.String,
    "scheduled": pl.String,
    "deadline": pl.String,
    "created": pl.String,
    "is_visible": pl.Boolean,
    "is_pin": pl.Boolean,
    "done_date": pl.String,
}


def load_tasks(conn: sqlite3.Connection) -> pl.LazyFrame:
    query = "SELECT * FROM tasks"

    return pl.read_database(
        query=query,
        connection=conn,
        schema_overrides=SCHEMA,
    ).lazy()


def save_tasks(tasks: pl.LazyFrame, conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    cursor.execute("DELETE FROM tasks")

    for row in tasks.collect().iter_rows():
        cursor.execute(
            f"INSERT INTO tasks (id, perma_id, status, desc, scheduled, deadline, created, is_visible, is_pin, done_date) VALUES ({','.join(['?' for _ in row])})",
            row,
        )


def add_task(new_tasks: list[str], conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)

    num_new_tasks = len(new_tasks)

    new_tasks_frame = pl.DataFrame(
        {
            "perma_id": [str(uuid.uuid4()) for _ in range(num_new_tasks)],
            "status": ["TODO"] * num_new_tasks,
            "desc": [t.capitalize() for t in new_tasks],
            "scheduled": [None] * num_new_tasks,
            "deadline": [None] * num_new_tasks,
            "created": [datetime.now().isoformat()] * num_new_tasks,
            "is_visible": [True] * num_new_tasks,
            "is_pin": [False] * num_new_tasks,
            "done_date": [None] * num_new_tasks,
        },
        schema_overrides=SCHEMA,
    ).lazy()

    tasks = cast("pl.LazyFrame", pl.concat([tasks.drop("id"), new_tasks_frame]))

    tasks = reindex(tasks)

    save_tasks(tasks, conn)

    list_tasks(conn)


def tag_tasks(task_ids: list[int], str_tags: str, conn: sqlite3.Connection) -> None:
    tags = str_tags.split(",")

    cursor = conn.cursor()

    tags_with_ids = []

    for tag in tags:
        query = "SELECT * FROM tags WHERE tag_desc = ?"

        res = cursor.execute(query, [tag]).fetchone()

        if not res:
            cursor.execute(
                "INSERT INTO tags (tag_desc) VALUES (?)",
                [tag],
            )

            res = cursor.execute(query, [tag]).fetchone()

        tags_with_ids.append(res)

    tags_with_ids = [t[0] for t in tags_with_ids]

    tasks_perma_id_to_tag = cursor.execute(
        "SELECT perma_id from tasks WHERE id IN (%s)" % ",".join("?" for _ in task_ids),
        task_ids,
    ).fetchall()

    tasks_perma_id_to_tag = [perma_id[0] for perma_id in tasks_perma_id_to_tag]

    for task_perma_id, tag_id in product(tasks_perma_id_to_tag, tags_with_ids):
        query = "SELECT * FROM task_tag WHERE task_perma_id = ? AND tag_id = ?"

        res = cursor.execute(query, (task_perma_id, tag_id)).fetchone()

        if res:
            cursor.execute(
                "DELETE FROM task_tag WHERE task_perma_id = ? AND tag_id = ?",
                (task_perma_id, tag_id),
            )

        else:
            cursor.execute(
                "INSERT INTO task_tag (task_perma_id, tag_id) VALUES (?,?)",
                (task_perma_id, tag_id),
            )

    list_tasks(conn)


def pin_task(task_ids: list[int], conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)

    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids), pl.col("is_pin"))
        .then(pl.lit(False))
        .when(pl.col("id").is_in(task_ids), ~(pl.col("is_pin")))
        .then(pl.lit(True))
        .otherwise(pl.col("is_pin"))
        .alias("is_pin"),
    )

    save_tasks(tasks, conn)

    list_tasks(conn)


def toggle_delete(task_ids: list[int], conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)

    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids), pl.col("is_visible"))
        .then(pl.lit(False))
        .when(pl.col("id").is_in(task_ids), ~(pl.col("is_visible")))
        .then(pl.lit(True))
        .otherwise(pl.col("is_visible"))
        .alias("is_visible"),
    )

    tasks = reindex(tasks)

    save_tasks(tasks, conn)

    list_tasks(conn)


def toggle_done(task_ids: list[int], conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)

    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids), pl.col("status") == "DONE")
        .then(pl.lit(None))
        .when(pl.col("id").is_in(task_ids), ~(pl.col("status") == "DONE"))
        .then(pl.lit(datetime.now().date().isoformat()))
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
        pl.when(pl.col("status") != "DONE", pl.col("id").is_in(task_ids))
        .then(pl.lit(True))
        .otherwise(pl.col("is_visible"))
        .alias("is_visible"),
    )

    save_tasks(tasks, conn)

    list_tasks(conn)


def schedule_task(date: str, task_ids: list[int], conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)
    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids))
        .then(pl.lit(date))
        .otherwise(pl.col("scheduled"))
        .alias("scheduled"),
    )

    save_tasks(tasks, conn)

    list_tasks(conn)


def update_task(task_id: int, new_desc: str, conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)
    tasks = tasks.with_columns(
        pl.when(pl.col("id") == task_id)
        .then(pl.lit(new_desc))
        .otherwise(pl.col("desc"))
        .alias("desc"),
    )

    save_tasks(tasks, conn)

    list_tasks(conn)


def set_deadline(date: str, task_ids: list[int], conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)
    tasks = tasks.with_columns(
        pl.when(pl.col("id").is_in(task_ids))
        .then(pl.lit(date))
        .otherwise(pl.col("deadline"))
        .alias("deadline"),
    )

    save_tasks(tasks, conn)

    list_tasks(conn)


def reindex(tasks: pl.LazyFrame) -> pl.LazyFrame:
    return (
        tasks.sort(
            ["is_visible", "is_pin", "status", "scheduled", "deadline"],
            descending=[True, True, True, False, False],
        )
        .drop("id", strict=False)
        .with_row_index("id", offset=1)
    )


def prune_done(conn: sqlite3.Connection) -> None:
    tasks = load_tasks(conn)
    tasks = tasks.with_columns(
        pl.when(pl.col("status") == "DONE")
        .then(pl.lit(False))
        .otherwise(pl.col("is_visible"))
        .alias("is_visible"),
    )

    tasks = reindex(tasks)

    save_tasks(tasks, conn)
    list_tasks(conn)


def purge(task_ids: list[int], conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    tasks_perma_id_to_delete = cursor.execute(
        f"SELECT perma_id from tasks WHERE id IN ({','.join('?' for _ in task_ids)})",
        task_ids,
    ).fetchall()

    tasks_perma_id_to_delete = [perma_id[0] for perma_id in tasks_perma_id_to_delete]

    for task_perma_id in tasks_perma_id_to_delete:
        cursor.execute("DELETE FROM task_tag WHERE task_perma_id = ?", [task_perma_id])

    tasks = load_tasks(conn)
    tasks = tasks.filter(~pl.col("id").is_in(task_ids))
    tasks = reindex(tasks)
    save_tasks(tasks, conn)
    list_tasks(conn)


def load_view(conn: sqlite3.Connection) -> pl.DataFrame:
    query = "SELECT * FROM tasks_with_tag"

    tasks = pl.read_database(
        query=query, connection=conn, schema_overrides=SCHEMA | {"tag_desc": pl.String}
    )

    concat_task_tag = (
        tasks.group_by("id")
        .agg(pl.col("tag_desc"))
        .with_columns(pl.col("tag_desc").list.join(", ").alias("tags"))
        .drop("tag_desc")
    )

    return (
        tasks.drop("tag_desc")
        .unique(subset=["id"])
        .join(concat_task_tag, on="id", how="inner", validate="1:1")
    )


def dump_tasks(conn: sqlite3.Connection, regex: str | None = None) -> None:
    task_to_print = load_view(conn).sort("id", descending=False)

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


def list_tasks(conn: sqlite3.Connection, regex: str | None = None) -> None:
    tasks = load_view(conn).sort(["is_pin", "id"], descending=[True, False])

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

                show_cols = ["pin", "id", "status", "desc", "tags"]

            else:
                show_cols = ["id", "status", "desc", "tags"]

            task_to_print = task_to_print.with_columns(
                pl.all().cast(pl.String).fill_null(""),
            )

            if any(task_to_print["scheduled"]):
                show_cols.append("scheduled")

            if any(task_to_print["deadline"]):
                show_cols.append("deadline")

            task_to_print = task_to_print.select(show_cols).with_columns(
                pl.all().fill_null("")
            )

            print(task_to_print)

    else:
        print("No active tasks found.")


def parse_list_of_int(list_of_int: list[str]) -> list[int]:
    return [int(s) for s in list_of_int]


def init_db(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER,
            perma_id TEXT PRIMARY KEY,
            status TEXT CHECK(status IN ('DONE', 'TODO')),
            desc TEXT,
            scheduled TEXT,
            deadline TEXT,
            created TEXT,
            is_visible INTEGER CHECK(is_visible IN (0, 1)),
            is_pin INTEGER CHECK(is_pin IN (0, 1)),
            done_date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            tag_id INTEGER PRIMARY KEY,
            tag_desc TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_tag (
            task_perma_id TEXT,
            tag_id INTEGER,
            FOREIGN KEY(task_perma_id) REFERENCES tasks(perma_id)
                DEFERRABLE INITIALLY DEFERRED,
            FOREIGN KEY(tag_id) REFERENCES tags(tag_id)
                DEFERRABLE INITIALLY DEFERRED
        )
    """)

    cursor.execute("""
        CREATE VIEW IF NOT EXISTS tasks_with_tag AS
        SELECT tasks.*,
        tags.tag_desc
        FROM tasks
        LEFT JOIN task_tag on tasks.perma_id = task_tag.task_perma_id
        LEFT JOIN tags on task_tag.tag_id = tags.tag_id
    """)


def main() -> None:
    DATA_PATH = Path("~/.config/nullus/").expanduser()
    TASKS_FILE = "task.db"

    data_file_path = DATA_PATH / TASKS_FILE

    conn = sqlite3.connect(data_file_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    init_db(conn)

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
        "-t",
        "--tag",
        nargs="+",
        metavar=("TASK_IDS", "TAGS"),
        help="add/remove comma-seperated tag(s) to tasks(s)",
    )

    group.add_argument(
        "-u",
        "--update",
        nargs=2,
        metavar=("TASK_ID", "DESC"),
        help="update task description",
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
        list_tasks(conn)

    if args.list:
        list_tasks(conn, args.list)

    if args.add:
        add_task(args.add, conn)

    if args.tag:
        *task_ids, tags = args.tag
        task_ids = parse_list_of_int(task_ids)
        tag_tasks(task_ids, tags, conn)

    if args.update:
        task_id, new_desc = args.update
        task_id = int(task_id)
        update_task(task_id, new_desc, conn)

    if args.pin:
        pin_task(args.pin, conn)

    if args.done:
        toggle_done(args.done, conn)

    if args.schedule:
        date, *task_ids = args.schedule
        task_ids = parse_list_of_int(task_ids)
        schedule_task(date, task_ids, conn)

    if args.deadline:
        date, *task_ids = args.deadline
        task_ids = parse_list_of_int(task_ids)
        set_deadline(date, task_ids, conn)

    if args.prune:
        prune_done(conn)

    if args.dump:
        dump_tasks(conn)

    if args.dumpr:
        dump_tasks(conn, args.dumpr[0])

    if args.delete:
        toggle_delete(args.delete, conn)

    if args.purge:
        task_ids = parse_list_of_int(args.purge)
        purge(task_ids, conn)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
