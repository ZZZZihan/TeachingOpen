"""Pure digest-classification regressions; no runtime, service, SQL or network is used."""
import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('local_media_index_probe', HERE / 'verify-local-media-index.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

# The full projection and original WHERE clause were recorded in the index
# probe's MySQL digest evidence. The integrated downloader removes only the
# del_flag predicate so it can reject committed deletion tombstones.
REGISTRATION = ('SELECT `id` , `create_time` , `update_by` , `create_by` , `update_time` , '
                '`sys_org_code` , `file_type` , `file_name` , `file_path` , `file_location` , '
                '`file_tag` , `del_flag` FROM `sys_file` WHERE `file_path` = ? AND `file_location` = ?')
LEGACY_REGISTRATION = REGISTRATION + ' AND `del_flag` = ?'
CANDIDATE = ('SELECT `source_type` , `source_id` , `reference_value` FROM `sys_local_file_reference` '
             'WHERE `reference_kind` = ? AND `reference_hash` = ?')
SOURCE = 'SELECT * FROM `teaching_news` WHERE `id` IN (...)'


def counter(identity, query, count=20, examined=0, sent=0):
    return '\t'.join((identity, query.encode('utf-8').hex(), str(count), str(examined), str(sent)))


def totals(counts):
    return {name: sum(item[name] for item in counts.values())
            for name in ('count', 'rows_examined', 'rows_sent')}


class DownloadDigestClassification(unittest.TestCase):
    def test_tombstone_and_original_registration_queries_are_counted(self):
        for query in (REGISTRATION, LEGACY_REGISTRATION):
            with self.subTest(query=query):
                self.assertEqual(probe.download_statement_counts(counter('file', query)), {
                    'file': {'digest_text': query, 'category': 'registration', 'count': 20,
                             'rows_examined': 0, 'rows_sent': 0}})

    def test_digest_whitespace_case_and_simple_projection_are_normalized(self):
        query = '\n  select\t* from `sys_file`\nwhere `file_path` = ? and `file_location` = ?  '
        self.assertEqual('registration', probe.download_statement_counts(counter('file', query))['file']['category'])

    def test_candidate_and_authoritative_source_shapes_remain_counted(self):
        counts = probe.download_statement_counts('\n'.join((
            counter('candidate', CANDIDATE, examined=20, sent=20),
            counter('source', SOURCE, examined=20, sent=20))))
        self.assertEqual({'candidate': 'candidate', 'source': 'source'},
                         {identity: item['category'] for identity, item in counts.items()})
        self.assertEqual({'count': 40, 'rows_examined': 40, 'rows_sent': 40}, totals(counts))

    def test_anonymous_unknown_keeps_exact_two_selects_per_request(self):
        for query in (REGISTRATION, LEGACY_REGISTRATION):
            with self.subTest(query=query):
                counts = probe.download_statement_counts('\n'.join((
                    counter('file', query), counter('candidate', CANDIDATE))))
                self.assertEqual({'count': 40, 'rows_examined': 0, 'rows_sent': 0}, totals(counts))

    def test_legacy_public_hit_keeps_exact_three_selects_and_two_rows_per_request(self):
        counts = probe.download_statement_counts('\n'.join((
            counter('file', REGISTRATION), counter('candidate', CANDIDATE, examined=20, sent=20),
            counter('source', SOURCE, examined=20, sent=20))))
        self.assertEqual({'count': 60, 'rows_examined': 40, 'rows_sent': 40}, totals(counts))

    def test_partial_filters_or_union_and_non_download_queries_are_excluded(self):
        invalid = (
            REGISTRATION.replace('`file_path` = ? AND ', ''),
            REGISTRATION.replace(' AND `file_location` = ?', ''),
            REGISTRATION.replace('`file_path` = ?', '`file_path` LIKE ?'),
            REGISTRATION.replace(' AND `file_location` = ?', ' OR `file_location` = ?'),
            REGISTRATION + ' OR `del_flag` = ?',
            LEGACY_REGISTRATION + ' OR `file_location` = ?',
            REGISTRATION + ' UNION SELECT * FROM `sys_file`',
            'SELECT COUNT ( * ) FROM `sys_file` WHERE `file_path` = ? AND `file_location` = ?',
            'SELECT * FROM `sys_file`',
            'SELECT * FROM `sys_file` WHERE `id` IN (...)',
            'SELECT * FROM `teaching_news` WHERE LOCATE ( ? , `news_content` ) > ?',
            CANDIDATE.replace(' AND `reference_hash` = ?', ''),
        )
        for query in invalid:
            with self.subTest(query=query):
                self.assertEqual({}, probe.download_statement_counts(counter('other', query)))

    def test_missing_registration_still_falls_short_of_the_exact_query_bound(self):
        counts = probe.download_statement_counts('\n'.join((
            counter('candidate', CANDIDATE),
            counter('unbounded', 'SELECT * FROM `sys_file`'))))
        self.assertEqual({'count': 20, 'rows_examined': 0, 'rows_sent': 0}, totals(counts))
        self.assertNotEqual(40, totals(counts)['count'])

    def test_rows_examined_are_retained_instead_of_clamped_to_the_expected_bound(self):
        counts = probe.download_statement_counts('\n'.join((
            counter('file', REGISTRATION, examined=200), counter('candidate', CANDIDATE))))
        self.assertEqual({'count': 40, 'rows_examined': 200, 'rows_sent': 0}, totals(counts))
        self.assertNotEqual(0, totals(counts)['rows_examined'])

    def test_empty_counters_remain_empty(self):
        self.assertEqual({}, probe.download_statement_counts(''))


if __name__ == '__main__':
    unittest.main()
