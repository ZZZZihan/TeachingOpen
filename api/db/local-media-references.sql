-- Additive local-media reference schema for MySQL 8.0.16+ / 8.4.
-- Apply explicitly with application/admin writes stopped and a verified private backup.
-- DDL commits implicitly. This migration never scans/backfills business content.
-- The application serializes the initial reference rebuild through state row id=1.
SET NAMES utf8mb4;
DROP PROCEDURE IF EXISTS teachingopen_local_media_references_v1;
DELIMITER $$
CREATE PROCEDURE teachingopen_local_media_references_v1()
BEGIN
  DECLARE v_lock INT DEFAULT 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    IF v_lock = 1 THEN DO RELEASE_LOCK(CONCAT('teachingopen.localmedia.', LEFT(SHA2(DATABASE(), 256), 40))); END IF;
    RESIGNAL;
  END;
  IF DATABASE() IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Select the TeachingOpen database explicitly';
  END IF;
  SELECT GET_LOCK(CONCAT('teachingopen.localmedia.', LEFT(SHA2(DATABASE(), 256), 40)), 30) INTO v_lock;
  IF v_lock IS NULL OR v_lock <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Another local media migration is running';
  END IF;
  IF @@version LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(@@version, '.', 1) AS UNSIGNED) <> 8
      OR (CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 2), '.', -1) AS UNSIGNED) = 0
          AND CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 3), '.', -1) AS UNSIGNED) < 16) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Local media references require MySQL 8.0.16 or later in the MySQL 8 series';
  END IF;
  IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()
      AND table_name IN ('sys_file', 'teaching_work', 'teaching_course', 'teaching_course_unit',
        'teaching_additional_work', 'sys_config', 'teaching_news', 'sys_data_log') AND engine = 'InnoDB') <> 8
      OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
      AND table_name = 'sys_file' AND ((column_name = 'file_path' AND data_type IN ('varchar', 'text', 'mediumtext', 'longtext')
        AND character_maximum_length >= 191) OR (column_name IN ('file_location', 'del_flag')
        AND data_type IN ('tinyint', 'smallint', 'mediumint', 'int', 'bigint')))) <> 3
      OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
      AND table_name = 'teaching_work' AND ((column_name IN ('work_file', 'work_cover')
        AND data_type = 'varchar' AND character_maximum_length <= 191)
        OR (column_name = 'del_flag' AND data_type IN ('tinyint', 'smallint', 'mediumint', 'int', 'bigint')))) <> 3 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Local media references require InnoDB source tables and compatible file/work metadata';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'sys_local_file_reference') THEN
    IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference' AND engine = 'InnoDB' AND table_collation = 'utf8mb4_bin') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference') <> 6
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference' AND is_nullable = 'NO' AND column_default IS NULL AND extra = ''
        AND ((column_name IN ('source_type', 'field_name') AND data_type = 'varchar' AND character_maximum_length = 40
          AND character_set_name = 'ascii' AND collation_name = 'ascii_bin')
          OR (column_name = 'source_id' AND data_type = 'varchar' AND character_maximum_length = 64
          AND character_set_name = 'utf8mb4' AND collation_name = 'utf8mb4_bin')
          OR (column_name = 'reference_kind' AND data_type = 'varchar' AND character_maximum_length = 8
          AND character_set_name = 'ascii' AND collation_name = 'ascii_bin')
          OR (column_name = 'reference_hash' AND data_type = 'char' AND character_maximum_length = 64
          AND character_set_name = 'ascii' AND collation_name = 'ascii_bin')
          OR (column_name = 'reference_value' AND data_type = 'mediumtext'
          AND character_set_name = 'utf8mb4' AND collation_name = 'utf8mb4_bin'))) <> 6
        OR NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference' AND index_name = 'PRIMARY' GROUP BY index_name
        HAVING COUNT(*) = 5 AND MAX(non_unique) = 0 AND MAX(sub_part) IS NULL
        AND GROUP_CONCAT(column_name ORDER BY seq_in_index) = 'source_type,source_id,field_name,reference_kind,reference_hash')
        OR NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference' AND index_name = 'idx_local_reference_lookup' GROUP BY index_name
        HAVING COUNT(*) = 2 AND MIN(non_unique) = 1 AND MAX(sub_part) IS NULL AND MIN(index_type) = 'BTREE' AND MIN(is_visible) = 'YES'
        AND GROUP_CONCAT(column_name ORDER BY seq_in_index) = 'reference_kind,reference_hash')
        OR (SELECT COUNT(DISTINCT index_name) FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference') <> 2
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = DATABASE()
        AND table_name = 'sys_local_file_reference') <> 2
        OR NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = DATABASE()
        AND table_name = 'sys_local_file_reference' AND constraint_name = 'chk_local_reference_kind'
        AND constraint_type = 'CHECK' AND enforced = 'YES')
        OR NOT EXISTS (SELECT 1 FROM information_schema.check_constraints WHERE constraint_schema = DATABASE()
        AND constraint_name = 'chk_local_reference_kind'
        AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(check_clause, CHAR(92), ''), '`', ''), ' ', ''), '_ascii', ''), '_utf8mb4', ''), '(', ''), ')', '') =
          'reference_kindin''key'',''file''')
        OR EXISTS (SELECT 1 FROM information_schema.triggers WHERE trigger_schema = DATABASE()
        AND event_object_table = 'sys_local_file_reference') THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Local media reference schema is incompatible; review it without automatic repair';
    END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'sys_local_file_reference_state') THEN
    IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference_state' AND engine = 'InnoDB' AND table_collation = 'utf8mb4_bin') <> 1
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference_state') <> 3
        OR (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference_state' AND extra = ''
        AND ((column_name = 'id' AND column_type IN ('int', 'int(11)') AND is_nullable = 'NO' AND column_default IS NULL)
          OR (column_name = 'version' AND column_type IN ('int', 'int(11)') AND is_nullable = 'NO' AND column_default = '0')
          OR (column_name = 'static_domain' AND data_type = 'varchar' AND character_maximum_length = 512
          AND character_set_name = 'utf8mb4' AND collation_name = 'utf8mb4_bin' AND is_nullable = 'YES' AND column_default IS NULL))) <> 3
        OR NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference_state' AND index_name = 'PRIMARY' GROUP BY index_name
        HAVING COUNT(*) = 1 AND MAX(non_unique) = 0 AND MAX(sub_part) IS NULL AND MAX(column_name) = 'id')
        OR (SELECT COUNT(DISTINCT index_name) FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'sys_local_file_reference_state') <> 1
        OR (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = DATABASE()
        AND table_name = 'sys_local_file_reference_state') <> 2
        OR NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = DATABASE()
        AND table_name = 'sys_local_file_reference_state' AND constraint_name = 'chk_local_reference_state_id'
        AND constraint_type = 'CHECK' AND enforced = 'YES')
        OR NOT EXISTS (SELECT 1 FROM information_schema.check_constraints WHERE constraint_schema = DATABASE()
        AND constraint_name = 'chk_local_reference_state_id'
        AND REPLACE(REPLACE(REPLACE(REPLACE(check_clause, '`', ''), ' ', ''), '(', ''), ')', '') = 'id=1')
        OR EXISTS (SELECT 1 FROM information_schema.triggers WHERE trigger_schema = DATABASE()
        AND event_object_table = 'sys_local_file_reference_state') THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Local media state schema is incompatible; review it without automatic repair';
    END IF;
  END IF;
  -- Existing indexes with these reserved names must already have the exact definition.
  IF EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
      AND table_name = 'sys_file' AND index_name = 'idx_sys_file_local_path')
      AND NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
      AND table_name = 'sys_file' AND index_name = 'idx_sys_file_local_path' GROUP BY index_name
      HAVING COUNT(*) = 3 AND MIN(non_unique) = 1 AND MIN(index_type) = 'BTREE' AND MIN(is_visible) = 'YES'
      AND GROUP_CONCAT(column_name ORDER BY seq_in_index) = 'file_path,file_location,del_flag'
      AND SUM(seq_in_index = 1 AND sub_part = 191) = 1 AND SUM(seq_in_index > 1 AND sub_part IS NULL) = 2) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Local file metadata index is incompatible; review it without automatic repair';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
      AND table_name = 'teaching_work' AND index_name = 'idx_work_file_live')
      AND NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
      AND table_name = 'teaching_work' AND index_name = 'idx_work_file_live' GROUP BY index_name
      HAVING COUNT(*) = 2 AND MIN(non_unique) = 1 AND MAX(sub_part) IS NULL AND MIN(index_type) = 'BTREE' AND MIN(is_visible) = 'YES'
      AND GROUP_CONCAT(column_name ORDER BY seq_in_index) = 'work_file,del_flag') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Work file metadata index is incompatible; review it without automatic repair';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
      AND table_name = 'teaching_work' AND index_name = 'idx_work_cover_live')
      AND NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
      AND table_name = 'teaching_work' AND index_name = 'idx_work_cover_live' GROUP BY index_name
      HAVING COUNT(*) = 2 AND MIN(non_unique) = 1 AND MAX(sub_part) IS NULL AND MIN(index_type) = 'BTREE' AND MIN(is_visible) = 'YES'
      AND GROUP_CONCAT(column_name ORDER BY seq_in_index) = 'work_cover,del_flag') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Work cover metadata index is incompatible; review it without automatic repair';
  END IF;
  IF COALESCE(@teachingopen_registration_preflight_only, 0) = 0 THEN
    CREATE TABLE IF NOT EXISTS sys_local_file_reference (
      source_type varchar(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
      source_id varchar(64) COLLATE utf8mb4_bin NOT NULL,
      field_name varchar(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
      reference_kind varchar(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
      reference_hash char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
      reference_value mediumtext COLLATE utf8mb4_bin NOT NULL,
      PRIMARY KEY (source_type, source_id, field_name, reference_kind, reference_hash),
      KEY idx_local_reference_lookup (reference_kind, reference_hash),
      CONSTRAINT chk_local_reference_kind CHECK (reference_kind IN ('key', 'file'))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
    CREATE TABLE IF NOT EXISTS sys_local_file_reference_state (
      id int NOT NULL PRIMARY KEY,
      version int NOT NULL DEFAULT 0,
      static_domain varchar(512) COLLATE utf8mb4_bin DEFAULT NULL,
      CONSTRAINT chk_local_reference_state_id CHECK (id = 1)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
    INSERT INTO sys_local_file_reference_state (id, version)
      SELECT 1, 0 WHERE NOT EXISTS (SELECT 1 FROM sys_local_file_reference_state WHERE id = 1);
    IF NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'sys_file' AND index_name = 'idx_sys_file_local_path') THEN
      ALTER TABLE sys_file ADD INDEX idx_sys_file_local_path (file_path(191), file_location, del_flag);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'teaching_work' AND index_name = 'idx_work_file_live') THEN
      ALTER TABLE teaching_work ADD INDEX idx_work_file_live (work_file, del_flag);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
        AND table_name = 'teaching_work' AND index_name = 'idx_work_cover_live') THEN
      ALTER TABLE teaching_work ADD INDEX idx_work_cover_live (work_cover, del_flag);
    END IF;
  END IF;
  DO RELEASE_LOCK(CONCAT('teachingopen.localmedia.', LEFT(SHA2(DATABASE(), 256), 40)));
END$$
DELIMITER ;
CALL teachingopen_local_media_references_v1();
DROP PROCEDURE teachingopen_local_media_references_v1;
