"""Build a synthetic BI model, export its tables, and render a local report."""

import argparse
from contextlib import closing
import csv
from datetime import date
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent
INPUTS = ('customers', 'products', 'sellers', 'orders', 'order_items')
MODEL_TABLES = ('DimDate', 'DimCustomer', 'DimProduct', 'DimSeller', 'FactOrder', 'FactOrderItem')
DATE_FIELDS = {'purchased_on', 'promised_on', 'delivered_on'}


def load_records(path):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        records = []
        for row in reader:
            for field in DATE_FIELDS.intersection(columns):
                if row[field]:
                    row[field] = date.fromisoformat(row[field]).isoformat()
            records.append(tuple(row[field] or None for field in columns))
    return columns, records


def create_model(data_dir=ROOT / 'data'):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    try:
        db.executescript((ROOT / 'model.sql').read_text(encoding='utf-8'))
        with db:
            for table in INPUTS:
                expected = [row['name'] for row in db.execute(f'PRAGMA table_info({table})')]
                columns, rows = load_records(data_dir / f'{table}.csv')
                if columns != expected:
                    raise ValueError(f'Unexpected header in {table}.csv')
                placeholders = ', '.join('?' for _ in expected)
                db.executemany(f'INSERT INTO {table} VALUES ({placeholders})', rows)
    except Exception:
        db.close()
        raise
    return db


def summarize(db, region=None):
    order_summary = db.execute('''
        SELECT COALESCE(SUM(o.on_time), 0) AS on_time_orders,
               COUNT(o.on_time) AS eligible_orders,
               COUNT(CASE WHEN o.status = 'delivered' AND o.on_time IS NULL THEN 1 END) AS missing_dates,
               COALESCE(SUM(CASE WHEN o.status = 'delivered' THEN o.merchandise_cents END), 0) AS sales_cents
        FROM FactOrder o JOIN DimCustomer c USING (customer_id)
        WHERE (:region IS NULL OR c.region = :region)
    ''', {'region': region}).fetchone()
    line_summary = db.execute('''
        SELECT COALESCE(SUM(o.on_time), 0) AS on_time_lines, COUNT(*) AS eligible_lines
        FROM FactOrderItem i JOIN FactOrder o USING (order_id)
        JOIN DimCustomer c ON o.customer_id = c.customer_id
        WHERE o.on_time IS NOT NULL AND (:region IS NULL OR c.region = :region)
    ''', {'region': region}).fetchone()
    return dict(order_summary) | dict(line_summary)


def build_report(db, output):
    output.mkdir(parents=True, exist_ok=True)
    model_dir = output / 'model'
    model_dir.mkdir(exist_ok=True)
    for table in MODEL_TABLES:
        result = db.execute(f'SELECT * FROM {table} ORDER BY 1, 2')
        with (model_dir / f'{table}.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(column[0] for column in result.description)
            writer.writerows(result)
    regions = [row['region'] for row in db.execute('SELECT DISTINCT region FROM DimCustomer ORDER BY region')]
    statistics = [{'region': 'All regions', **summarize(db)}]
    statistics.extend({'region': region, **summarize(db, region)} for region in regions)
    orders = [dict(row) for row in db.execute('''
        SELECT o.order_id, c.region, o.status, o.item_lines, o.on_time
        FROM FactOrder o JOIN DimCustomer c USING (customer_id) ORDER BY o.order_id
    ''')]
    payload = json.dumps({'statistics': statistics, 'orders': orders}).replace('<', '\\u003c')
    template = (ROOT / 'report.template.html').read_text(encoding='utf-8')
    (output / 'report.html').write_text(template.replace('__REPORT_DATA__', payload), encoding='utf-8', newline='\n')
    return statistics[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build')
    args = parser.parse_args()
    with closing(create_model()) as db:
        statistics = build_report(db, args.output)
    print(f"Order-based answer: {statistics['on_time_orders']}/{statistics['eligible_orders']} orders")
    print(f"Item-weighted comparison: {statistics['on_time_lines']}/{statistics['eligible_lines']} lines")
    print(f'Report: {args.output / "report.html"}')


if __name__ == '__main__':
    main()
