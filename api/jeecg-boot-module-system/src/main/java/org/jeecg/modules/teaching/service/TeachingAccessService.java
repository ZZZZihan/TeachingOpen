package org.jeecg.modules.teaching.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.system.service.ISysUserDepartService;
import org.jeecg.modules.system.service.ISysUserService;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.entity.TeachingAdditionalWork;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

/** Resource checks for endpoints shared by learning and management pages. */
@Service
public class TeachingAccessService {
    @Autowired private ITeachingCourseDeptService courseDeptService;
    @Autowired private ISysDepartService departService;
    @Autowired private ISysUserDepartService userDepartService;
    @Autowired private ISysUserService userService;

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

    /** Assignment details share the class boundary used by student task lists.
     * They have no public-course flag: publication makes them visible only to
     * assigned members; teachers can preview drafts for their current classes. */
    public boolean canReadAdditionalWork(TeachingAdditionalWork work) {
        if (work == null) return false;
        SysUser user = currentAdditionalWorkUser();
        if (user == null) return false;
        List<String> roles = additionalWorkRoles(user);
        if (roles.contains("admin") || roles.contains("dev")) return true;
        if (StringUtils.isBlank(work.getWorkDept())) return false;
        Set<String> assigned = Arrays.stream(work.getWorkDept().split(","))
                .map(String::trim).filter(id -> !id.isEmpty()).collect(Collectors.toSet());
        if (!Collections.disjoint(assigned, additionalWorkManagedDepartIds(user, roles))) return true;
        List<String> member = userDepartService.userDepartIds(user.getId());
        return Integer.valueOf(1).equals(work.getStatus()) && member != null && !Collections.disjoint(assigned, member);
    }

    public void requireReadAdditionalWork(TeachingAdditionalWork work) {
        if (!canReadAdditionalWork(work)) throw new UnauthorizedException("无附加作业访问权限");
    }

    /** Management lists use the same live identity and teacher scope as detail
     * previews. Keep the CSV boundary in SQL so counts and pages stay scoped. */
    public void limitManagedAdditionalWorks(QueryWrapper<TeachingAdditionalWork> query) {
        SysUser user = currentAdditionalWorkUser();
        if (user == null) throw new UnauthorizedException("无附加作业管理权限");
        List<String> roles = additionalWorkRoles(user);
        if (roles.contains("admin") || roles.contains("dev")) return;
        List<String> managed = additionalWorkManagedDepartIds(user, roles);
        if (managed.isEmpty()) throw new UnauthorizedException("无附加作业管理权限");
        // String.trim() used by detail authorization removes only U+0000..0020
        // at token edges. Do not remove whitespace from inside a class ID.
        String edgeWhitespace = "[\\x{0000}-\\x{0020}]*";
        String ids = managed.stream().map(TeachingAccessService::escapeAdditionalWorkClassPattern)
                .collect(Collectors.joining("|"));
        // Absolute anchors prevent ICU '$' from accepting a final Unicode line
        // separator that Java trim() would keep inside the class token.
        String pattern = "(\\A|,)" + edgeWhitespace + "(?:" + ids + ")" + edgeWhitespace + "(,|\\z)";
        // MySQL 8 uses ICU regex. Explicit 'c' avoids case aliases even under a
        // case-insensitive collation; apply() binds the pattern as a value.
        query.apply("REGEXP_LIKE(work_dept, {0}, 'c')", pattern);
    }

    private SysUser currentAdditionalWorkUser() {
        LoginUser principal = currentUser();
        if (principal == null || StringUtils.isBlank(principal.getId())) return null;
        SysUser user = userService.getById(principal.getId());
        return user != null && Objects.equals(principal.getId(), user.getId())
                && Integer.valueOf(0).equals(user.getDelFlag()) && Integer.valueOf(1).equals(user.getStatus()) ? user : null;
    }

    private List<String> additionalWorkRoles(SysUser user) {
        List<String> roles = userService.getRoleById(user.getId());
        return roles == null ? Collections.emptyList() : roles;
    }

    private List<String> additionalWorkManagedDepartIds(SysUser user, List<String> roles) {
        if (!roles.contains("teacher") || StringUtils.isBlank(user.getDepartIds())) return Collections.emptyList();
        List<String> managed = departService.getMySubDepIdsByDepId(user.getDepartIds());
        if (managed == null) return Collections.emptyList();
        // Such IDs cannot equal any trimmed CSV token, including in details.
        return managed.stream().filter(id -> id != null && !id.isEmpty() && id.equals(id.trim()) && !id.contains(","))
                .distinct().collect(Collectors.toList());
    }

    private static String escapeAdditionalWorkClassPattern(String id) {
        StringBuilder escaped = new StringBuilder();
        for (int index = 0; index < id.length(); index++) {
            char character = id.charAt(index);
            if ("\\.^$|?*+()[]{}".indexOf(character) >= 0) escaped.append('\\');
            escaped.append(character);
        }
        return escaped.toString();
    }

    /** Sharing a detail URL does not publish a draft or a graded submission. */
    public void requireCommunityWork(TeachingWork work) {
        if (work == null || !Integer.valueOf(0).equals(work.getDelFlag())) {
            throw new UnauthorizedException("作品不存在或无访问权限");
        }
        if ("3".equals(work.getWorkStatus()) || "4".equals(work.getWorkStatus())) return;
        requireReadWork(work);
    }

    /** WebSocket callbacks have no request-bound Shiro Subject. Recheck current
     * roles and class scope using the identity verified for this connection. */
    public boolean canReadCommunityWork(TeachingWork work, LoginUser user) {
        if (work == null || !Integer.valueOf(0).equals(work.getDelFlag())) return false;
        if ("3".equals(work.getWorkStatus()) || "4".equals(work.getWorkStatus())) return true;
        if (user == null) return false;
        if (Objects.equals(user.getId(), work.getUserId())) return true;
        Set<String> roles = userService.getUserRolesSet(user.getUsername());
        if (roles.contains("admin") || roles.contains("dev")) return true;
        if (!roles.contains("teacher")) return false;
        SysUser current = userService.getById(user.getId());
        if (current == null || StringUtils.isBlank(current.getDepartIds())) return false;
        List<String> managed = departService.getMySubDepIdsByDepId(current.getDepartIds());
        if (managed == null || managed.isEmpty()
                || (StringUtils.isNotBlank(work.getDepartId()) && !managed.contains(work.getDepartId()))) return false;
        List<String> ownerDeparts = userDepartService.userDepartIds(work.getUserId());
        return ownerDeparts != null && ownerDeparts.stream().anyMatch(managed::contains);
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
