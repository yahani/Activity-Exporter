import sqlite3
import unittest
from unittest import mock

import demo

export = demo.export_buggy


class ExporterTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch('demo.print_rows'))  # keep test output clean
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(demo.SCHEMA)
        self.conn.execute('INSERT INTO export_state (id, pointer) VALUES (1, ?)', (demo.INITIAL_POINTER,))

    def tearDown(self):
        self.conn.close()

    def start(self, activity_id, now):
        self.conn.execute('INSERT INTO activities (activity_id, start_time) VALUES (?, ?)', (activity_id, now))

    def finish(self, activity_id, score, now):
        self.conn.execute('UPDATE activities SET finish_time = ?, score = ? WHERE activity_id = ?',
                          (now, score, activity_id))

    def exported_ids(self):
        return [r['activity_id'] for r in self.conn.execute('SELECT activity_id FROM exported ORDER BY activity_id')]

    # Regression tests go here.


if __name__ == '__main__':
    unittest.main()
