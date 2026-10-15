package org.jeecg.modules.system.mapper;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/** Explicit SQL reserves legacy phone values and login names, including deleted accounts. */
public interface RegistrationProfileMapper {
    @Select("SELECT COUNT(*) FROM sys_user WHERE username = #{username} OR phone = #{username}")
    int countReservedUsername(@Param("username") String username);

    @Insert("INSERT INTO teaching_registration_profile(user_id, identity, create_time) VALUES(#{userId}, #{identity}, CURRENT_TIMESTAMP)")
    int insertProfile(@Param("userId") String userId, @Param("identity") String identity);
}
