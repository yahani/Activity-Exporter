"""Activity exporter demo.

Copies finished activities from the `activities` table to the `exported`
table (a stand-in for a reporting system). Every command takes a fake clock
via --now so events and exporter runs happen exactly when you say.

    python demo.py start A1 --now "2026-10-26 11:58"
    python demo.py finish A1 3 --now "2026-10-26 12:02"
    python demo.py export --now "2026-10-26 12:01"
    python demo.py show
    python demo.py missing
    python demo.py reset
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name('activities.db')
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
INITIAL_POINTER = '2026-10-26 00:00:00'

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id TEXT PRIMARY KEY,
    start_time  TEXT NOT NULL,
    finish_time TEXT,
    score       INTEGER
);
CREATE TABLE IF NOT EXISTS exported (
    activity_id TEXT PRIMARY KEY,
    start_time  TEXT NOT NULL,
    finish_time TEXT NOT NULL,
    score       INTEGER,
    exported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_state (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    pointer TEXT NOT NULL
);
"""


# --- helpers -----------------------------------------------------------------

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute('INSERT OR IGNORE INTO export_state (id, pointer) VALUES (1, ?)', (INITIAL_POINTER,))
    conn.commit()
    return conn


def parse_time(value):
    """Accept 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH:MM:SS'; return 'YYYY-MM-DD HH:MM:SS'."""
    for fmt in (TIME_FORMAT, '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(value, fmt).strftime(TIME_FORMAT)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f'bad time {value!r}, expected "YYYY-MM-DD HH:MM[:SS]"')


def get_pointer(conn):
    return conn.execute('SELECT pointer FROM export_state WHERE id = 1').fetchone()['pointer']


def set_pointer(conn, pointer):
    conn.execute('UPDATE export_state SET pointer = ? WHERE id = 1', (pointer,))


def print_rows(title, rows, columns):
    print(f'\n{title}')
    if not rows:
        print('  (none)')
        return
    values = [[('NULL' if row[c] is None else str(row[c])) for c in columns] for row in rows]
    widths = [max(len(c), *(len(v[i]) for v in values)) for i, c in enumerate(columns)]
    print('  ' + '  '.join(c.ljust(w) for c, w in zip(columns, widths)))
    print('  ' + '  '.join('-' * w for w in widths))
    for v in values:
        print('  ' + '  '.join(x.ljust(w) for x, w in zip(v, widths)))


# --- commands ----------------------------------------------------------------

def cmd_start(conn, args):
    try:
        conn.execute('INSERT INTO activities (activity_id, start_time) VALUES (?, ?)', (args.activity_id, args.now))
    except sqlite3.IntegrityError:
        sys.exit(f'activity {args.activity_id} already exists')
    conn.commit()
    print(f'[{args.now}] {args.activity_id} started')


def cmd_finish(conn, args):
    row = conn.execute('SELECT * FROM activities WHERE activity_id = ?', (args.activity_id,)).fetchone()
    if row is None:
        sys.exit(f'activity {args.activity_id} does not exist')
    if row['finish_time'] is not None:
        sys.exit(f'activity {args.activity_id} already finished at {row["finish_time"]}')
    conn.execute(
        'UPDATE activities SET finish_time = ?, score = ? WHERE activity_id = ?',
        (args.now, args.score, args.activity_id),
    )
    conn.commit()
    print(f'[{args.now}] {args.activity_id} finished with score {args.score}')


def export_activities(conn, now):
    pointer_before = get_pointer(conn)
    rows = conn.execute(
        """
        SELECT * FROM activities
        WHERE start_time > ? AND finish_time IS NOT NULL
        ORDER BY start_time
        """,
        (pointer_before,),
    ).fetchall()
    print_rows(f'Eligible rows (start_time > {pointer_before} AND finish_time IS NOT NULL)', rows,
               ['activity_id', 'start_time', 'finish_time', 'score'])

    for row in rows:
        conn.execute(
            'INSERT OR REPLACE INTO exported (activity_id, start_time, finish_time, score, exported_at) VALUES (?, ?, ?, ?, ?)',
            (row['activity_id'], row['start_time'], row['finish_time'], row['score'], now),
        )
    if rows:
        set_pointer(conn, max(row['start_time'] for row in rows))
    conn.commit()
    return pointer_before, rows


def cmd_export(conn, args):
    print(f'=== export run at {args.now} ===')
    pointer_before, sent = export_activities(conn, args.now)
    print(f'\nSent:    {", ".join(r["activity_id"] for r in sent) or "nothing"}')
    print(f'Pointer: {pointer_before} -> {get_pointer(conn)}')


def cmd_show(conn, args):
    print_rows('activities', conn.execute('SELECT * FROM activities ORDER BY start_time').fetchall(),
               ['activity_id', 'start_time', 'finish_time', 'score'])
    print_rows('exported', conn.execute('SELECT * FROM exported ORDER BY exported_at, activity_id').fetchall(),
               ['activity_id', 'start_time', 'finish_time', 'score', 'exported_at'])
    print(f'\nexport_state.pointer = {get_pointer(conn)}')


def cmd_missing(conn, args):
    rows = conn.execute(
        """
        SELECT a.* FROM activities a
        LEFT JOIN exported e ON e.activity_id = a.activity_id
        WHERE a.finish_time IS NOT NULL AND e.activity_id IS NULL
        ORDER BY a.start_time
        """
    ).fetchall()
    print_rows('Finished activities that never reached the reporting system', rows,
               ['activity_id', 'start_time', 'finish_time', 'score'])


def cmd_reset(conn, args):
    conn.execute('DELETE FROM activities')
    conn.execute('DELETE FROM exported')
    set_pointer(conn, INITIAL_POINTER)
    conn.commit()
    print(f'reset: tables emptied, pointer = {INITIAL_POINTER}')


# --- CLI ---------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(description='Activity exporter demo')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('start', help='an activity starts')
    p.add_argument('activity_id')
    p.add_argument('--now', type=parse_time, required=True)
    p.set_defaults(func=cmd_start)

    p = sub.add_parser('finish', help='an activity finishes')
    p.add_argument('activity_id')
    p.add_argument('score', type=int)
    p.add_argument('--now', type=parse_time, required=True)
    p.set_defaults(func=cmd_finish)

    p = sub.add_parser('export', help='run the exporter once')
    p.add_argument('--now', type=parse_time, required=True)
    p.set_defaults(func=cmd_export)

    sub.add_parser('show', help='print all tables').set_defaults(func=cmd_show)
    sub.add_parser('missing', help='finished activities not exported').set_defaults(func=cmd_missing)
    sub.add_parser('reset', help='empty tables and reset the pointer').set_defaults(func=cmd_reset)
    return parser


def main():
    args = build_parser().parse_args()
    conn = connect()
    try:
        args.func(conn, args)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
