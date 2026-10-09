package org.jeecg.modules.system.mapper;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/** Explicit SQL includes deleted accounts when reserving a phone or login name. */
public interface RegistrationProfileMapper {
    @Select("SELECT COUNT(*) FROM sys_user WHERE phone = #{phone} OR username = #{phone}")
    int countReservedPhone(@Param("phone") String phone);

    @Insert("INSERT INTO teaching_registration_profile(user_id, identity, create_time) VALUES(#{userId}, #{identity}, CURRENT_TIMESTAMP)")
    int insertProfile(@Param("userId") String userId, @Param("identity") String identity);
}
