-- Incremental migration; preserves all existing accounts and permissions.
-- Requires the existing unique indexes on sys_user.phone and sys_user.username.
CREATE TABLE IF NOT EXISTS teaching_registration_profile (
  user_id varchar(32) NOT NULL,
  identity varchar(16) NOT NULL COMMENT 'Self-declared student or teacher; does not grant permissions',
  create_time datetime NOT NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT chk_registration_identity CHECK (identity IN ('student', 'teacher'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Permit supplementary-plane characters in names and school names.
-- MODIFY retains the original length, nullability, defaults and comments;
-- repeating this migration keeps the same schema and preserves existing rows.
ALTER TABLE sys_user
  MODIFY COLUMN realname varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL COMMENT '真实姓名',
  MODIFY COLUMN school varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL DEFAULT '' COMMENT '学校';
