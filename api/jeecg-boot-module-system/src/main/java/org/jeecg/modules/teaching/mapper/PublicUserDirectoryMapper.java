package org.jeecg.modules.teaching.mapper;

import lombok.Data;
import org.apache.ibatis.annotations.Param;
import java.util.List;

public interface PublicUserDirectoryMapper {
    long countRegisteredUsers();
    List<RegisteredUser> listRegisteredUsers(@Param("offset") long offset);

    /** Internal projection; never returned by a controller. */
    @Data
    class RegisteredUser {
        private String realname;
        private String school;
        private String identity;
    }
}
