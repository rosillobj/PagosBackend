import unittest
from .airos_leases import parse_dhcp_leases


class LeaseParsingTests(unittest.TestCase):
    def test_all_rows_on_same_line_with_attributes(self):
        html = '<table><tr><th>MAC</th><th>IP</th></tr>'
        for index in range(1, 4):
            html += f'<tr class="lease"><td>00:11:22:33:44:0{index}</td><td>192.168.0.{index}</td><td>500</td><td>Equipo {index}</td></tr>'
        rows = parse_dhcp_leases(html + '</table>')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]['hostname'], 'Equipo 3')

    def test_multiline_nested_markup_entities_and_duplicates(self):
        row = '<tr>\n<td><span>AA:BB:CC:DD:EE:FF</span></td>\n<td>192.168.0.2</td><td>10 min</td><td>TV&nbsp;&amp; Audio</td></tr>'
        leases = parse_dhcp_leases(row + row)
        self.assertEqual(len(leases), 1)
        self.assertEqual(leases[0]['hostname'], 'TV & Audio')

    def test_empty_and_unrelated_tables(self):
        for html in ('', '<table><tr><td>CPU</td><td>1</td><td>2</td><td>3</td></tr></table>'):
            self.assertEqual(parse_dhcp_leases(html), [])
