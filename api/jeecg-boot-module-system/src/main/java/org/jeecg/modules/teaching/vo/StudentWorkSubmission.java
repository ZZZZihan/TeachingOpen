package org.jeecg.modules.teaching.vo;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;

/** Fields students can supply when saving or submitting their own work. */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class StudentWorkSubmission {
    private String id;
    private String courseId;
    private String additionalId;
    private String departId;
    private String workName;
    private String workType;
    private String workStatus;
    private String workFile;
    private String workCover;
    private Boolean hasCloudData;
}
