#!/usr/bin/env python3
"""Export/resolve a stopped database's legacy work-event decisions; never change old counters.

The exported facts are hints, not proof of a historical aggregate write. A decision
must cite the independently checked work/history and Redis backup evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess

from registration_upgrade import mysql_command, ordinary, private_file, sha256

FACTS = """SELECT JSON_OBJECT('work_id',e.work_id,'event_type',e.event_type,
 'depart_id',e.depart_id,'event_state',e.event_state,'work_status',w.work_status,
 'feedback_rows',(SELECT COUNT(*) FROM teaching_work_correct c WHERE c.work_id=e.work_id),
 'history_rows',(SELECT COUNT(*) FROM sys_data_log h WHERE h.data_table='teaching_work' AND h.data_id=e.work_id))
 FROM teaching_work_event e LEFT JOIN teaching_work w ON w.id=e.work_id
 WHERE e.event_state='LEGACY_REVIEW' ORDER BY e.work_id,e.event_type"""


def query(command, statement):
    result = subprocess.run(command, input=statement, text=True, capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError('MySQL rejected work-event review; inspect diagnostics privately')
    return result.stdout.strip()


def snapshot(command, database):
    rows = [json.loads(line) for line in query(command, FACTS).splitlines() if line]
    for row in rows:
        row.update(decision=None, evidence=None)
    return {'format': 1, 'database': database, 'events': rows}


def literal(value):
    return "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)"


def apply_review(command, database, review, backup, writes_stopped=False):
    if not writes_stopped:
        raise ValueError('Stop application/admin writes and explicitly confirm the maintenance window')
    backup = private_file(backup)
    if not backup.stat().st_size:
        raise ValueError('A nonempty private independent backup is required')
    if review.get('format') != 1 or review.get('database') != database:
        raise ValueError('Review format or database mismatch')
    current = snapshot(command, database)
    decisions = review.get('events')
    if not isinstance(decisions, list) or len(decisions) != len(current['events']):
        raise ValueError('Review must cover every pending event in the unchanged snapshot')
    for expected, supplied in zip(current['events'], decisions):
        if {k:v for k,v in supplied.items() if k not in ('decision','evidence')} != {k:v for k,v in expected.items() if k not in ('decision','evidence')}:
            raise ValueError('Legacy event snapshot changed; export and review again')
        if supplied.get('decision') not in ('READY','LEGACY_UNRESOLVED') or not isinstance(supplied.get('evidence'), str) or len(supplied['evidence'].strip()) < 12:
            raise ValueError('Every event needs a decision and concrete evidence reference (not only current status)')
    routine = 'teachingopen_work_review_' + secrets.token_hex(8)
    sql = ['DELIMITER $$', 'CREATE PROCEDURE ' + routine + '()', 'BEGIN',
           'DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;', 'START TRANSACTION;',
           "IF (SELECT COUNT(*) FROM teaching_work_event WHERE event_state='LEGACY_REVIEW') <> " + str(len(decisions)) + " THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Pending event set changed'; END IF;"]
    for row in decisions:
        sql.append("UPDATE teaching_work_event SET event_state=" + literal(row['decision']) + " WHERE work_id=" + literal(row['work_id']) + " AND event_type=" + literal(row['event_type']) + " AND depart_id=" + literal(row['depart_id']) + " AND event_state='LEGACY_REVIEW';")
        sql.append("IF ROW_COUNT() <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Event changed during review'; END IF;")
    sql += ['COMMIT;', 'END$$', 'DELIMITER ;', 'CALL ' + routine + '();', 'DROP PROCEDURE ' + routine + ';']
    try:
        query(command, '\n'.join(sql))
    finally:
        # Unique per invocation; never remove another operator's migration routine.
        query(command, 'DROP PROCEDURE IF EXISTS ' + routine)
    return {'resolved': len(decisions), 'backup_sha256': sha256(backup), 'historical_counters_changed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('export','apply'))
    parser.add_argument('--mysql', required=True, type=Path)
    parser.add_argument('--option-file', required=True, type=Path)
    parser.add_argument('--database', required=True)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--writes-stopped', action='store_true')
    args = parser.parse_args()
    command = mysql_command(args.mysql, args.option_file, args.database)
    if args.action == 'export':
        result = snapshot(command, args.database)
        with os.fdopen(os.open(args.review, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print('Exported', len(result['events']), 'pending decisions; no database writes')
    else:
        if args.backup is None:
            parser.error('--backup is required for apply')
        review = json.loads(private_file(args.review).read_text())
        result = apply_review(command, args.database, review, args.backup, args.writes_stopped)
        result['review_sha256'] = hashlib.sha256(args.review.read_bytes()).hexdigest()
        print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
