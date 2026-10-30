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

