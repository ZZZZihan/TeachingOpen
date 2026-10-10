package org.jeecg.modules.teaching.model;

import lombok.Data;
import java.util.List;

/** Only the coordinates of units in one authorized course may be changed. */
@Data
public class CourseMapUpdateRequest {
    private String courseId;
    private List<UnitPosition> units;

    @Data
    public static class UnitPosition {
        private String id;
        private Integer mapX;
        private Integer mapY;
    }
}
