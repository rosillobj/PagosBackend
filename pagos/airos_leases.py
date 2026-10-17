"""Parse every DHCP lease row without passing HTML through the status parser."""
from html.parser import HTMLParser
import re


class LeaseTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
            self.cell = None


def parse_dhcp_leases(raw):
    parser = LeaseTableParser()
    parser.feed(raw or '')
    leases = []
    seen = set()
    for cells in parser.rows:
        if len(cells) < 4:
            continue
        mac, ip, remaining, hostname = cells[:4]
        if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', mac):
            continue
        key = (mac.lower(), ip)
        if key in seen:
            continue
        seen.add(key)
        leases.append({'mac': mac, 'ip': ip, 'remaining': remaining, 'hostname': hostname})
    return leases
