package org.jeecg.modules.teaching.mapper;

import java.util.List;
import java.util.Set;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.apache.ibatis.annotations.Param;
import org.jeecg.modules.teaching.entity.TeachingCourseUnit;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.jeecg.modules.teaching.model.CourseUnitModel;
import org.jeecg.modules.teaching.model.CourseUnitWorkModel;

/**
 * @Description: 课程单元
 * @Author: jeecg-boot
 * @Date:   2020-04-14
 * @Version: V1.0
 */
public interface TeachingCourseUnitMapper extends BaseMapper<TeachingCourseUnit> {

    List<CourseUnitModel> getCourseUnitList(Page<CourseUnitModel> page, @Param("ew") QueryWrapper<CourseUnitModel> queryWrapper);

    List<String> lockMapUnits(@Param("courseId") String courseId, @Param("ids") Set<String> ids);

    int updateMapPosition(@Param("courseId") String courseId, @Param("unitId") String unitId,
                          @Param("mapX") Integer mapX, @Param("mapY") Integer mapY);

    //暂未使用
    List<CourseUnitModel> getCourseUnitAndMediaList(Page<CourseUnitModel> page, @Param("ew") QueryWrapper<CourseUnitModel> queryWrapper);

    CourseUnitWorkModel getCourseWorkUnit(@Param("unitId") String unitId, @Param("userId") String userId);

    String getUserDepartIdByUnitId(@Param("userId") String userId, @Param("unitId") String unitId);
}
