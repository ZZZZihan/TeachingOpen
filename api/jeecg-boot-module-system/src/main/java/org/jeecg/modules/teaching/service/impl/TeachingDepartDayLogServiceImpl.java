package org.jeecg.modules.teaching.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.IdWorker;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.teaching.entity.TeachingDepartDayLog;
import org.jeecg.modules.teaching.enums.DepartDayLogType;
import org.jeecg.modules.teaching.mapper.TeachingDepartDayLogMapper;
import org.jeecg.modules.teaching.service.ITeachingDepartDayLogService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

/**
 * @Description: 班级每日教学记录
 * @Author: jeecg-boot
 * @Date:   2021-06-25
 * @Version: V1.0
 */
@Service
public class TeachingDepartDayLogServiceImpl extends ServiceImpl<TeachingDepartDayLogMapper, TeachingDepartDayLog> implements ITeachingDepartDayLogService {
    private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");
    private Clock clock = Clock.systemUTC();

    @Autowired
    private ISysDepartService sysDepartService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void recordAdditionalWorkAssignment(String departId) {
        addLog(departId, DepartDayLogType.ADDITIONAL_WORK_ASSIGN_COUNT);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void addLog(String departId, DepartDayLogType type) {
        // Validate the server enum before acquiring locks or writing anything.
        TeachingDepartDayLog log = initialLog(type);
        // Existing installations have no unique (department, day) key.
        // All event types share this lock so first-row creation is serialized.
        SysDepart department = sysDepartService.getOne(new LambdaQueryWrapper<SysDepart>()
                .eq(SysDepart::getId, departId).eq(SysDepart::getDelFlag, "0").last("FOR UPDATE"));
        if (department == null || !Objects.equals(departId, department.getId())) {
            throw new JeecgBootException("未找到目标班级");
        }
        // Use one business date for both the current read and the DATE insert.
        // Passing java.util.Date here lets JDBC and the JVM disagree at midnight.
        String day = LocalDate.now(clock.withZone(BUSINESS_ZONE)).toString();
        String id = baseMapper.selectDayIdForUpdate(departId, day);
        if (id == null) {
            log.setId(IdWorker.getIdStr()).setDepartId(departId).setDepartName(department.getDepartName());
            if (baseMapper.insertDayLog(log, day) != 1) throw new JeecgBootException("班级教学统计保存失败");
        } else if (baseMapper.incrementDayCounter(id, departId, day, type.name()) != 1) {
            throw new JeecgBootException("班级教学统计更新失败");
        }
    }

    private TeachingDepartDayLog initialLog(DepartDayLogType type) {
        if (type == null) throw new JeecgBootException("教学统计类型不能为空");
        TeachingDepartDayLog log = new TeachingDepartDayLog()
                .setAdditionalWorkAssignCount(0).setAdditionalWorkCorrectCount(0).setAdditionalWorkSubmitCount(0)
                .setCourseWorkAssignCount(0).setCourseWorkCorrectCount(0).setCourseWorkSubmitCount(0).setUnitOpenCount(0);
        switch (type) {
            case UNIT_OPEN_COUNT: log.setUnitOpenCount(1); break;
            case COURSE_WORK_ASSIGN_COUNT: log.setCourseWorkAssignCount(1); break;
            case ADDITIONAL_WORK_ASSIGN_COUNT: log.setAdditionalWorkAssignCount(1); break;
            case COURSE_WORK_SUBMIT_COUNT: log.setCourseWorkSubmitCount(1); break;
            case ADDITIONAL_WORK_SUBMIT_COUNT: log.setAdditionalWorkSubmitCount(1); break;
            case COURSE_WORK_CORRECT_COUNT: log.setCourseWorkCorrectCount(1); break;
            case ADDITIONAL_WORK_CORRECT_COUNT: log.setAdditionalWorkCorrectCount(1); break;
            default: throw new JeecgBootException("不支持的教学统计类型");
        }
        return log;
    }
}
