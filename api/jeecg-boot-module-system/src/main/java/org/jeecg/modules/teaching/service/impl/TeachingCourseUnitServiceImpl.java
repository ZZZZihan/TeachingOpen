package org.jeecg.modules.teaching.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.jeecg.modules.teaching.entity.TeachingCourseUnit;
import org.jeecg.modules.teaching.mapper.TeachingCourseUnitMapper;
import org.jeecg.modules.teaching.model.CourseUnitModel;
import org.jeecg.modules.teaching.model.CourseUnitWorkModel;
import org.jeecg.modules.teaching.service.ITeachingCourseUnitService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.beans.factory.annotation.Autowired;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.modules.teaching.model.CourseMapUpdateRequest;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import java.util.HashSet;
import java.util.Set;
import java.util.List;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;

/**
 * @Description: 课程单元
 * @Author: jeecg-boot
 * @Date:   2020-04-14
 * @Version: V1.0
 */
@Service
public class TeachingCourseUnitServiceImpl extends ServiceImpl<TeachingCourseUnitMapper, TeachingCourseUnit> implements ITeachingCourseUnitService {

    @Autowired private TeachingAccessService teachingAccessService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public boolean updateMapPositions(CourseMapUpdateRequest request) {
        if (request == null || StringUtils.isBlank(request.getCourseId()) || request.getUnits() == null
                || request.getUnits().isEmpty()) throw new IllegalArgumentException("请提供课程及课程单元坐标");
        if (!teachingAccessService.isAdministrator()) throw new UnauthorizedException("无课程地图管理权限");
        teachingAccessService.requireCourse(request.getCourseId());
        Set<String> ids = new HashSet<>();
        for (CourseMapUpdateRequest.UnitPosition unit : request.getUnits()) {
            if (unit == null || StringUtils.isBlank(unit.getId()) || !ids.add(unit.getId())
                    || unit.getMapX() == null || unit.getMapY() == null) {
                throw new IllegalArgumentException("课程单元 ID 不能为空或重复，坐标必须为整数");
            }
        }
        // Lock every requested target in this course before the first write. A mixed-course
        // or missing/deleted unit fails the whole batch without touching any coordinates.
        List<String> lockedIds = this.baseMapper.lockMapUnits(request.getCourseId(), ids);
        if (lockedIds.size() != ids.size() || !ids.equals(new HashSet<>(lockedIds))) return false;
        for (CourseMapUpdateRequest.UnitPosition unit : request.getUnits()) {
            if (this.baseMapper.updateMapPosition(request.getCourseId(), unit.getId(), unit.getMapX(), unit.getMapY()) != 1) {
                TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
                return false;
            }
        }
        return true;
    }

    @Override
    public IPage<CourseUnitModel> getCourseUnitList(Page<CourseUnitModel> page, QueryWrapper<CourseUnitModel> queryWrapper) {
        return page.setRecords(this.baseMapper.getCourseUnitList(page, queryWrapper));
    }

    @Override
    public CourseUnitWorkModel getCourseWorkUnit(String unitId, String userId) {
        return this.baseMapper.getCourseWorkUnit(unitId, userId);
    }

    @Override
    public String getUserDepartIdByUnitId(String userId, String unitId) {
        return this.baseMapper.getUserDepartIdByUnitId(userId, unitId);
    }

}
