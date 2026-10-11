package org.jeecg.modules.teaching.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Param;
import org.jeecg.modules.teaching.entity.TeachingDepartDayLog;

/**
 * @Description: 班级每日教学记录
 * @Author: jeecg-boot
 * @Date:   2021-06-25
 * @Version: V1.0
 */
public interface TeachingDepartDayLogMapper extends BaseMapper<TeachingDepartDayLog> {

    String selectDayIdForUpdate(@Param("departId") String departId, @Param("day") String day);

    int insertDayLog(@Param("log") TeachingDepartDayLog log, @Param("day") String day);

    int incrementDayCounter(@Param("id") String id, @Param("departId") String departId,
                                         @Param("day") String day, @Param("counter") String counter);

    String selectUnitViewStateForUpdate(@Param("departId") String departId, @Param("unitId") String unitId);

    int insertUnitViewEvent(@Param("departId") String departId, @Param("unitId") String unitId,
                           @Param("userId") String userId, @Param("state") String state, @Param("day") String day);

}
