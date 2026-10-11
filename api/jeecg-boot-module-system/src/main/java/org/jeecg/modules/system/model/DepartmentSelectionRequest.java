package org.jeecg.modules.system.model;

import lombok.Data;

/** Username is retained for existing clients; it may only name the principal. */
@Data
public class DepartmentSelectionRequest {
    private String username;
    private String orgCode;
}
