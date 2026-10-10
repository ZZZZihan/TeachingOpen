-- Explicit, repeatable migration for MySQL 8.0.16+ / 8.4; never run from application startup.
-- Before an existing database upgrade: stop writes, verify bundle hashes, take and test a private backup.
-- MySQL DDL commits implicitly: START TRANSACTION cannot roll back CREATE/ALTER TABLE.
-- The reserved temporary procedure is removed on success. A failed call can leave it behind;
-- rerunning this exact migration replaces only that migration procedure, never user data.
SET NAMES utf8mb4;
DROP PROCEDURE IF EXISTS teachingopen_registration_schema_v1;
DELIMITER $$
CREATE PROCEDURE teachingopen_registration_schema_v1()
BEGIN
  DECLARE v_lock INT DEFAULT 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    IF v_lock = 1 THEN DO RELEASE_LOCK(CONCAT('teachingopen.reg.', LEFT(SHA2(DATABASE(), 256), 40))); END IF;
    RESIGNAL;
  END;
  SELECT GET_LOCK(CONCAT('teachingopen.reg.', LEFT(SHA2(DATABASE(), 256), 40)), 30) INTO v_lock;
  IF v_lock IS NULL OR v_lock <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Another registration migration is running';
  END IF;
  IF DATABASE() IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Select the target TeachingOpen database explicitly';
  END IF;
  IF @@version LIKE '%MariaDB%' OR CAST(SUBSTRING_INDEX(@@version, '.', 1) AS UNSIGNED) <> 8
      OR (CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 2), '.', -1) AS UNSIGNED) = 0
          AND CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(@@version, '.', 3), '.', -1) AS UNSIGNED) < 16) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registration migration requires MySQL 8.0.16 or later in the MySQL 8 series';
  END IF;
  IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()
      AND table_name IN ('sys_user', 'sys_role', 'sys_user_role', 'sys_config') AND engine = 'InnoDB') <> 4 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registration requires the existing InnoDB user, role and config tables';
  END IF;
  IF (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'sys_user'
      AND ((column_name = 'realname' AND data_type = 'varchar' AND character_maximum_length = 100
        AND is_nullable = 'YES' AND column_default IS NULL)
      OR (column_name = 'school' AND data_type = 'varchar' AND character_maximum_length = 256
        AND is_nullable = 'NO' AND column_default = ''))
      AND character_set_name IN ('utf8mb3', 'utf8', 'utf8mb4')
      AND collation_name IN ('utf8mb3_general_ci', 'utf8_general_ci', 'utf8mb4_general_ci') AND extra = '') <> 2 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unexpected name or school definition; review before changing column metadata';
  END IF;
  -- The reviewed restricted schema exporter omits all comments. Accept that
  -- exact pair or the canonical pair, never arbitrary/mixed custom comments.
  IF (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'sys_user'
      AND ((column_name = 'realname' AND column_comment = '真实姓名') OR (column_name = 'school' AND column_comment = '学校'))) <> 2
      AND (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'sys_user'
      AND column_name IN ('realname', 'school') AND column_comment = '') <> 2 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unexpected name or school comments; canonical or reviewed stripped pair required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'sys_user'
      GROUP BY index_name HAVING COUNT(*) = 1 AND MAX(non_unique) = 0 AND MAX(column_name) = 'username'
      AND MAX(sub_part) IS NULL) OR NOT EXISTS
      (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'sys_user'
      GROUP BY index_name HAVING COUNT(*) = 1 AND MAX(non_unique) = 0 AND MAX(column_name) = 'phone'
      AND MAX(sub_part) IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Full unique username and phone indexes are required; no index is repaired automatically';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'sys_role'
      GROUP BY index_name HAVING COUNT(*) = 1 AND MAX(non_unique) = 0 AND MAX(column_name) = 'role_code'
      AND MAX(sub_part) IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Full unique role_code index is required';
  END IF;
  IF (SELECT COUNT(*) FROM sys_role WHERE role_code = 'student') <> 1 OR
      (SELECT COUNT(*) FROM sys_role WHERE BINARY role_code = BINARY 'student' AND id <> '') <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Exactly one canonical student role is required; no permissions are invented';
  END IF;
  IF (SELECT COUNT(*) FROM sys_config WHERE config_key = 'allowReg') <> 1 OR
      (SELECT COUNT(*) FROM sys_config WHERE BINARY config_key = BINARY 'allowReg'
       AND BINARY config_value IN (BINARY '0', BINARY '1') AND config_enabled IN (0, 1)) <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Exactly one canonical allowReg config with value 0 or 1 is required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'sys_config'
      AND index_name = 'PRIMARY' GROUP BY index_name
      HAVING COUNT(*) = 1 AND MAX(column_name) = 'id' AND MAX(non_unique) = 0 AND MAX(sub_part) IS NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Config primary key id is required for a single-row update';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'teaching_registration_profile') THEN
  IF (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()
      AND table_name = 'teaching_registration_profile' AND engine = 'InnoDB') <> 1 OR
      (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
      AND table_name = 'teaching_registration_profile') <> 3 OR
      (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()
      AND table_name = 'teaching_registration_profile' AND is_nullable = 'NO' AND column_default IS NULL AND extra = ''
      AND ((column_name = 'user_id' AND data_type = 'varchar' AND character_maximum_length = 32 AND character_set_name = 'utf8mb4')
        OR (column_name = 'identity' AND data_type = 'varchar' AND character_maximum_length = 16 AND character_set_name = 'utf8mb4')
        OR (column_name = 'create_time' AND data_type = 'datetime' AND datetime_precision = 0))) <> 3 OR
      NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema = DATABASE()
      AND table_name = 'teaching_registration_profile' AND index_name = 'PRIMARY' GROUP BY index_name
      HAVING COUNT(*) = 1 AND MAX(column_name) = 'user_id' AND MAX(non_unique) = 0 AND MAX(sub_part) IS NULL) OR
      (SELECT COUNT(*) FROM information_schema.table_constraints WHERE constraint_schema = DATABASE()
      AND table_name = 'teaching_registration_profile' AND constraint_name = 'chk_registration_identity'
      AND constraint_type = 'CHECK' AND enforced = 'YES') <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registration profile schema is incompatible; manual review is required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.check_constraints
      WHERE constraint_schema = DATABASE() AND constraint_name = 'chk_registration_identity'
      AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(check_clause,
        CHAR(92), ''), '`', ''), ' ', ''), '_utf8mb4', ''), '(', ''), ')', '') IN
        ('identityin''student'',''teacher''',
         'castidentityasbinaryincast''student''asbinary,cast''teacher''asbinary',
         'castidentityascharcharsetbinaryincast''student''ascharcharsetbinary,cast''teacher''ascharcharsetbinary')) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registration identity CHECK has unexpected semantics';
  END IF;
  IF EXISTS (SELECT 1 FROM teaching_registration_profile WHERE BINARY identity NOT IN (BINARY 'student', BINARY 'teacher')) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unexpected registration identity values; existing profiles are preserved';
  END IF;
  END IF;
  IF COALESCE(@teachingopen_registration_preflight_only, 0) = 0 THEN
    CREATE TABLE IF NOT EXISTS teaching_registration_profile (
      user_id varchar(32) NOT NULL,
      identity varchar(16) NOT NULL COMMENT 'Self-declared student or teacher; does not grant permissions',
      create_time datetime NOT NULL,
      PRIMARY KEY (user_id),
      CONSTRAINT chk_registration_identity CHECK (BINARY identity IN (BINARY 'student', BINARY 'teacher'))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    -- Metadata was checked above; change these character sets and restore
    -- canonical comments for the reviewed restricted exporter output.
    IF (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'sys_user'
        AND column_name IN ('realname', 'school') AND character_set_name = 'utf8mb4'
        AND column_comment = CASE column_name WHEN 'realname' THEN '真实姓名' WHEN 'school' THEN '学校' END) <> 2 THEN
    ALTER TABLE sys_user
      MODIFY COLUMN realname varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '真实姓名',
      MODIFY COLUMN school varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '学校';
    END IF;
  END IF;
  DO RELEASE_LOCK(CONCAT('teachingopen.reg.', LEFT(SHA2(DATABASE(), 256), 40)));
END$$
DELIMITER ;
CALL teachingopen_registration_schema_v1();
DROP PROCEDURE teachingopen_registration_schema_v1;
