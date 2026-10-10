package org.jeecg.modules.system.model;

import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Data;
import java.util.Date;

/** Fields editable by the authenticated account; credential fields are excluded. */
@Data
public class UserProfileRequest {
    private String id;
    private String realname;
    private String avatar;
    private String email;
    private Integer sex;
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd")
    private Date birthday;

    @JsonAnySetter
    public void rejectOtherField(String name, Object value) {
        throw new IllegalArgumentException("个人资料包含不允许修改的字段");
    }
}
