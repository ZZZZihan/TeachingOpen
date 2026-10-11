-- Explicit additive migration for MySQL 8.0.16+ / 8.4. Never run at application startup.
-- Stop application/admin writes and verify a fresh private backup before an existing DB upgrade.
-- DDL commits implicitly. No Redis marker or historical counter is changed/backfilled.
-- Legacy Redis markers may precede failed SQL writes, so they cannot prove COUNTED.
SET NAMES utf8mb4;
DROP PROCEDURE IF EXISTS teachingopen_unit_view_events_v1;
DELIMITER $$
CREATE PROCEDURE teachingopen_unit_view_events_v1()
BEGIN
  DECLARE v_lock INT DEFAULT 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    IF v_lock = 1 THEN DO RELEASE_LOCK(CONCAT('teachingopen.unitview.', LEFT(SHA2(DATABASE(), 256), 40))); END IF;
    RESIGNAL;
  END;
  IF DATABASE() IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Select the TeachingOpen database explicitly';
  END IF;
  SELECT GET_LOCK(CONCAT('teachingopen.unitview.', LEFT(SHA2(DATABASE(), 256), 40)), 30) INTO v_lock;
  IF v_lock IS NULL OR v_lock <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Another unit view migration is running';
  END IF;
  IF @@version LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(@@version, '.', 1) AS UNSIGNED) <> 8
      OR (CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 2), '.', -1) AS UNSIGNED) = 0
          AND CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 3), '.', -1) AS UNSIGNED) < 16) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unit view events require MySQL 8.0.16 or later in the MySQL 8 series';
  END IF;
  IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()
      AND table_name IN ('sys_depart', 'teaching_depart_day_log') AND engine = 'InnoDB') <> 2 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unit view events require the existing InnoDB department and statistics tables';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'teaching_unit_view_event') THEN
    IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event' AND engine = 'InnoDB' AND table_collation = 'utf8mb4_bin') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event') <> 6
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event' AND is_nullable = 'NO' AND column_default IS NULL AND extra = ''
        AND character_set_name = 'utf8mb4' AND collation_name = 'utf8mb4_bin' AND data_type = 'varchar'
        AND ((column_name IN ('depart_id', 'unit_id', 'observed_user_id') AND character_maximum_length = 64)
          OR (column_name = 'event_state' AND character_maximum_length = 32))) <> 4
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event' AND column_name = 'counted_day' AND data_type = 'date'
        AND is_nullable = 'YES' AND column_default IS NULL AND extra = '') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event' AND column_name = 'observed_at' AND data_type = 'timestamp'
        AND datetime_precision = 0 AND is_nullable = 'NO' AND LOWER(column_default) IN ('current_timestamp', 'current_timestamp()')
        AND LOWER(extra) IN ('', 'default_generated')) <> 1
        OR NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event' AND index_name = 'PRIMARY' GROUP BY index_name
        HAVING COUNT(*) = 2 AND MAX(non_unique) = 0 AND MAX(sub_part) IS NULL
        AND GROUP_CONCAT(column_name ORDER BY seq_in_index) = 'depart_id,unit_id')
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event' AND constraint_name = 'chk_unit_view_event_state'
        AND constraint_type = 'CHECK' AND enforced = 'YES') <> 1
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = DATABASE()
        AND table_name = 'teaching_unit_view_event') <> 2
        OR EXISTS (SELECT 1 FROM information_schema.triggers WHERE trigger_schema = DATABASE()
        AND event_object_table = 'teaching_unit_view_event')
        OR NOT EXISTS (SELECT 1 FROM information_schema.check_constraints WHERE constraint_schema = DATABASE()
        AND constraint_name = 'chk_unit_view_event_state'
        AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(check_clause, CHAR(92), ''), '`', ''), ' ', ''), '_utf8mb4', ''), '(', ''), ')', '') =
          'event_state=''COUNTED''andcounted_dayisnotnullorevent_state=''LEGACY_UNRESOLVED''andcounted_dayisnull') THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unit view ledger schema is incompatible; review it without automatic repair';
    END IF;
  END IF;
  -- The shared upgrade preflight flag permits metadata validation without creating this table.
  IF COALESCE(@teachingopen_registration_preflight_only, 0) = 0 THEN
    CREATE TABLE IF NOT EXISTS teaching_unit_view_event (
      depart_id varchar(64) COLLATE utf8mb4_bin NOT NULL,
      unit_id varchar(64) COLLATE utf8mb4_bin NOT NULL,
      observed_user_id varchar(64) COLLATE utf8mb4_bin NOT NULL,
      event_state varchar(32) COLLATE utf8mb4_bin NOT NULL,
      counted_day date DEFAULT NULL,
      observed_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (depart_id, unit_id),
      CONSTRAINT chk_unit_view_event_state CHECK (
        (event_state = 'COUNTED' AND counted_day IS NOT NULL)
        OR (event_state = 'LEGACY_UNRESOLVED' AND counted_day IS NULL)
      )
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
  END IF;
  DO RELEASE_LOCK(CONCAT('teachingopen.unitview.', LEFT(SHA2(DATABASE(), 256), 40)));
END$$
DELIMITER ;
CALL teachingopen_unit_view_events_v1();
DROP PROCEDURE teachingopen_unit_view_events_v1;
