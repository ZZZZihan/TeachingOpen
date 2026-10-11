package org.jeecg.modules.teaching.enums;

/** A department/unit is deduplicated for its lifetime, not by day or student. */
public enum UnitViewLogResult {
    COUNTED, ALREADY_COUNTED, NOT_APPLICABLE, LEGACY_UNRESOLVED
}
