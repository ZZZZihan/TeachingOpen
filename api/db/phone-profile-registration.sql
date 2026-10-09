-- Incremental migration; preserves all existing accounts and permissions.
-- Requires the existing unique indexes on sys_user.phone and sys_user.username.
CREATE TABLE IF NOT EXISTS teaching_registration_profile (
  user_id varchar(32) NOT NULL,
  identity varchar(16) NOT NULL COMMENT 'Self-declared student or teacher; does not grant permissions',
  create_time datetime NOT NULL,
  PRIMARY KEY (user_id),
  CONSTRAINT chk_registration_identity CHECK (identity IN ('student', 'teacher'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
