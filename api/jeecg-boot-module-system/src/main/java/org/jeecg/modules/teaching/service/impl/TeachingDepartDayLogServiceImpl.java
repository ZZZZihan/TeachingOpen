package org.jeecg.modules.teaching.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.IdWorker;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.jeecg.common.exception.JeecgBootException;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.teaching.entity.TeachingDepartDayLog;
import org.jeecg.modules.teaching.entity.TeachingCourse;
import org.jeecg.modules.teaching.entity.TeachingCourseUnit;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.enums.DepartDayLogType;
import org.jeecg.modules.teaching.enums.UnitViewLogResult;
import org.jeecg.modules.teaching.enums.WorkEventType;
import org.jeecg.modules.teaching.mapper.TeachingCourseUnitMapper;
import org.jeecg.modules.teaching.mapper.TeachingCourseMapper;
import org.jeecg.modules.teaching.mapper.TeachingDepartDayLogMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.service.ITeachingDepartDayLogService;
import org.jeecg.modules.teaching.service.LegacyUnitViewMarkerStore;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

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
    @Autowired
    private SysUserMapper users;
    @Autowired
    private TeachingCourseUnitMapper units;
    @Autowired
    private TeachingCourseMapper courses;
    @Autowired
    private TeachingAccessService teachingAccessService;
    @Autowired
    private LegacyUnitViewMarkerStore legacyUnitViews;
    @Autowired
    private TeachingWorkMapper works;

    @Override
    @Transactional(propagation = Propagation.MANDATORY, rollbackFor = Exception.class)
    public void recordWorkEvent(String workId, WorkEventType eventType) {
        if (eventType == null) throw new JeecgBootException("作品统计类型不能为空");
        // Work -> department -> event -> daily row is the shared lock order.
        // Read the stored task identity, never the caller's editable DTO.
        TeachingWork work = works.selectOne(new QueryWrapper<TeachingWork>().eq("id", workId).last("FOR UPDATE"));
        if (work == null || !Objects.equals(workId, work.getId())) throw new JeecgBootException("未找到目标作品");
        boolean course = StringUtils.hasText(work.getCourseId());
        boolean additional = StringUtils.hasText(work.getAdditionalId());
        if (!StringUtils.hasText(work.getDepartId()) || (!course && !additional)) return;
        if (course && additional) throw new JeecgBootException("作品任务归属异常，请联系教师处理");
        if (baseMapper.workEventCutoverComplete() != 1) throw new JeecgBootException("作品统计迁移未完成，请联系管理员后重试");
        DepartDayLogType counter = eventType == WorkEventType.SUBMIT
                ? (course ? DepartDayLogType.COURSE_WORK_SUBMIT_COUNT : DepartDayLogType.ADDITIONAL_WORK_SUBMIT_COUNT)
                : (course ? DepartDayLogType.COURSE_WORK_CORRECT_COUNT : DepartDayLogType.ADDITIONAL_WORK_CORRECT_COUNT);
        SysDepart department = lockDepartment(work.getDepartId());
        String state = baseMapper.selectWorkEventStateForUpdate(workId, eventType.name());
        if ("COUNTED".equals(state) || "LEGACY_UNRESOLVED".equals(state)) return;
        if ("LEGACY_REVIEW".equals(state)) throw new JeecgBootException("历史作品统计尚未核对，请联系管理员完成迁移后重试");
        if (state != null && !"READY".equals(state)) throw new JeecgBootException("作品统计事件状态无效");
        String day = LocalDate.now(clock.withZone(BUSINESS_ZONE)).toString();
        int changed = state == null
                ? baseMapper.insertWorkEvent(workId, eventType.name(), work.getDepartId(), day)
                : baseMapper.countReadyWorkEvent(workId, eventType.name(), work.getDepartId(), day);
        if (changed != 1) throw new JeecgBootException("作品统计事件保存失败");
        incrementCounter(work.getDepartId(), department, counter, day, initialLog(counter));
    }

    @Override
    @Transactional(isolation = Isolation.READ_COMMITTED, rollbackFor = Exception.class)
    public UnitViewLogResult recordUnitView(String userId, String unitId) {
        if (userId == null || userId.isEmpty() || unitId == null || !unitId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new JeecgBootException("单元浏览参数无效");
        }
        SysUser actor = users.selectById(userId);
        if (actor == null || !userId.equals(actor.getId()) || !Integer.valueOf(0).equals(actor.getDelFlag())
                || !Integer.valueOf(1).equals(actor.getStatus())) throw new UnauthorizedException("账户不可用");
        // Existing IDs use case-insensitive collations; use the canonical ID for
        // the binary ledger key and reject aliases rather than counting twice.
        TeachingCourseUnit unit = units.selectById(unitId);
        if (unit == null || !unitId.equals(unit.getId())
                || (unit.getDelFlag() != null && !Integer.valueOf(0).equals(unit.getDelFlag()))) {
            throw new JeecgBootException("未找到目标单元");
        }
        TeachingCourse course = courses.selectById(unit.getCourseId());
        if (course == null || (course.getDelFlag() != null && !Integer.valueOf(0).equals(course.getDelFlag()))) {
            throw new JeecgBootException("未找到目标课程");
        }
        // Reading permission and eligibility for a class counter are distinct.
        // Authorize every caller before a no-op, including ordinary students.
        teachingAccessService.requireCourse(unit.getCourseId());
        if (!Integer.valueOf(2).equals(actor.getUserIdentity())) return UnitViewLogResult.NOT_APPLICABLE;
        String departId = units.getUserDepartIdByUnitId(userId, unitId);
        // Admin previews and shared-course reading need not belong to a class.
        // Do not invent a class association or report these legal reads as failures.
        if (departId == null || departId.isEmpty()) return UnitViewLogResult.NOT_APPLICABLE;
        // The class row serializes this event and all daily counters. READ_COMMITTED
        // keeps an absent ledger row from gap-locking another class's first insert.
        // Existing ledger checks remain current reads after waiting for the class.
        SysDepart department = lockDepartment(departId);
        String state = baseMapper.selectUnitViewStateForUpdate(departId, unitId);
        if ("COUNTED".equals(state)) return UnitViewLogResult.ALREADY_COUNTED;
        if ("LEGACY_UNRESOLVED".equals(state)) return UnitViewLogResult.LEGACY_UNRESOLVED;
        if (state != null) throw new JeecgBootException("单元浏览事件状态无效");
        boolean legacy = legacyUnitViews.contains(departId, unitId);
        String day = LocalDate.now(clock.withZone(BUSINESS_ZONE)).toString();
        if (baseMapper.insertUnitViewEvent(departId, unitId, userId,
                legacy ? "LEGACY_UNRESOLVED" : "COUNTED", legacy ? null : day) != 1) {
            throw new JeecgBootException("单元浏览事件保存失败");
        }
        // Preserve ambiguous history without either recounting it or claiming success.
        if (legacy) return UnitViewLogResult.LEGACY_UNRESOLVED;
        incrementCounter(departId, department, DepartDayLogType.UNIT_OPEN_COUNT, day,
                initialLog(DepartDayLogType.UNIT_OPEN_COUNT));
        return UnitViewLogResult.COUNTED;
    }

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
        SysDepart department = lockDepartment(departId);
        String day = LocalDate.now(clock.withZone(BUSINESS_ZONE)).toString();
        incrementCounter(departId, department, type, day, log);
    }

    private SysDepart lockDepartment(String departId) {
        // Existing installations have no unique (department, day) key.
        // All event types share this lock so first-row creation is serialized.
        SysDepart department = sysDepartService.getOne(new LambdaQueryWrapper<SysDepart>()
                .eq(SysDepart::getId, departId).eq(SysDepart::getDelFlag, "0").last("FOR UPDATE"));
        if (department == null || !Objects.equals(departId, department.getId())) {
            throw new JeecgBootException("未找到目标班级");
        }
        return department;
    }

    private void incrementCounter(String departId, SysDepart department, DepartDayLogType type,
                                  String day, TeachingDepartDayLog log) {
        // Use one business date for both the current read and the DATE insert.
        // Passing java.util.Date here lets JDBC and the JVM disagree at midnight.
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
