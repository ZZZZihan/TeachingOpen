-- MySQL 8.0.16+ / 8.4, explicit additive cutover. Never run at application startup.
-- Stop all application/admin writes and make a fresh private backup first.
-- Existing task work has two LEGACY_REVIEW rows: resolve with evidence before reopening writes.
-- No existing aggregate, work, feedback, Redis key or historical count is changed.
SET NAMES utf8mb4;
DROP PROCEDURE IF EXISTS teachingopen_work_events_v1;
DELIMITER $$
CREATE PROCEDURE teachingopen_work_events_v1()
BEGIN
  DECLARE v_lock INT DEFAULT 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    IF v_lock = 1 THEN DO RELEASE_LOCK(CONCAT('teachingopen.workevents.', LEFT(SHA2(DATABASE(), 256), 40))); END IF;
    RESIGNAL;
  END;
  IF DATABASE() IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Select the TeachingOpen database explicitly'; END IF;
  SELECT GET_LOCK(CONCAT('teachingopen.workevents.', LEFT(SHA2(DATABASE(), 256), 40)), 30) INTO v_lock;
  IF v_lock IS NULL OR v_lock <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Another work event migration is running'; END IF;
  IF @@version LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(@@version, '.', 1) AS UNSIGNED) <> 8
      OR (CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 2), '.', -1) AS UNSIGNED) = 0
          AND CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 3), '.', -1) AS UNSIGNED) < 16) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Work events require MySQL 8.0.16 or later in the MySQL 8 series';
  END IF;
  IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()
      AND table_name IN ('sys_depart','teaching_depart_day_log','teaching_work') AND engine='InnoDB') <> 3 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Work events require existing InnoDB work, department and statistics tables';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_work_event_cutover')
      AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_work_event') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cutover exists without ledger; restore or investigate instead of recounting';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_work_event') THEN
    IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_work_event'
        AND engine='InnoDB' AND table_collation='utf8mb4_bin') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='teaching_work_event') <> 6
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='teaching_work_event'
        AND data_type='varchar' AND is_nullable='NO' AND column_default IS NULL AND extra='' AND collation_name='utf8mb4_bin'
        AND ((column_name IN ('work_id','depart_id') AND character_maximum_length=64)
          OR (column_name IN ('event_type','event_state') AND character_maximum_length=32))) <> 4
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='teaching_work_event'
        AND column_name='counted_day' AND data_type='date' AND is_nullable='YES' AND column_default IS NULL AND extra='') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='teaching_work_event'
        AND column_name='observed_at' AND data_type='timestamp' AND datetime_precision=0 AND is_nullable='NO'
        AND LOWER(column_default) IN ('current_timestamp','current_timestamp()') AND LOWER(extra) IN ('','default_generated')) <> 1
        OR NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='teaching_work_event'
        AND index_name='PRIMARY' GROUP BY index_name HAVING COUNT(*)=2 AND MAX(non_unique)=0 AND MAX(sub_part) IS NULL
        AND GROUP_CONCAT(column_name ORDER BY seq_in_index)='work_id,event_type')
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name='teaching_work_event') <> 3
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name='teaching_work_event'
        AND constraint_type='CHECK' AND enforced='YES' AND constraint_name IN ('chk_work_event_type','chk_work_event_state')) <> 2
        OR EXISTS (SELECT 1 FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND event_object_table='teaching_work_event')
        OR NOT EXISTS (SELECT 1 FROM information_schema.check_constraints WHERE constraint_schema=DATABASE() AND constraint_name='chk_work_event_type'
        AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(check_clause,CHAR(92),''),'`',''),' ',''),'_utf8mb4',''),'(',''),')','') = 'event_typein''SUBMIT'',''CORRECT''')
        OR NOT EXISTS (SELECT 1 FROM information_schema.check_constraints WHERE constraint_schema=DATABASE() AND constraint_name='chk_work_event_state'
        AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(check_clause,CHAR(92),''),'`',''),' ',''),'_utf8mb4',''),'(',''),')','') =
        'event_state=''COUNTED''andcounted_dayisnotnullorevent_statein''LEGACY_REVIEW'',''LEGACY_UNRESOLVED'',''READY''andcounted_dayisnull') THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Work event schema incompatible; review without automatic repair';
    END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_work_event_cutover') THEN
    IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_work_event_cutover'
        AND engine='InnoDB' AND table_collation='utf8mb4_bin') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='teaching_work_event_cutover') <> 2
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='teaching_work_event_cutover'
        AND column_name='id' AND data_type='tinyint' AND is_nullable='NO' AND column_default IS NULL AND extra='') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='teaching_work_event_cutover'
        AND column_name='completed_at' AND data_type='timestamp' AND is_nullable='NO' AND datetime_precision=0
        AND LOWER(column_default) IN ('current_timestamp','current_timestamp()') AND LOWER(extra) IN ('','default_generated')) <> 1
        OR NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='teaching_work_event_cutover'
        AND index_name='PRIMARY' GROUP BY index_name HAVING COUNT(*)=1 AND MAX(non_unique)=0 AND MAX(column_name)='id')
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name='teaching_work_event_cutover') <> 2
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() AND table_name='teaching_work_event_cutover'
        AND constraint_name='chk_work_event_cutover_id' AND constraint_type='CHECK' AND enforced='YES') <> 1
        OR NOT EXISTS (SELECT 1 FROM information_schema.check_constraints WHERE constraint_schema=DATABASE() AND constraint_name='chk_work_event_cutover_id'
        AND REPLACE(REPLACE(REPLACE(REPLACE(check_clause,'`',''),' ',''),'(',''),')','')='id=1')
        OR EXISTS (SELECT 1 FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND event_object_table='teaching_work_event_cutover') THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Work event cutover schema incompatible; review without automatic repair';
    END IF;
  END IF;
  IF COALESCE(@teachingopen_registration_preflight_only,0)=0 THEN
    CREATE TABLE IF NOT EXISTS teaching_work_event (
      work_id varchar(64) COLLATE utf8mb4_bin NOT NULL,
      event_type varchar(32) COLLATE utf8mb4_bin NOT NULL,
      depart_id varchar(64) COLLATE utf8mb4_bin NOT NULL,
      event_state varchar(32) COLLATE utf8mb4_bin NOT NULL,
      counted_day date DEFAULT NULL,
      observed_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(work_id,event_type),
      CONSTRAINT chk_work_event_type CHECK(event_type IN ('SUBMIT','CORRECT')),
      CONSTRAINT chk_work_event_state CHECK((event_state='COUNTED' AND counted_day IS NOT NULL)
        OR (event_state IN ('LEGACY_REVIEW','LEGACY_UNRESOLVED','READY') AND counted_day IS NULL))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
    CREATE TABLE IF NOT EXISTS teaching_work_event_cutover (
      id tinyint NOT NULL PRIMARY KEY,
      completed_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT chk_work_event_cutover_id CHECK(id=1)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
    START TRANSACTION;
    IF NOT EXISTS (SELECT 1 FROM teaching_work_event_cutover WHERE id=1 FOR UPDATE) THEN
      IF EXISTS(SELECT 1 FROM teaching_work_event) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Existing events without cutover receipt; investigate instead of overwriting';
      END IF;
      INSERT INTO teaching_work_event(work_id,event_type,depart_id,event_state)
        SELECT w.id, e.event_type, w.depart_id, 'LEGACY_REVIEW' FROM teaching_work w
        CROSS JOIN (SELECT 'SUBMIT' event_type UNION ALL SELECT 'CORRECT') e
        WHERE COALESCE(TRIM(w.depart_id),'')<>'' AND
        (COALESCE(TRIM(w.course_id),'')<>'' OR COALESCE(TRIM(w.additional_id),'')<>'');
      INSERT INTO teaching_work_event_cutover(id) VALUES(1);
    END IF;
    COMMIT;
  END IF;
  DO RELEASE_LOCK(CONCAT('teachingopen.workevents.', LEFT(SHA2(DATABASE(), 256), 40)));
END$$
DELIMITER ;
CALL teachingopen_work_events_v1();
DROP PROCEDURE teachingopen_work_events_v1;
