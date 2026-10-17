import unittest
from .traffic_metrics import average, counters, select_queue


class TrafficMetricsTests(unittest.TestCase):
    def test_average_includes_idle_seconds_and_directions(self):
        result = average((100, 200), (3_000_100, 15_000_200), 30)
        self.assertEqual(result['upload_mbps'], 0.8)
        self.assertEqual(result['download_mbps'], 4)
        self.assertEqual(result['upload_mb'], 3)
        self.assertEqual(result['download_mb'], 15)

    def test_uses_actual_elapsed_time(self):
        self.assertEqual(average((0, 0), (4_000_000, 0), 32)['upload_mbps'], 1)

    def test_idle_client_is_zero(self):
        self.assertEqual(average((10, 20), (10, 20), 30)['download_mbps'], 0)

    def test_counter_reset_is_not_reported_as_zero(self):
        with self.assertRaises(ValueError):
            average((100, 200), (20, 250), 30)

    def test_individual_queue_excludes_parent(self):
        rows = [{'target': '192.168.1.0/24'}, {'target': '192.168.1.153/32', '.id': '*2'}]
        self.assertEqual(select_queue(rows, '192.168.1.153')['.id'], '*2')

    def test_missing_duplicate_and_disabled_queues_fail(self):
        row = {'target': '192.168.1.153/32'}
        for rows in ([], [row, row], [{**row, 'disabled': 'true'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                select_queue(rows, '192.168.1.153')

    def test_routeros_bytes_order_and_malformed_counters(self):
        self.assertEqual(counters({'bytes': '120/456'}), (120, 456))
        for value in ('', '10', 'a/b', '-1/10'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                counters({'bytes': value})
