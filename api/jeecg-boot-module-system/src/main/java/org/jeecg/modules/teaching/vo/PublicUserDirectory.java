package org.jeecg.modules.teaching.vo;

import lombok.Data;
import java.util.List;

/** Public response: never add account identifiers or private contact fields. */
@Data
public class PublicUserDirectory {
    private long total;
    private long pageNo;
    private final int pageSize = 10;
    private List<Entry> records;

    @Data
    public static class Entry {
        private String name;
        private String school;
        private String identity;
    }
}
