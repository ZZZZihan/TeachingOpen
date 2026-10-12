package org.jeecg.modules.system.service;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/** The existing local-download sources; this list does not grant new resource types. */
public enum LocalMediaSource {
    COURSE("teaching_course", "course_icon", "course_cover", "course_map", "course_desc"),
    UNIT("teaching_course_unit", "unit_cover", "unit_intro", "media_content", "course_video", "course_case", "course_ppt", "course_plan", "course_work", "course_work_answer"),
    ADDITIONAL("teaching_additional_work", "work_cover", "work_document_url", "work_url", "work_desc"),
    CONFIG("sys_config", "config_value"),
    NEWS("teaching_news", "news_content"),
    HISTORY("sys_data_log", "data_content");

    public final String table;
    public final List<String> fields;
    LocalMediaSource(String table, String... fields) {
        this.table = table;
        this.fields = Collections.unmodifiableList(Arrays.asList(fields));
    }
    public static LocalMediaSource forTable(String table) {
        for (LocalMediaSource source : values()) if (source.table.equals(table)) return source;
        throw new IllegalArgumentException("Unsupported local media source");
    }
}
