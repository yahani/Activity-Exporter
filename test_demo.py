import sqlite3
import unittest
from unittest import mock

import demo
import exporter

export = exporter.export_activities

# python3 -m unittest -v 2>&1 | tee test_results_before.txt
# python3 -m unittest -v 2>&1 | tee test_results_after.txt

class ExporterTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch('exporter.print_rows'))  # keep test output clean
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
    def test_activity_finishing_after_a_later_one_is_exported(self):
        self.start('A1', '2026-10-26 11:58:00')
        self.start('A2', '2026-10-26 11:59:00')
        self.finish('A2', 4, '2026-10-26 12:00:00')
        export(self.conn, '2026-10-26 12:01:00')
        self.finish('A1', 3, '2026-10-26 12:02:00')
        export(self.conn, '2026-10-26 12:06:00')

        self.assertEqual(self.exported_ids(), ['A1', 'A2'])

    def test_every_finished_activity_is_exported_exactly_once(self):
        activities = {'A0': ('11:50', '12:04'), 'A1': ('11:52', '11:55'), 'A2': ('11:58', '12:01'),
                      'A3': ('12:00', '12:09'), 'A4': ('12:03', '12:05')}
        # (time, order, kind, id): at the same minute, writes happen before the export run
        events = sorted([(s, 0, 'start', a) for a, (s, f) in activities.items()]
                        + [(f, 1, 'finish', a) for a, (s, f) in activities.items()]
                        + [(run, 2, 'export', None) for run in ['11:56', '12:01', '12:06', '12:11']])
        sent = []
        for time, _, kind, activity_id in events:
            now = f'2026-10-26 {time}:00'
            if kind == 'start':
                self.start(activity_id, now)
            elif kind == 'finish':
                self.finish(activity_id, 1, now)
            else:
                _, rows = export(self.conn, now)
                sent += [r['activity_id'] for r in rows]

        self.assertCountEqual(sent, activities)
        self.assertEqual(len(sent), len(set(sent)))

    def test_activity_finishing_exactly_at_run_time_is_sent_once(self):
        self.start('A1', '2026-10-26 11:58:00')
        self.finish('A1', 3, '2026-10-26 12:01:00')
        _, first = export(self.conn, '2026-10-26 12:01:00')
        _, second = export(self.conn, '2026-10-26 12:06:00')

        self.assertEqual([r['activity_id'] for r in first], ['A1'])
        self.assertEqual(second, [])

    def test_repeated_runs_without_new_data_send_nothing(self):
        self.start('A1', '2026-10-26 11:58:00')
        self.finish('A1', 3, '2026-10-26 12:00:00')
        export(self.conn, '2026-10-26 12:01:00')
        pointers = []
        for run in ['12:06', '12:11', '12:16']:
            _, rows = export(self.conn, f'2026-10-26 {run}:00')
            self.assertEqual(rows, [])
            pointers.append(demo.get_pointer(self.conn))

        self.assertEqual(pointers, sorted(pointers))

    def test_unfinished_activity_does_not_block_others(self):
        self.start('A1', '2026-10-26 11:58:00')
        self.start('A2', '2026-10-26 11:59:00')
        self.finish('A2', 4, '2026-10-26 12:00:00')
        export(self.conn, '2026-10-26 12:01:00')
        self.start('A3', '2026-10-26 12:02:00')
        self.finish('A3', 5, '2026-10-26 12:03:00')
        export(self.conn, '2026-10-26 12:06:00')

        self.assertEqual(self.exported_ids(), ['A2', 'A3'])

    def test_resending_an_exported_activity_does_not_fail(self):
        self.start('A1', '2026-10-26 11:58:00')
        self.finish('A1', 3, '2026-10-26 12:00:00')
        export(self.conn, '2026-10-26 12:01:00')
        demo.set_pointer(self.conn, demo.INITIAL_POINTER)
        export(self.conn, '2026-10-26 12:06:00')

        self.assertEqual(self.exported_ids(), ['A1'])



if __name__ == '__main__':
    unittest.main()
