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

    @Override
    @Transactional(rollbackFor = Exception.class)
    public boolean updateExistingUnits(List<TeachingCourseUnit> units) {
        for (TeachingCourseUnit unit : units) {
            // Check the actual write, not an earlier read that can race with deletion.
            if (!updateById(unit)) {
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
