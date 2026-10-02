package org.jeecg.modules.teaching.service;

import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.system.service.ISysDataLogService;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.system.service.ISysUserDepartService;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.teaching.entity.*;
import org.jeecg.modules.teaching.enums.DepartDayLogType;
import org.jeecg.modules.teaching.vo.StudentWorkSubmission;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.*;
import java.util.stream.Collectors;

/** Student writes cannot set ownership, moderation, metrics or audit fields. */
@Service
public class TeachingWorkSubmissionService {
    @Autowired private TeachingAccessService access;
    @Autowired private ITeachingWorkService works;
    @Autowired private ITeachingCourseUnitService units;
    @Autowired private ITeachingCourseService courses;
    @Autowired private ITeachingCourseDeptService courseDeparts;
    @Autowired private ITeachingAdditionalWorkService assignments;
    @Autowired private ISysUserDepartService userDeparts;
    @Autowired private ISysDataLogService history;
    @Autowired private ISysFileService files;
    @Autowired private ITeachingDepartDayLogService dailyLog;
    @Autowired private RedisUtil redis;

    @Transactional
    public TeachingWork submit(StudentWorkSubmission request) {
        LoginUser user = access.currentUser();
        if (user == null) throw new UnauthorizedException("请先登录");
        String courseId = StringUtils.trimToEmpty(request.getCourseId());
        String additionalId = StringUtils.trimToEmpty(request.getAdditionalId());
        if (!courseId.isEmpty() && !additionalId.isEmpty()) {
            throw new JeecgBootException("课程作业和附加作业不能同时提交");
        }
        String status = request.getWorkStatus() == null ? "0" : request.getWorkStatus();
        if (!"0".equals(status) && !"1".equals(status)) {
            throw new JeecgBootException("只能保存草稿或提交作业");
        }

        QueryWrapper<TeachingWork> lookup = new QueryWrapper<>();
        if (StringUtils.isNotBlank(request.getId())) {
            lookup.eq("id", request.getId());
        } else {
            lookup.eq("user_id", user.getId());
            if (!courseId.isEmpty()) lookup.eq("course_id", courseId);
            else if (!additionalId.isEmpty()) lookup.eq("additional_id", additionalId);
            else lookup.eq("work_name", request.getWorkName()).eq("work_type", request.getWorkType())
                    .and(q -> q.isNull("course_id").or().eq("course_id", ""))
                    .and(q -> q.isNull("additional_id").or().eq("additional_id", ""));
        }
        // Existing-row updates serialize with each other. New-work deduplication
        // across concurrent requests still needs a separate unique-key policy.
        List<TeachingWork> matches = works.list(lookup.last("FOR UPDATE"));
        if (StringUtils.isNotBlank(request.getId()) && matches.isEmpty()) {
            throw new UnauthorizedException("无作业提交权限");
        }
        if (matches.size() > 1) throw new JeecgBootException("存在多个同名作品，请从我的作品打开后保存");
        TeachingWork existing = matches.isEmpty() ? null : matches.get(0);
        if (existing != null) {
            if (!Objects.equals(existing.getUserId(), user.getId()) || Integer.valueOf(1).equals(existing.getDelFlag())) {
                throw new UnauthorizedException("无作业提交权限");
            }
            if ((!courseId.isEmpty() && !courseId.equals(existing.getCourseId()))
                    || (!additionalId.isEmpty() && !additionalId.equals(existing.getAdditionalId()))) {
                throw new UnauthorizedException("不能更换作品所属任务");
            }
            courseId = StringUtils.trimToEmpty(existing.getCourseId());
            additionalId = StringUtils.trimToEmpty(existing.getAdditionalId());
            if (!courseId.isEmpty() && !additionalId.isEmpty()) throw new JeecgBootException("作品任务归属异常，请联系教师处理");
        }
        String depart = submissionDepart(user, courseId, additionalId, existing, request.getDepartId());
        TeachingWork saved = new TeachingWork();
        saved.setId(existing == null ? null : existing.getId());
        saved.setWorkName(request.getWorkName() == null && existing != null ? existing.getWorkName() : request.getWorkName());
        saved.setWorkType(request.getWorkType() == null && existing != null ? existing.getWorkType() : request.getWorkType());
        saved.setWorkFile(request.getWorkFile() == null && existing != null ? existing.getWorkFile() : request.getWorkFile());
        if (StringUtils.isBlank(saved.getWorkName()) || saved.getWorkName().length() > 64
                || StringUtils.isBlank(saved.getWorkType()) || saved.getWorkType().length() > 32
                || StringUtils.isBlank(saved.getWorkFile()) || saved.getWorkFile().length() > 32) {
            throw new JeecgBootException("请提供有效的作品名称、类型和文件");
        }
        saved.setWorkCover(request.getWorkCover());
        requireAttachment(user, saved.getWorkFile(), existing);
        if (StringUtils.isNotBlank(saved.getWorkCover())) requireAttachment(user, saved.getWorkCover(), existing);
        saved.setHasCloudData(request.getHasCloudData());
        saved.setWorkStatus(status);
        saved.setDepartId(depart);
        // Assignment identity comes from the existing work when updating. Scene
        // is derived, rather than trusting a caller-supplied exam/course label.
        saved.setCourseId(courseId);
        saved.setAdditionalId(additionalId);
        saved.setWorkScene(!courseId.isEmpty() ? "course" : !additionalId.isEmpty() ? "additional" : "create");
        boolean changed;
        if (existing == null) {
            saved.setUserId(user.getId());
            saved.setCreateBy(user.getUsername());
            saved.setCreateTime(new Date());
            saved.setSysOrgCode(user.getOrgCode());
            saved.setDelFlag(0);
            saved.setViewNum(0);
            saved.setStarNum(0);
            saved.setCollectNum(0);
            changed = works.save(saved);
        } else {
            // Preserve the actual previous version, and roll it back if saving
            // the work or its daily record fails in this same transaction.
            history.addDataLog("teaching_work", existing.getId(), JSONObject.toJSONString(existing));
            changed = works.updateById(saved);
        }
        if (!changed) throw new JeecgBootException("作品保存失败，请刷新后重试");
        if ("1".equals(status) && StringUtils.isNotBlank(depart)) {
            if (!additionalId.isEmpty()) recordSubmission(saved, "addiWorkSubmit", DepartDayLogType.ADDITIONAL_WORK_SUBMIT_COUNT);
            else if (!courseId.isEmpty()) recordSubmission(saved, "courseWorkSubmit", DepartDayLogType.COURSE_WORK_SUBMIT_COUNT);
        }
        return works.getById(saved.getId());
    }

    private String submissionDepart(LoginUser user, String unitId, String assignmentId,
                                    TeachingWork existing, String requestedDepart) {
        List<String> memberships = userDeparts.userDepartIds(user.getId());
        if (memberships == null) memberships = Collections.emptyList();
        List<String> eligible = new ArrayList<>();
        if (!unitId.isEmpty()) {
            TeachingCourseUnit unit = units.getById(unitId);
            TeachingCourse course = unit == null ? null : courses.getById(unit.getCourseId());
            if (unit == null || course == null || Integer.valueOf(1).equals(unit.getDelFlag())
                    || Integer.valueOf(1).equals(course.getDelFlag())) throw new UnauthorizedException("无课程权限");
            if (!memberships.isEmpty()) {
                eligible = courseDeparts.list(new QueryWrapper<TeachingCourseDept>()
                        .eq("course_id", course.getId()).in("dept_id", memberships)).stream()
                        .map(TeachingCourseDept::getDeptId).distinct().sorted().collect(Collectors.toList());
            }
            if (eligible.isEmpty()) {
                if (existing != null && StringUtils.isNotBlank(existing.getDepartId())) {
                    throw new UnauthorizedException("原班级已无任务提交权限");
                }
                if (Boolean.TRUE.equals(course.getIsShared()) || access.isAdministrator()) return "";
                throw new UnauthorizedException("无课程权限");
            }
        } else if (!assignmentId.isEmpty()) {
            TeachingAdditionalWork assignment = assignments.getById(assignmentId);
            if (assignment == null || !Integer.valueOf(1).equals(assignment.getStatus())
                    || StringUtils.isBlank(assignment.getWorkDept())) throw new UnauthorizedException("无附加作业权限");
            final List<String> memberIds = memberships;
            eligible = Arrays.stream(assignment.getWorkDept().split(",")).map(String::trim)
                    .filter(memberIds::contains).distinct().sorted().collect(Collectors.toList());
            if (eligible.isEmpty()) throw new UnauthorizedException("无附加作业权限");
        } else {
            return existing == null ? "" : StringUtils.trimToEmpty(existing.getDepartId());
        }
        if (existing != null && StringUtils.isNotBlank(existing.getDepartId())) {
            if (!eligible.contains(existing.getDepartId())) throw new UnauthorizedException("原班级已无任务提交权限");
            return existing.getDepartId();
        }
        // A requested class is a hint only if both membership and assignment
        // authorize it. Otherwise derive a stable eligible class on the server.
        return eligible.contains(requestedDepart) ? requestedDepart : eligible.get(0);
    }

    private void recordSubmission(TeachingWork work, String kind, DepartDayLogType type) {
        String key = "departLog:" + kind + ":" + work.getDepartId();
        if (redis.sHasKey(key, work.getId())) return;
        dailyLog.addLog(work.getDepartId(), type);
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronizationAdapter() {
            @Override public void afterCommit() { redis.sSet(key, work.getId()); }
        });
    }

    private void requireAttachment(LoginUser user, String fileId, TeachingWork existing) {
        SysFile file = files.getById(fileId);
        boolean retained = existing != null && (fileId.equals(existing.getWorkFile()) || fileId.equals(existing.getWorkCover()));
        // Sent works legitimately retain another author's shared attachment.
        // A replacement must be a registered file uploaded by the current user.
        if (file == null || (!retained && !user.getUsername().equals(file.getCreateBy()))) {
            throw new UnauthorizedException("无附件使用权限");
        }
    }
}
