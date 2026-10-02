package org.jeecg.modules.teaching.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.system.service.ISysUserDepartService;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

/** Resource checks for endpoints shared by learning and management pages. */
@Service
public class TeachingAccessService {
    @Autowired private ITeachingCourseDeptService courseDeptService;
    @Autowired private ISysDepartService departService;
    @Autowired private ISysUserDepartService userDepartService;

    public LoginUser currentUser() {
        return (LoginUser) SecurityUtils.getSubject().getPrincipal();
    }

    public boolean isAdministrator() {
        return SecurityUtils.getSubject().hasRole("admin") || SecurityUtils.getSubject().hasRole("dev");
    }

    public List<String> managedDepartIds() {
        LoginUser user = currentUser();
        if (user == null || !SecurityUtils.getSubject().hasRole("teacher") || StringUtils.isBlank(user.getDepartIds())) {
            return Collections.emptyList();
        }
        List<String> ids = departService.getMySubDepIdsByDepId(user.getDepartIds());
        return ids == null ? Collections.emptyList() : ids;
    }

    public boolean canManageWork(TeachingWork work) {
        if (work == null || currentUser() == null) return false;
        if (isAdministrator()) return true;
        List<String> managed = managedDepartIds();
        if (managed.isEmpty() || (StringUtils.isNotBlank(work.getDepartId()) && !managed.contains(work.getDepartId()))) return false;
        List<String> ownerDeparts = userDepartService.userDepartIds(work.getUserId());
        return ownerDeparts != null && ownerDeparts.stream().anyMatch(managed::contains);
    }

    public void requireManageWork(TeachingWork work) {
        if (!canManageWork(work)) throw new UnauthorizedException("无作业管理权限");
    }

    public void requireReadWork(TeachingWork work) {
        LoginUser user = currentUser();
        if (work != null && user != null && Objects.equals(user.getId(), work.getUserId())) return;
        requireManageWork(work);
    }

    /** Sharing a detail URL does not publish a draft or a graded submission. */
    public void requireCommunityWork(TeachingWork work) {
        if (work == null || !Integer.valueOf(0).equals(work.getDelFlag())) {
            throw new UnauthorizedException("作品不存在或无访问权限");
        }
        if ("3".equals(work.getWorkStatus()) || "4".equals(work.getWorkStatus())) return;
        requireReadWork(work);
    }

    /** Apply the same owner and class boundary before list pagination or export. */
    public void limitManagedWorks(QueryWrapper<?> query) {
        if (isAdministrator()) return;
        List<String> managed = managedDepartIds();
        if (managed.isEmpty()) throw new UnauthorizedException("无作业管理权限");
        query.and(scope -> scope.isNull("teaching_work.depart_id")
                .or().eq("teaching_work.depart_id", "")
                .or().in("teaching_work.depart_id", managed));
        String placeholders = IntStream.range(0, managed.size())
                .mapToObj(index -> "{" + index + "}").collect(Collectors.joining(","));
        query.apply("EXISTS (SELECT 1 FROM sys_user_depart work_owner_depart "
                + "WHERE work_owner_depart.user_id = teaching_work.user_id "
                + "AND work_owner_depart.dep_id IN (" + placeholders + "))", managed.toArray());
    }

    public void requireCourse(String courseId) {
        LoginUser user = currentUser();
        if (user == null || (!isAdministrator() && !courseDeptService.checkCoursePermission(courseId, user.getId()))) {
            throw new UnauthorizedException("无课程权限");
        }
    }
}
